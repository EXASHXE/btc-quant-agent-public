# TASK-S9-D2-FIX-AND-REGRESSION-20261128 — Wave D2 S9 Remediation & Inherited Regression (P1)

> PUBLIC HISTORICAL TASK CONTRACT — private identifiers omitted; not new authorization.


- **Authorization**: `OWNER_CONFIRMED_T3_DISPATCH` (single Owner-approved serial dispatch following WSL 3.5 GiB RAM upgrade and Sol WEB independent QA `FIX_REQUIRED_BEFORE_ACCEPTANCE`).
- **Executor**: AGY-A `gemini-4-neon` XHigh (reuse thread `[private thread ID omitted]`, Run 2).
- **Accountable & Independent QA**: Sol WEB (strictly NO Neon self-acceptance; do not claim acceptance).

## 1. Baseline & Strict Write Set
- **Worktree**: `[private isolated worktree]`
- **Branch**: `feat/waved-s9-strategy-runtime-20261128`
- **Exact Base Commit**: `a27cf2d9f19edb857fcd24bf3cddf8457f53916d` (verify clean worktree and exact HEAD before editing).
- **Authorized 9-File Write Set ONLY** (existing S9 files introduced in `a27cf2d9`):
  1. `strategy_contracts.py`
  2. `strategy_b2_adapter.py`
  3. `strategy_catalog.py`
  4. `strategy_selection.py`
  5. `strategy_journal_v2.py`
  6. `strategy_runtime.py`
  7. `tests/phase02/test_s9_strategy_journal.py`
  8. `tests/phase02/test_s9_strategy_runtime.py`
  9. `docs/S9_STRATEGY_RUNTIME_CONTRACT.md`
- **Forbidden**: ZERO edits to frozen B2 kernel, `quant_core`, `quant_transport`, `quant_research`, `infrastructure`, or any existing tests/files outside the exact 9 S9 files above.

## 2. Required Remediation Items (Close All 4 Findings)
1. **`S9-F01` (P1 — Fail-closed explicit selection without approval)**:
   - In `strategy_selection.py` (around lines 807–823), disallow explicit operational selection when `approval_path=None`; fail closed with `APPROVAL_REQUIRED_FOR_EXPLICIT_SELECTION`.
   - Preserve the absent-file frozen B2 default behavior.
   - Isolate synthetic mode behind an explicit opt-in flag `allow_unapproved_synthetic=False` (default `False`).
   - Add/update tests verifying fail-closed explicit selection, absent-file frozen B2 default, and synthetic opt-in isolation.
2. **`S9-F02` (P1 — Shared market generation end-to-end without touching frozen B2)**:
   - In `strategy_runtime.py` (around lines 791–796, 849), stop opening a separate `MarketSnapshotAdapter` for B2.
   - Implement `SharedGenerationSnapshotAdapter(MarketSnapshotAdapter)` inside the authorized S9 files WITHOUT modifying the frozen B2 kernel so B2 consumes `SharedMarketGeneration` end-to-end.
   - Prove `acquisition_count == 1` in unit tests.
3. **`S9-F03` (P1 — Pre-commit snapshot drift guard)**:
   - In `strategy_runtime.py` (around line 909), move `verify_snapshot_unchanged()` to execute BEFORE drain/eligible commits.
   - Add a unit test proving zero partial commit occurs on snapshot drift.
4. **`S9-F04` (P2 — Normalized vs. fixed-clock raw byte parity)**:
   - Relabel the wall-clock-excluded parity check in `B2_BYTE_PARITY_RECEIPT.json` (and contract docs) as `normalized_byte_parity`.
   - Add a fixed-clock test verifying 100% full raw byte parity (including `journal_recorded_wall_ms`).

## 3. Verification, Commit & Heavy Regression (`S9-A09`)
1. Run `ruff check` on the 9-file write set (`0` errors).
2. Run targeted S9 tests and `test_s6_dependencies.py` inside an isolated loopback-only network namespace (`unshare -n`).
3. Commit locally on `feat/waved-s9-strategy-runtime-20261128` as a single child of `a27cf2d9f19edb857fcd24bf3cddf8457f53916d`. Verify `git status` is clean and `git diff --name-only a27cf2d9..HEAD` contains only paths within the authorized 9-file write set.
4. Acquire the shared cooperative heavy lock `/tmp/quant-wave-d-heavy.lock` (one heavy process group at a time; verify `MemAvailable >= 1200 MiB`, peak RSS target `<= 1000 MiB`, single worker, no OS-enforced memory limit claims; stop cleanly with `RESOURCE_HOLD` if unsafe).
5. Under the lock (offline loopback-only `unshare -n`), execute the inherited `S9-A09` full core/frozen/radar regression suite (`0` failed, `0` unexpected skipped). Measure and record sampled peak process-group RSS and lock inode.
6. Regenerate all receipts (including `B2_BYTE_PARITY_RECEIPT.json`, `FINAL_WRITE_SET.txt`, regression logs/JUnit XML, and `SHA256SUMS`) under `/tmp/quant-wave-d2-s9-20261128/` and verify `sha256sum -c SHA256SUMS` exits `0`.

## 4. Hard Safety Boundaries
- Execute this exact bounded task only; no further dispatch or subagent delegation.
- No live market, model, or Feishu calls; no secrets/chat/memory reads; no holdout enumeration/stat/hash; no deployment, service restart, timer changes, git merge, push, or tag.

## 5. Required Handoff Output
Return exactly one terminal status:
- `READY_FOR_INDEPENDENT_SOL_WEB_QA`
- `RESOURCE_HOLD`
- `BLOCKED_WITH_EVIDENCE`

Include exact commit hash, diff file list, `ruff` result, targeted test counts, inherited `S9-A09` regression counts, pre-start `MemAvailable` and sampled peak RSS, and verified receipt/SHA256SUMS paths under `/tmp/quant-wave-d2-s9-20261128/`.
