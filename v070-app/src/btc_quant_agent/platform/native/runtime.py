"""Finite foreground capture; consumed reservation precedes any transport request."""

from __future__ import annotations

from contextlib import contextmanager
import base64
import hashlib
import os
from pathlib import Path
import signal

from ..qualified_source import decode_binance_kline, BINANCE_VENUE
from .clock import Clock
from .contract import (
    AuditEnvelope,
    Envelope,
    Policy,
    Stop,
    authorize,
    authorization_proof,
    canonical,
    digest,
    require,
    source_hash,
    strict,
)
from .journal import Journal
from .transport import Transport


@contextmanager
def exclusive(path):
    handle = open(path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if not handle.read(1):
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            getattr(msvcrt, "locking")(handle.fileno(), getattr(msvcrt, "LK_NBLCK"), 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


def consume(raw, sample, grant, clock, seen):
    obj = strict(raw)
    require(set(obj) == {"stream", "data"} and obj["stream"] in grant.streams, "COMBINED_STREAM_SCOPE")
    event = obj["data"]
    require(
        isinstance(event, dict) and event.get("e") == "kline" and isinstance(event.get("k"), dict),
        "KLINE_TYPE",
    )
    k = event["k"]
    symbol, interval = obj["stream"].split("@kline_")
    require(event.get("s") == k.get("s") == symbol.upper() and k.get("i") == interval, "WIRE_SCOPE_MISMATCH")
    require(type(k.get("x")) is bool, "FINAL_FLAG_INVALID")
    if k["x"] is False:
        return "PARTIAL_IGNORED", {"stream": obj["stream"], "source_qualified": False}
    received = sample["wall_ms"]
    clock.event(event["E"], sample)
    record = decode_binance_kline(
        raw,
        venue=BINANCE_VENUE,
        endpoint=grant.endpoint,
        expected_symbol=symbol.upper(),
        expected_interval=interval,
        received_ms=received,
        available_ms=received,
        durable_ms=received,
        observed_now_ms=received,
    )
    value = record.model_dump(mode="json")
    identity = record.identity
    semantic = digest(
        [
            record.symbol,
            record.interval,
            record.open_time_ms,
            record.end_time_ms,
            record.open,
            record.high,
            record.low,
            record.close,
            record.volume,
        ]
    )
    if identity in seen:
        require(seen[identity] == semantic, "CORRECTION_REQUIRES_REQUALIFICATION")
        return "DUPLICATE", {"identity": identity, "raw_sha256": record.raw_sha256}
    seen[identity] = semantic
    return "COMPLETED", {
        "schema_version": "E_NATIVE_RECEIPT_V1",
        "exposure": grant.exposure,
        "identity": identity,
        "record": value,
        "clock_proof": clock.estimate,
        "receive_sample": sample,
        "grant_sha256": digest(grant.model_dump(mode="json")),
        "source_qualified": False,
        "classification": "CLOCK_CHECKED_WARMUP_UNQUALIFIED"
        if grant.exposure == "NATIVE_UNQUALIFIED"
        else "SYNTHETIC_NETWORK",
    }


def capture(grant, policy, journal, clock, transport):
    reason, report, failure = "UNKNOWN", None, None
    reserved = False
    prior = {}
    seen: dict[str, str] = {}
    try:
        seen = journal.initial_seen(grant.exposure, clock.sample()["wall_ms"])
        journal.reserve(grant)
        reserved = True
        with journal.db() as db:
            journal.append(db, grant.session_id, "AUTHORIZATION_VERIFIED", authorization_proof(grant))
        for sig in (signal.SIGINT, signal.SIGTERM):
            if __import__("threading").current_thread() is __import__("threading").main_thread():
                prior[sig] = signal.getsignal(sig)
                signal.signal(sig, lambda *_: (_ for _ in ()).throw(Stop("INTERRUPTED_RECEIVER")))
        clock.check(grant, require_probes=False)
        clock.refresh(transport, grant, journal)
        transport.open()
        while True:
            sample = clock.check(grant)
            if sample["mono_after_ms"] - clock.estimate["at_mono_ms"] >= policy.clock_refresh_ms:
                clock.refresh(transport, grant, journal)
            transport.heartbeat()
            event = transport.next_event()
            if event is None:
                continue
            clock.check(grant)
            sample = transport.last_receive_sample
            kind, raw = transport.frame_payload(event)
            frame = journal.receive(grant, raw, sample["wall_ms"], len(transport.pending))
            try:
                if kind == "TEXT":
                    state, value = consume(raw, sample, grant, clock, seen)
                    # The receipt's availability is only after the normalized transaction.
                    value["normalized_before_commit_ms"] = clock.check(grant)["wall_ms"]
                else:
                    state, value = "CONTROL", {"opcode": kind, "raw_b64": base64.b64encode(raw).decode()}
                journal.settle(grant, frame, "PREPARED" if state == "COMPLETED" else state, value)
                if state == "COMPLETED":
                    # The full raw+normalized preparation is already FULL-synced.
                    # Stamp its actual availability after that commit, never before it.
                    durable = clock.check(grant)["wall_ms"]
                    record = value["record"]
                    verified = decode_binance_kline(
                        raw,
                        venue=BINANCE_VENUE,
                        endpoint=grant.endpoint,
                        expected_symbol=record["symbol"],
                        expected_interval={"1H": "1h", "4H": "4h", "1D": "1d"}[record["interval"]],
                        received_ms=record["received_ms"],
                        available_ms=durable,
                        durable_ms=durable,
                        observed_now_ms=durable,
                    )
                    value["record"] = verified.model_dump(mode="json")
                    value["prepared_frame"] = frame
                    journal.finalize_receipt(grant, frame, value)
            except Exception as exc:
                journal.settle(grant, frame, "REJECTED", {"reason": str(exc)})
                raise
            if kind == "CLOSE":
                reason = "PEER_CLOSED_NO_RECONNECT"
                break
    except BaseException as exc:
        reason = str(exc) or type(exc).__name__
        failure = type(exc).__name__
    finally:
        for sig, handler in prior.items():
            signal.signal(sig, handler)
        closed, close_error = transport.close()
        if close_error:
            reason = reason + ";TERMINAL_SOCKET_FAILURE:" + close_error
        if reserved:
            try:
                try:
                    closed_ms = clock.sample()["wall_ms"]
                except Exception:
                    closed_ms = None
                report = journal.terminal(grant, reason, closed)
                # Create-only report, fsync before declaring terminal evidence available.
                path = Path(grant.output) / "terminal.json"
                with path.open("xb") as stream:
                    stream.write(
                        canonical(
                            {
                                **report,
                                "usage": journal.usage(grant.session_id),
                                "tls": transport.tls,
                                "failure_type": failure,
                                "native_market_requests": transport.connection_attempts
                                if grant.exposure == "NATIVE_UNQUALIFIED"
                                else 0,
                                "independent_capture_audit": "PENDING",
                                "clock_failure_evidence": clock.failure_evidence,
                                "closed_ms": closed_ms,
                            }
                        )
                    )
                    stream.flush()
                    os.fsync(stream.fileno())
                journal.sync_parent()
            except Exception as exc:
                raise Stop("FAILED_DURABLE_TERMINAL_CLOSURE:" + str(exc)) from exc
    require(report is not None, "RESERVATION_FAILED_OR_ALREADY_CONSUMED:" + reason)
    assert report is not None
    report["journal"] = journal.verify()
    report["tls_connections"] = len(transport.tls)
    return report


def run_native(grant_path, audit_path, config_path, wheel, registry, host_admission=None):
    # Trust is frozen in the installed source, never accepted from a CLI flag.
    roots_path = Path(__file__).parent / "authority_roots.json"
    roots = strict(roots_path.read_bytes())
    require(bool(roots.get("owner")) and bool(roots.get("auditor")), "INDEPENDENT_TRUST_REQUIRED")
    envelope = Envelope.model_validate(strict(Path(grant_path).read_bytes()))
    audit = AuditEnvelope.model_validate(strict(Path(audit_path).read_bytes()))
    policy = Policy.model_validate(strict(Path(config_path).read_bytes()))
    from ..qualification.admission import HostEnvelope, verify_host

    require(host_admission is not None, "HOST_CLOCK_UNQUALIFIED")
    host = HostEnvelope.model_validate(strict(Path(host_admission).read_bytes()))
    verify_host(host, roots, envelope.grant, Clock().sample()["wall_ms"])
    executable = Path(wheel)
    g = authorize(
        envelope,
        audit,
        roots,
        policy,
        source_hash=source_hash(),
        executable_hash=hashlib.sha256(executable.read_bytes()).hexdigest(),
        now_ms=Clock().sample()["wall_ms"],
        exposure="NATIVE_UNQUALIFIED",
    )
    # Verify the supplied built executable actually contains these installed Python bytes.
    import zipfile

    package = Path(__file__).resolve().parents[2]
    with zipfile.ZipFile(executable) as archive:
        for p in package.rglob("*"):
            if p.is_file() and p.suffix in {".py", ".json", ".yaml", ".jsonl"}:
                require(
                    archive.read("btc_quant_agent/" + str(p.relative_to(package))) == p.read_bytes(),
                    "INSTALLED_EXECUTABLE_CONTENT_MISMATCH",
                )
    registry = Path(registry)
    require(not any(p.is_symlink() for p in (registry, *registry.parents)), "REGISTRY_PATH_UNTRUSTED")
    import tempfile

    # A different registry must not create a second concurrent native collector.
    with (
        exclusive(Path(tempfile.gettempdir()) / "l4-p0-crossphase.dispatch.lock"),
        exclusive(str(registry) + ".worker.lock"),
    ):
        journal = Journal(registry)
        clock = Clock()
        transport = Transport(policy, g, journal, clock)
        return capture(g, policy, journal, clock, transport)
