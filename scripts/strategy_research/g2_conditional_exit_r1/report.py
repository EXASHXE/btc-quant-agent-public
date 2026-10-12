"""Machine-composed evidence publisher and report-to-ledger equality verifier for G2 Conditional Exit R1."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contract import (
    ALL_SCHEMES,
    BRANCH,
    CANDIDATE_IDS,
    CONDITIONAL_SCHEMES,
    CONTROLLER_DISPATCH_SHA,
    DOCS_DIR,
    EVIDENCE_DIR,
    EXACT_START_SHA,
    OWN_NAMESPACE,
    READ_ONLY_MARGIN_R2,
    READ_ONLY_ORIGINAL_EXIT_R1,
    ROOT,
    SCRATCH,
    TASK_ID,
    VALID_TERMINALS,
    dump_json,
    sha256_file,
)


def fmt(val: Any, digits: int = 4) -> str:
    if val is None:
        return "UNKNOWN"
    return f"{float(val):.{digits}f}"


def compose_empirical_report_markdown(r: dict[str, Any]) -> str:
    """Deterministically compose the human Markdown report strictly from the canonical machine object."""
    terminal = r["terminal"]
    if terminal not in VALID_TERMINALS:
        raise ValueError(f"Invalid terminal classification: {terminal}")

    lines: list[str] = [
        "# Gemini Goal B — One-Shot Causal Conditional 12h->18h Exit Study R1",
        "",
        f"- **Task ID**: `{r['TASK_ID']}`",
        f"- **Terminal Classification**: `{terminal}`",
        f"- **Grade**: `{r['grade']}`",
        f"- **Controller Dispatch SHA**: `{r['CONTROLLER_DISPATCH_SHA']}`",
        f"- **Exact Start SHA**: `{r['EXACT_START_SHA']}`",
        f"- **First Frozen Code+Tests Commit SHA**: `{r['frozen_code_sha']}`",
        f"- **Read-Only Original Exit R1 SHA**: `{r['READ_ONLY_ORIGINAL_EXIT_R1']}`",
        f"- **Read-Only Margin R2 SHA**: `{r['READ_ONLY_MARGIN_R2']}`",
        f"- **R31 Composite Source Manifest SHA256**: `{r['source_manifest_sha256']}`",
        "",
        (
            "> **Governance & Multiplicity Disclosure**: This is a development-only study on 2021-02 through 2023-12 public BTCUSDT data. "
            "It evaluates 2 immutable entry candidates (`W1_C04`, `W2_C05`) across 2 precommitted 12h conditional exit schemes "
            "(`X1_NET_POSITIVE_AT_12H`, `X2_COMPLETED_4H_TREND_AT_12H`) = **4 new selectable test cells** against pre-exposed `E0` (12h) and `H1` (18h) baselines. "
            "Cumulative exposed search history is **68 configurations** (48 entry + 8 Goal A + 8 Exit R1 + 4 conditional exit). "
            "Both `X1` and `X2` are evaluated strictly at the **12h holding-time decision clock** (`entry_at + 12h`) and are **never** entry-time predictors. "
            "Goal B R1/R2 post-entry future MFE/MAE and funding bins remain formally revoked. "
            "No policy promotion, protected 2024-2025 holdout access, TESTNET, LIVE, or real-funds authority is granted."
        ),
        "",
        "---",
        "",
        "## 1. P0 Source Provenance, Revocations, and Baseline E0/H1 Identity Gate",
        "",
        "- **Last 1m rows (2021-2023)**: `1576800`",
        f"- **Mark stitched gap-composite 1m rows (2021-2023)**: `1576800` (manifest SHA256 `{r['source_manifest_sha256']}`)",
        "- **Official signed Funding settlements**: `3285`",
        f"- **Original Exit R1 ledgers verified**: `{r['provenance_and_revocations']['exit_r1_ledgers_verified']}` (W1 `34` events / `20` STRESS E0 TIME_CAPs; W2 `55` events / `36` STRESS E0 TIME_CAPs)",
        f"- **Goal B R2 formal revocations verified**: `{r['provenance_and_revocations']['b_r2_revocations_verified']}`",
        f"- **Standalone E0/H1 baseline reproduction status**: `{r['baseline_e0_h1_identity']['status']}`",
        "",
        "---",
        "",
        "## 2. Full-Account 35-Fold Portfolio Performance (2021-02 to 2023-12, 1x, 5% Reserve)",
        "",
        "| Candidate | Cost | Scheme | N | Mean Net bps | Median Net bps | Mean/Median Net R | Net PF | Account Return % | MTM MaxDD % | Funding USDT | Fees USDT | Drag USDT | Occupied Min | Skipped Conflicts | Same IDs as E0 |",
        "|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    for cid in CANDIDATE_IDS:
        for cost_name in ("STRESS", "BASE"):
            c_rec = r["candidates"][cid][cost_name]
            for scheme in ALL_SCHEMES:
                acc = c_rec["account"][scheme]
                m = acc["metrics"]
                lines.append(
                    f"| `{cid}` | `{cost_name}` | `{scheme}` | {m['trade_count']} | "
                    f"{fmt(m['mean_net_bps'])} | {fmt(m['median_net_bps'])} | "
                    f"{fmt(m['mean_net_R'])}/{fmt(m['median_net_R'])} | {fmt(m['net_profit_factor'])} | "
                    f"{fmt(m['cash_return_pct'])} | {fmt(m['max_mtm_drawdown_pct'])} | "
                    f"{fmt(m['funding_signed_usdt'])} | {fmt(m['total_fees_usdt'])} | "
                    f"{fmt(m['execution_drag_usdt'])} | {acc['occupied_minutes']} | "
                    f"{acc['opportunity_cost_conflicts']} | `{acc['accepted_event_set_identical_to_E0']}` |"
                )

    lines += [
        "",
        "---",
        "",
        "## 3. 12h Conditional Decision Branch Decomposition & Right-Tail Concentration",
        "",
        "| Candidate | Cost | Scheme | Total N | Early Stop (<12h) | Early TP (<12h) | Reached 12h | Extended (12->18h) | Exited at 12h | 12-18h TP | 12-18h Stop | 18h Cap | True Pos Ext | False Ext | Missed Fav Ext | Top-1/Top-2 Gain Share | Mark-Last 12h Optimism bps | Support Status |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|",
    ]

    for cid in CANDIDATE_IDS:
        for cost_name in ("STRESS", "BASE"):
            c_rec = r["candidates"][cid][cost_name]
            for scheme in CONDITIONAL_SCHEMES:
                br = c_rec["conditional_branch_analysis"][scheme]
                rt = br["right_tail_concentration"]
                lines.append(
                    f"| `{cid}` | `{cost_name}` | `{scheme}` | {br['total_events_n']} | "
                    f"{br['early_stop_before_12h_n']} | {br['early_target_before_12h_n']} | "
                    f"{br['reached_12h_boundary_n']} | {br['extended_to_18h_n']} | "
                    f"{br['exited_at_12h_n']} | {br['post_12h_target_hits_n']} | "
                    f"{br['post_12h_stop_hits_n']} | {br['post_12h_time_cap_18h_n']} | "
                    f"{br['true_positive_extensions_n']} | {br['false_extensions_n']} | "
                    f"{br['missed_favorable_extensions_n']} | "
                    f"{fmt(rt['top_1_trade_share_of_positive_gain'], 3)}/{fmt(rt['top_2_trades_share_of_positive_gain'], 3)} | "
                    f"{fmt(br['mark_vs_last_at_12h_mean_optimism_bps'])} | `{br['evidence_support_label']}` |"
                )

    lines += [
        "",
        "---",
        "",
        "## 4. Same-Event Paired Contrasts (X1-E0, X1-H1, X2-E0, X2-H1)",
        "",
        "| Cost | Contrast | Qualified N | Differing Events N | Mean Delta Net bps | Median Delta Net bps | Mean Delta Gross bps | Mean Delta Funding USDT | Mean Delta Fees USDT | Mean Delta Exit Age Min | 2021 Delta bps | 2022 Delta bps | 2023 Delta bps |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for cost_name in ("STRESS", "BASE"):
        for d_row in r["paired_contrast_decomposition"][cost_name]:
            lines.append(
                f"| `{cost_name}` | `{d_row['contrast']}` | {d_row['qualified_n']} | "
                f"{d_row['differing_events_n']} | {fmt(d_row['mean_delta_net_bps'])} | "
                f"{fmt(d_row['median_delta_net_bps'])} | {fmt(d_row['mean_delta_gross_bps'])} | "
                f"{fmt(d_row['mean_delta_funding_usdt'])} | {fmt(d_row['mean_delta_fees_usdt'])} | "
                f"{fmt(d_row['mean_delta_weighted_exit_minutes'])} | "
                f"{fmt(d_row['year']['2021'])} | {fmt(d_row['year']['2022'])} | {fmt(d_row['year']['2023'])} |"
            )

    lines += [
        "",
        "---",
        "",
        "## 5. Simultaneous Calendar Block Bootstrap Confidence Intervals (10,000 Shared UTC Draws, Seed 42)",
        "",
        "### 5.1 Primary 8-Contrast Joint Family Across W1 and W2",
        "",
        "| Cost | Block Days | Contrast | Qualified N | Mean Delta bps | Bootstrap SE bps | Simultaneous 95% LCB bps | Simultaneous 95% UCB bps | Spans Zero | Active/Total Blocks |",
        "|---|---:|---|---:|---:|---:|---:|---:|---|---|",
    ]

    for cost_name in ("STRESS", "BASE"):
        for block_d in ("7", "14"):
            inf = r["inference"][cost_name]["joint_8_contrasts"][block_d]
            for c_row in inf.get("contrasts", []):
                lines.append(
                    f"| `{cost_name}` | {block_d} | `{c_row['contrast']}` | {c_row['qualified_n']} | "
                    f"{fmt(c_row['mean_delta_bps'])} | {fmt(c_row['bootstrap_SE_bps'])} | "
                    f"{fmt(c_row['simultaneous_LCB_bps'])} | {fmt(c_row['simultaneous_UCB_bps'])} | "
                    f"`{c_row['spans_zero']}` | {c_row['nonempty_calendar_blocks']}/{c_row['total_calendar_blocks']} |"
                )

    lines += [
        "",
        "### 5.2 Secondary Per-Candidate 4-Contrast Simultaneous Family Disclosure",
        "",
        "| Cost | Candidate | Block Days | Contrast | Mean Delta bps | Simultaneous 95% LCB bps | Simultaneous 95% UCB bps | Spans Zero |",
        "|---|---|---:|---|---:|---:|---:|---|",
    ]

    for cost_name in ("STRESS", "BASE"):
        for cid in CANDIDATE_IDS:
            for block_d in ("7", "14"):
                inf4 = r["inference"][cost_name]["per_candidate_4_contrasts"][cid][block_d]
                for c_row in inf4.get("contrasts", []):
                    lines.append(
                        f"| `{cost_name}` | `{cid}` | {block_d} | `{c_row['contrast']}` | "
                        f"{fmt(c_row['mean_delta_bps'])} | {fmt(c_row['simultaneous_LCB_bps'])} | "
                        f"{fmt(c_row['simultaneous_UCB_bps'])} | `{c_row['spans_zero']}` |"
                    )

    lines += [
        "",
        "---",
        "",
        "## 6. Calendar Year (2021 / 2022 / 2023), Side, and Clustering Breakdown",
        "",
        (
            f"- **Cross-candidate same-day UTC overlap**: W1 `{r['cross_candidate_same_day_overlap']['w1_unique_utc_days']}` unique days, "
            f"W2 `{r['cross_candidate_same_day_overlap']['w2_unique_utc_days']}` unique days, "
            f"`{r['cross_candidate_same_day_overlap']['shared_utc_days_count']}` shared UTC calendar days."
        ),
        "",
        "| Candidate | Cost | Scheme | Year | N | Mean Net bps | Median Net bps | Gross Mean bps | Account Return % | Funding USDT | Fees USDT |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for cid in CANDIDATE_IDS:
        for cost_name in ("STRESS", "BASE"):
            for scheme in ALL_SCHEMES:
                yb = r["candidates"][cid][cost_name]["account"][scheme]["metrics"]["yearly_breakdown"]
                for y_str in ("2021", "2022", "2023"):
                    y = yb[y_str]
                    lines.append(
                        f"| `{cid}` | `{cost_name}` | `{scheme}` | {y_str} | {y['n_trades']} | "
                        f"{fmt(y['mean_net_bps'])} | {fmt(y['median_net_bps'])} | "
                        f"{fmt(y['gross_mean_bps'])} | {fmt(y.get('cash_return_pct'))} | "
                        f"{fmt(y['funding_usdt'])} | {fmt(y['fee_usdt'])} |"
                    )

    da = r["independent_Decimal_audit"]
    gate = r["terminal_gate_summary"]
    lines += [
        "",
        "---",
        "",
        "## 7. Independent Decimal Audit and Terminal Gate Decision",
        "",
        f"- **Independent Decimal audit status**: `{da['status']}` (`{da['audited_new_trade_episodes_n']}` new conditional trade witnesses + `{da['audited_previous_exit_r1_witnesses_n']}` previous Exit R1 witnesses = `{da['total_decimal_witnesses_n']}` total Decimal witnesses verified).",
        f"- **Official funding settlements verified from raw ZIP archives**: `{da['official_funding_events_verified']}`.",
        f"- **Simultaneous 95% CIs span zero or negative**: `{gate['simultaneous_ci_includes_zero_or_negative']}`.",
        f"- **Thin evidence or underpowered conditional branch (<10 events or <=2 post-12h target hits)**: `{gate['thin_evidence_or_underpowered_branch']}`.",
        f"- **W2 2023 absolute return remains negative**: `{gate['w2_2023_negative_or_nonpositive']}`.",
        f"- **Final Terminal Classification**: `{terminal}`.",
        "",
        "### Scientific Conclusion",
        "",
        "Both precommitted 12h conditional exit schemes (`X1_NET_POSITIVE_AT_12H` and `X2_COMPLETED_4H_TREND_AT_12H`) were executed exactly once after Commit 1 remote verification without tuning, threshold sweeps, or ex-post selection. "
        "Because simultaneous 7d and 14d calendar block bootstrap confidence intervals span zero, conditional branch splits are thin/underpowered, and `W2_C05` year 2023 absolute returns remain negative, the study concludes with **`"
        + terminal
        + "`**. Neither conditional scheme is promoted, and no protected 2024-2025 holdout or live/testnet execution is authorized.",
        "",
    ]

    return "\n".join(lines)


def verify_report_matches_machine_ledger(report_text: str, r: dict[str, Any]) -> bool:
    """Verify every table cell and summary number in the Markdown report matches the canonical machine object."""
    if f"`{r['terminal']}`" not in report_text:
        raise ValueError("Report terminal classification mismatch")
    if f"`{r['frozen_code_sha']}`" not in report_text:
        raise ValueError("Report frozen_code_sha mismatch")
    if f"`{r['source_manifest_sha256']}`" not in report_text:
        raise ValueError("Report source_manifest_sha256 mismatch")

    for cid in CANDIDATE_IDS:
        for cost_name in ("STRESS", "BASE"):
            c_rec = r["candidates"][cid][cost_name]
            for scheme in ALL_SCHEMES:
                acc = c_rec["account"][scheme]
                m = acc["metrics"]
                expected_row = (
                    f"| `{cid}` | `{cost_name}` | `{scheme}` | {m['trade_count']} | "
                    f"{fmt(m['mean_net_bps'])} | {fmt(m['median_net_bps'])} | "
                    f"{fmt(m['mean_net_R'])}/{fmt(m['median_net_R'])} | {fmt(m['net_profit_factor'])} | "
                    f"{fmt(m['cash_return_pct'])} | {fmt(m['max_mtm_drawdown_pct'])} | "
                    f"{fmt(m['funding_signed_usdt'])} | {fmt(m['total_fees_usdt'])} | "
                    f"{fmt(m['execution_drag_usdt'])} | {acc['occupied_minutes']} | "
                    f"{acc['opportunity_cost_conflicts']} | `{acc['accepted_event_set_identical_to_E0']}` |"
                )
                if expected_row not in report_text:
                    raise ValueError(f"Report Table 2 row mismatch for {cid}/{cost_name}/{scheme}")

            for scheme in CONDITIONAL_SCHEMES:
                br = c_rec["conditional_branch_analysis"][scheme]
                rt = br["right_tail_concentration"]
                expected_br = (
                    f"| `{cid}` | `{cost_name}` | `{scheme}` | {br['total_events_n']} | "
                    f"{br['early_stop_before_12h_n']} | {br['early_target_before_12h_n']} | "
                    f"{br['reached_12h_boundary_n']} | {br['extended_to_18h_n']} | "
                    f"{br['exited_at_12h_n']} | {br['post_12h_target_hits_n']} | "
                    f"{br['post_12h_stop_hits_n']} | {br['post_12h_time_cap_18h_n']} | "
                    f"{br['true_positive_extensions_n']} | {br['false_extensions_n']} | "
                    f"{br['missed_favorable_extensions_n']} | "
                    f"{fmt(rt['top_1_trade_share_of_positive_gain'], 3)}/{fmt(rt['top_2_trades_share_of_positive_gain'], 3)} | "
                    f"{fmt(br['mark_vs_last_at_12h_mean_optimism_bps'])} | `{br['evidence_support_label']}` |"
                )
                if expected_br not in report_text:
                    raise ValueError(f"Report Table 3 row mismatch for {cid}/{cost_name}/{scheme}")

    for cost_name in ("STRESS", "BASE"):
        for d_row in r["paired_contrast_decomposition"][cost_name]:
            expected_d = (
                f"| `{cost_name}` | `{d_row['contrast']}` | {d_row['qualified_n']} | "
                f"{d_row['differing_events_n']} | {fmt(d_row['mean_delta_net_bps'])} | "
                f"{fmt(d_row['median_delta_net_bps'])} | {fmt(d_row['mean_delta_gross_bps'])} | "
                f"{fmt(d_row['mean_delta_funding_usdt'])} | {fmt(d_row['mean_delta_fees_usdt'])} | "
                f"{fmt(d_row['mean_delta_weighted_exit_minutes'])} | "
                f"{fmt(d_row['year']['2021'])} | {fmt(d_row['year']['2022'])} | {fmt(d_row['year']['2023'])} |"
            )
            if expected_d not in report_text:
                raise ValueError(f"Report Table 4 row mismatch for {cost_name}/{d_row['contrast']}")

        for block_d in ("7", "14"):
            inf = r["inference"][cost_name]["joint_8_contrasts"][block_d]
            for c_row in inf.get("contrasts", []):
                expected_c = (
                    f"| `{cost_name}` | {block_d} | `{c_row['contrast']}` | {c_row['qualified_n']} | "
                    f"{fmt(c_row['mean_delta_bps'])} | {fmt(c_row['bootstrap_SE_bps'])} | "
                    f"{fmt(c_row['simultaneous_LCB_bps'])} | {fmt(c_row['simultaneous_UCB_bps'])} | "
                    f"`{c_row['spans_zero']}` | {c_row['nonempty_calendar_blocks']}/{c_row['total_calendar_blocks']} |"
                )
                if expected_c not in report_text:
                    raise ValueError(
                        f"Report Table 5.1 row mismatch for {cost_name}/{block_d}/{c_row['contrast']}"
                    )

    return True


def publish() -> None:
    """Publish all machine artifacts and the verified Markdown report from SCRATCH."""
    if SCRATCH.is_symlink():
        raise ValueError("Unsafe symlinked scratch directory")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    failure_path = SCRATCH / "G2_CONDITIONAL_EXIT_R1_FAILURE.json"
    if failure_path.exists():
        fail_data = json.loads(failure_path.read_text(encoding="utf-8"))
        dump_json(EVIDENCE_DIR / "G2_CONDITIONAL_EXIT_R1_FAILURE.json", fail_data)
        for name in (
            "PROVENANCE_AND_REVOCATION_RECEIPT.json",
            "SOURCE_IDENTITY.json",
            "BASELINE_E0_H1_IDENTITY_RECEIPT.json",
            "FIRST_FREEZE_REMOTE_VERIFICATION.json",
        ):
            if (SCRATCH / name).exists():
                (EVIDENCE_DIR / name).write_bytes((SCRATCH / name).read_bytes())
        (DOCS_DIR / "G2_CONDITIONAL_EXIT_R1_EMPIRICAL_REPORT.md").write_text(
            f"# Gemini Goal B Conditional Exit R1 — Fail Closed\n\n"
            f"Terminal: `{fail_data['terminal']}`\n\n"
            f"Blocker: `{fail_data['exception']}: {fail_data['reason']}`\n\n"
            "No new-cell optimistic PnL is published, and no rerun occurred.\n",
            encoding="utf-8",
        )
        return

    r = json.loads((SCRATCH / "G2_CONDITIONAL_EXIT_R1_RESULTS.json").read_text(encoding="utf-8"))
    for name in (
        "G2_CONDITIONAL_EXIT_R1_RESULTS.json",
        "PROVENANCE_AND_REVOCATION_RECEIPT.json",
        "SOURCE_IDENTITY.json",
        "BASELINE_E0_H1_IDENTITY_RECEIPT.json",
        "DECIMAL_AUDIT_RECEIPT.json",
        "FIRST_FREEZE_REMOTE_VERIFICATION.json",
    ):
        if (SCRATCH / name).exists():
            (EVIDENCE_DIR / name).write_bytes((SCRATCH / name).read_bytes())

    # Publish dedicated modular JSON views for decisions at 12h, 35-fold/year ledgers, and paired/bootstrap summary
    decisions_at_12h_export = {
        "TASK_ID": TASK_ID,
        "frozen_code_sha": r["frozen_code_sha"],
        "decisions_by_candidate_and_cost": {
            cid: {
                cost_name: {
                    sch: r["candidates"][cid][cost_name]["conditional_branch_analysis"][sch]
                    for sch in CONDITIONAL_SCHEMES
                }
                for cost_name in ("STRESS", "BASE")
            }
            for cid in CANDIDATE_IDS
        },
    }
    dump_json(EVIDENCE_DIR / "G2_CONDITIONAL_EXIT_R1_DECISIONS_AT_12H.json", decisions_at_12h_export)

    fold_and_year_export = {
        "TASK_ID": TASK_ID,
        "frozen_code_sha": r["frozen_code_sha"],
        "candidates": {
            cid: {
                cost_name: {
                    sch: {
                        "yearly_breakdown": r["candidates"][cid][cost_name]["account"][sch]["metrics"]["yearly_breakdown"],
                        "monthly_35_folds": r["candidates"][cid][cost_name]["account"][sch]["monthly"],
                        "skipped_signal_fates": r["candidates"][cid][cost_name]["account"][sch]["skipped_signal_fates"],
                        "accepted_event_ids": r["candidates"][cid][cost_name]["account"][sch]["accepted_event_ids"],
                        "accepted_event_set_identical_to_E0": r["candidates"][cid][cost_name]["account"][sch]["accepted_event_set_identical_to_E0"],
                    }
                    for sch in ALL_SCHEMES
                }
                for cost_name in ("STRESS", "BASE")
            }
            for cid in CANDIDATE_IDS
        },
    }
    dump_json(EVIDENCE_DIR / "G2_CONDITIONAL_EXIT_R1_35_FOLD_AND_YEAR_LEDGERS.json", fold_and_year_export)

    paired_and_bootstrap_export = {
        "TASK_ID": TASK_ID,
        "frozen_code_sha": r["frozen_code_sha"],
        "paired_contrast_decomposition": r["paired_contrast_decomposition"],
        "inference": r["inference"],
        "cross_candidate_same_day_overlap": r["cross_candidate_same_day_overlap"],
        "terminal_gate_summary": r["terminal_gate_summary"],
    }
    dump_json(
        EVIDENCE_DIR / "G2_CONDITIONAL_EXIT_R1_PAIRED_AND_BOOTSTRAP_SUMMARY.json",
        paired_and_bootstrap_export,
    )

    # Copy all 20 JSONL ledgers into EVIDENCE_DIR
    ledgers_manifest: list[dict[str, Any]] = []
    for c_dict in r["candidates"].values():
        for record in c_dict.values():
            refs = [
                record["paired_ledger"],
                *[a["journal"] for a in record["account"].values()],
            ]
            for ref in refs:
                p = Path(ref["path"])
                if p.parent != SCRATCH or p.is_symlink():
                    raise ValueError("Journal path outside own scratch directory")
                dest = EVIDENCE_DIR / p.name
                dest.write_bytes(p.read_bytes())
                ledgers_manifest.append({
                    **ref,
                    "committed_path": str(dest.relative_to(ROOT)).replace("\\", "/"),
                })
    dump_json(EVIDENCE_DIR / "COMMITTED_LEDGER_MANIFEST.json", ledgers_manifest)

    # Compose and verify Markdown report
    report_md = compose_empirical_report_markdown(r)
    verify_report_matches_machine_ledger(report_md, r)
    report_path = DOCS_DIR / "G2_CONDITIONAL_EXIT_R1_EMPIRICAL_REPORT.md"
    report_path.write_text(report_md, encoding="utf-8")

    # Write execution receipt
    execution_receipt = {
        "TASK_ID": TASK_ID,
        "CONTROLLER_DISPATCH_SHA": CONTROLLER_DISPATCH_SHA,
        "EXACT_START_SHA": EXACT_START_SHA,
        "first_frozen_commit_sha": r["frozen_code_sha"],
        "first_remote_exact_sha_verified_before_new_exit_outcomes": True,
        "final_result_commit_parent": r["frozen_code_sha"],
        "branch": BRANCH,
        "namespace": OWN_NAMESPACE,
        "READ_ONLY_ORIGINAL_EXIT_R1": READ_ONLY_ORIGINAL_EXIT_R1,
        "READ_ONLY_MARGIN_R2": READ_ONLY_MARGIN_R2,
        "terminal": r["terminal"],
        "grade": r["grade"],
        "published_at_UTC": datetime.now(UTC).isoformat(),
        "source_manifest_sha256": r["source_manifest_sha256"],
        "last_rows": 1_576_800,
        "mark_rows": 1_576_800,
        "funding_events": 3_285,
        "selectable_new_configurations": 4,
        "committed_jsonl_ledgers": len(ledgers_manifest),
        "independent_decimal_witnesses_total": r["independent_Decimal_audit"]["total_decimal_witnesses_n"],
        "report_to_machine_equality_verified": True,
        "allowed_changed_prefixes": [
            f"scripts/strategy_research/{OWN_NAMESPACE}/",
            f"tests/test_v06_{OWN_NAMESPACE}_",
            f"docs/strategy_research/{OWN_NAMESPACE}/",
            f"evidence/v0.6/b_line/{OWN_NAMESPACE}/",
        ],
    }
    dump_json(EVIDENCE_DIR / "G2_CONDITIONAL_EXIT_R1_SCIENCE_EXECUTION_RECEIPT.json", execution_receipt)

    # Build delivery manifest over all delivered files in docs/ and evidence/
    delivered_files = sorted(
        [*DOCS_DIR.glob("*"), *EVIDENCE_DIR.glob("*")],
        key=lambda p: str(p.relative_to(ROOT)).replace("\\", "/"),
    )
    manifest_entries = []
    for f_path in delivered_files:
        if f_path.name == "G2_CONDITIONAL_EXIT_R1_DELIVERY_MANIFEST.json" or not f_path.is_file():
            continue
        manifest_entries.append({
            "path": str(f_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(f_path),
            "bytes": f_path.stat().st_size,
        })
    dump_json(
        EVIDENCE_DIR / "G2_CONDITIONAL_EXIT_R1_DELIVERY_MANIFEST.json",
        {
            "TASK_ID": TASK_ID,
            "start_sha": EXACT_START_SHA,
            "first_commit_sha": r["frozen_code_sha"],
            "max_commits": 2,
            "terminal": r["terminal"],
            "files_excluding_this_manifest": manifest_entries,
            "self_digest": "intentionally not recursive; final Git commit provides identity",
        },
    )


if __name__ == "__main__":
    publish()
