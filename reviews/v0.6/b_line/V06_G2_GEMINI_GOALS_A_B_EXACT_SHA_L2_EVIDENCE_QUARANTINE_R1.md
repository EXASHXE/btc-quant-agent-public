# B-line Controller L2 — Gemini Goal A/B exact-SHA receipt, evidence quarantine and bounded correction gate

**Decision date:** 2026-10-12 Asia/Shanghai
**Controller:** ChatGPT-0 (B-line only). **Status:** A=RECEIVED_NOT_SCIENTIFICALLY_ACCEPTED; B=PARTIAL_DIAGNOSTIC_ACCEPTED__ASOF_REGIME_FAIL_CLOSED. No Alpha/OOS/holdout/testnet/live/real account authority.
**Original umbrella dispatch SHA:** c02743fddccdf517582c371a47e82d8dcbb05923
**Shared immutable source start:** 55ac4c631c69f6edbd275462ad23e4486b9782ed

## 1. GitHub exact-SHA verification and CI classification

| Work | Frozen commit | Result commit | Remote ancestry / scope |
|---|---|---|---|
| A: new entries | 83c0ef60d9eacfd2440fa223c57f042cfff4912f | efa0b302233800f6474b3dda5775be56a77d0860 | verified start -> freeze -> result; two commits; all changed paths in own g2_goal_entry_discovery_r2 namespace |
| B: H18 mechanism | ebb33b7f96e5ab0c753beab14363632a0a221416 | 397a62c1a0fbd6ad14a569a5be0058b1f684f08e | verified start -> freeze -> result; two commits; all changed paths in own g2_goal_h18_mechanism_r1 namespace |
| C: independent execution assurance | start itself | no result | current C remote HEAD still shared start; not finished |

**CI evidence:** A freeze run [38159750713](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38159750713) FAILURE because *unchanged historical H40 M3A* canonical graph hash test expected d5a962... actual ee185f...; summary **3094 passed, 1 failed, 2 skipped**. B final run [38161000757](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38161000757) FAILURE on the **same historical H40** assertion; summary **3088 passed, 1 failed, 2 skipped**. Classify as unrelated preexisting repository full-suite reproducibility debt; CI nevertheless remains red, not "PASS". A final CI run [38161124788](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38161124788) was **IN_PROGRESS at this Controller decision**, do not invent final result or say all green. Both task-local pytest were reported as PASS but do not supersede exact implementation conformance.

## 2. Goal A reception — economic negative is plausible, NOT accepted as clean frozen experiment

A report and machine summary describe four fixed entry families × 12/18h, 8 configurations, STRESS44 profit factors 0.35–0.61 and all eight negative account P&L; even BASE22 PF <1. Disclose as **unaccepted new-engine development-only negative observation**, not a definitive falsification of these hypotheses.

**BLOCKER A01: final result commit changed frozen replay semantics.** Frozen source \`scripts/strategy_research/g2_goal_entry_discovery_r2/run.py@83c0ef60...\` used continuous 2021–23 Full Last/Mark arrays and all funding events, while result \`@efa0b302...\` replaced them with a **prior-month + current-month window**, current-month Mark and funding, changed data-slicing/feature warmup scope, and newly added opposite-side control execution. This is NOT an evidence-only result commit, not byte-equal first freeze; input support/fold boundaries and potential signal selection may change. Code-after-freeze changes are disclosed by exact diff, but Stage 1 receipt's claim "immutable freeze" cannot by itself authorize the revised real-outcome engine. Do not simply label this an innocuous OOM packaging patch without a time-availability and semantic-equivalence proof independent of outcome.

**BLOCKER A02: human report contradicts committed machine annual rows.** Example C01 12h: report 2021 n=569 / 2022 n=549; machine \`GOAL_A_COMPLETE_ANALYSIS_TABLES.json\` year 2021 n=619 / 2022 n=499 (same 1118 aggregate), and the report's 3-year GROSS/fee cash numbers also diverge from summary. For C03 12h report 2021 4 and 2022 7 versus machine 5 and 6. A publication with non-matching yearly table cannot be an accepted authority; stop before inferring market regime or declaring a cohort definitively disproven.

**Gate for future bounded A correction** (not automatically dispatched): no re-optimization, no new 2021–23 configurations, no new historical outcome run merely to make metrics look better. First publish an exact two-version frozen-versus-delivered code diff and scientific reason; independent deterministic/synthetic proofs of equivalence or explicit non-equivalence for source feature warmup, candidate clock/set and accounting; reconcile report from immutable machine data and classify annual/date/cash measurement vs account. If not provably equivalent, invalidate historical A test as a clean preregistered run; require a new prospective method authority before any new development replay. Retain all negative records as exploratory evidence only.

## 3. Goal B reception — time-cap price/funding descriptive diagnostics only; as-of regime causal claims REJECTED

B report starts from known fixed R1 results: E0 STRESS W1 34 trades +11.2047bp, W2 55 trades +19.0135bp; H1 18h +48.5499/+41.4477bp and all 7/14-day familywise intervals cross zero. B reports E0 TIME_CAP W1 20 and W2 36, 26/56 adverse continuation after 12h and small right-tail TARGET concentration (claimed W1 4 TARGET episodes driving 98.06% increment; W2 3 driving 74.64%). These are **exploratory retrospective conditional price-path descriptions**. They are not a stable 18h effect, nor entry-time regime predictors, and the mechanism details remain qualified pending provenance reconciliation.

**BLOCKER B01: future information used under "as-of ENTRY" cohort label.** \`scripts/strategy_research/g2_goal_h18_mechanism_r1/run.py@ebb33b7f...\` and unchanged result \`@397a62c...\` read \`p.path24h.before12h.Last_MFE_R/Last_MAE_R\` for \`TREND_ALIGNED / COUNTERTREND\` at entry. Those extrema occur **AFTER entry, in [entry,entry+12h)**. The repo contains a correct previous-only 4h helper in \`regimes.py\`, but \`run.py\` does not call it. This is explicit known-at violation. Never use resulting trend-alignment rows as pre-entry causal evidence or design selection justification.

**BLOCKER B02: future funding state used as entry feature.** \`run.py\` derives \`funding_regime\` from \`e0['funding_settlements'][0]['source_rate_fraction']\`, which can settle AFTER position entry. Although \`regimes.py\` provides \`extract_funding_regime(funding_rates, signal_at_ms)\`, the submitted actual path does not use it. Declared \`as-of entry\` funding strata therefore are invalid.

**BLOCKER B03: predeclared volatility definition not actually implemented in results.** Freeze requires a previous-only 90-day completed 1h ATR(14)/price median, and \`regimes.py\` implements a helper. Actual \`run.py\` instead bins \`e0.get('risk_bps',300)\` at 300bp. This is a **different variable and threshold**. Do not use HIGH_VOL/LOW_VOL effect claims as if measured against preregistered volatility regime.

**BLOCKER B04: human annual table/skip rates internally contradict primary R1 and B machine receipts.** Original R1 STRESS W2 E0 2021 n10/2022 n21/2023 n24; B human Table 4 says W2 2021 n14 / 2022 n17 / 2023 n24. B whole-account table E0 skipped=0 though source R1 and B machine signal_collision report nonzero skipped. B Stage1 to result commit also changed \`run.py\` independent audit slippage cost specification (STRESS 16→6 bps and BASE 8→3 bps), selection/label and evidence writes; not purely evidence-only. Do not claim the machine and published table agree, or that post-freeze code was immutable.

**Gate for future bounded B correction** (not automatically dispatched): redline/withdraw causal regime assertions, produce machine-derived corrected tables, and document future information lineage with minimal exact event witnesses. Never use B's outcome-contaminated strata as signal filters or permission to run D1/D2. If a genuinely causal pre-entry regime investigation is desired, it is a **new experiment** needing prospective source+feature freeze and strict new development trial budget, not silent edits/replay of the previous frozen run. The previously published R1 aggregate E0/H1/H2 means and uncertainty remain the primary evidence.

## 4. Scientific action and concurrent Agent slots

- **A L2:** \`GOAL_A_RECEIVED_METHOD_FREEZE_DIVERGENCE_REPORT_UNRECONCILED\`, no new entry winner, no accepted clean negative scientific authority.
- **B L2:** \`GOAL_B_TIME_CAP_DESCRIPTION_PROVISIONAL_ASOF_REGIME_FAIL_CLOSED\`, no accepted as-of market-state prediction, no D1/D2 authorization.
- **C:** still at original branch start; **do not disrupt** its independent execution. C, if completed, may provide independent execution evidence but cannot retroactively repair A/B study outcomes.
- **Current blocker:** semantic equivalence and human-to-machine reconciliation (A); future time labels, alternate regime definitions and report mismatch (B); repo unrelated H40 hash CI debt. Do not waste cycles modifying H40 in this B-line scope.
- **Next Controller action:** finish narrow docs/semantic conformance gate on A/B with exact evidence if requested; after any new push, separately check remote HEAD, exact freeze-vs-result code difference and CI. No new Goal wave, no protected/testnet/live access, and no P1 engine restart.
