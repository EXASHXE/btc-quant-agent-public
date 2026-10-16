#!/usr/bin/env python3
"""
Unit tests for OKX Historical Data Portal One-File Pilot QC Harness (R11-E2)
"""

import json
import unittest

from scripts.research.r11_e2.okx_portal_pilot_qc import (
    BudgetTracker,
    SafetyError,
    qc_candlesticks_rows,
    qc_funding_rows,
    qc_l2_stream_slice,
    qc_trades_rows,
)


class TestOKXPortalPilotQC(unittest.TestCase):

    def test_trades_qc_valid(self):
        rows = [
            ["instrument_name", "trade_id", "side", "price", "size", "created_time"],
            ["BTC-USDT-SWAP", "1001", "buy", "42000.5", "10.0", "1705248000000"],
            ["BTC-USDT-SWAP", "1002", "sell", "42000.0", "5.0", "1705248000100"],
            ["BTC-USDT-SWAP", "1003", "buy", "42001.0", "15.0", "1705248000200"]
        ]
        res = qc_trades_rows(iter(rows))
        self.assertEqual(res["row_count"], 3)
        self.assertEqual(res["min_trade_id"], 1001)
        self.assertEqual(res["max_trade_id"], 1003)
        self.assertEqual(res["total_volume_contracts"], 30.0)
        self.assertTrue(res["monotonic_trade_id"])
        self.assertTrue(res["monotonic_timestamp"])

    def test_trades_qc_decreasing_id_fails(self):
        rows = [
            ["instrument_name", "trade_id", "side", "price", "size", "created_time"],
            ["BTC-USDT-SWAP", "1002", "buy", "42000.5", "10.0", "1705248000000"],
            ["BTC-USDT-SWAP", "1001", "sell", "42000.0", "5.0", "1705248000100"]
        ]
        with self.assertRaises(SafetyError):
            qc_trades_rows(iter(rows))

    def test_trades_qc_invalid_side_fails(self):
        rows = [
            ["instrument_name", "trade_id", "side", "price", "size", "created_time"],
            ["BTC-USDT-SWAP", "1001", "hold", "42000.5", "10.0", "1705248000000"]
        ]
        with self.assertRaises(SafetyError):
            qc_trades_rows(iter(rows))

    def test_candlesticks_qc_valid(self):
        rows = [
            ["instrument_name", "open", "high", "low", "close", "vol", "vol_ccy", "vol_quote", "open_time", "confirm"],
            ["BTC-USDT-SWAP", "42000.0", "42100.0", "41950.0", "42050.0", "100.0", "1.00", "420000.0", "1705248000000", "0"],
            ["BTC-USDT-SWAP", "42050.0", "42120.0", "42040.0", "42110.0", "200.0", "2.00", "841000.0", "1705248060000", "0"]
        ]
        res = qc_candlesticks_rows(iter(rows))
        self.assertEqual(res["row_count"], 2)
        self.assertEqual(res["interval_ms"], 60000)
        self.assertEqual(res["total_volume_contracts"], 300.0)
        self.assertEqual(res["total_volume_btc"], 3.0)
        self.assertAlmostEqual(res["observed_contract_multiplier"], 0.01)

    def test_candlesticks_gap_fails(self):
        rows = [
            ["instrument_name", "open", "high", "low", "close", "vol", "vol_ccy", "vol_quote", "open_time", "confirm"],
            ["BTC-USDT-SWAP", "42000.0", "42100.0", "41950.0", "42050.0", "100.0", "1.00", "420000.0", "1705248000000", "0"],
            ["BTC-USDT-SWAP", "42050.0", "42120.0", "42040.0", "42110.0", "200.0", "2.00", "841000.0", "1705248180000", "0"]  # 120s gap
        ]
        with self.assertRaises(SafetyError):
            qc_candlesticks_rows(iter(rows))

    def test_candlesticks_extrema_violation_fails(self):
        rows = [
            ["instrument_name", "open", "high", "low", "close", "vol", "vol_ccy", "vol_quote", "open_time", "confirm"],
            ["BTC-USDT-SWAP", "42000.0", "41900.0", "41950.0", "42050.0", "100.0", "1.00", "420000.0", "1705248000000", "0"]  # high < open
        ]
        with self.assertRaises(SafetyError):
            qc_candlesticks_rows(iter(rows))

    def test_funding_qc_valid(self):
        rows = [
            ["instrument_name", "funding_rate", "funding_time"],
            ["BTC-USDT-SWAP", "0.000125", "1705248000000"],
            ["BTC-USDT-SWAP", "0.000100", "1705276800000"],
            ["BTC-USDT-SWAP", "0.000115", "1705305600000"]
        ]
        res = qc_funding_rows(iter(rows), filter_instrument="BTC-USDT-SWAP")
        self.assertEqual(res["settlement_count"], 3)
        self.assertEqual(len(res["settlements"]), 3)
        self.assertAlmostEqual(res["settlements"][0]["funding_rate"], 0.000125)

    def test_l2_stream_slice_valid(self):
        header_tar = b"BTC-USDT-SWAP-L2orderbook-400lv-2024-01-15.data" + b"\x00" * (512 - 47)
        snap = {
            "instId": "BTC-USDT-SWAP",
            "action": "snapshot",
            "ts": "1705276800000",
            "asks": [["42000.0", "10.0", "1"]] * 400,
            "bids": [["41999.0", "12.0", "2"]] * 400
        }
        upd = {
            "instId": "BTC-USDT-SWAP",
            "action": "update",
            "ts": "1705276800010",
            "asks": [["42001.0", "5.0", "1"]],
            "bids": [["41998.0", "0.0", "0"]]
        }
        stream_bytes = header_tar + json.dumps(snap).encode() + b"\n" + json.dumps(upd).encode() + b"\n"
        res = qc_l2_stream_slice(stream_bytes)
        self.assertTrue(res["snapshot_verified"])
        self.assertEqual(res["snapshot_depth_bids"], 400)
        self.assertEqual(res["snapshot_depth_asks"], 400)
        self.assertEqual(res["incremental_updates_verified"], 1)

    def test_budget_cap_enforcement(self):
        tracker = BudgetTracker(compressed_cap=1000, expanded_cap=2000)
        tracker.consume_compressed(500)
        tracker.consume_expanded(1500)
        with self.assertRaises(SafetyError):
            tracker.consume_compressed(600)  # total 1100 > 1000


if __name__ == "__main__":
    unittest.main()
