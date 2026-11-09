"""Opt-in operational time successor. Frozen L transport/S1/validators remain intact."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Literal
import time

from pydantic import model_validator

from ..core import fingerprint
from ..native.contract import digest, strict
from ..qualification.source import causal
from ..rc_models import STRATEGY_VERSION, frozen_contract
from ..rc_strategy import compile_s1
from ..reporting import table
from ..swing import INTERVALS, SwingPolicy
from .models import POLICY, Receipt, ensure, offset_step, sample
from .source import Collector, metadata, parse_rows, project, reference
from .swing_review import (
    SwingDecision,
    SwingProduct,
    V2_HASH,
    actionability,
    observation,
    product_for as old_product_for,
    verify_market,
    window_minutes,
)

CONTRACT = strict((Path(__file__).parent / "operational_clock.json").read_bytes())
VERSION = CONTRACT["schema"]
HASH = digest(CONTRACT)
PRODUCT = CONTRACT["product"]
FIELDS = ("wall_ms", "mono_before_ms", "mono_after_ms", "boot_id")


def mono_check(a, b):
    ensure(a["boot_id"] == b["boot_id"], "O_BOOT_CHANGE", "LIVE_CLOCK_DEGRADED_BLOCKED")
    ensure(
        0 <= a["mono_after_ms"] - a["mono_before_ms"] <= 5
        and 0 <= b["mono_after_ms"] - b["mono_before_ms"] <= 5
        and b["mono_before_ms"] >= a["mono_after_ms"],
        "O_MONOTONIC_DISCONTINUITY",
        "LIVE_CLOCK_DEGRADED_BLOCKED",
    )


def control_sample():
    s = sample()
    ensure(
        hasattr(time, "CLOCK_MONOTONIC_RAW") and hasattr(time, "CLOCK_BOOTTIME"),
        "O_INDEPENDENT_LOCAL_CLOCK_DOMAINS_REQUIRED",
        "LIVE_CLOCK_DEGRADED_BLOCKED",
    )
    s.update(
        raw_ms=time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW) // 1000000,
        boottime_ms=time.clock_gettime_ns(time.CLOCK_BOOTTIME) // 1000000,
        control_end_ms=time.monotonic_ns() // 1000000,
    )
    ensure(
        0 <= s["control_end_ms"] - s["mono_before_ms"] <= 5,
        "O_CONTROL_SAMPLE_UNCERTAIN",
        "LIVE_CLOCK_DEGRADED_BLOCKED",
    )
    return s


def control_check(a, b):
    mono_check(a, b)
    ensure(
        all(0 <= s["control_end_ms"] - s["mono_before_ms"] <= 5 for s in (a, b)),
        "O_CONTROL_SAMPLE_UNCERTAIN",
        "LIVE_CLOCK_DEGRADED_BLOCKED",
    )
    tolerance = 50 + (a["control_end_ms"] - a["mono_before_ms"]) + (b["control_end_ms"] - b["mono_before_ms"])
    for field in ("raw_ms", "boottime_ms"):
        ensure(
            b[field] >= a[field]
            and abs((b[field] - b["mono_before_ms"]) - (a[field] - a["mono_before_ms"])) <= tolerance,
            "O_MONOTONIC_RAW_OR_BOOTTIME_DISCONTINUITY",
            "LIVE_CLOCK_DEGRADED_BLOCKED",
        )


def reconcile_reference(a, b):
    ensure(
        a["boot_id"] == b["boot_id"]
        and max(a["offset_lower_ms"], b["offset_lower_ms"])
        <= min(a["offset_upper_ms"], b["offset_upper_ms"]),
        "O_VENUE_REFERENCE_MISMATCH",
        "LIVE_CLOCK_DEGRADED_BLOCKED",
    )


class OperationalCollector(Collector):
    shadow_only = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ensure(self.grace >= 120000, "O_GRACE_AT_LEAST_120_SECONDS")
        ensure(self.max_age <= 120000, "O_REFERENCE_MAX_AGE_120_SECONDS")
        self.control = control_sample()
        mono_check(self.start, self.control)
        self.last = self.control
        self.phase = "INITIAL"
        self.wall_steps = []
        self.controls = [self.control]

    def track(self, stamp, role):
        mono_check(self.last, stamp)
        if offset_step(self.last, stamp):
            event = {
                "session": self.session,
                "ordinal": self.requests,
                "phase": self.phase,
                "role": role,
                "before": self.last,
                "after": stamp,
                "threshold_ms": 50,
                "wall_minus_mono_change_ms": (stamp["wall_ms"] - stamp["mono_before_ms"])
                - (self.last["wall_ms"] - self.last["mono_before_ms"]),
                "quality": "CLOCK_DEGRADED",
                "source_UTC_claim": False,
            }
            self.wall_steps.append(event)
            self.store.events.append("O_WALL_CLOCK_DEGRADED", event)
        self.last = stamp

    def tick(self, role):
        s = control_sample()
        try:
            control_check(self.control, s)
            control_check(self.controls[0], s)
        except ValueError as error:
            # The rejected observation is evidence too; never discard its counters.
            self.store.events.append(
                "O_CONTROL_CLOCK_REJECTED",
                {
                    "session": self.session,
                    "role": role,
                    "quality": "CLOCK_DEGRADED",
                    "anchor": self.controls[0],
                    "previous": self.control,
                    "observed": s,
                    "reason": str(error),
                    "admission": "HARD_STOP",
                },
            )
            raise
        self.track(s, role)
        self.control = s
        self.controls.append(s)
        ensure(s["control_end_ms"] <= self.deadline, "LIVE_SESSION_DURATION_EXCEEDED")
        return s

    def get(self, route, params):
        # Same J transport/budget/receipt rules; clock policy is explicitly separate.
        now = self.tick("BEFORE_REQUEST")
        remaining = (self.deadline - now["control_end_ms"]) / 1000
        weight = 2 if params.get("limit", 0) >= 100 else 1
        ensure(
            remaining > 0.3
            and self.requests < 24
            and self.weight + weight <= 40
            and self.size + POLICY["response_bytes_max"] <= POLICY["session_bytes_max"],
            "LIVE_FINITE_REQUEST_BUDGET",
        )
        self.store.capacity()
        self.requests += 1
        self.weight += weight
        self.store.events.append(
            "REQUEST_ADMITTED",
            {
                "session": self.session,
                "ordinal": self.requests,
                "route": route,
                "params": params,
                "charged_weight": weight,
                "sample": {k: now[k] for k in FIELDS},
                "operational_phase": self.phase,
                "operational_time_policy_sha256": HASH,
            },
        )
        wire = self.transport.request(route, params, min(8, remaining - 0.2))
        raw, record = self.store.persist_response(self.session, self.requests, wire)
        # Preserve every received byte even if its clocks subsequently reject it.
        self.size += len(raw)
        for field in ("request_sample", "receive_sample", "durable_sample"):
            self.track(record[field], field)
        self.tick("AFTER_RESPONSE")
        ensure(record.get("response_complete", True), "LIVE_RESPONSE_SIZE_LIMIT_TRUNCATED_RECEIPT")
        ensure(self.size <= POLICY["session_bytes_max"], "LIVE_RESPONSE_BYTE_BUDGET")
        ensure(
            record["status"] == 200,
            "LIVE_HTTP_DENIED_OR_LIMITED_" + str(record["status"]) + "_NO_RETRY_OR_GEO_BYPASS",
        )
        ensure("application/json" in record["headers"].get("content-type", ""), "LIVE_NON_JSON_RESPONSE")
        used = record["headers"].get("x-mbx-used-weight-1m")
        ensure(used is None or (used.isdigit() and int(used) <= 2000), "LIVE_SHARED_RATE_BUDGET_UNCERTAIN")
        value = strict(b'{"response":' + raw + b"}")
        ensure(set(value) == {"response"}, "LIVE_JSON_TRAILING_OR_MULTIPLE_VALUES")
        return value["response"], record

    def full_pass(self):
        first = self.get("/fapi/v1/time", {})
        ensure(
            isinstance(first[0], dict) and type(first[0].get("serverTime")) is int,
            "LIVE_SERVER_TIME_SCHEMA",
            "LIVE_CLOCK_DEGRADED_BLOCKED",
        )
        w = first[1]
        lower = (
            first[0]["serverTime"]
            - (w["receive_sample"]["mono_after_ms"] - w["request_sample"]["mono_before_ms"])
            - 1
        )
        trigger = lower // INTERVALS["4H"] * INTERVALS["4H"]
        batches = []
        bars = POLICY["bars"] if self.shadow_only else {"1D": 80, "4H": 100}
        for symbol in POLICY["symbols"]:
            for interval, count in bars.items():
                width = INTERVALS[interval]
                end = (lower - self.grace) // width * width
                start = end - count * width
                ensure(
                    not any(start < hi and end > lo for lo, hi in self.exclusions["excluded_UTC_ms_ranges"]),
                    "LIVE_HOLDOUT_DATE_OVERLAP_FORBIDDEN",
                )
                body, wire = self.get(
                    "/fapi/v1/klines",
                    {
                        "symbol": symbol,
                        "interval": interval.lower(),
                        "startTime": start,
                        "endTime": end - 1,
                        "limit": count,
                    },
                )
                batches.append((body, wire, symbol, interval, start, end))
        current = []
        if not self.shadow_only:
            for symbol in POLICY["symbols"]:
                ensure(
                    not any(
                        trigger < hi and trigger + INTERVALS["4H"] > lo
                        for lo, hi in self.exclusions["excluded_UTC_ms_ranges"]
                    ),
                    "LIVE_HOLDOUT_DATE_OVERLAP_FORBIDDEN",
                )
                body, wire = self.get(
                    "/fapi/v1/klines",
                    {
                        "symbol": symbol,
                        "interval": "4h",
                        "startTime": trigger,
                        "endTime": trigger + INTERVALS["4H"] - 1,
                        "limit": 1,
                    },
                )
                current.append((body, wire, symbol))
        last = self.get("/fapi/v1/time", {})
        ref = reference(first, last)
        records = []
        for body, wire, symbol, interval, start, end in batches:
            rows, _ = parse_rows(
                body,
                symbol,
                interval,
                start=start,
                end=end,
                source_lower=lower,
                grace_ms=self.grace,
                wire=wire,
                ref=ref,
                exposure=self.exposure,
            )
            records.extend(rows)
        market = {
            "reference": ref,
            "time_responses": [[v["session"], v["ordinal"]] for _, v in (first, last)],
            "observations": [observation(b, w, ref, trigger, s) for b, w, s in current],
        }
        return {
            "records": records,
            "reference": ref,
            "swing_market": market,
            "pass_ordinals": [first[1]["ordinal"], last[1]["ordinal"]],
        }

    def run(self):
        self.store.recover()
        self.store.events.append(
            "SESSION_START",
            {
                "session": self.session,
                "sample": self.start,
                "exposure": self.exposure,
                "policy_sha256": HASH,
                "access_sha256": digest(self.access.model_dump(mode="json")) if self.access else None,
            },
        )
        try:
            ensure(
                not self.store.events.values("SOURCE_STOP") and not self.store.events.values("O_FATAL_STOP"),
                "O_UNRESOLVED_FATAL_SOURCE_STOP_REQUIRES_FRESH_SCOPE",
            )
            previous = self.store.snapshots()
            if previous:
                old = previous[-1]["o_clock"]["control_samples"][-1]
                mono_check(old, self.control)
                if self.control["mono_before_ms"] - old["mono_after_ms"] <= 120000:
                    control_check(old, self.control)
            info, wire = self.get("/fapi/v1/exchangeInfo", {})
            instruments = metadata(info)
            initial = self.full_pass()
            self.tick("INITIAL_PASS_END")
            result = initial
            witness = False
            if self.wall_steps:
                witness = True
                self.store.events.append(
                    "O_QUARANTINED_INITIAL_PASS",
                    {
                        "session": self.session,
                        "records_sha256": digest(initial["records"]),
                        "pass_ordinals": initial["pass_ordinals"],
                        "wall_step_count": len(self.wall_steps),
                        "not_eligible_for_decisions": True,
                    },
                )
                self.phase = "WITNESS"
                step_count = len(self.wall_steps)
                result = self.full_pass()
                self.tick("WITNESS_PASS_END")
                ensure(
                    len(self.wall_steps) == step_count,
                    "O_WITNESS_CLOCK_STILL_DEGRADED",
                    "LIVE_CLOCK_DEGRADED_BLOCKED",
                )
                reconcile_reference(initial["reference"], result["reference"])
                ensure(
                    {r["identity"]: r["content_sha256"] for r in initial["records"]}
                    == {r["identity"]: r["content_sha256"] for r in result["records"]},
                    "O_REVISED_OR_CHANGED_COMPLETED_WITNESS",
                    "SOURCE_BLOCKED",
                )
                # A forming candle may evolve, but its cumulative extremes cannot regress.
                for old, new in zip(
                    initial["swing_market"]["observations"], result["swing_market"]["observations"]
                ):
                    ensure(
                        old["cycle_open_ms"] == new["cycle_open_ms"]
                        and old["open"] == new["open"]
                        and new["high"] >= old["high"]
                        and new["low"] <= old["low"],
                        "O_CURRENT_CANDLE_REVISION_OR_CYCLE_CHANGE",
                        "SOURCE_BLOCKED",
                    )
            self.phase = "COMMIT"
            before = len(self.wall_steps)
            now = self.tick("BEFORE_COMMIT")
            ensure(len(self.wall_steps) == before, "O_POST_PROOF_WALL_STEP", "LIVE_CLOCK_DEGRADED_BLOCKED")
            if previous:
                # Each separately authorized finite session has a fresh mapping.
                # Do not extrapolate an expired mapping or treat normal long-term
                # RAW/discipled-monotonic frequency drift as a sampled clock step.
                prior_sample = previous[-1]["o_clock"]["control_samples"][-1]
                if now["mono_before_ms"] - prior_sample["mono_after_ms"] <= 120000:
                    reconcile_reference(previous[-1]["reference"], result["reference"])
                ensure(
                    project(result["reference"], now, self.max_age)[0] >= previous[-1]["source_bounds"][0],
                    "O_VENUE_TIME_REGRESSION_BETWEEN_SESSIONS",
                    "LIVE_CLOCK_DEGRADED_BLOCKED",
                )
            prior = {r["identity"]: r for r in self.store.records()}
            for row in result["records"]:
                ensure(
                    row["identity"] not in prior
                    or prior[row["identity"]]["content_sha256"] == row["content_sha256"],
                    "LIVE_UNRESOLVED_CANDLE_REVISION",
                    "SOURCE_BLOCKED",
                )
            result["records"] = [prior.get(v["identity"], v) for v in result["records"]]
            snapshot = {
                "schema": "O_OPERATIONAL_SNAPSHOT_V1",
                "session": self.session,
                "exposure": self.exposure,
                **result,
                "last_sample": {k: now[k] for k in FIELDS},
                "source_bounds": list(project(result["reference"], now, self.max_age)),
                "grace_ms": self.grace,
                "reference_max_age_ms": self.max_age,
                "instruments": instruments,
                "metadata_response_sha256": wire["body_sha256"],
                "requests": self.requests,
                "request_weight": self.weight,
                "response_bytes": self.size,
                "clock": "CLOCK_DEGRADED_RECONCILED"
                if self.wall_steps
                else "OPERATIONAL_VENUE_MONOTONIC_LOCAL_WALL_UNQUALIFIED",
                "retention_days": self.access.retention_days if self.access else 1,
                "incomplete_rows_excluded": 0,
                "operational_time_policy_sha256": HASH,
                "shadow_observation_only": self.shadow_only,
                "o_clock": {
                    "policy_sha256": HASH,
                    "witness_used": witness,
                    "accepted_pass": result["pass_ordinals"],
                    "initial_pass": initial["pass_ordinals"],
                    "wall_steps": self.wall_steps,
                    "control_samples": self.controls,
                    "strict_UTC_qualified": False,
                    "source_qualified": False,
                },
            }
            verify_snapshot(self.store, snapshot)
            self.store.events.append("SNAPSHOT", snapshot)
            self.store.events.append(
                "SESSION_TERMINAL",
                {
                    "session": self.session,
                    "status": "COMPLETE",
                    "snapshot_sha256": digest(snapshot),
                    "requests": self.requests,
                    "weight": self.weight,
                    "response_bytes": self.size,
                },
            )
            self.store.events.append("O_CLOCK_STATE", {"session": self.session, "held": False})
            return snapshot
        except BaseException as error:
            reason = str(error)
            self.store.events.append(
                "O_CLOCK_STATE", {"session": self.session, "held": True, "reason": reason}
            )
            if any(n in reason for n in ("BOOT_CHANGE", "MONOTONIC_", "CONTROL_SAMPLE")):
                self.store.events.append("O_FATAL_STOP", {"session": self.session, "reason": reason})
            if "REVISION" in reason or "REVISED" in reason:
                self.store.events.append("SOURCE_STOP", {"session": self.session, "reason": reason})
            self.store.events.append(
                "SESSION_TERMINAL",
                {
                    "session": self.session,
                    "status": "FAILED",
                    "reason": reason,
                    "requests": self.requests,
                    "weight": self.weight,
                    "response_bytes": self.size,
                },
            )
            raise


class OperationalObserver(OperationalCollector):
    shadow_only = True


def verify_snapshot(store, s):
    ensure(s.get("operational_time_policy_sha256") == HASH, "O_TIME_POLICY_REQUIRED")
    proof = s["o_clock"]
    ensure(proof["policy_sha256"] == HASH, "O_CLOCK_PROOF_HASH")
    controls = proof["control_samples"]
    for a, b in zip(controls, controls[1:]):
        control_check(a, b)
        control_check(controls[0], b)
    wires = sorted(
        (w for w in store.events.values("HTTP_RESPONSE") if w["session"] == s["session"]),
        key=lambda w: w["ordinal"],
    )
    admissions = [w for w in store.events.values("REQUEST_ADMITTED") if w["session"] == s["session"]]
    ensure(
        len(wires) == len(admissions) == s["requests"] <= 24
        and sum(w["charged_weight"] for w in admissions) == s["request_weight"] <= 40,
        "O_REQUEST_ACCOUNTING",
    )
    steps = []
    last = controls[0]
    wire_by_id = {w["ordinal"]: w for w in wires}
    for w in wires:
        # Admissions are sampled immediately before their HTTP worker.
        for item in [
            admissions[w["ordinal"] - 1]["sample"],
            w["request_sample"],
            w["receive_sample"],
            w["durable_sample"],
        ]:
            mono_check(last, item)
            if offset_step(last, item):
                steps.append(item["mono_after_ms"])
            last = item
    # Every runtime diagnostic is independently bound to journaled raw samples.
    logged = [e for e in store.events.values("O_WALL_CLOCK_DEGRADED") if e["session"] == s["session"]]
    ensure(logged == proof["wall_steps"], "O_WALL_EVIDENCE_TAMPER")
    for e in logged:
        mono_check(e["before"], e["after"])
        ensure(offset_step(e["before"], e["after"]), "O_FALSE_WALL_WARNING")
    if proof["witness_used"]:
        ensure(proof["wall_steps"], "O_WITNESS_WITHOUT_WARNING")
        start, end = proof["accepted_pass"]
        ensure(
            (not steps or max(steps) <= wire_by_id[start]["request_sample"]["mono_before_ms"])
            and start > proof["initial_pass"][1]
            and end == s["requests"]
            and all(
                e["after"]["mono_after_ms"] <= wire_by_id[start]["request_sample"]["mono_before_ms"]
                for e in proof["wall_steps"]
            ),
            "O_WITNESS_NOT_AFTER_LAST_STEP",
        )
    else:
        ensure(not steps and not proof["wall_steps"], "O_MISSING_POST_ANOMALY_WITNESS")
    start, end = proof["accepted_pass"]
    ensure(
        proof["initial_pass"] == [2, 12]
        and [start, end] == ([13, 23] if proof["witness_used"] else [2, 12])
        and s["requests"] == (23 if proof["witness_used"] else 12),
        "O_FIXED_FINITE_PHASE_ACCOUNTING",
    )
    ensure(end - start == 10, "O_FULL_PASS_REQUIRED")
    accepted = [w for w in wires if start <= w["ordinal"] <= end]
    ensure(accepted[0]["route"] == accepted[-1]["route"] == "/fapi/v1/time", "O_PROBE_ROUTES")

    def body(w):
        raw = (store.directory / w["raw_path"]).read_bytes()
        import hashlib

        ensure(hashlib.sha256(raw).hexdigest() == w["body_sha256"], "O_RAW_PROOF_HASH")
        ensure(
            w["tls"]["chain"] == "CERT_REQUIRED"
            and w["tls"]["hostname_verified"]
            and w["tls"]["host"] == w["tls"]["sni"] == "fapi.binance.com",
            "O_ORIGINAL_TARGET_TLS",
        )
        return strict(b'{"response":' + raw + b"}")["response"]

    ref = reference((body(accepted[0]), accepted[0]), (body(accepted[-1]), accepted[-1]))
    ensure(ref == s["reference"], "O_TIME_PROOF_MISMATCH")
    ensure(len(accepted) == 11, "O_COMPLETE_ACCEPTED_PASS")
    if not s["shadow_observation_only"]:
        verify_market(store, s, controls[-1])
    # Raw completed normalization and instrument checks are independently rebuilt
    # by frozen Store.snapshots() on every persisted restart.
    ensure(
        controls[-1]["mono_after_ms"] >= accepted[-1]["durable_sample"]["mono_after_ms"]
        and controls[-1]["control_end_ms"] - controls[0]["mono_before_ms"] <= 120000,
        "O_COMMIT_CLOCK_OR_DURATION",
    )


class OperationalSource:
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
            ss = self.store.snapshots()
            ensure(ss, "O_NO_ADMITTED_SNAPSHOT", "SOURCE_BLOCKED")
            ensure(
                not self.events.values("SOURCE_STOP") and not self.events.values("O_FATAL_STOP"),
                "O_SOURCE_FATAL_STOP",
                "SOURCE_BLOCKED",
            )
            ensure(
                self.events.values("SESSION_TERMINAL")[-1]["status"] == "COMPLETE",
                "O_LAST_SESSION_FAILED",
                "SOURCE_BLOCKED",
            )
            s = ss[-1]
            verify_snapshot(self.store, s)
            now = control_sample()
            prior = s["o_clock"]["control_samples"][-1]
            control_check(prior, now)
            ensure(
                not offset_step(prior, now),
                "O_WALL_STEP_AFTER_PROOF_NEEDS_NEW_AUTHORIZED_SCAN",
                "LIVE_CLOCK_DEGRADED_BLOCKED",
            )
            lo, hi = project(s["reference"], now, s["reference_max_age_ms"])
            trigger = lo // INTERVALS["4H"] * INTERVALS["4H"]
            ensure(
                hi < ss[0]["source_bounds"][0] + s["retention_days"] * INTERVALS["1D"],
                "LIVE_RETENTION_EXPIRED_OPERATOR_DELETION_REQUIRED",
            )
            limit = self.events.values("MANUAL_REVIEW_POLICY")[0]["window_minutes"]
            open_window = max(120000, s["grace_ms"]) <= lo - trigger and hi - trigger <= limit * 60000
            if review:
                ensure(open_window, "O_REVIEW_HORIZON_EXPIRED", "SOURCE_BLOCKED")
                ensure(not s["shadow_observation_only"], "O_FRESH_SCAN_REQUIRED", "SOURCE_BLOCKED")
            quotes = {} if s["shadow_observation_only"] else verify_market(self.store, s, now)
            return {
                "status": "ELIGIBLE",
                "data_status": "LIVE_OPERATIONAL_DATA_UNQUALIFIED",
                "clock": s["clock"],
                "source_bounds": [lo, hi],
                "trigger": trigger,
                "sample": {k: now[k] for k in FIELDS},
                "control_sample": now,
                "snapshot_sha256": digest(s),
                "reason": None,
                "records": [Receipt(v) for v in s["records"]],
                "market_observations": quotes,
                "review_not_before_ms": max(
                    (q["available_bounds_ms"][1] for q in quotes.values()), default=0
                ),
                "review_window_open": open_window,
                "operational_time_policy": VERSION,
                "clock_evidence": s["o_clock"],
                "new_candidate_generation": "REQUIRES_FRESH_MANUAL_REVIEW"
                if open_window and quotes
                else "SOURCE_BLOCKED",
                "coverage": {
                    name: {
                        i: sum(
                            r["candle"]["symbol"] == name and r["candle"]["interval"] == i
                            for r in s["records"]
                        )
                        for i in ("1D", "4H")
                    }
                    for name in POLICY["symbols"]
                },
            }
        except (ValueError, KeyError) as error:
            return {
                "observed_control_sample": locals().get("now"),
                "last_verified_control_sample": locals().get("prior"),
                "status": getattr(error, "status", "SOURCE_BLOCKED"),
                "data_status": "DATA_NOT_READY",
                "clock": "CLOCK_DEGRADED_HOLD",
                "reason": str(error),
                "records": [],
            }


class OperationalDecision(SwingDecision):
    schema_version: Literal["O_PUBLIC_CLOCK_DECISION_V1"] = "O_PUBLIC_CLOCK_DECISION_V1"  # type: ignore[assignment]
    product_version: Literal["O_PUBLIC_SWING_CLOCK_V1"] = "O_PUBLIC_SWING_CLOCK_V1"  # type: ignore[assignment]
    contract_sha256: str = HASH
    clock_evidence: dict
    review_control_sample: dict

    @model_validator(mode="after")
    def integrity(self):
        ensure(
            self.contract_sha256 == HASH and self.clock_evidence["policy_sha256"] == HASH,
            "O_DECISION_CLOCK_CONTRACT",
        )
        ensure(fingerprint(list(self.admitted_prefix)) == self.prefix_sha256, "O_PREFIX_TAMPER")
        lo, hi = self.review_source_bounds_ms
        ensure(
            self.decision_ms == lo <= hi
            and self.trigger_close_ms + 120000 <= lo
            and hi <= self.trigger_close_ms + self.review_window_minutes * 60000,
            "O_ACTUAL_REVIEW_WINDOW",
        )
        ensure(self.scheduled_review_ms == SwingPolicy().next_review(lo), "O_SCHEDULED_REVIEW")
        ensure(
            {k: self.review_control_sample[k] for k in FIELDS} == self.review_local.model_dump(),
            "O_REVIEW_SAMPLE_BINDING",
        )
        prior = self.clock_evidence["control_samples"][-1]
        control_check(prior, self.review_control_sample)
        ensure(not offset_step(prior, self.review_control_sample), "O_POST_PROOF_WALL_STEP")
        q = self.market_observation
        ensure(
            q["symbol"] == self.symbol
            and q["cycle_open_ms"] == self.trigger_close_ms
            and q["available_bounds_ms"][1] <= lo
            and 0 <= hi - q["available_bounds_ms"][0] <= 30000,
            "O_PRICE_CAUSALITY",
        )
        positive = self.market_state in ("WATCH", "ARMED")
        ensure(positive == (self.opportunity is not None) == (self.episode_id is not None), "O_PLAN_STATE")
        if self.opportunity:
            plan = self.opportunity
            ensure(
                plan.setup_close_ms == self.trigger_close_ms
                and plan.symbol == self.symbol
                and 4 <= plan.holding_hours <= 48
                and plan.available_ms <= lo < self.scheduled_review_ms < plan.expires_ms
                and plan.account_status == "UNKNOWN"
                and plan.planned_after_cost_r >= 2,
                "O_CAUSAL_PLAN",
            )
            ensure(
                self.episode_id
                == fingerprint(
                    [PRODUCT, STRATEGY_VERSION, self.symbol, self.trigger_close_ms, self.prefix_sha256]
                ),
                "O_EPISODE_ID",
            )
            ensure(
                self.eligible_planned_r == tuple(r for r in (2, 3, 4) if r <= plan.planned_after_cost_r),
                "O_R_LABEL",
            )
            ensure(actionability(plan, q, hi) is None, "O_ACTIONABILITY")
        else:
            ensure(not self.eligible_planned_r, "O_NEGATIVE_R_LABEL")
        return self


class OperationalProduct(SwingProduct):
    source_view = OperationalSource  # type: ignore[assignment]  # Explicit versioned adapter, same interface.
    decision_model = OperationalDecision  # type: ignore[assignment]  # Deliberate schema successor.
    metadata_fields = (*SwingProduct.metadata_fields, "clock_evidence", "review_control_sample")

    def decision_metadata(self, q, symbol):
        return {
            **super().decision_metadata(q, symbol),
            "clock_evidence": q["clock_evidence"],
            "review_control_sample": q["control_sample"],
        }

    def compile(self, symbol, trigger, lower, records, holding, metadata):
        policy = SimpleNamespace(
            max_availability_delay_ms=metadata["review_window_minutes"] * 60000,
            minimum_history_bars=60,
            next_review=SwingPolicy().next_review,
        )

        def factory(**kw):
            kw["diagnostics"].update(
                hypothetical_costs_bps=frozen_contract()["strategy"]["costs_bps"],
                operational_time_policy=VERSION,
                actual_review_delay_ms=lower - trigger,
                signal_issued_at_close=False,
                local_wall_is_not_source_UTC=True,
            )
            if kw.get("opportunity"):
                reason = actionability(
                    kw["opportunity"], metadata["market_observation"], metadata["review_source_bounds_ms"][1]
                )
                if reason:
                    kw.update(
                        market_state="NO_SETUP",
                        reasons=(*kw["reasons"], reason),
                        opportunity=None,
                        episode_id=None,
                        eligible_planned_r=(),
                    )
                else:
                    kw["reasons"] = (*kw["reasons"], "O_POST_PROOF_CURRENT_PATH_NO_CHASE")
            return OperationalDecision(**kw, **metadata)

        return compile_s1(
            symbol=symbol,
            trigger_ms=trigger,
            decision_ms=lower,
            receipts=records,
            holding_hours=holding,
            asof_reader=causal,
            decision_factory=factory,
            product_id=PRODUCT,
            bar_policy=policy,
            source_reason="PUBLIC_HTTPS_UNSIGNED_OPERATIONAL_ONLY_ACCOUNT_VETO",
            cost_label="HYPOTHETICAL_UNCALIBRATED_FEE_SPREAD_SLIPPAGE_FUNDING_NOT_FILL_OR_RETURN",
        )

    def decisions(self):
        values = super().decisions()
        snapshots = {digest(s): s for s in self.store.snapshots()}
        for d in values:
            s = snapshots[d.snapshot_sha256]
            verify_snapshot(self.store, s)
            ensure(d.clock_evidence == s["o_clock"], "O_DECISION_PROOF_NOT_IN_SNAPSHOT")
        return values

    def snapshot(self):
        value = super().snapshot()
        value.update(schema_version="O_EXPLORATORY_DASHBOARD_V1", operational_time_policy=VERSION)
        value.pop("snapshot_sha256")
        value["snapshot_sha256"] = digest(value)
        return value

    def dashboard(self, output=None):
        result = super().dashboard(output)
        path = self.store.directory / "dashboard/latest.html"
        extra = table(
            [
                {
                    "Operational time policy": VERSION,
                    "Local wall quality": "Recorded, never overwritten or treated as UTC",
                    "Source time": "Fresh HTTPS venue bounds + boot-scoped monotonic; NOT STRICT UTC",
                    "Reconciliation": "Complete independent post-anomaly witness only; no warning bypass",
                }
            ]
        )
        path.write_text(path.read_text().replace("</html>", extra + "</html>"))
        return result


def product_for(store, requested=None, minutes=None):
    modes = store.events.values("MANUAL_REVIEW_POLICY")
    if modes and modes[0].get("policy") == VERSION:
        ensure(
            len(modes) == 1 and modes[0]["sha256"] == HASH and requested in (None, VERSION),
            "O_MODE_IMMUTABLE",
        )
        ensure(minutes is None or modes[0]["window_minutes"] == minutes, "O_WINDOW_IMMUTABLE")
        return OperationalProduct(store)
    if requested == VERSION:
        ensure(
            not modes
            and not store.events.values("SESSION_START")
            and not store.snapshots()
            and not store.events.values("DECISION"),
            "O_FRESH_OUTPUT_REQUIRED_NO_N_OR_L_PROMOTION",
        )
        store.events.append(
            "MANUAL_REVIEW_POLICY",
            {
                "policy": VERSION,
                "sha256": HASH,
                "manual_window_policy_sha256": V2_HASH,
                "window_minutes": window_minutes(120 if minutes is None else minutes),
            },
        )
        return OperationalProduct(store)
    return old_product_for(store, requested, minutes)
