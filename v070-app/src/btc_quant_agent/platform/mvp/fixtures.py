"""Frozen deterministic demo data, never an arbitrary-file synthetic bypass."""

from __future__ import annotations

from dataclasses import asdict

from ..rc_fixture import mixed_fixture, fixture, future_fixture, TRIGGER
from .models import Dataset, Reference, Row, CaptureClocks, SYNTHETIC

SIM_BASE = TRIGGER - 61 * 86400000
SIM_BOOT = "H_FIXED_SIMULATOR_NOT_HOST_CLOCK"


def mono(utc_ms):
    return utc_ms - SIM_BASE + 1000000


def dataset(kind="mixed", *, source_ms=TRIGGER + 1000, origin="PRIMARY_DETERMINISTIC_FIXTURE", decision=None):
    if kind in ("mixed", "irreconcilable", "no-warmup", "gap"):
        records = mixed_fixture()
    elif kind == "flat":
        records = fixture(flat=True)
    elif kind.startswith("future:") and decision is not None:
        records = future_fixture(decision, scenario=kind.split(":")[1], hours=50)
    else:
        raise ValueError("UNKNOWN_FROZEN_MVP_FIXTURE")
    if kind == "no-warmup":
        records = [r for r in records if r.bar.candle.interval == "1H"]
    elif kind == "gap":
        candidates = [
            r for r in records if r.bar.candle.symbol == "BTCUSDT" and r.bar.candle.interval == "4H"
        ]
        target = candidates[len(candidates) // 2]
        records = [r for r in records if r.identity != target.identity]
    rows = []
    for r in records:
        c, b = r.bar.candle, r.bar
        interval = {"1H": "1h", "4H": "4h", "1D": "1d"}[c.interval]
        wire = {
            "stream": f"{c.symbol.lower()}@kline_{interval}",
            "data": {
                "e": "kline",
                "E": b.source_event_ms,
                "s": c.symbol,
                "k": {
                    "s": c.symbol,
                    "i": interval,
                    "t": c.open_time_ms,
                    "T": c.close_time_ms,
                    "x": True,
                    "o": str(c.open),
                    "h": str(c.high),
                    "l": str(c.low),
                    "c": str(c.close),
                    "v": str(c.volume),
                },
            },
        }
        rows.append(
            Row(
                kind="COMBINED_KLINE",
                symbol=c.symbol,
                interval=c.interval,
                candle=asdict(c),
                raw_kline=wire,
                original_source_event_ms=b.source_event_ms,
                clocks=CaptureClocks(
                    receive_wall_ms=b.received_ms,
                    available_wall_ms=b.available_ms,
                    durable_wall_ms=b.durable_ms,
                    receive_mono_ms=mono(b.received_ms),
                    available_mono_ms=mono(b.available_ms),
                    durable_mono_ms=mono(b.durable_ms),
                    boot_id=SIM_BOOT,
                ),
            )
        )
    if kind == "irreconcilable":
        rows[-1] = rows[-1].model_copy(update={"original_source_event_ms": source_ms + 5000})
    return Dataset(
        evidence_class=SYNTHETIC,
        source_id="H_FROZEN_SIMULATOR_V1",
        capture_origin=origin,
        fixture_id=kind,
        reference=Reference(
            lower_ms=source_ms,
            upper_ms=source_ms,
            received_mono_ms=mono(source_ms),
            boot_id=SIM_BOOT,
            provenance="DETERMINISTIC_SIMULATION_NOT_AUTHENTIC_EXCHANGE_TIME",
        ),
        transport_provenance="FABRICATED_WIRE_NO_EXCHANGE_CONNECTION",
        rows=rows,
    )


def verify(dataset_value, decisions):
    kind = dataset_value.fixture_id
    d = None
    if kind and kind.startswith("future:"):
        d = next((x for x in decisions if x.opportunity is not None), None)
    expected = dataset(
        kind, source_ms=dataset_value.reference.lower_ms, origin=dataset_value.capture_origin, decision=d
    )
    if dataset_value.model_dump(mode="json") != expected.model_dump(mode="json"):
        raise ValueError("SYNTHETIC_LABEL_REQUIRES_EXACT_FROZEN_FIXTURE_NO_NATIVE_RELABEL")
