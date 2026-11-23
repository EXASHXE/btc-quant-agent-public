"""Locked production lifecycle. Phase A intentionally has no provisioned trust."""

from __future__ import annotations

import json
import os
from pathlib import Path

from quant_personal_public_b1.clock import SystemClock
from quant_personal_public_b1.policy import SourceBlocked, require
from quant_personal_public_b1.runtime import run_identity

from .admission import Adapter
from .approval import load_local_json, verify_envelope
from .collection import collect
from .contract import GENUINE, SYMBOL_ORDER
from .decision import DecisionJournal, engine
from .egress import PhysicalTransport, check_local_route
from .enrollment import enroll_once
from .ledger import Active, B5Store, Ledger, secure_storage
from .release import verify_release
from .trust import production_roots


def _load(wheel, scope, activation, clock, *, historical=False):
    roots = production_roots()
    require(os.geteuid() == roots.local_uid, "RUNTIME_PRINCIPAL_MISMATCH")
    scope_raw = load_local_json(scope)
    envelope = load_local_json(activation)
    require(type(envelope) is dict and type(envelope.get("claims")) is dict, "ACTIVATION_CLAIMS_INVALID")
    release = envelope["claims"].get("release_sha256")
    approval = verify_envelope(envelope, scope_raw, roots, release, clock.sample().wall_ms, historical=historical)
    require(approval.scope.stage_plan is not None and approval.scope.journal != roots.enrollment.path,
            "H2A_STAGED_SCOPE_REQUIRED")
    verify_release(wheel, approval.release)
    return roots, approval, envelope, scope_raw


def provision_reviewed_state(wheel: Path, scope: Path, activation: Path):
    """Local post-review provisioning; the delivered Phase A wheel has no trust roots."""
    roots = production_roots()
    roots, approval, envelope, raw_scope = _load(wheel, scope, activation, SystemClock())
    check_local_route(approval.scope.route)
    secure_storage(roots.state_path, roots.local_uid, creating=True)
    ledger = enroll_once(roots.enrollment, roots.local_uid, approval, roots.state_path, lambda: Ledger._create(
        roots.state_path, GENUINE, approval, envelope=envelope, raw_scope=raw_scope))
    return {"state": "AVAILABLE", "scope_sha256": approval.scope.sha256, "run_id": ledger.run_id}


def _active(wheel, scope, activation, *, recovery=False):
    production_roots()
    clock, identity = SystemClock(), run_identity()
    roots, approval, _, _ = _load(wheel, scope, activation, clock, historical=recovery)
    if not recovery:
        check_local_route(approval.scope.route)
    secure_storage(roots.state_path, roots.local_uid)
    ledger = Ledger(B5Store(roots.state_path, GENUINE, roots.egress_id))
    with ledger.store.connect() as db:
        ledger.verify_registration(db, approval, roots)
    return Active(ledger, approval, clock, identity, roots=roots)


def preflight(wheel, scope, activation):
    active = _active(wheel, scope, activation)
    active.check_available()
    secure_storage(active.approval.scope.journal, active.roots.local_uid, creating=True)
    PhysicalTransport(active)  # Verifies the installed system trust bundle without opening a socket.
    return {"state": "REGISTERED_AVAILABLE", "scope_sha256": active.approval.scope.sha256,
            "phase_limits": list(active.approval.scope.phase_limits)}


def revoke(wheel, scope, activation):
    """An authenticated local stop remains available without the network route or a current TTL."""
    active = _active(wheel, scope, activation, recovery=True)
    return {"state": active.revoke(), "run_id": active.ledger.run_id}


def open_historical(wheel):
    roots = production_roots()
    secure_storage(roots.state_path, roots.local_uid)
    ledger = Ledger(B5Store(roots.state_path, GENUINE, roots.egress_id))
    with ledger.store.connect() as db:
        row = ledger.control(db)
        approval = verify_envelope(json.loads(row["approval"]), json.loads(row["scope"]),
                                   roots, row["release_sha"], 0, historical=True)
        ledger.verify_registration(db, approval, roots)
    verify_release(wheel, approval.release)
    secure_storage(approval.scope.journal, roots.local_uid)
    return Adapter(ledger, approval=approval, roots=roots), approval.scope.journal


def live_once(wheel, scope, activation, *, progress):
    active = _active(wheel, scope, activation)
    ledger, approval, roots = active.ledger, active.approval, active.roots
    journal = approval.scope.journal
    plan = approval.scope.stage_plan
    with ledger.store.collector():
        active.check_available()
        secure_storage(journal, roots.local_uid, creating=True)
        transport = PhysicalTransport(active)
        active.claim()
        try:
            adapter = None
            if plan.market_allowed:
                if not journal.exists():
                    fd = os.open(journal,os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY,0o600)
                    os.close(fd)
                secure_storage(journal,roots.local_uid)
                qualified = DecisionJournal(journal,GENUINE,create=True)
                require(qualified.read() is None,"JOURNAL_ALREADY_IN_USE")
                adapter = Adapter(ledger,approval=approval,roots=roots)
            progress({"stage":"CANARY","state":"COLLECTING"})
            publication = collect(active,"bootstrap",transport,SYMBOL_ORDER,
                                  notify_stage=lambda: progress({"stage":"MARKET","state":"COLLECTING"}))
            as_of = publication["visible_venue_upper_ms"]
            cards = []
            if as_of is not None and adapter is not None:
                evaluator = engine(adapter,journal)
                cards = [evaluator.evaluate(symbol,scan=publication["scan_id"],as_of_ms=as_of)
                         for symbol in SYMBOL_ORDER]
            final_stage = publication["stage"]
            result = {"run_id":ledger.run_id, "scan_id":publication["scan_id"], "one_shot_consumed":True,
                      "canary_passed":final_stage.get("activation_gate") is not None,
                      "source_status":"SOURCE_BLOCKED" if final_stage["issue"] else
                          "COLLECTED" if cards else "NOT_EVALUATED",
                      "source_issue":final_stage["issue"], "stats":final_stage["stats"],
                      "cards":[{"symbol":card["symbol"],"market_status":card["market_status"],
                                "card_id":card["card_id"]} for card in cards]}
            active.close()
            return result
        except BaseException as exc:
            active.close(reason=exc.code if isinstance(exc,SourceBlocked) else type(exc).__name__)
            raise
