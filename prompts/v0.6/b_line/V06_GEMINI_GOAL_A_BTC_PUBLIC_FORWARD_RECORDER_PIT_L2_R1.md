# Gemini Goal A — BTCUSDT Public Forward Recorder: Event-Time PIT / L2 / Signed Receipts R1

You are Gemini engineering executor A under ChatGPT-0 B-line Controller. Full GOAL task: implement, independently exercise and push a high-reliability **public-only, account-free, order-free** BTCUSDT Binance USDⓈ-M futures forward market recorder that makes previously impossible causal source/known-at questions measurable. Do not stop at an architectural essay. Source/region unavailability is a valid explicit BLOCKED state, not permission to invent events or use private user files.

TASK_ID: `V06_GEMINI_GOAL_A_PUBLIC_FORWARD_RECORDER_R1`
CONTROLLER_DISPATCH_SHA: `e35724f1d1ee7458709e003dfc5673c826c68ffd`
AUTHORITY: https://github.com/EXASHXE/btc-quant-agent-public/blob/e35724f1d1ee7458709e003dfc5673c826c68ffd/reviews/v0.6/b_line/V06_FORWARD_SHADOW_G1G3_THREE_GEMINI_GOALS_R1_CONTROLLER_AUTHORITY.md
REPO: `EXASHXE/btc-quant-agent-public`
BRANCH: `feature/v06-bline-gemini-forward-public-feed-r1`
EXACT_START_SHA: `55ac4c631c69f6edbd275462ad23e4486b9782ed`
WORKTREE: `/root/workspace/project/quant-v0.6/gemini-forward-public-feed-r1`
SCRATCH: `/tmp/btc-forward_public_feed_r1`
WRITE_SCOPE: `scripts/market_data/forward_public_feed_r1/**`; `tests/test_v06_forward_public_feed_r1_*.py`; `docs/market_data/forward_public_feed_r1/**`; `evidence/v0.6/b_line/forward_public_feed_r1/**`.
This branch MUST remain independent of the Gemini shadow research and G1/G3 offline port worktrees. Never modify production `src/**`, CI, original S F3, H39/40/41, or old P1.

## Final Goal

Build a read-only system for current and FUTURE PUBLIC BTCUSDT-USDT-M events, creating sealed MarketEventV1 event receipts and honest quality witnesses. Needed data dimensions: Last 1m OHLC with final-close status, Mark price stream, aggTrade timestamps and aggressor side where provider defines, differential depth updates with REST **PUBLIC-only** snapshot bridge and known-as-of top bid/ask/depth, and separately only **official completed settled** funding readings. A funding projection from mark-price is not settled funding. No API keys.

Runtime modes:
- `fixture`: hermetic deterministic fake exchange frames, no Internet or credentials.
- `replay`: read saved immutable public raw segments with original *observed arrival times*, not backdated historical Binance snapshots, verify hashes and continuous depth.
- `live-public`: explicit opt-in CLI flag **public market-data only**; after offline tests pass, connect only to allowlisted official Binance USDⓈ-M public exchange HTTP(S)/WS read endpoints. This is an observational recording operation, NOT Binance account access nor LIVE trading. No POST/PUT/DELETE, no signed/authenticated APIs, no listenKey, no userData Stream, no order/cancel paths, no private accounts.

PUBLIC-only network gate MUST be explicit. Do not let default CLI or import instantiate live network connection. Confirm official USDⓈ-M endpoints and stream IDs against current official docs before code writes. Do NOT accidentally use COIN-M `dapi` or spot `api/v3` orderbook. Respect exchange 24h WS session rollover, ping/pong, data rates and subscription constraints as in current official docs. If public endpoint unreachable/geoblocked, live smoke = `NOT_TESTED_SOURCE_UNREACHABLE`; do not use a proxy around geographic restriction or change base provider silently.

## MarketEventV1 contract exact

Follow shared Controller authority literally, including:
`schema_version=market-event-v1`, product `BINANCE_USDT_M_PERP`, `symbol=BTCUSDT`, `channel`, `provider_event_ms`, `provider_transaction_ms`, `observed_wall_utc_ms`, `observed_monotonic_ns`, `available_at_ms`, `source_stream_id`, `connection_epoch`, `source_sequence`, `payload_sha256`, `payload`, `quality`, `reason_codes`, `raw_source_manifest_sha256`. Optional `book` is BookIntegrityV1 with exactly mandated fields and semantics. JSON/UTF8 and decimals preserve integer ms and raw decimal strings. Receiver wall/monotonic timestamps captured **immediately upon network receive**, pre-parse. `available_at_ms >= observed_wall_utc_ms`, never `=bar_close_ms` merely because a candle theoretically closed then. Protect against system clock rollback by flagging `CLOCK_UNCERTAIN`, not backdating feature timing. `observed_monotonic_ns` order only within recorded process epoch; persisted after restart must have new monotonic epoch, no false cross-restart ordering.

Bar x flag: finalized Binance futures 1m kline `x=true`, bar_close, receiver arrival. Reopened candle correction handled as provider revision *with new recorded observation*, no silent overwrite. Funding event only official already settled; latest estimated rate and settlement pending = separate `estimated` annotation and not cash.

## Required implemented software

1. **Schemas and ingestion mapping**: strict provider payload shape validation, public symbol allowlist BTCUSDT only, bounded fields, no private identifiers; MarketEventV1 canonical serialization and SHA. Fields unknown/bad → reject/quarantine with reason, do not fill missing values. Save raw and normalized event separately.
2. **Depth correct bootstrap**: buffer diff depth events; read authenticated *public* REST snapshot with `lastUpdateId`; only start book after official USDⓈ-M bridge rules including U/u/pu if present; skip stale updates, fail closed on discontinuity, duplicates, reversed IDs, crossed/zero/negative prices, depth-level mutation contradictions; rebootstrap after gap. Persist continuity and epoch. If only partial book/timed snapshot available, label `DEGRADED` and never label L2 fills provable.
3. **Time authority**: wall+monotonic observer clocks, optional exchange clock offset *diagnostic*, sequence ordering by arrival vs event/transaction, late corrections, drift and reconnect. No unobserved moment receives known-at credit. Cross-channel Mark/Last join permissible only when both `VERIFIED` and observed at/before decision. Local temporal latency histograms P50/P90/P99 and monotonic violations, ingress queue drop counts.
4. **Durability**: append-only raw segment log+hash-chain (or Merkle receipts) and atomic segment-manifest roll, torn-write quarantine, crash-restart idempotence, open file handle lifecycle, disk-pressure bounded buffers, explicit gap markers, resync id after restart. Require deterministic bytes for fixture replay; segment manifest includes feed+SHA+clock uncertainty. Do not commit megabytes of raw live market data to GitHub; put only tiny sanitized deterministic fixtures, checksums and summarized machine receipts.
5. **Health**: last meaningful event by channel, exchange access denial, stale Mark/Last, book invalid, duplicate, out-of-order, local consumer drop, gap rates, last settled funding unknown; health gate `SOURCE_READY` iff all required features known-at and coherent, else `SOURCE_DEGRADED`/`SOURCE_UNAVAILABLE`. A source gap cannot be patched with imaginary forward fills.
6. **Replay/CLI**: single-process Linux Python3.12, deterministic fixture generator, example launch and restart, `--network disabled` default, offline `pytest`, read-only live smoke optional bounded duration and no daemon left running without explicit opt-in. Minimal dependencies pinned where necessary and no covert egress.

## Verification matrix

At least **100 meaningful automated tests** across unit/integration/property areas: timed gap bridging (U/u/pu variants), snapshot race/stale snapshot, invalid bid > ask and zero size deletion, 1k reconnect epochs, duplicates, sender/resolver refusal, Mark/Last desynchronization, final vs developing bar, late funding, estimated versus settled, ingress wall rollback and monotonic relative order, out-of-order pub/sub, network default forbidden, no private keys and order method AST/network allowlist, schema regression and clock future mutation, rate-limit/backoff, corrupt raw segment/checkpoint, process death around fsync/manifest swap, stale book 5m period, ping/disconnection, consumer head-of-line drop, case-sensitive symbol confusion and binance coin-M URL block. Add test fixture emulating high-velocity 15m synthetic data with controlled known expected P99/health.
- CLI 15-minute bounded PUBLIC smoke permitted only if live-public option explicitly selected; if official public endpoints disallow, report accurately and rely on hermetic tests. Never claim any 24h real recorder until it actually ran; don't leave unattended eternal recorder process.
- Independent cash account tests NOT required. A is strictly data source, not strategy execution.
- Strict serializer/hash determinism and original arrival watermark across replay must be machine asserted.

## Work protocol

C1 read-only source contract+list exact official documentation URLs, implement schemas + first runnable fixture with deterministic test; push.
C2 implement depth/PIT durable recorder and comprehensive synthetic unit suite, push.
C3 implement optional allowlisted public live connector and isolated offline replay/health, exercise synthetic suites plus bounded public smoke if accessible, push.
C4 only if needed final regression and machine evidence report, push. Max 4 coherent commits; engineering fixes allowed before final but disclose live code hash and actual test mode.
Report: full command lines, Python deps, coverage, all negative test classes, raw→normalized SHA, depth continuity witness, tested wall-clock source quality and public endpoint access, gap counters, CI actual steps, no private data reads and no trading ports. Terminal `PUBLIC_FORWARD_RECORDER_OFFLINE_VERIFIED`, `PUBLIC_FORWARD_RECORDER_PUBLIC_SMOKE_VERIFIED` or `PUBLIC_FORWARD_RECORDER_FAIL_CLOSED`. All are **engineering evidence grades**, not trading/source authority until Controller L2. Task must be genuinely runnable, not pseudocode.

No access/list/stat to protected `/root/workspace/project/Quant-agent/data` or `Quant-agent-sanitized`, H39/H40/H41/Forward, historical 2024–26, user funds or accounts. NEW public data observed after dispatch is allowed; NO retrospective backfill of 2026 or protected 2024–25. No autonomous unattended network operations after Goal session, no migrations into `Quant-agent-sanitized`, no merges and no real trade/TESTNET/LIVE order calls.
