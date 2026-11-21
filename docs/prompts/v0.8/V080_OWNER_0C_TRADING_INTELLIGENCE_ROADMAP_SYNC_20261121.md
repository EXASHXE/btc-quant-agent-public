# QUANT v0.8.0 — Owner Roadmap Update: Trading Intelligence Platform
Task ID: V080-OWNER-0C-TRADING-INTELLIGENCE-ROADMAP-SYNC-20261121
Recipient: Controller 0-C
Status: OWNER_DIRECTED / PLANNING_AND_DOCUMENTATION_ONLY / NO_AUTO_DISPATCH

## Owner product direction
Keep the existing H route and S0–S8 live-operational stage gates as the immediate execution priority. After S5 closes the FIRST independently validated real Hermes+QUANT+Feishu loop, prioritize:
- QI1: AI opportunity analysis, candidate pre-analysis and bounded first-notice annotations (deterministic card always remains independently sendable).
- QL1: SignalEpisode lifecycle, event-sourced notification/reprice/human response/outcome records and actual-vs-hypothetical separation.
- QB1: versioned historical data and reproducible, fee/slippage/no-lookahead-aware backtesting.
- QR1: Agent-driven attribution, falsifiable strategy hypotheses, independently executed experiments and human-approved candidate promotion.
- QN1 and QM1: later news/event intelligence and multi-market expansion, deferred until domain architecture and research validation are stable.

This is a PERSONAL low-frequency human-operated trading intelligence platform, NOT a general Feishu chat bot and NOT an autonomous trading system.

## Mandatory read-first
Canonical branch: docs/engineering, current HEAD.
- docs/project/V080_TRADING_INTELLIGENCE_PLATFORM_ROADMAP_20261121.md
- docs/project/V080_ROADMAP_AND_GATES_20261118.md
- docs/project/V080_PROJECT_HOME_20261118.md
- docs/project/V080_HERMES_H_FIRST_PI_FIELD_TRIAL_SEQUENCE_20261120.md
- docs/architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md (frozen)
- docs/project/V080_MODEL_ROUTING_POLICY_20261119.md
Read actual Controller decisions and sealed worker handoffs from /root/workspace/project/quant-0.8.0/, not stale status prose.

## Reconcile latest work before planning
As of the 2026-11-21 ~17:10 HKT inspection:
- H1 corrected offline reference, H2-A, H2-B, H3 Phase A and H3-B Gate A all have independent OFFLINE acceptance within their own scopes.
- Controller A1 local Binance release candidate was DISPATCHED_OFFLINE_ONLY at 16:52, and its worker submitted READY_FOR_CONTROLLER_REVIEW_OFFLINE_CANDIDATE with 237 worker PASS. No independent A1 acceptance was verified at this checkpoint. Verify whether newer receipts now exist; do not redispatch.
- Genuine Binance S2/S3 and real Feishu S4, H actual-use S5/S6, optional LLM credentials, recurrent scans, private B3 and TRADE were not authorized by the offline receipts.
- Pi P1 accepted ARCHITECTURE_ONLY; Pi P2 remains OWNER_DEFERRED until S5 is genuinely underway and first operational evidence exists.

## Planning deliverables
1. Adopt collision-free product IDs QI1, QL1, QB1, QR1, QN1, QM1. Existing A1 (Binance derivative), S0–S8 gates, R1 PUBLIC_MARKET, R6 evaluation, H1–H3 and P1/P2 MUST retain their meanings. Do not rename historical receipts.
2. Publish one consolidated dependency graph with exit evidence: S1 A1 candidate → S2 two-GET Canary (NOT_EVALUATED) → S3 real BTC/ETH/SOL market+strategy → S4 real Feishu private DM → S5 real H3 loop → S6 bounded operations → QI1/QL1 → QB1 → QR1; QN1/QM1 deferred.
3. Keep H's deterministic model-free first notification valid. Build QI1 candidate pre-analysis and immutable AI annotations with evidence IDs, hard latency budgets, freshness/revalidation and safe fallbacks. AI never changes WATCH/EXECUTABLE/SL/TP/netR or invents account clearance.
4. Define QL1 as multi-axis event sourcing (market, delivery, AI, human feedback, hypothetical market outcomes, verified account results), rather than a single invalid status machine. No-episode diagnostics remain diagnostic. Record MFE/MAE, ambiguity of intrabar TP/SL order, timing, fees, missed/no-chase, and denominators.
5. Define QB1 data licensing, time availability, exchange microstructure limits, strategy parity, time-based out-of-sample/walk-forward, cost/execution assumptions, leakage and multiple-testing audits.
6. Define QR1 hypothesis registry, reproducible experiments, independent evaluator, negative results, shadow/paper validation and explicit Owner+0-C strategy-version promotion. NO self-modifying production strategy or auto-trading.
7. Separate synthetic QA, historical simulation, forward opportunity and actual account fills/PnL. Real account permissions remain separately gated. Define signals/AI annotations/strategy candidates as versioned contracts independent of Hermes/Pi runtime.
8. Pi P2 is optional offline platform comparison during S6 after initial S5 field data; it must not block QI1/QL1, become a second real sender or trigger a fresh framework competition.
9. Reconcile canonical Project Home, Roadmap, 0-C/1-A startup, roles where necessary. Preserve frozen V1, immutable receipts and the original H-first policy. Only documentation scope is authorized by this request.

## Output to Owner (Chinese)
A. The latest independently evidenced S0–S8 and A1 state.
B. A single prioritized implementation queue with entry/exit criteria and task dependencies.
C. Proposed QI1/QL1 interface seams, data contract changes needing future approval and recommended worker allocations.
D. QB1/QR1 research plan with explicit no-overfitting/no-economic-claim gates.
E. A concise list of remaining REAL activation blockers.
F. Docs commit SHA and changed links if updates were made.
G. ONE immediate action, without launching anything automatically.

No worker dispatch, no real Binance requests, no Feishu send, no model OAuth/provider calls, no private USER_DATA, no TRADE and no Pi P2 start are authorized by this planning prompt.
