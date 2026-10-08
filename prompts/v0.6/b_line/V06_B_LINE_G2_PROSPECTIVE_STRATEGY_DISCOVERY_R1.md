# V06 B-line G2 — prospective Strategy Discovery R1 (NONPROTECTED, parallel with G1)

## Dispatch identity and executor role

This is one **bounded scientific-research work package** with a forced PRE-REGISTRATION stage *before looking at newly selected empirical outcomes*. No previously invalid protected RC2 execution is repeated.

| Field | Immutable contract |
|---|---|
| TASK_ID | `V06_B_LINE_G2_PROSPECTIVE_STRATEGY_DISCOVERY_R1` |
| REPOSITORY | `EXASHXE/btc-quant-agent-public` |
| CONTROLLER_DISPATCH_SHA | `0cc3d6e14d5c4e301c987b9e760fabb393e8141a` — [Controller development authority](https://github.com/EXASHXE/btc-quant-agent-public/blob/0cc3d6e14d5c4e301c987b9e760fabb393e8141a/evidence/v0.6/controller/B_LINE_G2_DISCOVERY_R1_DEV_DISPATCH_AUTHORITY.json) |
| G2 code START_SHA | `d6500140f3141d179181f2360ad815b5bfe9c954` — separate `v0.6` baseline |
| Target feature branch | `feature/v06-bline-g2-strategy-discovery-r1` |
| Existing entry checkout | `/root/workspace/project/rc2-tactical-successor` |
| G2 isolated worktree | `/root/workspace/project/rc2-tactical-successor-v06-g2-r1` |
| G1 concurrent worktree | `/root/workspace/project/rc2-tactical-successor-v06-preview-r1` — **DO NOT TOUCH** |
| Allowed test capability | hermetic, nonprotected development only |
| Protected RC2 retry | `NOT_AUTHORIZED`; neither archive read nor outcome resolution |
| Exchange/API key/write, TESTNET, live funds | `FORBIDDEN` / `NONE` |

**Choose executor profile without changing the authority:**
- **Sol High (preferred):** lead the research design, adversarial validity challenge, evidence interpretation, and optionally implementation if tools allow. Scientific judgment and methodology decisions own this profile.
- **Gemini:** lead sustained coding, deterministic replay adapters, tests, data manifests, experiment execution and end-to-end artifact publication. Gemini may execute the entire prompt when Sol is unavailable, but MUST follow the pre-registered design without outcome-informed alteration.
- **Luna:** use for narrowly bounded, deterministic metadata inventory, syntax, test planning, hashes, regression checks, data coverage and receipts **after the method is frozen**. Luna alone **cannot** adjudicate a new strategy-quality PASS or claim alpha. If given the whole task, do only the mechanical subset, publish clearly incomplete evidence and mark `NEEDS_SOL_OR_CONTROLLER_SCIENTIFIC_REVIEW`.

Any executor may work from this *same prompt* but must record `executor_profile`, what it completed, what it **did not** complete, and independent review needs. Avoid running multiple concurrent executors on the **same branch/worktree**. If Sol and Gemini both participate, serialise handoff by exact pushed immutable commit (Sol pre-reg first, Gemini implementation after), not shared dirty files.

### Required reading

- [B-line v0.6 roadmap](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/docs/project/V0.6_PROJECT_STATUS_AND_ROADMAP.md)
- [G2 scientific/evidence contract](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/docs/project/V0.6_G2_STRATEGY_DISCOVERY_R1_CONTRACT.md)
- [Legacy B-line tactical evaluation contract](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/reviews/v0.5/tactical-policy/V0.5.5_B_LINE_TACTICAL_DECISION_QUALITY_R1_EVALUATION_CONTRACT.md)
- [RC1 valid hard-FAIL](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/evidence/v0.5.5/controller/B_LINE_RC1_WP_B_ADJUDICATION.json)
- [RC2 R1.1 limited infra acceptance](https://github.com/EXASHXE/btc-quant-agent-public/blob/f123cc5811aa4be0f071922d7c42d6145ed0f6fd/reviews/v0.5/rc2/V0.5.5_RC2_FINAL_HOLDOUT_INFRA_REPAIR_R1_1_CONTROLLER_L2_DISPOSITION.md)
- [CI/test-economy policy](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/docs/project/B_LINE_TEST_AND_CI_ECONOMY_V1.md)

## 1. Objective and honest terminal states

Primary question: **is there a small, intelligible, PIT-safe, transaction-cost-aware family of short-horizon crypto directional or grid strategies that merits a strictly fresh independent validation?**

Research horizons should serve the intended use of **a few hours to 12/24h**, not assume every opportunity fits exactly 12h. Compare **2–6h, 6–12h, 12–24h** as separate explicitly predefined horizons when support permits; avoid crossing multi-horizon trade outcomes or selecting best horizon retrospectively.

Do **not** change old Tactical `TACTICAL_POLICY_R2_B0` or `TACTICAL_POLICY_R2_B1` params, RC1/RC2 cost assumptions, frozen target universe, previous Holdout boundaries, nor G1 execution code. G2 is a **research sidecar**, not a new production policy.

Outcomes:
- `G2_R1_EXPLORATORY_SHORTLIST_READY_FOR_CONTROLLER`: integrity/support met for a *development-data* shortlist, **not** validated alpha.
- `G2_R1_EXPLORATORY_NO_GO`: usable data and valid evaluation, but no candidate appears economically worthwhile.
- `G2_R1_DIAGNOSTIC_ONLY_INSUFFICIENT_DATA`: causality/cost-safe evaluation but insufficient support or independent samples.
- `G2_R1_METHOD_OR_SOURCE_BLOCKED`: methodology, PIT, source identity, exposure, provenance or measurement not safely demonstrable.
- `BLOCKED_NOT_PUSHED`: if required proactive public remote push or verification fails.

**Forbidden terminal:** `TACTICAL_DECISION_QUALITY_PASS`, `RC2_HOLDOUT_PASS`, `LIVE_AUTHORIZED`. Historical development-data success cannot become independently validated policy quality merely because its formula beats the old thresholds.

## 2. Worktree, Git, file/dataset behavior (mandatory)

The original root `/root/workspace/project/rc2-tactical-successor` is a user-controlled checkout, potentially still on RC2 validation. Do NOT switch its branch, change tracked/untracked files, reset/stash/clean, delete worktrees or rewrite remotes. G1 has its own sibling worktree. G2 MUST use a **different** sibling worktree.

Read-only preflight in original entry checkout:

```bash
ENTRY=/root/workspace/project/rc2-tactical-successor
WT=/root/workspace/project/rc2-tactical-successor-v06-g2-r1
cd "$ENTRY" || exit 1
pwd -P
git rev-parse --show-toplevel
git rev-parse HEAD
git branch --show-current
git status --porcelain=v1 --untracked-files=all
git worktree list --porcelain
git remote -v  # redact tokens/userinfo in published receipts
```

The real root must equal ENTRY; validate remote identity is actually `EXASHXE/btc-quant-agent-public`, regardless of whether the verified public remote is named origin. No `git init`, clone into ENTRY, force changes to remotes or ref hacks. Fetch only required `v0.6`/`v0.6-docs` refs plus pinned source objects from verified remote **without checking out ENTRY**. Assert `v0.6` remote HEAD still equals `d6500140f3141d179181f2360ad815b5bfe9c954`; `0cc3d6e14d5c4e301c987b9e760fabb393e8141a` belongs to fetched trusted docs ancestry and contains the exact permitted G2 authority JSON. If not, stop with `BLOCKED_IDENTITY_OR_BASE_DRIFT`.

Create the isolated worktree only when its path and branch are unused:

```bash
git worktree add --no-track -b feature/v06-bline-g2-strategy-discovery-r1 \
  "$WT" d6500140f3141d179181f2360ad815b5bfe9c954
cd "$WT" || exit 1
test "$(git rev-parse HEAD)" = d6500140f3141d179181f2360ad815b5bfe9c954
git status --porcelain=v1
```

For an existing task branch/path, resume only if exact task ownership, parent, scope, and clean status are provable; otherwise stop `BLOCKED_WORKTREE_COLLISION`. No `git reset --hard`, `git clean -fd[x]`, `git stash` on ENTRY, `git checkout -f`, `git push --force`, destructive cleanup, worktree removal or modifications to `Quant-agent-sanitized`. Do not touch `/root/workspace/project/rc2-tactical-successor-v06-preview-r1` (G1). Never commit archives, `.env`, tokens, exchange credentials, downloaded raw 1m market archives, or user-private files.

### Exclusive G2 editable surfaces

- New independent modules `src/btc_quant_agent/strategy_research/**` (may READ existing MarketWatch APIs as immutable dependencies);
- `scripts/strategy_research/**` (new CLI/replay/analysis scripts);
- `tests/test_strategy_research_*.py` (new unit/contract/adversarial tests);
- `configs/strategy_research/**` (fixed prospective method/candidate YAML/JSON);
- `docs/strategy_research/**` (research notes);
- `evidence/v0.6/b_line/g2_discovery_r1/**` (append-only receipts, no raw protected data).

**Forbidden edits** include `src/btc_quant_agent/market_watch/**`, `src/btc_quant_agent/decision/**`, `approval/**`, `execution/**`, `api.py`, `config.py`, `src/btc_quant_agent/h40/**`, `h41/**`, `tests/h41/**`, `scripts/rc2/validation/**`, CI workflows and test planner, `data/forward/**`, `data/research/**`, `evidence/v0.5.5/**` and controller authority. If a shared module fix is essential, record a minimized issue and STOP — no shared source expansion while G1 is concurrent.

Use unique task-specific temporary directories under `/tmp/v06-g2-r1-<pid>/` for **nonprotected** local source cache and synthetic fixtures only; avoid existing caches whose contents/protection status are unproven. No recursive scan of all data directories, no network endpoint discovery against protected symbols, no secret scrapes. Local fixture permission/scope needs manifest proof; unknown permission => do not read.

## 3. Firewalls for source, outcome and history

**Allowed research universe:** `BTCUSDT`, `ETHUSDT`, `SOLUSDT` only, with a prospectively bound asset/symbol set, exact venue and data contract. This is *not* a fresh blind cohort: some BTC/ETH/SOL histories were already analysed in RC1. Mark all historical outcomes before task dispatch as `PRIOR_EXPOSED_OR_DEVELOPMENT`, **never independently untouched holdout**, even if fetched again.

**Sealed/protected RC2 target symbols FORBIDDEN:** `ZECUSDT`, `HYPEUSDT`, `ORCAUSDT`, `PUMPUSDT`, `NMRUSDT`, `BRUSDT`, `RLCUSDT`, `QNTUSDT`. Do not read their archives, historical cached observations, outcome manifests or network source within reserved RC2 target partitions. A public exchange endpoint does NOT revoke scientific exposure protection. No `HOLDOUT_FINAL`, `FINAL_TARGET_SEAL`, `scripts/rc2/validation --execute`, A-line/H40/H41 outcome or synthetic authority reads.

Public Binance unauthenticated **read-only** historical-data download for allowlisted BTC/ETH/SOL is permitted solely where a data source and time window have been pre-registered and internet/source access is available. No private signed endpoint, no API key, no order, balance, funding payment, account or TESTNET call; no proxy/credential recovery. Prefer already **verified nonprotected** fixtures only. Record exchange, market type, endpoint, response/archive digest, retrieval timestamp, source event time, publication lag, availability and missingness. If source is unavailable or terms/rate limits forbid, report missingness and stop/diagnostic rather than generate synthetic trading alpha data. Synthetic market data is for unit tests only, not empirical profitability.

**CRITICAL: pre-registration must be pushed before reading NEW empirical outcomes.** If there are already known results for a cohort, disclose as exposed/development instead of claiming blindness. Future independent quality authorization can only be granted by Controller in a new task with demonstrably unexposed partition and freeze provenance; not by this executor.

## 4. STAGE A — metadata-only audit + prospective method freeze, then FIRST PUSH

Before any new outcome backtest, inspect the existing v0.6 MarketWatch interfaces, accepted contracts and **metadata-only** data accessibility. No price series/oos performance scans before freeze. Include a nonprotected source-ledger recording what has already been seen by RC1/RC2 and each selected data source's trust level; do not access protected raw material.

Design and commit `configs/strategy_research/G2_R1_PREREGISTRATION.json` plus `evidence/v0.6/b_line/g2_discovery_r1/PRE_REGISTRATION_RECEIPT.json` and any method/design note, containing at least:

1. Research question, exact allowlisted symbols, market type (e.g. USDT-M perp vs spot) and data identity; fixed inclusive/exclusive time boundaries *chosen before outcome data access*. Define disjoint development/calibration, internally exploratory rolling OOS, and separate **FUTURE_NOT_YET_AVAILABLE_OR_NOT_AUTHORIZED** independent cohort. Even strict chronological historical splits are **not fresh independent release evidence** if previously exposed.
2. **At most 12 total registered candidates**; preferably 3 interpretable families × 4 fixed coarse variants. Suggested candidate families (adjust only at prereg time): (A) trend-following breakout/retest, (B) pullback/mean-reversion within an interpretable regime, (C) neutral/range-grid versus pause; compare against WAIT, no-trade, naïve directional controls and an existing frozen Tactical baseline as **diagnostic**. Do not automatically promote Grid/Trend shadow features from the accepted Tactical implementation.
3. Explicit entry conditions, WAIT/NO-TRADE controls, direction, holding horizon **2–6h / 6–12h / 12–24h**, stop/exit and fill semantics, maker/taker assumptions, costs incl. funding/fees/spread/slippage, decimal precision, no martingale or unbounded grid inventory, grid capital utilization and boundary stop. Define a fixed candidate-selection budget and a **single** scoring/ranking rule before outcomes; no open-ended parameter grid search or retrospective subgroup rescue.
4. PIT fields: receipt/event/available/decision/execution timestamps; no same-bar signal-and-fill, conservative ambiguous TP/SL ordering; derivative features only if point-in-time available. If funding/OI/liquidity history is missing or unavailable at decision time, candidate requiring it is **ineligible or explicitly ablated as preregistered**, not silently forward-filled.
5. Data eligibility/coverage thresholds, resampling time alignment and no missing 1m outcome filler; unique trades and purged/embargoed overlapping holding periods across validation boundaries; handling simultaneous asset shocks and clustered trades.
6. Planned realistic friction sensitivity (base, higher-cost stress, maker-not-filled scenario), no inflated 10–20x leveraged PnL, distinguish fee rate from margin return; no claim of funding profitability without time-aligned actual funding schedule.
7. Minimum evidence/support (report actionable counts, LONG/SHORT imbalance, 3 chronological partitions when available, >=100 trades/partition coverage from historic precedent as an **exploratory reference**, not a newly approved release pass). If shorter data can't support robust inference, predeclare `DIAGNOSTIC_ONLY`. Predeclare statistical uncertainty using time-block bootstrap/cluster-aware uncertainty, multiple-candidate correction or clearly labelled exploratory screening; evaluate baselines with same cost model.
8. Stop rules: strict PIT violation, unknown source lineage, partial exposure mistaken for blind, unmeasured costs, look-ahead, hidden test tuning, unstable accounting, or protected-read capability => FAIL CLOSED.

**Required first push:** commit and PUSH the method freeze to target feature branch **before opening selected historical prices/outcomes**, verify remote `PRE_REGISTRATION_SHA` and branch HEAD; save exact method commit SHA. If unable to push now, terminal `BLOCKED_NOT_PUSHED`; **do not run outcomes**. If another executor continues, it MUST start from this immutable SHA without altering frozen prereg files.

## 5. STAGE B — implement bounded research sidecar and replay

Once PRE_REGISTRATION_SHA is remotely fixed:

- Implement typed, deterministic source ingestion/normalization and availability schema (read-only, UTC/event-time/PIT), symbol/timeframe calendars, idempotent input manifest digests; no reuse of previously burned protected cache data.
- Build **only registered candidates**. Use accepted `market_watch` APIs read-only where compatible and emit new independent `strategy_research` result structures; never mutate accepted strategy or production MarketWatch schemas. Evaluate signals on completed bars, enter on following tradable bar with conservative costs/fills, no within-bar hindsight.
- Test event-time causality, missing 1m data, late derivative prints, source permutation invariance, version/cache digest changes, shift-by-one/look-ahead attack, stop/TP collision conservative ordering, missing maker fills, funding sign, per-trade notional/margin invariance, grid overrun/underwater/accounting, restart/replay determinism, duplicate identity, and generated output dataset provenance.
- Produce **development-only** chronological walk-forward or fixed chronological replay, no optimization on a previously viewed evaluation slice; if you alter candidates/horizons after seeing outcomes you must **retire this preregistered campaign** and propose a new one without pretending the same dataset is fresh.
- If G2 data are unavailable, implement the harness with synthetic unit tests, publish source-data blocker; no fabricated profitability.
- Record all 12 candidate statuses (eligible/rejected/not-computable), all trade observations or reasonably compact reproducible derived rows, no selective deletion. Keep decision table before ranking.

## 6. STAGE C — evidence and comparative inference, NO promotion

Required metrics *for every applicable candidate and benchmark*, LONG/SHORT/WAIT separately:
- decisions/trades, coverage, action frequency, fill rate, holding-time distribution, exposure days and concentration;
- gross/net PnL in R (when comparable), median/mean net R, realized trading cost split maker/taker/slippage/funding, net hit rate, TP1/SL order and stop-before-target, MFE/MAE, drawdown/tail loss;
- 2–6 / 6–12 / 12–24h horizon comparison **only where registered**; per-symbol/per-regime and ≥3 chronological partition support without subgroup promotion;
- fee/funding/slippage stress, liquidity/market-timing sensitivity, parameter-neighborhood sanity (diagnostic only, **not** new candidate selection), stratified concentration, stationary/block bootstrap or other dependence-adjusted intervals, selection-bias note (12 candidate search).
- For grid only: paired spread profit, inventory/MTM PnL, capital utilization, boundary breach, underwater time, grid churn, maker fill realism. Never compare grid "paired profit" alone against directional `net_R`.

**Screening decision:** choose at most **2** exploratory candidates from frozen ranking rule, and explicitly give strongest reasons they could fail. A positive historic net R on explored data cannot be named `ALPHA_PASS`. If all fail realistic transaction costs, report `G2_R1_EXPLORATORY_NO_GO`, not endless repair/tuning. If inference weak, report `DIAGNOSTIC_ONLY`. Publish suggested *independent future* experiment with exact prospective null, data length/sample support, precommitted thresholds and exposure safeguards, to be Controller-authorized separately.

No strategy parameter promotion to `TACTICAL_POLICY_R2_B1` or executable G1 workflow in this task. No actual signals sent to account, phone/Slack/Feishu as actionable live advice.

## 7. L0/L1 test budget and quality gates

- L0 during coding: `git diff --check`, changed-file `ruff`, `compileall`, fast hermetic unit and source-contract tests; no repeated full pytest/H40/H41.
- L1 once at terminal: `tests/test_strategy_research_*.py` + only applicable MarketWatch evidence/causality tests if new sidecar imports that behavior; deterministic identical-input hashes and no-protected-access sentinel; targeted mypy/ruff. Let existing CI planner safely fall back to FULL for new unmapped modules if necessary, but do **not** modify shared CI planner from G2 (G1 parallelism). If full CI runs due fail-closed unknown path, report duration; do not force unsafe skips. Controller can separately authorize CI mapping enhancement after G2 review.
- Separate **test-only synthetic** fixtures from true historic outcome metrics. Do not claim full external alpha proof from unit tests; some repository fixtures can be previously exposed.
- No stage may claim PASS if planned tests are skipped, source absent or temporal ordering unknown. Record counts and reasons precisely.

## 8. Mandatory proactive push and self-contained evidence

Publish under `evidence/v0.6/b_line/g2_discovery_r1/**`:
1. `PRE_REGISTRATION_RECEIPT.json` and exact prereg artifact (frozen/pushed first);
2. `SOURCE_AND_EXPOSURE_LEDGER.json`: dataset origin/digests, event time, prior evidence/holdout classification, usage;
3. `CANDIDATE_REGISTRY.json`: 0–12 candidates, frozen configs/horizons, trial counts and no after-the-fact selection;
4. `REPLAY_AND_PIT_VALIDATION.json`: invariants, counterfactual attack tests, cost/fill/stop timing checks;
5. `EXPLORATORY_RESULT_TABLE.json`: per-candidate **all** output, support and interval, no survivor-only reporting;
6. `G2_R1_RESEARCH_REPORT.md`: economic viability, competing explanations, key failures, recommendation and what **fresh** future validation is needed;
7. `TEST_RECEIPT.json`: code SHA, env, commands, pass/fail/skip, data manifest hashes, timings, protected reads/writes=0;
8. `ORIGINAL_WORKTREE_PRESERVATION.json`: original checkout branch/HEAD and dirty/untracked **counts only** pre/post, G1 and other worktrees untouched.

Push **method-freeze commit first** before outcome access, then bounded implementation commit and independent evidence-only follow-up if necessary (do not create circular source-SHA references). Once L1 checks succeed: `git add -- <EXPLICIT_ALLOWED_PATHS>`, staged diff review, proactively `git commit`, `git push -u <VERIFIED_REMOTE> HEAD:refs/heads/feature/v06-bline-g2-strategy-discovery-r1` without force, query remote HEAD SHA/parent/changed files and report `REMOTE_PUSH_VERIFIED=true`. Do not wait for user to request push. Failed Git auth/permission/network => `BLOCKED_NOT_PUSHED`.

**Terminal output:**
```yaml
task_id: V06_B_LINE_G2_PROSPECTIVE_STRATEGY_DISCOVERY_R1
executor_profile: SOL_HIGH | GEMINI | LUNA_MECHANICAL
controller_dispatch_sha: 0cc3d6e14d5c4e301c987b9e760fabb393e8141a
code_start_sha: d6500140f3141d179181f2360ad815b5bfe9c954
original_entry_checkout: /root/workspace/project/rc2-tactical-successor
new_worktree: /root/workspace/project/rc2-tactical-successor-v06-g2-r1
branch: feature/v06-bline-g2-strategy-discovery-r1
pre_registration_sha: <FIRST_PUSHED_COMMIT_SHA>
implementation_sha: <EXACT_CODE_SHA_OR_NONE>
evidence_final_sha: <EXACT_FINAL_REMOTE_SHA>
remote_push_verified: true | false
universe: BTCUSDT, ETHUSDT, SOLUSDT (nonprotected historical DEVELOPMENT)
candidates_registered: 0..12
candidates_evaluated: 0..12
method_integrity: PASS | BLOCKED
observed_test_results: pass/fail/skip/duration
exploratory_decision: SHORTLIST_READY | NO_GO | DIAGNOSTIC_ONLY | BLOCKED
fresh_independent_policy_quality: NONE
protected_reads: 0
exchange_writes: 0
testnet_authority: NOT_AUTHORIZED
real_funds_write_authority: NONE
g1_shared_source_changes: ZERO
next_controller_action: L2_EVIDENCE_REVIEW_AND_PROSPECTIVE_R2_DECISION
```
If the role was Luna and inference is not independently assessed, return `NEEDS_SOL_OR_CONTROLLER_SCIENTIFIC_REVIEW`, never strategy-quality PASS.
