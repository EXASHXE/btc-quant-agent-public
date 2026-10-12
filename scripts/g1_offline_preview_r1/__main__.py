"""python -m scripts.g1_offline_preview_r1 --fixture long_24h.json --output ..."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from .model import SafetyViolation, canonical, decimal, exact, initial_state, redact_text, timestamp
from .storage import OWN_SCRATCH, Engine, guard_directory, strict_json

FIXTURES = Path(__file__).parent / "fixtures"


class OfflineLLMAnalysisPort:
    """Deterministic JSON-only mock; reducer validates the full analysis schema."""

    def analyze(self, output):
        value = strict_json(output if isinstance(output, str) else canonical(output))
        exact(
            value,
            {
                "schema_version",
                "signal_id",
                "proposal_hash",
                "source_hash",
                "as_of",
                "summary",
                "risk",
            },
            "LLM_SCHEMA",
        )
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or value["risk"] != "DESCRIPTIVE_ONLY"
            or not isinstance(value["summary"], str)
            or not 1 <= len(value["summary"]) <= 256
        ):
            raise SafetyViolation("LLM_SCHEMA")
        for key in ("signal_id", "proposal_hash", "source_hash"):
            if not isinstance(value[key], str) or not value[key]:
                raise SafetyViolation("LLM_SCHEMA")
        timestamp(value["as_of"])
        value["summary"] = redact_text(value["summary"])
        return value


def load_fixture(name):
    # Filename admission precedes any stat/list/resolve on the caller's path.
    if (
        not isinstance(name, str)
        or Path(name).name != name
        or name not in ("long_24h.json", "short_24h.json")
    ):
        raise SafetyViolation("FIXTURE_PATH_SCOPE")
    path = FIXTURES / name
    if FIXTURES.is_symlink() or path.is_symlink():
        raise SafetyViolation("PATH_SYMLINK")
    raw = path.read_bytes()
    if len(raw) > 2_000_000:
        raise SafetyViolation("FIXTURE_SIZE")
    f = strict_json(raw.decode())
    if (
        not isinstance(f, dict)
        or set(f)
        != {
            "schema_version",
            "fixture_name",
            "synthetic_only",
            "scenario_hours",
            "ACK_tail_minutes",
            "trusted_approvals",
            "events",
        }
        or f["schema_version"] != 1
        or f["synthetic_only"] is not True
    ):
        raise SafetyViolation("FIXTURE_SCHEMA")
    return f, hashlib.sha256(raw).hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture", default="long_24h.json")
    p.add_argument("--output", default=str(OWN_SCRATCH / "preview-long"))
    p.add_argument("--crash-event")
    p.add_argument(
        "--crash-edge",
        choices=[
            "before_append",
            "after_append",
            "after_fsync",
            "after_snapshot",
            "after_outbox_delivery",
        ],
    )
    args = p.parse_args(argv)

    def crash(edge, event):
        if edge == args.crash_edge and (
            event["id"] == args.crash_event or args.crash_event == "OUTBOX"
        ):
            os._exit(91)

    engine = None
    try:
        fixture, fixture_hash = load_fixture(args.fixture)
        out = guard_directory(Path(args.output))
        initial = initial_state(fixture["trusted_approvals"])
        initial["fixture_identity"] = fixture_hash
        with Engine(out, initial) as engine:
            port = OfflineLLMAnalysisPort()
            for event in fixture["events"]:
                if event["kind"] == "ANALYZE":
                    event = {**event, "payload": port.analyze(event["payload"])}
                engine.apply(event, hook=crash)
            engine.checkpoint()
            engine.deliver(hook=crash)
            receipt = {
                **engine.receipt(),
                "fixture_sha256": fixture_hash,
                "fixture_name": fixture["fixture_name"],
                "LLM_port": "DETERMINISTIC_OFFLINE_JSON_MOCK",
                "Feishu_port": "LOCAL_JSONL_OUTBOX_ONLY",
            }
            if (
                receipt["phase"] != "CLOSED"
                or receipt["pending_cash"]
                or decimal(receipt["reserved_notional"]) != 0
            ):
                raise SafetyViolation("TERMINAL_NOT_FLAT")
            (out / "RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n")
            print(canonical(receipt))
        return 0
    except (SafetyViolation, OSError, UnicodeError) as exc:
        code = exc.code if isinstance(exc, SafetyViolation) else "OFFLINE_IO_ERROR"
        result = {
            "status": "G1_OFFLINE_PREVIEW_FAIL_CLOSED",
            "code": code,
            "health": "NOT_READY_FAIL_CLOSED",
            "retry_classification": "RETRY_AFTER_WRITER_RELEASE"
            if code == "SINGLE_WRITER_LOCKED"
            else "STOP_REQUIRES_OPERATOR",
            "safety_status": "DRY_RUN_NO_NETWORK_NO_ORDERING",
            "not_authorized": "TESTNET_LIVE_PRODUCTION_OR_REAL_MONEY",
        }
        # No failed path is accessed to place receipts through an untrusted path.
        print(canonical(result))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
