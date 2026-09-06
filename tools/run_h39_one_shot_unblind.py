"""Run H39 one-shot unblind preregistration, gatekeeper verification, or unblind execution."""
from __future__ import annotations

import argparse
import json
import sys

from btc_quant_agent.microstructure_research import (
    H39_BLIND_LEDGER_DEFAULT_PATH,
    H39_CANONICAL_CANDLES_PATH,
    H39_FROZEN_SNAPSHOT_DEFAULT_DIR,
    H39_ONE_SHOT_EXECUTION_REGISTRY_DEFAULT_PATH,
    H39_PROTOCOL_PATH,
    H39OneShotUnblindGatekeeper,
    generate_all_v0325_deliverables,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="H39 One-Shot Unblind Preregistration & Execution Tool"
    )
    parser.add_argument(
        "--action",
        choices=["preregister", "freeze", "verify", "unblind", "readiness"],
        default="preregister",
        help="Action to execute: preregister (generate v0.3.25 deliverables), freeze (create cutoff manifest), verify (verify freeze manifest), unblind (execute formal validation), readiness (check gates)",
    )
    parser.add_argument(
        "--output-dir",
        default="deliverables/v0.3.25",
        help="Directory to write deliverables or results",
    )
    parser.add_argument(
        "--freeze-manifest",
        default="deliverables/v0.3.25/H39_ONE_SHOT_UNBLIND_FREEZE.json",
        help="Path to freeze manifest",
    )
    parser.add_argument(
        "--output-manifest",
        default="deliverables/v0.3.25/H39_ONE_SHOT_UNBLIND_FREEZE.json",
        help="Path to write freeze manifest when action=freeze",
    )
    parser.add_argument(
        "--ledger-path",
        default=H39_BLIND_LEDGER_DEFAULT_PATH,
        help="Path to blind validation ledger SQLite database",
    )
    parser.add_argument(
        "--registry-path",
        default=H39_ONE_SHOT_EXECUTION_REGISTRY_DEFAULT_PATH,
        help="Path to one-shot execution registry SQLite database",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=H39_FROZEN_SNAPSHOT_DEFAULT_DIR,
        help="Directory for frozen ledger snapshots",
    )
    parser.add_argument(
        "--readiness-path",
        default=None,
        help="Optional path to write authoritative readiness artifact",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Optional path to git repository root for committed freeze verification",
    )
    parser.add_argument(
        "--protocol-path",
        default=H39_PROTOCOL_PATH,
        help="Path to frozen protocol JSON",
    )
    parser.add_argument(
        "--clarification-path",
        default="deliverables/v0.3.22/H39_PROTOCOL_CLARIFICATION_001.json",
        help="Path to clarification JSON",
    )
    parser.add_argument(
        "--microstructure-root",
        default="data/forward/BTCUSDT/microstructure",
        help="Root path of microstructure partitions",
    )
    parser.add_argument(
        "--opportunity-store",
        default="data/forward/BTCUSDT/opportunity_shadow.sqlite3",
        help="Path to opportunity shadow SQLite database",
    )
    parser.add_argument(
        "--canonical-candles",
        default=H39_CANONICAL_CANDLES_PATH,
        help="Path to canonical 1m candles SQLite database",
    )
    parser.add_argument(
        "--as-of-ms",
        type=int,
        default=None,
        help="Optional explicit timestamp in ms for deterministic replay/audit",
    )

    args = parser.parse_args()

    gatekeeper = H39OneShotUnblindGatekeeper(
        ledger_path=args.ledger_path,
        protocol_path=args.protocol_path,
        clarification_path=args.clarification_path,
        microstructure_root=args.microstructure_root,
        opportunity_store_path=args.opportunity_store,
        canonical_candles_path=args.canonical_candles,
        registry_path=args.registry_path,
        snapshot_dir=args.snapshot_dir,
        repo_root=args.repo_root,
    )

    if args.action == "readiness":
        res = gatekeeper.verify_readiness_preconditions(as_of_ms=args.as_of_ms)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ready_for_unblind") else 1

    if args.action == "freeze":
        try:
            manifest = gatekeeper.create_freeze_manifest(
                output_path=args.output_manifest,
                as_of_ms=args.as_of_ms,
                readiness_artifact_path=args.readiness_path,
            )
            print(json.dumps({"status": "SUCCESS", "manifest": manifest}, indent=2))
            return 0
        except RuntimeError as exc:
            print(json.dumps({"status": "REFUSED", "error": str(exc)}, indent=2))
            return 1

    if args.action == "verify":
        try:
            manifest = gatekeeper.verify_freeze_manifest(args.freeze_manifest)
            print(json.dumps({"status": "VERIFIED", "manifest": manifest}, indent=2))
            return 0
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"status": "VERIFICATION_FAILED", "error": str(exc)}, indent=2))
            return 1

    if args.action == "unblind":
        try:
            results = gatekeeper.execute_one_shot_unblind(
                freeze_manifest_path=args.freeze_manifest,
                output_dir=args.output_dir,
                repo_root=args.repo_root,
            )
            print(json.dumps({"status": "SUCCESS", "scientific_verdict": results.get("scientific_verdict")}, indent=2))
            return 0
        except RuntimeError as exc:
            print(json.dumps({"status": "REFUSED", "error": str(exc)}, indent=2))
            return 1

    if args.action == "preregister":
        files = generate_all_v0325_deliverables(
            output_dir=args.output_dir,
            ledger_path=args.ledger_path,
            microstructure_root=args.microstructure_root,
            opportunity_store_path=args.opportunity_store,
            as_of_ms=args.as_of_ms,
        )
        print(json.dumps({"status": "SUCCESS", "deliverables": files}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
