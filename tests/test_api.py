import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from helpers import signal

from btc_quant_agent import api
from btc_quant_agent.config import AppConfig, StorageConfig
from btc_quant_agent.domain import SignalStatus
from btc_quant_agent.storage import Repository


class ApiCorrectnessTests(unittest.TestCase):
    @staticmethod
    def _endpoint(app: object, path: str, method: str):
        return next(
            route.endpoint
            for route in app.routes  # type: ignore[attr-defined]
            if getattr(route, "path", None) == path and method in getattr(route, "methods", set())
        )

    def test_signal_routes_expire_before_returning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "api.db")
            config = AppConfig(storage=StorageConfig(sqlite_path=path))
            repo = Repository(path)
            item = signal()
            repo.save_signal(item, 90)
            with patch("btc_quant_agent.api.load_config", return_value=config):
                app = api.create_app()
            latest = self._endpoint(app, "/signals/latest", "GET")()
            shown = self._endpoint(app, "/signals/{signal_id}", "GET")(item.signal_id)
            self.assertEqual(latest["status"], SignalStatus.EXPIRED.value)
            self.assertEqual(shown["status"], SignalStatus.EXPIRED.value)

    def test_performance_days_query_is_applied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = AppConfig(storage=StorageConfig(sqlite_path=str(Path(directory) / "api.db")))
            with (
                patch("btc_quant_agent.api.load_config", return_value=config),
                patch(
                    "btc_quant_agent.storage.Repository.performance",
                    side_effect=lambda since_ms=0: {"since_ms": since_ms},
                ),
            ):
                app = api.create_app()
                before = int(time.time() * 1000) - 7 * 86_400_000
                response = self._endpoint(app, "/performance", "GET")(7)
                after = int(time.time() * 1000) - 7 * 86_400_000
            self.assertGreaterEqual(response["since_ms"], before)
            self.assertLessEqual(response["since_ms"], after)

    def test_performance_rejects_invalid_days(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = AppConfig(storage=StorageConfig(sqlite_path=str(Path(directory) / "api.db")))
            with patch("btc_quant_agent.api.load_config", return_value=config):
                app = api.create_app()
            with self.assertRaises(HTTPException) as raised:
                self._endpoint(app, "/performance", "GET")(0)
            self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
