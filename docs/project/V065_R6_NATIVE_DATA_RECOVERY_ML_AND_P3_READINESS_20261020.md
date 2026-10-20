# quant v0.6.5 — R6 Native Data Recovery, ML Architecture and Net-PnL Readiness

**Status as of 2026-10-20.** Controller B decision-grade addendum. This file supersedes stale READY/running labels in earlier R1–R5 roadmap text; it is not an executable approval or a repository code change. **Conversation language:** Chinese by default. **Documentation/task prompt language:** English.

**Verified remote references:** executable main \`v0.6.5@5116a61fa255d9823be80416a659ca6acdecf70f\`; documentation baseline before this addendum \`docs/engineering@90c3fe6eca63e08a7b24025a0c946e066b96235b\`. Owner checkout was independently read-only observed at \`39a68a1c8b3490a5a3826d2fab6a7e3f0e441dc2\` with dirty tracked and untracked research files. Never equate checkout HEAD with remote executable HEAD; preserve both.

## 1. Native 2022 top-position-ratio repairability — verified

Existing scoped R3 source-forensics terminal: \`NATIVE_RATIO_2022_PUBLISHER_GAP\`, artifact \`/root/workspace/project/crypto-data/lakehouse/research-bline-r3-ratio-gap/NEXT_DECISION.md\` and \`reconciliation_report.json\`.

- R3 audited all **365** 2022 Binance Vision BTCUSDT USD-M daily metrics archives, official checksum sidecars and invariant 8-column CSV header. The 2022 set contains **105,120** five-minute rows; \`sum_toptrader_long_short_ratio\` contains **91,733 actual empty strings**, with 314 fully blank calendar days. Exactly **7,645 of 8,760** scheduled hourly origins lack the native position ratio; **1,115** ratio origins survive, while **8,750** hourly base-OI origins are present.
- On 2026-10-20 Controller independently opened **four original archive ZIPs**, checked their SHA-256 against the existing R3 reference-slice hashes, and counted actual raw CSV fields without printing private/outcome rows:
  - 2022-02-15: 288/288 position-ratio blanks, 0/288 base-OI blanks;
  - 2022-06-15: 0/288 position-ratio blanks, 0/288 base-OI blanks;
  - 2022-07-15: 288/288 position-ratio blanks, 0/288 base-OI blanks;
  - 2022-12-15: 0/288 position-ratio blanks, 0/288 base-OI blanks.
  All four ZIP hashes matched. Matching publisher sidecars for the full 2022 collection are **reported by the earlier R3 audit**, not newly rechecked individually in this addendum.
- R3 reported no raw/normalized column mapping mismatch, row absence or timestamp mismatch behind the hourly gap. Native field loss is an upstream publisher-source absence, not a repairable CSV parsing bug.
- Binance USD-M \`/futures/data/topLongShortPositionRatio\` exposes only a rolling 30-day historical window; it cannot currently retrieve 2022. Official source reference: https://github.com/binance/binance-futures-connector-python/blob/main/binance/um_futures/market.py .
- **Precise repair statement:** cannot reconstruct the missing **original Binance-native 2022 Top Trader Position Ratio values** from these officially preserved empty records or the current 30-day API, without an independently archived historical copy of the same exact field and independently authenticated provenance. No whole-host or third-party nonexistence claim is made. Do not substitute account ratio, global ratio, OI notional, inferred value, another venue or interpolation as if it were the native position ratio.
- Other features are usable for separate **exploratory model registrations**: base OI where valid, spot/perpetual bars, taker imbalance, funding, premium and basis. These do **not** restore P1's originally specified Z. Preserve missingness masks.

## 2. Current milestones and authoritative terminals

| Track | Evidence/result | Next interpretation |
|---|---|---|
| R1/R2 historical feature pipeline | R1 engineering pipeline accepted; native OI expansion completed | Source coverage is not receiver-first-known PIT, outcome authorization, or Alpha |
| 2022 native ratio gap | \`NATIVE_RATIO_2022_PUBLISHER_GAP\` with original ZIP provenance and measured raw blanks | STOP futile identical-field historical backfills; allow newly authenticated exact archived source only |
| R4/R5 TLOB novelty | R5 engineering code published on main 5116a61; 24/24 focused tests independently reported passing; \`R5_INCONCLUSIVE_P1_COMPARATOR_UNAVAILABLE\` | \`TLOB=X AND Z\` provides zero new same-symbol X timestamps, but conditional profitability remains untested |
| P1 historical fitted comparator | \`P1_BUNDLE_UNAVAILABLE_AFTER_BOUNDED_CHECK\` in the exact 17-file allowlist | No substitute re-fit of a purportedly frozen old P1; source implementation and synthetic tests remain available |
| Multi-asset pilot | \`PORTFOLIO_FREQUENCY_IMPROVED_FEATURE_ONLY\`: 826 unique 8h portfolio clusters vs 294 BTC-only on the same **26,901** covered calendar hours; 115,564 eligible asset-hours; 580 simultaneous UTC candidate hours | Opportunity density improved, but this is **not net-PnL, causal independence or new Alpha**. Don't re-dispatch pilot |
| First-net-PnL DEV Gate 1 | \`P3_SCOPE_BLOCKED\`; owner research consent recorded; zero outcome labels/materializations, no PnL | Blocked on authenticated Owner v2 task-specific source/date/mask/privacy and two-phase materialization permissions |
| Owner-v2 scope preparation | \`OWNER_V2_SCOPE_AWAITING_AUTHENTICATED_INPUT\`; draft \`UNATTESTED_DRAFT\`, 11 negative checks PASS | Structural validation cannot authenticate human approval; draft is **not authority** |
| Historical TLOB owner contract | \`BLOCKED_ON_EXACT_INPUT_OR_AUTHORITY\`; registered feature-only candidate and synthetic compatibility, but real entry/exit/cost/capital policy and authenticated X/matched masks missing | Owner/Controller supplies authentic scoped contract; no historical outcome read |

**Scope note:** earlier attempts read a pure-feature April 2026 row outside an intended 2021–2024 R5 inspection window; it was not used for analysis, and no outcomes were read. Do not certify that all preliminary feature reads were in range.

## 3. Research architecture — separate immutable legacy from new exploratory science

\`\`\`
PUBLIC SOURCE CATALOG / RIGHTS / NATIVE BYTES
           |
    hash + native identity + timestamps + missingness
           |
       PIT / availability provenance  (PIT_UNKNOWN until proven)
           |
   feature-only research lake (read-only archives and immutable registrations)
           |                             |
   P1 baseline: X_common/XZ_common     multi-asset BTC/ETH/BNB/XRP
   P1 X_full separate training arm     frequency + overlap only (COMPLETED)
           |                             |
       P1-R2 new versioned evaluator      new preregistered hypotheses only
           |                             |
       Owner-v2 task-specific authenticated scope and masks
           |
   P3 phase 1 → authorized panel → derived allowlist
           |
  source/feature/fold/exit/economics contract validated
           |
    Authorized EXPOSED_DEV net-PnL research
           |
    paired expectancy / costs / drawdown / block uncertainty
           |
   independent, separately authorized confirmation gates
\`\`\`

- Keep original P1/R1–R5 contracts immutable. Existing P1 provides ten X controls, a 4h OI + native top-position interaction, training-fold-only normalization, sign-constrained ridge regression, nested tuning and baseline/stress cost assumptions.
- **P1-R2 only as a new engineering/research version:** fix mutually inconsistent \`92 * 24\` panel-size and three 14-day outer validation folds versus 12-week support floor. Six 14-day validation windows after initial day 42 require **at least day 126 for fold coverage**, plus appropriate exit-label/feature tail or separate compatible authorization; a 127-day contiguous hourly panel is a plausible implementation planning bound, not a standing P3 authorization.
- Native Owner v2/P3 bridge remains capped at **92 days and BTC-specific channel/registration** in the inspected contract. Do **not** silently widen the authorized panel, concatenate disallowed 92-day windows, change the Owner bridge, or treat a 126/127-day synthetic grid as outcome permission. Draft a separately versioned **synthetic-only compatibility contract** with exact implications for P3 first; obtain task-specific Controller and authenticated Owner acceptance before any real input.
- Separate \`X_common\` (same observed native Z training/validation origins as XZ), \`XZ_common\`, and \`X_full\` (X-only training and deployment population). Preserve purge/embargo and full source availability masks; never use an X/Z paired denominator to claim full X eligibility.
- **Cost-aware trading decision:** distinguish ex-ante causal/observable funding reserve and assumed fees from ex-post realized funding, bid/ask proxy and exit-price-scaled costs. No actual future funding is allowed in the entry decision. Do not equate Last Price proxy and synthetic 16/32bp costs with live fills.
- The eight multiplicity slots include four frozen B slots with p=1.0 and \`RESERVED_NOT_ENABLED\`; they are not free entitlement to choose several Funding/Premium models post-hoc. New Mechanism B must have a predeclared feature/parameter/selection plan and multiplicity handling.
- Multi-symbol work must retain symbol-specific funding/cost/PIT, cross-symbol clustering and simultaneous risk. BTC+ETH+BNB+XRP frequency expansion is promising for **coverage**, not yet for profit.

## 4. Updated execution order (no outcome accesses implied)

**Track A — P0 owner/control dependency (not a new consent request):**
1. Refresh exact source/feature refs, identify actual private authorized Scope v2 and its genuine Owner/Controller provenance, or have the Owner supply one authentic task-specific \`exposed_dev_bridge.owner-scope.v2\` package and companion contract.
2. Scope must name the candidate, purpose, allowed DEV dates and all protected/private exclusions, exact source roots/products/fields/hashes, independent native source/PIT limits, X and paired masks/registration hashes, two-phase panel plan, and frozen entry/exit/order/fill/missingness/cost/funding/capital policy.
3. Existing research consent is already recorded; do not ask the user to approve research in general again. Controller acceptance and derived allowlist are later distinct gates. No invented dates, signers, signatures, permissions or hashes. Request only verifiable missing facts.
4. Resolve explicit **92-day vs proposed 126/127-day** eligibility and historical TLOB/BTC channel/registration compatibility through a separately approved route; maintain outcome-access HOLD until every genuine gate passes.

**Track B — P0 Codex synthetic-only research engineering (independent paths):**
1. Audit/fix P1 three-versus-six-fold minimum-week support deadlock in a new version, not frozen P1; separate \`X_common\`, \`XZ_common\`, \`X_full\` train/eval masks; refactor constant diagnostic status; preserve exact purge and embargo.
2. Produce a metadata-only P3 compatibility impact assessment before any real adapter/label materializer; existing 92-day contract remains unchanged. Show whether an approved multi-panel route could preserve 12 valid blocks without prohibited concatenation; else stop and seek a separately accepted 126+ day route.
3. For dynamic funding-aware policy, supply a **proposal and synthetic tests only** using decision-time-available information; leave old 5bp/day policy frozen.
4. Focused tests, provenance/changed-path evidence and no market outcomes. No obligatory 1-A audit for routine synthetic code.

**Track C — conditional once Track A passes:**
Run a separately preregistered, authorized \`EXPOSED_DEV\` historical net-PnL analysis for X vs XZ on matched origin sets and X_full independently; also allow registered TLOB vs its X price baseline without requiring historical fitted P1. Include exact entry/exit, fee/slippage and complete native funding calendars, missingness treatment, trade-level payoff ratio, Profit Factor, net expectancy, drawdown, yearly stability, effective blocks and uncertainty. **No real PnL, fitted claims or candidate promotion before allowed data access.**

**Track D — deferred mechanism discovery:**
Choose at most one initial continuous position-overhang (P1-A) and one preregistered funding/basis mechanism, subject to source QA/PIT. Additional symbols or ML complexity only after evidence of conditional net improvement. Zero viable candidate remains a valid STOP.

## 5. Final statuses and owner dashboard rules

- \`P3_ACCESS_SCOPE_HOLD / SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / COST_UNVALIDATED_REAL_FILL / UTILITY_NOT_IDENTIFIED / NO_ALPHA_ESTABLISHED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE\` remain in effect.
- Do not change CI, TESTNET/LIVE, orders or real funds. Preserve the dirty local checkout and protected Owner archival roots. No backfill-by-imputation.
- Controller's owner-facing conversation is Chinese; executable documents and prompts are English. At most two compact task cards with **one Copy prompt button each**, the full prompt body hidden.
- The first decision-changing action is **authenticated scoped Owner/Controller contract completion**, while Codex may independently deliver synthetic-only P1-R2 compatibility engineering. Do not redispatch completed R2 or multi-asset frequency studies and do not launch outcome materialization prematurely.

## Primary evidence locators

- R3 native 2022 ratio: \`/root/workspace/project/crypto-data/lakehouse/research-bline-r3-ratio-gap/reconciliation_report.json\`, \`reference_slices.json\`, \`NEXT_DECISION.md\`
- Multi-asset: \`/root/workspace/project/crypto-data/lakehouse/multi-asset-r2-frequency-20261020/portfolio_density_summary.json\`, \`DECISION.md\`, \`RUN_RECEIPT.json\`
- Gate 1: \`/root/workspace/project/crypto-data/lakehouse/first-net-pnl-dev-backtest-20261020T0525Z/GATE1_DECISION.md\`
- Owner scope: \`/root/workspace/project/crypto-data/lakehouse/owner-v2-p3-scope-package-20261020-01/DECISION.md\`
- Historical TLOB contract gate: \`/root/workspace/project/crypto-data/lakehouse/historical-tlob-owner-contract-gate-20261020-01/OWNER_INPUT_GATE_DECISION.md\`
- Executable source: \`scripts/research/strategy_eval/{__init__.py,clocked_dataset.py,pipeline.py,costs.py}\` at frozen 5116a61; no code was changed for this document.
