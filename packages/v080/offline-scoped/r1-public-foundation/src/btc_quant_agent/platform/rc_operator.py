"""Bounded local operator workflow; no daemon, market connection or external delivery."""
from __future__ import annotations

from pathlib import Path
import os
import stat

from .core import fingerprint
from .rc_dashboard import snapshot, write_snapshot
from .rc_fixture import DECISION, TRIGGER, fixture, future_fixture, mixed_fixture
from .rc_observe import advance_episode, observe
from .qualified_source import (BINANCE_MARKET_ENDPOINT, BINANCE_VENUE,
                              decode_binance_kline)
from .rc_source import SYMBOLS, admit_stream, normalize
from .rc_store import RCStore
from .swing import INTERVALS


def _secure_read_child(root, name, *, maximum_bytes, error_prefix):
    root = Path(root).absolute()
    if any(parent.is_symlink() for parent in (root, *root.parents)) or not root.is_dir():
        raise ValueError(error_prefix + "_ROOT_INVALID")
    if Path(name).name != name or name in {".", ".."}:
        raise ValueError(error_prefix + "_FILENAME_INVALID")
    target = root / name
    if target.is_symlink():
        raise ValueError(error_prefix + "_PATH_INVALID")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    directory_fd = None
    try:
        if os.open in getattr(os, "supports_dir_fd", set()) and hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
            if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
                os.close(directory_fd)
                directory_fd = None
                raise ValueError(error_prefix + "_ROOT_INVALID")
            descriptor = os.open(name, flags, dir_fd=directory_fd)
        else:
            descriptor = os.open(target, flags)
    except OSError as exc:
        if directory_fd is not None:
            os.close(directory_fd)
        raise ValueError(error_prefix + "_OPEN_REJECTED") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum_bytes:
            raise ValueError(error_prefix + "_NOT_BOUNDED_REGULAR_FILE")
        with os.fdopen(descriptor, "rb") as stream:
            payload = stream.read(maximum_bytes + 1)
        if len(payload) > maximum_bytes:
            raise ValueError(error_prefix + "_BYTE_LIMIT_EXCEEDED")
        return payload
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        if directory_fd is not None:
            os.close(directory_fd)


def run_demo(output, *, all_no_setup=False):
    output = Path(output)
    store = RCStore(output / "state.sqlite")
    admitted = admit_stream(store, fixture(flat=True) if all_no_setup else mixed_fixture())
    decisions = [store.compile(symbol, TRIGGER, DECISION) for symbol in SYMBOLS]
    digests = [store.commit(d) for d in decisions]
    initial = snapshot(store, now_ms=DECISION)
    write_snapshot(output / "initial", initial)
    later_ms = DECISION
    for d in decisions:
        if not d.episode_id:
            continue
        future = future_fixture(d)
        admit_stream(store, future)
        later_ms = TRIGGER + 50 * INTERVALS["1H"] + 1000
        observation = observe(d, store.receipts(), asof_ms=later_ms)
        store.record_observation(observation.model_dump(mode="json"))
        advance_episode(store, d.episode_id, now_ms=later_ms)
    final = snapshot(store, now_ms=later_ms)
    write_snapshot(output, final)
    # Reload through a fresh read-only store and verify original decisions and episode state.
    restarted = RCStore(output / "state.sqlite", readonly=True)
    counts = restarted.verify()
    replay = [fingerprint(d.model_dump(mode="json")) for d in restarted.decisions()]
    if replay != digests:
        raise ValueError("OPERATOR_RESTART_DIGEST_MISMATCH")
    return {"exposure": "SYNTHETIC", "new_receipts_admitted": admitted, "counts": counts,
            "original_decisions": {d.symbol: d.market_state for d in decisions},
            "decision_digests": digests, "replay_digests": replay,
            "snapshot_sha256": final["snapshot_sha256"],
            "initial_dashboard": str(output / "initial/latest.html"),
            "later_dashboard": str(output / "latest.html"),
            "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO", "source_qualified": False,
            "shadow_advisory_qualified": False, "economically_validated": False}


def status(output):
    store = RCStore(Path(output) / "state.sqlite", readonly=True)
    receipts = store.receipts()
    latest = {}
    for r in receipts:
        b = r.bar
        key = (b.candle.symbol, b.candle.interval)
        if key not in latest or b.end_ms > latest[key]["end_ms"]:
            latest[key] = {"end_ms": b.end_ms, "durable_ms": b.durable_ms,
                           "revision": b.revision, "receipt_id": r.identity}
    return {"mode": "READ_ONLY_RESTART_STATUS", "counts": store.verify(),
            "source_freshness": {"exposure": "SYNTHETIC", "qualified": False,
                                 "latest_completed_bars": [
                                     {"symbol": symbol, "interval": interval, **value}
                                     for (symbol, interval), value in sorted(latest.items())],
                                 "native_status": "NATIVE_BLOCKED_AUTHORITY"},
            "b_shadow_states": store.b_states(),
            "decisions": [{"symbol": d.symbol, "state": d.market_state,
                           "digest": fingerprint(d.model_dump(mode="json")), "episode_id": d.episode_id}
                          for d in store.decisions()],
            "episodes": [store.episode(d.episode_id) for d in store.decisions() if d.episode_id],
            "observations": store.observations(), "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO"}


def ingest_synthetic_fixture(output, fixture_name):
    allowed = {"SYNTHETIC_positive_v1.jsonl", "SYNTHETIC_all_no_setup_v1.jsonl",
               "SYNTHETIC_mixed_v1.jsonl"}
    if fixture_name not in allowed:
        raise ValueError("SYNTHETIC_FIXTURE_NOT_ALLOWLISTED")
    project_root = Path(__file__).resolve().parents[1] / "resources"
    fixture_root = project_root / "fixtures"
    if any(parent.is_symlink() for parent in (project_root, *project_root.parents)):
        raise ValueError("SYNTHETIC_FIXTURE_ROOT_INVALID")
    payload = _secure_read_child(fixture_root, fixture_name,
                                 maximum_bytes=8_388_608,
                                 error_prefix="SYNTHETIC_FIXTURE")
    receipts = []
    try:
        lines = payload.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("SYNTHETIC_FIXTURE_UTF8_INVALID") from exc
    for line in lines:
        if line.strip():
            receipts.append(normalize(line))
            if len(receipts) > 4096:
                raise ValueError("BACKFILL_BATCH_LIMIT_EXCEEDED")
    store = RCStore(Path(output) / "state.sqlite")
    admitted = admit_stream(store, receipts)
    return {"mode": "MANUAL_FINITE_SYNTHETIC_INGEST", "fixture": fixture_name,
            "input_receipts": len(receipts), "new_receipts_admitted": admitted,
            "exposure": "SYNTHETIC", "source_qualified": False,
            "native_status": "NATIVE_BLOCKED_AUTHORITY", "network_requests": 0}


def review_once(output, symbol, trigger_ms, decision_ms, holding_hours=24):
    if symbol not in SYMBOLS:
        raise ValueError("SYMBOL_OUT_OF_SCOPE")
    output = Path(output)
    store = RCStore(output / "state.sqlite")
    decision = store.compile(symbol, trigger_ms, decision_ms, holding_hours=holding_hours)
    digest = store.commit(decision)
    value = snapshot(store, now_ms=decision_ms)
    write_snapshot(output, value)
    return {"mode": "ONE_MANUAL_REVIEW", "symbol": symbol,
            "state": decision.market_state, "decision_digest": digest,
            "episode_id": decision.episode_id, "reasons": list(decision.reasons),
            "source": "SYNTHETIC", "account": decision.account,
            "source_qualified": False, "dashboard": str(output / "latest.html")}


def observe_episode(output, episode_id, *, asof_ms=None):
    output = Path(output)
    store = RCStore(output / "state.sqlite")
    decision = next((d for d in store.decisions() if d.episode_id == episode_id), None)
    if decision is None:
        raise ValueError("EPISODE_NOT_FOUND")
    now = asof_ms if asof_ms is not None else decision.trigger_close_ms + 50 * INTERVALS["1H"] + 1000
    episode = store.episode(episode_id)
    latest_observation_ms = max((item["asof_ms"] for item in store.observations()
                                 if item["episode_id"] == episode_id), default=decision.decision_ms)
    if now < max(episode["updated_ms"], latest_observation_ms, decision.decision_ms):
        raise ValueError("OBSERVATION_ASOF_REGRESSION")
    eligible_future = tuple(r for r in future_fixture(decision)
                            if r.bar.end_ms <= now and r.bar.durable_ms <= now)
    if eligible_future:
        admit_stream(store, eligible_future)
    item = observe(decision, store.receipts(), asof_ms=now)
    digest = store.record_observation(item.model_dump(mode="json"))
    advance_episode(store, episode_id, now_ms=now)
    value = snapshot(store, now_ms=now)
    write_snapshot(output, value)
    return {"mode": "APPENDED_SYNTHETIC_LATER_OBSERVATION", "episode_id": episode_id,
            "outcome": item.outcome, "observation_digest": digest,
            "executable_R": "UNKNOWN", "economic_evidence": False,
            "dashboard": str(output / "latest.html")}


def inspect_native_wire_file(filename, *, symbol, interval, received_ms, available_ms,
                             durable_ms, observed_now_ms, root=None):
    """Inspect one saved raw frame in an isolated quarantine directory; never admits it."""
    root = Path(root) if root is not None else Path.cwd()
    quarantine = root / "native_quarantine"
    if any(parent.is_symlink() for parent in (Path(root).absolute(), *Path(root).absolute().parents)):
        raise ValueError("NATIVE_QUARANTINE_ROOT_INVALID")
    raw = _secure_read_child(quarantine, filename, maximum_bytes=65_536,
                             error_prefix="NATIVE_QUARANTINE")
    record = decode_binance_kline(raw, venue=BINANCE_VENUE,
                                  endpoint=BINANCE_MARKET_ENDPOINT,
                                  received_ms=received_ms, available_ms=available_ms,
                                  durable_ms=durable_ms, observed_now_ms=observed_now_ms,
                                  expected_symbol=symbol, expected_interval=interval)
    return {"mode": "READ_ONLY_NATIVE_WIRE_INSPECTION",
            "source_status": record.source_status,
            "source_state": "NATIVE_BLOCKED_AUTHORITY",
            "source_id": record.source_id, "venue": record.venue,
            "endpoint": record.endpoint, "symbol": record.symbol,
            "interval": record.interval, "open_time_ms": record.open_time_ms,
            "end_time_ms": record.end_time_ms,
            "source_event_ms": record.source_event_ms,
            "received_ms": record.received_ms,
            "available_ms": record.available_ms,
            "durable_ms": record.durable_ms,
            "revision": record.revision, "provenance_id": record.provenance_id,
            "identity": record.identity, "raw_sha256": record.raw_sha256,
            "normalized_sha256": record.normalized_sha256,
            "clock_status": record.clock_status,
            "source_qualified": False, "network_requests": 0}


def recover(output):
    output = Path(output)
    store = RCStore(output / "state.sqlite")
    store.verify()
    store.reconcile()
    decisions = store.decisions()
    if not decisions:
        raise ValueError("RECOVERY_REQUIRES_DURABLE_DECISION")
    now = max([d.decision_ms for d in decisions]
              + [store.episode(d.episode_id)["updated_ms"] for d in decisions if d.episode_id]
              + [o["asof_ms"] for o in store.observations()])
    value = snapshot(store, now_ms=now)
    write_snapshot(output, value)
    return {"mode": "SNAPSHOT_RECOVERED_FROM_VERIFIED_DURABLE_STORE", "snapshot_sha256": value["snapshot_sha256"]}
