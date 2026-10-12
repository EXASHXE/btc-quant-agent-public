"""Independent Decimal financial oracle, AST/socket guards, and synthetic fixture builders."""

from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import socket
import urllib.request
from collections.abc import Iterator
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any

from scripts.g1_offline_preview_r1.model import SafetyViolation, digest, initial_state
from scripts.g1_offline_preview_r1.reducer import transition

REPO_ROOT = Path(__file__).resolve().parents[3]
PREVIEW_DIR = REPO_ROOT / "scripts/g1_offline_preview_r1"

EXPECTED_C4_SOURCE_HASHES: dict[str, str] = {
    "scripts/g1_offline_preview_r1/__main__.py": (
        "65dcb3d726ed5a8b828ed0288d10fa9f51340f4cf3a70cf44b4a2c62e21cd5fb"
    ),
    "scripts/g1_offline_preview_r1/analysis_schema.json": (
        "dea9da8a0f03740894f117a7da56cd7c99476aa3058bdf2a665107019a98e1cb"
    ),
    "scripts/g1_offline_preview_r1/fixtures/long_24h.json": (
        "ae6c70f7c26b752df1cfc2cc803d6a941a62e1699749365f4902d335cb93fe4f"
    ),
    "scripts/g1_offline_preview_r1/fixtures/short_24h.json": (
        "d6bf849411f82db75f433f91985b7c8698fbbd1834685fb706453de3cad1dc11"
    ),
    "scripts/g1_offline_preview_r1/fixtures.py": (
        "9999418e5cb1f9fd98d1f4cae5c1d460a9593b28c9f7f338a3043374fa4ea8b0"
    ),
    "scripts/g1_offline_preview_r1/model.py": (
        "086d6ec8747f82d59b6f8f42bfefd2d9c61e5f962707b4f9119f784741dd206e"
    ),
    "scripts/g1_offline_preview_r1/reducer.py": (
        "c0114c8cc0480b3c4c637217363833590fb231ad8529c93f85f574ce161ed89e"
    ),
    "scripts/g1_offline_preview_r1/storage.py": (
        "9e4ac21c501e48734a750021f8ea2f51f4f06ecc0ee2e798647718b4c453f101"
    ),
    "tests/test_v06_g1_offline_preview_r1_core.py": (
        "d5679c583d1122f2ce877f7686e477acc869637e7ee21643fbee1f5058e52da3"
    ),
    "tests/test_v06_g1_offline_preview_r1_decimal_and_ports.py": (
        "7a0fef994f1548ebe0813836b41340519f49dcefbe46a5d5850b23392ee731e2"
    ),
    "tests/test_v06_g1_offline_preview_r1_exit_safety.py": (
        "8efc412469fa5be183bca05dacd7ba255e7ad1f20f93e39706698e8bc4cd71f0"
    ),
    "tests/test_v06_g1_offline_preview_r1_process_recovery.py": (
        "d6c99ea559f9c4a8c384568af52ed6aa556ecca896d9add58ca9aa5c07f04249"
    ),
    "tests/test_v06_g1_offline_preview_r1_wal.py": (
        "41d53a583502b4d28da92dfa9f8c9e2dde73522509009739418d9dfff42c8585"
    ),
}

FORBIDDEN_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "socket",
        "ssl",
        "http",
        "urllib",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
        "binance",
        "ccxt",
        "openai",
        "anthropic",
        "google",
        "feishu",
        "lark",
        "pyperclip",
        "tkinter",
        "ctypes",
        "subprocess",
        "multiprocessing",
        "threading",
        "asyncio",
        "sqlite3",
        "btc_quant_agent",
    }
)

FORBIDDEN_CALL_ATTRS: frozenset[str] = frozenset(
    {
        "system",
        "popen",
        "spawn",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "connect",
        "connect_ex",
        "create_connection",
        "urlopen",
        "place_order",
        "cancel_order",
        "send_message",
        "post_webhook",
    }
)


def extract_core_state(state: dict[str, Any]) -> dict[str, Any]:
    """Extract compact deterministic summary of reducer state before/after an input."""
    return {
        "phase": state.get("phase"),
        "last_at": state.get("last_at"),
        "last_clock": state.get("last_clock"),
        "cash": state.get("cash"),
        "available_cash": state.get("available_cash"),
        "reserved_notional": state.get("reserved_notional"),
        "mark_equity": state.get("mark_equity"),
        "remaining_qty": state.get("remaining_qty"),
        "order_id": state.get("order_id"),
        "entry_acknowledged": state.get("entry_acknowledged"),
        "tp1_filled": state.get("tp1_filled"),
        "stop": state.get("stop"),
        "required_exit": copy.deepcopy(state.get("required_exit")),
        "pending_cash_keys": sorted(state.get("pending_cash", {}).keys()),
        "journal_len": len(state.get("journal", [])),
        "outbox_len": len(state.get("outbox", [])),
        "used_tokens_len": len(state.get("used_tokens", [])),
        "counters": copy.deepcopy(state.get("counters")),
        "state_hash": digest(state),
    }


def record_negative_transition(
    test_id: str,
    category: str,
    state: dict[str, Any],
    event: dict[str, Any],
    expected_code: str,
) -> dict[str, Any]:
    """Execute a negative reducer transition and verify zero state mutation."""
    before_copy = copy.deepcopy(state)
    before_summary = extract_core_state(state)
    caught_code: str | None = None
    try:
        transition(state, event)
    except SafetyViolation as exc:
        caught_code = exc.code
    if caught_code != expected_code:
        raise AssertionError(
            f"{test_id}: expected SafetyViolation({expected_code!r}), got {caught_code!r}"
        )
    after_summary = extract_core_state(state)
    mutated = (state != before_copy) or (before_summary["state_hash"] != after_summary["state_hash"])
    if mutated:
        raise AssertionError(f"{test_id}: reducer mutated input state on rejected event")
    return {
        "test_id": test_id,
        "category": category,
        "event_kind": event.get("kind"),
        "event_at": event.get("at"),
        "expected_code": expected_code,
        "observed_code": caught_code,
        "state_mutated": mutated,
        "before": before_summary,
        "after": after_summary,
    }


def audit_static_import_and_call_surface() -> dict[str, Any]:
    """Audit AST imports and call attributes across all scripts/g1_offline_preview_r1/*.py."""
    files_Report: dict[str, Any] = {}
    violations: list[str] = []
    for py_path in sorted(PREVIEW_DIR.glob("*.py")):
        rel = str(py_path.relative_to(REPO_ROOT)).replace("\\", "/")
        source_bytes = py_path.read_bytes()
        sha = hashlib.sha256(source_bytes).hexdigest()
        tree = ast.parse(source_bytes.decode("utf-8"), filename=rel)
        imports: list[str] = []
        attr_calls: list[str] = []
        funcs_and_classes: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                funcs_and_classes.append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
                    root = alias.name.split(".")[0]
                    if root in FORBIDDEN_IMPORT_ROOTS:
                        violations.append(f"{rel}: forbidden import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    imports.append(node.module)
                    root = node.module.split(".")[0]
                    if root in FORBIDDEN_IMPORT_ROOTS:
                        violations.append(f"{rel}: forbidden from-import {node.module}")
                elif node.level > 0:
                    imports.append("." * node.level + (node.module or ""))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                attr_calls.append(attr)
                if attr in FORBIDDEN_CALL_ATTRS:
                    violations.append(f"{rel}: forbidden attribute call .{attr}()")
        files_Report[rel] = {
            "sha256": sha,
            "imports": sorted(set(imports)),
            "defined_symbols": sorted(set(funcs_and_classes)),
            "distinct_attr_calls": sorted(set(attr_calls)),
        }
    return {
        "verified_file_count": len(files_Report),
        "violations": violations,
        "files": files_Report,
    }


@contextlib.contextmanager
def intercept_outbound_network() -> Iterator[list[str]]:
    """Intercept socket/DNS/HTTP outbound calls within the current process."""
    attempted_calls: list[str] = []
    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex
    orig_create_conn = socket.create_connection
    orig_getaddrinfo = socket.getaddrinfo
    orig_urlopen = urllib.request.urlopen

    def trap(label: str):
        def _blocked(*args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            attempted_calls.append(label)
            raise RuntimeError(f"OUTBOUND_NETWORK_BLOCKED:{label}")

        return _blocked

    socket.socket.connect = trap("socket.connect")  # type: ignore[method-assign]
    socket.socket.connect_ex = trap("socket.connect_ex")  # type: ignore[method-assign]
    socket.create_connection = trap("socket.create_connection")  # type: ignore[assignment]
    socket.getaddrinfo = trap("socket.getaddrinfo")  # type: ignore[assignment]
    urllib.request.urlopen = trap("urllib.request.urlopen")  # type: ignore[assignment]
    try:
        yield attempted_calls
    finally:
        socket.socket.connect = orig_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = orig_connect_ex  # type: ignore[method-assign]
        socket.create_connection = orig_create_conn  # type: ignore[assignment]
        socket.getaddrinfo = orig_getaddrinfo  # type: ignore[assignment]
        urllib.request.urlopen = orig_urlopen  # type: ignore[assignment]


def independent_fill_price(raw_price: Decimal, side: str, *, is_entry: bool) -> Decimal:
    """Independent Decimal computation of 5bp adverse fill price quantized to 0.1 tick."""
    tick = Decimal("0.1")
    impact = Decimal("0.0005")
    adverse_up = (side == "LONG") if is_entry else (side == "SHORT")
    slipped = raw_price * (Decimal(1) + (impact if adverse_up else -impact))
    return slipped.quantize(tick, rounding=ROUND_CEILING if adverse_up else ROUND_FLOOR)


def independent_net_be_stop(entry_price: Decimal, side: str) -> Decimal:
    """Independent Decimal computation of net-BE stop including 6bp fees and 5bp exit impact."""
    tick = Decimal("0.1")
    fee = Decimal("0.0006")
    impact = Decimal("0.0005")
    if side == "LONG":
        raw = entry_price * (Decimal(1) + fee) / ((Decimal(1) - impact) * (Decimal(1) - fee))
        candidate = raw.quantize(tick, rounding=ROUND_CEILING)
        while independent_fill_price(candidate, "LONG", is_entry=False) * (
            Decimal(1) - fee
        ) < entry_price * (Decimal(1) + fee):
            candidate += tick
        return candidate
    raw = entry_price * (Decimal(1) - fee) / ((Decimal(1) + impact) * (Decimal(1) + fee))
    candidate = raw.quantize(tick, rounding=ROUND_FLOOR)
    while independent_fill_price(candidate, "SHORT", is_entry=False) * (
        Decimal(1) + fee
    ) > entry_price * (Decimal(1) - fee):
        candidate -= tick
    return candidate


def independent_fixture_ledger(
    side: str, horizon_hours: int = 24, exit_kind: str = "STOP"
) -> dict[str, Any]:
    """Compute independent Decimal ledger for make_fixture(side, horizon_hours, exit_kind)."""
    sign = Decimal(1) if side == "LONG" else Decimal(-1)
    fee_rate = Decimal("0.0006")
    qty = Decimal("0.01")
    half_qty = Decimal("0.005")

    entry_base = Decimal(30000)
    entry_fill = independent_fill_price(entry_base, side, is_entry=True)
    entry_fee = -(qty * entry_fill * fee_rate)

    tp1_target = Decimal(30300) if side == "LONG" else Decimal(29700)
    tp1_fill = independent_fill_price(tp1_target, side, is_entry=False)
    tp1_net = sign * half_qty * (tp1_fill - entry_fill) - (half_qty * tp1_fill * fee_rate)

    mark_360 = Decimal(30312) if side == "LONG" else Decimal(29688)
    mark_post = Decimal(30207) if side == "LONG" else Decimal(29793)
    funding_1 = -sign * half_qty * mark_360 * Decimal("0.0001")
    funding_2 = -sign * half_qty * mark_post * Decimal("0.0001")
    funding_3 = -sign * half_qty * mark_post * Decimal("-0.0002")

    if exit_kind == "STOP":
        # Bar 720 opens at 29900 (LONG) or 30100 (SHORT), gapping beyond net-BE stop.
        final_base = Decimal(29900) if side == "LONG" else Decimal(30100)
        close_index = 720
        final_journal_kind = "STOP_NET"
    elif exit_kind == "TP2":
        final_base = Decimal(30600) if side == "LONG" else Decimal(29400)
        close_index = 720
        final_journal_kind = "TP2_NET"
    elif exit_kind == "TIME_CAP":
        final_base = Decimal(30200) if side == "LONG" else Decimal(29800)
        close_index = horizon_hours * 60 + 1
        final_journal_kind = "TIME_CAP_NET"
    else:
        raise ValueError(f"Unsupported exit_kind: {exit_kind}")

    final_fill = independent_fill_price(final_base, side, is_entry=False)
    final_net = sign * half_qty * (final_fill - entry_fill) - (half_qty * final_fill * fee_rate)
    final_ack_at = (close_index * 60000 + 59999) + 60000

    raw_rows = [
        ("ENTRY_FEE", 60004, entry_fee, qty),
        ("FUNDING", 21660001, funding_1, half_qty),
        ("TP1_NET", 21719999, tp1_net, Decimal(0)),
        ("FUNDING", 28800000, funding_2, half_qty),
        ("FUNDING", 36000000, funding_3, half_qty),
        (final_journal_kind, final_ack_at, final_net, Decimal(0)),
    ]
    raw_rows.sort(key=lambda r: r[1])

    cash = Decimal(1000)
    effects: list[dict[str, str | int]] = []
    for kind, at, delta, q in raw_rows:
        cash += delta
        effects.append(
            {
                "kind": kind,
                "at": at,
                "cash_delta": format(delta, "f"),
                "quantity": format(q, "f"),
                "cash_after": format(cash, "f"),
            }
        )
    return {
        "side": side,
        "horizon_hours": horizon_hours,
        "exit_kind": exit_kind,
        "entry_fill_price": format(entry_fill, "f"),
        "tp1_fill_price": format(tp1_fill, "f"),
        "be_stop_price": format(independent_net_be_stop(entry_fill, side), "f"),
        "final_fill_price": format(final_fill, "f"),
        "final_cash": format(cash, "f"),
        "effects": effects,
    }


def make_bar(
    open_time: int = 0,
    *,
    last_open: str = "100",
    last_high: str = "101",
    last_low: str = "99",
    last_close: str = "100",
    mark_close: str = "100",
    source: str = "SYNTHETIC_V1",
    close_time: int | None = None,
    available_at: int | None = None,
) -> dict[str, Any]:
    """Construct a synthetic 1m bar payload."""
    ct = open_time + 59999 if close_time is None else close_time
    avail = ct if available_at is None else available_at
    return {
        "source": source,
        "open_time": open_time,
        "close_time": ct,
        "available_at": avail,
        "last_open": last_open,
        "last_high": last_high,
        "last_low": last_low,
        "last_close": last_close,
        "mark_close": mark_close,
    }


def make_event(
    kind: str, at: int, payload: dict[str, Any] | None = None, event_id: str | None = None
) -> dict[str, Any]:
    """Construct a canonical synthetic event wrapper."""
    return {
        "id": event_id or f"{kind}-{at}",
        "kind": kind,
        "at": at,
        "payload": {} if payload is None else payload,
    }


def make_proposal(
    source_hash: str,
    *,
    signal_id: str = "sig-1",
    side: str = "LONG",
    quantity: str = "0.02",
    stop: str | None = None,
    tp1: str | None = None,
    tp2: str | None = None,
    horizon_hours: int = 12,
    source_close_at: int = 59999,
    decision_at: int = 60000,
    expires_at: int = 180000,
    version: int = 1,
    schema_version: int = 1,
    exit_identity: str = "OFFLINE_TP1_BE_TIME_CAP_V1",
) -> dict[str, Any]:
    """Construct a synthetic signal proposal payload."""
    default_stop = "95" if side != "SHORT" else "105"
    default_tp1 = "105" if side != "SHORT" else "95"
    default_tp2 = "110" if side != "SHORT" else "90"
    return {
        "schema_version": schema_version,
        "signal_id": signal_id,
        "source_hash": source_hash,
        "source_close_at": source_close_at,
        "decision_at": decision_at,
        "side": side,
        "quantity": quantity,
        "stop": stop or default_stop,
        "tp1": tp1 or default_tp1,
        "tp2": tp2 or default_tp2,
        "horizon_hours": horizon_hours,
        "expires_at": expires_at,
        "version": version,
        "exit_identity": exit_identity,
    }


def make_token(
    proposal: dict[str, Any],
    *,
    token_id: str = "tok-1",
    issued_at: int = 60002,
    expires_at: int = 160000,
    quantity: str | None = None,
    signal_id: str | None = None,
    proposal_hash: str | None = None,
    proposal_version: int = 1,
    approved: Any = True,
    issuer: str = "TRUSTED_HUMAN_FIXTURE",
) -> dict[str, Any]:
    """Construct an explicit human approval token fixture."""
    return {
        "token_id": token_id,
        "signal_id": signal_id if signal_id is not None else proposal["signal_id"],
        "proposal_hash": proposal_hash if proposal_hash is not None else digest(proposal),
        "proposal_version": proposal_version,
        "quantity": quantity if quantity is not None else proposal["quantity"],
        "issued_at": issued_at,
        "expires_at": expires_at,
        "approved": approved,
        "issuer": issuer,
    }


def make_analysis(
    proposal: dict[str, Any],
    *,
    as_of: int = 60000,
    summary: str = "Synthetic descriptive risk note; no execution authority.",
    risk: str = "DESCRIPTIVE_ONLY",
    schema_version: int = 1,
    signal_id: str | None = None,
    proposal_hash: str | None = None,
    source_hash: str | None = None,
) -> dict[str, Any]:
    """Construct a synthetic mock LLM analysis payload."""
    return {
        "schema_version": schema_version,
        "signal_id": signal_id if signal_id is not None else proposal["signal_id"],
        "proposal_hash": proposal_hash if proposal_hash is not None else digest(proposal),
        "source_hash": source_hash if source_hash is not None else proposal["source_hash"],
        "as_of": as_of,
        "summary": summary,
        "risk": risk,
    }


def build_state_at_phase(
    target_phase: str, *, side: str = "LONG", quantity: str = "0.02"
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build a valid state up to the requested workflow phase."""
    b0 = make_bar(0)
    prop = make_proposal(digest(b0), side=side, quantity=quantity)
    tok = make_token(prop)
    analysis = make_analysis(prop)
    s = initial_state([tok])
    if target_phase == "READY":
        return s, b0, prop, tok
    s = transition(s, make_event("BAR", 59999, b0))
    if target_phase == "BAR_LOADED":
        return s, b0, prop, tok
    s = transition(s, make_event("PROPOSE", 60000, prop))
    if target_phase == "PROPOSED":
        return s, b0, prop, tok
    s = transition(s, make_event("ANALYZE", 60001, analysis))
    if target_phase == "ANALYZED":
        return s, b0, prop, tok
    s = transition(s, make_event("APPROVE", 60002, {"token_id": tok["token_id"]}))
    if target_phase == "APPROVED":
        return s, b0, prop, tok
    s = transition(s, make_event("PLACE", 60003))
    if target_phase == "PLACED":
        return s, b0, prop, tok
    s = transition(s, make_event("FILL_ENTRY", 60004, {"fill_id": "entry-1"}))
    if target_phase == "WAIT_ENTRY_ACK":
        return s, b0, prop, tok
    b1 = make_bar(60000)
    s = transition(s, make_event("BAR", 119999, b1))
    s = transition(
        s,
        make_event(
            "ACK",
            120004,
            {"ack_id": "ack-entry-1", "order_id": s["order_id"], "fill_id": "entry-1"},
        ),
    )
    if target_phase == "OPEN":
        return s, b1, prop, tok
    raise ValueError(f"Unsupported target_phase: {target_phase}")
