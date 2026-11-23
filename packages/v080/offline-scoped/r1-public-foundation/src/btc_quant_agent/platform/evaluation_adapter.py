"""D adapter: frozen B schema, verified durable producer, unchanged C economics.

No ordered post-review execution path is present in a B export. It remains empty
in C; the producer outcome is descriptive and cannot establish an executed return.
"""
from __future__ import annotations

from pathlib import Path

from program_c.integrity import digest, fresh_directory, parse, read_input, sha, write_json
from program_c.protocol import load_protocol
from program_c.reporting import evaluate
from program_c.validation import adapt_b

from .program_c_export import build_export, validate_export
from .rc_store import RCStore


def evaluate_export(input_path: Path, output: Path):
    raw = read_input(input_path)
    value = parse(raw)
    validate_export(value)
    # Bind export to the complete verified append-only ledger, not a mutable label.
    store = RCStore(input_path.parent / "state.sqlite", readonly=True)
    if build_export(store) != value:
        raise ValueError("D_EXPORT_DURABLE_LINEAGE_MISMATCH")
    protocol = load_protocol()
    rows = []
    for row in value["rows"]:
        adapted = adapt_b({**value, "rows": [row]}, protocol)["episodes"][0]
        if adapted["coverage_end_ms"] is None:
            adapted["coverage_end_ms"] = row["decision_ms"]
        rows.append(adapted)
    asof = max([d.decision_ms for d in store.decisions()] +
               [o["asof_ms"] for o in store.observations()], default=1)
    envelope = {"schema_version": "C_SOURCE_NEUTRAL_EPISODE_EXPORT_V1",
                "origin_schema": value["schema_version"], "protocol_sha256": protocol["protocol_sha256"],
                "source_kind": "SOURCE_SYNTHETIC", "evaluation_asof_ms": asof,
                "episodes": rows, "control_pool": [],
                "no_setup_decision_count": value["no_setup_decision_count"],
                "input_export_sha256": value["export_sha256"]}
    directory = fresh_directory(output)
    evaluate(envelope, protocol, directory, raw)
    report = directory / "scientific_report.md"
    with report.open("a", encoding="utf-8") as stream:
        stream.write("\nProducer market-side labels (not executed returns): " +
                     ", ".join(str(row["observation_outcome"]) for row in value["rows"]) +
                     ". C independently classifies the missing ordered post-review path.\n")
    write_json(directory / "D_adapter_lineage.json", {
        "schema": "D_B_TO_C_ADAPTER_V1", "durable_store_verified": True,
        "input_sha256": sha(raw), "export_sha256": value["export_sha256"],
        "adapted_sha256": digest(envelope), "protocol_sha256": protocol["protocol_sha256"],
        "ordered_execution_path": "MISSING", "native_economic_observations": 0,
        "producer_outcome_is_economic_evidence": False})
    return {"status": "OFFLINE_EVALUATED", "scientific_decision": "INSUFFICIENT_SUPPORT",
            "output": str(directory), "native_economic_observations": 0}
