from __future__ import annotations

import pytest

from btc_quant_agent.decision.models import CasePackageV1
from btc_quant_agent.position_supervisor import (
    PositionObservationV1,
    PositionSupervisor,
    position_case_from_event,
)

NOW = 1_700_000_000_000
HASH = "a" * 64


def observation(**changes: object) -> PositionObservationV1:
    values: dict[str, object] = {
        "account_snapshot_hash": HASH, "market_source_hash": "b" * 64,
        "symbol": "BTCUSDT", "observed_at_ms": NOW, "quantity": 1.0,
        "previous_quantity": 0.0, "entry_price": 100.0, "mark_price": 100.0,
        "unrealized_pnl_usdt": 0.0, "realized_pnl_usdt": 0.0,
        "margin_usdt": 20.0, "stop_price": 90.0, "take_profit_price": 110.0,
        "funding_rate": 0.0, "oi_change_pct": 0.0, "volatility_percentile": 0.2,
        "spread_bps": 1.0, "tactical_regime": "BULLISH", "grid_boundary_breached": False,
        "order_status": "FILLED", "order_filled_quantity": 1.0,
        "order_observed_at_ms": NOW, "evidence_id": "c" * 64,
        "signal_identity": "new-signal", "prior_evidence_ids": ("d" * 64,),
        "prior_signal_identities": ("old-signal",), "add_opportunity": False,
    }
    values.update(changes)
    return PositionObservationV1.build(**values)


def market_case() -> CasePackageV1:
    return CasePackageV1.build(
        case_id="base", created_at_ms=NOW, observed_at_ms=NOW,
        expires_at_ms=NOW + 60_000, symbol="BTCUSDT", trigger="MARKET_WATCH",
        strategy="BREAKOUT", strategy_version="v1", direction="LONG",
        evidence_id="c" * 64, snapshot_hash="snapshot", signal_identity="new-signal",
        price=100.0, entry_low=99.0, entry_high=101.0, stop_loss=90.0,
        take_profit_1=110.0, take_profit_2=120.0, atr=1.0,
        data_quality="OK", spread_bps=1.0, liquidity_usdt=100_000.0,
    )


@pytest.mark.parametrize(("change", "trigger"), [
    ({"previous_quantity": 0.0}, "POSITION_OPENED"),
    ({"previous_quantity": 1.0, "order_status": "PARTIALLY_FILLED",
      "order_observed_at_ms": NOW - 31_000}, "PARTIAL_FILL_STALE"),
    ({"previous_quantity": 1.0, "mark_price": 91.0}, "STOP_NEAR"),
    ({"previous_quantity": 1.0, "mark_price": 109.0}, "TP_NEAR"),
    ({"previous_quantity": 1.0, "tactical_regime": "BEARISH"}, "REGIME_REVERSAL"),
    ({"previous_quantity": 1.0, "oi_change_pct": 0.25}, "OI_SHOCK"),
    ({"previous_quantity": 1.0, "funding_rate": 0.002}, "FUNDING_SHOCK"),
    ({"previous_quantity": 1.0, "volatility_percentile": 0.95}, "VOLATILITY_SPIKE"),
    ({"previous_quantity": 1.0, "spread_bps": 12.0}, "LIQUIDITY_DETERIORATION"),
    ({"previous_quantity": 1.0, "grid_boundary_breached": True}, "GRID_BOUNDARY_BREACH"),
    ({"previous_quantity": 1.0, "add_opportunity": True}, "ADD_OPPORTUNITY"),
])
def test_each_trigger_persists_with_source_identity(tmp_path, change, trigger):
    supervisor = PositionSupervisor(tmp_path / "live.db")
    events = supervisor.evaluate(observation(**change), NOW)
    found = next(event for event in events if event.trigger == trigger)
    assert found.source_hash == observation(**change).observation_hash
    found.verify()
    assert supervisor.get_event(found.event_id) == found


def test_restart_dedupes_identical_source_and_cools_new_ticks(tmp_path):
    path = tmp_path / "live.db"
    first = PositionSupervisor(path).evaluate(observation(), NOW)
    assert first
    restarted = PositionSupervisor(path)
    assert restarted.evaluate(observation(), NOW + 1) == ()
    assert restarted.evaluate(observation(mark_price=101.0), NOW + 2) == ()
    assert restarted.evaluate(observation(mark_price=102.0), NOW + 60_001) == ()


def test_add_requires_independent_market_evidence(tmp_path):
    supervisor = PositionSupervisor(tmp_path / "live.db")
    assert not any(e.trigger == "ADD_OPPORTUNITY" for e in supervisor.evaluate(
        observation(previous_quantity=1.0, add_opportunity=True,
                    evidence_id="d" * 64), NOW))


def test_position_case_links_fresh_verified_market_identity(tmp_path):
    event = PositionSupervisor(tmp_path / "live.db").evaluate(observation(), NOW)[0]
    base = market_case()
    case = position_case_from_event(base, event, now_ms=NOW)
    case.verify()
    assert case.evidence_id == base.evidence_id
    assert case.signal_identity == base.signal_identity
    assert case.base_case_hash == base.case_hash
    assert case.position_event_hash == event.event_hash
    assert case.case_hash != base.case_hash


import asyncio


def test_only_material_new_event_invokes_existing_analysis(tmp_path):
    async def run() -> None:
        calls: list[str] = []

        class Spy:
            async def analyze_case(self, case: CasePackageV1) -> None:
                calls.append(case.case_hash)

        supervisor = PositionSupervisor(
            tmp_path / "live.db", analysis_service=Spy(), fresh_market_case=lambda _: market_case(),
        )
        ordinary = observation(previous_quantity=1.0)
        assert await supervisor.process(ordinary, NOW) == ()
        assert not calls
        assert await supervisor.process(observation(), NOW)
        assert len(calls) == 1
        assert await supervisor.process(observation(), NOW + 1) == ()
        assert len(calls) == 1

    asyncio.run(run())
