# QUANT v0.8.0 — Controller 0-C Trading Intelligence Roadmap Synchronization

- **Owner task:** V080-OWNER-0C-TRADING-INTELLIGENCE-ROADMAP-SYNC-20261121
- **Disposition:** OWNER_DIRECTION_ADOPTED / PLANNING_AND_DOCUMENTATION_ONLY / NO_DISPATCH / NO_LIVE_AUTHORIZATION
- **Evidence checkpoint:** 2026-11-21 ~17:22 +08:00; later status requires re-reading current receipts
- **Canonical branch:** docs/engineering; runtime evidence: /root/workspace/project/quant-0.8.0/
- **Primary product authority:** [Trading Intelligence Platform product roadmap](V080_TRADING_INTELLIGENCE_PLATFORM_ROADMAP_20261121.md)
- **Operational authority:** [S0–S8 roadmap](V080_ROADMAP_AND_GATES_20261118.md), [H-first sequencing](V080_HERMES_H_FIRST_PI_FIELD_TRIAL_SEQUENCE_20261120.md), frozen [Quant-Agent V1](../architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md)

This document is the **Controller's forward-looking dependency, contract-seam and review plan**, not a task dispatch, an independent acceptance of A1, or permission to activate any API, sender, model or trading capability. Preserve prior Controller records and the frozen V1 interface byte-identically.

## 1. Latest independently evidenced state and source hierarchy

**Source-of-truth rule:** Controller decision JSON and fresh independent review > sealed worker handoff (worker evidence) > dated planning prose. A locally valid SHA256 manifest verifies the supplied bytes, not production readiness or Controller acceptance.

| Gate/capability | Disposition and evidence boundary | Required next proof |
|---|---|---|
| S0: R1/B1–B5, H1 corrected, H2-A, H2-B, H3 Phase A, H3-B Gate A | Controller independently accepted their **separate OFFLINE scopes**; H3-B acceptance: \`controller-decisions/V080_CONTROLLER_H3B_GATE_A_OFFLINE_PREPARATION_SCOPED_ACCEPTANCE_20261121.json\` (SHA256 \`fab36ced3bdc4f545ff409d1df9381770261c2239abbc3da9d602db477005969\`) | No live service is proven |
| S1 / Controller A1: B5 local derivative | \`V080-SOL62-A1-B5-LOCAL-DERIVATIVE-OFFLINE-01\` dispatched 16:52, worker **READY_FOR_CONTROLLER_REVIEW_OFFLINE_CANDIDATE**, release \`0.8.0b5.post2\`, wheel \`1acaae4e9e49bf3a0dd9313b3c21d45ee5cd2476b3fce80d024ab7c83608a56f\`, worker 237 PASS; original \`SHA256SUMS\` \`0c33ca5255a61dec0efa38ae2c2ba248907ff9375c22986ea7b7e97ba2ebe1ed\` verified | **NO independent A1 acceptance receipt found** at checkpoint; independently review and accept/reject the candidate, including rollback and installed-byte proof |
| S2 Binance first bounded Canary | **NOT_AUTHORIZED**, no real GET observed | Separate authorized single-run two GET: \`/fapi/v1/time\`, \`/fapi/v1/exchangeInfo\`; <=2 requests, <=2 known weight, no retry; success \`NOT_EVALUATED\`, zero cards |
| S3 genuine three-symbol market/B2 | **BLOCKED** | Independent numeric fundingRate general-IP-weight evidence, approved full staged request budget, eligible route and genuine causal raw receipts; preserve \`NO_SETUP\` |
| S4 real Feishu | **BLOCKED** | Repair H2-B replaced-ledger quota reset; bound real Lark client/release, authenticated app/tenant/Owner/p2p chat, dedicated UID, finite receive/reply caps; separately approve outbound and inbound |
| S5 first actual H3 field loop | **NOT_STARTED** | Authenticated genuine source and accepted status/card, sole deterministic sender and private-DM query/reply, actual telemetry, explicit unobserved gaps, independent 0-C review |
| S6 bounded continuing H observations | **NOT_STARTED** | Separately scoped cadence, one-sender/kill/revoke/refresh, rate limits, feedback and outcome denominators; no automatic grant from S5 |
| S7 optional Pi P2 | \`OWNER_DEFERRED_UNTIL_H_FIELD_TRIAL / NOT_DISPATCHED\`; P1 ADR architecture only | First independent S5 operational baseline and fresh Owner/0-C dispatch; Pi offline shadow, never second sender |
| S8 optional B3 real account | B3 **OFFLINE_ONLY**; real Futures USER_DATA **NOT_AUTHORIZED** | Independent read-only permission proof, local credential/storage/data-boundary review; Layer 3 TRADE stays disabled |
| QI1 / QL1 / QB1 / QR1 | **RESERVED / NOT_DISPATCHED** | Detailed gates in sections 3–6; product implementation after S5 |
| QN1 / QM1 | **DEFERRED / NOT_DISPATCHED** | Separate Owner scope after foundational domain/data/research design is stable |

Evidence consulted: accepted Controller H1/H2-A/H2-B/H3/H3-B decisions; A1 workroot \`CONTROLLER_HANDOFF.md\`, \`A1_SECURITY_AND_QA_REPORT.md\` and verified sealed manifest; runtime \`controller-decisions/\` inspection showed only the A1 dispatch, no scoped A1 acceptance. This document does **not** independently rerun A1 worker tests.

## 2. One consolidated dependency graph and exit evidence

\`\`\`mermaid
flowchart TD
    S0["S0 offline engine + Hermes/H3/H3-B accepted"] --> S1["S1 A1 candidate independent 0-C review"]
    S1 --> P["Owner-local eligibility / egress / UID / protected state + production release review"]
    P --> S2["S2 separately authorized Binance 2-GET Canary"]
    S2 --> S3["S3 separate full market/B2 grant; funding weight resolved"]
    S0 --> F["A3/A4 Feishu ledger + live-client + bounded callback fixes"]
    F --> S4["S4 separately authorized real Feishu outbound + inbound"]
    S3 --> S5["S5 first genuine H3 human-use loop; 0-C observed baseline"]
    S4 --> S5
    S5 --> S6["S6 separately bounded continuing operations"]
    S5 --> D["Shared domain seam / Astra design challenge"]
    D --> QI["QI1 AI opportunity annotation (optional model gate)"]
    D --> QL["QL1 lifecycle event sourcing"]
    S6 --> QI
    S6 --> QL
    QL --> QB["QB1 versioned data + point-in-time backtesting"]
    QB --> QR["QR1 falsifiable hypotheses + independent research evaluation"]
    S5 --> PI["Optional Pi P2 offline shadow during S6, fresh dispatch only"]
    QR -. future Owner approval .-> QN["QN1 news/events deferred"]
    QR -. future Owner approval .-> QM["QM1 multi-market deferred"]
\`\`\`

Edges represent **engineering dependencies**, not automatic permissions. S3 and S4 are separately gated; their readiness work may proceed independently. A synthetic Feishu smoke + Binance-only Canary can establish a **PARTIAL_OPERATIONAL_BASELINE**, never a genuine QUANT signal-to-alert success. S5 requires an actual authenticated human-use loop with genuine market/QUANT evidence; if the market provides only NO_SETUP, capture that truth and do not synthesize a trade card. A single trial does not demonstrate economic alpha.

## 3. Prioritized single implementation queue (no tasks are newly dispatched)

| Priority | Package / work | Entry condition | Falsifiable exit / independent evidence | Owner / recommended executor after future dispatch |
|---|---|---|---|---|
| **P0 now** | **Controller independently review existing S1 A1 worker** | A1 sealed \`0.8.0b5.post2\` delivered | Seal, reproducible wheel, candidate vs H2-A diff, original disabled, enrolled/spent-state/rollback negative tests, 237 worker assertions independently challenged; issue acceptance or scoped hold | **0-C independent review**; **do not redispatch A1** |
| P1 | Owner-local A1 environment and production review | Candidate accepted | Venue/region eligibility, direct egress, CA/SNI, runtime UID, storage, shared headroom and exact separate production release/scope hashes reviewed; missing fields stay UNKNOWN | Owner locally + 0-C gate, scoped Sol only if additional code needed |
| P2 | S2 two-GET genuine Canary | Exact dual Owner/0-C bounded authorization | At most two actual GET and two weight, no Stage 2, zero cards, proper NOT_EVALUATED or precise blocked/failed result, receipt and cost evidence | Owner-authorized bounded operator; no auto dispatch |
| P3a | S3 public-market continuation | Separate combined-stage grant and trusted numeric fundingRate debit | Genuine BTC/ETH/SOL five-frame source, provenance and B2 states with independent QA; no fabricated EXECUTABLE | Sol primary; Neon equivalent fallback |
| P3b | S4 Feishu A3/A4 fixes and real tests | Independent P0 defect correction + precise distinct Feishu grants | Durable ledger identity and quota under replacement, single sender/client, authenticated p2p finite inbound, six V1 tools, ACK vs human-read separation | Sol complex security/integration; independent 0-C |
| P4 | S5 H3 real field baseline | Authorized S3 and S4 and actual events | Verified source→Core→Hermes send→owner query/reply with observed latency/failure/unknowns; partial separate smoke labelled partial | Owner real-use + 0-C audit |
| P5 | S6 bounded H operations and domain seam | S5 baseline accepted + separate cadence authority for real continued use | Persistent limits/revocation, representative observations and versioned immutable contract proposal; no manual-risk clearance claims | Sol operation; Astra domain review |
| P6a | QI1 first-notice intelligence | S5 baseline, shared seam design approved; any real model has separate auth | Pre-analysis and validated optional annotation within budget; deterministic alert unchanged on timeout/unauthorized/invalid; exact source refs; offline and prospective measurements | **Neon or Sol** (AI adapter; one writer) |
| P6b | QL1 SignalEpisode lifecycle | S5 baseline, shared seam design approved | Replayable multi-axis events, identity/time/provenance, no-episode diagnostics, real vs hypothetical denominators, adverse crashes/out-of-order tests | **Sol** (event store/Core interface); pair with QI1 only after frozen seam |
| P7 | QB1 historical data/backtest | QL1 stable event/data lineage and data rights proven | Point-in-time snapshots, reproducible cost/microstructure assumptions, out-of-sample/walk-forward, leak and multiple-testing audits | Sol/Neon implementation; Astra methodology review |
| P8 | QR1 strategy research lab | QB1 independently accepted | Registered falsifiable hypotheses, deterministic external evaluator, sealed holdout, negative findings, shadow/paper evidence, Owner+0-C candidate-version promotion/rollback | Astra hypothesis/research review; Sol/Neon implementation |
| Deferred | QN1 news / QM1 multi-market / Pi P2 / S8 B3 real overlay | Separate Owner criteria (Pi after S5; QN/QM after foundation) | Explicit separate gates; never block QI1/QL1 or initial H loop | No worker dispatched |

**Parallelism:** after S5, Astra first resolves the shared schema. Then one owner for QL1 storage and one independent owner for QI1 annotation/adapter may work in disjoint workroots, with **Sol as named H/Core integration owner**. If the seam is not frozen, run sequentially. Hydrogen handles bounded fixtures/docs/QA only. Controller independently accepts each scope.

## 4. QI1 / QL1 interface seams — PROPOSALS ONLY, not frozen V1 changes

### QI1 proposed \`QI1.AnalysisAnnotation.DRAFT\`

- Immutable identity: \`annotation_id\`, \`annotation_version\`, \`producer_model_id\`, \`prompt_template_version\`, \`validator_version\`, \`payload_digest\`.
- Core association: \`episode_id\` (nullable only for **diagnostic context**, never an affirmative signal), \`card_id\`, \`card_version\`, \`strategy_version\`, \`core_market_status\`, \`candidate_stage\`.
- Evidence: ordered \`evidence_refs[]\` with \`source_receipt/publication_id\`, \`availability_at\`, \`as_of_ms\`, \`evidence_class\`, \`fingerprint\`; \`contradictions[]\`, assumptions and explicit UNKNOWNs.
- Analysis: \`thesis\`, \`counter_thesis\`, \`obstacle_notes\`, \`execution_concerns\`, \`confidence_limitations\`. These are **non-authoritative prose**, never numeric eligibility.
- Timing: \`analysis_started_at\`, \`analysis_completed_at\`, \`core_revalidated_at\`, \`release_deadline_at\`, \`freshness_result\`, \`annotation_state\` (separate axis \`PREPARED|VALIDATED|REJECTED|EXPIRED|TIMED_OUT|UNAUTHORIZED|INCONCLUSIVE\`), token/cost and fallback metadata.
- No model-generated \`EXECUTABLE\`, SL, TP, entry, netR, account clearance or arbitrary source request. Only Core can issue new numeric or eligibility versions.
- Pipeline: on WATCH/early 1H candidates, pre-analyze from available source evidence; on independently closed-15m confirmation, Core rechecks latest 5m/quote/freshness and release eligibility. Sender assembles **one** event: deterministic H1 card with optional already-validated annotation ref. Finite per-channel deadline, to be proposed and approved from actual S5/S6 latency data. If deadline/model/provider/validation fails, immediately use the deterministic market-only card. Late output cannot create a second 'first' alert.
- No-episode \`NO_SETUP\`/\`NOT_EVALUATED\` stays diagnostic. AI discussion about a possible opportunity is not a Core signal. Distinguish annotations from separate, non-sendable research hypotheses.

### QL1 proposed \`QL1.SignalEvent.DRAFT\`

Use a shared immutable \`episode_id\` where genuinely assigned by Core; allow separate \`diagnostic_id\` for no-episode reports, **never invent an episode**. Agent and delivery may reference Core ids but not write authoritative market events.

Common envelope proposal: \`event_id\`, \`event_schema_version\`, \`axis\`, \`aggregate_ref\`, \`episode_id?\`, \`diagnostic_id?\`, \`card_id?\`, \`card_version?\`, \`notification_event_id?\`, \`causal_parent_ids[]\`, \`producer/authority\`, \`strategy_version/code_hash/config_hash\`, \`evidence_class\`, \`source_available_at\`, \`event_time\`, \`observed_at\`, \`processed_at\`, \`as_of_ms\`, \`clock_confidence\`, \`source_fingerprint\`, \`payload_hash\`, \`idempotency_key\`, \`payload_schema\`.

**Orthogonal axes (never collapse to one status machine):**

1. **Market:** immutable Core discoveries, WATCH, confirmed EXECUTABLE, invalidations, expiry, reprice and no-chase; exact Core status only.
2. **Delivery:** outbox enqueue, attempt, provider ACK, ambiguous UNKNOWN_DELIVERY, suppression, recipient/lease; never infer human read from ACK.
3. **AI:** QI1 annotation created, validated, rejected, timed out, superseded; cannot alter the Market axis.
4. **Human:** prompt shown, user saw/skipped/manual entered/exited with explicit source and uncertainty; unverified self-report is not an exchange fill.
5. **Hypothetical:** point-in-time forward observation, MFE/MAE, TP/SL paths, after-fee hypothetical R and explicit partial fills/ambiguous intrabar ordering. If only OHLCV can tell TP and SL both touched, classify \`AMBIGUOUS\` or conservative sensitivity ranges; do not choose an optimistic order.
6. **Verified account:** future Layer 2 separately authenticated fills, real fees, funding, positions and realized PnL. Remains \`UNAVAILABLE\` until a distinct live read-only permission gate is accepted. Never substitute hypothetical for real.
7. **Research lineage:** versioned QB1/QR1 datasets, experiments, strategy candidate evaluations and human promotion decisions; not a market eligibility rewrite.

Required projections/denominators: candidates seen, confirmed, notified, provider-accepted, acknowledged by human (if independently observed), missed/no-chase, expired, reprice-eligible, hypothetical outcomes, and verified account fills. Distinguish data provenance; record zero-trade cohorts and censored periods rather than deleting them. Replay must be idempotent across process restart, dual-writer attempts, duplication, timestamp reordering and storage loss; missing provenance stays UNKNOWN.

**Domain ownership:** QUANT Core/event service owns authoritative market + versioned domain event store; Hermes is a replaceable read-only facade consumer and single deterministic sender; Pi later is a non-sending consumer. Do not persist Hermes-session objects, prompt strings or Feishu SDK records as the core domain contract; store normalized event evidence refs.

**Future approval required:** the two DRAFT contracts, any new event/version schema, optional read-only V2/additive API, retention/privacy/storage migration and historical backfill require separate 0-C architecture/compatibility review with Python/Node vectors, frozen V1 unchanged, strategy Core untouched. No silent V1 edit.

## 5. QB1 — research architecture and explicit failure gates

- Data catalog: source-specific licensing, permitted retention/export, venue/instrument/timezone, public availability lag, timestamp confidence, immutable raw checksum, revisions and gaps. Fetch rights and real endpoints require independent scopes.
- Use point-in-time OHLCV finality, historical OI/funding/mark only to the degree available then; **do not invent historical order book, slippage or user fills** from candles. Separate recorded snapshots from estimated liquidity scenarios.
- Shares B2 strategy primitives, reasons and versions; no divergent backtest-only implementation of the strategy. Audit parity using exact B2 fixture cards and observation timestamps.
- Three distinct reports: **signal-only detection**, **execution-aware simulated** PnL with conservative spread/slippage/fees/funding/fill and order ambiguity, and **prospective paper/forward** with actual availability, send delay and action-time missed/no-chase.
- Temporal splits: contiguous walk-forward, anchored/rolling out-of-sample, purging + embargo for overlapping labels/episodes, holdout kept unseen by the proposer, regime and liquidity stratification; preserve all rejected candidates and parameter trials in a multiple-testing ledger.
- Acceptance fail gates: lookahead or revised-future record, data licensing ambiguity, insufficient completeness, simulated fill without observed/declared assumptions, fee/funding schedule uncertainty, nondeterministic replay, holdout reuse, unaccounted multiple comparisons => \`REJECTED/INCONCLUSIVE\`, not a profitable claim.
- Performance reports must show gross vs net hypotheses, confidence/uncertainty, transaction costs, drawdowns and sample denominators. Worker test PASS or backtest return does not demonstrate Alpha or actual PnL.

## 6. QR1 — hypothesis registry and independent research evaluation

A \`QR1.Hypothesis.DRAFT\` records \`hypothesis_id\`, parent strategy version, falsifiable mechanism, target market/regime, outcome metric, null/alternative, predeclared acceptance and failure thresholds, permissible parameter search, sample/period split, data and code hash, multiple-test family, known confounders and Owner-requested rationale.

1. Agent **proposes** mechanism and an experiment plan; its proposed claims are not acceptance evidence.
2. A separate deterministic evaluator runs reproducible QB1 experiments under exact approved data/code/config and test budget; no Agent Shell/SQL/private keys/trade tool.
3. Independent 0-C or designated reviewer examines negative results, walk-forward/holdout confidence, leakage, calibration, regime breakdown, costs and sensitivity. Seal both failed and positive hypotheses.
4. Only then consider time-bounded shadow/paper prospective comparison with current baseline and a defined stop rule. Do not expose new real market calls, production models or order routes by default.
5. Strategy promotion requires **separate explicit Owner approval + 0-C independent strategy-version decision**, immutable code/config/data hashes, rehearsed rollback and no automatic self-modifying thresholds.
6. Ongoing performance monitoring may recommend a rollback but must not silently deploy a new strategy.

## 7. Non-negotiable evidence partitions and permission gates

| Evidence lane | Admissible statement | Not admissible |
|---|---|---|
| SYNTHETIC_QA | Module behavior against frozen fixtures | Real market, delivery, human or PnL claims |
| HISTORICAL_SIMULATION | Counterfactual strategy behavior under declared information/cost model | Actual fills, live causality, economic Alpha |
| FORWARD_OPPORTUNITY | Genuine observed cards, missed/no-chase, timely delivery and price-path observations | Realized trader PnL without authenticated fills |
| OWNER_SELF_REPORT | Human said seen/entered/exited/skipped, with provenance and uncertainty | Exchange-verified trade/result |
| VERIFIED_ACCOUNT | Authenticated Futures USER_DATA fills/fees/funding if separately permitted | Blanket account clearance, automatic trading |

Future extensions may not relabel one evidence lane as another. Real ACCOUNT requires the separate Layer 2 gate. No TRADE mutation, automatic order, second Feishu sender, model-as-authority or unapproved market recrawl. Explicit model-provider API/OAuth permission is separate from consumer subscriptions.

## 8. Current genuine activation blockers

1. **A1 pending:** no independent Controller acceptance of the delivered \`0.8.0b5.post2\` candidate at this checkpoint. Protected rollback/durable state and installed-byte evidence require independent review; actual eligible region, approved direct egress/peer/CA, dedicated UID, state/enrollment paths, owner-local release and precise dual approval still missing.
2. **S2:** no one-shot signed Owner+0-C capability, thus zero authorized real GET; after future approval, exactly two, no Stage 2; NOT_EVALUATED is success.
3. **S3:** \`FUNDING_WEIGHT_UNRESOLVED\` numeric general IP debit and full combined-stage signed budget/route/clock provenance; no speculative debit.
4. **S4 outbound:** H2-B ledger replacement restores quota in current logic; offline H3-B pin check is **not** a production fix. Real provider client, immutably bound release, app/tenant/recipient and one-sender launch remain unproven.
5. **S4 inbound:** authenticated real callback/finite WebSocket, real distinct UID/UDS permissions, independent turn/reply quotas, dedup and teardown remain unproven.
6. **S5–S6:** no genuine H field data or approved cadence/reprice, no actual provider response, user receipt or suitable latency denominator. Genuine LLM/OAuth separate.
7. **S8:** real Futures USER_DATA permission proven read-only is absent; Layer 3 TRADE disabled.

## 9. Controller's one immediate action

**Independently review the existing A1 \`0.8.0b5.post2\` offline candidate** in a fresh isolated copy, including the worker's 237-test claims, byte-accurate release, native \`H2A_OWNER_PUBLIC_SCOPE_V2\` vs old \`B5_OWNER_PUBLIC_SCOPE_V1\` distinction, spent-state rollback, wrong UID, approved mock two-GET/no-card, cross-version regressions and sealed inputs. Issue one scoped 0-C acceptance or a bounded HOLD with reproducing evidence. **Do not redispatch the worker and do not perform or approve real Binance/Feishu calls in this planning turn.**

Only after that acceptance should the Owner supply protected local exact A1 operating evidence and seek a **separate** production release/scope approval. All QI1/QL1/QB1/QR1, Pi P2, QN1/QM1 remain **NOT_DISPATCHED**.
