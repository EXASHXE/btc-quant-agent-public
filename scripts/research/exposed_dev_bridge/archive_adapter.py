"""PASS ZIP streams and bounded rolling source-to-P1 materialization.

Default reads are feature/QC only. Label-capable reads require DualGate before
opening a CSV. No extraction, dataframes, network clients or execution APIs.
"""

from __future__ import annotations

import hashlib
import os
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from scripts.research.cross_venue import normalized_sources as n
from scripts.research.strategy_eval import DAY, HORIZONS, clocked_dataset as p1
from scripts.research.strategy_eval import pipeline as evaluator

from .authorization import DualGate, PhaseOnePermit, authorize_dual_gate, authorize_phase_one
from .inspection import _raw_signature, p1_bars
from .outcome_adapter import H39_CUTOFF_US, build_panel_row


@dataclass(frozen=True, slots=True)
class NativeRecord:
    t: int
    value: Any
    provenance: dict[str, Any]


def native_records(source: n.Source, budget: n.Budget, *, purpose: str = "FEATURE_QC",
                   permit: DualGate | PhaseOnePermit | None = None) -> Iterator[NativeRecord]:
    """Reuse secure P2 ZIP/CRC/SHA readers and P1 numeric/clock validation."""
    n.require(purpose in ("FEATURE_QC", "OUTCOME"), "SOURCE_READ_PURPOSE_INVALID")
    r, venue = source.record, source.snapshot.venue
    n.require(r.get("verdict") == "PASS" and source.qc is not None
              and source.qc.get("verdict") == "PASS", "SOURCE_NOT_SELECTED_PASS")
    _, market, interval = n.expected_identity(venue, r["family"], r["symbol"])
    n.require(r.get("market") == market and r.get("interval") == interval,
              "SOURCE_FAMILY_IDENTITY_MISMATCH")
    path = source.snapshot.root / r["local_path"]
    if purpose == "OUTCOME":
        n.require(isinstance(permit, (DualGate, PhaseOnePermit)), "DUAL_AUTHORIZATION_REQUIRED")
        permit.verify()
        pins = [f for f in permit.scope["verified_files"] if f["path"] == str(path)]
        n.require(len(pins) == 1 and pins[0]["sha256"] == r["local_sha256"]
                  and all(pins[0][k] == r[k] for k in ("family", "market", "symbol")),
                  "SOURCE_OUTSIDE_OWNER_SCOPE")
        meta = [s for s in permit.scope["sources"] if s["root"] == str(source.snapshot.root)]
        n.require(len(meta) == 1 and meta[0]["sha256_before"] == source.snapshot.before,
                  "INPUT_CHANGED", document="source_metadata")
    source.snapshot.verify()
    source.selected = True
    is_p1_bar = venue == "binance" and r["family"] in ("klines", "spot_klines")
    if not is_p1_bar:
        n.require(budget.reserve(r), "SOURCE_SCAN_BUDGET_EXCEEDED")
    if is_p1_bar:
        iterator = p1_bars(source, budget)
    elif r["family"] in n.BAR_FAMILIES:
        iterator = n.source_bars(source, budget)
    elif r["family"] == "metrics":
        iterator = n.source_stocks(source, budget)
    else:
        iterator = n.source_funding(source, budget)
    try:
        for value in iterator:
            if isinstance(value, p1.Bar):
                factor = 1 if market == "spot" else 1000
                provenance = source.provenance(value.open_us // factor,
                    "us" if factor == 1 else "ms", value.open_us, value.close_us // factor)
                t = value.t
            else:
                provenance = dict(value.provenance)
                t = (value.open_us if isinstance(value, n.Bar) else value.t_us) // n.US
            provenance.update(source_path=str(path), receiver_first_known_utc=None,
                              read_purpose=purpose)
            yield NativeRecord(t, value, provenance)
        if r["family"] in n.BAR_FAMILIES:
            n.require(source.scan["missing_minutes"] == r["gaps"], "SOURCE_GAP_COUNT_MISMATCH")
    finally:
        iterator.close()
        source.snapshot.verify()


def scoped_sources(permit: DualGate | PhaseOnePermit) -> list[n.Source]:
    """Dispatch final metadata only; admit no unlisted file for later streams."""
    result = []
    for receipt in permit.scope["sources"]:
        snap = n.Snapshot.capture(Path(receipt["root"]), receipt["venue"], receipt["quarter"])
        n.require(snap.before == receipt["sha256_before"], "INPUT_CHANGED", document="source_metadata")
        pins = {f["path"]: f for f in permit.scope["verified_files"]}
        for source in n.expansion_sources(snap, n.Budget(expanded_cap=0)):
            pin = pins.get(str(snap.root / source.record["local_path"]))
            if pin is not None:
                n.require(pin["sha256"] == source.record["local_sha256"], "INPUT_CHANGED")
                result.append(source)
        snap.verify()
    n.require(len(result) == len(permit.scope["verified_files"]), "SOURCE_PIN_SET_CHANGED")
    return result


class RollingStream:
    """At most a 24h lookback, 24h exit buffer, and one stream head."""
    def __init__(self, iterator: Iterator[NativeRecord]):
        self.iterator = iterator
        self.head = next(iterator, None)
        self.values: dict[int, NativeRecord] = {}
        self.previous: int | None = None
        self.max_retained = 0

    def window(self, left: int, right: int) -> dict[int, NativeRecord]:
        while self.head is not None and self.head.t < right:
            row = self.head
            n.require(self.previous is None or row.t > self.previous, "NATIVE_STREAM_ORDER_INVALID")
            self.previous = row.t
            if row.t >= left:
                self.values[row.t] = row
            self.head = next(self.iterator, None)
        self.values = {t: r for t, r in self.values.items() if t >= left}
        n.require(len(self.values) <= 3000, "ROLLING_WINDOW_LIMIT")
        self.max_retained = max(self.max_retained, len(self.values))
        return self.values

    def finish(self) -> None:
        # Exhaust current and remaining selected archives for final QC/CRC.
        for _ in self.iterator:
            pass

    def close(self) -> None:
        self.iterator.close()


CHANNELS = {
    "perp": ("binance", "klines", "BTCUSDT"),
    "spot": ("binance", "spot_klines", "BTCUSDT"),
    "mark": ("binance", "markPriceKlines", "BTCUSDT"),
    "stock": ("binance", "metrics", "BTCUSDT"),
    "funding": ("binance", "fundingRate", "BTCUSDT"),
    "okx_swap": ("okx", "candlesticks", "BTC-USDT-SWAP"),
    "okx_spot": ("okx", "spot_candlesticks", "BTC-USDT"),
    "okx_funding": ("okx", "funding_rates", "ALL_SWAPS"),
}


def _channel(sources: list[n.Source], channel: str, budget: n.Budget,
             permit: DualGate | PhaseOnePermit, ledger: dict[str, Any]) -> Iterator[NativeRecord]:
    venue, family, symbol = CHANNELS[channel]
    selected = [s for s in sources if (s.snapshot.venue, s.record["family"], s.record["symbol"])
                == (venue, family, symbol) and n.file_window(s.record, venue)[0] < permit.end * n.US
                and n.file_window(s.record, venue)[1] > permit.start * n.US]
    for source in sorted(selected, key=lambda s: n.file_window(s.record, venue)):
        for row in native_records(source, budget, purpose="OUTCOME", permit=permit):
            ledger["outcome_source_records_exposed"] = ledger.get("outcome_source_records_exposed", 0) + 1
            if isinstance(row.value, n.Funding):
                if row.value.asset != "BTC":
                    continue
                if venue == "binance":
                    n.require(row.value.native_interval_hours == 8, "FUNDING_CALENDAR_UNSUPPORTED")
            yield row


def _funding_coverage(sources: list[n.Source], entry: int, exit_: int) -> tuple[int, int]:
    from scripts.research.cross_venue.pipeline import _merge_intervals
    intervals = _merge_intervals([list(n.file_window(s.record, "binance")) for s in sources
        if s.snapshot.venue == "binance" and s.record["family"] == "fundingRate"
        and s.record["symbol"] == "BTCUSDT"])
    return next(((a, b) for a, b in intervals if a <= entry * n.US < exit_ * n.US < b), (0, 0))


def panel_rows(permit: DualGate | PhaseOnePermit, ledger: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Outcome-capable only after a valid Owner pre-label gate; retain all origins."""
    n.require(isinstance(permit, (DualGate, PhaseOnePermit)), "DUAL_AUTHORIZATION_REQUIRED")
    permit.verify()
    sources = scoped_sources(permit)
    signatures = {source.snapshot.root / source.record["local_path"]:
                  _raw_signature(source.snapshot.root / source.record["local_path"])
                  for source in sources}
    budget = n.Budget(compressed_cap=256 * 1024**2, expanded_cap=768 * 1024**2,
                      row_cap=8_000_000)
    streams = {}
    with ExitStack() as stack:
        for name in CHANNELS:
            stream = RollingStream(_channel(sources, name, budget, permit, ledger))
            stack.callback(stream.close)
            streams[name] = stream
        for cutoff in range(permit.start, permit.end, 3600):
            left = max(permit.start, cutoff - DAY - 60)
            right = min(permit.end, cutoff + DAY + 180)
            windows = {k: s.window(left, right) for k, s in streams.items()}
            values = lambda k: {t: r.value for t, r in windows[k].items()}
            perp, spot = values("perp"), values("spot")
            mark = {t: r.value.opening for t, r in windows["mark"].items()}
            stocks = {t: p1.Stock(t, r.value.base_oi, r.value.top_position_ls,
                                 native_timestamp=r.provenance["native_sample"])
                      for t, r in windows["stock"].items()}
            funding = {t: r.value.rate for t, r in windows["funding"].items()}
            origin = cutoff + 60
            coverage = _funding_coverage(sources, origin + 60, origin + 60 + DAY)
            # Each horizon has its own coverage check, including shorter windows
            # at a partial source boundary.
            row = build_panel_row(origin, perp, spot, mark, stocks, funding, coverage,
                                  min(H39_CUTOFF_US, permit.end * n.US), known_mark_gaps=[])
            for h in HORIZONS:
                if row["outcome_reasons"][str(h)] == "UNRESOLVED_FUNDING_COVERAGE":
                    from .outcome_adapter import build_origin_outcome
                    covered = _funding_coverage(sources, origin + 60, origin + 60 + h * 3600)
                    outcome, reason = build_origin_outcome(origin, h, perp, mark, funding, covered,
                                                          min(H39_CUTOFF_US, permit.end * n.US), [])
                    row["outcome_reasons"][str(h)] = reason
                    if outcome is not None:
                        row["outcomes"][str(h)] = outcome.to_dict()
            if cutoff - DAY - 60 < permit.start:
                row.update(x=None, x_complete=False, x_reason="WARMUP_X_24H", native_feature_ready=False)
            row["source_references"] = {
                name: {str(t): {k: windows[name][t].provenance[k] for k in
                       ("source_id", "event_utc_us", "native_sample", "native_time_unit")}
                       for t in sorted(times) if t in windows[name]}
                for name, times in {
                    "perp": {origin + 60, *(origin + 60 + h * 3600 for h in HORIZONS
                        if str(h) in row["outcomes"])},
                    "stock": {row["z_t"], None if row["z_t"] is None else row["z_t"] - 14400},
                    "mark": {s["t_us"] // n.US for o in row["outcomes"].values() for s in o["settlements"]},
                    "funding": {s["t_us"] // n.US for o in row["outcomes"].values() for s in o["settlements"]},
                    "okx_funding": {t for t in windows["okx_funding"] if t < cutoff},
                }.items()}
            yield row
        for stream in streams.values():
            stream.finish()
        permit.verify()
        for source in sources:
            source.snapshot.verify()
        n.require(all(_raw_signature(p) == sig for p, sig in signatures.items()), "INPUT_CHANGED")
        ledger.update(source_signatures={str(p): list(sig) for p, sig in signatures.items()},
                      sources=[{**s.inventory(), "source_path": str(s.snapshot.root / s.record["local_path"])}
                               for s in sources], scan_budget=budget.receipt(),
                      max_retained_rows_by_channel={k: s.max_retained for k, s in streams.items()},
                      receiver_pit="PIT_UNKNOWN", future_okx_not_used_for_binance_labels=True,
                      outcome_source_rows_read=budget.rows_read)


def _verify_inputs(permit: DualGate | PhaseOnePermit, ledger: dict[str, Any]) -> None:
    permit.verify()
    n.require(all(list(_raw_signature(Path(p))) == sig for p, sig in ledger["source_signatures"].items()),
              "INPUT_CHANGED", document="raw_source")
    for source in permit.scope["sources"]:
        snap = n.Snapshot.capture(Path(source["root"]), source["venue"], source["quarter"])
        n.require(snap.before == source["sha256_before"], "INPUT_CHANGED", document="source_metadata")


def matched_population(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """P1's X and XZ arms see identical feature eligibility; keep all origins."""
    result = []
    for row in rows:
        native_x, common = p1.ready(row)
        result.append({**row, "native_x_complete": native_x, "x_complete": common,
                       "population_reason": "MATCHED_X_XZ" if common else "MATCHED_X_XZ_FEATURE_UNAVAILABLE"})
    return result


def materialize_authorized(scope_path: Path, allowlist_path: Path | None,
                           output: Path, *, evaluate: bool = False,
                           audit: dict[str, Any] | None = None) -> dict[str, Any]:
    """Future authorized entry point. This task exercises it on ZIP fixtures only."""
    from scripts.research.cross_venue.pipeline import prepare_output
    panel_path = output / "normalized_panel.json"
    with n.published_file(scope_path, 1024**2) as stream:
        import json
        contract = json.loads(stream.read(), object_pairs_hook=n._unique, parse_constant=n._bad_constant)
    derived = type(contract) is dict and type(contract.get("p1_binding")) is dict and \
        contract["p1_binding"].get("mode") == "DERIVED_P1_INTEGRITY_V1"
    permit = (authorize_phase_one(scope_path, panel_path) if derived else
              authorize_dual_gate(scope_path, allowlist_path, panel_path))
    active_allowlist = permit.allowlist_path
    ledger = {} if audit is None else audit
    ledger.update(dual_gate_authorized=True, scope_sha256=permit.scope_sha256,
                  authority_contract="OWNER_PHASE_ONE_DERIVED_P1_INTEGRITY" if derived else "LEGACY_PREPINNED_DUAL_GATE")
    prepare_output(output, [scope_path] + ([] if derived else [active_allowlist]) +
                   [Path(s["root"]) for s in permit.scope["sources"]])
    stage_name = ".normalized_panel.json.stage"
    try:
        with n.directory_fd(output) as directory:
            fd = os.open(stage_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            digest = hashlib.sha256()
            panel_bytes = 0
            with os.fdopen(fd, "wb") as stream:
                def write(block):
                    nonlocal panel_bytes
                    panel_bytes += len(block)
                    n.require(panel_bytes <= 32 * 1024**2, "P1_PANEL_BYTE_LIMIT")
                    digest.update(block)
                    stream.write(block)
                write(b'{"exposure":"EXPOSED_DEV","label":"HISTORICAL_OFFLINE / PIT_UNKNOWN","rows":[')
                for i, row in enumerate(panel_rows(permit, ledger)):
                    write((b"," if i else b"") + n.canonical_bytes(row).rstrip(b"\n"))
                write(b'],"schema":"strategy_eval.normalized.v1","start_utc_s":' + str(permit.start).encode() + b'}\n')
                stream.flush()
                os.fsync(stream.fileno())
            if not derived:
                n.require(digest.hexdigest() == permit.panel_sha256, "P1_EXPECTED_PANEL_HASH_MISMATCH")
        _verify_inputs(permit, ledger)
        n.require(hashlib.sha256((output / stage_name).read_bytes()).hexdigest() == digest.hexdigest(),
                  "STAGED_PANEL_HASH_MISMATCH")
        os.replace(output / stage_name, panel_path)
        if derived:
            # This document binds immutable output bytes to P1. It is not an
            # Owner decision and cannot authorize any additional source read.
            from .synthetic_contract import write_json
            write_json(output, active_allowlist.name, {
                "schema": "strategy_eval.exposed-dev.v1", "exposure": "EXPOSED_DEV",
                "binding_kind": "DERIVED_INTEGRITY_NOT_OWNER_AUTHORIZATION",
                "owner_scope_sha256": permit.scope_sha256,
                "panels": [{"path": str(panel_path), "sha256": digest.hexdigest(),
                            "start_utc_s": permit.start, "end_utc_s": permit.end}]})
        ledger["allowlist_sha256"] = hashlib.sha256(active_allowlist.read_bytes()).hexdigest()
        # Keep descriptor identities pinned across P1's separate path opens.
        with n.published_file(panel_path, 32 * 1024**2), n.published_file(active_allowlist, 1024**2):
            rows, start, authorization = evaluator.authorized_panel(panel_path, active_allowlist)
        _verify_inputs(permit, ledger)
        n.require(hashlib.sha256(panel_path.read_bytes()).hexdigest() == digest.hexdigest()
                  and hashlib.sha256(active_allowlist.read_bytes()).hexdigest() == ledger["allowlist_sha256"],
                  "POST_STAGE_TAMPER_DETECTED")
        common_rows = matched_population(rows)
        result = {"status": "AUTHORIZED_PANEL_PARSED", "origin_rows": len(rows),
                  "horizon_denominators": {str(h): len(rows) for h in HORIZONS},
                  "missing_outcomes": {str(h): sum(str(h) not in r["outcomes"] for r in rows) for h in HORIZONS},
                  "p1_authorization": authorization, "panel_sha256": digest.hexdigest(),
                  "evaluation_delegated": evaluate, "ledger": ledger}
        if evaluate:
            ledger["p1_evaluation_attempted"] = True
            evaluation = evaluator.evaluate(common_rows, start)
            ledger["evaluated_origin_count"] = len({key[0] for key in evaluation["records"]})
            _verify_inputs(permit, ledger)
            result["evaluated_origin_count"] = ledger["evaluated_origin_count"]
            result["evaluated_decision_records"] = len(evaluation["records"])
            # Use the original P1 reports, including its frozen folds and costs.
            report_root = p1.prepare_output(output / "p1_evaluation")
            result["evaluation"] = evaluator.write_reports(report_root, common_rows, start,
                {"mode": "HISTORICAL_OFFLINE / PIT_UNKNOWN", "authorization": authorization,
                 "source_lineage": ledger}, evaluation, "HISTORICAL_OFFLINE / PIT_UNKNOWN",
                authorization=authorization)
        return result
    except BaseException:
        # Never leave a partial or mismatched panel/derived allowlist looking ready.
        (output / stage_name).unlink(missing_ok=True)
        panel_path.unlink(missing_ok=True)
        if derived:
            active_allowlist.unlink(missing_ok=True)
        raise
