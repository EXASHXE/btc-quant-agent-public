"""Durable, short-lived pre-execution receipts; never exchange credentials."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Self

from pydantic import ValidationInfo, model_validator

from ..account_watch.models import AccountSnapshotV1
from ..account_watch.store import AccountStore
from ..decision.models import Hash, ImmutableModel, content_hash
from ..live_db import connection
from ..live_market.models import MarketObservationV1
from .guard import ExecutionBlocked
from .intents import IntentStore, TradeIntentV1


class PreExecutionAuthorizationV1(ImmutableModel):
    authorization_id: str
    authorization_hash: str = ""
    intent_id: str
    intent_hash: Hash
    proposal_hash: Hash
    case_hash: Hash
    approval_event_id: str
    approval_hash: Hash
    risk_policy_hash: Hash
    account_snapshot_hash: Hash
    market_observation_hash: Hash
    execution_compilation_hash: Hash
    environment: Literal["TESTNET"]
    validated_at_ms: int
    expires_at_ms: int
    validator_version: Literal["PRE_EXECUTION_VALIDATOR_R2"] = "PRE_EXECUTION_VALIDATOR_R2"

    @model_validator(mode="after")
    def identity(self, info: ValidationInfo) -> Self:
        if not 0 <= self.validated_at_ms < self.expires_at_ms:
            raise ValueError("authorization chronology invalid")
        digest = content_hash(self.model_dump(mode="json", exclude={"authorization_hash"}))
        if info.context and info.context.get("build") and not self.authorization_hash:
            object.__setattr__(self, "authorization_hash", digest)
        elif self.authorization_hash != digest:
            raise ValueError("authorization hash mismatch")
        return self

    @classmethod
    def build(cls, **values: Any) -> Self:
        return cls.model_validate(values, context={"build": True})


class AuthorizationStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        IntentStore(self.path)
        AccountStore(self.path)
        with connection(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS live_execution_market_observations (
                    observation_hash TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS live_pre_execution_authorizations (
                    authorization_id TEXT PRIMARY KEY, authorization_hash TEXT NOT NULL UNIQUE,
                    intent_id TEXT NOT NULL REFERENCES live_trade_intents(intent_id),
                    status TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS live_execution_claims (
                    intent_id TEXT PRIMARY KEY REFERENCES live_trade_intents(intent_id),
                    authorization_id TEXT NOT NULL REFERENCES live_pre_execution_authorizations(authorization_id),
                    claimed_at_ms INTEGER NOT NULL);
            """)

    def issue(
        self, intent: TradeIntentV1, account: AccountSnapshotV1,
        market: MarketObservationV1, executable: dict[str, Any],
        now_ms: int, expires_at_ms: int,
    ) -> PreExecutionAuthorizationV1:
        account.verify()
        MarketObservationV1.model_validate_json(market.canonical_json())
        values = {
            "intent_id": intent.intent_id, "intent_hash": intent.intent_hash,
            "proposal_hash": intent.proposal_hash, "case_hash": intent.case_hash,
            "approval_event_id": intent.approval_event_id, "approval_hash": intent.approval_hash,
            "risk_policy_hash": intent.risk_policy_hash,
            "account_snapshot_hash": account.snapshot_hash,
            "market_observation_hash": market.observation_hash,
            "execution_compilation_hash": content_hash(executable),
            "environment": "TESTNET", "validated_at_ms": now_ms, "expires_at_ms": expires_at_ms,
        }
        auth = PreExecutionAuthorizationV1.build(authorization_id="auth_" + content_hash(values)[:32], **values)
        AccountStore(self.path).save(account)
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT intent_hash, status FROM live_trade_intents WHERE intent_id=?", (intent.intent_id,)).fetchone()
            if row is None or row["intent_hash"] != intent.intent_hash:
                raise ExecutionBlocked("AUTHORIZATION_INTENT_NOT_PERSISTED")
            if row["status"] not in {"PENDING_VALIDATION", "AUTHORIZED", "VALIDATED"}:
                raise ExecutionBlocked("INTENT_NOT_ELIGIBLE_FOR_AUTHORIZATION")
            db.execute("INSERT OR IGNORE INTO live_execution_market_observations VALUES (?,?)", (market.observation_hash, market.canonical_json()))
            db.execute("INSERT OR IGNORE INTO live_pre_execution_authorizations VALUES (?,?,?,'ISSUED',?)", (auth.authorization_id, auth.authorization_hash, intent.intent_id, auth.canonical_json()))
            db.execute("UPDATE live_trade_intents SET status='AUTHORIZED' WHERE intent_id=?", (intent.intent_id,))
            db.execute("INSERT INTO live_intent_transitions(intent_id,from_status,to_status,reason,at_ms) VALUES (?,?,'AUTHORIZED','PRE_EXECUTION_VALIDATED',?)", (intent.intent_id, row["status"], now_ms))
        return auth

    def load(self, authorization_id: str) -> tuple[PreExecutionAuthorizationV1, TradeIntentV1, AccountSnapshotV1, MarketObservationV1]:
        try:
            with connection(self.path) as db:
                row = db.execute("SELECT * FROM live_pre_execution_authorizations WHERE authorization_id=?", (authorization_id,)).fetchone()
                if row is None:
                    raise ExecutionBlocked("AUTHORIZATION_NOT_FOUND")
                auth = PreExecutionAuthorizationV1.model_validate_json(row["payload"])
                if (auth.authorization_id != authorization_id or auth.authorization_hash != row["authorization_hash"] or auth.intent_id != row["intent_id"]):
                    raise ExecutionBlocked("AUTHORIZATION_HASH_MISMATCH")
                account_row = db.execute("SELECT payload FROM live_account_snapshots WHERE snapshot_hash=?", (auth.account_snapshot_hash,)).fetchone()
                market_row = db.execute("SELECT payload FROM live_execution_market_observations WHERE observation_hash=?", (auth.market_observation_hash,)).fetchone()
            if account_row is None or market_row is None:
                raise ExecutionBlocked("AUTHORIZATION_OBSERVATION_NOT_FOUND")
            account = AccountSnapshotV1.model_validate_json(account_row["payload"])
            market = MarketObservationV1.model_validate_json(market_row["payload"])
            intent = IntentStore(self.path).get_intent(auth.intent_id)
            if intent is None:
                raise ExecutionBlocked("AUTHORIZATION_INTENT_NOT_PERSISTED")
            if (account.snapshot_hash != auth.account_snapshot_hash or market.observation_hash != auth.market_observation_hash
                    or intent.intent_hash != auth.intent_hash or intent.environment != auth.environment
                    or intent.proposal_hash != auth.proposal_hash or intent.case_hash != auth.case_hash
                    or intent.approval_event_id != auth.approval_event_id or intent.approval_hash != auth.approval_hash
                    or intent.risk_policy_hash != auth.risk_policy_hash):
                raise ExecutionBlocked("AUTHORIZATION_BINDING_MISMATCH")
            return auth, intent, account, market
        except ExecutionBlocked:
            raise
        except Exception:  # noqa: BLE001 - persisted corruption fails closed without raw payloads
            raise ExecutionBlocked("AUTHORIZATION_HASH_MISMATCH") from None

    def for_claimed_intent(self, intent_id: str) -> str:
        with connection(self.path) as db:
            row = db.execute("SELECT authorization_id FROM live_execution_claims WHERE intent_id=?", (intent_id,)).fetchone()
        if row is None:
            raise ExecutionBlocked("AUTHORIZATION_REQUIRED")
        return str(row["authorization_id"])

    def claim(self, auth: PreExecutionAuthorizationV1, now_ms: int) -> bool:
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT authorization_id FROM live_execution_claims WHERE intent_id=?", (auth.intent_id,)).fetchone()
            if existing is not None:
                return False
            row = db.execute("SELECT intent_hash,status FROM live_trade_intents WHERE intent_id=?", (auth.intent_id,)).fetchone()
            receipt = db.execute("SELECT authorization_hash,status FROM live_pre_execution_authorizations WHERE authorization_id=?", (auth.authorization_id,)).fetchone()
            if (row is None or receipt is None or row["intent_hash"] != auth.intent_hash
                    or receipt["authorization_hash"] != auth.authorization_hash
                    or row["status"] != "AUTHORIZED" or receipt["status"] != "ISSUED"):
                raise ExecutionBlocked("AUTHORIZATION_NOT_VALIDATED")
            db.execute("INSERT INTO live_execution_claims VALUES (?,?,?)", (auth.intent_id, auth.authorization_id, now_ms))
            db.execute("UPDATE live_pre_execution_authorizations SET status='CLAIMED' WHERE authorization_id=?", (auth.authorization_id,))
            db.execute("UPDATE live_trade_intents SET status='SUBMITTING' WHERE intent_id=?", (auth.intent_id,))
            db.execute("INSERT INTO live_intent_transitions(intent_id,from_status,to_status,reason,at_ms) VALUES (?,'AUTHORIZED','SUBMITTING','AUTHORIZATION_CLAIMED',?)", (auth.intent_id, now_ms))
            return True
