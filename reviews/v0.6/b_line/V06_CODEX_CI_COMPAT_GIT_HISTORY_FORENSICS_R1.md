# v0.6 CI compatibility and Git history forensics — engineering findings

**CI_COMPAT_GIT_HISTORY_FIX_VALIDATED_WITH_H40_HOLD.** The workflow-only P1A history fix is independently reviewed and validated by genuine exact-SHA full CI on Python 3.11, 3.12, and 3.13. Each selected 2,981 tests: 2,979 passed, 0 failed, 2 unchanged skips, 0 errors. The historical P1D protected H40 digest discrepancy remains unresolved; this P1A green result provides no H40 waiver, P1D patch approval, integration, or release authority.

## Authority and scope

The full dispatch file matched prompt Git blob `1a758ab3ebdacf2e74e3e32ae2014925d7b7ac98` at source commit `cf9796fe638d9d6046d8a05c3c6a9ca5785765d8`. Frozen source heads remain P1A `bc91a9d58701f5ace3b7d26e912e2a81ad9502a5` and P1D `04cbc46497ed26b0c4e889f30fa10eb8d666a79e`. Both frozen heads contain the identical original workflow blob `0cf87687216b475f338f637fb968af2f670ace67`. Existing CI reports remain archived at docs commit `7ac48cb15cdbc0a8d9b1614251b238fd25190c49`.

The only code change is on branch `repair/v06-p1a-compat-full-git-history-r1`, based directly on P1A. Candidate commit: `13e3a710b137efeec2e21e3002f748834ec0cc22`; workflow blob: `5034463aa6c6061b5059ebc1978dfa5c1c671c1e`. Its sole diff sets `fetch-depth: 0` on the compatibility job checkout in `.github/workflows/ci.yml`. Test profiles and commands, selection, timeout, credentials, protected gates, and tests are unchanged. The independent engineer performed no P1D cherry-pick or CI dispatch. The root delivery agent subsequently published this exact unchanged commit and dispatched the single full-profile run recorded below.

## Existing exact-SHA CI matrix

All six job logs are from `workflow_dispatch` with `profile=full`; their metadata and checkout output identify the exact frozen head SHA. Checkout, Python setup, and dependency installation succeeded. Each compatibility job reached the pytest step and completed within the 30-minute job timeout.

| Frozen head | Run | Job / Python | Result and tests | Failure classification |
|---|---:|---|---|---|
| P1A `bc91a9d…` | `38426593989` | `115398228093` / 3.11 | 4 failed, 2975 passed, 2 skipped | planner tests 06/08; protected H40 diff reference unavailable; H40 fixed-graph digest mismatch |
| P1A `bc91a9d…` | same | `115398228658` / 3.13 | 3 failed, 2976 passed, 2 skipped | planner tests 06/08; protected H40 diff reference unavailable |
| P1A `bc91a9d…` | same | `115398228998` / 3.12 quality | success: 2979 passed, 2 skipped | quality job already uses full history |
| P1D `04cbc464…` | `38426601134` | `115398123684` / 3.11 | 7 failed, 3353 passed, 2 skipped | planner tests 06/08; protected H40 diff reference unavailable; H40 digest mismatch; three historical-source `git show a37721e…` lookups unavailable |
| P1D `04cbc464…` | same | `115398123966` / 3.13 | 6 failed, 3354 passed, 2 skipped | planner tests 06/08; protected H40 diff reference unavailable; three historical-source `git show a37721e…` lookups unavailable |
| P1D `04cbc464…` | same | `115398123993` / 3.12 quality | 1 failed, 3359 passed, 2 skipped | H40 fixed-graph digest mismatch; quality job already uses full history |

Each P1A job selected 2,981 tests (2,979 executed, 2 skipped); each P1D job selected 3,362 tests (3,360 executed, 2 skipped), with no deselections or collection errors reported. Baseline actual runtimes were CPython 3.11.17, 3.12.15, and 3.13.16, proven by the respective setup logs. The Python 3.12 totals also match retained JUnit receipts; compatibility counts come from final pytest console summaries. All six actual checkout log hashes matched their pinned heads. Compatibility logs show `--depth=1`; quality logs show the all-heads fetch.

The complete compatibility failure lists are:

- P1A 3.11: `tests/test_ci_test_plan.py::test_06_first_branch_push_with_multiple_commits`; `tests/test_ci_test_plan.py::test_08_pr_merge_rename_delete_non_silent`; `tests/test_tactical_grid_shadow_evaluation_v1.py::test_b2b_a34_h40_diff_remains_zero`; `tests/test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph`.
- P1A 3.13: the first three above; no fourth failure.
- P1D 3.11: those first four plus `tests/test_v06_g2_btc_two_lead_funding_mark_r3_contract.py::test_exact_two_original_configs_and_no_new_signal`, `tests/test_v06_gemini_goal_trend_flow_r1_reanalysis_contract.py::test_frozen_24_contract_stops_before_source_access`, and `tests/test_v06_gemini_goal_trend_flow_r1_reanalysis_r2_run.py::test_original_ast_23_candidate_identity_and_exclusion`.
- P1D 3.13: the first three P1D history-related failures and the three P1D `git show` failures; no H40 digest failure in this job.

P1D 3.12's single failure is the H40 fixed-graph digest test. The allowed public failure excerpt reports actual digest prefix `ee185f1fce50…` versus expected prefix `d5a962cd9c95…`. It also appears in P1A 3.11 and P1D 3.11, but not P1A 3.13 or P1D 3.13. This pattern is separate from missing Git history; its cause across jobs is unknown and remains with the independent A-line owner. The independent engineer did not inspect H40 source or goldens and made no change or waiver.

## Reproducible clean-checkout evidence

The reproduction source was an isolated bare mirror at `/tmp/v06-ci-public-ref-mirror.git`, created with `git clone --mirror --no-local /root/workspace/project/Quant-agent-market-watch/.git /tmp/v06-ci-public-ref-mirror.git`. The local common repository had already fetched the public pinned refs; the mirror was used solely as a transport fixture, not as evidence of remote publication. It has no `objects/info/alternates`. The source's `refs/remotes/origin/*` public refs were copied to corresponding `refs/heads/*` in this temporary mirror to model advertised GitHub branch heads. Pinned source heads and candidate are exact commits. The checkouts under `/tmp/v06-ci-repro-*` are independently initialized repositories that fetch from this mirror; no worktree or shared object database is used.

The shallow reproduction fetch was:

```sh
git init /tmp/v06-ci-repro-p1a-shallow
git -C /tmp/v06-ci-repro-p1a-shallow remote add origin /tmp/v06-ci-public-ref-mirror.git
git -C /tmp/v06-ci-repro-p1a-shallow fetch --no-tags --depth=1 origin \
  +refs/heads/repair/v06-p1a-r2-doc-surface-ci-r1:refs/remotes/origin/repair/v06-p1a-r2-doc-surface-ci-r1
git -C /tmp/v06-ci-repro-p1a-shallow checkout --detach bc91a9d58701f5ace3b7d26e912e2a81ad9502a5
```

Equivalent P1D shallow setup used `repair/v06-p1d-r2-doc-surface-ci-r1` and `04cbc46497ed26b0c4e889f30fa10eb8d666a79e`. For each full-history checkout, the exact fetch was:

```sh
git -C CHECKOUT fetch --no-tags origin \
  '+refs/heads/*:refs/remotes/origin/*' \
  '+refs/tags/*:refs/tags/*'
git -C CHECKOUT checkout --detach PINNED_SHA
```

That refspec is the behavior implemented by `actions/checkout@v4` for `fetch-depth: 0`: its v4 source selects the all-heads/all-tags refspec when fetch depth is nonpositive, and its ref helper defines those exact mappings ([provider](https://github.com/actions/checkout/blob/v4/src/git-source-provider.ts), [ref helper](https://github.com/actions/checkout/blob/v4/src/ref-helper.ts)). The isolated mirror had public branch heads containing both `407dabc…` and `a37721e…`; full-history P1A and P1D checkouts fetched those refs and histories. It also fetched `refs/heads/v0.6` to `refs/remotes/origin/v0.6`. Additionally, `407dabc…` is an ancestor of both exact pinned heads, and `a37721e…` is an ancestor of the exact P1D head; their required availability therefore does not depend on unrelated local branch objects. In both pinned bases, immutable base `8ecff4ec4b25bf73a35309689fd3ecfacc0d3399` is an ancestor, so the planner can resolve it as its fallback even if the named branch ref is absent. These facts show that an extra fetch step is unnecessary for the two pinned bases and observed assertions.

Reachability, checked with `git merge-base --is-ancestor` in the isolated mirror:

| Object | P1A pinned head | P1D pinned head | Also on fetched public refs |
|---|---|---|---|
| `407dabc415ae8cae4210250e992941c8b9b25464` | ancestor | ancestor | `feature/v06-bline-btc-12h-funding-mark-economic-admission-r3`; `feature/v06-bline-gemini-a-code-identity-exploratory-replay-r2` |
| `a37721eaa1f3cd176146df6bdb63fbd17746189e` | not ancestor | ancestor | same two feature refs |
| immutable base `8ecff4ec4b25bf73a35309689fd3ecfacc0d3399` | ancestor | ancestor | `v0.6` and both feature refs above |

Focused planner command in each checkout, using Python 3.13.13:

```sh
pytest -q tests/test_ci_test_plan.py::test_06_first_branch_push_with_multiple_commits \
  tests/test_ci_test_plan.py::test_08_pr_merge_rename_delete_non_silent
```

| Checkout | Path | Exit / stdout | Raw output |
|---|---|---|---|
| P1A shallow | `/tmp/v06-ci-repro-p1a-shallow` | exit 1; `2 failed in 0.15s` | `/tmp/v06-ci-repro-p1a-shallow-planner.log` |
| P1A full | `/tmp/v06-ci-repro-p1a-full` | exit 0; `2 passed in 0.11s` | `/tmp/v06-ci-repro-p1a-full-planner.log` |
| P1D full | `/tmp/v06-ci-repro-p1d-full` | exit 0; `2 passed in 0.11s` | `/tmp/v06-ci-repro-p1d-full-planner.log` |
| candidate full | `/tmp/v06-ci-repro-candidate-full` | exit 0; `2 passed in 0.10s` | `/tmp/v06-ci-repro-candidate-full-planner.log` |

The structured stdout and commands are in `/tmp/v06-ci-repro-planner-results.json`. Historical guards are in `/tmp/v06-ci-repro-historical-guards.json`. They record shallow/full state, `origin/v0.6` presence, object availability, merge base, H40 diff exit status, and `a37721e…:.../signals.py` path availability. The H40 diff guard used `git diff --quiet` so no H40 source text could be emitted. In full P1A/P1D/candidate clones it returned 0 (empty diff); shallow clones returned 128 (invalid revision range). `a37721e…` and the referenced path resolve in full clones and fail in shallow clones. No protected source or golden contents were read.

The exact graph and ref evidence is in `/tmp/v06-ci-repro-git-graph.json`. It records that the isolated mirror has no alternates, ancestry booleans for both pinned heads, public refs containing each historical commit, and the checkout v4 refspec. The `origin/v0.6` ref and immutable fallback both resolve in full clones; neither is present in depth-1 clones.

## Failure stage, credentials, timeouts, and identity

The six actual job records show checkout, setup-python, and pip installation succeeded. Five jobs failed at pytest; the original P1A Python 3.12 quality job passed. The named failures are local read-only `git diff`, `git show`, and planner `git` subprocesses. Their captured errors identify absent revisions/objects/paths; no authentication or permission error appears. The pytest steps completed in 660–1210 seconds. None of the six jobs timed out; the configured job limit remains 1800 seconds. Git author identity is not used by these failing operations because they do not write commits or refs. The workflow patch adds no `continue-on-error`, suppression, skip, altered selection, or bypass; it only gives compatibility checkout the full-history refspec.

## H40 disposition and handoff

The H40 digest mismatch is a separate observed failure from missing history, but its variation across Python jobs has not been established. It remains unresolved and must be routed to the independent A-line owner with the public excerpt only. The exact-SHA full-profile GitHub rerun and independent review are recorded below; any H40 failure is retained without waiver. Controller review owns the workflow patch. No Alpha, TESTNET, LIVE, protected data, new strategy trials, auto-merge, or funds authority was exercised.


## Separation of engineering and independent review

The root delivery agent authored an earlier P1D R4 implementation and therefore does not claim independence from P1D engineering. A separate CI engineer (`/root/ci_history_engineer`) performed the frozen-base forensics, clean-checkout reproductions, and workflow patch. A separate reviewer (`/root/migration_independent_review`) checked the full dispatch, exact candidate tree, recorded reproduction evidence, and workflow v4 refspec. The root handled remote publication, full CI dispatch, receipt collection, and this single report.

The Stage I reviewer confirmed scope compliance and all 614 unchanged non-workflow entries, but correctly withheld validation pending genuine full CI. The final receipt review is below. No agent acquired release, H40 waiver, or P1D integration authority.

## Exact publication and preservation

- Code branch: `repair/v06-p1a-compat-full-git-history-r1`.
- Remote code head: `13e3a710b137efeec2e21e3002f748834ec0cc22`.
- Sole parent: `bc91a9d58701f5ace3b7d26e912e2a81ad9502a5`.
- Tree: `84748bb376ab1570b2380a319985fdb09c1ecd47`.
- Workflow: old blob `0cf87687216b475f338f637fb968af2f670ace67`; new blob `5034463aa6c6061b5059ebc1978dfa5c1c671c1e`.
- The only tree difference is `M .github/workflows/ci.yml`; all 614 other tracked mode/type/blob entries are identical. No source, test, result, historical report, golden, safety gate, or planner logic change occurred. `git diff --check` passes.
- Existing report archive remains docs commit `7ac48cb15cdbc0a8d9b1614251b238fd25190c49`: P1A report blob `00945d048664445710505bc56d64ad2210be89fe`, P1D report blob `84a4448df7c85db1d0caf04cc16351fa65e248a1`. The catalog review-directory issue is closed.
- No P1D code or branch was changed, and no P1D CI-patch merge/cherry-pick was attempted.
- Git push transport attempts timed out. Publication used the Git Database API with exact local blob/tree/commit assertions followed by creation of the new absent ref; no force update or reset. The remote head was verified before CI dispatch.
- Docs branch: `docs/v06-codex-ci-compat-git-history-forensics-r1`, based directly on dispatch `cf9796fe638d9d6046d8a05c3c6a9ca5785765d8`. This file is its only authorized ADD. Its commit/blob are provided in the delivery response rather than self-referenced inside their own content. No report directory was added to the code branch.

The minimal authorized patch is:

```diff
     steps:
       - uses: actions/checkout@v4
+        with:
+          fetch-depth: 0
       - uses: actions/setup-python@v5
```

The patch applies only to the compatibility checkout. The quality checkout already had depth zero. Default checkout fetches one commit, whereas zero depth fetches history for all branches and tags ([official checkout v4 documentation](https://github.com/actions/checkout/blob/v4/README.md)). No additional ref-fetch step is necessary for the observed pinned-base failures.

## Real full-profile candidate CI

A single manual `workflow_dispatch` requested `profile=full` after remote head freeze. Run [38494710188](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38494710188) completed **SUCCESS**, exact head `13e3a710b137efeec2e21e3002f748834ec0cc22`, branch `repair/v06-p1a-compat-full-git-history-r1`. All three jobs completed successfully.

| Job | Actual CPython | Selected | Executed | Passed | Failed | Skipped | Errors | Complete failure list |
|---|---|---:|---:|---:|---:|---:|---:|---|
| [115628134472](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38494710188/job/115628134472) | 3.11.17 | 2981 | 2979 | 2979 | 0 | 2 | 0 | none |
| [115628134525](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38494710188/job/115628134525) | 3.12.15 | 2981 | 2979 | 2979 | 0 | 2 | 0 | none |
| [115628134588](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38494710188/job/115628134588) | 3.13.16 | 2981 | 2979 | 2979 | 0 | 2 | 0 | none |

Compatibility job counts are their final pytest console summaries, not invented compatibility JUnit receipts. Python 3.12 counts also match the retained JUnit. No deselections or collection errors were reported. Each job's actual checkout command `git log -1 --format=%H` is followed immediately by the exact candidate SHA. Each checkout log shows the all-heads/all-tags history fetch:

```text
git -c protocol.version=2 fetch --prune --no-recurse-submodules origin +refs/heads/*:refs/remotes/origin/* +refs/tags/*:refs/tags/*
```

The unchanged compatibility command is `pytest -q --durations=20`. The quality command is `pytest -q --durations=20 --junitxml=ci-junit.xml`, executed through the existing full-profile planner. Checkout, Python/dependency setup and teardown succeeded; quality lint, mypy, compile and artifact checks succeeded. No timeout, credential, Git identity, test selection, or planner logic blocker remains for this tested candidate.

Python 3.12 artifact `11862839990`, `b-line-test-receipt-13e3a710b137efeec2e21e3002f748834ec0cc22`, contains `ci-test-plan.json` and `ci-junit.xml`. Its exact fields:

```json
{
  "code_sha": "13e3a710b137efeec2e21e3002f748834ec0cc22",
  "tested_sha": "13e3a710b137efeec2e21e3002f748834ec0cc22",
  "event": "workflow_dispatch",
  "mode": "full",
  "profile_executed": "full",
  "returncode": 0,
  "protected_reads": 0
}
```

JUnit has 2,981 total, 2,979 passed, 0 failed, 0 errors and 2 skipped. It directly records `test_06_first_branch_push_with_multiple_commits`, `test_08_pr_merge_rename_delete_non_silent` and `test_b2b_a34_h40_diff_remains_zero` passed without skips. Both compatibility jobs execute the full suite with the same total and no failing tests. The prior P1A history failures are absent; the fixed-graph digest assertion also passed in this candidate run, but its prior job-to-job variation and the P1D discrepancy remain unexplained.

The two quality skip identities and reasons are exactly the same as the frozen P1A baseline:

- `tests.test_v051_h40_p3_controller_authority_publication::test_p3_11_production_readiness_chain_with_real_local_data`;
- `tests.test_v051_h40_p3_controller_authority_publication::test_p3_12_run_grant_negative_bindings_fail_closed`.

Their existing reason is that an untracked non-protected local fixture is absent in remote CI. No local fixture was obtained and no new skip was added. The receipt's `protected_reads: 0` is reported CI metadata, not an independent scientific acceptance or proof about every test process.

The automatic push run [38494688754](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38494688754), same candidate head, was **CANCELLED** by the unchanged branch concurrency policy when manual full CI superseded it. It is not counted as a successful gate. No repeated full CI or automatic merge was issued.

After final CI, remote refs were independently read: P1A base remains `bc91a9d58701f5ace3b7d26e912e2a81ad9502a5`, P1D base remains `04cbc46497ed26b0c4e889f30fa10eb8d666a79e`, and the sole new code repair ref remains `13e3a710b137efeec2e21e3002f748834ec0cc22`.


## Protected H40 handoff and remaining authorization boundaries

The independent A-line owner must investigate the protected fixed synthetic graph digest using its own authority. Public failing test: `tests/test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph`.

Exact already-public assertion evidence from P1D full CI at `04cbc46497ed26b0c4e889f30fa10eb8d666a79e`, run [38426601134](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38426601134), Python 3.12 job [115398123993](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38426601134/job/115398123993):

```text
AssertionError
expected: d5a962cd9c9556b573a890b6af8cbeb09d7201187511f477d727c8670bf0b2e0
actual:   ee185f1fce50bdf710295a23506a5c29d83a70c361aff72e2b6be9e54526643d
```

This is a substantive protected-gate mismatch even though some other jobs passed the same assertion. Its job variation remains unexplained. No attribution to Python, harmless randomness, environment, or an acceptable scientific result is established here. A missing historical object and a resolved object with a different digest are different failure classes. Restoring history does not authorize a digest/golden rewrite or an H40 waiver.

Controller and independent review must decide whether any separately authorized P1D workflow change is appropriate. The P1A result proves only the tested P1A candidate; local P1D full-history focused/metadata checks do not constitute a new P1D GitHub full-CI result. The original P1D run remains failed. No automatic merge, source collection, account access, orders, new strategic scoring/trials, Alpha, TESTNET, LIVE, or protected-data authority was exercised.

## Final independent reviewer route and terminal decision

The reviewer `/root/migration_independent_review`, independent of the workflow engineer and the P1D implementation author, reviewed the final exact-SHA run metadata, all three checkout/fetch logs, both compatibility console summaries, quality full-profile plan and JUnit. The reviewer confirmed 2,979 passed / 0 failed / 2 skipped for each Python job, planner 06/08 and the path-limited diff guard passing unskipped, and full history in every checkout.

Its substantive terminal verdict is **CI_COMPAT_GIT_HISTORY_FIX_VALIDATED_WITH_H40_HOLD**. The tested P1A workflow fix is validated within the one-file authorization. The independent A-line owner retains the historical H40 discrepancy; the Controller retains any future P1D workflow adoption or integration decision. The prior P1D full CI is still failed and no new P1D full run is claimed. This task is complete within its dispatch scope; H40 resolution and P1D adoption require separate authority.
