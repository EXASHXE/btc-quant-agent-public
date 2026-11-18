# TASK — QUANT v0.8.0 | R1 PUBLIC_MARKET Personal Mode
## V080-SOL62-PERSONAL-MVP-LAYER1-PUBLIC-01

**Executor:** GPT-6.2 Sol  
**Architecture challenger:** GPT-6.2 Astra  
**Post-delivery mechanical QA:** Gemini 4 Hydrogen  
**Independent dispatcher/reviewer/acceptance:** Controller 0-C  
**Task state:** OWNER_REQUESTED / READY_FOR_0C_REVIEW / NOT_YET_DISPATCHED  
**Project root:** /root/workspace/project/quant-0.8.0/  
**Isolated work root:** workspaces/lt-v080-sol62-personal-mvp-layer1-public-01/  
**GitHub branch:** v0.8.0

This task prompt supersedes the unstarted v0.7.0 manual-forward task for Layer 1. The old v0.7.0 Controller dispatch remains immutable and recorded NOT_STARTED with work_root_created=false. Do not reuse its task ID or worktree.

## 1. Mission

Implement the v0.8.0 PERSONAL_MVP Layer 1 PUBLIC_MARKET data path for Binance USDⓈ-M USDT perpetuals. Reuse and extend the accepted Program J implementation pattern, but keep PERSONAL_MVP policy and code separate from Strict Research and Program J's accepted runtime.

Initial symbols:
- BTCUSDT
- ETHUSDT
- SOLUSDT

Required intervals:
- 1d
- 4h
- 1h
- 15m
- 5m

Required market context:
- exchangeInfo and symbol filters
- 24h ticker
- best bid/ask
- normal depth
- current OI and historical OI
- funding history/current funding
- Mark Price
- optional RPI depth as a separate observation

The product horizon remains 2–12h: 1D background → 4H regime → 1H setup → 15m trigger → 5m actionability.

## 2. Read-first baseline

Read these files before changing anything:
- README.md
- AGENTS.md
- docs/project/V080_PROJECT_HOME_20261118.md
- docs/project/V080_OWNER_REBASELINE_DECISION_20261118.md
- docs/architecture/V080_THREE_LAYER_API_ARCHITECTURE_20261118.md
- docs/architecture/V080_BINANCE_API_ENDPOINT_MATRIX_20261118.md
- docs/project/V080_ROADMAP_AND_GATES_20261118.md
- docs/roles/V080_ACTIVE_ROLE_MATRIX_20261118.md
- OWNER_STANDING_M2_AUTHORIZATION_20261024.md
- baseline/PROGRAM_J_BASELINE_MANIFEST_20261118.json

Program J source snapshot is read-only:
baseline/program-j/

Relevant existing Program J modules include:
- src/btc_quant_agent/platform/live/rest.py
- src/btc_quant_agent/platform/live/source.py
- src/btc_quant_agent/platform/live/models.py
- src/btc_quant_agent/platform/live/policy.json
- src/btc_quant_agent/platform/live/product.py
- src/btc_quant_agent/platform/live/store.py

Program J currently allowlists only /fapi/v1/time, /fapi/v1/exchangeInfo and /fapi/v1/klines; its candle path is limited to 1D/4H/1H and BTC/ETH/SOL. Its strict access model requires a reviewer reference and evidence hashes, applies the prior 50ms wall/monotonic step veto, and has fixed 24-request / 40-weight / 120-second limits. Do not silently reuse these as PERSONAL_MVP requirements and do not weaken or modify Program J in place.

The Owner standing public-data statement is already present at the project root. Its SHA256 is 094780240fb440fc550326fbb3797ee60d26cb9e776374fcbc2c0645818830c6 and its provenance is OWNER_ATTESTED. Do not ask for the same statement again. It is not third-party legal certification and does not authorize proxy/region circumvention.

## 3. Worktree and preservation

1. Create the isolated work root exactly as listed above.
2. Copy the necessary Program J source, tests, configs, contracts and tools into the work root. Preserve source paths and hashes in a baseline input manifest.
3. Do not edit baseline/program-j/.
4. Do not edit accepted Program J/J7 files in the source project or historical v0.7.0 workspaces.
5. Add a separate PERSONAL_MVP module/config/evidence class. Preferred package boundary:
   src/btc_quant_agent/platform/personal_mvp/public_market/
6. Keep Strict Research and PERSONAL_MVP code paths independently selectable. No global change to Program J policy.
7. Keep private account modules absent from R1. No Layer 2 implementation in this task.

## 4. API scope

All R1 requests are public unsigned GETs. No API key or secret is required or permitted.

Required endpoint allowlist:
- GET /fapi/v1/time
- GET /fapi/v1/exchangeInfo
- GET /fapi/v1/klines
- GET /fapi/v1/ticker/24hr
- GET /fapi/v1/ticker/bookTicker
- GET /fapi/v1/depth
- GET /fapi/v1/openInterest
- GET /futures/data/openInterestHist
- GET /fapi/v1/fundingRate
- GET /fapi/v1/premiumIndex

Optional, separately labeled:
- GET /fapi/v1/rpiDepth
- GET /fapi/v1/aggTrades

No other endpoint is allowed without a Controller-reviewed task amendment. Never call private USER_DATA or any TRADE endpoint.

Use exchangeInfo to validate instrument type, status, quote/margin assets and symbol filters. Maintain a versioned endpoint-weight table from current official documentation and account for response headers; exchangeInfo rateLimits are not a substitute for endpoint-specific weights.

Normal depth excludes RPI orders. If RPI depth is implemented, retain it as a separate observation with distinct semantics. Do not merge it into ordinary depth or claim the book is complete.

## 5. PERSONAL_MVP time and freshness policy

Implement a separate practical personal mode:
- normal Windows/OS time synchronization for local wall time;
- monotonic clock for elapsed duration and local ordering;
- bracket Binance /fapi/v1/time calls and estimate venue/local offset plus uncertainty;
- use venue candle timestamps as bar identity;
- configurable candle-close grace and per-data-type freshness thresholds;
- per-run quarantine/reacquisition when time offset cannot be reconciled;
- no mandatory independent NTS, hardware witness or unconditional 50ms wall-step rejection.

Do not relabel Binance serverTime as independent authenticated UTC. Do not change Strict Research clock rules.

Initial close grace may default to 2 seconds but must be configurable and justified by tests. A forming candle may be displayed as live context but must never confirm a setup or trigger.

## 6. Data contracts and correctness

- Five timeframes must be supported end to end.
- Kline closeTime is inclusive; normalize the bar end to closeTime + 1.
- Validate alignment, OHLC consistency, finite numeric values, volume non-negativity, duplicates, ordering and gaps.
- Use Decimal for exchange price/quantity/filter calculations; avoid float rounding in identities and risk calculations.
- Preserve raw response bytes/hash, endpoint, params, HTTP status, request/receive samples, local monotonic sequence, venue-time estimate and response headers needed for audit.
- Preserve source timestamps and local availability separately. If exchange publication time is unavailable, mark it UNKNOWN.
- Never fabricate historical availability at candle close for a backfilled row.
- Revisions or conflicting bytes for an existing candle identity must be quarantined and surfaced, not silently overwritten.
- Cache incrementally and avoid refetching full histories on every scan.
- The public-market evidence class must be PERSONAL_PUBLIC_MARKET, never Strict Source/E1.

## 7. Rate limits, retries and region behavior

- Use a configurable dynamic request/weight budget derived from endpoint weights, exchangeInfo ceilings and response headers.
- Do not hard-code 24 requests / 40 weight / 120 seconds as permanent product ceilings.
- Respect HTTP 429 and Retry-After. Back off and stop on HTTP 418.
- At most one bounded retry for a clearly transient idempotent GET failure. No retry for permission, malformed schema, 403/451, explicit region restriction or blocked network.
- No proxy rotation, alternate region, DNS manipulation or direct-fallback bypass.
- Verify TLS hostname and certificate chain. Never disable certificate verification.
- Do not create unattended polling loops. R1 should support an explicit bounded scan invocation.

## 8. Strategy integration boundary

R1 provides normalized public market data and a market-side decision input only. It does not know the Owner's actual positions.

When Layer 2 is absent, expose account context as ACCOUNT_CONTEXT_UNAVAILABLE. Do not block all market analysis, but do not imply existing positions, conflicting exposure or existing TP/SL were checked.

Keep separate fields:
- market_setup_status: EXECUTABLE / WATCH / INVALID / NO_SETUP / SOURCE_BLOCKED
- account_context_status: UNAVAILABLE for R1
- human_actionability: manual account check required when private context is absent

Any EXECUTABLE value is an advisory market-side classification only; it never places an order.

## 9. Explicit prohibitions

- No real Binance request during implementation, tests or QA.
- No live public API call, including /time or /exchangeInfo.
- No API key/secret creation, reading, request or configuration.
- No private USER_DATA endpoint or account data.
- No Layer 2 signer, credential store or account database in R1.
- No order placement, cancellation, amendment, leverage, margin, transfer or withdrawal.
- No Feishu send.
- No production host/time-service/network changes.
- No edits to Program J baseline or historical Controller decisions.
- No synthetic data represented as real market data.

All tests use deterministic fixtures, Mock transport or loopback-only fabricated TLS. No external network.

## 10. Required tests

### Positive
- Five intervals for BTC/ETH/SOL parse, normalize, persist and reload.
- Ticker, bookTicker, depth, OI, OI history, funding and premiumIndex schemas.
- exchangeInfo symbol/filter validation.
- Incremental refresh does not duplicate or overwrite unchanged bars.
- Venue-time offset bracket and normal OS clock operation.
- Dynamic weight accounting and response-header reconciliation.

### Negative and boundary
- Forming 5m/15m candle cannot confirm trigger.
- CloseTime inclusive/exclusive boundary off by one.
- Missing, duplicate, reordered, stale, future, revised or malformed bars.
- Wrong contractType, quoteAsset, marginAsset or inactive symbol.
- Decimal overflow/nonfinite values and invalid OHLC.
- Depth truncation and RPI-vs-normal-depth separation.
- 429 with Retry-After, 418 ban, 403/451 restriction and transient timeout.
- TLS hostname/certificate failure.
- Unreconcilable serverTime offset quarantines only the run.
- Forbidden endpoint, non-GET method, unknown route and credential access all fail before transport.
- Strict Research/Program J path remains byte/hash unchanged.
- PERSONAL_MVP data cannot be relabeled Strict Source/E1 or strict Shadow.

### Cross-platform and packaging
- Run targeted pytest, full offline pytest suite, ruff, mypy where configured, compileall and package build.
- Report PASS/FAIL/SKIP separately; do not hide skips.
- No network test may be silently skipped and then reported as passed.

## 11. Deliverables

Inside the isolated work root:
1. Implementation source and versioned PERSONAL_MVP policy/config.
2. Deterministic fixtures and tests.
3. Exact source-baseline manifest and post-change preservation comparison.
4. Test logs, command list, environment versions and machine/runtime details.
5. Endpoint weight matrix with source URL and verification date.
6. Local operator runbook and a future bounded-scan plan (plan only; do not run it).
7. A draft PERSONAL_PUBLIC_MARKET operating-scope config based on governance/V080_PERSONAL_PUBLIC_MARKET_SCOPE_TEMPLATE_20261118.json; keep it NOT_ACTIVE and do not perform a live scan.
8. WORKER_RESULT.md and CONTROLLER_HANDOFF.md.
9. SHA256SUMS for every deliverable; manifest excludes itself.
10. Explicit statement of all external effects: expected zero.

## 12. Stop conditions

Stop and report BLOCKED if:
- Program J baseline manifest mismatches;
- required source path or dependency is absent;
- implementing PERSONAL_MVP would require modifying accepted Program J files;
- API docs contradict the endpoint contract and cannot be resolved without an architecture decision;
- any test attempts external network or credential access;
- a permission or regional restriction appears;
- a proposed change introduces Layer 2 or Layer 3.

Do not improvise a scope expansion. Ask Controller 0-C for a scoped design decision.

## 13. Completion status

Return READY_FOR_CONTROLLER_REVIEW only when all offline evidence and handoff files exist. Otherwise return BLOCKED with exact missing evidence.

Worker completion is not Controller acceptance. Do not mark the task ACCEPTED or dispatch R2 yourself.
