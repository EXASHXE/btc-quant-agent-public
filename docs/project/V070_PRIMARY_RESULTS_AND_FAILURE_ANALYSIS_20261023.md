# V070 PRIMARY-01 to PRIMARY-03 — Research Results and Failure Analysis

**As of 2026-10-23.** This report consolidates the three completed registered trials in the V070 price-primary campaign. It does not combine them with the separate V0.6.5/R8 experiments.

## 1. Summary

| Trial | Frozen question | Actual result | What it means |
|---|---|---|---|
| PRIMARY-01 X_KER | Does a path-efficiency filter improve a frozen 12h continuation policy? | INCONCLUSIVE; operational STOP | Relative results improve, but the candidate remains negative after modeled costs. |
| PRIMARY-02 failed-escape A | Does reversing a failed 24h range escape beat continuation and cash after costs? | INCONCLUSIVE_STOP; operational STOP | Gross expectancy is positive but too small to cover modeled BASE/STRESS charges; statistical and year-stability gates fail. |
| PRIMARY-03 continuous-flow Ridge | Do continuous F1/F4/F12 features improve a six-feature price/activity Ridge policy? | INSUFFICIENT_SUPPORT; operational STOP | The frozen policy produces too few M1 actions; assessment economics was not computed. |

None of these dispositions is a positive Alpha result. PRIMARY-01/02 have negative modeled ex-funding candidate economics; PRIMARY-03 has no measured assessment economic outcome.

## 2. PRIMARY-01 — X_KER

Frozen trial: PRICE_PRIMARY_01_XKER_12H_E0.

- 36 frozen Binance Vision BTCUSDT USD-M 1m archives passed source QC; 1,576,800 valid minutes and 26,280 complete hours.
- Fixed 2022–2023 assessment: 14,681 common X opportunities and 5,122 active X_KER trades; 105 UTC assessment week blocks.
- Candidate gross active-trade expectancy: +4.4935bp.
- Candidate BASE active-trade expectancy: -11.5041bp; STRESS: -27.5018bp.
- On the common 14,681-opportunity calendar, X_KER BASE mean is -4.0136bp and STRESS mean is -9.5950bp. Full net is NULL because funding/mark evidence was not admitted.
- Paired X_KER-minus-X improvement is +11.8843bp BASE and +22.3027bp STRESS on the common denominator. The gross paired improvement is only +1.4659bp; most of the difference is avoided modeled cost on the 9,559 filtered-out X opportunities.
- Candidate absolute adjusted lower bounds fail under both frozen cost scenarios. Relative improvement against a losing baseline is not evidence of positive standalone economics.
- Terminal classification remains INCONCLUSIVE because full net is unknown; operational decision is STOP the frozen candidate.

This is a classic turnover-filter trap: a filter can improve the comparison by declining to trade, while its own traded events still lose after costs. Do not relabel the avoided-cost effect as directional Alpha.

Primary evidence: local report path /root/workspace/project/crypto-data/lakehouse/research-loop-bootstrap-v070-20261022/runs/PRICE_PRIMARY_01_XKER_12H_E0-20261022T080811Z/ECONOMIC_REPORT.md. SHA-256: 855ce114b4dea7062d100a9c3af8c01e43dfb05e39c3226c9dbf23ad8d137801.

## 3. PRIMARY-02 — failed-escape reversal A

Frozen trial: PRICE_PRIMARY_02_FAILED_ESCAPE_4H_E0.

- The 413-event 2022–2023 assessment passed the frozen source and support gates; both directions were adequately represented under the original support contract.
- Candidate gross expectancy: +2.761237bp per event.
- Candidate BASE expectancy: -13.238050bp; STRESS: -29.237336bp.
- Paired candidate-minus-continuation mean is approximately +6.30bp at both cost levels, but this does not rescue the candidate's negative absolute economics.
- All four predeclared multiplicity-adjusted lower-bound gates fail.
- Candidate absolute means are negative in both 2022 and 2023 under both costs. Best-week removal does not rescue absolute expectancy.
- Funding, mark and full-net results remain NULL. The experiment therefore closes as INCONCLUSIVE_STOP, not as a claim that all failed-breakout reversal strategies are universally unprofitable.

The important distinction from PRIMARY-01 is that A's candidate and continuation control used the same 413 scheduled events. Its relative advantage was not primarily caused by reducing the number of trades. However, relative advantage over a losing control is insufficient when the candidate's own costed expectancy remains negative.

Primary evidence: local report path /root/workspace/project/quant-0.7.0/a-failed-escape-isolated/a_failed_escape/execution-OWNER-V070-PRICE-PRIMARY-02-FAILED-ESCAPE-01/ECONOMIC_REPORT.md. SHA-256: 33d14b128433f64bb4d5b2a18f1b9dd38355506aca7436ae99f1e531c3b47a3c.

## 4. PRIMARY-03 — continuous-flow Ridge

Frozen trial: PRICE_PRIMARY_03_CONTINUOUS_FLOW_RIDGE_8H_E0.

- The actual Owner decision passed the existing authority gate. Exactly one REGISTER, START and COMPLETE was appended.
- All 36 source archives passed QC: 1,576,800 valid minute rows, 26,280 complete hours, zero reported missing minutes, duplicates or invalid rows.
- 703 mature 2021 training origins were used for four fixed LONG/SHORT Ridge fits.
- The 2022–2023 common assessment calendar contains 1,452 feature-valid origins with 100% reported price/reference coverage.
- M0 generated 26 active decisions (12 LONG, 14 SHORT) and 1,426 CASH decisions.
- M1 generated 20 active decisions (13 LONG, 7 SHORT) and 1,432 CASH decisions.
- M1 active decisions occurred in 18 UTC weeks, with 13 LONG and 7 SHORT; the frozen requirement was at least 150 active decisions, 50 each side, 26 active weeks and 12 weeks per side. The active count, both directional counts, total active weeks and SHORT active weeks fail.
- M0/M1 decisions disagree at 22 origins across 21 weeks. This is a support descriptor, not evidence of positive economics or adequate statistical power.
- The worker stopped before assessment economic labels. GROSS/BASE/STRESS expectancy, actual turnover, exit cost bridge, annual economic stability, best-week removal and all four confidence bounds are NULL/NOT COMPUTED. Funding/full net is also NULL.

This is not a measured economic loss and does not prove that continuous signed flow has no information. It proves that this exact frozen model-plus-32bp policy did not produce the support required to test that claim. Do not lower the threshold, change the fixed calendar, fit another model, or append new dates as an automatic rescue.

Primary evidence: local report path /root/workspace/project/quant-0.7.0/continuous-flow-ridge-01b-isolated/execution-OWNER-V070-CONTINUOUS-FLOW-RIDGE-03-01/ECONOMIC_AND_SUPPORT_REPORT.md. SHA-256: 2a2a01d6e23effc6cb1bc33a3c5863cffc13f5725a07f3231ba6cb1e99be7fb7.

## 5. Cross-trial lessons

### 5.1 Distinguish economic failure from support failure

- PRIMARY-01: sufficient event support, negative standalone costed candidate economics, full net missing.
- PRIMARY-02: sufficient event support, negative standalone costed economics and adjusted-bound/year-stability failure, full net missing.
- PRIMARY-03: source and common-origin support passed, but the frozen M1 policy did not produce sufficient active decisions; economic labels were never evaluated.
- C1: the frozen interaction was too sparse before economics; no C1 return result exists.

These are different terminal states. Never convert NULL into zero, and never describe an untested mechanism as economically falsified.

### 5.2 A positive paired difference is not sufficient

X_KER improved against X primarily by avoiding costs on rejected opportunities, while its own common-calendar mean remained negative. A improved against continuation by about 6.30bp, but its own costed mean remained negative. Future candidates must beat CASH and meet their own absolute costed gates, not only beat a weak control.

### 5.3 Support must precede economic labels

PRIMARY-03 correctly stopped after the support ledger and before assessment outcomes. A support gate is not an invitation to tune a threshold. If a different policy is proposed later, it is a new frozen hypothesis and requires a new scope, registration and budget slot.

### 5.4 Source QC is not causal execution evidence

Archive hash/schema validity establishes the quality of the observed archive, not the original receiver-first-known clock, order-book queue, adverse fills or realized execution. OHLC E0 outcomes are modeled references, not real fills.

### 5.5 Full-net and capital PnL remain unresolved

Funding/mark reads were not authorized for these studies. Full-net, funding-adjusted account PnL and capital-constrained drawdown remain NULL. This does not erase negative ex-funding findings, but it limits the wording of terminal scientific claims.

## 6. Registry and immutable campaign status

Registry directory: /root/workspace/project/crypto-data/lakehouse/research-loop-bootstrap-v070-20261022/registry.

- Events 000001–000003: PRIMARY-01 REGISTER/START/COMPLETE; terminal COMPLETE hash 2eb4047e2f26de5763e5349c35f78019550c634c09f72e76e35103233d7a56e6.
- Events 000004–000006: PRIMARY-02 REGISTER/START/COMPLETE; terminal COMPLETE hash 83cc87ce12fa0a340068ddbd729a32e7a8b16a0e6513a687da9f92dbecab11bb.
- Events 000007–000009: PRIMARY-03 REGISTER/START/COMPLETE; terminal COMPLETE/current chain head 3597b81ba7963ebf70609b45a12b004e33406c9bb44909b0abac6d71ed828985.

Current budget: 3 of 6 slots consumed; 3 remain. No slot is reserved for a particular next strategy. Do not use all remaining slots just because they exist.

## 7. Conclusion

No currently tested V070 primary candidate has established positive standalone after-cost expectancy. PRIMARY-03 did not reach economic evaluation. The next work should be independent mechanism discovery and novelty/support review, not a fourth automatic experiment or model/threshold rescue. The correct output of the next review may be NO_NEW_STRATEGY.
