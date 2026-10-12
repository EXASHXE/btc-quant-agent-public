"""CLI entrypoint for G1/G3 offline/loopback ports sidecar integration.

Usage:
  python -m scripts.g1g3_offline_ports_r1 --side LONG --output /tmp/btc-g1g3_offline_ports_r1/run-long [--allow-loopback]
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from scripts.g1_offline_preview_r1.model import SafetyViolation, canonical

from .durable_supervisor import DurableSidecarSupervisor
from .no_order_port import OWN_SCRATCH, guard_scratch_dir

VALID_CRASH_BOUNDARIES = [
    "after_operator_receipt_fsync",
    "before_approve",
    "after_approve_before_place",
    "after_place_before_entry",
    "after_simulated_entry",
    "after_feishu_ack",
    "after_tp1_before_ack",
    "at_stop_before_snapshot",
    "at_stop_after_snapshot",
    "double_pending_ack",
]


class SafeArgumentParser(argparse.ArgumentParser):
    """Rejected CLI arguments are never echoed into stderr/stdout to prevent secret reflection."""

    def error(self, message: str) -> None:
        del message
        self.exit(
            3,
            canonical(
                {
                    "status": "G1G3_OFFLINE_PORTS_FAIL_CLOSED",
                    "code": "CLI_ARGUMENTS_INVALID",
                    "health": "NOT_READY_FAIL_CLOSED",
                    "readiness": "OFFLINE_LOOPBACK_ONLY",
                    "safety_status": "DRY_RUN_NO_NETWORK_NO_ORDERING",
                }
            )
            + "\n",
        )


def main(argv: list[str] | None = None) -> int:
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=["LONG", "SHORT"], default="LONG")
    parser.add_argument("--horizon", type=int, choices=[12, 18, 24], default=24)
    parser.add_argument("--exit-kind", choices=["STOP", "TIME_CAP", "TP2"], default="STOP")
    parser.add_argument(
        "--scenario-type",
        choices=["STANDARD_24H", "DUAL_PENDING_ACK"],
        default="STANDARD_24H",
    )
    parser.add_argument("--output", default=str(OWN_SCRATCH / "cli-run-long"))
    parser.add_argument("--allow-loopback", action="store_true", default=False)
    parser.add_argument("--operator-id", default="op-alpha")
    parser.add_argument("--key-id", default="ed25519-offline-op-alpha-v1")
    parser.add_argument("--crash-boundary", choices=VALID_CRASH_BOUNDARIES)
    parser.add_argument("--llm-mode", default="OK")
    parser.add_argument("--feishu-mode", default="OK_200")
    parser.add_argument("--feishu-fail-count", type=int, default=0)
    args = parser.parse_args(argv)

    try:
        out_dir = guard_scratch_dir(Path(args.output))
        supervisor = DurableSidecarSupervisor(out_dir)
        receipt: dict[str, Any] = supervisor.run_scenario(
            side=args.side,
            horizon=args.horizon,
            exit_kind=args.exit_kind,
            scenario_type=args.scenario_type,
            allow_loopback=args.allow_loopback,
            operator_id=args.operator_id,
            key_id=args.key_id,
            crash_boundary=args.crash_boundary,
            llm_mode=args.llm_mode,
            feishu_mode=args.feishu_mode,
            feishu_fail_count=args.feishu_fail_count,
        )
        print(canonical(receipt))
        return 0 if receipt.get("sidecar_terminal") == "G1G3_OFFLINE_PORTS_BOUNDED_VERIFIED" else 3
    except (SafetyViolation, OSError, UnicodeError) as exc:
        code = exc.code if isinstance(exc, SafetyViolation) else "OFFLINE_IO_ERROR"
        failure = {
            "status": "G1G3_OFFLINE_PORTS_FAIL_CLOSED",
            "code": code,
            "health": "NOT_READY_FAIL_CLOSED",
            "readiness": "OFFLINE_LOOPBACK_ONLY",
            "safety_status": "DRY_RUN_NO_NETWORK_NO_ORDERING",
            "not_authorized": "TESTNET_LIVE_PRODUCTION_OR_REAL_MONEY",
        }
        print(canonical(failure))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
