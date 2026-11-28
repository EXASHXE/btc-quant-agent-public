# QUANT v0.8.0 — B4 Public Source Bridge & First Bounded Scan Readiness

> **Current navigation (2026-11-28):** [Wave D checkpoint](../../project/V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](../../project/V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.

Task ID: V080-PERSONAL-MVP-PUBLIC-SOURCE-BRIDGE-B4-01
Primary executor: GPT-6.2 Sol Extra High
Peer alternative: Gemini Neon XHigh if Sol capacity/quota is insufficient
Controller: 0-C — single independent integrated acceptance
Task status: CONTROLLER_SCOPE_APPROVED / AWAITING_OWNER_FORWARD / NOT_STARTED
Capability: OFFLINE IMPLEMENTATION ONLY. This task DOES NOT authorize any genuine Binance request.

## 0. Product objective and non-negotiable restrictions

Deliver one substantial, installable B4 engineering package connecting the accepted B1 public runtime to the accepted B2 2–12h human market-decision workflow through a provenance-preserving, production-shaped **genuine public market source bridge** and an explicit future first-scan activation boundary.

Today B1 genuine mode always raises LIVE_CAPABILITY_DORMANT; B2's accepted adapter admits only fixture/loopback synthetic origins. Do NOT pretend either already supports genuine Binance data. B4 must introduce versioned source admission and integration, not rename a fixture to "real".

The integrated task has four internal phases: genuine-source transport/budget boundary, causal market persistence and adapter, B2 decision-card/reprice integration, and bounded first-scan runbook/negative QA. One core writer, one final READY_FOR_CONTROLLER_REVIEW, one Controller audit. No internal microtask approvals unless material architectural/security conflict.

**No real Binance API calls, DNS lookups to Binance, private USER_DATA reads, credentials, live activation, proxy changes, Feishu, trade API calls, deployment, external transmissions or market orders.** Run all tests/build/demo against offline fixtures or explicitly bounded local loopback HTTPS. The actual first genuine-public scan requires a separate Owner-completed local operating scope and Controller-accepted activation. Nothing here is permission to run it.

PERSONAL_MVP is read-only research/decision support, 1D background / 4H regime / 1H setup / 15m trigger / 5m actionability, 2–12h target hold, human-only execution. Synthetic B4 "EXECUTABLE" is NOT a live opportunity or order instruction.

## 1. Exact baseline and preflight

Code root: /root/workspace/project/quant-0.8.0/
Code branch/head at Controller preparation: v0.8.0 @ bd144f2d15836bb84786c91aec571df77351bf5c
Canonical docs root: /root/workspace/project/quant-docs-engineering/
Docs branch/head at Controller preparation: docs/engineering @ ce43c43f71f88e3aac61e913e10829d8a0c311a9
New isolated work root: workspaces/lt-v080-personal-mvp-public-source-bridge-b4-01/

Upstream accepted immutable inputs:
- B1: workspaces/lt-v080-sol62-personal-mvp-public-runtime-foundation-b1-01/; SHA256SUMS SHA 73af3d2e273e9d4c6865fe3fe935939c4ae64a7a1475c4bb0ab99ceef319f7a5; controller acceptance b42ad44bc91a5fe89e7e2209ba4682ca5232d6611c5340b2b5febfe356a08cbf.
- B2: workspaces/lt-v080-sol62-personal-mvp-market-decision-b2-01/; SHA256SUMS SHA 8c908905eaa8002e12f53f1d78939b15726658726c20b19abc66c673c6a58368; controller acceptance 7de93eed45541d09a3b65b3e8452033c894ad402a169306bd97e4952929ac48d.
- B3: workspaces/lt-v080-personal-mvp-account-aware-b3-01/; SHA256SUMS SHA b652ffdc79a0392612c19f02542df3713baf0ab82bd12af5c0eae017c596e54b; controller acceptance 0d3b88ea3bcedeab9f8d18d8118929be4610ecfa433d2bd35cd6fc7f96b8d7a0. B3 is NOT a dependency of B4; must remain disconnected.
- R1, Astra and Program J accepted historical artifacts must stay byte-identical.

Read latest docs/engineering:
docs/project/V080_PROJECT_HOME_20261118.md
docs/project/V080_ROADMAP_AND_GATES_20261118.md
docs/project/V080_MODEL_ROUTING_POLICY_20261119.md
docs/architecture/V080_THREE_LAYER_API_ARCHITECTURE_20261118.md
docs/architecture/V080_BINANCE_API_ENDPOINT_MATRIX_20261118.md
docs/roles/V080_ACTIVE_ROLE_MATRIX_20261118.md
and the source of governance/V080_PERSONAL_PUBLIC_MARKET_SCOPE_TEMPLATE_20261118.json.

Inspect B1 live.py, runtime.py, wire.py, policy.py, budget.py, session.py, store.py and B2 adapter.py, model.py, engine.py, strategy.py, risk.py, journal.py. Establish actual public interfaces before coding. The existing B1 and B2 wheel/package files are immutable. If no safe B4 adapter can bridge B1/B2 without mutating accepted packages, STOP with a specific interface-blocker report.

Check clean branches, original SHA digests, B4 workspace absence/ownership and actual model identifier from the execution interface. For this task Sol is the default executor; Neon is an equally approved alternative, but never a simultaneous writer of the same B4 package.

## 2. A — Production-shaped but still dormant genuine-public transport

Implement a separate installable B4 namespace, e.g. quant_personal_public_bridge_b4, with explicit pinned B1/B2 wheel dependencies. Expose a strict runtime separation:
- FIXTURE and LOOPBACK_HTTPS_QA remain synthetic.
- GENUINE_PUBLIC_MARKET is a new, separate evidence origin; can be created only from a future validated Owner scope + Controller activation.
- This **offline B4 build** must not ship a runnable genuine network entrypoint; invoking live-scan returns LIVE_CAPABILITY_NOT_ACTIVATED (or an exact equivalent) before DNS, socket, secret lookup or request budgeting. A mere environment variable, CLI flag, config edit or fabricated JSON cannot enable it.

Build a testable real-shaped network-adapter interface and an injected loopback HTTPS implementation. Target host is pinned to the approved official Binance USDⓈ-M Futures host only when later activated (default documented base: fapi.binance.com), with strict certificate/hostname/TLS chain validation, no redirect, no fallback host, no IP literals, no downgrade, no arbitrary CA injection, no proxy/region bypass and no generic arbitrary URL caller. The first live release will require its own separately reviewed physical-origin binding rather than simply removing the dormant flag.

Exact unsigned GET-only 10-endpoint allowlist (no key/signature/private input):
GET /fapi/v1/time
GET /fapi/v1/exchangeInfo
GET /fapi/v1/klines
GET /fapi/v1/ticker/24hr
GET /fapi/v1/ticker/bookTicker
GET /fapi/v1/depth
GET /fapi/v1/openInterest
GET /futures/data/openInterestHist
GET /fapi/v1/fundingRate
GET /fapi/v1/premiumIndex

No RPI, aggTrades or extra venue API endpoints without separately revised scope. Per-route strict parameter/symbol/interval validation must happen **again immediately before transport**. Input symbols initially BTCUSDT, ETHUSDT, SOLUSDT; exactly five timeframe intervals 1d,4h,1h,15m,5m. Block POST/PUT/PATCH/DELETE, private/trade routes, malformed encoding, query-path aliases, unexpected parameters and symbol/interval expansion.

Version endpoint weights from the latest **official USDⓈ-M** documentation (not Spot or COIN-M). Include fetch date, source URLs, ambiguous/not-yet-verified rules and per-route weight calculations. Cross-check request weights against runtime response headers and /exchangeInfo limits. Do not assume old fixed offline budgets or a particular minute ceiling is universal.

## 3. B — Limits, venue denial and causal storage

Reuse proven B1 semantics using a bounded read-only B4 interface rather than mutating accepted B1. Protect physical egress as well as the B4 process: cross-process persistent SQLite budget reservations, pre-dispatch debit, bounded retries, crash/restart durability, response weight headers and a documented shared-IP/other-program limitation. Never reset exchange cooldown by restarting.

On HTTP 429 persist Retry-After/cooldown and stop the affected run; HTTP 418 persist a venue/IP ban; HTTP 403/451 or a documented regional restriction must hard stop with no alternate egress or bypass. TLS/certificate/hostname failures and redirect attempts fail closed. 5xx/408/network timeout are SOURCE_BLOCKED with at most one narrowly justified idempotent GET retry under the same budget. Malformed/oversize/partial JSON, mismatched symbols/time, clock uncertainty and data contradictions block promotion.

Define a versioned B4 source receipt and storage contract that distinguishes request start, receive, exchange event/close time, local durable commit, first publication, and subsequent evaluation as-of. When a venue source-publication timestamp does not exist, it remains UNKNOWN; receipt/commit times must never be relabeled as source publication.

Use only closed, gap-free completed bars for confirmation. Kline inclusive close time becomes exclusive boundary closeTime+1. Reject a newly backfilled or revised bar from affecting an earlier evaluation. Preserve raw response hash, normalized digest, partial/gap/revision history and exact source origin. Upstream accepted B1 V1/V2 archives must not be reinterpreted as genuine.

Use existing B1 warmup/incremental cache behavior, but design a first bootstrap that obtains sufficient contiguous five-frame candles and then performs efficient ongoing updates; fast 5m/15m quote/depth/mark/OI refresh is distinct from slow funding/history/meta. Avoid unbounded warmup and rate spikes. Persist and safely reopen after process crash. A failed symbol must not rewrite another symbol's historical decision; global rate/venue bans must stop the run globally.

## 4. C — B2 market decision bridge and human reprice

The accepted B2 adapter currently admits only QA origins. Implement a new versioned B4 genuine-origin admission layer with **strictly stronger** provenance validation and independent conformance tests. Do not disable B2 checks, forge SYNTHETIC_QA_ONLY as genuine, monkeypatch accepted wheels, or mutate B2 journal schema.

Provide a narrowly versioned compatibility API that reuses accepted B2 4H/1H/15m/5m strategy and Decimal risk math while preserving input provenance. Where B2's accepted adapter is not extensible, create a B4-owned adapter that verifies equivalent causal invariants before constructing the B2 Market object and calling the unchanged pure strategy/risk engine. Never bypass hash, window, age, bar finality or as-of checks to force a card. Explicitly document any duplicated validation and demonstrate it by fail-first negatives.

Produce synthetic **B4-shaped** E2E cards for both setup families and directions with:
- Market status EXECUTABLE/WATCH/INVALID/NO_SETUP/SOURCE_BLOCKED/NOT_EVALUATED, not conflating source readiness with signal evaluation.
- Signal K, independent closed 15m confirmation, 5m actionability, 4H regime, 1D context.
- Reference entry zone, hard stop, TP1/TP2/TP3 or blocked reason, first 4H/1D opposing barrier, ATR, OI, mark, spread/depth, funding, all estimated costs, net R and no-chase rules.
- Immutable SignalEpisode and appended +5/+10 minute reprices. A later observation cannot alter the earlier card.
- Local human decision journal. Account context stays UNAVAILABLE and MANUAL_ACCOUNT_CHECK_REQUIRED; no portfolio-cleared sizing or "safe to trade" conclusion.

Cards based on mock/loopback data must carry clear SYNTHETIC_QA_ONLY / NOT_GENUINE_MARKET warnings even when they exercise the new B4 adapter. Only a later genuinely sourced and separately admitted activation could produce PERSONAL_PUBLIC_MARKET_GENUINE evidence.

Prepare human-use CLI commands for local inspect, dry-run, full readiness report, card view and local replay. No daemon or Feishu.

## 5. D — First bounded genuine scan activation packet (PREPARE ONLY)

Prepare an actionable **inactive** owner scope candidate derived from the existing governance template, never silently modifying that historical template or marking it ACTIVE. It must enumerate:
- Owner-controlled local operating region and approved direct network route (placeholders if not supplied); do not invent these.
- Official pinned host and allowed exact 10 GET routes, initial 3 symbols and 5 frames.
- Explicit one-time bootstrap + later incremental cadence, request-count/weight budgets calculated from the versioned weights and response-header rules; separate stop/cooldown thresholds.
- Local retention, public source evidence path, max response size, timeouts, budget recovery, source timestamps, symbol-level isolation and 5–10m refresh policy.
- Event log and no-real-trading disclaimer; prohibition of private credentials, Layer3, Feishu, region bypass or automated sends.
- A literal, auditable **NOT_AUTHORIZED / LIVE_DISABLED** field that survives reboot and CLI defaults.

Produce PRE_ACTIVATION_CHECKLIST.md, FIRST_BOUNDED_SCAN_RUNBOOK.md and proposed scope JSON. Describe the specific separate Controller and Owner action required to enable a future first real public scan. Include command templates only if the live command is nonfunctional in this delivered wheel; mark all genuine commands NOT EXECUTABLE UNTIL ACTIVATION. Do not ask Owner to repeat the existing standing personal public-data attestation or paste private identity, location/address or credentials.

The future first genuine run should demonstrate response schema conformity, 5-frame closed-candle completeness, source freshness, per-endpoint weights, quote/depth/mark/OI/funding consistency and B2 card reprice, then either accept real MARKET_SIDE eligibility or SOURCE_BLOCKED with explicit reasons. This is an acceptance plan, not an instruction to run it now.

## 6. Acceptance tests — one consolidated offline matrix

Mandatory:
1. Clean wheel installation with pinned B1 and B2; no B3/private/legacy execution imports.
2. Exact 10 GET route allowlist; missing/excess params, mutated symbol/timeframe and private/trade methods rejected before any mock transport.
3. Loopback HTTPS certificate mismatch, wrong host/SNI, redirect, oversized body, truncated response, stale/malformed data, timeout, inconsistent clock, WAF and restriction failures; zero remote DNS/network. Avoid monkeypatching TLS to always succeed.
4. 429/418/403/451 persisted global stops across fresh process restarts; concurrent request budgets and actual headers; failures charge budget and cannot be retried to circumvent ban.
5. Bar finality/gaps/revisions/backfills; 1D/4H/1H/15m/5m causal filtering; first known availability and publication evidence.
6. Real-shaped mock funding/OI semantics, including funding history time windows and OI history retention; metadata filters and correct decimal rounding.
7. B4 adapter provenance forgery, QA-to-genuine relabel, wrong publication SHA, late depth/mark/OI, missing raw receipts and historical retroactive decisions all fail closed.
8. B2 both families × both directions positive synthetic cards, 5m no-chase negatives, 5/10m reprice, immutable journal and failure recovery.
9. Genuine-public mode remains disabled in **every install path**, including hostile environment variables, copied config, alternate CLI entrypoints, mixed installed packages, and process restarts.
10. Recompute at least several Decimal risk/net-R paths independently from raw synthetic inputs; no trading profitability claim.
11. All B1/B2/B3/R1/Astra/Program J seal hashes remain unchanged; code v0.8.0 and docs/engineering tracked trees remain clean.
12. All tests and demos in network-isolated namespace; no genuine Binance requests, real key/secret access, private account reads, trade execution, Feishu, upload or deployment.

Do not impose an arbitrary test-count quota. Report actual PASS/FAIL/SKIP and exact commands, run parameters and independent hashes.

## 7. Required final artifacts and stop conditions

All new writable files stay under:
workspaces/lt-v080-personal-mvp-public-source-bridge-b4-01/

Deliver one installable B4 wheel, tests, synthetic input fixtures, local CLI, offline E2E logs, clean/mixed install evidence, raw-to-card replay, source-contract documentation, endpoint weight/source table, operating scope candidate, preactivation checklist, first scan runbook, B4_QA_REPORT.md, WORKER_RESULT.md, CONTROLLER_HANDOFF.md and deterministic SHA256SUMS sealing **every** final file (no symlinks/path escapes/self-entry). Independently run sha256sum -c SHA256SUMS, and include manifest and wheel digests.

Abort immediately and report to Controller if:
- accepted B1/B2 contracts cannot be bridged without modifying accepted wheels;
- the implementation needs actual exchange network calls, credential/secret access, region bypass or a TRADE method;
- a source admission shortcut would falsely promote fixture data to genuine;
- the proposed physical route or first-scan scope is unspecified but a real run is being attempted;
- an overlapping core worker or contested write set exists;
- any pre-existing accepted artifact differs from its pinned SHA.

Perform complete internal engineering and corrections within B4; do not request approvals for individual coding steps. Handoff once as READY_FOR_CONTROLLER_REVIEW. This is NOT self-acceptance. The maximum acceptance from this package is **SCOPED_ACCEPTED_OFFLINE_PUBLIC_BRIDGE_ONLY**. The first real scan, and any further source admission, require a separate Owner+Controller activation and real-source evidence gate; they are not authorized by this prompt.

Finally respond in concise Chinese with the task ID, actual executor/model and reasoning, package root/wheel, modules, true live-gate status, QA commands/results, sealed SHA manifests, B1/B2 preservation evidence, pre-activation checklist, limitations and READY_FOR_CONTROLLER_REVIEW.
