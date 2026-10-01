"""Immutable TradeIntentV1 and durable intent storage for Live V1."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import Field, ValidationInfo, model_validator

from ..account_watch.models import AccountSnapshotV1
from ..approval.store import LiveStore
from ..decision.models import (
    Hash,
    ImmutableModel,
    content_hash,
)
from ..live_db import connection
from .guard import ExecutionBlocked


class TradeIntentV1(ImmutableModel):
    schema_version: Literal["TRADE_INTENT_V1"] = "TRADE_INTENT_V1"
    intent_id: Annotated[str, Field(min_length=1, max_length=128)]
    intent_hash: str = ""
    case_id: str
    case_hash: Hash
    proposal_id: str
    proposal_hash: Hash
    approval_event_id: str
    approval_actor: str
    approval_hash: Hash
    risk_policy_hash: Hash
    account_snapshot_hash: Hash
    environment: Literal["DRY_RUN", "TESTNET"]
    account_authority: str
    symbol: str
    side: Literal["BUY", "SELL"]
    order_type: Literal["LIMIT", "MARKET"]
    quantity: Annotated[float, Field(gt=0)]
    price: Annotated[float, Field(gt=0)]
    leverage: Annotated[int, Field(ge=1)]
    stop_loss: Annotated[float, Field(gt=0)]
    take_profit_1: Annotated[float, Field(gt=0)]
    take_profit_2: float | None = None
    created_at_ms: Annotated[int, Field(ge=0)]
    expires_at_ms: Annotated[int, Field(gt=0)]
    idempotency_key: str
    client_order_id: str

    @model_validator(mode="after")
    def validate_identity(self, info: ValidationInfo) -> Self:
        if self.created_at_ms >= self.expires_at_ms:
            raise ValueError("intent chronology invalid")
        expected = content_hash(self.model_dump(mode="json", exclude={"intent_hash"}))
        if info.context and info.context.get("build") and not self.intent_hash:
            object.__setattr__(self, "intent_hash", expected)
        elif self.intent_hash != expected:
            raise ValueError("trade intent hash mismatch")
        return self

    @classmethod
    def build(cls, **values: Any) -> Self:
        return cls.model_validate(values, context={"build": True})

    def verify(self) -> None:
        self.model_validate_json(self.canonical_json())


def build_trade_intent(
    live_store: LiveStore,
    account_snapshot: AccountSnapshotV1,
    proposal_hash: str,
    approval_event_id: str,
    *,
    allowed_approvers: frozenset[str] | None = None,
    now_ms: int,
    idempotency_key: str | None = None,
    client_order_id: str | None = None,
) -> TradeIntentV1:
    account_snapshot.verify()
    if account_snapshot.quality != "OK" or not account_snapshot.reconciled:
        raise ExecutionBlocked("account snapshot is not reconciled or degraded")

    proposal = live_store.get_proposal(proposal_hash)
    proposal.verify()

    case = live_store.get_case(proposal.case_id)
    case.verify()

    if case.case_hash != proposal.case_hash:
        raise ExecutionBlocked("proposal case hash mismatch")

    active_proposal = live_store.active_proposal(case.case_id)
    if active_proposal is None or active_proposal.proposal_hash != proposal.proposal_hash:
        raise ExecutionBlocked("proposal is not active on case")

    if now_ms >= case.expires_at_ms or now_ms >= proposal.expires_at_ms:
        raise ExecutionBlocked("proposal or case has expired")

    if proposal.requires_manual_review or proposal.blocked_reasons:
        raise ExecutionBlocked("proposal requires manual review or is blocked")

    if proposal.recommended_notional_usdt <= 0:
        raise ExecutionBlocked("proposal has zero or negative recommended notional")

    with live_store._connection() as db:
        row = db.execute(
            "SELECT action, actor, proposal_hash, case_hash, at_ms, result_state "
            "FROM approval_records WHERE event_id=?",
            (approval_event_id,),
        ).fetchone()

    if row is None:
        raise ExecutionBlocked("approval record not found")

    if (
        row["action"] != "APPROVE"
        or row["proposal_hash"] != proposal.proposal_hash
        or row["case_hash"] != case.case_hash
    ):
        raise ExecutionBlocked("approval record does not match proposal or case")

    actor = str(row["actor"])
    if allowed_approvers is not None and actor not in allowed_approvers:
        raise ExecutionBlocked(f"approver '{actor}' is not authorized")

    approval_dict = {
        "event_id": approval_event_id,
        "action": row["action"],
        "actor": actor,
        "proposal_hash": proposal.proposal_hash,
        "case_hash": case.case_hash,
        "at_ms": int(row["at_ms"]),
    }
    approval_hash = content_hash(approval_dict)

    if proposal.action in ("OPEN_LONG", "ADD"):
        side = "BUY"
    elif proposal.action == "OPEN_SHORT":
        side = "SELL"
    else:
        raise ExecutionBlocked(f"unsupported proposal action for intent: {proposal.action}")

    midpoint = (proposal.entry_low + proposal.entry_high) / 2.0
    price = round(midpoint, 2)
    quantity = round(proposal.recommended_notional_usdt / price, 4) if price > 0 else 0.0

    if quantity <= 0:
        raise ExecutionBlocked("computed order quantity must be positive")

    intent_seed = secrets.token_hex(12)
    intent_id = f"intent-{intent_seed}"
    idem_key = idempotency_key or f"idem-{intent_seed}"
    client_oid = client_order_id or f"bqa-{intent_seed[:16]}"

    env_val: Literal["DRY_RUN", "TESTNET"] = (
        "TESTNET" if account_snapshot.environment == "TESTNET" else "DRY_RUN"
    )

    return TradeIntentV1.build(
        intent_id=intent_id,
        case_id=case.case_id,
        case_hash=case.case_hash,
        proposal_id=proposal.proposal_id,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=approval_event_id,
        approval_actor=actor,
        approval_hash=approval_hash,
        risk_policy_hash=proposal.risk_policy_hash,
        account_snapshot_hash=account_snapshot.snapshot_hash,
        environment=env_val,
        account_authority=account_snapshot.account_id,
        symbol=case.symbol,
        side=side,
        order_type="LIMIT",
        quantity=quantity,
        price=price,
        leverage=proposal.leverage,
        stop_loss=proposal.stop_loss,
        take_profit_1=proposal.take_profit_1,
        take_profit_2=proposal.take_profit_2 if proposal.take_profit_2 > 0 else None,
        created_at_ms=now_ms,
        expires_at_ms=min(case.expires_at_ms, proposal.expires_at_ms),
        idempotency_key=idem_key,
        client_order_id=client_oid,
    )


class IntentStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with connection(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS live_trade_intents (
                    intent_id TEXT PRIMARY KEY,
                    intent_hash TEXT NOT NULL UNIQUE,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    client_order_id TEXT NOT NULL UNIQUE,
                    proposal_hash TEXT NOT NULL,
                    case_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_intents_proposal ON live_trade_intents(proposal_hash);
                CREATE INDEX IF NOT EXISTS idx_intents_idempotency ON live_trade_intents(idempotency_key);
                CREATE TABLE IF NOT EXISTS live_intent_transitions (
                    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent_id TEXT NOT NULL REFERENCES live_trade_intents(intent_id),
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    at_ms INTEGER NOT NULL
                );
            """)

    def save_intent(self, intent: TradeIntentV1, status: str = "PENDING_VALIDATION") -> None:
        intent.verify()
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO live_trade_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    intent.intent_id,
                    intent.intent_hash,
                    intent.idempotency_key,
                    intent.client_order_id,
                    intent.proposal_hash,
                    intent.case_hash,
                    status,
                    intent.created_at_ms,
                    intent.canonical_json(),
                ),
            )
            db.execute(
                "INSERT INTO live_intent_transitions(intent_id, from_status, to_status, reason, at_ms) "
                "VALUES (?, NULL, ?, 'CREATED', ?)",
                (intent.intent_id, status, intent.created_at_ms),
            )

    def get_intent(self, intent_id: str) -> TradeIntentV1 | None:
        with connection(self.path) as db:
            row = db.execute(
                "SELECT payload FROM live_trade_intents WHERE intent_id=?", (intent_id,)
            ).fetchone()
            if row is None:
                return None
            return TradeIntentV1.model_validate(json.loads(row["payload"]))

    def get_intent_by_idempotency_key(self, idempotency_key: str) -> TradeIntentV1 | None:
        with connection(self.path) as db:
            row = db.execute(
                "SELECT payload FROM live_trade_intents WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if row is None:
                return None
            return TradeIntentV1.model_validate(json.loads(row["payload"]))

    def update_status(self, intent_id: str, new_status: str, reason: str = "", now_ms: int = 0) -> None:
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM live_trade_intents WHERE intent_id=?", (intent_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown intent: {intent_id}")
            old = row["status"]
            db.execute("UPDATE live_trade_intents SET status=? WHERE intent_id=?", (new_status, intent_id))
            db.execute(
                "INSERT INTO live_intent_transitions(intent_id, from_status, to_status, reason, at_ms) "
                "VALUES (?, ?, ?, ?, ?)",
                (intent_id, old, new_status, reason, now_ms),
            )
