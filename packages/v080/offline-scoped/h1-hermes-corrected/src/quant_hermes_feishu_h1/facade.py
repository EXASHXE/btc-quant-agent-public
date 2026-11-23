"""QUANT-owned local authenticated V1 facade service, UDS server with SO_PEERCRED, and client."""

from __future__ import annotations

import base64
import json
import os
import socket
import socketserver
import struct
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contract import (
    APPROVED_FAMILIES,
    APPROVED_SYMBOLS,
    CONTRACT_ID,
    DEFAULT_DEADLINE_MS,
    EVIDENCE_SYNTHETIC,
    EVIDENCE_UNKNOWN,
    HETEROGENEOUS_BANNER,
    MARKET_STATUSES,
    MAX_LIST_LIMIT,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    SAFE_ID_RE,
    SYNTHETIC_BANNER,
    UNKNOWN_EVIDENCE_BANNER,
    V1_ALL_TOOLS,
    ContractError,
    build_response_envelope,
    canonical_json,
    redact_error_text,
    validate_request_envelope,
)
from .journal_reader import ApprovedJournalRegistry, VerifiedCardRecord

_PEERCRED_FMT = "3i"
_PEERCRED_SIZE = struct.calcsize(_PEERCRED_FMT)
_FORBIDDEN_ARG_PATTERNS = ("select ", "insert ", "update ", "delete ", "drop ", "union ", "--", ";", "/")


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _encode_cursor(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if type(cursor) is not str or not cursor or len(cursor) > 128:
        raise ContractError("INVALID_ARGUMENT", "Invalid pagination cursor")
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        obj = json.loads(raw.decode("utf-8"))
        offset = obj["offset"]
        if type(offset) is not int or offset < 0 or offset > 100_000:
            raise ValueError("offset out of bounds")
        return offset
    except Exception as exc:
        raise ContractError("INVALID_ARGUMENT", "Malformed pagination cursor") from exc


def _validate_id_arg(value: Any, name: str) -> str:
    if type(value) is not str or not value or not SAFE_ID_RE.fullmatch(value):
        raise ContractError("INVALID_ARGUMENT", f"Invalid {name}")
    if name == "episode_id" and value.startswith("noep:"):
        raise ContractError("INVALID_ARGUMENT", "Synthetic noep: episode_id is forbidden")
    lower = value.lower()
    for pat in _FORBIDDEN_ARG_PATTERNS:
        if pat in lower:
            raise ContractError("INVALID_ARGUMENT", f"Forbidden pattern in {name}")
    return value


def _classify_aggregate_evidence(classes: set[str]) -> tuple[str, str, str, bool]:
    """Classify response evidence class across a collection without min() guessing."""
    if not classes:
        return EVIDENCE_UNKNOWN, "EMPTY_UNQUALIFIED", UNKNOWN_EVIDENCE_BANNER, False
    if len(classes) == 1:
        only = next(iter(classes))
        banner = SYNTHETIC_BANNER if only == EVIDENCE_SYNTHETIC else f"{only} / MARKET_SIDE_ONLY"
        return only, "HOMOGENEOUS", banner, False
    return EVIDENCE_UNKNOWN, "HETEROGENEOUS_MIXED", HETEROGENEOUS_BANNER, True


def _reject_extra_args(args: dict[str, Any], allowed: frozenset[str]) -> None:
    forbidden = {"sql", "query", "path", "file", "db", "sqlite", "command", "shell", "url"}
    bad = set(args.keys()) & forbidden
    if bad:
        raise ContractError("INVALID_ARGUMENT", f"Forbidden argument keys: {sorted(bad)}")
    extra = set(args.keys()) - allowed
    if extra:
        raise ContractError("INVALID_ARGUMENT", f"Unexpected arguments: {sorted(extra)}")


@dataclass(frozen=True)
class PrincipalPolicy:
    """Server-side authenticated caller policy binding OS UID -> principal -> scopes -> tools."""

    principal_id: str
    allowed_uids: frozenset[int]
    allowed_recipient_scopes: frozenset[str]
    allowed_tools: frozenset[str] = field(default_factory=lambda: frozenset(V1_ALL_TOOLS))
    max_requests_per_minute: int = 120


class QuantFacadeService:
    """In-process Contract V1 service enforcing authz, validation, re-verification, and audit."""

    def __init__(
        self,
        registry: ApprovedJournalRegistry,
        *,
        principals: list[PrincipalPolicy] | None = None,
        audit_log_path: Path | None = None,
        clock_ms_fn: Callable[[], int] | None = None,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ) -> None:
        self._registry = registry
        self._clock_ms_fn = clock_ms_fn or _now_ms
        self._max_response_bytes = max_response_bytes
        self._audit_log_path = audit_log_path
        self._lock = threading.Lock()
        self._rate_windows: dict[str, deque[int]] = {}

        if principals is None:
            uid = os.getuid()
            principals = [
                PrincipalPolicy(
                    principal_id="hermes_quant_plugin",
                    allowed_uids=frozenset({uid}),
                    allowed_recipient_scopes=frozenset({"owner_dm", "outbox_worker", "qa_harness"}),
                )
            ]
        self._principals: dict[str, PrincipalPolicy] = {p.principal_id: p for p in principals}

    def _authorize(self, req: dict[str, Any], *, peer_uid: int | None) -> PrincipalPolicy:
        principal_id = req["principal_id"]
        policy = self._principals.get(principal_id)
        if policy is None:
            raise ContractError("UNAUTHORIZED", f"Unlisted principal: {principal_id!r}")
        if peer_uid is not None and peer_uid not in policy.allowed_uids:
            raise ContractError(
                "UNAUTHORIZED",
                f"OS peer UID {peer_uid} not bound to principal {principal_id!r}",
            )
        scope = req["recipient_scope"]
        requested_scopes = {scope} if isinstance(scope, str) else set(scope)
        if not requested_scopes or not requested_scopes.issubset(policy.allowed_recipient_scopes):
            raise ContractError("UNAUTHORIZED", "Requested recipient_scope not authorized for principal")
        if req["tool"] not in policy.allowed_tools:
            raise ContractError("UNAUTHORIZED", f"Tool {req['tool']!r} not permitted for principal")
        return policy

    def _check_rate_limit(self, policy: PrincipalPolicy, now_ms: int) -> None:
        cutoff = now_ms - 60_000
        with self._lock:
            dq = self._rate_windows.setdefault(policy.principal_id, deque())
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= policy.max_requests_per_minute:
                raise ContractError("RATE_LIMITED", "Principal rate limit exceeded")
            dq.append(now_ms)

    def _write_audit(self, entry: dict[str, Any]) -> None:
        if self._audit_log_path is None:
            return
        self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._audit_log_path.parent, 0o700)
        except OSError:
            pass
        line = canonical_json(entry) + "\n"
        with self._lock:
            with self._audit_log_path.open("a", encoding="utf-8") as fh:
                fh.write(line)
            try:
                os.chmod(self._audit_log_path, 0o600)
            except OSError:
                pass

    def handle_request(
        self,
        raw_req: dict[str, Any],
        *,
        peer_uid: int | None = None,
        peer_pid: int | None = None,
    ) -> dict[str, Any]:
        """Validate, authenticate, execute, and wrap one Contract V1 request."""
        start_ns = time.monotonic_ns()
        now_ms = self._clock_ms_fn()
        request_id = str(raw_req.get("request_id") or "invalid") if isinstance(raw_req, dict) else "invalid"
        tool = str(raw_req.get("tool") or "") if isinstance(raw_req, dict) else ""
        principal_id = str(raw_req.get("principal_id") or "") if isinstance(raw_req, dict) else ""
        server_as_of_ms: int | None = None
        evidence_class = EVIDENCE_UNKNOWN

        try:
            req = validate_request_envelope(raw_req)
            request_id = req["request_id"]
            tool = req["tool"]
            principal_id = req["principal_id"]
            policy = self._authorize(req, peer_uid=peer_uid)
            self._check_rate_limit(policy, now_ms)
            self._validate_tool_args(tool, req["args"])

            if tool == "request_reprice":
                raise ContractError(
                    "REPRICE_NOT_AUTHORIZED",
                    "request_reprice is DISABLED_BY_DEFAULT in H1; no Binance acquisition or journal mutation performed",
                )

            pre_read_ms = (time.monotonic_ns() - start_ns) / 1_000_000.0
            if pre_read_ms > req["deadline_ms"]:
                raise ContractError("TIMEOUT", f"Request exceeded deadline_ms={req['deadline_ms']}")

            records, default_as_of_ms = self._registry.load_all_verified_cards()
            classes = {r.source_evidence_class for r in records}
            if len(classes) == 1 and records:
                evidence_class = next(iter(classes))
                server_as_of_ms = default_as_of_ms
            else:
                evidence_class = EVIDENCE_UNKNOWN
                server_as_of_ms = None

            data, used_as_of_ms, resp_evidence_class = self._dispatch_readonly(
                tool=tool,
                args=req["args"],
                records=records,
                default_as_of_ms=default_as_of_ms,
                verified_at_ms=now_ms,
            )
            server_as_of_ms = used_as_of_ms
            evidence_class = resp_evidence_class

            elapsed_ms = (time.monotonic_ns() - start_ns) / 1_000_000.0
            if elapsed_ms > req["deadline_ms"]:
                evidence_class = EVIDENCE_UNKNOWN
                server_as_of_ms = None
                raise ContractError("TIMEOUT", f"Request exceeded deadline_ms={req['deadline_ms']}")

            resp = build_response_envelope(
                request_id=request_id,
                generated_at_ms=self._clock_ms_fn(),
                status="OK",
                server_as_of_ms=server_as_of_ms,
                source_evidence_class=evidence_class,
                data=data,
            )
            encoded_len = len(canonical_json(resp).encode("utf-8"))
            if encoded_len > self._max_response_bytes:
                raise ContractError("INVALID_ARGUMENT", "Response exceeded max payload size")

            self._write_audit({
                "ts_ms": now_ms,
                "request_id": request_id,
                "principal_id": principal_id,
                "peer_uid": peer_uid,
                "peer_pid": peer_pid,
                "tool": tool,
                "status": "OK",
                "error_code": None,
                "duration_ms": round(elapsed_ms, 3),
            })
            return resp

        except ContractError as exc:
            elapsed_ms = (time.monotonic_ns() - start_ns) / 1_000_000.0
            resp = build_response_envelope(
                request_id=request_id,
                generated_at_ms=self._clock_ms_fn(),
                status="ERROR",
                server_as_of_ms=server_as_of_ms,
                source_evidence_class=evidence_class,
                error=exc.to_dict(),
            )
            self._write_audit({
                "ts_ms": now_ms,
                "request_id": request_id,
                "principal_id": principal_id,
                "peer_uid": peer_uid,
                "peer_pid": peer_pid,
                "tool": tool,
                "status": "ERROR",
                "error_code": exc.code,
                "duration_ms": round(elapsed_ms, 3),
            })
            return resp
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = (time.monotonic_ns() - start_ns) / 1_000_000.0
            evidence_class = EVIDENCE_UNKNOWN
            server_as_of_ms = None
            safe = ContractError("INTERNAL_REDACTED", redact_error_text(exc))
            resp = build_response_envelope(
                request_id=request_id,
                generated_at_ms=self._clock_ms_fn(),
                status="ERROR",
                server_as_of_ms=server_as_of_ms,
                source_evidence_class=evidence_class,
                error=safe.to_dict(),
            )
            self._write_audit({
                "ts_ms": now_ms,
                "request_id": request_id,
                "principal_id": principal_id,
                "peer_uid": peer_uid,
                "peer_pid": peer_pid,
                "tool": tool,
                "status": "ERROR",
                "error_code": "INTERNAL_REDACTED",
                "duration_ms": round(elapsed_ms, 3),
            })
            return resp

    @staticmethod
    def _validate_request_reprice_args(args: dict[str, Any]) -> None:
        _reject_extra_args(args, frozenset({"episode_id", "idempotency_key", "desired_delay_minutes", "requested_by"}))
        for field_name in ("episode_id", "idempotency_key", "requested_by"):
            if field_name not in args:
                raise ContractError("INVALID_ARGUMENT", f"Missing {field_name}")
            _validate_id_arg(args[field_name], field_name)
        delay = args.get("desired_delay_minutes")
        if delay not in (5, 10) or type(delay) is not int:
            raise ContractError("INVALID_ARGUMENT", "desired_delay_minutes must be 5 or 10")

    def _validate_tool_args(self, tool: str, args: dict[str, Any]) -> None:
        if tool == "request_reprice":
            self._validate_request_reprice_args(args)
            return
        if tool == "list_active_signals":
            _reject_extra_args(args, frozenset({"limit", "cursor", "as_of_ms", "statuses"}))
            limit = args.get("limit", 20)
            if type(limit) is not int or not (1 <= limit <= MAX_LIST_LIMIT):
                raise ContractError("INVALID_ARGUMENT", f"limit must be integer 1..{MAX_LIST_LIMIT}")
            _decode_cursor(args.get("cursor"))
            if args.get("as_of_ms") is not None and (type(args["as_of_ms"]) is not int or args["as_of_ms"] <= 0):
                raise ContractError("INVALID_ARGUMENT", "as_of_ms must be a positive integer")
            statuses_raw = args.get("statuses")
            if statuses_raw is not None:
                if not isinstance(statuses_raw, list) or not statuses_raw:
                    raise ContractError("INVALID_ARGUMENT", "statuses must be a non-empty list")
                for st in statuses_raw:
                    if st not in MARKET_STATUSES:
                        raise ContractError("INVALID_ARGUMENT", f"Unknown market_status in statuses: {st!r}")
            return
        if tool == "get_signal_detail":
            _reject_extra_args(args, frozenset({"episode_id", "card_id", "as_of_ms"}))
            if "episode_id" not in args:
                raise ContractError("INVALID_ARGUMENT", "Missing episode_id")
            _validate_id_arg(args["episode_id"], "episode_id")
            if args.get("card_id") is not None:
                _validate_id_arg(args["card_id"], "card_id")
            if args.get("as_of_ms") is not None and (type(args["as_of_ms"]) is not int or args["as_of_ms"] <= 0):
                raise ContractError("INVALID_ARGUMENT", "as_of_ms must be a positive integer")
            return
        if tool == "get_market_context":
            _reject_extra_args(args, frozenset({"symbol", "as_of_ms"}))
            symbol = args.get("symbol")
            if type(symbol) is not str or symbol not in APPROVED_SYMBOLS:
                raise ContractError("INVALID_ARGUMENT", f"Unsupported or unapproved symbol: {symbol!r}")
            if args.get("as_of_ms") is not None and (type(args["as_of_ms"]) is not int or args["as_of_ms"] <= 0):
                raise ContractError("INVALID_ARGUMENT", "as_of_ms must be a positive integer")
            return
        if tool == "get_latest_reprice":
            _reject_extra_args(args, frozenset({"episode_id", "as_of_ms"}))
            if "episode_id" not in args:
                raise ContractError("INVALID_ARGUMENT", "Missing episode_id")
            _validate_id_arg(args["episode_id"], "episode_id")
            if args.get("as_of_ms") is not None and (type(args["as_of_ms"]) is not int or args["as_of_ms"] <= 0):
                raise ContractError("INVALID_ARGUMENT", "as_of_ms must be a positive integer")
            return
        if tool == "get_signal_history":
            _reject_extra_args(args, frozenset({"limit", "cursor", "start_ms", "end_ms", "symbol", "episode_id"}))
            limit = args.get("limit", 20)
            if type(limit) is not int or not (1 <= limit <= MAX_LIST_LIMIT):
                raise ContractError("INVALID_ARGUMENT", f"limit must be integer 1..{MAX_LIST_LIMIT}")
            _decode_cursor(args.get("cursor"))
            start_ms = args.get("start_ms")
            end_ms = args.get("end_ms")
            if start_ms is not None and (type(start_ms) is not int or start_ms <= 0):
                raise ContractError("INVALID_ARGUMENT", "start_ms must be positive integer")
            if end_ms is not None and (type(end_ms) is not int or end_ms <= 0):
                raise ContractError("INVALID_ARGUMENT", "end_ms must be positive integer")
            if start_ms is not None and end_ms is not None and start_ms > end_ms:
                raise ContractError("INVALID_ARGUMENT", "start_ms cannot exceed end_ms")
            symbol = args.get("symbol")
            if symbol is not None and symbol not in APPROVED_SYMBOLS:
                raise ContractError("INVALID_ARGUMENT", f"Unsupported symbol: {symbol!r}")
            if args.get("episode_id") is not None:
                _validate_id_arg(args["episode_id"], "episode_id")
            return
        if tool == "get_strategy_summary":
            _reject_extra_args(args, frozenset({"family", "start_ms", "end_ms"}))
            family = args.get("family")
            if family is not None and family not in APPROVED_FAMILIES:
                raise ContractError("INVALID_ARGUMENT", f"Unsupported strategy family: {family!r}")
            start_ms = args.get("start_ms")
            end_ms = args.get("end_ms")
            if start_ms is not None and (type(start_ms) is not int or start_ms <= 0):
                raise ContractError("INVALID_ARGUMENT", "start_ms must be positive integer")
            if end_ms is not None and (type(end_ms) is not int or end_ms <= 0):
                raise ContractError("INVALID_ARGUMENT", "end_ms must be positive integer")
            if start_ms is not None and end_ms is not None and start_ms > end_ms:
                raise ContractError("INVALID_ARGUMENT", "start_ms cannot exceed end_ms")
            return
        raise ContractError("UNKNOWN_TOOL", f"Unknown tool: {tool}")

    def _dispatch_readonly(
        self,
        *,
        tool: str,
        args: dict[str, Any],
        records: list[VerifiedCardRecord],
        default_as_of_ms: int | None,
        verified_at_ms: int,
    ) -> tuple[dict[str, Any], int | None, str]:
        if tool == "list_active_signals":
            return self._list_active_signals(args, records, default_as_of_ms, verified_at_ms)
        if tool == "get_signal_detail":
            return self._get_signal_detail(args, records, default_as_of_ms, verified_at_ms)
        if tool == "get_market_context":
            return self._get_market_context(args, records, default_as_of_ms)
        if tool == "get_latest_reprice":
            return self._get_latest_reprice(args, records, default_as_of_ms, verified_at_ms)
        if tool == "get_signal_history":
            return self._get_signal_history(args, records, default_as_of_ms, verified_at_ms)
        if tool == "get_strategy_summary":
            return self._get_strategy_summary(args, records, default_as_of_ms)
        raise ContractError("UNKNOWN_TOOL", f"Unknown tool: {tool}")

    def _list_active_signals(
        self,
        args: dict[str, Any],
        records: list[VerifiedCardRecord],
        default_as_of_ms: int | None,
        verified_at_ms: int,
    ) -> tuple[dict[str, Any], int | None, str]:
        _reject_extra_args(args, frozenset({"limit", "cursor", "as_of_ms", "statuses"}))
        limit = args.get("limit", 20)
        offset = _decode_cursor(args.get("cursor"))
        ref_as_of = self._registry.resolve_reference_as_of(args.get("as_of_ms"), default_as_of_ms)

        statuses_raw = args.get("statuses")
        if statuses_raw is None:
            allowed_statuses = frozenset({"EXECUTABLE", "WATCH"})
        else:
            allowed_statuses = frozenset(statuses_raw)

        # P0-C01: null-episode NO_SETUP / NOT_EVALUATED cards are diagnostics only and NEVER enter active signals.
        diagnostic_omitted = sum(
            1
            for r in records
            if not r.episode_id and (ref_as_of is None or r.evaluated_at_ms <= ref_as_of)
        )
        latest_map = self._registry.latest_records_by_episode(records)
        filtered: list[dict[str, Any]] = []
        expired_omitted = 0
        for rec in sorted(latest_map.values(), key=lambda r: (-r.evaluated_at_ms, r.symbol, r.card_id)):
            if not rec.episode_id:
                continue
            if ref_as_of is not None and rec.evaluated_at_ms > ref_as_of:
                continue
            snap = self._registry.project_record(
                rec,
                reference_as_of_ms=ref_as_of,
                verified_at_ms=verified_at_ms,
            )
            if snap["is_expired"]:
                expired_omitted += 1
                continue
            if snap["market_status"] not in allowed_statuses:
                continue
            filtered.append({
                "episode_id": snap["episode_id"],
                "card_id": snap["card_id"],
                "card_version": snap["card_version"],
                "symbol": snap["symbol"],
                "direction": snap["direction"],
                "strategy_family": snap["strategy_family"],
                "market_status": snap["market_status"],
                "status_reason_codes": snap["status_reason_codes"],
                "source_evidence_class": snap["source_evidence_class"],
                "source_as_of_ms": snap["source_as_of_ms"],
                "evaluated_at_ms": snap["evaluated_at_ms"],
                "absolute_expiry_ms": snap["absolute_expiry_ms"],
                "expiry_status": snap["expiry_status"],
                "freshness_state": snap["freshness_state"],
                "account_context_status": snap["account_context_status"],
                "source_banner": snap["source_banner"],
                "not_a_real_trade_signal": snap["not_a_real_trade_signal"],
                "plan_summary": (
                    {
                        "entry_low": snap["plan"].get("entry_low"),
                        "entry_high": snap["plan"].get("entry_high"),
                        "hard_stop": snap["plan"].get("hard_stop"),
                        "tp1_net_r": (
                            snap["plan"].get("targets", [{}])[0].get("net_r")
                            if snap["plan"].get("targets")
                            else None
                        ),
                    }
                    if snap["plan"]
                    else None
                ),
            })

        page = filtered[offset : offset + limit]
        next_cursor = _encode_cursor(offset + limit) if (offset + limit) < len(filtered) else None
        page_classes = {str(item["source_evidence_class"]) for item in page}
        env_cls, agg_mode, banner, is_het = _classify_aggregate_evidence(page_classes)
        # Empty unqualified collection carries UNKNOWN and no invented source time unless caller pinned as_of_ms.
        out_as_of = ref_as_of if page else args.get("as_of_ms")
        return {
            "signals": page,
            "total_matching": len(filtered),
            "expired_omitted": expired_omitted,
            "diagnostic_omitted": diagnostic_omitted,
            "next_cursor": next_cursor,
            "as_of_ms": out_as_of,
            "source_evidence_class": env_cls,
            "evidence_aggregation": agg_mode,
            "heterogeneous_evidence": is_het,
            "evidence_classes_present": sorted(page_classes),
            "affirmative_notification_allowed": bool(page) and not is_het,
            "source_banner": banner,
            "account_context_status": "UNAVAILABLE",
        }, out_as_of, env_cls

    def _get_signal_detail(
        self,
        args: dict[str, Any],
        records: list[VerifiedCardRecord],
        default_as_of_ms: int | None,
        verified_at_ms: int,
    ) -> tuple[dict[str, Any], int | None, str]:
        _reject_extra_args(args, frozenset({"episode_id", "card_id", "as_of_ms"}))
        episode_id = _validate_id_arg(args["episode_id"], "episode_id")
        card_id = _validate_id_arg(args["card_id"], "card_id") if args.get("card_id") is not None else None
        ref_as_of = self._registry.resolve_reference_as_of(args.get("as_of_ms"), default_as_of_ms)

        ep_records = sorted(
            (r for r in records if r.episode_id == episode_id),
            key=lambda r: (r.evaluated_at_ms, r.pub_seq, r.card_id),
        )
        if not ep_records:
            raise ContractError("NOT_FOUND", f"Unknown episode_id: {episode_id}")
        latest_rec = ep_records[-1]

        if card_id is not None:
            matched = [r for r in ep_records if r.card_id == card_id]
            if not matched:
                raise ContractError("NOT_FOUND", f"Card {card_id} not found for episode {episode_id}")
            target_rec = matched[0]
        else:
            target_rec = latest_rec

        snapshot = self._registry.project_record(
            target_rec,
            reference_as_of_ms=ref_as_of,
            verified_at_ms=verified_at_ms,
        )
        latest_snapshot = self._registry.project_record(
            latest_rec,
            reference_as_of_ms=ref_as_of,
            verified_at_ms=verified_at_ms,
        )
        is_superseded = target_rec.card_id != latest_rec.card_id

        return {
            "snapshot": snapshot,
            "is_superseded": is_superseded,
            "latest_card_id": latest_snapshot["card_id"],
            "latest_card_version": latest_snapshot["card_version"],
            "latest_market_status": latest_snapshot["market_status"],
            "latest_is_expired": latest_snapshot["is_expired"],
        }, ref_as_of, snapshot["source_evidence_class"]

    def _get_market_context(
        self,
        args: dict[str, Any],
        records: list[VerifiedCardRecord],
        default_as_of_ms: int | None,
    ) -> tuple[dict[str, Any], int | None, str]:
        _reject_extra_args(args, frozenset({"symbol", "as_of_ms"}))
        symbol = str(args["symbol"])
        ref_as_of = self._registry.resolve_reference_as_of(args.get("as_of_ms"), default_as_of_ms)

        candidates = [
            r for r in records
            if r.symbol == symbol and (ref_as_of is None or r.evaluated_at_ms <= ref_as_of)
        ]
        if not candidates:
            raise ContractError("NOT_FOUND", f"No verified market context available for {symbol}")
        latest = max(candidates, key=lambda r: (r.evaluated_at_ms, r.pub_seq, r.card_id))
        now_verified = self._clock_ms_fn()
        snap = (
            self._registry.project_diagnostic(
                latest,
                reference_as_of_ms=ref_as_of,
                verified_at_ms=now_verified,
            )
            if latest.episode_id is None
            else self._registry.project_record(
                latest,
                reference_as_of_ms=ref_as_of,
                verified_at_ms=now_verified,
            )
        )
        card = latest.card
        ctx = card.get("card_context") or {}
        compact_ctx: dict[str, Any] = {}
        for key in ("quote", "depth", "mark", "oi", "oi_history", "funding"):
            entry = ctx.get(key)
            if isinstance(entry, dict):
                compact_ctx[key] = {
                    "receipt_id": entry.get("receipt_id"),
                    "source_event_ms": entry.get("source_event_ms"),
                    "age_upper_ms": entry.get("age_upper_ms"),
                    "raw_sha256": entry.get("raw_sha256"),
                    "values": entry.get("values"),
                }
        return {
            "symbol": symbol,
            "as_of_ms": ref_as_of,
            "episode_id": snap["episode_id"],
            "diagnostic_only": snap["episode_id"] is None,
            "not_eligible_for_alert": snap["episode_id"] is None,
            "card_id": snap["card_id"],
            "card_version": snap["card_version"],
            "market_status": snap["market_status"],
            "reasons": snap["reasons"],
            "data_ready": bool(card.get("data_ready", False)),
            "source_evidence_class": snap["source_evidence_class"],
            "source_origin": snap["source_origin"],
            "source_as_of_ms": snap["source_as_of_ms"],
            "freshness_state": snap["freshness_state"],
            "frame_end_ms": snap["frame_end_ms"],
            "current_regime_4h": card.get("current_regime_4h"),
            "market_context": compact_ctx,
            "source_issue": card.get("source_issue"),
            "account_context_status": "UNAVAILABLE",
            "account_overlay": "MANUAL_ACCOUNT_CHECK_REQUIRED",
            "source_banner": snap["source_banner"],
            "not_a_real_trade_signal": snap["not_a_real_trade_signal"],
        }, ref_as_of, snap["source_evidence_class"]

    def _get_latest_reprice(
        self,
        args: dict[str, Any],
        records: list[VerifiedCardRecord],
        default_as_of_ms: int | None,
        verified_at_ms: int,
    ) -> tuple[dict[str, Any], int | None, str]:
        _reject_extra_args(args, frozenset({"episode_id", "as_of_ms"}))
        episode_id = _validate_id_arg(args["episode_id"], "episode_id")
        ref_as_of = self._registry.resolve_reference_as_of(args.get("as_of_ms"), default_as_of_ms)

        ep_records = sorted(
            (
                r
                for r in records
                if r.episode_id == episode_id and (ref_as_of is None or r.evaluated_at_ms <= ref_as_of)
            ),
            key=lambda r: (r.evaluated_at_ms, r.pub_seq, r.card_id),
        )
        if not ep_records:
            raise ContractError("NOT_FOUND", f"Unknown episode_id: {episode_id}")

        reprice_records = [r for r in ep_records if r.card.get("reprice") is not None]
        if not reprice_records:
            latest = self._registry.project_record(
                ep_records[-1],
                reference_as_of_ms=ref_as_of,
                verified_at_ms=verified_at_ms,
            )
            return {
                "status": "NOT_AVAILABLE",
                "episode_id": episode_id,
                "latest_reprice": None,
                "snapshot": latest,
                "source_evidence_class": latest["source_evidence_class"],
                "source_banner": latest["source_banner"],
                "account_context_status": "UNAVAILABLE",
            }, ref_as_of, latest["source_evidence_class"]

        rec = reprice_records[-1]
        snap = self._registry.project_record(
            rec,
            reference_as_of_ms=ref_as_of,
            verified_at_ms=verified_at_ms,
        )
        return {
            "status": "AVAILABLE",
            "episode_id": episode_id,
            "latest_reprice": snap["latest_reprice"],
            "snapshot": snap,
            "source_evidence_class": snap["source_evidence_class"],
            "source_banner": snap["source_banner"],
            "account_context_status": "UNAVAILABLE",
        }, ref_as_of, snap["source_evidence_class"]

    def _get_signal_history(
        self,
        args: dict[str, Any],
        records: list[VerifiedCardRecord],
        default_as_of_ms: int | None,
        verified_at_ms: int,
    ) -> tuple[dict[str, Any], int | None, str]:
        _reject_extra_args(args, frozenset({"limit", "cursor", "start_ms", "end_ms", "symbol", "episode_id"}))
        limit = args.get("limit", 20)
        offset = _decode_cursor(args.get("cursor"))
        start_ms = args.get("start_ms")
        end_ms = args.get("end_ms")
        symbol = args.get("symbol")
        episode_id = _validate_id_arg(args["episode_id"], "episode_id") if args.get("episode_id") is not None else None

        ref_as_of = end_ms if end_ms is not None else default_as_of_ms
        filtered: list[VerifiedCardRecord] = []
        for rec in sorted(records, key=lambda r: (-r.evaluated_at_ms, -r.pub_seq, r.card_id)):
            if symbol is not None and rec.symbol != symbol:
                continue
            if episode_id is not None and rec.episode_id != episode_id:
                continue
            if start_ms is not None and rec.evaluated_at_ms < start_ms:
                continue
            if end_ms is not None and rec.evaluated_at_ms > end_ms:
                continue
            filtered.append(rec)

        page_recs = filtered[offset : offset + limit]
        items: list[dict[str, Any]] = []
        for rec in page_recs:
            is_diag = rec.episode_id is None
            snap = (
                self._registry.project_diagnostic(
                    rec,
                    reference_as_of_ms=ref_as_of,
                    verified_at_ms=verified_at_ms,
                )
                if is_diag
                else self._registry.project_record(
                    rec,
                    reference_as_of_ms=ref_as_of,
                    verified_at_ms=verified_at_ms,
                )
            )
            items.append({
                "episode_id": snap["episode_id"],
                "diagnostic_only": is_diag,
                "not_eligible_for_alert": is_diag,
                "card_id": snap["card_id"],
                "card_version": snap["card_version"],
                "pub_seq": rec.pub_seq,
                "pub_sha256": rec.pub_sha,
                "symbol": snap["symbol"],
                "direction": snap["direction"],
                "strategy_family": snap["strategy_family"],
                "market_status": snap["market_status"],
                "status_reason_codes": snap["status_reason_codes"],
                "source_evidence_class": snap["source_evidence_class"],
                "source_origin": snap["source_origin"],
                "source_as_of_ms": snap["source_as_of_ms"],
                "evaluated_at_ms": snap["evaluated_at_ms"],
                "observed_at_ms": snap["observed_at_ms"],
                "absolute_expiry_ms": snap["absolute_expiry_ms"],
                "is_expired": snap["is_expired"],
                "freshness_state": snap["freshness_state"],
                "reprice": (snap["latest_reprice"] or {}).get("reprice") if snap["latest_reprice"] else None,
                "source_banner": snap["source_banner"],
                "not_a_real_trade_signal": snap["not_a_real_trade_signal"],
            })

        next_cursor = _encode_cursor(offset + limit) if (offset + limit) < len(filtered) else None
        page_classes = {str(it["source_evidence_class"]) for it in items}
        env_cls, agg_mode, banner, is_het = _classify_aggregate_evidence(page_classes)
        out_as_of = ref_as_of if items else end_ms
        return {
            "history": items,
            "total_matching": len(filtered),
            "next_cursor": next_cursor,
            "account_context_status": "UNAVAILABLE",
            "source_evidence_class": env_cls,
            "evidence_aggregation": agg_mode,
            "heterogeneous_evidence": is_het,
            "evidence_classes_present": sorted(page_classes),
            "affirmative_notification_allowed": bool(items) and not is_het,
            "source_banner": banner,
        }, out_as_of, env_cls

    def _get_strategy_summary(
        self,
        args: dict[str, Any],
        records: list[VerifiedCardRecord],
        default_as_of_ms: int | None,
    ) -> tuple[dict[str, Any], int | None, str]:
        _reject_extra_args(args, frozenset({"family", "start_ms", "end_ms"}))
        family = args.get("family")
        start_ms = args.get("start_ms")
        end_ms = args.get("end_ms")

        family_defs = {
            "TREND_PULLBACK": (
                "4H directional regime alignment (EMA10/EMA20/displacement/pivots) + "
                "1H pullback depth 0.85..3.50 ATR with higher close and healthy body ratio >= 0.45, "
                "followed by independent delayed 15m close confirmation and 5m no-chase/cost check."
            ),
            "EARLY_CONTINUATION": (
                "4H directional regime alignment + compact 1H continuation shelf "
                "(depth -0.35..1.35 ATR, shelf_width <= 1.10 ATR, breakout above shelf ceiling + tick, "
                "relative volume >= 0.85), followed by independent 15m close confirmation and 5m cost check."
            ),
        }

        status_counts: dict[str, int] = {}
        family_counts: dict[str, int] = {}
        evidence_counts: dict[str, int] = {}
        episodes: set[str] = set()
        reprice_count = 0
        diagnostic_cards = 0

        for rec in records:
            if start_ms is not None and rec.evaluated_at_ms < start_ms:
                continue
            if end_ms is not None and rec.evaluated_at_ms > end_ms:
                continue
            ep = rec.card.get("episode") or rec.episode_row or {}
            rec_fam = ep.get("family")
            if family is not None and rec_fam != family:
                continue
            st = str(rec.card.get("market_status"))
            status_counts[st] = status_counts.get(st, 0) + 1
            if rec_fam:
                family_counts[str(rec_fam)] = family_counts.get(str(rec_fam), 0) + 1
            evidence_counts[rec.source_evidence_class] = evidence_counts.get(rec.source_evidence_class, 0) + 1
            if rec.episode_id:
                episodes.add(rec.episode_id)
            else:
                diagnostic_cards += 1
            if rec.card.get("reprice") is not None:
                reprice_count += 1

        selected_defs = {family: family_defs[family]} if family else family_defs
        classes_present = set(evidence_counts.keys())
        env_cls, agg_mode, banner, is_het = _classify_aggregate_evidence(classes_present)
        out_as_of = default_as_of_ms if status_counts else end_ms
        return {
            "strategy_id": "B2_TREND_SETUP_V1",
            "features_id": "B2_EMA_ATR_PIVOT_V1",
            "timeframes": ["1d", "4h", "1h", "15m", "5m"],
            "family_definitions": selected_defs,
            "recorded_counts": {
                "cards": sum(status_counts.values()),
                "episodes": len(episodes),
                "diagnostic_cards": diagnostic_cards,
                "reprice_cards": reprice_count,
                "by_market_status": dict(sorted(status_counts.items())),
                "by_family": dict(sorted(family_counts.items())),
                "by_evidence_class": dict(sorted(evidence_counts.items())),
            },
            "profitability_claim": False,
            "economic_validation_status": "UNQUALIFIED_OFFLINE_SYNTHETIC_ONLY",
            "disclaimer": (
                "Factual definitions and recorded journal counts only. Synthetic QA counts do not "
                "demonstrate prospective profitability or real-market execution outcomes."
            ),
            "account_context_status": "UNAVAILABLE",
            "source_evidence_class": env_cls,
            "evidence_aggregation": agg_mode,
            "heterogeneous_evidence": is_het,
            "evidence_classes_present": sorted(classes_present),
            "source_banner": banner,
        }, out_as_of, env_cls


class _UdsHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server: QuantUdsServer = self.server  # type: ignore[assignment]
        peer_uid: int | None = None
        peer_pid: int | None = None
        if hasattr(socket, "SO_PEERCRED"):
            cred = self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _PEERCRED_SIZE)
            peer_pid, peer_uid, _peer_gid = struct.unpack(_PEERCRED_FMT, cred)
        else:
            raise RuntimeError("Platform lacks SO_PEERCRED for OS-authenticated UDS")

        try:
            header = self.rfile.read(4)
            if len(header) != 4:
                return
            (length,) = struct.unpack("!I", header)
            if length <= 0 or length > MAX_REQUEST_BYTES:
                resp = build_response_envelope(
                    request_id="oversized",
                    generated_at_ms=_now_ms(),
                    status="ERROR",
                    server_as_of_ms=None,
                    source_evidence_class=EVIDENCE_UNKNOWN,
                    error=ContractError("INVALID_ARGUMENT", f"Invalid frame length: {length}").to_dict(),
                )
            else:
                body = self.rfile.read(length)
                if len(body) != length:
                    return
                raw_req = json.loads(body.decode("utf-8"))
                resp = server.service.handle_request(raw_req, peer_uid=peer_uid, peer_pid=peer_pid)
        except Exception as exc:  # noqa: BLE001
            resp = build_response_envelope(
                request_id="malformed",
                generated_at_ms=_now_ms(),
                status="ERROR",
                server_as_of_ms=None,
                source_evidence_class=EVIDENCE_UNKNOWN,
                error=ContractError("INVALID_ARGUMENT", f"Malformed JSON frame: {exc}").to_dict(),
            )

        payload = canonical_json(resp).encode("utf-8")
        self.wfile.write(struct.pack("!I", len(payload)) + payload)
        self.wfile.flush()


class QuantUdsServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """Protected Unix-domain socket server enforcing 0700 dir, 0600 socket, and SO_PEERCRED."""

    daemon_threads = True

    def __init__(
        self,
        socket_path: Path,
        service: QuantFacadeService,
        *,
        socket_mode: int = 0o600,
    ) -> None:
        self.socket_path = socket_path
        self.service = service
        parent = socket_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        os.chmod(parent, 0o700)
        if socket_path.exists():
            socket_path.unlink()
        super().__init__(str(socket_path), _UdsHandler)
        os.chmod(socket_path, socket_mode)


class QuantFacadeClient:
    """Least-privilege UDS client for Hermes plugin / outbox workers (no SQLite access)."""

    def __init__(
        self,
        socket_path: Path,
        *,
        principal_id: str = "hermes_quant_plugin",
        recipient_scope: str | list[str] = "owner_dm",
        timeout_s: float = 5.0,
    ) -> None:
        self.socket_path = Path(socket_path)
        self.principal_id = principal_id
        self.recipient_scope = recipient_scope
        self.timeout_s = timeout_s
        self._seq = 0
        self._lock = threading.Lock()

    def _next_request_id(self) -> str:
        with self._lock:
            self._seq += 1
            return f"{self.principal_id}-{self._seq}-{int(time.time_ns() // 1_000_000)}"

    def call_tool(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
        deadline_ms: int = DEFAULT_DEADLINE_MS,
        recipient_scope: str | list[str] | None = None,
    ) -> dict[str, Any]:
        req = {
            "contract_id": CONTRACT_ID,
            "request_id": request_id or self._next_request_id(),
            "tool": tool,
            "args": args or {},
            "principal_id": self.principal_id,
            "recipient_scope": recipient_scope if recipient_scope is not None else self.recipient_scope,
            "deadline_ms": deadline_ms,
        }
        return self.send_raw_envelope(req)

    def send_raw_envelope(self, raw_req: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(raw_req, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > MAX_REQUEST_BYTES:
            raise ContractError("INVALID_ARGUMENT", "Client request exceeds max request size")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout_s)
                sock.connect(str(self.socket_path))
                sock.sendall(struct.pack("!I", len(payload)) + payload)
                hdr = _recv_exact(sock, 4)
                if len(hdr) != 4:
                    raise ContractError("SOURCE_UNAVAILABLE", "Truncated response header from facade")
                (resp_len,) = struct.unpack("!I", hdr)
                if resp_len <= 0 or resp_len > MAX_RESPONSE_BYTES * 2:
                    raise ContractError("INTEGRITY_FAILURE", f"Unexpected response length {resp_len}")
                body = _recv_exact(sock, resp_len)
                if len(body) != resp_len:
                    raise ContractError("SOURCE_UNAVAILABLE", "Truncated response body from facade")
                return json.loads(body.decode("utf-8"))
        except ContractError:
            raise
        except OSError as exc:
            raise ContractError("SOURCE_UNAVAILABLE", f"Facade UDS unavailable: {exc}") from exc


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)
