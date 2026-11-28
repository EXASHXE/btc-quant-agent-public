# QUANT v0.8.0 — B3 ACCOUNT_AWARE_DECISION_SUPPORT

> **Current navigation (2026-11-28):** [Wave D checkpoint](../../project/V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](../../project/V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.

## Consolidated R2 PRIVATE_USER_DATA + R3 Account/Signal Overlay

- Task ID: V080-PERSONAL-MVP-ACCOUNT-AWARE-B3-01
- Executor: Gemini Neon (complex-engineering tier; use the highest available reasoning/effort setting)
- Peer-level alternative: GPT-6.2 Sol Extra High, only if Neon quota/capacity is insufficient
- Architecture advisor: GPT-6.2 Astra only for a material architecture fork; no mandatory full-system audit
- Optional bounded QA: Gemini 4 Hydrogen; not a substitute executor for this complex package
- Dispatcher and sole independent acceptance authority: Controller 0-C
- Status: READY_FOR_OWNER_FORWARDING / NOT_DISPATCHED
- Purpose: Deliver one offline, installable account-aware decision-support package that joins deterministic private-account fixtures to accepted B2 MarketPlan/SignalEpisode records, reconciles orders, fills, fees and funding, and produces a local risk/protection overlay without enabling real account access or any trading capability.

## 0. Status, authority and hard boundary

This is one consolidated engineering package combining the former R2 PRIVATE_USER_DATA and R3 account/signal overlay scopes. B2 has already received Controller acceptance as SCOPED_ACCEPTED_OFFLINE_INTEGRATED_ONLY. Its MarketPlan and SignalEpisode contracts are now the integration boundary.

This prompt is prepared for Owner forwarding. It is NOT a dispatch, does not start a worker, and does not grant API, credential, private-account, network, deployment, Feishu, or trading permission. Start only after the Owner forwards this complete prompt.

B3 implementation and every test must remain offline and use deterministic synthetic private-account fixtures and fake credentials. No real Binance request, public or private. No real API key may be requested, read, generated, configured, or tested. No private account payload may be accessed. No external network transport may be implemented or activated in this package.

The private client may implement a transport abstraction, exact request construction, and a deterministic local signer for fake test credentials. Provide only an offline fixture transport. Any production secret provider or live HTTP transport must remain absent or hard-disabled and return PRIVATE_CONNECTION_NOT_ACTIVATED. The eventual private credential permission gate is a separate future Owner/Controller decision.

Layer 3 TRADE_EXECUTION remains disabled and unreachable. No order placement, cancel, amend, close, leverage/margin change, transfer, withdrawal, auto-stop, auto-take-profit, or other mutation path.

## 1. Verified project baseline and read-first requirements

Repository: EXASHXE/btc-quant-agent-public
Executable code/runtime branch: v0.8.0
Code baseline commit: bd144f2d15836bb84786c91aec571df77351bf5c
Canonical documentation branch: docs/engineering
Documentation baseline commit at prompt preparation: 373dd96bc5bb1d12b8663965deb8d639b93fcf3c
Local project root: /root/workspace/project/quant-0.8.0/

Accepted B2 work root:
workspaces/lt-v080-sol62-personal-mvp-market-decision-b2-01/

B2 Controller acceptance:
controller-decisions/V080_CONTROLLER_B2_MARKET_DECISION_OFFLINE_INTEGRATED_ACCEPTANCE_20261119.json
Acceptance-record SHA-256:
7de93eed45541d09a3b65b3e8452033c894ad402a169306bd97e4952929ac48d

Accepted B2 wheel:
workspaces/lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/wheel/quant_personal_decision_b2-0.8.0b2-py3-none-any.whl
Wheel SHA-256:
29cce34ff2b751ef9a9d305d3b7591281a6028c0057e360c9eb666b0840fed64

B2 sealed manifest SHA-256:
8c908905eaa8002e12f53f1d78939b15726658726c20b19abc66c673c6a58368

Before editing:
1. Verify the current code branch, exact baseline commit, worktree status, B2 acceptance record, B2 wheel hash and B2 manifest. Verify the canonical docs branch and current routing policy.
2. Confirm that no existing B3 worker/worktree or overlapping write owner exists. The Controller observed no B3 implementation workspace at prompt preparation; recheck before starting.
3. Read the current canonical docs/engineering versions of:
   - docs/project/V080_PROJECT_HOME_20261118.md
   - docs/project/V080_ROADMAP_AND_GATES_20261118.md
   - docs/project/V080_MODEL_ROUTING_POLICY_20261119.md
   - docs/project/V080_PROMPT_COPY_CARD_STANDARD_20261118.md
   - docs/architecture/V080_THREE_LAYER_API_ARCHITECTURE_20261118.md
   - docs/architecture/V080_BINANCE_API_ENDPOINT_MATRIX_20261118.md
   - docs/roles/V080_ACTIVE_ROLE_MATRIX_20261118.md
   - docs/prompts/v0.8/V080_SOL62_PERSONAL_MVP_LAYER2_USER_DATA_DRAFT_20261118.md
   - docs/prompts/v0.8/V080_SOL62_ACCOUNT_SIGNAL_OVERLAY_R3_DRAFT_20261118.md
4. Read the B2 implementation and accepted contracts:
   - B2_STRATEGY_AND_STATE_CONTRACT.md
   - B2_CAUSAL_SIGNAL_AND_EPISODE.md
   - B2_RISK_COST_AND_OBSTACLE_MATH.md
   - B2_LOCAL_CARD_JOURNAL_AND_REPRICE.md
   - src/quant_personal_decision_b2/model.py
   - src/quant_personal_decision_b2/strategy.py
   - src/quant_personal_decision_b2/journal.py
   - src/quant_personal_decision_b2/engine.py
   - B2_QA_REPORT.md and CONTROLLER_HANDOFF.md
5. Treat the current accepted B2 artifacts and schemas as immutable. If a baseline hash, schema, task ownership or branch state differs unexpectedly, stop and report the exact mismatch to Controller 0-C before editing. Do not repair B1/B2 in this task.

Create one isolated work root:
workspaces/lt-v080-personal-mvp-account-aware-b3-01/

Use a separate worktree or clean isolated copy based on the verified v0.8.0 baseline. Do not edit the shared v0.8.0 checkout. Do not modify Program J, baseline/program-j, accepted R1, B1, B2, prior controller decisions, or historical v0.7.0 artifacts. Keep implementation, synthetic fixtures, tests and sanitized evidence inside the B3 work root. Canonical project documentation remains on docs/engineering; do not write canonical project documents to v0.8.0.

Record the actual execution-interface model identifier and available thinking effort. Do not infer the exact model ID from a nickname. Gemini Neon is the primary assigned executor. If GPT-6.2 Sol is used instead because Neon quota/capacity is insufficient, preserve the same task ID, scope and acceptance bar, and record the actual Sol model identifier and effort. This is a single integrated work package with one core writer; do not run Neon and Sol concurrently on the same package.

## 2. B2 integration contract — read-only and immutable

B2 is the market-side decision engine only. Its accepted contracts include:
- B2_MARKET_PLAN_V1
- B2_SIGNAL_EPISODE_V1
- B2_MARKET_CARD_V1
- B2_EVALUATION_RECEIPT_V1

B2 cards preserve independent dimensions including market_status, episode_id, immutable episode, plan, evaluation_receipt, and the existing account fields:
- account_context_status = UNAVAILABLE
- account_overlay = MANUAL_ACCOUNT_CHECK_REQUIRED
- portfolio_exposure_limits = UNKNOWN

The B2 SQLite journal contains identity, episodes, cards and append-only events. The episode and card payloads are digest-bound; event history is SHA-linked. Read the accepted B2 Journal implementation and use a strictly read-only connection/adapter. Verify card and episode digests and the event hash chain before using B2 data.

B3 must:
- read B2 cards, episodes and events without modifying the B2 database;
- never update, delete, migrate, rewrite or append to B2 tables;
- never alter B2 market_status, trigger, episode, plan, source receipt or historical card;
- never convert B2's SYNTHETIC_QA_ONLY evidence into genuine market evidence;
- publish account overlay data into a separate B3 database/journal and link it to the B2 card_id and episode_id;
- preserve market setup status and account context status as separate dimensions.

The B2 wheel is an accepted dependency, not a source tree to fork. Do not import legacy BTC execution modules or B1 signer/credential functionality into B3.

## 3. Dedicated PRIVATE_USER_DATA client — offline GET-only implementation

Create a separate package namespace, for example quant_personal_account_b3, with independent configuration, client, signer abstraction, persistence and evidence labels. Do not place private functionality inside B1 or B2.

Implement the following core USDⓈ-M Futures signed USER_DATA route allowlist only:

- GET /fapi/v3/account
- GET /fapi/v3/positionRisk
- GET /fapi/v1/openOrders
- GET /fapi/v1/openAlgoOrders
- GET /fapi/v1/userTrades
- GET /fapi/v1/allOrders
- GET /fapi/v1/allAlgoOrders
- GET /fapi/v1/income

The final request boundary must independently enforce exact method, exact path and endpoint-specific parameter allowlists. Reject every POST, PUT, PATCH, DELETE, unknown path, path alias, unexpected query parameter, duplicate security-sensitive parameter, malformed timestamp, or invalid symbol/window before the transport is invoked. Negative tests must prove that rejected requests cause zero transport calls.

Do not add optional endpoints by default. An optional GET endpoint may be included only if a concrete B3 requirement cannot be satisfied from the core set, its current contract and weight are documented in the task evidence, and Controller review can still verify the exact allowlist. Do not use SAPI permission introspection as a shortcut.

Implement:
- a narrow credential-provider interface;
- a FakeCredentialProvider used only by tests and demo;
- a signer interface with deterministic fake signing and canonical query serialization;
- an injected clock/time-offset interface, with deterministic fake time;
- a PrivateUserDataClient that can only call the injected offline transport in this package;
- endpoint-specific typed errors and fail-closed response validation;
- strict redaction of API key, signature, signed query, timestamp/recvWindow and private response fields from logs and exceptions.

Do not implement a production provider that reads the Owner's OS keyring, DPAPI, environment, config files or shell state. A future local secret-store adapter may be represented only by an interface/stub that is permanently disconnected in this build. Never inspect the machine for existing keys or credentials.

The fake signer must not imply that a real key type or permission set has been selected. Keep the signer pluggable; use only deterministic fake key material in tests. Do not put fake secrets in source logs, command arguments, evidence summaries or task handoffs.

No private WebSocket or listenKey lifecycle. Those flows require non-GET control calls and are outside this GET-only boundary. No live HTTP implementation, DNS lookup, public/private network socket or Binance endpoint call. The test harness must run with external networking disabled.

## 4. Normalized account, position, order and ledger data

Normalize and preserve the raw synthetic fixture fields and unknown enum values for:

Account:
- walletBalance, availableBalance, marginBalance, totalUnrealizedProfit and other documented account balance/margin fields when present.

Positions:
- symbol, positionAmt, positionSide, entryPrice, breakEvenPrice, markPrice, unRealizedProfit, liquidationPrice, leverage, marginType, isolatedMargin, notional and updateTime when present.
- One-way/Hedge semantics and BOTH/LONG/SHORT legs.

Ordinary orders:
- symbol, orderId, clientOrderId, side, positionSide, type, status, origQty, executedQty, price, stopPrice, workingType, closePosition, reduceOnly, timeInForce, create/update times and other documented fields.

Algo/conditional orders:
- algoId, clientAlgoId, algoType, orderType, algoStatus, symbol, side, positionSide, quantity, triggerPrice, price, workingType, closePosition, reduceOnly, create/update/trigger times and trigger result where returned.

Fills/trades:
- symbol, tradeId, orderId, side, positionSide, price, qty, quoteQty, realizedPnl, commission, commissionAsset and trade time; preserve partial fills and multiple entry/exit legs.

Income:
- tranId, incomeType, income, asset, info, time, symbol and trade/order references when returned. Preserve FUNDING_FEE, COMMISSION, REALIZED_PNL and other income types separately.

Do not discard unknown fields or silently coerce unknown enum values. Parse all prices, quantities, PnL, commissions, funding and ratios with Decimal. Never use binary float for accounting or risk calculations.

A missing positionRisk row is NOT proof of zero position. A missing, stale or incomplete endpoint is UNKNOWN/PARTIAL, not empty. A multi-endpoint account snapshot is NON_ATOMIC. Each endpoint must carry its own request/receive time, venue-time basis, source identity, page coverage, freshness/age, status and error. Expose both per-endpoint coverage and an overall snapshot status; never present a partially fetched snapshot as complete.

## 5. Pagination, checkpoints, recovery and history limitations

Implement bounded, resumable pagination and durable checkpoints. Checkpoint identity must include endpoint, symbol where required, time window/cursor, schema/version and last accepted exchange identifier or timestamp. Persist each page transactionally and make exact retries idempotent.

Respect the endpoint limitations in the canonical matrix and R2 draft:
- userTrades is symbol-scoped and each requested time interval must be no more than 7 days. Use fromId/time-window pagination where supported. Do not assume unlimited historical backfill.
- allOrders and allAlgoOrders queries use windows shorter than 7 days. Records older than 90 days are unavailable; canceled/expired orders with no fills may disappear after 3 days.
- income exposes only the latest 3 months; the default recent window is 7 days and the documented request weight is 30. Use incremental polling semantics in the offline planner; do not design frequent full-history scans.
- openOrders and openAlgoOrders are current-open views, not historical order sources.
- Any missing page, unavailable retention interval, cursor discontinuity or endpoint failure must be explicitly PARTIAL/GAP/UNKNOWN with exact reason and affected time range. Never synthesize missing history.

Test crash/restart at page boundaries, duplicate pages, repeated cursors, out-of-order records, overlapping time windows, empty pages, retention gaps, and partial endpoint failure. Prove that resume neither loses nor double-counts records.

## 6. Canonical accounting and reconciliation

Use a single documented accounting policy with Decimal arithmetic and exchange identifiers.

Required default treatment unless the worker demonstrates a concrete endpoint-semantic reason to revise it:
- userTrades is the canonical fill-level source for executed quantity, fill price, trade-level realizedPnl and commission/commissionAsset.
- income rows of type FUNDING_FEE are the canonical funding cash-flow source; other non-fill income types remain separate ledger categories.
- income rows of type COMMISSION and REALIZED_PNL are reconciliation/cross-check evidence for the corresponding fill-level totals, not additional amounts to add to the same realized PnL or commission total.
- Any discrepancy is surfaced with a reconciliation status and source references; it is never silently netted away.

Deduplicate by stable exchange identifiers such as tradeId and tranId, scoped by symbol/account/endpoint as required. Preserve commission asset and income asset. Never sum different assets as if they were USDT; do not invent FX conversion. Actual realized PnL, commissions and funding must remain separate from B2's projected fee, spread, slippage and funding assumptions.

Support partial fills and multi-leg entries/exits. Provide per-trade, per-order, per-episode and per-period ledger views where evidence permits. If source coverage is incomplete, label totals PARTIAL and identify the missing window. Do not claim a complete account PnL history beyond venue retention.

For actual net R, use the accepted B2 plan's explicit risk basis and actual matched fills/fees/funding only when the denominator and all required evidence are available. Distinguish planned net R from realized net R. If actual stop-risk basis, position linkage, fill coverage, fee asset valuation or funding coverage is missing, return ACTUAL_R_UNAVAILABLE/PARTIAL rather than inventing a denominator or treating planned R as realized R.

## 7. SignalEpisode-to-account reconciliation — multi-to-many

Read B2 SignalEpisode and MarketPlan from verified B2 cards. Build a separate matching/reconciliation layer between:
- immutable B2 SignalEpisode and MarketPlan;
- ordinary orders and historical orders;
- current and historical Algo TP/SL/trailing orders;
- userTrades fills, including partial fills;
- current position legs and their later snapshots;
- income/fee/funding ledger entries.

Support multi-to-many relationships: one episode may map to multiple orders and fills; one position may contain exposure from multiple episodes; one order may have multiple fills; an episode may have partial entries and exits. Do not force one-to-one matching.

Use evidence such as explicit exchange order/trade IDs, client IDs, symbol, side, positionSide, order linkage, venue-time window, quantity and price proximity. Preserve the matching evidence and deterministic reason codes. Never infer a confirmed match from symbol and time alone.

Required match states:
- MATCHED — strong direct identifiers or explicit Owner-entered linkage with consistent side/quantity/time evidence;
- PROBABLE_MATCH — consistent multi-field evidence but no direct unique identifier;
- UNMATCHED — no adequate candidate;
- AMBIGUOUS — multiple plausible candidates or contradictory evidence.

Do not assign statistical match probabilities. A manual association, if implemented, must be explicitly OWNER_ENTERED, immutable/auditable, idempotent and separately displayed from machine-derived matching. A manual association cannot overwrite contradictory exchange evidence.

Preserve B2 source/card/episode identity and the original B2 market status. Never backdate a fill, rewrite a signal episode or mutate the B2 journal.

## 8. Account overlay and human actionability

The local overlay must expose these independent dimensions:

- market_setup_status: preserve the B2 status EXECUTABLE / WATCH / INVALID / NO_SETUP / SOURCE_BLOCKED;
- account_context_status: CONNECTED / UNAVAILABLE / STALE / PARTIAL, with an explicit evidence class and connection mode;
- position_relation: NO_POSITION / SAME_DIRECTION / OPPOSITE_DIRECTION / MULTIPLE / UNKNOWN;
- protection_status: PROTECTED / PARTIAL / UNPROTECTED / CONFLICTING / UNKNOWN;
- signal_trade_match: MATCHED / PROBABLE_MATCH / UNMATCHED / AMBIGUOUS;
- human_actionability: a concrete manual next check, including stale, missing, partial or conflicting data warnings.

Because B3 is fixture-only, any synthetic account snapshot must be unmistakably labelled SYNTHETIC_PRIVATE_QA_ONLY / FIXTURE_ONLY / NOT_A_REAL_ACCOUNT. It may use a distinct SYNTHETIC_CONNECTED status or the CONNECTED enum only when the synthetic evidence banner is inseparable from it. This build must never claim a real account is CONNECTED. Reserve genuine PERSONAL_PRIVATE_ACCOUNT / CONNECTED for a future separately approved activation.

Protection assessment must include both ordinary and Algo conditional orders. Distinguish stop-loss, take-profit and trailing semantics using actual order type, closePosition, reduceOnly, workingType, trigger price, positionSide, quantity and current status. Do not count a historical, canceled, expired, triggered or stale order as current protection. Do not mark a position PROTECTED merely because some stop-like order exists. Compare covered quantity with the live synthetic position leg and expose uncovered quantity. If endpoint coverage is incomplete or stale, protection is UNKNOWN rather than UNPROTECTED.

Expose position and portfolio context, including direction, quantity, notional, entry, mark, unrealized PnL, leverage, margin type, liquidation price/distance and protection coverage when available. Use UNKNOWN when a field or endpoint is absent. Do not invent portfolio risk limits, safe size or liquidation clearance.

The previously stated 2.5% per-trade loss preference and usual 10–15x isolated leverage are OWNER_STATED historical context, not approved executable B3 policy. Do not hard-code them as risk limits. Without an explicitly approved numerical account policy, portfolio_exposure_limits and safe_position_size remain UNKNOWN.

When private data is unavailable, stale, partial or disconnected, B2 public-market decision support must continue unchanged. Show the manual account/protection check and never imply that existing exposure or TP/SL was checked.

## 9. Local persistence, privacy and isolation

Use a separate B3 private database and separate overlay journal. Never store private payloads in the B1 public database or B2 decision journal. The B2 database must be opened read-only. B3 storage must have a distinct schema/application identity and transactional writes.

Apply restrictive local filesystem permissions/ACLs to the private database directory and files. Document the local storage boundary and backup/retention assumptions; do not claim encryption unless it is actually implemented and verified. Retention is Owner-controlled; do not impose a 24-hour purge.

Only deterministic synthetic private fixtures may appear in the repository/work root. No real account rows, API keys, signatures, signed queries or personal balances in source files, logs, shell history, command arguments, environment dumps, screenshots, QA reports, Controller handoffs, Git, cloud storage or Feishu. Sanitize exception messages and test failure output.

No network calls, external sends, telemetry, cloud upload, scheduled polling, Feishu, or deployment. No real secret-store access. No private account connector may be enabled by a config flag in this build.

## 10. Required offline test matrix

Positive and recovery coverage must include:
- deterministic fake signed GET construction for every core allowlisted endpoint;
- endpoint parameter validation and schema normalization;
- account balances and one-way/hedge long/short position fixtures;
- ordinary and Algo open/history orders, including stop, TP and trailing variants;
- partial fills, multiple entries/exits and income ledger rows;
- non-atomic snapshot and per-endpoint freshness/coverage;
- pagination, checkpoints, idempotent replay and restart recovery;
- canonical fee/PnL/funding reconciliation without double counting;
- currency/asset separation;
- B2 card/episode/event read-only loading and digest verification;
- one-to-many and many-to-many matches plus all four match states;
- position relation, protection coverage and partial/unprotected/conflicting/unknown cases;
- stale, partial and unavailable private context with successful public-only fallback;
- clean install, CLI/demo, journal replay and database recovery.

Mandatory negative/boundary coverage:
- POST/PUT/PATCH/DELETE and every unknown route rejected before transport;
- unlisted endpoint, path alias and invalid/duplicate parameter rejected;
- prove zero network/socket/DNS activity in all tests;
- fake secret, API key, signature and signed query never appear in logs/errors/artifacts;
- no real credential provider or local key-store access;
- permission-denied and timestamp errors never widen permissions or retry without bound;
- omitted position rows never become fabricated zero positions;
- openOrders without openAlgoOrders cannot qualify protection coverage as complete;
- stale/historical/canceled Algo orders cannot count as active protection;
- duplicate trade/income rows never double count PnL, commission or funding;
- different commission/funding assets are never silently combined;
- missing pagination pages/retention gaps remain PARTIAL;
- B2 database writes, migrations, UPDATE or DELETE are rejected; tampered B2 card/episode/event digest is rejected;
- ambiguous signal matches are never forced to MATCHED;
- stale/missing account context cannot suppress or rewrite B2 market status;
- no Layer 3 import, client, route or reachable mutation function;
- no private payload leaks into logs, handoffs or public B2 storage.

Use external networking disabled for the full test run. Positive fixture tests do not prove real Binance schema or key permission. Do not live-probe to improve test coverage.

## 11. Build, deliverables and consolidated handoff

Deliver one installable offline B3 wheel in the new package namespace, with hash-pinned dependencies on the accepted B2 wheel and its required offline dependencies. Do not bundle or fork B1/B2 source modules into the B3 wheel.

Provide a usable local CLI or equivalent read-only interface for:
- loading a synthetic private snapshot;
- reading normalized account/position/order/fill/ledger state;
- generating an overlay for a selected B2 card/episode;
- reading/replaying the B3 overlay journal;
- showing per-endpoint coverage, freshness, accounting reconciliation and human actionability.

Include deterministic fixtures for no position, one-way, hedge mode, long/short, multiple position legs, ordinary and Algo protection, partial protection, no protection, conflicting orders, partial fills, multiple entries/exits, funding/commission, stale/partial/missing endpoints, ambiguous matching and public-only fallback.

The work root must contain only useful engineering artifacts:
- concise B3 contract/schema note;
- focused runbook with exact offline install/demo/test commands;
- B3_QA_REPORT.md with actual PASS / FAIL / SKIP counts and commands;
- WORKER_RESULT.md and CONTROLLER_HANDOFF.md;
- evidence logs, test XML, clean-install/demo/recovery evidence and dependency locks;
- SHA256SUMS covering the final deliverables.

Do not create generic governance documents or separate task IDs for internal modules. Do not ask Controller 0-C for approval after each implementation phase. Implement, test, correct and integrate autonomously within this single scope, then submit one READY_FOR_CONTROLLER_REVIEW handoff. Do not self-accept.

Run lint, configured type checks, compileall, full offline tests, wheel build, hash-pinned clean installation and installed-demo/replay. Report exact commands, environment, exit codes, test counts, skips and failures. Preserve B2/B1/R1/Program J seals; use targeted inherited regression rather than rerunning unrelated full historical suites without a concrete reason.

## 12. Stop conditions and final acceptance boundary

Stop immediately and report to Controller 0-C if:
- the pinned code/docs baseline or accepted B2 evidence does not match;
- another B3 writer/worktree or overlapping integration owner exists;
- implementation requires a real API call, real credential, real account payload, live HTTP transport or permission change;
- any required endpoint's read-only semantics are unclear and cannot be proven from the pinned contract;
- any POST/PUT/PATCH/DELETE or Layer 3 path becomes reachable;
- private data could enter public storage, logs, Git or external systems;
- B2 immutability or accepted baseline preservation cannot be maintained.

If the future Binance key permission combination for Futures USER_DATA is not demonstrably read-only, complete the offline package with private connection permanently DISCONNECTED. Do not enable a trade-capable Futures permission as a workaround.

The final status can only be READY_FOR_CONTROLLER_REVIEW. B3 Controller acceptance, if granted, will mean OFFLINE ACCOUNT-AWARE INTEGRATION ONLY. It will not authorize a real private key, real USER_DATA calls, live public market activation, external messages, deployment, or trading. Those remain separate capability decisions.

No profitability, live-readiness, actual account protection, or real execution claims may be made from synthetic fixtures.

## 13. Worker final response format

Return a concise Chinese handoff with:
1. Exact task ID, actual model identifier/effort, base commit and work root.
2. Implemented modules and verified B2 integration boundary.
3. Core/optional endpoint allowlist and proof of GET-only enforcement.
4. Private-data isolation, fake credential and no-network proof.
5. Accounting and signal-match methodology, including unresolved/partial cases.
6. Actual PASS / FAIL / SKIP counts and exact verification commands.
7. Wheel, clean install, demo/replay and SHA256 manifest paths/hashes.
8. Explicit statement: no real Binance requests, no real credentials, no private account access, no trade path, no Feishu/external sends.
9. Remaining limitations and READY_FOR_CONTROLLER_REVIEW status.

End of task.
