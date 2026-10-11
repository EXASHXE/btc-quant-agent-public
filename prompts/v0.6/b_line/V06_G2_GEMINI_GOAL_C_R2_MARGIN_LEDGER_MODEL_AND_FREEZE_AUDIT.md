# GEMINI GOAL C R2 — Independent margin, synthetic liquidation and forensic audit truth repair

MODE: Gemini Goal sustained autonomous work. Produce an auditable contradiction resolution, not an executive-summary rewrite. Prove or falsify each primary claim, deliver tests + machine receipts + science gate. No leverage strategy optimization or TESTNET/LIVE.
CONTROLLER_DISPATCH_SHA: 1172d3a91324c1a7379bc9e5c24ef601076547c2
AUTHORITY_URL: https://github.com/EXASHXE/btc-quant-agent-public/blob/1172d3a91324c1a7379bc9e5c24ef601076547c2/reviews/v0.6/b_line/V06_G2_GEMINI_ABC_GOAL_R2_CONTROLLER_EVIDENCE_REPAIR_AUTHORITY.md
REPOSITORY: EXASHXE/btc-quant-agent-public
EXACT_START_SHA: f381dd73a8c583e2a28dcab2e354b019b1d946fa
BRANCH: feature/v06-bline-gemini-goal-c-risk-assurance-r2
WORKTREE: /root/workspace/project/quant-v0.6/gemini-goal-c-risk-assurance-r2
SCRATCH: /tmp/btc-gemini-goal-c-risk-assurance-r2
OWN_PREFIX: g2_goal_c_risk_assurance_r2
C_R1_FROZEN_SHA: 8db2e3ff36011c6a65458f8cf4c2ba5e90d5fee2
C_R1_MID_REPAIR_SHA: 4c0bac051767f788e6de173f6563a7b47af2ac69
C_R1_FINAL_SHA: f381dd73a8c583e2a28dcab2e354b019b1d946fa
ORIGINAL_EXIT_R1_FINAL_SHA: 55ac4c631c69f6edbd275462ad23e4486b9782ed

## Scientific mission

Independent Goal C R1 reported 48 Decimal forensic deep episodes, 890 ledger-order trades, 48/48 synthetic fixtures, 0 funding/cash discrepancies. Its final GitHub Actions CI 38162845456 SUCCESS was docs/evidence-only: tests, Ruff and type-check skipped. Original task required max two commits but it made THREE: 8db2e3ff freeze -> 4c0bac0 source URL/ZIP-name attestation fix + frozen-contract code edit -> f381dd7 evidence. Report and machine risk outputs conflict and MUST be reconciled before any historical execution-model or leverage-risk readiness claim.

Hard-source observed contradictions:
- R1 original E0 executed W1 n34, W2 n55 in both costs, but C R1 SYNTHETIC_MARGIN_AND_LEVERAGE_STRESS.json cell_exposure_summaries records peak Mark notional/equity 0 for all four E0 cells. H1 etc show ratios ~0.93–0.95. This cannot be used as E0 0 exposure proof; likely bad curve-link or default.
- C human report describes initial 1R stop distance 7.5–11.6% of BTC spot entry, but C primary machine adverse_mae_and_stop_distance_tails shows max historical W1=3.612%, W2=3.5591%. It states 3.61% stop exceeds 15x ~6.67% initial margin buffer, mathematically false. Differentiate a hypothetical 7.5% scenario and actual frozen stop distribution, liquidation price and maintenance margin including fee/funding.
- C human report says 7/6 bankruptcy deficits (impossible denominator); C machine parametric envelope says scenario_count=32, naive 10x/15x before-stop liq count=5 and gap bankruptcy deficit count=7. Recompute counts BY ACTUAL row booleans and fields, not narrative; distinguish cross-stop liquidation, gap deficit of isolated collateral vs negative total account equity, and threshold while Mark is at worst high/low versus settled close.
- Original machine ledger may be self-consistent but 1m OHLC cannot prove exchange L2 queue or actual stop fill; historical 10x/15x maintenance brackets UNKNOWN. Claim synthetic risk-capped setup zero liquidation means only under its explicit toy assumptions; never trading safety guarantee.

GOAL: build independent finite reproducible truth matrix across (1) C freeze provenance, (2) all E0/H1/H2/E1/E2 1x account exposure, (3) 32 synthetic 1x/5x/10x/15x margin scenarios, (4) actual 2021–23 stop distance and realized gap tails, (5) event-book fee/funding/ACK consistency, (6) execution unknown and TESTNET prerequisites. Any material discrepancy yields FAIL_CLOSED and exact witness; no optimistic patch to original reports.

## C0 — immutability/attack-surface admission

- Verify own branch points EXACT_START_SHA and old C 3-commit chain and exact parent each. Compare SHA/changed files of first freeze and middle repair: list code symbols/contracts changed, prove source_url/zip_name repair cannot modify audited economic outcomes or invariant selection; if unprovable downgrade C R1 pass to POST_FREEZE_REPAIR_NOT_PREACCEPTED.
- Fetch old C report, C result, source-vs-algo claim matrix, 32 synthetic case rows, 20 account order ledgers and original R1 Mark curves as read-only. Verify manifest SHA and row counts; no reinterpretation from human report as machine authority.
- Public authenticated Binance BTCUSDT USD-M 2021–23 only, source bytes read-only and only if hashes match. For unknown exact Binance historical leverage brackets, DO NOT invent maintenance margin, liquidation parameter or VIP fee rules. Forbidden access, even stat/list, to /root/workspace/project/Quant-agent/data or Quant-agent-sanitized, protected 2024–26/holdout/H39/H40/H41/Forward, other agent worktrees, private account data, A-line, TESTNET, LIVE or live orders.

## C1 — FREEZE methodological contract and adversarial tests, then remote push

Define an independent pure Decimal forensic analyzer and formal scenario model:
- Account equity E; posted isolated initial margin M0=N/L + discretionary buffer (explicit), maintenance MMR(N,t), liquidation fee buffer, accumulated signed Funding, realized fees, changing size q. Distinguish isolated collateral vs overall free account equity; liquidation occurs if mark-equity AFTER fees/funding <= maintenance; a proposed stop event triggers before liquidation only if path and event clocks permit, else liquidation-first; no retroactive fills. Model interval uncertainty for 1m intrabar unknown sequencing conservatively.
- Define gap-bankruptcy as isolated equity below zero; distinguish before/after liquidation and bankruptcy deficit convention. Negative total account wealth is a separate observable. No fake historical 10x/15x returns.
- All synthetic scenario denominators derived from actual array of scenarios filtered by leverage, size mode, MMR, side and TP1 status. If X of Y, Y must be exact filtered count. Zero denominator -> UNKNOWN, never X/Y greater than 1.
- For original 1x E0 order ledger, define per-minute q open and notional/equity ratio. If committed E0 curve lacks a field, reconstruct via read-only order event clocks and completed Mark, initial 1000 cash and explicit fee/funding; do not default 0 or confuse 0 in a missing source with proof of no position. Require tolerance <=1e-7 for cash/qty as feasible; expose mismatch.
- Define synthetic fixture matrix >=50 scenarios including 1x/5x/10x/15x, 3 MMR hypotheses, LONG/SHORT, large adverse gap, post-TP1 partial quantity, fee/funding before/after, 1m mark close/high/low, cancel-replace ACK, stop-vs-liquidation clock, negative isolated collateral but positive total equity, account deficit/solvency and unknown exchange tiers.
- Implement independent NEW prefix only (do not call existing C R1 risk_envelope.py as sole oracle), include >=50 meaningful deterministic synthetic tests, plus base proof of 20+ real R1 ledger event cases from previous source for quantity, fee and as-of Mark.
- Freeze design and source hashes, formulas, every input case and comparison logic. Commit first method/tests, non-force PUSH, independently verify remote HEAD,parent and changed-file namespace BEFORE any newly computed reconciliation output.

## C2 — finite reconciliation pass, not a new trading backtest

Using only committed 2021–23 public/R1 data and C R1 frozen 32 synthetic scenario fields:
1. Validate all 32 rows' declared leverage, MMR, posted margin, mark loss, size, TP1 q, equity, fees, funding and gap deficit through independent Decimal formulas. Present exact observed vs recomputed, row ID and earliest violating invariant. Count grouped denominators for naive 10x/15x, all 1x/5x, capped 10x/15x, gap deficit and liquidation-first. If old machine summary cannot be reproduced, mark C R1 risk findings INVALID and give corrected case table.
2. Reconstruct original **20** Exit R1 account cells' per-minute maximum Notional/MarkEquity (especially four E0), 0-exceedance claim, 5% reserve gate, pre/post ACK cash. Preserve original full-account E0 R3.1 digests; no changes to frozen 2021–23 trade outcomes. For each E0 zero-exposure item produce earliest positive q trade+minute+Mark witness or prove data absent; do not convert a partial view to full verification.
3. Separate **real historical** 1R stop distance distribution maximum W1 3.612% and W2 3.5591% from a SYNTHETIC 7.5% stop scenario, and compute inequalities for 10x 10% initial vs 15x 6.667% initial buffers under explicitly hypothetical MMR/fee/funding. At 15x a 3.61% adverse movement alone is less than the raw margin ratio; show conditions where fees/MMR/shock nevertheless force liquidation. In synthetic 7.5% stop scenario, liquidation can precede stop at particular parameters. No out-of-sample observed leveraged loss inference.
4. Re-audit C R1 48 deep case claims and 890 ledger-wide verification at least 20 independently chosen real cases (both directions, funding signs, all year/costs and variants where present) with source receipts; independent lookahead and minimum volume coverage from synthetic only when empirical sample missing.
5. Precisely reconcile C 3-commit freeze+attestation repair with original at-most-two rule; static diff + witness + terminal authority note. Report final C docs-only CI skipped tests truthfully. Determine whether C ledger mathematical findings are still bounded usable even if risk report invalid; do not claim blanket C PASS.
6. Prepare explicit future TESTNET readiness prerequisites *design-only*: verified current exchange risk bracket, leverage/position mode, reduceOnly/stop orders, clientOrderId idempotency, ACK latency, orderbook fill/limit queue and funding exact settlement logging. No Testnet exercise, deployment or real account connection.

## C3 — publish terminal with honest contradiction disposition

- Deliver audited 32-row machine scenario truth table, 20-cell E0/H1/... exposure report, stop-distance and liquidation-inequality proof, freeze lineage proof, independent >=50 synthetic and >=20 real event receipt, claim-by-claim ACCEPTED/INVALID/UNKNOWN matrix, corrected narrative as addendum only. Explicit status for finance/solvency claims separated from price-edge scientific validation.
- Ruff, compile, strict JSON, pytest, SHA manifests and direct underlying arithmetic consistency. Commit2 report/evidence ONLY; auto nonforce push, exact parent and changed paths, verify GitHub Actions mode and skipped suites, report all.
- Terminals: C_R2_MARGIN_RISK_EVIDENCE_RECONCILED_SYNTHETIC_ONLY / C_R2_MATERIAL_MARGIN_OR_EXPOSURE_DEFECT_FAIL_CLOSED / C_R2_INCONCLUSIVE_SOURCE_OR_FREEZE_REPAIR. No strategy promotion, no imported 10x/15x empirical P&L or permission to try live.

Only permitted writes: scripts/strategy_research/g2_goal_c_risk_assurance_r2/**, tests/test_v06_g2_goal_c_risk_assurance_r2_*.py, docs/strategy_research/g2_goal_c_risk_assurance_r2/**, evidence/v0.6/b_line/g2_goal_c_risk_assurance_r2/**. Never mutate original R1 implementation/results, CI, roles, A/B worktrees or protected data.
