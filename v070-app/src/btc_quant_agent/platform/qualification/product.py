"""Explicit F native/QA decision schema, immutable Shadow and existing HTML/C adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Any, cast

from pydantic import create_model, model_validator

from ..core import fingerprint
from ..rc_models import RCPlan, STRATEGY_VERSION
from ..rc_observe import Observation, observe_path, advance_episode
from ..rc_strategy import compile_s1
from ..reporting import document, table
from ..swing import Contract, SwingPolicy
from ..native.contract import digest, require, canonical, strict
from .evidence import Ledger, SCHEMA_HASH
from .source import causal

PRODUCT = "F_NATIVE_S1_PRODUCT_V1"


class Decision(Contract):
    schema_version: Literal["F_NATIVE_PRODUCT_V1"] = "F_NATIVE_PRODUCT_V1"
    product_version: Literal["F_NATIVE_S1_PRODUCT_V1"] = "F_NATIVE_S1_PRODUCT_V1"
    exposure: Literal["GENUINE_NATIVE", "SYNTHETIC_NETWORK_QA"]
    strategy: Literal["trend_pullback"] = "trend_pullback"
    strategy_version: Literal["PROGRAM_A_S1_CAUSAL_V1"] = "PROGRAM_A_S1_CAUSAL_V1"
    symbol: Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    market_state: Literal["NO_SETUP", "WATCH", "ARMED", "DATA_UNAVAILABLE", "SOURCE_BLOCKED"]
    source_qualified: bool
    shadow_advisory_qualified: Literal[False] = False
    economically_validated: Literal[False] = False
    account: Literal["ACCOUNT_UNKNOWN/ACCOUNT_VETO"] = "ACCOUNT_UNKNOWN/ACCOUNT_VETO"
    actionability: Literal["NOT_ACTIONABLE_ACCOUNT_VETO"] = "NOT_ACTIONABLE_ACCOUNT_VETO"
    qualification_sha256: str
    schema_sha256: str = SCHEMA_HASH
    trigger_close_ms: int
    decision_ms: int
    scheduled_review_ms: int
    prefix_sha256: str
    receipt_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    diagnostics: dict[str, Any]
    opportunity: RCPlan | None = None
    episode_id: str | None = None
    eligible_planned_r: tuple[int, ...] = ()

    @model_validator(mode="after")
    def integrity(self):
        require(self.schema_sha256 == SCHEMA_HASH, "NATIVE_PRODUCT_SCHEMA_HASH")
        require(
            self.scheduled_review_ms == SwingPolicy().next_review(self.decision_ms), "SCHEDULED_REVIEW_CLOCK"
        )
        positive = self.market_state in ("WATCH", "ARMED")
        require(
            positive == (self.opportunity is not None) == (self.episode_id is not None), "NATIVE_PLAN_STATE"
        )
        require(
            not self.source_qualified or self.exposure == "GENUINE_NATIVE", "QA_CANNOT_BE_NATIVE_QUALIFIED"
        )
        if positive:
            require(
                self.exposure == "SYNTHETIC_NETWORK_QA" or self.source_qualified,
                "UNQUALIFIED_NATIVE_POSITIVE_FORBIDDEN",
            )
            require(
                self.episode_id
                == fingerprint(
                    [PRODUCT, STRATEGY_VERSION, self.symbol, self.trigger_close_ms, self.prefix_sha256]
                ),
                "NATIVE_EPISODE_ID",
            )
            require(
                self.opportunity is not None
                and self.opportunity.account_status == "UNKNOWN"
                and self.decision_ms < self.scheduled_review_ms < self.opportunity.expires_ms,
                "NATIVE_REVIEW_ACTIONABILITY",
            )
        return self


# Reuse the accepted observation field validators with explicit new provenance.
observation_fields: dict[str, Any] = {
    name: (field.annotation, field) for name, field in Observation.model_fields.items()
}
observation_fields.update(
    schema_version=(Literal["F_NATIVE_OBSERVATION_V1"], "F_NATIVE_OBSERVATION_V1"),
    exposure=(Literal["GENUINE_NATIVE", "SYNTHETIC_NETWORK_QA"], ...),
)
model_builder: Any = create_model
NativeObservation: Any = model_builder(
    "NativeObservation",
    __base__=Contract,
    __validators__={"clocks": model_validator(mode="after")(cast(Any, Observation.clocks))},
    **observation_fields,
)


class Product:
    def __init__(self, qualification, path):
        self.qualification = qualification
        self.events = Ledger(path)
        self._assessment = None

    def review(self, symbol, trigger_ms, decision_ms):
        q = self.qualification.assess(decision_ms)
        self._assessment = q
        if not self.qualification.qa and q["status"] == "ELIGIBLE":
            from .admission import HostEnvelope, verify_host, verify_review_epoch
            from ..native.clock import Clock
            from ..native.contract import Grant

            current = Clock().sample()
            entries = self.qualification.ledger.values("HOST_ADMISSION")
            chosen = next(
                (
                    x
                    for x in reversed(entries)
                    if HostEnvelope.model_validate(x["envelope"]).grant.valid_start_ms
                    <= decision_ms
                    < HostEnvelope.model_validate(x["envelope"]).grant.valid_end_ms
                ),
                None,
            )
            require(chosen is not None, "LIVE_HOST_CLOCK_ADMISSION_MISSING")
            assert chosen is not None
            with self.qualification.journal.db() as db:
                grant = Grant.model_validate_json(
                    db.execute("SELECT grant_json FROM sessions WHERE id=?", (chosen["session"],)).fetchone()[
                        0
                    ]
                )
            host = HostEnvelope.model_validate(chosen["envelope"])
            verify_host(host, self.qualification.roots, grant, current["wall_ms"])
            verify_review_epoch(host, current, decision_ms)

        def factory(**fields):
            return Decision(
                **fields,
                exposure=q["evidence_class"],
                source_qualified=q["source_qualified"],
                qualification_sha256=digest(q["proof"]),
            )

        decision = compile_s1(
            symbol=symbol,
            trigger_ms=trigger_ms,
            decision_ms=decision_ms,
            receipts=q["records"],
            source_blocked=q["status"] != "ELIGIBLE",
            asof_reader=causal,
            decision_factory=factory,
            product_id=PRODUCT,
            cost_label="UNCALIBRATED_ADVERSE_COST_GEOMETRY_NOT_EXECUTABLE_R",
            source_reason="VERSIONED_SOURCE_EVIDENCE_ACCOUNT_VETO",
        )
        if q["status"] != "ELIGIBLE":
            decision = decision.model_copy(update={"reasons": tuple([q["reason"]])})
        previous = next(
            (
                x
                for x in self.events.values("DECISION")
                if x["symbol"] == symbol and x["trigger_close_ms"] == trigger_ms
            ),
            None,
        )
        if previous:
            require(previous == decision.model_dump(mode="json"), "EXANTE_PLAN_IMMUTABLE")
        else:
            self.events.append("DECISION", decision.model_dump(mode="json"))
        return decision

    def decisions(self):
        result = [Decision.model_validate_json(json.dumps(x)) for x in self.events.values("DECISION")]
        for d in result:
            q = self.qualification.assess(d.decision_ms)
            require(
                d.qualification_sha256 == digest(q["proof"])
                and (not d.source_qualified or q["source_qualified"]),
                "PERSISTED_NATIVE_ADMISSION_REJECTED",
            )
        return result

    def receipts(self):
        return self._assessment["records"] if self._assessment else []

    def stopped(self):
        return () if self._assessment and self._assessment["status"] == "ELIGIBLE" else ("SOURCE_BLOCKED",)

    def episode(self, identity):
        d = next(d for d in self.decisions() if d.episode_id == identity)
        updates = [e for e in self.events.values("LIFECYCLE") if e["episode_id"] == identity]
        last = (
            updates[-1]
            if updates
            else {
                "revision": 0,
                "now_ms": d.decision_ms,
                "state": d.market_state,
                "reason": "INITIAL_VERSIONED_SOURCE_PLAN",
            }
        )
        return {
            "anchors": {"decision": d.model_dump(mode="json")},
            "updated_ms": last["now_ms"],
            "revision": last["revision"],
            "state": {"status": last["state"], "account": d.account, "actual_fill": False},
        }

    def transition(self, identity, expected_revision, state, now_ms, reason):
        e = self.episode(identity)
        require(
            e["revision"] == expected_revision and now_ms >= e["updated_ms"], "NATIVE_SHADOW_CAS_OR_CLOCK"
        )
        update = {
            "episode_id": identity,
            "revision": expected_revision + 1,
            "now_ms": now_ms,
            "state": state,
            "reason": reason,
        }
        if e["state"]["status"] in ("EXPIRED", "CANCELED", "INVALIDATED", "NO_CHASE"):
            return e
        self.events.append("LIFECYCLE", update)
        return self.episode(identity)

    def observe(self, identity, asof_ms):
        d = next(d for d in self.decisions() if d.episode_id == identity)
        q = self.qualification.assess(asof_ms)
        self._assessment = q
        # Price-path observations remain distinct from current Source eligibility.
        from .source import receipt

        with self.qualification.journal.db() as db:
            raw = [
                strict(v)
                for (v,) in db.execute("SELECT value FROM receipts ORDER BY frame")
                if strict(v)["record"]["durable_ms"] <= asof_ms
            ]
        rows = [receipt(v) for v in raw] if len(q["stages"]) >= 4 else []
        observation = observe_path(
            d,
            rows,
            asof_ms=asof_ms,
            decision_parser=Decision.model_validate_json,
            observation_factory=lambda **k: NativeObservation(**k, exposure=d.exposure),
            evidence_reason="CONDITIONAL_MARKET_SIDE_PATH_NOT_EXECUTION_OR_PNL",
        )
        current = observation.model_dump(mode="json")
        previous = next(
            (
                x
                for x in self.events.values("OBSERVATION")
                if x["episode_id"] == identity and x["asof_ms"] == asof_ms
            ),
            None,
        )
        if previous is not None:
            require(previous == current, "OBSERVATION_IMMUTABLE_CONFLICT")
        else:
            self.events.append("OBSERVATION", current)
        advance_episode(self, identity, now_ms=asof_ms, decision_parser=Decision.model_validate_json)
        return observation

    def dashboard(self, path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        decisions = self.decisions()
        rows = []
        for d in decisions:
            p = d.opportunity
            rows.append(
                {
                    "Symbol": d.symbol,
                    "Direction": p.direction if p else "NONE",
                    "Strategy": d.strategy,
                    "Regime": p.regime if p else d.diagnostics,
                    "Source": d.exposure,
                    "Source qualified": d.source_qualified,
                    "Decision/review": (d.decision_ms, d.scheduled_review_ms),
                    "State": self.episode(d.episode_id)["state"]["status"] if p else d.market_state,
                    "Entry": p.entry_region if p else None,
                    "Stop": p.buffered_stop if p else None,
                    "Targets": p.target_zones if p else None,
                    "After-cost planned R": p.planned_after_cost_r if p else None,
                    "Expiry": p.expires_ms if p else None,
                    "Account": d.account,
                    "Gaps/reasons": d.reasons,
                }
            )
        value = {
            "schema_version": "F_NATIVE_PRODUCT_SNAPSHOT_V1",
            "decisions": [d.model_dump(mode="json") for d in decisions],
            "observations": self.events.values("OBSERVATION"),
            "lifecycle": self.events.values("LIFECYCLE"),
            "economic_validation": False,
            "shadow_qualified": False,
            "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
        }
        value["snapshot_sha256"] = digest(value)
        (path / "latest.json").write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        (path / "latest.html").write_text(
            document(
                "Swing advisory — versioned Source",
                table(rows)
                + "<p>Later market-side observations: "
                + json.dumps(value["observations"])
                + "</p><p>Planned geometry is not realized profit. S2/S3 RESEARCH_ONLY_DISABLED.</p>",
                label="VERSIONED SOURCE · ACCOUNT UNKNOWN/VETO · ECONOMIC VALIDATION FALSE",
            ),
            encoding="utf-8",
        )
        return value

    def export_c(self, output):
        from program_c.protocol import load_protocol
        from program_c.reporting import evaluate
        from program_c.validation import default_costs
        from program_c.integrity import fresh_directory, write_json

        decisions = self.decisions()
        rows = []
        if any(d.exposure != "SYNTHETIC_NETWORK_QA" for d in decisions):
            directory = fresh_directory(Path(output))
            write_json(
                directory / "F_native_episode_export.json",
                {
                    "schema_version": "F_NATIVE_EPISODE_EXPORT_V1",
                    "source_kind": "GENUINE_NATIVE",
                    "decisions": [d.model_dump(mode="json") for d in decisions],
                    "observations": self.events.values("OBSERVATION"),
                    "economic_evidence": False,
                    "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
                },
            )
            (directory / "scientific_report.md").write_text(
                "# Native economic admission blocked\n\nINSUFFICIENT_SUPPORT. The immutable Program C protocol has no accepted native economic admission roots. Source qualification does not authorize an economic study or establish execution.\n",
                encoding="utf-8",
            )
            write_json(
                directory / "status.json",
                {
                    "status": "C_NATIVE_ADMISSION_UNAVAILABLE",
                    "scientific_decision": "INSUFFICIENT_SUPPORT",
                    "real_economic_samples": 0,
                },
            )
            return
        protocol = load_protocol()
        for d in decisions:
            if not d.opportunity:
                continue
            p = d.opportunity
            rows.append(
                {
                    "episode_id": d.episode_id,
                    "strategy_version": d.strategy_version,
                    "symbol": d.symbol,
                    "direction": p.direction,
                    "regime": p.regime,
                    "source_manifest_sha256": d.prefix_sha256,
                    "causal_prefix_sha256": d.prefix_sha256,
                    "trigger_close_ms": d.trigger_close_ms,
                    "decision_ms": d.decision_ms,
                    "scheduled_review_ms": d.scheduled_review_ms,
                    "entry_region": list(p.entry_region),
                    "structural_stop": p.buffered_stop,
                    "volatility_buffer": p.atr_buffer,
                    "execution_buffer": p.execution_buffer,
                    "fixed_preobservable_target_zones": list(p.target_zones),
                    "expiry_ms": p.expires_ms,
                    "holding_horizon_hours": p.holding_hours,
                    "decision_digest": digest(d.model_dump(mode="json")),
                    "row_sha256": digest(d.model_dump(mode="json")),
                    "source_kind": "SOURCE_SYNTHETIC",
                    "reviewed_ms": None,
                    "source_facts": [],
                    "path": [],
                    "coverage_start_ms": d.decision_ms,
                    "coverage_end_ms": d.decision_ms,
                    "right_censored": False,
                    "administrative_censor_ms": None,
                    "interval_hours": 1,
                    "price_unit": "USDT_PER_BASE",
                    "volatility_bucket": "UNKNOWN",
                    "source_path_id": d.prefix_sha256,
                    "entry_premise": "CONDITIONAL_ONLY_NOT_A_FILL",
                    "costs": default_costs(d.decision_ms),
                    "fixture_name": "F_SYNTHETIC_NETWORK_QA",
                    "producer_outcome": None,
                    "producer_planned_R": d.diagnostics["planned_gross_r"],
                    "producer_projected_after_cost_R": p.planned_after_cost_r,
                    "producer_projected_after_cost_R_semantics": "EX_ANTE_GEOMETRY_NOT_OBSERVED_RETURN",
                }
            )
        envelope = {
            "schema_version": "F_TO_C_SOURCE_NEUTRAL_V1",
            "protocol_sha256": protocol["protocol_sha256"],
            "source_kind": "SOURCE_SYNTHETIC",
            "evaluation_asof_ms": max(d.decision_ms for d in decisions),
            "episodes": rows,
            "control_pool": [],
            "no_setup_decision_count": sum(d.market_state == "NO_SETUP" for d in decisions),
        }
        directory = fresh_directory(Path(output))
        write_json(directory / "F_episode_export.json", envelope)
        evaluate(envelope, protocol, directory, canonical(envelope))
