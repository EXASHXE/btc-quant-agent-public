# V065-M0 — Bounded Validation Receipt R1

**Candidate:** integration/v0.6.5-candidate-r1. **Intended unified target:** v0.6.5.
**Frozen executable base:** `11e4ccc5f1c86ce4680b54be1e6329993f9db380`.
**Manifest freeze commit:** `7a2e1a41dc33bd2590dcf91d5ef7fbdf5d0f527c`.
**Author disposition:** CONSOLIDATION_CANDIDATE_WITH_LIMITS; independent integration review pending. No release or scientific promotion.

## Actual local verification

| Check | Actual result | Scope / limitation |
|---|---|---|
| Input ref refresh | 216/216 branch names and HEADs unchanged before manifest publication | Frozen snapshot, not a claim that moving refs never change |
| DAG inventory | 216 branches, 211 different HEADs; 1,693 complete frozen-input commit-parent records | Commit/tree/path metadata only for protected scopes |
| Patch identity | 164 safe executable net patch IDs computed; 72 distinct IDs; seven multi-branch equivalence groups | Declared safe executable paths only; 27 out-of-scope and 15 protected/control branches not content-compared; ten have no safe executable delta |
| Actions history | All 211 different frozen HEADs queried; all result sets fit one page | Workflow-level results preserved; not automatically full-test evidence |
| CI planner regression | `python -m pytest -q tests/test_ci_test_plan.py`: **12 passed** | Existing tests, no new implementation-mirroring tests |
| Safety negative/regression suites | `python -m pytest -q tests/test_execution_guard.py tests/test_execution_environment_authority.py`: **39 passed** | Synthetic/hermetic safety checks; no accounts, protected payloads or market actions |
| Ruff | `python -m ruff check src scripts tests tools --output-format=concise`: **PASS** | Active code/tests/tools only; protected historical evidence directories excluded |
| mypy | `python -m mypy --no-incremental --python-executable <isolated-env-python>`: **PASS, 161 source files** | Initial run before installing declared pyarrow research dependency reported four import/unused-ignore errors; dependency installed, explicit interpreter used, no code changed |
| Compile | `python -m compileall -q src scripts tests tools`: **PASS** | Static compilation only |
| Diff whitespace | `git diff --check`: **PASS** | Includes path-specific documentation reconciliation |
| Navigation | 26 missing relative targets redirected to exact immutable source SHA; zero unresolved targets in reconciled pages | Frozen dispatched prompts retained; a fresh V065 Controller bootstrap was added |
| Whole-tree and inventory integrity | **PASS**: 17 allowed changed paths; complete 216-branch lists match original Git metadata; all 1,693 parent records close; 96 local Markdown targets resolve; JSON parses | All executable/protected trees and the separate A-line role are byte-identical to base |
| Risk planning on manifest freeze | Exact `7a2e1a41dc33bd2590dcf91d5ef7fbdf5d0f527c`: mode **none**, two documentation files | Final published candidate plan/CI must be checked separately |

The repository's complete source/test/script/config/dependency/workflow trees are retained from the frozen base. Whole-tree metadata comparison against the frozen base passed with only README, documentation and the fresh navigation bootstrap changed. This avoids changing A-line controls, source/PIT/funding/accounting/Mark identities, NO_ACTION and account safety. No protected payload was opened for validation. No existing source branch is rebased, reset, force-pushed, merged or deleted.

## Remote CI and protection

- Frozen base Actions [38871664542](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38871664542) at exact `11e4ccc5f1c86ce4680b54be1e6329993f9db380`: SUCCESS. This is an observed workflow result, not an independently re-audited full suite.
- Manifest-freeze Actions [38876065627](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38876065627) at exact `7a2e1a41dc33bd2590dcf91d5ef7fbdf5d0f527c`: SUCCESS, documentation scope.
- The final candidate's SHA, parent, tree, file blobs and automatic GitHub Actions result must be returned in the external delivery receipt after publication. This document does not invent its own future SHA or claim a future run is green.
- D2 author CI 38852084293 and E2 author CI 38852426013 remain FAILURE in the frozen inventory. Consolidation does not retroactively change them.
- Full/integration/compatibility suites were **NOT RUN** for this documentation-only consolidation. No material executable patch was selected. No full executable or release PASS is claimed. Existing code/docs catalog invariants may require a separately authorized full-integration review; they were not weakened or skipped through a CI edit here.
- Effective branch-protection/required-check coverage remains **BRANCH_PROTECTION_VERIFICATION_PENDING**. Integration requests to three canonical protection endpoints returned 403; visible rulesets were empty, not proof of absence. Required review/check/bypass/push policy is not declared absent. No protections, CI triggers, job logic or tests changed.

## Review and scientific limits

All local checks are implementation QA by the integration author. A distinct independent reviewer has not yet accepted this candidate. Further source-adapter or executable imports require their own exact-code independent gate and Controller selection. No pilot, obsolete runner, alternative engine, legacy proof or scientific hypothesis is activated by this round.

`SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE` remain unchanged. Source feature/docs branches and historical reports remain immutable evidence; v0.6.5 is a maintainable repository integration target, not an authorization to trade or a default-branch migration.
