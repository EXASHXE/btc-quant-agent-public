# Gemini — S3A single-file FD reader bounded security semantics repair R2 (synthetic only)

**TASK_ID:** `V06_P2_S3A_FD_READER_ROOT_ALIAS_AND_BUDGET_SECURITY_REPAIR_R2`.
**ROLE:** Gemini B-line scoped maintenance executor. Implement ONLY the four Controller-reviewed S3A boundary/security fixes. Do not rerun the previous whole S3 design campaign; do not write a new signal/backtester/market reader workflow.
**CONTROLLER_DISPATCH_SHA:** `89c1caf07eebd3db81dc16314c3238c037e6fac3`.
**READ FIRST, BIND EXACT:** [Controller exact-SHA security HOLD and finite repair authorization](https://github.com/EXASHXE/btc-quant-agent-public/blob/89c1caf07eebd3db81dc16314c3238c037e6fac3/reviews/v0.6/b_line/V06_P2_S3A_SINGLE_FILE_FD_READER_CONTROLLER_EXACT_SHA_SECURITY_HOLD_AND_BOUNDED_REPAIR_R1.md).
**REPO:** `EXASHXE/btc-quant-agent-public`.
**EXECUTE ON EXISTING branch:** `feature/v06-bline-p2-s3-footer-reader-r1`.
**EXACT START HEAD:** `30833953804bd965c80913ee6a3ecd4ae7457b40`. Its direct parent is original code `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`; your *repair commit* MUST have direct parent `308339...` (one new commit, no squashing).
**Existing isolated worktree:** `/root/workspace/project/quant-v0.6/p2-s3-footer-reader-r1` if still owned/clean. Work there, no new code tree unless needed. Never reset/stash/clean other worker changes, force-push or touch original `/root/workspace/project/Quant-agent`, `Quant-agent-sanitized`, protected partitions or another agent's branch.

## Absolute NO REAL DATA restriction

This R2 permits **zero** OS interactions with owner market root `/root/workspace/project/Quant-agent/data` and any ancestors/children for discovery/inspection; no real market metadata lstat, scan, Parquet Footer, header, file hashing, Mark/Funding, exchange API, account, H39/H40/H41/Forward, 2026 protected dates. All syscall tests only on independently generated `tempfile`/pytest `tmp_path` trees with **invented Parquet**. Any test of a malicious owner-root alias MUST use a **temp forbidden-owner surrogate**, NEVER a symbolic link to real `Quant-agent/data`. Raw 2021-03 alias is a *prospective string only*, not a read grant. No `S3B`, P3, P4, TESTNET, LIVE, real funds.

## Four required repair gates; do not declare PASS on a superficial unit test

### F01 — trusted fixture root custody and ancestor symlink escape
Root cause: `reader.py` accepts any caller-supplied `synthetic_fixture_root` and `fd_syscall_wrapper.py:323` uses absolute `os.open(root_path,O_NOFOLLOW)`, where `O_NOFOLLOW` constrains only the final path component; untrusted symlink ancestors/mount aliases may follow into the owner root, while `assert_not_owner_data_root` is lexical only.

- Write an **actual runnable adversarial regression** using two temp trees: a fixture allowed tree and an entirely temp forbidden-owner surrogate, plus an ancestor symlink alias of the surrogate, and show old unguarded behavior would have accepted or reached the forbidden fake target; repaired reader must reject BEFORE reading its Footer. Also test multiple parent symlinks, path `../`, hardlinks, relative/absolute aliases, dangling/renamed parent, and if possible a mock bind-mount equivalent. Use temp fake source only; no real owner path.
- Eliminate the insecure `os.open(untrusted_absolute_synthetic_fixture_root)` path as a security boundary. Prefer **trusted test-harness supplied pre-opened directory FD / securely anchored path traversal** with explicit provenance attestation that the fixture FD came from a freshly created test-owned temp directory and exact inode/dev expectations; never allow untrusted caller path to self-declare ownership. A simple `os.path.realpath` string check alone, `O_NOFOLLOW` on leaf alone, or `stat` after opening through untrusted ancestors are NOT sufficient independent proof. Must fail closed if trusted FD/custody unavailable; return `S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN`. If isolation guarantee cannot be proven in this one repair, keep the implementation test-only and report unresolved root threat as terminal FAIL/HOLD rather than exposing a production-style callable.
- R2 remains synthetic-only even if this succeeds: **no production/root read grant**, no broad path override, no owner root file access.

### F02 — honest synthetic token semantics
- Existing `SyntheticTestGrant.compute_expected_signature()` uses public SHA-256 and `create_valid_synthetic_grant()` generates it. It is **not HMAC** and **not independent issuer authorization**.
- Label it `TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION` clearly across API/docs/receipts or replace it with externally injected non-self-issuable test-only harness capabilities; no secret in source. Explicit tests show a caller can recompute the old checksum and that a self-minted token **never grants production/owner-root access**. Do not present the checksum as a real security signature, owner permission or future S3B token.

### F03 — syscall cap and FD cleanup invariant
- Fix `fd_syscall_wrapper.py:211-223` reservation logic so **first** root FD open also reserves its close; run adversarial `max_attempted_fs_calls=1,2,3,25,27,100` and prove attempts never exceed cap (including failed calls, cleanup closes), no FD leaked on all tested exits, bounded error classification `BUDGET_INSUFFICIENT_STOP` not continued. Avoid `os.close` exception aborting cleanup of other live FDs; separately count failed close attempts and show failure mode is not falsely PASS. Verify actual calls from injected syscall hooks or temp filesystem instrumenting, NOT counting distinct paths or solely test prose. Do not create a new OS helper that bypasses metering.

### F04 — exact immutable S1 BTC six-file metadata truth
- Read only **Git-published** original immutable machine receipt `c6823dbc46249cac43aa10400aacbbe9f4542410`, never current WSL data. Correct five non-pilot S3A constants:
  - 2021-04 **2,621,313** (not 2,492,430)
  - 2023-03 **2,415,597** (not 2,672,321)
  - 2023-04 **2,201,521** (not 2,075,555)
  - 2025-03 **2,352,476** (not 1,970,619)
  - 2025-04 **2,329,220** (not 1,942,082)
- The pilot 2021-03 remains **2,756,024**. Cross-asset four prior S2 errata remain correct as per `9782c...`. Implement a regression checking every (path,size) pair against **pinned original JSON parse**, not a same-file self-echo of constants. ETH/SOL true 1m is UNKNOWN, not ABSENT.
- **Do not rewrite or delete initial S3A R1 receipt and oracle JSON**, which are frozen evidence of what R1 claimed. Add **new clearly marked R2 supplemental** machine evidence under `evidence/v0.6/b_line/p2_s3_footer_reader_r1/**`, with supersedes paths and old→new field mapping. Source-level constants/tests/docs updates within original S3A-only files are authorized, but immutable R1 published reports remain intact; optional add an R2 erratum doc.

## Finite verification and publication
Allowed changed files **ONLY**:
- `scripts/strategy_research/p2_s3_footer_reader/**`
- `tests/test_v06_p2_s3_footer_reader_*.py`
- **New** `docs/strategy_research/g2_r3/p2_s3_footer_reader_r1/S3A_R2_*.md`
- **New** `evidence/v0.6/b_line/p2_s3_footer_reader_r1/S3A_R2_*.json`.

No changes to original 15-file R1 docs/evidence, S1/S2 methods/receipts, CI, H40 tests, source data, old P1 engine or unrelated branches. Maintain >=45 original passing scoped tests plus meaningful NEW adversarial regressions, local `ruff check`, focused pytest, compile, JSON check, `git diff --check`. Avoid lengthy repeated full pytest; exact GitHub CI will run on push. Have a scoped observed test assertion for parent-symlink alias, low-cap=1, public token self-issue, all six recorded sizes. Record run IDs; inherited H40 golden assertion must be reported as full CI red but NOT fixed via test skip/method change.

Push **one non-force repair commit** with message metadata `TASK_ID`, `CONTROLLER_DISPATCH_SHA=89c1caf07eebd3db81dc16314c3238c037e6fac3`, `EXACT_START_SHA=30833953804bd965c80913ee6a3ecd4ae7457b40` to the same `feature/v06-bline-p2-s3-footer-reader-r1`. Return exact parent/head, change list, scoped pass count, os-level attempted call and bytes accounting evidence, root-alias + grant regression results, immutable original evidence hashes, GitHub Actions URL/outcome, and one terminal:
- `S3A_R2_BOUNDED_SECURITY_REPAIR_DELIVERED_PENDING_CONTROLLER_SOL_AUDIT` if all finite gates genuinely pass;
- `S3A_R2_ROOT_ISOLATION_UNPROVEN_STOP`;
- `S3A_R2_BUDGET_OR_EVIDENCE_CONTRACT_FAILED_STOP`;
- `BLOCKED_IDENTITY_OR_SCOPE`.

**Next is independent Sol High implementation security review bound to your frozen FINAL commit only after Controller GitHub re-verification.** No owner file content reads without later separate S3B authorization plus owner rights/consent. Do not conflate engineering gate with market source admission or Alpha.
