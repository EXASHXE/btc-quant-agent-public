"""Bounded, fail-closed analysis providers for immutable decision cases."""

from __future__ import annotations

import asyncio
import json
import math
import os
import signal
import tempfile
import time
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from openai import AsyncOpenAI

from .models import AnalysisResultV1, CasePackageV1


class AnalysisMode(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"


class AnalysisBackend(Protocol):
    async def analyze(self, case: CasePackageV1, mode: AnalysisMode) -> AnalysisResultV1: ...


def _case_error(case: CasePackageV1, now_ms: int) -> str | None:
    try:
        case.verify()
    except (ValueError, TypeError):
        return "INVALID_CASE"
    if now_ms < case.created_at_ms or now_ms >= case.expires_at_ms:
        return "STALE_CASE"
    return None


def _parse_result(payload: Any, case: CasePackageV1, backend: str, model: str,
                  request_id: str | None) -> AnalysisResultV1:
    if isinstance(payload, AnalysisResultV1):
        raw = payload.model_dump(mode="json")
    elif isinstance(payload, str):
        raw = json.loads(payload)
    else:
        raw = payload
    if not isinstance(raw, dict):
        raise TypeError("invalid analysis payload")
    # Validate every provider field before replacing the provenance it cannot be trusted to set.
    validated = AnalysisResultV1.model_validate_json(json.dumps(raw))
    validated.verify_case(case)
    return AnalysisResultV1.model_validate_json(json.dumps({
        **validated.model_dump(mode="json"), "backend": backend, "model": model,
        "provider_request_id": request_id,
    }))


def _has_refusal(output: Any) -> bool:
    for item in output or ():
        if getattr(item, "type", None) == "refusal":
            return True
        for content in getattr(item, "content", ()) or ():
            if getattr(content, "type", None) == "refusal":
                return True
    return False


class ResponsesBackend:
    def __init__(self, model: str | None, timeout_seconds: float, *, client: Any = None,
                 clock_ms: Callable[[], int] | None = None,
                 max_output_tokens: int = 2048) -> None:
        self.model = model or ""
        self.timeout_seconds = timeout_seconds
        self.client = client
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self.max_output_tokens = max_output_tokens

    async def analyze(self, case: CasePackageV1, mode: AnalysisMode) -> AnalysisResultV1:
        reason = _case_error(case, self.clock_ms())
        if reason:
            return AnalysisResultV1.fail_closed(case, "responses", self.model, reason)
        if (not self.model.strip() or self.max_output_tokens <= 0 or
                not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0):
            return AnalysisResultV1.fail_closed(case, "responses", self.model, "BACKEND_CONFIG")
        case_json = case.canonical_json()
        if len(case_json.encode()) > 256 * 1024:
            return AnalysisResultV1.fail_closed(case, "responses", self.model,
                                                "CASE_TOO_LARGE")
        owned_client = self.client is None
        client: Any = None
        try:
            client = self.client if self.client is not None else AsyncOpenAI(max_retries=0)
            response = await asyncio.wait_for(client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": (
                        "Review the case for decision support only. Return AnalysisResultV1. "
                        "Do not request or describe executable orders. "
                        f"Mode: {mode.value}. Bind the result to the supplied case_id and case_hash."
                    )},
                    {"role": "user", "content": case_json},
                ],
                text_format=AnalysisResultV1, store=False,
                max_output_tokens=self.max_output_tokens,
            ), timeout=self.timeout_seconds)
            if response.status != "completed" or _has_refusal(response.output):
                raise ValueError("incomplete or refused response")
            if response.output_parsed is None:
                raise ValueError("missing parsed response")
            actual_model = getattr(response, "model", None) or self.model
            request_id = getattr(response, "id", None)
            return _parse_result(response.output_parsed, case, "responses", actual_model,
                                 request_id)
        except TimeoutError:
            reason = "BACKEND_TIMEOUT"
        except Exception:  # noqa: BLE001 - provider errors must not reach the caller
            reason = "BACKEND_RESPONSE_INVALID"
        finally:
            if owned_client and client is not None:
                try:
                    await asyncio.wait_for(client.close(), timeout=1)
                except Exception:  # noqa: BLE001, S110 - close errors cannot expose provider data
                    pass
        return AnalysisResultV1.fail_closed(case, "responses", self.model, reason)


class CodexExecBackend:
    def __init__(self, model: str | None, timeout_seconds: float, *,
                 process_factory: Any = None, clock_ms: Callable[[], int] | None = None,
                 max_output_tokens: int = 2048) -> None:
        self.model = model or ""
        self.timeout_seconds = timeout_seconds
        self.process_factory = process_factory or asyncio.create_subprocess_exec
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self.max_output_tokens = max_output_tokens

    async def analyze(self, case: CasePackageV1, mode: AnalysisMode) -> AnalysisResultV1:
        if mode != AnalysisMode.SECONDARY:
            return AnalysisResultV1.fail_closed(case, "codex_exec", self.model, "SECONDARY_ONLY")
        reason = _case_error(case, self.clock_ms())
        if reason:
            return AnalysisResultV1.fail_closed(case, "codex_exec", self.model, reason)
        if (not self.model.strip() or not math.isfinite(self.timeout_seconds) or
                self.timeout_seconds <= 0 or self.max_output_tokens <= 0):
            return AnalysisResultV1.fail_closed(case, "codex_exec", self.model,
                                                "BACKEND_CONFIG")
        prompt = ("Review this single case for decision support only. Return the required JSON "
                  "schema. No executable order, tools, files, or external data. "
                  f"Mode: {mode.value}. Output budget: {self.max_output_tokens} tokens.\n"
                  + case.canonical_json()).encode()
        if len(prompt) > 256 * 1024:
            return AnalysisResultV1.fail_closed(case, "codex_exec", self.model,
                                                "CASE_TOO_LARGE")
        try:
            return await asyncio.wait_for(self._run(case, prompt), self.timeout_seconds)
        except TimeoutError:
            reason = "BACKEND_TIMEOUT"
        except Exception:  # noqa: BLE001 - subprocess errors must not reach the caller
            reason = "BACKEND_RESPONSE_INVALID"
        return AnalysisResultV1.fail_closed(case, "codex_exec", self.model, reason)

    async def _run(self, case: CasePackageV1, prompt: bytes) -> AnalysisResultV1:
        with tempfile.TemporaryDirectory(prefix="decision-codex-") as temporary:
            schema = Path(temporary, "schema.json")
            result_path = Path(temporary, "result.json")
            schema.write_text(json.dumps(AnalysisResultV1.model_json_schema()), encoding="utf-8")
            env_names = ("PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                         "SYSTEMROOT", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL")
            env = {key: os.environ[key] for key in env_names if key in os.environ}
            kwargs: dict[str, Any] = {
                "cwd": temporary, "env": env, "stdin": asyncio.subprocess.PIPE,
                "stdout": asyncio.subprocess.DEVNULL, "stderr": asyncio.subprocess.DEVNULL,
            }
            if os.name == "posix":
                kwargs["start_new_session"] = True
            # No inherited hooks, MCP connections, project instructions or model tools.
            # The custom profile extends read-only but also denies host credential reads.
            # Do not pass --sandbox: legacy flags would override this stronger profile.
            settings = (
                'default_permissions="live-v1-review"',
                'permissions.live-v1-review.extends=":read-only"',
                ('permissions.live-v1-review.filesystem= {":root"="deny", '
                 '":minimal"="read", ":tmpdir"="deny", ":slash_tmp"="deny", '
                 '":workspace_roots"="read"}'),
                "permissions.live-v1-review.network.enabled=false",
                "features.shell_tool=false", "features.unified_exec=false",
                "features.apps=false", "features.hooks=false", "features.memories=false",
                "features.multi_agent=false", "features.plugins=false",
                "features.browser_use=false", "features.computer_use=false",
                "mcp_servers={}", 'web_search="disabled"', "project_doc_max_bytes=0",
            )
            config_args = tuple(arg for setting in settings for arg in ("-c", setting))
            process = await self.process_factory(
                "codex", "exec", "--model", self.model,
                "--ignore-user-config", "--ignore-rules", "--strict-config", *config_args,
                "--ephemeral", "--skip-git-repo-check", "--output-schema", str(schema),
                "-o", str(result_path),
                "-", **kwargs,
            )
            try:
                await process.communicate(input=prompt)
            except BaseException:
                if process.returncode is None:
                    if os.name == "posix":
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    else:
                        process.kill()
                    await asyncio.wait_for(process.wait(), timeout=5)
                raise
            if process.returncode != 0 or not result_path.is_file():
                raise ValueError("codex failed")
            if result_path.stat().st_size > 64 * 1024:
                raise ValueError("codex result too large")
            payload = result_path.read_text(encoding="utf-8")
            return _parse_result(payload, case, "codex_exec", self.model, None)
