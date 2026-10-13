"""DurableSidecarSupervisor: Integrates MarketPitPort, BoundedLLMPort, AuthenticatedHumanPort,
FeishuOutboxPort, NoOrderPort, and read-only Codex G1 Engine with crash recovery.

Provides:
- End-to-end synthetic MarketEventV1 -> Proposal -> BoundedLLM -> Ed25519 Human Auth ->
  Sealed Fixture -> G1 Pure Engine -> Feishu Outbox execution.
- Hash-chained sidecar.wal.jsonl linking trace_id, span_id, source_event_hash,
  operator_key_id, bounded_llm_request_hash, final_approval_event_id, and simulated_intent_id.
- At-most-once simulated intent settlement across process crashes (os._exit(91)).
- Explicit documentation that hardware power-loss durability is not proven.
"""

from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
from typing import Any

from scripts.g1_offline_preview_r1.fixtures import bar as g1_bar
from scripts.g1_offline_preview_r1.fixtures import make_fixture as g1_make_fixture
from scripts.g1_offline_preview_r1.model import (
    SafetyViolation,
    canonical,
    decimal,
    digest,
    exact,
    initial_state,
)
from scripts.g1_offline_preview_r1.storage import Engine as G1Engine
from scripts.g1_offline_preview_r1.storage import strict_json

from .authenticated_human_port import (
    APPROVAL_CLASS,
    DEFAULT_ROUTE_ID,
    DEFAULT_WORKTREE_ID,
    AuthenticatedHumanPort,
    compute_operator_context_hash,
    sign_synthetic_operator_decision,
)
from .bounded_llm_port import BoundedLLMPort
from .feishu_outbox_port import FeishuOutboxPort
from .loopback_servers import FakeLoopbackFeishuServer, FakeLoopbackLLMServer
from .market_pit_port import (
    MarketPitPort,
    make_synthetic_market_event_v1_from_g1_bar,
    make_synthetic_market_event_v1_from_g1_funding,
)
from .no_order_port import LoopbackSocketGuard, NoOrderPort, guard_scratch_dir


def make_untrusted_dual_pending_ack_fixture(side: str = "LONG") -> dict[str, Any]:
    """Build a synthetic scenario where STOP triggers before TP1 is ACKed (len(pending_cash) == 2)."""
    sign = 1 if side == "LONG" else -1
    b0 = g1_bar(0, side=side)
    prop = {
        "schema_version": 1,
        "signal_id": f"synthetic-dual-pending-{side.lower()}",
        "source_hash": digest(b0),
        "source_close_at": 59999,
        "decision_at": 60000,
        "side": side,
        "quantity": "0.02",
        "stop": str(30000 - sign * 300),
        "tp1": str(30000 + sign * 300),
        "tp2": str(30000 + sign * 600),
        "horizon_hours": 12,
        "exit_identity": "OFFLINE_TP1_BE_TIME_CAP_V1",
        "expires_at": 180000,
        "version": 1,
    }
    order_id = digest([digest(prop), "SIMULATED_ENTRY"])
    b1 = g1_bar(1, side=side)
    # Bar 2 hits TP1
    b2 = {
        "source": "SYNTHETIC_V1",
        "open_time": 120000,
        "close_time": 179999,
        "available_at": 179999,
        "last_open": str(30000 + sign * 305),
        "last_high": str(30000 + sign * 310),
        "last_low": str(30000 + sign * 295),
        "last_close": str(30000 + sign * 305),
        "mark_close": str(30000 + sign * 305),
    }
    # Bar 3 hits STOP before TP1 is ACKed
    b3 = {
        "source": "SYNTHETIC_V1",
        "open_time": 180000,
        "close_time": 239999,
        "available_at": 239999,
        "last_open": str(30000 - sign * 310),
        "last_high": str(30000 - sign * 295),
        "last_low": str(30000 - sign * 315),
        "last_close": str(30000 - sign * 310),
        "mark_close": str(30000 - sign * 310),
    }
    b4 = g1_bar(4, side=side)
    events = [
        {"id": "BAR-0", "kind": "BAR", "at": 59999, "payload": b0},
        {"id": "PROPOSE-60000", "kind": "PROPOSE", "at": 60000, "payload": prop},
        {
            "id": "ANALYZE-60001",
            "kind": "ANALYZE",
            "at": 60001,
            "payload": {
                "schema_version": 1,
                "signal_id": prop["signal_id"],
                "proposal_hash": digest(prop),
                "source_hash": digest(b0),
                "as_of": 60000,
                "summary": "Offline mocked descriptive risk analysis; no trading authority",
                "risk": "DESCRIPTIVE_ONLY",
            },
        },
        {
            "id": "APPROVE-60002",
            "kind": "APPROVE",
            "at": 60002,
            "payload": {"token_id": f"synthetic-explicit-human-{side.lower()}"},
        },
        {"id": "PLACE-60003", "kind": "PLACE", "at": 60003, "payload": {}},
        {
            "id": "FILL_ENTRY-60004",
            "kind": "FILL_ENTRY",
            "at": 60004,
            "payload": {"fill_id": "entry1"},
        },
        {"id": "BAR-1", "kind": "BAR", "at": 119999, "payload": b1},
        {
            "id": "ACK-120004",
            "kind": "ACK",
            "at": 120004,
            "payload": {"ack_id": "ack-entry", "order_id": order_id, "fill_id": "entry1"},
        },
        {"id": "BAR-2", "kind": "BAR", "at": 179999, "payload": b2},
        {"id": "TP1-179999", "kind": "TP1", "at": 179999, "payload": {"fill_id": "partial1"}},
        {"id": "BAR-3", "kind": "BAR", "at": 239999, "payload": b3},
        {"id": "STOP-239999", "kind": "STOP", "at": 239999, "payload": {"fill_id": "final1"}},
        {"id": "BAR-4", "kind": "BAR", "at": 299999, "payload": b4},
        {
            "id": "ACK-300000",
            "kind": "ACK",
            "at": 300000,
            "payload": {"ack_id": "ack-partial", "order_id": order_id, "fill_id": "partial1"},
        },
        {
            "id": "ACK-300001",
            "kind": "ACK",
            "at": 300001,
            "payload": {"ack_id": "ack-final", "order_id": order_id, "fill_id": "final1"},
        },
    ]
    return {
        "schema_version": 1,
        "fixture_name": f"synthetic-dual-pending-{side.lower()}",
        "synthetic_only": True,
        "scenario_hours": 1,
        "ACK_tail_minutes": 1,
        "trusted_approvals": [],
        "events": events,
    }


class DurableSidecarSupervisor:
    """Coordinates all offline ports and the read-only G1 Engine with crash recovery."""

    def __init__(
        self,
        storage_dir: str | Path,
        *,
        worktree_id: str = DEFAULT_WORKTREE_ID,
        route_id: str = DEFAULT_ROUTE_ID,
        process_epoch: int = 1,
        temporary: bool = False,
    ) -> None:
        self.root = guard_scratch_dir(storage_dir, temporary=temporary)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.g1_dir = self.root / "g1_engine"
        self.sidecar_wal_path = self.root / "sidecar.wal.jsonl"
        if self.sidecar_wal_path.is_symlink():
            raise SafetyViolation("PATH_SYMLINK")
        self.worktree_id = worktree_id
        self.route_id = route_id
        self.process_epoch = process_epoch
        self.temporary = temporary
        self.no_order_port = NoOrderPort()
        self.chain = digest({"wal": "G1G3_SIDECAR_WAL_V1", "worktree": worktree_id})
        self.seq = 0
        self.records: list[dict[str, Any]] = []
        self.settled_intents: dict[str, dict[str, Any]] = {}
        self.recovered_llm_results: dict[str, dict[str, Any]] = {}
        self.funding_port = MarketPitPort()
        self._init_or_recover_sidecar_wal()

    def apply_funding_envelope(self, engine: G1Engine, envelope: dict[str, Any], *, hook=None):
        """Synthetic R4 delivery: the G1 cash WAL, never port memory, owns ACK.

        No wallet/source admission or external dispatch occurs here. A crash
        before ACK requires retry; the reconstructed settlement journal makes
        that retry financially idempotent, even on a fresh supervisor/port.
        """
        if hook:
            hook("before_receipt", envelope)
        ingested = self.funding_port.ingest_envelope(envelope)
        event = ingested["g1_event"]
        if event is None or event["kind"] != "FUNDING_RECEIPT":
            raise SafetyViolation("FUNDING_CONTRACT_INVALID")
        if hook:
            hook("after_receipt", event)
        result = engine.apply(event, hook=hook)
        if hook:
            hook("before_receipt_ack", event)
        ack = {
            "status": result,
            "settlement_id": event["payload"]["settlement_id"],
            "g1_seq": engine.seq,
            "g1_chain": engine.chain,
            "scope": "SYNTHETIC_INTEGRATION_ONLY",
        }
        if hook:
            hook("after_receipt_ack", event)
        return ack

    def _quarantine_sidecar(self, code: str) -> None:
        qdir = self.root / "quarantine"
        qdir.mkdir(exist_ok=True, mode=0o700)
        raw = self.sidecar_wal_path.read_bytes() if self.sidecar_wal_path.exists() else b""
        qname = digest({"code": code, "sha256": hashlib.sha256(raw).hexdigest()})
        (qdir / f"{qname}.sidecar.wal").write_bytes(raw)
        info = {
            "code": code,
            "retained_bytes": len(raw),
            "unsafe_effects_replayed": False,
        }
        (qdir / f"{qname}.sidecar.json").write_text(canonical(info) + "\n", encoding="utf-8")

    def _init_or_recover_sidecar_wal(self) -> None:
        if not self.sidecar_wal_path.exists():
            fd = os.open(
                self.sidecar_wal_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            try:
                header = (
                    canonical({"format": "G1G3_SIDECAR_WAL_V1", "genesis_chain": self.chain}) + "\n"
                ).encode("utf-8")
                os.write(fd, header)
                os.fsync(fd)
            finally:
                os.close(fd)
            return

        try:
            raw = self.sidecar_wal_path.read_bytes()
            if not raw.endswith(b"\n"):
                raise SafetyViolation("SIDECAR_WAL_TRUNCATED")
            lines = raw.decode("utf-8").splitlines()
            if not lines or strict_json(lines[0]) != {
                "format": "G1G3_SIDECAR_WAL_V1",
                "genesis_chain": self.chain,
            }:
                raise SafetyViolation("SIDECAR_WAL_GENESIS_MISMATCH")
            for line in lines[1:]:
                rec = strict_json(line)
                exact(
                    rec,
                    {"seq", "previous", "kind", "payload", "payload_hash", "record_hash"},
                    "SIDECAR_WAL_SCHEMA",
                )
                body = {k: v for k, v in rec.items() if k != "record_hash"}
                if (
                    rec["seq"] != self.seq + 1
                    or rec["previous"] != self.chain
                    or digest(body) != rec["record_hash"]
                ):
                    raise SafetyViolation("SIDECAR_WAL_CHAIN_CORRUPT")
                payload = rec["payload"]
                if digest(payload) != rec["payload_hash"]:
                    raise SafetyViolation("SIDECAR_WAL_PAYLOAD_HASH_MISMATCH")
                self.seq = rec["seq"]
                self.chain = rec["record_hash"]
                self.records.append(rec)
                if rec["kind"] == "LLM_ANALYSIS_RECORDED":
                    self.recovered_llm_results[payload["proposal_hash"]] = payload["llm_result"]
                elif rec["kind"] == "SIMULATED_INTENT_SETTLED":
                    intent_id = payload["simulated_intent_id"]
                    self.settled_intents[intent_id] = payload
        except (SafetyViolation, UnicodeError, OSError) as exc:
            code = exc.code if isinstance(exc, SafetyViolation) else "SIDECAR_WAL_INVALID"
            self._quarantine_sidecar(code)
            raise SafetyViolation(code) from exc

    def _append_sidecar_wal(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {
            "seq": self.seq + 1,
            "previous": self.chain,
            "kind": kind,
            "payload": payload,
            "payload_hash": digest(payload),
        }
        record = {**body, "record_hash": digest(body)}
        raw = (canonical(record) + "\n").encode("utf-8")
        fd = os.open(self.sidecar_wal_path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        try:
            offset = 0
            while offset < len(raw):
                offset += os.write(fd, raw[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
        self.seq = record["seq"]
        self.chain = record["record_hash"]
        self.records.append(record)
        if kind == "LLM_ANALYSIS_RECORDED":
            self.recovered_llm_results[payload["proposal_hash"]] = payload["llm_result"]
        elif kind == "SIMULATED_INTENT_SETTLED":
            self.settled_intents[payload["simulated_intent_id"]] = payload
        return record

    def run_scenario(
        self,
        *,
        side: str = "LONG",
        horizon: int = 24,
        exit_kind: str = "STOP",
        scenario_type: str = "STANDARD_24H",
        allow_loopback: bool = False,
        operator_id: str = "op-alpha",
        key_id: str = "ed25519-offline-op-alpha-v1",
        approval_nonce: str | None = None,
        crash_boundary: str | None = None,
        llm_mode: str = "OK",
        feishu_mode: str = "OK_200",
        feishu_fail_count: int = 0,
    ) -> dict[str, Any]:
        """Execute full offline/loopback sidecar workflow with optional crash injection."""

        def maybe_crash(boundary_name: str) -> None:
            if crash_boundary == boundary_name:
                os._exit(91)

        if scenario_type == "DUAL_PENDING_ACK":
            base_fixture = make_untrusted_dual_pending_ack_fixture(side=side)
        else:
            raw_fix = g1_make_fixture(side=side, horizon=horizon, exit_kind=exit_kind)
            base_fixture = copy.deepcopy(raw_fix)
            base_fixture["trusted_approvals"] = []

        # Extract proposal and first bar from scenario events
        propose_ev = next(e for e in base_fixture["events"] if e["kind"] == "PROPOSE")
        proposal = propose_ev["payload"]
        prop_hash = digest(proposal)
        approve_ev = next(e for e in base_fixture["events"] if e["kind"] == "APPROVE")
        token_id = approve_ev["payload"]["token_id"]
        nonce = approval_nonce or f"nonce-{base_fixture['fixture_name']}-v1"

        # 1. Validate synthetic MarketEventV1 stream through MarketPitPort
        pit_port = MarketPitPort()
        mono_ns = 1_000_000
        seq_num = 0
        validated_events: list[dict[str, Any]] = []
        for ev in base_fixture["events"]:
            if ev["kind"] == "BAR":
                env = make_synthetic_market_event_v1_from_g1_bar(
                    ev, sequence=seq_num, monotonic_ns=mono_ns
                )
                ingested = pit_port.ingest_envelope(env, reference_at_ms=ev["at"])
                validated_events.append(ingested["g1_event"])
                seq_num += 1
                mono_ns += 1_000_000
            elif ev["kind"] == "FUNDING":
                env = make_synthetic_market_event_v1_from_g1_funding(
                    ev, sequence=seq_num, monotonic_ns=mono_ns
                )
                ingested = pit_port.ingest_envelope(env, reference_at_ms=ev["at"])
                validated_events.append(ingested["g1_event"])
                seq_num += 1
                mono_ns += 1_000_000
            else:
                validated_events.append(copy.deepcopy(ev))

        base_fixture["events"] = validated_events

        llm_server: FakeLoopbackLLMServer | None = None
        feishu_server: FakeLoopbackFeishuServer | None = None
        allowed_endpoints: set[tuple[str, int]] = set()

        try:
            if allow_loopback:
                llm_server = FakeLoopbackLLMServer(mode=llm_mode).start()
                feishu_server = FakeLoopbackFeishuServer(
                    mode=feishu_mode, fail_count=feishu_fail_count
                ).start()
                allowed_endpoints.add((llm_server.host, llm_server.port))
                allowed_endpoints.add((feishu_server.host, feishu_server.port))

            with LoopbackSocketGuard(
                allow_loopback=allow_loopback, allowed_endpoints=allowed_endpoints
            ):
                # 2. BoundedLLMPort analysis (idempotent recovery if already recorded before crash)
                if prop_hash in self.recovered_llm_results:
                    llm_result = self.recovered_llm_results[prop_hash]
                else:
                    llm_port = BoundedLLMPort(
                        endpoint_url=llm_server.endpoint_url if llm_server else None,
                        allow_loopback=allow_loopback,
                        allowed_endpoints=allowed_endpoints,
                        no_order_port=self.no_order_port,
                    )
                    offline_mock = (
                        {
                            "schema_version": 1,
                            "model_id": "offline-loopback-analyzer-v1",
                            "request_sha256": digest(
                                llm_port.build_request(
                                    signal_id=proposal["signal_id"],
                                    proposal_hash=prop_hash,
                                    source_hash=proposal["source_hash"],
                                    as_of=proposal["decision_at"],
                                )
                            ),
                            "token_usage": {
                                "prompt_tokens": 32,
                                "completion_tokens": 24,
                                "total_tokens": 56,
                            },
                            "analysis": {
                                "schema_version": 1,
                                "signal_id": proposal["signal_id"],
                                "proposal_hash": prop_hash,
                                "source_hash": proposal["source_hash"],
                                "as_of": proposal["decision_at"],
                                "summary": "Offline mocked descriptive risk analysis; no trading authority",
                                "risk": "DESCRIPTIVE_ONLY",
                            },
                        }
                        if not allow_loopback
                        else None
                    )
                    llm_result = llm_port.analyze(
                        signal_id=proposal["signal_id"],
                        proposal_hash=prop_hash,
                        source_hash=proposal["source_hash"],
                        as_of=proposal["decision_at"],
                        offline_mock_response=offline_mock,
                    )
                    self._append_sidecar_wal(
                        "LLM_ANALYSIS_RECORDED",
                        {
                            "proposal_hash": prop_hash,
                            "bounded_llm_request_hash": llm_result["request_sha256"],
                            "bounded_llm_response_hash": llm_result["response_sha256"],
                            "llm_result": llm_result,
                        },
                    )

                if (
                    llm_result["status"] != "DESCRIPTIVE_ANALYSIS_VERIFIED"
                    or llm_result["analysis"] is None
                ):
                    return {
                        "status": "NO_ACTION_OR_MANUAL_REVIEW",
                        "reason": llm_result["failure_code"],
                        "order_authorized": False,
                        "llm_result": llm_result,
                        "readiness": "OFFLINE_LOOPBACK_ONLY",
                    }

                analysis_payload = llm_result["analysis"]
                ctx_hash = compute_operator_context_hash(
                    source_hash=proposal["source_hash"],
                    proposal_hash=prop_hash,
                    analysis_hash=digest(analysis_payload),
                    worktree_id=self.worktree_id,
                    route_id=self.route_id,
                    process_epoch=self.process_epoch,
                )

                # 3. AuthenticatedHumanPort verification & sealed fixture materialization
                human_port = AuthenticatedHumanPort(
                    self.root,
                    worktree_id=self.worktree_id,
                    route_id=self.route_id,
                    process_epoch=self.process_epoch,
                    temporary=self.temporary,
                )
                signed_decision = sign_synthetic_operator_decision(
                    token_id=token_id,
                    signal_id=proposal["signal_id"],
                    proposal_hash=prop_hash,
                    version=proposal["version"],
                    side=proposal["side"],
                    quantity=proposal["quantity"],
                    issued_at=approve_ev["at"],
                    expires_at=160000,
                    operator_id=operator_id,
                    key_id=key_id,
                    context_hash=ctx_hash,
                    approval_nonce=nonce,
                    decision_class=APPROVAL_CLASS,
                )

                def human_hook(edge_name: str, _rec: dict[str, Any]) -> None:
                    if edge_name == "after_operator_receipt_fsync":
                        maybe_crash("after_operator_receipt_fsync")

                op_receipt = human_port.recover_or_verify_decision(
                    signed_decision,
                    proposal=proposal,
                    analysis=analysis_payload,
                    analysis_at=60001,
                    approve_at=approve_ev["at"],
                    hook=human_hook,
                )
                sealed_fixture, _sealed_path, seal_manifest = human_port.materialize_sealed_fixture(
                    base_fixture, op_receipt
                )

                # 4. Run immutable Codex G1 Engine over the sealed fixture
                init = initial_state(sealed_fixture["trusted_approvals"])
                if scenario_type == "STANDARD_24H":
                    # Preserve exact canonical G1 fixture_identity when matching long_24h/short_24h
                    canonical_g1_fix = g1_make_fixture(
                        side=side, horizon=horizon, exit_kind=exit_kind
                    )
                    init["fixture_identity"] = digest(canonical_g1_fix)
                else:
                    init["fixture_identity"] = seal_manifest["sealed_fixture_sha256"]

                feishu_port = FeishuOutboxPort(
                    self.root,
                    endpoint_url=feishu_server.endpoint_url if feishu_server else None,
                    allow_loopback=allow_loopback,
                    allowed_endpoints=allowed_endpoints,
                    no_order_port=self.no_order_port,
                    temporary=self.temporary,
                )

                ack_seen_count = 0
                with G1Engine(self.g1_dir, init, temporary=True) as engine:
                    for ev in sealed_fixture["events"]:
                        if ev["kind"] == "ANALYZE":
                            ev = {**ev, "payload": copy.deepcopy(analysis_payload)}
                        if ev["kind"] == "APPROVE":
                            maybe_crash("before_approve")

                        def g1_hook(edge: str, current_ev: dict[str, Any]) -> None:
                            nonlocal ack_seen_count
                            k = current_ev["kind"]
                            if k == "APPROVE" and edge == "after_snapshot":
                                maybe_crash("after_approve_before_place")
                            elif k == "FILL_ENTRY" and edge == "after_fsync":
                                maybe_crash("after_simulated_entry")
                            elif k == "TP1" and edge == "after_snapshot":
                                maybe_crash("after_tp1_before_ack")
                            elif k == "STOP" and edge == "after_fsync":
                                maybe_crash("at_stop_before_snapshot")
                            elif k == "STOP" and edge == "after_snapshot":
                                maybe_crash("at_stop_after_snapshot")
                            elif k == "ACK" and edge == "after_fsync":
                                ack_seen_count += 1
                                if scenario_type == "DUAL_PENDING_ACK" and ack_seen_count == 3:
                                    maybe_crash("double_pending_ack")

                        apply_status = engine.apply(ev, hook=g1_hook)

                        if ev["kind"] == "PLACE":
                            intent_id = str(engine.state["order_id"])
                            if intent_id not in self.settled_intents:
                                self._append_sidecar_wal(
                                    "SIMULATED_INTENT_SETTLED",
                                    {
                                        "simulated_intent_id": intent_id,
                                        "proposal_hash": prop_hash,
                                        "final_approval_event_id": approve_ev["id"],
                                        "source_event_hash": proposal["source_hash"],
                                        "operator_key_id": key_id,
                                        "bounded_llm_request_hash": llm_result["request_sha256"],
                                        "trace_id": digest([intent_id, "intent_trace"])[:24],
                                        "span_id": digest([intent_id, "intent_span"])[:16],
                                        "apply_status": apply_status,
                                    },
                                )
                            maybe_crash("after_place_before_entry")

                        # Deliver outbox messages when no mandatory exit is pending
                        if (
                            ev["kind"] not in ("BAR", "OUTBOX_RECEIPT")
                            and engine.state.get("required_exit") is None
                            and engine.state.get("outbox")
                        ):
                            latest_row = engine.state["outbox"][-1]
                            card = feishu_port.build_card_from_g1_outbox_row(latest_row)

                            row_kind = latest_row["event_kind"]

                            def feishu_hook(
                                f_edge: str,
                                _entry: dict[str, Any],
                                _rk: str = row_kind,
                            ) -> None:
                                if f_edge == "after_feishu_wal_fsync" and _rk == "APPROVE":
                                    maybe_crash("after_feishu_ack")

                            feishu_port.deliver_card(card, hook=feishu_hook)

                    engine.checkpoint()
                    engine.deliver()
                    g1_receipt = engine.receipt()
                    final_mark_equity = engine.state["mark_equity"]
                    final_remaining_qty = engine.state["remaining_qty"]

                # Cross-verify sidecar WAL vs G1 Engine state
                if len(self.settled_intents) != 1:
                    raise SafetyViolation("AT_MOST_ONCE_SIMULATED_INTENT_VIOLATED")
                settled_intent_id = next(iter(self.settled_intents.keys()))
                if settled_intent_id != digest([prop_hash, "SIMULATED_ENTRY"]):
                    raise SafetyViolation("SIMULATED_INTENT_ID_MISMATCH")

                if (
                    g1_receipt["phase"] != "CLOSED"
                    or g1_receipt["pending_cash"]
                    or decimal(g1_receipt["reserved_notional"]) != 0
                ):
                    raise SafetyViolation("TERMINAL_NOT_FLAT")

                final_receipt = {
                    **g1_receipt,
                    "mark_equity": final_mark_equity,
                    "remaining_qty": final_remaining_qty,
                    "sidecar_terminal": "G1G3_OFFLINE_PORTS_BOUNDED_VERIFIED",
                    "readiness": "OFFLINE_LOOPBACK_ONLY",
                    "power_loss_durability_proven": False,
                    "trust_translation_boundary": "SYNTHETIC_ED25519_TO_SEALED_G1_FIXTURE_ONLY",
                    "fixture_name": sealed_fixture["fixture_name"],
                    "sealed_fixture_sha256": seal_manifest["sealed_fixture_sha256"],
                    "source_event_hash": proposal["source_hash"],
                    "operator_id": operator_id,
                    "operator_key_id": key_id,
                    "approval_nonce": nonce,
                    "bounded_llm_request_hash": llm_result["request_sha256"],
                    "bounded_llm_response_hash": llm_result["response_sha256"],
                    "final_approval_event_id": approve_ev["id"],
                    "simulated_intent_id": settled_intent_id,
                    "settled_simulated_intent_count": len(self.settled_intents),
                    "feishu_delivered_unique_count": len(feishu_port.receipts_by_dedup_id),
                    "market_pit_accepted_envelopes": pit_port.accepted_envelope_count,
                    "market_pit_duplicate_envelopes": pit_port.duplicate_envelope_count,
                    "no_order_telemetry": self.no_order_port.telemetry(),
                    "sidecar_wal_seq": self.seq,
                    "sidecar_wal_chain": self.chain,
                }
                (self.root / "SIDECAR_RECEIPT.json").write_text(
                    canonical(final_receipt) + "\n", encoding="utf-8"
                )
                return final_receipt
        finally:
            if llm_server is not None:
                llm_server.close()
            if feishu_server is not None:
                feishu_server.close()
