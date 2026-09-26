from __future__ import annotations

import os
from typing import Any

from ..config import DataConfig
from ..data.binance import BinancePublicClient
from .alerting import send_test_market_watch_alert
from .config import MarketWatchConfig
from .domain import SymbolAssessment
from .scanner import MarketWatchScanner
from .state import MarketWatchStateStore


class MarketWatchService:
    """Production service facade for isolated MarketWatch operational subsystem."""

    def __init__(
        self,
        config: MarketWatchConfig,
        client: BinancePublicClient,
        store: MarketWatchStateStore,
    ) -> None:
        self.config = config
        self.client = client
        self.store = store
        self.scanner = MarketWatchScanner(config, client, store)

    @classmethod
    def create(cls, config: MarketWatchConfig | None = None) -> MarketWatchService:
        cfg = config or MarketWatchConfig()
        client = BinancePublicClient(DataConfig())
        store = MarketWatchStateStore(cfg.sqlite_path)
        return cls(cfg, client, store)

    def scan(
        self,
        symbols: list[str] | None = None,
        notify: bool = False,
    ) -> list[SymbolAssessment]:
        assessments, _ = self.scanner.scan_universe(symbols=symbols, notify=notify)
        return assessments

    def status(self, symbol: str | None = None) -> list[dict[str, Any]] | dict[str, Any]:
        if symbol is not None:
            st = self.store.get_symbol_state(symbol.upper())
            return st or {"symbol": symbol.upper(), "status": "NO_STATE_RECORDED"}
        return self.store.get_all_states()

    def top(self, limit: int = 5) -> list[dict[str, Any]]:
        states = self.store.get_all_states()
        return states[:limit]

    def explain(self, symbol: str) -> dict[str, Any]:
        """Output structured reason and risk codes for a symbol without LLM prose."""
        state = self.store.get_symbol_state(symbol.upper())
        if state is None:
            return {"symbol": symbol.upper(), "status": "NO_STATE_RECORDED"}

        return {
            "symbol": symbol.upper(),
            "regime": state.get("regime"),
            "directional_decision": state.get("directional_decision"),
            "grid_decision": state.get("grid_decision"),
            "derivatives_regime": state.get("derivatives_regime"),
            "entry_quality": state.get("entry_quality"),
            "recent_support": state.get("recent_support"),
            "recent_resistance": state.get("recent_resistance"),
            "recent_failed_breakout": state.get("recent_failed_breakout"),
            "recent_failed_breakdown": state.get("recent_failed_breakdown"),
            "lifecycle_state": state.get("lifecycle_state"),
            "rank": state.get("last_rank"),
            "last_alert_fingerprint": state.get("last_alert_fingerprint"),
            "last_alert_time_ms": state.get("last_alert_time_ms"),
            "updated_at_ms": state.get("updated_at_ms"),
        }

    def test_feishu(self, symbol: str = "BTCUSDT") -> dict[str, Any]:
        """Send a non-trading connectivity test card to Feishu webhook."""
        webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
        secret = os.getenv("FEISHU_WEBHOOK_SECRET")

        if not webhook_url:
            return {
                "status": "FAILED",
                "error": "FEISHU_WEBHOOK_URL environment variable is not configured",
            }

        try:
            send_test_market_watch_alert(webhook_url, secret)
            return {
                "status": "SUCCESS",
                "message": "MARKET WATCH FEISHU CONNECTIVITY TEST succeeded",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "FAILED",
                "error": str(exc),
            }
