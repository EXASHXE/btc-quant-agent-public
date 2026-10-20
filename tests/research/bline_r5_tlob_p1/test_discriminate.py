"""Focused falsification, strict clocks, masks, frozen identity and scope tests."""

from __future__ import annotations

import copy
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.research.bline_r5_tlob_p1 import discriminate as d


def row(t=1641002460, price=-0.02, cur=100.0, prev24=97.0, prev4=99.0, xok=True):
    label = (t - 660) * d.US
    zok = all(v is not None for v in (cur, prev24, prev4))
    a = math.log(cur / prev24) if zok else None
    b = math.log(cur / prev4) if zok else None
    x = xok and price <= -0.01
    z = zok and a >= 0.015 and b >= -0.005
    paired = xok and zok
    trigger = paired and x and z
    return {
        "t": t, "cutoff": t - 60, "cutoff_us": (t - 60) * d.US,
        "origin_utc": datetime.fromtimestamp(t, UTC).isoformat(),
        "expected_native_label_us": label, "content_upper_us": label + 300 * d.US,
        "pred_24h_label_us": label - 86400 * d.US,
        "pred_4h_label_us": label - 14400 * d.US, "archive_sha256": "a" * 64,
        "registration_sha256": d.REGISTRATION, "receiver_pit": "PIT_UNKNOWN",
        "source_status": "SOURCE_NOT_ADMITTED", "x_eligible": xok, "z_eligible": zok,
        "paired_xz_eligible": paired, "log_return_4h": price if xok else None,
        "base_open_interest": cur, "pred_24h_base_open_interest": prev24,
        "pred_4h_base_open_interest": prev4, "delta_log_oi_24h": a, "delta_log_oi_4h": b,
        "x_condition": x, "z_condition": z, "trigger": trigger,
        "action": "SHORT" if trigger else "NO_ACTION",
        "paired_baseline_action": "SHORT" if paired and x else "NO_ACTION",
        "no_action_reasons": [],
    }


@pytest.mark.parametrize("t", [d.START - 3540, d.END + 60, 1775019660, d.START * d.US])
def test_scope_rejects_outside_years_and_wrong_units(t):
    r = row()
    r["t"] = t
    with pytest.raises(ValueError, match="BOUNDED_ORIGIN"):
        d.validate_row(r)


def test_no_nonmissing_predecessor_values_outside_native_scope():
    with pytest.raises(ValueError, match="BOUNDED_NATIVE_VALUE"):
        d.validate_row(row(t=d.START + d.HOUR + 60))


@pytest.mark.parametrize("key,value,error", [
    ("pred_4h_label_us", 0, "PREDECESSOR_4H"),
    ("content_upper_us", 0, "OI_CONTENT_CLOCK"),
    ("registration_sha256", "wrong", "ROW_FREEZE_IDENTITY"),
    ("action", "NO_ACTION", "TLOB_ACTION"),
    ("base_open_interest", -1, "INVALID_OI"),
    ("base_open_interest", float("nan"), "INVALID_OI"),
])
def test_causal_and_freeze_tampering(key, value, error):
    r = row()
    r[key] = value
    with pytest.raises(ValueError, match=error):
        d.validate_row(r)


@pytest.mark.parametrize("field", ["outcomes", "forward_return", "realized_pnl", "fill_price", "decisions"])
def test_only_exact_feature_schema(field):
    r = row()
    r[field] = None
    with pytest.raises(ValueError, match="FEATURE_SCHEMA_ONLY"):
        d.validate_row(r)


def test_original_thresholds_and_negative_current_oi_change():
    # Original thresholds, including permitted small 4h contraction; no new proxy.
    for price, prev24, prev4, expected in [
        (-0.01, 97, 100.4, True), (-0.009999, 97, 99, False),
        (-0.02, 99, 99, False), (-0.02, 97, 101, False),
        (-0.02, 100.1, 99, False),
    ]:
        r = row(price=price, prev24=prev24, prev4=prev4)
        d.validate_row(r)
        assert r["trigger"] is expected


def test_matched_denominator_excludes_missing_and_preserves_negatives():
    rows = [row(), row(t=1641006060, prev24=None), row(t=1641009660, price=-0.001),
            row(t=1641013260, xok=False), row(t=1641016860, prev24=99)]
    evidence = d.analyze(rows)
    p = evidence["population"]
    assert (p["scheduled"], p["matched"], p["missing_X_only"], p["missing_Z_only"]) == (5, 3, 1, 1)
    assert (p["x_events_before_z_mask"], p["x_events"], p["x_events_excluded_by_z_mask"]) == (3, 2, 1)
    assert evidence["event_hours"]["both"] == 1
    assert evidence["event_hours"]["x_only"] == 1
    assert evidence["event_hours"]["neither"] == 1
    assert sum(evidence["original_threshold_categories"].values()) == 3
    assert evidence["P1"]["actions"] is None
    assert p["three_way_matched_denominator"] is None
    assert evidence["P1"]["status"] == "COMPARATOR_UNAVAILABLE"
    assert not evidence["r5_full_acceptance"]


def test_duplicate_origins_are_rejected():
    r = row()
    with pytest.raises(ValueError, match="DUPLICATE_ORIGIN"):
        d.analyze([r, copy.deepcopy(r)])


@pytest.mark.parametrize("r,matched", [(row(prev24=None, xok=False), 0), (row(prev24=101), 1)])
def test_fully_missing_or_negative_population_never_fabricates_support(r, matched):
    e = d.analyze([r])
    assert e["population"]["matched"] == matched
    assert e["population"]["tlob_events"] == 0
    assert e["population"]["tlob_episodes_8h"] == 0
    assert e["concentration"]["max_event_year_share"] is None
    assert e["concentration"]["max_episode_start_year_share"] is None
    assert e["P1"]["actions"] is None


def test_calendar_exact_starts_differ_from_interval_overlap():
    t = 1641002460
    rows = [row(t=t, prev24=99), row(t=t + d.HOUR), row(t=t + 8 * d.HOUR)]
    result = d.analyze(rows)
    assert d.episodes([t, t + d.HOUR, t + 8 * d.HOUR]) == [t, t + 8 * d.HOUR]
    assert d.episodes([t + d.HOUR, t + 8 * d.HOUR]) == [t + d.HOUR]
    ep = result["episode_calendar"]
    assert ep["exact_starts"]["both"] == 0
    assert ep["exact_starts"]["tlob_only"] == 1
    assert ep["overlapping_interval_pairs"] == 2
    assert ep["tlob_episodes_overlapping_x"] == 1
    assert ep["covered_hour_slots"]["both"] == 8
    assert result["event_hours"]["tlob_only"] == 0


def test_changed_manifest_is_rejected_before_panel_access(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"outputs": {}}))
    with pytest.raises(ValueError, match="R4_MANIFEST_IDENTITY"):
        d.load_panel(tmp_path)


@pytest.fixture(scope="module")
def frozen_run():
    root = Path(os.environ["BLINE_R4_ROOT"])
    before = d.frozen_hashes(root)
    rows = d.load_panel(root)
    evidence = d.analyze(rows)
    yield root, rows, evidence
    assert d.frozen_hashes(root) == before


def test_actual_frozen_identity_scope_and_decisions(frozen_run):
    root, rows, e = frozen_run
    assert len(d.frozen_hashes(root)) == 15  # fourteen artifacts plus manifest
    assert len(rows) == len({r["t"] for r in rows}) == 35063
    assert all(d.START <= r["t"] < d.END for r in rows)
    assert (e["population"]["matched"], e["population"]["x_events"],
            e["population"]["tlob_events"]) == (34821, 4651, 1265)
    assert e["population"]["x_events_excluded_by_z_mask"] == 46
    assert e["event_hours"]["tlob_only"] == 0
    assert e["population"]["tlob_episodes_8h"] == 515
    assert e["episode_calendar"]["tlob_episode_start_iso_weeks"] == 168
    assert e["yearly"]["2023"]["tlob_episodes_8h"] == 49
    assert e["negative_OI"]["tlob_with_4h_negative"] > 0
    assert all(v is None for v in (e["P1"]["scores"], e["P1"]["eligible_origins"]))
    assert set(e["labels"]) == set(d.LABELS)
