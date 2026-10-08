# v0.6 B-line G2 R3 — Cost-Aware Strategy Discovery Campaign DESIGN R1 (Sol High)

## Immutable task identity

- `TASK_ID=V06_B_LINE_G2_R3_COST_AWARE_CAMPAIGN_DESIGN_R1`.
- `CONTROLLER_DISPATCH_SHA=05ad881995cb5a8b93e086c79edd4bbc7c051bd4` — [Controller scope/identity authority](https://github.com/EXASHXE/btc-quant-agent-public/blob/05ad881995cb5a8b93e086c79edd4bbc7c051bd4/evidence/v0.6/controller/B_LINE_G2_R3_COST_AWARE_SCIENTIFIC_DESIGN_DISPATCH.json).
- Repository `EXASHXE/btc-quant-agent-public`; frozen starting code `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32` (`v0.6` integrated G1 and G3 scoped ops).
- Source G2 R2 research final `2e922f486cf5b3f6cb7fa3aa7823cd096f24c17e`; **read-only** `configs/strategy_research/G2_R2_PERP_PREREGISTRATION.json` historical method blob, first prereg `66aad50500bf6e860e76bf3ae8c0ef70799d5f47`; implementation `d38f7b45983cd74dc9e28439ebfb2fa60971122a`.
- Use feature branch `feature/v06-bline-g2-r3-cost-aware-method-design`, unique local worktree `/root/workspace/project/quant-v0.6/g2-r3-cost-aware-method-design`. Preserve original `/root/workspace/project/rc2-tactical-successor`, G1, G2 R1, G2 R2, G3 and controller-review worktrees. Do not reset/clean/stash/rebase/move/collide with any existing tasks.

**Executor**: Sol High preferred for economics, scientific-method design and adversarial challenge. Gemini can draft a bounded technical implementation design; Luna mechanical schema/provenance checks only. If tool access lacks Git or local worktrees, document BLOCKED rather than falsely claiming push. Executor must autonomously commit, **push and independently verify remote SHA**. No code, experiment, market-price replay or protected data access authorized in this DESIGN task.

### Source documents (read only)
- [G2 R2 results & negative strategies](https://github.com/EXASHXE/btc-quant-agent-public/blob/2e922f486cf5b3f6cb7fa3aa7823cd096f24c17e/evidence/v0.6/b_line/g2_reconstruction_r2/G2_R2_RESEARCH_REPORT.md)
- [R2 source and exposure ledger](https://github.com/EXASHXE/btc-quant-agent-public/blob/2e922f486cf5b3f6cb7fa3aa7823cd096f24c17e/evidence/v0.6/b_line/g2_reconstruction_r2/SOURCE_AND_EXPOSURE_LEDGER.json)
- [R2 frozen method preregistration](https://github.com/EXASHXE/btc-quant-agent-public/blob/2e922f486cf5b3f6cb7fa3aa7823cd096f24c17e/configs/strategy_research/G2_R2_PERP_PREREGISTRATION.json)
- [R2 complete candidate registry](https://github.com/EXASHXE/btc-quant-agent-public/blob/2e922f486cf5b3f6cb7fa3aa7823cd096f24c17e/evidence/v0.6/b_line/g2_reconstruction_r2/CANDIDATE_REGISTRY.json)
- [R2 test/cost evidence](https://github.com/EXASHXE/btc-quant-agent-public/blob/2e922f486cf5b3f6cb7fa3aa7823cd096f24c17e/evidence/v0.6/b_line/g2_reconstruction_r2/EXECUTION_SEMANTICS_AND_PIT_REPORT.json)
- [Controller G2 R2 adjudication](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/reviews/v0.6/b_line/V06_G2_R2_CONTROLLER_L2_DIAGNOSTIC_REVIEW.md)
- [G2 R2 prior contract](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/docs/project/V0.6_G2_R2_PERP_HISTORICAL_RECONSTRUCTION_CONTRACT.md)

## Context: do NOT rescue a historically losing policy

G2 R2 ran **one** independent deterministic computational campaign, not three. Eight frozen BTC/ETH/SOL Binance USDT-M perpetual **directional** formulas (breakout/pullback × LONG/SHORT × 4h/12h) were evaluated on 2026-05/06/07 previously exposed development months, Apr warmup. **Every candidate has negative average base net R and stressed net R**. Closest to zero was `TREND_PULLBACK_SHORT_12H` at `-0.129R` base and `-0.349R` stress with 77 trades total / 25,32,20 per partition, **not a winner**, no shortlist. R2 used assumed 60s archival-event availability, no live receipt-proof. Conservatively proxied adverse funding (timestamps did not satisfy exact frozen cadence), 22bps taker/spread/slippage base round trip, 44bps stressed. No GRID was evaluated because `NO_GRID` frozen and four candidate slots relinquished. All were limited to developed/researched historical samples and sparse dependent blocks; not scientific alpha PASS nor universal theory that all strategies lose. Historical results are **exposed**, even if the same archive is downloaded again.

The problem is **no demonstrated gross edge able to survive friction**. It is *not* solved by choosing the best asset/horizon after viewing R2, lowering fees without live execution evidence, reusing RC2 protected holdout, or requiring user to wait an arbitrary 360 days before any alternative hypothesis is designed. The proposed R2 executor `360`-day forward is a possible future confirmatory gate, **not an approved mandate**: no candidate currently deserves such a costly validation.

## Stage A — diagnose negative economics at method level, no new outcome viewing

Read existing R2 *published aggregate* report/evidence only to construct a high-level diagnostic ledger of failure mechanisms, without inspecting newly downloaded raw market bodies or protected history. Explain:

1. Why R2 scored `-0.129R` even on highest gross `+0.091R`, including 22bps round-trip friction vs 44bps stress, stop-first churn, adverse funding proxy, variable ATR denominators and exposure assumptions. Decompose gross edge vs transaction cost in basis points **and** R, identifying which units are comparable and why an R average is not a fee-rate.
2. Structural exposure failure vs selection/prediction failure: compare gross average, matched-control incremental edge, decision density, stop/target economics, average hold, and tail risk. **Do not optimise / rerank individual asset/month subgroup based on R2 outcomes.** Any descriptive regressions on R2 are already data-exposed development, never blind validation.
3. Report missing data needed to judge any grid: L2 book/queue/fills/adverse selection, unpaired inventory MTM and boundary-stop realism. **Don't include grid as profit candidate if source cannot support credible maker fills.** Consider a deliberate PAUSE control (no trade) as first-class outcome.
4. Real funding: verify the **specification-level** distinction between funding calculation/published/settlement timestamps, UTC schedule and mark price, and the difference between an archive rate and cashflow proof. Do not inspect RC2 restricted symbols or hidden outcomes. If correct public source semantics cannot be asserted, declare proxy-only and propose a *separate data-contract experiment* rather than claiming R2 PnL correction.

## Stage B — propose a materially different, budget-capped prospective discovery campaign

A new strategy candidate is a **new hypothesis**, not a slight relabel of an old R2 winner. Propose **at most 12 total** concrete interpretable variants; recommend spending no more than **8** until feasibility passes. Candidate families should address friction and false positives:

- *Regime/volatility-qualified trend continuation*: e.g., directional participation after completed 4h structural trend plus 1h confirmation, risk-to-friction feasibility and measured no-trade gate. No future label/regime lookahead.
- *Post-breakout retest and selective continuation*: trigger confirmation after breakout-retest closure, rather than chasing a first spike; conservative next-minute entry and no-fill controls.
- *Cross-asset/regime relative strength or asymmetry*: only if features are point-in-time available and overlap/cross-asset common shocks are modelled; no retrospective symbol selection.
- *Range/grid* **optional** separate non-order-book directional range-proxy that is explicitly **NOT an executable maker grid**, or an L2-source/queue-feasibility audit before any true grid economics. Do not mix paired-grid profit with directional net R.

Need choose 2–6h, 6–12h and 12–24h horizons **only when each hypothesis supports it**; if 24h horizon conflicts with short-turnover objective, quantify its economic trade-off, do not add duration merely to bury transaction cost. Alternatives such as fewer but higher-quality entries and legitimate HOLD/WAIT are preferred over rapid churn.

Define outcome-**agnostic** model classes: simple interpretable rules/small calibrated classifier/two-stage opportunity+direction **only** if candidate/training/search budget can be frozen; no AutoML, wide feature expansion, black-box hyperparameter sweeping or LLM hindsight labelling.

Pre-specified economics must include tick/lot, maker vs taker assumptions with verified fee tier, spread/slippage, funding/mark-price, minimum entry opportunity in bps vs plausible expected total costs, net expectancy and tail/drawdown; **stress before trade** not after. No 10–20x leverage amplification of apparent alpha. Only public unauthenticated Binance futures read-only, no account API, no live signed client or user credentials.

## Stage C — distinguish 3 levels of data/decision authority

Produce a clear table:
- `HISTORICAL_EXPOSED_DEVELOPMENT` (includes ALL 2026-05/06/07 BTC/ETH/SOL in R2): can be used to **design**, calibrate or screen, with model-selection penalty and explicit exposure ledger; never fresh independent holdout.
- `NEW_FROZEN_HISTORICAL_EXPLORATION` (other previously uninspected but public windows, if any): may improve directional development discrimination **only with prospective freeze and disclosure of indirect exposure**. An old historical window is not necessarily an unexposed future release cohort simply because the executor hasn't opened it. Treat as nonprotected development, not independently release-authoritative.
- `CONTEMPORANEOUS_RECEIPT_PROVEN_FORWARD` or a separately Controller-authorized unexposed split: required for stronger quality claims. Define short **information milestones** (e.g. 14/30/60 day coverage review) rather than arbitrarily promising 360 days or treating a fortnight as sufficient statistical power. A later sample sufficiency calculation should use actual signal frequency and dependence, and may require longer.

**Before another empirical campaign**, independently register fixed candidates/priority/rules/horizons/data windows, cost and source availability, sample and early stopping, multiplicity, support, and hard failure semantics; **push freeze first**. This design task **does NOT authorize those market outcome reads** nor count as the later prereg freeze; a new Controller dispatch is required for execution.

## Stage D — design artifact quality and acceptance

Write only under:
`docs/strategy_research/g2_r3/**`,
`evidence/v0.6/b_line/g2_r3_design/**`.

Required artifacts:
- `docs/strategy_research/g2_r3/METHOD_DESIGN.md`: hypothesis families/variants/controls, disjoint experiment hierarchy, PIT/event availability, costs/fill/stress, selection/uncertainty, data-tier distinction, trade and counterfactual accounting.
- `docs/strategy_research/g2_r3/SOURCE_QUALITY_AND_COST_FEASIBILITY.md`: evidence-provenance audit, realistic execution assumptions, funding/tick/fee verification plan, strategies that lack credible book/queue source excluded.
- `evidence/v0.6/b_line/g2_r3_design/CANDIDATE_REGISTER_PROPOSAL.json`: ≤12 designs, fixed number of variants and prereg freeze fields, without fabricated profitability.
- `docs/strategy_research/g2_r3/R3_EXECUTION_GATE_PLAN.md`: 1) narrow source/method audit, 2) frozen bounded development experiment, 3) independent evaluation boundary if justified, cost/time data collection budgets, distinct G1/G3/G4 dependencies.
- `evidence/v0.6/b_line/g2_r3_design/DESIGN_RECEIPT.json`: identity, source ref, changed paths, proof no new outcome reads, no protected reads, no account/provider/API writes, exact tests/validation and resulting remote SHA where possible.

Design scenarios and gate requirements must be **decidable** and falsifiable, not marketing. Require aggressive invalidation: if none of ≤12 pass plausible friction **in development**, retire the family, return DEVELOPMENT_NO_GO and reconsider source premise, not tweak live strategy parameters mid-campaign. Do not target only positive results. No production Tactical mutation or alpha claim. G2 R2 negatives are admissible context but not a valid search space for ex-post rescues.

## Local Git and proactive publication

Read-only verify `v0.6` branch current exact `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32` and docs dispatch identity, actual remote `EXASHXE/btc-quant-agent-public`, existing sibling worktrees and target branch/path free; if drift/collision STOP. Using trusted ENTRY original repository, create **new** worktree from pinned code:
```bash
ENTRY=/root/workspace/project/rc2-tactical-successor
WT=/root/workspace/project/quant-v0.6/g2-r3-cost-aware-method-design
BASE=e0ff8c3473de4bfa3e66fe7928d42992a4d38a32
git -C "$ENTRY" worktree add --no-track -b feature/v06-bline-g2-r3-cost-aware-method-design "$WT" "$BASE"
cd "$WT"
test "$(git rev-parse HEAD)" = "$BASE"
```
Only after preflight, and never move/reset/clean/stash original or other tasks. Read R2 aggregate reports by explicitly named Git file, **no recursive scan into protected paths or new market body download**. No Python code or tests or `.github` edits in this task. JSON format/diff checking only. Minimize interaction and avoid more than one method design review iteration unless actual blocking contradiction found.

At completion autonomously `git add -- <ALLOWED_PATHS>`; verify staged diff, `git diff --check`, JSON syntax, no forbidden path changes; `git commit` and **`git push`** to the new `feature/v06-bline-g2-r3-cost-aware-method-design` branch, then query remote SHA, parent, changed files. Publish `REMOTE_PUSH_VERIFIED=true` only after independent remote success. Stop if cannot push; do not leave claims of remotely accepted or executed R3.

**Terminal:** `G2_R3_DESIGN_READY_FOR_CONTROLLER_SCIENTIFIC_REVIEW` / `G2_R3_DESIGN_METHOD_REPAIR_REQUIRED` / `BLOCKED_IDENTITY_OR_WORKTREE` / `BLOCKED_NOT_PUSHED`.

Return `CONTROLLER_DISPATCH_SHA=05ad881995cb5a8b93e086c79edd4bbc7c051bd4`, exact code/source SHAs, branch/parent/final remote SHA, number of candidates, source/method and cost design decisions, past-failure analysis, sample budget, no empirical outcomes, `REAL_FUNDS_WRITE_AUTHORITY=NONE`, `TESTNET=NOT_AUTHORIZED`, and next separate Controller method-approval gate. **Do not start a 360-day Forward.**
