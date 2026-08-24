import tempfile
import unittest
from pathlib import Path

from helpers import signal

from btc_quant_agent.domain import Candle, SignalStatus
from btc_quant_agent.shadow import update_shadow
from btc_quant_agent.storage import Repository


class ShadowTests(unittest.TestCase):
    def test_unfilled_signal_stays_pending_until_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Repository(str(Path(directory) / "test.db"))
            item = signal()
            repo.save_signal(item, 90)
            bar = Candle("BTCUSDT", "1m", 60_000, 119_999, 110, 111, 109, 110, 1)
            self.assertEqual(update_shadow(repo, [bar], 120_000), [])
            stored = repo.get_signal(item.signal_id)
            assert stored
            self.assertEqual(stored.status, SignalStatus.ACTIVE)
            resolved = update_shadow(repo, [bar], item.expires_at_ms + 1)
            self.assertEqual(resolved[0]["outcome"], "UNFILLED")
            stored = repo.get_signal(item.signal_id)
            assert stored
            self.assertEqual(stored.status, SignalStatus.EXPIRED)


if __name__ == "__main__":
    unittest.main()
