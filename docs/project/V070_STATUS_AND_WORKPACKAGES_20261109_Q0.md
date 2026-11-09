# Quant v0.7.0 — Current State and Pending Work Package Ledger (2026-11-09)

**Status basis:** latest local Controller/worker receipts read on 2026-11-09; all status changes after this snapshot must be independently rechecked. Start at [Handoff Home](V070_HANDOFF_HOME_20261109.md). This is a dated planning/evidence summary, NOT a substitute for sealed local receipts or a code integration decision.

## Product objective

Read-only, bounded scheduled multi-symbol crypto opportunity monitoring, primarily 2–12h trades, optional explicitly planned overnight up to 24h. Signals: 4H market regime, 1H setup, completed 15m entry trigger, fresh quote/5m check. Alert using Feishu only after strict state and channel eligibility; Owner handles execution manually in about 5–10 minutes. No account access or auto trading.

## Engineering evidence by phase

| Program | Accepted/verified facts | Remaining gap |
| --- | --- | --- |
| A–C / D–L | Deterministic offline S1/Shadow/HTML, infrastructure and source/clock adapters built and separately scoped accepted; C scientific status INSUFFICIENT_SUPPORT. Historical receipts retained | Not evidence of real Alpha, stable live product or real Source admission |
| N | 22 actual public Binance REST GET responses HTTP 200, 28 request weight, 240 1D + 300 4H distinct completed candles from 3 symbols | Clock discontinuities -799/+918ms triggered safe stop before Source admission. Raw deleted under exact-scope Owner decision |
| O | O operational clock work accepted offline; 672 regression cases | Windows/WSL clock not qualified; O exploratory time contract not strict evidence |
| P2 | Time-sync service stop attempted, 3.29s guard failure, restored active/enabled; scoped Controller receipt available | Original host remains unqualified; no repeat under consumed authorization |
| S | Windows native capture/NTFS→WSL finite offline pipeline; 26 Windows + 11 WSL tests and fresh 672 O; 1195 samples over 120.025s without observed Windows wall jump | 0-C decision at 2026-11-09T08:03:41Z: ACCEPT_S_WINDOWS_OFFLINE_HISTORICAL_AUDIT_ONLY_REAL_CURRENT_SOURCE_BLOCKED. S had 0 actual exchange GET, 14 simulated TLS |
| Q0B | Worker handed off isolated versioned S1_INTRADAY_MTF_V2, synthetic 4H+1H+15m/5m gates, card schema, 1H-only control and deterministic request planning | 100 claimed tests; Controller 0-C acceptance pending; no integrated real Source or forward data |
| Q0C | Worker handed off offline SQLite outbox and mock Feishu adapter, idempotency, expiry, UNKNOWN_DELIVERY, 5–10m response model | Controller 0-C acceptance pending; no real webhook, real transport, source or channel authorization |

Program S original local acceptance:
controller-decisions/V070_CONTROLLER_S_OFFLINE_SCOPED_ACCEPTANCE_20261109.json.
Q0B original handoff:
lt-q0b-intraday-mtf-v2-01/Q0B_HANDOFF.md.
Q0C original handoff:
lt-q0c-feishu-outbox-offline-01/Q0C_HANDOFF.md.

This export's local code roots are worktrees and artifact directories, not unified committed Git history. Their public snapshot names and per-file SHA manifest are linked from the [Handoff Home](V070_HANDOFF_HOME_20261109.md). A worker's synthetic test result must not be relabeled independent Controller acceptance.

## Specific Q0B and Q0C contracts to adjudicate before integration

**Q0B**: Worker designed 1H WATCH independent of 15m; candidate may become ENTRY_READY only from a *newly completed* 15m confirmation plus source/quote/stop/target/actionability checks. Fixed candidate entry/stop/targets at 1H setup, 45min setup expiry, 15m confirmation consumed, 5–10min human response reserve. 1D disagreement warns and downweights the hypothetical risk budget instead of veto; 4H opposite direction blocks READY. One-hour-only matched control is a prospectively testable counterfactual, not proven profitability. Q0B uses synthetic 2030-era sample times, no real market source or authorization. It chose 3/10/50 planning assumptions not measured official live endpoint weights. No production connection.

**Q0C**: Worker implemented mock-only notifications (no socket/send implementation), durable outbox states QUEUED/ATTEMPTED/PROVIDER_ACCEPTED/FAILED/UNKNOWN_DELIVERY, deterministic dedup, provider ACCEPTED != human read, and explicit no-retry for uncertain delivery. Synthetic/provider latency statistics cannot establish live SLO. Proposed Feishu sign behavior lacks real official/provider integration testing. The exact adapter from Q0B card to Q0C event schema and reliable revalidation must be independently designed, not merely copied from example JSON.

## Binding blockers to first genuine card/alert

1. **Trusted operational Source**: S independent consumer current/retention anchor, external trusted bundle/provenance, NTFS no-follow and producer race proof, 120s whole-process termination including blocking disk, actual legal/right/access review, exact new Owner-authorized finite session; do not extend spent N approval.
2. **Application integration**: Independent Q0B and Q0C Controller acceptance, semantically correct source→bar→MTF→plan→outbox adapter, 1H/15m warmup and no-future proofs, exact JSON schema and version migrations.
3. **Feishu live channel**: Owner-confirmed recipient/destination, protected webhook/signature secret, official provider behavior tests, independently approved message types/volume/window and no duplicate/unknown send resolution. MOCK accepted messages do not count.
4. **Universe/rate budget**: Current Program O public REST envelope allows 3 symbols and 24 GET / 40 weight per finite session; Q0B's 10–50 symbol plans are offline assumptions and are not permission to increase external use. Versioned endpoint/filter/cache/cost and rate budget required for broader production scope.
5. **Operations**: Finite sessions first; only after evidence review allow recurring scheduled monitor. Fail closed on global time/custody faults, isolate per-symbol bad data and suppress stale or nonactionable ENTRY_READY.
6. **Research**: No confirmed after-cost edge. Original Program C first-passage refuses qualified-native progression absent external Controller roots; DeepSeek review raises connected week-cluster collapse and conservative power. Preserve C V1; study V2 independently.

## Explicit outcome semantics

- **Operational MVP**: authenticated/authorized real data consumed by qualified bounded runtime, at least real NO_SETUP or truthful plan, reliable state and dashboard, and approved Feishu provider acceptance test. Success does not imply actual fills, returns or economic edge.
- **Shadow-ready MVP**: real prospective, immutable episodes/observations, missing/no-fill/ambiguous data preserved and actionability measured.
- **Scientifically confirmed strategy**: separate future independent after-cost support and power/uncertainty gates. Neither false-positive alerts nor lookahead are acceptable shortcuts.

## Next 0-C decision

Resolve pending Q0B/Q0C acceptance first, then dispatch a bounded integration compatibility check and targeted S technical closure, subject to active locks and current status. Keep source rights and actual external channel delivery gated. See [roadmap](V070_MULTISYMBOL_MTF_FEISHU_ROADMAP_20261109.md) and [0-C new-chat prompt](../../prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C_20261109_Q0.md).
