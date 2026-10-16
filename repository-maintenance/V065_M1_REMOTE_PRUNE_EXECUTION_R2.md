# V065-M1 remote prune execution R2

**M1_PARTIAL_CLEAN_WITH_EXPLICIT_HOLDS.** Eligible remote pruning is executed: **222 → 49 branches; 173 actually deleted in 12 verified batches; 3 permanent target branches retained; 46 additional refs held**. Default is now **v0.6.5**. Remaining holds are ownership/review decisions, not missing GitHub administration access.

## Current permanent topology

| Branch | Verified identity |
|---|---|
| v0.6.5 — default | `941f24af8f1e12c1f314e2d970e7af8f97293b21` |
| docs/engineering | This report's containing commit, an ordinary descendant of `d2ff586cb234dd3a3999ab5f77409bec6c274923`; final delivery freshly verifies the published ref |
| legacy/research-archive | `0176cdde836a660420e5e4b5693591cb8108a4f6` — unchanged |

[All 49 branch names and exact pre-receipt SHA identities](v065-m1-prune-r2/REMAINING_REFS_BEFORE_RECEIPT.tsv). Only docs/engineering advances to publish this receipt; resolve its final exact SHA as the containing commit. [Exact 173 deleted refs and original HEADs](v065-m1-prune-r2/DELETED_REFS.json). [All 46 held refs, SHAs and release conditions](v065-m1-prune-r2/HELD_REFS.json). [Machine dashboard](v065-m1-prune-r2/SUMMARY.json).

## Authority and actual administration

Official interactive GitHub CLI device login completed as **EXASHXE**, with repo/workflow scopes. Authenticated repository and collaborator APIs both confirm admin/push permission. All 222 initial branches have protected=false; canonical protection reads for main, previous default and v0.6 return explicit **404 Branch not protected**. Canonical protection reads for every deletion candidate are repeated in its batch and recorded. Parent-inclusive repository rulesets are **[]**, re-read before every batch. Thus no required branch checks/reviews or protection deletion restriction was bypassed. No 403 was treated as authority. No protection rules or bypass settings were modified.

Default switch used authenticated PATCH only after the CI fix succeeded; a separate GET verifies v0.6.5. [Fresh switch proof](v065-m1-prune-r2/DEFAULT_SWITCH_VERIFIED.json). The owner approved the durable local backup directory before any deletion.

## CI dependency and schedule

[Published CI fix 941f24a](https://github.com/EXASHXE/btc-quant-agent-public/commit/941f24af8f1e12c1f314e2d970e7af8f97293b21) changes only `.github/workflows/ci.yml`, `scripts/ci/test_plan.py` and `tests/test_ci_test_plan.py`. The planner/fetch now uses the exact old v0.6 HEAD `11e4ccc5f1c86ce4680b54be1e6329993f9db380`, preserving comparison scope without requiring the named branch. The former last-resort immutable fallback remains. This base is an ancestor of the retained archive. v0.6 was subsequently deleted successfully.

The weekly schedule was removed before the default switch to prevent unexpected full scheduled workloads. Push, PR, manual profiles, all existing tests and full manual compatibility checks remain. Regression verifies first-push and PR-fallback diff scope without old branch lookups. Local validation: **13 planner tests passed**, Ruff passed, compileall passed, git diff --check passed.

Actual GitHub [CI run 38918484549](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38918484549) at the exact new main SHA is **completed / success**. Immutable-base fetch, plan, scoped Ruff, compile, JSON validation and selected tests succeeded. Production/research dependency installation, mypy and full compatibility matrix were **SKIPPED** under the unchanged CI-only routing. No full research/production suite pass is claimed. [Run evidence](v065-m1-prune-r2/CI_RUN.json), [actual job/step outcomes](v065-m1-prune-r2/CI_JOBS.json). Engineering report and archive have no own workflow; no CI run is claimed for them.

## Preservation and real deletion receipts

The handover bundle was not found in this workspace or /tmp. A fresh complete bundle was constructed from advertised public refs, then refreshed after publishing the CI fix. Owner-approved private local backup:

`/root/workspace/project/quant-v0.6/m1-remote-cleanup/backups/pre-prune-execution.bundle`

SHA256 **`44e9b94242bff4bf950018d61c026639746774aeaab2472c1a65d575d537c8da`**. Complete-history bundle verification, independent mirror clone, **222/222 exact branch HEAD restoration** including new main, and connectivity fsck passed. The earlier initial-checkpoint bundle is also retained privately. Neither bundle nor credentials were uploaded. [Backup/recovery proof](v065-m1-prune-r2/BACKUP_PROOF.json).

The frozen ledger's **178/178 selected refs** were independently checked against legacy ancestry. No blanket preservation claim was made for excluded A-line/control refs. For every deleted current HEAD, a retained archive/main ancestor check and exact backup-ref recovery check passed before deletion. Each batch re-read authority, rulesets, PR dependencies, exact live SHAs and canonical protection; used explicit named `git push origin --delete`; re-read all live heads; verified only selected refs disappeared; then actually pushed every recovered original SHA at its original branch name to a **local-only rollback target** and re-read every restored ref. **173/173 deleted original HEADs recovered and rollback procedures verified.** This is local recovery proof, not a promise that future remote policy cannot change.

Actual successful batch sizes: **15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 13, 10**. [All real delete responses, protection checks, counts and local rollback push responses](v065-m1-prune-r2/BATCH_RECEIPTS.json). One batch-9 attempt failed with a TLS handshake error. Fresh reconciliation proved all 15 refs still present at exact SHAs and **0 deletions from that failed attempt**; the subsequent fully checked retry succeeded. [Unmodified failed-attempt response and reconciliation](v065-m1-prune-r2/FAILED_ATTEMPTS.json). An automatic-review concurrency concern prevented an earlier batch-8 start; a separate no-running-process check and completed prior receipt resolved it before the sequential successful start. No overlapping pruning process, force-push, wildcard deletion, history rewrite or protection bypass occurred.

## Exact remaining holds

| Reason | Ref count | Release condition |
|---|---:|---|
| A-line | 26 | Independent A-line owner releases each exact governed ref |
| Protected/control lineage | 15 | Separate control authority releases each exact ref; lineage label does not assert current GitHub protection |
| Previous default + A-line | 1 | Default dependency is cleared, but independent A-line authority is still required |
| PR #3/#5 head and base | 4 | Independent scientific/design adjudication resolves each PR and base dependency |
| **Total additional holds** | **46** | Exact names/SHAs and reasons in HELD_REFS.json |

[#3](https://github.com/EXASHXE/btc-quant-agent-public/pull/3) remains OPEN: synthetic-method Challenger review pending, head `c7c8d98520b21f3d36352e1ba0df408327e011fe`, base `repair/v06-p1a-compat-full-git-history-r1`. [#5](https://github.com/EXASHXE/btc-quant-agent-public/pull/5) remains OPEN: independent WAL design audit/Controller authorization pending, head `8c7693700c15f32329614a23b737d34cc7e2b0c4`, base `v0.6-docs`. Their submissions are not superseded adoption evidence; neither was closed.

No remaining owner-only GitHub administration action is required for default migration, authenticated deletion access or protection visibility. Further reduction requires the 42 governed-ref owner releases and resolution of the two PRs/four refs; there is no authorization to invent those decisions. Current old default `v0.5-refactor` remains because of A-line governance, not because GitHub still treats it as default.

**Research/source/Alpha gates unchanged:** SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE. No source/strategy code or admission record changes, strategy trials, data collection, protected holdout inspection, TESTNET/LIVE or financial writes.
