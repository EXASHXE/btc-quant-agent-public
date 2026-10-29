# V070-L4-READONLY-SOURCE-CANARY-01 — Revised 2026-10-29

Role: Codex Autonomous Public-Source Admission & Local Shadow Advisory Engineer.
Controller: Quant v0.7.0 Controller 0-C.
Cadence: one substantial A/B/C mandate, autonomous internal implementation/tests/repairs, one consolidated milestone receipt. No parallel task or intermediate standing audit.
Status: **PHASE A AUTHORIZED NOW** under the Owner's existing isolated engineering/synthetic-test scope; **PHASE B/C REAL-MARKET READS NOT AUTHORIZED** without a later exact Owner source grant.
This task card is not an Owner grant for public-data acquisition, deployment, accounts or notifications.

## 0. Baseline, scope, concurrence and preservation

Read the latest EXASHXE/btc-quant-agent-public \`docs/engineering\` AGENTS.md, branch policy, mission, roles, roadmap, handoff and this existing revised mandate. Verify actual local code and evidence in \`/root/workspace/project/quant-0.7.0/l23-selector-evaluation-01\`: L23_FINAL_DELIVERY.md, L23_ACCEPTANCE.json, L23_TEST_MATRIX.json, L23_PRESERVATION.json, L23_SOURCE_SELECTOR_CONTRACT.md and \`artifacts/final/source_readiness.json\`. Also inspect the bridge and platform baselines, exact changed source and tests.

L23 = **ACCEPT isolated/offline synthetic engineering only**, 482 unique passes, exactly three unchanged legacy-contract fails (separate passing replacements), three independent structural fabricated episodes, no real source/Alpha validation. L23 includes 5m structural history, 1m monitoring, per-field provenance, stateful deterministic V1 and user-reported position management. Treat each feature's actual implemented warmup and gating contract as authoritative; do not assume Astro/Astra research hypotheses were implemented.

Before workspace creation, check live Codex ownership and existing L4 evidence. If another worker is performing the same task, STOP rather than duplicate it. Create only \`/root/workspace/project/quant-0.7.0/l4-readonly-source-canary-01\` under the authorized isolated engineering scope. Copy allowlisted code, configs, tests and fabricated fixtures; never copy secrets, runtime stores, protected forward/historical data, original .git directories or account material. Record pre/post source hashes, test names and worktree fingerprints. Preserve dirty R/M/Q worktrees and indexes, all prior isolated baselines, registry/PRIMARY, and the Q collector without touching, controlling or restarting it.

## A. AUTHORIZED NOW — Offline transport, policy and failure-injection engineering

Work autonomously, without another Owner sign-off, on source-transport interfaces that are **disabled by default and cannot open a real network connection**. Use only simulated HTTP/WebSocket responses and locally generated clocks. Implement deterministic source classification, per-source admission and fault-injection tests for timeouts, disconnects, duplicate/out-of-order updates, missing timestamps, invalid venue/symbol/units, precision/contract changes, backpressure, rate-limit responses, receiver clock drift, reconnect gaps and source recovery. Reuse the existing L23 selector, bridge decoders, risk/store/outbox; do not rebuild them.

Build a versioned acquisition policy and **per-endpoint/per-stream matrix**. A row MUST contain:
- Provider, legal/region-specific API host, market (USD-M/COIN-M/spot or OKX SWAP/SPOT), instrument/contract type, exact endpoint or stream and authenticated/public status.
- Native fields/units, event/transaction timestamp field and documented semantics (or UNKNOWN), trading status, contract multiplier, tick/lot/min-notional rules, native update/push cadence, completion rule and freshness TTL.
- REST request-weight formula per symbol/limit, per-minute projected weight and applicable IP/rate caps; or WS connection, subscriptions, expected message rate, incoming control-message limits, heartbeat/reconnect and gap behavior.
- Proposed acquisition cadence, failover policy, required L23 features, estimated bytes/storage, retention, documentation version/reference URL and permission/terms review result.
- Status \`OFFLINE_SCHEMA_REVIEWED\`, \`UNVERIFIED_NATIVE\`, \`SOURCE_CLOCK_BLOCKED\`, \`READY_FOR_OWNER_GRANT\`, or \`DISABLED\`. Never convert review of documentation to observed feed quality.

### Endpoint-specific candidate acquisition matrix (planning ONLY; not an access grant)

| Feed | Candidate transport and pacing | Required qualification |
|---|---|---|
| Binance USD-M perpetual contract/rules | Public \`GET /fapi/v1/exchangeInfo\`: start, relevant trading-state changes and end; periodic refresh only if configured | Exact \`fapi\`/USDT linear contract identity, filters, statuses, contract metadata, weight, update limits. Do not substitute \`dapi\` COIN-M or spot \`api\` paths. |
| Binance USD-M best bid/ask and size | Prefer individual public \`<symbol>@bookTicker\` WS through officially verified USD-M public stream host. Count one subscription per symbol and event-driven messages; no 1-second REST polling by default | Validate actual payload \`E\` event vs \`T\` transaction meanings, update ID, venue, symbol, native quantities, ordering, 24h connection/reconnect rules and burst rates. REST \`GET /fapi/v1/ticker/bookTicker\` only as timestamp-qualified, explicitly budgeted fallback; its native \`time\` semantics must be verified on the exact deployed response. Top-of-book is NOT guaranteed liquidity/fill. |
| Completed 1m/5m perpetual candles | Prefer qualified native public kline streams or batch public \`GET /fapi/v1/klines\` on completion/repair schedule | Only closed bars with availability after completion, exact interval boundaries, missing-bar repair and receive clocks. No per-second candle REST polling. |
| Binance USD-M OI | Public \`GET /fapi/v1/openInterest\` or a separately verified native stream if documented | Point-in-time units, timestamp, provider-defined cadence, sampling delay and request weight; lack of consistent consecutive observations blocks shock cessation. Do not alias historical OI statistics as live OI. |
| Binance USD-M funding/mark | Public \`GET /fapi/v1/premiumIndex\`, \`/fapi/v1/fundingInfo\`, or an approved mark/funding stream | Rate, next settlement, variable funding cadence, mark provenance and native publish time. Snapshot is not settled cash. Poll only as needed by source changes/expiry rather than every second. |
| USD-M spot reference | Separately authorized Binance spot public kline/quote feeds and host | Spot-vs-perpetual symbol map, matched 1m/5m bars, separate receive/event timestamps; USD-M permission does not automatically authorize spot. |
| Liquidity/universe | Public 24h ticker/turnover statistics at declared source cadence; eligible contract metadata | Quote turnover units, 24h rolling-window semantics, sample quality, minimum 10 synchronized symbols for percentile ranking; three-symbol pilot may use absolute gates/WATCH only. |
| OKX alternative (not active unless independently granted) | Public \`/api/v5/public/instruments\`, \`/api/v5/market/candles\`, SWAP \`tickers\`/qualified BBO WS, public funding/OI, and matching SPOT fields | \`BTC-USDT-SWAP\` versus \`BTC-USDT\`, \`ctVal\`/contract units and \`ts\` semantics, region-correct hosts, public WS quotas and channel eligibility; do not assume every OKX ticker \`ts\` is a matching-engine event timestamp. |

The above names are candidate interfaces, not verified operational eligibility. Before Phase B, check **current official provider API docs, changelogs, permitted-use/terms, venue/region, channel access rules and concrete per-endpoint weights**. Record specific version/date and live-eligibility uncertainty. Do not derive USD-M stream properties from COIN-M or spot documentation. No private/user-data endpoints, keys or auth.

**Budget preflight:** derive projected REST weight as \`sum(weight(endpoint, params, symbols) * planned_calls_per_min)\`; add a separate bounded retry/gap-repair reserve and hard per-IP/per-endpoint throttle. WS: record symbol × channel subscriptions, control messages per second, observed/expected data message rates, CPU/disk pressure and reconnect cap. Choose an Owner-approved hard budget comfortably below the actual current official ceiling; if weight or ceiling is unknown, endpoint is not approved. Implement local counters, immediate circuit-break on breach/429/418/venue-specific throttling, bounded backoff and no retry storm. Offline fixtures must reproduce these failure modes.

## Source-clock qualification and admission invariant

Preserve the source's native event/transaction/publish timestamp **with a verified semantic label**; local request-start wall and monotonic times, response-first/complete receive wall and monotonic times, parse/normalization available time, decision time and commit time. Where meaningful, retain actual notification acceptance and separately observed delivery/acknowledgment times; offline shadow uses labeled assumptions, not observations.

Collect bounded server-time probes where expressly authorized, with monotonic RTT, local-offset estimate and jitter, clock-sync evidence and a conservative uncertainty interval. Differentiate \`measured_local_elapsed\` from \`event_to_receive_estimate ± clock_uncertainty\`. Clock-offset estimates cannot manufacture a missing exchange timestamp, guarantee one-way latency or override provider event semantics. Local wall clock jumps/time-sync failures force downgrade. Validate wrong-symbol binding, stale/future/duplicated/out-of-order messages, schema/contract changes, reconnect holes and source identity changes with reason-coded fail-closed behavior.

A verified native best bid/ask and visible quantities provide a **bounded executable-quote observation** under freshness and capacity haircuts; they do not establish real fill, queue priority, hidden depth or slippage. Missing/undocumented venue timestamps remain UNKNOWN and may permit local WATCH/RISK only, not actionable eligibility.

## Warmup and history constraints

Derive and freeze the exact predeclared readiness warmup from the ENABLED L23 features, not from number of elapsed hours alone:
- Completed 5m EMA20/EMA40, ADX14, ATR14, ER20, confirmed structural channels/pivots and L23 prior-60-bar volatility/shock proxy; require the **maximum actual causal dependency window plus confirmation bars** with no gap. A 60-bar proxy is not the proposed 20-day volatility-percentile implementation.
- L23 beta/correlation/ranking and portfolio sizing may require **200 preceding aligned 5m return observations**, and any configured 288-observation reference may demand more. Count completed bars/returns and valid universe/benchmark membership, not partial bars; count successful cross-symbol coverage separately.
- Entry monitoring requires two distinct continuous completed 1m confirmation observations after its known setup, and new qualified quote evidence at delayed acknowledgment; no same-bar completion/fill assumption.
- Three-symbol Stage 1 cannot qualify >=10-member percentile ranking; absolute-gate WATCH and risk/source qualification can still succeed.
- A proposed 26-hour *future-only* collection may be adequate for a subset of short-window gates if uninterrupted; it **cannot** supply a 10–20-day volatility percentile history or guarantee full multi-symbol/strategy warmup. Do not backfill protected data or silently use post-pilot timestamps. Disable unready features and record \`WARMUP_INSUFFICIENT\`; actionable strategy gating remains unavailable until all specific prerequisites are met. Distinguish \`source-qualified\` from \`strategy-ready\`.

## Retention and bounded autonomous stop

Resolve the 26h collection versus 24h raw-retention conflict: **recommend and propose 36h minimum rolling raw receipt retention** (the earliest retained raw data then remains available for at least 10h after a 26h pilot), and approved 7d normalized observation retention; both require the Owner's exact source/retention grant and a predeclared byte quota. Retain immutable SHA256 chunks, manifests, UTC ranges, source/normalizer versions, replay crosschecks and representative raw schemas. Implement total/symbol/chunk quotas, atomic writes, audit checks, expiry and clean UTC stop. Storage pressure triggers deterministic shedding of optional diagnostic samples or an explicit \`STORAGE_BLOCKED\` stop, NEVER silent corruption or loss of source qualification evidence.

If the Owner instead approves only 24h raw retention, deliver an immutable audited prefix manifest/checksums, representative raw snapshots, normalized replay parity and an explicit \`EARLIEST_RAW_NOT_RETAINED\` limitation; never claim complete 26h raw replay. Permission to retain records cannot exceed terms or Owner scope. At approved end time, close subscriptions, finalize checksums and cease the canary; no recurring collector, daemon or background continuation.

## B. CONDITIONAL — Exact Owner-granted public-data canary

**Hard stop before any network market call:** require an unambiguous machine-readable Owner grant naming provider+region+market, every public endpoint/stream and fields, symbols, UTC start/end, rate/weight/connection budgets, bytes and expiry retention, isolated output path, and explicit permitted-use status. The L23 proposal of 2026-11-01T00:00:00Z to 2026-11-02T02:00:00Z (26h) is **UNAPPROVED, NOT SCHEDULED**. Absent or mismatched grant: complete Phase A, emit \`OFFLINE_READY_PENDING_AUTH\`, and **terminate immediately**; do not idle, repeatedly poll for approval or create a standing automation/background collector.

After the exact grant and fresh official-doc verification, begin with BTCUSDT, ETHUSDT and SOLUSDT *only*, within its approved endpoints. Start with a bounded schema/clock observation, then stable stream integrity, only then conditional expansion to specifically approved additional symbols (up to the L23-proposed 12 if included in the grant). Every expansion requires the **predeclared** per-source acceptance checks: timestamp semantics verified (or blocked), instrument units/filter correctness, expected contiguous closed-bar coverage, freshness distributions and stale-event veto, bounded arrival uncertainty, no uncontrolled rate-limit violation, reconnect/gap recovery, storage/CPU budgets and matching source identity. No human micro-approval to expand WITHIN an already approved 12-symbol scope if these deterministic checks pass.

Predeclare numeric tolerances in the approved run configuration before first market read (e.g. per-field bar completeness, source-age upper bounds, reconnect-gap duration and clock uncertainty; use current L23 5s quote lease only where source semantics justify it). Never tune acceptance thresholds after seeing outcomes. Source qualification may pass in a quiet market with **zero opportunities**. Stop/downgrade ACTION whenever source clock or venue contract semantics are unqualified, persistent gaps occur, rate ceilings are breached, required warmup fails, or the clock-estimate uncertainty exceeds the quote lease. Never synthesize favorable conditions to meet a trade count.

## C. CONDITIONAL — Local-only shadow advisory

If B is authorized and individual sources are qualified, reuse L23's selector/position ledger/outbox **without external send**. Compute per-field availability/missingness, event→receive→available→decision intervals with uncertainty, stream updates/second, subscriptions, weighted REST requests, quote age, reconnects, disk/CPU/memory, strategy rank→setup→trigger→veto→readiness funnel, missed-entry/expiry and 1/3/5-minute response sensitivity.

For delayed shadow revalidation, assume notification delivery **explicitly as a synthetic scenario**, then at each modeled human response clock consume a subsequently **actually received** qualifying quote/observation. If none exists, output \`NO_VALID_QUOTE/UNKNOWN\` rather than reusing a stale setup quote. Simulated acknowledgement and quote-cross modeled fills are NOT user actions or observed executions. Maintain user-reported position protection on known admissible data and RISK/WATCH when ACTION is blocked; never assert a stop executed, position was closed or an exchange order exists.

Separate terminal assertions:
1. \`SOURCE_QUALIFIED\`: proven per-field public source identity, native clock authority, coverage, freshness, units, rate and recovery within the approved pilot.
2. \`SHADOW_ADVISORY_QUALIFIED\`: deterministic no-external-send L23 pipeline operating on actually observed inputs, correct gating/funnel/replay parity and honest latency/missingness. May be limited to WATCH and risk; zero eligible trades is permissible.
3. \`ECONOMICALLY_VALIDATED\`: **NOT REACHABLE IN L4**. No alpha, full-net PnL, observed fill or trade-execution claim.

## Acceptance, artifacts and one clean terminal

Run synthetic A tests plus scoped L23/Bridge/Platform/legacy regression and genuine fabricated-process restart tests, exact counts/hashes. Keep **three original known-red legacy tests separately visible**, preserve replacement passes; no skip/xfail/weakening. B/C require their additional grant and can report source-qualified slices while other features remain blocked. No network is necessary to finish the authorized A scope.

Deliver only one coherent set:
- \`L4_CHECKPOINT.md\`, \`L4_FINAL_DELIVERY.md\`, \`L4_SOURCE_GRANT_AND_ENDPOINT_MATRIX.json\`, \`L4_SOURCE_HEALTH.json\`, \`L4_ACCEPTANCE.json\`, \`L4_TEST_MATRIX.json\`, \`L4_PRESERVATION.json\`.
- Exact code/source diff/hash, official-doc verification refs and dates, endpoint-specific budget model, receipt/clock uncertainty schema, storage/retention contract, replay-integrity evidence, local demo CLI/JSON/HTML and reproducible fault tests.
- Final states \`OFFLINE_READY_PENDING_AUTH\`, \`SOURCE_QUALIFIED\`, \`SHADOW_ADVISORY_QUALIFIED\`, \`SOURCE_CLOCK_BLOCKED\`, \`PARTIAL\`, \`BLOCKED\`; list each feed's actual status. None implies live deployment/economic validation.
- Chinese Owner milestone summary, English engineering receipts. No automatic successor/reviewer chain.

**Never infer** that source approval authorizes original R/M/Q integration, push/commit, deployed services, collector changes, external/push alerts, credentials, accounts, orders, money movements, protected 2024–25 or FINAL_HOLDOUT, existing forward market payloads, economics or PRIMARY registration. If grant absent or timing expired: no request, no wait, no background task. Stop safely and preserve original state.
