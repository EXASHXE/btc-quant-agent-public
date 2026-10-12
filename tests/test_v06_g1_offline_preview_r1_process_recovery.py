"""Real process-kill and restart witnesses for the offline JSON WAL CLI."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "scripts/g1_offline_preview_r1/fixtures"
SCRATCH = Path("/tmp/btc-g1_offline_preview_r1")
SCRATCH.mkdir(mode=0o700, parents=True, exist_ok=True)
RUN_ROOT = Path(tempfile.mkdtemp(prefix="process-recovery-run-", dir=SCRATCH))
ZERO_COUNTERS = {
    "false_approvals_accepted": 0,
    "actual_private_or_network_calls": 0,
    "duplicate_cash_charges": 0,
    "oversize_exposure": 0,
    "phantom_spendable_ack": 0,
}

# One kill per case. The same fixed event IDs exist in both side fixtures.
CASES = (
    ("proposal_pre", "PROPOSE", 0, "before_append"),
    ("proposal_appended", "PROPOSE", 0, "after_append"),
    ("analysis_fsynced", "ANALYZE", 0, "after_fsync"),
    ("approval_snapshotted", "APPROVE", 0, "after_snapshot"),
    ("place_pre", "PLACE", 0, "before_append"),
    ("entry_appended", "FILL_ENTRY", 0, "after_append"),
    ("entry_ack_fsynced", "ACK", 0, "after_fsync"),
    ("funding_appended", "FUNDING", 0, "after_append"),
    ("tp1_snapshotted", "TP1", 0, "after_snapshot"),
    ("partial_ack_fsynced", "ACK", 1, "after_fsync"),
    ("stop_update_appended", "UPDATE_STOP", 0, "after_append"),
    ("funding_snapshotted", "FUNDING", 1, "after_snapshot"),
    ("stop_pre", "STOP", 0, "before_append"),
    ("final_ack_snapshotted", "ACK", 2, "after_snapshot"),
    ("outbox_delivered", "OUTBOX", 0, "after_outbox_delivery"),
)


def _directory(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix, dir=RUN_ROOT))


def _cli(fixture: str, output: Path, *, crash_event: str | None = None,
         edge: str | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "scripts.g1_offline_preview_r1", "--fixture", fixture,
           "--output", str(output)]
    if crash_event is not None:
        cmd.extend(("--crash-event", crash_event, "--crash-edge", str(edge)))
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120,
                          check=False)


def _fixture_events(fixture: str) -> list[dict]:
    return json.loads((FIXTURES / fixture).read_text())["events"]


def _event_id(fixture: str, kind: str, occurrence: int) -> str:
    if kind == "OUTBOX":
        return "OUTBOX"
    matches = [e["id"] for e in _fixture_events(fixture) if e["kind"] == kind]
    assert len(matches) > occurrence, (fixture, kind, occurrence)
    return matches[occurrence]


def _receipt(output: Path) -> dict:
    return json.loads((output / "RECEIPT.json").read_text())


def _delivery_keys(output: Path) -> list[str]:
    return [json.loads(row)["key"] for row in
            (output / "outbox_delivery.jsonl").read_text().splitlines()]


def _checkpoints(output: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (output / "checkpoints").glob("checkpoint-*.json")}


def _terminal_checkpoint(output: Path, event_count: int) -> Path | None:
    matches = list((output / "checkpoints").glob(f"checkpoint-{event_count:08d}-*.json"))
    assert len(matches) <= 1
    return matches[0] if matches else None


@pytest.fixture(scope="module", params=("long_24h.json", "short_24h.json"))
def reference(request: pytest.FixtureRequest) -> tuple[str, Path, dict]:
    fixture = request.param
    output = _directory(f"process-reference-{fixture.split('_')[0]}-")
    run = _cli(fixture, output)
    assert run.returncode == 0, (fixture, run.stdout[-1000:], run.stderr[-1000:])
    receipt = _receipt(output)
    assert receipt["status"] == "G1_OFFLINE_PREVIEW_VERIFIED"
    assert receipt["counters"] == ZERO_COUNTERS
    assert receipt["logical_event_count"] == len(_fixture_events(fixture))
    assert len(set(_delivery_keys(output))) == len(_delivery_keys(output))
    return fixture, output, receipt


@pytest.mark.parametrize(("case", "kind", "occurrence", "edge"), CASES,
                         ids=[row[0] for row in CASES])
def test_process_kill_then_restart_matches_reference(
    reference: tuple[str, Path, dict], case: str, kind: str, occurrence: int, edge: str,
) -> None:
    fixture, ref_output, expected = reference
    output = _directory(f"process-{fixture.split('_')[0]}-{case}-")
    event_id = _event_id(fixture, kind, occurrence)
    killed = _cli(fixture, output, crash_event=event_id, edge=edge)
    assert killed.returncode == 91, (fixture, case, killed.stdout[-1000:], killed.stderr[-1000:])
    resumed = _cli(fixture, output)
    assert resumed.returncode == 0, (fixture, case, resumed.stdout[-1000:], resumed.stderr[-1000:])
    actual = _receipt(output)
    for key in ("status", "safety_status", "fixture_sha256", "logical_event_count",
                "state_hash", "wal_chain", "journal_hash", "journal_effects", "cash",
                "available_cash", "reserved_notional", "phase", "pending_cash", "counters"):
        assert actual[key] == expected[key], (fixture, case, key)
    assert actual["counters"] == ZERO_COUNTERS
    # A delivery killed after fsync can be replayed physically. Its idempotency key
    # and the financial state remain identical to the uninterrupted execution.
    physical = _delivery_keys(output)
    assert set(physical) == set(_delivery_keys(ref_output))
    assert len(physical) >= len(set(physical))
    # The terminal snapshot is required; a crash after fsync may skip only an
    # earlier intermediate snapshot, because replayed WAL events are idempotent.
    ref_terminal = _terminal_checkpoint(ref_output, expected["logical_event_count"])
    if ref_terminal is None:
        rerun = _cli(fixture, ref_output)
        assert rerun.returncode == 0, (fixture, rerun.stdout[-1000:])
        ref_terminal = _terminal_checkpoint(ref_output, expected["logical_event_count"])
    actual_terminal = _terminal_checkpoint(output, actual["logical_event_count"])
    assert ref_terminal is not None and actual_terminal is not None
    assert json.loads(actual_terminal.read_text())["seq"] == actual["logical_event_count"]
    terminal_sha = hashlib.sha256(actual_terminal.read_bytes()).hexdigest()
    assert terminal_sha == hashlib.sha256(ref_terminal.read_bytes()).hexdigest()
    reference_checkpoints = _checkpoints(ref_output)
    resumed_checkpoints = _checkpoints(output)
    common = reference_checkpoints.keys() & resumed_checkpoints.keys()
    assert common
    assert all(reference_checkpoints[name] == resumed_checkpoints[name] for name in common)
    proof = {"fixture": fixture, "case": case, "event_id": event_id, "edge": edge,
             "crash_exit": killed.returncode, "restart_exit": resumed.returncode,
             "state_hash": actual["state_hash"], "wal_chain": actual["wal_chain"],
             "journal_hash": actual["journal_hash"], "cash": actual["cash"],
             "financial_counters": actual["counters"],
             "physical_outbox_deliveries": len(physical),
             "unique_outbox_keys": len(set(physical)),
             "terminal_checkpoint_sha256": terminal_sha,
             "common_checkpoint_count": len(common),
             "reference_state_hash": expected["state_hash"]}
    (output / "RECOVERY_PROOF.json").write_text(json.dumps(proof, sort_keys=True, indent=2) + "\n")


@pytest.mark.parametrize("fixture", ("long_24h.json", "short_24h.json"))
def test_truncated_wal_quarantines_and_fails_closed(fixture: str) -> None:
    output = _directory(f"process-truncated-{fixture.split('_')[0]}-")
    killed = _cli(fixture, output, crash_event=_event_id(fixture, "PROPOSE", 0),
                  edge="after_append")
    assert killed.returncode == 91
    wal = output / "events.wal.jsonl"
    raw = wal.read_bytes()
    assert raw.endswith(b"\n") and len(raw) > 100
    wal.write_bytes(raw[:-1])
    resumed = _cli(fixture, output)
    assert resumed.returncode == 3
    failure = json.loads(resumed.stdout.strip())
    assert failure["status"] == "G1_OFFLINE_PREVIEW_FAIL_CLOSED"
    assert failure["code"] == "WAL_TRUNCATED"
    assert not (output / "RECEIPT.json").exists()
    quarantine = list((output / "quarantine").glob("*.json"))
    assert len(quarantine) == 1
    details = json.loads(quarantine[0].read_text())
    assert details["code"] == "WAL_TRUNCATED"
    assert details["unsafe_effects_replayed"] is False
    proof = {"fixture": fixture, "crash_exit": killed.returncode,
             "restart_exit": resumed.returncode, "failure_code": failure["code"],
             "quarantine_receipt": quarantine[0].name,
             "unsafe_effects_replayed": details["unsafe_effects_replayed"]}
    (output / "TRUNCATION_PROOF.json").write_text(json.dumps(proof, sort_keys=True, indent=2) + "\n")
