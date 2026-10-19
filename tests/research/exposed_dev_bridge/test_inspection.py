import hashlib
import json
import math
from dataclasses import replace

import pytest

from scripts.research.cross_venue import normalized_sources as n
from scripts.research.cross_venue import pipeline as p2
from scripts.research.exposed_dev_bridge import LABELS
from scripts.research.exposed_dev_bridge import inspection as b
from scripts.research.exposed_dev_bridge import pipeline as cli
from scripts.research.strategy_eval import clocked_dataset as p1

from .conftest import archive, publish

START = n.quarter_window("Q3")[0]


def test_q2_q3_stitch_uses_utc8_adjacent_file_and_exact_p1_predecessor(tmp_path):
    roots = {(q, v): tmp_path / f"{v}-{q}" for q in ("Q2", "Q3") for v in ("binance", "okx")}
    records = {key: [] for key in roots}
    minutes = [(START - 86400 - 60 + i * 60) * n.US for i in range(1441)]
    for family in ("klines", "spot_klines", "markPriceKlines"):
        records["Q2", "binance"].append(archive(roots["Q2", "binance"], "binance", family,
                                                 period="2026-06", times=minutes))
    stock_times = [(START - 300 - 14400) * n.US, (START - 300) * n.US]
    records["Q2", "binance"].append(archive(roots["Q2", "binance"], "binance", "metrics",
                                              period="2026-06-30", times=stock_times))
    records["Q2", "binance"].append(archive(roots["Q2", "binance"], "binance", "fundingRate",
                                              period="2026-06", times=[(START - 3600) * n.US]))
    for family in ("candlesticks", "spot_candlesticks"):
        records["Q3", "okx"].append(archive(roots["Q3", "okx"], "okx", family,
                                              times=[(START - 60) * n.US]))
    records["Q3", "okx"].append(archive(roots["Q3", "okx"], "okx", "funding_rates",
                                          times=[(START - 3600) * n.US]))
    for key, root in roots.items():
        publish(root, key[1], records[key])
    state = b.inspect_sources(roots)
    assert state.error is None
    assert len(state.rows) == (91 + 92) * 24 * 2 == 8784
    first_q3 = next(r for r in state.rows if r["asset"] == "BTC" and r["cutoff_utc_s"] == START)
    assert first_q3["t"] == START + 60 and first_q3["native_feature_ready"]
    assert p1.ready(first_q3["p1"]) == (True, True)
    assert first_q3["p1"]["x"] == pytest.approx([0, 0, 0, 0, 0, math.log1p(60000), 0, 0, 1/6, 0])
    assert first_q3["binance_z"]["predecessor"]["event_utc_us"] == stock_times[0]
    assert first_q3["bars"]["okx_swap"]["sample"]["file_calendar_label"] == "2026-07-01"
    assert first_q3["bars"]["okx_swap"]["sample"]["file_calendar_timezone"] == "UTC+08:00"
    assert first_q3["bars"]["binance_perp"]["sample"]["raw_source_sha256"] == records["Q2", "binance"][0]["local_sha256"]
    q2 = next(i for i in state.intersections if i["quarter"] == "Q2" and i["asset"] == "BTC")
    assert q2["aligned_minutes_scanned"] == 1
    assert q2["quarter_local_metadata"]["candidate_aligned_minutes"] == 0
    assert q2["proof"] == "FULL_STREAM_SCAN_AGREES_WITH_METADATA"
    assert all(r["action"] == "NO_ACTION" and r["receiver_pit"] == "PIT_UNKNOWN" for r in state.rows)
    assert not any("outcomes" in r or "return" in r for r in state.rows)


def test_denominator_and_byte_determinism_even_when_every_feature_missing(empty_roots, tmp_path):
    first = cli.inspect(empty_roots, tmp_path / "out1")
    second = cli.inspect(empty_roots, tmp_path / "out2")
    assert first == second
    assert first["status"] == "INSPECTION_ONLY" and first["exit_code"] == 1
    assert first["scheduled_origin_denominator"] == first["no_action_origins"] == 4416
    assert first["historical_outcomes_evaluated"] == first["native_feature_ready_origins"] == 0
    for name in cli.OUTPUT_FILES:
        assert (tmp_path / "out1" / name).read_bytes() == (tmp_path / "out2" / name).read_bytes()
    receipt = json.loads((tmp_path / "out1/test_receipt.json").read_text())
    assert all(receipt["checks"].values())
    for name, sha in receipt["artifact_sha256"].items():
        assert sha == hashlib.sha256((tmp_path / "out1" / name).read_bytes()).hexdigest()
    assert set(LABELS) <= set(first["labels"])


def test_l2_missing_is_distinct_from_pass_klines(tmp_path):
    root = tmp_path / "binance"
    r = archive(root, "binance", "klines")
    snap = n.Snapshot.capture(publish(root, "binance", [r]), "binance", "Q3")
    sources = n.expansion_sources(snap, n.Budget(expanded_cap=0))
    okx = n.Snapshot.capture(publish(tmp_path / "okx", "okx", []), "okx", "Q2")
    missing = n.Source(okx, {"family": "orderbook", "symbol": "BTC-USDT-SWAP", "market": "swap",
        "period": "2026-04-01", "verdict": "OBJECT_NOT_FOUND", "rows": None, "gaps": None}, None)
    state = p2.Inspection("inspect-historical", snapshots=[snap, okx], sources=sources + [missing])
    report = b.source_coverage(state)
    assert next(f for f in report["families"] if f["family"] == "klines" and f["symbol"] == "BTCUSDT")["manifest_status"] == "PASS"
    l2 = next(f for f in report["families"] if f["quarter"] == "Q2" and f["family"] == "orderbook")
    assert l2["manifest_status"] == "MISSING" and l2["not_pass_periods"] == ["2026-04-01"]
    blocker = next(c for c in report["family_blockers"] if c["family"] == "orderbook")
    assert blocker["blocks_native_features"] is False


@pytest.mark.parametrize("age,prior,reason", [(300, True, "READY"), (600, True, "READY"),
    (900, True, "Z_STALE"), (300, False, "Z_4H_PREDECESSOR_MISSING"), (0, False, "Z_FUTURE_OR_TOO_RECENT")])
def test_z_staleness_exact_predecessor_and_future_in_both_existing_apis(age, prior, reason):
    cutoff = START + 86400
    timestamp = cutoff - age
    stocks = {timestamp: p1.Stock(timestamp, 1000, 1.2)}
    if prior:
        stocks[timestamp - 14400] = p1.Stock(timestamp - 14400, 900, 1.1)
    got = p1.select_z(stocks, sorted(stocks), cutoff)
    assert got["z_reason"] == reason
    native = {t * n.US: n.Stock("BTC", t * n.US, s.base_oi, s.top_position_ls, {}) for t, s in stocks.items()}
    assert p2.select_z(native, sorted(native), cutoff, "BTC")["reason"] == reason
    if prior and age == 300:
        wrong = stocks.pop(timestamp - 14400)
        stocks[timestamp - 14700] = replace(wrong, t=timestamp - 14700)
        assert p1.select_z(stocks, sorted(stocks), cutoff)["z_reason"] == "Z_4H_PREDECESSOR_MISSING"


def test_future_funding_does_not_become_feature_or_receiver_pit():
    c = START + 3600
    past = n.Funding("BTC", "binance", (c - 1) * n.US, .0001, {"contract": "BTCUSDT"})
    events = [past, replace(past, t_us=c * n.US, rate=.9), replace(past, t_us=(c + 1) * n.US, rate=.8)]
    row = p2.origin("BTC", "Q3", c, {}, {}, [], {"binance": events},
                    {"binance": [e.t_us for e in events]})
    assert row["settled_funding"]["binance"]["sample"]["settled_rate"] == .0001
    assert row["settled_funding"]["binance"]["receiver_pit"] == row["receiver_pit"] == "PIT_UNKNOWN"
    assert row["action"] == "NO_ACTION"
    assert p2.settled_funding(events[1:], [e.t_us for e in events[1:]], c, "BTC", "binance")["reason"] == "FUNDING_FUTURE_OR_AT_CUTOFF"


@pytest.mark.parametrize("mutation,reason", [("unclosed", "X_BAR_NOT_STRICTLY_CLOSED"),
    ("future", "MISSING_X_1M_WINDOW"), ("gap", "MISSING_X_1M_WINDOW")])
def test_p1_controls_reject_unclosed_future_and_gap(mutation, reason):
    cutoff = START + 2 * 86400
    times = range(cutoff - 86400 - 60, cutoff, 60)
    futures = [p1.Bar(t * n.US, (t + 60) * n.US - 1000,
                      100, 102, 99, 101, 10, 1000, 500) for t in times]
    spot = [replace(bar, market="spot") for bar in futures]
    assert p1.controls(futures, spot, cutoff)[1] == "READY"
    if mutation == "unclosed":
        futures[-1] = replace(futures[-1], close_us=cutoff * n.US)
    else:
        futures[-1] = replace(futures[-1], open_us=(cutoff if mutation == "future" else cutoff - 120) * n.US)
    assert p1.controls(futures, spot, cutoff) == (None, reason)


def test_changed_manifest_discards_all_rows(empty_roots, monkeypatch):
    original = n.Snapshot.verify
    calls = {}
    def change_at_final(self):
        calls[self.root] = calls.get(self.root, 0) + 1
        if self.venue == "binance" and calls[self.root] == 2:
            with (self.root / "manifest.json").open("ab") as out:
                out.write(b"\n")
        return original(self)
    monkeypatch.setattr(n.Snapshot, "verify", change_at_final)
    state = b.inspect_sources(empty_roots)
    assert state.error.code == "INPUT_CHANGED"
    assert not state.rows and not state.intersections
    assert not state.snapshots[0].unchanged


def test_incomplete_archive_fails_final_row_qc(empty_roots):
    root = empty_roots["Q3", "binance"]
    record = archive(root, "binance", "klines")
    record["rows"] += 1
    publish(root, "binance", [record])
    state = b.inspect_sources(empty_roots)
    assert state.error.code == "SOURCE_ROW_COUNT_MISMATCH" and not state.rows


def test_raw_replacement_after_completed_stream_is_input_changed(empty_roots, monkeypatch):
    root = empty_roots["Q3", "binance"]
    record = archive(root, "binance", "klines")
    publish(root, "binance", [record])
    original = p2.build_asset_grid
    def replace_after_read(asset, *args):
        result = original(asset, *args)
        if asset == "BTC":
            path = root / record["local_path"]
            raw = bytearray(path.read_bytes())
            raw[len(raw) // 2] ^= 1
            path.write_bytes(raw)
        return result
    monkeypatch.setattr(p2, "build_asset_grid", replace_after_read)
    state = b.inspect_sources(empty_roots)
    assert state.error.code == "INPUT_CHANGED" and not state.rows
    assert not state.raw_inputs_unchanged
    assert all(s.unchanged for s in state.snapshots)


def test_cli_rejects_q2_half_pair_and_nonempty_output(empty_roots, tmp_path):
    args = ["inspect", "--binance-root", str(empty_roots["Q3", "binance"]),
            "--okx-root", str(empty_roots["Q3", "okx"]), "--binance-q2", str(tmp_path / "q2"),
            "--output-dir", str(tmp_path / "out")]
    assert cli.main(args) == 2
    result = json.loads((tmp_path / "out/bridge_result.json").read_text())
    assert result["error"]["code"] == "Q2_ROOT_PAIR_REQUIRED"
    assert cli.main(args) == 2
