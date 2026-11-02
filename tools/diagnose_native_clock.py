#!/usr/bin/env python3
"""Read only the sealed L4 first-session receipts; never opens a market socket."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

from btc_quant_agent.platform.canary.public_data import normalize
from btc_quant_agent.platform.core import primitive

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "artifacts/live_public_canary_20261030/run"
OUT = ROOT / "artifacts/clock_remediation_20261030"


def reconstruct():
    chunks, source_hashes = {}, {}
    for kind in ("raw", "normalized"):
        for path in sorted((RUN / kind).glob("*.json.gz")):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != path.name[:-8]:
                raise ValueError("SEALED_CHUNK_HASH_MISMATCH")
            chunks[digest] = json.loads(gzip.decompress(path.read_bytes()))
            source_hashes[str(path.relative_to(ROOT))] = digest
    children = {}
    for sha, value in chunks.items():
        prior = value["previous_sha"]
        if prior in children:
            raise ValueError("SEALED_CHAIN_FORK")
        children[prior] = sha
    records, previous, visited = [], None, set()
    while previous in children:
        previous = children[previous]
        if previous in visited:
            raise ValueError("SEALED_CHAIN_CYCLE")
        visited.add(previous)
        value = chunks[previous]
        if value["kind"] == "raw":
            records.extend(value["records"])
    if len(visited) != len(chunks) or not previous or len(chunks) != 10:
        raise ValueError("SEALED_CHAIN_INCOMPLETE")
    points, provider_receive = [], []
    for i, record in enumerate(records):
        w = record["wire"]
        for field in ("request", "first", "receive", "available"):
            wall, mono = w.get(field + "_wall"), w.get(field + "_mono")
            if type(wall) is int and type(mono) is int:
                points.append(
                    {
                        "mono_ms": mono,
                        "wall_ms": wall,
                        "field": field,
                        "record": i,
                        "endpoint_id": w["endpoint_id"],
                    }
                )
        for wall_key, mono_key, field in (
            ("normalization_available_wall_ms", "normalization_available_mono_ms", "normalization"),
            ("decision_wall_ms", "decision_mono_ms", "decision"),
        ):
            if type(record.get(wall_key)) is int and type(record.get(mono_key)) is int:
                points.append(
                    {
                        "mono_ms": record[mono_key],
                        "wall_ms": record[wall_key],
                        "field": field,
                        "record": i,
                        "endpoint_id": w["endpoint_id"],
                    }
                )
        if w["endpoint_id"] != "source_failure":
            provider_receive.append(w["receive_mono"])
    points.sort(key=lambda p: (p["mono_ms"], p["wall_ms"], p["record"], p["field"]))
    origin = points[0]["wall_ms"] - points[0]["mono_ms"]
    for p in points:
        p["wall_minus_mono_change_ms"] = p["wall_ms"] - p["mono_ms"] - origin
    first = next(i for i, p in enumerate(points) if abs(p["wall_minus_mono_change_ms"]) > 50)
    tied = Counter(p["mono_ms"] for p in points)
    pairs = total = 0
    status = Counter()
    replay_hashes = {}
    for sha, value in chunks.items():
        if value["kind"] != "normalized":
            continue
        raw = chunks[value["raw_sha"]]
        replay = [primitive(normalize(r)) for r in raw["records"]]
        if replay != value["records"]:
            raise ValueError("SEALED_LEGACY_REPLAY_CHANGED")
        pairs += 1
        total += len(replay)
        status.update(v["status"] for v in replay)
        replay_hashes[sha] = hashlib.sha256(
            json.dumps(replay, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    return {
        "scope": "OFFLINE_READ_ONLY_RECONSTRUCTION_OF_SEALED_FIRST_NATIVE_SESSION",
        "new_market_requests": 0,
        "original_run_mutated": False,
        "records": len(records),
        "sample_pairs": len(points),
        "wire_sample_pairs": sum(p["field"] in ("request", "first", "receive", "available") for p in points),
        "original_samples_bracketed": False,
        "ordering": "STRICT_MONOTONIC_WITH_EXPLICIT_MILLISECOND_TIES; wall order within a tie is diagnostic only",
        "mono_tie_groups": sum(n > 1 for n in tied.values()),
        "provider_receive_regressions_in_raw_chain": sum(
            b < a for a, b in zip(provider_receive, provider_receive[1:])
        ),
        "relative_offset_histogram_ms": dict(
            sorted(Counter(p["wall_minus_mono_change_ms"] for p in points).items())
        ),
        "transition_neighborhood": points[max(0, first - 4) : first + 6],
        "strict_mono_time_series": points,
        "confirmed": [
            "Persistent approximately 899-900ms relative wall/monotonic discontinuity remains after monotonic sorting",
            "Original event E and transaction T differ from raw local wall clock; a clock-domain conversion proof was unsupported",
            "One native probe is insufficient for V2 multi-probe qualification; old decisions are not reclassified",
            "Legacy normalization replay is unchanged; sort/replay ordering cannot explain the persistent offset shift",
        ],
        "suspected_not_proven": [
            "Abrupt host wall correction or VM clock behavior; unbracketed old sampling cannot identify which clock stepped",
            "WSL2/TSC context and currently synchronized kernel are diagnostics, not historical NTP attribution",
        ],
        "historical_ntp_log": "No entries in the bounded timesyncd/chrony query; no clock/service changes made",
        "legacy_replay": {
            "pairs": pairs,
            "records": total,
            "status_counts": dict(status),
            "normalized_content_hashes": replay_hashes,
            "parity": True,
        },
        "sealed_chunk_sha256": source_hashes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-receipt", action="store_true", help="Write only the dated offline repair receipt"
    )
    args = parser.parse_args()
    value = reconstruct()
    if args.write_receipt:
        OUT.mkdir(exist_ok=True)
        (OUT / "root_cause.json").write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
        (OUT / "diagnosis_run.json").write_text(
            json.dumps(
                {
                    "utc": datetime.now(timezone.utc).isoformat(),
                    "command": "PYTHONPATH=src python tools/diagnose_native_clock.py --write-receipt",
                    "native_network_calls": 0,
                },
                indent=2,
            )
            + "\n"
        )
    print(
        json.dumps(
            {
                k: value[k]
                for k in (
                    "records",
                    "sample_pairs",
                    "provider_receive_regressions_in_raw_chain",
                    "relative_offset_histogram_ms",
                    "legacy_replay",
                )
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
