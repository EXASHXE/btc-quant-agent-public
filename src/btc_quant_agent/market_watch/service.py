from __future__ import annotations

import json
import os
import time
from typing import Any

from ..config import DataConfig
from ..data.binance import BinancePublicClient
from .alerting import send_test_market_watch_alert
from .config import MarketWatchConfig
from .domain import SymbolAssessment
from .scanner import MarketWatchScanner
from .shadow import ShadowDecisionRecorder
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
        self.shadow_recorder = ShadowDecisionRecorder(store)

    @classmethod
    def create(
        cls,
        config: MarketWatchConfig | None = None,
        data_config: DataConfig | None = None,
    ) -> MarketWatchService:
        cfg = config or MarketWatchConfig()
        dcfg = data_config or DataConfig()
        client = BinancePublicClient(dcfg)
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
        latest_asmt = self.store.get_latest_assessment(symbol.upper())
        if state is None and latest_asmt is None:
            return {"symbol": symbol.upper(), "status": "NO_STATE_RECORDED"}

        reason_codes: list[str] = []
        risk_codes: list[str] = []
        veto_reasons: list[str] = []
        grid_codes: list[str] = []
        snapshot_hash = ""
        policy_version = ""
        config_hash = ""
        playbook = state.get("breakout_state", "NO_TRADE") if state else "NO_TRADE"
        entry_quality = state.get("entry_quality", "POOR") if state else "POOR"
        derivatives_state = state.get("derivatives_regime", "BALANCED") if state else "BALANCED"
        benchmark_context = "NEUTRAL"

        if latest_asmt:
            snapshot_hash = latest_asmt.get("snapshot_hash", "")
            policy_version = latest_asmt.get("policy_version", "")
            config_hash = latest_asmt.get("config_hash", "")
            playbook = latest_asmt.get("setup", playbook)
            entry_quality = latest_asmt.get("entry_quality", entry_quality)
            derivatives_state = latest_asmt.get("derivatives_regime", derivatives_state)
            benchmark_context = latest_asmt.get("benchmark_context", "NEUTRAL")
            try:
                reason_codes = json.loads(latest_asmt.get("reason_codes_json", "[]"))
            except (json.JSONDecodeError, TypeError):
                reason_codes = []
            try:
                risk_codes = json.loads(latest_asmt.get("risk_codes_json", "[]"))
            except (json.JSONDecodeError, TypeError):
                risk_codes = []
            try:
                dec = json.loads(latest_asmt.get("decision_json", "{}"))
                veto_reasons = dec.get("veto_reasons", [])
                grid_codes = dec.get("grid", {}).get("reason_codes", dec.get("grid", {}).get("reasons", []))
            except (json.JSONDecodeError, TypeError):
                veto_reasons = []
                grid_codes = []

        return {
            "symbol": symbol.upper(),
            "policy_version": policy_version,
            "config_hash": config_hash,
            "snapshot_hash": snapshot_hash,
            "regime": state.get("regime") if state else (latest_asmt.get("regime") if latest_asmt else None),
            "playbook": playbook,
            "directional_decision": state.get("directional_decision") if state else (latest_asmt.get("directional_decision") if latest_asmt else None),
            "grid_decision": state.get("grid_decision") if state else (latest_asmt.get("grid_decision") if latest_asmt else None),
            "entry_quality": entry_quality,
            "derivatives_regime": derivatives_state,
            "benchmark_context": benchmark_context,
            "opportunity_score": latest_asmt.get("opportunity_score") if latest_asmt else None,
            "reason_codes": reason_codes,
            "risk_codes": risk_codes,
            "veto_reasons": veto_reasons,
            "grid_codes": grid_codes,
            "grid_reason_codes": grid_codes,
            "recent_support": state.get("recent_support") if state else None,
            "recent_resistance": state.get("recent_resistance") if state else None,
            "recent_failed_breakout": state.get("recent_failed_breakout") if state else None,
            "recent_failed_breakdown": state.get("recent_failed_breakdown") if state else None,
            "lifecycle_state": state.get("lifecycle_state") if state else None,
            "rank": state.get("last_rank") if state else (latest_asmt.get("rank") if latest_asmt else None),
            "last_alert_fingerprint": state.get("last_alert_fingerprint") if state else (latest_asmt.get("alert_fingerprint") if latest_asmt else None),
            "last_alert_time_ms": state.get("last_alert_time_ms") if state else None,
            "updated_at_ms": state.get("updated_at_ms") if state else (latest_asmt.get("decision_time_ms") if latest_asmt else None),
        }

    def shadow_status(self) -> dict[str, Any]:
        """Return status and resolution metrics of shadow observation tracking."""
        return self.shadow_recorder.get_status()

    def shadow_resolve(self) -> dict[str, Any]:
        """Resolve pending shadow observations against subsequent closed candles."""
        now_ms = int(time.time() * 1000)
        res = self.shadow_recorder.resolve_pending_observations(self.client, now_ms)
        return {
            "status": "SUCCESS",
            "resolved_count": res.get("resolved_count", 0),
            "pending_count": res.get("pending_count", 0),
            "results": res.get("results", []),
            "summary": self.shadow_recorder.get_status(),
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
