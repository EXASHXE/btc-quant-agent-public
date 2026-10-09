# Gemini — Post-P1 bounded long-form P2 local data root and source readiness reconnaissance R1

**TASK_ID:** `V06_POST_P1_GEMINI_LONG_P2_METADATA_ROOT_AND_SOURCE_READINESS_R1`
**ROLE:** Gemini engineering/research data provenance auditor, standalone. Not a trading system, not source-admission authority, not a P1 repair worker. Use a capable long-context Gemini model. You are executing a **bounded substantial task**: accomplish all gates, do not stop after a smoke test and don't artificially wait.
**CONTROLLER_DISPATCH_SHA:** `858735e0ae81b1ca0ced8cfa4c2e9ee5d01532e2`. Read [binding Controller authorization](https://github.com/EXASHXE/btc-quant-agent-public/blob/858735e0ae81b1ca0ced8cfa4c2e9ee5d01532e2/reviews/v0.6/b_line/V06_POST_P1_TERMINAL_PARALLEL_P2_METADATA_AND_OPPORTUNITY_SCIENCE_CONTROLLER_DISPATCH_R1.md). READ IT BEFORE filesystem work. It is on docs branch, not ancestor of your code branch.
**REPOSITORY:** `EXASHXE/btc-quant-agent-public`.
**YOUR EXISTING REMOTE BRANCH:** `feature/v06-bline-postp1-gemini-p2-metadata-r1`.
**BRANCH START / CODE_START_SHA:** `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32` — exact `v0.6` code baseline, not docs dispatch.
**SUGGESTED FRESH WORKTREE:** `/root/workspace/project/quant-v0.6/postp1-gemini-p2-metadata-r1`; check that path does not contain unowned work, do NOT overwrite/reset/clean.
**PARALLEL OTHER TASK:** `feature/v06-bline-postp1-sol61-opportunity-science-r1`. Never read its mutable working files, wait for it, commit to it, or depend on its artifacts. Your output is a metadata-grade contract for later Controller integration.
**Prior baseline P2 evidence (read-only):** `feature/v06-bline-g2-data-readiness-sol61-r1@7f96369b1209ffdaca5d7f1233c2c9c0ae17ae29`, particularly `evidence/v0.6/b_line/g2_r3_data_readiness_fastpath/DATA_READINESS_DECISION.json`, `LOCAL_MARKET_METADATA_INVENTORY.json`, and `docs/strategy_research/g2_r3/data_readiness_fastpath/ONE_CAMPAGIN_SOURCE_AND_PREREG_FASTPATH.md`. Prior 67 BTC monthly claims and 2,934,720 declared 1m rows are **logical claims, NOT evidence of physical files**. No approved local root; ETH/SOL sources unknown; true minute mark unknown.

## Hard, non-negotiable authority fence

- P1 engine routes old VirtualBook and new event ledger **TERMINATED** by [Controller final NO-GO `fd3c13645df9ad2506293b109d3891cf57936208`](https://github.com/EXASHXE/btc-quant-agent-public/blob/fd3c13645df9ad2506293b109d3891cf57936208/reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_FINAL_INDEPENDENT_AUDIT_CONTROLLER_TERMINAL_NO_GO_R1.md). Do not patch/re-execute engine, republish old 34 PASS, or create a third engine.
- **NO empirical market file body access.** Forbidden: reading any 1m Kline/Mark/Funding price/return/OI/trade/aggTrade payload values, `head`, `cat` CSV payload, pandas/pyarrow parquet data pages, SQL SELECT on price tables, ZIP extracted payload, remote market APIs, downloading prices/funding, hashing whole data files. No private credentials/tokens/private account endpoints. No protected holdout outputs, testnet, live, real funds.
- Legacy protected BTC holdout `[2026-02-01, 2026-08-01)` (including 2026 Feb–Apr) is **sealed**: do not traverse, open, stat individual market files, enumerate contents, hash/checksum or take snapshots of protected subtree. If encountered by ancestor directory names, classify PROTECTED_EXCLUDED; do not cross into it.
- No mounts outside the allowlist, no symlink following, no hidden dot-directories (incl. .git/.ssh/.config/.cache), no scanning `/proc` `/sys` `/dev` `/run` `/etc` nor other users' home, other repos or `Quant-agent-sanitized`. No `find /`, `du -a /`, `locate`, `updatedb`, `grep -R` broad search. All output evidence Git-safe; never commit real raw market data, full machine user path secrets, private URLs or file payloads.
- **One prospective, finite exception** to old "root unknown, no further unbounded audit" is explicitly granted by this new Controller SHA: *bounded, owner project/safe data directories **metadata only**, to locate actual local root*. NOT permission to infer or certify data bodies.
- P2 source admission remains **NONE** even if ROOT_CONFIRMED, until later separate Controller method/source licence/pit review. P3/P4/future backtest/testnet/LIVE remain NONE.

## Scope — implement a reusable metadata-only locator and one finite run

Start with static config/manifest in your own checkout (read previously public/frozen docs and **text metadata only**, avoiding any protected results/performance measures). Resolve candidate path hints from known project-owned roots and known safe data mounts:
- `/root/workspace/project/quant-v0.6` (bounded shallow traversal, only owned B project subtrees)
- `/root/workspace/project` (only immediate high-level directory names for candidate project data; never enter other git repositories)
- `/root/data`, `/data`, `/mnt/data` if present and project-owned/authorized
- a literal root path supplied through the **local task input/environment explicitly by owner**, if available; never assume or invent one.
Do not scan `/root` broadly. Every candidate root must be lstat-checked (no symlink traversal), mount boundary checked where possible, owned project context established before listing deeper levels. No discovery by filename matching private dirs. With no clear ownership, emit ROOT_UNKNOWN and stop rather than expanding scope.

**Hard execution caps:** `MAX_DEPTH=5`, `MAX_DIR_ENTRIES=1500` (total scanned), `MAX_LSTAT=2500`, `MAX_SELECTED_PARTITION_LSTAT=36`, `MAX_WALL_CLOCK_SECONDS=7200` (safety cutoff, not requested waiting), `MAX_SYMLINK_FOLLOW=0`, `MAX_REAL_DATA_BODY_BYTES=0`, `MAX_PROTECTED_BODY_OR_PARTITION_FILE_ACCESSES=0`, `MAX_REMOTE_MARKET_CALLS=0`. Must stop safely when first cap is reached; exit `BUDGET_EXHAUSTED_ROOT_UNCONFIRMED` if still unknown, NEVER silently raise limits. Allowed outputs should publish actual counts and skipped entries, not generic claims. If root found early, narrow to selected safe paths, **do not consume remaining budget for its own sake**.

Only selected **2021-03/04, 2023-03/04, 2025-03/04** nonprotected candidate partitions; BTC known logical manifest 1m/year=YEAR/month=MM/data.parquet may be used for path comparison. ETH/SOL cannot be inferred to share it. Separate roles:
- actual 1m **trade-price Kline**,
- actual continuous 1m **Mark PRICE** (different from Kline; daily Mark repairs never establish full minute),
- Funding rates with economics-at, publication-available-at, settlement schedule,
- historical contract symbol tick/lot/notional/maker/taker fee metadata,
- spread/impact assumptions, exchange issuance and noncommercial licence/rights.
No source substitution or manufacture of missingness. **Physical existence does not prove schema/correctness/rights/full continuity**. Row-count declaration in Git manifest is not a verified actual parquet row count. A Parquet footer MAY be read only if independently approved and guaranteed footer metadata-only, and restrict reporting to schema column names/row-count metadata, never row-group min/max statistics or data pages. Default is **lstat-only**. CSV/ZIP content (including first header line) not allowed.

## Long execution phases (must do meaningful work across all applicable phases)

**P0 Identity and preflight**: remote origin, branch HEAD == CODE_START_SHA, clean worktree, Controller exact SHA and prompt git-blob pin, no symlink escapes, active resource counters. If dirty/unclear abort without reset/stash. Determine expected six BTC safe month paths from frozen text manifest *without reading any protected output or PnL*.

**P1 Safe script and tests FIRST**: author deterministic dry-run script with discovery plan, safe `lstat` and `os.scandir` that excludes protected dates/paths before descend, mount & symlink protections, byte-read counters, source role classification, root candidate evidence/certainty, bounded run with explicit `--approved-root` / root allowlist (no implicit absolute root `/`). Provide **≥16 focused behavioral tests** using temporary generated fake tree and tiny fake Parquet filenames (never genuine data), incl. depth exhaustion, entry cap, lstat cap, symlink to restricted path, hidden folder, protected Feb2026, repo worktree exclusions, mount escape, ENOENT vs EACCES, 1m Kline/Mark distinction, eight original asset/period boundaries, zero content reads and deterministic traversal order; actually run tests and record commands/results. Avoid `pytest` full repo suite.

**P2 One bounded actual metadata reconnaissance**: execute only if P0 scope safe, within hard caps. Record stable relative locator confidence/permission issues, lstat sizes/counts and physical POSITIVELY_IDENTIFIED matches for selected safe partitions. Log disposition UNKNOWN rather than ABSENT for unprobed paths. Absolutely no unbounded recursion or retries; no "try wider /". If project cwd cannot see historical files because data lives on another machine, classify ROOT_UNKNOWN and provide one minimal exact local owner path binding request rather than guessing.

**P3 Consequence and coverage matrix**: produce BTC, ETH, SOL × selected six safe months × 1m Kline/true1m Mark/Funding/filters/rights, with `PRESENT_METADATA_ONLY` / `MISSING_VERIFIED_SELECTED_PATH` / `UNKNOWN_UNPROBED` / `PROTECTED_EXCLUDED` / `SCOPE_DENIED`. Compute no returns/RSI/ATR/statistics. Report Option A three-symbol feasibility separately from prospective explicit BTC-only amendment (BTC-only fails unchanged original <=60% positive-support screen; cannot quietly waive).

**P4 Negative/adversarial self-review**: mutate synthetic fake tree in four stress passes (overflow path depth, malicious symlinks, logically aliased protected folder, discrepant source role), rerun and produce mutation oracle matrix. Independent row count totals and source lineage clarity. Make no claim of actual database accessibility without objective stat proof. Run Ruff on new files, compileall focused, `git diff --check`, JSON parse, path allowlist. CI repository-wide known H41 Ruff F401/S102 debt unrelated; report actual remote outcome after push, never claim green.

**P5 Evidence/push**: write under allowed prefix ONLY:
1. `docs/strategy_research/g2_r3/postp1_p2_metadata_r1/P2_LOCAL_DATA_ROOT_AND_SOURCE_READINESS_REPORT.md`
2. `evidence/v0.6/b_line/postp1_p2_metadata_r1/P2_METADATA_ROOT_AND_COVERAGE.json`
3. `evidence/v0.6/b_line/postp1_p2_metadata_r1/P2_SCAN_BUDGET_AND_TEST_RECEIPT.json`
4. `evidence/v0.6/b_line/postp1_p2_metadata_r1/P2_SCOPED_PATH_AND_PROTECTION_MATRIX.json`
5. `scripts/strategy_research/p2_metadata_locator/**`, `tests/test_v06_p2_metadata_locator_*.py` as needed for executable bounded proofs.
Publish only allowed new paths. Test isolated branch; non-force commit/push to its existing remote; verify `git ls-remote` exact final SHA, parent, whitelist and available CI. If empty root result, still publish truthful bounded code/evidence, not fake success.

**Required terminal ONE of** `P2_SELECTED_LOCAL_ROOT_CONFIRMED_METADATA_ONLY`, `P2_LOCAL_ROOT_CANDIDATE_UNVERIFIED`, `P2_LOCAL_ROOT_UNKNOWN_WITH_BOUNDED_NEGATIVE_EVIDENCE`, `P2_PROTECTION_OR_SCOPE_STOP`, `P2_BUDGET_EXHAUSTED_UNCONFIRMED`, `BLOCKED_IDENTITY_OR_SCOPE`, `BLOCKED_NOT_PUSHED`. Selected ROOT_CONFIRMED does NOT mean source admitted, real Mark complete or P4 data authorized.

**Final one-page return**: task, exact Controller dispatch/prompt SHAs, Git branch START/final remote SHA and parent, discovered eligible local root or precise UNKNOWN with one owner input, safe partition matches, role separated coverage, no-body/no-protected counters, tests/caps/CI factual, protected dates avoided, verdict, next Controller choice. Do not add a new engineering work package as a follow-up. Sol independent work is out of scope.
