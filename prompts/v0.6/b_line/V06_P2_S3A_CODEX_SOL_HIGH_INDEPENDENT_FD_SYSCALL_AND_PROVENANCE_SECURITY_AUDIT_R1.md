# Codex GPT-6 Sol High — independently falsify P2 S3A R2 POSIX FD reader, syscall budget and source lineage

**TASK_ID:** `V06_P2_S3A_CODEX_SOL_HIGH_INDEPENDENT_EXACT_SHA_FD_SYSCALL_AND_SOURCE_AUDIT_R1`
**ROLE:** independent B-line security/scientific-evidence auditor. **NO CODE FIXES** to Gemini implementation; do not convert an audit into an unauthorized new reader or real-data QA.
**CONTROLLER_DISPATCH_SHA:** `874c42e8e3e4121955710f3207870aebb473e5da`
**MANDATORY FIRST READ:** [Frozen Controller R2 disposition, exact code findings and audit authority](https://github.com/EXASHXE/btc-quant-agent-public/blob/874c42e8e3e4121955710f3207870aebb473e5da/reviews/v0.6/b_line/V06_P2_S3A_R2_CODEX_INDEPENDENT_SECURITY_AUDIT_DISPATCH_R1.md). Treat as binding. Carefully distinguish author claims, tool-reported counters and observed native OS calls.

## Pre-created branch and immutable target

Repo `EXASHXE/btc-quant-agent-public`. **Audit branch already created** `feature/v06-bline-p2-s3a-codex-sol-audit-r1` at **exact frozen implementation `999cf7005c741bdbabae727f10f90f23330fb035`**. Start from that SHA, not latest `v0.6` and not latest `v0.6-docs`. Preserve implementation and original Gemini receipts byte-identically.

Suggested isolated new worktree `/root/workspace/project/quant-v0.6/p2-s3a-codex-sol-audit-r1` if unused; do not stash, reset, clean or modify other worktrees. No commits on `feature/v06-bline-p2-s3-footer-reader-r1` and no unrelated branch edits. Verify exact branch HEAD, target parent `30833953804bd965c80913ee6a3ecd4ae7457b40`, changed files and frozen published receipts. The code baseline itself has [GitHub Actions #38039633974](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38039633974) **PASS** `2843 passed /2 skipped`; do not infer security approval from CI.

Choose **Codex GPT-6 Sol High** if selectable. If not exposed, record actual model and effort as `NOT_EXPOSED`; no fabricated hardware/model selection claims.

## Absolute no-real-market access

The immutable owner WSL root is `/root/workspace/project/Quant-agent/data` and real BTC pilot alias is `research/BTCUSDT/1m/year=2021/month=03/data.parquet`. Both are **only literals in this audit**. Do **not** `stat`, `lstat`, `realpath`, `open`, `read`, `hash`, `scandir` any actual user data root or any original repo's market files. Tests only against **fresh synthetic temporary filesystem trees** and invented Parquet Footers. No 2026 BTC protected `[2026-02-01,2026-08-01)`, no `data/forward/**`, `h39_validation/**`, A-line/H40/H41 outcomes, private keys/accounts, market APIs, broker, TESTNET/LIVE operations. No implementation repair in this branch.

## P0 — independent authority and Git identities

Read Controller dispatch and source-level exact target without using Gemini's narrative as authority. Fetch immutable original Git metadata receipt `c6823dbc46249cac43aa10400aacbbe9f4542410:evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json` and its actual structure (`candidate_month_observations`, `additional_target_observations`), not an unstated filesystem or previous agent summary. Verify R2 changed files, frozen original R1 receipts, CI and S2 authority. Separate code correctness, source evidence consistency, and real-data authority.

## P1 — independent OS-boundary syscall accounting falsification (highest priority)

R2 `fd_syscall_wrapper.py:433-528` uses **raw `os.open("/", ...)`, `os.open(ancestor_comp, ..., dir_fd=cur_fd)`, `os.close(cur_fd)`, `os.fstat(cur_fd)`** in `open_anchored_root_dir`, bypassing metered `_raw_open/_check_syscall_budget` and its counters. Failure invokes second `_raw_open` retry, not mere logging. R2 source `types.py:_walk_and_attest_temp_root` also calls raw OS primitives. Build independent instrumentation on synthetic temp trees that wraps actual `os.open/os.fstat/os.pread/os.close` (and relevant `os.stat` / `os.scandir` if used) and records every attempted call including failures. Avoid recursion in monkeypatch and distinguish grant-attestation setup from reader-operation scope. Assert the exact *delta* `true attempted native OS events - R2 wrapper reported attempted_fs_calls_total`; report exact events and labels. Do not rely on comment counts, test fixture assertions, or expected number alone.

At minimum probe normal synthetic valid Footer, parent ancestor symlink denial, missing ancestor, permission EACCES, induced close failure and budgets `1,2,3,25,27,100`. Some low budgets may STOP correctly at wrapper level while raw OS count already exceeds cap: count both. Also consider **denial should not execute a second failed `open`** when first open already returned ENOENT/ENOTDIR; validate errno-to-status classification. Distinguish `open_fds_remaining` tracked wrapper vs actual process-held descriptors if exception occurs in unmetered root-walk before `finally`.

Results must include independent, executable assert comparing instrumentation totals; if any false claim of absolute caps persists, **FAIL HARD**. Don't patch the audited package.

## P2 — root custody/TOCTOU/rights and metadata integrity adversarial

Use only temp allowed tree plus temp fake forbidden owner surrogate. Test symlinked ancestor, multi-hop symlinks, same-device fake disallowed subtree, path replacement after custody attestation, direct self-minted grant, escaped under `/tmp`/other temp prefix, root FD scope and file identity. Do not use the real owner root as surrogate or follow an alias to it. Confirm `O_NOFOLLOW` per component, `st_dev/st_ino` custody comparators, minimum caps, correct fail-closed behavior in supplied tests; identify if an attack is unproven instead of claiming exploit without reproduction. Analyze process-local custody registry and self-signed checksum boundaries: grant is **TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION**, not a real authorization issuer, and `S3B` read remains out of scope.

Inspect Footer-byte bound (<=8 trailer +<=65536 metadata) and in-memory parser, possible hidden library IO/data-page read, resource ceilings, `close_all_open_fds` errors and partial close, cross-filesystem mount and race assumptions. Static findings can be documented when synthetic reproduction is impractical; never conflate a test with proof of all WSL mounts.

## P3 — source evidence and document contradiction gate

Original source of truth = exact Git content at `c6823dbc...`. Do not use `report.md` as source. Reconcile all six BTC month file sizes and ancillary file paths/sizes with R2 `constants.py`, R2 supplemental machine receipt, and `docs/strategy_research/g2_r3/p2_s3_footer_reader_r1/S3A_R2_BOUNDED_SECURITY_REPAIR_AND_ERRATA_REPORT.md`.

Controller has independently observed in **R2 narrative Section 4.3** statements **`research/BTCUSDT/data_manifest.json = 475 bytes` and `funding_events.csv = 424781 bytes`** while actual original immutable `c6823dbc...` receipt says **45234** and **219066** respectively, and narrative invents or borrows alternate file names. Verify exact contents; distinguish wrong narrative from corrected R2 Python constants/JSON. Publish specific anchored ERRATUM, not patch prior docs/receipts; do not let inconsistent provenance silently turn into authority.

## P4 — executable evidence, deliverables, decision

Implement new self-contained **independent audit test harness** against synthetic tempfile fixtures; target >=12 independently formulated adversarial/verification cases, including at least 5 new native-call instrumentation/negative traces (root-walk normal/negative/budget/cleanup), no copying of Gemini test function expectations. Freeze fixture provenance and hashes; report observed OS syscall totals, wrapper totals, resource impact and exact code cite lines. Run focused audit tests and Ruff (mypy only if relevant), `python -m compileall` new code/tests, JSON checks, `git diff --check`, preserve original code/old evidence unchanged. Avoid repeated 15-minute full pytest when actual GitHub CI will run after push.

Write **only new files** under:
- `reviews/v0.6/b_line/s3a_codex_independent_audit_r1/S3A_R2_CODEX_SOL_INDEPENDENT_SECURITY_VERDICT.md`
- `reviews/v0.6/b_line/s3a_codex_independent_audit_r1/S3A_R2_SOURCE_PROVENANCE_ERRATUM.md`
- `evidence/v0.6/b_line/p2_s3a_codex_independent_audit_r1/S3A_R2_NATIVE_OS_SYSCALL_TRACE_COMPARISON.json`
- `evidence/v0.6/b_line/p2_s3a_codex_independent_audit_r1/S3A_R2_CODEX_AUDIT_EXECUTION_RECEIPT.json`
- `scripts/strategy_research/p2_s3a_independent_audit_r1/**`
- `tests/test_v06_p2_s3a_independent_audit_*.py`

No modifications to existing tests, implementation, docs, machine evidence, CI, H40 or protected trees. Any test instrumenting unsafe code must use in-memory monkeypatch **and temp files only**, without actual owner path touches.

Conclude one of:
- `S3A_CODEX_INDEPENDENT_AUDIT_FAIL_HARD_SYSCALL_ACCOUNTING_OR_ROOT_ISOLATION`;
- `S3A_CODEX_INDEPENDENT_AUDIT_BOUNDED_PASS_SYNTHETIC_ONLY`;
- `INCOMPLETE_EVIDENCE_STOP`.

One non-force commit and push to **audit branch**. Return audit HEAD/parent (parent MUST exactly `999cf7005c741bdbabae727f10f90f23330fb035`), changed file list, real test counts, traced syscall delta, source provenance differences, CI final URL/outcome and exact terminal decision. If FAIL do not implement a repair in this audit: Controller decides if a bounded separate Codex implementation route or outright P2 source tool STOP. No actual real file opening or new P3/P4/Alpha/trading authority.
