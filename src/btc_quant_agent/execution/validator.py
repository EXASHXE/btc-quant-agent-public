"""Pre-execution validator enforcing strict deterministic safety gates immediately before order submission."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..account_watch.models import AccountSnapshotV1
from ..approval.store import LiveStore
from ..decision.models import content_hash
from ..decision.risk import RiskPolicyV1
from ..live_db import connection
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
        risk_policy: RiskPolicyV1 | None = None,
        tactical_validity_provider: Callable[[str, int], bool] | None = None,
        max_market_staleness_ms: int = 15_000,
        max_account_staleness_ms: int = 60_000,
        max_spread_bps: float = 10.0,
        max_price_drift_bps: float = 50.0,
    ) -> None:
        self.live_store = live_store
        self.intent_store = intent_store
        self.kill_switch = kill_switch
        self.risk_policy = risk_policy or RiskPolicyV1()
        self.tactical_validity_provider = tactical_validity_provider
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

        active_proposal = self.live_store.active_proposal(case.case_id)
        if active_proposal is None or active_proposal.proposal_hash != proposal.proposal_hash:
            return ValidationResult(is_valid=False, reason="PROPOSAL_NOT_ACTIVE")

        # 5. Approval revalidation
        with self.live_store._connection() as db:
            row = db.execute(
                "SELECT action, actor, proposal_hash, case_hash, at_ms FROM approval_records WHERE event_id=?",
                (intent.approval_event_id,),
            ).fetchone()
        if row is None:
            return ValidationResult(is_valid=False, reason="APPROVAL_RECORD_NOT_FOUND")
        if row["action"] != "APPROVE":
            return ValidationResult(is_valid=False, reason="APPROVAL_NOT_APPROVED")
        if row["actor"] != intent.approval_actor:
            return ValidationResult(is_valid=False, reason="APPROVAL_ACTOR_MISMATCH")
        if row["proposal_hash"] != intent.proposal_hash:
            return ValidationResult(is_valid=False, reason="APPROVAL_PROPOSAL_HASH_MISMATCH")
        if row["case_hash"] != intent.case_hash:
            return ValidationResult(is_valid=False, reason="APPROVAL_CASE_HASH_MISMATCH")

        approval_dict = {
            "event_id": intent.approval_event_id,
            "action": row["action"],
            "actor": row["actor"],
            "proposal_hash": row["proposal_hash"],
            "case_hash": row["case_hash"],
            "at_ms": int(row["at_ms"]),
        }
        if content_hash(approval_dict) != intent.approval_hash:
            return ValidationResult(is_valid=False, reason="APPROVAL_HASH_MISMATCH")

        # 6. Current Account snapshot verification (recalculated from fresh current snapshot)
        try:
            account_snapshot.verify()
        except Exception:  # noqa: BLE001
            return ValidationResult(is_valid=False, reason="ACCOUNT_SNAPSHOT_HASH_MISMATCH")

        if account_snapshot.environment != intent.environment:
            return ValidationResult(is_valid=False, reason="ACCOUNT_ENVIRONMENT_MISMATCH")
        if account_snapshot.account_id != intent.account_authority:
            return ValidationResult(is_valid=False, reason="ACCOUNT_AUTHORITY_MISMATCH")
        if not account_snapshot.reconciled or account_snapshot.quality != "OK":
            return ValidationResult(is_valid=False, reason="ACCOUNT_UNRECONCILED")
        if (now_ms - account_snapshot.observed_at_ms) > self.max_account_staleness_ms:
            return ValidationResult(is_valid=False, reason="ACCOUNT_SNAPSHOT_STALE")

        # 8. Risk Policy authority check
        bound_policy_hash = content_hash(self.risk_policy.model_dump(mode="json"))
        if intent.risk_policy_hash != bound_policy_hash:
            return ValidationResult(is_valid=False, reason="RISK_POLICY_HASH_MISMATCH")

        notional = intent.quantity * intent.price
        if notional > self.risk_policy.max_notional_usdt:
            return ValidationResult(is_valid=False, reason="MAX_NOTIONAL_CAP_EXCEEDED")
        if intent.leverage > self.risk_policy.max_leverage:
            return ValidationResult(is_valid=False, reason="MAX_LEVERAGE_EXCEEDED")

        margin_required = notional / intent.leverage
        if account_snapshot.available_balance_usdt < margin_required:
            return ValidationResult(is_valid=False, reason="INSUFFICIENT_MARGIN")

        max_daily_loss = min(
            self.kill_switch.policy.daily_loss_cap_usdt,
            account_snapshot.equity_usdt * self.risk_policy.max_daily_loss_pct,
        )
        if account_snapshot.daily_loss_usdt >= max_daily_loss:
            return ValidationResult(is_valid=False, reason="DAILY_LOSS_CAP_REACHED")

        max_drawdown = min(
            self.kill_switch.policy.drawdown_cap_pct,
            self.risk_policy.drawdown_kill_pct,
        )
        if account_snapshot.drawdown_pct >= max_drawdown:
            return ValidationResult(is_valid=False, reason="DRAWDOWN_CAP_REACHED")

        # Symbol & portfolio exposure headroom recalculated against current account snapshot
        current_symbol_exp = sum(
            abs(p.quantity * p.mark_price) for p in account_snapshot.positions if p.symbol == intent.symbol
        )
        max_symbol_exp = account_snapshot.equity_usdt * self.risk_policy.max_symbol_exposure_pct
        if (current_symbol_exp + notional) > max_symbol_exp:
            return ValidationResult(is_valid=False, reason="SYMBOL_EXPOSURE_CAP_EXCEEDED")

        current_portfolio_exp = sum(
            abs(p.quantity * p.mark_price) for p in account_snapshot.positions
        )
        max_portfolio_exp = account_snapshot.equity_usdt * self.risk_policy.max_portfolio_exposure_pct
        if (current_portfolio_exp + notional) > max_portfolio_exp:
            return ValidationResult(is_valid=False, reason="PORTFOLIO_EXPOSURE_CAP_EXCEEDED")

        # Simultaneous positions limit
        has_symbol_position = any(p.quantity != 0 for p in account_snapshot.positions if p.symbol == intent.symbol)
        current_open_positions = sum(1 for p in account_snapshot.positions if p.quantity != 0)
        new_open_positions = current_open_positions if has_symbol_position else current_open_positions + 1
        if new_open_positions > self.risk_policy.max_simultaneous_positions:
            return ValidationResult(is_valid=False, reason="SIMULTANEOUS_POSITIONS_LIMIT_EXCEEDED")

        # Current open orders conflict
        for order in account_snapshot.orders:
            if (
                order.symbol == intent.symbol
                and order.side != intent.side
                and order.status in {"NEW", "PARTIALLY_FILLED"}
            ):
                return ValidationResult(is_valid=False, reason="OPEN_ORDER_CONFLICT")
            if (
                order.client_order_id == intent.client_order_id
                and order.status in {"NEW", "PARTIALLY_FILLED", "FILLED"}
            ):
                return ValidationResult(is_valid=False, reason="DUPLICATE_CLIENT_ORDER_ID_ON_EXCHANGE")

        # Conflicting opposite position
        for pos in account_snapshot.positions:
            if (
                pos.symbol == intent.symbol
                and ((intent.side == "BUY" and pos.quantity < 0) or (intent.side == "SELL" and pos.quantity > 0))
            ):
                return ValidationResult(is_valid=False, reason="CONFLICTING_POSITION_EXISTS")

        # 9. Market data verification
        if market_obs.symbol != intent.symbol:
            return ValidationResult(is_valid=False, reason="MARKET_SYMBOL_MISMATCH")
        if (now_ms - market_obs.receipt_timestamp_ms) > self.max_market_staleness_ms:
            return ValidationResult(is_valid=False, reason="MARKET_DATA_STALE")

        effective_max_spread = min(self.max_spread_bps, float(self.risk_policy.max_spread_bps))
        if market_obs.spread_bps > effective_max_spread:
            return ValidationResult(is_valid=False, reason="SPREAD_TOO_WIDE")

        drift_bps = abs(market_obs.mark_price - intent.price) / intent.price * 10_000
        allowed_drift = min(
            self.max_price_drift_bps,
            proposal.allowed_price_drift_bps or self.max_price_drift_bps,
            float(self.risk_policy.allowed_price_drift_bps),
        )
        if drift_bps > allowed_drift:
            return ValidationResult(is_valid=False, reason="PRICE_DRIFT_EXCEEDED")

        # 10. Duplicate intent check (local database)
        existing = self.intent_store.get_intent_by_idempotency_key(intent.idempotency_key)
        if existing is not None and existing.intent_id != intent.intent_id:
            return ValidationResult(is_valid=False, reason="DUPLICATE_IDEMPOTENCY_KEY")

        with connection(self.intent_store.path) as db:
            row = db.execute(
                "SELECT intent_id FROM live_trade_intents WHERE client_order_id=? AND intent_id != ?",
                (intent.client_order_id, intent.intent_id),
            ).fetchone()
            if row is not None:
                return ValidationResult(is_valid=False, reason="DUPLICATE_CLIENT_ORDER_ID_LOCAL")

        # 11. Current Tactical validity
        if intent.environment == "TESTNET":
            if self.tactical_validity_provider is None:
                return ValidationResult(is_valid=False, reason="TACTICAL_VALIDITY_UNAVAILABLE")
            try:
                is_tactical_valid = self.tactical_validity_provider(intent.symbol, now_ms)
            except Exception:  # noqa: BLE001
                return ValidationResult(is_valid=False, reason="TACTICAL_VALIDITY_UNAVAILABLE")
            if not is_tactical_valid:
                return ValidationResult(is_valid=False, reason="TACTICAL_VALIDITY_INVALID")
        elif self.tactical_validity_provider is not None:
            try:
                is_tactical_valid = self.tactical_validity_provider(intent.symbol, now_ms)
            except Exception:  # noqa: BLE001
                return ValidationResult(is_valid=False, reason="TACTICAL_VALIDITY_UNAVAILABLE")
            if not is_tactical_valid:
                return ValidationResult(is_valid=False, reason="TACTICAL_VALIDITY_INVALID")

        return ValidationResult(is_valid=True, reason="OK")
