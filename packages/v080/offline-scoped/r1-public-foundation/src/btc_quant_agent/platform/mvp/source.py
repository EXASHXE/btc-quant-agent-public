"""Local import and clock reconciliation adapter. This module has no sockets."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from ..core import Candle, fingerprint
from ..native.clock import Clock
from ..native.contract import canonical, digest, require, strict, verify_key, ENDPOINT
from ..qualified_source import decode_binance_kline, BINANCE_VENUE
from ..qualification.evidence import Ledger
from ..qualification.source import causal
from ..swing import INTERVALS, SwingPolicy, closed_bar_errors
from .models import Dataset, MVPBar, Sample, Reference, PermitEnvelope, SYNTHETIC, IMPORTED, CONTRACT_HASH


@dataclass(frozen=True)
class Receipt:
    original: dict
    bar: Any
    evidence_class: str
    source_id: str

    @property
    def identity(self):
        return fingerprint(["H_MVP_RECEIPT_V1", self.evidence_class, self.source_id, self.original])

    @property
    def raw_sha256(self):
        return digest(self.original)

    def model_dump(self, mode="json"):
        return {
            "schema": "H_MVP_RECEIPT_V1",
            "evidence_class": self.evidence_class,
            "source_id": self.source_id,
            "original": self.original,
            "view": self.bar.model_dump(mode="json"),
        }


def content(row):
    c = Candle(**row.candle)
    return [
        c.symbol,
        c.interval,
        c.open_time_ms,
        c.close_time_ms,
        c.open,
        c.high,
        c.low,
        c.close,
        c.volume,
        c.closed,
    ]


def normalize(ds, row):
    required = {
        "symbol",
        "interval",
        "open_time_ms",
        "close_time_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "closed",
    }
    require(
        required <= set(row.candle) <= set(Candle.__dataclass_fields__) and row.candle.get("closed") is True,
        "MVP_EXPLICIT_COMPLETED_CANDLE_SCHEMA_REQUIRED",
    )
    c = Candle(**row.candle)
    size = INTERVALS[row.interval]
    require(
        type(c.open_time_ms) is int and type(c.close_time_ms) is int and c.open_time_ms > 0,
        "MVP_BAR_TIMESTAMP_TYPE",
    )
    require(
        all(
            type(v) in (int, float) and math.isfinite(v)
            for v in (c.open, c.high, c.low, c.close, c.volume, c.quote_volume)
        ),
        "MVP_NUMERIC_OHLCV_REQUIRED",
    )
    require(
        c.symbol == row.symbol and c.interval == row.interval and c.closed is True, "MVP_CLOSED_BAR_IDENTITY"
    )
    end = c.close_time_ms + 1
    require(c.open_time_ms % size == 0 and end - c.open_time_ms == size, "MVP_INTERVAL_ALIGNMENT")
    require(
        min(c.open, c.high, c.low, c.close) > 0
        and c.low <= min(c.open, c.close) <= max(c.open, c.close) <= c.high
        and c.volume >= 0,
        "MVP_OHLCV_INVALID",
    )
    upper = ds.reference.upper_ms
    require(
        c.available_at_ms is None or end <= c.available_at_ms <= upper,
        "MVP_ORIGINAL_AVAILABILITY_CONTRADICTION",
    )
    require(end <= ds.reference.lower_ms, "MVP_INCOMPLETE_OR_FUTURE_BAR")
    event = row.original_source_event_ms
    if event is not None:
        require(end <= event <= upper, "MVP_UNRECONCILABLE_SOURCE_EVENT")
    if row.kind == "COMBINED_KLINE":
        require(row.raw_kline is not None and event is not None, "MVP_WS_RAW_EVENT_REQUIRED")
        raw = canonical(row.raw_kline)
        r = decode_binance_kline(
            raw,
            venue=BINANCE_VENUE,
            endpoint=ENDPOINT,
            expected_symbol=row.symbol,
            expected_interval={"1H": "1h", "4H": "4h", "1D": "1d"}[row.interval],
            received_ms=upper,
            available_ms=upper,
            durable_ms=upper,
            observed_now_ms=upper,
        )
        require(
            r.source_event_ms == event
            and [
                r.symbol,
                r.interval,
                r.open_time_ms,
                r.close_time_ms,
                r.open,
                r.high,
                r.low,
                r.close,
                r.volume,
                True,
            ]
            == content(row),
            "MVP_RAW_NORMALIZED_CONTRADICTION",
        )
    else:
        require(row.raw_kline is None, "MVP_DATASET_KIND_CONTRADICTION")
    require(row.revision == 0, "MVP_UNRESOLVED_REVISION")
    # This is an explicitly labelled conservative source-snapshot view for the
    # shared compiler, not a rewrite of original capture/publication timestamps.
    c = replace(c, available_at_ms=upper)
    bar = MVPBar(
        candle=c,
        source_id=ds.source_id,
        source_event_ms=event if event is not None else upper,
        received_ms=upper,
        available_ms=upper,
        durable_ms=upper,
        revision=0,
    )
    require(bar.reason(upper, SwingPolicy()) is None, "MVP_CANONICAL_VIEW_INVALID")
    return Receipt(row.model_dump(mode="json"), bar, ds.evidence_class, ds.source_id)


def authorize_import(ds, permissions):
    from .. import native

    roots = strict((Path(native.__file__).parent / "authority_roots.json").read_bytes())
    require(
        bool(roots.get("owner")) and bool(roots.get("auditor")),
        "MVP_DATA_NOT_READY_AUTHENTIC_IMPORT_PERMISSION_ABSENT",
    )
    require(permissions is not None, "MVP_IMPORT_PERMISSION_REQUIRED")
    owner = PermitEnvelope.model_validate(permissions["owner"])
    auditor = PermitEnvelope.model_validate(permissions["auditor"])
    k1 = verify_key(owner, roots["owner"])
    k2 = verify_key(auditor, roots["auditor"])
    p = owner.grant
    require(k1 != k2 and p == auditor.grant, "MVP_INDEPENDENT_IMPORT_PERMISSION")
    require(
        p.dataset_sha256 == digest(ds.model_dump(mode="json"))
        and p.source_id == ds.source_id
        and p.contract_sha256 == CONTRACT_HASH
        and p.rights_sha256 == roots.get("rights_sha256"),
        "MVP_IMPORT_PERMISSION_BINDING",
    )
    require(
        all(
            [
                p.prospective_or_historical_permission,
                p.caching_retention_reference,
                p.region_venue_reference,
                p.source_transport_reference,
                p.chronology_reference,
            ]
        ),
        "MVP_RIGHTS_OR_CHRONOLOGY_REFERENCE_MISSING",
    )


def checked_output(directory):
    directory = Path(directory)
    parts = [p.lower() for p in directory.resolve().parts]
    require(
        not any(
            "holdout" in p
            or p.startswith("l4-")
            or (p.startswith("lt-program-") and p != "lt-program-h-exploratory-mvp-01")
            for p in parts
        ),
        "MVP_ORIGINAL_OR_PROTECTED_OUTPUT_FORBIDDEN",
    )
    require(
        not any(p.is_symlink() for p in (directory, *directory.absolute().parents)),
        "MVP_OUTPUT_SYMLINK_FORBIDDEN",
    )
    return directory


class Source:
    def __init__(self, directory, *, create=False, synthetic=False, grace_ms=120000):
        self.directory = checked_output(directory)
        if create:
            require(60000 <= grace_ms <= 300000, "MVP_GRACE_REQUIRES_60_TO_300_SECONDS")
            self.directory.mkdir(parents=True, exist_ok=False)
        require(
            (self.directory / "mvp.sqlite").is_file() or create, "MVP_DATA_NOT_READY_INITIALIZE_OR_IMPORT"
        )
        database = self.directory / "mvp.sqlite"
        require(not database.is_symlink(), "MVP_STORE_SYMLINK_FORBIDDEN")
        if not create:
            try:
                with sqlite3.connect("file:" + str(database.absolute()) + "?mode=ro", uri=True) as db:
                    rows = [
                        strict(raw) for (raw,) in db.execute("SELECT body FROM evidence WHERE kind='H_MODE'")
                    ]
                require(
                    len(rows) == 1
                    and rows[0].get("mode") == "EXPLORATORY_MVP"
                    and rows[0].get("contract") == CONTRACT_HASH,
                    "MVP_STORE_MODE_MISMATCH",
                )
            except sqlite3.Error as exc:
                raise ValueError("MVP_STORE_MODE_MISMATCH") from exc
        self.events = Ledger(database)
        if create:
            self.events.append(
                "H_MODE",
                {
                    "mode": "EXPLORATORY_MVP",
                    "contract": CONTRACT_HASH,
                    "evidence_class": SYNTHETIC if synthetic else IMPORTED,
                    "grace_ms": grace_ms,
                },
            )
        meta = self.events.values("H_MODE")
        require(
            len(meta) == 1 and meta[0]["mode"] == "EXPLORATORY_MVP" and meta[0]["contract"] == CONTRACT_HASH,
            "MVP_STORE_MODE_MISMATCH",
        )
        self.meta = meta[0]

    @property
    def synthetic(self):
        return self.meta["evidence_class"] == SYNTHETIC

    def sample(self):
        if self.synthetic:
            from .fixtures import SIM_BOOT, mono
            from ..rc_fixture import TRIGGER

            rows = self.events.values("SIM_CLOCK")
            value = rows[-1] if rows else {"source_ms": TRIGGER + 1000, "wall_offset": 0}
            m = mono(value["source_ms"])
            return Sample(
                wall_ms=value["source_ms"] + value["wall_offset"],
                mono_before_ms=m,
                mono_after_ms=m,
                boot_id=SIM_BOOT,
            )
        pair = Clock().pair()
        return Sample(**pair, boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip())

    def tick(self, source_ms, wall_offset=0):
        require(self.synthetic, "MVP_TIME_OVERRIDE_FORBIDDEN_ON_IMPORTED_DATA")
        self.events.append("SIM_CLOCK", {"source_ms": source_ms, "wall_offset": wall_offset})

    def clock(self, sample):
        rows = self.events.values("CLOCK")
        old = rows[-1] if rows else None
        if old is None:
            known = not self.synthetic and "microsoft" in __import__("platform").release().lower()
            old = {
                "anchor": sample.model_dump(mode="json"),
                "last": sample.mono_after_ms,
                "held": known,
                "degraded": known,
                "reason": "KNOWN_WSL_CLOCK_HISTORY_REQUIRES_DATA_RECONCILIATION" if known else None,
            }
        else:

            class Check(Clock):
                def pair(self):
                    return {k: getattr(sample, k) for k in ("wall_ms", "mono_before_ms", "mono_after_ms")}

            detector = Check()
            detector.anchor = {k: old["anchor"][k] for k in ("wall_ms", "mono_before_ms", "mono_after_ms")}
            detector.last = old["last"]
            try:
                require(old["anchor"]["boot_id"] == sample.boot_id, "MVP_LOCAL_BOOT_CHANGED")
                detector.sample()
            except ValueError as exc:
                old = {
                    **old,
                    "held": True,
                    "degraded": True,
                    "reason": str(exc),
                    "failure": detector.failure_evidence,
                }
            old = {**old, "last": sample.mono_after_ms}
        old = {**old, "last_sample": sample.model_dump(mode="json")}
        if not rows or old != rows[-1]:
            self.events.append("CLOCK", old)
        return old

    def imports(self):
        return self.events.values("IMPORT_DURABLE")

    def datasets(self):
        return {v["dataset_id"]: v for v in self.events.values("DATASET")}

    def validate(self, ds, permissions):
        require(ds.evidence_class == self.meta["evidence_class"], "MVP_EVIDENCE_CLASS_MIXING_FORBIDDEN")
        if self.synthetic:
            from .fixtures import verify
            from .models import Decision

            decisions = [Decision.model_validate_json(json.dumps(x)) for x in self.events.values("DECISION")]
            verify(ds, decisions)
        else:
            authorize_import(ds, permissions)
        normalized = [normalize(ds, row) for row in ds.rows]
        require(normalized, "MVP_EMPTY_DATASET")
        return normalized

    def ingest(self, ds, permissions=None):
        identity = digest(ds.model_dump(mode="json"))
        if identity in self.datasets():
            if any(r["dataset_id"] == identity for r in self.imports()):
                return {"status": "DUPLICATE_DATASET_NO_CHANGE", "dataset_id": identity}
            self.validate(ds, permissions)
            sample = self.sample()
            ds.reference.project(sample)
            self.clock(sample)
            self.events.append(
                "IMPORT_DURABLE",
                {
                    "dataset_id": identity,
                    "sample": sample.model_dump(mode="json"),
                    "reference": ds.reference.model_dump(mode="json"),
                    "recovered_after_interrupted_import": True,
                },
            )
            self.events.append("SOURCE_REFERENCE", {"reference": ds.reference.model_dump(mode="json")})
            return {"status": "RECOVERED_IMPORT_WITH_NEW_DURABILITY_STAMP", "dataset_id": identity}
        try:
            self.validate(ds, permissions)
            sample = self.sample()
            ds.reference.project(sample)
            state = self.clock(sample)
            prior = self.events.values("SOURCE_REFERENCE")
            if prior:
                previous = Reference.model_validate(prior[-1]["reference"])
                if previous.boot_id == sample.boot_id:
                    previous_lower = previous.lower_ms + sample.mono_before_ms - previous.received_mono_ms
                    new_upper = ds.reference.upper_ms + sample.mono_after_ms - ds.reference.received_mono_ms
                    require(new_upper >= previous_lower, "MVP_SOURCE_REFERENCE_REGRESSION")
            offsets: dict[str, list[int]] = {}
            for row in ds.rows:
                offsets.setdefault(row.clocks.boot_id, []).append(
                    row.clocks.receive_wall_ms - row.clocks.receive_mono_ms
                )
            uncertain = (
                state["held"]
                or any(r.clocks.jumped() for r in ds.rows)
                or any(max(v) - min(v) > 50 for v in offsets.values())
            )
            if uncertain and not state["held"]:
                self.events.append(
                    "CLOCK", {**state, "held": True, "degraded": True, "reason": "MVP_CAPTURE_CLOCK_JUMP"}
                )
            self.events.append(
                "DATASET",
                {
                    "dataset_id": identity,
                    "dataset": ds.model_dump(mode="json"),
                    "permissions": permissions,
                    "quarantined": uncertain,
                },
            )
            durable = self.sample()
            self.events.append(
                "IMPORT_DURABLE",
                {
                    "dataset_id": identity,
                    "sample": durable.model_dump(mode="json"),
                    "reference": ds.reference.model_dump(mode="json"),
                },
            )
            self.events.append("SOURCE_REFERENCE", {"reference": ds.reference.model_dump(mode="json")})
            return {
                "status": "QUARANTINED_CLOCK_DEGRADED" if uncertain else "IMPORTED_COMPLETED_UNQUALIFIED",
                "dataset_id": identity,
            }
        except (ValueError, KeyError) as exc:
            self.events.append("REJECTED_IMPORT", {"dataset_id": identity, "reason": str(exc)})
            raise

    def reference(self):
        entries = self.events.values("SOURCE_REFERENCE")
        if entries:
            return Reference.model_validate(entries[-1]["reference"])
        require(self.imports(), "MVP_DATA_NOT_READY_NO_LAWFUL_WARMUP")
        return Reference.model_validate(self.imports()[-1]["reference"])

    def receipts(self):
        data = self.datasets()
        released = set()
        for entry in self.events.values("RECONCILIATION"):
            released.update(entry["dataset_ids"])
        out = []
        seen: dict[tuple, list] = {}
        for commit in self.imports():
            entry = data[commit["dataset_id"]]
            if entry["quarantined"] and commit["dataset_id"] not in released:
                continue
            ds = Dataset.model_validate(entry["dataset"])
            normalized = self.validate(ds, entry["permissions"])
            for row, receipt in zip(ds.rows, normalized):
                key = tuple(content(row)[:4])
                value = content(row)
                if key in seen:
                    require(seen[key] == value, "MVP_UNRECONCILED_CANDLE_CORRECTION")
                    continue
                seen[key] = value
                out.append(receipt)
        return out

    def assess(self, symbol=None):
        records = []
        try:
            sample = self.sample()
            state = self.clock(sample)
            lower, upper = self.reference().project(sample)
            require(not state["held"], "CLOCK_DEGRADED_HOLD_RECONCILIATION_REQUIRED")
            require(not self.events.values("REJECTED_IMPORT"), "MVP_UNRECONCILED_REJECTED_IMPORT")
            commits = self.imports()
            require(commits, "MVP_DATA_NOT_READY_NO_IMPORT")
            for commit in commits:
                c = Sample.model_validate(commit["sample"])
                if c.boot_id == sample.boot_id:
                    require(c.mono_after_ms <= sample.mono_before_ms, "MVP_IMPORT_NOT_DURABLE_BEFORE_REVIEW")
                else:
                    require(self.events.values("RECONCILIATION"), "MVP_RESTART_DATA_REVALIDATION_REQUIRED")
            records = self.receipts()
            trigger = lower // INTERVALS["4H"] * INTERVALS["4H"]
            require(
                self.meta["grace_ms"] <= lower - trigger <= 300000, "MVP_CLOSE_GRACE_OR_FRESHNESS_NOT_MET"
            )
            for name in [symbol] if symbol else ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
                rows, _ = causal(records, name, trigger, lower)
                errors = closed_bar_errors(
                    [r.bar for r in rows],
                    symbol=name,
                    decision_ms=lower,
                    trigger_close_ms=trigger,
                    policy=SwingPolicy(),
                )
                require(not errors, "MVP_WARMUP_OR_COMPLETENESS:" + ",".join(errors))
            return {
                "status": "ELIGIBLE",
                "data_status": "MVP_SYNTHETIC_READY"
                if self.synthetic
                else "MVP_AUTHORIZED_IMPORT_READY_UNQUALIFIED",
                "records": records,
                "source_bounds": [lower, upper],
                "sample": sample,
                "trigger": trigger,
                "clock": "CLOCK_DEGRADED_RECONCILED" if state["degraded"] else "MVP_CLOCK_OK_UNQUALIFIED",
                "watermark": len(commits),
                "reason": None,
            }
        except (ValueError, KeyError) as exc:
            return {
                "status": "MVP_DATA_NOT_READY",
                "data_status": "MVP_DATA_NOT_READY",
                "records": records,
                "reason": str(exc),
                "clock": "CLOCK_DEGRADED_HOLD"
                if self.events.values("CLOCK") and self.events.values("CLOCK")[-1]["held"]
                else "UNQUALIFIED",
                "source_qualified": False,
            }

    def reconcile(self, witness, permissions=None):
        normalized = self.validate(witness, permissions)
        sample = self.sample()
        lower, _ = witness.reference.project(sample)
        primary = self.datasets()
        require(primary, "MVP_RECONCILIATION_REQUIRES_DATA")
        require(
            witness.capture_origin not in {e["dataset"]["capture_origin"] for e in primary.values()},
            "MVP_INDEPENDENT_SNAPSHOT_REQUIRED",
        )
        witness_content = {tuple(content(r)[:4]): content(r) for r in witness.rows}
        for entry in primary.values():
            ds = Dataset.model_validate(entry["dataset"])
            self.validate(ds, entry["permissions"])
            require(
                all(witness_content.get(tuple(content(r)[:4])) == content(r) for r in ds.rows),
                "MVP_WITNESS_SOURCE_DISAGREEMENT",
            )
        trigger = lower // INTERVALS["4H"] * INTERVALS["4H"]
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            rows, _ = causal(normalized, symbol, trigger, lower)
            require(
                not closed_bar_errors(
                    [r.bar for r in rows],
                    symbol=symbol,
                    decision_ms=lower,
                    trigger_close_ms=trigger,
                    policy=SwingPolicy(),
                ),
                "MVP_WITNESS_WARMUP_OR_CAUSALITY_FAILED",
            )
        require(
            not self.events.values("REJECTED_IMPORT"),
            "MVP_IRRECONCILABLE_IMPORT_REQUIRES_NEW_VERSIONED_DATASET",
        )
        self.events.append(
            "RECONCILIATION",
            {
                "mode": "EXPLORATORY_MVP",
                "evidence_class": self.meta["evidence_class"],
                "witness": witness.model_dump(mode="json"),
                "permissions": permissions,
                "dataset_ids": list(primary),
                "sample": sample.model_dump(mode="json"),
                "strict_qualification": False,
            },
        )
        self.events.append("SOURCE_REFERENCE", {"reference": witness.reference.model_dump(mode="json")})
        self.events.append(
            "CLOCK",
            {
                "anchor": sample.model_dump(mode="json"),
                "last": sample.mono_after_ms,
                "held": False,
                "degraded": True,
                "reason": "INDEPENDENT_DATA_RECONCILIATION_EXPLORATORY_ONLY",
            },
        )
        return {
            "status": "CLOCK_DEGRADED_RECONCILED",
            "new_candidates_permitted_after_all_other_gates": True,
            "strict_qualification": False,
        }
