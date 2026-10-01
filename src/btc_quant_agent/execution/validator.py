"""Pre-execution validator enforcing strict deterministic safety gates immediately before order submission."""

from __future__ import annotations

from dataclasses import dataclass

from ..account_watch.models import AccountSnapshotV1
from ..approval.store import LiveStore
from ..live_market.models import MarketObservationV1
from ..position_supervisor.kill_switch import KillSwitch
from .intents import IntentStore, TradeIntentV1


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    reason: str


class PreExecutionValidator:
    def __init__(
        self,
        live_store: LiveStore,
        intent_store: IntentStore,
        kill_switch: KillSwitch,
        max_market_staleness_ms: int = 15_000,
        max_account_staleness_ms: int = 60_000,
        max_spread_bps: float = 10.0,
        max_price_drift_bps: float = 50.0,
    ) -> None:
        self.live_store = live_store
        self.intent_store = intent_store
        self.kill_switch = kill_switch
        self.max_market_staleness_ms = max_market_staleness_ms
        self.max_account_staleness_ms = max_account_staleness_ms
        self.max_spread_bps = max_spread_bps
        self.max_price_drift_bps = max_price_drift_bps

    def validate(
        self,
        intent: TradeIntentV1,
        market_obs: MarketObservationV1,
        account_snapshot: AccountSnapshotV1,
        now_ms: int,
    ) -> ValidationResult:
        # 1. Intent integrity
        try:
            intent.verify()
        except Exception:  # noqa: BLE001
            return ValidationResult(is_valid=False, reason="INTENT_HASH_MISMATCH")

        # 2. TTL
        if now_ms >= intent.expires_at_ms:
            return ValidationResult(is_valid=False, reason="INTENT_EXPIRED")

        # 3. Kill switch
        if not self.kill_switch.allows_new_risk():
            return ValidationResult(is_valid=False, reason="KILL_SWITCH_ACTIVE")

        # 4. Proposal & Case verification
        try:
            proposal = self.live_store.get_proposal(intent.proposal_hash)
            case = self.live_store.get_case(intent.case_id)
        except KeyError:
            return ValidationResult(is_valid=False, reason="PROPOSAL_OR_CASE_NOT_FOUND")

        if case.case_hash != intent.case_hash:
            return ValidationResult(is_valid=False, reason="CASE_HASH_MISMATCH")
        if proposal.proposal_hash != intent.proposal_hash:
            return ValidationResult(is_valid=False, reason="PROPOSAL_HASH_MISMATCH")
        if now_ms >= case.expires_at_ms or now_ms >= proposal.expires_at_ms:
            return ValidationResult(is_valid=False, reason="PROPOSAL_OR_CASE_EXPIRED")
        if proposal.requires_manual_review or proposal.blocked_reasons:
            return ValidationResult(is_valid=False, reason="PROPOSAL_BLOCKED")

        # 5. Approval verification
        with self.live_store._connection() as db:
            row = db.execute(
                "SELECT action, proposal_hash, case_hash FROM approval_records WHERE event_id=?",
                (intent.approval_event_id,),
            ).fetchone()
        if (
            row is None
            or row["action"] != "APPROVE"
            or row["proposal_hash"] != intent.proposal_hash
            or row["case_hash"] != intent.case_hash
        ):
            return ValidationResult(is_valid=False, reason="APPROVAL_INVALID")

        # 6. Account snapshot verification
        try:
            account_snapshot.verify()
        except Exception:  # noqa: BLE001
            return ValidationResult(is_valid=False, reason="ACCOUNT_SNAPSHOT_HASH_MISMATCH")

        if account_snapshot.snapshot_hash != intent.account_snapshot_hash:
            return ValidationResult(is_valid=False, reason="ACCOUNT_SNAPSHOT_HASH_MISMATCH")
        if account_snapshot.environment != intent.environment:
            return ValidationResult(is_valid=False, reason="ACCOUNT_ENVIRONMENT_MISMATCH")
        if account_snapshot.account_id != intent.account_authority:
            return ValidationResult(is_valid=False, reason="ACCOUNT_AUTHORITY_MISMATCH")
        if not account_snapshot.reconciled or account_snapshot.quality != "OK":
            return ValidationResult(is_valid=False, reason="ACCOUNT_UNRECONCILED")
        if (now_ms - account_snapshot.observed_at_ms) > self.max_account_staleness_ms:
            return ValidationResult(is_valid=False, reason="ACCOUNT_SNAPSHOT_STALE")

        # 7. Market data verification
        if market_obs.symbol != intent.symbol:
            return ValidationResult(is_valid=False, reason="MARKET_SYMBOL_MISMATCH")
        if (now_ms - market_obs.receipt_timestamp_ms) > self.max_market_staleness_ms:
            return ValidationResult(is_valid=False, reason="MARKET_DATA_STALE")
        if market_obs.spread_bps > self.max_spread_bps:
            return ValidationResult(is_valid=False, reason="SPREAD_TOO_WIDE")

        drift_bps = abs(market_obs.mark_price - intent.price) / intent.price * 10_000
        allowed_drift = min(self.max_price_drift_bps, proposal.allowed_price_drift_bps or self.max_price_drift_bps)
        if drift_bps > allowed_drift:
            return ValidationResult(is_valid=False, reason="PRICE_DRIFT_EXCEEDED")

        # 8. Available margin and risk limits
        margin_required = (intent.quantity * intent.price) / intent.leverage
        if account_snapshot.available_balance_usdt < margin_required:
            return ValidationResult(is_valid=False, reason="INSUFFICIENT_MARGIN")

        if account_snapshot.daily_loss_usdt >= self.kill_switch.policy.daily_loss_cap_usdt:
            return ValidationResult(is_valid=False, reason="DAILY_LOSS_CAP_REACHED")
        if account_snapshot.drawdown_pct >= self.kill_switch.policy.drawdown_cap_pct:
            return ValidationResult(is_valid=False, reason="DRAWDOWN_CAP_REACHED")

        # Conflicting opposite position
        for pos in account_snapshot.positions:
            if (
                pos.symbol == intent.symbol
                and ((intent.side == "BUY" and pos.quantity < 0) or (intent.side == "SELL" and pos.quantity > 0))
            ):
                return ValidationResult(is_valid=False, reason="CONFLICTING_POSITION_EXISTS")

        # 9. Duplicate intent check
        existing = self.intent_store.get_intent_by_idempotency_key(intent.idempotency_key)
        if existing is not None and existing.intent_id != intent.intent_id:
            return ValidationResult(is_valid=False, reason="DUPLICATE_IDEMPOTENCY_KEY")

        return ValidationResult(is_valid=True, reason="OK")
