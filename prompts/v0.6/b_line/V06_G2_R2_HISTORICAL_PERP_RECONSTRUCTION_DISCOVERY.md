# V06 G2 R2 — Historical USDT-M Perpetual Strategy Discovery, Development Reconstruction

## Task and authority

**TASK_ID:** `V06_B_LINE_G2_R2_HISTORICAL_PERP_RECONSTRUCTION`.

**CONTROLLER_DISPATCH_SHA:** `fdcac0bfc7126f9715c4db3ba84581eb7a93256c`, [immutable Controller G2 R2 authority](https://github.com/EXASHXE/btc-quant-agent-public/blob/fdcac0bfc7126f9715c4db3ba84581eb7a93256c/evidence/v0.6/controller/B_LINE_G2_R2_HISTORICAL_PERP_RECONSTRUCTION_DISPATCH.json).

**Start exact code commit:** `a56cc413d87a71111f2be02f10052dced9ff0275` on **v0.6**, containing G1 accepted offline engineering + CI repair. G1 accepted does **NOT** grant strategy quality, TESTNET or LIVE. G2 R1 source-blocked final SHA `aab31f8735c8be8f88651ef4677bd0c3a4068cae`, with first method commit `a46b0537c592f5d90a166aebe94737363f1706c0`. Do not rewrite, delete, change or pretend to rescue the R1 pre-registration.

**New feature branch:** `feature/v06-bline-g2-perp-reconstruction-r2`.
**New isolated worktree:** `/root/workspace/project/quant-v0.6/g2-perp-reconstruction-r2`. Do **not** reuse or switch the currently occupied existing G2 R1 `g2-strategy-discovery` worktree.

**Executor preference:** Sol High freezes scientific methodology and challenges outcomes; Gemini implements data/provenance/replay/test infrastructure, and can do the whole package if Sol not available. Luna can perform only mechanical source/metadata/contracts/test receipts after method freeze, not independent economics/alpha adjudication. Multiple executors must serialize the same task branch by **exact pushed SHA**; never concurrently edit same worktree. No need to ask user for repeated approval to perform this bounded task.

## Research objective and appropriate interpretation

Find **exploratory** evidence on whether any interpretable **BTCUSDT/ETHUSDT/SOLUSDT Binance USDT-M perpetual** direction LONG/SHORT and conservative grid/pause policies have plausible **realistic NET-of-cost performance** at short horizons (roughly 4h/12h/24h). Do not confuse this with RC1 valid hard FAIL, RC2 protected outcome PASS, or independent alpha.

**R1 blocker lesson:** Monthly exchange archive fetched today establishes past event timestamps and plausibly reconstructible history, **not** proof that an original historical market feature was received in live trading before its decision. R2 explicitly permits **historical event-time reconstruction with pre-frozen availability-lag assumptions**, only for previously exposed DEVELOPMENT evidence, while NEVER describing it as past receipt-proven live PIT or fresh untouched HOLDOUT. A *future* independent validation still needs an unexposed partition and separate Controller release authority. R1 method remains frozen and source-blocked.

**R2 is not required to wait 180 days** to conduct development tests. R2 **cannot** declare alpha PASS, TESTNET authority, real-funds readiness, or operational release based on historical proxy reconstruction. If empirical historical coverage/cost/PIT integrity is insufficient, mark DIAGNOSTIC_ONLY or SOURCE_BLOCKED without fabricating positive returns.

## Source and protection firewall — immutable

- Permit only public unauthenticated Binance **USDT-M** historical futures OHLCV/official exchange public funding records, allowlist BTCUSDT, ETHUSDT and SOLUSDT. Identify exact endpoint / ZIP monthly source / retrieval UTC / SHA256 archive/raw file / event bar opens and closes / release availability assumptions, duplicate/gap checks and published clock. Use no private exchange account API, credentials, signed order, balances, position endpoint, TESTNET, Feishu/OpenAI provider smoke, or trade execution.
- Forbidden RC2 sealed target symbols ZECUSDT, HYPEUSDT, ORCAUSDT, PUMPUSDT, NMRUSDT, BRUSDT, RLCUSDT, QNTUSDT, **including by public archive endpoint inside protected partitions**, along with A-line/H40/H41 protected outcomes, archives or unknown classified caches. Do not attempt RC2 reruns/cross-host one-shot admission or repurpose its invalid source cohort as fresh.
- All historical R2 crypto returns and old BTC/ETH/SOL studies are **PRIOR_EXPOSED_OR_DEVELOPMENT**; three chronological development partitions do not become a new blinded OOS merely by their timestamp labels.
- Data-grade field per feature/result: `RECEIPT_PROVEN_PIT` only with authenticated contemporaneous receipt and available_at proof (R2 is not expected to have this); `ARCHIVAL_EVENT_TIME_RECONSTRUCTED` with explicit conservative time lag; `UNKNOWN_OR_INELIGIBLE` blocked. Never fill absent derivative features from future data. Persist source ledger and release-lag assumptions.
- Use completed 1m bars. 15m/1h/4h indicators recomputed from historical **completed earlier bars only** with explicit lag. Signal/entry in the same bar prohibited. Resampling must account for UTC epoch and precise open/close timestamp. Synthetic fixtures can assert mechanics but never count toward empirical profitability.
- Source documents and metadata may be read first; **do not read/download empirical return bars for chosen windows before the prospective method is pushed**, even though history is not independently fresh.

## A. Preflight and branch creation

Read current [G2 R1 closeout](https://github.com/EXASHXE/btc-quant-agent-public/blob/aab31f8735c8be8f88651ef4677bd0c3a4068cae/evidence/v0.6/b_line/g2_discovery_r1/G2_R1_RESEARCH_REPORT.md), its nonmutable G2 R1 method (read-only), the existing MarketWatch feature evidence contract (read-only), G1's new `v0.6` code, and [G2 R2 scope contract](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/docs/project/V0.6_G2_R2_PERP_HISTORICAL_RECONSTRUCTION_CONTRACT.md).

READ-ONLY preflight:
```bash
ENTRY=/root/workspace/project/rc2-tactical-successor
WT=/root/workspace/project/quant-v0.6/g2-perp-reconstruction-r2
BASE=a56cc413d87a71111f2be02f10052dced9ff0275
git -C "$ENTRY" rev-parse --show-toplevel
git -C "$ENTRY" rev-parse HEAD
git -C "$ENTRY" status --porcelain=v1 --untracked-files=all
git -C "$ENTRY" worktree list --porcelain
git -C "$ENTRY" remote -v  # REDACT remote credentials in reports
```

Confirm remote identity `EXASHXE/btc-quant-agent-public`, `v0.6` HEAD exact `a56cc413d87a71111f2be02f10052dced9ff0275`, and trusted docs `fdcac0bfc7126f9715c4db3ba84581eb7a93256c` authority. Existing G1 `g1-engineering-preview`, G2 R1 `g2-strategy-discovery`, `controller-review`, and ENTRY remain untouched. Do not switch ENTRY branch; no reset, clean, stash, force, worktree migration, unsafe package install or shared caches. If G2 R2 new branch/worktree already exists, permit resume only after verifying exact task/clean Git state and branch lineage; otherwise STOP.

On clean new R2 path and absent R2 branch:
```bash
git -C "$ENTRY" worktree add --no-track -b feature/v06-bline-g2-perp-reconstruction-r2 "$WT" "$BASE"
cd "$WT"
test "$(git rev-parse HEAD)" = "$BASE"
```
Do not assume G2 R1 sidecar source exists on the new mainline (it does not). Reuse small G2 R1 source/replay functions via **path-by-path audited import** of exact blobs from `aab31f...` only if needed, with explicit source hashes in provenance. **Do not cherry-pick the R1 branch**, overwrite R1 frozen configs/evidence, or import its SPOT-only restrictions as perpetual execution semantics without a dedicated derivative rewrite and tests. Follow strict path separation below.

## B. STAGE A — first push immutable prospective R2 method BEFORE market price access

Create `configs/strategy_research/G2_R2_PERP_PREREGISTRATION.json`, `docs/strategy_research/G2_R2_METHOD.md`, and `evidence/v0.6/b_line/g2_reconstruction_r2/PRE_REGISTRATION_RECEIPT.json`.

Define and freeze:

1. exact Binance USDT-M product identity (continuous PERPETUAL, not spot, not quarterly), symbols BTC/ETH/SOL, date/time UTC development windows e.g. training `2026-04-01T00:00Z`–`2026-05-01T00:00Z`, exploratory segments `2026-05-01`–`2026-06-01`, `2026-06-01`–`2026-07-01`, `2026-07-01`–`2026-08-01` exclusive ends, and optional extended `2026-08-01`–`2026-09-01` **only if precommitted and uniformly applied**. These are **design suggestions**; actual method must choose exact constant windows BEFORE downloading outcomes. Record archive coverage for any start/month missingness.
2. candidate budget **at most 12 all-in**. Suggested fixed 8 directional combinations: **2 families** (trend breakout/retest; regime-aware pullback) × **2 directions** (LONG, SHORT) × **2 horizons** (4h, 12h). Plus 4 conservatively bounded range-grid policies (neutral / single-direction conservative grid × fixed 12h/24h or width variants), with strict boundary breach STOP, inventory MTM, effective notional/margin ceiling and maker fill realism. Define grid parameter and direction fixed at registration; unlike directional trades, grid returns must use common **capital-at-risk normalized units** for comparability. If empirically responsible grid simulation cannot be implemented, prereg an explicit **NO_GRID** variant and give up its portion of budget (do not silently substitute another winning family).
3. exact entry, exit, stop, max hold, ATR lookbacks, signal update frequency, source availability offsets, risk budget/inventory/overlap across positions; **leverage <=1x in research PnL accounting** (no liquidation-modelling evasion via 20x multiplication); forbidden martingale and averaging down; no production policy changes.
4. conservative contract for *one-minute* ambiguous TP/SL: SL-first if both within one bar; gap-stop worse price; no optimistic limit fills. Maker-dependent grid orders require evidence-supported fill priority or strong adverse conservative scenarios; no claims of guaranteed paired profit. Funding charges by time-aligned public funding rates when verifiable, otherwise conservative **nonzero adverse funding sensitivity** over each possible 8-hour funding interval; unavailable inputs are declared `PROXY_STRESS_ONLY` not actual measured cost.
5. **COST DECISION RULE BEFORE RESULTS:** freeze round-trip fees (maker/taker separately), spread/slippage/base and higher-cost stress levels in basis points, expected turnover and exit rates. Compare conservative taker cost case and a >1x fees/slippage stress; if realistic scenario unavailable, DIAGNOSTIC_ONLY not false PASS. Positive funding benefits must not be presumed.
6. diagnostics/control set: perpetual naïve matched-time LONG/SHORT, WAIT/no trade, historical RC1 known failed Tactical reference only where input semantics/source align; do not make it a resurrected policy. Define missing-data/unsupported-feature fallbacks **before** outcomes; no post-outcome tuning.
7. exact sample support and uncertainty: at least three independent **chronological developmental** partitions where history allows; all trades unique, purged/embargo ≥ max horizon at fold boundary, no overlapping same-symbol positions, cross-asset common-shock dependence; clustered/block-bootstrap or appropriate time-dependence-aware intervals, multiplicity for ≤12 tried strategies. Define pre-outcome ranking and **shortlist ≤2**. Compare gross and higher-cost net performance with matched exposure controls; fragile significance ⇒ DIAGNOSTIC_ONLY. Support thresholds are **development diagnostic heuristics** not authority to declare strategy PASS.
8. full prohibited-source admission rules and hard halt modes: unclassifiable archive provenance, missing 1m history, missing venue identity, bar timing lookahead, future funding publication, hidden outcome access, post-outcome method edits ⇒ fail closed. If source legal/rate-limited/unavailable, note and stop not manufacture sample.

**FIRST PUSH GATE:** Before opening actual chosen-window price bodies or inspecting chosen-window trade outcomes, commit and **push** method/candidate freeze as the **first G2 R2 commit** on feature branch. Query exact remote HEAD SHA, record `PRE_REG_R2_SHA` in a *subsequent* evidence commit (avoid circular SHA). If GitHub push fails STOP `BLOCKED_NOT_PUSHED`; no empirical execution. Frozen candidates/assumptions must not change after first push even if R2 development outcome surprises.

## C. STAGE B — implementation and realistic empirical development replay

Allowed implementation only under:
- `src/btc_quant_agent/strategy_research/**`
- `scripts/strategy_research/**`
- `tests/test_strategy_research_*.py`
- `configs/strategy_research/**`
- `docs/strategy_research/**`
- `evidence/v0.6/b_line/g2_reconstruction_r2/**`

Forbidden edits: `market_watch/**`, `decision/**`, `approval/**`, `execution/**`, `api.py`, `config.py`, `h40/**`, `h41/**`, historical `evidence/v0.5.5/**`, Controller authority, `scripts/rc2/validation/**`, CI workflow/planner, and both G1/G2 R1 worktrees. No raw downloaded futures archives under Git; temp cache in a unique `/tmp/v06-g2-r2-<pid>/`, with checksum and local cache provenance. Don't fetch more data than frozen partitions/timeframes need.

1. Obtain authentic public futures historical **1m** price arrays for every eligible symbol/month. Validate archive/source hash, consistent UTC millisecond timestamps, missing bars, duplicates, close/open continuity and symbol/perpetual contract type. Check **minimum source provenance** before any empirical result; if no data accessible, commit SOURCE_BLOCKED diagnostic without invented rows.
2. Reconstruct signal availability only after completed bars plus **frozen explicit public-feed lag**, flag all as `ARCHIVAL_EVENT_TIME_RECONSTRUCTED`; do not claim exact historical exchange arrival times. Funding/mark price/OI may enter only if historical event and real public availability semantics are defensible; otherwise exclude feature or subject result to frozen adverse sensitivity; no hindsight OI, future funding settlement or hidden total fees.
3. Implement strategy families exactly as preregistered. Directional fill next feasible 1m bar, gap stop worse execution, fair realistic fees/slippage/funding, no overlapping intrabar outcome ordering optimism. Grid inventory exposure/time-underwater, all legs charged realistic friction, unpaired carry and stop loss included, no cash-flow double counting.
4. Compare controls and all candidates on the **same** time identities and accounting; freeze baseline experiments; maintain deterministic event row/evaluation hash. Perform bounded chronological exploratory replay. Retune only on strictly preceding development data as explicitly registered; no leakage to future exploratory segment, no using earlier exposed OOS as blind.
5. Prioritize *actual* economic interpretation of adverse price movement, funding, fee stress and liquidity. If model assumptions would make favorable performance disappear under plausible stress, report this and de-prioritize. Do not use open-ended genetic optimization / unlimited parameter search or LLM to post-select the best lookback/regime/horizon.

### Essential tests

Hermetic synthetic:
- completed bar availability and 1m/15m/1h/4h resampling, lag/shift-by-one/lookahead attacks;
- symbol/market registry and RC2 target denylist, artifact checksum, duplicate/corrupt/gapped K lines;
- positive LONG / SHORT direction sign, funding side and sign/time, exposure/notional/margin units;
- maker/taker/slippage and 2x adverse stress, unfilled maker orders, stop/TP simultaneous bars, bad gaps, stale markets, boundary breach;
- no new grid buying into falling knife, capital lock and underwater loss; deterministic replay plus no R1 outcome/config edits;
- different Python version and Decimal contexts should not change fixed-seed scientific digests;
- protected reads and exchange signed writes zero.

L0 during work: changed-file Ruff, compile, contract tests. L1 once at terminal: own strategy_research tests (plus truly imported MarketWatch callers), provenance checks, mypy where valid, no full suite per edit. Python **3.12 is canonical** for project integration; if tests are 3.13 only, explicitly `PY312_NOT_CERTIFIED`; never say release-ready.

## D. STAGE C — comprehensive, non-survivor-filtered research evidence

Persist under `evidence/v0.6/b_line/g2_reconstruction_r2/**`:
- PRE_REGISTRATION_RECEIPT.json + remote freeze receipt / method hash / first push timestamp and git parent.
- SOURCE_AND_EXPOSURE_LEDGER.json with every symbol-month SHA256 archive, source URL, retrieval time, market type, present-day archive vs historical feature available proxy and any blocked source.
- CANDIDATE_REGISTRY.json and complete including failing/NOT_COMPUTABLE candidates.
- EXECUTION_SEMANTICS_AND_PIT_REPORT.json: bar causality, conservative unresolved collisions, unit conversions, funding and overlap tests.
- EXPLORATORY_RESULT_TABLE.json for **all** registered configurations: n, LONG/SHORT/WAIT, fill ratio, gross/net R and PnL, costs split, stop-before-target, MFE/MAE, holding time, drawdown/tail, regime/asset/fold stability, sample coverage, 2x cost stress, uncertainty, count of time blocks and multiple-testing caution. Grid needs MTM equity, paired realised profits **and** inventory/unpaired drawdown/time under water, capital utilisation and boundary breach.
- G2_R2_RESEARCH_REPORT.md: method, empirical blockers, against-claim alternative explanations, ≤2 prereg-ranked exploratory candidates **if** any, or honest NO_GO/DIAGNOSTIC_ONLY; **prospective R3 suggestion** requiring separate Controller-authorized unexposed data.
- TEST_RECEIPT.json: code/data/manifest SHA, environment, exact tests pass/fail/skip/duration, caches and protected reads zero, candidate count and terminal push identity.
- ORIGINAL_WORKTREE_PRESERVATION.json: existing ENTRY/G1/G2 R1/reviewer worktree untouched evidence, redact user data.

**Terminal state** must be exactly one:
- `G2_R2_EXPLORATORY_SHORTLIST_READY_FOR_CONTROLLER`: ≤2 qualified DEVELOPMENT candidates, supported and subjected to friction stress. **Not release alpha.**
- `G2_R2_EXPLORATORY_NO_GO`: enough empirical data, all registered candidates poor under frozen economics.
- `G2_R2_DIAGNOSTIC_ONLY`: evidence exists but sample, proxy source, cost/funding execution uncertainty prevents credible positive/negative conclusion.
- `G2_R2_SOURCE_OR_METHOD_BLOCKED`: cannot justify even historical reconstruction / causal semantics.
- `BLOCKED_NOT_PUSHED`: cannot verify first or final remote push.

No `TACTICAL_DECISION_QUALITY_PASS`, `RC2_HOLDOUT_PASS`, `G2_STRATEGY_ALPHA_ACCEPTED`, `TESTNET_READY`, `LIVE_APPROVAL_ONLY`.

**MANDATORY AUTO-PUSH:** Independently commit/push first prereg **before outcomes**; after code/tests/results, commit and push all allowed changes to `feature/v06-bline-g2-perp-reconstruction-r2`. Verify remote head/parent/diff, record `REMOTE_PUSH_VERIFIED=true` or STOP `BLOCKED_NOT_PUSHED`; do not ask user to push. Never push directly to v0.6; no merge or trading permission inherited.

Terminal include `CONTROLLER_DISPATCH_SHA=fdcac0bfc7126f9715c4db3ba84581eb7a93256c`, code start `a56cc413d87a71111f2be02f10052dced9ff0275`, first prereg SHA, implementation and evidence SHA, data grade, sample coverage, n candidates registered and evaluated, actual source digest, all costs and tests, URL to evidence, provenance, full/partial blockers and next `CONTROLLER_L2_G2_R2_RESEARCH_REVIEW`.

**Safety:** `REAL_FUNDS_WRITE_AUTHORITY=NONE`, `TESTNET=NOT_AUTHORIZED`, `PROTECTED_RC2_RETRY=FORBIDDEN`, no provider external actions, no live signals. Any favorable research result remains only a candidate for an independent follow-up.
