"""Fabricated clocks and PUBLIC-shaped envelopes only; no native network I/O."""

from copy import deepcopy
from dataclasses import replace
import gzip
import hashlib
import json
import os
from pathlib import Path

import pytest

from btc_quant_agent.platform.canary import clock_domain as d
from btc_quant_agent.platform.canary.public_data import normalize, quote_from_record, bar_from_record
from btc_quant_agent.platform.canary.public_io import Wire
from btc_quant_agent.platform.canary.public_policy import START, END, PublicStop, Window, SystemClock
from btc_quant_agent.platform.canary.control import CanaryStore
from btc_quant_agent.platform.core import (
    Candle,
    MarketEvent,
    PositionState,
    dec,
    DataProvenance,
    InstrumentSpec,
    primitive,
)
from btc_quant_agent.platform.position_management import supervise
from btc_quant_agent.platform.selection.management import ExitPolicy
from btc_quant_agent.platform.selection.sources import FrozenUniverse, SourceHistory, aggregate_five_minutes
from .fixtures import meta_payload

SCOPE = "a" * 64


class EpochClock:
    """Manual fake with independently variable wall/monotonic clocks."""

    def __init__(self, wall=START + 1_000_000, epoch="fabricated-epoch-1"):
        self.w = wall
        self.m = 1_000_000
        self.epoch = d.ClockEpoch(epoch)
        self.utc_uncertainty_ms = 1
        self.sample()

    def wall(self):
        return self.w

    def mono(self):
        return self.m

    def pair(self):
        s = self.sample()
        return s["wall_ms"], s["mono_after_ms"]

    def sample(self):
        self.sync_evidence = {"status": "SYNC_OBSERVED", "uncertainty_ms": 1, "sample_mono_ms": self.m}
        return self.epoch.capture(self.w, self.m, self.m, self.sync_evidence)

    def advance(self, elapsed, wall_step=0):
        self.m += elapsed
        self.w += elapsed + wall_step


def probes(clock, offset=0, *, rtt=20, exposure="PUBLIC_CANARY"):
    values = []
    for i in range(2):
        clock.advance(5)
        request = clock.sample()
        server = clock.wall() + offset + rtt // 2
        clock.advance(rtt)
        received = clock.sample()
        clock.advance(1)
        values.append(
            {
                "request": request,
                "receive": received,
                "available": clock.sample(),
                "server_ms": server,
                "scope_hash": SCOPE,
                "exposure": exposure,
                "wire_id": hashlib.sha256(str(i).encode()).hexdigest(),
            }
        )
    return values


def frame(clock, endpoint, payload, symbol="*", stream=None, request=None):
    received = clock.sample()
    clock.advance(1)
    available = clock.sample()
    return Wire(
        endpoint,
        symbol,
        {},
        json.dumps(payload, sort_keys=True),
        request["wall_ms"] if request else None,
        request["mono_after_ms"] if request else None,
        received["wall_ms"],
        received["mono_after_ms"],
        available["wall_ms"],
        available["mono_after_ms"],
        stream=stream,
        exposure="PUBLIC_CANARY",
        clock_samples={
            "receive": received,
            "available": available,
            **({"request": request} if request else {}),
        },
    )


def scenario(offset=0):
    c = EpochClock()
    meta = frame(c, "binance_usdm_exchange_info", meta_payload())
    p = probes(c, offset)
    e = d.estimate(p, SCOPE, "PUBLIC_CANARY")
    c.advance(100)
    event = c.wall() + offset - 50
    w = frame(
        c,
        "binance_usdm_bbo_ws",
        {
            "stream": "btcusdt@bookTicker",
            "data": {
                "e": "bookTicker",
                "st": 1,
                "u": 10,
                "s": "BTCUSDT",
                "E": event,
                "T": event - 2,
                "b": "100.00",
                "a": "100.02",
                "B": "10",
                "A": "20",
            },
        },
        "BTCUSDT",
        "btcusdt@bookTicker",
    )
    c.advance(1)
    decision = c.sample()
    record = {
        "wire": w.record(),
        "exposure": "PUBLIC_CANARY",
        "scope_hash": SCOPE,
        "symbol": w.symbol,
        "received_wall_ms": w.receive_wall,
        "clock_contract_version": d.VERSION,
        "clock": e,
        "metadata": {"wire": meta.record()},
        "decision_sample": decision,
        "decision_wall_ms": decision["wall_ms"],
        "decision_mono_ms": decision["mono_after_ms"],
    }
    return c, record


@pytest.mark.parametrize("offset", [0, 846, -846])
def test_bounded_stable_offsets_admit_without_rebasing(offset):
    c, record = scenario(offset)
    result = normalize(record)
    assert result["status"] == "ADMITTED_OBSERVATION", result
    q = quote_from_record(result["quote"])
    native = json.loads(record["wire"]["payload_text"])["data"]["E"]
    assert q.provenance.exchange_event_ts == native
    assert q.provenance.received_ts == record["wire"]["receive_wall"]
    assert q.provenance.available_ts == record["wire"]["available_wall"]
    if offset > 0:
        assert native > q.provenance.received_ts
        legacy = DataProvenance(
            "binance", "legacy-synthetic", native, q.provenance.received_ts, q.provenance.available_ts
        )
        assert legacy.reason(c.wall(), 5000) == "CLOCK_ORDER_INVALID"
    assert result["native_transaction_ms"] == native - 2
    assert result["clock"]["event_to_receive_estimate_bounds_ms"] == [39, 61]
    assert not result["clock"]["one_way_latency_proven"]
    with d.decision_clock(c.sample(), SCOPE):
        assert q.reason(InstrumentSpec("BTCUSDT", provider="binance"), c.wall(), 5000) is None
    assert q.provenance.reason(c.wall(), 5000) == "CLOCK_DECISION_EVIDENCE_MISSING"


@pytest.mark.parametrize("step", [900, -900])
def test_wall_step_invalidates_epoch_and_old_quotes_irreversibly(step):
    c, record = scenario(846)
    q = quote_from_record(normalize(record)["quote"])
    c.advance(10, wall_step=step)
    after = c.sample()
    assert d.sample_reason(after) == "LOCAL_WALL_CLOCK_JUMP"
    with d.decision_clock(after, SCOPE):
        assert q.provenance.reason(c.wall(), 5000) == "LOCAL_WALL_CLOCK_JUMP"
    c.advance(10, wall_step=-step)
    assert d.sample_reason(c.sample()) == "LOCAL_WALL_CLOCK_JUMP"
    fresh = deepcopy(record)
    fresh["decision_sample"] = after
    fresh.update(decision_wall_ms=after["wall_ms"], decision_mono_ms=after["mono_after_ms"])
    result = normalize(fresh)
    assert not result["quote"] and result["status"] == "INADMISSIBLE"


def test_fifty_ms_detector_is_not_relaxed_by_native_offset():
    c = EpochClock()
    c.advance(10, wall_step=49)
    assert d.sample_reason(c.sample()) is None
    c.advance(10, wall_step=3)
    assert d.sample_reason(c.sample()) == "LOCAL_WALL_CLOCK_JUMP"
    assert d.WALL_STEP_MS == 50


def test_system_clock_brackets_raw_reads_and_retains_invalid_samples(monkeypatch):
    values = {"wall": START + 1000, "mono": 1000}
    monkeypatch.setattr(SystemClock, "wall", lambda self: values["wall"])
    monkeypatch.setattr(SystemClock, "mono", lambda self: values["mono"])

    def sync(self):
        self.sync_evidence = {
            "status": "SYNC_OBSERVED",
            "uncertainty_ms": 1,
            "sample_mono_ms": values["mono"],
        }
        self.utc_uncertainty_ms = 1

    monkeypatch.setattr(SystemClock, "refresh_sync", sync)
    clock = SystemClock()
    window = Window(clock)
    first = clock.sample()
    assert first["mono_before_ms"] == first["mono_after_ms"] == 1000
    values.update(wall=values["wall"] + 910, mono=1010)
    after = clock.sample()
    assert after["wall_ms"] == values["wall"] and after["epoch_id"] == first["epoch_id"]
    assert d.sample_reason(after) == "LOCAL_WALL_CLOCK_JUMP"
    assert clock.pair() == (values["wall"], values["mono"])
    with pytest.raises(PublicStop, match="LOCAL_WALL_CLOCK_JUMP"):
        window.check()


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("missing", "CLOCK_UNCERTAINTY_UNKNOWN"),
        ("single", "MULTIPLE_INDEPENDENT_CLOCK_PROBES_REQUIRED"),
        ("duplicate", "CLOCK_PROBES_NOT_INDEPENDENT_OR_ORDERED"),
        ("overlap", "CLOCK_PROBES_NOT_INDEPENDENT_OR_ORDERED"),
        ("epoch", "CLOCK_EPOCH_MIXING"),
        ("exposure", "CLOCK_PROBE_SCOPE_OR_EXPOSURE_MISMATCH"),
        ("scope", "CLOCK_PROBE_SCOPE_OR_EXPOSURE_MISMATCH"),
        ("tamper", "CLOCK_ESTIMATE_EVIDENCE_MISMATCH"),
        ("unsync", "CLOCK_SYNC_UNVERIFIED"),
        ("unbracketed", "CLOCK_SAMPLE_INVALID"),
        ("wide", "CLOCK_SAMPLE_BRACKET_TOO_WIDE"),
        ("sync_missing", "CLOCK_SYNC_UNVERIFIED"),
        ("epoch_flag", "CLOCK_EPOCH_INVALID"),
    ],
)
def test_probe_and_capture_failures_are_explicit(fault, expected):
    _, r = scenario(846)
    e = r["clock"]
    if fault == "missing":
        r["clock"] = None
    elif fault == "single":
        e["probes"] = e["probes"][:1]
    elif fault == "duplicate":
        e["probes"][1]["wire_id"] = e["probes"][0]["wire_id"]
    elif fault == "overlap":
        e["probes"][1]["request"] = deepcopy(e["probes"][0]["request"])
    elif fault == "epoch":
        e["probes"][1]["receive"]["epoch_id"] = "foreign-epoch"
    elif fault in ("scope", "exposure"):
        e["probes"][0]["scope_hash" if fault == "scope" else "exposure"] = "wrong"
    elif fault == "tamper":
        e["native_minus_monotonic_low_ms"] += 1
    elif fault == "unsync":
        r["wire"]["clock_samples"]["receive"]["sync"]["status"] = "UNVERIFIED"
    elif fault == "unbracketed":
        r["wire"]["clock_samples"]["receive"].pop("mono_before_ms")
    elif fault == "wide":
        r["wire"]["clock_samples"]["receive"]["mono_before_ms"] -= 6
    elif fault == "sync_missing":
        r["wire"]["clock_samples"]["receive"]["sync"] = None
    elif fault == "epoch_flag":
        r["wire"]["clock_samples"]["receive"]["epoch_valid"] = "false"
    result = normalize(r)
    assert result["quote"] is None
    assert expected in result["reasons"], result


@pytest.mark.parametrize(
    "fault", ["negative_latency", "expired_event", "stale_probes", "jitter", "unknown_semantics"]
)
def test_no_midpoint_or_local_wall_shortcut(fault):
    c, r = scenario(846)
    if fault in ("negative_latency", "expired_event"):
        payload = json.loads(r["wire"]["payload_text"])
        payload["data"]["E"] += 50 if fault == "negative_latency" else -6000
        payload["data"]["T"] = payload["data"]["E"] - 2
        r["wire"]["payload_text"] = json.dumps(payload)
    elif fault == "stale_probes":
        c.advance(d.MAX_PROBE_AGE_MS + 1)
        s = c.sample()
        r.update(decision_sample=s, decision_wall_ms=s["wall_ms"], decision_mono_ms=s["mono_after_ms"])
    elif fault == "jitter":
        c2 = EpochClock()
        p = probes(c2, 846, rtt=300)
        r["clock"] = d.estimate(p, SCOPE, "PUBLIC_CANARY")
        c2.advance(500)
        s = c2.sample()
        r.update(decision_sample=s, decision_wall_ms=s["wall_ms"], decision_mono_ms=s["mono_after_ms"])
    elif fault == "unknown_semantics":
        r["wire"].update(
            endpoint_id="binance_usdm_premium",
            stream=None,
            params={"symbol": "BTCUSDT"},
            payload_text=json.dumps(
                {"symbol": "BTCUSDT", "time": c.wall() + 846 - 50, "lastFundingRate": "0.001"}
            ),
        )
    result = normalize(r)
    expected = {
        "negative_latency": "SOURCE_TIME_POTENTIALLY_FUTURE",
        "expired_event": "SOURCE_AGE_UPPER_BOUND_EXCEEDED",
        "stale_probes": "CLOCK_ESTIMATE_STALE",
        "jitter": "CLOCK_UNCERTAINTY_EXCEEDS_LEASE",
        "unknown_semantics": "NATIVE_TIMESTAMP_OR_SEMANTICS_UNKNOWN",
    }[fault]
    assert not result["quote"] and expected in result["reasons"], result


def test_probe_union_keeps_slow_probe_uncertainty():
    c = EpochClock()
    p = probes(c, 846, rtt=300)
    fast = probes(c, 846)
    for i, item in enumerate(fast):
        item["wire_id"] = hashlib.sha256(f"fast{i}".encode()).hexdigest()
    e = d.estimate(p + fast, SCOPE, "PUBLIC_CANARY")
    assert e["uncertainty_ms"] == 151 and e["rtt_ms"] == [300, 300, 20, 20]


def test_uncertainty_cannot_exceed_shorter_lease():
    _, r = scenario(846)
    s = r["wire"]["clock_samples"]
    result = d.qualify(
        r["clock"],
        json.loads(r["wire"]["payload_text"])["data"]["E"],
        s["receive"],
        s["available"],
        r["decision_sample"],
        SCOPE,
        "PUBLIC_CANARY",
        10,
        "EVENT_TIME",
    )
    assert result["reason"] == "CLOCK_UNCERTAINTY_EXCEEDS_LEASE"


def test_clock_provenance_is_bound_to_wire_and_current_epoch():
    c, r = scenario(846)
    q = quote_from_record(normalize(r)["quote"])
    with d.decision_clock(c.sample(), SCOPE):
        assert (
            replace(q.provenance, exchange_event_ts=q.provenance.exchange_event_ts - 1).reason(c.wall(), 5000)
            == "CLOCK_PROVENANCE_BINDING_MISMATCH"
        )
        assert (
            replace(q.provenance, received_ts=q.provenance.received_ts + 1).reason(c.wall(), 5000)
            == "CLOCK_PROVENANCE_BINDING_MISMATCH"
        )
    replacement = EpochClock(c.wall(), epoch="fabricated-restarted-process")
    with d.decision_clock(replacement.sample(), SCOPE):
        assert q.provenance.reason(replacement.wall(), 5000) == "CLOCK_EPOCH_MIXING"
    base = DataProvenance(
        "binance", q.provenance.source_id, c.wall() - 1, c.wall(), c.wall(), "PUBLIC_CANARY"
    )
    assert base.reason(c.wall(), 5000) == "PUBLIC_CLOCK_EVIDENCE_MISSING"


@pytest.mark.parametrize("step", [0, 900, -900])
def test_exact_utc_end_and_near_end_clock_changes_never_extend_window(step):
    c = EpochClock(END - 2000)
    window = Window(c)
    deadline = window.mono_end
    window.check()
    c.advance(1000, wall_step=step)
    if step:
        with pytest.raises(PublicStop, match="LOCAL_WALL_CLOCK_JUMP"):
            window.check()
    else:
        window.check()
    assert window.mono_end <= deadline
    c.advance(1000)
    with pytest.raises(PublicStop):
        window.check()
    c.w = END - 10_000
    with pytest.raises(PublicStop):
        window.check()


@pytest.mark.parametrize("offset", [0, 846, -846])
def test_native_completed_candle_feeds_l23_history_with_original_clocks(offset):
    c, r = scenario(offset)
    # Use a native-aligned minute whose close precedes receive by 50ms.
    end = ((c.wall() + offset) // 60000 + 1) * 60000
    c.advance(end + 50 - offset - c.wall())
    k = {
        "s": "BTCUSDT",
        "i": "1m",
        "x": True,
        "t": end - 60000,
        "T": end - 1,
        "o": "100",
        "h": "101",
        "l": "99",
        "c": "100",
        "v": "10",
        "q": "1000",
    }
    w = frame(
        c,
        "binance_usdm_klines_ws",
        {"stream": "btcusdt@kline_1m", "data": {"e": "kline", "s": "BTCUSDT", "st": 1, "E": end + 1, "k": k}},
        "BTCUSDT",
        "btcusdt@kline_1m",
    )
    s = c.sample()
    r.update(
        wire=w.record(), decision_sample=s, decision_wall_ms=s["wall_ms"], decision_mono_ms=s["mono_after_ms"]
    )
    result = normalize(r)
    assert result["status"] == "ADMITTED_OBSERVATION", result
    bar = bar_from_record(result["bars"][0])
    assert bar.fields[0].provenance.exchange_event_ts == end - 1
    with d.decision_clock(c.sample(), SCOPE):
        values, errors = bar.values(c.wall())
        assert values["close"] == 100 and not errors
        history = SourceHistory(
            (bar,), FrozenUniverse(("BTCUSDT",), "BTCUSDT", end, interval_ms=60000, decision_ts=c.wall())
        )
        assert history.synchronized(), history.errors
        with pytest.raises(ValueError, match="NATIVE_AGGREGATION_PROOF_COMPOSITION_UNSUPPORTED"):
            aggregate_five_minutes((bar,), c.wall())
        p = bar.fields[0].provenance
        event = MarketEvent(
            bar.spec,
            Candle(
                "BTCUSDT",
                "1m",
                bar.start,
                bar.end - 1,
                open=100,
                high=101,
                low=99,
                close=100,
                volume=10,
                closed=True,
                available_at_ms=p.available_ts,
            ),
            p,
            c.wall(),
        )
        assert event.reason(90000) is None
        position = PositionState(
            "owner-fixture",
            "BTCUSDT",
            "LONG",
            dec(100),
            dec(1),
            dec("99.5"),
            dec("99.5"),
            1,
            "ISOLATED",
            1,
            "OPEN",
            "USER_REPORTED",
            c.wall() - 100,
        )
        for action in (supervise(position, event), supervise(position, event, episode_policy=ExitPolicy())):
            assert action.action == "EXIT" and action.execution_status == "EXECUTION_UNKNOWN"
        assert position.status == "OPEN"
    c.advance(1, wall_step=900)
    with d.decision_clock(c.sample(), SCOPE):
        assert not bar.values(c.wall())[0]
        assert supervise(position, replace(event, decision_ts=c.wall())).action == "RECONCILE"


@pytest.mark.parametrize("small_wall_change", [0, -49])
def test_native_quote_proof_cannot_survive_utc_or_monotonic_grant_end(small_wall_change):
    c, record = scenario(846)
    q = quote_from_record(normalize(record)["quote"])
    c.advance(END - c.wall(), wall_step=small_wall_change)
    sample = c.sample()
    assert d.sample_reason(sample) is None
    with d.decision_clock(sample, SCOPE):
        assert q.provenance.reason(c.wall(), 5000) == "GRANT_WINDOW_EXPIRED"


def test_native_original_expiry_equality_uses_frozen_earliest_monotonic_deadline():
    c, r = scenario(846)
    p = quote_from_record(normalize(r)["quote"]).provenance
    expiry_native = p.exchange_event_ts + 10000
    deadline = d.native_bounds(p, expiry_native)[0]
    a = {"expiry": expiry_native, "expiry_mono_ms": deadline, "clock_epoch_id": c.epoch.id}
    c.advance(deadline - c.mono() - 1)
    with d.decision_clock(c.sample(), SCOPE):
        assert not d.expired(a, c.wall())
    c.advance(1)
    with d.decision_clock(c.sample(), SCOPE):
        assert d.expired(a, c.wall())
    assert a["expiry"] == expiry_native and a["expiry_mono_ms"] == deadline


def test_native_regime_source_override_does_not_compare_raw_native_cutoff_to_wall(tmp_path):
    c, record = scenario(846)
    native = json.loads(record["wire"]["payload_text"])["data"]["E"]
    assert native > c.wall()
    store = CanaryStore(tmp_path / "s.sqlite")
    store.save_regime(
        "BTCUSDT",
        {
            "state": "TREND_UP",
            "pending": "TREND_UP",
            "count": 2,
            "failures": 0,
            "cutoff": native,
            "clock_sample": record["decision_sample"],
            "clock_scope_hash": SCOPE,
        },
    )
    with d.decision_clock(c.sample(), SCOPE):
        store.revoke_regime("BTCUSDT", c.wall(), native)
    value = store.regime("BTCUSDT")
    assert value["state"] == "UNKNOWN" and value["cutoff"] == native
    assert value["source_override_ts"] == c.wall()


def test_sealed_native_legacy_replay_is_identical_and_read_only():
    default = Path(__file__).resolve().parents[2] / "artifacts/live_public_canary_20261030/run"
    root = Path(os.environ.get("L4_SEALED_NATIVE_RUN", str(default)))
    before = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for kind in ("raw", "normalized")
        for p in (root / kind).glob("*.gz")
    }
    raw = {}
    for p in (root / "raw").glob("*.gz"):
        raw[p.name[:-8]] = json.loads(gzip.decompress(p.read_bytes()))["records"]
    pairs = records = 0
    for p in (root / "normalized").glob("*.gz"):
        normal = json.loads(gzip.decompress(p.read_bytes()))
        replay = [primitive(normalize(r)) for r in raw[normal["raw_sha"]]]
        assert replay == normal["records"]
        pairs += 1
        records += len(replay)
    assert (pairs, records) == (5, 103)
    assert before == {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in before}
