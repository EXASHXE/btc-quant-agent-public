# v0.6 B-line Controller — Gemini A/B/C Goal R2 exact-SHA L2 adjudication

**Date:** 2026-10-12 Asia/Shanghai. **Authority:** ChatGPT-0 B-line Controller only. **Disposition:** ACCEPT_BOUNDED_DIAGNOSTIC_EVIDENCE__NO_POLICY_PROMOTION. **Original R2 authorization SHA:** `1172d3a91324c1a7379bc9e5c24ef601076547c2`. The three Gemini sessions are finished and pushed, not automatically accepted as scientific or release authority.

## 1. Exact remote GitHub evidence and CI truth

| Track | Remote start | First method freeze commit | Remote result HEAD | Evidence identity | CI |
|---|---|---|---|---|---|
| **A R2**: Entry-replay frozen semantics | `efa0b302233800f6474b3dda5775be56a77d0860` | `d45b9e9f2c82203336c263662ecc7c6e742f7b84` | `9415441f216b2eaca6078102cf7ec05b8e6b57cf` | Exactly 2 commits, own namespace; but final commit **modified frozen differential_harness.py** | [38172524824](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38172524824) FAILURE: 3137 passed, 1 failed, 2 skipped; unrelated inherited H40 canonical hash |
| **B R2**: Causal as-of regimes | `397a62c1a0fbd6ad14a569a5be0058b1f684f08e` | `aa73187bf2f535a17a64b894ccb07211928ad4a9` | `d5e3a8407b1b84111dc7f4276865ffd68cb0a7d2` | Exactly 2 commits, own namespace; final commit **added run.py and substantially expanded asof_features.py**, not only reports/evidence | [38169874800](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38169874800) FAILURE: 3130 passed, 1 failed, 2 skipped; same inherited H40 hash |
| **C R2**: Margin, execution and freeze truth | `f381dd73a8c583e2a28dcab2e354b019b1d946fa` | `0aa7c2fd8457ea64b343239ff7bc4c08d3c56b3f` | `c9846adacc1f2df85931ecf4649e02a3a61cf466` | Exactly 2 commits, own namespace, **final evidence/docs only**; frozen code untouched | [38171532977](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38171532977) SUCCESS but **docs/evidence-only lane, Ruff/type/pytest skipped**, not proof of full suite pass |

**Remote ancestry, parent SHA and changed-file scope:** checked against GitHub commits and compare. CI failure in A/B is inherited `tests/test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph` (expected `d5a962...`, got `ee185f...`), not any new R2 failing test. Do not state A/B "green"; do not repair H40 in this B-line scope.

## 2. Track-specific science adjudication

### A: `A_R2_NON_EQUIVALENT_R1_FROZEN_METHOD_INVALID` — ACCEPT AS NEGATIVE FORENSIC FINDING, NOT CLEAN PREREGISTERED RESULT

Report: [Goal A R2 differential conformance](https://github.com/EXASHXE/btc-quant-agent-public/blob/9415441f216b2eaca6078102cf7ec05b8e6b57cf/docs/strategy_research/g2_goal_a_conformance_r2/GOAL_A_CONFORMANCE_REPORT.md).

A's published sidecar contrasts two semantics: (1) continuous 36-month Last/Mark/Funding history vs (2) previous+current-month streaming arrays. For C01/C02/C03 (6 horizon configs), published STRESS and BASE comparisons report same signal/trade event IDs and account balances. For C04 (12h/18h), 1,227 vs 1,225 signals, and STRESS 455 vs 454 (12h) / 445 vs 444 (18h) trades, because ATR(168) Wilder smoothing preserves historical seed memory beyond a 1-month warmup, crossing decision threshold. That is a scientifically MATERIAL `frozen_vs_delivered` non-equivalence even when average PF difference appears small. The old 8-config R1 entry study **cannot** receive pristine first-freeze authority; report C04 as exploratory only. Negative STRESS PF 0.35–0.61 for delivered candidates does not prove no possible BTC alpha.

A's machine-year reconciliation corrected C01 12h 2021/2022 619/499 vs human 569/549, C03 2021/2022 5/6 vs 4/7; correct numbers from existing machine, not human report. Critically C01 2023 zero executed trades reflects **capital exhaustion after 2022** ($17.02 USDT ending cash, 6,288 signals rejected by lot/budget) rather than signal absence. Never interpret C01 zero 2023 fills as a regime in which signals did not appear. Opposite-direction fixed-quantity controls are NOT executable alternative policies.

**Independent Controller procedural caveat:** R2 final commit changed its own frozen `differential_harness.py`: replaced references to non-existent `exit_year` field with `time.gmtime(entry_at)` in the annual report logic and replaced missing `fee_total_usdt` with `fee_entry+fee_exit`. These are plausible *measurement bug repairs*, not observed trading signal threshold changes, but happened AFTER method-freeze commit and violate literal two-stage immutable runner contract. Sidecar imports shared original `signals/account` code and implements the two caller/window modes; Controller did not independently rerun all 35 months. Hence keep A-R2 diagnostic as a corroborated discrepancy receipt, **not independent unconditional scientific PASS**. Do not re-run/fix only to chase eligibility.

**L2 outcome:** `A_R2_BOUNDED_DIAGNOSTIC_ACCEPT__ENTRY_R1_C04_FREEZE_INVALID`. Holdout access / new strategy promotion = NO.

### B: `B_R2_ASOF_LABELS_CAUSALLY_RECONSTRUCTED_DEVELOPMENT_ONLY` — ACCEPT RETROSPECTIVE CAUSAL-LABEL ADDENDUM WITH PROVENANCE CAVEAT

Report: [Goal B R2 as-of corrected mechanism](https://github.com/EXASHXE/btc-quant-agent-public/blob/d5e3a8407b1b84111dc7f4276865ffd68cb0a7d2/docs/strategy_research/g2_goal_b_asof_repair_r2/B_R2_CORRECTED_MECHANISM_REPORT.md).

B R1 trend bins using post-entry 12h MFE/MAE, future first Funding settlement and volatility based on initial `risk_bps` are **REVOKED**. B R2 published public-source as-of signal-decision features for 89 events: completed preceding 4h Last trend, preceding-only 90d completed 1h ATR(14)/price, and previous settled Funding. W1 = 34, W2 =55; all labeled directionally TREND_ALIGNED (unsurprising for selected momentum systems); W1 high/low vol 20/14 and W2 27/28; negative funding W1 n7 underpowered. Statistical positivity by regime remains **exploratory post-selection only**, not an entry-time predictive effect, no conditional 18h policy. The old 14d adjusted H1-E0 interval and B R2 recomputation both include 0 (different values due resampling specifications); H1 18h point advantage is supported by a few 12–18h target completions (W1 4, W2 3) but NOT statistically proven. B human W2 annual counts fixed to 10/21/24 for 2021/22/23, and E0 blocked counts 42 W1, 46 W2 (they are not zero).

**Independent Controller procedural caveat:** B R2 result commit added a substantial new `run.py` and appended ~90 code lines to `asof_features.py` after its purported method code freeze. Even if primarily orchestration/formatting, it breaches evidence-only final-commit discipline. Causal as-of timestamp evidence is executor-supplied rather than independently rerun by Controller. This is NOT a clean preregistered new feature efficacy test, and no B-R2 result may justify choosing high-vol/funding state based on hindsight without fresh prospective authority.

**L2 outcome:** `B_R2_POSTHOC_ASOF_DIAGNOSTIC_ACCEPT__NO_CONDITIONAL_POLICY`.

### C: `C_R2_MARGIN_RISK_EVIDENCE_RECONCILED_SYNTHETIC_ONLY` — BOUNDED LEDGER AND SCENARIO-TRUTH ACCEPTED

Report: [Goal C R2 margin/exposure reconciliation](https://github.com/EXASHXE/btc-quant-agent-public/blob/c9846adacc1f2df85931ecf4649e02a3a61cf466/docs/strategy_research/g2_goal_c_risk_assurance_r2/BTC_GOAL_C_R2_RISK_ASSURANCE_RECONCILIATION_REPORT.md).

Corrected C-R1 naive 10x/15x no-TP1 scenario filter is 10 cases, not 6: 5/10 simulated liquidation-before-planned-stop and 7/10 simulated isolated gap deficits; old human 7/6 was an impossible hardcoded denominator. Even this filtered ratio is synthetic-only and includes multiple hypothetical MMR, shocks and sizing choices; not a rate of actual exchange liquidation. C-R1 "risk capped" scenario used hidden discretionary margin topup above N/L, reducing effective isolated leverage to about 8.3–8.7x for nominal 15x. Under strict N/L posted margin assumption, 3/6 risk-capped 10x/15x cases liquidate under the toy shock. Account 20-cell replay has 890 order-ledger trades, 0 reserve breaches, 0 notional/Mark-equity >1x minutes; actual E0 peak ratios reconstructed W1 BASE .940370 STRESS .943953 / W2 BASE .934337 STRESS .935323, **not zero**. Original initial-stop distance actual maxima W1 3.6120% and W2 3.5591% (not synthetic 7.5%, not unstopped excursion 10–11%). Standalone synthetic 15x liquidation move under cited 40–100bp MMR + buffers ~4.43–5.02%; a 3.61% adverse mark move alone does NOT prove pre-stop liquidation. >4.43–5.02% Mark wick and stop-gap tails matter. C R2 24 deep real-case and full 890-ledger Decimal recheck cited, no material cash/remaining quantity/fee/Funding mismatch within retained sampled source. C R1's historical three-commit freeze repair remains `POST_FREEZE_REPAIR_NOT_PREACCEPTED` even though economic modules were unchanged.

**Material UNKNOWN:** exact historic exchange maintenance brackets, account-specific fee tiers, L2 maker queue, sub-minute stop/TP collision, true exchange Funding Mark and latency. Synthetic 56-case R2 cannot turn 10/15x risk into real-market validation. CI final docs-only skipped execution tests; Controller did not independently run local datasets.

**L2 outcome:** `C_R2_BOUNDED_MATH_AND_REPORT_RECONCILIATION_ACCEPTED__LIVE_EXECUTION_UNKNOWN`.

## 3. Next gate and research policy

**Do NOT dispatch repetitive three-way "repair-to-green" goals solely to erase provenance debt**. A (except C04 frozen validity) and B have supplied developer-relevant negative/causal diagnostic, and C execution math is substantially independently checked. Original scientific blocker remains **no independently verified positive after-cost Alpha**, 18h max-horizon improvement still has simultaneous adjusted CI crossing zero, limited year stability / ex-post exposure of 48 previous entry trials+8 exit contrasts, and missing live execution observability. No promotion to chronological protected holdout, P1 replacement, TESTNET, LIVE, or real funds.

Priorities for a future Controller-authorized task (not yet dispatched):
1. **Scientific method next wave**: preregister *genuinely different* new entry mechanism(s) beyond repeated old breakout/mean-reversion, with causal feature availability and conservative fee/queue/funding/Mark, independent original signal/control and live 4–24h time-exit/stop/partial TP mechanics, finite candidate and search budgets; choose out-of-exposure independent evaluation only after new separate authority and data admission. Do NOT automatically use 2024–25.
2. **Execution model next wave**: separate non-ordering offline instrument/exchange-spec source admission and Mark vs Last execution uncertainty, known-as-of exchange leverage bracket and reduceOnly/ACK semantics, synthetic verified liquidation, not deployment.
3. **Independent next review**: one separately frozen scientific auditor adjudicates whether more 2021–23 development scans provide information or whether holdout must remain sealed; do not use 2024–25 opportunistically.

A-line, Performance and earlier v0.5.5 authority remain entirely separate, unchanged.
