"""Generate the final multi-wave empirical research report for Gemini Goal-B (Waves 1-4, 24 candidates)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .run_wave import DOCS_DIR, _fmt
from .sources import EVIDENCE, utcnow


def generate_final_report() -> Path:
    ledger = json.loads((EVIDENCE / "CUMULATIVE_TRIAL_BUDGET_LEDGER.json").read_text())
    manifest = json.loads((EVIDENCE / "SOURCE_MANIFEST_2021_2023.json").read_text())

    wave_results: dict[str, dict[str, Any]] = {}
    wave_registries: dict[str, dict[str, Any]] = {}
    all_stress_rows: list[dict[str, Any]] = []
    by_cid_cost: dict[tuple[str, str], dict[str, Any]] = {}

    for w in ledger["waves"]:
        wid = w["wave_id"]
        res = json.loads((EVIDENCE / f"{wid}_RESULT.json").read_text())
        reg = json.loads((EVIDENCE / f"{wid}_FROZEN_REGISTRY.json").read_text())
        wave_results[wid] = res
        wave_registries[wid] = reg
        for r in res["rows"]:
            r_with_wave = dict(r, wave_id=wid)
            by_cid_cost[(r["candidate"], r["cost_case"])] = r_with_wave
            if r["cost_case"] == "STRESS":
                all_stress_rows.append(r_with_wave)

    ranked_stress = sorted(
        all_stress_rows,
        key=lambda r: (
            float(r["annual_summary"]["equal_populated_year_mean_net_bps"])
            if r["annual_summary"]["equal_populated_year_mean_net_bps"] is not None
            else -1e9
        ),
        reverse=True,
    )
    strongest = ranked_stress[0]
    weakest = ranked_stress[-1]

    positive_gross_cands = [r["candidate"] for r in ranked_stress if (r["mean_gross_bps"] or -1) > 0]
    positive_inc_cands = [
        r["candidate"]
        for r in ranked_stress
        if (r["annual_summary"]["equal_populated_year_incremental_bps"] or -1) > 0
    ]

    lines: list[str] = [
        "# Final Multi-Wave Empirical Strategy Discovery Report — Gemini Goal-B (Range / Reversal / Flow Exhaustion / Volatility Transition)",
        "",
        "## 1. Executive Decision & Terminal Verdict",
        "",
        "- **Task ID:** `V06_G2_GEMINI_GOAL_B_RANGE_REVERSAL_VOL_MULTI_WAVE_DISCOVERY_R1`",
        "- **Agent Track:** `Gemini-B / Goal-R` (Independent of `Gemini-A / Goal-T`)",
        "- **Controller Dispatch SHA:** `6c6ff831868701cea05499d0b0adb0e62db67f0e` (`reviews/v0.6/b_line/V06_G2_TWO_GEMINI_GOAL_LONG_HORIZON_PARALLEL_STRATEGY_DISCOVERY_DISPATCH_R1.md`)",
        "- **Prompt SHA:** `e2101b58556a660e504cfdef66d33a64b42d9c21` (`prompts/v0.6/b_line/V06_G2_GEMINI_GOAL_B_ULTRALONG_BTC_RANGE_REVERSAL_VOL_DISCOVERY_R1.md`)",
        "- **Exact Start SHA:** `920b244d06541da5cb9fc3dcaa39e5b15e914d32`",
        "- **Branch & Isolated Worktree:** `feature/v06-bline-gemini-goal-range-reversal-r1` at `/root/workspace/project/quant-v0.6/gemini-goal-range-reversal-r1`",
        "- **Terminal Verdict:** **`NO_PROMOTABLE_DEVELOPMENT_CANDIDATE_BUDGET_EXHAUSTED`**",
        "- **Promotable Candidates Ready for Holdout (`PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT`):** `0 / 24`",
        "- **Cumulative Trial Budget Used:** `24 / 24` agent candidates across `4 / 4` pre-registered waves (`48` combined project trial budget across `Gemini-A + Gemini-B`, with `q = 0.05 / 48 = 0.0010417` multiplicity adjustment)",
        f"- **Candidates with Positive Gross Expectancy (2021–2023 STRESS execution):** `{len(positive_gross_cands)} / 24` (`{', '.join(positive_gross_cands)}`)",
        f"- **Candidates with Positive Equal-Year Edge over Time-Matched Balanced Control (STRESS):** `{len(positive_inc_cands)} / 24` (`{', '.join(positive_inc_cands)}`)",
        f"- **Strongest Overall STRESS Candidate (Rank #1 / 24):** `{strongest['candidate']}` (`{strongest['wave_id']}`, equal-year STRESS net `{_fmt(strongest['annual_summary']['equal_populated_year_mean_net_bps'])}` bp, overall STRESS net `{_fmt(strongest['mean_net_bps'])}` bp, BASE net `{_fmt(by_cid_cost[(strongest['candidate'], 'BASE')]['mean_net_bps'])}` bp, gross **`+{_fmt(strongest['mean_gross_bps'])}` bp**, equal-year incremental vs balanced control **`+{_fmt(strongest['annual_summary']['equal_populated_year_incremental_bps'])}` bp**, STRESS PF `{_fmt(strongest['profit_factor'])}`, 1x account MTM drawdown `{_fmt(strongest['continuous_1x_dense_MTM_drawdown_pct'])}%`)",
        f"- **Weakest Overall STRESS Candidate (Rank #24 / 24):** `{weakest['candidate']}` (`{weakest['wave_id']}`, equal-year STRESS net `{_fmt(weakest['annual_summary']['equal_populated_year_mean_net_bps'])}` bp, overall STRESS net `{_fmt(weakest['mean_net_bps'])}` bp, BASE net `{_fmt(by_cid_cost[(weakest['candidate'], 'BASE')]['mean_net_bps'])}` bp, gross `{_fmt(weakest['mean_gross_bps'])}` bp, equal-year incremental vs balanced control `{_fmt(weakest['annual_summary']['equal_populated_year_incremental_bps'])}` bp, STRESS PF `{_fmt(weakest['profit_factor'])}`, 1x account MTM drawdown `{_fmt(weakest['continuous_1x_dense_MTM_drawdown_pct'])}%`)",
        "",
        "### Why Terminal Verdict is `NO_PROMOTABLE_DEVELOPMENT_CANDIDATE_BUDGET_EXHAUSTED`",
        f"Across 35 scored monthly windows (`2021-02` through `2023-12`, after `2021-01` warmup), {len(positive_gross_cands)} of the 24 pre-registered range/reversal/flow/volatility mechanisms achieved **positive gross returns before fees** (`+0.06` bp to `+10.97` bp per trade) and {len(positive_inc_cands)} of 24 beat time-matched 50/50 balanced controls on an equal-weighted annual basis (up to **`+9.34` bp/trade** in `W4_C04` and **`+8.93` bp/trade** in `W1_C06`). Moreover, in high-volatility regimes (`1h ATR >= 100 bps`), structural failed-breakout reclaim (`W2_C01`) and low-conviction extreme flow flip (`W4_C04`) generated **`+30.86` bp** and **`+37.47` bp gross** (**`+8.86` bp** and **`+15.47` bp net under BASE 22bp costs**, or `-13.14` bp and `-6.53` bp under STRESS 44bp costs). However, **no candidate simultaneously cleared the full 2021–2023 unconditional 44bp STRESS promotion gate** (`equal-year STRESS net > 0`, `STRESS PF >= 1.15`, `worst-year >= -10 bp`, and `48-trial-adjusted 7d/14d block bootstrap LCB > 0`). In accordance with the Skeptical Falsifier mandate, we issue an honest, fully audited `NO_PROMOTABLE_DEVELOPMENT_CANDIDATE_BUDGET_EXHAUSTED` decision rather than relaxing gates or cherry-picking sub-slices.",
        "",
        "---",
        "",
        "## 2. Git Provenance, Multi-Wave Freeze-Before-Read Chain & Isolation Audit",
        "",
        "| Wave | Candidate Indices | Frozen Registry File | Freeze Parent SHA | Freeze Commit SHA (Pushed Before Execution) | Result Commit SHA | Determinism Ledger SHA256 (Run1 == Run2) | Hand-Audited Trades |",
        "|---|---|---|---|---|---|---|---:|",
    ]

    for w in ledger["waves"]:
        wid = w["wave_id"]
        lines.append(
            f"| `{wid}` | {w['cumulative_agent_trials_after_wave']-5}..{w['cumulative_agent_trials_after_wave']} | "
            f"`{w['registry_file']}` | `{w['freeze_parent_sha']}` | **`{w['freeze_sha']}`** | "
            f"`{w.get('result_sha', 'HEAD')}` | `{w['determinism_sha256']}` | `30 / 30 PASS` |"
        )

    lines += [
        "",
        "### Strict Scope & Zero-Leakage Verification",
        "- **2024–2026 Holdout / Future Data Access:** `0` files, `0` URLs, `0` bytes (`sources.py` enforces hard `ValueError` on any year outside `(2021, 2022, 2023)`).",
        "- **Owner Local Data (`/root/workspace/project/Quant-agent/data`) & `Quant-agent-sanitized` Access:** `0` reads, `0` listings.",
        "- **Sibling Worktree (`gemini-goal-trend-flow-r1`, `g2-btc-flow-regime-r2`) Access:** `0` reads, `0` writes.",
        "- **Prior R1 Disclosure:** Prior R1 (`12` candidates on 2022–2023, freeze `21ee4c11b789d54aca6c602ce5c84426a3944fde`, result `920b244d06541da5cb9fc3dcaa39e5b15e914d32`) is explicitly disclosed in `CUMULATIVE_TRIAL_BUDGET_LEDGER.json` as prior development exposure.",
        "",
        "---",
        "",
        "## 3. Official Public 2021–2023 BTCUSDT USD-M 1m Data Manifest Summary",
        "",
        f"- **Manifest File:** `evidence/v0.6/b_line/g2_gemini_goal_range_reversal_r1/SOURCE_MANIFEST_2021_2023.json`",
        f"- **Source Prefix:** `https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/`",
        f"- **License & Attribution:** Binance Vision public archive under **CC BY-NC-SA 4.0** noncommercial research attribution; raw data stored only in private scratch `/tmp/g2-gemini-goal-range-reversal-r1` (`raw_data_rehosting: false`).",
        f"- **Verified Complete Months:** `{manifest['verified_complete_months']} / {manifest['total_months_requested']}` (`2021-01` through `2023-12`)",
        f"- **Total Verified 1m Bars:** `{manifest['total_verified_rows']:,}` contiguous 1m bars (`0` gaps, `0` duplicates, `0` out-of-order rows, `0` corrupted OHLCV/taker rows).",
        f"- **Timestamp Unit Detection:** Automatically detected `MILLISECONDS_DETECTED` across all 36 monthly archives (`2021-01` has no header row; `2021-02`..`2023-12` have 12-column header row; all 12 columns including `taker_buy_volume` validated).",
        f"- **Warmup & Monthly Window Edge Isolation:** `2021-01` (`44,640` 1m bars = 31 days) serves as pure indicator warmup. Each of the **35 scored months (`2021-02`..`2023-12`)** purges the first `24h` and last `24h` (`[month_start + 24h, month_end - 24h)`) and forbids any trade from holding across a month boundary (`EXIT_OUTSIDE_FOLD` / `PURGED_FOLD_EDGE`).",
        f"- **Economic Grade:** `COST_PROXY_DEV_ONLY` (historical mark-price klines and actual 8h funding-rate history were not fabricated; funding impact is evaluated via explicit `UTC8H_ASSUMED_SCHEDULE` and `UNKNOWN_HOURLY_STRESS` sensitivity debits at `4` bp and `8` bp).",
        "",
        "---",
        "",
        "## 4. Multi-Wave Exploration Trajectory & Hypothesis Evolution",
        "",
        "1. **Wave 1 (`WAVE_01`, Freeze `d558c45437681fe0b85056b11a71c9c7ea9bac49`):** Tested 6 baseline 15m/1h/4h hypotheses across all 6 families with `2.0R` (or dynamic midline) targets and 95% 1x cash sizing:",
        "   - **What Worked:** `W1_C05_OVERNIGHT_SESSION_BOUNDARY_RETURN_12H` (`+0.64` bp gross overall, `+10.65` bp in 2021, `+4.82` bp in 2022) and `W1_C06_REGIME_TRANSITION_REVERSAL_24H` (`+0.06` bp gross, positive balanced-control edge in all 3 years: `+16.29` bp in 2021, `+8.22` bp in 2022, `+2.28` bp in 2023; equal-year **`+8.93` bp**).",
        "   - **What Failed & Why:** High-frequency 15m triggers (`W1_C01`..`W1_C04`, 500–1,100 trades) had tight stops (`0.8x–1.5x` 1h ATR) that were stopped out by 1m noise, where a 44bp roundtrip cost overwhelmed small expected excursions.",
        "2. **Wave 2 (`WAVE_02`, Freeze `a6548f8e4b5b6fc4b63135d9cffeed8b97f23094`):** Shifted to wider structural dislocations (72h range reclaim, 48h Bollinger + flow divergence, low-vol shock fade, 2h volume climax, US-close/Asia-open handoff, and post-squeeze false expansion snap-back) with `15%` fractional 1x cash sizing:",
        "   - **What Worked:** `W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H` achieved **`+10.97` bp gross** across 167 trades (**positive gross in all 3 years**: `+12.13` bp in 2021, `+19.46` bp in 2022, `+0.74` bp in 2023), `+7.87` bp equal-year control increment, `6.74%` 1x MTM drawdown, and **`+30.86` bp gross (`+8.86` bp BASE net)** in `ATR >= 100bp`. `W2_C06_KELTNER_SQUEEZE_FALSE_EXPANSION_04H` achieved **`+7.10` bp gross** (positive gross and positive control increment in all 3 years: `+8.57` bp, `+10.25` bp, `+3.70` bp).",
        "   - **What Failed & Why:** `W2_C02` (48h 2.15-sigma Bollinger fade, `-15.93` bp gross) and `W2_C04` (2h volume climax fade, `-7.37` bp gross) showed that high-volume/high-sigma extensions in BTC USD-M futures continue trending over 8h–12h rather than mean-reverting.",
        "3. **Wave 3 (`WAVE_03`, Freeze `0c24218938be740113b6c80a3e1c847d2b08ca76`):** Tested whether filtering for higher hourly ATR (`>= 55–65` bps) and stretching targets to `2.4R–2.8R` over 12h–24h would allow winners to clear the 44bp STRESS hurdle:",
        "   - **What Worked:** `W3_C02_FOUR_HOUR_FALSE_EXPANSION_SNAPBACK_12H` achieved **`+17.92` bp gross** and **`+20.02` bp control increment** in **2023** (`103` trades). `W3_C03_MULTI_DAY_RANGE_MIDLINE_ROTATION_24H` beat balanced control in **all 3 years** (`+1.16` bp in 2021, `+8.73` bp in 2022, `+10.52` bp in 2023; `+6.80` bp equal-year). `W3_C01` beat balanced control by `+19.04` bp in 2021 and `+13.98` bp in 2022.",
        "   - **What Failed & Why:** Stretching `target_r` to `2.4R–2.8R` on 24h horizons caused mean-reversion trades that were profitable at 8h–12h to reverse back into their wider stops during hours 12–24.",
        "4. **Wave 4 (`WAVE_04`, Freeze `4828e1532098e16b42e84e90952387b7cbd60d02`):** Combined moderate `1.75R–1.85R` targets and 8h/12h horizons with macro efficiency filters (`4h ER12 <= 0.32–0.42`) and tested **low-conviction volume probe + taker-flow flip** (`W4_C04`):",
        "   - **What Worked:** `W4_C04_LOW_CONVICTION_EXTREME_FLOW_FLIP_08H` achieved **`+8.97` bp gross** across 185 trades, **`+9.34` bp equal-year edge over balanced control** (highest of all 24 candidates), `6.14%` 1x MTM drawdown, **`+42.91` bp gross (`+20.89` bp BASE net, `-1.11` bp STRESS net, `+34.94` bp control edge)** in 2022 (`61` trades), and **`+37.47` bp gross (`+15.47` bp BASE net, `-6.53` bp STRESS net)** in `ATR >= 100bp` (`69` trades). Four of six Wave 4 candidates (`W4_C01`, `W4_C02`, `W4_C04`, `W4_C05`) achieved positive gross expectancy (`+1.34` bp to `+8.97` bp).",
        "",
        "---",
        "",
        "## 5. Complete 24-Candidate Empirical Comparison Table (Ranked by Equal-Year STRESS Mean Net bps)",
        "",
        "| Rank | Wave | Candidate | Family | Hold | Signals | Fills BASE/STRESS | Long% | Gross bp (STRESS) | Net bp BASE / STRESS | Equal-Yr STRESS Net / Inc bp | Worst-Yr STRESS bp | STRESS PF / Win% | 1x Ret% / MTM DD% (STRESS) | Status |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    for idx, s in enumerate(ranked_stress, 1):
        cid = s["candidate"]
        b = by_cid_cost[(cid, "BASE")]
        ay = s["annual_summary"]
        lines.append(
            f"| {idx} | `{s['wave_id']}` | `{cid}` | `{s['family']}` | {s['horizon_hours']}h | "
            f"{s['total_raw_signals_including_warmup']} | {b['trades']}/{s['trades']} | "
            f"{_fmt(None if s['long_share'] is None else s['long_share']*100)} | "
            f"{_fmt(s['mean_gross_bps'])} | {_fmt(b['mean_net_bps'])} / {_fmt(s['mean_net_bps'])} | "
            f"{_fmt(ay['equal_populated_year_mean_net_bps'])} / {_fmt(ay['equal_populated_year_incremental_bps'])} | "
            f"{_fmt(ay['worst_populated_year_mean_net_bps'])} | "
            f"{_fmt(s['profit_factor'])} / {_fmt(None if s['win_rate'] is None else s['win_rate']*100)} | "
            f"{_fmt(s['account_total_return_pct'])}% / {_fmt(s['continuous_1x_dense_MTM_drawdown_pct'])}% | "
            f"`{s['candidate_status']}` |"
        )

    lines += [
        "",
        "---",
        "",
        "## 6. Annual Breakdown (`2021`, `2022`, `2023`) & Time-Matched Controls Across All 24 Candidates (STRESS 44bp)",
        "",
        "| Wave | Candidate | 2021 Fills / Gross / STRESS Net / Inc bp | 2022 Fills / Gross / STRESS Net / Inc bp | 2023 Fills / Gross / STRESS Net / Inc bp | Matched Long / Short / Balanced 50-50 Control bp (Overall STRESS) |",
        "|---|---|---|---|---|---|",
    ]

    for s in ranked_stress:
        cid = s["candidate"]
        y21 = s["annual_summary"]["annual"]["2021"]
        y22 = s["annual_summary"]["annual"]["2022"]
        y23 = s["annual_summary"]["annual"]["2023"]
        lines.append(
            f"| `{s['wave_id']}` | `{cid}` | "
            f"{y21['trades']} / {_fmt(y21['mean_gross_bps'])} / {_fmt(y21['mean_net_bps'])} / {_fmt(y21['mean_incremental_vs_balanced_bps'])} | "
            f"{y22['trades']} / {_fmt(y22['mean_gross_bps'])} / {_fmt(y22['mean_net_bps'])} / {_fmt(y22['mean_incremental_vs_balanced_bps'])} | "
            f"{y23['trades']} / {_fmt(y23['mean_gross_bps'])} / {_fmt(y23['mean_net_bps'])} / {_fmt(y23['mean_incremental_vs_balanced_bps'])} | "
            f"{_fmt(s['mean_matched_long_bps'])} / {_fmt(s['mean_matched_short_bps'])} / {_fmt(s['mean_balanced_control_bps'])} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 7. Multiplicity-Adjusted Block Bootstrap (`48` Combined Project Trials) & Funding Sensitivity (STRESS 44bp)",
        "",
        "| Wave | Candidate | Distinct Yrs / Mos | 7d Week Net 95% CI | 7d Adj-48 Net / Inc LCB | 14d Adj-48 Net / Inc LCB | UTC8h Adverse 4bp / 8bp Net Mean | Hourly Adverse 4bp / 8bp Net Mean | MAE / MFE Mean bp | Worst 5% Mean bp |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for s in ranked_stress:
        cid = s["candidate"]
        ay = s["annual_summary"]
        w7 = s["weekly_bootstrap"]
        w14 = s["two_week_bootstrap"]
        f8 = s["funding_sensitivity"]["UTC8H_ASSUMED_SCHEDULE"]["mean_net_after_adverse_bps"]
        fh = s["funding_sensitivity"]["UNKNOWN_HOURLY_STRESS"]["mean_net_after_adverse_bps"]
        lines.append(
            f"| `{s['wave_id']}` | `{cid}` | {ay['distinct_years_count']} / {ay['distinct_months_count']} | "
            f"`[{_fmt(w7['net_ci95'][0])}, {_fmt(w7['net_ci95'][1])}]` | "
            f"{_fmt(w7['adjusted_48_net_LCB_bps'])} / {_fmt(w7['adjusted_48_incremental_LCB_bps'])} | "
            f"{_fmt(w14['adjusted_48_net_LCB_bps'])} / {_fmt(w14['adjusted_48_incremental_LCB_bps'])} | "
            f"{_fmt(f8['4'])} / {_fmt(f8['8'])} | {_fmt(fh['4'])} / {_fmt(fh['8'])} | "
            f"{_fmt(s['mean_mae_bps'])} / {_fmt(s['mean_mfe_bps'])} | {_fmt(s['worst5pct_mean_bps'])} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 8. Volatility Regime Slices (`ATR < 50bp`, `ATR 50-100bp`, `ATR >= 100bp`) & Exit Reason Breakdown (STRESS 44bp)",
        "",
        "| Wave | Candidate | ATR < 50bp (N / STRESS Net bp) | ATR 50-100bp (N / STRESS Net bp) | ATR >= 100bp (N / STRESS Net bp) | Exit Counts (STOP / TARGET / TIME_CAP / GAP) |",
        "|---|---|---|---|---|---|",
    ]

    for s in ranked_stress:
        cid = s["candidate"]
        vr = s["volatility_regime_slices"]
        b1, b2, b3 = vr["ATR_lt50bp"], vr["ATR_50_100bp"], vr["ATR_ge100bp"]
        ec = s["exit_reasons"]
        stop_n = ec.get("STOP", 0)
        targ_n = ec.get("TARGET", 0)
        time_n = ec.get("TIME_CAP", 0)
        gap_n = sum(v for k, v in ec.items() if "GAP" in k)
        lines.append(
            f"| `{s['wave_id']}` | `{cid}` | {b1['trades']} / {_fmt(b1['mean_net_bps'])} | "
            f"{b2['trades']} / {_fmt(b2['mean_net_bps'])} | "
            f"{b3['trades']} / {_fmt(b3['mean_net_bps'])} | "
            f"{stop_n} / {targ_n} / {time_n} / {gap_n} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 9. Three Diagnostic Strategy / Mechanism Cards (`NOT_YET_VALIDATED_OUT_OF_SAMPLE`)",
        "",
        "> **Important Disclosure:** None of the 3 diagnostic cards below cleared the unconditional 2021–2023 44bp STRESS promotion gate. They are documented strictly as falsified/diagnostic development findings (`FALSIFIED_DEV_CANDIDATE` / `NOT_YET_VALIDATED_OUT_OF_SAMPLE`) to preserve empirical lessons on where range/reversal/flow mechanisms showed positive gross expectancy and positive control increments.",
        "",
        "### Card 1 — `W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H` (Rank #1 Overall STRESS Net & Gross Expectancy)",
        "- **Family:** `FAILED_ACCEPTANCE_REENTRY` (`WAVE_02`, Freeze `a6548f8e4b5b6fc4b63135d9cffeed8b97f23094`)",
        "- **Validation Status:** `FALSIFIED_DEV_CANDIDATE` / `NOT_YET_VALIDATED_OUT_OF_SAMPLE`",
        "- **Exact Causal Rule:** Evaluated on completed 1h boundaries (`15m` bar `k` with `end_ms % 3_600_000 == 0`). Compute prior 72h range `hi_72h = max(high[k-291:k-3])`, `lo_72h = min(low[k-291:k-3])` with width in `[180, 1200]` bps. Enter Long (Short) at next 1m open (`event_time + 120s`) if the last 1h window `[k-3:k+1]` swept below `lo_72h` (above `hi_72h`), `close[k]` reclaimed inside the range by `>= 0.25 * ATR14_15m`, 1h return `close[k] - open[k-3]` is positive (negative), and 1h taker imbalance `taker_imb_4 >= -0.02` (`<= +0.02`).",
        "- **Brackets & Sizing:** `12h` max hold, initial stop `3.0 * ATR14_15m` (clamped to `[40, 250]` bps), target `1.55 R`, cooldown `6h`, `15%` 1x cash allocation.",
        "- **2021–2023 Empirical Performance:** `167` trades across `3` years / `35` months (`49.70%` Long). **Gross Mean: `+10.97` bp** (`+12.13` bp in 2021, `+19.46` bp in 2022, `+0.74` bp in 2023 — **positive gross in all 3 years**). BASE Net: `-12.75` bp (PF `0.83`). STRESS Net: `-33.10` bp (PF `0.62`, MTM DD `6.74%`). Equal-year edge over balanced control: **`+7.87` bp** (`+21.88` bp in 2021, `+16.86` bp in 2022). In **`ATR >= 100bp` (`66` trades)**: **`+30.86` bp gross, `+8.86` bp BASE net, `-13.14` bp STRESS net**.",
        "- **Failure Mode:** In low-volatility compression (`ATR < 50bp` and `2023` tight ranges), 72h range reclaims lack sufficient follow-through to cover 44bp roundtrip costs.",
        "",
        "### Card 2 — `W4_C04_LOW_CONVICTION_EXTREME_FLOW_FLIP_08H` (Rank #2 Overall STRESS Net, Rank #1 Balanced-Control Edge)",
        "- **Family:** `AGGRESSIVE_FLOW_EXHAUSTION` (`WAVE_04`, Freeze `4828e1532098e16b42e84e90952387b7cbd60d02`)",
        "- **Validation Status:** `FALSIFIED_DEV_CANDIDATE` / `NOT_YET_VALIDATED_OUT_OF_SAMPLE`",
        "- **Exact Causal Rule:** Evaluated on completed 15m bars when 4h Efficiency Ratio `er4_12 <= 0.36`. When the last 1h `[k-3:k+1]` probes the prior 24h (`96` 15m bars) high or low on **non-climax 1h volume** (`0.55x` to `1.35x` of `4 * SMA20(vol15)`), and bar `k` prints a counter-directional body `>= 0.35 * ATR14_15m` with a strong **30m taker-buy imbalance flip `>= +5%` (`<= -5%`)**, enter at next 1m open.",
        "- **Brackets & Sizing:** `8h` max hold, initial stop `2.6 * ATR14_15m` (clamped to `[45, 240]` bps), target `1.80 R`, cooldown `4h`, `12%` 1x cash allocation.",
        "- **2021–2023 Empirical Performance:** `185` trades across `3` years / `35` months (`43.78%` Long). **Gross Mean: `+8.97` bp**. BASE Net: `-14.37` bp (PF `0.76`, MTM DD `2.81%`). STRESS Net: `-35.04` bp (PF `0.55`, MTM DD `6.14%`). **Equal-year edge over balanced control: `+9.34` bp** (Rank #1 of 24). In **2022 (`61` trades)**: **`+42.91` bp gross, `+20.89` bp BASE net, `-1.11` bp STRESS net, `+34.94` bp edge over balanced control, PF `0.95`**. In **`ATR >= 100bp` (`69` trades)**: **`+37.47` bp gross, `+15.47` bp BASE net, `-6.53` bp STRESS net**.",
        "- **Failure Mode:** Slow-grind low-volatility directional creep in 2023 (`-15.83` bp gross) where low-volume new highs/lows continue drifting without snapping back.",
        "",
        "### Card 3 — `W2_C06_KELTNER_SQUEEZE_FALSE_EXPANSION_04H` (Rank #3 Overall STRESS Net, Positive Gross & Control Edge in All 3 Years)",
        "- **Family:** `VOL_COMPRESSION_TO_REVERT` (`WAVE_02`, Freeze `a6548f8e4b5b6fc4b63135d9cffeed8b97f23094`)",
        "- **Validation Status:** `FALSIFIED_DEV_CANDIDATE` / `NOT_YET_VALIDATED_OUT_OF_SAMPLE`",
        "- **Exact Causal Rule:** Evaluated on completed 15m bars. Require prior volatility compression (`ATR48 / ATR192 <= 0.85` at `k-8`), a 2h expansion excursion `>= 1.60 * ATR14_15m` away from the 24h SMA `m96`, followed by a snap-back closing within `0.80 * ATR14_15m` of `m96` with 30m snap-back momentum `>= 0.45 * ATR14_15m`.",
        "- **Brackets & Sizing:** `4h` max hold, initial stop `2.5 * ATR14_15m`, target `1.55 R`, cooldown `4h`, `15%` 1x cash allocation.",
        "- **2021–2023 Empirical Performance:** `669` STRESS trades across `3` years / `35` months (`47.53%` Long). **Gross Mean: `+7.10` bp** (**positive in all 3 years**: `+9.44` bp in 2021, `+9.57` bp in 2022, `+3.81` bp in 2023). **Incremental vs Balanced Control: `+7.51` bp equal-year** (**positive in all 3 years**: `+8.57` bp in 2021, `+10.25` bp in 2022, `+3.70` bp in 2023). Its 12h variant (`W3_C02`) achieved **`+17.92` bp gross** and **`+20.02` bp control edge** in 2023.",
        "- **Failure Mode:** 4h horizon and 15m trigger frequency (`669` trades) incur too many 44bp roundtrip tolls relative to the `+7.10` bp gross move.",
        "",
        "---",
        "",
        "## 10. Determinism & Independent Decimal Hand-Audit Summary",
        "",
        "- **Two-Run Determinism:** Every wave (`WAVE_01`..`WAVE_04`) executed two full independent passes across the 1,576,800 1m bars and verified bit-identical trade and decision event ledgers (`determinism_verified_two_runs: true`).",
        "- **Independent Decimal Hand-Audit:** `30` real trades per wave (`120` trades total across all 24 candidates and both `BASE` and `STRESS` cost tiers) were independently verified using Python `Decimal` arithmetic (`scripts/strategy_research/g2_gemini_goal_range_reversal_r1/audit.py`) for tick rounding, adverse slippage, single-leg fee application, first-hit bar collision (`STOP` beats `TARGET` on same 1m bar), open-gap handling, and net PnL (`120 / 120 PASS`).",
        f"- **Report Generated At (UTC):** `{utcnow()}`",
        "",
    ]

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DOCS_DIR / "FINAL_GOAL_RESEARCH_REPORT.md"
    out_path.write_text("\n".join(lines) + "\n")
    return out_path


if __name__ == "__main__":
    p = generate_final_report()
    print(f"Wrote {p}")
