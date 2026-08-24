import sqlite3
import tempfile
import unittest
from pathlib import Path

from helpers import signal

from btc_quant_agent.domain import SignalStatus, UserDecision
from btc_quant_agent.storage import Repository


class StorageTests(unittest.TestCase):
    def test_connection_is_closed_on_success_and_exception(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Repository(str(Path(directory) / "test.db"))
            with repo._connect() as connection:
                connection.execute("SELECT 1")
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

            with self.assertRaisesRegex(RuntimeError, "boom"), repo._connect() as failed_connection:
                raise RuntimeError("boom")
            with self.assertRaises(sqlite3.ProgrammingError):
                failed_connection.execute("SELECT 1")

    def test_dedup_decision_and_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Repository(str(Path(directory) / "test.db"))
            item = signal()
            self.assertTrue(repo.save_signal(item, 90))
            self.assertFalse(repo.save_signal(item, 90))
            repo.mark_decision(item.signal_id, UserDecision.ACCEPT, 99.5, 100_000)
            self.assertEqual(repo.expire_signals(item.expires_at_ms + 1), 1)
            stored = repo.get_signal(item.signal_id)
            self.assertIsNotNone(stored)
            assert stored
            self.assertEqual(stored.status, SignalStatus.EXPIRED)

    def test_invalidation_reason_and_notification_timestamp_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Repository(str(Path(directory) / "test.db"))
            item = signal()
            repo.save_signal(item, 90)
            repo.mark_signal_notified(item.signal_id, 123_000)
            repo.invalidate_signal(item.signal_id, "REGIME_REVERSED")
            stored = repo.get_signal(item.signal_id)
            assert stored
            self.assertEqual(stored.status, SignalStatus.INVALIDATED)
            self.assertEqual(stored.invalidation_reason, "REGIME_REVERSED")
            self.assertEqual(stored.notified_at_ms, 123_000)


if __name__ == "__main__":
    unittest.main()
