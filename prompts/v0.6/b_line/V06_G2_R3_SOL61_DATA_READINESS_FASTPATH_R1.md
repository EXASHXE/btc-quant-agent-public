# G2 R3 Sol 6.1 — Data Readiness Fast Path R1

ACTIVE, **metadata-only**. Recommended executor: Codex GPT-6.1 Sol High if selectable; do not claim model selection automatically.

TASK_ID: V06_G2_R3_DATA_READINESS_FASTPATH_SOL61_R1
CONTROLLER_DISPATCH_SHA: `06d5c7bf373468a797cabf6ba906dbca29719558`
[Immutable Controller dispatch](https://github.com/EXASHXE/btc-quant-agent-public/blob/06d5c7bf373468a797cabf6ba906dbca29719558/evidence/v0.6/controller/B_LINE_G2_R3_DATA_READINESS_FASTPATH_SOL61_R1_DISPATCH.json)

Exact start `v0.6@e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`. Prior scientific draft: `fc89f05014b61c51a55141cb419948f4eee9d8f3`. Original R3 method: `cf2d5cc33774cdcff7d709636305bba830e977ef`. Work independently from Gemini A repair and Gemini B verifier; do not change their branches or files.

## Directory and branch instructions

Start shell in `~/workspace/project/quant-v0.6` (parent, not Git checkout). Locate trusted anchor worktree `g2-r3-cost-aware-method-design`. Verify its origin is exactly `EXASHXE/btc-quant-agent-public`, remote `v0.6` HEAD equals the exact start SHA, and Controller dispatch at the exact frozen commit exists. If local Git object missing or user files dirty, fail closed; no reset, clean, stash, cherry-pick, force or uncontrolled fetch.

Create a *new isolated worktree* `~/workspace/project/quant-v0.6/g2-r3-data-readiness-sol61-r1` on branch `feature/v06-bline-g2-data-readiness-sol61-r1`, only if both are absent. Coordinate Git worktree creation under the existing shared `~/workspace/project/quant-v0.6/.g2_p0_worktree.lock` using `flock -x`; do not create worktrees within another checkout. From the anchor, `git worktree add --no-track -b <branch> <worktree> e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`. Prove own HEAD/branch and clean initial status before writing.

## Precise mission — no new strategy design

Legacy BTCUSDT USD-M 1m Git manifest `artifacts/research/run0-dev-frozen-v022-seed7-20260825/data_manifest.json` records Jan2021–Jul2026, 67 monthly Parquet partitions and 2,934,720 rows. Its *physical Parquet root is not confirmed*. Old v0.3 BTC protected final holdout `[2026-02-01,2026-08-01)` **cannot** become R3 Feb–Apr development without later Controller authority.

1. Inspect **only** static source manifests/config and bounded path/filename/`lstat` metadata for expected March/April 2021, 2023, 2025 local BTC files. Locate actual root through trusted manifest/config paths. Max 120 file-stat calls. Do not recursively crawl other worktrees, entire home filesystem or follow untrusted symlinks. Check whether ETH/SOL matched historical files have credible distinct metadata. Unknown means UNKNOWN, not absent or present.
2. Do **not open, hash, parse, copy or download market price/mark/funding Parquet/CSV/ZIP bodies**, including protected months. Static manifest JSON may be read. Source archive existence or file size does not establish minute continuity or live PIT. No past H40/H41/RC2 protected outcomes.
3. Reconcile previously completed Sol scientific matrix: Option A uses March warmups and April 2021/2023/2025 development (candidate for prospective approval, not selected). Option B Feb–Apr 2026 is blocked by prior holdout. Preserve **exact eight original R3 candidates**; no returns, signals, replay or tuning.
4. Return one finite Controller decision: `FULL_THREE_SYMBOL_OPTION_A_CANDIDATE`, `BTC_ONLY_DIAGNOSTIC_AMENDMENT_RECOMMENDED`, `BLOCKED_SOURCE_OR_PROTECTION` or `LOCAL_ROOT_UNKNOWN`. State licensing/fee/funding/mark uncertainties and exact minimal future prereg/source admission needed. Do not freeze an effective prereg or grant empirical access. Do not create a new audit loop.

## Allowed changes and required delivery

Only append under `docs/strategy_research/g2_r3/data_readiness_fastpath/**` and `evidence/v0.6/b_line/g2_r3_data_readiness_fastpath/**`. Deliver (1) local metadata inventory JSON with source paths and no-price-body counters, (2) brief local-data/window decision report, (3) one-campaign source/prereg fast path, (4) gate matrix JSON, (5) git/validation receipt JSON. Report missing local files transparently.

Validate JSON, `git diff --check` and staged changed-path allowlist. Auto-commit and push **only your own branch**, no force; independently compare local HEAD to `git ls-remote --heads origin <branch>`, verify parent and changed paths. Max three hours, stop sooner if done or blocked; do not manufacture runtime. Return exact `CONTROLLER_DISPATCH_SHA`, remote final SHA, blockers and terminal verdict.

**EMPIRICAL_PRICE_BODY_AUTHORITY=NONE; TESTNET=NOT_AUTHORIZED; REAL_FUNDS_WRITE_AUTHORITY=NONE.**
