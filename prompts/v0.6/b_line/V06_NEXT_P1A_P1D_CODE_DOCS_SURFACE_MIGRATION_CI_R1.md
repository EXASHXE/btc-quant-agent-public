# Controller Dispatch — P1A/P1D Code–Docs Segregation and Full CI R1

Controller: ChatGPT-0 B-line Primary Controller.
Recommended implementer: Codex Sol mechanical/engineering. Separate independent reviewer must inspect final two code SHAs and test receipts.
This prompt's exact immutable commit SHA is the task identity. No force push, no branch reset, no H40 golden edits, no skipping or weakening old tests.

## Frozen starting commits

Canonical docs source: 2c99c8f64368a02dfeca05ac1886ed2280faf3ba (start a NEW docs copy branch from this exact SHA; do not directly rewrite history).
P1A code+report final SHA: 0540e2c902ef9565cd3719e60174ac01b1c22adf. Original code test SHA a535fde2aa24e6e0d65a3e353d4a51e532e1abf6.
P1D code+report final SHA: 81c613c3c8dc3fb22fd4d09b2d0ef4674f09c079.

Exact code-branch review files:
P1A reviews/v0.6/b_line/V06_P1A_R2_SYNTHETIC_COST_CONTRACT_REPORT.md, Git blob 00945d048664445710505bc56d64ad2210be89fe.
P1D reviews/v0.6/b_line/V06_P1D_CONSUMER_C_LATE_FUNDING_R2_IMPLEMENTATION_AND_EVIDENCE.md, Git blob 84a4448df7c85db1d0caf04cc16351fa65e248a1.

Old failing GitHub Actions:
P1A run 38382220675 = full 2975 PASS / 4 FAIL / 2 SKIP. Three failures require the reviews/ code-branch directory to be absent; fourth is PROTECTED H40 scientific SHA mismatch (expected d5a962..., actual ee185f...).
P1D run 38390261764 = full 3357 PASS / 3 FAIL / 2 SKIP, all reviews/ catalog assertion failures. A docs-only green run is NOT executable CI PASS.

## Mandatory two-stage non-destructive relocation

Stage A: Preserve the exact two original report blobs byte-for-byte in a NEW docs-only branch docs/v06-p1a-p1d-ci-report-archive-r1 rooted at 2c99c8f64368a02dfeca05ac1886ed2280faf3ba. Allowed ADD paths only:
- reviews/v0.6/b_line/V06_P1A_R2_SYNTHETIC_COST_CONTRACT_REPORT.md
- reviews/v0.6/b_line/V06_P1D_CONSUMER_C_LATE_FUNDING_R2_IMPLEMENTATION_AND_EVIDENCE.md
- reviews/v0.6/b_line/V06_P1A_P1D_CODE_DOCS_MIGRATION_RECEIPT_R1.md
Compare original Git blob SHAs EXACTLY and freeze the archived docs commit before modifying either code branch. If any intended destination already exists with different bytes, STOP CONFLICT; do not overwrite. Record both original source SHA and archive SHA and full compare.

Stage B: Create TWO separate descendants (no cross-merges):
- repair/v06-p1a-r2-doc-surface-ci-r1 from 0540e2c902ef9565cd3719e60174ac01b1c22adf.
- repair/v06-p1d-r2-doc-surface-ci-r1 from 81c613c3c8dc3fb22fd4d09b2d0ef4674f09c079.
Only allowed code-branch changes: DELETE the respective single original reviews/... report path once the archive has been identity-verified. No code, test, evidence JSON, protected source, CI workflow, lint policy, golden, config or dependency modifications. Confirm reviews/ is absent in each checked-out code branch after deletion and source/test Git blob identities remain unchanged. If other tracked reviews/ paths persist, STOP and request a new scope instead of deleting them.

Stage C: Rerun real exact-branch/full CI. Existing .github/workflows/ci.yml at both code SHAs provides workflow_dispatch input profile=full; trigger only on the exact archived-confirmed repair branches, with full profile, and verify actual source checkout SHA and full test execution (including Python 3.12 quality; compatibility 3.11/3.13 jobs if selected). A push-only docs-scoped green run with executable tests SKIPPED is invalid as a release receipt. If manual workflow invocation is unavailable to the executor, report FULL_CI_RERUN_BLOCKED; do not edit workflow files or mislabel result.

At all stages distinguish pre-existing fail vs causal change only through authorized code-branch before/after tests; do not claim the H40 digest failure is harmless. Protect H40: NO reading or executing restricted datasets, no editing H40 code/tests/goldens, no disabling tests, no unexplained hash adoption. Escalate any recurring H40 test failure to its independent A-line authority with only the public CI failure excerpt and exact SHA. That protected gate remains a separate hold even if all other tests pass.

## Hard success conditions

- Both report blobs identical in immutable docs archive.
- Both code branches contain only one allowed deletion each with baseline source/test blobs unchanged.
- Confirm policy-neutral removal of the catalog-directory conflict; actual full CI run IDs and non-skipped test counts recorded.
- P1D can reach CODE_CI_PASS_PENDING_CAUSAL_AUDIT if its entire real CI succeeds; P1A cannot be labelled FULL_PASS while H40 mismatch persists.
- Independent reviewer confirms no protected/ledger/history changes.
- No G2 strategy repricing, historical search, exchange actions, testnet, live trading or auto-merges.

Submit 3 branch URLs/SHAs, report archive identity checks, CI logs, all test counts, reviewer receipt, terminal CODE_DOCS_RELOCATION_COMPLETE / FULL_CI_STILL_BLOCKED / SCOPE_BLOCKED. No implicit Controller merge authorization.
