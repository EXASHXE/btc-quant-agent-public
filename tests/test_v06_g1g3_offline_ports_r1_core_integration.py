"""Category 4: Core Integration, MarketPitPort, BookIntegrityV1, and Exact Financial Math Tests."""

from __future__ import annotations

import copy
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.g1_offline_preview_r1.model import (
    SafetyViolation,
    digest,
    initial_state,
)
from scripts.g1_offline_preview_r1.reducer import transition
from scripts.g1g3_offline_ports_r1.durable_supervisor import (
    DurableSidecarSupervisor,
)
from scripts.g1g3_offline_ports_r1.market_pit_port import (
    MarketPitPort,
    calculate_settled_funding_cash_flow,
    compute_settlement_exposure,
    make_synthetic_bar_envelope,
    make_synthetic_funding_envelope,
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


def test_market_pit_funding_on_time_settled() -> None:
    port = MarketPitPort()
    env = make_synthetic_funding_envelope(
        settlement_id="s-ontime",
        settlement_at_ms=480_000,
        rate_fraction="0.00010000",
        observed_wall_utc_ms=480_000,
        available_at_ms=480_000,
        mark_price="64000.00",
    )
    res = port.ingest_envelope(env, reference_at_ms=480_000)
    assert res["status"] == "ACCEPTED"
    assert res["available_at_ms"] == 480_000
    assert res["feature_known_at_ms"] == 480_000
    assert res["g1_event"]["kind"] == "FUNDING"
    assert res["g1_event"]["at"] == 480_000
    assert res["g1_event"]["payload"]["settlement_id"] == "s-ontime"
    assert res["g1_event"]["payload"]["rate_fraction"] == "0.00010000"


def test_market_pit_funding_3s_and_multi_minute_late_receipt_with_known_at() -> None:
    port = MarketPitPort()
    # Case A: 3-second late receipt
    t_settle = 480_000
    t_recv_3s = 483_000
    env_3s = make_synthetic_funding_envelope(
        settlement_id="s-3s-late",
        settlement_at_ms=t_settle,
        rate_fraction="0.00015000",
        observed_wall_utc_ms=t_recv_3s,
        available_at_ms=t_recv_3s,
        sequence=1,
        monotonic_ns=1_000_000,
    )
    res_3s = port.ingest_envelope(env_3s, reference_at_ms=t_recv_3s)
    assert res_3s["status"] == "ACCEPTED"
    assert res_3s["available_at_ms"] == t_recv_3s
    assert res_3s["feature_known_at_ms"] == t_recv_3s
    # Economic clock is preserved at settlement time, NOT delayed receipt time
    assert res_3s["g1_event"]["at"] == t_settle
    assert res_3s["g1_event"]["payload"]["settlement_at"] == t_settle

    # Case B: Multi-minute late receipt (5 minutes = 300_000 ms)
    t_settle_2 = 960_000
    t_recv_5m = 1_260_000
    env_5m = make_synthetic_funding_envelope(
        settlement_id="s-5m-late",
        settlement_at_ms=t_settle_2,
        rate_fraction="-0.00020000",
        observed_wall_utc_ms=t_recv_5m,
        available_at_ms=t_recv_5m,
        sequence=2,
        monotonic_ns=2_000_000,
    )
    res_5m = port.ingest_envelope(env_5m, reference_at_ms=t_recv_5m)
    assert res_5m["status"] == "ACCEPTED"
    assert res_5m["available_at_ms"] == t_recv_5m
    assert res_5m["feature_known_at_ms"] == t_recv_5m
    assert res_5m["g1_event"]["at"] == t_settle_2


def test_market_pit_funding_unchanged_earlier_decision_feature_view() -> None:
    port = MarketPitPort()
    # Bar arrives at 60_000
    b0 = make_synthetic_bar_envelope(0, sequence=1, monotonic_ns=1_000_000)
    port.ingest_envelope(b0, reference_at_ms=59_999)
    # Decision at 60_000 is valid before late funding arrives
    port.validate_decision_pit(60_000)

    # Late funding arrives with available_at_ms = 120_000 for settlement at 60_000
    env_late = make_synthetic_funding_envelope(
        settlement_id="s-late-decision",
        settlement_at_ms=60_000,
        rate_fraction="0.0001",
        observed_wall_utc_ms=120_000,
        available_at_ms=120_000,
        sequence=2,
        monotonic_ns=2_000_000,
    )
    port.ingest_envelope(env_late, reference_at_ms=120_000)

    # After late funding arrives, feature known-at is 120_000.
    # An earlier decision timestamp (60_000) now fails closed, proving future funding
    # cannot retroactively leak into an earlier decision information set.
    with pytest.raises(SafetyViolation) as exc:
        port.validate_decision_pit(60_000)
    assert exc.value.code == "DECISION_BEFORE_FEATURE_KNOWN_AT"

    # New decision at or after receiver known-at (120_000) succeeds
    port.validate_decision_pit(120_000)


def test_market_pit_funding_duplicate_replay_idempotence() -> None:
    port = MarketPitPort()
    env = make_synthetic_funding_envelope(
        settlement_id="s-replay-1",
        settlement_at_ms=480_000,
        rate_fraction="0.00010000",
        observed_wall_utc_ms=481_000,
        available_at_ms=481_000,
        sequence=1,
        monotonic_ns=1_000_000,
    )
    res1 = port.ingest_envelope(env, reference_at_ms=481_000)
    assert res1["status"] == "ACCEPTED"
    assert res1["g1_event"] is not None

    # Exact replay of same envelope
    res2 = port.ingest_envelope(env, reference_at_ms=481_000)
    assert res2["status"] == "DUPLICATE_IGNORED"
    assert res2["g1_event"] is None

    # Replay under different sequence and later wall time with same settlement ID and rate
    env_rekey = make_synthetic_funding_envelope(
        settlement_id="s-replay-1",
        settlement_at_ms=480_000,
        rate_fraction="0.00010000",
        observed_wall_utc_ms=482_000,
        available_at_ms=482_000,
        sequence=2,
        monotonic_ns=2_000_000,
    )
    res3 = port.ingest_envelope(env_rekey, reference_at_ms=482_000)
    assert res3["status"] == "DUPLICATE_IGNORED"
    assert res3["g1_event"] is None
    assert port.accepted_envelope_count == 1
    assert port.duplicate_envelope_count == 2
    assert port.duplicate_funding_count == 2

    # Port clocks advanced correctly through the duplicate funding envelope
    assert port.last_monotonic_ns == 2_000_000
    assert port.last_wall_utc_ms == 482_000

    # Clock regression after duplicate funding must fail closed
    env_mono_regress = make_synthetic_funding_envelope(
        settlement_id="s-replay-next",
        settlement_at_ms=483_000,
        rate_fraction="0.00010000",
        observed_wall_utc_ms=483_000,
        available_at_ms=483_000,
        sequence=3,
        monotonic_ns=1_500_000,
    )
    with pytest.raises(SafetyViolation) as exc_mono:
        port.ingest_envelope(env_mono_regress, reference_at_ms=483_000)
    assert exc_mono.value.code == "MONOTONIC_REGRESSION"

    # Provenance drift on sequence 2 dedupe key must be detected
    env_tampered_seq2 = make_synthetic_funding_envelope(
        settlement_id="s-other-tampered",
        settlement_at_ms=482_000,
        rate_fraction="0.00010000",
        observed_wall_utc_ms=482_000,
        available_at_ms=482_000,
        sequence=2,
        monotonic_ns=2_000_000,
    )
    with pytest.raises(SafetyViolation) as exc_drift:
        port.ingest_envelope(env_tampered_seq2, reference_at_ms=482_000)
    assert exc_drift.value.code == "MARKET_EVENT_PROVENANCE_DRIFT"


def test_market_pit_funding_same_settlement_id_conflicting_rate_or_mark_hard_fail() -> None:
    port = MarketPitPort()
    env1 = make_synthetic_funding_envelope(
        settlement_id="s-conflict-rate",
        event_id="FUNDING-EVT-1",
        settlement_at_ms=480_000,
        rate_fraction="0.00010000",
        mark_price="64000.00",
        observed_wall_utc_ms=481_000,
        available_at_ms=481_000,
        sequence=1,
        monotonic_ns=1_000_000,
    )
    res = port.ingest_envelope(env1, reference_at_ms=481_000)
    assert res["status"] == "ACCEPTED"

    # Same settlement ID with conflicting rate must hard fail
    env_bad_rate = make_synthetic_funding_envelope(
        settlement_id="s-conflict-rate",
        event_id="FUNDING-EVT-1",
        settlement_at_ms=480_000,
        rate_fraction="0.00020000",
        mark_price="64000.00",
        observed_wall_utc_ms=482_000,
        available_at_ms=482_000,
        sequence=2,
        monotonic_ns=2_000_000,
    )
    with pytest.raises(SafetyViolation) as exc_rate:
        port.ingest_envelope(env_bad_rate, reference_at_ms=482_000)
    assert exc_rate.value.code == "FUNDING_SETTLEMENT_CONFLICT"

    # Same settlement ID with conflicting Mark value must hard fail
    env_bad_mark = make_synthetic_funding_envelope(
        settlement_id="s-conflict-rate",
        event_id="FUNDING-EVT-1",
        settlement_at_ms=480_000,
        rate_fraction="0.00010000",
        mark_price="65000.00",
        observed_wall_utc_ms=483_000,
        available_at_ms=483_000,
        sequence=3,
        monotonic_ns=3_000_000,
    )
    with pytest.raises(SafetyViolation) as exc_mark:
        port.ingest_envelope(env_bad_mark, reference_at_ms=483_000)
    assert exc_mark.value.code == "FUNDING_SETTLEMENT_CONFLICT"

    # Same settlement ID with missing Mark when previously witnessed must hard fail
    env_missing_mark = make_synthetic_funding_envelope(
        settlement_id="s-conflict-rate",
        event_id="FUNDING-EVT-1",
        settlement_at_ms=480_000,
        rate_fraction="0.00010000",
        mark_price=None,
        observed_wall_utc_ms=484_000,
        available_at_ms=484_000,
        sequence=4,
        monotonic_ns=4_000_000,
    )
    with pytest.raises(SafetyViolation) as exc_no_mark:
        port.ingest_envelope(env_missing_mark, reference_at_ms=484_000)
    assert exc_no_mark.value.code == "FUNDING_SETTLEMENT_CONFLICT"

    # Same settlement ID with conflicting event ID must hard fail
    env_diff_eid = make_synthetic_funding_envelope(
        settlement_id="s-conflict-rate",
        event_id="FUNDING-EVT-FORGED",
        settlement_at_ms=480_000,
        rate_fraction="0.00010000",
        mark_price="64000.00",
        observed_wall_utc_ms=485_000,
        available_at_ms=485_000,
        sequence=5,
        monotonic_ns=5_000_000,
    )
    with pytest.raises(SafetyViolation) as exc_eid:
        port.ingest_envelope(env_diff_eid, reference_at_ms=485_000)
    assert exc_eid.value.code == "FUNDING_SETTLEMENT_CONFLICT"


def test_market_pit_funding_receipt_before_settlement_rejected() -> None:
    port = MarketPitPort()
    # Case 1: Ingress wall clock is earlier than economic settlement
    env_early_wall = make_synthetic_funding_envelope(
        settlement_id="s-early-wall",
        settlement_at_ms=500_000,
        rate_fraction="0.0001",
        observed_wall_utc_ms=490_000,
        available_at_ms=500_000,
        sequence=1,
        monotonic_ns=1_000_000,
    )
    with pytest.raises(SafetyViolation) as exc1:
        port.ingest_envelope(env_early_wall)
    assert exc1.value.code == "FUNDING_PIT_INVALID"

    # Case 2: Available time is earlier than economic settlement
    env_early_avail = make_synthetic_funding_envelope(
        settlement_id="s-early-avail",
        settlement_at_ms=500_000,
        rate_fraction="0.0001",
        observed_wall_utc_ms=500_000,
        available_at_ms=499_000,
        sequence=2,
        monotonic_ns=2_000_000,
    )
    with pytest.raises(SafetyViolation) as exc2:
        port.ingest_envelope(env_early_avail)
    assert exc2.value.code in ("AVAILABLE_AT_BEFORE_INGRESS_WALL", "FUNDING_PIT_INVALID")

    # Case 3: Available time is in the future relative to reference time
    env_future_ref = make_synthetic_funding_envelope(
        settlement_id="s-future-ref",
        settlement_at_ms=500_000,
        rate_fraction="0.0001",
        observed_wall_utc_ms=505_000,
        available_at_ms=505_000,
        sequence=3,
        monotonic_ns=3_000_000,
    )
    with pytest.raises(SafetyViolation) as exc3:
        port.ingest_envelope(env_future_ref, reference_at_ms=500_000)
    assert exc3.value.code == "MARKET_EVENT_FUTURE_KNOWN"


def test_market_pit_funding_missing_mark_or_rate_cost_incomplete() -> None:
    # Missing mark price => COST_INCOMPLETE (never silently 0)
    r1 = calculate_settled_funding_cash_flow(
        side="LONG",
        quantity="1.5",
        mark_price=None,
        rate_fraction="0.0001",
    )
    assert r1["status"] == "COST_INCOMPLETE"
    assert r1["cash_flow"] is None

    # Missing rate fraction => COST_INCOMPLETE
    r2 = calculate_settled_funding_cash_flow(
        side="LONG",
        quantity="1.5",
        mark_price="64000.00",
        rate_fraction=None,
    )
    assert r2["status"] == "COST_INCOMPLETE"
    assert r2["cash_flow"] is None

    # Nonpositive or invalid mark => COST_INCOMPLETE
    r3 = calculate_settled_funding_cash_flow(
        side="LONG",
        quantity="1.5",
        mark_price="-100.00",
        rate_fraction="0.0001",
    )
    assert r3["status"] == "COST_INCOMPLETE"
    assert r3["cash_flow"] is None

    # Zero mark price with negative rate fails closed to COST_INCOMPLETE (never assumes 0.0)
    r4 = calculate_settled_funding_cash_flow(
        side="LONG",
        quantity="1.5",
        mark_price="0.00",
        rate_fraction="-0.0001",
    )
    assert r4["status"] == "COST_INCOMPLETE"
    assert r4["reason"] == "MARK_PRICE_INVALID"
    assert r4["cash_flow"] is None

    # Zero mark price in synthetic envelope fails closed with DECIMAL_BOUNDS
    port = MarketPitPort()
    env_zero_mark = make_synthetic_funding_envelope(
        settlement_id="s-zero-mark",
        settlement_at_ms=480_000,
        rate_fraction="-0.0001",
        mark_price="0.00",
        observed_wall_utc_ms=481_000,
        available_at_ms=481_000,
    )
    with pytest.raises(SafetyViolation) as exc_zero_mark:
        port.ingest_envelope(env_zero_mark, reference_at_ms=481_000)
    assert exc_zero_mark.value.code == "DECIMAL_BOUNDS"


def test_market_pit_funding_credit_debit_side_symmetry() -> None:
    qty = Decimal("2.0")
    mark = Decimal("50000.00")
    rate_pos = Decimal("0.0001")
    rate_neg = Decimal("-0.0002")

    # Positive rate: LONG pays, SHORT receives
    long_pos = calculate_settled_funding_cash_flow(
        side="LONG", quantity=qty, mark_price=mark, rate_fraction=rate_pos
    )
    short_pos = calculate_settled_funding_cash_flow(
        side="SHORT", quantity=qty, mark_price=mark, rate_fraction=rate_pos
    )
    assert long_pos["status"] == "COST_COMPLETE"
    assert short_pos["status"] == "COST_COMPLETE"
    assert long_pos["cash_flow"] == Decimal("-10.0000")
    assert short_pos["cash_flow"] == Decimal("10.0000")
    assert long_pos["cash_flow"] + short_pos["cash_flow"] == Decimal(0)

    # Negative rate: LONG receives, SHORT pays
    long_neg = calculate_settled_funding_cash_flow(
        side="LONG", quantity=qty, mark_price=mark, rate_fraction=rate_neg
    )
    short_neg = calculate_settled_funding_cash_flow(
        side="SHORT", quantity=qty, mark_price=mark, rate_fraction=rate_neg
    )
    assert long_neg["status"] == "COST_COMPLETE"
    assert short_neg["status"] == "COST_COMPLETE"
    assert long_neg["cash_flow"] == Decimal("20.0000")
    assert short_neg["cash_flow"] == Decimal("-20.0000")
    assert long_neg["cash_flow"] + short_neg["cash_flow"] == Decimal(0)


def test_market_pit_funding_exposure_before_vs_after_partial_fill_and_settlement() -> None:
    # Case A: Partial exit executed BEFORE settlement (at 400_000, settlement at 500_000, receipt at 850_000)
    fills_a = [
        {"action": "ENTRY", "quantity": "0.010", "executed_at": 100_000},
        {"action": "EXIT", "quantity": "0.004", "executed_at": 400_000},
        {"action": "EXIT", "quantity": "0.006", "executed_at": 800_000},
    ]
    exp_a = compute_settlement_exposure(fills_a, 500_000, side="LONG")
    # Residual exposure at settlement was 0.010 - 0.004 = 0.006
    assert exp_a == Decimal("0.006")
    cf_a = calculate_settled_funding_cash_flow(
        side="LONG", quantity=exp_a, mark_price="60000.00", rate_fraction="0.0001"
    )
    assert cf_a["cash_flow"] == -Decimal("0.006") * Decimal("60000.00") * Decimal("0.0001")

    # Case B: Partial exit executed AFTER settlement (at 600_000, settlement at 500_000, receipt at 850_000)
    fills_b = [
        {"action": "ENTRY", "quantity": "0.010", "executed_at": 100_000},
        {"action": "EXIT", "quantity": "0.004", "executed_at": 600_000},
        {"action": "EXIT", "quantity": "0.006", "executed_at": 800_000},
    ]
    exp_b = compute_settlement_exposure(fills_b, 500_000, side="LONG")
    # Full exposure was intact at settlement time (0.010)
    assert exp_b == Decimal("0.010")
    cf_b = calculate_settled_funding_cash_flow(
        side="LONG", quantity=exp_b, mark_price="60000.00", rate_fraction="0.0001"
    )
    assert cf_b["cash_flow"] == -Decimal("0.010") * Decimal("60000.00") * Decimal("0.0001")

    # Case C: SHORT exposure with partial fill before vs after settlement
    exp_c = compute_settlement_exposure(fills_a, 500_000, side="SHORT")
    assert exp_c == Decimal("-0.006")
    # Piped directly into cash flow calculation with signed SHORT exposure
    cf_c = calculate_settled_funding_cash_flow(
        side="SHORT", quantity=exp_c, mark_price="60000.00", rate_fraction="0.0001"
    )
    assert cf_c["status"] == "COST_COMPLETE"
    assert cf_c["signed_exposure"] == Decimal("-0.006")
    # SHORT receives positive funding cash flow:
    assert cf_c["cash_flow"] == Decimal("0.006") * Decimal("60000.00") * Decimal("0.0001")


def test_market_pit_funding_ambiguous_fill_vs_settlement_boundary() -> None:
    # A fill executed at the exact millisecond of funding settlement is ambiguous
    fills_boundary = [
        {"action": "ENTRY", "quantity": "0.010", "executed_at": 100_000},
        {"action": "EXIT", "quantity": "0.004", "executed_at": 500_000},
    ]
    with pytest.raises(SafetyViolation) as exc:
        compute_settlement_exposure(fills_boundary, 500_000, side="LONG")
    assert exc.value.code == "AMBIGUOUS_SETTLEMENT_BOUNDARY"


def test_market_pit_funding_zero_real_funding_complete_witnessed_coverage() -> None:
    # Zero rate with incomplete coverage fails closed to COST_INCOMPLETE
    r_incomplete = calculate_settled_funding_cash_flow(
        side="LONG",
        quantity="1.0",
        mark_price="60000.00",
        rate_fraction="0.0",
        funding_coverage_complete=False,
    )
    assert r_incomplete["status"] == "COST_INCOMPLETE"
    assert r_incomplete["cash_flow"] is None

    # Zero rate with missing mark fails closed
    r_no_mark = calculate_settled_funding_cash_flow(
        side="LONG",
        quantity="1.0",
        mark_price=None,
        rate_fraction="0.0",
        funding_coverage_complete=True,
    )
    assert r_no_mark["status"] == "COST_INCOMPLETE"
    assert r_no_mark["cash_flow"] is None

    # Zero rate with full witnessed coverage realizes exact 0.0 cash flow
    r_complete = calculate_settled_funding_cash_flow(
        side="LONG",
        quantity="1.0",
        mark_price="60000.00",
        rate_fraction="0.0",
        funding_coverage_complete=True,
    )
    assert r_complete["status"] == "COST_COMPLETE"
    assert r_complete["cash_flow"] == Decimal(0)

    # Flat position (quantity=0) with complete coverage realizes exact 0.0 cash flow
    r_zero_qty = calculate_settled_funding_cash_flow(
        side="LONG",
        quantity=Decimal(0),
        mark_price="60000.00",
        rate_fraction="0.0001",
        funding_coverage_complete=True,
    )
    assert r_zero_qty["status"] == "COST_COMPLETE"
    assert r_zero_qty["cash_flow"] == Decimal(0)
    assert r_zero_qty["signed_exposure"] == Decimal(0)

    # Flat position with incomplete coverage fails closed to COST_INCOMPLETE
    r_zero_qty_incomplete = calculate_settled_funding_cash_flow(
        side="LONG",
        quantity=Decimal(0),
        mark_price="60000.00",
        rate_fraction="0.0001",
        funding_coverage_complete=False,
    )
    assert r_zero_qty_incomplete["status"] == "COST_INCOMPLETE"
    assert r_zero_qty_incomplete["cash_flow"] is None


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
