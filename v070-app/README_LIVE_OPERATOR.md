# Quant public-market read-only advisory — J

The installed entrypoint is `quant live`. It reuses the accepted S1 compiler, market-side Shadow, local HTML renderer and frozen C evaluator admission checks. Holding horizon: 4–48 hours. S1 only; S2/S3 disabled. No private API, credentials, trading, account state, execution or notifications.

`J_PUBLIC_MARKET_ADVISORY_V1` is ordinary unsigned public REST data observed over verified HTTPS. It is neither SYNTHETIC nor STRICT_NATIVE_QUALIFIED. Strict Research code, 50ms sticky stop, Owner/auditor and independent UTC protocols are unchanged. No strict Source/Shadow/Economic qualification follows from J.

**Current delivery:** real access/usage eligibility, actual access region and sealed-date exclusion metadata have not been supplied. A real scan has not run. The adapter is implemented and offline tested; missing evidence returns LIVE_SOURCE_UNAVAILABLE before a socket or store is created. Local tests use J_LOCAL_HTTP_QA_V1 with fabricated TLS and an explicit fabricated wall-clock domain; never treat their cards as current markets or host-clock qualification.

## Install

From the J source/offline packet, with tested Linux x86_64 / CPython 3.13:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links release/wheelhouse --require-hashes -r release/requirements-lock.txt
.venv/bin/quant live doctor
.venv/bin/quant --mode STRICT_RESEARCH doctor
```

No new dependency was added. Use `tools/build_live.py` for post4; historical build_mvp/build_native tools remain frozen baseline utilities.

## Small operational access record

Copy `configs/j_public_access.example.json` into a dedicated ordinary operator directory. It deliberately says UNVERIFIED/UNKNOWN and cannot authorize a request. An independent applicability review must establish actual region/venue access and this personal read-only advisory/caching use, then provide references and SHA256 hashes for `eligibility.json`, `usage_and_cache.json` and `excluded_dates.json`. Store no private keys, API tokens or account credentials. J does not require a Strict Owner signature, capture auditor or 60-day prospective qualification ceremony.

`excluded_dates.json` contains only externally supplied exclusion metadata:

```json
{"metadata_complete": true, "excluded_UTC_ms_ranges": [[START_MS, END_MS_EXCLUSIVE]]}
```

The example is schematic, not valid data/authority. An empty list is acceptable only when the actual independent review establishes no excluded overlap. Never open FINAL_HOLDOUT to discover its contents or assume missing metadata means no excluded dates. Use the benign filename `excluded_dates.json`; protected-path guards reject names containing holdout and original l4/other program trees.

The operational scope is a new segregated rolling window: at most the latest 80 completed 1D, 100 completed 4H and 72 optional 1H candles per BTCUSDT/ETHUSDT/SOLUSDT. It never reads the PRIMARY corpus, protected historical worktrees or FINAL_HOLDOUT and never claims historical OOS validation. Requested date ranges are calculated from fresh exchange time and rejected before any kline request if they overlap exclusion metadata.

The only target is `https://fapi.binance.com`, GET `/fapi/v1/time`, `/fapi/v1/exchangeInfo`, `/fapi/v1/klines`. The adapter checks each symbol's PERPETUAL, quote/margin USDT, underlying asset and active status. No spot/COIN-M/mark/index/continuous-contract substitution. Current documentation: [official REST reference](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data). Public documentation alone does not establish the operator's applicable rights. [Vision archive terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md) were reviewed as distinct archive conditions, not automatically treated as a REST advisory license.

`proxy` defaults to null (direct verified HTTPS). Environment proxy variables are ignored. If a legitimate permitted HTTP CONNECT proxy is necessary, supply exactly host, port and permitted_reference. No credentials, redirect, direct fallback after proxy failure, geo-restriction workaround, or automatic retry is provided.

## Manual operation

Run only after the reviewed operational record and all underlying facts genuinely pass. Commands below are examples, not executed authority.

```bash
.venv/bin/quant live doctor --access operator/access.json
.venv/bin/quant live scan --access operator/access.json --output work/public --holding-hours 24
.venv/bin/quant live status --output work/public
.venv/bin/quant live opportunities --output work/public
.venv/bin/quant live episodes --output work/public
.venv/bin/quant live dashboard --output work/public
```

Open `work/public/dashboard/latest.html`; full proof is in latest.json and live.sqlite plus immutable raw response files. The page displays evidence class, UTC as-of bounds/completed candles, clock/freshness status, regime/structure/reasons, entry, stop, genuine preobservable targets only, planned gross and hypothetical after-cost R, explicit uncalibrated bps assumptions, expiry/invalidation, horizon and ACCOUNT_UNKNOWN/ACCOUNT_VETO. No payoff probability, fill or realized profit is inferred.

The unchanged S1 review window remains strict: default grace 120s (configurable 60–300s), source lower bound no later than 300s after the latest 4H close. Start a manual scan with margin, e.g. around 08:02:15 or 20:02:15 UTC, at most two review cycles per UTC day. There is no scheduler or waiting collector. Outside that window, warmup can be captured but S1 returns SOURCE_BLOCKED, not NO_SETUP. A fresh valid market can still produce NO_SETUP for every symbol.

Reference age defaults to 120s, configurable 30–300s using `--fresh-seconds`. A stale dashboard keeps its frozen original plans and clearly displays DATA_NOT_READY; it does not acquire a current quote automatically. Source times are uncertainty bounds from one venue's HTTPS time responses, width at most 5000ms, not strict independent UTC. REST event/publication time remains UNKNOWN. Local request/receive/durable wall and monotonic clocks remain distinct.

On a >50ms wall/monotonic discontinuity, boot/epoch problem or known WSL history, candidates remain held while the same finite session obtains another complete rolling snapshot using new connections and two fresh time probes. Candle identities/content must agree and the previously admitted prefix must have no corrections. Only then may CLOCK_DEGRADED_RECONCILED restore operational advisory; the warning and old failures remain. Repeated instability or contradictory timestamps stop the session. Strict sticky stops are not reset.

A subsequent manual real observation, when actually available:

```bash
.venv/bin/quant live observe --access operator/access.json --output work/public
.venv/bin/quant live episodes --output work/public
.venv/bin/quant live dashboard --output work/public
.venv/bin/quant live evaluate --output work/public --report-output work/evaluation_new
```

Observe reacquires fresh bounded market data, never manufactures later candles. Original levels/IDs stay frozen. The accepted first-passage method excludes the initial partial hour, retains missing intervals, no-entry/missed-entry/expiry/cancellation and same-bar ambiguity. Market entry or target touch is not an exchange fill. Multi-day prospective evidence requires actual later manual invocations; none are claimed by this delivery.

C's frozen protocol currently rejects J_PUBLIC_MARKET_ADVISORY_V1/J_LOCAL_HTTP_QA_V1 with SOURCE_CLASS_INVALID. `evaluate` preserves J_episode_export.json, executes that original validator, and records SCHEMA_BLOCKED_NEW_J_EVIDENCE_CLASS / INSUFFICIENT_SUPPORT. It does not relabel J as NATIVE_UNQUALIFIED or SYNTHETIC, change C, or execute an illegitimate economic ledger. `evaluator_status.md` is an admission report, not a C profitability report.

## Limits, recovery and reproduction

Each session admits at most 24 requests, weight 40, 120s, response size 2MiB and response storage 16MiB. Normal scan uses 12 requests; a clock reconciliation uses 23. Sequential HTTPS has one response in flight. Every attempted request is durably charged before connection. A separate finite request worker bounds DNS/socket lifetime and is killed/waited on timeout; no retry/reconnect loop exists. 3xx/403/418/429/451 stop without following or bypassing. Oversized response prefixes are explicitly incomplete and never admitted.

Raw bytes are fsynced before response receipts; completed normalized rows rederive from those bytes and their clock/reference lineage. SQLite uses the original FULL synchronous append-only hash chain. Sessions without successful terminal closure cannot admit a snapshot. `quant live recover --output work/public` marks interrupted sessions failed and regenerates local snapshots; it performs no market request. Conflicting revisions stop the Source and require an explicitly reviewed fresh store/version, never rewriting old plans.

Store budget is 64MiB with a 64MiB free-space floor. Actual permitted retention is set in access.json, maximum 30 days. Expired stores are blocked; the operator must perform rights-compliant authorized deletion/archive handling. No unattended cleanup, grant renewal or hidden collector is started.

```bash
.venv/bin/python -m pip install --no-index --find-links release/wheelhouse --require-hashes -r release/toolchain-lock.txt
.venv/bin/python -B tools/build_live.py
.venv/bin/python -B tools/verify_release.py
```

Full final regression runs use an ordinary temporary materialization so the unchanged H path guard and C cwd confinement both apply. The original verifier AST check runs separately against its real read-only source; selections are disjoint and historical/repeated runs are not added as unique tests. See J7_TEST_MATRIX.json for exact counts, commands, earlier failures and limitations. No source/economic or sustained native-performance qualification is claimed. Controller 0-C performs final acceptance.
