# v0.6 G2 R3 — Method and Official Mark-Archive Metadata Repair R1

**TASK_ID:** `V06_G2_R3_METHOD_MARK_SOURCE_REPAIR_R1`
**CONTROLLER_DISPATCH_SHA:** `52e41bbed246a4c0257834a8d56365beac7ee04e`
**Authority:** https://github.com/EXASHXE/btc-quant-agent-public/blob/52e41bbed246a4c0257834a8d56365beac7ee04e/evidence/v0.6/controller/B_LINE_G2_R3_METHOD_MARK_SOURCE_REPAIR_R1_DISPATCH.json
**Controller L2 audit:** https://github.com/EXASHXE/btc-quant-agent-public/blob/52e41bbed246a4c0257834a8d56365beac7ee04e/reviews/v0.6/b_line/V06_G2_R3_SOURCE_AUDIT_CONTROLLER_L2_REVIEW.md
**Repository:** `EXASHXE/btc-quant-agent-public`
**Exact code mainline:** `v0.6@e0ff8c3473de4bfa3e66fe7928d42992a4d38a32` (do not alter)
**Working branch:** `feature/v06-bline-g2-r3-cost-aware-method-design` at exact starting HEAD `e5b2006a89441f7eb2ec900e508aff451106b87a`
**Worktree:** `/root/workspace/project/quant-v0.6/g2-r3-cost-aware-method-design` — **REUSE the existing clean R3 design worktree**, not R1/R2 or source-audit worktrees, and do NOT create a duplicate directory.
**Read-only independent source-audit head:** `12793bc04db7414d11a0961684fd14f5df3ce16e`
**Official Binance public historical data script exact SHA:** `binance/binance-public-data@f446ce3812bd4e5521f21faecd4ae3c6460e49fc`.
**Executor:** Sol High preferable to finalize clock/economic method; Gemini may carry out mechanical HEAD/GET-CHECKSUM validation, but serially on same branch.

## Outcome: one bounded addendum, not yet a backtest

Current original R3 design has 8 proposed structurally different variants (STRUCTURAL_CONTINUATION/CLOSED_RETEST × LONG/SHORT × 4h/12h). **Do not modify its original frozen proposal files or candidate registry**. Add a new, explicitly versioned **METHOD_REPAIR_R1 addendum** linked by exact design SHA; this is a proposal for later Controller preregistration, not a retroactive R3 outcome or permission to inspect prices.

The [G2 R3 source-cost audit report](https://github.com/EXASHXE/btc-quant-agent-public/blob/12793bc04db7414d11a0961684fd14f5df3ce16e/docs/strategy_research/g2_r3/source_audit/SOURCE_SEMANTICS_AND_COST_FEASIBILITY.md) correctly ended `G2_R3_METHOD_REPAIR_REQUIRED_BEFORE_PREREG` with 11 metadata requests, issuer fee/funding docs HTTP202/empty responses and no market bodies. Its finding that mark archive path could not be established has now been **narrowed but NOT fully closed** through Controller independent inspection of official code:
- [Official Python README](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/python/README.md) explicitly documents USD-M historical `markPriceKlines`, explicit symbols and interval `1m`.
- [Official downloader](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/python/download-futures-markPriceKlines.py) constructs monthly `SYMBOL-1m-YYYY-MM.zip` and `.zip.CHECKSUM`.
- [Official path assembly](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/python/utility.py) plus [base URL](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/python/enums.py) specify `https://data.binance.vision/data/futures/um/monthly/markPriceKlines/<SYMBOL>/1m/<SYMBOL>-1m-<YYYY>-<MM>.zip`. **This is a source-path claim only; no January–April 2026 object or data continuity has yet been verified.**

### Hard access firewall

- **NO** price OHLCV/mark-price ZIP body/CSV/row download or decoding, signal or trade outcomes, funding-rate history, new R2 data/cache, protected RC2 symbols, A-line/H40/H41 protected outcomes, TESTNET, private account endpoints, fees via account credentials, any signed Binance calls, actual orders, market scans, trading advice or unapproved strategy implementation.
- Historical mark source HEAD may access only 3 allowlisted symbols (`BTCUSDT,ETHUSDT,SOLUSDT`) × 4 named months (`2026-01..04`) × 1m `um` `markPriceKlines`, using exact paths above from official source. **HEAD only** on up to 12 ZIPs, optionally **GET only the matching .zip.CHECKSUM small text** if existence/permission and legal audit allow, ≤4KB each; NO range GET on ZIP, NO ZIP downloads, no XML bucket listings or all-symbol discovery, no brute-force directory guessing. Total MAX **40 HTTP operations and 1MB actual downloaded allowed metadata**; include final host/redirect chain (stop if unexpected domain), response status/Last-Modified/ETag/Content-Length, content hash only when an allowed checksum text body is actually present, UTC, and count all redirects in network request budget. Do not treat a HEAD object presence as complete monthly candle coverage. If HEAD gives 403/405, report `HEAD_METADATA_UNVERIFIED`, do not bypass by reading price bytes.
- Public official static docs only for source terms; no account or provider environment inspection. The current official dataset terms appear to restrict use to noncommercial research/require attribution for redistribution. Review current terms/dated applicability and produce a **licensing status** (NONCOMMERCIAL_RESEARCH_SUITABILITY_UNDER_REVIEW, PERMISSION_BLOCKED or LICENSE_VERIFIED_FOR_STATED_SCOPE); do not provide a legal guarantee. If current intended downstream use is live/commercial and permitted scope is not established, STOP data access and report, and keep any future raw-data redistribution prohibited. Only independent execution-authorized checks can later create data.
- Respect 429/403/legal/geo block and network timeout, stop after bounded retries; no proxy switching, credential discovery, ignoring ToS or requesting bigger API responses. The prior source audit's 2026-01..04 archive legal assessment remains CONDITIONAL.

### Stage 0: Git identity and worktree safety

Before any change verify:
```bash
WT=/root/workspace/project/quant-v0.6/g2-r3-cost-aware-method-design
git -C "$WT" rev-parse HEAD
git -C "$WT" branch --show-current
git -C "$WT" status --porcelain=v1 --untracked-files=all
git -C "$WT" worktree list --porcelain
```
Confirm source branch HEAD `e5b2006a89441f7eb2ec900e508aff451106b87a`, expected origin repository and exact Controller `CONTROLLER_DISPATCH_SHA=52e41bbed246a4c0257834a8d56365beac7ee04e`, and initial clean target. Git metadata only across sibling original/G1/G2 R1/G2 R2/G3/reviewer/source-audit worktrees, no touching their caches or user files. **STOP** `BLOCKED_WORKTREE_DRIFT` if target is dirty or actively occupied, or branch moved without new authority. NO checkout to alternative branch, no worktree add, reset/clean/stash/rebase/move/delete/force.

### Stage 1: method addendum scientific repairs (NO price access)

Create `docs/strategy_research/g2_r3/method_repair/METHOD_R1_1_PIT_COST_ACCOUNTING.md` with a **fully deterministic** clock/state schema. For every minute t, distinguish: (1) raw price and mark event timestamps, (2) the ex-post cashflow/equity reporting ledger, (3) data actually available to decision/risk at t+frozen lag, (4) pending order earliest next future feasible minute open, (5) exchange trade-tape intrabar stop/TP gap resolution, (6) funding ownership and unsettled adverse reserve, (7) minute MTM/risk and cooldown, and (8) first open for latched drawdown kill/reduction. Require independently testable ordering for same-bar funding/entry/exit collisions, stale mark, 10% max drawdown, 5% equity reserve, lot/tick rounding and zero/negative equity. Adverse ex-post mark value may never backdate a stop/new trade rejection. Maintain separate funded candidate/control ledgers and unfunded matched episodes; do not double charge spread/impact/cashflow. Specify USDT notional, bps, R, equity and margin units independently; no leverage >1x or liquidation-profit magic.

Create `docs/strategy_research/g2_r3/method_repair/R1_1_FUNDING_COST_AND_SUPPORT.md` with:
- exact current issuer source claim versus historical settlement/publication proof. A fixed base 4bp/event and higher-stress 8bp/event is a **scenario**, not an empirically measured funding cap. If interval/cap cannot be bounded, expose `FUNDING_EVENT_SCHEDULE_UNVERIFIED` and do NOT assert that any 12h strategy loses or was fairly screened merely because a 12-hour hourly proxy demands stop>=280bp over the frozen 250bp max. A structurally infeasible stress scenario becomes `STRESS_COST_GEOMETRY_INELIGIBLE` and `DIAGNOSTIC_ONLY` unless future method repair approved; no hidden relaxed 12h settings. Preserve candidate IDs and original stop/cost assumptions until a later explicit amended prereg and Controller approval.
- separately freeze before results the information classes `DEVELOPMENT_POSITIVE_SUPPORT`, `NEGATIVE_UNDERPOWERED_DIAGNOSTIC`, `SUPPORTED_DEVELOPMENT_ECONOMIC_NO_GO`, `SOURCE_OR_PERMISSION_BLOCKED`. Original ≥100 unique trades per fold for positive support remains proposal; no false requirement that 3 months must yield 100 for EVERY strategy to report negative diagnostics. For a meaningful negative decision require adequately powered **upper** adjusted confidence bound below an explicitly frozen economically meaningful net edge (the source audit proposes +5bp), not just point mean<0. Include no result-dependent window extension or per-asset rerank.
- fees: original 6bp taker+2bp half spread+3bp slippage **per leg** base; doubled stress; current/2026 applicable fee not proven, therefore known assumed 22/44bps round trip separate from future measured execution and tick/lot effective versions. Do not silently assume VIP. Account for funding cap shock and mark notional proxies, false maker fill optimism. Classification `PROXY_COST_DIAGNOSTIC_ONLY` if plausible fee/impact envelope remains unverified.

Create `docs/strategy_research/g2_r3/method_repair/R1_1_SOURCE_AND_LICENSE_ADMISSION.md` with an **allowlisted source matrix**: price trade K 1m, mark 1m, symbol filters, fee schedule, funding settlement/caps, public receipt lag, source licence/redistribution, spread/slippage uncertainty. Explicit known official mark-path lead, metadata HEAD observations versus unknown **actual continuous body completeness** (no early success). Call out resource bounds: 12 known mark symbol-month ZIPs potentially reduce the REST 1500-row pagination load, but ZIP existence still does not certify minutes; later 1GB/250 requests budget must be reviewed only if pipeline/source budget actually fits. Source paths and data licenses must not be silently reused for compensated signal services or live execution.

### Stage 2: narrow source HEAD metadata audit — no ZIP content

**Only after scope/terms preflight**, programmatically construct at most the following 12 paths:
```
https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2026-01.zip
# same exact pattern BTCUSDT/ETHUSDT/SOLUSDT × 2026-01,02,03,04
```
Use HEAD only, optional allowlisted small matching .CHECKSUM text with explicit max-bytes. Record matrix as FOUND_OBJECT_METADATA / NOT_FOUND / BLOCKED / UNKNOWN; note month coverage is **NOT_ASSESSED** for all. No 1m candle data ever. If any known path unavailable, report per-month missingness without substitution. Do not query future/exposed R2 outcomes, even by related derivative APIs.

### Stage 3: design-only evidence and next Controller handoff

Allowed append-only paths ONLY:
- `docs/strategy_research/g2_r3/method_repair/**`
- `evidence/v0.6/b_line/g2_r3_design/method_repair/**`

Required evidence:
1. `MARK_ARCHIVE_METADATA_HEAD_LEDGER.json` — exact URL, symbol/month, HEAD status, redirect, bytes actually read (zero for HEAD), checksum if explicitly permitted, uncertainties; files NOT downloaded.
2. `METHOD_REPAIR_R1_1_GATE_MATRIX.json` — all method/source/permission/funding/cost/mark availability and support rows with OPEN/CLOSED_FOR_DESIGN/BLOCKED/PROXY_ONLY, freeze-ready? yes/no, candidate count unchanged8, empirical evaluations0.
3. `METHOD_REPAIR_R1_1_RECEIPT.json` — original method SHA, audit SHA, Controller dispatch SHA, source official SHA, no new outcomes, request/byte budgets, local exact environment identity, seven sibling worktree HEAD/dirty-count preservation, diff whitelist and JSON syntax.
4. Short `R1_1_CONTROLLER_HANDOFF.md`: indicate whether **one** separate prospective frozen development diagnostic R3 could be responsibly authorized, what must still be verified after prereg (actual mark/trade continuity), exact blocked cases and data-rights scope. This is not alpha approval.

**Status (one):**
- `R3_METHOD_ADDENDUM_READY_FOR_CONTROLLER_SOURCE_METADATA_PARTIAL`
- `R3_METHOD_ADDENDUM_READY_FOR_CONTROLLER_MARK_METADATA_FOUND`
- `R3_METHOD_REPAIR_SOURCE_OR_PERMISSION_BLOCKED`
- `BLOCKED_WORKTREE_DRIFT`
- `BLOCKED_NOT_PUSHED`.

Rules: data API/price body reads=0; empirical backtests=0; historical candidate IDs and 8 proposed formula source files **unchanged**; nonprotected future price access/first prereg **NOT** authorized; code or tests under `src/**`, `scripts/**`, `tests/**`, `configs/**`, `.github/**`, original prior R3 design/audit evidence, G2 R2, H40/H41 and G1/G3 all forbidden edits. No real Binance/account/TESTNET/LIVE.

**MANDATORY proactive Git push**: stages only the two new addendum prefixes, runs `git diff --check` and JSON/file-scope checks, commits, pushes **to existing R3 design branch** `feature/v06-bline-g2-r3-cost-aware-method-design`, then independently fetches remote commit SHA, parent and changed paths. No push to `v0.6`; no branch reset/rebase/force. Return exact `CONTROLLER_DISPATCH_SHA=52e41bbed246a4c0257834a8d56365beac7ee04e`, terminal SHA, evidence paths and explicit no-data/no-funds claims. The original design SHA `e5b2006a89441f7eb2ec900e508aff451106b87a` remains an immutable ancestor. **Next separate step**: Controller L2 method/source review then, only if accepted, frozen pre-outcome prereg, bounded market source admission and one finite nonprotected developmental replay. No 360-day forward without a candidate.

`RC2_PROTECTED_RETRY=NOT_AUTHORIZED`; `G4_TESTNET=NOT_AUTHORIZED`; `REAL_FUNDS_WRITE_AUTHORITY=NONE`.
