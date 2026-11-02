"""Persistent read-only scanner using existing factors, strategies, risk and user ledger."""

from __future__ import annotations

import json
from dataclasses import replace

from ..advisory import gate, scan
from ..backtest import correlations
from ..core import (
    DataProvenance,
    EvidenceTier,
    InstrumentSpec,
    Lifecycle,
    ManagementAction,
    StrategyCandidate,
    UserReportedFill,
    dec,
    fingerprint,
    lifecycle_path,
    primitive,
)
from ..portfolio import Exposure
from ..position_management import AdvisoryStore, supervise
from ..reporting import source_identity
from ..factors import REGISTRY as FACTORS
from ..strategies import REGISTRY, resolve
from .adapters import PublicPayloadAdapter
from .admission import compile_snapshot
from .config import BridgeConfig
from .contracts import ProviderBatch, PublicSource


def candidate_from_json(raw: dict) -> StrategyCandidate:
    raw = dict(raw)
    for key in ("entry_low", "entry_high", "max_entry_price", "invalidation", "stop", "target"):
        if raw[key] is not None:
            raw[key] = dec(raw[key])
    raw["state"] = Lifecycle(raw["state"])
    raw["evidence_tier"] = EvidenceTier(raw["evidence_tier"])
    raw["provenance"] = DataProvenance(**raw["provenance"])
    for key in ("confirmation", "veto_reasons"):
        raw[key] = tuple(raw[key])
    return StrategyCandidate(**raw)


def spec_from_json(raw: dict) -> InstrumentSpec:
    return InstrumentSpec(**raw)


class BridgeStore(AdvisoryStore):
    def __init__(self, path):
        super().__init__(path)
        with self._connect() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS bridge_sessions (
                session_id TEXT PRIMARY KEY, epoch INTEGER NOT NULL, last_ts INTEGER NOT NULL,
                pending_json TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS bridge_snapshots (
                session_id TEXT NOT NULL, decision_ts INTEGER NOT NULL, snapshot_id TEXT NOT NULL,
                result_json TEXT NOT NULL, PRIMARY KEY(session_id,decision_ts));
              CREATE TABLE IF NOT EXISTS bridge_plans (
                id TEXT PRIMARY KEY, candidate_json TEXT NOT NULL, spec_json TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS bridge_position_contracts (
                position_id TEXT PRIMARY KEY, spec_json TEXT NOT NULL);
            """)

    def state(self, session_id):
        with self._connect() as db:
            row = db.execute(
                "SELECT epoch,last_ts,pending_json FROM bridge_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        return (row[0], row[1], json.loads(row[2])) if row else (0, 0, {})

    def cached(self, session_id, decision_ts, snapshot_id):
        with self._connect() as db:
            row = db.execute(
                "SELECT snapshot_id,result_json FROM bridge_snapshots WHERE session_id=? AND decision_ts=?",
                (session_id, decision_ts),
            ).fetchone()
        if row and row[0] != snapshot_id:
            raise ValueError("SNAPSHOT_ORIGIN_CONFLICT")
        return json.loads(row[1]) if row else None

    def commit_snapshot(self, session_id, epoch, snapshot_id, result, pending, plan_specs):
        encoded = json.dumps(primitive(result), sort_keys=True, allow_nan=False)
        now = result["decision_ts"]
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT snapshot_id,result_json FROM bridge_snapshots WHERE session_id=? AND decision_ts=?",
                (session_id, now),
            ).fetchone()
            if existing:
                if existing[0] != snapshot_id:
                    raise ValueError("SNAPSHOT_ORIGIN_CONFLICT")
                return json.loads(existing[1])
            previous = db.execute(
                "SELECT epoch,last_ts FROM bridge_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if previous and (previous[0] != epoch or previous[1] >= now):
                raise ValueError("SNAPSHOT_STATE_CONFLICT_OR_TIME_REGRESSION")
            if not previous and epoch != 0:
                raise ValueError("SNAPSHOT_STATE_CONFLICT")
            for candidate, spec in plan_specs:
                values = (
                    candidate.id,
                    json.dumps(primitive(candidate), sort_keys=True),
                    json.dumps(primitive(spec), sort_keys=True),
                )
                old = db.execute(
                    "SELECT candidate_json,spec_json FROM bridge_plans WHERE id=?", (candidate.id,)
                ).fetchone()
                if old and tuple(old) != values[1:]:
                    raise ValueError("IMMUTABLE_BRIDGE_PLAN_CONFLICT")
                db.execute("INSERT OR IGNORE INTO bridge_plans VALUES (?,?,?)", values)
            db.execute(
                "INSERT INTO bridge_sessions VALUES (?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET epoch=excluded.epoch,last_ts=excluded.last_ts,pending_json=excluded.pending_json",
                (session_id, epoch + 1, now, json.dumps(primitive(pending), sort_keys=True)),
            )
            db.execute(
                "INSERT INTO bridge_snapshots VALUES (?,?,?,?)", (session_id, now, snapshot_id, encoded)
            )
        return json.loads(encoded)

    def preview_receipts(self, result):
        """Repairable after crash: frozen snapshot commits before existing decision/outbox writes."""
        output = []
        for index, record in enumerate(result["records"]):
            identity = self.commit_decision(
                record,
                result["decision_ts"],
                result["decision_ts"],
                origin=fingerprint([result["session_id"], result["snapshot_id"], index]),
            )
            event = self.prepare(identity, record["symbol"], result["decision_ts"])
            output.append(
                {
                    "decision_id": identity,
                    "event_id": event,
                    "notification_status": self.get_notification(event)["status"],
                }
            )
        return {**result, "persistence": output, "notification_mode": "PREVIEW_ONLY"}

    def positions(self, cutoff: int | None = None):
        with self._connect() as db:
            rows = db.execute(
                "SELECT p.evidence,c.spec_json FROM platform_position_versions p LEFT JOIN bridge_position_contracts c ON c.position_id=p.id WHERE p.version=(SELECT MAX(q.version) FROM platform_position_versions q WHERE q.id=p.id AND json_extract(q.evidence,'$.updated_ts')<=?) ORDER BY p.id",
                (cutoff if cutoff is not None else 2**63 - 1,),
            ).fetchall()
        return [
            (self._decode(row[0]), spec_from_json(json.loads(row[1])) if row[1] else None)
            for row in rows
            if json.loads(row[0])["status"] != "CLOSED"
        ]

    def report_plan_fill(self, plan_id: str, fill: UserReportedFill):
        if not isinstance(fill, UserReportedFill) or fill.source != "USER_REPORTED":
            raise ValueError("ACTUAL_FILL_REQUIRES_USER_REPORT")
        with self._connect() as db:
            row = db.execute(
                "SELECT candidate_json,spec_json FROM bridge_plans WHERE id=?", (plan_id,)
            ).fetchone()
            binding = db.execute(
                "SELECT spec_json FROM bridge_position_contracts WHERE position_id=?", (fill.position_id,)
            ).fetchone()
            published = db.execute(
                "SELECT result_json FROM bridge_snapshots WHERE decision_ts<=? ORDER BY decision_ts DESC",
                (fill.user_action_ts,),
            ).fetchall()
        if row is None:
            raise ValueError("UNKNOWN_COMMITTED_PLAN")
        c = candidate_from_json(json.loads(row[0]))
        spec = spec_from_json(json.loads(row[1]))
        if c.symbol != fill.symbol or c.direction != fill.direction:
            raise ValueError("USER_FILL_PLAN_IDENTITY_MISMATCH")
        if binding and binding[0] != row[1]:
            raise ValueError("USER_POSITION_CONTRACT_MISMATCH")
        position = self.report(fill, spec, stop=c.stop)
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO bridge_position_contracts VALUES (?,?)", (position.id, row[1]))
        warnings = []
        if fill.operation == "OPEN":
            if not c.entry_low <= fill.price <= c.entry_high:
                warnings.append("USER_FILL_OUTSIDE_ADVISED_REGION")
            if fill.user_action_ts >= c.expires_ts:
                warnings.append("USER_FILL_AFTER_ADVISED_EXPIRY")
            latest = None
            for snapshot_row in published:
                for record in json.loads(snapshot_row[0])["records"]:
                    plan_candidate = record.get("plan", {}).get("candidate", record.get("candidate", {}))
                    if plan_candidate.get("id") == plan_id:
                        latest = record
                        break
                if latest is not None:
                    break
            if latest is None or latest.get("state") != "ENTRY_ELIGIBLE":
                warnings.append("USER_FILL_WITHOUT_RECORDED_ENTRY_ELIGIBILITY")
        return {
            "position": primitive(position),
            "warnings": warnings,
            "execution_authority": "USER_REPORTED_ONLY",
        }


class ReadOnlyScanner:
    def __init__(self, config: BridgeConfig, store: BridgeStore):
        self.config = config
        self.store = store
        self.source_hash = source_identity()
        self.session_id = fingerprint(["BRIDGE_V1", config.hash, self.source_hash])

    def scan(self, batch: ProviderBatch) -> dict:
        c = self.config
        if c.mode != "offline_fixture":
            PublicSource(c.provider).snapshot(0)
        cached = self.store.cached(self.session_id, batch.decision_ts, batch.id)
        if cached is not None:
            return self.store.preview_receipts(cached)
        epoch, last_ts, pending_raw = self.store.state(self.session_id)
        if batch.decision_ts <= last_ts:
            raise ValueError("DECISION_TIME_REGRESSION")
        normalized = PublicPayloadAdapter(
            c.provider, c.platform.market, c.platform.interval_seconds
        ).normalize(batch, c.platform.universe)
        admitted = compile_snapshot(normalized, c)
        pending = {s: candidate_from_json(value) for s, value in pending_raw.items()}
        positions = self.store.positions(batch.decision_ts)
        risk_records = []
        exposures = []
        portfolio_veto = []
        for position, spec in positions:
            event = admitted.events.get(position.symbol)
            if spec is None or event is None or fingerprint(spec) != fingerprint(event.spec):
                action = ManagementAction(
                    position.id, "RECONCILE", "POSITION_CONTRACT_OR_SOURCE_UNKNOWN", batch.decision_ts
                )
                portfolio_veto.append("OPEN_POSITION_SOURCE_OR_CONTRACT_UNKNOWN")
            else:
                index = admitted.indices[position.symbol]
                atr = admitted.pipeline.result(position.symbol, "ATR", index, batch.decision_ts).value
                action = supervise(position, event, atr=atr, policy=c.platform.exits)
                beta = admitted.pipeline.result(position.symbol, "BETA", index, batch.decision_ts).value
                exposures.append(
                    Exposure(
                        position.symbol,
                        position.direction,
                        float(position.quantity * spec.multiplier) * event.candle.close,
                        beta,
                    )
                )
            risk_records.append(
                {
                    "kind": "POSITION_RISK",
                    "symbol": position.symbol,
                    "position_version": position.version,
                    "action": primitive(action),
                    "severity": "RISK" if action.action in ("EXIT", "REDUCE", "RECONCILE") else "INFO",
                    "position_status": position.status,
                    "execution_confirmed": False,
                }
            )
        eligible_events = [
            e
            for s, e in admitted.events.items()
            if not set(admitted.diagnostics[s]).intersection(
                {
                    "INSTRUMENT_NOT_TRADING",
                    "BELOW_LIQUID_UNIVERSE_THRESHOLD",
                    "LIQUIDITY_OBSERVATION_UNKNOWN_OR_STALE",
                }
            )
        ]
        all_candidates = (
            scan(admitted.pipeline, eligible_events, admitted.indices, c.platform, resolve_conflicts=False)
            if eligible_events
            else []
        )
        selected = resolve(all_candidates, c.platform)
        winner = {x.symbol: x for x in selected}
        evaluations = []
        for symbol in c.platform.universe:
            for strategy in c.platform.strategies:
                candidate = next(
                    (x for x in all_candidates if x.symbol == symbol and x.strategy_id == strategy.id), None
                )
                reasons = []
                if symbol not in admitted.events:
                    reasons = ["SOURCE_UNAVAILABLE"]
                elif candidate is None:
                    for feature in REGISTRY[strategy.id].required_features:
                        feature_result = admitted.pipeline.result(
                            symbol, feature, admitted.indices[symbol], batch.decision_ts
                        )
                        if feature_result.value is None:
                            reasons.append(f"{feature}:{feature_result.status}:{feature_result.reason}")
                    if not reasons:
                        reasons = ["NO_SETUP_OR_REGIME_INACTIVE"]
                elif symbol not in winner:
                    reasons = ["STRATEGY_VOTE_TIE"]
                elif winner[symbol].strategy_id != strategy.id:
                    reasons = ["STRATEGY_CONFLICT_OR_LOWER_PRIORITY"]
                evaluations.append(
                    {
                        "symbol": symbol,
                        "strategy": strategy.id,
                        "direction": candidate.direction if candidate else None,
                        "opportunity_score": candidate.opportunity_score if candidate else None,
                        "reasons": reasons,
                        "evaluated_snapshot": batch.id,
                    }
                )
        records = list(risk_records)
        plan_specs = []
        finished = set()
        correlation = (
            correlations(admitted.pipeline, admitted.indices, list(admitted.events.values()), exposures)
            if exposures
            else {}
        )
        for symbol, candidate in sorted(pending.items()):
            if any(position.symbol == symbol for position, _ in positions):
                records.append(
                    {
                        "kind": "CANDIDATE",
                        "symbol": symbol,
                        "candidate": primitive(candidate),
                        "state": "CANCELLED",
                        "action": "CANCEL",
                        "veto_reasons": ["USER_REPORTED_POSITION_EXISTS"],
                        "severity": "WATCH",
                    }
                )
                finished.add(symbol)
                continue
            event = admitted.events.get(symbol)
            if event is None:
                state = Lifecycle.EXPIRED if batch.decision_ts >= candidate.expires_ts else candidate.state
                records.append(
                    {
                        "kind": "CANDIDATE",
                        "symbol": symbol,
                        "candidate": primitive(candidate),
                        "state": str(state),
                        "action": "CANCEL" if state == Lifecycle.EXPIRED else "WAIT",
                        "veto_reasons": ["SOURCE_UNAVAILABLE"],
                        "severity": "WATCH",
                    }
                )
                if state == Lifecycle.EXPIRED:
                    finished.add(symbol)
                continue
            evidence = json.loads(candidate.evidence_json)
            veto = [*admitted.admission[symbol].reasons, *portfolio_veto]
            if evidence["contract_hash"] != fingerprint(event.spec):
                veto.append("CONTRACT_SPEC_CHANGED")
            if symbol in winner and winner[symbol].direction != candidate.direction:
                veto.append("OPPOSING_STRATEGY_PRIORITY")
            authority = replace(admitted.admission[symbol], reasons=tuple(sorted(set(veto))))
            beta = admitted.pipeline.result(symbol, "BETA", admitted.indices[symbol], batch.decision_ts).value
            plan = gate(candidate, event, c.platform, exposures, correlation, beta, authority)
            if "OPPOSING_STRATEGY_PRIORITY" in veto or "CONTRACT_SPEC_CHANGED" in veto:
                plan = replace(
                    plan,
                    state=Lifecycle.CANCELLED,
                    action="CANCEL",
                    risk=None,
                    lifecycle_transitions=lifecycle_path(candidate.state, Lifecycle.CANCELLED),
                )
            elif plan.state == Lifecycle.ARMED:
                analytic_veto = {
                    "CONFIRMATION_PENDING",
                    "PRICE_CONFIRMATION_PENDING",
                    "SOURCE_STALE_OR_INADMISSIBLE",
                }
                if candidate.state == Lifecycle.WATCH and analytic_veto.intersection(plan.veto_reasons):
                    plan = replace(plan, state=Lifecycle.WATCH, lifecycle_transitions=(Lifecycle.WATCH,))
            if plan.risk and event.quote:
                capacity = (
                    event.quote.ask_quantity if candidate.direction == "LONG" else event.quote.bid_quantity
                )
                if capacity is not None and plan.risk.quantity > capacity:
                    plan = replace(
                        plan,
                        state=Lifecycle.ARMED,
                        action="WAIT",
                        risk=None,
                        veto_reasons=tuple(
                            sorted(set([*plan.veto_reasons, "PLANNED_SIZE_EXCEEDS_OBSERVED_QUOTE_CAPACITY"]))
                        ),
                    )
            records.append(
                {
                    "kind": "CANDIDATE",
                    "symbol": symbol,
                    "state": str(plan.state),
                    "action": plan.action,
                    "plan": primitive(plan),
                    "veto_reasons": list(plan.veto_reasons),
                    "severity": "WATCH",
                    "opportunity_score": candidate.opportunity_score,
                }
            )
            if plan.state in (Lifecycle.CANCELLED, Lifecycle.EXPIRED):
                finished.add(symbol)
            else:
                pending[symbol] = replace(candidate, state=plan.state)
        for symbol in finished:
            pending.pop(symbol, None)
        for candidate in selected:
            if candidate.symbol in pending or candidate.symbol in finished:
                continue
            if any(p.symbol == candidate.symbol for p, _ in positions):
                continue
            event = admitted.events[candidate.symbol]
            evidence = json.loads(candidate.evidence_json)
            evidence.update(
                snapshot_id=batch.id, contract_hash=fingerprint(event.spec), exposure=normalized.exposure
            )
            candidate = replace(
                candidate,
                id=fingerprint([candidate.id, batch.id, self.session_id]),
                evidence_json=json.dumps(evidence, sort_keys=True),
            )
            pending[candidate.symbol] = candidate
            plan_specs.append((candidate, event.spec))
            preview = gate(
                candidate,
                event,
                c.platform,
                exposures,
                correlation,
                admitted.pipeline.result(
                    candidate.symbol, "BETA", admitted.indices[candidate.symbol], batch.decision_ts
                ).value,
                admitted.admission[candidate.symbol],
            )
            records.append(
                {
                    "kind": "CANDIDATE",
                    "symbol": candidate.symbol,
                    "candidate": primitive(candidate),
                    "state": "WATCH",
                    "action": "WATCH",
                    "opportunity_score": candidate.opportunity_score,
                    "veto_reasons": sorted(
                        set(
                            [*preview.veto_reasons]
                            + (["EXECUTABLE_QUOTE_MISSING"] if event.quote is None else [])
                        )
                    ),
                    "severity": "WATCH",
                }
            )
        represented = {record["symbol"] for record in records}
        for symbol, reasons in admitted.diagnostics.items():
            if symbol not in represented:
                records.append(
                    {
                        "kind": "SOURCE_STATUS",
                        "symbol": symbol,
                        "state": "WATCH",
                        "action": "WAIT",
                        "veto_reasons": reasons or ["NO_SETUP"],
                        "severity": "WATCH",
                    }
                )
        result = {
            "session_id": self.session_id,
            "snapshot_id": batch.id,
            "decision_ts": batch.decision_ts,
            "config_hash": c.hash,
            "source_hash": self.source_hash,
            "exposure": normalized.exposure,
            "provider": c.provider,
            "source_activation": "OFFLINE_FIXTURE_ONLY; LIVE_BLOCKED",
            "records": records,
            "strategy_evaluations": evaluations,
            "source_diagnostics": admitted.diagnostics,
            "observations": {s: primitive(e) for s, e in admitted.events.items()},
            "factor_results": {
                s: {
                    factor: primitive(
                        admitted.pipeline.result(s, factor, admitted.indices[s], batch.decision_ts)
                    )
                    for factor in FACTORS
                }
                for s in admitted.events
            },
            "factor_registry_count": len(FACTORS),
            "directional_strategy_count": sum(d.status != "RESEARCH_ONLY" for d in REGISTRY.values()),
            "receipt_ids": list(normalized.receipt_ids),
            "limitations": [
                "Generated fixtures are not observed market connectivity or profitability.",
                "Opportunity scores are not calibrated probabilities. Quote eligibility is not a fill.",
                "All notifications are local previews. User reports alone change actual position quantities.",
            ],
        }
        frozen = self.store.commit_snapshot(self.session_id, epoch, batch.id, result, pending, plan_specs)
        return self.store.preview_receipts(frozen)
