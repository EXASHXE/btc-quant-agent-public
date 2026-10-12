"""Categories 3 & 4 Assurance: Independent Decimal ledger and native OS crash/WAL recovery."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from scripts.g1_offline_preview_r1.fixtures import make_fixture
from scripts.g1_offline_preview_r1.model import (
    SafetyViolation,
    canonical,
    digest,
    initial_state,
)
from scripts.g1_offline_preview_r1.reducer import transition
from scripts.g1_offline_preview_r1.storage import Engine
from scripts.strategy_research.g1_offline_assurance_r1 import OWN_SCRATCH
from scripts.strategy_research.g1_offline_assurance_r1.crash_worker import (
    PROCESS_CRASH_CHECKPOINTS,
)
from scripts.strategy_research.g1_offline_assurance_r1.oracle import (
    REPO_ROOT,
    build_state_at_phase,
    independent_fill_price,
    independent_fixture_ledger,
    make_analysis,
    make_bar,
    make_event,
    make_proposal,
    make_token,
    record_negative_transition,
)

FIXTURES_DIR = REPO_ROOT / "scripts/g1_offline_preview_r1/fixtures"


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
@pytest.mark.parametrize(
    ("exit_kind", "horizon"),
    [
        ("STOP", 24),
        ("TP2", 24),
        ("TIME_CAP", 12),
        ("TIME_CAP", 18),
        ("TIME_CAP", 24),
    ],
)
def test_independent_decimal_reference_across_sides_and_exits(
    side: str, exit_kind: str, horizon: int
) -> None:
    fixture = make_fixture(side, horizon, exit_kind)
    oracle = independent_fixture_ledger(side, horizon, exit_kind)
    s = initial_state(fixture["trusted_approvals"])
    for ev in fixture["events"]:
        prev_cash = s["cash"]
        s = transition(s, ev)
        if ev["kind"] in ("TP1", "STOP", "TP2", "TIME_CAP"):
            # Unacknowledged exit proceeds must never be spendable before causal ACK
            assert s["cash"] == prev_cash
    assert s["phase"] == "CLOSED"
    assert not s["pending_cash"]
    assert Decimal(s["reserved_notional"]) == Decimal(0)
    assert Decimal(s["cash"]) == Decimal(oracle["final_cash"])
    assert len(s["journal"]) == len(oracle["effects"]) == 6
    for actual, expected in zip(s["journal"], oracle["effects"], strict=True):
        assert actual["kind"] == expected["kind"]
        assert actual["at"] == expected["at"]
        assert Decimal(actual["cash_delta"]) == Decimal(str(expected["cash_delta"]))
        assert Decimal(actual["quantity"]) == Decimal(str(expected["quantity"]))


@pytest.mark.parametrize(
    ("qty", "expected_tier", "expected_rem"),
    [
        ("0.011", "0.005", "0.006"),
        ("0.003", "0.001", "0.002"),
        ("0.050", "0.025", "0.025"),
    ],
)
def test_lot_rounding_floors_tp1_half_and_preserves_residual(
    qty: str, expected_tier: str, expected_rem: str
) -> None:
    s, _, _, _ = build_state_at_phase("OPEN", side="LONG", quantity=qty)
    b_tp1 = make_bar(120000, last_open="106", last_high="107", last_low="105", last_close="106")
    s = transition(s, make_event("BAR", 179999, b_tp1))
    s = transition(s, make_event("TP1", 179999, {"fill_id": f"tp1-{qty}"}))
    assert Decimal(s["remaining_qty"]) == Decimal(expected_rem)
    tp1_trace = next(r for r in s["trace"] if r["kind"] == "TP1" and "quantity" in r)
    assert Decimal(tp1_trace["quantity"]) == Decimal(expected_tier)


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_adverse_stop_gap_execution_and_fee_proxy(side: str) -> None:
    s, _, _, _ = build_state_at_phase("OPEN", side=side, quantity="0.02")
    # Gap open beyond stop (95 for LONG -> opens at 90; 105 for SHORT -> opens at 110)
    gap_open = "90" if side == "LONG" else "110"
    b_gap = make_bar(
        120000,
        last_open=gap_open,
        last_high=str(int(gap_open) + 1),
        last_low=str(int(gap_open) - 1),
        last_close=gap_open,
    )
    s = transition(s, make_event("BAR", 179999, b_gap))
    s = transition(s, make_event("STOP", 179999, {"fill_id": f"gap-stop-{side}"}))
    stop_trace = next(r for r in s["trace"] if r["kind"] == "STOP" and "fill_price" in r)
    want_price = independent_fill_price(Decimal(gap_open), side, is_entry=False)
    assert Decimal(stop_trace["fill_price"]) == want_price
    assert Decimal(stop_trace["exit_fee"]) == Decimal("0.02") * want_price * Decimal("0.0006")


def test_funding_deduplication_collisions_and_rate_bounds() -> None:
    s, _, _, _ = build_state_at_phase("OPEN", side="LONG", quantity="0.02")
    # Out-of-bounds funding rate (> 0.1)
    record_negative_transition(
        "funding_rate_above_bound",
        "financial_ledger",
        s,
        make_event(
            "FUNDING",
            120005,
            {"settlement_id": "f-bound", "settlement_at": 120005, "rate_fraction": "0.1001"},
        ),
        "FUNDING_RATE_BOUNDS",
    )
    # Timestamp mismatch between event.at and payload.settlement_at
    record_negative_transition(
        "funding_clock_mismatch",
        "financial_ledger",
        s,
        make_event(
            "FUNDING",
            120005,
            {"settlement_id": "f-mismatch", "settlement_at": 120006, "rate_fraction": "0.0001"},
        ),
        "FUNDING_DUPLICATE_OR_FUTURE",
    )
    s = transition(
        s,
        make_event(
            "FUNDING",
            120005,
            {"settlement_id": "f-valid", "settlement_at": 120005, "rate_fraction": "-0.0005"},
        ),
    )
    # Negative funding on LONG credits positive cash
    assert Decimal(s["journal"][-1]["cash_delta"]) == Decimal("0.001000")
    # Reused settlement_id at a later timestamp rejected
    record_negative_transition(
        "duplicate_settlement_id_later_clock",
        "financial_ledger",
        s,
        make_event(
            "FUNDING",
            120006,
            {"settlement_id": "f-valid", "settlement_at": 120006, "rate_fraction": "0.0001"},
        ),
        "FUNDING_DUPLICATE_OR_FUTURE",
    )


@pytest.mark.parametrize("second_exit", ["STOP", "TP2"])
@pytest.mark.parametrize("ack_reverse", [False, True])
def test_two_pending_exit_acks_conserve_cash_in_all_orders(
    second_exit: str, ack_reverse: bool
) -> None:
    s, _, _, _ = build_state_at_phase("OPEN", side="LONG", quantity="0.02")
    b_tp1 = make_bar(120000, last_open="106", last_high="107", last_low="105", last_close="106")
    s = transition(s, make_event("BAR", 179999, b_tp1))
    s = transition(s, make_event("TP1", 179999, {"fill_id": "exit-tp1"}))
    assert s["phase"] == "WAIT_TP1_ACK"

    # Next bar triggers second_exit BEFORE exit-tp1 is ACKed
    if second_exit == "STOP":
        b_exit2 = make_bar(180000, last_open="94", last_high="95", last_low="93", last_close="94")
    else:
        b_exit2 = make_bar(
            180000, last_open="111", last_high="112", last_low="110", last_close="111"
        )
    s = transition(s, make_event("BAR", 239999, b_exit2))
    assert s["required_exit"]["kind"] == second_exit
    s = transition(s, make_event(second_exit, 239999, {"fill_id": f"exit-{second_exit}"}))
    assert len(s["pending_cash"]) == 2
    assert Decimal(s["remaining_qty"]) == Decimal(0)
    assert s["phase"] == "EXIT_WAIT_ACK"

    cash_before_acks = Decimal(s["cash"])
    expected_net = sum((Decimal(v) for v in s["pending_cash"].values()), Decimal(0))

    b_ack = make_bar(240000, last_open="100", last_high="101", last_low="99", last_close="100")
    s = transition(s, make_event("BAR", 299999, b_ack))
    fill_order = (
        [f"exit-{second_exit}", "exit-tp1"]
        if ack_reverse
        else ["exit-tp1", f"exit-{second_exit}"]
    )
    for i, fid in enumerate(fill_order):
        s = transition(
            s,
            make_event(
                "ACK",
                300000 + i,
                {"ack_id": f"ack-{fid}", "order_id": s["order_id"], "fill_id": fid},
            ),
        )
    assert s["phase"] == "CLOSED"
    assert not s["pending_cash"]
    assert Decimal(s["reserved_notional"]) == Decimal(0)
    assert Decimal(s["cash"]) == cash_before_acks + expected_net


def test_min_notional_and_five_percent_reserve_fail_closed() -> None:
    # 1. PLACE min-notional fail-closed: qty=0.001 at last_close=500 -> notional ~0.50025 < 1
    b_low = make_bar(
        0, last_open="500", last_high="505", last_low="495", last_close="500", mark_close="500"
    )
    prop_low = make_proposal(
        digest(b_low), quantity="0.001", stop="450", tp1="550", tp2="600"
    )
    tok_low = make_token(prop_low)
    s_low = initial_state([tok_low])
    s_low = transition(s_low, make_event("BAR", 59999, b_low))
    s_low = transition(s_low, make_event("PROPOSE", 60000, prop_low))
    s_low = transition(s_low, make_event("ANALYZE", 60001, make_analysis(prop_low)))
    s_low = transition(s_low, make_event("APPROVE", 60002, {"token_id": tok_low["token_id"]}))
    record_negative_transition(
        "place_below_synthetic_min_notional",
        "financial_ledger",
        s_low,
        make_event("PLACE", 60003),
        "ONE_X_OR_MIN_NOTIONAL",
    )

    # 2. TP1 partial lot fail-closed when entry_qty = 0.001 (half floors to 0.000 LOT)
    s_one_lot, _, _, _ = build_state_at_phase("OPEN", side="LONG", quantity="0.001")
    b_tp1 = make_bar(120000, last_open="106", last_high="107", last_low="105", last_close="106")
    s_one_lot = transition(s_one_lot, make_event("BAR", 179999, b_tp1))
    record_negative_transition(
        "tp1_unsplit_single_lot",
        "financial_ledger",
        s_one_lot,
        make_event("TP1", 179999, {"fill_id": "tp1-tiny"}),
        "PARTIAL_LOT_OR_MIN_NOTIONAL",
    )

    # 3. 5% reserve boundary on PLACE / FILL_ENTRY when qty * price exceeds 95% of cash (950)
    b_high = make_bar(
        0,
        last_open="20000",
        last_high="20100",
        last_low="19900",
        last_close="20000",
        mark_close="20000",
    )
    prop_high = make_proposal(
        digest(b_high), quantity="0.05", stop="19000", tp1="21000", tp2="22000"
    )
    tok_high = make_token(prop_high)
    s_high = initial_state([tok_high])
    s_high = transition(s_high, make_event("BAR", 59999, b_high))
    s_high = transition(s_high, make_event("PROPOSE", 60000, prop_high))
    s_high = transition(s_high, make_event("ANALYZE", 60001, make_analysis(prop_high)))
    s_high = transition(s_high, make_event("APPROVE", 60002, {"token_id": tok_high["token_id"]}))
    record_negative_transition(
        "place_exceeds_95pct_reserve_cap",
        "financial_ledger",
        s_high,
        make_event("PLACE", 60003),
        "ONE_X_OR_MIN_NOTIONAL",
    )


def test_single_position_exclusivity_and_six_hour_cooldown_boundary() -> None:
    s, _, prop, _ = build_state_at_phase("OPEN", side="LONG", quantity="0.02")
    # Cannot propose a second position while OPEN
    record_negative_transition(
        "propose_while_position_open",
        "financial_ledger",
        s,
        make_event("PROPOSE", 120005, {**prop, "signal_id": "sig-2"}),
        "PHASE_INVALID",
    )
    # Close via STOP + ACK
    b_stop = make_bar(120000, last_open="95", last_high="96", last_low="94", last_close="95")
    s = transition(s, make_event("BAR", 179999, b_stop))
    s = transition(s, make_event("STOP", 179999, {"fill_id": "stop-close"}))
    b_ack = make_bar(180000, last_open="95", last_high="96", last_low="94", last_close="95")
    s = transition(s, make_event("BAR", 239999, b_ack))
    s = transition(
        s,
        make_event(
            "ACK",
            239999,
            {"ack_id": "ack-stop-close", "order_id": s["order_id"], "fill_id": "stop-close"},
        ),
    )
    assert s["phase"] == "CLOSED"
    cooldown_until = s["cooldown_until"]
    assert cooldown_until == 239999 + 6 * 3600 * 1000

    # Inject a fresh bar right at cooldown boundary without looping 360 bars by testing PROPOSE check
    record_negative_transition(
        "propose_one_ms_before_cooldown_expiry",
        "financial_ledger",
        s,
        make_event("PROPOSE", cooldown_until - 1, {**prop, "signal_id": "sig-early"}),
        "COOLDOWN_ACTIVE",
    )


def _run_worker(args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "-m",
        "scripts.strategy_research.g1_offline_assurance_r1.crash_worker",
        *args,
    ]
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _event_id_for(fixture_name: str, kind: str, occurrence: int) -> str:
    if kind == "OUTBOX":
        return "OUTBOX"
    events = json.loads((FIXTURES_DIR / fixture_name).read_text(encoding="utf-8"))["events"]
    matches = [e["id"] for e in events if e["kind"] == kind]
    return matches[occurrence]


@pytest.fixture(scope="module")
def reference_24h_long() -> tuple[Path, dict[str, Any]]:
    OWN_SCRATCH.mkdir(mode=0o700, parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="assurance-ref-long-", dir=OWN_SCRATCH))
    proc = _run_worker(["--fixture", "long_24h.json", "--output", str(out)])
    assert proc.returncode == 0, proc.stderr
    receipt = json.loads((out / "RECEIPT.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "G1_OFFLINE_PREVIEW_VERIFIED"
    return out, receipt


@pytest.mark.parametrize(
    ("case_name", "kind", "occurrence", "edge", "is_novel"),
    PROCESS_CRASH_CHECKPOINTS,
    ids=[row[0] for row in PROCESS_CRASH_CHECKPOINTS],
)
def test_native_process_kill_and_restart_across_22_checkpoints(
    reference_24h_long: tuple[Path, dict[str, Any]],
    case_name: str,
    kind: str,
    occurrence: int,
    edge: str,
    is_novel: bool,
) -> None:
    _ref_dir, ref_receipt = reference_24h_long
    out = Path(tempfile.mkdtemp(prefix=f"assurance-kill-{case_name}-", dir=OWN_SCRATCH))
    ev_id = _event_id_for("long_24h.json", kind, occurrence)
    killed = _run_worker(
        [
            "--fixture",
            "long_24h.json",
            "--output",
            str(out),
            "--crash-event",
            ev_id,
            "--crash-edge",
            edge,
        ]
    )
    assert killed.returncode == 91, (case_name, is_novel, killed.stdout, killed.stderr)

    resumed = _run_worker(["--fixture", "long_24h.json", "--output", str(out)])
    assert resumed.returncode == 0, (case_name, is_novel, resumed.stdout, resumed.stderr)
    actual = json.loads((out / "RECEIPT.json").read_text(encoding="utf-8"))
    for key in (
        "status",
        "safety_status",
        "state_hash",
        "wal_chain",
        "logical_event_count",
        "journal_hash",
        "journal_effects",
        "cash",
        "available_cash",
        "reserved_notional",
        "phase",
        "pending_cash",
        "counters",
    ):
        assert actual[key] == ref_receipt[key], (case_name, key)


@pytest.mark.parametrize(
    "edge", ["before_append", "after_append", "after_fsync", "after_snapshot"]
)
def test_native_process_kill_around_second_pending_exit_ack(edge: str) -> None:
    OWN_SCRATCH.mkdir(mode=0o700, parents=True, exist_ok=True)
    ref_out = Path(tempfile.mkdtemp(prefix="assurance-dual-ref-", dir=OWN_SCRATCH))
    ref_run = _run_worker(["--mode=dual_pending_ack", "--output", str(ref_out)])
    assert ref_run.returncode == 0
    ref_rec = json.loads((ref_out / "RECEIPT.json").read_text(encoding="utf-8"))

    out = Path(tempfile.mkdtemp(prefix=f"assurance-dual-{edge}-", dir=OWN_SCRATCH))
    killed = _run_worker(
        [
            "--mode=dual_pending_ack",
            "--output",
            str(out),
            "--crash-event",
            "ACK-SECOND-PENDING",
            "--crash-edge",
            edge,
        ]
    )
    assert killed.returncode == 91
    resumed = _run_worker(["--mode=dual_pending_ack", "--output", str(out)])
    assert resumed.returncode == 0
    actual = json.loads((out / "RECEIPT.json").read_text(encoding="utf-8"))
    assert actual["status"] == "G1_OFFLINE_PREVIEW_VERIFIED"
    assert actual["state_hash"] == ref_rec["state_hash"]
    assert actual["wal_chain"] == ref_rec["wal_chain"]
    assert actual["journal_hash"] == ref_rec["journal_hash"]
    assert actual["cash"] == ref_rec["cash"]


@pytest.mark.parametrize(
    ("tamper_mode", "expected_code"),
    [
        ("torn_trailing_bytes", "WAL_TRUNCATED"),
        ("duplicate_wal_line", "WAL_CHAIN"),
        ("checksum_mismatch", "WAL_CHAIN"),
        ("event_hash_mismatch_recomputed_record", "WAL_EVENT_IDENTITY"),
        ("duplicate_event_id_recomputed_chain", "WAL_EVENT_IDENTITY"),
        ("state_hash_mismatch_recomputed_record", "WAL_STATE_IDENTITY"),
        ("changed_genesis_fixture", "WAL_GENESIS_MISMATCH"),
        ("unknown_wal_format_version", "WAL_GENESIS_MISMATCH"),
        ("checkpoint_fork_mutated_state", "CHECKPOINT_IDENTITY"),
        ("checkpoint_ahead_of_stale_wal", "CHECKPOINT_AHEAD_OF_WAL"),
        ("checkpoint_unknown_format_version", "CHECKPOINT_AHEAD_OF_WAL"),
        ("checkpoint_missing_schema_field", "CHECKPOINT_SCHEMA"),
    ],
)
def test_wal_and_checkpoint_corruption_quarantine_and_fail_closed(
    tamper_mode: str, expected_code: str, tmp_path: Path
) -> None:
    s, b0, prop, _ = build_state_at_phase("READY")
    ev1 = make_event("BAR", 59999, b0, "BAR-0")
    ev2 = make_event("PROPOSE", 60000, prop, "PROPOSE-1")
    with Engine(tmp_path, s, temporary=True) as eng:
        eng.apply(ev1)
        eng.apply(ev2)
        eng.checkpoint()

    wal_path = tmp_path / "events.wal.jsonl"
    lines = wal_path.read_text(encoding="utf-8").splitlines()
    rec1 = json.loads(lines[1])
    rec2 = json.loads(lines[2])
    reopen_initial = s

    if tamper_mode == "torn_trailing_bytes":
        wal_path.write_text("\n".join(lines) + '\n{"seq":3', encoding="utf-8")
    elif tamper_mode == "duplicate_wal_line":
        wal_path.write_text("\n".join([*lines, lines[2]]) + "\n", encoding="utf-8")
    elif tamper_mode == "checksum_mismatch":
        rec2["record_hash"] = "00" * 32
        wal_path.write_text(
            "\n".join([lines[0], lines[1], canonical(rec2)]) + "\n", encoding="utf-8"
        )
    elif tamper_mode == "event_hash_mismatch_recomputed_record":
        body = {k: v for k, v in rec1.items() if k != "record_hash"}
        body["event_hash"] = "11" * 32
        forged = {**body, "record_hash": digest(body)}
        wal_path.write_text("\n".join([lines[0], canonical(forged)]) + "\n", encoding="utf-8")
    elif tamper_mode == "duplicate_event_id_recomputed_chain":
        # Second WAL record reuses BAR-0 id with valid hash chain -> triggers WAL_EVENT_IDENTITY
        body2 = {
            "seq": 2,
            "previous": rec1["record_hash"],
            "event": ev1,
            "event_hash": digest(ev1),
            "state_hash": rec1["state_hash"],
        }
        forged2 = {**body2, "record_hash": digest(body2)}
        wal_path.write_text(
            "\n".join([lines[0], lines[1], canonical(forged2)]) + "\n", encoding="utf-8"
        )
    elif tamper_mode == "state_hash_mismatch_recomputed_record":
        body = {k: v for k, v in rec1.items() if k != "record_hash"}
        body["state_hash"] = "22" * 32
        forged = {**body, "record_hash": digest(body)}
        wal_path.write_text("\n".join([lines[0], canonical(forged)]) + "\n", encoding="utf-8")
    elif tamper_mode == "changed_genesis_fixture":
        reopen_initial = initial_state([])
    elif tamper_mode == "unknown_wal_format_version":
        header = json.loads(lines[0])
        header["format"] = "G1_OFFLINE_WAL_V99"
        wal_path.write_text(
            "\n".join([canonical(header), lines[1], lines[2]]) + "\n", encoding="utf-8"
        )
    elif tamper_mode == "checkpoint_fork_mutated_state":
        cp_file = max((tmp_path / "checkpoints").glob("checkpoint-*.json"))
        cp_file.chmod(0o600)
        snap = json.loads(cp_file.read_text(encoding="utf-8"))
        snap["state"]["cash"] = "999999"
        cp_file.write_text(canonical(snap) + "\n", encoding="utf-8")
    elif tamper_mode == "checkpoint_ahead_of_stale_wal":
        wal_path.write_text("\n".join([lines[0], lines[1]]) + "\n", encoding="utf-8")
    elif tamper_mode == "checkpoint_unknown_format_version":
        cp_file = max((tmp_path / "checkpoints").glob("checkpoint-*.json"))
        cp_file.chmod(0o600)
        snap = json.loads(cp_file.read_text(encoding="utf-8"))
        snap["format"] = "G1_CHECKPOINT_V99"
        cp_file.write_text(canonical(snap) + "\n", encoding="utf-8")
    elif tamper_mode == "checkpoint_missing_schema_field":
        cp_file = max((tmp_path / "checkpoints").glob("checkpoint-*.json"))
        cp_file.chmod(0o600)
        snap = json.loads(cp_file.read_text(encoding="utf-8"))
        del snap["state_hash"]
        cp_file.write_text(canonical(snap) + "\n", encoding="utf-8")

    with pytest.raises(SafetyViolation) as exc:
        Engine(tmp_path, reopen_initial, temporary=True)
    assert exc.value.code == expected_code
    q_files = list((tmp_path / "quarantine").glob("*.json"))
    assert len(q_files) >= 1
    q_meta = json.loads(q_files[-1].read_text(encoding="utf-8"))
    assert q_meta["code"] == expected_code
    assert q_meta["unsafe_effects_replayed"] is False


def test_checkpoint_immutable_conflict_and_missing_outbox_recovery(
    tmp_path: Path,
) -> None:
    s, b0, prop, _ = build_state_at_phase("READY")
    with Engine(tmp_path, s, temporary=True) as eng:
        eng.apply(make_event("BAR", 59999, b0, "BAR-0"))
        eng.apply(make_event("PROPOSE", 60000, prop, "PROPOSE-1"))
        eng.deliver()
        outbox_path = tmp_path / "outbox_delivery.jsonl"
        assert outbox_path.exists()
        # Remove outbox_delivery.jsonl to simulate missing physical outbox file
        outbox_path.unlink()

    # Reopen from WAL, verify state recovered and outbox can be deterministically redelivered
    with Engine(tmp_path, s, temporary=True) as eng2:
        assert eng2.seq == 2
        assert len(eng2.state["outbox"]) == 1
        assert eng2.deliver() == 1
        assert (tmp_path / "outbox_delivery.jsonl").exists()
        # Corrupt the existing checkpoint file bytes to trigger CHECKPOINT_IMMUTABLE_CONFLICT
        cp = next((tmp_path / "checkpoints").glob("checkpoint-00000002-*.json"))
        cp.chmod(0o600)
        cp.write_text('{"corrupt":true}\n', encoding="utf-8")
        with pytest.raises(SafetyViolation, match="CHECKPOINT_IMMUTABLE_CONFLICT"):
            eng2.checkpoint()


def test_unknown_state_schema_version_rejected() -> None:
    s, b0, _, _ = build_state_at_phase("READY")
    bad_state = {**s, "schema_version": 2}
    record_negative_transition(
        "unknown_state_schema_version",
        "failure_recovery",
        bad_state,
        make_event("BAR", 59999, b0),
        "STATE_SCHEMA",
    )
