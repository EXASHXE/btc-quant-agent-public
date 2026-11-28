# QUANT v0.8.0 — B1 Integrated Public Runtime Foundation

> **Current navigation (2026-11-28):** [Wave D checkpoint](../../project/V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](../../project/V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.

Task ID: V080-SOL62-PERSONAL-MVP-PUBLIC-RUNTIME-FOUNDATION-B1-01
Executor: GPT-6.2 Sol — High thinking effort; use Extra High for materially complex cross-module decisions
Task owner: Owner
Dispatcher / independent acceptance: Controller 0-C
Status: CONTROLLER_SCOPE_APPROVED / AWAITING_OWNER_FORWARD / WORKER_NOT_STARTED
Delivery: ONE consolidated B1 implementation package and ONE final independent Controller acceptance

## 0. Mission and strict authority

Implement a substantial OFFLINE-INTEGRATED PUBLIC_RUNTIME_FOUNDATION that consolidates the former Stage 1A and Stage 1B plus the applicable G10 public API compatibility/recovery work. This is a single engineering scope. You may iteratively implement, test, fix, integrate and document internal milestones without returning to 0-C after routine substeps. Do not dispatch other engineering workers or ask Controller to accept each internal module.

B1 does NOT authorize a real Binance request, private credential access, private signed GET, Feishu message, trading action, deployment, or live capability activation. Build and prove the future HTTPS capability using local deterministic fixtures, loopback TLS tests and offline responses only.

Preserve accepted R1 and Program J, including all existing seals. Rebuild a distinct and independently installable B1 artifact from the accepted R1 source as an input, without replacing or editing it.

## 1. Exact source roots, decisions and preflight

Repository: EXASHXE/btc-quant-agent-public
Code/runtime branch: v0.8.0
Pinned baseline HEAD: bd144f2d15836bb84786c91aec571df77351bf5c
Code root: /root/workspace/project/quant-0.8.0/

Canonical documentation branch: docs/engineering
Docs checkout: /root/workspace/project/quant-docs-engineering/
Documentation HEAD at Controller preparation: 4e9fc835177ef2d36758ed9b313df57c29e68764
The docs branch is the sole writable project-document authority. Do not modify it from this worker task.

Accepted R1:
workspaces/lt-v080-sol62-personal-mvp-layer1-public-01/
R1 SHA256SUMS SHA-256: 78125e1549de4b8d9e13e1d1c97ec0e5d66cdd9ebcd0c241e069d37ee396d365

New B1 isolated work root:
workspaces/lt-v080-sol62-personal-mvp-public-runtime-foundation-b1-01/

Controller approval:
controller-decisions/V080_CONTROLLER_SOL62_B1_PUBLIC_RUNTIME_FOUNDATION_FORWARD_APPROVAL_20261118.json

Read in order:
- README.md and AGENTS.md from docs/engineering, plus its active branch policy;
- docs/project/V080_OWNER_REBASELINE_DECISION_20261118.md;
- docs/project/V080_ROADMAP_AND_GATES_20261118.md;
- docs/architecture/V080_THREE_LAYER_API_ARCHITECTURE_20261118.md;
- docs/architecture/V080_BINANCE_API_ENDPOINT_MATRIX_20261118.md;
- docs/prompts/v0.8/V080_SOL62_PERSONAL_MVP_LAYER1_PUBLIC_IMPLEMENTATION_20261118.md;
- R1: WORKER_RESULT.md, CONTROLLER_HANDOFF.md, R1_MARKET_DATA_CONTRACT.md, R1_ENDPOINTS.md, R1_QA_REPORT.md and implementation/tests;
- workspaces/lt-v080-astra-full-system-arch-audit-roadmap-01/: FULL_SYSTEM_ARCHITECTURE_AUDIT.md, ARCHITECTURE_GAP_REGISTER.md, REVISED_ROADMAP_AND_STAGE_GATES.md, CONTROLLER_0C_HANDOFF.md;
- controller-decisions/V080_CONTROLLER_R1_LAYER1_PUBLIC_OFFLINE_SCOPED_ACCEPTANCE_20261118.json;
- controller-decisions/V080_CONTROLLER_ASTRA_FULL_SYSTEM_ARCH_AUDIT_ACCEPTANCE_20261118.json;
- controller-decisions/V080_CONTROLLER_SOL62_STAGE1A_BOUNDARY_CAUSALITY_FORWARD_APPROVAL_20261118.json;
- this B1 supplemental Controller approval.

Preflight: independently verify branches, R1 manifest, Program J baseline and that the old 1A workspace has not started. The narrower 1A approval is SUPERSEDED FOR FUTURE FORWARDING, not rewritten. If a competing writer or altered pinned baseline appears, STOP and disclose the exact conflict. Do not overwrite evidence. Create the B1 work root atomically only after preflight.

## 2. Internal implementation sequence — NO interim Controller acceptances

Internally organize implementation into five integrated technical phases (do not create five dispatches or five Controller gates).

### Phase A — PERSONAL_MVP runtime and capability isolation (G01)

Provide one explicit PERSONAL_MVP composition root and independently installable artifact, with clean CLI and a bounded read-only API or equivalent offline operator interface. Keep the package lean and locally operable.

Prevent legacy source tree or distribution aliasing from importing btc_quant_agent.api / QuantService / ExecutionService / BinanceSignedClient / AccountWatch / position supervisor / order router / user-stream/listenKey / any mutation capability into the personal process. A default-off flag is insufficient; validate import graph, installed file inventory, entry points and adversarial configuration/environment variables. Resolve the R1 wheel versus root repository package-name collision using a demonstrably isolated distribution/namespace and explicit dependencies. Preserve legacy source in place for historical workflows without shipping it into the personal artifact.

Separate fixture-only and future genuine-public composition modes at construction, configuration, store identity, audit labels and data reader. The future genuine-public mode must have no implicit fallback to fixture transport. No private signer, key provider or account database shall be reachable from the public path.

### Phase B — causal market consumer V2 and truthful state (G04)

Preserve the accepted R1 PERSONAL_PUBLIC_MARKET_SNAPSHOT_V1 semantics, historical bytes and raw evidence. Introduce an explicit versioned V2 causal consumer view, never silently relabeling V1.

Track distinct exchange bar open/close, source event time, first request/observation/receipt, venue clock uncertainty, local durable commit/availability, decision as-of/publish time and boot/session identity for monotonic comparisons. Retain raw source/receipt IDs and bar revisions, source-origin identity and per-symbol/per-field freshness.

Prove that a quote, depth, mark or OI observation received after a historical bar cutoff is not available at that cutoff. Later actual observations may be consumed at their true availability time; do not reject valid late-context current evaluations just because they follow bar close. Historical backfill, newer revisions and cache reload cannot retroactively create or rewrite an earlier signal/decision. Atomic persistence and after-restart causal replay must be demonstrable.

Separate data_ready from feature_warmup_ready, strategy_evaluated, strategy_status and account_context_status. In B1 no strategy runs. Therefore valid ready inputs must report strategy_evaluated=false / NOT_EVALUATED, NOT a genuine NO_SETUP. A genuine NO_SETUP is reserved for a completed strategy evaluation with adequate inputs. Three bars are insufficient for ATR14/EMA30 and cannot be interpreted as no opportunity. Account context is UNAVAILABLE; do not claim risk clearance or executable advice.

Provide configurable bounded Kline prewarm requests and indicator dependency descriptors for the later B2 engine; do not implement B2 strategy logic.

### Phase C — production-shaped unsigned HTTPS transport, tested OFFLINE (G02)

Implement a separately gated HTTPS-capable public client with strict final-send checks for approved Binance USDⓈ-M host, TLS port, method=GET, route, query parameter set, symbol, intervals, request size and budgets. Reuse R1's ten public endpoint definitions as the initial allowlist. Keep RPI depth and aggregate trades DISABLED.

Verify certificate chain AND hostname with no insecure fallback. Reject redirects instead of following them; prohibit hidden proxy, region rotation, alternate host, URL rewriting, unreviewed routing and permission bypass. Enforce connection timeout, read-idle timeout, whole-request and whole-scan deadlines; stream and bound both transfer bytes and decompressed payload. Do not buffer an unbounded response before enforcing size limits. At most one explicitly permitted transient retry and charge EVERY attempt. Fail closed on malformed JSON, schema mismatch, TLS error, incorrect origin, restriction or unknown status.

All acceptance tests MUST run against loopback HTTPS with locally generated test certificates or mocked transport. Never resolve, connect to or call a real Binance market host while implementing B1. Keep future live enablement default false and require a separate reviewed Owner operating-scope artifact and an explicit future Controller capability activation. A transport class being constructible does not enable network access.

### Phase D — persistent budgets, cooldowns and recovery (G03)

Implement a single-collector lease/lock OR a local atomic, restart-safe budget coordinator. No distributed service or new Orchestrator. Before external dispatch, persist a conservative reservation covering endpoint family, request weight/count, rate window, egress/IP scope, scan identity and retry. A crash after reservation must not make the reservation free. Concurrent process starts must not double-spend a quota.

Persist 429 Retry-After, 418 hard stop, explicit region/venue prohibition and appropriate 403/451 stop semantics across process restart. Re-enable only under a justified, reviewable policy (not arbitrary restart). Do not treat inaccurate bookTicker X-MBX-USED-WEIGHT-1M as authoritative. Reconcile real exchangeInfo limits and trustworthy headers conservatively. Cover request-count limits, zero-weight OI history endpoint limits, funding-rate shared quota, retries and separate process launches.

Use normal PERSONAL_MVP venue time/monotonic policies, not Strict Research 50ms/NTS hardware constraints. Restart must reacquire time uncertainty and should not misinterpret a new boot's monotonic clock as comparable to an earlier boot's clock. Retain durable original audit receipts and blocked reasons. Failed partial scans must not publish a fictitious valid result.

### Phase E — public endpoint schema, cache and scan readiness (G10)

Test exchangeInfo filters, five timeframe Klines, bookTicker, depth excluding RPI, OI and OI history, funding history, premiumIndex and 24h ticker with pinned official-document-derived fixture examples and explicit endpoint/weight versioning. Distinguish facts checked from current official documents from assumptions not verified live.

Resolve fundingRate omitted startTime/endTime semantics, legal response length versus requested limit, funding pagination or bounded queries; never silently truncate a valid longer venue response or mistake a documented response for malformed data without a reproducible contract reason. Preserve shared funding quota treatment. Handle OI history gaps/retention and mutable exchange symbol lifecycle.

Introduce bounded incremental Kline warmup and catch-up, overlap revision detection, per-symbol failure isolation, deterministic recovery after large but allowed gaps, separately refreshed slow-changing metadata/history vs. short-lived quote/depth/mark. Whole-venue restriction or clock failure remains a global stop; an isolated bad symbol need not block other symbols. Keep optimistic status as SOURCE_BLOCKED/NOT_EVALUATED when required evidence is missing or too old; do not weaken freshness thresholds to make fixtures pass.

An offline end-to-end demonstration must connect:
fixture/loopback source -> unsigned GET admission -> V2 causal snapshot -> normalized market context -> persisted/reloaded cache -> truthful NOT_EVALUATED or blocked status.

Provide an explicitly dormant future-live composition gate and demonstrate it sends ZERO requests in any unapproved configuration.

## 3. Required final acceptance matrix

Build meaningful deterministic tests without arbitrary pass-count quotas. Supply positive AND negative tests of the changed boundary.

A. Package / isolation:
- clean venv or wheel install, CLI/entrypoint and dependency inventory;
- import/call graph proves no execution, signed trade, private AccountWatch or listenKey reachability;
- malicious legacy env flags, module shadowing and mixed install attempts cannot enable those paths;
- public mode never loads secrets or private-store adapters.

B. Temporal integrity / status:
- bar inclusive close normalized to exclusive end;
- first observation, durable availability and decision as-of remain distinct;
- late quote/depth/OI/mark cannot contaminate a prior replay;
- later legal decision may use newly observed data with proper age;
- historical revision/backfill cannot retroactively create earlier signal;
- R1 ready snapshot becomes V2 NOT_EVALUATED, not genuine NO_SETUP;
- insufficient ATR14/EMA30 history remains not evaluated;
- five-timeframe boundaries, stale/partial data and per-symbol invalidity fail clearly.

C. Transport and origin:
- trusted versus untrusted CA, hostname mismatch, expired certificates;
- redirect, off-domain, unexpected ports or paths, non-GET and forbidden query rejected before send;
- slow handshake/read, body that exceeds encoded or decoded byte limit, malformed/unexpected JSON;
- TLS/restriction and region denial cannot fall back to fixtures, alternate hosts or insecure mode;
- fixture and future genuine-public databases are mutually inaccessible as the wrong origin;
- tests never open a real exchange connection.

D. Persistence and limits:
- crash immediately after reservation; concurrent startup competing for budget;
- restart after 429, 418, 403/451 and explicit venue restriction;
- accurate and misleading headers, including bookTicker;
- funding/OI family quotas, failed attempt and one-retry accounting;
- duplicate pages, outages and restart do not create double credits or fabricated complete scans.

E. Endpoint/scan compatibility:
- all ten GET endpoints have versioned good/bad fixture coverage;
- funding time-window and response-boundary fixture including legally long result;
- OI missing periods, schema extensions and invalid filters;
- long-gap bounded catch-up and per-symbol isolation;
- slow and fast input refresh age evaluated separately;
- synthetic two-scan incremental/reload demonstration.

Run appropriate static checks (Ruff, mypy, compileall), build wheel(s), install in a clean isolated environment and execute inherited offline regressions proportionate to changed dependencies. Confirm exact baseline and accepted R1 SHA seals still pass. Report PASS / FAIL / SKIP and reasons; never suppress a failing suite by replacing its expected baseline. Controller will independently rerun chosen high-value tests after delivery.

## 4. Deliverables — one consolidated handoff

All B1 implementation outputs belong ONLY to:
workspaces/lt-v080-sol62-personal-mvp-public-runtime-foundation-b1-01/

Deliver:
- functional source, tests, packaging and offline demo;
- WORKER_RESULT.md with implemented/absent scope, internal milestones and final exact test results;
- CONTROLLER_HANDOFF.md with execution commands and review pointers;
- B1_RUNTIME_AND_CAPABILITY_BOUNDARY.md with installed package audit and execution-path proof;
- B1_CAUSAL_SNAPSHOT_V2.md with schema, time/availability examples and compatibility from R1;
- B1_PUBLIC_TRANSPORT_LIMITS_AND_RECOVERY.md with allowlist/TLS/retries/persisted lease+cooldown;
- B1_ENDPOINT_COMPATIBILITY.md with documented versus unverified venue schema details, especially funding;
- B1_QA_REPORT.md with a compact test matrix and negative cases;
- evidence/ with original test logs, hashes, fixtures, cold-install inventory, loopback TLS records and demo snapshots;
- SHA256SUMS sealing the whole deliverable except itself.

Avoid redundant governance reports or per-module approval receipts. Internal self-tests, bug fixing and module integration are authorized inside this B1 scope. Escalate only if a material architecture fork, immutable baseline conflict, unexpected worker overlap or unapproved external capability would be necessary.

## 5. Absolute exclusions and stop conditions

No real Binance PUBLIC_MARKET request of any kind.
No private USER_DATA call, credential access, actual signing or account database.
No external Feishu messages, trade, order, cancellation, leverage, transfer or withdrawal action.
No live daemon or scheduled background network service.
No use of geographically evasive proxy/host routing.
No edits to root tracked code, Program J, accepted R1 evidence, historical Controller decisions or docs/engineering files.
No RPI or aggTrades activation, WS production stream, strategy/EXECUTABLE generator, personal position sizing, R2/R3 connector, or Layer 3 execution.
No Strict Research evidence promotion, economic or profitability claims, self-acceptance or new Orchestrator.

An unapproved scope expansion, real network request, detected write conflict or evidence tampering is an immediate STOP / BLOCKED handoff to Controller 0-C.

## 6. Final state

Return READY_FOR_CONTROLLER_REVIEW only after the complete B1 package, offline end-to-end demonstration, negative tests, clear versioned contracts and sealed evidence are complete.

One Controller 0-C consolidated independent acceptance will determine whether B1 is ACCEPTED_OFFLINE_ONLY or must be fixed. It will NOT authorize the first real market scan.

The future first live public scan requires a SEPARATE Owner-controlled operating scope, reviewed region/route/retention/cadence/weights, explicit live enablement and Controller capability activation. R1 Owner standing public attestation is reused, not re-requested.

B2 MARKET_DECISION_MVP and B3 ACCOUNT_AWARE_DECISION_SUPPORT are separately planned work packages; neither is authorized by this B1 task. The human alone executes trades. Layer 3 remains disabled.
