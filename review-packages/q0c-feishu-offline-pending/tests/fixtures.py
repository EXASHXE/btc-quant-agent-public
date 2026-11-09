import copy

NOW = 1800000000.0


class FakeClock:
    def __init__(self):
        self.wall = NOW
        self.mono = 1000.0

    def time(self):
        return self.wall

    def monotonic(self):
        return self.mono

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds


def candidate(now=NOW, episode="synthetic-episode-001", kind="ENTRY_READY"):
    return copy.deepcopy({
        "contract_version": "Q0C_ALERT_EVENT_V1", "strategy": "S1_INTRADAY_MTF_V2",
        "episode_id": episode, "transition_id": kind.lower() + "-001", "event_type": kind,
        "channel": "FEISHU_MOCK", "eligible_at": now, "expires_at": now + 120,
        "source": {"name": "OFFLINE_FIXTURE", "observed_at": now, "received_at": now,
                   "trusted": True, "admitted": True, "quality": "GOOD"},
        "account_status": "UNKNOWN",
        "watermark": {"synthetic": True, "test": True, "label": "SYNTHETIC / TEST ONLY"},
        "dashboard_url": "https://dashboard.invalid/synthetic/episode-001",
        "symbol": "TESTUSDT", "side": "LONG", "regime_4h": {"value": "BULLISH", "admitted": True},
        "setup_1h": {"completed": True, "valid": True, "closed_at": now - 600},
        "confirmation_15m": {"completed": True, "valid": True, "closed_at": now - 30},
        "quote": {"price": 100, "as_of": now, "received_at": now, "trusted": True,
                  "current": True, "gate_passed": True, "path_admitted": True},
        "plan": {"entry_area": [99, 101], "hard_stop": 95,
                 "take_profits": [{"price": 115, "weight": 1, "rationale": "synthetic prior resistance"}],
                 "after_cost_r": 2.8,
                 "model": {"entry_reference": 100, "fee_bps_round_trip": 10,
                           "slippage_bps_round_trip": 10, "min_after_cost_r": 2,
                           "assumptions": "Synthetic fixed bps; no fill/liquidity guarantee; hypothetical resistance."}},
        "candidate_expires_at": now + 1200,
        "invalidation": {"condition": "price crosses hard stop or setup invalidates",
                         "triggered": False, "reason": "not triggered"},
        "human_delay": {"min_seconds": 300, "max_seconds": 600, "assessed_at": now,
                        "valid_until": now + 1200, "feasible": True,
                        "worst_entry_at_5m": 100.5, "worst_entry_at_10m": 101,
                        "after_cost_r_at_5m": 2.4, "after_cost_r_at_10m": 2.2,
                        "assumptions": "Synthetic bounded path stays in entry area for 600s; no live prediction."}})


def degraded(now=NOW, episode="system:offline-source:001"):
    e = candidate(now, episode)
    keep = {"contract_version", "strategy", "episode_id", "transition_id", "event_type", "channel",
            "eligible_at", "expires_at", "source", "account_status", "watermark", "dashboard_url"}
    e = {k: v for k, v in e.items() if k in keep}
    e.update(event_type="SYSTEM_DEGRADED", transition_id="degraded-001", reason="Synthetic source delay")
    e["source"]["quality"] = "DEGRADED"
    return e
