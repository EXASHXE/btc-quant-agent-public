"""Explicit J evidence adapter around accepted S1, Shadow, HTML and C gates."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Literal, cast

from pydantic import create_model, model_validator

from ..mvp.product import Product as HProduct
from ..native.contract import canonical, digest
from ..qualification.source import causal
from ..rc_models import frozen_contract
from ..rc_observe import Observation, observe_path, advance_episode
from ..rc_strategy import compile_s1
from ..reporting import table
from ..swing import INTERVALS
from .models import (
    Decision,
    POLICY,
    PRODUCT,
    QA,
    Blocked,
    Receipt,
    ensure,
    offset_step,
    path_guard,
    sample,
    write_json,
)
from .source import project

obs_fields: dict[str, Any] = {n: (f.annotation, f) for n, f in Observation.model_fields.items()}
obs_fields.update(
    schema_version=(Literal["J_PUBLIC_OBSERVATION_V1"], "J_PUBLIC_OBSERVATION_V1"),
    exposure=(Literal["J_PUBLIC_MARKET_ADVISORY_V1", "J_LOCAL_HTTP_QA_V1"], ...),
)
builder: Any = create_model
JObservation = builder(
    "JObservation",
    __base__=Decision.__bases__[0],
    __validators__={"clocks": model_validator(mode="after")(cast(Any, Observation.clocks))},
    **obs_fields,
)


class SourceView:
    intervals = tuple(POLICY["bars"])

    def check_review_window(self, snapshot, lower, upper, trigger):
        ensure(
            snapshot["grace_ms"] <= lower - trigger <= POLICY["review_delay_ms_max"],
            "LIVE_REVIEW_OUTSIDE_COMPLETED_4H_MANUAL_WINDOW",
            "SOURCE_BLOCKED",
        )

    def __init__(self, store):
        self.store, self.events, self.directory, self.meta = store, store.events, store.directory, store.meta

    def receipts(self):
        return [
            Receipt(r)
            for r in sorted(
                self.store.records(),
                key=lambda r: (r["candle"]["symbol"], r["candle"]["interval"], r["candle"]["open_time_ms"]),
            )
        ]

    def assess(self, symbol=None, *, review=False):
        try:
            snapshots = self.store.snapshots()
            ensure(snapshots, "LIVE_NO_ADMITTED_SNAPSHOT")
            ensure(not self.events.values("SOURCE_STOP"), "LIVE_SOURCE_REVISION_STOP_UNRESOLVED")
            s = snapshots[-1]
            ensure(
                self.events.values("SESSION_TERMINAL")[-1]["status"] == "COMPLETE",
                "LIVE_LAST_SESSION_FAILED_SOURCE_BLOCKED",
            )
            now = sample()
            ensure(
                not offset_step(s["last_sample"], now),
                "LIVE_CLOCK_JUMP_NEEDS_REACQUISITION",
                "LIVE_CLOCK_DEGRADED_BLOCKED",
            )
            states = self.events.values("CLOCK_STATE")
            ensure(
                not states or not states[-1]["held"],
                "LIVE_CLOCK_HOLD_NEEDS_REACQUISITION",
                "LIVE_CLOCK_DEGRADED_BLOCKED",
            )
            lower, upper = project(s["reference"], now, s["reference_max_age_ms"])
            ensure(
                upper < snapshots[0]["source_bounds"][0] + s["retention_days"] * INTERVALS["1D"],
                "LIVE_RETENTION_EXPIRED_OPERATOR_DELETION_REQUIRED",
            )
            trigger = lower // INTERVALS["4H"] * INTERVALS["4H"]
            if review:
                self.check_review_window(s, lower, upper, trigger)
            return {
                "status": "ELIGIBLE",
                "data_status": "LIVE_OPERATIONAL_DATA_UNQUALIFIED",
                "clock": s["clock"],
                "source_bounds": [lower, upper],
                "trigger": trigger,
                "sample": now,
                "snapshot_sha256": digest(s),
                "reason": None,
                "records": [Receipt(r) for r in s["records"]],
                "latest_completed": {
                    name: {
                        i: max(
                            r["candle"]["close_time_ms"] + 1
                            for r in s["records"]
                            if r["candle"]["symbol"] == name and r["candle"]["interval"] == i
                        )
                        for i in self.intervals
                    }
                    for name in POLICY["symbols"]
                },
                "coverage": {
                    name: {
                        i: sum(
                            r["candle"]["symbol"] == name and r["candle"]["interval"] == i
                            for r in s["records"]
                        )
                        for i in self.intervals
                    }
                    for name in POLICY["symbols"]
                },
            }
        except (ValueError, KeyError) as e:
            return {
                "status": getattr(e, "status", "LIVE_SOURCE_UNAVAILABLE"),
                "data_status": "DATA_NOT_READY",
                "clock": "UNQUALIFIED_OR_DEGRADED",
                "reason": str(e),
                "records": [],
                "source_qualified": False,
            }


class Product(HProduct):
    source: Any
    source_view = SourceView
    decision_model: Any = Decision
    metadata_fields: tuple[str, ...] = (
        "exposure",
        "snapshot_sha256",
        "admitted_prefix",
        "review_local",
        "review_source_bounds_ms",
        "clock_condition",
        "data_status",
    )

    def decision_metadata(self, assessment, symbol):
        return {}

    def existing_review(self, decision, assessment):
        return decision

    def __init__(self, store):
        self.store = store
        self.source = self.source_view(store)
        self.events = store.events
        self._assessment = None
        self._verified_decisions = set()

    def compile(self, symbol, trigger, lower, records, holding, metadata):
        def factory(**kw):
            kw["diagnostics"] = {
                **kw["diagnostics"],
                "hypothetical_costs_bps": frozen_contract()["strategy"]["costs_bps"],
            }
            return Decision(**kw, **metadata)

        return compile_s1(
            symbol=symbol,
            trigger_ms=trigger,
            decision_ms=lower,
            receipts=records,
            holding_hours=holding,
            asof_reader=causal,
            decision_factory=factory,
            product_id=PRODUCT,
            cost_label="HYPOTHETICAL_UNCALIBRATED_FEE_SPREAD_SLIPPAGE_FUNDING_NOT_FILL_OR_RETURN",
            source_reason="PUBLIC_HTTPS_UNSIGNED_OPERATIONAL_ONLY_ACCOUNT_VETO",
        )

    def decisions(self):
        self.events.verify()
        snapshots = {digest(s): s for s in self.store.snapshots()}
        values = [
            self.decision_model.model_validate_json(json.dumps(x)) for x in self.events.values("DECISION")
        ]
        for d in values:
            identity = digest(d.model_dump(mode="json"))
            if identity in self._verified_decisions:
                continue
            ensure(d.snapshot_sha256 in snapshots, "LIVE_DECISION_SNAPSHOT_NOT_COMMITTED")
            available = {digest(r) for r in snapshots[d.snapshot_sha256]["records"]}
            ensure(all(digest(r) in available for r in d.admitted_prefix), "LIVE_PREFIX_NOT_IN_SNAPSHOT")
            metadata = {k: getattr(d, k) for k in self.metadata_fields}
            expected = self.compile(
                d.symbol,
                d.trigger_close_ms,
                d.decision_ms,
                [Receipt(r) for r in d.admitted_prefix],
                d.diagnostics["holding_hours"],
                metadata,
            )
            ensure(expected == d, "LIVE_FROZEN_S1_RECOMPUTATION_MISMATCH")
            self._verified_decisions.add(identity)
        return values

    def review(self, symbol, holding_hours=24):
        ensure(type(holding_hours) is int and 4 <= holding_hours <= 48, "LIVE_HORIZON_REQUIRES_4_48_HOURS")
        q = self.source.assess(symbol, review=True)
        if q["status"] == "ELIGIBLE":
            # Conservative UTC intervals may overlap although monotonic durability
            # precedes review. Wait at most the predeclared operational uncertainty.
            wait = (
                max(max(r.bar.durable_ms for r in q["records"]), q.get("review_not_before_ms", 0))
                - q["source_bounds"][0]
                + 1
            )
            if 0 < wait <= POLICY["reference_width_ms_max"]:
                time.sleep(wait / 1000)
                q = self.source.assess(symbol, review=True)
        self._assessment = q
        if q["status"] != "ELIGIBLE":
            self.events.append("REVIEW_BLOCKED", {k: v for k, v in q.items() if k != "records"})
            return {k: v for k, v in q.items() if k != "records"}
        trigger, lower = q["trigger"], q["source_bounds"][0]
        existing = next(
            (d for d in self.decisions() if d.symbol == symbol and d.trigger_close_ms == trigger), None
        )
        if existing:
            ensure(existing.diagnostics["holding_hours"] == holding_hours, "LIVE_PLAN_HORIZON_IMMUTABLE")
            return self.existing_review(existing, q)
        day = trigger // INTERVALS["1D"]
        cycles = {
            d.trigger_close_ms for d in self.decisions() if d.trigger_close_ms // INTERVALS["1D"] == day
        }
        ensure(trigger in cycles or len(cycles) < 2, "LIVE_TWO_MANUAL_REVIEW_CYCLES_PER_DAY_MAX")
        rows, _ = causal(q["records"], symbol, trigger, lower)
        metadata = {
            "exposure": self.store.meta["evidence_class"],
            "snapshot_sha256": q["snapshot_sha256"],
            "admitted_prefix": tuple(r.model_dump(mode="json") for r in rows),
            "review_local": q["sample"],
            "review_source_bounds_ms": tuple(q["source_bounds"]),
            "clock_condition": q["clock"],
            "data_status": q["data_status"],
            **self.decision_metadata(q, symbol),
        }
        d = self.compile(symbol, trigger, lower, q["records"], holding_hours, metadata)
        self.events.append("DECISION", d.model_dump(mode="json"))
        return d

    def observe(self, identity):
        d = next(d for d in self.decisions() if d.episode_id == identity)
        q = self.source.assess(d.symbol)
        self._assessment = {**q, "records": self.source.receipts() if q["status"] == "ELIGIBLE" else []}
        ensure(q["status"] == "ELIGIBLE", q["reason"], q["status"])
        lower = q["source_bounds"][0]
        observation = observe_path(
            d,
            self._assessment["records"],
            asof_ms=lower,
            decision_parser=self.decision_model.model_validate_json,
            observation_factory=lambda **kw: JObservation(**kw, exposure=d.exposure),
            evidence_reason="PUBLIC_REST_OHLC_CONDITIONAL_PATH_NOT_EXCHANGE_FILL_OR_ECONOMIC_PROOF",
        )
        value = observation.model_dump(mode="json")
        value.update(
            snapshot_sha256=q["snapshot_sha256"],
            observed_local=q["sample"],
            observed_source_bounds=q["source_bounds"],
        )
        previous = [r for r in self.events.values("OBSERVATION") if r["episode_id"] == identity]
        if not previous or previous[-1] != value:
            self.events.append("OBSERVATION", value)
        advance_episode(self, identity, now_ms=lower, decision_parser=self.decision_model.model_validate_json)
        return value

    def snapshot(self):
        q = self.source.assess()
        snapshots = self.store.snapshots()
        last = snapshots[-1] if snapshots else None
        value = {
            "schema_version": "J_PUBLIC_DASHBOARD_V1",
            "mode": "EXPLORATORY_MVP",
            "evidence_class": self.store.meta["evidence_class"],
            "data": {k: v for k, v in q.items() if k != "records"},
            "decisions": [d.model_dump(mode="json") for d in self.decisions()],
            "lifecycle": self.events.values("LIFECYCLE"),
            "observations": self.events.values("OBSERVATION"),
            "source_qualified": False,
            "shadow_qualified": False,
            "economically_validated": False,
            "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
            "source_provenance": [
                {
                    "evidence_class": self.store.meta["evidence_class"],
                    "host": POLICY["host"],
                    "routes": POLICY["routes"],
                    "signed_exchange_observations": False,
                    "original_source_publication_ms": None,
                    "snapshot_sha256": digest(last) if last else None,
                    "source_asof_UTC_bounds": last["source_bounds"] if last else None,
                    "response_receipts": len(self.events.values("HTTP_RESPONSE")),
                    "durable_prefix_sha256": self.events.verify(),
                }
            ],
            "timestamp_semantics": "REST event/publication times UNKNOWN. Candle boundaries, HTTPS server-time bounds, local wall/monotonic receive/durable and actual manual-review times are retained separately. Unsigned operational data, never Strict UTC/Source evidence.",
            "limitations": [
                "PUBLIC_OPERATIONAL_ONLY_NOT_STRICT_NATIVE",
                "NO_EXCHANGE_SIGNATURE_OR_INDEPENDENT_UTC_QUALIFICATION",
                "OHLC_INTRABAR_ORDER_UNKNOWN_NO_FILL_INFERRED",
                "COST_GEOMETRY_UNCALIBRATED_NOT_REALIZED_R",
                "ACCOUNT_UNKNOWN_ACCOUNT_VETO_S2_S3_DISABLED",
            ],
        }
        value["snapshot_sha256"] = digest(value)
        return value

    def dashboard(self, output=None):
        ensure(output is None, "LIVE_DASHBOARD_USES_STORE_LOCAL_OUTPUT")
        result = super().dashboard()
        path = self.store.directory / "dashboard/latest.html"
        extra = table(
            [
                {
                    "Evidence": self.store.meta["evidence_class"],
                    "Transport": "LOCAL FABRICATED TLS QA"
                    if self.store.meta["evidence_class"] == QA
                    else "UNSIGNED PUBLIC HTTPS; NOT STRICT SOURCE",
                    "Actual fills / verified profit": "UNKNOWN / NONE INFERRED",
                }
            ]
        )

        def utc(milliseconds):
            return (
                datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat()
                if milliseconds
                else None
            )

        extra += table(
            [
                {
                    "Symbol": d.symbol,
                    "Planned gross R": d.diagnostics.get("planned_gross_r"),
                    "Hypothetical cost assumptions bps": d.diagnostics["hypothetical_costs_bps"],
                    "Source/as-of UTC lower": utc(d.review_source_bounds_ms[0]),
                    "Source/as-of UTC upper": utc(d.review_source_bounds_ms[1]),
                    "Latest completed 1D UTC": utc(d.diagnostics.get("1D", {}).get("last_completed_end_ms")),
                    "Latest completed 4H UTC": utc(d.diagnostics.get("4H", {}).get("last_completed_end_ms")),
                    "Entry expiry UTC": utc(d.opportunity.expires_ms) if d.opportunity else None,
                }
                for d in self.decisions()
            ]
        )
        temp = path.with_suffix(".html.tmp")
        temp.write_text(path.read_text().replace("</html>", extra + "</html>"), encoding="utf-8")
        temp.replace(path)
        return result

    def evaluate(self, output):
        from program_c.protocol import load_protocol
        from program_c.validation import validate, C_SCHEMA
        from program_c.integrity import digest as c_digest

        directory = path_guard(output)
        ensure(not directory.exists(), "LIVE_EVALUATION_OUTPUT_MUST_BE_UNUSED")
        directory.mkdir(parents=True)
        decisions = self.decisions()
        protocol = load_protocol()
        export = {
            "schema_version": "J_EXPLORATORY_EPISODE_EXPORT_V1",
            "evidence_class": self.store.meta["evidence_class"],
            "decisions": [d.model_dump(mode="json") for d in decisions],
            "observations": self.events.values("OBSERVATION"),
            "lifecycle": self.events.values("LIFECYCLE"),
            "strict_source_qualified": False,
            "economic_evidence": False,
        }
        write_json(directory / "J_episode_export.json", export)
        gate = {
            "schema_version": C_SCHEMA,
            "protocol_sha256": protocol["protocol_sha256"],
            "source_kind": self.store.meta["evidence_class"],
            "native_admission": None,
            "synthetic_manifest": None,
            "historical_bounded": False,
            "evaluation_asof_ms": max([d.decision_ms for d in decisions] or [1]),
            "episodes": [],
            "control_pool": [],
            "no_setup_decision_count": sum(d.market_state == "NO_SETUP" for d in decisions),
        }
        gate["export_sha256"] = c_digest(gate)
        write_json(directory / "C_source_class_gate_probe.json", gate)
        try:
            validate(canonical(gate), protocol)
        except ValueError as error:
            blocker = str(error)
        else:
            raise Blocked("C_PROTOCOL_CHANGED_REQUIRES_INDEPENDENT_REVIEW")
        ensure(blocker == "SOURCE_CLASS_INVALID", "C_UNEXPECTED_SCHEMA_GATE:" + blocker)
        result = {
            "schema": "J_C_ADMISSION_RESULT_V1",
            "scientific_decision": "INSUFFICIENT_SUPPORT",
            "evaluator_status": "SCHEMA_BLOCKED_NEW_J_EVIDENCE_CLASS",
            "actual_C_validator_error": blocker,
            "C_protocol_sha256": protocol["protocol_sha256"],
            "source_kind": self.store.meta["evidence_class"],
            "source_relabeling": False,
            "C_economic_ledger_executed": False,
            "economically_validated": False,
            "export": str(directory / "J_episode_export.json"),
        }
        write_json(directory / "evaluation_status.json", result)
        (directory / "evaluator_status.md").write_text(
            "# Program C admission for exploratory J evidence\n\nINSUFFICIENT_SUPPORT. "
            "The unchanged C validator rejected SOURCE_CLASS_INVALID. No economic ledger was run; "
            "J observations remain in their original evidence class. No realized/executable R or alpha is inferred.\n"
        )
        return result
