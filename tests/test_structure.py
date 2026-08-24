import unittest

from btc_quant_agent.domain import Candle
from btc_quant_agent.structure import confirmed_pivots


class StructureTests(unittest.TestCase):
    def _bar(self, index: int, high: float, low: float) -> Candle:
        return Candle(
            symbol="BTCUSDT",
            interval="15m",
            open_time_ms=index * 900_000,
            close_time_ms=(index + 1) * 900_000 - 1,
            open=(high + low) / 2,
            high=high,
            low=low,
            close=(high + low) / 2,
            volume=1,
        )

    def test_pivot_is_unavailable_until_right_bars_close(self) -> None:
        bars = [
            self._bar(0, 2, 0),
            self._bar(1, 3, 1),
            self._bar(2, 6, 2),
            self._bar(3, 3, 1),
            self._bar(4, 2, 0),
        ]
        self.assertEqual(confirmed_pivots(bars[:4], 2, 2), [])
        pivots = confirmed_pivots(bars, 2, 2)
        high = next(pivot for pivot in pivots if pivot.kind == "HIGH")
        self.assertEqual(high.pivot_index, 2)
        self.assertEqual(high.confirmed_index, 4)

    def test_lookahead_mutation_does_not_change_past_output(self) -> None:
        past = [
            self._bar(0, 2, 0),
            self._bar(1, 3, 1),
            self._bar(2, 6, 2),
            self._bar(3, 3, 1),
            self._bar(4, 2, 0),
        ]
        baseline = confirmed_pivots(past, 2, 2)
        mutated_future = [self._bar(5, 100, -100), self._bar(6, 200, -200)]
        replayed_past = [
            pivot
            for pivot in confirmed_pivots([*past, *mutated_future], 2, 2)
            if pivot.confirmed_index <= len(past) - 1
        ]
        self.assertEqual(baseline, replayed_past)


if __name__ == "__main__":
    unittest.main()
