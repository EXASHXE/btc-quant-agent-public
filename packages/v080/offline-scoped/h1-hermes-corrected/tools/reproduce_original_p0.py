"""Independently reproduce P0-C01, P0-C02, and P0-C03 against the untouched original H1 baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

WORKSPACES = Path(__file__).resolve().parents[1].parent
FIX_ROOT = Path(__file__).resolve().parents[1]
ORIG_H1_ROOT = WORKSPACES / "lt-v080-gemini-neon-hermes-quant-feishu-h1-01"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    # Ensure imports resolve against untouched original H1 src before loading fixtures
    sys.path.insert(0, str(ORIG_H1_ROOT / "src"))
    sys.path.insert(0, str(FIX_ROOT))
    for mod in list(sys.modules):
        if mod == "quant_hermes_feishu_h1" or mod.startswith("quant_hermes_feishu_h1."):
            del sys.modules[mod]

    from fixtures.build_conformance_journals import build_edge_case_journal
    from quant_hermes_feishu_h1.contract import (
        CONTRACT_ID,
        compute_outbox_event_id,
    )
    from quant_hermes_feishu_h1.facade import QuantFacadeService
    from quant_hermes_feishu_h1.journal_reader import (
        ApprovedJournalRegistry,
        ApprovedJournalSource,
    )

    with tempfile.TemporaryDirectory(prefix="h1-orig-repro-") as td:
        tmp = Path(td)
        edge_db = build_edge_case_journal(tmp / "edge.sqlite")
        gen_db = build_edge_case_journal(
            tmp / "genuine.sqlite",
            evidence="PERSONAL_PUBLIC_MARKET_GENUINE",
            source_origin="BINANCE_OFFICIAL_PUBLIC",
            include_receipt_hashes=True,
            base_ts_ms=1735691000000,
        )

        # P0-C01 reproduction on original H1
        svc_edge = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("edge", edge_db)]))
        active_noep = svc_edge.handle_request({
            "contract_id": CONTRACT_ID,
            "request_id": "orig-c01-active",
            "tool": "list_active_signals",
            "args": {"statuses": ["NO_SETUP", "NOT_EVALUATED"]},
            "principal_id": "hermes_quant_plugin",
            "recipient_scope": "owner_dm",
            "deadline_ms": 2000,
        })
        hist_noep = svc_edge.handle_request({
            "contract_id": CONTRACT_ID,
            "request_id": "orig-c01-hist",
            "tool": "get_signal_history",
            "args": {"limit": 10},
            "principal_id": "hermes_quant_plugin",
            "recipient_scope": "owner_dm",
            "deadline_ms": 2000,
        })
        reg_orig = ApprovedJournalRegistry([ApprovedJournalSource("edge", edge_db)])
        orig_recs, _ = reg_orig.load_all_verified_cards()
        orig_latest_keys = sorted(reg_orig.latest_records_by_episode(orig_recs).keys())

        # P0-C02 reproduction on original H1
        pre_auth_err = svc_edge.handle_request({
            "contract_id": CONTRACT_ID,
            "request_id": "orig-c02-auth",
            "tool": "list_active_signals",
            "args": {},
            "principal_id": "unknown_principal",
            "recipient_scope": "owner_dm",
            "deadline_ms": 2000,
        })
        svc_mixed = QuantFacadeService(
            ApprovedJournalRegistry([
                ApprovedJournalSource("edge", edge_db),
                ApprovedJournalSource("gen", gen_db, allow_hypothetical_genuine=True),
            ])
        )
        mixed_active = svc_mixed.handle_request({
            "contract_id": CONTRACT_ID,
            "request_id": "orig-c02-mixed",
            "tool": "list_active_signals",
            "args": {"limit": 10},
            "principal_id": "hermes_quant_plugin",
            "recipient_scope": "owner_dm",
            "deadline_ms": 2000,
        })

        # P0-C03 reproduction on original H1
        no_golden_dir = not (ORIG_H1_ROOT / "reference-export").exists()
        accepted_noep_event_id = compute_outbox_event_id(
            contract_id=CONTRACT_ID,
            channel="feishu",
            recipient=" ou_owner001 ",
            episode_id="noep:fake",
            card_id="f" * 64,
            card_version="jseq:1:aaaa:bbbb",
            market_status="NO_SETUP",
        )

    orig_wheel = ORIG_H1_ROOT / "evidence/wheel/quant_hermes_feishu_h1-0.8.0-py3-none-any.whl"
    orig_manifest = ORIG_H1_ROOT / "SHA256SUMS"
    report = {
        "reproduction_target": "workspaces/lt-v080-gemini-neon-hermes-quant-feishu-h1-01",
        "original_wheel_sha256": hashlib.sha256(orig_wheel.read_bytes()).hexdigest(),
        "original_manifest_sha256": hashlib.sha256(orig_manifest.read_bytes()).hexdigest(),
        "p0_c01_reproduced": {
            "list_active_signals_with_no_setup_filter_count": len(active_noep["data"]["signals"]),
            "returned_statuses": [s["market_status"] for s in active_noep["data"]["signals"]],
            "returned_episode_ids": [s["episode_id"] for s in active_noep["data"]["signals"]],
            "history_null_episode_missing_diagnostic_flag": any(
                h["episode_id"] is None and "diagnostic_only" not in h for h in hist_noep["data"]["history"]
            ),
            "internal_noep_keys_synthesized": [k for k in orig_latest_keys if k.startswith("noep:")],
        },
        "p0_c02_reproduced": {
            "pre_source_unauthorized_error_class": pre_auth_err["source_evidence_class"],
            "pre_source_unauthorized_error_code": pre_auth_err["error"]["code"],
            "pre_source_server_as_of_ms": pre_auth_err["server_as_of_ms"],
            "mixed_page_source_evidence_class": mixed_active["source_evidence_class"],
            "mixed_page_banner": mixed_active["data"]["source_banner"],
            "mixed_page_item_classes": sorted({s["source_evidence_class"] for s in mixed_active["data"]["signals"]}),
        },
        "p0_c03_reproduced": {
            "original_lacks_reference_export_pack": no_golden_dir,
            "compute_outbox_event_id_accepted_noep_and_whitespace": accepted_noep_event_id,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("P0_BEFORE_REPRODUCTION_OK")


if __name__ == "__main__":
    main()
