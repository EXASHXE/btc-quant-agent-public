"""Seven evidence-based native Source stages. No authority comes from a label."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...domain import Candle
from ..native.audit import verify_capture_audit
from ..native.contract import (
    Envelope,
    AuditEnvelope,
    digest,
    require,
    strict,
    verify_key,
    ENDPOINT,
    CLOCK_ENDPOINT,
    STREAMS,
    REQUIRED_STREAMS,
)
from ..qualified_source import NativeQuarantineRecord, decode_binance_kline, BINANCE_VENUE
from ..swing import ClosedBar, INTERVALS, SwingPolicy, closed_bar_errors
from .evidence import Ledger, PlanEnvelope, SCHEMA_HASH, STAGES, TimedAuditEnvelope


@dataclass(frozen=True)
class SourceReceipt:
    value: dict
    bar: ClosedBar

    @property
    def identity(self):
        return self.value["identity"]

    @property
    def raw_sha256(self):
        return self.value["record"]["raw_sha256"]

    def model_dump(self, mode="json"):
        return self.value


def receipt(value):
    import base64

    r = NativeQuarantineRecord.model_validate(value["record"])
    verified = decode_binance_kline(
        base64.b64decode(r.raw_payload_b64),
        venue=BINANCE_VENUE,
        endpoint=ENDPOINT,
        received_ms=r.received_ms,
        available_ms=r.available_ms,
        durable_ms=r.durable_ms,
        observed_now_ms=r.durable_ms,
        expected_symbol=r.symbol,
        expected_interval={"1H": "1h", "4H": "4h", "1D": "1d"}[r.interval],
    )
    require(verified == r and r.identity == value["identity"], "NATIVE_RAW_NORMALIZED_BINDING")
    c = Candle(
        symbol=r.symbol,
        interval=r.interval,
        open_time_ms=r.open_time_ms,
        close_time_ms=r.close_time_ms,
        open=r.open,
        high=r.high,
        low=r.low,
        close=r.close,
        volume=r.volume,
        available_at_ms=r.available_ms,
    )
    b = ClosedBar(
        candle=c,
        source_id=r.source_id,
        source_event_ms=r.source_event_ms,
        received_ms=r.received_ms,
        available_ms=r.available_ms,
        durable_ms=r.durable_ms,
        revision=r.revision,
    )
    return SourceReceipt(value, b)


def causal(receipts, symbol, trigger, decision):
    rows = [
        r
        for r in receipts
        if r.bar.candle.symbol == symbol and r.bar.end_ms <= trigger and r.bar.durable_ms <= decision
    ]
    # Optional1H is used only with an adequate contiguous prefix. It never fills mandatory gaps.
    hourly = [r for r in rows if r.bar.candle.interval == "1H"]
    if hourly and (
        len(hourly) < 2
        or hourly[-1].bar.end_ms != trigger
        or any(b.bar.end_ms - a.bar.end_ms != INTERVALS["1H"] for a, b in zip(hourly, hourly[1:]))
    ):
        rows = [r for r in rows if r.bar.candle.interval != "1H"]
    return rows, ()


def clock_proof(value, g):
    e = value["clock_proof"]
    probes = e["probes"]
    require(len(probes) == 2, "TWO_NATIVE_CLOCK_PROBES_REQUIRED")
    previous = None
    samples: list[dict] = []
    for p in probes:
        wire = p.get("wire_record")
        require(
            isinstance(wire, dict) and digest(wire) == p["wire_sha256"],
            "NATIVE_CLOCK_RAW_WIRE_MISSING_OR_TAMPERED",
        )
        require(
            strict(wire["body"]).get("serverTime") == p["server_ms"], "NATIVE_CLOCK_RAW_SERVER_TIME_MISMATCH"
        )
        tls = wire["tls"]
        require(
            tls["host"] == tls["sni"] == "fapi.binance.com"
            and tls["chain"] == "CERT_REQUIRED"
            and tls["hostname_verified"] is True,
            "NATIVE_CLOCK_ORIGINAL_TARGET_TLS",
        )
        require(p["scope_sha256"] == digest(g), "CLOCK_SCOPE_MISMATCH")
        a, b = p["request"], p["receive"]
        require(
            a["mono_after_ms"] <= b["mono_before_ms"]
            and (
                not previous
                or previous["receive"]["mono_after_ms"] < a["mono_before_ms"]
                and previous["server_ms"] < p["server_ms"]
            ),
            "CLOCK_PROBE_ORDER_OR_REGRESSION",
        )
        samples.extend((a, b))
        previous = p
    low = min(p["server_ms"] - p["receive"]["mono_after_ms"] - 1 for p in probes)
    high = max(p["server_ms"] - p["request"]["mono_before_ms"] + 1 for p in probes)
    require(
        e["low"] == low and e["high"] == high and e["uncertainty_ms"] == (high - low) / 2 <= 100,
        "CLOCK_UNCERTAINTY",
    )
    received = value.get("receive_sample")
    require(isinstance(received, dict), "CLOCK_RECEIVE_MONOTONIC_BINDING_MISSING")
    require(received["wall_ms"] == value["record"]["received_ms"], "RECEIVE_CLOCK_BINDING")
    age = received["mono_after_ms"] - e["at_mono_ms"]
    require(0 <= age <= 300000 and e["at_mono_ms"] == probes[-1]["receive"]["mono_after_ms"], "CLOCK_STALE")
    require(age <= 120000, "CLOCK_REFRESH_CONTRACT_MISSED")
    samples.append(received)
    anchor = samples[0]
    for s in samples:
        require(0 <= s["mono_after_ms"] - s["mono_before_ms"] <= 5, "CLOCK_BRACKET_UNCERTAIN")
        lower = s["wall_ms"] - s["mono_after_ms"] - (anchor["wall_ms"] - anchor["mono_before_ms"]) - 1
        upper = s["wall_ms"] - s["mono_before_ms"] - (anchor["wall_ms"] - anchor["mono_after_ms"]) + 1
        require(lower >= -50 and upper <= 50, "CLOCK_EPOCH_UNQUALIFIED")
    return digest(e)


class StableJournal:
    """Verify the immutable Source once per assessment; reject concurrent file changes."""

    def __init__(self, base):
        self.base = base
        self.seal = base.verify()
        self.stamp = self.stat()
        with base.db() as db:
            self.by_session: dict[str, list[dict]] = {}
            for session, raw in db.execute(
                "SELECT f.session,r.value FROM frames f JOIN receipts r ON r.frame=f.id ORDER BY f.id"
            ):
                self.by_session.setdefault(session, []).append(strict(raw))

    def stat(self):
        st = self.base.path.stat()
        return st.st_ino, st.st_size, st.st_mtime_ns

    def verify(self):
        require(self.stat() == self.stamp, "CONCURRENT_NATIVE_SOURCE_CHANGE")
        return self.seal

    def db(self):
        self.verify()
        return self.base.db()

    def records(self, session):
        self.verify()
        return self.by_session.get(session, [])


class Qualification:
    def __init__(self, journal, ledger: Ledger, *, qa_roots=None, qa_schema_roots=None):
        self.journal, self.ledger = journal, ledger
        self.qa = qa_roots is not None
        if self.qa:
            self.roots, self.product_roots = qa_roots, qa_schema_roots or {}
        else:
            self.roots = strict((Path(__file__).parents[1] / "native/authority_roots.json").read_bytes())
            self.product_roots = strict((Path(__file__).parent / "roots.json").read_bytes())

    def assess(self, asof_ms):
        try:
            return self._assess(asof_ms)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            return {
                "status": "SOURCE_BLOCKED",
                "stages": [],
                "proof": {"input_failure": str(exc)},
                "cohort": digest(["FAILED_SOURCE", asof_ms]),
                "evidence_class": "SYNTHETIC_NETWORK_QA" if self.qa else "GENUINE_NATIVE",
                "source_qualified": False,
                "shadow_eligible": False,
                "records": [],
                "reason": str(exc),
            }

    def _assess(self, asof_ms):
        journal = StableJournal(self.journal)
        stages = []
        records = []
        proof: dict = {}
        plan = None
        cohort = digest(
            ["F_NATIVE_PRODUCT_V1", asof_ms, journal.verify()["head"], self.ledger.values("PLAN")]
        )
        evidence_class = "SYNTHETIC_NETWORK_QA" if self.qa else "GENUINE_NATIVE"

        def advance(stage):
            self.ledger.transition(cohort, stage, proof, evidence_class)
            stages.append(stage)

        try:
            plans = self.ledger.values("PLAN")
            require(len(plans) <= 1, "MULTIPLE_QUALIFICATION_PLANS")
            if plans:
                entry = plans[0]
                owner = PlanEnvelope.model_validate(entry["owner"])
                auditor = PlanEnvelope.model_validate(entry["auditor"])
                plan = owner.grant
                require(
                    plan.evidence_class == evidence_class and entry["evidence_class"] == evidence_class,
                    "EVIDENCE_CLASS_MISMATCH",
                )
                pk = verify_key(owner, self.roots.get("owner", {}))
                ak = verify_key(auditor, self.roots.get("auditor", {}))
                require(
                    pk != ak and owner.grant == auditor.grant and auditor.key_id == plan.auditor_key_id,
                    "PLAN_SIGNATURES",
                )
                require(plan.created_ms <= entry["persisted_ms"] < plan.start_ms, "PLAN_NOT_PREDECLARED")
            with journal.db() as db:
                sessions = {
                    sid: (strict(g), status)
                    for sid, g, status in db.execute("SELECT id,grant_json,status FROM sessions")
                    if strict(g)["start_ms"] <= asof_ms
                }
                values = [
                    strict(v)
                    for (v,) in db.execute("SELECT value FROM receipts ORDER BY frame")
                    if strict(v)["record"]["durable_ms"] <= asof_ms
                ]
                events = [
                    (sid, kind, strict(v))
                    for sid, kind, v in db.execute("SELECT session,kind,body FROM events ORDER BY seq")
                    if sid in sessions
                ]
            require(values, "NO_DURABLE_NATIVE_CANDLES")
            expected = "SYNTHETIC_NETWORK" if self.qa else "NATIVE_UNQUALIFIED"
            require(
                all(v["exposure"] == expected for v in values)
                and all(g["exposure"] == expected for g, _ in sessions.values()),
                "GENUINE_NATIVE_MISLABELED_SYNTHETIC",
            )
            proof = {
                "plan_sha256": digest(plan.model_dump(mode="json")) if plan else None,
                "prefix_sha256": digest(values),
                "asof_ms": asof_ms,
            }
            advance(STAGES[0])
            audits = {
                r["session"]: r["envelope"]
                for r in self.ledger.values("CAPTURE_AUDIT")
                if r["session"] in sessions
            }
            host_entries = {
                r["session"]: r["envelope"]
                for r in self.ledger.values("HOST_ADMISSION")
                if r["session"] in sessions
            }
            proof.update(
                {
                    "audits_sha256": digest(audits),
                    "host_admissions_sha256": digest(host_entries),
                    "authority_roots_sha256": digest(self.roots),
                    "product_roots_sha256": digest(self.product_roots),
                }
            )
            for sid, (g, status) in sessions.items():
                require(status == "CLOSED", "NATIVE_SAFETY_STOP_OR_FAILED_CLOSURE")
                auth = next((v for s, k, v in events if s == sid and k == "AUTHORIZATION_VERIFIED"), None)
                require(auth is not None, "SIGNED_SOURCE_PROVENANCE_MISSING")
                assert auth is not None
                env = Envelope.model_validate(auth["owner_envelope"])
                adm = AuditEnvelope.model_validate(auth["admission_auditor"])
                ownerkey = verify_key(env, self.roots.get("owner", {}))
                auditkey = verify_key(adm, self.roots.get("auditor", {}))
                require(
                    ownerkey != auditkey and env.grant.model_dump(mode="json") == g,
                    "GENUINE_SOURCE_SIGNATURE_BINDING",
                )
                require(
                    adm.key_id == g["auditor_key_id"]
                    and (plan is None or adm.key_id == plan.auditor_key_id)
                    and adm.grant.grant_sha256 == digest(g),
                    "AUDITOR_SCOPE",
                )
                require(
                    g["rights_sha256"] == self.roots.get("rights_sha256")
                    and (plan is None or g["rights_sha256"] == plan.rights_sha256)
                    and adm.grant.rights_sha256 == g["rights_sha256"],
                    "RIGHTS_BINDING",
                )
                require(
                    plan is None
                    or (
                        g["source_sha256"] == plan.source_sha256
                        and g["executable_sha256"] == plan.executable_sha256
                        and g["config_sha256"] == plan.config_sha256
                    ),
                    "FINAL_SOURCE_CONFIG_EXECUTABLE_BINDING",
                )
                require(g["streams"] in (STREAMS, REQUIRED_STREAMS), "EXACT_SIGNED_STREAM_SCOPE")
                require(
                    g["endpoint"] == ENDPOINT
                    and g["clock_endpoint"] == CLOCK_ENDPOINT
                    and g["issued_ms"] < g["start_ms"] < g["end_ms"]
                    and g["end_ms"] - g["start_ms"] <= 86400000,
                    "EXACT_SIGNED_SCOPE_WINDOW",
                )
                require(sid in audits, "INDEPENDENT_CAPTURE_AUDIT_MISSING")
                verify_capture_audit(
                    journal,
                    sid,
                    TimedAuditEnvelope.model_validate(audits[sid]),
                    self.roots,
                    synthetic=self.qa,
                )
                terminal = strict((Path(g["output"]) / "terminal.json").read_bytes())
                require(
                    terminal.get("reason") in ("PEER_CLOSED_NO_RECONNECT", "WINDOW_END_OR_NOT_OPEN")
                    and terminal.get("clock_failure_evidence") is None,
                    "UNRESOLVED_NATIVE_TERMINAL_SAFETY_STOP",
                )
                signed_audit = TimedAuditEnvelope.model_validate(audits[sid]).grant
                require(
                    type(terminal.get("closed_ms")) is int
                    and terminal["closed_ms"] <= signed_audit.audited_ms <= asof_ms,
                    "CAPTURE_AUDIT_NOT_AVAILABLE_AT_REVIEW",
                )
                require(sid in host_entries, "INDEPENDENT_HOST_CLOCK_ADMISSION_MISSING")
                require(
                    signed_audit.host_admission_sha256 == digest(host_entries[sid]),
                    "AUDITED_HOST_ADMISSION_BINDING",
                )
                require(
                    terminal["transport_closed"] and terminal["unsettled_frames"] == 0,
                    "FAILED_TERMINAL_CLOSURE",
                )
                tls = terminal.get("tls", [])
                require(
                    {"fapi.binance.com", "fstream.binance.com"} <= {t["host"] for t in tls}
                    and all(
                        t.get("chain") == "CERT_REQUIRED"
                        and t.get("hostname_verified")
                        and t.get("sni") == t["host"]
                        and t.get("route") == "HTTP_CONNECT"
                        for t in tls
                    ),
                    "ORIGINAL_TARGET_TLS_UNVERIFIED",
                )
            advance(STAGES[1])
            from .admission import HostEnvelope, verify_host
            from ..native.contract import Grant

            hosts = {
                r["session"]: HostEnvelope.model_validate(r["envelope"])
                for r in self.ledger.values("HOST_ADMISSION")
            }
            for v in values:
                sid = next((s for s, (g, _) in sessions.items() if digest(g) == v["grant_sha256"]), None)
                require(sid is not None, "RECEIPT_GRANT_LINEAGE")
                g = sessions[sid][0]
                require(
                    g["start_ms"] <= v["record"]["received_ms"] < g["end_ms"], "SOURCE_GRANT_RECEIVE_WINDOW"
                )
                require(sid in hosts, "INDEPENDENT_HOST_CLOCK_ADMISSION_MISSING")
                verify_host(
                    hosts[sid],
                    self.roots,
                    Grant.model_validate(g),
                    v["record"]["received_ms"],
                    qa=self.qa,
                    historical=True,
                )
                r = v["record"]
                stream = f"{r['symbol'].lower()}@kline_" + {"1H": "1h", "4H": "4h", "1D": "1d"}[r["interval"]]
                require(stream in g["streams"], "CANDLE_OUTSIDE_SIGNED_STREAM_SCOPE")
                clock_proof(v, g)
            advance(STAGES[2])
            require(
                not any(k == "SETTLED" and (v["state"] == "REJECTED") for _, k, v in events),
                "UNRESOLVED_SOURCE_REJECTION_OR_CORRECTION",
            )
            records = [receipt(v) for v in values]
            require(len({r.identity for r in records}) == len(records), "DUPLICATE_OR_CORRECTED_CANDLE")
            advance(STAGES[3])
            require(plan is not None, "SIGNED_AVAILABILITY_PLAN_MISSING")
            assert plan is not None
            trigger = asof_ms // INTERVALS["4H"] * INTERVALS["4H"]
            require(asof_ms - trigger <= 300000, "STALE_SOURCE")
            for symbol in plan.required_symbols:
                rows, _ = causal(records, symbol, trigger, asof_ms)
                errors = closed_bar_errors(
                    [r.bar for r in rows],
                    symbol=symbol,
                    decision_ms=asof_ms,
                    trigger_close_ms=trigger,
                    policy=SwingPolicy(),
                )
                require(not errors, "WARMUP_GAP_OR_STALE:" + ",".join(errors))
                require(
                    all(r.bar.candle.open_time_ms >= plan.start_ms for r in rows),
                    "UNAUTHORIZED_RETROSPECTIVE_WARMUP",
                )
            advance(STAGES[4])
            require(
                plan.end_ms <= asof_ms and plan.end_ms - plan.availability_start_ms == 7 * 86400000,
                "SEVEN_DAY_AVAILABILITY_INCOMPLETE",
            )
            expected_closes = {
                (symbol, interval, end)
                for symbol in plan.required_symbols
                for interval in ("1D", "4H")
                for end in range(
                    plan.availability_start_ms + INTERVALS[interval], plan.end_ms + 1, INTERVALS[interval]
                )
            }
            available = {
                (r.bar.candle.symbol, r.bar.candle.interval, r.bar.end_ms)
                for r in records
                if r.bar.available_ms - r.bar.end_ms <= 300000
            }
            require(
                len(expected_closes) == 147
                and len(expected_closes & available) / len(expected_closes) >= 0.995,
                "AVAILABILITY_BELOW_PREDECLARED_995",
            )
            require(
                self.product_roots.get("accepted_product_schema_sha256") == SCHEMA_HASH,
                "CONTROLLER_NATIVE_SCHEMA_NOT_ACCEPTED",
            )
            require(
                any(h.grant.valid_start_ms <= asof_ms < h.grant.valid_end_ms for h in hosts.values()),
                "HOST_CLOCK_UNQUALIFIED",
            )
            advance(STAGES[5])
            advance(STAGES[6])
            return {
                "status": "ELIGIBLE",
                "stages": stages,
                "proof": proof,
                "cohort": cohort,
                "evidence_class": evidence_class,
                "source_qualified": not self.qa,
                "shadow_eligible": not self.qa,
                "records": records,
                "reason": None,
            }
        except (ValueError, KeyError, StopIteration, TypeError, OSError) as exc:
            reason = str(exc) or type(exc).__name__
            self.ledger.append(
                "BLOCKED",
                {
                    "cohort": cohort,
                    "asof_ms": asof_ms,
                    "stage": stages[-1] if stages else None,
                    "reason": reason,
                    "evidence_class": evidence_class,
                },
            )
            return {
                "status": "SOURCE_BLOCKED",
                "stages": stages,
                "proof": proof,
                "cohort": cohort,
                "evidence_class": evidence_class,
                "source_qualified": False,
                "shadow_eligible": False,
                "records": [],
                "reason": reason,
            }
