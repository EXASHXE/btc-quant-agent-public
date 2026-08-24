import unittest
from dataclasses import replace

from helpers import candles, signal

from btc_quant_agent.backtest import EventDrivenBacktestEngine
from btc_quant_agent.config import AppConfig, DataConfig, RuntimeConfig
from btc_quant_agent.domain import ScanResult


class ScriptedEngine:
    def __init__(self, *, invalidate_on_call: int | None = None):
        self.config = AppConfig(
            runtime=RuntimeConfig(ttl_minutes=60, cooldown_minutes=90),
            data=DataConfig(history_limit_15m=3, history_limit_1h=2, history_limit_4h=2),
        )
        self.scan_calls: list[tuple[int, int, int, int]] = []
        self.invalidate_calls = 0
        self.invalidate_on_call = invalidate_on_call

    def scan(self, bars_4h, bars_1h, bars_15m, derivatives, now_ms, **_kwargs):
        self.scan_calls.append((now_ms, len(bars_4h), len(bars_1h), len(bars_15m)))
        item = replace(
            signal(),
            signal_id=f"sig-{len(self.scan_calls)}",
            fingerprint="same-fingerprint",
            data_timestamp_ms=now_ms - 1,
            created_at_ms=now_ms,
            expires_at_ms=now_ms + 3_600_000,
            entry_low=200.0,
            entry_high=201.0,
        )
        return ScanResult("LONG", "OK", "confirmed", item)

    def invalidation_reason(self, *_args, **_kwargs):
        self.invalidate_calls += 1
        if self.invalidate_on_call == self.invalidate_calls:
            return "REGIME_REVERSED"
        return None


class EventBacktestTests(unittest.TestCase):
    def test_pending_signal_does_not_block_scans_and_cooldown_deduplicates(self) -> None:
        engine = ScriptedEngine()
        bars = candles(60, "1m", 60_000)
        outcomes = EventDrivenBacktestEngine(engine).run(bars)  # type: ignore[arg-type]
        self.assertEqual(len(engine.scan_calls), 4)
        self.assertEqual([item.outcome for item in outcomes], ["PENDING"])
        self.assertLessEqual(max(call[3] for call in engine.scan_calls), 3)

    def test_pending_signal_can_be_invalidated_before_fill(self) -> None:
        engine = ScriptedEngine(invalidate_on_call=1)
        outcomes = EventDrivenBacktestEngine(engine).run(  # type: ignore[arg-type]
            candles(31, "1m", 60_000)
        )
        self.assertIn("INVALIDATED", [item.outcome for item in outcomes])

    def test_signal_is_not_filled_from_its_creation_bar(self) -> None:
        class TouchingEngine(ScriptedEngine):
            def scan(self, bars_4h, bars_1h, bars_15m, derivatives, now_ms, **kwargs):
                result = super().scan(bars_4h, bars_1h, bars_15m, derivatives, now_ms, **kwargs)
                assert result.signal
                result.signal.entry_low = 99.0
                result.signal.entry_high = 101.0
                return result

        engine = TouchingEngine()
        outcomes = EventDrivenBacktestEngine(engine).run(  # type: ignore[arg-type]
            candles(15, "1m", 60_000)
        )
        self.assertEqual(outcomes[0].outcome, "PENDING")
        self.assertIsNone(outcomes[0].entered_at_ms)

    def test_signal_fills_and_resolves_only_on_next_arriving_bar(self) -> None:
        class FillEngine(ScriptedEngine):
            def scan(self, bars_4h, bars_1h, bars_15m, derivatives, now_ms, **kwargs):
                result = super().scan(bars_4h, bars_1h, bars_15m, derivatives, now_ms, **kwargs)
                assert result.signal
                result.signal.entry_low = 99.0
                result.signal.entry_high = 101.0
                result.signal.stop_loss = 90.0
                result.signal.take_profit = 100.2
                return result

        engine = FillEngine()
        outcomes = EventDrivenBacktestEngine(engine).run(  # type: ignore[arg-type]
            candles(16, "1m", 60_000)
        )
        self.assertEqual(outcomes[0].outcome, "WIN")
        self.assertEqual(outcomes[0].entered_at_ms, 900_000)

    def test_multi_year_complexity_uses_bounded_decision_history(self) -> None:
        engine = ScriptedEngine()
        EventDrivenBacktestEngine(engine).run(candles(10_000, "1m", 60_000))  # type: ignore[arg-type]
        self.assertLessEqual(max(call[1] for call in engine.scan_calls), 2)
        self.assertLessEqual(max(call[2] for call in engine.scan_calls), 2)
        self.assertLessEqual(max(call[3] for call in engine.scan_calls), 3)


if __name__ == "__main__":
    unittest.main()
