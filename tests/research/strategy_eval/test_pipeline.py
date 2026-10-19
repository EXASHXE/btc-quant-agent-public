import csv
import hashlib
import io
import json
import socket
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from scripts.research.strategy_eval import DAY, HORIZONS, LABELS, PLAN
from scripts.research.strategy_eval import clocked_dataset as d
from scripts.research.strategy_eval import pipeline as p
from scripts.research.strategy_eval.costs import BASELINE, US, Outcome


def normalized_fixture(days=84):
    rng = np.random.default_rng(650410)
    rows = []
    for i in range(days * 24):
        t = i * 3600 + 60
        x = rng.normal(size=10).tolist()
        z = [0.01 + i / 100000, float(np.sin(i))]
        r = 0.002 * x[0] - 0.005 * z[0] * z[1]
        labels = {str(h): Outcome(t + 60, t + 60 + h * 3600, 100,
                                 100 * (1 + r * h / 8), (), (),
                                 ((t + 60) * US, (t + 60 + h * 3600) * US)) for h in HORIZONS}
        rows.append({"t": t, "cutoff": t - 60, "entry_t": t + 60,
                     "x": x, "x_complete": True, "x_end_us": (t - 60) * US - 1000,
                     "x_reason": "READY", "z": z, "z_t": t - 360,
                     "z_4h_exact": True, "z_status": "OBSERVED", "z_reason": "READY",
                     "raw_z_present": True, "outcomes": labels})
    return rows


@pytest.fixture(scope="module")
def rows():
    return normalized_fixture()


@pytest.fixture(scope="module")
def evaluation(rows):
    return p.evaluate(rows, 0)


def test_paired_train_populations_purge_and_max_horizon_embargo(rows):
    boundary = 42 * DAY
    altered = deepcopy(rows)
    altered[100]["z"] = None
    train = p.purge(altered, 0, boundary)
    assert altered[100] not in train
    assert all(r["t"] + 60 + DAY < boundary - 3600 for r in train)
    assert len(train) == len(p.purge(rows, 0, boundary)) - 1
    models = [p.fit(train, 8, 1, full) for full in (False, True)]
    assert models[0].train_times_sha256 == models[1].train_times_sha256
    assert models[1].beta[-1] <= 0
    equality_origin = boundary - 3600 - DAY - 60
    assert all(r["t"] != equality_origin for r in train)


def test_inner_blocks_expanding_and_no_label_ends_after_development(rows):
    splits = p.inner_splits(rows, 0, 42 * DAY)
    assert len(splits) == 3
    assert [v[0]["t"] for _, v in splits] == [d * DAY + 60 for d in (21, 28, 35)]
    assert all(len(a[0]) < len(b[0]) for a, b in zip(splits, splits[1:]))
    for train, val in splits:
        v0 = val[0]["t"] - 60
        assert all(r["t"] + 60 + DAY < v0 - 3600 for r in train)
        assert all(r["t"] + 60 + DAY < 42 * DAY for r in val)


def test_future_outcome_and_feature_mutation_cannot_change_tuning_or_fit(rows):
    original = deepcopy(rows)
    changed = deepcopy(rows)
    for r in changed[42 * 24:]:
        r["x"] = [1e8] * 10
        r["z"] = [10, 1e8]
        r["outcomes"] = {k: replace(v, exit_price=1e9) for k, v in r["outcomes"].items()}
    for full in (False, True):
        a = p.tune(original, 0, 42 * DAY, 8, full)
        b = p.tune(changed, 0, 42 * DAY, 8, full)
        assert a == b
        before = p.fit(p.purge(original, 0, 42 * DAY), 8, a[0], full)
        after = p.fit(p.purge(changed, 0, 42 * DAY), 8, b[0], full)
        np.testing.assert_array_equal(before.beta, after.beta)
        np.testing.assert_array_equal(before.mean, after.mean)
        assert before.center == after.center


def test_fit_only_centering_and_positive_score_constrained_to_zero(rows):
    train = deepcopy(rows[:200])
    center = float(np.mean([r["z"][1] for r in train]))
    for r in train:
        r["x"] = [0.0] * 10
        score = (r["z"][1] - center) * max(r["z"][0], 0)
        r["outcomes"] = {k: replace(v, exit_price=100 * (1 + 10 * score)) for k, v in r["outcomes"].items()}
    model = p.fit(train, 8, 1, True)
    assert model.beta[-1] == 0
    assert model.center == center
    assert p.predict(model, [train[0]])[0] == pytest.approx(p.predict(model, [train[-1]])[0])


def test_lambda_tie_break_is_smaller_and_selection_deterministic(rows):
    flat = deepcopy(rows[:42 * 24])
    for row in flat:
        row["outcomes"] = {k: replace(v, exit_price=100) for k, v in row["outcomes"].items()}
    assert p.tune(flat, 0, 42 * DAY, 8, True)[0] == 0.1
    assert p.tune(rows, 0, 42 * DAY, 8, True) == p.tune(rows, 0, 42 * DAY, 8, True)


@pytest.mark.parametrize("age", [300, 600])
def test_claimed_projection_clock_includes_both_native_stock_guard_endpoints(age):
    row = normalized_fixture(1)[0]
    row["t"] += 2 * DAY
    row["x_end_us"] += 2 * DAY * US
    row["z_t"] = row["t"] - 60 - age
    assert d.ready(row) == (True, True)
    verdict = p.claimed_clock(row)
    assert verdict["status"] == "CLAIMED_TIMING_ELIGIBLE"
    assert verdict["receiver_pit"] == "PIT_UNKNOWN"


def test_malformed_outcome_clock_cannot_enter_model_training():
    row = normalized_fixture(1)[0]
    row["outcomes"]["8"] = replace(row["outcomes"]["8"], entry_t=float(row["t"] + 60))
    assert p.label_return(row, 8) is None
    assert not p.purge([row], 0, 42 * DAY)


def test_frozen_folds_and_identical_eligible_prediction_loss_population(evaluation):
    assert evaluation["status"] == "EVALUATED_OFFLINE"
    assert len(evaluation["cells"]) == 48
    assert [f["development_end_day"] for f in evaluation["folds"]] == [42, 56, 70]
    for fold in evaluation["folds"]:
        assert fold["scheduled"] == 336
        for h in HORIZONS:
            models = [m for m in fold["models"] if m["h"] == h]
            assert len({m["train_times_sha256"] for m in models}) == 1
            assert len({m["prediction_mse_denominator"] for m in models}) == 1
            assert all(m["lambda"] in (0.1, 1, 10) for m in models)
        assert all(m["score_coefficient"] is None or m["score_coefficient"] <= 0 for m in fold["models"])


def test_missingness_ablation_is_diagnostic_and_loss_comparison_is_paired(evaluation):
    reports = p.paired_diagnostics(evaluation)
    assert len(reports) == 8  # Four frozen horizons, two mandatory cost sensitivities.
    assert all(not r["missingness_diagnostic_is_claim_slot"] for r in reports)
    assert reports[0]["primary"] and reports[0]["h"] == 8
    for report in reports:
        assert report["all_origins_denominator"] == report["common_Z_denominator"] == 42 * 24
        # With no missing Z, the ablation exactly equals the X policy.
        cells = [c for c in evaluation["cells"] if c["h"] == report["h"] and c["arm"] == "X"
                 and c["scenario"] == report["scenario"]]
        expected = sum(p["sleeve_pnl"] for c in cells for p in c["points"]) / (42 * 24)
        assert report["missingness_only_X_abstention_diagnostic_mean"] == pytest.approx(expected)
        assert report["alpha"] == "NO_ALPHA_ESTABLISHED"


def test_missing_Z_abstains_but_X_acts_and_all_origins_remain(rows):
    changed = deepcopy(rows)
    val = changed[42 * 24:56 * 24]
    for row in val:
        row.update(z=None, z_status="UNAVAILABLE", z_reason="MISSING_Z", raw_z_present=False)
    answer = p.evaluate(changed, 0)
    cells = [c for c in answer["cells"] if c["fold_day"] == 42 and c["h"] == 8]
    for cell in cells:
        assert cell["scheduled"] == len(cell["points"]) == 336
        if cell["arm"] == "XZ":
            assert cell["no_action"] == 336 and cell["aggregate_matured_sleeve_pnl"] == 0
            assert cell["reason_counts"] == {"MISSING_Z": 336}
        else:
            assert cell["acted_on"] > 0
    assert answer["origins_dropped"] == 0


def test_short_panel_is_insufficient_and_missing_grid_row_is_rejected():
    rows = normalized_fixture(31)
    result = p.evaluate(rows, 0)
    assert result["status"] == "INSUFFICIENT_HISTORY" and not result["records"]
    assert len(result["inference"]) == 8
    del rows[30]
    with pytest.raises(ValueError, match="GRID_ROWS_MUST_INCLUDE_UNAVAILABLE_ORIGINS"):
        p.evaluate(rows, 0)


def test_net_win_rate_origin_denominator_unresolved_and_tail():
    row = normalized_fixture(1)[0]
    row["outcomes"]["8"] = replace(row["outcomes"]["8"], exit_price=101)
    win = p._decision(row, 8, "X", BASELINE, 0.01, "", 42)
    loss = p._decision(row, 8, "X", BASELINE, -0.01, "", 42)
    no_action = p._decision(row, 8, "X", BASELINE, 0.0, "", 42)
    missing = deepcopy(row)
    missing["outcomes"]["8"] = replace(row["outcomes"]["8"], expected_settlements_us=None)
    unresolved = p._decision(missing, 8, "X", BASELINE, 0.01, "", 42)
    stats = p.cell_metrics([win, loss, no_action, unresolved], 8)
    assert stats["scheduled"] == 4 and stats["acted_on"] == 3
    assert stats["resolved_acted_on"] == stats["net_win_rate_denominator"] == 2
    assert stats["unresolved_acted_on"] == 1 and stats["net_win_rate"] == 0.5
    assert stats["aggregate_matured_sleeve_pnl"] is None
    assert stats["mean_net_utility_per_scheduled_origin"] is None
    assert stats["worst_net_trade_return"] < 0
    assert stats["mean_gain"] > 0 and stats["mean_loss"] < 0
    assert stats["path_drawdown"] is None


@pytest.mark.parametrize("h", HORIZONS)
def test_overlap_uses_at_most_H_fixed_sleeves_and_releases_at_exit(h):
    points = [{"action": 1, "entry_t": i * 3600 + 120,
               "exit_t": (i + h) * 3600 + 120} for i in range(100)]
    capital = p.capital_overlap(points, h)
    assert capital["max_simultaneous_positions"] == h
    assert capital["max_allocated_capital"] == 1
    assert not capital["reinvestment"]
    with pytest.raises(ValueError, match="CAPITAL_OVERLAP"):
        p.capital_overlap(points + [points[h]], h)


def test_paired_block_inference_null_budget_seed_and_pilot_support(evaluation):
    cells = []
    for h in HORIZONS:
        for arm in ("X", "XZ"):
            cells.append({"h": h, "arm": arm, "scenario": BASELINE.name,
                          "points": [{"t": i * 3600 + 60, "sleeve_pnl": 0.0, "z_eligible": True}
                                     for i in range(42 * 24)]})
    answer = p.paired_inference(cells, reps=99)
    assert answer == p.paired_inference(cells, reps=99)
    assert len(answer) == PLAN["claim_slots"] == 8
    assert all(c["p"] == c["holm_p_8_slots"] == 1 for c in answer)
    assert all(c["all_origins"]["bonferroni_simultaneous_CI"] == [0, 0]
               and not c["power_sufficient"] and c["week_blocks"] == 6 for c in answer[:4])
    assert all(c["status"] == "RESERVED_NOT_ENABLED" for c in answer[4:])
    assert all(not c["power_sufficient"] for c in evaluation["inference"][:4])
    cells[1]["points"].pop()
    with pytest.raises(ValueError, match="UNPAIRED_ORIGINS"):
        p.paired_inference(cells, reps=5)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("p1-demo")
    with patch.object(socket, "socket", side_effect=AssertionError("network")), \
         patch.object(socket, "create_connection", side_effect=AssertionError("network")):
        summary = p.run_demo(root)
    return root, summary


def test_demo_computes_actual_synthetic_PnL_and_serializes_required_reports(demo):
    root, summary = demo
    assert set(x.name for x in root.iterdir()) == set(p.OUTPUT_FILES)
    assert summary["feature_origins"] == 2016 and summary["origin_horizon_rows"] == 8064
    assert summary["trades_csv_rows"] > 0 and summary["cells"] == 48
    metrics = json.loads((root / "metrics.json").read_text())
    assert metrics["mode"] == "DEV_SYNTHETIC_ONLY"
    assert metrics["coverage"]["origins_dropped"] == 0
    assert set(LABELS).issubset(metrics["labels"])
    assert metrics["claim_slots"] == 8 and not metrics["confirmatory"]
    assert len(metrics["validation_aggregates"]) == 16
    assert {a["h"] for a in metrics["always_no_action_baseline"]} == set(HORIZONS)
    assert all(a["scheduled"] == 2016 and a["no_action"] == 2016
               and a["acted_on"] == 0 and a["aggregate_matured_sleeve_pnl"] == 0
               and a["claim_slot"] is False for a in metrics["always_no_action_baseline"])
    assert all(a["capital"]["max_allocated_capital"] <= 1 for a in metrics["validation_aggregates"])
    with (root / "trades.csv").open() as stream:
        trade = next(csv.DictReader(stream))
    action, horizon = int(trade["action"]), int(trade["h"])
    gross = action * (float(trade["exit_price"]) / float(trade["entry_price"]) - 1)
    assert float(trade["gross_return"]) == pytest.approx(gross)
    assert float(trade["net_return"]) == pytest.approx(gross - float(trade["total_cost"]) - float(trade["funding_debit"]))
    assert float(trade["sleeve_pnl"]) == pytest.approx(float(trade["net_return"]) / horizon)
    events = json.loads(trade["funding_settlements_json"])
    assert [s["t_us"] for s in events] == sorted(s["t_us"] for s in events)
    receipt = json.loads((root / "test_receipt.json").read_text())
    assert receipt["scope"] == "BUILTIN_CONTRACT_CHECKS_NOT_A_PYTEST_RECEIPT"
    for name, digest in receipt["artifact_sha256"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
    with (root / "origins.jsonl").open() as stream:
        rows = [json.loads(next(stream)) for _ in range(4)]
    assert [r["h"] for r in rows] == [8, 4, 12, 24]
    assert all(r["decisions"]["NO_ACTION"]["action"] == 0
               and r["decisions"]["NO_ACTION"]["sleeve_pnl"] == 0
               and r["decisions"]["NO_ACTION"]["claim_slot"] is False for r in rows)
    assert all(r["decisions"]["XZ"][BASELINE.name]["action"] == 0 for r in rows)


def test_demo_cli_reproducible_bytes_and_claimed_clock_reuse(tmp_path, demo):
    root, _ = demo
    out = tmp_path / "repeat"
    stdout = io.StringIO()
    from scripts.research.r11_d2 import prospective_causal_clock as clock
    with redirect_stdout(stdout), patch.object(clock, "evaluate_fixed_origin", wraps=clock.evaluate_fixed_origin) as check:
        assert p.main(["demo", "--output-dir", str(out)]) == 0
    assert check.call_count == 2016
    assert json.loads(stdout.getvalue())["mode"] == "DEV_SYNTHETIC_ONLY"
    assert {f.name: d.digest_file(f) for f in root.iterdir()} == {f.name: d.digest_file(f) for f in out.iterdir()}
    # Full native warmup is unavailable; the first ready projection is still only a caller claim.
    with (out / "origins.jsonl").open() as stream:
        ready = next(json.loads(line) for line in stream if 'CLAIMED_TIMING_ELIGIBLE' in line)
    assert ready["clock_verdict"]["receiver_pit"] == "PIT_UNKNOWN"
    assert ready["clock_verdict"]["R3_sources"].startswith("DERIVED_FEATURE_PROJECTIONS")


def test_historical_outcome_gate_precedes_any_panel_or_output_access(tmp_path):
    input_path = tmp_path / "does-not-exist.json"
    output = tmp_path / "output"
    with patch.object(d, "read_json", side_effect=AssertionError("unauthorized read")):
        with pytest.raises(ValueError, match="EXPOSED_DEV_NOT_AUTHORIZED"):
            p.evaluate_historical(input_path, None, output)
    assert not output.exists()
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        code = p.main(["evaluate-historical", "--input", str(input_path), "--output-dir", str(output)])
    assert code == 2 and json.loads(stderr.getvalue())["reason"] == "EXPOSED_DEV_NOT_AUTHORIZED"


def normalized_panel(tmp_path):
    path = tmp_path / "panel.json"
    rows = normalized_fixture(2)
    for row in rows:
        row.update(x=None, x_complete=False, x_reason="WARMUP_X_24H")
        row["outcomes"] = {}  # A short panel can authorize coverage without future labels.
    path.write_text(json.dumps({"schema": "strategy_eval.normalized.v1", "label": "HISTORICAL_OFFLINE / PIT_UNKNOWN",
                                "exposure": "EXPOSED_DEV", "start_utc_s": 0, "rows": rows}))
    entry = {"path": str(path), "sha256": d.digest_file(path), "start_utc_s": 0, "end_utc_s": 2 * DAY}
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"schema": "strategy_eval.exposed-dev.v1", "exposure": "EXPOSED_DEV", "panels": [entry]}))
    return path, allowlist


def test_historical_allowlist_is_hash_path_window_bound_and_stays_insufficient(tmp_path):
    path, allowlist = normalized_panel(tmp_path)
    rows, start, authorization = p.authorized_panel(path, allowlist)
    assert start == 0 and len(rows) == 48 and authorization["exposure"] == "EXPOSED_DEV"
    assert p.evaluate(rows, start)["status"] == "INSUFFICIENT_HISTORY"
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="EXPOSED_DEV_NOT_AUTHORIZED"):
        p.authorized_panel(path, allowlist)


@pytest.mark.parametrize("field,value", [("exposure", "PROTECTED"), ("schema", "1.0")])
def test_labels_alone_cannot_authorize_historical_outcomes(tmp_path, field, value):
    path, allowlist = normalized_panel(tmp_path)
    doc = json.loads(allowlist.read_text())
    doc[field] = value
    allowlist.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="EXPOSED_DEV_NOT_AUTHORIZED"):
        p.authorized_panel(path, allowlist)


def test_allowlist_cannot_extend_feature_or_outcome_windows(tmp_path):
    path, allowlist = normalized_panel(tmp_path)
    doc = json.loads(path.read_text())
    doc["rows"][0].update(x=[0] * 10, x_complete=True)
    path.write_text(json.dumps(doc))
    permit = json.loads(allowlist.read_text())
    permit["panels"][0]["sha256"] = d.digest_file(path)
    allowlist.write_text(json.dumps(permit))
    with pytest.raises(ValueError, match="EXPOSURE_FEATURE_WINDOW_OUTSIDE_ALLOWLIST"):
        p.authorized_panel(path, allowlist)


def test_unsafe_output_cli_leaves_owner_file_unchanged(tmp_path):
    marker = tmp_path / "owner.py"
    marker.write_text("dirty owner file\n")
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        assert p.main(["demo", "--output-dir", str(tmp_path)]) == 2
    assert marker.read_text() == "dirty owner file\n"
