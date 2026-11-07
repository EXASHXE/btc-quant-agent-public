from dataclasses import replace
import json

import pytest

from btc_quant_agent.platform.core import fingerprint
from btc_quant_agent.platform.rc_dashboard import snapshot, validate, write_snapshot
from btc_quant_agent.platform.rc_fixture import DECISION, future_fixture, wire
from btc_quant_agent.platform.rc_observe import observe
from btc_quant_agent.platform.rc_source import normalize
from btc_quant_agent.platform.swing import INTERVALS
from btc_quant_agent.platform.ui import page


@pytest.mark.parametrize("scenario,expected", [("target", "TARGET_FIRST"), ("stop", "STOP_FIRST"),
    ("ambiguous", "AMBIGUOUS_OHLC_ORDER_UNKNOWN"), ("entry_ambiguous", "AMBIGUOUS_OHLC_ORDER_UNKNOWN"),
    ("no_fill", "NO_FILL"), ("missed", "MISSED_ENTRY"), ("time", "TIME_STOP")])
def test_later_paths_classify_without_assuming_fills_or_profits(scenario, expected, positive):
    result = observe(positive, future_fixture(positive, scenario=scenario),
                     asof_ms=DECISION + 50 * INTERVALS["1H"])
    assert result.outcome == expected
    assert not result.actual_fill and not result.execution_inferred and not result.economic_evidence


@pytest.mark.parametrize("censored,expected", [(False, "INSUFFICIENT_FUTURE_HORIZON"), (True, "RIGHT_CENSORED")])
def test_short_future_is_never_a_loss_or_success(censored, expected, positive):
    result = observe(positive, future_fixture(positive, scenario="time", hours=4),
                     asof_ms=DECISION + 4 * INTERVALS["1H"], right_censored=censored)
    assert result.outcome == expected


def test_gap_and_future_observation_are_honest_unknown(positive):
    rows = list(future_fixture(positive))
    del rows[3]
    assert observe(positive, rows, asof_ms=DECISION + 50 * INTERVALS["1H"]).outcome == "MISSING_COVERAGE"
    early = observe(positive, rows, asof_ms=DECISION)
    assert early.outcome == "INSUFFICIENT_FUTURE_HORIZON" and not early.future_receipt_ids


def test_durable_observation_is_separate_deduplicated_and_replay_cannot_reset_it(stored, positive):
    future = future_fixture(positive)
    stored.admit(future)
    item = observe(positive, stored.receipts(), asof_ms=DECISION + 50 * INTERVALS["1H"]).model_dump(mode="json")
    digest = stored.record_observation(item)
    assert stored.record_observation(item) == digest
    assert stored.commit(positive)
    assert len(stored.observations()) == 1 and stored.decisions() == (positive,)
    altered = dict(item, outcome="STOP_FIRST")
    with pytest.raises(ValueError, match="DURABLE_SYNTHETIC_PATH"):
        stored.record_observation(altered)


def test_existing_html_and_snapshot_publisher_watermark_and_escape(stored, positive, tmp_path):
    value = snapshot(stored, now_ms=DECISION)
    write_snapshot(tmp_path / "view", value)
    html = (tmp_path / "view/latest.html").read_text()
    assert "SYNTHETIC" in html and "NATIVE_UNQUALIFIED" in html
    assert "NATIVE_QUALIFIED FALSE" in html and "ARMED" in html and "ACCOUNT UNKNOWN / VETO" in html
    assert "Entry zone" in html and "Structural stop" in html and "Fixed targets" in html
    assert "fetch(" not in html and "<script" not in html and "<button" not in html
    malicious = json.loads(json.dumps(value))
    malicious["decisions"][0]["reasons"] = ["<script>evil()</script>"]
    malicious["episodes"][0]["anchors"]["decision"] = malicious["decisions"][0]
    malicious["snapshot_sha256"] = fingerprint({k: v for k, v in malicious.items() if k != "snapshot_sha256"})
    escaped = page(malicious, now_ms=DECISION)
    assert "<script>" not in escaped and "&lt;script&gt;" in escaped


def test_snapshot_schema_blocks_promotion_and_legacy_view_never_activates(stored, positive):
    value = snapshot(stored, now_ms=DECISION)
    value["source_qualified"] = True
    with pytest.raises(ValueError, match="AUTHORITY"):
        validate(value)
    legacy = page(positive.model_dump(mode="json"), now_ms=DECISION)
    assert "HISTORICAL_FROZEN" in legacy and "NOT_ACTIONABLE" in legacy
    assert "LEGACY_STATE_IS_NOT_A_NEW_SWING_ACTIVATION" in legacy


def test_observation_future_revision_cannot_rewrite_past_observation(positive):
    future = future_fixture(positive)
    cutoff = DECISION + 10 * INTERVALS["1H"]
    past = observe(positive, future, asof_ms=cutoff)
    c = future[2].bar.candle
    revised = normalize(wire(replace(c, high=c.high * 2), revision=1, at_ms=cutoff + 1000))
    assert observe(positive, [*future, revised], asof_ms=cutoff) == past
    corrected = observe(positive, [*future, revised], asof_ms=cutoff + 2000)
    assert corrected.outcome == "MISSING_COVERAGE"
