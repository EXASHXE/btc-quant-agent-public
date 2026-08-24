import tempfile
import unittest
from pathlib import Path

from btc_quant_agent.config import DataConfig
from btc_quant_agent.data.derivatives import (
    HistoricalDerivativeStore,
    sanitize_derivatives,
    write_historical_derivatives_csv,
)
from btc_quant_agent.domain import DerivativesSnapshot


def snapshot(observed_at_ms: int, *, event_time_ms: int | None = None) -> DerivativesSnapshot:
    event_time_ms = observed_at_ms if event_time_ms is None else event_time_ms
    return DerivativesSnapshot(
        observed_at_ms=observed_at_ms,
        mark_price=100.0,
        index_price=99.9,
        premium_bps=10.01,
        funding_rate=0.0001,
        funding_time_ms=event_time_ms,
        open_interest=1000.0,
        open_interest_change_pct=0.02,
        open_interest_time_ms=event_time_ms,
        taker_buy_sell_ratio=1.1,
        taker_time_ms=event_time_ms,
        basis_rate=0.0002,
        basis_time_ms=event_time_ms,
        long_short_account_ratio=1.05,
        long_short_time_ms=event_time_ms,
        order_book_imbalance=0.2,
        spread_bps=0.5,
        order_book_time_ms=event_time_ms,
    )


class HistoricalDerivativeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = DataConfig(
            oi_stale_seconds=10,
            funding_stale_seconds=10,
            derivatives_stale_seconds=10,
        )

    def test_asof_join_never_uses_future_data(self) -> None:
        store = HistoricalDerivativeStore([snapshot(1_000), snapshot(3_000)])
        selected = store.snapshot_at(2_000, self.config)
        assert selected
        self.assertEqual(selected.observed_at_ms, 1_000)

    def test_stale_oi_returns_none(self) -> None:
        selected, stale = sanitize_derivatives(snapshot(1_000), 12_000, self.config)
        assert selected
        self.assertIsNone(selected.open_interest)
        self.assertIsNone(selected.open_interest_change_pct)
        self.assertIn("open_interest", stale)

    def test_stale_funding_returns_none(self) -> None:
        selected, stale = sanitize_derivatives(snapshot(1_000), 12_000, self.config)
        assert selected
        self.assertIsNone(selected.funding_rate)
        self.assertIn("funding", stale)

    def test_backtest_and_live_feature_contract_match(self) -> None:
        item = snapshot(1_000)
        live, _ = sanitize_derivatives(item, 2_000, self.config, include_order_book=False)
        historical = HistoricalDerivativeStore([item]).snapshot_at(2_000, self.config)
        self.assertEqual(live, historical)

    def test_derivative_snapshot_reproducible(self) -> None:
        store = HistoricalDerivativeStore([snapshot(1_000), snapshot(2_000)])
        values = [store.snapshot_at(2_500, self.config) for _ in range(100)]
        self.assertTrue(all(item == values[0] for item in values))

    def test_future_mutation_does_not_change_past_snapshot(self) -> None:
        before = HistoricalDerivativeStore([snapshot(1_000)]).snapshot_at(2_000, self.config)
        after = HistoricalDerivativeStore([snapshot(1_000), snapshot(2_001)]).snapshot_at(
            2_000, self.config
        )
        self.assertEqual(before, after)

    def test_csv_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "derivatives.csv"
            write_historical_derivatives_csv(path, [snapshot(1_000)])
            restored = HistoricalDerivativeStore.from_csv(path)
            self.assertEqual(restored.as_rows()[0]["open_interest"], 1000.0)


if __name__ == "__main__":
    unittest.main()
