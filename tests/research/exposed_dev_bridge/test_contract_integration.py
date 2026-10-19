"""Exercise the actual frozen P1 parser and economics with synthetic data only."""

import copy
import hashlib
import json
from dataclasses import replace

import pytest

from scripts.research.cross_venue import normalized_sources as n
from scripts.research.exposed_dev_bridge import outcome_adapter as oa
from scripts.research.exposed_dev_bridge import pipeline as cli
from scripts.research.exposed_dev_bridge.archive_adapter import matched_population
from scripts.research.exposed_dev_bridge.synthetic_contract import run_demo
from scripts.research.strategy_eval import HORIZONS, PLAN
from scripts.research.strategy_eval import clocked_dataset as data
from scripts.research.strategy_eval import pipeline as p1
from scripts.research.strategy_eval.costs import BASELINE, STRESS, Outcome, economics


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    output = tmp_path_factory.mktemp("r3-contract") / "demo"
    summary = run_demo(output)
    return output, summary


def load_fixture(output):
    return (json.loads((output / "normalized_panel.json").read_text()),
            json.loads((output / "p1_synthetic_allowlist.json").read_text()))


def test_demo_actual_p1_parser_costs_funding_and_denominators(demo):
    output, summary = demo
    rows, start, receipt = p1.authorized_panel(output / "normalized_panel.json", output / "p1_synthetic_allowlist.json")
    assert len(rows) == summary["origins_scheduled"] == 120
    assert summary["status"] == "P3_R3_E2E_DEV_READY"
    assert summary["access_status"] == "P3_ACCESS_SCOPE_HOLD"
    assert summary["full_fold_status"] == "FULL_FOLD_SYNTHETIC_NOT_RUN"
    assert all(d == 120 for d in summary["horizon_denominators"].values())
    assert summary["real_outcome_labels_read"] == summary["real_historical_outcomes_evaluated"] == 0
    assert any(isinstance(o, Outcome) and o.settlements for r in rows for o in r["outcomes"].values())
    assert all(data.ready(r) == (False, False) for r in rows[:25])
    for scenario in summary["economics"].values():
        for e in scenario.values():
            assert e["total_origins"] == e["resolved_trades"] + e["no_action_origins"] + e["unresolved_origins"]
            assert e["resolved_trades"] > 0 and e["unresolved_origins"] > 0
            assert e["sleeve_pnl_sum"] is None
    assert receipt["panel_sha256"] == hashlib.sha256((output / "normalized_panel.json").read_bytes()).hexdigest()
    assert PLAN["outer_development_days"] == [42, 56, 70]
    assert PLAN["outer_validation_days"] == 14 and PLAN["inner_validation_days"] == 7
    assert PLAN["purge_max_horizon_h"] == 24 and PLAN["embargo_s"] == 3600
    assert [BASELINE.nominal_round_trip_bp, STRESS.nominal_round_trip_bp] == [16, 32]


def test_missing_outcome_sparse_and_distinct_from_true_zero_return(demo):
    output, _ = demo
    rows, _, _ = p1.authorized_panel(output / "normalized_panel.json", output / "p1_synthetic_allowlist.json")
    assert any(not r["outcomes"] for r in rows)
    for r in rows:
        assert set(r["outcome_reasons"]) == {str(h) for h in HORIZONS}
        assert all((r["outcome_reasons"][str(h)] == "RESOLVED") == (str(h) in r["outcomes"]) for h in HORIZONS)
    zero = Outcome(1704067320, 1704067320 + 4 * 3600, 100, 100, (), (),
                   (1704067200 * n.US, (1704067320 + 4 * 3600) * n.US))
    assert zero.simple_return == 0
    assert economics(zero, 1, 4)["status"] == "RESOLVED"
    assert economics(zero, 1, 4)["gross_return"] == 0
    assert economics(None, 1, 4)["net_return"] is None
    assert economics(None, 1, 4)["status"] == "UTILITY_UNRESOLVED"
    assert economics(None, 0, 4)["status"] == "NO_ACTION"


@pytest.mark.parametrize("mutation,reason", [
    ("null", "OUTCOME_SCHEMA_INVALID"), ("sha", "EXPOSED_DEV_NOT_AUTHORIZED"),
    ("path", "EXPOSED_DEV_NOT_AUTHORIZED"), ("interval", "EXPOSED_DEV_NOT_AUTHORIZED"),
    ("entry", "OUTCOME_CLOCK_INVALID"), ("exit_boundary", "EXPOSURE_OUTCOME_OUTSIDE_ALLOWLIST"),
])
def test_actual_p1_parser_rejects_incompatible_or_unbound_panels(demo, tmp_path, mutation, reason):
    panel, fixture = load_fixture(demo[0])
    row = panel["rows"][30]
    if mutation == "null":
        row["outcomes"]["8"] = None
    elif mutation == "entry":
        row["outcomes"]["8"]["entry_t"] += 1
    elif mutation == "exit_boundary":
        last = panel["rows"][-1]
        last["outcomes"]["4"] = copy.deepcopy(row["outcomes"]["4"])
        last["outcomes"]["4"].update(entry_t=last["t"] + 60, exit_t=last["t"] + 60 + 4 * 3600)
    path = tmp_path / "panel.json"
    path.write_bytes(n.canonical_bytes(panel))
    fixture["panels"][0].update(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    if mutation == "sha":
        fixture["panels"][0]["sha256"] = "0" * 64
    elif mutation == "path":
        fixture["panels"][0]["path"] = str(tmp_path / "other.json")
    elif mutation == "interval":
        fixture["panels"][0]["end_utc_s"] += 3600
    allowlist = tmp_path / "fixture.json"
    allowlist.write_bytes(n.canonical_bytes(fixture))
    with pytest.raises(ValueError, match=reason):
        p1.authorized_panel(path, allowlist)


def test_features_exactly_reuse_p1_and_missing_spot_is_unavailable():
    start = 1704067200
    f = oa.generate_synthetic_fixture_data(start, 1)
    futures = [oa.as_p1_bar(f["perp_1m_bars"][t], "futures_um") for t in range(start - 86460, start, 60)]
    spot = [oa.as_p1_bar(f["spot_1m_bars"][t], "spot") for t in range(start - 86460, start, 60)]
    result = oa.extract_x_controls(f["perp_1m_bars"], f["spot_1m_bars"], start)
    assert result[0] == data.controls(futures, spot, start)[0]
    assert result[1] is True and result[2] == start * n.US - 1
    for bars in (None, {}, {t: b for t, b in f["spot_1m_bars"].items() if t != start - 60}):
        assert oa.extract_x_controls(f["perp_1m_bars"], bars, start)[0] is None
    wrong = {b.t: replace(b, market="spot") for b in futures}
    assert oa.extract_x_controls(wrong, f["spot_1m_bars"], start)[3] == "X_SOURCE_IDENTITY_INVALID"


@pytest.mark.parametrize("mutation,reason", [
    ("future", "Z_FUTURE_OR_TOO_RECENT"), ("stale", "Z_STALE"),
    ("predecessor", "Z_4H_PREDECESSOR_MISSING"), ("market", "Z_SOURCE_IDENTITY_INVALID"),
    ("contract", "Z_SOURCE_IDENTITY_INVALID"), ("interval", "Z_NATIVE_INTERVAL_INVALID"),
])
def test_native_z_never_uses_future_or_approximate_predecessor(mutation, reason):
    cutoff = 1704067200
    t = cutoff - (0 if mutation == "future" else 900 if mutation == "stale" else 300)
    sample = data.Stock(t, 1000, 1.2)
    if mutation == "market":
        sample = replace(sample, market="spot")
    if mutation == "contract":
        sample = replace(sample, symbol="ETHUSDT")
    if mutation == "interval":
        sample = replace(sample, interval_s=60)
    pred = t - (14700 if mutation == "predecessor" else 14400)
    stocks = {t: sample}
    if mutation != "future":
        stocks[pred] = data.Stock(pred, 900, 1.1)
    assert oa.extract_z_state(stocks, cutoff)["z_reason"] == reason


def test_matched_population_retains_no_action_and_missing_outcome_denominators(demo):
    output, _ = demo
    rows, _, _ = p1.authorized_panel(output / "normalized_panel.json", output / "p1_synthetic_allowlist.json")
    rows[30].update(z=None, z_status="UNAVAILABLE")
    assert data.ready(rows[30]) == (True, False)
    common = matched_population(rows)
    assert [r["t"] for r in common] == [r["t"] for r in rows]
    assert all(data.ready(r)[0] == data.ready(r)[1] for r in common)
    assert data.ready(common[30]) == (False, False)
    assert len({r["t"] for r in p1.purge(common, common[0]["t"] - 60, common[-1]["t"])}) <= len(common)


def test_h39_aug31_strict_origin_limit_and_no_price_lookup():
    boundary = n.utc_us("2026-08-31T00:00:00Z") // n.US
    assert oa.horizon_max_origin(24) == boundary - 3540
    assert oa.is_origin_mature(boundary - 3540, 24)
    class Forbidden(dict):
        def get(self, *args):
            pytest.fail("Protected outcome touched a price row")
    outcome, reason = oa.build_origin_outcome(boundary + 60, 24, Forbidden(), Forbidden(), Forbidden(), (0, 0))
    assert outcome is None and reason == "OUTCOME_MATURITY_BLOCKED_BY_EMBARGO"


def test_synthetic_demo_is_separate_cli_and_materialize_has_no_synthetic_flag(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(["materialize", "--scope", str(tmp_path / "unsigned.json"),
                  "--output-dir", str(tmp_path / "denied"), "--synthetic"])
    assert exc.value.code == 2 and not (tmp_path / "denied").exists()
    assert cli.main(["synthetic-contract-demo", "--hours", "48", "--output-dir", str(tmp_path / "demo")]) == 0
    receipt = json.loads((tmp_path / "demo/test_receipt.json").read_text())
    assert all(receipt["checks"].values())
    for name, sha in receipt["artifact_sha256"].items():
        assert hashlib.sha256((tmp_path / "demo" / name).read_bytes()).hexdigest() == sha


def test_synthetic_output_must_be_fresh_and_tmp(demo):
    with pytest.raises(n.BridgeError, match="OUTPUT_DIRECTORY_NOT_EMPTY"):
        run_demo(demo[0])
