# QUANT v0.8.0 — B2 Integrated Market Decision MVP

> **Current navigation (2026-11-28):** [Wave D checkpoint](../../project/V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](../../project/V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.

Task ID: V080-SOL62-PERSONAL-MVP-MARKET-DECISION-B2-01
Executor: GPT-6.2 Sol — Extra High thinking effort
Task owner: Owner
Dispatcher / independent final acceptance: Controller 0-C
State: CONTROLLER_SCOPE_APPROVED / AWAITING_OWNER_FORWARD / WORKER_NOT_STARTED
Goal: ONE integrated offline strategy-to-human-decision capability and ONE consolidated Controller acceptance

## 0. Product mission and exact boundaries

Build the personal, local, noncommercial, human-operated Binance USDⓈ-M USDT perpetual MARKET_DECISION_MVP for a typical holding horizon of 2–12 hours (overnight only when explicitly reviewed). It must progress from causally available public inputs to explainable opportunities, conservative entry/stop/target economics, immutable signal episodes, action-time repricing and a human-readable local card/journal.

This is NOT a market data collector alone, and NOT an automatic trading agent. The Owner takes all trading actions manually at the exchange. B2 must work without any private-account API key.

Consolidate the prior Stage 4A and Stage 4B into one meaningful engineering package. You may design, implement, test, correct and integrate internal modules without returning to Controller for routine micro-approvals. Only material architectural/security conflicts or unapproved capability expansion require STOP and escalation.

B2 implementation and acceptance are OFFLINE-ONLY. No genuine Binance API call, credential, actual user-account reading, Feishu message, trading action or external deployment is authorized by this task. Positive fixture EXECUTABLE output is a synthetic test result, never a real actionable opportunity.

## 1. Sources and preflight

Repository: EXASHXE/btc-quant-agent-public
Executable code branch: v0.8.0
Verified baseline code HEAD at B1 review: bd144f2d15836bb84786c91aec571df77351bf5c
Local code root: /root/workspace/project/quant-0.8.0/
Canonical project docs: docs/engineering (read latest branch HEAD; no documentation writes from this worker)
Docs checkout: /root/workspace/project/quant-docs-engineering/

Accepted B1 root:
workspaces/lt-v080-sol62-personal-mvp-public-runtime-foundation-b1-01/
Accepted B1 manifest SHA-256:
73af3d2e273e9d4c6865fe3fe935939c4ae64a7a1475c4bb0ab99ceef319f7a5
Controller acceptance:
controller-decisions/V080_CONTROLLER_B1_PUBLIC_RUNTIME_OFFLINE_SCOPED_ACCEPTANCE_20261118.json

Accepted R1 root:
workspaces/lt-v080-sol62-personal-mvp-layer1-public-01/
R1 manifest SHA-256:
78125e1549de4b8d9e13e1d1c97ec0e5d66cdd9ebcd0c241e069d37ee396d365

Architectural audit:
workspaces/lt-v080-astra-full-system-arch-audit-roadmap-01/
Read FULL_SYSTEM_ARCHITECTURE_AUDIT.md, ARCHITECTURE_GAP_REGISTER.md, REVISED_ROADMAP_AND_STAGE_GATES.md, CONTROLLER_0C_HANDOFF.md.

Read latest canonical docs/project/V080_PROJECT_HOME_20261118.md, V080_ROADMAP_AND_GATES_20261118.md, V080_OWNER_REBASELINE_DECISION_20261118.md, docs/architecture/V080_THREE_LAYER_API_ARCHITECTURE_20261118.md and role/prompt policies.

Also inspect actual B1 Store.snapshot, V2 causality, source admission, statuses, latest fixture demo, and inherited Program J S1 and historical Q0B setup_identity/confirmation as comparison inputs. Reuse individually verified pure computations where appropriate, not historical execution or account clients. Historical fixed parameters, research budgets and stale strategy gates are not automatically current product policy.

New isolated work root:
workspaces/lt-v080-sol62-personal-mvp-market-decision-b2-01/

The entire B1, R1 and Program J accepted evidence must remain byte-identical. Do not modify main code root or docs branch. Prefer a new independently installable B2 namespace/distribution which declares the accepted B1 wheel as an explicit, exact local dependency and reads V2 public data through an explicit adapter; no legacy btc_quant_agent import or hidden execution path. Test this in a clean environment. If an unavoidable B1 API change is required, STOP and report the interface conflict rather than silently modifying the accepted B1 artifact.

## 2. B2 integrated stages — one engineering package

### A. Data-to-decision adapter and immutable evidence binding

Consume only validated, durably published B1 PERSONAL_PUBLIC_MARKET_SNAPSHOT_V2 observations with a full source origin, immutable receipt references, venue time bounds, availability and decision as-of information. Data must exist at the evaluation time and be final/continuous/fresh for the specific feature.

Separate the following states and reason codes:
- SOURCE_BLOCKED / partial input / stale data / unqualified source
- data ready but strategy NOT_EVALUATED
- features insufficiently warmed
- genuine complete strategy evaluation returning NO_SETUP
- WATCH candidate not triggered, paused or temporarily infeasible
- INVALID candidate irreversibly expired or structurally invalidated
- EXECUTABLE as a MARKET-SIDE eligibility classification only

Never carry forward R1's readiness-only NO_SETUP as a genuine strategy evaluation. Prevent backfilled candles, revisions and late book/mark/OI observations from becoming historical earlier decisions. Define a versioned B2 MarketSnapshotAdapter, EvaluationReceipt and reason catalogue.

The first live scan is separately gated and NOT part of B2. All tests and demos use accepted B1 offline fixtures, locally fabricated versions of B1 V2 public data, or loopback-only transport with explicit QA origin. No fixture result may claim authentic Binance source.

### B. Multi-timeframe market regime and setup engine

Implement:
- 1D background and first major barriers/support-resistance;
- 4H regime direction up/down/range/transition and structural higher/lower swing levels;
- 1H primary setup identification;
- 15m completed-bar independent confirmation/trigger;
- 5m momentum/no-chase and actionability refresh.

Use causal EMA, ATR14, optional ADX/DI and volume as versioned explanatory features, never trading probabilities. Require appropriate consecutive closed historical bars, explicitly record warmup and pivot lag (e.g., right-side confirmation only after those bars exist).

Provide at least two first-class, direction-symmetric trend setup families:
1. Conventional trend pullback, stabilization and continuation.
2. EARLY_CONTINUATION after shallow consolidation/breakout without waiting for a deep or perfect pullback.

Freeze 1H signal candle (Signal K), structural setup anchor, candidate family, confirmation level and buffer, invalidation line, initial entry band, earliest permissible independent 15m trigger and deadline BEFORE eligible trigger evaluation. An incomplete 15m candle, same-candle self-confirmation, shadow wick-only breakout or higher-timeframe structure visible only later must not upgrade a candidate. Long/short mirror cases must be explicit.

A reversal family or complex breakout families may be implemented as research/WATCH-only if insufficient positive/negative proof exists; do not fabricate full production eligibility to satisfy a checklist.

Detect early WATCH proximity without converting it to EXECUTABLE prematurely. Same symbol/direction overlapping families should have a stable grouping/priority rule instead of duplicate notifications.

### C. Market feasibility, cost geometry and risk card

Create pure, deterministic, Decimal-based calculations for:
- entry zone and conservative actual bid/ask side;
- tick/step/min-notional instrument constraints and quantity-independent unit risk;
- ATR/structure justified hard stop and expected stop-fill stress;
- TP1, TP2, TP3 or explicit UNESTABLISHED with reason;
- first 4H and 1D opposing obstacle and remaining reachable room;
- depth and liquidity capacity for an explicitly declared reference quantity (not pretend user-owned equity);
- OI participation and gaps, mark/index basis, current/expected funding, funding settlement crossing, spread and slippage assumptions;
- worst-side price and all after-cost net R values, with the fee/spread/slippage accounting basis documented to avoid double counting;
- partial exit and remaining-quantity stop paths;
- signal invalidation/expiry, no-chase cutoff and observed data age;
- evidence/source confidence and market-only eligibility.

All numeric risk estimates must be dimensioned and recomputable. Distinguish hypothetical geometric R, after-cost conditional path R and statistically expected value (unknown absent calibrated probabilities). Do not claim positive strategy edge.

Respect Owner-stated constraints as design context: typical isolated 10–15x leverage and a previously stated per-trade planned-loss cap of <=2.5% of total capital. These are not yet a formally accepted v0.8 executable account-risk policy. With no verified current equity, leverage, positions, stop orders and portfolio limits, show risk per base unit/reference nominal and mandatory human checks; never output "safe size", account approval, liquidation clearance or portfolio allowance from simulated funds. Portfolio exposure caps are UNKNOWN unless later formally approved.

Do not impose arbitrary institutional gates that preclude normal personal use. Define narrow P0 invariants (source validity, independently triggered setup, hard stop, realistic costs, adequate first-obstacle room, entry not chased) separate from configurable strategy quality scoring and versioned thresholds. A historical S1 2R gate is a comparison baseline, not automatically the universal new setup-family gate.

### D. Signal episode, state machine and action-time reprice

Produce stable versioned SignalEpisode identities based on venue/contract, strategy/version, direction, family and frozen 1H setup anchor. A particular setup may be observed and repriced multiple times; do not create a new signal merely because a quote refreshes.

Allowed state transitions must be explicit and auditable. Distinguish:
candidate WATCH -> triggered WATCH -> market-side EXECUTABLE -> still-valid/repriced/too-expensive/expired/invalidated, with SOURCE_BLOCKED as input overlay rather than rewriting established history. A temporary quote fault may suspend actionability without erasing a valid structural confirmation; the original absolute expiry is never extended by a refresh.

Freeze all decision-time source IDs, feature versions, price assumptions, first obstacle, status, expiry and reason codes. Repricing creates an appended version with fresh 5m/bar where relevant, quote/depth/mark/funding and fees/SL/TP/net R, not a rewrite of a historical card.

Provide deterministic +5 and +10 minute human-response scenarios:
- still inside entry zone, revalidated;
- already left zone or moved through first target: MISSED_NO_CHASE;
- structurally invalidated/stop breached;
- setup expired;
- quote stale or venue restriction: SOURCE_BLOCKED;
- changed spread/impact causes net R to fall below eligibility.

Do not infer an actual order or fill from a market signal. Actual account positions remain unknown.

### E. Local user-facing card and replayable journal

Ship a minimal useful local CLI/HTML dashboard or equivalent local-only read-only card view. Focus on legibility and exact why/status, not visual polish.

Card fields include symbol, direction, family and rank, all five timeframe timestamps, signal K/confirmation line, entry zone, hard SL, TP1/TP2/TP3 or reason absent, first 4H/1D obstacle, OI/mark/funding/depth provenance, after-cost net R by path, market status, blockers, expiry and next human action.

Show a separate explicit account overlay UNAVAILABLE / MANUAL_ACCOUNT_CHECK_REQUIRED. No "account-cleared executable" when Layer2 unavailable.

Build an append-only local decision and operator journal: initial observation, candidate, trigger, publication, +5/+10 reprice, expired/invalidated, manual WATCH/skip/intended action and optionally Owner-entered notes. Operator-entered records must carry OWNER_ENTERED evidence labels and must not be misrepresented as actual exchange fills. Ensure SQLite transaction/restart/duplicate-safe behavior. A versioned local read view can reproduce earlier cards without applying newer market context.

Do not implement Feishu, user-data connections, wallet/account telemetry, private dashboards or outbound model prompts. Local public-market-only outputs can later be projected for market-only notification after separate authorization.

## 3. One final adversarial test matrix

A. Data availability and temporal integrity:
- late depth/mark/book/OI and revisions do not create old signal eligibility;
- missing/wrong/duplicated bar, forming 15m, insufficient indicator prefix, bad clock and stale quote;
- confirmed 1H setup requires later independent 15m confirmation, not same bar;
- new B1 V2 publication version, reboot and historical replay preserve decision semantics.

B. Strategy state and symmetry:
- long/short pullback and early continuation positive cases;
- no deep retracement but valid shallow continuation;
- long wick false breakout, nontrending chop, contradictory 4H regime and obstacle proximity negatives;
- explicit WATCH proximity, NOT_EVALUATED, true NO_SETUP and INVALID distinct;
- one episode across repeated scans, overlapping family de-duplication, expiry immutability.

C. Risk arithmetic and quote actionability:
- hand-checkable Decimal E/SL/TP, fee/spread/slippage, funding crossing and after-cost R;
- first 4H/1D obstacle blocks fictitious distant TP benefit;
- tick/step/min-notional rounding, pressure stop, partial take profit then stop, negative funding and adverse spread;
- source or reference-size insufficiency prevents misleading liquidity/size claim;
- price moves outside band, stop breaches or TP1 hit before human response => no chase.

D. Persistence and usability:
- local-card read/reopen yields byte-equivalent historical versions;
- append-only journal, duplicate operator action, crash between stage and publish, recover/replay, old invalidated episode not revived;
- +5/+10 minute scenarios and logged manual action timing;
- impossible real-account risk claims, no hardcoded simulated equity or unapproved leverage cap;
- fixture evidence remains visibly synthetic and cannot be promoted to authentic market.

E. Isolation and preservation:
- clean install B2 + pinned B1; no legacy execution, signer, credential, order client, Feishu, private database, account read or real Binance request;
- B1 accepted SHA256SUMS and R1 accepted seals remain identical; protected Program J 323 hashes remain unchanged;
- dormant B1 live gate still blocks all genuine requests; no environment variable or old package imports can bypass;
- all test network traffic, if any, loopback-only with no external access.

Do not game acceptance by manufacturing a real-market EXECUTABLE. Synthetic positive cases are required for deterministic correctness, and economic effectiveness stays UNKNOWN. No arbitrary test-count quota: report exact PASS/FAIL/SKIP and all executed commands.

## 4. Deliverables and self-test expectations

Write all B2 implementation files ONLY under:
workspaces/lt-v080-sol62-personal-mvp-market-decision-b2-01/

Required:
- executable source, tests, pyproject/build and clean installable wheel or tightly equivalent local artifact;
- WORKER_RESULT.md and CONTROLLER_HANDOFF.md;
- B2_STRATEGY_AND_STATE_CONTRACT.md;
- B2_CAUSAL_SIGNAL_AND_EPISODE.md;
- B2_RISK_COST_AND_OBSTACLE_MATH.md;
- B2_LOCAL_CARD_JOURNAL_AND_REPRICE.md;
- B2_QA_REPORT.md with positive/negative test matrix, exact command results, limitations and source boundaries;
- evidence/ with two or more complete synthetic market-card evaluations, 5/10-minute repricing episodes, raw/normalized provenance, wheel/install evidence, test logs, controlled failures and restoration;
- SHA256SUMS sealing the delivered artifacts.

You are permitted to implement and correct all internal modules and fixtures under the B2 work package without additional Controller approvals. You may run full offline tests, clean builds and selected inherited B1/R1 regression tests within the exact scope. Do not rewrite accepted evidence or substitute a failing earlier acceptance with a new checksum.

If B1 lacks a needed immutable contract, implement a bounded read-only B2 compatibility wrapper. STOP and notify Controller if even that cannot preserve the accepted B1 semantics, rather than silently mutating B1.

## 5. Explicitly excluded capabilities

No real Binance public or private request, DNS/HTTPS production activation, credential signing, wallet/position read, trade/TP-SL order creation or cancellation, balance or leverage mutation, API key handling, Feishu send, network daemon or deployment.

No operation on real money.
No automatic trading or Layer3 activation.
No promotion of personal fixture evidence to Strict Source/E1, Strict Shadow or economic/Alpha proof.
No modification to canonical docs/engineering, v0.8.0 root, accepted B1/R1/Program J or Controller decisions.
No second core writer, Orchestrator or self-acceptance.

## 6. Final handoff and acceptance scope

Return READY_FOR_CONTROLLER_REVIEW with one coherent integrated B2 package and sealed evidence. Controller 0-C performs ONE independent consolidated audit.

If no separately authorized and independently verified genuine market inputs are available, the maximum positive decision is ACCEPT_B2_OFFLINE_INTEGRATED_ONLY. It may prove synthetic logic and UI operation, NOT a live actionable market MVP.

The first real public scan and any future authenticated account connection require independent Owner/Controller capability activation. B3 private connector + signal-account reconciliation is later and separate. A real market EXECUTABLE is always market-side eligibility, not permission to trade or assurance of account risk.

Human execution only.
