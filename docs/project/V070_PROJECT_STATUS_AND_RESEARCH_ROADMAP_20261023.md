# V070 Project Status and Research Roadmap — 2026-10-23

**Status:** Research-first, one-shot historical discovery campaign. No strategy has passed the current project's positive after-cost evidence standard.

## 1. Executive decision

The first three registered V070 price-primary experiments are complete. Their terminal states are:

- PRIMARY-01 X_KER: INCONCLUSIVE; frozen candidate stopped because its own modeled ex-funding expectancy is negative under BASE and STRESS.
- PRIMARY-02 failed-escape reversal A: INCONCLUSIVE_STOP; frozen candidate stopped after its own costed expectancy and adjusted confidence-bound gates failed.
- PRIMARY-03 continuous-flow Ridge: INSUFFICIENT_SUPPORT; frozen candidate stopped before assessment economic labels because its predicted policy generated too few active decisions.

C1 is separately stopped before economics because its frozen active-interaction support was inadequate. R8-7 is a distinct V0.6.5/R8 historical experiment and must not be conflated with V070 PRIMARY-01.

**Current scientific conclusion: NO POSITIVE AFTER-COST STRATEGY ESTABLISHED.** This is not equivalent to proving every possible BTC strategy unprofitable. It means no current candidate has met the required evidence standard.

## 2. Authoritative state and preservation

- Research worktree: /root/workspace/project/quant-0.7.0/research-loop-bootstrap
- Observed branch: codex/research-loop-bootstrap
- Observed HEAD: 40c70c740f352d1b444decb75276196d17a72dd2
- Campaign registry: /root/workspace/project/crypto-data/lakehouse/research-loop-bootstrap-v070-20261022/registry
- Registry chain head after PRIMARY-03: 3597b81ba7963ebf70609b45a12b004e33406c9bb44909b0abac6d71ed828985
- Registry records 000001–000009: three one-shot PRIMARY trials, each with exactly one REGISTER, START and COMPLETE.
- Budget: 3/6 PRIMARY slots consumed; 3/6 unused and unassigned.
- The original 12 dirty research-loop paths, 29 protected identities, original registry events 000001–000006 and prior X_KER/A/C1 evidence were preserved.
- The PRIMARY-03 report and 45-entry delivery manifest were hash-verified. No code commit, push, production release, trading action or automatic next experiment occurred in that trial.
- This documentation update is on the documentation-only branch docs/engineering. It does not modify the executable v0.7.0 branch or the local research worktree.

The V070 campaign uses a frozen executable baseline and isolated study packages. A matching local HEAD does not, by itself, prove that every isolated research implementation is integrated into the remote v0.7.0 code branch.

## 3. Current research dashboard

| Candidate / track | Evidence | Terminal interpretation | Current action |
|---|---|---|---|
| PRIMARY-01 X_KER, 12h E0 | 14,681 common assessment opportunities; 5,122 active X_KER trades; active gross expectancy +4.4935bp; BASE active expectancy -11.5041bp; STRESS -27.5018bp | Relative improvement over X mostly reflects avoiding costs on rejected events. Candidate absolute economics fails. Full net is NULL. | Close exact candidate; no threshold or cost rescue |
| PRIMARY-02 A, failed-escape reversal, 4h E0 | 413 assessment events; gross +2.761237bp; BASE -13.238050bp; STRESS -29.237336bp; all four adjusted lower bounds negative; annual stability fails | Costed economics and inference gates fail. Funding/full net is NULL, so retain INCONCLUSIVE_STOP rather than claim a complete full-net rejection. | Close exact candidate |
| PRIMARY-03 continuous-flow Ridge, 8h E0 | 703 training origins; 1,452 common assessment origins; M1 active decisions 20 (13 LONG / 7 SHORT), 18 active weeks; model disagreement at 22 origins | Frozen support gate failed before assessment outcome labels. Economic expectancy, cost bridge and confidence bounds are NULL. | Close exact candidate; do not lower the 32bp hurdle or rerun |
| C1 active-I interaction | Native source QC passed; 25 active assessment events versus a frozen minimum of 100; 16 LONG / 9 SHORT versus 50 each | Insufficient support, not an economic loss result | Keep stopped; do not relax its interaction threshold |
| R8-7 X-only, separate V0.6.5 track | 545 frozen events; gross -3,081.95 USDT; BASE ex-funding -11,802.83 USDT; STRESS -20,523.72 USDT; BASE PF 0.719 | Its own frozen reference is economically negative; this is not the same specification or denominator as PRIMARY-01 | Keep closed; no delayed-entry or exit rescue |
| R9 liquidation-flow source track | Previously source-blocked; no new source authorization in this update | Source/PIT feasibility is separate from price-primary economics | Do not restart source hunting automatically |

Units reported in basis points are per unit entry notional per event/trade as specified by each source report. They are not account-level compounded returns. Cross-report means may use different denominators; compare only where the cited report explicitly defines a common denominator.

## 4. What has and has not been established

### Established

- The 36 frozen Binance Vision BTCUSDT USD-M 1-minute archives used in PRIMARY-01/02/03 passed the reported source hash/schema/coverage checks: 1,576,800 valid minute rows, 26,280 complete UTC hours, and zero reported missing minutes, duplicate rows or invalid rows.
- PRIMARY-03 completed four fixed Ridge fits using 703 common 2021 training origins and generated 1,452 common 2022–2023 assessment decisions.
- The new M0 is a six-feature price/activity baseline; M1 appends three volume-weighted native signed-taker-imbalance features F1/F4/F12. This is a different baseline definition from C1's original fourteen-feature M0.
- The three primary experiments were each registered and executed once. A failed or inconclusive registered trial consumes its slot.
- Frozen costs, event calendars, support gates and stopping rules were applied as specified in the corresponding reports.

### Not established

- No positive after-cost directional Alpha.
- No complete funding-inclusive full-net result for these candidates.
- No receiver-first-known point-in-time proof, executable order-book replay, actual fill or live profitability proof.
- No clean out-of-sample claim: 2021–2023 has substantial research exposure and was used as training/internal discovery.
- No account-capital-constrained PnL, liquidation-aware portfolio replay or real-money result.
- No evidence that deep learning, more indicators, or a larger model would fix the current failures.

## 5. Research decision and next roadmap

### Immediate state: close, do not auto-dispatch

1. Archive PRIMARY-03 as INSUFFICIENT_SUPPORT / STOP.
2. Keep PRIMARY-01 and PRIMARY-02 closed under their original terminal classifications.
3. Leave the three remaining PRIMARY slots unassigned.
4. Do not lower the 32bp policy threshold, alter the 12h calendar, expand the assessment window, tune Ridge, or replay any stopped candidate under a new label.
5. Do not read funding/mark payloads, protected 2024+ outcomes, or new historical sources as a side effect of this documentation update.

### Next decision: Astra independent mechanism review, not another immediate backtest

Astra should receive the current three-primary result ledger and produce at most two genuinely differentiated research hypotheses—or recommend NO_NEW_STRATEGY. Its task is discovery and falsification design only; it does not register a trial, read new market-value payloads, fit models, or backtest.

A proposed candidate must demonstrate all of the following before it can be considered for a future PRIMARY slot:

- A precise economic mechanism distinct from X_KER, failed-escape reversal A, C1's sparse active-I interaction, the continuous-flow Ridge policy, and the already tested R8-7 reference.
- A frozen observable Z and a fixed baseline X, with exact units, formulas, causal timestamps and source provenance.
- A pre-outcome support estimate using only authorized metadata/feature availability, not outcome-guided event selection.
- A common opportunity calendar and control that separate directional edge from reduced turnover or cash allocation.
- Explicit BASE/STRESS cost treatment, full event denominators, clustered uncertainty, annual/weekly stability and a stop condition.
- A separately reviewed source-use scope and explicit Owner authorization before any new historical outcome experiment.

If the candidate depends on an unadmitted observable, the next deliverable is source/rights/clock feasibility—not a proxy backtest.

## 6. ML and deep-learning roadmap

Do not escalate model complexity to compensate for failed strategy evidence.

1. First require a genuinely differentiated mechanism and a support-feasible, frozen experiment.
2. Use a low-capacity regularized baseline and a common fixed calendar.
3. Consider one bounded GBDT comparison only if a positive, costed linear result suggests a specific nonlinear residual.
4. Defer TCN/GRU/Transformer until a simpler model demonstrates incremental after-cost value and there is enough independent chronological/asset evidence.
5. Defer offline RL until fill counterfactuals, a common-capital simulator and a positive baseline exist.

The 1,576,800 minute rows are not 1,576,800 independent economic samples. Effective information is constrained by event frequency, clustered weeks, overlapping horizons, regime dependence and the number of actual decisions.

## 7. Evidence references

The following are local owner-workspace artifacts; they are not included as raw market data in this documentation branch.

- PRIMARY-01: /root/workspace/project/crypto-data/lakehouse/research-loop-bootstrap-v070-20261022/runs/PRICE_PRIMARY_01_XKER_12H_E0-20261022T080811Z/ECONOMIC_REPORT.md
  SHA-256: 855ce114b4dea7062d100a9c3af8c01e43dfb05e39c3226c9dbf23ad8d137801
- PRIMARY-02: /root/workspace/project/quant-0.7.0/a-failed-escape-isolated/a_failed_escape/execution-OWNER-V070-PRICE-PRIMARY-02-FAILED-ESCAPE-01/ECONOMIC_REPORT.md
  SHA-256: 33d14b128433f64bb4d5b2a18f1b9dd38355506aca7436ae99f1e531c3b47a3c
- PRIMARY-03: /root/workspace/project/quant-0.7.0/continuous-flow-ridge-01b-isolated/execution-OWNER-V070-CONTINUOUS-FLOW-RIDGE-03-01/ECONOMIC_AND_SUPPORT_REPORT.md
  SHA-256: 2a2a01d6e23effc6cb1bc33a3c5863cffc13f5725a07f3231ba6cb1e99be7fb7
- Astra fast closure review: /root/workspace/project/quant-0.7.0/astra-v070-fast-closure-20261023-yfzb2j3x/ASTRA_V070_FAST_STRATEGY_CLOSURE_REVIEW.md
  SHA-256: bb67bf27f994d44e58c4c92b7f472bf27c5168e769afaee47f241712a459b13b
- C1 native QA: /root/workspace/project/quant-0.7.0/c1-preflight-isolated/c1_native_qa/QA_REPORT.md
  SHA-256: b352b9c3aa83d23c225d7dcf12994c411d5fc3b4af3be68a95ed9102cc93b6ea

Source attribution: Binance Vision; no endorsement. Derived artifacts remain subject to applicable dataset terms and attribution requirements. This report does not grant public redistribution, commercial, production, funding/mark, or trading permission beyond the separately recorded Owner scope.

## 8. Terminal recommendation

**STOP all automatic strategy execution.** Close the three frozen candidates under their existing terminal states, keep three PRIMARY slots unassigned, and request one Astra independent mechanism-and-novelty review before selecting any further candidate. A NO_NEW_STRATEGY verdict is acceptable and preferable to spending the remaining budget on near-duplicate filters.
