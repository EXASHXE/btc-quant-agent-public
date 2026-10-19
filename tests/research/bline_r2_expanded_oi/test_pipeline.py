"""Focused contract and boundary regressions; synthetic features only, no outcomes."""

from __future__ import annotations

import argparse
import json
import math

import pytest

from scripts.research.bline_r2_expanded_oi import pipeline as p
from scripts.research.bline_r2_expanded_oi.contracts import canonical, digest, freeze, registration

T = p.epoch_us("2024-01-02T12:01:00Z")
LABEL = T - 660 * p.US
POP = "C_EXPLORATORY_2021_2025"


def baseline(t=T):
    return {
        "t": t // p.US,
        "x_eligible": True,
        "log_return_4h": -0.02,
        "x_end_us": t - 61 * p.US,
        "x_source_ids": ["frozen-x"],
        "z": [-0.03, math.log(1.5)],
        "z_status": "OBSERVED",
    }


def native(label=LABEL, *, ratio=1.5, pred=True):
    states = {label: (95.0, 999999.0, 0.1, ratio, 2.0, 1.0)}
    if pred:
        states[label - 4 * p.HOUR] = (100.0, 1.0, 99.0, None, 2.0, 1.0)
    return {
        "states": states,
        "times": sorted(states),
        "conflicts": set(),
        "refs": {t: {"archive-a"} for t in states},
        "strings": {t: p.utc(t) for t in states},
    }


def test_exact_predecessor_no_nearby_or_forward_fill():
    n = native(pred=False)
    n["states"][LABEL - 4 * p.HOUR + 300 * p.US] = (100.0, 1.0, 2.0, 2.0, 2.0, 1.0)
    n["times"] = sorted(n["states"])
    r = p.origin_row(T, POP, baseline(), n, "registration")
    assert not r["trigger"] and not r["exact_4h_predecessor"]
    assert "EXACT_4H_PREDECESSOR_MISSING" in r["no_action_reasons"]


@pytest.mark.parametrize("offset", [-300, 300, 600, 900])
def test_source_content_guard_rejects_stale_recent_and_future(offset):
    r = p.origin_row(T, POP, baseline(), native(LABEL + offset * p.US), "registration")
    assert r["boundary_rejected"] and not r["paired_xz_eligible"] and not r["trigger"]


def test_valid_content_bounds_and_predecessor_clock():
    r = p.origin_row(T, POP, baseline(), native(), "registration")
    assert r["trigger"] and r["paired_xz_eligible"]
    assert r["selected_native_label_us"] == r["cutoff_us"] - 600 * p.US
    assert r["content_upper_us"] == r["cutoff_us"] - 300 * p.US
    assert r["selected_native_label_us"] - r["predecessor_label_us"] == 4 * p.HOUR
    assert r["predecessor_content_upper_us"] == r["cutoff_us"] - 4 * p.HOUR - 300 * p.US
    assert r["base_open_interest"] == 95 and r["sum_toptrader_long_short_ratio"] == 1.5
    assert r["no_action_reasons"] == [] and r["executable"] is False


def test_missing_position_ratio_keeps_oi_only_and_masks_both_actions():
    r = p.origin_row(T, POP, baseline(), native(ratio=None), "registration")
    assert r["oi_only_eligible"] and not r["z_eligible"]
    assert not r["paired_xz_eligible"] and r["paired_baseline_action"] == "NO_ACTION"
    assert not r["trigger"] and "NATIVE_TOP_POSITION_RATIO_MISSING" in r["no_action_reasons"]


@pytest.mark.parametrize("which", [LABEL, LABEL - 4 * p.HOUR])
def test_conflicting_labels_fail_closed_without_fallback(which):
    n = native()
    n["conflicts"].add(which)
    older = native(LABEL - 300 * p.US)
    n["states"].update(older["states"])
    n["times"] = sorted(n["states"])
    r = p.origin_row(T, POP, baseline(), n, "registration")
    assert not r["trigger"] and r["conflicting_label"]
    assert "CONFLICTING_NATIVE_LABEL" in r["no_action_reasons"]


def test_identical_duplicates_deduplicate_but_full_native_conflicts_persist():
    n = native()
    v = n["states"][LABEL]
    assert p.add_native(
        n["states"], n["refs"], n["strings"], n["conflicts"], LABEL, v, "archive-b", p.utc(LABEL)
    )
    assert len(n["states"]) == 2 and n["conflicts"] == set()
    assert p.origin_row(T, POP, baseline(), n, "reg")["trigger"]
    conflicting = (*v[:1], 42.0, *v[2:])  # Even an unused native field conflict is rejected.
    p.add_native(
        n["states"],
        n["refs"],
        n["strings"],
        n["conflicts"],
        LABEL,
        conflicting,
        "archive-c",
        p.utc(LABEL),
    )
    p.add_native(
        n["states"], n["refs"], n["strings"], n["conflicts"], LABEL, v, "archive-a", p.utc(LABEL)
    )
    assert LABEL in n["conflicts"]
    assert not p.origin_row(T, POP, baseline(), n, "reg")["trigger"]


def test_future_native_values_do_not_change_current_features_or_hash():
    n = native()
    before = canonical(p.origin_row(T, POP, baseline(), n, "reg"))
    for t in (T, T + p.HOUR, T + 24 * p.HOUR):
        n["states"][t] = (1e12, 1.0, 2.0, 100.0, 2.0, 1.0)
    n["times"] = sorted(n["states"])
    assert canonical(p.origin_row(T, POP, baseline(), n, "reg")) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("venue", "okx"),
        ("venue", "bybit"),
        ("symbol", "ETHUSDT"),
        ("product", "SPOT"),
        ("family", "fundingRate"),
        ("family", "spot_klines"),
        ("interval", "1h"),
        ("status", "DOWNLOADED_LOCAL_SHA_ONLY"),
    ],
)
def test_venue_contract_and_source_families_are_not_substitutable(field, value):
    rec = {
        "venue": "binance",
        "symbol": "BTCUSDT",
        "product": "USD_M_PERPETUAL",
        "family": "metrics",
        "interval": "5m",
        "status": "DOWNLOADED_VERIFIED",
    }
    assert p.eligible_source(rec)
    rec[field] = value
    assert not p.eligible_source(rec)


@pytest.mark.parametrize(
    "x,oi,ratio,expected",
    [
        (-0.01, -0.02, 1.5, True),
        (-0.009999, -0.02, 1.5, False),
        (-0.01, -0.019999, 1.5, False),
        (-0.01, -0.02, 1.499999, False),
        (0.01, -0.02, 1.5, False),
    ],
)
def test_exact_frozen_thresholds_and_direction(x, oi, ratio, expected):
    assert p.signal(x, oi, ratio) is expected


def r1_fixture(path, *, x_end=None, extra=None):
    row = {
        "t": T // p.US,
        "cutoff": T // p.US - 60,
        "venue": "binance",
        "asset": "BTC",
        "data_kind": "HISTORICAL_FEATURE_ONLY",
        "x_complete": True,
        "x_names": p.X_NAMES,
        "x": [0.0, -0.02] + [0.0] * (len(p.X_NAMES) - 2),
        "x_end_us": T - 61 * p.US if x_end is None else x_end,
        "source_ids": {"X": ["frozen-x"]},
        "z": [-0.03, math.log(1.5)],
        "z_status": "OBSERVED",
    }
    row.update(extra or {})
    path.write_bytes(canonical(row))


def test_frozen_R1_read_only_and_output_overlap_blocked(tmp_path):
    r1 = tmp_path / "r1"
    r1.mkdir()
    path = r1 / "feature_panel.jsonl"
    r1_fixture(path)
    before = digest(path)
    assert p.load_r1(path)[T]["x_eligible"]
    assert digest(path) == before
    for out in (r1, r1 / "new", tmp_path):
        with pytest.raises(ValueError, match="OUTPUT_INPUT_OVERLAP"):
            p.output_guard(out, [r1])
    assert digest(path) == before


def test_future_or_cutoff_X_content_is_ineligible(tmp_path):
    path = tmp_path / "features.jsonl"
    r1_fixture(path, x_end=T - 60 * p.US)
    rows = p.load_r1(path)
    assert not rows[T]["x_eligible"]
    assert not p.origin_row(T, POP, rows[T], native(), "reg")["trigger"]


@pytest.mark.parametrize("extra", [{"forward_return_8h": 0.1}, {"outcome": 1}])
def test_no_outcome_input_schema_fails_closed(tmp_path, extra):
    path = tmp_path / "features.jsonl"
    r1_fixture(path, extra=extra)
    with pytest.raises(ValueError, match="NO_OUTCOME_SCHEMA"):
        p.load_r1(path)


def test_no_outcome_output_schema_fails_closed():
    row = p.origin_row(T, POP, baseline(), native(), "reg")
    row["forward_return_8h"] = 0.1
    with pytest.raises(ValueError, match="NO_OUTCOME_PANEL_SCHEMA"):
        p.validate_panel_row(row)


def test_protected_2025_X_remains_ineligible():
    t = p.epoch_us("2025-03-01T12:01:00Z")
    r = p.origin_row(t, POP, baseline(t), native(t - 660 * p.US), "reg")
    assert r["protected_window"] and not r["paired_xz_eligible"] and not r["trigger"]
    assert r["base_open_interest"] is None
    assert "KNOWN_EXCLUDED_FEATURE_WINDOW" in r["no_action_reasons"]


def test_deterministic_registration_and_panel_hashes(tmp_path):
    reg = registration({"frozen": {"sha256": "a", "bytes": 1}})
    for name in ("one", "two"):
        (tmp_path / name).mkdir()
        freeze(tmp_path / name, reg)
    one = tmp_path / "one/exploratory_registration.v1.json"
    two = tmp_path / "two/exploratory_registration.v1.json"
    assert digest(one) == digest(two)
    assert freeze(tmp_path / "one", reg) == digest(one)
    with pytest.raises(ValueError, match="ALREADY_FROZEN"):
        freeze(tmp_path / "one", registration({"changed": True}))
    assert canonical(reg) == one.read_bytes()
    n = native()
    first = canonical(p.origin_row(T, POP, baseline(), n, digest(one)))
    n["states"] = dict(reversed(list(n["states"].items())))
    assert canonical(p.origin_row(T, POP, baseline(), n, digest(two))) == first


def test_registration_written_before_trigger_feature_read(tmp_path, monkeypatch):
    r1, r2, out = [tmp_path / x for x in ("r1", "r2", "out")]
    r1.mkdir()
    r2.mkdir()
    monkeypatch.setattr(p, "identities", lambda *args: (r2 / "reports", {}))

    def stop_at_first_feature_read(path):
        reg = json.loads((out / "exploratory_registration.v1.json").read_text())
        assert reg["no_outcome_scope"]["threshold_search_budget"] == 0
        assert (out / "registration_freeze_receipt.json").exists()
        raise RuntimeError("FEATURE_READ_AFTER_FROZEN_REGISTRATION")

    monkeypatch.setattr(p, "load_r1", stop_at_first_feature_read)
    args = argparse.Namespace(r1_root=r1, r2_root=r2, existing_r2_root=None, output_root=out)
    with pytest.raises(RuntimeError, match="FEATURE_READ_AFTER_FROZEN"):
        p.build(args)


def test_episode_nonoverlap_half_open_boundary_and_week_floor():
    times = [T, T + 7 * p.HOUR, T + 8 * p.HOUR, T + 9 * p.HOUR]
    rows = [{"origin_us": t, "trigger": True} for t in times]
    report = p.episodes(rows)
    m = report["horizons"]["8"]
    assert m["total_trigger_hours"] == 4 and m["nonoverlap_episode_count"] == 2
    assert m["cluster_sizes"] == [2, 2]
    assert not m["acted_origin_feasibility_floor_passed"]
    assert not m["conservative_episode_floor_passed"]
    assert "effective_sample_size" not in m


def test_verify_rejects_artifact_tampering_before_loading_inputs(tmp_path):
    artifact = tmp_path / "panel.jsonl"
    artifact.write_text("original\n")
    p.write_json(
        tmp_path / "manifest.json",
        {
            "artifacts": {
                "panel.jsonl": {"sha256": digest(artifact), "bytes": artifact.stat().st_size}
            }
        },
    )
    artifact.write_text("changed\n")
    with pytest.raises(ValueError, match="OUTPUT_SHA_MISMATCH"):
        p.verify(argparse.Namespace(output_root=tmp_path))
