"""Category 4: Core Integration, MarketPitPort, BookIntegrityV1, and Exact Financial Math Tests."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.g1_offline_preview_r1.model import (  # noqa: E402
    SafetyViolation,
    digest,
    initial_state,
)
from scripts.g1_offline_preview_r1.reducer import transition  # noqa: E402
from scripts.g1g3_offline_ports_r1.durable_supervisor import (  # noqa: E402
    DurableSidecarSupervisor,
)
from scripts.g1g3_offline_ports_r1.market_pit_port import (  # noqa: E402
    MarketPitPort,
    make_synthetic_bar_envelope,
    make_synthetic_market_event_v1_from_g1_funding,
)


def _valid_book(
    *,
    snapshot_update_id: int = 100,
    first_update_id: int = 101,
    final_update_id: int = 105,
    previous_final_update_id: int | None = None,
    continuous: bool = True,
    best_bid: str = "29999.50",
    best_ask: str = "30000.50",
    observed_depth_levels: int = 20,
    stale_age_ms: int = 50,
    quality: str = "VERIFIED",
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "snapshot_update_id": snapshot_update_id,
        "first_update_id": first_update_id,
        "final_update_id": final_update_id,
        "previous_final_update_id": previous_final_update_id,
        "continuous": continuous,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "observed_depth_levels": observed_depth_levels,
        "stale_age_ms": stale_age_ms,
        "quality": quality,
        "reason_codes": reason_codes if reason_codes is not None else [],
    }


def test_market_pit_valid_closed_bar_accepted_and_translated() -> None:
    port = MarketPitPort()
    env = make_synthetic_bar_envelope(0, side="LONG")
    res = port.ingest_envelope(env, reference_at_ms=59999)
    assert res["status"] == "ACCEPTED"
    assert res["g1_event"]["kind"] == "BAR"
    assert res["g1_event"]["at"] == 59999
    assert port.accepted_envelope_count == 1


def test_market_pit_rejects_unclosed_incomplete_bar() -> None:
    port = MarketPitPort()
    env = make_synthetic_bar_envelope(0)
    env["payload"]["closed"] = False
    env["payload_sha256"] = digest(env["payload"])
    with pytest.raises(SafetyViolation) as exc:
        port.ingest_envelope(env, reference_at_ms=59999)
    assert exc.value.code == "BAR_INCOMPLETE_UNCLOSED"


def test_market_pit_rejects_stale_and_future_known_envelopes() -> None:
    port = MarketPitPort(max_stale_ms=5000)
    env = make_synthetic_bar_envelope(0)
    # Stale: reference_at_ms=70000, available_at_ms=59999 -> age 10001 > 5000
    with pytest.raises(SafetyViolation) as stale_exc:
        port.ingest_envelope(env, reference_at_ms=70000)
    assert stale_exc.value.code == "MARKET_EVENT_STALE"

    # Future-known: reference_at_ms=59000 < available_at_ms=59999
    with pytest.raises(SafetyViolation) as fut_exc:
        port.ingest_envelope(env, reference_at_ms=59000)
    assert fut_exc.value.code == "MARKET_EVENT_FUTURE_KNOWN"


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda e: e.update({"symbol": "ETHUSDT"}), "MARKET_EVENT_SYMBOL_INVALID"),
        (lambda e: e.update({"product": "SPOT"}), "MARKET_EVENT_PRODUCT_INVALID"),
        (lambda e: e.update({"channel": "unknown_chan"}), "MARKET_EVENT_CHANNEL_INVALID"),
        (lambda e: e.update({"source_stream_id": "UNTRUSTED_STREAM"}), "MARKET_PROVENANCE_DRIFT"),
        (lambda e: e.update({"raw_source_manifest_sha256": "0" * 64}), "MARKET_PROVENANCE_DRIFT"),
        (lambda e: e.update({"payload_sha256": "f" * 64}), "MARKET_EVENT_PAYLOAD_HASH_MISMATCH"),
        (lambda e: e.update({"quality": "DEGRADED"}), "MARKET_EVENT_QUALITY_UNUSABLE"),
        (
            lambda e: e.update({"source_stream_id": "stream_with_api_key_leak"}),
            "MARKET_EVENT_SECRET_OR_PRIVATE_FIELD",
        ),
    ],
)
def test_market_pit_rejects_invalid_envelope_fields_and_provenance(
    mutator: Any, expected_code: str
) -> None:
    port = MarketPitPort()
    env = make_synthetic_bar_envelope(0)
    mutator(env)
    with pytest.raises(SafetyViolation) as exc:
        port.ingest_envelope(env, reference_at_ms=59999)
    assert exc.value.code == expected_code


def test_market_pit_clock_uncertain_and_monotonic_regression() -> None:
    port = MarketPitPort()
    env0 = make_synthetic_bar_envelope(0, sequence=0, monotonic_ns=2_000_000)
    port.ingest_envelope(env0, reference_at_ms=59999)

    # Monotonic regression (mono_ns <= 2_000_000)
    env_mono_reg = make_synthetic_bar_envelope(1, sequence=1, monotonic_ns=1_500_000)
    with pytest.raises(SafetyViolation) as exc_mono:
        port.ingest_envelope(env_mono_reg, reference_at_ms=119999)
    assert exc_mono.value.code == "MONOTONIC_REGRESSION"

    # Wall clock regression while monotonic advances -> CLOCK_UNCERTAIN
    env_wall_reg = make_synthetic_bar_envelope(1, sequence=1, monotonic_ns=3_000_000)
    env_wall_reg["observed_wall_utc_ms"] = 50000
    with pytest.raises(SafetyViolation) as exc_wall:
        port.ingest_envelope(env_wall_reg, reference_at_ms=119999)
    assert exc_wall.value.code == "CLOCK_UNCERTAIN"

    # Explicit CLOCK_UNCERTAIN reason code in envelope
    env_rc = make_synthetic_bar_envelope(1, sequence=1, monotonic_ns=3_000_000)
    env_rc["reason_codes"] = ["CLOCK_UNCERTAIN"]
    with pytest.raises(SafetyViolation) as exc_rc:
        port.ingest_envelope(env_rc, reference_at_ms=119999)
    assert exc_rc.value.code == "CLOCK_UNCERTAIN"


def test_book_integrity_valid_and_gap_crossed_stale_rejections() -> None:
    port = MarketPitPort(max_stale_ms=5000)
    b1 = _valid_book(first_update_id=101, final_update_id=105)
    port.validate_book_integrity(b1)
    assert port.last_book_final_update_id == 105

    # Continuous follow-up book
    b2 = _valid_book(
        first_update_id=106,
        final_update_id=110,
        previous_final_update_id=105,
    )
    port.validate_book_integrity(b2)
    assert port.last_book_final_update_id == 110

    # Sequence gap (previous_final_update_id=108 != 110)
    with pytest.raises(SafetyViolation) as exc_gap:
        port.validate_book_integrity(
            _valid_book(first_update_id=111, final_update_id=115, previous_final_update_id=108)
        )
    assert exc_gap.value.code == "BOOK_SEQUENCE_GAP"

    # Explicit continuous=False
    with pytest.raises(SafetyViolation) as exc_cont:
        port.validate_book_integrity(_valid_book(continuous=False, previous_final_update_id=110))
    assert exc_cont.value.code == "BOOK_SEQUENCE_GAP"

    # Crossed spread (best_bid >= best_ask)
    with pytest.raises(SafetyViolation) as exc_cross:
        port.validate_book_integrity(
            _valid_book(best_bid="30001.00", best_ask="30000.00", previous_final_update_id=110)
        )
    assert exc_cross.value.code == "BOOK_CROSSED_SPREAD"

    # Stale book (stale_age_ms > 5000)
    with pytest.raises(SafetyViolation) as exc_stale:
        port.validate_book_integrity(_valid_book(stale_age_ms=6000, previous_final_update_id=110))
    assert exc_stale.value.code == "BOOK_STALE"


def test_market_pit_missing_bar_gap_fails_closed_without_forward_fill() -> None:
    port = MarketPitPort()
    port.ingest_envelope(make_synthetic_bar_envelope(0, sequence=0), reference_at_ms=59999)
    # Skip bar 1 and send bar 2 directly
    with pytest.raises(SafetyViolation) as exc:
        port.ingest_envelope(make_synthetic_bar_envelope(2, sequence=2), reference_at_ms=179999)
    assert exc.value.code == "NO_DATA_UNKNOWN_GAP"


def test_market_pit_deduplication_and_conflicting_duplicate_rejection() -> None:
    port = MarketPitPort()
    env0 = make_synthetic_bar_envelope(0, sequence=0)
    res1 = port.ingest_envelope(env0, reference_at_ms=59999)
    assert res1["status"] == "ACCEPTED"

    # Identical duplicate is ignored idempotently and counted
    res2 = port.ingest_envelope(copy.deepcopy(env0), reference_at_ms=59999)
    assert res2["status"] == "DUPLICATE_IGNORED"
    assert port.duplicate_envelope_count == 1

    # Conflicting payload with same dedupe key raises MARKET_EVENT_PROVENANCE_DRIFT
    bad_dup = copy.deepcopy(env0)
    bad_dup["observed_monotonic_ns"] += 1_000_000
    bad_dup["payload"]["last_close"] = "30001.00"
    bad_dup["payload_sha256"] = digest(bad_dup["payload"])
    with pytest.raises(SafetyViolation) as exc:
        port.ingest_envelope(bad_dup, reference_at_ms=59999)
    assert exc.value.code == "MARKET_EVENT_PROVENANCE_DRIFT"


def test_market_pit_funding_estimated_rejected_and_settled_accepted() -> None:
    port = MarketPitPort()
    g1_fund = {
        "id": "FUNDING-480000",
        "kind": "FUNDING",
        "at": 480000,
        "payload": {
            "settlement_id": "fund-1",
            "settlement_at": 480000,
            "rate_fraction": "0.0001",
        },
    }
    env = make_synthetic_market_event_v1_from_g1_funding(
        g1_fund, sequence=10, monotonic_ns=10_000_000
    )
    est_env = copy.deepcopy(env)
    est_env["payload"]["settled"] = False
    est_env["payload"]["rate_type"] = "ESTIMATED_PREDICTED"
    est_env["payload_sha256"] = digest(est_env["payload"])

    with pytest.raises(SafetyViolation) as exc:
        port.ingest_envelope(est_env, reference_at_ms=480000)
    assert exc.value.code == "FUNDING_ESTIMATED_NOT_SETTLED"

    res = port.ingest_envelope(env, reference_at_ms=480000)
    assert res["status"] == "ACCEPTED"
    assert res["g1_event"]["kind"] == "FUNDING"
    assert res["g1_event"]["payload"]["rate_fraction"] == "0.0001"


def test_market_pit_decision_pit_guard() -> None:
    port = MarketPitPort()
    port.ingest_envelope(make_synthetic_bar_envelope(0, sequence=0), reference_at_ms=59999)
    with pytest.raises(SafetyViolation) as exc:
        port.validate_decision_pit(59998)
    assert exc.value.code == "DECISION_BEFORE_FEATURE_KNOWN_AT"
    port.validate_decision_pit(60000)


def test_core_g1_last_vs_mark_separation_and_one_x_mark_exposure_guard() -> None:
    # Build an open LONG position at entry=100, stop=95, tp1=105, tp2=110
    b0 = {
        "source": "SYNTHETIC_V1",
        "open_time": 0,
        "close_time": 59999,
        "available_at": 59999,
        "last_open": "100",
        "last_high": "101",
        "last_low": "99",
        "last_close": "100",
        "mark_close": "100",
    }
    prop = {
        "schema_version": 1,
        "signal_id": "s-last-mark",
        "source_hash": digest(b0),
        "source_close_at": 59999,
        "decision_at": 60000,
        "side": "LONG",
        "quantity": "0.02",
        "stop": "95",
        "tp1": "105",
        "tp2": "110",
        "horizon_hours": 12,
        "expires_at": 180000,
        "version": 1,
        "exit_identity": "OFFLINE_TP1_BE_TIME_CAP_V1",
    }
    token = {
        "token_id": "tok-1",
        "signal_id": "s-last-mark",
        "proposal_hash": digest(prop),
        "proposal_version": 1,
        "quantity": "0.02",
        "issued_at": 60002,
        "expires_at": 160000,
        "approved": True,
        "issuer": "TRUSTED_HUMAN_FIXTURE",
    }
    s = initial_state([token])
    s = transition(s, {"id": "B0", "kind": "BAR", "at": 59999, "payload": b0})
    s = transition(s, {"id": "P", "kind": "PROPOSE", "at": 60000, "payload": prop})
    s = transition(
        s,
        {
            "id": "A",
            "kind": "ANALYZE",
            "at": 60001,
            "payload": {
                "schema_version": 1,
                "signal_id": "s-last-mark",
                "proposal_hash": digest(prop),
                "source_hash": digest(b0),
                "as_of": 60000,
                "summary": "Note",
                "risk": "DESCRIPTIVE_ONLY",
            },
        },
    )
    s = transition(
        s, {"id": "APP", "kind": "APPROVE", "at": 60002, "payload": {"token_id": "tok-1"}}
    )
    s = transition(s, {"id": "PL", "kind": "PLACE", "at": 60003, "payload": {}})
    s = transition(s, {"id": "FE", "kind": "FILL_ENTRY", "at": 60004, "payload": {"fill_id": "e1"}})
    # Bar 1: mark_close moves to 110 while last stays at 100 -> mark_equity and funding use mark_close (110), NOT last_close (100)!
    b1 = {
        "source": "SYNTHETIC_V1",
        "open_time": 60000,
        "close_time": 119999,
        "available_at": 119999,
        "last_open": "100",
        "last_high": "101",
        "last_low": "99",
        "last_close": "100",
        "mark_close": "110",
    }
    s = transition(s, {"id": "B1", "kind": "BAR", "at": 119999, "payload": b1})
    s = transition(
        s,
        {
            "id": "ACK-E1",
            "kind": "ACK",
            "at": 120004,
            "payload": {"ack_id": "a1", "order_id": s["order_id"], "fill_id": "e1"},
        },
    )
    s = transition(
        s,
        {
            "id": "F1",
            "kind": "FUNDING",
            "at": 120005,
            "payload": {"settlement_id": "f1", "settlement_at": 120005, "rate_fraction": "0.001"},
        },
    )
    # 0.02 * 110 (mark_close) * 0.001 = -0.00220
    assert s["journal"][-1]["cash_delta"] == "-0.00220"

    # Synthetic 1x mark exposure violation on SHORT when mark_close spikes above mark_equity / qty
    prop_short = {
        **prop,
        "signal_id": "s-last-mark-short",
        "side": "SHORT",
        "stop": "105",
        "tp1": "95",
        "tp2": "90",
    }
    tok_short = {
        **token,
        "token_id": "tok-short-1",
        "signal_id": "s-last-mark-short",
        "proposal_hash": digest(prop_short),
    }
    ss = initial_state([tok_short])
    ss = transition(ss, {"id": "B0", "kind": "BAR", "at": 59999, "payload": b0})
    ss = transition(ss, {"id": "P", "kind": "PROPOSE", "at": 60000, "payload": prop_short})
    ss = transition(
        ss,
        {
            "id": "A",
            "kind": "ANALYZE",
            "at": 60001,
            "payload": {
                "schema_version": 1,
                "signal_id": "s-last-mark-short",
                "proposal_hash": digest(prop_short),
                "source_hash": digest(b0),
                "as_of": 60000,
                "summary": "Note",
                "risk": "DESCRIPTIVE_ONLY",
            },
        },
    )
    ss = transition(
        ss, {"id": "APP", "kind": "APPROVE", "at": 60002, "payload": {"token_id": "tok-short-1"}}
    )
    ss = transition(ss, {"id": "PL", "kind": "PLACE", "at": 60003, "payload": {}})
    ss = transition(
        ss, {"id": "FE", "kind": "FILL_ENTRY", "at": 60004, "payload": {"fill_id": "es1"}}
    )
    b1_extreme_mark = {
        "source": "SYNTHETIC_V1",
        "open_time": 60000,
        "close_time": 119999,
        "available_at": 119999,
        "last_open": "100",
        "last_high": "101",
        "last_low": "99",
        "last_close": "100",
        "mark_close": "30000",
    }
    with pytest.raises(SafetyViolation) as exc:
        transition(ss, {"id": "B1", "kind": "BAR", "at": 119999, "payload": b1_extreme_mark})
    assert exc.value.code == "MARK_EXPOSURE_ABOVE_ONE_X"


def test_core_g1_out_of_order_or_unknown_ack_rejected() -> None:
    s = initial_state([])
    with pytest.raises(SafetyViolation) as exc:
        transition(
            s,
            {
                "id": "ACK-BAD",
                "kind": "ACK",
                "at": 60005,
                "payload": {"ack_id": "a1", "order_id": "o1", "fill_id": "unknown"},
            },
        )
    assert exc.value.code == "PHASE_INVALID"


def test_llm_failure_fails_closed_without_order_authorization(tmp_path: Path) -> None:
    sup = DurableSidecarSupervisor(tmp_path / "llm_fail_closed", temporary=True)
    res = sup.run_scenario(side="LONG", allow_loopback=True, llm_mode="HTTP_500")
    assert res["status"] == "NO_ACTION_OR_MANUAL_REVIEW"
    assert res["order_authorized"] is False
    assert len(sup.settled_intents) == 0


@pytest.mark.parametrize("allow_loopback", [False, True])
def test_long_24h_exact_financial_baseline_reproduction(
    tmp_path: Path, allow_loopback: bool
) -> None:
    sup = DurableSidecarSupervisor(
        tmp_path / f"long_24h_{allow_loopback}",
        temporary=True,
    )
    receipt = sup.run_scenario(
        side="LONG", horizon=24, exit_kind="STOP", allow_loopback=allow_loopback
    )
    assert receipt["sidecar_terminal"] == "G1G3_OFFLINE_PORTS_BOUNDED_VERIFIED"
    assert receipt["phase"] == "CLOSED"
    assert receipt["cash"] == "1000.33834810"
    assert receipt["available_cash"] == "1000.33834810"
    assert receipt["mark_equity"] == "1000.33834810"
    assert receipt["reserved_notional"] == "0.0000"
    assert receipt["remaining_qty"] == "0.000"
    assert receipt["journal_effects"] == 6
    assert receipt["settled_simulated_intent_count"] == 1


@pytest.mark.parametrize("allow_loopback", [False, True])
def test_short_24h_exact_financial_baseline_reproduction(
    tmp_path: Path, allow_loopback: bool
) -> None:
    sup = DurableSidecarSupervisor(
        tmp_path / f"short_24h_{allow_loopback}",
        temporary=True,
    )
    receipt = sup.run_scenario(
        side="SHORT", horizon=24, exit_kind="STOP", allow_loopback=allow_loopback
    )
    assert receipt["sidecar_terminal"] == "G1G3_OFFLINE_PORTS_BOUNDED_VERIFIED"
    assert receipt["phase"] == "CLOSED"
    assert receipt["cash"] == "1000.34054750"
    assert receipt["available_cash"] == "1000.34054750"
    assert receipt["mark_equity"] == "1000.34054750"
    assert receipt["reserved_notional"] == "0.0000"
    assert receipt["remaining_qty"] == "0.000"
    assert receipt["journal_effects"] == 6
    assert receipt["settled_simulated_intent_count"] == 1


@pytest.mark.parametrize("exit_kind", ["TIME_CAP", "TP2"])
def test_24h_time_cap_and_tp2_scenarios_close_flat_with_exact_invariants(
    tmp_path: Path, exit_kind: str
) -> None:
    sup = DurableSidecarSupervisor(tmp_path / f"long_{exit_kind}", temporary=True)
    receipt = sup.run_scenario(side="LONG", horizon=24, exit_kind=exit_kind, allow_loopback=False)
    assert receipt["sidecar_terminal"] == "G1G3_OFFLINE_PORTS_BOUNDED_VERIFIED"
    assert receipt["phase"] == "CLOSED"
    assert receipt["remaining_qty"] == "0.000"
    assert receipt["reserved_notional"] == "0.0000"
    assert receipt["settled_simulated_intent_count"] == 1
