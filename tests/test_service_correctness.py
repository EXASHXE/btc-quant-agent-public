import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from helpers import candles, signal

from btc_quant_agent.config import AppConfig, NotifyConfig, StorageConfig
from btc_quant_agent.domain import DerivativesSnapshot, ScanResult, SignalStatus
from btc_quant_agent.service import QuantService
from btc_quant_agent.storage import Repository


class FakeClient:
    def server_time_ms(self) -> int:
        return 1_800_000

    def klines(self, _symbol: str, interval: str, _limit: int):
        sizes = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
        return candles(2, interval, sizes[interval])

    def derivatives(
        self, _symbol: str, *, include_order_book: bool = False
    ) -> DerivativesSnapshot:
        return DerivativesSnapshot(observed_at_ms=1_800_000)


class ServiceCorrectnessTests(unittest.TestCase):
    def test_pushed_active_signal_is_invalidated_and_notified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "service.db")
            config = AppConfig(
                storage=StorageConfig(sqlite_path=path),
                notify=NotifyConfig(feishu_enabled=True),
            )
            repo = Repository(path)
            item = replace(
                signal(),
                data_timestamp_ms=899_999,
                created_at_ms=900_000,
                expires_at_ms=3_600_000,
            )
            repo.save_signal(item, 90)
            repo.mark_signal_notified(item.signal_id, 900_000)
            service = QuantService(config, repo, FakeClient(), Mock())  # type: ignore[arg-type]
            with (
                patch.dict("os.environ", {"FEISHU_WEBHOOK_URL": "https://example.invalid"}),
                patch(
                    "btc_quant_agent.service.QuantEngine.invalidation_reason",
                    return_value="REGIME_REVERSED",
                ),
                patch(
                    "btc_quant_agent.service.QuantEngine.scan",
                    return_value=ScanResult("WAIT", "OK", "no setup", reason_code="NO_SETUP"),
                ),
                patch("btc_quant_agent.service.send_invalidation") as notify,
            ):
                result = service.scan(notify=False)
            stored = repo.get_signal(item.signal_id)
            assert stored
            self.assertEqual(result.reason_code, "NO_SETUP")
            self.assertEqual(stored.status, SignalStatus.INVALIDATED)
            self.assertEqual(stored.invalidation_reason, "REGIME_REVERSED")
            notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
