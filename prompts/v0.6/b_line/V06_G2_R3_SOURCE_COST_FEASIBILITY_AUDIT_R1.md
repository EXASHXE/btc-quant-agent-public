# v0.6 G2 R3 — Source, Funding, Cost and Support Feasibility Audit R1

**TASK_ID:** `V06_G2_R3_SOURCE_COST_FEASIBILITY_AUDIT_R1`
**CONTROLLER_DISPATCH_SHA:** `290664c17e14a4fd7530b5308b5fbdebb69b8a1e`
**Frozen Controller authority:** https://github.com/EXASHXE/btc-quant-agent-public/blob/290664c17e14a4fd7530b5308b5fbdebb69b8a1e/evidence/v0.6/controller/B_LINE_G2_R3_SOURCE_METHOD_FEASIBILITY_AUDIT_R1_DISPATCH.json
**Scientific review:** https://github.com/EXASHXE/btc-quant-agent-public/blob/290664c17e14a4fd7530b5308b5fbdebb69b8a1e/reviews/v0.6/b_line/V06_G2_R3_DESIGN_CONTROLLER_L2_SCIENTIFIC_REVIEW.md
**Repo:** `EXASHXE/btc-quant-agent-public`
**Start exact code SHA:** `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32` on `v0.6`
**Read-only R3 design SHA:** `e5b2006a89441f7eb2ec900e508aff451106b87a`, branch `feature/v06-bline-g2-r3-cost-aware-method-design`
**Target branch:** `feature/v06-bline-g2-r3-source-feasibility-r1`
**New, separate worktree:** `/root/workspace/project/quant-v0.6/g2-r3-source-feasibility-r1`
**Executor recommendation:** Sol High scientific/data-contract owner, Gemini may implement metadata-only collection and mechanically validate the report; neither has authority to start strategy code, new price-return access or fund writes. Run serially and pin each handoff to immutable pushed SHA.

## Required outcome and absolute fences

**This is a bounded SPECIFICATION and SOURCE FEASIBILITY study, NOT R3 prereg, historical backtest, fresh holdout or strategy-quality evaluation.** Its purpose is to determine whether the proposed 8 new structural-continuation and closed-retest LONG/SHORT 4h/12h variants could be evaluated with credible Binance USDT-M perps fee, funding, mark-price, tick/lot and availability semantics, at an affordable sample/compute budget.

**Forbidden**: Binance futures price/OHLCV 1m bodies, any return/trade outcome body, funding **rate-history bodies**, mark-price historical candles, order books/order-flow records, previously unknown cache data, protected RC2 assets ZECUSDT HYPEUSDT ORCAUSDT PUMPUSDT NMRUSDT BRUSDT RLCUSDT QNTUSDT, H40/H41/A-line research outcomes, account/private/signed Binance API, G1/G3 runtime/provider activity, TESTNET, orders, or any real funds. Do not browse new asset/month returns or optimize variables; do not run or modify R3 implementation (none is authorized). May read existing **published G2 R2 aggregate scientific report** and immutable R3 design only for context, not raw trade rows, prices or strategy replay.

Public documentation / technical source specs / explicit-symbol **nonprice** metadata may be retrieved, only when provenance, source, purpose, rate limit and size are known. Up to **30 HTTP requests and 10MB** of public metadata bytes total; stop on 429, unavailable legal/licensing permission, unforeseen protected/unbounded response or non-allowlisted endpoint. Avoid whole-universe / all-symbol queries: some exchangeInfo endpoints inherently return all symbols, so classify them `UNSUPPORTED_BY_SCOPE` rather than obtaining a full dump. The only admissible explicit symbol identifiers are BTCUSDT, ETHUSDT, SOLUSDT in Binance **USDT-M PERPETUAL**. No account credential, fee-tier probe, signing, preflight network scan or speculative endpoint discovery.

No tool access to local worktree? Return `BLOCKED_LOCAL_EXECUTOR_UNAVAILABLE`; never fabricate a successful Git push.

## Preflight and own worktree

Read-only Git identity/provenance check on existing ENTRY `/root/workspace/project/rc2-tactical-successor`. Verify `v0.6` remote head equals pinned `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32` and docs dispatch SHA above; verify `feature/v06-bline-g2-r3-cost-aware-method-design` HEAD is exactly `e5b2006a89441f7eb2ec900e508aff451106b87a`, and no edits in original/G1/G2 R1/G2 R2/G2 R3/G3/controller-review worktrees. Record Git metadata and dirty/untracked counts only; do **not** traverse or inspect G2 price caches. If existing target branch/worktree is occupied or user files exist, stop without clean/reset/move/stash.

Only after full preflight:
```bash
ENTRY=/root/workspace/project/rc2-tactical-successor
WT=/root/workspace/project/quant-v0.6/g2-r3-source-feasibility-r1
BASE=e0ff8c3473de4bfa3e66fe7928d42992a4d38a32
git -C "$ENTRY" worktree add --no-track -b feature/v06-bline-g2-r3-source-feasibility-r1 "$WT" "$BASE"
cd "$WT"
test "$(git rev-parse HEAD)" = "$BASE"
```

**Do not check out the design branch or cherry-pick it.** Read its fixed proposal files via SHA, and write only NEW source-audit documents into the authorized prefixes:
- `docs/strategy_research/g2_r3/source_audit/**`
- `evidence/v0.6/b_line/g2_r3_source_audit/**`

No source, scripts, tests, configs, `.github/workflows`, controller evidence, strategy candidates or design files are writable.

## Scientific tasks (minimal input, decidable outputs)

1. **Exchange/perpetual identity and filters.** Check publicly available issuer specifications and, only if exact explicit-symbol metadata admissible, PERPETUAL vs SPOT identity, quote/margin currency, trading status, price tick, LOT_SIZE, MARKET_LOT_SIZE, minimum notional. Distinguish **current** snapshot from verified effective 2026-01..04 historical filter versions; current filters are not historical proof. State source path, retrieved UTC, content SHA256/ETag if available, date and no account access. If historical filters cannot be certified, propose conservative tick/lot rounding and `HISTORICAL_FILTER_PROXY_ONLY` outcome, not measured execution.
2. **Fees.** Check published USDT-M regular-user taker commission applicable to this product and approximate relevant historical period, excluding any VIP, BNB, promo or referral assumption. Design fixed 6bp per-leg taker +2bp modeled half-spread +3bp slippage, stress 12+4+6; do not lower post hoc. A publishable fee guide does not authenticate user actual fee tier. If applicable standard fee >6bp or not knowable, explicitly `COST_SOURCE_NOT_VERIFIED` / `METHOD_REPAIR_REQUIRED`; never call a private fee endpoint.
3. **Funding schedule and cashflows.** Specify separate clocks: market calculation time, rate publication or archive generation time, effective interval changes, actual settlement time, expected/confirmed mark-price notional, historical adjustment/caps, and ownership around settlement clock jitter (the previously observed milliseconds). Use **documentation and metadata only**, not past funding rate arrays. Decide `SCHEDULE_SEMANTICS_VERIFIED`, `SCHEDULE_UNKNOWN_PROXY_ONLY` or `FUNDING_METHOD_BLOCKED`; never snap calculation clock to 00/08/16 and call it measured. Define sign conventions (LONG paying positive rates; SHORT receiving positive) and conservative no-funding-benefit selection. Unknown interval's hourly adverse charge is a **stress upper scenario** and cannot validate measured net returns. Note published cap shocks may make fixed 8bps per possible event insufficient; add separately bounded cap stress or fail closed.
4. **Historical minute-mark coverage feasibility.** Verify issuer format/schema/documentation, availability/retention, public archive URLs or manifest HEAD/metadata without opening mark-price historical candle bodies. Need active 1m **mark path** for minute MTM accounting, not merely trade OHLCV. Check whether Jan–Apr2026 3 symbols × time coverage could plausibly be obtained and hashed without violating retention and licensing rules. Existence of metadata alone is `POTENTIAL_COVERAGE`, not successful price-body coverage. If impossible or pricing source misleading ⇒ `SOURCE_BLOCKED`.
5. **Spread, impact, realistic taker fill.** Record no observed L2 depth/queue and therefore no independently measured bid/ask or slippage at past execution times. Report 2bp and3bp per-leg assumptions as proxies; propose a public source and exact limitation that could assess conservatism in a **later** authorized experimental phase. If nothing can bound plausible costs, do not certify a positive R3 shortlist.
6. **PIT and mechanical timeline** without replay. Build a compact event table for 1m OHLCV, completed 1h/4h aggregation, frozen bar+60s availability, decision, earliest fill, same-minute SL-first, gap stops, target cap, funding and mark-price MTM, margin/notional reserve, liquidation after 10% drawdown, per-candidate separate books, matched unfunded counterfactual. Identify any under-specified ordering (e.g. mark-minute publication lag vs close, settlement vs exit minute, forced deleveraging same minute) and propose exact prereg amendments before data access. No code or price downloads.
7. **Sparsity and budget power.** R3 proposals require **≥100 unique candidate trades in each monthly developmental fold** (total≥300/candidate), more selective than R2 candidates that had 20–66 trades per fold. Using ONLY prior published aggregate R2 counts and a hypothetical symbolic range of new signal rates, evaluate whether this is feasible in Feb–Apr2026 without ex-post window extension. This is a **design-time scenario estimate**, not observed R3 frequency. Explicitly separate: `POSITIVE_PROMOTION_SUPPORT`, `NEGATIVE_DEVELOPMENT_DIAGNOSTIC`, and `SUPPORTED_DEVELOPMENT_NO_GO`. State minimum power effect size, time dependence and joint weekly blocks; a simple "fewer than100 => no conclusion" must not force endless reruns. Support/sample threshold may be repaired ONLY before a later sealed prereg, never after seeing R3 outcomes.
8. **No covert strategy promotion.** Freeze no additional candidate IDs, no grid, no maker assumption, no LLM signal or realized alpha claim; original 8 proposals stay read-only. Check that the economics hurdle is **necessary not sufficient** for profit; an eligibility rule `stop >=2×stress cost` doesn't make expected PnL positive. No independent HOLDOUT from recycling Jan–Apr history.

## Required deliverables and terminal

Write:
- `docs/strategy_research/g2_r3/source_audit/SOURCE_SEMANTICS_AND_COST_FEASIBILITY.md` with dated source links/negative access assertions and fully scoped specifications, fee funding filter mark-price and PIT findings.
- `docs/strategy_research/g2_r3/source_audit/METHOD_REPAIR_DECISION.md` documenting precisely what must be added/amended in a **separate future pre-reg design** before any price data; classify blockers vs proxy-only limitations vs optional improvements, with 100-trades/fold feasibility guidance. **Do not edit prior R3 design itself.**
- `evidence/v0.6/b_line/g2_r3_source_audit/SOURCE_METADATA_LEDGER.json`: every actual public documentation or permitted metadata request/URL/UTC/HTTP status/bytes/hash, counts, authenticated? false, symbol classification; zero raw price/rate body downloads. If no external metadata accessible, disclose all sources `NOT_VERIFIED`, no invented hashes.
- `evidence/v0.6/b_line/g2_r3_source_audit/GATE_MATRIX.json`: normalized verdict per required gate (VERIFIED / POTENTIAL / PROXY_DIAGNOSTIC_ONLY / BLOCKED), technical uncertainty and evidence ref. Must explicitly describe what stays unverified.
- `evidence/v0.6/b_line/g2_r3_source_audit/AUDIT_RECEIPT.json`: Git baseline, Controller dispatch, design SHA, selected source inputs, no protected reads, no market outcome rows, no credentials/calls/orders, 0 implementation tests by authorization, validations JSON/diff/allowed scope, worktree metadata preservation, local+remote SHA. Avoid circular final-commit SHA.

Allowed terminal one of:
`G2_R3_SOURCE_FEASIBILITY_ACCEPTABLE_FOR_SEPARATE_PREREG` only if market/product identity, mark-feed feasibility, cost envelope, symbol filters and event-time semantics all sufficiently specified for later developmental reconstruction; this still **does not certify actual historical coverage or positive alpha**.
`G2_R3_SOURCE_PROXY_DIAGNOSTIC_ONLY` where known issuer provenance plus conservative explicit proxies permit only diagnostic economic exercises under future authority;
`G2_R3_METHOD_REPAIR_REQUIRED_BEFORE_PREREG` if live engineering semantics/equity/settlement/source admission contradictions require pre-freeze correction;
`G2_R3_SOURCE_BLOCKED` if source identity/admission unavailable or completeness cannot be credibly established;
`BLOCKED_NOT_PUSHED`.

Validation: only audit document readability/JSON syntax/source hashes/changed-path whitelist/`git diff --check` and relevant no-network constraints; no empirical market tests, full pytest or CI reruns just for docs. Human-readable report must distinguish proposal, official source claim and verified empirical finding. Preserve request budget receipts.

**MANDATORY AUTO-COMMIT AND PUSH:** Stage only the two allowed prefixes, commit on new `feature/v06-bline-g2-r3-source-feasibility-r1` branch, push without force, fresh read of remote HEAD/parent/tree/changed paths and return `REMOTE_PUSH_VERIFIED=true` only if verified. If cannot push, `BLOCKED_NOT_PUSHED`. No merge to v0.6. Next Controller L2 decides a separate method repair or tightly authorized freeze-first developmental implementation. Both `G4_TESTNET=NOT_AUTHORIZED` and `REAL_FUNDS_WRITE_AUTHORITY=NONE`.
