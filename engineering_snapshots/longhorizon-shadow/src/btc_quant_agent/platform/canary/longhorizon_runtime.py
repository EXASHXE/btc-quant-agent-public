"""Bounded lifecycle, source accounting and local reports on the existing L4/L23 engine."""

from __future__ import annotations

from collections import Counter
from decimal import InvalidOperation
import html
import json
import os
from pathlib import Path
import shutil
import tempfile

from ..core import primitive, dec, fingerprint
from ..selection.selector import PLAYS
from ..selection.sources import MINUTE, STRUCTURE
from . import clock_domain as domain
from .longhorizon import PROFILE, SYMBOLS, IDS
from .public_runtime import PublicEngine, clocked
from .storage import StorageBlocked

ENTRY_VETOES = ("RANK_COVERAGE_BELOW_TEN_WATCH_ONLY", "CURRENT_CAPITAL_AND_MARGIN_NOT_VERIFIED",
                "NATIVE_FUNDING_EVIDENCE_INCOMPLETE")


def allocation(path):
    stat = path.stat()
    return stat.st_blocks * 512 if hasattr(stat, "st_blocks") else stat.st_size


class LongEngine(PublicEngine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.health = {}
        self.funnel: Counter[str] = Counter()
        self.vetoes: Counter[str] = Counter()
        self.transitions: Counter[str] = Counter()
        self.last_maintenance = -(10**18)
        self.last_repair = -(10**18)
        self.retention: dict = {"expired_chunks": 0, "raw_to_normalized_full_session_replay": "NO_RECEIPTS"}
        self.repair_ingest = False
        self.bar_late: Counter[tuple[str, int]] = Counter()
        self.field_context = {}
        self.quote_context = {}
        self.storage_fault = None
        self.bar_history_cap = 3000
        self.storage_projection = {}
        self.quality_slots: Counter[str] = Counter()
        if fault := self.store.get_value("longhorizon_clock_fault"):
            self.clock_fault = fault["reason"]
            self.advisory_enabled = False

    def ingest(self, wire, **kwargs):
        # Clock V2 is mandatory even for simulated transport used by this profile.
        if wire.clock_samples is None:
            raise ValueError("LONGHORIZON_CLOCK_DOMAIN_V2_REQUIRED")
        return super().ingest(wire, **kwargs)

    def invalidate_clock(self, reason, sample):
        if self.clock_fault:
            return
        if domain.sample_reason(sample):
            super().invalidate_clock(reason, sample)
        else:
            self.clock_fault = reason
            self.quote.clear()
            self.estimate = None
            self.advisory_enabled = False
            self.store.set_value("longhorizon_clock_fault", {"reason": reason, "sample": sample})
            for symbol in SYMBOLS:
                self.store.revoke_regime(symbol, self.clock.wall(), 0)

    @clocked
    def apply(self, record, result, commit):
        wire = record["wire"]
        response_start = len(self.response)
        self.repair_ingest = wire["endpoint_id"] == "binance_usdm_klines_rest"
        try:
            super().apply(record, result, commit)
        finally:
            self.repair_ingest = False
        symbols = SYMBOLS if wire["symbol"] == "*" else (wire["symbol"],)
        for symbol in symbols:
            key = (symbol, wire["endpoint_id"])
            row = self.health.setdefault(key, {"received": 0, "admitted": 0, "failed": 0})
            row["received"] += 1
            row["last_receive_mono_ms"] = wire["receive_mono"]
            row["last_receive_utc_ms"] = wire["receive_wall"]
            row["last_status"] = result["status"]
            row["last_reasons"] = result["reasons"]
            if result["status"] == "INADMISSIBLE":
                row["failed"] += 1
            else:
                row["admitted"] += int(bool(result.get("quote") or result.get("bars")))
            context = result.get("context_values")
            current_quote = self.quote.get(symbol)
            if (result.get("quote") and current_quote and current_quote.provenance.source_id
                == result["quote"]["provenance"]["source_id"]):
                self.quote_context[symbol] = {"native_T": result.get("native_transaction_ms"),
                    "wire_id": result["wire_id"], "commit_utc_ms": commit,
                    "source_id": current_quote.provenance.source_id}
                for response in self.response[response_start:]:
                    if response.get("quote_id") == fingerprint(current_quote):
                        response["native_quote_context"] = self.quote_context[symbol]
            if context is not None:
                self.field_context[key] = {"values": context, "clock": result.get("clock", {}),
                                           "wire_id": result["wire_id"], "receipt_mono_ms": wire["receive_mono"]}
            if "cadence_hours" in result:
                self.field_context[key] = {"cadence_hours": result["cadence_hours"].get(symbol),
                                           "wire_id": result["wire_id"], "receipt_mono_ms": wire["receive_mono"]}

    def apply_bar(self, rawbar, now):
        # Repaired history restores coverage for future scans. Past monitor/risk
        # decisions are immutable and are never run again on late observations.
        advisory = self.advisory_enabled
        if self.repair_ingest:
            self.advisory_enabled = False
            self.bar_late[(rawbar["spec"]["symbol"], rawbar["interval_ms"])] += 1
        try:
            super().apply_bar(rawbar, now)
        finally:
            self.advisory_enabled = advisory and self.clock_fault is None
        # A full 48h session has 2880 1m bars. Preserve full-window integrity counts
        # separately in the durable journal; the RAM history remains bounded.

    def discover(self, now):
        structures = [self.bars.get((s, STRUCTURE), {}) for s in SYMBOLS]
        if not all(structures):
            return
        end = min(max(v) + STRUCTURE for v in structures)
        if self.last_cutoff is not None and end <= self.last_cutoff:
            return
        before = set(self.episodes)
        super().discover(now)
        for key in self.episodes.keys() - before:
            self.funnel["WATCH"] += 1
            self.funnel["playbook:" + self.episodes[key]["anchors"]["strategy"]] += 1

    def monitor(self, bar, now, *, include_risk=True):
        before = {key: e["last_status"] for key, e in self.episodes.items()}
        super().monitor(bar, now, include_risk=include_risk)
        for key, e in self.episodes.items():
            state = self.store.episode(key)["state"]
            if e["last_status"] != before.get(key):
                self.transitions[before.get(key, "UNKNOWN") + "->" + e["last_status"]] += 1
                self.funnel[e["last_status"]] += 1
            self.vetoes.update(state.get("reasons", []))

    def revalidate(self, symbol, now):
        before = len(self.response)
        super().revalidate(symbol, now)
        for item in self.response[before:]:
            e = self.episodes[item["episode"]]
            a = e["anchors"]
            reasons = []
            if item["state"] == "NO_VALID_QUOTE/UNKNOWN":
                item["conditional_market_survival"] = "UNKNOWN"
            else:
                q = self.quote.get(symbol)
                if q is None:
                    raise ValueError("POST_ACK_QUOTE_DISAPPEARED")
                sign = 1 if a["side"] == "LONG" else -1
                entry = q.ask if sign == 1 else q.bid
                if e["last_status"] in ("CANCELLED", "EXPIRED") or domain.expired(a, now):
                    reasons.append("SETUP_INVALID_OR_EXPIRED")
                if dec(sign) * (entry - dec(a["chase_cap"])) > 0:
                    reasons.append("CHASE_CAP_EXCEEDED")
                if a["entry_mode"] == "market" and not dec(a["zone_low"]) <= entry <= dec(a["zone_high"]):
                    reasons.append("ENTRY_REGION_LOST")
                if (q.ask - q.bid) / q.bid * 10000 > self.policy.max_spread_bps:
                    reasons.append("SPREAD_LIMIT_EXCEEDED")
                if e["last_status"] not in ("ARMED", "ENTRY_ELIGIBLE"):
                    reasons.append("MECHANISM_CONFIRMATION_PENDING")
                item["conditional_market_survival"] = "FAILED" if reasons else "SURVIVED_CONDITIONALLY"
                item["observed_revalidation_price"] = str(entry)
                item["quote_chronology"] = "POST_MODELED_ACK_NATIVE_AND_RECEIPT_VERIFIED"
                item["quote_provenance"] = primitive(q.provenance)
                quote_context = self.quote_context.get(symbol)
                item["native_quote_context"] = (quote_context if quote_context and
                    quote_context["source_id"] == q.provenance.source_id else None)
            item["conditional_vetoes"] = reasons
            item["entry_eligible"] = False
            item["account_risk_status"] = "MISSING"
            item["vetoes"] = sorted(set(item["vetoes"]) | set(ENTRY_VETOES))

    @clocked
    def maintenance(self):
        now = self.clock.mono()
        if now - self.last_maintenance < 60000:
            return
        self.flush()
        self.last_maintenance = now
        if self.clock_fault:
            return
        if self.estimate is None or not isinstance(self.estimate, dict):
            self.invalidate_clock("CLOCK_ESTIMATE_MISSING", domain.capture(self.clock)[2])
            raise ValueError("CLOCK_ESTIMATE_MISSING")
        if (now - self.estimate["available"]["mono_before_ms"] > domain.MAX_PROBE_AGE_MS
            or self.estimate["uncertainty_ms"] > domain.MAX_UNCERTAINTY_MS):
            self.invalidate_clock("CLOCK_REFRESH_UNQUALIFIED", domain.capture(self.clock)[2])
            raise ValueError("CLOCK_REFRESH_UNQUALIFIED")
        # Both receipt and current UTC samples may carry up to 1000ms receiver
        # uncertainty. Retain an extra margin for both plus the 50ms epoch bound;
        # a small allowed wall movement must never shorten the minimum retention.
        retention_now = self.clock.wall() - 2 * max(1000, getattr(self.clock, "utc_uncertainty_ms", 1000)) - 50
        expired = self.journal.expire(retention_now)
        self.retention["expired_chunks"] += len(expired["expired"])
        self.retention["raw_to_normalized_full_session_replay"] = (
            "INCOMPLETE_EARLY_RAW_EXPIRED" if self.retention["expired_chunks"] else "RETAINED_PENDING_FINAL_AUDIT")
        used = self.journal.used()
        free = shutil.disk_usage(self.journal.root).free
        with self.store._connect() as db:
            cumulative = dict(db.execute("SELECT kind,SUM(allocated) FROM public_chunks GROUP BY kind"))
        elapsed = max(1, (self.clock.wall() - self.scope.start_ms) / 1000)
        self.storage_projection = {
            "observed_raw_allocated_bytes_per_second": cumulative.get("raw", 0) / elapsed,
            "projected_raw_36h_bytes": int(cumulative.get("raw", 0) / elapsed * 36 * 3600),
            "projected_auxiliary_48h_bytes": int(used["auxiliary"] / elapsed * 48 * 3600),
            "semantics": "Measured average since grant start; burst risk remains; no early retention eviction"}
        # Stop with enough room for final fault/report sealing; no early deletion.
        if (used["raw"] + 2 * self.journal.chunk_cap > self.journal.raw_cap
            or used["auxiliary"] + 4 * self.journal.chunk_cap > self.journal.aux_cap
            or free < self.journal.reserve + 4 * self.journal.chunk_cap):
            self.storage_fault = "STORAGE_HEADROOM_STOP"
            self.store.set_value("longhorizon_storage_fault", {"reason": self.storage_fault, "used": used})
            raise StorageBlocked(self.storage_fault)
        if elapsed >= 300 and (self.storage_projection["projected_raw_36h_bytes"] > self.journal.raw_cap
            or self.storage_projection["projected_auxiliary_48h_bytes"] > self.journal.aux_cap):
            self.storage_fault = "STORAGE_RETENTION_PROJECTION_BLOCKED"
            self.store.set_value("longhorizon_storage_fault", {"reason": self.storage_fault,
                                                               "projection": self.storage_projection})
            raise StorageBlocked(self.storage_fault)
        self.queue_gaps()
        snapshot = self.report()
        for symbol, row in snapshot["per_symbol"].items():
            self.quality_slots[symbol + ":" + row["quote"]["status"]] += 1
        self.store.set_value("longhorizon_quality_slots", dict(self.quality_slots))
        write_snapshot(self.journal.root, snapshot, producer=self)

    def queue_gaps(self):
        if not isinstance(self.estimate, dict) or self.clock_fault:
            return
        cutoff = min(self.scope.end_ms, self.clock.mono() + self.estimate["native_minus_monotonic_low_ms"] - 2000)
        pending = set(self.repairs)
        for symbol in SYMBOLS:
            for interval in (MINUTE, STRUCTURE):
                first = ((self.scope.start_ms + interval - 1) // interval) * interval
                history = self.bars.get((symbol, interval), {})
                # Only the last 99 bars may be repaired per scan. Older missing
                # ranges remain visible; no unbounded catch-up or historical read.
                end = cutoff // interval * interval
                first = max(first, end - 99 * interval)
                missing = [t for t in range(first, end, interval) if t not in history]
                if missing:
                    lo = missing[0]
                    hi = lo + interval
                    while hi in missing:
                        hi += interval
                    item = (symbol, interval, lo, hi - 1)
                    if item not in pending and len(self.repairs) < 32:
                        self.repairs.append(item)
                        pending.add(item)

    def repair_ready(self):
        if self.clock.mono() - self.last_repair < 10000:
            return False
        self.last_repair = self.clock.mono()
        return True

    def field_status(self, symbol, endpoint, field, ttl, unit_known=True, clock_known=True):
        row = self.health.get((symbol, endpoint))
        if not row:
            return {"status": "MISSING", "value": None, "reason": "NO_NATIVE_OBSERVATION"}
        context = self.field_context.get((symbol, endpoint), {})
        age = self.clock.mono() - context.get("receipt_mono_ms", row["last_receive_mono_ms"])
        values = context.get("values", {})
        value = values.get(field) if isinstance(values, dict) else None
        if field == "fundingIntervalHours":
            value = context.get("cadence_hours")
        numeric = True
        if value is not None:
            try:
                number = dec(value)
                numeric = number.is_finite() and (field == "lastFundingRate" or number >= 0)
            except (ValueError, TypeError, InvalidOperation):
                numeric = False
        clock_ok = context.get("clock", {}).get("source_clock_qualified", False)
        status = ("MISSING" if value is None else "STALE" if age > ttl else "UNKNOWN"
                  if not numeric or not unit_known or not clock_known or not clock_ok
                  or row["last_status"] == "INADMISSIBLE" else "CONTEXT_ONLY")
        return {"status": status, "value": value, "receipt_age_ms": age,
                "native_clock_qualified": context.get("clock", {}).get("source_clock_qualified", False),
                "unit_qualified": unit_known, "action_qualified": False,
                "reason": "NATIVE_UNITS_OR_TIMESTAMP_UNQUALIFIED" if not unit_known or not clock_known
                else "READONLY_CONTEXT_NO_ACCOUNT_RISK_AUTHORITY", "wire_id": context.get("wire_id")}

    @clocked
    def report(self):
        base = super().report()
        per_symbol = {}
        for symbol in SYMBOLS:
            q = self.quote.get(symbol)
            reason = None
            if q and self.metadata:
                meta = self.metadata
                from .public_data import instrument
                from .public_io import Wire
                spec = instrument(Wire(**meta["wire"]).payload, symbol, Wire(**meta["wire"])).spec
                reason = q.reason(spec, self.clock.wall(), 5000)
            bars = self.bars.get((symbol, STRUCTURE), {})
            latest = bars[max(bars)] if bars else None
            values = latest.values(latest.end + 1000)[0] if latest else None
            intervals = {}
            for interval in (MINUTE, STRUCTURE):
                history = self.bars.get((symbol, interval), {})
                first = ((self.scope.start_ms + interval - 1) // interval) * interval
                lower = (self.clock.mono() + self.estimate["native_minus_monotonic_low_ms"]
                         if isinstance(self.estimate, dict) else self.scope.start_ms)
                end = min(self.scope.end_ms, lower - 2000) // interval * interval
                missing = [t for t in range(first, end, interval) if t not in history]
                intervals[str(interval)] = {"expected_completed": max(0, (end - first) // interval),
                    "retained_history_count": len(history), "missing_count": len(missing),
                    "first_missing_starts_ms": missing[:20], "missing_list_truncated": len(missing) > 20,
                    "late_repaired_observations": self.bar_late[(symbol, interval)],
                    "trailing_contiguous": len(self.contiguous(symbol, interval))}
            per_symbol[symbol] = {
                "quote": {"status": "MISSING" if q is None else "STALE" if reason else "QUALIFIED_PRICE_ONLY",
                    "reason": reason, "bid": str(q.bid) if q else None, "ask": str(q.ask) if q else None,
                    "native_E": q.provenance.exchange_event_ts if q else None,
                    "native_T": self.quote_context.get(symbol, {}).get("native_T"),
                    "local_receipt_utc_ms": q.provenance.received_ts if q else None,
                    "available_utc_ms": q.provenance.available_ts if q else None,
                    "provenance": primitive(q.provenance) if q else None,
                    "native_sizes": self.quote_native_sizes.get(symbol),
                    "receipt": self.quote_context.get(symbol)},
                "bars": intervals,
                "structure": {"status": "OBSERVED" if latest else "MISSING", "end_ms": latest.end if latest else None,
                              "values": values, "regime": self.store.regime(symbol)["state"],
                              "field_status": {f: "OBSERVED" if values and f in values else "MISSING"
                                  for f in ("open", "high", "low", "close", "volume", "quote_volume")}},
                "fields": {name: self.field_status(symbol, endpoint, field, ttl, units, clock)
                    for name, endpoint, field, ttl, units, clock in (
                        ("open_interest", "binance_usdm_oi", "openInterest", 120000, False, True),
                        ("mark_price", "binance_usdm_premium", "markPrice", 120000, True, False),
                        ("index_price", "binance_usdm_premium", "indexPrice", 120000, True, False),
                        ("funding_rate", "binance_usdm_premium", "lastFundingRate", 300000, True, False),
                        ("next_funding", "binance_usdm_premium", "nextFundingTime", 300000, True, False),
                        ("funding_cadence", "binance_usdm_funding_info", "fundingIntervalHours", 300000, True, False),
                        ("turnover", "binance_usdm_turnover", "quoteVolume", 300000, True, True))}}
        outcomes = {}
        for minute in (1, 3, 5):
            rows = [r for r in self.response if r["response_minutes"] == minute]
            known = [r for r in rows if r.get("conditional_market_survival") in ("SURVIVED_CONDITIONALLY", "FAILED")]
            outcomes[str(minute)] = {"evaluated": len(rows), **dict(Counter(
                r.get("conditional_market_survival", "UNKNOWN") for r in rows)),
                "known_evaluations": len(known),
                "pending_or_censored": max(0, len(self.episodes) - len(rows)),
                "conditional_survival_rate": (sum(r.get("conditional_market_survival") == "SURVIVED_CONDITIONALLY"
                                                 for r in known) / len(known)) if known else None}
        used = self.journal.used()
        span = max(0, self.last_received - self.first_received) if self.first_received is not None else 0
        value = {**base, "profile": PROFILE, "per_symbol": per_symbol,
                "source_lifecycle": {s + ":" + e: self.health.get((s, e), {"last_status": "MISSING",
                    "received": 0, "admitted": 0, "failed": 0}) for s in SYMBOLS for e in IDS},
                "coverage": {"actual_receive_span_ms": span,
                    "authorized_duration_ms": self.scope.end_ms - self.scope.start_ms,
                    "quote_quality_slots_60s": dict(self.quality_slots),
                    "opportunities_per_observed_hour": len(self.episodes) / (span / 3600000)
                        if span and self.scans else None,
                    "prevalence_support": "L23_SCANS_AVAILABLE" if self.scans else "UNKNOWN_NO_L23_SCAN_SUPPORT",
                    "span_is_continuous_qualified_coverage": False},
                "opportunity_funnel": {"event_counts": dict(self.funnel), "transitions": dict(self.transitions),
                    "veto_observations": dict(self.vetoes), "episodes": len(self.episodes),
                    "enabled_playbooks": list(PLAYS), "selector_policy_sha256": self.policy.hash,
                    "denominator": "Causally discovered L23 episodes; no opportunity rate before observation",
                    "entry_eligible": 0}, "modeled_response_survival": outcomes,
                "risk": {"account_inputs": "MISSING", "entry_eligible_blocked": True,
                         "required": ["current equity", "available margin", "existing positions and exposure",
                                      "venue account margin tiers", "qualified funding schedule"],
                         "vetoes": list(ENTRY_VETOES), "actual_positions_inferred": False},
                "storage": {"used": used, "raw_cap": self.journal.raw_cap, "auxiliary_cap": self.journal.aux_cap,
                    "free_bytes": shutil.disk_usage(self.journal.root).free, "fault": self.storage_fault,
                    "raw_retention_hours": 36, "normalized_retention_hours": 168,
                    "projection": self.storage_projection, **self.retention},
                "source_qualified": False, "shadow_advisory_qualified": False,
                "qualification_status": "OBSERVATION_ONLY_CONTROLLER_REVIEW_REQUIRED",
                "economic_claims": {"fills": False, "executable_net_pnl": False, "alpha": False,
                                    "prospective_strategy_profitability": False}}
        from .longhorizon_acceptance import tier_outcomes, capacity_plan

        value["three_tier_acceptance"] = tier_outcomes(value)
        value["storage"]["capacity_plan"] = capacity_plan()
        from .longhorizon_view import SCHEMA, producer_identity, core_digest

        context = domain.current_decision()
        rankings = {c["anchors"]["id"]: c.get("ranking") for c in
                    (self.last_scan or {}).get("candidates", [])}
        value["clock_readiness"] = {"independent_probes": len(self.native_probes),
            "probe_age_ms": context[0]["mono_after_ms"] - self.estimate["available"]["mono_before_ms"]
                if context and isinstance(self.estimate, dict) else None,
            "uncertainty_ms": self.estimate.get("uncertainty_ms") if isinstance(self.estimate, dict) else None,
            "epoch_fault": self.clock_fault}
        value.update(snapshot_schema_id=SCHEMA, producer_identity=producer_identity(),
            as_of_utc_ms=context[0]["wall_ms"] if context else self.clock.wall(),
            advisory_episodes=[{"episode_id": key, "status": e["last_status"],
                "known_at_utc_ms": e["known_at"], "anchors": primitive(e["anchors"]),
                "ranking": rankings.get(key),
                "state": (self.store.episode(key) or {}).get("state")}
                for key, e in self.episodes.items()])
        value["user_reported_positions"] = {}
        for id in {a["position_id"] for a in self.management}:
            position = self.store.position(id)
            value["user_reported_positions"][id] = {"source": position.source, "version": position.version,
                "status": position.status, "updated_ts": position.updated_ts}
        self.last_view_core_digest = core_digest(value)
        return value


def _publish(root, name, text, *, immutable=False):
    root = Path(root)
    target = root / name
    if any(p.is_symlink() for p in (root, *root.parents)) or target.is_symlink():
        raise ValueError("DASHBOARD_SYMLINK_FORBIDDEN")
    if immutable and target.exists():
        raise ValueError("IMMUTABLE_DASHBOARD_ALREADY_EXISTS")
    fd, temporary = tempfile.mkstemp(dir=root, prefix="." + name + ".", suffix=".part")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if immutable:
            os.link(temporary, target)
        else:
            os.replace(temporary, target)
        if hasattr(os, "O_DIRECTORY"):
            directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target


def write_snapshot(root, value, *, producer=None):
    root = Path(root)
    from .longhorizon_view import adapt

    adapt(value, producer=producer)  # Validate before replacing either public snapshot.
    text = json.dumps(primitive(value), sort_keys=True, indent=2, allow_nan=False) + "\n"
    _publish(root, "latest.json", text)
    save_dashboard(root, {"model": value, "exposure": value["exposure"]}, live=True, producer=producer)


def save_dashboard(root, result, *, live=False, producer=None, historical_root=None):
    from .longhorizon_view import adapt

    model = result["model"]
    view = adapt(model, producer=producer)
    if result["exposure"] != model["exposure"]:
        raise ValueError("DASHBOARD_EXPOSURE_MISMATCH")
    rows = []
    for row in view["symbols"]:
        b = row["bars"]["value"] or {}
        q = row["quote"]["value"] or {}
        rows.append("<tr>" + "".join("<td>" + html.escape("UNKNOWN" if v is None else str(v)) + "</td>" for v in (
            row["symbol"], row["quote"]["state"], q.get("bid"), q.get("ask"),
            (b.get(str(MINUTE)) or {}).get("missing_count"),
            (b.get(str(STRUCTURE)) or {}).get("trailing_contiguous"),
            row["regime"]["value"])) + "</tr>")
    text = ("<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>L4 Source + Shadow</title><style>body{font:16px system-ui;background:#101827;color:#e8edf4;"
            "max-width:1100px;margin:3rem auto;padding:1rem}table{border-collapse:collapse;width:100%}"
            "td,th{text-align:left;padding:.7rem;border-bottom:1px solid #35405a}pre{white-space:pre-wrap;"
            "overflow-wrap:anywhere}details{margin:1.5rem 0}strong{color:#f6c66e}</style>"
            "<h1>L4 Source + Shadow</h1><p><strong>" + html.escape(result["exposure"]) +
            " · LOCAL OBSERVATION ONLY · ENTRY BLOCKED</strong></p>"
            "<p>Read-only snapshot. Reload this local file for the latest report. No external delivery or fills.</p>"
            "<table><tr><th>Symbol</th><th>Quote</th><th>Bid</th><th>Ask</th><th>Missing 1m</th>"
            "<th>Contiguous 5m</th><th>Regime</th></tr>" + "".join(rows) + "</table>")
    def table(headers, data):
        def esc(value):
            return html.escape("UNKNOWN" if value is None else str(value))
        return ("<div style='overflow:auto'><table><tr>" + "".join("<th>" + esc(h) + "</th>" for h in headers)
                + "</tr>" + "".join("<tr>" + "".join("<td>" + esc(v) + "</td>" for v in row) + "</tr>"
                                     for row in data) + "</table></div>")

    text += "<h2>Qualification / field evidence</h2>" + table(
        ["Independent tier", "State", "Authority", "As of UTC ms"],
        [(name, f["state"], f["authority"], f["as_of_utc_ms"]) for name, f in view["qualifications"].items()])
    if historical_root is not None:
        from .longhorizon_view import historical_source

        history = historical_source(historical_root)
        text += ("<h2>Historical native Session03: PARTIAL / OBSERVED</h2>"
                 "<p>Separate sealed evidence, not the synthetic rows or a current feed. "
                 "SOURCE_QUALIFIED=false; SHADOW_ADVISORY_QUALIFIED=false.</p><pre>" + html.escape(
                     json.dumps(history, indent=2, allow_nan=False)) + "</pre>")
    text += "<p>Snapshot schema " + html.escape(view["view_schema"]) + "; input SHA256 " + view["input_sha256"] + "</p>"
    text += "<h2>Candidate / frozen structure / veto</h2>" + table(
        ["Symbol", "Side", "Strategy", "Regime", "Rank (not probability)", "State", "Entry zone", "Original stop", "Chase cap", "Expiry", "Evidence tier"],
        [(f["value"]["anchors"]["symbol"], f["value"]["anchors"]["side"], f["value"]["anchors"].get("strategy"),
          f["value"]["anchors"].get("regime"), f["value"].get("ranking"),
          f["state"], str([f["value"]["anchors"].get("zone_low"), f["value"]["anchors"].get("zone_high")]),
          f["value"]["anchors"].get("stop"), f["value"]["anchors"].get("chase_cap"),
          f["value"]["anchors"].get("expiry"), str(f["value"]["anchors"].get("evidence_tier")) + " / " + f["evidence_kind"])
         for f in view["episodes"]])
    if not view["episodes"]:
        text += "<p>No episode records supplied. NO_SETUP requires an evaluated scan; otherwise UNKNOWN / NOT_EVALUATED.</p>"
    text += "<h2>Modeled 1/3/5-minute responses</h2>" + table(
        ["Episode", "Minutes", "Outcome", "Post-ack receive UTC ms", "Evidence", "Actual ack / fill"],
        [(f["value"]["episode"], f["value"]["response_minutes"], f["state"],
          f["value"].get("subsequently_received_quote_ts"), f["evidence_kind"], "UNKNOWN / UNKNOWN")
         for f in view["responses"]])
    text += "<p>Missing horizons are pending/censored, not losses or fills. ACCOUNT_SIDE = UNKNOWN / ACCOUNT_VETO.</p>"
    text += "<h2>User-reported position risk</h2><pre>" + html.escape(
        json.dumps(view["position_risk"], indent=2, allow_nan=False)) + "</pre>"
    text += "<details open><summary>Timestamp authority, warmup, quota and source evidence</summary><pre>" + html.escape(
        json.dumps(view, indent=2, allow_nan=False)) + "</pre></details>"
    for label, key in (("Fields and completed structure", "per_symbol"), ("Opportunity funnel and vetoes", "opportunity_funnel"),
                       ("Separate source, market shadow and account outcomes", "three_tier_acceptance"),
                       ("Modeled 1/3/5-minute response survival", "modeled_response_survival"),
                       ("Risk inputs", "risk"), ("Retention and integrity condition", "storage"),
                       ("Clock fault", "clock_epoch_failure")):
        text += "<details open><summary>" + label + "</summary><pre>" + html.escape(
            json.dumps(primitive(model.get(key)), indent=2, allow_nan=False)) + "</pre></details>"
    text += "<p>Three symbols cannot meet the ten-symbol ranking contract. Source and shadow qualification require Controller review.</p></html>"
    name = "dashboard.html" if live else "dashboard_final.html"
    return _publish(root, name, text, immutable=not live)
