"""Clock, missingness, policy and authorization regressions; no real outcomes."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from datetime import UTC, datetime, timedelta

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.research.bline_multiyear import contracts as c
from scripts.research.bline_multiyear import panel as a
from scripts.research.bline_multiyear import pipeline as cli
from scripts.research.bline_multiyear.evaluation import candidate_economics
from scripts.research.exposed_dev_bridge.outcome_adapter import horizon_max_origin, is_origin_mature
from scripts.research.strategy_eval.costs import BASELINE, STRESS, Outcome, Settlement, economics

START = c.epoch("2024-01-01T00:00:00Z")
CUTOFF = START+26*3600


def native(t, kind="bar", **values):
    dt = datetime.fromtimestamp(t, UTC)
    return {"exchange": "binance", "native_symbol": "BTCUSDT", "product_type": "USD_M_PERPETUAL",
            "source_id": "synthetic-"+kind, "raw_sha256": "a"*64, "source_time_unit": "ms",
            "source_native_ts": str(t*1000), "interval": "1m",
            "interval_start_utc": dt, "interval_end_utc": dt+timedelta(minutes=1),
            "event_ts_utc": dt if kind in ("oi", "funding") else dt+timedelta(minutes=1), **values}


@pytest.fixture
def channels():
    raw = []
    for i, t in enumerate(range(CUTOFF-27*3600, CUTOFF+3600, 60)):
        price = 100+math.sin(i/17)+i*.002
        raw.append(native(t, close=price, high=price+1, low=price-1,
                          base_volume=10., quote_volume=1000.))
    result = {"perp": a.Channel(raw, ("close", "high", "low", "base_volume", "quote_volume"))}
    for key, factor in (("spot", .999), ("mark", 1.001), ("index", 1.), ("premium", .00001)):
        rows = [{**r, "close": r["close"]*factor} for r in raw]
        result[key] = a.Channel(rows, ("close",))
    result["funding"] = a.Channel([
        native(CUTOFF-8*3600, "funding", funding_rate=.0001),
        native(CUTOFF, "funding", funding_rate=.5),
        native(CUTOFF+60, "funding", funding_rate=.9)], ("funding_rate",), event=True)
    zt = CUTOFF-300
    result["oi"] = a.Channel([native(t, "oi", interval="5m", base_open_interest=v,
                                       top_position_long_short_ratio=2.)
                              for t, v in ((zt-14400, 100.), (zt, 95.))],
                             ("base_open_interest", "top_position_long_short_ratio"))
    flow = [native(t, volume_quote=1000., signed_flow_quote=100.)
            for t in range(CUTOFF-3600, CUTOFF+60, 60)]
    result["flow_perp"] = a.Channel(flow, ("volume_quote", "signed_flow_quote"))
    result["flow_spot"] = a.Channel(flow, ("volume_quote", "signed_flow_quote"))
    return result


def one(channels):
    return a.build_rows(CUTOFF, CUTOFF+3600, channels)[0]


def test_shared_adapter_no_future_bar_funding_flow_leak(channels):
    before = one(channels)
    changed = copy.deepcopy(channels)
    for channel in changed.values():
        for key, values in channel.values.items():
            # X price last permitted open is C-120; flow may end exactly C.
            last = CUTOFF-60 if key in ("volume_quote", "signed_flow_quote") else CUTOFF-120
            values[channel.t > last*a.US] = 1e9
    # Funding exactly C is not available even at HH:01.
    changed["funding"].values["funding_rate"][changed["funding"].t >= CUTOFF*a.US] = 1e9
    after = one(changed)
    assert before["x"] == after["x"]
    assert before["derivatives"] == after["derivatives"]
    assert before["signed_flow"] == after["signed_flow"]
    assert before["x_end_us"] < CUTOFF*a.US
    assert before["derivatives"]["funding_event_us"] < CUTOFF*a.US


def test_receiver_clock_remains_unknown(channels):
    row = one(channels)
    assert row["clock"]["action"] == "FEATURE_READY_NOT_TRADE"
    assert row["receiver_gate"] == row["action"] == "NO_ACTION"
    assert row["receiver_pit"] == "PIT_UNKNOWN"
    assert "outcomes" not in row


def test_exact_oi_lag_predecessor_and_native_timestamp(channels):
    row = one(channels)
    assert row["z_t"] == CUTOFF-300
    assert row["z"][0] == pytest.approx(math.log(.95))
    assert row["oi_clock"]["action"] == "FEATURE_READY_NOT_TRADE"
    assert row["oi_native_samples"][0]["source_native_ts"] == str((CUTOFF-300)*1000)
    channels["oi"] = a.Channel(channels["oi"].rows[1:], ("base_open_interest", "top_position_long_short_ratio"))
    assert one(channels)["z_reason"] == "Z_4H_PREDECESSOR_MISSING"


def test_no_forward_fill_of_missing_bar_or_flow(channels):
    rows = channels["perp"].rows
    channels["perp"] = a.Channel([r for r in rows if r["interval_start_utc"] !=
                                 datetime.fromtimestamp(CUTOFF-3*3600, UTC)], tuple(channels["perp"].values))
    assert one(channels)["x"] is None
    flow = channels["flow_perp"]
    channels["flow_perp"] = a.Channel(flow.rows[1:], tuple(flow.values))
    assert one(channels)["signed_flow"]["perp"] is None


def test_stale_funding_does_not_backfill(channels):
    r = native(CUTOFF-10*3600, "funding", funding_rate=.0001)
    channels["funding"] = a.Channel([r], ("funding_rate",), event=True)
    assert one(channels)["derivatives"] is None


def test_duplicate_old_new_identity_denied():
    old = native(START, close=100.)
    new = {**old, "source_id": "Q2_NEW_ZIP"}
    with pytest.raises(ValueError, match="DUPLICATE"):
        a.Channel([old, new], ("close",))


def test_repeatable_canonical_sha(channels):
    row = one(channels)
    assert hashlib.sha256(c.canonical(row)).hexdigest() == hashlib.sha256(c.canonical(one(channels))).hexdigest()


@pytest.mark.parametrize("h", [4, 8, 12, 24])
def test_h39_right_edge(h):
    last = horizon_max_origin(h)
    assert is_origin_mature(last, h)
    assert not is_origin_mature(last+3600, h)


@pytest.mark.parametrize("left,right", [
    ("2025-02-01T00:00:00Z", "2025-03-01T00:00:00Z"),
    ("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"),
    ("2026-09-01T00:00:00Z", "2026-10-01T00:00:00Z")])
def test_protected_h40_and_post2025_exclusion(left, right):
    assert c.excluded(c.epoch(left), c.epoch(right))


def test_post2025_does_not_mean_all_data_permitted():
    assert not c.excluded(c.epoch("2026-04-01T00:00:00Z"), c.H39)
    # Known-date eligibility is not Owner authorization.
    with pytest.raises(ValueError, match="PREEXISTING_OWNER"):
        cli.evaluate_authorized(None, None, None, None, None, started_ns=time.time_ns())


def test_unauthorized_does_not_open_real_outcome(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("outcome parser must not be called")
    monkeypatch.setattr(cli.p1, "authorized_panel", forbidden)
    with pytest.raises(ValueError, match="PREEXISTING_OWNER"):
        cli.evaluate_authorized(None, None, tmp_path/"protected.json", None, None,
                                started_ns=time.time_ns())


def test_fake_owner_v1_stops_before_outcome_parser(monkeypatch, tmp_path):
    paths = [tmp_path/f"fixture{i}.json" for i in range(5)]
    for p in paths:
        p.write_text('{}')
    monkeypatch.setattr(cli, "validate_scope", lambda *a, **k: {"schema": "exposed_dev_bridge.owner-scope.v1"})
    monkeypatch.setattr(cli.p1, "authorized_panel", lambda *a: pytest.fail("early outcome read"))
    with pytest.raises(ValueError, match="OWNER_SCOPE_V2"):
        cli.evaluate_authorized(*paths, started_ns=time.time_ns())


def test_frozen_policies_and_common_missingness(channels):
    r = one(channels)
    r["x"][1] = -.02
    assert c.signals(r, "OI_DELEVERAGING_CONTINUATION") == (-1, -1, True)
    r["z"] = None
    assert c.signals(r, "OI_DELEVERAGING_CONTINUATION") == (0, 0, False)
    r["x"][1] = .02
    r["derivatives"].update(premium_prior4h=.001, basis_prior4h=.001,
                            premium_change=-.0003, basis_change=-.0003, funding_rate=.0002)
    assert c.signals(r, "FUNDING_PREMIUM_RELEASE") == (-1, -1, True)


def test_no_action_denominator_and_unresolved_outcomes(channels):
    row = one(channels)
    row["x"][1] = -.02
    row["t"] = START+42*86400+60
    missing = {**row, "z": None, "z_status": "UNAVAILABLE"}
    missing["t"] += 3600
    cells = candidate_economics([row, missing], START)
    cell = next(c for c in cells if c["candidate"] == "OI_DELEVERAGING_CONTINUATION" and c["fold_day"] == 42)
    assert cell["arms"]["X"]["scheduled"] == 2
    assert cell["arms"]["XZ"]["scheduled"] == 2
    assert cell["arms"]["X"]["no_action"] == 1
    assert cell["arms"]["XZ"]["unresolved"] == 1
    assert cell["paired_increment"] is None


@pytest.mark.parametrize("cost", [BASELINE, STRESS])
def test_actual_cost_funding_accounting(cost):
    entry = START+120
    event = (entry+3600)*1_000_000
    outcome = Outcome(entry, entry+8*3600, 100., 102., (Settlement(event, .001, 101.),),
                      (event,), (entry*1_000_000, (entry+8*3600)*1_000_000))
    result = economics(outcome, -1, 8, cost)
    expected_cost = (cost.entry_fee_bp+cost.entry_spread_bp+cost.entry_slippage_bp +
                     (cost.exit_fee_bp+cost.exit_spread_bp+cost.exit_slippage_bp)*1.02)/10000
    assert result["total_cost"] == pytest.approx(expected_cost)
    assert result["net_return"] == pytest.approx(-.02+.00101-expected_cost)
    assert result["sleeve_pnl"] == pytest.approx(result["net_return"]/8)


def test_output_cannot_touch_existing_sources(tmp_path):
    with pytest.raises(ValueError, match="OUTPUT_MUST"):
        cli.output_directory(tmp_path/"other")


def test_two_fixed_candidates_and_actual_failure_ledger():
    r = c.registration()
    assert len(r["candidates"]) == 2 and r["parameter_search_budget"] == 0
    assert {x["status"] for x in c.prior_map(cli.REPO)["families"]} == {
        "FAIL", "INCONCLUSIVE", "SOURCE_BLOCKED", "ECONOMIC_BLOCKED", "UNTESTED"}


def test_c1_integer_timestamp_projection_and_receipt_hash(tmp_path):
    root = tmp_path/"lake"
    folder = root/"c1/canonical_v1/table=funding_settlements/exchange=binance/asset=BTC/product=USD_M_PERPETUAL/period=2024-01"
    folder.mkdir(parents=True)
    (root/"c2/checkpoints").mkdir(parents=True)
    raw = root/"synthetic-original.txt"
    raw.write_text("TEST_ONLY_SYNTHETIC")
    row = native(START, "funding", funding_rate=.0001)
    row["event_ts_utc"] += timedelta(microseconds=1001)
    row["source_time_unit"] = "us"
    row["source_native_ts"] = str(START*1_000_000+1001)
    row["raw_sha256"] = c.sha(raw)
    path = folder/"synthetic.parquet"
    outside = {**row, "interval_start_utc": datetime.fromtimestamp(START+1800, UTC),
               "interval_end_utc": datetime.fromtimestamp(START+3600, UTC),
               "event_ts_utc": datetime.fromtimestamp(START+3600, UTC),
               "source_native_ts": str((START+3600)*1_000_000)}
    pq.write_table(pa.Table.from_pylist([row, outside]), path)
    receipts = {"fixture": {"source_id": row["source_id"], "source_path": str(raw),
        "source_sha256": row["raw_sha256"], "partition_path": str(path),
        "partition_sha256": c.sha(path), "table": "funding_settlements", "status": "SUCCESS",
        "exchange": "binance", "asset": "BTC", "product": "USD_M_PERPETUAL"}}
    (root/"c1/source_receipts.json").write_text(json.dumps(receipts))
    (root/"c1/conflict_resolution.json").write_text("[]")
    lake = a.Lake(root)
    channel = lake.load("funding_settlements", "binance", "BTC", "USD_M_PERPETUAL",
                        datetime.fromtimestamp(START, UTC), datetime.fromtimestamp(START+3600, UTC),
                        ("funding_rate",))
    assert channel.rows[0]["event_ts_utc"] == row["event_ts_utc"]
    assert len(channel.rows) == 1  # accrual began inside, settlement is outside
    assert channel.t[0] == START*1_000_000+1001
    assert lake.verify_unchanged()["changed"] == []
    path.write_bytes(b"modified only synthetic fixture")
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        lake.verify_unchanged()


def test_candidate_cannot_use_eth_or_outside_preregistered_window(channels):
    row = one(channels)
    row["x"][1] = -.02
    assert c.signals({**row, "asset": "ETH"}, "OI_DELEVERAGING_CONTINUATION") == (0, 0, False)
    row.update(data_kind="HISTORICAL_FEATURE_ONLY")
    assert c.signals(row, "OI_DELEVERAGING_CONTINUATION") == (0, 0, False)


def test_feature_warmup_cannot_reopen_h40(monkeypatch):
    lake = a.Lake.__new__(a.Lake)
    bounds = []
    def load(table, venue, asset, product, left, right, fields):
        bounds.append((int(left.timestamp()), int(right.timestamp())))
        return a.Channel([], fields)
    monkeypatch.setattr(lake, "load", load)
    rows = lake.month("binance", "BTC", datetime(2026, 2, 1, tzinfo=UTC),
                      datetime(2026, 2, 2, tzinfo=UTC))
    assert len(rows) == 24 and all(r["x"] is None for r in rows)
    assert all(left >= c.H40[1] for left, right in bounds)
