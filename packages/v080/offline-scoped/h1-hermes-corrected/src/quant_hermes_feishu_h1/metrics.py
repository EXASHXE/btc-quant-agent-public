"""Local-only mock timeline & performance metrics collector (explicitly labeled synthetic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any

from .contract import EVIDENCE_SYNTHETIC, SYNTHETIC_BANNER


@dataclass
class AlertTimelineMeasurement:
    """Single synthetic end-to-end notification + chat response timeline."""

    episode_id: str
    card_id: str
    symbol: str
    market_status: str
    source_as_of_ms: int | None
    verified_card_at_ms: int
    outbox_created_at_ms: int
    attempt_start_at_ms: int | None
    provider_ack_at_ms: int | None
    inbound_request_at_ms: int | None
    status_recheck_at_ms: int | None
    reply_sent_at_ms: int | None
    tool_latency_ms: float
    queue_delay_ms: float
    model_latency_ms: float
    delivery_state: str
    reprice_plus5_status: str | None = None
    reprice_plus10_status: str | None = None
    explanation_consistent: bool | None = None


@dataclass
class LocalPerformanceReport:
    """Aggregated offline H1 telemetry clearly separating simulated vs local CPU timings."""

    evidence_class: str = EVIDENCE_SYNTHETIC
    banner: str = SYNTHETIC_BANNER
    timelines: list[AlertTimelineMeasurement] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=lambda: {
        "cards_verified": 0,
        "alerts_enqueued": 0,
        "alerts_deduplicated": 0,
        "alerts_provider_ack": 0,
        "alerts_suppressed_stale_or_superseded": 0,
        "alerts_expired": 0,
        "alerts_missed_or_blocked": 0,
        "alerts_unknown_delivery": 0,
        "alerts_retryable": 0,
        "alerts_permanent": 0,
        "explanation_validated": 0,
        "explanation_fallbacks": 0,
        "model_quota_or_provider_errors": 0,
        "gateway_reconnect_events": 0,
        "inbound_commands_ok": 0,
        "inbound_commands_rejected": 0,
    })
    synthetic_actionability_denominator: int = 0
    synthetic_plus5_actionable_numerator: int = 0
    synthetic_plus10_actionable_numerator: int = 0

    def inc(self, key: str, delta: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + delta

    def add_timeline(self, item: AlertTimelineMeasurement) -> None:
        self.timelines.append(item)

    def summary(self) -> dict[str, Any]:
        tool_latencies = [t.tool_latency_ms for t in self.timelines]
        queue_delays = [t.queue_delay_ms for t in self.timelines]
        model_latencies = [t.model_latency_ms for t in self.timelines if t.model_latency_ms > 0]

        def _p95(vals: list[float]) -> float:
            if not vals:
                return 0.0
            s = sorted(vals)
            idx = min(len(s) - 1, max(0, round(0.95 * (len(s) - 1))))
            return round(s[idx], 3)

        denom = self.synthetic_actionability_denominator
        return {
            "evidence_class": self.evidence_class,
            "banner": self.banner,
            "measurement_nature": "OFFLINE_SYNTHETIC_LOCAL_ONLY",
            "claims": {
                "real_feishu_delivery_measured": False,
                "real_human_response_delay_measured": False,
                "live_market_alpha_or_pnl_proven": False,
            },
            "counters": dict(self.counters),
            "synthetic_actionability": {
                "denominator_episodes": denom,
                "plus5_executable_count": self.synthetic_plus5_actionable_numerator,
                "plus10_executable_count": self.synthetic_plus10_actionable_numerator,
                "plus5_rate": round(self.synthetic_plus5_actionable_numerator / denom, 4) if denom else None,
                "plus10_rate": round(self.synthetic_plus10_actionable_numerator / denom, 4) if denom else None,
                "label": "SYNTHETIC_QA_ONLY_DENOMINATOR",
            },
            "latency_summary_ms": {
                "local_tool_p50_ms": round(median(tool_latencies), 3) if tool_latencies else 0.0,
                "local_tool_p95_ms": _p95(tool_latencies),
                "simulated_queue_delay_p50_ms": round(median(queue_delays), 3) if queue_delays else 0.0,
                "simulated_queue_delay_p95_ms": _p95(queue_delays),
                "mock_model_p50_ms": round(median(model_latencies), 3) if model_latencies else 0.0,
                "mock_model_p95_ms": _p95(model_latencies),
            },
            "timelines": [
                {
                    "episode_id": t.episode_id,
                    "card_id": t.card_id,
                    "symbol": t.symbol,
                    "market_status": t.market_status,
                    "source_as_of_ms": t.source_as_of_ms,
                    "verified_card_at_ms": t.verified_card_at_ms,
                    "outbox_created_at_ms": t.outbox_created_at_ms,
                    "attempt_start_at_ms": t.attempt_start_at_ms,
                    "provider_ack_at_ms": t.provider_ack_at_ms,
                    "inbound_request_at_ms": t.inbound_request_at_ms,
                    "status_recheck_at_ms": t.status_recheck_at_ms,
                    "reply_sent_at_ms": t.reply_sent_at_ms,
                    "tool_latency_ms": t.tool_latency_ms,
                    "queue_delay_ms": t.queue_delay_ms,
                    "model_latency_ms": t.model_latency_ms,
                    "delivery_state": t.delivery_state,
                    "reprice_plus5_status": t.reprice_plus5_status,
                    "reprice_plus10_status": t.reprice_plus10_status,
                    "explanation_consistent": t.explanation_consistent,
                }
                for t in self.timelines
            ],
        }
