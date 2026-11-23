"""Exploratory adapter reusing accepted S1, Shadow methods, HTML and C math."""

from __future__ import annotations

import json
from typing import Any, Literal, cast

from pydantic import create_model, model_validator

from ..native.contract import digest, require, canonical
from ..qualification.product import Product as StrictProduct
from ..rc_strategy import compile_s1
from ..rc_observe import observe_path, advance_episode, Observation
from ..reporting import document, table
from ..swing import INTERVALS
from ..qualification.source import causal
from .models import Decision, PRODUCT
from .source import Source, checked_output
from .models import Dataset


fields: dict[str, Any] = {name: (field.annotation, field) for name, field in Observation.model_fields.items()}
fields.update(
    schema_version=(Literal["H_MVP_OBSERVATION_V1"], "H_MVP_OBSERVATION_V1"),
    exposure=(Literal["H_DETERMINISTIC_SYNTHETIC", "H_AUTHORIZED_IMPORT_UNQUALIFIED"], ...),
)
model_builder: Any = create_model
MVPObservation: Any = model_builder(
    "HObservation",
    __base__=Decision.__bases__[0],
    __validators__={"clocks": model_validator(mode="after")(cast(Any, Observation.clocks))},
    **fields,
)


class Product:
    def __init__(self, source):
        self.source: Source = source
        self.events = source.events
        self._assessment = None
        self._verified_decisions: set[str] = set()

    def receipts(self):
        return self._assessment["records"] if self._assessment else []

    def stopped(self):
        return () if self._assessment and self._assessment["status"] == "ELIGIBLE" else ("SOURCE_BLOCKED",)

    def episode(self, identity):
        return StrictProduct.episode(cast(Any, self), identity)

    def decisions(self):
        result = [Decision.model_validate_json(json.dumps(x)) for x in self.events.values("DECISION")]
        self.events.verify()
        for d in result:
            identity = digest(d.model_dump(mode="json"))
            if identity in self._verified_decisions:
                continue
            commits, datasets = self.source.imports()[: d.import_watermark], self.source.datasets()
            receipts = []
            for commit in commits:
                entry = datasets[commit["dataset_id"]]
                receipts.extend(
                    self.source.validate(Dataset.model_validate(entry["dataset"]), entry["permissions"])
                )
            wanted = {digest(v) for v in d.admitted_prefix}
            admitted = [r for r in receipts if digest(r.model_dump(mode="json")) in wanted]
            require(
                {digest(r.model_dump(mode="json")) for r in admitted} == wanted,
                "MVP_PREFIX_NOT_IN_ORIGINAL_IMPORT_WATERMARK",
            )
            metadata = {
                k: getattr(d, k)
                for k in (
                    "exposure",
                    "review_source_bounds_ms",
                    "review_local",
                    "clock_condition",
                    "data_status",
                    "import_watermark",
                    "admitted_prefix",
                )
            }
            expected = compile_s1(
                symbol=d.symbol,
                trigger_ms=d.trigger_close_ms,
                decision_ms=d.decision_ms,
                receipts=admitted,
                holding_hours=d.diagnostics["holding_hours"],
                asof_reader=causal,
                decision_factory=lambda **kw: Decision(**kw, **metadata),
                product_id=PRODUCT,
                cost_label="HYPOTHETICAL_ADVERSE_COST_GEOMETRY_UNCALIBRATED_NOT_EXECUTABLE_OR_REALIZED_R",
                source_reason="EXPLORATORY_UNQUALIFIED_MARKET_SIDE_ONLY_ACCOUNT_VETO",
            )
            require(expected == d, "MVP_PERSISTED_PLAN_DOES_NOT_MATCH_FROZEN_S1")
            self._verified_decisions.add(identity)
        return result

    def review(self, symbol, holding_hours=24):
        require(type(holding_hours) is int and 4 <= holding_hours <= 48, "MVP_HOLDING_REQUIRES_4_TO_48_HOURS")
        q = self.source.assess(symbol)
        self._assessment = q
        if q["status"] != "ELIGIBLE":
            self.events.append("REVIEW_BLOCKED", {k: v for k, v in q.items() if k != "records"})
            return {k: v for k, v in q.items() if k != "records"}
        trigger, lower = q["trigger"], q["source_bounds"][0]
        existing = next(
            (d for d in self.decisions() if d.symbol == symbol and d.trigger_close_ms == trigger), None
        )
        if existing is not None:
            require(
                existing.diagnostics["holding_hours"] == holding_hours, "MVP_ORIGINAL_PLAN_HORIZON_IMMUTABLE"
            )
            return existing
        day = trigger // INTERVALS["1D"]
        cycles = {
            d.trigger_close_ms for d in self.decisions() if d.trigger_close_ms // INTERVALS["1D"] == day
        }
        require(trigger in cycles or len(cycles) < 2, "MVP_TWO_MANUAL_REVIEW_CYCLES_PER_DAY_MAX")
        rows, _ = causal(q["records"], symbol, trigger, lower)

        def factory(**kw):
            return Decision(
                **kw,
                exposure=self.source.meta["evidence_class"],
                review_source_bounds_ms=tuple(q["source_bounds"]),
                review_local=q["sample"],
                clock_condition=q["clock"],
                data_status=q["data_status"],
                import_watermark=q["watermark"],
                admitted_prefix=tuple(r.model_dump(mode="json") for r in rows),
            )

        decision = compile_s1(
            symbol=symbol,
            trigger_ms=trigger,
            decision_ms=lower,
            receipts=q["records"],
            holding_hours=holding_hours,
            asof_reader=causal,
            decision_factory=factory,
            product_id=PRODUCT,
            cost_label="HYPOTHETICAL_ADVERSE_COST_GEOMETRY_UNCALIBRATED_NOT_EXECUTABLE_OR_REALIZED_R",
            source_reason="EXPLORATORY_UNQUALIFIED_MARKET_SIDE_ONLY_ACCOUNT_VETO",
        )
        self.events.append("DECISION", decision.model_dump(mode="json"))
        return decision

    def transition(self, identity, expected_revision, state, now_ms, reason):
        # Only provenance wording changes; accepted append-only CAS/terminal logic remains.
        previous = self.episode(identity)
        if previous["state"]["status"] == state and previous["updated_ms"] == now_ms:
            return previous
        return StrictProduct.transition(
            cast(Any, self),
            identity,
            expected_revision,
            state,
            now_ms,
            reason.replace("LATER_SYNTHETIC_", "LATER_MARKET_SIDE_"),
        )

    def observe(self, identity):
        d = next(d for d in self.decisions() if d.episode_id == identity)
        q = self.source.assess(d.symbol)
        self._assessment = q
        sample = self.source.sample()
        lower, upper = self.source.reference().project(sample)
        clock = self.events.values("CLOCK")[-1]
        rows = [] if clock["held"] or self.events.values("REJECTED_IMPORT") else self.source.receipts()
        observation = observe_path(
            d,
            rows,
            asof_ms=lower,
            decision_parser=Decision.model_validate_json,
            observation_factory=lambda **kw: MVPObservation(**kw, exposure=d.exposure),
            evidence_reason="HYPOTHETICAL_UNQUALIFIED_MARKET_PATH_NOT_FILL_EXECUTION_OR_PNL",
        )
        value = observation.model_dump(mode="json")
        value["review_local"] = sample.model_dump(mode="json")
        value["source_bounds"] = [lower, upper]
        before = next(
            (
                r
                for r in self.events.values("OBSERVATION")
                if r["episode_id"] == identity and r["asof_ms"] == lower
            ),
            None,
        )
        if before is None:
            self.events.append("OBSERVATION", value)
        else:
            require(before == value, "MVP_OBSERVATION_IMMUTABLE")
        advance_episode(self, identity, now_ms=lower, decision_parser=Decision.model_validate_json)
        return value

    def snapshot(self):
        self._assessment = self.source.assess()
        q = self._assessment
        state = {k: v for k, v in q.items() if k not in ("records", "sample")}
        if "sample" in q:
            state["local_time"] = q["sample"].model_dump(mode="json")
        value = {
            "schema_version": "H_MVP_DASHBOARD_V1",
            "mode": "EXPLORATORY_MVP",
            "data": state,
            "evidence_class": self.source.meta["evidence_class"],
            "decisions": [d.model_dump(mode="json") for d in self.decisions()],
            "lifecycle": self.events.values("LIFECYCLE"),
            "observations": self.events.values("OBSERVATION"),
            "source_qualified": False,
            "shadow_qualified": False,
            "economically_validated": False,
            "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
            "limitations": [
                "HYPOTHETICAL_MARKET_SIDE_ONLY_NO_ACCOUNT_EXECUTABILITY",
                "SOURCE_TIME_BOUNDS_AND_IMPORT_PROVENANCE_NOT_STRICT_UTC",
                "NO_FILL_OR_REALIZED_PNL_INFERRED",
                "COSTS_UNCALIBRATED_GEOMETRY_ONLY",
                "S2_S3_RESEARCH_ONLY_DISABLED",
                "NO_NATIVE_ACQUISITION_IN_MVP",
            ],
        }
        value["source_provenance"] = [
            {
                "source_id": e["dataset"]["source_id"],
                "capture_origin": e["dataset"]["capture_origin"],
                "evidence_class": e["dataset"]["evidence_class"],
                "source_reference": e["dataset"]["reference"],
                "transport_provenance": e["dataset"]["transport_provenance"],
                "quarantined_on_import": e["quarantined"],
                "missing_original_source_event_count": sum(
                    r["original_source_event_ms"] is None for r in e["dataset"]["rows"]
                ),
            }
            for e in self.source.datasets().values()
        ]
        value["timestamp_semantics"] = (
            "Original event/receive/available/durable wall+monotonic records retained in admitted_prefix; compiler UTC view uses conservative source-snapshot availability, not invented publication timestamps. Local import durability and actual review clocks checked separately."
        )
        value["snapshot_sha256"] = digest(value)
        return value

    def dashboard(self, output=None):
        path = checked_output(output) if output else self.source.directory / "dashboard"
        path.mkdir(parents=True, exist_ok=True)
        value = self.snapshot()
        rows = []
        for d in self.decisions():
            p = d.opportunity
            targets = list(p.target_zones[:3]) if p else []
            rows.append(
                {
                    "Symbol": d.symbol,
                    "Direction": p.direction if p else "NONE",
                    "Mode/source": d.exposure,
                    "1D/4H regime": {k: d.diagnostics.get(k) for k in ("1D", "4H")},
                    "Setup/structure": d.diagnostics.get("structure"),
                    "Reasons/limitations": d.reasons,
                    "State": self.episode(d.episode_id)["state"]["status"] if p else d.market_state,
                    "Entry region": p.entry_region if p else None,
                    "Structural hard stop": p.buffered_stop if p else None,
                    "TP1/TP2/TP3 if valid": targets,
                    "Eligible planned 2R/3R/4R": d.eligible_planned_r,
                    "Hypothetical after-cost R": p.planned_after_cost_r if p else None,
                    "Cost assumption": p.cost_assumption if p else "UNKNOWN",
                    "Expiry": p.expires_ms if p else None,
                    "Invalidation": p.structural_invalidation if p else None,
                    "Holding hours": d.diagnostics["holding_hours"],
                    "Source review bounds": d.review_source_bounds_ms,
                    "Local review clocks": d.review_local.model_dump(mode="json"),
                    "Clock at decision": d.clock_condition,
                    "Current clock/data": value["data"],
                    "Account/executability": d.account + " / HYPOTHETICAL_ONLY",
                }
            )
        body = table(
            [
                {
                    "Mode": "EXPLORATORY_MVP",
                    "Readiness": value["data"]["data_status"],
                    "Clock": value["data"].get("clock"),
                    "Reason": value["data"].get("reason"),
                    "Strict qualification": "SOURCE FALSE / SHADOW FALSE / ECONOMIC FALSE",
                }
            ]
        )
        for row in rows:
            body += "<h2>" + row["Symbol"] + " — " + str(row["State"]) + "</h2>"
            body += table([{"Field": key, "Value": val} for key, val in row.items()])
        body += table(
            [
                {
                    "Source provenance": value["source_provenance"],
                    "Timestamp semantics": value["timestamp_semantics"],
                }
            ]
        )
        body += table(
            [
                {
                    k: o[k]
                    for k in (
                        "episode_id",
                        "asof_ms",
                        "outcome",
                        "coverage_end_ms",
                        "entry_condition_observed",
                        "actual_fill",
                        "execution_inferred",
                        "economic_evidence",
                        "reasons",
                    )
                }
                for o in value["observations"]
            ]
        )
        body += table(value["lifecycle"])
        body += table([{"Evidence limitations": value["limitations"]}])
        for name, raw in {
            "latest.json": json.dumps(value, indent=2, sort_keys=True),
            "latest.html": document(
                "Quant swing advisory — EXPLORATORY_MVP",
                body,
                label="EXPLORATORY_MVP · HYPOTHETICAL · ACCOUNT UNKNOWN/VETO · NOT STRICT RESEARCH",
            ),
        }.items():
            target = path / name
            temp = path / (name + ".tmp")
            temp.write_text(raw + "\n", encoding="utf-8")
            temp.replace(target)
        return {
            "dashboard": str(path / "latest.html"),
            "snapshot": str(path / "latest.json"),
            "snapshot_sha256": value["snapshot_sha256"],
            "data_status": value["data"]["data_status"],
        }

    def evaluate(self, output):
        from program_c.protocol import load_protocol
        from program_c.reporting import evaluate
        from program_c.validation import default_costs
        from program_c.integrity import fresh_directory, write_json

        decisions = self.decisions()
        require(decisions, "MVP_DATA_NOT_READY_NO_DECISIONS_TO_EVALUATE")
        source_class = "SOURCE_SYNTHETIC" if self.source.synthetic else "NATIVE_UNQUALIFIED"
        protocol = load_protocol()
        rows = []
        for d in decisions:
            if d.opportunity is None:
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
                    "source_kind": source_class,
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
                    "fixture_name": "H_MVP_UNQUALIFIED",
                    "producer_outcome": None,
                    "producer_planned_R": d.diagnostics["planned_gross_r"],
                    "producer_projected_after_cost_R": p.planned_after_cost_r,
                    "producer_projected_after_cost_R_semantics": "EX_ANTE_GEOMETRY_NOT_OBSERVED_RETURN",
                }
            )
        observations = self.events.values("OBSERVATION")
        for row in rows:
            later = [o for o in observations if o["episode_id"] == row["episode_id"]]
            row["producer_outcome"] = later[-1]["outcome"] if later else None
        envelope = {
            "schema_version": "H_TO_C_SOURCE_NEUTRAL_V1",
            "mode": "EXPLORATORY_MVP",
            "protocol_sha256": protocol["protocol_sha256"],
            "source_kind": source_class,
            "evaluation_asof_ms": max(
                [d.decision_ms for d in decisions] + [o["asof_ms"] for o in observations]
            ),
            "episodes": rows,
            "control_pool": [],
            "no_setup_decision_count": sum(d.market_state == "NO_SETUP" for d in decisions),
            "MVP_unqualified_producer_observations": observations,
        }
        directory = fresh_directory(checked_output(output))
        write_json(directory / "H_episode_export.json", envelope)
        evaluate(envelope, protocol, directory, canonical(envelope))
        write_json(
            directory / "MVP_LIMITATIONS.json",
            {
                "mode": "EXPLORATORY_MVP",
                "evidence_class": self.source.meta["evidence_class"],
                "genuine_imported_rows_are_not_strict_economic_samples": True,
                "qualified_real_economic_samples": 0,
                "observed_outcomes_are_not_executed_opportunities": True,
                "C_native_qualification_not_granted": True,
            },
        )
        return {
            "scientific_decision": "INSUFFICIENT_SUPPORT",
            "report": str(directory / "scientific_report.md"),
            "source_kind": source_class,
            "economically_validated": False,
        }
