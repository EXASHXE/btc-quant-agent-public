# V065-M1 — Clean Research Main, Engineering Docs, Legacy Evidence, Verified Branch Pruning

**Executor:** Codex repository consolidation / Git history engineer, High reasoning if available.
**Repo:** EXASHXE/btc-quant-agent-public.
**Owner intent:** This is a personal, noncommercial BTC/ETH quant-research repository. Optimize research iteration velocity and keep a small, clean, navigable GitHub branch list. This task authorizes ACTUAL deletion of verified redundant remote branches **only after the preservation and no-active-work checks below pass**. Do not merely produce another deletion proposal.

## 0. Verified starting reference (recheck all moving refs at execution)

- As observed 2026-10-16: **219 remote branches** across three pages; M0 branch inventory previously froze 216, so DO NOT treat that inventory as current or complete.
- `v0.6.5@065d62965373627c4887e52f482d1dcb984af860` = current B-line code/integration target, not a scientifically accepted Alpha or a release.
- Current GitHub default: `v0.5-refactor@8ecff4ec4b25bf73a35309689fd3ecfacc0d3399`.
- Owner-directed operating-role cleanup in **open draft PR #6**, source `docs/v065-research-first-role-controller-ui-r2@9ec13bb44dc674c45c7099db1ff2177ea60393ff`, aimed at `v0.6.5`. This must be consciously integrated/split BEFORE its branch is archived or removed. The R2 PR contains both current research operating docs and one CI/model engineering-process document.
- Other observed open drafts: #5 `docs/v06-next-p1d-c4-wal-design-r3`, #3 `feature/v06-reset-r1-synthetic-inference-calibration`, #2 `docs/v06-bline-role-roadmap-auditor-handover-20261013-r2`. Treat as active/unknown until verified, not automatically disposable.
- R11-Q1 `8c3e53f8fe37d9a8acd340944b843e04f05d2fdc` blocked general source admission. R11-Q2 `c07c60385479f0d595352ad751c1c49150b4cbbc` permitted only bounded data work. D2 `803a4173717ace9c03ff97051b7696210e183bef` and E2 `7f8c6acadead47dccdeba80b2ae27c2497ee8cdf` are author deliveries awaiting independent gate; C2 `9dbb0ce7d266c0d6731775a7a53170bf34400520` STOP_UNMEASURED_SOURCE.
- Effective branch protection / required-check rules were inaccessible via GitHub integration HTTP 403. Visible rulesets [] does NOT prove protection absent. Do not bypass by force.
- Previous M0 manifest: `docs/project/V065_BRANCH_CONSOLIDATION_MANIFEST_R1.md`, DAG `docs/project/V065_BRANCH_DAG_INVENTORY_R1.json` and path provenance on v0.6.5. These describe historical disposition, NOT a completed archive or permission to delete.
- This prompt branch itself is temporary and must be protected/reachable in the final legacy archive before eventual deletion.

## 1. Desired final topology (small and intelligible)

**Target THREE permanent branches:**
1. **`v0.6.5`:** canonical/default B-line active code + concise researcher-relevant README, source/PIT/strategy validation status, current 0/1/2-R/2-C/2-E role/Controller task-card contracts, relevant tests/fixtures and concise current roadmap. Keep the source/test/config/CLI files needed for working research.
2. **`docs/engineering`:** a deliberately **docs-only orphan/root branch** holding infrastructure/engineering process materials not needed as active quantitative research context: old CI workflow investigations, Git cleanup/integration recipes, deployment/architecture engineering notes, task/cross-agent historical instructions and archived maintenance status. Favor a concise index and pinned original links over copying every stale write-up. Do NOT inadvertently create this branch by cloning the full live repo tree and call it docs-only.
3. **`legacy/research-archive`:** a deliberately **archive-only branch** with an easy-to-read research evidence index, complete original-branch-head ledger, original scientific/negative-result attribution and preserved commit ancestry sufficient to make each retired exact SHA still **reachable after remote ref deletion**. Historical experiment and provenance files may be selectively exposed in a curated `research/` subtree, but not in current v0.6.5. Never copy private/protected datasets or secrets.

**Allowed temporary/fourth exceptions:** An actively governed A-line stable branch (`a-line/stable` or existing named original) if independent A-line ownership requires it; an unresolved open-PR branch; or old default `v0.5-refactor` until an authorized admin actually switches default. Every exception must have explicit owner, purpose and end condition. Do not forcibly achieve "3" by deleting active/protected history.

**What "clean" means:** active v0.6.5 working tree, roles/README and branch list are focused. Retained Git history can still be large; archiving commit ancestry is NOT a promise to shrink GitHub object storage bytes. Do NOT rewrite protected/frozen SHAs or the entire history to chase a smaller pack size.

## 2. PHASE A — Freeze live refs, ownership, and recoverable backup

1. Fetch origin without modifying local user data. Enumerate ALL remote heads via Git protocol AND GitHub paginated API; record 40-char HEAD, tree SHA, merge-base, ancestors and descendants, timestamp, branch protection signal/unknown, open PRs (including author/target/status), workflows/dependencies, and changed-path risk. Refresh after each deletion wave. Work in a **new isolated authorized cloud/local clone**; do not touch `Quant-agent-sanitized`, `Quant-agent/data`, old protected holdout/worktrees, credentials or private operational files.
2. Record default branch, open PRs, required checks/protection/rulesets. If read 403, report `PROTECTION_UNKNOWN` and do not make privileged claims.
3. Make a **verified, local/nonpublic Git bundle** from all fetched public-repo refs, e.g. `git bundle create <safe-external-path>/pre-v065-m1-allrefs.bundle --all`, plus SHA-256, object/refs manifest. `git bundle verify` against a clean test clone and prove a representative selected retired HEAD can be restored. Do not commit/upload the bundle to the public GitHub repository. If bundle/backup is impossible or disk insufficient: **STOP BEFORE ANY DELETION** with exact blocker. A manifest of SHAs alone is NOT a restorable backup.
4. Generate a machine-readable current `BRANCH_DISPOSITION.json` with **one entry for every live head**: old ref, exact SHA, classification, preserved-by archive SHA/ancestry, relevant frozen report path/commit, open PR/active owner status, deletion eligibility and actual eventual delete receipt. Do not overtrust the old 216-entry census.

## 3. PHASE B — Split current research docs from engineering/maintenance docs

1. First process open draft PR #6: reconcile its current v0.6.5 research-first documents with latest code and the owner instruction here. Keep current concise research mission, objective, current scientific/source status, real Controller UI/task cards, five role contracts, active handover and compact scientific register **on v0.6.5**.
2. Put verbose CI planner histories, Git DAG/branch-pruning forensics, routine deployment/infra/cross-agent work instructions and generic software-process maintenance notes on **`docs/engineering`**. For mixed docs, extract a short researcher-facing summary on main, move the full maintenance detail to docs/engineering with links; retain immutable source provenance. No unrelated copied 216-branch tables on main.
3. Do not blindly merge PR #6 or stale `v0.6-docs`: selectively reconcile file paths/intent, preserving current research behavior. Close/merge the draft PR only under an explicit reviewed disposition; if still open and active, do not delete its head.
4. The docs branch should be born orphan with ONLY docs-oriented content, e.g. `git switch --orphan docs/engineering` in a separate clean worktree, remove staged old tree, add `README.md`, `ci/`, `infra/`, `repository-maintenance/`, `historical-engineering/`. No runtime/test/workflow files copied. Do not create docs branch by moving necessary runtime documentation out of main without updating links/dependencies.
5. Main README should start with current quant v0.6.5 research use, dataset known limitations, active command usage and links to a concise progress dashboard. Avoid stale v0.5 general chronology and retired experiment prompts as main navigation.
6. Preserve source/PIT/rights science and its negative outcomes **without changing scientific labels**. Do not turn expired experimental notes, CI greens, data checksums or author claims into G2 acceptance.

Deliver: path-by-path KEEP_MAIN / MOVE_ENGINEERING_DOCS / ARCHIVE_LEGACY / DROP_DUPLICATE matrix; resolved links and one safe Git diff. Distinguish doc relocation (non-destructive) from branch deletion (destructive).

## 4. PHASE C — Create a genuinely reachable `legacy/research-archive`

1. Create an **orphan archive branch** with a small visible current tree:
   - `README.md`: exact research/archive scope and "historical records are not current authorization".
   - `research/INDEX.md`: ordered historical mechanisms, original exact-SHA reports, canonical STOP/FAIL/INCONCLUSIVE/PASS_WITH_LIMITS results, exposed DEV vs protected OOS, source provenance and reason old work is not active.
   - `provenance/BRANCH_DISPOSITION.json` and human summary with every original ref, head, object identity, archive status and recovery instructions.
   - Curated non-sensitive, research-essential report snapshots or immutable links, not bulk raw datasets/secret files.
2. **Critical: preserve Git ancestry, not merely links.** For each branch HEAD intended for deletion that is not already ancestor of retained refs, connect its immutable commit graph to legacy branch using explicit history-only merge parents, e.g. bounded `git merge -s ours --no-ff --allow-unrelated-histories <frozen-temp-ref>` under a clean archive-only worktree; this retains legacy's clean visible tree while making the old head an ancestor. Minimize redundant merges by deduplicating identical heads and already-covered ancestors. All commands must be audited so they cannot bring old executables into current main or claim a failed strategy is accepted. If a merge affects the visible archive tree unexpectedly, STOP and restore from the backup. An equivalent documented ancestry-preserving Git method is acceptable.
3. For EVERY retiring exact HEAD SHA run `git merge-base --is-ancestor <sha> legacy/research-archive` and `git cat-file -e <sha>^{commit}`. Verify important `<sha>:<path>` report blobs and source links remain resolvable after archive push using a **second clean clone that fetches only retained remote branches**. A successful push without independent remote re-fetch and reachability proof is insufficient.
4. Historical A-line/H39/H40/H41/Forward/Final/OOS, sensitive owners or protected payloads: **NO contents inspection/copy or casual archive of confidential data**. Where author/Controller authority or visibility is unclear, retain the exact original branch as a named HOLD exception rather than unexpectedly spreading protected history into a public archive. Immutable Git ancestry must not be synthesized by editing original science.
5. Preserve important D2/E2 code/test/report HEADs even if their feature branches are deleted; those authors are **pending independent review**, so include exact source/parent/blob and `NOT_ACCEPTED`. Archive failed and rejected ideas too; never rewrite scientific status.

Before any delete, push and independently verify `legacy/research-archive` and `docs/engineering`; verify GitHub can fetch the original exact research source SHA even without its old branch ref.

## 5. PHASE D — Actually prune safe redundant branches, in reversible batches

**Owner authorizes actual removal of clearly redundant refs after every gate in A–C passes**; do NOT stop at a plan-only report. Maintain an explicit short allowlist of final refs, and do **not** delete protected, current HEAD-moving, default, open-PR-active, unarchived, source-unreachable or unclear-governance refs.

- Candidate pool: old `dispatch/*`, `docs/v06-*`, completed `feature/*`, `proof/*`, `repair/*`, `validation/*`, dormant `v0.6-docs`, old `v0.6.1`, old `integration/*`. Do not assume names imply permission; compare exact live head to frozen inventory, activity, PR status and archive ancestry.
- Delete in TWO OR MORE bounded waves: start exact duplicated/done branches, then old documentary/feature heads with proven legacy ancestry. Use an explicit Git remote deletion by name (e.g. `git push origin --delete <branch>`), **never wildcard push**, record the remote response, delete-list SHA and result. Re-query branch SHA and active PR immediately before each batch and STOP for any moved branch. If a deletion fails due to protection/permissions, mark `HOLD_ADMIN_REQUIRED` instead of bypassing.
- Resolve the 4 current open drafts intentionally: #6 must be integrated or cleanly superseded; #2/#3/#5 may be closed only after actual read of owner/activity/acceptance and clear archive/replacement (no erasing still-needed work). Never delete an open-PR head while the PR remains in active consideration. Report unresolved PRs as explicit exceptions.
- DEFAULT BRANCH: Switch to `v0.6.5` ONLY using an authorized admin/UI/gh flow, verify via fresh GitHub repository GET, inspect scheduled workflow behavior and do not bypass required checks. The current GitHub app lacks branch protection/admin read. If Codex lacks default-switch privilege, leave `v0.5-refactor` in place and report exact manual owner action; do not falsely claim the branch topology is finished. After a real default switch and legacy ancestry proof, old default can be deleted only if separately verified no A-line active or protected dependencies; otherwise keep as a clear active A-line exception.
- User never authorized wholesale branch reset/force push/rewrite, destruction of independently governed A-line controls, protected experiment samples or the creation of fake science acceptance. Keep the existing CI YAML/tests unmodified for this task.

A failed partial deletion is not permission to retry blindly. Retained backup + original SHA ledger are the rollback path: `git push origin <recoverable-old-sha>:refs/heads/<old-branch-name>` when explicitly needed, after verifying the old name remains vacant, permissions and protected status. Record test of this **procedure** without creating extraneous permanent branches.

## 6. PHASE E — Verification and exact final handoff

**Research main:** `v0.6.5` clean, unchanged necessary executable semantics, current source/Alpha gates and usable research README. Verify no accidentally removed needed config/docs/runtime imports, relative links, docs ownership and actual changed-code focused regressions. Docs-only changes: exact tree/diff/link integrity; no unrelated all-suite loop. Material code move or changed execution semantics: targeted real negatives and relevant independent gate.

**Engineering docs:** orphan docs tree contains documentation only, readable topic index, active maintenance instructions and links back to the main. No duplicate active Controller scientific authority.

**Legacy:** only archive index/curated research visible at tip, ALL retired heads reachable, bundle verified, important original blob/commit links work. A legacy branch is not a new Alpha experiment or permission.

**Branch cleanup:** page through GitHub API at end to report EXACT remaining refs and counts. Target **3 permanent branches**, or **4 with documented active A-line**, plus only explicit temporary/admin/PR exceptions. No undocumented old `docs/*`, `dispatch/*` or `feature/*` refs. Show:
- before/after branch counts and every remaining branch SHA;
- exact retired head count, duplicate/covered count, actually deleted count, held/exceptions and why;
- preserved ancestry proof count N/N and sampled restoration test, local nonpublic bundle checksum and path (do not expose protected local directory if sensitive);
- all changed files on each retained tree, exact commit/parent/blobs, final active default branch and real permission/protection status;
- open PR resolution map (#6/#5/#3/#2 and newly discovered PRs);
- actual tests, exact SHA + CI URL (pass/fail/skipped), no fictional full-suite PASS;
- recovery instructions, no historical-science status inflation;
- the next research milestone and one concise Controller-ready handoff card.

**Terminals:** `M1_CLEAN_REPOSITORY_COMPLETE` only when branch deletion, retained refs, archive links, default-switch and exception accounting are all verified; otherwise `M1_PARTIAL_CLEAN_WITH_EXPLICIT_HOLDS`, or `M1_NO_DELETE_BACKUP_OR_AUTHORITY_STOP` if backups/rights fail. Never report a clean 3-branch completion if protected/default/open-PR branches remain.

**Preserve:** `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`. No new market downloads, protected outcome reads, Alpha trials, TESTNET/LIVE, funds or order activity.
