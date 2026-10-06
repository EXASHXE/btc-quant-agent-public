from dataclasses import replace
from pathlib import Path

import pytest
from test_market_watch import make_dummy_tf

from btc_quant_agent.config import DataConfig
from btc_quant_agent.data.binance import BinancePublicClient
from btc_quant_agent.decision.case import case_from_assessment
from btc_quant_agent.domain import Regime
from btc_quant_agent.market_watch.config import MarketWatchConfig
from btc_quant_agent.market_watch.domain import DerivativesMetrics, MarketSnapshot, PriceMetrics
from btc_quant_agent.market_watch.scanner import MarketWatchScanner
from btc_quant_agent.market_watch.state import MarketWatchStateStore


def assessment(tmp_path: Path):
    cfg = MarketWatchConfig()
    store = MarketWatchStateStore(tmp_path / "mw.db")
    scanner = MarketWatchScanner(cfg, BinancePublicClient(DataConfig()), store)
    tf = make_dummy_tf("BTCUSDT", "1h", 101.0, Regime.TREND_UP,
                       ema_fast=100.0, ema_mid=95.0, recent_swing_low=99.0,
                       supports=(99.0,))
    from unittest.mock import MagicMock
    mock_trend = MagicMock()
    mock_trend.structure_transition = "CONTINUATION_UP"
    mock_trend.trend_persistence = 0.75
    snapshot = MarketSnapshot(symbol="BTCUSDT", decision_time_ms=3000,
        observed_at_ms=3000, exchange_time_ms=3000, price=PriceMetrics(100.2,
        quote_volume_24h=1000000.0), tf_15m=make_dummy_tf("BTCUSDT", "15m",
        close=100.2, ema_fast=100.0, atr=0.8, recent_swing_low=99.0),
        tf_1h=tf, tf_4h=replace(tf, interval="4h"),
        derivatives=DerivativesMetrics(mark_price=100.2, oi_1h_change=0.02,
        funding_rate=0.0001, spread_bps=1.0), snapshot_hash="snap",
        trend_evidence=mock_trend)
    return scanner.assess_symbol(snapshot, None, snapshot, None, None)


def test_market_watch_evidence_to_case_allowlist(tmp_path):
    item = assessment(tmp_path)
    case = case_from_assessment(item, ttl_ms=60000)
    assert case.evidence_id == item.feature_evidence_id
    assert case.snapshot_hash == item.snapshot.snapshot_hash
    assert case.entry_low == item.directional.entry_low
    assert case.account is None and case.calibration is None
    assert case.case_hash == case_from_assessment(item, ttl_ms=60000).case_hash
    assert "decision_config" not in case.canonical_json()


def test_source_evidence_tamper_rejected(tmp_path):
    item = assessment(tmp_path)
    corrupt = replace(item.feature_evidence, rule_score=999)
    with pytest.raises(ValueError, match="SOURCE_EVIDENCE"):
        case_from_assessment(replace(item, feature_evidence=corrupt), ttl_ms=60000)


def test_rehashed_invalid_evidence_is_rejected(tmp_path):
    from btc_quant_agent.market_watch.evidence import compute_evidence_id
    item = assessment(tmp_path)
    changed = replace(item.feature_evidence, policy_version="UNACCEPTED")
    changed = replace(changed, evidence_id=compute_evidence_id(changed))
    with pytest.raises(ValueError, match="SOURCE_EVIDENCE_INVALID"):
        case_from_assessment(replace(item, feature_evidence=changed,
            feature_evidence_id=changed.evidence_id), ttl_ms=60000)
