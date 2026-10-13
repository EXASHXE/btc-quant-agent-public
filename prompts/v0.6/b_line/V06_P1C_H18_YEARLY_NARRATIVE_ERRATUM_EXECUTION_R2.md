# Controller Dispatch — P1C H18 Published Narrative Erratum R2

**Owner:** ChatGPT-0 — B-line Controller.
**Executor/model route:** Gemini NORMAL (bounded, doc-only), then independent ChatGPT-1 or Codex Sol read-only review.
**DISPATCH_ID:** V06_P1C_H18_ERRATUM_R2.
**DISPATCH_SHA:** immutable Git commit containing THIS file, as linked in the Controller's task handoff. Verify the commit SHA and blob before working. Do not substitute a moving branch.
**Authorized task:** one isolated documentation/forensics branch; no new empirical strategy trial or historical PnL evaluation.
**EXECUTION BASE:** Controller docs branch frozen SHA efa2df62c02d21b20ce07846c7ca30901716e773. Create a new branch/worktree from this exact commit: docs/v06-p1c-h18-narrative-erratum-r2. If a branch already exists, stop and report conflict; no force push.

## Immutable source identities

H18 report and machine:
- 397a62c1a0fbd6ad14a569a5be0058b1f684f08e:docs/strategy_research/g2_goal_h18_mechanism_r1/H18_MECHANISM_EMPIRICAL_REPORT.md
- 397a62c1a0fbd6ad14a569a5be0058b1f684f08e:evidence/v0.6/b_line/g2_goal_h18_mechanism_r1/H18_MECHANISM_DIAGNOSTIC_RESULTS.json

Canonical upstream:
- 55ac4c631c69f6edbd275462ad23e4486b9782ed:docs/strategy_research/g2_exit_horizon_r1/EXIT_R1_EMPIRICAL_REPORT.md
- 55ac4c631c69f6edbd275462ad23e4486b9782ed:evidence/v0.6/b_line/g2_exit_horizon_r1/EXIT_R1_RESULTS.json

Use the already-exposed reports and machine results for table-to-table comparison; do NOT load underlying event/market data or execute the historical runner. In particular, do not read reserved, H39/H40/H41/Forward/Final Holdout, owner Quant-agent/data, Quant-agent-sanitized, private accounts or credentials, even for metadata.

## Write allowlist

Only:
- reviews/v0.6/b_line/V06_P1C_H18_YEARLY_TABLE4_IMMUTABLE_ERRATUM_R2.md
- reviews/v0.6/b_line/evidence/V06_P1C_H18_TABLE4_CROSSWALK_R2.json

Never modify the original report, source-machine JSON, code, tests, CI, planning docs or old research ledgers.

## Required deliverables

1. Exhaustive candidate × year × H1/H2/E0 × STRESS annual narrative Table 4 crosswalk, including values, event N, units, field paths, frozen SHA, matching status, and no arbitrary rounding tolerance. Start with known conflicts: W1 2021 H1 +128.53 narrative vs +107.5206 canonical; W1 H1-E0 +23.95 narrative vs +2.9443 machine; W2 2021 N14 narrative vs N10 canonical.
2. For each mismatch distinguish mechanical arithmetic/copy error, cohort/estimand identity mismatch, and UNKNOWN. Do not infer a historical ledger defect without source-exact event-identity evidence.
3. State that H18's four W1 target winners ≈98.064% and three W2 ≈74.636% are ex-post right-tail attributions, not ex-ante 18h classifier evidence. Retain 26/56 adverse 12–18h continuation and no Alpha promotion.
4. Document independent reviewer challenges and disposition. If no reviewer is available, mark REVIEW_PENDING; no self-certification.
5. Publish exact commit SHA, source SHA receipts, changed file allowlist, test/CI executed or skipped. Docs-only CI failures caused by inherited H41 Ruff must be distinguished; never edit H41 or disable lint to green a docs deliverable.

**Pass:** exhaustive reproducible table/field crosswalk plus non-destructive erratum, with independent review. **Hard stop:** source identities cannot reconcile, missing machine field, unexpected file differences or any proposed historical replay. Terminal: REPORT_ERRATUM_READY or SOURCE_IDENTITY_BLOCKED. Never claim strategy Alpha or unlock a new trial.
