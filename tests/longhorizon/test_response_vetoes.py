import pytest

from btc_quant_agent.platform.canary import clock_domain as d
from btc_quant_agent.platform.canary.public_data import instrument
from btc_quant_agent.platform.canary.public_io import Wire
from btc_quant_agent.platform.core import primitive
from .fixtures import engine_at, probes, quote


@pytest.mark.parametrize("scenario", ["CHASE", "EXPIRED", "MISSING"])
def test_conditional_response_does_not_survive_chase_expiry_or_missing_quote(tmp_path, scenario):
    c, _, _, _, e = engine_at(tmp_path)
    known = c.sample()
    wire = Wire(**e.metadata["wire"])
    expiry_delta = 120000 if scenario == "EXPIRED" else 3600000
    a = {"id": "conditional", "symbol": "BTCUSDT", "side": "LONG", "strategy": "trend_pullback",
         "contract": primitive(instrument(wire.payload, "BTCUSDT", wire).spec),
         "expiry": c.wall() + expiry_delta, "expiry_mono_ms": c.mono() + expiry_delta,
         "clock_epoch_id": known["epoch_id"], "chase_cap": "101", "zone_low": "99",
         "zone_high": "101", "entry_mode": "market"}
    e.episodes["conditional"] = {"anchors": a, "known_at": c.wall(), "known_mono": c.mono(),
                                  "responses": {}, "last_status": "ARMED"}
    c.advance(3 * 60000)
    probes(e, c)
    if scenario == "MISSING":
        c.advance(6000)
        with d.decision_clock(c.sample(), e.scope.hash):
            e.revalidate("BTCUSDT", c.wall())
    else:
        c.advance(100)
        for i in range(1, 5):
            quote(e, c, sequence=i, bid="102" if scenario == "CHASE" else "100")
            c.advance(10)
        e.flush()
    result = e.episodes["conditional"]["responses"]["3"]
    assert result["conditional_market_survival"] == ("UNKNOWN" if scenario == "MISSING" else "FAILED")
    if scenario == "CHASE":
        assert "CHASE_CAP_EXCEEDED" in result["conditional_vetoes"]
    if scenario == "EXPIRED":
        assert "SETUP_INVALID_OR_EXPIRED" in result["conditional_vetoes"]
    assert not result["entry_eligible"] and not result["modeled_fill"]


def test_direct_native_authority_cannot_skip_preflight():
    from btc_quant_agent.platform.canary import longhorizon as lh
    from btc_quant_agent.platform.canary.public_policy import PublicStop
    from .fixtures import scope, START
    fabricated = scope()
    unverified = lh.make_scope(fabricated.authorization)
    with pytest.raises(PublicStop, match="NATIVE_PREFLIGHT_REQUIRED"):
        unverified.require_authority(START + 10, native=True)
