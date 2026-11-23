"""Reuse F append-only hash journal. Incomplete sessions never admit snapshots."""

import base64
import hashlib
import os
import shutil
import sqlite3

from ..qualification.evidence import Ledger
from ..native.contract import digest, strict
from .models import POLICY, POLICY_HASH, PUBLIC, QA, ensure, path_guard, sample


class Store:
    def __init__(self, directory, *, create=False, exposure=None):
        self.directory = path_guard(directory)
        file = self.directory / "live.sqlite"
        if create:
            ensure(not self.directory.exists(), "LIVE_UNUSED_OUTPUT_REQUIRED")
            ensure(exposure in (PUBLIC, QA), "LIVE_EVIDENCE_CLASS_REQUIRED")
            self.directory.mkdir(parents=True)
        else:
            ensure(file.is_file() and not file.is_symlink(), "LIVE_STORE_NOT_FOUND")
            try:
                with sqlite3.connect("file:" + str(file) + "?mode=ro", uri=True) as db:
                    rows = [strict(v) for (v,) in db.execute("SELECT body FROM evidence WHERE kind='J_MODE'")]
                ensure(len(rows) == 1 and rows[0]["policy_sha256"] == POLICY_HASH, "LIVE_WRONG_STORE_MODE")
            except sqlite3.Error as e:
                raise ValueError("LIVE_WRONG_STORE_MODE") from e
        self.events = Ledger(file)
        if create:
            self.events.append(
                "J_MODE", {"schema": "J_STORE_V1", "policy_sha256": POLICY_HASH, "evidence_class": exposure}
            )
        self.meta = self.events.values("J_MODE")[0]
        self._checked_snapshots = set()
        ensure(exposure is None or exposure == self.meta["evidence_class"], "LIVE_EVIDENCE_CLASS_MIXING")
        self.verify_raw()

    def capacity(self, additional=0):
        size = sum(p.stat().st_size for p in self.directory.rglob("*") if p.is_file())
        ensure(size + additional <= POLICY["store_bytes_max"], "LIVE_STORAGE_BUDGET_EXHAUSTED")
        ensure(
            shutil.disk_usage(self.directory).free >= POLICY["disk_free_bytes_min"] + additional,
            "LIVE_DISK_FULL",
        )

    def persist_response(self, session, ordinal, wire):
        raw = base64.b64decode(wire.pop("body_base64"), validate=True)
        self.capacity(len(raw))
        ensure(hashlib.sha256(raw).hexdigest() == wire["body_sha256"], "LIVE_WIRE_HASH_MISMATCH")
        folder = self.directory / "raw" / session
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (str(ordinal) + ".bin")
        with path.open("xb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        fd = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        durable = sample()
        value = {
            **wire,
            "session": session,
            "ordinal": ordinal,
            "raw_path": path.relative_to(self.directory).as_posix(),
            "durable_sample": durable,
            "source_publication_ms": None,
        }
        self.events.append("HTTP_RESPONSE", value)
        return raw, value

    def verify_raw(self):
        for r in self.events.values("HTTP_RESPONSE"):
            p = path_guard(self.directory / r["raw_path"])
            ensure(
                p.is_relative_to(self.directory)
                and p.is_file()
                and hashlib.sha256(p.read_bytes()).hexdigest() == r["body_sha256"],
                "LIVE_RAW_LINEAGE_TAMPER",
            )

    def snapshots(self):
        terminals = {r["session"]: r for r in self.events.values("SESSION_TERMINAL")}
        out = []
        for r in self.events.values("SNAPSHOT"):
            t = terminals.get(r["session"], {})
            if t.get("status") == "COMPLETE" and t.get("snapshot_sha256") == digest(r):
                out.append(r)
        self.verify_normalized(out)
        return out

    def verify_normalized(self, snapshots):
        """Rebuild normalized rows from the recorded HTTPS bodies, never trust a cache label."""
        from .source import metadata, parse_rows, reference

        pending = [s for s in snapshots if digest(s) not in self._checked_snapshots]
        if not pending:
            return
        responses = self.events.values("HTTP_RESPONSE")
        by_hash = {r["body_sha256"]: r for r in responses}
        by_request = {(r["session"], r["ordinal"]): r for r in responses}
        origins = {s["session"]: s for s in snapshots}
        bodies, parsed = {}, {}

        def body(wire):
            key = wire["raw_path"]
            if key not in bodies:
                raw = (self.directory / key).read_bytes()
                ensure(hashlib.sha256(raw).hexdigest() == wire["body_sha256"], "LIVE_RAW_LINEAGE_TAMPER")
                wrapper = strict(b'{"response":' + raw + b"}")
                ensure(set(wrapper) == {"response"}, "LIVE_RAW_JSON_LINEAGE")
                bodies[key] = wrapper["response"]
            return bodies[key]

        for s in pending:
            ensure(s["exposure"] == self.meta["evidence_class"], "LIVE_SNAPSHOT_EXPOSURE_TAMPER")
            ensure(
                metadata(body(by_hash[s["metadata_response_sha256"]])) == s["instruments"],
                "LIVE_METADATA_LINEAGE_TAMPER",
            )
            refs = [by_hash[h] for h in s["reference"]["time_response_sha256"]]
            ensure(reference(*[(body(w), w) for w in refs]) == s["reference"], "LIVE_TIME_LINEAGE_TAMPER")
            for row in s["records"]:
                key = (row["session"], row["ordinal"])
                if key not in parsed:
                    wire = by_request[key]
                    origin = origins[row["session"]]
                    ref = origin["reference"]
                    first = by_hash[ref["time_response_sha256"][0]]
                    lower = (
                        body(first)["serverTime"]
                        - (
                            first["receive_sample"]["mono_after_ms"]
                            - first["request_sample"]["mono_before_ms"]
                        )
                        - 1
                    )
                    params = wire["params"]
                    values, _ = parse_rows(
                        body(wire),
                        params["symbol"],
                        {"1d": "1D", "4h": "4H", "1h": "1H"}[params["interval"]],
                        start=params["startTime"],
                        end=params["endTime"] + 1,
                        source_lower=lower,
                        grace_ms=origin["grace_ms"],
                        wire=wire,
                        ref=ref,
                        exposure=origin["exposure"],
                    )
                    parsed[key] = {v["identity"]: v for v in values}
                ensure(parsed[key].get(row["identity"]) == row, "LIVE_NORMALIZED_RAW_LINEAGE_TAMPER")
            self._checked_snapshots.add(digest(s))

    def records(self):
        seen: dict[str, dict] = {}
        for s in self.snapshots():
            for r in s["records"]:
                old = seen.get(r["identity"])
                ensure(old is None or old["content_sha256"] == r["content_sha256"], "LIVE_COMMITTED_REVISION")
                seen.setdefault(r["identity"], r)
        return list(seen.values())

    def recover(self):
        done = {s["session"] for s in self.events.values("SESSION_TERMINAL")}
        abandoned = []
        for s in self.events.values("SESSION_START"):
            if s["session"] not in done:
                self.events.append(
                    "SESSION_TERMINAL",
                    {"session": s["session"], "status": "FAILED_CRASH", "reason": "NO_TERMINAL_NO_ADMISSION"},
                )
                abandoned.append(s["session"])
        return abandoned
