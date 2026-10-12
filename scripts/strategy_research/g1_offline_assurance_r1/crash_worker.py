"""Subprocess worker for native os._exit(91) crash-recovery tests under own scratch."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import scripts.g1_offline_preview_r1.__main__ as preview_main
import scripts.g1_offline_preview_r1.storage as preview_storage
from scripts.g1_offline_preview_r1.model import SafetyViolation, canonical, digest, initial_state
from scripts.g1_offline_preview_r1.storage import Engine
from scripts.strategy_research.g1_offline_assurance_r1 import OWN_SCRATCH
from scripts.strategy_research.g1_offline_assurance_r1.oracle import (
    make_analysis,
    make_bar,
    make_event,
    make_proposal,
    make_token,
)

# Checkpoints for the 24h fixture native process-kill battery:
# 15 original checkpoints + 7 novel offsets = 22 checkpoints.
PROCESS_CRASH_CHECKPOINTS: tuple[tuple[str, str, int, str, bool], ...] = (
    # Original 15 checkpoints (is_novel=False)
    ("proposal_pre", "PROPOSE", 0, "before_append", False),
    ("proposal_appended", "PROPOSE", 0, "after_append", False),
    ("analysis_fsynced", "ANALYZE", 0, "after_fsync", False),
    ("approval_snapshotted", "APPROVE", 0, "after_snapshot", False),
    ("place_pre", "PLACE", 0, "before_append", False),
    ("entry_appended", "FILL_ENTRY", 0, "after_append", False),
    ("entry_ack_fsynced", "ACK", 0, "after_fsync", False),
    ("funding_appended", "FUNDING", 0, "after_append", False),
    ("tp1_snapshotted", "TP1", 0, "after_snapshot", False),
    ("partial_ack_fsynced", "ACK", 1, "after_fsync", False),
    ("stop_update_appended", "UPDATE_STOP", 0, "after_append", False),
    ("funding_snapshotted", "FUNDING", 1, "after_snapshot", False),
    ("stop_pre", "STOP", 0, "before_append", False),
    ("final_ack_snapshotted", "ACK", 2, "after_snapshot", False),
    ("outbox_delivered", "OUTBOX", 0, "after_outbox_delivery", False),
    # 7 Novel checkpoints (is_novel=True)
    ("approve_pre_novel", "APPROVE", 0, "before_append", True),
    ("place_fsynced_novel", "PLACE", 0, "after_fsync", True),
    ("entry_snapshotted_novel", "FILL_ENTRY", 0, "after_snapshot", True),
    ("tp1_pre_novel", "TP1", 0, "before_append", True),
    ("stop_update_fsynced_novel", "UPDATE_STOP", 0, "after_fsync", True),
    ("funding3_fsynced_novel", "FUNDING", 2, "after_fsync", True),
    ("stop_appended_novel", "STOP", 0, "after_append", True),
)


def build_dual_pending_ack_scenario() -> tuple[dict, list[dict]]:
    """Construct a deterministic scenario with two simultaneous pending exit ACKs."""
    b0 = make_bar(0, last_open="100", last_high="101", last_low="99", last_close="100")
    prop = make_proposal(digest(b0), side="LONG", quantity="0.02")
    tok = make_token(prop)
    analysis = make_analysis(prop)
    order_id = digest([digest(prop), "SIMULATED_ENTRY"])

    b1 = make_bar(60000, last_open="100", last_high="101", last_low="99", last_close="100")
    b2 = make_bar(120000, last_open="105", last_high="106", last_low="104", last_close="105")
    b3 = make_bar(180000, last_open="94", last_high="95", last_low="93", last_close="94")
    b4 = make_bar(240000, last_open="94", last_high="95", last_low="93", last_close="94")

    events = [
        make_event("BAR", 59999, b0, "BAR-0"),
        make_event("PROPOSE", 60000, prop, "PROPOSE-60000"),
        make_event("ANALYZE", 60001, analysis, "ANALYZE-60001"),
        make_event("APPROVE", 60002, {"token_id": tok["token_id"]}, "APPROVE-60002"),
        make_event("PLACE", 60003, {}, "PLACE-60003"),
        make_event("FILL_ENTRY", 60004, {"fill_id": "entry-1"}, "FILL_ENTRY-60004"),
        make_event("BAR", 119999, b1, "BAR-1"),
        make_event(
            "ACK",
            120004,
            {"ack_id": "ack-entry-1", "order_id": order_id, "fill_id": "entry-1"},
            "ACK-120004",
        ),
        make_event("BAR", 179999, b2, "BAR-2"),
        make_event("TP1", 179999, {"fill_id": "tp1-half"}, "TP1-179999"),
        make_event("BAR", 239999, b3, "BAR-3"),
        make_event("STOP", 239999, {"fill_id": "stop-rem"}, "STOP-239999"),
        make_event("BAR", 299999, b4, "BAR-4"),
        make_event(
            "ACK",
            300000,
            {"ack_id": "ack-stop-rem", "order_id": order_id, "fill_id": "stop-rem"},
            "ACK-FIRST-PENDING",
        ),
        make_event(
            "ACK",
            300001,
            {"ack_id": "ack-tp1-half", "order_id": order_id, "fill_id": "tp1-half"},
            "ACK-SECOND-PENDING",
        ),
    ]
    init = initial_state([tok])
    init["fixture_identity"] = "dual-pending-ack-v1"
    return init, events


def run_dual_pending_ack(
    output: Path, crash_event: str | None = None, crash_edge: str | None = None
) -> int:
    """Execute the dual-pending-exit-ACK workflow with optional os._exit(91) crash hook."""
    init, events = build_dual_pending_ack_scenario()

    def crash(edge: str, event: dict) -> None:
        if edge == crash_edge and event["id"] == crash_event:
            os._exit(91)

    try:
        with Engine(output, init, temporary=True) as engine:
            for ev in events:
                engine.apply(ev, hook=crash)
            engine.checkpoint()
            engine.deliver(hook=crash)
            receipt = engine.receipt()
            (output / "RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n")
            print(canonical(receipt))
        return 0
    except (SafetyViolation, OSError, UnicodeError) as exc:
        code = exc.code if isinstance(exc, SafetyViolation) else "OFFLINE_IO_ERROR"
        print(canonical({"status": "G1_OFFLINE_PREVIEW_FAIL_CLOSED", "code": code}))
        return 3


def main(argv: list[str] | None = None) -> int:
    """Dispatch either standard preview CLI (scoped to OWN_SCRATCH) or dual_pending_ack."""
    OWN_SCRATCH.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Scope preview storage scratch path strictly to our own task scratch directory
    preview_storage.OWN_SCRATCH = OWN_SCRATCH
    preview_main.OWN_SCRATCH = OWN_SCRATCH

    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == "--mode=dual_pending_ack":
        parser = argparse.ArgumentParser()
        parser.add_argument("--mode")
        parser.add_argument("--output", required=True)
        parser.add_argument("--crash-event")
        parser.add_argument("--crash-edge")
        parsed = parser.parse_args(args_list)
        return run_dual_pending_ack(
            Path(parsed.output),
            crash_event=parsed.crash_event,
            crash_edge=parsed.crash_edge,
        )
    return int(preview_main.main(args_list))


if __name__ == "__main__":
    raise SystemExit(main())
