# v0.6 G2 R3 — Sol High Scientific Gate, Historical Data Reuse & Preregistration DRAFT R1

## Dispatch identity (active scientific analysis; NOT empirical/replay authority)

- TASK_ID: V06_G2_R3_SOL_SCIENCE_GATE_R1
- CONTROLLER_DISPATCH_SHA: `647e2e6e1e2e375817ec7a07f2ea11fc57484827`
- Immutable scoped controller authority: https://github.com/EXASHXE/btc-quant-agent-public/blob/647e2e6e1e2e375817ec7a07f2ea11fc57484827/evidence/v0.6/controller/B_LINE_G2_R3_SOL_SCIENCE_GATE_R1_DISPATCH.json
- Repository: `EXASHXE/btc-quant-agent-public`
- Exact code baseline `v0.6@e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`
- Exact Controller-accepted design-only R3 method addendum `cf2d5cc33774cdcff7d709636305bba830e977ef` on `feature/v06-bline-g2-r3-cost-aware-method-design`. Original eight-strategy registry exists at `e5b2006a89441f7eb2ec900e508aff451106b87a`; do not alter it.
- Role: **Sol High**, independent scientific methodology and authority-boundary reviewer. NOT third strategy alpha searcher, not production execution agent, not authorized to make the preregistration freeze effective.
- User starts from the shared parent `~/workspace/project/quant-v0.6` on Linux/WSL. Your OWN worktree will be `~/workspace/project/quant-v0.6/g2-r3-sol-science-gate-r1` and OWN branch `feature/v06-bline-g2-r3-sol-science-gate-r1`.
- Existing active parallel tasks: Gemini A `feature/v06-bline-g2-overnight-discovery-a` synthetic candidate replay skeleton, Gemini B `feature/v06-bline-g2-overnight-verifier-b` independent synthetic oracle; P0 dispatch `56f8a9faa1a4539124ab006b49bf42b6e7c997e3`. Both have ZERO permission for real empirical data. Do not block, update, cherry-pick or reset their worktrees/branches.

## What to deliver — focus on eliminating the NEXT scientific Controller blocker

**Objective:** produce an exact-SHA reviewable, one-pass proposed R3 research freeze specification by resolving the old BTC historical holdout overlap, local verified-data reuse planning, valid statistical decision rules, and data licence/source authority tiers. No price access or new scientific trial is needed or permitted. Commit/push design-only artifacts. The Controller, not Sol, will decide whether a subsequent frozen prereg and data-body admission is safe.

### Task 1: historical exposure/holdout authority matrix — the critical gate

- The prior v0.3 BTC data audit declared `[2021-01-01, 2026-02-01)` **development** and `[2026-02-01, 2026-08-01)` **final HOLDOUT**. The newer R3 design proposed Jan warmup/Feb–Apr 2026 development, which overlaps the old final HOLDOUT. R2 already developed on May–Jul 2026 BTC/ETH/SOL; that exposure does not itself cancel or refresh the prior v0.3 protection.
- Resolve documents and *metadata-only* evidence into a compact month/asset/authority matrix for BTC/ETH/SOL covering 2021-01 through 2026-07 with explicit `PROTECTED_OR_DISPUTED`, `EXPOSED_DEVELOPMENT`, `SOURCE_UNCONFIRMED` and `CONTROLLER_DECISION_REQUIRED` statuses. Do not infer ETH/SOL old five-year coverage, do not inspect prior sealed outcome or RC2 result files. A missing authoritative release document is `UNVERIFIED`, not permission.
- Propose **Option A (default)** frozen new R3 development windows entirely within previously authorized nonprotected BTC development, such as 2021–2025 UTC historical archive months selected for scientific regime diversity **without viewing new outcomes**, with asset-comparability restrictions clearly identified. If other assets lack these months, do not silently replace them. **Option B** retains Feb–Apr 2026 only after an explicit separate Controller protection reconciliation/reclassification grant, not because a previous agent read those prices. A true future independent validation sample must remain separately sealed or contemporaneously collected.
- Specify how older R1/R2/v0.3 strategy attempts and exposed months enter a **global attempt/exposure ledger**: one 8-variant R3 family; R2 variants remain previous attempts, no selecting winners by old subgroup results; no artificial fresh OOS from a redownload.
- Output `docs/strategy_research/g2_r3/science_gate/PRIOR_HOLDOUT_EXPOSURE_AND_AUTHORITY_MATRIX.md` with evidence-graded cells, unresolved blockers and default fail-closed partition recommendation. Do not claim the Controller approved unsealing.

### Task 2: reusing multi-year existing BTC without crossing data privilege

- Read ONLY the existing Git **text/JSON manifest**, not Parquet/candle/mark/funding content: `artifacts/research/run0-dev-frozen-v022-seed7-20260825/data_manifest.json` at exact `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`. Previously audited BTCUSDT USD-M perpetual 1m Jan2021–Jul2026, 67 months, 2,934,720 rows, funding 6,114 events, 210 source ZIP checksums, canonical logical SHA256 `82d058b2e9e5bfbd20bf36026abec045fb778ddb72582277e0dac00846ae9901`.
- Identify explicit manifest-to-current-R3-schema compatibility needs: symbol, product, UTC 1m, source and reconstructed availability, separate true mark candle time path, funding cashflow settlement/cap caveat, source checksum/permission and old daily mark repair. The 67 parquet files' current physical availability has NOT been independently verified. Existing `data_manifest.json` alone does not establish current disk bytes.
- Prepare only **bounded file-names/stat metadata inspection** when paths are positively identified from trusted manifests or config; no root-wide recursive walk, no following unknown symlinks, no opening market row bodies, no hash of sealed Parquet bytes under this task. Record physical-presence status `PRESENT_METADATA_ONLY` or `NOT_VERIFIED`. ETH/SOL multi-year coverage unknown until a separately authorized inventory.
- Propose a future read-only content-addressed or symlinked immutable source cache suitable for Gemini A/B, without modifying original data, exposing older protected months or duplicating raw archives into Git. Distinguish ARCHIVAL_EVENT_TIME_RECONSTRUCTED from CONTEMPORANEOUS_RECEIPT_PROVEN_FORWARD. No historical OI/L2/taker-ratio PTI inference from klines.
- Output `docs/strategy_research/g2_r3/science_gate/LOCAL_DATA_REUSE_AND_WINDOW_FREEZE_OPTIONS.md` including cost/time savings and explicit `NOT_VERIFIED` points.

### Task 3: freeze-ready DRAFT of one finite eight-candidate development trial, but DON'T FREEZE

- Read the original fixed eight proposed `STRUCTURAL_CONTINUATION` and `CLOSED_RETEST` LONG/SHORT ×4h/12h registry at exact `e5b2006a89441f7eb2ec900e508aff451106b87a`; copy **IDs and hypotheses unchanged**, not guessed from prose. Use accepted method `cf2d5cc33774cdcff7d709636305bba830e977ef` for two-ledger clock, availability lag, next-entry bar, stop-first, funding reserve, equity/intrabar risk, adverse gaps.
- Write an explicit **DRAFT** future R3 prereg plan specifying allowable symbol-month partitions with `PENDING_CONTROLLER_SELECTION` where any protection or source gate unresolved; candidate formulas and 8 unique IDs; one campaign and zero hyperparameter sweeps; controlled source manifest, 1m trade+mark available at time, stale/gap fail-close; 22/44bps base/stress plus funding assumptions, fees/tick/lot and legality risk grade; 1x/5% reserve/10% MTM kill; PAUSE/control portfolios and cost-case ledger independence; finite time/request/size budget and termination semantics.
- Must use original ≥100 trades/fold positive candidate support as proposal and separately predefine prospective low-n negative diagnostic, upper-confidence-bound based supported economic NO_GO, global 8×2 multiplicity/cross-asset clustering and min +5bp meaningful net edge. Do **not** relax any threshold after observed results. Unsupported costs → at most PROXY_DIAGNOSTIC_ONLY; no alpha or release PASS.
- Explicitly flag 12h stressed funding schedule geometry scenario `12×8bp + 44bp = 140bp total`, risk hurdle `2× = 280bp > 250bp proposed max stop` as `STRESS_COST_GEOMETRY_INELIGIBLE`, **not** empirical failure. Do not rescue it via new parameters or unmeasured maker fills.
- Importantly **DO NOT** create the FIRST_PUSHED_PREREG_SHA, do not seal/dispatch an empirical trial, do not fetch one minute of actual new prices/returns. Your output is `DRAFT`, and cannot serve as the future data-access authority.
- Outputs `docs/strategy_research/g2_r3/science_gate/R3_EIGHT_CANDIDATE_PREREG_DRAFT.md` and `docs/strategy_research/g2_r3/science_gate/SCIENCE_ECONOMICS_AND_POWER_GATES.md`.

### Task 4: final gate matrix and handoff

- Write `evidence/v0.6/b_line/g2_r3_science_gate/SCIENCE_GATE_MATRIX.json` with each gate's verdict (`READY_FOR_CONTROLLER_REVIEW`, `PENDING_EXTERNAL_SOURCE`, `DISPUTED_PROTECTED_WINDOW`, `PROXY_ONLY`, `BLOCKED`) and concrete required next fact/authority; no blanket PASS. Include reproducible sources, regulatory/licence uncertainties, BTC/ETH/SOL local coverage, event clock, frozen candidate budget, 8x2 multiple testing, cost/funding, H40 inherited test and G3 nontrading separate tracks. Historical issuer terms may permit noncommercial research but must not be treated as a blanket licence for live/commercial signal services.
- Write `evidence/v0.6/b_line/g2_r3_science_gate/SCIENCE_GATE_RECEIPT.json`: exact Controller dispatch SHA, baseline and method SHAs, input blob identity, outputs, changed paths, no-market-body/no-holdout/no-trade claims, test/lint/JSON/diff-check receipts and remote push verification. Never fabricate physical Parquet file status, sealed-data authority or chronology.
- **Terminal one of:** `G2_R3_SCIENTIFIC_GATE_DRAFT_READY_FOR_CONTROLLER` / `G2_R3_PROTECTION_CONFLICT_REQUIRES_CONTROLLER` / `G2_R3_DATA_SOURCE_ADMISSION_BLOCKED` / `BLOCKED_SCOPE_OR_WORKTREE` / `BLOCKED_NOT_PUSHED`. Protection conflict may coexist with an otherwise complete draft and must remain visible. Give an **explicit** recommendation: finite diagnostic replay after future grants versus stop/repair; do not request more rounds of unlimited metadata audit.

## Code / data / trade hard fences

ONLY changed paths: `docs/strategy_research/g2_r3/science_gate/**` and `evidence/v0.6/b_line/g2_r3_science_gate/**`. No source, scripts, tests, config, `.github`, Controller authority JSON, previous R3 docs, v0.3 code/manifest mutation, A/B P0 artifacts or whole project roadmap edits. Read only **named static published metadata and scientific spec/report sources** (not sealed outcome or private body paths). Zero new price/mark/funding rate contents, candidate test runs on historical data, orders, TESTNET, provider/signed private APIs and protected RC2 access. Never convert existing JWT/credential access into an implicit research grant.

## Git execution from shared ROOT — only your OWN branch

Run in your own Sol terminal from `~/workspace/project/quant-v0.6`. The parent is NOT necessarily a Git checkout. Existing trusted anchor checkout `g2-r3-cost-aware-method-design` is read-only to you. Never use/modify its current branch or files. Do NOT call `git init` or `git clone` in the ROOT. If ROOT itself is an active worktree, stop rather than nest another. Identity preflight:

```bash
set -euo pipefail
ROOT="$(cd "$HOME/workspace/project/quant-v0.6" && pwd -P)"
ANCHOR="$ROOT/g2-r3-cost-aware-method-design"
test -d "$ANCHOR" || { echo 'BLOCKED_ANCHOR_MISSING'; exit 2; }
test "$(cd "$(git -C "$ANCHOR" rev-parse --show-toplevel)" && pwd -P)" = "$(cd "$ANCHOR" && pwd -P)" || { echo 'BLOCKED_ANCHOR_NOT_ROOT'; exit 2; }
remote="$(git -C "$ANCHOR" remote get-url origin)"
case "$remote" in
  'https://github.com/EXASHXE/btc-quant-agent-public'|'https://github.com/EXASHXE/btc-quant-agent-public.git'|'git@github.com:EXASHXE/btc-quant-agent-public.git'|'ssh://git@github.com/EXASHXE/btc-quant-agent-public.git') ;;
  *) echo 'BLOCKED_UNEXPECTED_ORIGIN'; exit 2;;
esac
git -C "$ANCHOR" worktree list --porcelain
test "$(git -C "$ANCHOR" ls-remote --heads origin v0.6 | awk '{print $1}')" = 'e0ff8c3473de4bfa3e66fe7928d42992a4d38a32' || { echo 'BLOCKED_BASE_BRANCH_DRIFT'; exit 2; }
test "$(git -C "$ANCHOR" ls-remote --heads origin feature/v06-bline-g2-r3-cost-aware-method-design | awk '{print $1}')" = 'cf2d5cc33774cdcff7d709636305bba830e977ef' || { echo 'BLOCKED_METHOD_BRANCH_DRIFT'; exit 2; }
git -C "$ANCHOR" cat-file -e 'e0ff8c3473de4bfa3e66fe7928d42992a4d38a32^{commit}' || { echo 'BLOCKED_BASE_OBJECT_NOT_LOCAL'; exit 2; }
```

Verify exact Controller dispatch record under `CONTROLLER_DISPATCH_SHA=647e2e6e1e2e375817ec7a07f2ea11fc57484827` by remote immutable SHA, not latest docs HEAD. The branch must descend exactly from the pinned code baseline. This task is **separate** from both Gemini P0 branches. Use same `flock` lock as A/B for shared Git metadata operations, but no shared writable repository or data files:

```bash
command -v flock >/dev/null || { echo 'BLOCKED_NO_FLOCK'; exit 2; }
BRANCH='feature/v06-bline-g2-r3-sol-science-gate-r1'
WT="$ROOT/g2-r3-sol-science-gate-r1"
(
  flock -x 9
  test ! -e "$WT" || { echo 'BLOCKED_WORKTREE_COLLISION'; exit 2; }
  if git -C "$ANCHOR" show-ref --verify --quiet "refs/heads/$BRANCH"; then echo 'BLOCKED_LOCAL_BRANCH_EXISTS'; exit 2; fi
  test -z "$(git -C "$ANCHOR" ls-remote --heads origin "$BRANCH")" || { echo 'BLOCKED_REMOTE_BRANCH_EXISTS'; exit 2; }
  git -C "$ANCHOR" worktree add --no-track -b "$BRANCH" "$WT" 'e0ff8c3473de4bfa3e66fe7928d42992a4d38a32'
) 9>"$ROOT/.g2_p0_worktree.lock"
test "$(git -C "$WT" rev-parse HEAD)" = 'e0ff8c3473de4bfa3e66fe7928d42992a4d38a32' || { echo 'BLOCKED_BASE_SHA'; exit 2; }
test "$(git -C "$WT" branch --show-current)" = "$BRANCH" || { echo 'BLOCKED_BRANCH'; exit 2; }
cd "$WT"
```

Prepare at most the 6 new allowlisted docs/evidence deliverables. `git diff --check`; JSON parse; inspect `git diff --cached --name-only` before committing. **Auto-commit and push** own feature branch with `git push -u origin "$BRANCH"` (never force). Independently `git ls-remote --heads origin "$BRANCH"` must equal local HEAD, verify parent, changed-path whitelist and immutability of original registry/source. If unable to push, `BLOCKED_NOT_PUSHED`.

Keep task bounded to ≤3 hours and stop early when deliverables are ready; do not spend a night reading entire historical science archive. If a protected-policy ambiguity cannot be closed from public authority text, present both lawful Controller choices and mark the gate unresolved. No direct merge to v0.6. H40 CI baseline issue and G3 provider smoke do not belong to this Sol task. Real funds/TESTNET remain NONE.

**Return:** `CONTROLLER_DISPATCH_SHA=647e2e6e1e2e375817ec7a07f2ea11fc57484827`, exact remote branch/SHA/parent, files, research window candidates (no outcomes), holdout gate and licensing statuses, all eight candidate IDs, cost/power rule status, provenance and `REAL_FUNDS_WRITE_AUTHORITY=NONE`.