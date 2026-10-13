# Codex Sol Medium/High — P1A/P1D Cross-Python CI History and Protected-Gate Forensics

## Identity and isolation

Owner: ChatGPT-0 B-line Controller, quant v0.6. Task ID: V06_CODEX_CI_COMPAT_GIT_HISTORY_FORENSICS_R1.
Controller authority: the exact Git commit containing this prompt; verify the full blob/SHA before working.
Codex engineer for CI forensics, independent of the P1D Funding implementation. No code-branch cherry-picking or merging.
Frozen repaired code bases:
- P1A \`bc91a9d58701f5ace3b7d26e912e2a81ad9502a5\`, branch \`repair/v06-p1a-r2-doc-surface-ci-r1\`;
- P1D \`04cbc46497ed26b0c4e889f30fa10eb8d666a79e\`, branch \`repair/v06-p1d-r2-doc-surface-ci-r1\`.
Existing exact-SHA real manual full CI:
- P1A \`38426593989\`: Python 3.12 risk-based quality SUCCESS, Python 3.11 and 3.13 compatibility FAIL.
- P1D \`38426601134\`: Python 3.12 3359 passed / 1 failed / 2 skipped, failure protected H40 fixed synthetic graph digest; Python 3.11 and 3.13 compatibility FAIL.
Both code reports were already byte-preserved to docs \`7ac48cb15cdbc0a8d9b1614251b238fd25190c49\`; the catalog review-directory conflict is closed. Do not repeat it as an open bug.

## Exact hypotheses to test

At both repaired branches, \`.github/workflows/ci.yml\` uses full fetch-depth for its Python3.12 quality job, but the \`compatibility\` job uses default \`actions/checkout@v4\` shallow clone. Python3.11 and Python3.13 logs show two \`tests/test_ci_test_plan.py\` failures involving absent Git base identification, \`git diff 407dabc...HEAD\` exit128, \`git show a37721ea...\` exit128 on P1D, plus a separate H40 digest mismatch. **Do not assume all failures share one cause.** Falsify the shallow-history hypothesis using actual checkout metadata, available refs, test fixtures and before/after repo graph. Distinguish:
- Git object history unavailable versus incorrect CI planner logic;
- historical Git object on another branch lacking ref fetch versus intentionally protected/missing object;
- environment-specific compatibility behavior 3.11/3.13 versus identical Python3.12 gate;
- genuine protected H40 graph digest difference versus unsafe science-golden change; A-line controls H40.

Read public CI logs and allowed repo code metadata only. No private/protected H39/H40/H41/Forward/Final Holdout data, original A-line experimental datasets, or manual strategic scoring. For protected H40 read **only the already-public CI failure excerpt and diff metadata**, not protected sources/goldens or confidential corpus.

## Narrow engineering scope and two-stage delivery

STAGE I, required: Read-only independent forensic matrix with exact workflow runs, job IDs, issue classification and minimal fix proposal. Prove whether checkout fetch-depth=0 and explicit safe ref fetch within compatibility job is sufficient, and whether job timeouts, credentials or Git identity remain blockers. Avoid suppressing failures, rewriting expected SHA, altering scientific tests or globally disabling safety.

STAGE II, conditional limited code change: Only IF a reproducible fixture and available Git-object hypothesis warrants it, create one isolated branch \`repair/v06-p1a-compat-full-git-history-r1\` based on P1A SHA \`bc91a9d...\`. **Allowed sole MODIFY path:** \`.github/workflows/ci.yml\`. Ancestry/history availability and preserving original test selection/full profiles ONLY; no "paths-ignore" or skips to turn old red tests green. If a fix requires any other path, STOP with \`SCOPE_ESCALATION_REQUIRED\` and do not modify it. This one-branch patch must not be blindly cherry-picked into P1D before independent review/Controller approval.

For logs and receipts, create new docs-only report \`reviews/v0.6/b_line/V06_CODEX_CI_COMPAT_GIT_HISTORY_FORENSICS_R1.md\` on an isolated docs branch from the exact dispatch commit (NOT on code branch, and NOT a review dir under code checkout). This report is authorized independently of optional CI code change. At most one report file. If docs branch creation impossible, return findings in response rather than changing unrelated files.

## Acceptance and CI policy

Run focused planner tests in permitted clean checkouts first; issue workflow_dispatch profile=full only when code change exists and exact code head frozen, and record real job IDs, Python versions, complete failing test lists, selected vs skipped test counts. An H40 graph digest failure is **not** authorized to be fixed/waived by B-line; escalate to A-line independent owner with exact public failure evidence. A successful Python3.12 risk-based CI does not imply compatibility 3.11/3.13 passed. Preserve source/test/result blobs and CI behavior.

Terminal deliverables:
- \`CI_COMPAT_GIT_HISTORY_FIX_VALIDATED_WITH_H40_HOLD\`, \`CI_COMPAT_DIAGNOSIS_COMPLETE_PENDING_PATCH\`, or \`CI_COMPAT_SCOPE_BLOCKED\`;
- exact branch/commit/blob/CI evidence, independent reviewer route;
- no Alpha, TESTNET, LIVE, protected-data, new strategy trials, auto-merge or funds authority.
