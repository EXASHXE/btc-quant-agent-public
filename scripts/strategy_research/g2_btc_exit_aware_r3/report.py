"""Publish compact research reports and five reproducible synthetic hand audits."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from . import engine, sources

DOCS = sources.ROOT / "docs/strategy_research/g2_r3/exit_aware_r3"


def fmt(x):
    return "NA" if x is None else f"{x:.2f}"


def build():
    result = json.loads((sources.EVIDENCE / "DEVELOPMENT_RESULTS_BASE_STRESS.json").read_text())
    pairs = json.loads((sources.EVIDENCE / "PAIRED_EXIT_DELTA_VS_X0.json").read_text())["rows"]
    test = sources.ROOT / "tests/test_v06_g2_btc_exit_aware_r3_engine.py"
    spec = importlib.util.spec_from_file_location("r3_synthetic_hand_audits", test)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    audits = []
    for case in (1, 2, 3, 4, 5):
        trade, expected, fixture = module.witness(case)
        assert trade["net_usdt"] == expected
        audits.append(
            {
                "id": f"HAND{case}",
                "fixture": fixture,
                "fixture_sha256": hashlib.sha256(engine.canonical(fixture)).hexdigest(),
                "independent_expected_net_USDT": str(expected),
                "observed_net_USDT": str(trade["net_usdt"]),
                "PASS": True,
                "ledger": json.loads(engine.canonical(trade)),
            }
        )
    sources.write(
        "MANUAL_DECIMAL_EXIT_LEG_AUDITS.json",
        {
            "label": "SYNTHETIC_ONLY_NOT_MARKET_PERFORMANCE",
            "freeze_sha": sources.FREEZE,
            "engine_sha256": sources.digest(Path(engine.__file__).read_bytes()),
            "fixture_test_source_sha256": sources.digest(test.read_bytes()),
            "audits": audits,
            "hand_verified_cases": 5,
            "independent_method": "fixed precomputed expectations plus re-derived adverse effective-price/fee sum in pytest; independent read-only helper also reconciled all five",
        },
    )
    lines = [
        "# BTC exit-aware developmental results R3",
        "",
        f"**Terminal: {result['terminal']}. Eligible hypotheses: {result['top3_eligible']}.**",
        "",
        f"Freeze `{sources.FREEZE}` was remotely verified at {result['freeze_push_receipt']['push_verified_utc']} before new scoring. Parent `{sources.BASE}`. Actual model/effort UNKNOWN.",
        "",
        "Exactly 27 frozen hypotheses, BASE and STRESS each; no retuning. All 12 exposed 2021–2023 scored folds and their warmups passed source admission: 24 archives, 1,045,440 rows. Current ZIP hashes match the previous public R2 development manifest. Reserved 2024–2025 reads = 0.",
        "",
        "Every PnL below is NET_EX_FUNDING_PROXY with assumed taker fees, spread, slip, tick/lot and hypothetical fills. Mark, actual funding, historical L2/capacity and historical ingress are UNKNOWN. Results are exposed-development hypotheses, not OOS Alpha or trading permission.",
        "",
        f"Source manifest SHA256 `{result['source_manifest_sha256']}`. Measured campaign time {result['runtime_seconds']:.3f} seconds; 54 candidate/cost rows, 648 independent month books. Repeated candidate trade records are not independent discoveries.",
        "",
        "| Cell | BASE N / gross / net bp | STRESS N / gross / net bp | STRESS PF | Max closed+dense DD % | Disposition |",
        "|---|---|---|---:|---:|---|",
    ]
    stress = []
    for base in [r for r in result["rows"] if r["cost_case"] == "BASE"]:
        row = next(
            r
            for r in result["rows"]
            if r["candidate"] == base["candidate"] and r["cost_case"] == "STRESS"
        )
        stress.append(row)
        lines.append(
            f"| {row['candidate']} | {base['completed_trades']} / {fmt(base['mean_gross_bps'])} / {fmt(base['mean_net_bps'])} | {row['completed_trades']} / {fmt(row['mean_gross_bps'])} / {fmt(row['mean_net_bps'])} | {fmt(row['profit_factor'])} | {fmt(row['max_closed_dense_MTM_DD_pct'])} | NO_GO |"
        )
    lines += [
        "",
        "## Annual and monthly book interpretation",
        "",
        "Each cost/candidate/month resets to 1000 USDT. Annual percentages are the mean of four independent month-book returns; they are neither compounded annual ROI nor net USDT on one continuous account. Full 54×12 month rows, all three years, LONG/SHORT and zero-trade groups are in DEVELOPMENT_RESULTS_BASE_STRESS.json.",
        "",
        "| STRESS cell | 2021 N / net bp | 2022 N / net bp | 2023 N / net bp |",
        "|---|---|---|---|",
    ]
    for row in stress:
        years = " | ".join(
            f"{y['completed_trades']} / {fmt(y['mean_net_bps'])}" for y in row["years"]
        )
        lines.append(f"| {row['candidate']} | {years} |")
    lines += [
        "",
        "## Same-entry exit improvements and selection effects",
        "",
        "Paired episodes use the same frozen entry, side, cap, cost and initial quantity, with a fixed unfunded 1000-USDT sizing reference. They ignore account blocking and cannot be treated as portfolio ROI. Portfolio admission/size/cooldown/risk fates are separately recorded, including unmatched entry IDs in scratch event ledgers.",
        "",
        "| STRESS alternate | Matched entries | Mean delta vs X0 bp | Tail5 alternate / X0 bp | Portfolio intersection / only X0 / only alternate |",
        "|---|---:|---:|---|---|",
    ]
    for p in [p for p in pairs if p["cost_case"] == "STRESS"]:
        lines.append(
            f"| {p['candidate']} | {p['matched_entries']} | {fmt(p['mean_delta_bps'])} | {fmt(p['tail5_candidate_bps'])} / {fmt(p['tail5_X0_bps'])} | {p['actual_account_entry_intersection']} / {p['actual_account_only_X0']} / {p['actual_account_only_alternate']} |"
        )
    lines += [
        "",
        "A scale-outs sometimes reduce losses versus X0 while remaining negative after STRESS costs. B has very little support. C scale-outs/trailing can reduce profit as well as tail exposure. Every STRESS cell remains below the 50-trade support gate and has nonpositive equal-year net economics; no winner is promoted. The least-negative table entry is not an eligible hypothesis.",
        "",
        "## Execution, financing and uncertainty",
        "",
        "JSON reports per-leg fees/spread/slip/tick drag, netR, PF, collision count, partial TP frequency, cap8/18/24 triggers, min/median/p75/max holding minutes and exits before4/12/18/24h. There is no 12h cap experiment. STOP/GAP/TIME_CAP/RISK_CLOSE are actual simulator causes; holding caps do not force a minimum holding time.",
        "",
        "Funding sensitivities are adverse4/8bp at possible UTC8h windows and adverse8bp hourly, using remaining quantity and conservative Last high. These are separate hypothetical financing charges, not verified historical costs. Additional exit2bp spread+3bp slip is a fixed-leg price/fee sensitivity, not a newly tuned strategy replay.",
        "",
        "Inference uses 10,000 shared deterministic calendar-week block draws within year, includes empty eligible weeks, and applies Bonferroni27 to net and paired improvement. Calendar-month blocks are a descriptive sensitivity. Undefined support/resamples are reported explicitly. No minute-IID sample claim or post-result threshold changes.",
        "",
        "A retains raw R2 entry dictionaries and hashes. All exits use a common24h+ACK fold cutoff, so admitted A accounts differ from the old8h-specific cutoff. R3 uses a full causal account risk close rather than R2 partial notional reduction. These account differences cannot be attributed solely to new exit targets.",
        "",
        "## Reproducibility and examples",
        "",
        "```sh",
        "PYTHONDONTWRITEBYTECODE=1 python3.12 -m pytest -q --noconftest tests/test_v06_g2_btc_exit_aware_r3_engine.py -p no:cacheprovider",
        "PYTHONDONTWRITEBYTECODE=1 python3.12 -m scripts.strategy_research.g2_btc_exit_aware_r3.run",
        "PYTHONDONTWRITEBYTECODE=1 python3.12 -m scripts.strategy_research.g2_btc_exit_aware_r3.report",
        "```",
        "",
        "Download admission precedes replay and requires the remote freeze receipt; raw ZIP/CSV/NPY and full entry/leg/curve paths remain in task scratch. Five unique real-development event examples (good and bad hypothetical trades) are in result.sample_trades; five synthetic Decimal audits are in MANUAL_DECIMAL_EXIT_LEG_AUDITS.json. CI_TEST_EXECUTION_EXACT_SHA.json distinguishes source/test hashes, exact committed test SHA, local focused execution and GitHub status; no docs-only green is used as code acceptance.",
        "",
        "Binance Vision attribution. Dataset-derived analytical results are CC BY-NC-SA4.0 for noncommercial historical research. [Official data format/checksums](https://github.com/binance/binance-public-data); [dataset terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md).",
    ]
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "DEVELOPMENT_27_CELL_RESULTS.md").write_text("\n".join(lines) + "\n")
    (DOCS / "EXIT_SIMULATOR_CONTRACT_AND_HAND_AUDITS.md").write_text(
        "# Exit simulator contract and hand audits\n\n"
        "Frozen numerical specification: EXPERIMENT_FROZEN_PROTOCOL.md and FROZEN_ROSTER_27_CELLS.json. "
        "Research-only Entry/ExitLeg are immutable; PositionState deduplicates fill IDs and conserves lot-rounded quantity. "
        "ResearchAccount is a separate independent monthly1000-USDT book. No broker or production imports.\n\n"
        "All five invented fixtures use price10000, stop9970 long/10030 short, declared BASE6/2/3bp per leg, "
        "event E=0, decision60000, fill120000. X2 fixture quantity.128BTC; other fixtures.127BTC. "
        "Each fixture, expected scalar, full per-leg ledger and SHA256 is in MANUAL_DECIMAL_EXIT_LEG_AUDITS.json.\n\n"
        "| Audit | Case | Independent expected net USDT | Observed |\n|---|---|---:|---:|\n"
        + "\n".join(
            f"| HAND{i} | {name} | {audits[i - 1]['independent_expected_net_USDT']} | {audits[i - 1]['observed_net_USDT']} |"
            for i, name in enumerate(
                [
                    "long stop",
                    "long three targets",
                    "TP1 then cost-inclusive protected stop",
                    "X2 half then3R",
                    "short three targets",
                ],
                1,
            )
        )
        + "\n\nTP1 intrabar239999 ACK300000, stop replacement360000 in HAND3; no retroactive protection. "
        "Entry fee is charged once on initial quantity; subsequent fees use actual exit quantity. "
        "Raw gross minus entry/exit friction and fees reconciles net within explicitly bounded eight-place rounding. "
        "The independent helper also reconciled five examples; its suspected rounding risk was not reproduced.\n\n"
        "Last-close dense MTM includes residual liquidation friction/fee. It is an ex-post measurement; "
        "account risk decisions only observe its two-minute-shifted prefix. The engine assumes an atomic protective bracket "
        "and conservative stop-first minute collisions, so real queue position/capacity/fills remain UNKNOWN. "
        "No simulated PnL is verified realized cash.\n"
    )
    (DOCS / "INDEPENDENT_FUTURE_VALIDATION_HANDOFF.md").write_text(
        "# Future validation boundary\n\n"
        f"Terminal {result['terminal']}; eligible candidates {result['top3_eligible']}. This measured negative campaign ends here. "
        "No28th strategy, post-result retuning, reserved-source access, or automatic Alpha promotion follows.\n\n"
        f"Controller can review registry/source identity at freeze {sources.FREEZE}, all54 score rows, "
        "the same-entry paired diagnostics, five hand audits and exact code/test/CI receipt. "
        "A future experiment requires a separate Controller dispatch, an independently reviewed candidate/source freeze, "
        "an independent agent and genuinely unexposed legally admitted data with explicit available-at assumptions. "
        "R2 reserved2024–2025 months remain closed. Gemini engineering work does not change this boundary.\n\n"
        "G2_ALPHA_AUTHORITY=NONE. REAL_FUNDS_AND_TESTNET_LIVE=NONE. "
        "No G1 DRY_RUN, real LLM/Feishu, brokerage/order, G3 or G4 permission is granted.\n"
    )


if __name__ == "__main__":
    build()
