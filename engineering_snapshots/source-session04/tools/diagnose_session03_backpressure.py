"""Offline, read-only audit of the consumed Session03 capture. Never acquires data."""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "artifacts/live_public_canary_flex/session_03_clock_v2"
PHASE = ROOT / "artifacts/session03_native_backpressure_offline_20261101"


def offline_output(path):
    resolved = Path(path).resolve()
    if not (resolved.is_relative_to(PHASE) or resolved.is_relative_to(Path("/tmp"))):
        raise ValueError("OFFLINE_OUTPUT_MUST_BE_IN_DEDICATED_PHASE_OR_TMP")
    return resolved


def offline():
    def blocked(*args, **kwargs):
        raise AssertionError("SESSION03_OFFLINE_NETWORK_FORBIDDEN")

    setattr(socket.socket, "connect", blocked)
    setattr(socket.socket, "connect_ex", blocked)
    setattr(socket.socket, "sendto", blocked)
    socket.getaddrinfo = blocked
    socket.create_connection = blocked

    def deny_network(event, args):
        if event in ("socket.connect", "socket.getaddrinfo", "socket.sendto"):
            raise AssertionError("SESSION03_OFFLINE_NETWORK_FORBIDDEN")

    sys.addaudithook(deny_network)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def records():
    manifest = json.loads((CAPTURE / "replay_manifest.json").read_text())
    for row in manifest["manifest"]:
        if row["kind"] == "raw":
            path = CAPTURE / "raw" / (row["sha256"] + ".json.gz")
            yield from json.loads(gzip.decompress(path.read_bytes()))["records"]


def audit():
    # Normalization is pure; no journal/store constructors are called on the sealed root.
    from base64 import b64decode
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from btc_quant_agent.platform.canary.public_data import normalize
    from btc_quant_agent.platform.core import primitive

    before = {str(p.relative_to(CAPTURE)): sha(p) for p in sorted(CAPTURE.rglob("*")) if p.is_file()}
    seal = json.loads((CAPTURE / "receipt_seal.json").read_text())
    assert all(before[name] == digest for name, digest in seal.items()), "SEAL_MISMATCH"
    envelope = json.loads((CAPTURE / "owner_signed_grant.json").read_text())
    keys = json.loads((ROOT / "configs/canary/session03_owner_keys.json").read_text())["keys"]
    key = keys[envelope["key_id"]]
    public = b64decode(key["public_key_base64"], validate=True)
    assert hashlib.sha256(public).hexdigest() == key["public_key_sha256"]
    body = envelope["grant"]
    signed = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    Ed25519PublicKey.from_public_bytes(public).verify(b64decode(envelope["signature_base64"], validate=True), signed)
    assert key["verified_owner_reference"] == body["authorization_reference"]
    assert key["session_id"] == body["session_id"]
    for field in ("launch_window_start_utc_ms", "launch_window_end_utc_ms"):
        assert key[field] == body[field]
    source = json.loads((CAPTURE / "source_sha256.json").read_text())
    assert hashlib.sha256(canonical(source)).hexdigest() == body["source_sha256_fingerprint"]
    source_changes = {name: sha(ROOT / name) for name, digest in source.items() if sha(ROOT / name) != digest}
    manifest = json.loads((CAPTURE / "replay_manifest.json").read_text())
    report = json.loads((CAPTURE / "report.json").read_text())
    assert report["replay"] == manifest
    assert report["status"] == "PARTIAL" and report["stop_reason"] == "BACKPRESSURE_BLOCKED"
    assert not any(report[key] for key in ("safe_terminal_evidence", "source_qualified", "shadow_advisory_qualified", "economically_validated"))
    scope_hash = hashlib.sha256(canonical(body)).hexdigest()
    assert scope_hash == report["scope_hash"]
    assert report["flex_window_contract"]["source_fingerprint"] == body["source_sha256_fingerprint"]
    previous, pairs, total = None, 0, 0
    raw_chunks = {}
    rates: dict[int, Counter[int]] = {width: Counter() for width in (10, 100, 1000)}
    delays, receiver_parse, available_decision, raw_commits, pair_commits = [], [], [], [], []
    receive_times = []
    endpoints: Counter[str] = Counter()
    raw_clock_missing: Counter[str] = Counter()
    started = time.perf_counter()
    for row in manifest["manifest"]:
        path = CAPTURE / row["kind"] / (row["sha256"] + ".json.gz")
        assert sha(path) == row["sha256"] and path.stat().st_size == row["bytes"]
        value = json.loads(gzip.decompress(path.read_bytes()))
        assert row["previous_sha256"] == value["previous_sha"] == previous
        assert value["kind"] == row["kind"] and value["raw_sha"] == row["raw_sha"]
        for field in ("start_ms", "end_ms", "expires_ms"):
            assert row[field] == value[field]
        previous = row["sha256"]
        if row["kind"] == "raw":
            raw_chunks[row["sha256"]] = value["records"]
            for record in value["records"]:
                endpoints[record["wire"]["endpoint_id"]] += 1
                if record["wire"]["stream"]:
                    received = record["wire"]["receive_mono"]
                    receive_times.append(received)
                    receiver_parse.append(record["wire"]["available_mono"] - received)
                    available_decision.append(record["decision_mono_ms"] - record["wire"]["available_mono"])
                    for width in rates:
                        rates[width][received // width] += 1
                    delays.append(record["decision_mono_ms"] - received)
                    for field in ("request_wall", "request_mono", "first_wall", "first_mono"):
                        raw_clock_missing[field] += record["wire"].get(field) is None
        else:
            original = raw_chunks[row["raw_sha"]]
            assert canonical([primitive(normalize(r)) for r in original]) == canonical(value["records"])
            pairs += 1
            total += len(original)
            raw_row = next(r for r in manifest["manifest"] if r["sha256"] == row["raw_sha"])
            raw_commits.append(raw_row["commit_observed_ms"] - raw_row["end_ms"])
            pair_commits.append(row["commit_observed_ms"] - raw_row["commit_observed_ms"])
    with sqlite3.connect((CAPTURE / "state.sqlite").as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        circuit = json.loads(db.execute("SELECT value FROM canary_values WHERE key='circuit'").fetchone()[0])
        budgets = db.execute("SELECT scope,count(*),sum(amount) FROM canary_budget GROUP BY scope").fetchall()
        db_manifest = db.execute("SELECT sha,previous_sha,kind,raw_sha FROM public_chunks ORDER BY ordinal").fetchall()
        assert db_manifest == [(r["sha256"], r["previous_sha256"], r["kind"], r["raw_sha"]) for r in manifest["manifest"]]
        query_plan = db.execute("EXPLAIN QUERY PLAN DELETE FROM canary_budget WHERE mono_ms<?", (0,)).fetchall()
        journal_mode = db.execute("PRAGMA journal_mode").fetchone()[0]
    assert before == {str(p.relative_to(CAPTURE)): sha(p) for p in sorted(CAPTURE.rglob("*")) if p.is_file()}
    delays.sort()
    def distribution(values):
        values = sorted(values)
        return {"min": min(values), "p50": values[len(values)//2], "p99": values[int(len(values)*.99)], "max": max(values)}

    peaks = {}
    for width in (10, 100, 1000):
        left, peak = 0, 0
        for right, received in enumerate(receive_times):
            while receive_times[left] <= received - width:
                left += 1
            peak = max(peak, right - left + 1)
        peaks[str(width)] = peak
    return {
        "mode": "OFFLINE_READ_ONLY_CONSUMED_CAPTURE_AUDIT", "native_requests": 0,
        "capture_files_sha256": before, "sealed_files_verified": len(seal),
        "owner_signature": "Ed25519 independently reconstructed canonical bytes VERIFIED",
        "signed_source_fingerprint": body["source_sha256_fingerprint"], "source_files": len(source),
        "current_source_differences": source_changes, "capture_unchanged": True,
        "replay": {"pairs": pairs, "records": total, "status": "PARITY_VERIFIED", "seconds": time.perf_counter() - started},
        "endpoints": dict(endpoints), "circuit": circuit, "budgets": budgets,
        "queue_limit": 128, "trigger": "BudgetGuard.data_message pending >= 128 (persisted circuit)",
        "aligned_receive_bin_peak_counts": {str(k): max(v.values()) for k, v in rates.items()},
        "rolling_receive_window_peak_counts": peaks,
        "ws_receive_span_ms": receive_times[-1] - receive_times[0],
        "ws_observed_receive_rate_per_second": len(receive_times) * 1000 / (receive_times[-1] - receive_times[0]),
        "receiver_parse_to_available_ms": distribution(receiver_parse),
        "available_to_decision_including_queue_and_normalizer_ms": distribution(available_decision),
        "last_receive_to_raw_commit_ms_not_fsync_duration": distribution(raw_commits),
        "raw_to_normalized_commit_ms_not_full_pair_duration": distribution(pair_commits),
        "receiver_to_decision_ms": {"min": min(delays), "p50": delays[len(delays)//2], "p99": delays[int(len(delays)*.99)], "max": max(delays)},
        "unknown_ws_clocks_preserved": dict(raw_clock_missing), "sqlite_journal_mode": journal_mode,
        "budget_delete_query_plan": query_plan,
        "historical_stage_cpu_fs_scheduler_timings": "UNKNOWN; absent in original capture",
    }


def main():
    offline()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = offline_output(args.output)
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "capture_files_sha256"}, indent=2))


if __name__ == "__main__":
    main()
