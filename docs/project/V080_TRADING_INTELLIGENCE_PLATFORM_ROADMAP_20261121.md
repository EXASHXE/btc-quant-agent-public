# QUANT v0.8.0 — Trading Intelligence Platform: Product and Research Roadmap

## Current 2026-11-26 10:12 UTC+8 checkpoint (supersedes earlier status)
Active workroot /root/workspace/project/quant-1.0.0, branch v1.0.0 still at accepted RC1 2a40471. Stage 4A bedd2d7 scoped accepted, operator four packages upgraded to 1.0.0rc1, integration pending. Stage 4B offline hardening 4b77df2 and Track C beb3d57 are sibling commits based on bedd2d7, pending independent acceptance/integration. Track C report/registry show NO_CANDIDATE_PROMOTED, 10/16 trials, cumulative 19; final holdout sealed, no P4. S6 marker absent and no timer listed; Hermes active but RC1 in-memory compatibility not verified. Workspace reclamation audit only; preserve S5 rollback and RC1 evidence, no cleanup. Next: independent reviews, safe integration, Owner-gated S6 readiness/field trial and separately planned additive radar context. No automatic new research or live dispatch.

Read [the controlling checkpoint and roadmap](V080_CURRENT_CHECKPOINT_AND_ROADMAP_20261126.md). Older status below is historical where inconsistent; authorization rules remain binding.

## Controlling 2026-11-26 update — RC1 and Owner-confirmed T3
The current accepted local source baseline is v1.0-rc1 at 2a40471; P3 closed NO_CANDIDATE_BEATS_B2_V1 (9/24 trials), P4 not run, final OOS sealed; Stage 3 scoped acceptance recorded locally. Operator upgrade pending, remote code/tag publication and hosted CI unverified, S6 unauthorized. Current product is personal trading intelligence / market structure radar; no validated trading strategy. Current research horizon ~4h–5d; frozen B2 V1 remains unchanged.
Both web ChatGPT GPT-6.2 Sol and Gemini 4 Neon remain coequal combined 1-A + Controller 0-C, mutual audit and planning, one queue, one accountable Controller, no Worker self-acceptance. Both may use T3 MCP to inspect local tasks read-only, and launch/send an exact bounded task to Codex or AGY **only after Owner explicitly confirms T3 dispatch in a prompt identifying that task/prompt and executor**. No automatic dispatch, steering, restart, recurring tasks, permission escalation or live operations. Existing Owner-direct bounded offline forwarding (2026-11-24) remains valid without extra EXECUTE. T3 capability is not authorization; a draft/card/peer report does not grant launch authority. Record actual task/thread/run status, use exact provider options, pinned local base and non-overlapping write sets; no public sensitive identifiers. Keep full English copy-button cards and Chinese Owner communication.
See the canonical current checkpoint and T3 dispatch protocol linked below. **All older status, routing and execution restrictions below are historical where inconsistent with this controlling update; historical evidence and restrictions on real operations remain intact.**

- [Current checkpoint and roadmap](V080_CURRENT_CHECKPOINT_AND_ROADMAP_20261126.md)
- [Owner-confirmed T3 remote dispatch](V080_T3_OWNER_CONFIRMED_REMOTE_DISPATCH_20261126.md)

---


Status: OWNER_DIRECTION / PLANNING_ONLY / NO_WORKER_DISPATCH / NO_CAPABILITY_ACTIVATION
Owner update: 2026-11-21
Product: Personal low-frequency cryptocurrency trading decision support (2–12h), later extensible to other asset classes.
Controlling execution: [H first, Pi during actual H field trials](V080_HERMES_H_FIRST_PI_FIELD_TRIAL_SEQUENCE_20261120.md).
Existing stage gates: [S0–S8 underlying engineering and real-access roadmap](V080_ROADMAP_AND_GATES_20261118.md).
Controller authority: 0-C owns verified state, task scoping and independent acceptance. This document is a product direction, not evidence of implementation or an authorization.
**Independent Controller synchronization (2026-11-21):** [Controller 0-C evidence, dependency, schema and acceptance sync](V080_CONTROLLER_TRADING_INTELLIGENCE_ROADMAP_SYNC_20261121.md). That addendum provides the current A1 receipt audit, single operational/product dependency graph, proposed QI1/QL1 contracts, QB1/QR1 failure gates and one immediate action. It is documentation only.

## 1. Owner decision — what becomes the core product

The product priority is NOT a general-purpose Chat Agent or an autonomous trader. It is a coherent platform that:
1. Discovers and critically analyzes low-frequency market opportunities.
2. Publishes timely, trustworthy trade-decision cards and follows every SignalEpisode from discovery through expiry/outcome.
3. Captures actual delivery/human response, reprice and (only if separately authorized) real-account observations without claiming hypothetical profits as actual results.
4. Replays history and tests hypotheses with no-lookahead, venue-aware costs, point-in-time data and out-of-sample controls.
5. Lets an Agent produce bounded, auditable research proposals and experiment plans; only independently validated versions plus Owner approval can change active strategies.
6. Adds news/events and other markets later via versioned adapters, NOT by expanding present live data/network permissions.

QUANT Core remains the sole source of strategy/card eligibility, prices, SL/TP, net R, expiry and validated market outcomes. The Agent is a research and explanation layer. Chat/Feishu is one interaction surface; it does not own the business data model.

## 2. Collision-free naming

DO NOT reuse established identifiers:
- **A1** already denotes the Controller's local Binance B5 derivative release candidate.
- **S0–S8** denotes real access, first field usage, ongoing operations and Pi sequencing.
- **R1** already denotes the accepted PUBLIC_MARKET fixture foundation; **R6** denotes prospective evaluation.
- **H1–H3** denotes Hermes integration and rollout; **P1/P2** denotes Pi architecture/prototype.

New product work packages (not dispatched):
- **QI1 — AI Opportunity Intelligence** (AI opportunity analysis and truthful first-alert enhancement).
- **QL1 — Signal Lifecycle & Outcome** (event histories, monitoring, reprice, delivery and counterfactual vs actual results).
- **QB1 — Historical Data & Backtesting** (data quality, reproducible point-in-time research and cost-aware validation).
- **QR1 — Agent Strategy Research Lab** (attribution, experiment hypotheses, controlled evaluation/promotion).
- **QN1 — News & Event Intelligence** (DEFERRED).
- **QM1 — Multi-Market Adaptation** (DEFERRED).

Old discussion aliases “A1 AI analyst / S1 lifecycle / R1 backtest / R2 research / N1 news / M1 markets” are conceptual descriptions only. All formal task cards must use the collision-free IDs above.

## 3. Current H engineering reality — as-of 2026-11-21 17:10 +08:00 evidence, not live acceptance

Controller receipts in code workspace /root/workspace/project/quant-0.8.0/controller-decisions/:
- R1, B1–B4 and B5 Phase A: independently accepted only for their stated OFFLINE scopes.
- H1 corrected post1 reference: independently accepted OFFLINE_ONLY (63 tests, immutable reference pack).
- H2-A Binance Phase B readiness: SCOPED_ACCEPTED_OFFLINE_H2A_ACTIVATION_READINESS_ONLY.
- H2-B Hermes/Feishu readiness: SCOPED_ACCEPTED_OFFLINE_H2B_FEISHU_READINESS_ONLY.
- H3 Phase A integration: SCOPED_ACCEPTED_H3_PHASE_A_OFFLINE_ONLY.
- H3-B Gate A preparation: SCOPED_ACCEPTED_H3B_OFFLINE_GATE_A_PREPARATION_ONLY, live blockers unresolved.
- Controller **A1 local B5 derivative** was dispatched offline at 16:52 on 2026-11-21. Worker workroot workspaces/lt-v080-sol62-a1-b5-local-derivative-offline-01/ now reports READY_FOR_CONTROLLER_REVIEW_OFFLINE_CANDIDATE, 237 worker tests PASS and a sealed manifest (17:10 observation). **No A1 independent acceptance receipt yet verified.** Real A1 two-GET canary remains BLOCKED_INPUT / NOT_AUTHORIZED.
- Genuine Binance calls, real Feishu outbound/inbound, model OAuth/API, continuing scans/reprices, real Futures USER_DATA and TRADE are NOT AUTHORIZED by any of the above offline receipts.
- Pi P1 architecture accepted ARCHITECTURE_ONLY. Pi P2 implementation remains OWNER_DEFERRED_UNTIL_H_FIELD_TRIAL / NOT_DISPATCHED.

Always re-query current receipts and workroots. Treat worker evidence as worker evidence, do not relabel as Controller acceptance. Historical status in the older 2026-11-20 files may be superseded by newer receipts.

## 4. Preserve Controller's operational stages S0–S8

| Existing stage | Scope | Current status (at evidence checkpoint) | Exit boundary |
|---|---|---|---|
| **S0** | PUBLIC_MARKET / B2 strategy / H1-H3 + H3-B offline integration | **Offline chain accepted** | Only accepted offline evidence; NOT live |
| **S1 / Controller A1** | Reproducible, identity-bound Binance local release candidate | **Worker READY_FOR_CONTROLLER_REVIEW_OFFLINE_CANDIDATE; 0-C acceptance pending** | Independent package, hash, UID, source, enrolled trust and rollback checks |
| **S2** | First official Binance bounded canary | **NOT_AUTHORIZED** | Exact Owner/0-C grant, 2 GET (time, exchangeInfo), truthful NOT_EVALUATED; zero invented cards |
| **S3** | BTC/ETH/SOL five-frame genuine market scan + B2 | **BLOCKED** | New scope/weights/funding checks, genuine provenance, causal cards and reprice |
| **S4** | First real Feishu sender and allowlisted private DM | **BLOCKED** | Separate client/recipient, sender identity, outbound/inbound receipts and UDS checks |
| **S5** | First genuine H3 human-use loop | **NOT_STARTED** | Source → B2 card → deterministic first send → human read/query/reprice evidence, Controller review |
| **S6** | Authorized bounded continuing H operations | **NOT_STARTED** | Explicit recurrence/cadence scope, delivery/stale/unknown handling and first reliable field feedback |
| **S7 / Pi P2** | Optional offline Pi SDK consumer comparison | **OWNER_DEFERRED** | H real-use baseline + independent Owner task/0-C scope; never a second production sender |
| **S8** | Optional actual personal-account read-only overlay and ongoing optimization | **DEFERRED** | Proved Futures read-only permissions and separate security gates; TRADE stays disabled |

S2, S3 and S4 are separate capability boundaries, not automatic consequences of S1/H3-B acceptance. A single S2 canary is NOT S3 recurring market research or S5 real messaging.

**Product kickoff:** QI1/QL1 detailed design may be specified now; their actual core implementation is proposed **after S5 real H baseline**, with QL1 event contract/outcome scaffolding optionally proceeding alongside S6 under a separately approved offline task. Neither QI1 nor QL1 may delay the present S1–S5 H delivery or create an alternative real notification sender. Pi P2 may start later during S6 after initial H field baseline, not as a prerequisite to QI1/QL1.

## 5. Product delivery packages and acceptance design

### QI1 — AI Opportunity Intelligence (PRIORITY 1, NOT_DISPATCHED)

Goal: an Agent that finds and analyzes market *candidates* and returns a more useful first opportunity alert than a templated numeric card, while remaining causal and time-bounded.

Design:
- Accept QUANT-issued WATCH/early-continuation/confirmed candidates with immutable episode/version; a no-episode NO_SETUP/NOT_EVALUATED is diagnostic only.
- Analyze evidence early at 1H setup while waiting for independent closed-15m trigger. Fresh data and 5m/action-time quote must be revalidated by QUANT at release.
- Agent emits a structured, source-attributed **AnalysisAnnotation** with bullish/bearish rationale, contradiction, first 4H/1D obstacle, execution concerns, confidence limitations and assumption ledger. It must cite tool evidence IDs/as-of; unsupported claims → INCONCLUSIVE.
- AI may propose a research candidate but can NEVER promote WATCH to EXECUTABLE, change numeric levels, request unrestricted Binance data, or send a real message itself.
- First notice = deterministic validated QUANT trade card + optional valid AI annotation **already prepared within bounded latency**. On model timeout, invalid/stale explanation, unknown provenance, non-authorized provider or no budget, publish the deterministic market-only card immediately with "AI 分析未完成" if that card itself is actionable and authorized.
- Avoid duplicate sends or a delayed second "first" notification; any revision uses a new explicit event type/version and freshness gate. Keep model failures/usage separate from market status.
- Chat Q&A is a secondary interaction, not an acceptance objective.

Acceptance evidence: no added first-notice blocking, exact QUANT status/SL/TP/netR fidelity, zero stale/unsafe affirmative AI text across adversarial cases, structured annotation/version and no-episode refusal, recorded AI on/off latency and cost, model-free fallback and clear real-vs-synthetic distinction. Do not claim AI improves profit until prospective data supports it.

### QL1 — Signal Lifecycle & Outcome (PRIORITY 1, NOT_DISPATCHED)

Goal: immutable, queryable opportunity history across detection → WATCH → confirmed/actionable → published → sent/ack/unknown → reprice → missed/expired/invalidated → observed outcomes → evaluated.

Use **separate orthogonal state axes** rather than overwriting B2 status:
1. Market episode state + immutable B2 decision publications.
2. Notification delivery state (attempt, ack, unknown, suppress, recipient/lease).
3. AI annotation state and version.
4. Human response and any explicitly documented manual action.
5. Hypothetical outcome observation vs genuine account fill/fee/PnL (not interchangeable).
6. Experiment/strategy-version lineage.

Store event_time, source_available_at, observed_at, processed_at, reference as-of, card/episode/publication IDs, strategy code/config hash and clock confidence. Distinguish append-only facts from derived current projections. Replay and crash recovery need deterministic idempotency and no lookahead. UNKNOWN_DELIVERY never blind-retried; expired signals never reactivated from model explanations.

Evaluation: missed/no-chase counts and denominators, +5/+10-min actionability, latency, MFE/MAE, ambiguous intra-bar TP-vs-SL ordering (mark UNKNOWN/AMBIGUOUS unless path data available), after-fee hypothetical R and verified actual execution metrics only when Layer 2 becomes separately authorized. Zero-trade observations still count in the opportunity funnel.

Acceptance: synthetic backward-compatible replay of B2/H1 accepted fixtures, isolated storage, exact monotonic event reconciliation, one notification identity, no PII/account leakage, adversarial clock/restart/replay tests, defensible outcome denominator definitions and zero fabricated realized PnL.

### QB1 — Historical Data & Backtesting (PRIORITY 2, AFTER QL1 FOUNDATION, NOT_DISPATCHED)

Build a versioned, point-in-time historical data store for OHLCV (with verified finality), available OI/funding/mark/venue rules and *only when observed/available* historical liquidity snapshots. Preserve data revisions, licensing, provenance, query-as-of, and explicit gaps. A historical OHLCV candle is NOT an historical full-book quote.

Share strategy primitives/config with B2 to avoid a separate contradictory "backtest strategy". Provide three distinct tests:
- signal-only backtest,
- execution-aware backtest with explicit spread/slippage/funding/fees and fill assumptions,
- prospective/paper evaluation with actual publication/notification delays and reprice.

Use chronological splits, purging/embargo where overlapping labels, walk-forward, out-of-sample samples, multiple-testing accounting, regime breakdown and leakage tests. Guard against replaying revised/future data into prior timestamps.

Acceptance: reproducible pinned data/config/code manifests, exact event/order chronology, conservative fill and ambiguous-candle semantics, baseline strategies, versioned report and full failure cases. Do not compare synthetic backtests to real PnL as if equivalent.

### QR1 — Agent Strategy Research Lab (PRIORITY 3, AFTER QB1, NOT_DISPATCHED)

Agent responsibilities: search and summarize QL1/QB1 results, identify recurring failure modes, propose **testable hypotheses** with controls and failure criteria, create bounded experiment plans, request approved deterministic backtests, interpret comparable results and archive rejected/negative hypotheses.

Deterministic evaluators own performance metrics and statistical tests. The Agent cannot edit production strategy config, run arbitrary code/Shell/SQL, promote a new live model or trade. Register immutable strategy candidates with lineage (parent/version, code/config/data hashes), train/dev/test separation and sealed holdout protections.

Candidate promotion sequence: hypothesis → parameterized offline experiment → independent validation/out-of-sample → shadow/paper prospective period → independent Controller review + explicit Owner strategy-version activation; rollback/replay proven before promotion. No "self-improving" opaque dynamic production thresholds.

### QN1 / QM1 — DEFERRED future adapters

QN1 later adds official sourced news, disclosure/macro and crypto events with both publication and first-observed/usable times, licensing, dedup and causal event linking. Do not perform ongoing news scraping now.

QM1 later extends through an instrument/venue calendar + fee/contract schema (equities/ETFs vs CME index futures vs options are distinct), market hours/rolls/corporate actions, session and entitlement. Do not reuse Binance perpetual funding/contract assumptions for other venues. No market-provider connection is authorized by this plan.

## 6. Architectural rules across H and Pi

- Deterministic QUANT Core and H1 outbox remain single-authority; Agent SDK (Hermes today, Pi candidate later) never owns the market-decision writer.
- Domain tool and event contracts should be runtime-agnostic: QI1/QL1/QB1/QR1 must not import Hermes-specific session internals as persistent business schemas.
- Market-only information can enter approved model context only within explicit provider/data/recipient scope. B3 real account, API credentials, trade controls and private PnL must not be sent to remote LLM or Feishu by default.
- Model-dependent commentary is not evidence that a market fact is verified. Persist model, prompt template version, cited evidence IDs, token/cost metadata and postvalidator result separately from the market journal.
- Keep separate datasets/denominators for synthetic fixtures, historical simulated entries, forward opportunity observations and actual account fills.
- Support explicit human feedback (saw / skipped / entered / exited / reason) without presenting unverified manual reports as exchange-authenticated fills.
- Canonical V1 and accepted seals are immutable. Any extension follows a versioned adapter, compatibility vectors and 0-C acceptance.
- Trade remains human-only; no automatic Layer 3 order execution in this roadmap.

## 7. Suggested dependency-aware engineering order

Current execution queue: S1 independent acceptance of Controller A1 worker delivery → separately approved S2 Binance 2-GET Canary → separately approved S3 market scan and S4 Feishu → S5 first H real-use loop → S6 bounded continued observation.

After S5:
1. QI1 + QL1 can be decomposed into **one coherent product architecture review and two bounded non-overlapping implementation work packages**, without redundant framework building. QI1 first-alert annotations and QL1 episode/delivery journal share immutable IDs; agree one interface before concurrent writes.
2. Preserve H first sender; add model support only after its distinct provider permission gate. If unavailable, QI1 remains model-free with explicit unknown.
3. While S6 accumulates real lifecycle data, begin QL1 outcome labeling and QI1 quality evaluation. Pi P2 may be dispatched for offline comparison at Owner option after first H real baseline, but Pi must not block domain work.
4. When QL1 provides stable versioned data lineage, build QB1 historical research. After QB1 passing leak/fees/holdout tests, consider QR1 Agent-guided hypotheses.
5. QN1/QM1 remain NOT_DISPATCHED / NO_INVESTMENT until QR1/QB1 architecture is stable and the Owner makes a new scope decision.

Do not make task counts, economic win rate, return targets or dates commitments without evidence. Report evidence-based states: NOT_DISPATCHED, WORKER_READY, CONTROLLER_ACCEPTED_OFFLINE, REAL_GATE_AUTHORIZED, FIELD_TRIAL_OBSERVED, INCONCLUSIVE.

## 8. Immediate Controller decision required

This roadmap is planning-only. Controller 0-C should:
- Reconcile the 2026-11-21 A1 B5 local derivative worker handoff against the latest independent receipt; no duplicate worker.
- Keep live gates explicit, especially two-GET S2 versus full S3 and outbound/inbound S4.
- Adopt QI1/QL1/QB1/QR1/QN1/QM1 as RESERVED FUTURE DOMAIN PACKAGE IDS, not automatically dispatched tasks.
- Add work package dependencies and future review points to active roadmap and startup prompts.
- Keep Pi P2 deferred until S5 first real operational baseline and fresh Owner decision.
- Return one prioritized queue and acceptance-gate map. Do not dispatch the new domain packages or authorize any real call based on this document.

## 2026-11-21 19:58 checkpoint / Owner direct-offline authority

Controller H4 consolidated S2–S5 OFFLINE readiness is now accepted (336 independently passing QA, 103 sealed files), superseding the earlier S1 A1 worker-pending checkpoint for H4 integrated readiness only. No real Binance, Feishu, LLM or private/trading rights were conferred; S2 protected production/Owner-local eligibility, S3 fundingRate general IP weight, S4 authentic client/identity and S5 real field baseline remain unresolved.

Future QI1/QL1/QB1/QR1 development stays after H real field use; Pi P2 remains Owner-deferred. For future **explicitly Owner-executed bounded offline work**, apply the [new execution-start protocol](V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md); absent formal Controller JSON is not by itself a reason to block otherwise valid offline tasks. Worker output still requires Controller independent acceptance. This is a dated supplemental status and does not rewrite any prior immutable decision.

## 2026-11-23 verified checkpoint — product-first handoff

[Controller receipt / independent progress and revised operational priority](V080_PROGRESS_AND_NEXT_GATES_20261123.md) supersedes this roadmap's older 17:10 S1/A1 candidate snapshot for **current progress**; preserve that earlier paragraph as evidence history. S2 V2 (55 Controller QA PASS, 39 sealed), optional risk local CLI (12 PASS, 36 sealed), Astra S3 documentary admission (9 sealed), and optional Feishu Mode0/1 were subsequently scoped-accepted OFFLINE ONLY. S2 genuine public API, S3 qualified market scan, real Feishu S4, S5 H human use and S6 operations remain blocked or not observed. The 2026-11-22 22:23 next-stage note is planning only, not dispatch.

Primary milestone is a separately authenticated **genuine S2 two-GET** following Sol's disabled physical transport candidate and Owner-local eligibility/egress/rollback checks; S3 offline zero-retry readiness can run conditionally without displacing S2. Simultaneously gather Owner S4 app/recipient prerequisites without launching the provider. Only after independent S5 field evidence should QI1/QL1 implementation advance together; QB1/QR1 follow verified lifecycle/point-in-time contracts. Keep QN1/QM1 and Pi P2 deferred as previously specified.
