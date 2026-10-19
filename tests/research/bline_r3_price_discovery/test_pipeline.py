"""Offline positive and negative boundaries; synthetic prices are never outcomes."""

from __future__ import annotations

import copy
import math
from dataclasses import replace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.research.bline_r3_price_discovery import adapter as a
from scripts.research.bline_r3_price_discovery import contracts as c
from scripts.research.bline_r3_price_discovery import pipeline as p


def price_paths():
    spot = [0, -0.0011] + [-0.0014] * 14
    perp = [0, 0, -0.0004] + [-0.00105] * 13
    return [100 * math.exp(v) for v in spot], [100 * math.exp(v) for v in perp]


def channels():
    origin = c.us("2023-04-03T12:01:00Z")
    cutoff = origin - c.MINUTE
    spot, perp = price_paths()
    out = []
    for product, prices in zip(["spot", "perp"], [spot, perp]):
        bars = {}
        for j, close in enumerate(prices):
            end = cutoff - (16 - j) * c.MINUTE
            bars[end] = a.Bar(end - c.MINUTE, end, close, (close,), product, product + "_sha")
        out.append(bars)
    refs = [{t: {(b.source_id, b.raw_sha256)} for t, b in bars.items()} for bars in out]
    return origin, out, [set(), set()], refs


def xrow(origin, value=-0.02):
    return {
        "x_eligible": True,
        "log_return_4h": value,
        "x_end_us": origin - 2 * c.MINUTE,
        "x_source_ids": ["frozen_X"],
    }


def test_positive_complete_causal_sequence_and_same_paired_baseline():
    t, bars, conflicts, refs = channels()
    r = p.panel_row(t, xrow(t), bars, conflicts, refs, "frozen")
    assert r["paired_eligible"] and r["baseline_action"] == r["candidate_action"] == -1
    assert r["features"]["first_spot_cross_index"] == 1
    assert r["features"]["first_perp_cross_index"] == 3
    assert r["first_interval_open_us"] == r["cutoff_us"] - 17 * c.MINUTE
    assert r["last_interval_end_us"] == r["cutoff_us"] - c.MINUTE
    assert not r["executable"] and r["receiver_pit"] == "PIT_UNKNOWN"
    assert r["primary_no_action_reason"] is None


def test_novel_order_observable_holds_X_and_terminal_basis_fixed():
    spot, perp = price_paths()
    valid, _ = a.displacement(spot, perp)
    # Earlier perpetual crossing, unchanged final spot/perpetual basis and X.
    reordered = list(perp)
    reordered[1], reordered[3] = reordered[3], reordered[1]
    alternate, reasons = a.displacement(spot, reordered)
    assert valid["Z_condition"] and not alternate["Z_condition"]
    assert spot[-1] / perp[-1] == spot[-1] / reordered[-1]
    assert "SPOT_FIRST_ORDER_NOT_OBSERVED" in reasons
    # Constant rescaling changes static basis but leaves incremental Z unchanged.
    rescaled, _ = a.displacement([v * 1.01 for v in spot], perp)
    assert rescaled["Z_condition"] == valid["Z_condition"]


@pytest.mark.parametrize("market", [0, 1])
def test_missing_either_market_masks_both_policies(market):
    t, bars, bad, refs = channels()
    del bars[market][min(bars[market])]
    r = p.panel_row(t, xrow(t), bars, bad, refs, "frozen")
    assert not r["paired_eligible"] and not r["z_observable"]
    assert r["baseline_action"] == r["candidate_action"] == 0
    assert ("SPOT_MINUTE_MISSING" if market == 0 else "PERP_MINUTE_MISSING") in r[
        "no_action_reasons"
    ]


def test_future_values_and_bar_at_cutoff_cannot_affect_current_panel():
    t, bars, bad, refs = channels()
    before = p.panel_row(t, xrow(t), bars, bad, refs, "frozen")
    cutoff = t - c.MINUTE
    for market in bars:
        for end in [cutoff, cutoff + c.MINUTE, cutoff + 24 * c.HOUR]:
            market[end] = a.Bar(end - c.MINUTE, end, 999999, (999999,), "future", "future")
    assert p.panel_row(t, xrow(t), bars, bad, refs, "frozen") == before


def test_UTC_cutoff_rejects_end_shift_and_nonfixed_origin():
    t, bars, bad, refs = channels()
    last = max(bars[0])
    bars[0][last] = replace(bars[0][last], end=t - c.MINUTE)
    with pytest.raises(ValueError, match="CAUSAL_CLOCK"):
        p.panel_row(t, xrow(t), bars, bad, refs, "frozen")
    with pytest.raises(ValueError, match="HH01"):
        p.panel_row(t + c.MINUTE, xrow(t), bars, bad, refs, "frozen")


def test_duplicates_deduplicate_and_conflicts_never_rescue():
    t, bars, bad, refs = channels()
    end = min(bars[0])
    original = bars[0][end]
    assert a.insert_bar(bars[0], bad[0], refs[0], original)
    assert not bad[0]
    assert a.insert_bar(bars[0], bad[0], refs[0], replace(original, fingerprint=(123,)))
    assert end in bad[0]
    a.insert_bar(bars[0], bad[0], refs[0], original)
    r = p.panel_row(t, xrow(t), bars, bad, refs, "frozen")
    assert not r["paired_eligible"] and "CONFLICTING_NATIVE_MINUTE" in r["no_action_reasons"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2025-02-01T00:01:00Z", True),
        ("2025-12-31T23:01:00Z", True),
        ("2026-01-31T23:01:00Z", True),
        ("2026-02-01T00:01:00Z", True),
        ("2026-02-03T00:01:00Z", False),
        ("2026-09-01T00:01:00Z", True),
        ("2024-12-31T23:01:00Z", False),
    ],
)
def test_protected_windows_and_warmup(text, expected):
    assert c.protected(c.us(text)) == expected


def test_protected_origin_never_reads_channels():
    class Unreadable(dict):
        def __contains__(self, key):
            raise AssertionError("PROTECTED_PAYLOAD_ACCESSED")

    t = c.us("2025-02-01T00:01:00Z")
    row = p.panel_row(t, xrow(t), [Unreadable(), Unreadable()], [set(), set()], [{}, {}], "frozen")
    assert not row["paired_eligible"] and row["features"] is None


@pytest.mark.parametrize("text", ["2021-01-01T00:00:00", "2021-01-01T08:00:00+08:00"])
def test_explicit_UTC_required(text):
    with pytest.raises(ValueError, match="UTC"):
        c.us(text)


def native():
    start = c.us("2021-01-01T00:00:00Z")
    row = {
        "exchange": "binance",
        "native_symbol": "BTCUSDT",
        "canonical_underlying": "BTC",
        "quote_asset": "USDT",
        "product_type": "SPOT",
        "contract_identity": "SPOT",
        "price_unit": "USDT/BTC",
        "interval": "1m",
        "interval_start_utc": start,
        "interval_end_utc": start + c.MINUTE,
        "event_ts_utc": start + c.MINUTE,
        "source_native_ts": str(start // 1000),
        "source_time_unit": "ms",
        "source_id": "source",
        "raw_sha256": "rawpin",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
        "base_volume": 1.0,
        "quote_volume": 100.0,
        "qc_flags": "SOURCE_NOT_ADMITTED",
    }
    rec = {
        "table": "bars",
        "family": "spot_klines",
        "interval": "1m",
        "product": "SPOT",
        "source_id": "source",
        "source_sha256": "rawpin",
        "period": "2021-01",
    }
    return row, rec


@pytest.mark.parametrize(
    "field,value",
    [
        ("exchange", "okx"),
        ("native_symbol", "ETHUSDT"),
        ("product_type", "USD_M_PERPETUAL"),
        ("interval", "5m"),
        ("contract_identity", "BTCUSD"),
        ("source_time_unit", "us"),
        ("event_ts_utc", 0),
        ("interval_end_utc", 0),
        ("source_native_ts", "0"),
        ("close", float("nan")),
    ],
)
def test_wrong_native_contract_clock_or_nonfinite_fields_rejected(field, value):
    row, receipt = native()
    row[field] = value
    with pytest.raises(ValueError):
        a.native_bar(row, "SPOT", receipt)


def test_source_family_cannot_substitute_mark_index_or_flow():
    row, receipt = native()
    assert a.native_bar(row, "SPOT", receipt).close == 100
    for family in ["markPriceKlines", "indexPriceKlines", "aggTrades"]:
        with pytest.raises(ValueError, match="SOURCE_FAMILY"):
            a.native_bar(row, "SPOT", {**receipt, "family": family})


def test_preregistration_is_immutable_and_has_zero_search_budget(tmp_path):
    reg = c.registration({"source_pin": "unchanged"})
    h = c.freeze(tmp_path, reg)
    assert c.freeze(tmp_path, reg) == h
    changed = copy.deepcopy(reg)
    changed["formulas"]["lead"] = "different"
    with pytest.raises(ValueError, match="IMMUTABLE"):
        c.freeze(tmp_path, changed)
    assert all(v == 0 for v in reg["budget"].values())


def test_input_schema_with_outcome_fails_before_read(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "C1", tmp_path)
    path = (
        tmp_path / "table=bars/exchange=binance/asset=BTC/product=SPOT/period=2021-01/test.parquet"
    )
    path.parent.mkdir(parents=True)
    row, rec = native()
    # Extra outcome field must fail before any row payload is loaded.
    row = {**{k: None for k in a.SCHEMA}, **row, "forward_return_8h": 1.0}
    pq.write_table(pa.Table.from_pylist([row]), path)
    rec.update(
        partition_path=str(path), partition_sha256=c.digest(path), status="SUCCESS", row_count=1
    )
    with pytest.raises(ValueError, match="NO_OUTCOME_INPUT_SCHEMA"):
        a.load_month([rec], "SPOT", "2021-01", *a.month_bounds("2021-01"))


def test_output_schema_rejects_outcome_field():
    t, bars, bad, refs = channels()
    row = p.panel_row(t, xrow(t), bars, bad, refs, "frozen")
    with pytest.raises(ValueError, match="NO_OUTCOME_OUTPUT_SCHEMA"):
        p.validate_panel({**row, "PnL": 1})
    row["features"]["forward_return_8h"] = 1
    with pytest.raises(ValueError, match="NO_OUTCOME_NESTED"):
        p.validate_panel(row)


def test_frozen_X_rejects_outcome_schema(tmp_path):
    path = tmp_path / "features.jsonl"
    path.write_bytes(c.canonical({"future_return": 1}))
    with pytest.raises(ValueError, match="NO_OUTCOME_SCHEMA"):
        p.load_r1(path)


def test_X_at_or_after_cutoff_is_ineligible():
    t, bars, bad, refs = channels()
    for end in [t - c.MINUTE, t, t + c.HOUR]:
        x = {**xrow(t), "x_end_us": end}
        row = p.panel_row(t, x, bars, bad, refs, "frozen")
        assert not row["x_eligible"] and not row["paired_eligible"]
        assert row["baseline_action"] == row["candidate_action"] == 0


def test_no_signal_is_observable_not_missing_and_NO_ACTION_denominator():
    t, bars, bad, refs = channels()
    for market in bars:
        for key, bar in market.items():
            market[key] = replace(bar, close=100.0)
    row = p.panel_row(t, xrow(t), bars, bad, refs, "frozen")
    assert row["paired_eligible"] and row["baseline_action"] == -1
    assert row["candidate_action"] == 0 and row["no_action"]
    summary = p.summarize([row])
    assert summary["scheduled_origins"] == summary["paired_eligible"] == summary["no_action"] == 1
    assert summary["source_ineligible_origins"] == 0


def test_fixed_baseline_threshold_and_missing_X_masks_both():
    t, bars, bad, refs = channels()
    row = p.panel_row(t, xrow(t, -0.01), bars, bad, refs, "frozen")
    assert row["candidate_action"] == -1
    row = p.panel_row(t, xrow(t, -0.009999), bars, bad, refs, "frozen")
    assert row["baseline_action"] == row["candidate_action"] == 0
    row = p.panel_row(t, None, bars, bad, refs, "frozen")
    assert not row["paired_eligible"] and row["baseline_action"] == row["candidate_action"] == 0


def test_episode_half_open_nonoverlap_weeks_and_density():
    origin = c.us("2023-01-01T23:01:00Z")
    rows = [
        {
            "origin_us": origin + h * c.HOUR,
            "candidate_action": -1,
            "paired_eligible": True,
            "year": c.iso(origin + h * c.HOUR)[:4],
        }
        for h in [0, 1, 7, 8, 9, 16]
    ]
    ep = p.episodes(rows, "candidate", 8)
    assert ep["nonoverlap_episodes"] == 3 and ep["weekly_blocks"] == 2
    assert ep["episode_coverage_trigger_hours"] == len(rows)
    assert ep["episodes_per_eligible_48h"] == 24
    assert [len(e["trigger_origins_us"]) for e in ep["episodes"]] == [3, 2, 1]
    assert all(
        a["end_exclusive_us"] <= b["start_us"] for a, b in zip(ep["episodes"], ep["episodes"][1:])
    )


def test_density_rejection_cannot_be_rescued_by_raw_trigger_count():
    reg = c.registration({})
    ep = {
        "trigger_hours": 100,
        "nonoverlap_episodes": 40,
        "weekly_blocks": 20,
        "by_year_episodes": {"2021": 15, "2022": 15, "2023": 10},
        "maximum_year_trigger_share": 0.5,
        "episodes_per_eligible_48h": 0.1,
    }
    verdict = p.feasibility({"paired_eligibility_proportion": 0.99}, ep, reg)
    assert verdict["status"] == "R3_MECHANISM_FEASIBILITY_NO_GO"
    assert verdict["exact_falsifiers"] == ["opportunity_density"]


def test_missing_registration_blocks_build_before_features(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "calculate", lambda *args: pytest.fail("features read before freeze"))
    with pytest.raises(FileNotFoundError):
        p.build(tmp_path)


def test_R1_reference_never_uses_extended_R2_OI_population(monkeypatch):
    original = {
        "funding_triggers": 168,
        "funding_independent_episodes_8h": 113,
        "funding_weekly_blocks": 44,
        "funding_z_eligible": 35250,
        "oi_triggers": 4,
        "oi_independent_episodes_8h": 2,
        "oi_weekly_blocks": 2,
        "oi_z_eligible": 3667,
    }
    expanded = {
        "total_trigger_hours": 89,
        "independent_episodes_count": 38,
        "weekly_blocks_count": 22,
    }

    def read_reference(path):
        if path == p.R2 / "before_after_eligibility.json":
            return {"before_r1": original, "after_r2": {"oi_triggers": 10}}
        if path == p.R2 / "event_episodes.json":
            pytest.fail("R2 extended OI cannot be called frozen R1")
        if path.name == "COMPLETION_RECEIPT.json":
            return {"BTC_binance": {"funding_premium_eligible": 35250, "OI_eligible": 3667}}
        if path.name == "event_episodes.json":
            return {"C_EXPLORATORY_2021_2025": {"horizons": {"8": expanded}}}
        return {"by_population": {"C_EXPLORATORY_2021_2025": {"paired_xz_eligible": 27973}}}

    monkeypatch.setattr(p, "read", read_reference)
    report = p.prior_comparison({"total": {}}, {"baseline": {"8": {}}, "candidate": {"8": {}}})
    oi = next(r for r in report["frozen_prior_reference"] if r["name"] == "frozen_R1_OI")
    assert (
        oi["trigger_hours"],
        oi["nonoverlap_8h_episodes"],
        oi["weekly_blocks"],
        oi["paired_origins"],
    ) == (4, 2, 2, 3667)
