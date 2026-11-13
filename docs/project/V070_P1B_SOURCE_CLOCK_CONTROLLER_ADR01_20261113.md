# Quant v0.7.0 — P1-B Source/Clock Architecture Decision ADR-01 (Controller 0-C, 2026-11-13)

**Status:** `DESIGN_APPROVED_FOR_ISOLATED_L0_IMPLEMENTATION`. **NOT a real Binance Source grant**; `SOURCE_BLOCKED=true` and all live/economic/trading gates remain false. Owner has not authorized a standing L1 operation.

**Purpose:** Replace the “wait for Astra/Sol quota” dependency with an explicit Controller-approved design that Gemini 4 Hydrogen can implement incrementally in disposable **offline** workspaces. Controller performs adversarial source, transaction, clock and security review between work packages. High-risk changes do not become accepted just because Hydrogen’s tests pass.

## Grounded baseline

- Q0A5 G0–G4 synthetic offline `ACCEPT_Q0A5_FULL_L0_OFFLINE_SCOPED` (local `controller-decisions/V070_Q0A5_FULL_L0_CONTROLLER_CLOSURE_20261113.json`).
- P1-A `win_clock.py` localized `w32tm` raw-byte diagnostics `ACCEPT_P1A_DECODE_ONLY_OFFLINE_SCOPED`, patched SHA-256 `323aca8fb05ee51f4f92785d4fb1f16ed52d7bd1bfa2af82b51e78727efead00`. Controller reran WSL 70 PASS / 1 platform-only SKIP, inspected Windows author 71/71 PASS. No strict UTC qualification.
- Host w32tm: unsynchronized Leap=3, Stratum=0, Local CMOS Clock. QPC and UnbiasedInterruptTimePrecise short-window consistency **does not establish UTC**.
- `WindowsHttpsTransport(qa=None)` currently always returns `SOURCE_BLOCKED`, even if access arguments are provided; `public_bridge.py` is explicitly disabled and `SourceLedger` is synthetic-only. `transport.py` lacks bookTicker. `access.py` lacks bookTicker and 15m/5m live admission. `request_plan.py` and Q0B source reject 2026 present because of protected historical windows.
- Existing 3-symbol L0 plans: one pass = 21 requests / 24 weight; two stage = 23 requests / 26 weight. Cap 24 requests / 40 weight per run. Draft stage2 refresh = 28 >24 and MUST remain disabled.
- Official Binance USDⓈ-M 2026 docs: `/fapi/v1/time` weight 1; single-symbol `/fapi/v1/ticker/bookTicker` weight 2; `/fapi/v1/klines` current LIMIT weights `[1,100)->1; [100,500)->2; [500,1000]->5; >1000->10`. Current code `kline_weight_for_limit` incorrectly returns 1 at limit=100 and 2 at limit=500 under `LEGACY_PROFILE_ID`. This does **not** change 32-bar E1 costs, but is an independently reproduced **P1C-WEIGHT-BOUNDARY-F01** fix-before-live candidate. Official documentation: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data .
- Quote TTL clarification: `q0bc_v2/producer.py` already rejects `now - q.exchange_ms > 30_000` as `STALE_VENUE_QUOTE`; its `now - snapshot.clock.exchange_lower_ms > 60_000` is **a different source/clock-bracket age check**, NOT a competing 60-second quote TTL. Preserve both until independently demonstrated false equivalence. Do not schedule a blanket “30 vs 60 TTL alignment” patch.

## Decision D1 — Three explicit operating modes, strict default

- `SYNTHETIC_L0_2030`: existing frozen implementation, no real HTTP and no Feishu. Preserve unchanged.
- `PUBLIC_DIAGNOSTIC_L1_RAW_ONLY`: future explicitly Owner-authorized finite public read-only request sequence. May preserve raw, bounded responses and diagnostic time/rights status even when `strict_utc_qualified=false`; **no trusted E1 admission, no EXECUTABLE/ENTRY_READY, no Feishu or live notifications**. This is NOT implemented or authorized by this ADR.
- `PUBLIC_QUALIFIED_L1_CURRENT`: a separate future approval after clock and legal/region/retention/provenance proofs. Only then may authentic frames enter a *new versioned* non-synthetic Source adapter. It cannot reuse `SYNTHETIC_STRICT_FIXTURE` provenance, synthetic 2030 date policy or QA bypasses.

Both L1 modes start disabled, require a concrete bounded Controller+Owner envelope bound to exact approved version and endpoints, and have a duration/request ceiling. Never create a grant from a supplied bundle SHA, env toggle or self-generated certificate. If denied, no network. No ungranted “warmup” HTTP or time probes.

## Decision D2 — Time and causality

- Authoritative elapsed-time lineage: Windows native QPC + UnbiasedInterruptTimePrecise + boot identity. WSL wall/monotonic clock **must not** be promoted to the real capture authority on the currently unqualified host.
- Absolute UTC: `W32Time status` is observational only; Leap=3 or free-running Local CMOS blocks qualified mode. `/fapi/v1/time` is a venue clock sample, **not an independent UTC certificate**. A separately established and authenticated UTC interval is needed; source provenance/uncertainty must be auditable. No local-host time setting.
- Bounded trusted time: use integer millisecond `utc_lower_ms`, `utc_upper_ms`; target width <=1000ms for the separately verified independent anchor and source bracket <=2000ms as existing E1 upper bound. These are validation ceilings, **not statements that current equipment meets them**. Unavailable/wide/expired/source-changed anchor -> `CLOCK_UNTRUSTED` / `SOURCE_BLOCKED`.
- On wall step >50ms (new regression threshold proposal for cycle quarantine), boot/session change, negative QPC progress, QPC-vs-unbiased mismatch, or unknown absolute UTC, invalidate the current cycle and **do not auto-reactivate**; recovery requires a fresh approved anchor plus new generation/epoch. The existing `q0a_gate.check_anchor()` smaller 5ms pairwise wall-consistency check is not relaxed.
- Completed bars: Binance REST Kline `closeTime=end_exclusive_ms-1`; for interval I, demand `openTime % I = 0`, `closeTime+1 = openTime+I`, nonoverlapping contiguous sequence, all finite OHLCV, `end_exclusive_ms <= trusted_utc_lower_ms` (and applicable 2s grace), never infer closure from merely receiving HTTP 200. If partially formed last bar exists, drop it only when enough historical closed bars remain; otherwise fail closed, not fake coverage.
- Market actionability gates: quote age <=30s, snapshot age <=1s at emission, source reference-bracket age <=60s as a separate distinct check, and completed 1H/15m/5m evidence. For human 5–10m later, request a *new qualified quote and current source*; a previous card is not executable forever. If qualified time is absent, record `WATCH` or `INVALID` with explicit SOURCE reason, never `EXECUTABLE`.

## Decision D3 — Protected windows and data classes

Do not weaken or delete `PROTECTED_2024_2026`, `FINAL_HOLDOUT_2026=[2026-02-01,2026-08-01)`, or the 2030 synthetic-mode predicates. Implement a separate versioned **rolling live-only window validator** which:
- requires a provable present-time UTC interval, prescribed lookback (only what the current L1 envelope needs), local explicit endpoint/quantity and symbol bounds, and `requested_start_ms >= 2026-08-01T00:00:00Z` for this scoped first canary;
- rejects overlaps of both protected holdout and any other protected Project interval. A new live mode is not a backdoor into historical data or holdout;
- cannot be used by archived `SourceLedger`, research/backtesting, or synthetic tests without explicit mode ownership. Disable data mixing and synthetic-to-real provenance relabeling.

Note: today's 2026-Nov 32-bar 1D lookback does not intersect the [2026-02-01,2026-08-01) final holdout, but this **does not automatically authorize** either historical or present public Source.

## Decision D4 — Request, quote and optional OI budget

- First 3-symbol canary: preserve <=24 real GETs, <=40 local planned weight, <=120s per run, bounded bytes, retries=0, exact symbols BTCUSDT/ETHUSDT/SOLUSDT, one venue `fapi.binance.com`. Explicitly exclude private endpoints, API keys, orders, all-symbol ticker and additional transport hosts.
- Source `bookTicker` must be exactly one symbol and carry a valid `time` integer; 30s age evaluated against **trusted** UTC not unsynchronized host local wall clock.
- Fix `kline_weight_for_limit(100)` and `(500)` only in an **isolated versioned proposal** with fail-first boundary tests, preserving old 32-bar L0 proofs. No quiet global historic-contract mutation.
- Disable R1.2 five-request refresh (23+5=28 >24); no unreviewed cap increases. OI, depth, funding and premiumIndex are outside initial request profile and cannot be silently added. If V3.8 requires OI/depth for EXECUTABLE, missing proof remains WATCH/INVALID rather than inventing data.
- Recompute budget from a versioned official weight table and local ceilings before each future run; never trust only Binance `X-MBX-USED-WEIGHT-1M` for bookTicker, whose official docs warn it is inaccurate.

## Decision D5 — Durable Source state and retention

Implement separate L1-only `source_state` SQLite on a verified fixed NTFS volume; one transaction must bind `capture_session_id`, `boot_session_id`, `source_generation`, `source_epoch`, monotonic sequence, cycle identity, last confirmed five-TF bar digests, raw response checksums, package ledger and atomic manifest commits. On restart:
- revalidate the exact persistent generation/epoch and the complete raw->HTTP response ledger->manifest->normalized frame binding (reuse Q0A4 FIX03 verification without mutating it);
- reject torn / altered / incomplete bundles, old boot identity, replay contradicting bar hashes, and ambiguous once-consumed grants; never silently reset sequence or repair history;
- one canonical Q0BC Outbox remains Producer-owned; Source persistence and deletion must not write Outbox tables.

Raw L1 data retention: 24-hour maximum only if current rights allow it; create/expiry anchored to trustworthy UTC intervals, and purge only under the isolated L1 capture root, against a recorded manifest path allowlist. No symlink/junction/reparse escape. Do not delete accepted offline evidence or protected research. Purge should be atomic/fail-closed where possible; record which bytes/files were removed with predelete checksum and a non-secret receipt if retention terms permit retaining receipts. If ACL prevents secure purge, block and report, never change host ACL/privilege silently.

## Decision D6 — Safety and rollout stages

For the no-Codex period:
1. **P1C-01 (Hydrogen, L0-S/L0-M):** pure versioned `clock_policy`, `live_window_policy` and `request_weight_policy` using static synthetic fixtures and explicit Controller contracts; no real networking, no mutations of accepted baseline. Fail-first negative tests: clock stale, local CMOS, >50ms step, boot reset, exact boundary 100/500, 28>24, protected holdout, bookTicker missing time, 15m/5m forming tail. Controller accepts this package before next.
2. **P1C-02 (Hydrogen, bounded temporary L0-M exception):** dedicated SourceLedger SQLite and restart/crash/replay diagnostics, tested solely via synthetic bundles on local NTFS. No raw historical purge or live network, no author signing. Controller independently reviews SQLite state/crash/holdout falsifiers before next.
3. **P1C-03 (Hydrogen, bounded temporary L0-M exception):** detached diagnostic raw store, isolated bounded retention index and purge simulation with disposable test fixtures ONLY. Forbid touching existing archival/preserved evidence, no privileged ACL bypass. Controller verifies retention and rollback before next.
4. **P1C-04 (Controller-approved only after 01–03):** mock loopback HTTPS public data pipeline integration with a grant stub that is NON-AUTHORIZING and unforgeable as a real grant; `qa=None` remains hard blocked and `Q0APublicToE1Bridge.LIVE_ENABLED` stays False. Genuine live-access code must remain unimplemented or behind unbreakable disabled branch pending new Controller review + one Owner L1 envelope. High-impact changes to the frozen Source trust, Q0BC contracts or authority must STOP and be routed back to Controller.

**No Hydrogen architecture improvisation:** design ADR overrides an executor's speculation but never overrides frozen contracts or actual source receipts. The Controller can personally implement/review sensitive seams with the same bounded evidence process. No self-promotion to Astra/Sol authority.

## Exit gates

- P1C prep offline accepted only after fail-first & replay/restart/corruption tests in Linux and native Win NTFS, no unexpected skips; original Q0A5/P1A hashes unchanged; no real HTTP/Feishu egress; authority flags remain false.
- Future L1 diagnostic canary requires a **separate** Owner grant for host, endpoints, KR egress and rights, finite duration/requests, exact retention and stop button. Diagnostic data must remain unqualified.
- Future L1 qualified canary additionally requires authentic independent UTC proof and full Controller Source trust acceptance, not a mere clean HTTP 200 or green unit suite.

## Explicit non-decisions

Not deciding to change Windows NTP settings, grant public API rights, enable `L1_PUBLIC_CANARY_LIVE`, substitute WSL clock, alter frozen R1.1/R1.2, replace Producer Outbox authority, make V3.8 signals executable, or claim Alpha. Those require their own reviewed scopes.

**Authority:** `SOURCE_BLOCKED=true; SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false; REAL_FEISHU_SEND=false`.
