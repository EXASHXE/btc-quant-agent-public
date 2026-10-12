"""Single-process JSON WAL, fsync boundaries and immutable hash checkpoints."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .model import SafetyViolation, canonical, decimal, digest, redact_text
from .reducer import transition

OWN_SCRATCH = Path("/tmp/btc-g1_offline_preview_r1")
MAX_WAL_BYTES = 32 * 1024 * 1024


def strict_json(raw: str) -> Any:
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise SafetyViolation("JSON_DUPLICATE_KEY")
            obj[key] = value
        return obj

    def bad(_):
        raise SafetyViolation("JSON_NONFINITE")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)
    except (json.JSONDecodeError, UnicodeError, RecursionError) as exc:
        raise SafetyViolation("JSON_MALFORMED") from exc


def guard_directory(path: Path, *, temporary=False):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise SafetyViolation("PATH_SCOPE")
    base = Path("/tmp") if temporary else OWN_SCRATCH
    if path != base and base not in path.parents:
        raise SafetyViolation("PATH_SCOPE")
    for p in [base, *reversed([p for p in path.parents if p != base and base in p.parents]), path]:
        if p.is_symlink():
            raise SafetyViolation("PATH_SYMLINK")
    return path


def _file(path):
    if path.is_symlink():
        raise SafetyViolation("PATH_SYMLINK")
    return path


def _directory_sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Engine:
    """No external ports. Recovery replays every committed record independently.

    Complete valid records surviving process death before fsync may be replayed.
    Partial lines/corrupt hashes/a checkpoint ahead of WAL always quarantine and
    stop. This proves process-crash behavior, not power-loss filesystem fidelity.
    """

    def __init__(self, path, initial, *, temporary=False):
        self.root = guard_directory(Path(path), temporary=temporary)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock_fd = os.open(
            _file(self.root / "writer.lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
        )
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(self.lock_fd)
            self.lock_fd = None
            raise SafetyViolation("SINGLE_WRITER_LOCKED") from exc
        self.wal = _file(self.root / "events.wal.jsonl")
        self.checkpoints = _file(self.root / "checkpoints")
        self.checkpoints.mkdir(exist_ok=True, mode=0o700)
        self.initial = copy.deepcopy(initial)
        self.state = copy.deepcopy(initial)
        self.seen = {}
        self.seq = 0
        self.chain = digest(initial)
        try:
            if not self.wal.exists():
                fd = os.open(self.wal, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                try:
                    os.write(
                        fd,
                        (
                            canonical({"format": "G1_OFFLINE_WAL_V1", "genesis_hash": self.chain})
                            + "\n"
                        ).encode(),
                    )
                    os.fsync(fd)
                finally:
                    os.close(fd)
                _directory_sync(self.root)
            self._recover()
        except Exception:
            self.close()
            raise

    def close(self):
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def quarantine(self, code):
        folder = _file(self.root / "quarantine")
        folder.mkdir(exist_ok=True, mode=0o700)
        original_size = self.wal.stat().st_size if self.wal.exists() else 0
        if self.wal.exists():
            with self.wal.open("rb") as handle:
                raw = handle.read(MAX_WAL_BYTES + 1)
        else:
            raw = b""
        # Stable, bounded original bytes retained only inside owned directory.
        name = digest({"code": code, "bytes_hash": hashlib.sha256(raw).hexdigest()})
        p = _file(folder / (name + ".wal"))
        if not p.exists():
            p.write_bytes(raw)
        info = _file(folder / (name + ".json"))
        info.write_text(
            canonical(
                {
                    "code": code,
                    "original_bytes": original_size,
                    "retained_bytes": len(raw),
                    "copy_truncated": len(raw) < original_size,
                    "unsafe_effects_replayed": False,
                }
            )
            + "\n"
        )

    def _recover(self):
        try:
            if self.wal.stat().st_size > MAX_WAL_BYTES:
                raise SafetyViolation("WAL_SIZE_BOUND")
            raw = self.wal.read_bytes()
            if not raw.endswith(b"\n"):
                raise SafetyViolation("WAL_TRUNCATED")
            lines = raw.decode("utf-8").splitlines()
            if not lines or strict_json(lines[0]) != {
                "format": "G1_OFFLINE_WAL_V1",
                "genesis_hash": digest(self.initial),
            }:
                raise SafetyViolation("WAL_GENESIS_MISMATCH")
            anchors = {0: (self.chain, digest(self.state), {})}
            for line in lines[1:]:
                rec = strict_json(line)
                if not isinstance(rec, dict) or set(rec) != {
                    "seq",
                    "previous",
                    "event",
                    "event_hash",
                    "state_hash",
                    "record_hash",
                }:
                    raise SafetyViolation("WAL_SCHEMA")
                body = {k: v for k, v in rec.items() if k != "record_hash"}
                if (
                    rec["seq"] != self.seq + 1
                    or rec["previous"] != self.chain
                    or digest(body) != rec["record_hash"]
                ):
                    raise SafetyViolation("WAL_CHAIN")
                e = rec["event"]
                if digest(e) != rec["event_hash"] or e["id"] in self.seen:
                    raise SafetyViolation("WAL_EVENT_IDENTITY")
                new = transition(self.state, e)
                if digest(new) != rec["state_hash"]:
                    raise SafetyViolation("WAL_STATE_IDENTITY")
                self.state = new
                self.seq = rec["seq"]
                self.chain = rec["record_hash"]
                self.seen[e["id"]] = rec["event_hash"]
                # Retain checkpoints only at their declared anchors, avoiding
                # full O(N^2) state copies in recovery.
                anchors[self.seq] = (self.chain, rec["state_hash"], None)
            for p in self.checkpoints.glob("checkpoint-*.json"):
                snap = strict_json(_file(p).read_text())
                if not isinstance(snap, dict) or set(snap) != {
                    "format",
                    "seq",
                    "chain",
                    "state_hash",
                    "state",
                }:
                    raise SafetyViolation("CHECKPOINT_SCHEMA")
                seq = snap["seq"]
                if snap["format"] != "G1_CHECKPOINT_V1" or seq not in anchors:
                    raise SafetyViolation("CHECKPOINT_AHEAD_OF_WAL")
                chain, state_hash, _ = anchors[seq]
                if (
                    snap["chain"] != chain
                    or snap["state_hash"] != state_hash
                    or digest(snap["state"]) != state_hash
                ):
                    raise SafetyViolation("CHECKPOINT_IDENTITY")
        except (SafetyViolation, UnicodeError, OSError, KeyError, TypeError) as exc:
            code = exc.code if isinstance(exc, SafetyViolation) else "WAL_INVALID"
            self.quarantine(code)
            raise SafetyViolation(code) from exc

    def checkpoint(self):
        snap = {
            "format": "G1_CHECKPOINT_V1",
            "seq": self.seq,
            "chain": self.chain,
            "state_hash": digest(self.state),
            "state": self.state,
        }
        body = (canonical(snap) + "\n").encode()
        dest = _file(self.checkpoints / f"checkpoint-{self.seq:08d}-{digest(self.state)[:16]}.json")
        if dest.exists():
            if dest.read_bytes() != body:
                raise SafetyViolation("CHECKPOINT_IMMUTABLE_CONFLICT")
            return
        temp = _file(self.checkpoints / f"pending-{self.seq:08d}.tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        try:
            offset = 0
            while offset < len(body):
                offset += os.write(fd, body[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
        # Single writer owns the name; never overwrite any immutable checkpoint.
        os.link(temp, dest, follow_symlinks=False)
        temp.unlink()
        os.chmod(dest, 0o400)
        _directory_sync(self.checkpoints)

    def apply(self, event, *, hook: Callable[[str, dict], None] | None = None):
        if self.lock_fd is None:
            raise SafetyViolation("ENGINE_CLOSED")
        e = copy.deepcopy(event)
        if (
            isinstance(e, dict)
            and e.get("kind") == "ANALYZE"
            and isinstance(e.get("payload"), dict)
            and isinstance(e["payload"].get("summary"), str)
        ):
            e["payload"]["summary"] = redact_text(e["payload"]["summary"])
        h = digest(e)
        if isinstance(e, dict) and isinstance(e.get("id"), str) and e["id"] in self.seen:
            if self.seen[e["id"]] != h:
                raise SafetyViolation("EVENT_REUSE_DRIFT")
            return "IDEMPOTENT_DUPLICATE"
        new = transition(self.state, e)

        def edge(name):
            if hook:
                hook(name, e)

        edge("before_append")
        body = {
            "seq": self.seq + 1,
            "previous": self.chain,
            "event": e,
            "event_hash": h,
            "state_hash": digest(new),
        }
        record = {**body, "record_hash": digest(body)}
        raw = (canonical(record) + "\n").encode()
        if self.wal.stat().st_size + len(raw) > MAX_WAL_BYTES:
            raise SafetyViolation("WAL_SIZE_BOUND")
        fd = os.open(self.wal, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        try:
            offset = 0
            while offset < len(raw):
                offset += os.write(fd, raw[offset:])
            edge("after_append")
            os.fsync(fd)
            edge("after_fsync")
        finally:
            os.close(fd)
        self.state = new
        self.seq += 1
        self.chain = record["record_hash"]
        self.seen[e["id"]] = h
        if e["kind"] != "BAR" or self.seq % 120 == 0:
            self.checkpoint()
        edge("after_snapshot")
        # Logs are operational artifacts; WAL is the recovery authority.
        log = {
            "seq": self.seq,
            "trace_id": digest([e["id"], e["kind"]])[:24],
            "span_id": digest([e["id"], e["kind"]])[:16],
            "kind": e["kind"],
            "at": e["at"],
            "phase": self.state["phase"],
            "safety": self.state["safety_status"],
        }
        with _file(self.root / "events.log.jsonl").open("a") as f:
            f.write(canonical(log) + "\n")
        return "COMMITTED"

    def deliver(self, *, hook=None):
        """Offline physical delivery is at-least-once; keys permit deduplication."""
        p = _file(self.root / "outbox_delivery.jsonl")
        for message in self.state["outbox"]:
            with p.open("a") as f:
                f.write(
                    canonical(
                        {
                            **message,
                            "span_id": digest([message["key"], "outbox"])[:16],
                            "safety": "DRY_RUN_NO_NETWORK_NO_ORDERING",
                        }
                    )
                    + "\n"
                )
                f.flush()
                os.fsync(f.fileno())
            if hook:
                hook("after_outbox_delivery", {"id": message["key"], "kind": "OUTBOX"})
        return len(self.state["outbox"])

    def receipt(self):
        complete = (
            self.state["phase"] == "CLOSED"
            and not self.state["pending_cash"]
            and decimal(self.state["reserved_notional"]) == 0
        )
        return {
            "status": "G1_OFFLINE_PREVIEW_VERIFIED"
            if complete
            else "G1_OFFLINE_PREVIEW_IN_PROGRESS",
            "safety_status": self.state["safety_status"],
            "health": "SINGLE_WRITER_WAL_VERIFIED",
            "state_hash": digest(self.state),
            "wal_chain": self.chain,
            "logical_event_count": self.seq,
            "journal_hash": digest(self.state["journal"]),
            "journal_effects": len(self.state["journal"]),
            "cash": self.state["cash"],
            "available_cash": self.state["available_cash"],
            "reserved_notional": self.state["reserved_notional"],
            "phase": self.state["phase"],
            "pending_cash": self.state["pending_cash"],
            "required_exit": self.state["required_exit"],
            "retry_classification": "IDENTICAL_EVENT_RETRANSMISSION_ONLY",
            "counters": self.state["counters"],
            "readiness": "OFFLINE_ONLY",
            "network_ports": "NONE",
            "checkpoint_count": len(list(self.checkpoints.glob("checkpoint-*.json"))),
        }
