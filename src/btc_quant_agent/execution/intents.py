"""Immutable TradeIntentV1 and durable intent storage for Live V1."""

from __future__ import annotations

import hashlib
import json
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import Field, ValidationInfo, model_validator

from ..account_watch.models import AccountSnapshotV1
from ..account_watch.store import AccountStore
from ..approval.store import LiveStore
from ..decision.models import (
    CasePackageV1,
    Hash,
    ImmutableModel,
    TradeProposalV1,
    content_hash,
)
from ..decision.risk import RiskPolicyV1
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
        expected_ids = canonical_execution_identity(
            self.case_hash, self.proposal_hash, self.approval_event_id,
        )
        if (self.intent_id, self.idempotency_key, self.client_order_id) != expected_ids:
            raise ValueError("trade intent canonical identity mismatch")
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


def canonical_execution_identity(
    case_hash: str, proposal_hash: str, approval_event_id: str,
) -> tuple[str, str, str]:
    authority_hash = hashlib.sha256(
        f"{case_hash}:{proposal_hash}:{approval_event_id}".encode()
    ).hexdigest()
    return (
        f"intent_{authority_hash[:24]}",
        f"idem_{authority_hash[:24]}",
        f"cuid_v1_{authority_hash[:16]}",
    )


def compile_executable_intent_fields(
    case: CasePackageV1, proposal: TradeProposalV1,
    account_snapshot: AccountSnapshotV1, risk_policy: RiskPolicyV1 | None = None,
) -> dict[str, Any]:
    """The single approved executable contract, shared by builder and validator."""
    case.verify()
    proposal.verify()
    account_snapshot.verify()
    if proposal.case_id != case.case_id or proposal.case_hash != case.case_hash:
        raise ExecutionBlocked("EXECUTABLE_CASE_BINDING_MISMATCH")
    if risk_policy is not None and proposal.risk_policy_hash != risk_policy.policy_hash:
        raise ExecutionBlocked("RISK_POLICY_HASH_MISMATCH")
    if proposal.action not in {"OPEN_LONG", "OPEN_SHORT", "ADD"}:
        raise ExecutionBlocked("UNSUPPORTED_EXECUTABLE_ACTION")
    side = "SELL" if case.direction == "SHORT" else "BUY"
    if (proposal.action == "OPEN_LONG" and side != "BUY"
            or proposal.action == "OPEN_SHORT" and side != "SELL"):
        raise ExecutionBlocked("EXECUTABLE_DIRECTION_MISMATCH")
    if account_snapshot.environment == "TESTNET":
        if (account_snapshot.credential_namespace != "BINANCE_TESTNET"
                or account_snapshot.rest_base_url != "https://testnet.binancefuture.com"):
            raise ExecutionBlocked("EXECUTABLE_ACCOUNT_AUTHORITY_MISMATCH")
    elif (account_snapshot.environment != "DRY_RUN"
          or account_snapshot.credential_namespace != "NONE"
          or account_snapshot.rest_base_url != "local://paper"):
        raise ExecutionBlocked("EXECUTABLE_ACCOUNT_AUTHORITY_MISMATCH")
    price = round((proposal.entry_low + proposal.entry_high) / 2.0, 2)
    if price <= 0 or not proposal.entry_low <= price <= proposal.entry_high:
        raise ExecutionBlocked("EXECUTABLE_PRICE_INVALID")
    quantity = float((Decimal(str(proposal.recommended_notional_usdt)) / Decimal(str(price)))
                     .quantize(Decimal("0.0001"), rounding=ROUND_DOWN))
    if quantity <= 0:
        raise ExecutionBlocked("computed order quantity must be positive")
    return {
        "symbol": case.symbol, "side": side, "order_type": "LIMIT",
        "price": price, "quantity": quantity, "leverage": proposal.leverage,
        "stop_loss": proposal.stop_loss, "take_profit_1": proposal.take_profit_1,
        "take_profit_2": proposal.take_profit_2 if proposal.take_profit_2 > 0 else None,
        "risk_policy_hash": proposal.risk_policy_hash,
        "environment": account_snapshot.environment,
        "account_authority": account_snapshot.account_id,
    }


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
    intent_store: IntentStore | None = None,
    risk_policy: RiskPolicyV1 | None = None,
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

    executable = compile_executable_intent_fields(case, proposal, account_snapshot, risk_policy)
    AccountStore(live_store.path).save(account_snapshot)

    # One approval authority (case_hash, proposal_hash, approval_event_id)
    # maps deterministically to exactly one executable TradeIntent authority
    intent_id, idem_key, client_oid = canonical_execution_identity(
        case.case_hash, proposal.proposal_hash, approval_event_id,
    )
    if idempotency_key is not None and idempotency_key != idem_key:
        raise ExecutionBlocked("NONCANONICAL_IDEMPOTENCY_KEY")
    if client_order_id is not None and client_order_id != client_oid:
        raise ExecutionBlocked("NONCANONICAL_CLIENT_ORDER_ID")

    if intent_store is not None:
        existing = intent_store.get_intent_by_approval_event(approval_event_id)
        if existing is not None:
            return existing

    return TradeIntentV1.build(
        intent_id=intent_id,
        case_id=case.case_id,
        case_hash=case.case_hash,
        proposal_id=proposal.proposal_id,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=approval_event_id,
        approval_actor=actor,
        approval_hash=approval_hash,
        account_snapshot_hash=account_snapshot.snapshot_hash,
        created_at_ms=now_ms,
        expires_at_ms=min(case.expires_at_ms, proposal.expires_at_ms),
        idempotency_key=idem_key,
        client_order_id=client_oid,
        **executable,
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
                    approval_event_id TEXT NOT NULL UNIQUE,
                    proposal_hash TEXT NOT NULL,
                    case_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_intents_approval ON live_trade_intents(approval_event_id);
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
            row = db.execute(
                "SELECT intent_hash, payload FROM live_trade_intents WHERE approval_event_id=? OR intent_id=?",
                (intent.approval_event_id, intent.intent_id),
            ).fetchone()
            if row is not None:
                if row["intent_hash"] == intent.intent_hash:
                    return  # Identical replay returns existing identical authority
                raise ExecutionBlocked(f"divergent intent for approval event {intent.approval_event_id}")

            db.execute(
                "INSERT INTO live_trade_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    intent.intent_id,
                    intent.intent_hash,
                    intent.idempotency_key,
                    intent.client_order_id,
                    intent.approval_event_id,
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

    def get_intent_by_approval_event(self, approval_event_id: str) -> TradeIntentV1 | None:
        with connection(self.path) as db:
            row = db.execute(
                "SELECT * FROM live_trade_intents WHERE approval_event_id=?", (approval_event_id,)
            ).fetchone()
            if row is None:
                return None
            return self._verified_row(row)

    def get_intent(self, intent_id: str) -> TradeIntentV1 | None:
        with connection(self.path) as db:
            row = db.execute(
                "SELECT * FROM live_trade_intents WHERE intent_id=?", (intent_id,)
            ).fetchone()
            if row is None:
                return None
            return self._verified_row(row)

    def get_intent_by_idempotency_key(self, idempotency_key: str) -> TradeIntentV1 | None:
        with connection(self.path) as db:
            row = db.execute(
                "SELECT * FROM live_trade_intents WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if row is None:
                return None
            return self._verified_row(row)

    @staticmethod
    def _verified_row(row: Any) -> TradeIntentV1:
        intent = TradeIntentV1.model_validate(json.loads(row["payload"]))
        for key in ("intent_id", "intent_hash", "approval_event_id", "client_order_id", "idempotency_key", "proposal_hash", "case_hash"):
            if getattr(intent, key) != row[key]:
                raise ExecutionBlocked("PERSISTED_INTENT_IDENTITY_MISMATCH")
        return intent

    def unfinished_intent_ids(self) -> tuple[str, ...]:
        # Durable claims/order identities survive stale legacy ABORTED transitions.
        with connection(self.path) as db:
            rows = db.execute("SELECT intent_id FROM live_trade_intents ORDER BY created_at_ms").fetchall()
        return tuple(str(row["intent_id"]) for row in rows
                     if self.has_existing_side_effect(str(row["intent_id"])))

    def has_existing_side_effect(self, intent_id: str) -> bool:
        """Whether an intent must reconcile before any new-entry gates run."""
        with connection(self.path) as db:
            row = db.execute("SELECT status FROM live_trade_intents WHERE intent_id=?", (intent_id,)).fetchone()
            if row is None:
                return False
            tables = {r["name"] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('live_execution_claims','live_execution_orders','live_protection_owners')"
            ).fetchall()}
            if row["status"] in {"FILLED", "CANCELED", "EXPIRED", "REJECTED", "ABORTED"} and "live_protection_owners" in tables:
                released = db.execute("SELECT intent_hash FROM live_protection_owners WHERE intent_id=? AND status='RELEASED'",
                                      (intent_id,)).fetchone()
                persisted = self.get_intent(intent_id)
                if released is not None and persisted is not None and released["intent_hash"] == persisted.intent_hash:
                    return False
            if row["status"] in {"SUBMITTING", "UNKNOWN", "NEW", "PARTIALLY_FILLED", "FILLED"}:
                return True
            if "live_execution_claims" in tables and db.execute(
                "SELECT 1 FROM live_execution_claims WHERE intent_id=? LIMIT 1", (intent_id,)
            ).fetchone() is not None:
                return True
            return "live_execution_orders" in tables and db.execute(
                "SELECT 1 FROM live_execution_orders WHERE intent_id=? AND is_protective=0 LIMIT 1",
                (intent_id,),
            ).fetchone() is not None

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
