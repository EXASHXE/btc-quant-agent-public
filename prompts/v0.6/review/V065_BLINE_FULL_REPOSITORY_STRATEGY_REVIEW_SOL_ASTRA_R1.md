# V065-R3 — Independent B-line Full-Repository Strategy and Test Roadmap Review

**Executor:** ONE local Codex **Sol Max** OR **Astra High** high-reasoning session. **Mode:** read-only domain-wide engineering/science diagnosis; not implementation, trading, autonomous experimentation or branch pruning.

## Frozen starting point and workspace contract

Repository: `EXASHXE/btc-quant-agent-public`.
Observed 2026-10-17 default/code HEAD: `v0.6.5@941f24af8f1e12c1f314e2d970e7af8f97293b21`.
Engineering docs: `docs/engineering@84955be4cd947cf6a92a9e09c036daf4b948f3fb`, separate docs-only orphan. Research archive: `legacy/research-archive@0176cdde836a660420e5e4b5693591cb8108a4f6`.
Owner-requested local working directory: `~/workspace/project/quant-0.6.5` (the previous remote-root agent did not find this path: a different actual user HOME/host may exist).

**FIRST** confirm user/host and code identity:
`pwd`, `echo "$HOME"`, `realpath ~/workspace/project/quant-0.6.5`, `git -C ... status -sb`, `git -C ... rev-parse HEAD`, `git -C ... remote -v`, and `git worktree list`. Never assume that directory name proves branch/code identity. If absent on the intended host, request or prepare a NEW empty isolated clone of the public `v0.6.5` at the owner-specified path (only if appropriate), otherwise return `WORKSPACE_NOT_FOUND`. Never switch/reset/clean an existing dirty repo or substitute `Quant-agent/`, `history/`, `Quant-agent-sanitized/` or `Quant-agent/data/`. Record actual SHA and any difference from frozen baseline before analysis.

Read `README.md`, `AGENTS.md` if present, `docs/project/V0.6_PROJECT_STATUS_AND_ROADMAP.md`, `docs/project/V0.6_B_LINE_STRATEGY_VALIDATION_REGISTER.md`, `docs/project/V065_RESEARCH_FIRST_OPERATING_CONTRACT_R2.md`, `docs/roles/`, relevant `src/`, `tests/`, `configs/`, `scripts/` and frozen `prompts/v0.6/b_line/`, relevant exact-SHA negative audits and D2/E2/C2 evidence. Engineering-only context is on `docs/engineering`; do not merge branches or read sensitive controlled histories merely because they exist.

## Owner objective

Discover **genuinely incremental, after-cost executable BTCUSDT perpetual 4–24h strategy opportunity** and design the quickest reliable non-leaking validation workflow for personal, noncommercial, nonproduction research. ETH may be a context/control if justified; BTC is primary. The result may properly be `NO_VIABLE_HYPOTHESIS_NOW`.

Do not offer cosmetic architecture scorecards or generic trading indicators. Judge priorities by measurable scientific information gain, lawful causal data availability, realistic execution costs, and probability of honest falsification.

## Required six-part diagnosis

**A. Architecture and real research path.** Map source → native ingest/QC → original publish/receiver-first-known PIT → features/labels → signal → executable maker/taker quote & fill/ACK → ledger/account/no-action → backtest/validation. Identify missing or stubbed pieces, broken invariants, and critical incorrect assumptions at exact `path:line@SHA`. Distinguish *built*, *tested*, *scientifically admitted* and *merely proposed*.

**B. Failed strategy and exposed-data lineage.** Reconcile frozen tests and negative research across v0.3.12 taker flow spread (H32 INCONCLUSIVE/H33–H34 FALSIFIED), R3/Goal/H18, R8 novelty, T6 PA-B CHALLENGE_FAIL and R11 source audit. Create mechanism-level equivalence clusters, old controls X, past exposed windows, actual failure classification, and the **new external witness** that alone could warrant a genuinely fresh trial. No reparameterized resurrections, no reading final/protected holdout data.

**C. Binance and OKX source suitability.** Review author-delivered D2 `803a4173717ace9c03ff97051b7696210e183bef`, E2 `7f8c6acadead47dccdeba80b2ae27c2497ee8cdf`, C2 `9dbb0ce7d266c0d6731775a7a53170bf34400520`, consequential R11-Q1 negative audit and R11-Q2 limited pilot authorization. Product identities (BTC spot / USDT-M / COIN-M), trades, candles, Mark, funding announcement/effective clocks, OI original snapshot clocks, native units, archive vs API rights, source manifests and missingness. Split `OFFLINE_DEV_USE_WITH_LIMITS` from `SOURCE_PIT_ADMITTED`. Do NOT assume exchange-reported historical timestamps equal receiver knowledge. No bulk download or new paid data.

**D. Economic + statistical testability.** Check maker/taker fees, spread, slippage, impact, ACK/partial fills/queue, funding, mark/liquidation and margin, position sizing, account/no-action utility, fail-safe state isolation. Assess leakage, walk-forward splits, hidden OOS, multiple comparisons, effective sample size, regime fragility and pre-registration. Do not invent positive PnL/Sharpe, sample numbers or known-at clocks; calculate only grounded bounds with traceable inputs or state UNKNOWN.

**E. New mechanism shortlist.** Recommend **at most 2** fundamentally differentiated BTC 4–24h hypothesis families, *only if* dataset and older-failure comparison make them credible. Specify unique observable Z beyond X, why after-cost edge could exist, first-known clock, market execution, data qualification needed, positive/negative control, sharp falsifier, sample/power/multiplicity and pre-registered out-of-sample evaluation. If none, choose `NO_NEW_SOURCE_COMPATIBLE_HYPOTHESIS` and the smallest source/data or contract proof that changes that decision.

**F. Next research direction.** Deliver up to **3 prioritized milestones for the next 1–2 weeks** (not a promised schedule). Show gating DAG with at most **2 truly independent READY parallel tasks** and one conditional successor, execution owner (0 Controller, 1 Auditor, 2-R Scientist, 2-C Challenger, 2-E narrow docs, local Codex/Gemini for engineering), exact acceptance/STOP conditions and concrete expected artifacts. Say what work to STOP doing: unbounded ref cleanup, speculative CI/infra, broad strategy sweeps, unqualified data collection or re-optimizing prior failures.

## Boundaries and result quality

- READ-ONLY repository. Do not commit/push/edit/delete any Git refs, PRs, CI, configs, science gates or source code. If a file is needed, write only to reviewer-owned `~/workspace/project-review-output/v065-r3/` (create outside repo) and return location.
- Do not read/copy protected/private market data, `Quant-agent/data/**`, `Quant-agent-sanitized/**`, `history/**`, H39/H40/H41 protected outcomes, Final Holdout, secrets or account identifiers. No live exchange/private APIs, downloads, trades, orders, funds, testnet or production.
- Do not execute broad backtests, optimize hyperparameters, train models or run trials on previously exposed/protected OOS. Small nondestructive code-path checks only if essential to a concrete claim and confined to isolated workspace.
- Always label consequential findings `VERIFIED@SHA:path:line`, `REPORTED_ONLY`, `INFERENCE` or `UNKNOWN`. Distinguish evidence from review judgments. Passing CI and author-delivered data ≠ scientific Alpha. Avoid an unbounded research report without a decision.
- Existing 49 remote branches: 3 permanent, 42 A-line/control HOLD, 4 PR #3/#5 dependencies (KEEP). They are maintenance governance and NOT authorization to inspect protected A-line studies or delete refs.
- Current gates remain `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.

## Final outputs (Chinese)

1. `VERDICT`: SCIENCE_PATH_CLEAR / CONDITIONAL_RESEARCH_PATH / SOURCE_OR_ECONOMIC_BLOCKED with strongest reason.
2. 5–10 high-impact, **evidence-linked** pipeline and science defects ranked by lost information/edge.
3. Deduplicated historical mechanism/failed hypothesis map and status.
4. 0–2 admissible new hypothesis cards (or explicit NONE), each with economic and scientific disconfirmation.
5. Maximum three-step, 1–2-week DAG (≤2 parallel READY), source/workspace ownership, acceptance metric and terminal STOP alternative.
6. One owner decision card: exactly which permission/source/sample/data witness changes next action, what is already executable in offline DEV, and what remains prohibited.

Write a concise `REVIEW.md` (optional `EVIDENCE_INDEX.json`) outside repo; return exact reviewed commit, report path and `NO_REPO_MUTATION`. No self-certified scientific acceptance and no generic “waiting” response.
