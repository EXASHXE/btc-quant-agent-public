import math
import unittest
from dataclasses import replace
from unittest.mock import patch

from btc_quant_agent.config import AppConfig, StrategyConfig
from btc_quant_agent.domain import Candle
from btc_quant_agent.engine import HistoricalFeatureCache, QuantEngine
from btc_quant_agent.features import build_features
from btc_quant_agent.indicators import (
    atr,
    bollinger_width,
    percentile_rank,
    rolling_zscore,
)


class FeatureOptimizationParityTests(unittest.TestCase):
    def _rows(self) -> list[Candle]:
        rows: list[Candle] = []
        for index in range(500):
            close = 100.0 + index * 0.02 + math.sin(index / 7)
            rows.append(
                Candle(
                    "BTCUSDT",
                    "15m",
                    index * 900_000,
                    (index + 1) * 900_000 - 1,
                    close - 0.1,
                    close + 0.5,
                    close - 0.5,
                    close,
                    10.0 + index % 17,
                    taker_buy_base_volume=6.0 + index % 5,
                )
            )
        return rows

    def test_latest_rolling_features_match_full_reference_series(self) -> None:
        rows = self._rows()
        features = build_features(rows, StrategyConfig())
        closes = [row.close for row in rows]
        highs = [row.high for row in rows]
        lows = [row.low for row in rows]
        volumes = [row.volume for row in rows]
        self.assertAlmostEqual(
            features.atr_percentile,
            percentile_rank(atr(highs, lows, closes, 14), 120)[-1],
        )
        self.assertAlmostEqual(features.volume_z, rolling_zscore(volumes, 30)[-1])
        self.assertAlmostEqual(
            features.bb_width_percentile,
            percentile_rank(bollinger_width(closes, 20), 120)[-1],
        )

    def test_shared_research_cache_ignores_scoring_only_changes(self) -> None:
        rows = self._rows()
        cache = HistoricalFeatureCache()
        base = AppConfig()
        scoring_change = replace(
            base, strategy=replace(base.strategy, factor_score_min=75.0)
        )
        feature_change = replace(base, strategy=replace(base.strategy, ema_fast=8))
        with patch("btc_quant_agent.engine.build_features", wraps=build_features) as builder:
            QuantEngine(base, cache)._features("15m", rows)
            QuantEngine(scoring_change, cache)._features("15m", rows)
            self.assertEqual(builder.call_count, 1)
            QuantEngine(feature_change, cache)._features("15m", rows)
            self.assertEqual(builder.call_count, 2)


if __name__ == "__main__":
    unittest.main()
