# Gemini — P2 exact-root metadata verifier ONE bounded CI + fail-closed semantic repair R1

**Task:** `V06_P2_OWNER_EXACT_ROOT_CI_AND_SYMLINK_FAIL_CLOSED_REPAIR_R1`. **Role:** Gemini scoped verifier-maintainer, NOT market research or a trading executor.
**CONTROLLER_DISPATCH_SHA:** `52830a73adf9e8c318da8efa8f10c6323a6292b8`. Read binding [Controller source-evidence accept, verifier quality-HOLD and exact repair contract](https://github.com/EXASHXE/btc-quant-agent-public/blob/52830a73adf9e8c318da8efa8f10c6323a6292b8/reviews/v0.6/b_line/V06_P2_OWNER_EXACT_ROOT_CONTROLLER_L2_METADATA_EVIDENCE_AND_CI_SEMANTIC_REPAIR_R1.md).
**Code repo:** `EXASHXE/btc-quant-agent-public`.
**Reuse existing REMOTE branch:** `feature/v06-bline-p2-owner-exact-root-metadata-r1`, **REQUIRED START EXACT SHA** `c6823dbc46249cac43aa10400aacbbe9f4542410` (direct child of `1e12d6a6467d3bc39c0deedd97204604ac623f18`). Worktree `/root/workspace/project/quant-v0.6/p2-owner-exact-root-metadata-r1` if genuinely owned; never reset/stash/remove user or other agent's work. If remote HEAD changed, STOP and report before writing.
**Original evidence**, frozen and DO NOT MODIFY:
`docs/strategy_research/g2_r3/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_METADATA_REPORT.md`;
`evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json`;
`evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_SELECTED_SOURCE_TYPE_AND_PERMISSIONS_MATRIX.json`.
The six historical month metadata files already have executor-observed lstat presence; this is NOT a license to open Parquet/CSV, hash datasets, descend into 2026, or rerun root search. Future Controller adjudicates true PIT/Mark/Funding/source admission separately.

## Why repair (independently verified CI, not guesses)

[Current CI `38014778959`](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38014778959) **failed before pytest** due 20 Ruff violations in only new verifier package/tests. Categories include I001, RUF022, F401, F541, ISC004, BLE001, RUF059. Do not misattribute to inherited H40. Prior "17 PASS" was local executor-reported, NOT CI. Most importantly:
- `probe.py:221`: `except Exception: pass` on fallback alternate Parquet path swallows security/budget failures and makes a hard halt look like legitimate unavailable file.
- `probe.py:102,241`: broad exception handlers collapse permission/unexpected-error identity; must catch precise expected OS exceptions and propagate hard-stop errors.
- Intermediate path `BTCUSDT/1m/year=YYYY/month=MM/data.parquet` is only leaf-checked for symlink. Symlink at `1m` or `year=YYYY` can cause traversal before leaf `lstat` (normal `os.lstat` does not protect earlier path components). Enforce fail-closed **every intermediate path component**, including alternate filename path, no symlink follow, and approved exact root outside Git worktree.
- User-provided WSL root is `/root/workspace/project/Quant-agent/data`, BUT DO NOT OPEN OR EVEN STAT ITS REAL DATA IN THIS REPAIR. All negative tests must be synthetic temporary trees only. Avoid foreign `Quant-agent` git writes; do not touch `Quant-agent-sanitized`.
- Check `os.path.exists()` preflight (it follows symlinks) and CLI arbitrary root path handling; ensure fixture injected root path in tests is allowed in explicit TEST fixture mode without weakening production root whitelist. Do not let naive string-prefix root checks accept `data-v2` or `..` escaping actual root.

## Required scope and real execution

1. Exact remote identity, immutable dispatch/prompt inspection, clean own worktree and original reports hash records.
2. Fix **all 20 present Ruff violations**, no blanket `# noqa` or repo-wide lint exclusion, especially broad catch. Do not change unrelated H40/H41. Keep `__init__`, `cli`, `config`, `probe`, `matrix` readable and maintain existing 6-month positive reporting semantics.
3. Implement strict path-component and owner-root guard, exceptions for permission vs missing and security/budget propagation, and bounded alternate-name probing in a **single coherent semantic change**. MAX_LSTAT100, MAX_SELECTED_LIST6, MAX_ENTRIES16, forbidden protected `2026-02..07`, `forward/`, `h39_validation/` and any source/body reading still zero. Do not auto-unseal any extra month.
4. Add focused REAL pytest adversarial negative cases **beyond old17**: intermediate symlink at 1m, at year=2021, at selected month, symlink leaf, malicious alternate name, unexpected PermissionError (never ABSENT), cap limit raising within alternate probe, fake root escaping, protected path rejection even on fallback, hard stop propagation. Prefer parametrized but assert actual guards invoked; test a valid alternate filename in synthetic temp tree and 6-month normal happy path. Tests that mutate a generated fake tree are permitted; **never manipulate physical market data**.
5. Run `ruff check scripts/strategy_research/p2_owner_root_metadata tests/test_v06_p2_owner_root_metadata_*.py` against final bytes; `python3.12 -m pytest -q tests/test_v06_p2_owner_root_metadata_*.py`, optionally Python3.13 if available; `python -m compileall` scoped, `git diff --check`, JSON parse / no protected path & changed-file allowlist. Report exact counts/errors, no invented PASS.
6. Write **NEW** supplemental `docs/strategy_research/g2_r3/p2_owner_root_metadata_r1/P2_VERIFIER_SECURITY_AND_CI_REPAIR_R1.md` and `evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_VERIFIER_REPAIR_EXECUTION_RECEIPT_R1.json`: fixed baseline SHA and new parent, rules changed, all negative tests actually run, 20→0 Ruff delta, controlled repo test matrix, synthetic-only/no-market-byte counters. Do not overwrite original six-month JSON/stat evidence.
7. One non-force coherent commit and push to **same** remote branch, verify final remote SHA, exactly one direct parent `c6823dbc46249cac43aa10400aacbbe9f4542410`, allowed changes limited to:
   - `scripts/strategy_research/p2_owner_root_metadata/**`
   - `tests/test_v06_p2_owner_root_metadata_*.py`
   - NEW supplemental docs/evidence under `docs/strategy_research/g2_r3/p2_owner_root_metadata_r1/**`, `evidence/v0.6/b_line/p2_owner_root_metadata_r1/**`
   - NO baseline receipt changes; NO shared configs/old engines or research data.
8. Inspect final remote CI. If it now fails H40 Golden **after** scoped Ruff and focused test passes, classify as `P2_VERIFIER_SCOPED_ACCEPTABLE_PENDING_CONTROLLER_GLOBAL_CI_DEBT`, not global green. If Ruff or targeted tests still fail, terminal `P2_VERIFIER_REPAIR_FAILED_STOP`. No endless repair loop or automatic third reviewer.

**Required terminal:** `P2_VERIFIER_ONE_SHOT_REPAIR_DELIVERED_PENDING_CONTROLLER`, `P2_VERIFIER_REPAIR_FAILED_STOP`, `BLOCKED_IDENTITY_OR_SCOPE`, or `BLOCKED_NOT_PUSHED`. No P2 SOURCE_ADMITTED, P3/P4, Alpha, TESTNET/LIVE authority in any disposition.

**Final report:** SHA lineage, changed file list, signed test counts, original immutable report preserved, real CI run link and exact reason, adversarial exception/symlink demonstrations, semantic limitations and new terminal. Do not ask user again for owner root or perform an unbounded historical scan.
