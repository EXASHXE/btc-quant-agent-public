# v0.6.5 — Branch Lifecycle, Engineering Docs and Research-Legacy Archive Runbook R1

**Status:** documented planned procedure; **NOT EXECUTED**. Authoritative owner-requested Codex task: [V065-M1](V065_M1_CODEX_CLEAN_MAIN_DOCS_LEGACY_BRANCH_PRUNE_R1.md). Source was the 2026-10-16 live state: 219 remote heads, default `v0.5-refactor`, `v0.6.5@065d62965373627c4887e52f482d1dcb984af860`, draft PRs #6/#5/#3/#2, repo protection-read HTTP 403. All moving facts must be refreshed.

## Main branch — active research

`v0.6.5` is intended to be the GitHub default **after authorized verification**. Its current tree should contain active quant software, minimal usable CLI/source/data documentation, current research status and exposure/source/PIT/strategy evidence links, the 0/1/2-R/2-C/2-E current role contracts and Controller owner-facing UI. It is **not** a historical audit scrapbook or maintenance log. Keep one current status entrypoint; long original reports remain at immutable Git SHAs in legacy.

No value is created by deleting old scientific STOP/FAIL records or relabeling a data pilot as accepted Alpha. Current execution and G2/G4 gates remain unchanged.

## Docs branch — engineering-only, preferably orphan

`docs/engineering` should be a genuine orphan branch containing `README.md`, `ci/`, `infrastructure/`, `repository-maintenance/` and `historical-engineering/` as needed. Move nonresearch CI performance, branch/PR operations, old deployment engineering plans and infrastructure maintenance process content here. Only move documents that are NOT necessary for current code imports, published science reproducibility, active setup or runtime tests. Main retains a short owner-friendly link, not an exhaustive engineer-only index. Keep copy/source commit mapping.

An ordinary descendant branch of v0.6.5 includes the entire main tree and is not a docs-only branch; creating this orphan requires Git worktree/CLI. Never force-replace any preexisting protected docs branch.

## Legacy branch — preserve exact original Git history

`legacy/research-archive` should have a small visible top tree: `README.md`, `research/INDEX.md`, `provenance/BRANCH_DISPOSITION.json`, `provenance/RESTORE.md`. It must retain all historical outcomes as facts, not active instructions. Key studies include historical failed/blocked BTC mechanisms, methodological audits, R8/R9 source/novelty gates and R11 Q1/Q2/D2/E2 data-source limits. Source documents may be curated/readable; original commit ancestry is the crucial technical preservation proof.

**Do not confuse an archived Markdown SHA list with reachability.** For each planned deleted head that is not already covered by a retained branch, connect its original exact commit to the legacy branch history without changing the visible archive tree (a verified `git merge -s ours --no-ff --allow-unrelated-histories <frozen-ref>` is one possible method). Recheck `git merge-base --is-ancestor <old-sha> legacy/research-archive` for **all** retired tips, then use a clean clone fetching **retained refs only** to verify the old commits and vital `<SHA>:<path>` blobs. A branch containing confidential/protected material requires independent classification and must be held rather than copied without authority.

## Backup and destructive-action gates

**Before deletion:** fetch ALL remote refs, build SHA/PR/activity/protection inventory, make a local nonpublic Git bundle of the complete accessible public repository, verify the bundle and perform at least one isolated restore test. Publish clean `docs/engineering` and `legacy/research-archive` branches and independently refetch them. Preserve a per-branch restoration record.

**Per deletion batch:** exact branch-ref allowlist, current remote SHA equals frozen SHA, no active PR/push/dependency, no administrative protection uncertainty, original SHA guaranteed reachable from retained archive, backup good. Use explicit per-branch deletion commands. Always log success/failure. Do not delete default branch until owner/admin has switched it to v0.6.5 and confirmed via independent repo GET; old A-line may require a separately retained exception. Do not close active PRs or change branch protections silently.

**After deletion:** refresh all paginated branches, PRs, default and actual CI. Count `eligible`, `deleted`, `held` and `unexpected move` exactly; compare against baseline SHA ledger. Confirm only 3 desired permanent heads remain (`v0.6.5`, `docs/engineering`, `legacy/research-archive`), or list each justified fourth/temporary A-line/default/PR exception and how it can end. Preserve a privately verified restorable backup; **Git object storage may remain large** even if branch count drops.

## Classification vocabulary

- `KEEP_ACTIVE_MAIN`: present-day B-line scientific or executable work.
- `MOVE_DOCS_ENGINEERING`: only current/historical maintenance instructions, docs-only.
- `ARCHIVE_LEGACY`: historically meaningful negative/positive-bounded methods and commit graph preserved, old branch can be deleted after ancestor proof.
- `DELETE_DUPLICATE_REACHABLE`: exact old tip already ancestor of a retained ref and no active dependency.
- `HOLD_ACTIVE_PR`, `HOLD_A_LINE`, `HOLD_PROTECTION_UNKNOWN`, `HOLD_MOVED_REF`, `HOLD_ARCHIVE_FAILURE`: no deletion, explicitly counted.
- `DELETED_VERIFIED`: remote deletion confirmed, old SHA independently recoverable by archive or backup.

## Checkpoint receipts

Report final `v0.6.5` HEAD and observed default, `docs/engineering` and `legacy/research-archive` head SHAs, exact before/after counts, merged/superseded PRs, per-ref deletion list and archival reachability N/N, file move/source SHA map, real CI/test statuses and restore command. A "delete suggestion" without remote deletion receipts is **not** a completed clean-up.

**Unchanged:** `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.
