# G2 R3 Gemini A — Active Parallel P0 Synthetic Strategy Build

**Role A: `GEMINI_A` / Synthetic Replay & Candidate Implementation.**
```bash
ROLE_DIR=g2-overnight-discovery-a
ROLE_BRANCH=feature/v06-bline-g2-overnight-discovery-a
```

## Controller and execution authority — MUST verify
Task `V06_G2_R3_PARALLEL_P0_OFFLINE_PREPARATION`.
**CONTROLLER_DISPATCH_SHA=56f8a9faa1a4539124ab006b49bf42b6e7c997e3**
Frozen Controller record: https://github.com/EXASHXE/btc-quant-agent-public/blob/56f8a9faa1a4539124ab006b49bf42b6e7c997e3/evidence/v0.6/controller/B_LINE_G2_R3_PARALLEL_P0_OFFLINE_PREPARATION_DISPATCH.json
Method acceptance L2 review: https://github.com/EXASHXE/btc-quant-agent-public/blob/56f8a9faa1a4539124ab006b49bf42b6e7c997e3/reviews/v0.6/b_line/V06_G2_R3_METHOD_R1_1_CONTROLLER_L2_ACCEPTANCE.md
Frozen code base SHA **e0ff8c3473de4bfa3e66fe7928d42992a4d38a32**; accepted design-addendum HEAD **cf2d5cc33774cdcff7d709636305bba830e977ef**; original eight-candidate design SHA `e5b2006a89441f7eb2ec900e508aff451106b87a`; source audit `12793bc04db7414d11a0961684fd14f5df3ce16e`.

**This is an ACTIVE P0 OFFLINE/SYNTHETIC code-preparation task, NOT an empirical campaign.** Authorized: create own worktree and own research/testing files, run synthetic tests, commit/push. Prohibited until later dispatch: raw local or downloaded historical price/mark/funding rate rows, any R3 backtest results, actual fee reads from user's account, rc2 protected data/outcomes, A-line/H40/H41 sources or results, external signed clients, TESTNET, live trading, real funds, new strategies, actual holdout access.
Existing old BTC data manifest is allowed as **static metadata only**, `artifacts/research/run0-dev-frozen-v022-seed7-20260825/data_manifest.json`; no Parquet or ZIP body reads, no `du -a` into private other worktrees, no full SHA256 pass over data bodies at P0. Old BTC v0.3 holdout `[2026-02-01,2026-08-01)` overlaps R3 proposed Feb-Apr. Report this conflict and propose eligible exposed historic development months, but **do not decide a substitute date by running returns**. R3 12h funding stress geometry may be ineligible, do not remove those candidate IDs or relax rules to fabricate a PASS.

## Both Gemini agents start in the same parent directory — no shared worktree
User launches two separate Gemini sessions from `~/workspace/project/quant-v0.6`. This path is a PARENT of Git worktrees. Do not `git init`, `git clone`, edit parent code, switch/reset old branches, or assume `$PWD` is a Git repository.
Run the following safe read-only preflight in your own terminal:
```bash
set -euo pipefail
ROOT="$(cd "$HOME/workspace/project/quant-v0.6" && pwd -P)"
ANCHOR="$ROOT/g2-r3-cost-aware-method-design"
test -d "$ANCHOR" || { echo 'BLOCKED_TRUSTED_ANCHOR_MISSING'; exit 2; }
test "$(cd "$(git -C "$ANCHOR" rev-parse --show-toplevel)" && pwd -P)" = "$(cd "$ANCHOR" && pwd -P)" || { echo 'BLOCKED_ANCHOR_IDENTITY'; exit 2; }
remote="$(git -C "$ANCHOR" remote get-url origin)"
case "$remote" in
 'https://github.com/EXASHXE/btc-quant-agent-public'|'https://github.com/EXASHXE/btc-quant-agent-public.git'|'git@github.com:EXASHXE/btc-quant-agent-public.git'|'ssh://git@github.com/EXASHXE/btc-quant-agent-public.git') ;;
 *) echo 'BLOCKED_UNTRUSTED_ORIGIN'; exit 2;;
esac
git -C "$ANCHOR" worktree list --porcelain
git -C "$ANCHOR" status --porcelain=v1 --untracked-files=all
remote_base="$(git -C "$ANCHOR" ls-remote --heads origin v0.6 | awk '{print $1}')"
remote_method="$(git -C "$ANCHOR" ls-remote --heads origin feature/v06-bline-g2-r3-cost-aware-method-design | awk '{print $1}')"
test "$remote_base" = 'e0ff8c3473de4bfa3e66fe7928d42992a4d38a32' || { echo 'BLOCKED_BASE_DRIFT'; exit 2; }
test "$remote_method" = 'cf2d5cc33774cdcff7d709636305bba830e977ef' || { echo 'BLOCKED_METHOD_DRIFT'; exit 2; }
git -C "$ANCHOR" cat-file -e 'e0ff8c3473de4bfa3e66fe7928d42992a4d38a32^{commit}' || { echo 'BLOCKED_LOCAL_BASE_OBJECT_MISSING'; exit 2; }
```
Independently verify the exact frozen dispatch file above exists and permits your role, parent, branch, paths and no empirical access. A docs-HEAD ref is not a dispatch; do not use an older template to upgrade the scope.

## Branch/worktree creation — only after identity gate
Set your role values shown below. Shared `.git/worktrees` metadata requires serialized creation. Both sessions must use the same `.g2_p0_worktree.lock` in parent. Linux `flock` mandatory (stop if absent). Existing branch/path means STOP rather than resume/reset.
```bash
command -v flock >/dev/null || { echo 'BLOCKED_FLOCK_UNAVAILABLE'; exit 2; }
WT="$ROOT/$ROLE_DIR"
BRANCH="$ROLE_BRANCH"
(
  flock -x 9
  test ! -e "$WT" || { echo 'BLOCKED_WORKTREE_PATH_EXISTS'; exit 2; }
  if git -C "$ANCHOR" show-ref --verify --quiet "refs/heads/$BRANCH"; then echo 'BLOCKED_LOCAL_BRANCH_EXISTS'; exit 2; fi
  test -z "$(git -C "$ANCHOR" ls-remote --heads origin "$BRANCH")" || { echo 'BLOCKED_REMOTE_BRANCH_EXISTS'; exit 2; }
  git -C "$ANCHOR" worktree add --no-track -b "$BRANCH" "$WT" 'e0ff8c3473de4bfa3e66fe7928d42992a4d38a32'
) 9>"$ROOT/.g2_p0_worktree.lock"
test "$(git -C "$WT" rev-parse HEAD)" = 'e0ff8c3473de4bfa3e66fe7928d42992a4d38a32' || { echo 'BLOCKED_WRONG_START_SHA'; exit 2; }
test "$(git -C "$WT" branch --show-current)" = "$BRANCH" || { echo 'BLOCKED_WRONG_ROLE_BRANCH'; exit 2; }
test -z "$(git -C "$WT" status --porcelain=v1 --untracked-files=all)" || { echo 'BLOCKED_DIRTY_WORKTREE'; exit 2; }
cd "$WT"
```
Never operate on sibling checkout except read-only Git metadata; no `reset`, `clean`, `stash`, `rebase`, `cherry-pick`, `force`, `worktree prune`, or recursive data scans of other worktrees. Each agent owns its own Python env and temporary outputs and stays below reasonable shared host CPU/RAM limits.

## Publish proactively — mandatory
Commit/push only your role allowlisted paths to your role branch. Check `git diff --check`, `git diff --cached --name-only` and all added/edited files. Use `git push -u origin "$BRANCH"` (NO force), then fresh `git ls-remote --heads origin "$BRANCH"` and prove its SHA matches local HEAD. Report exact root, source SHA, method SHA, dispatch SHA, final code/evidence HEAD and parent, CI link/status, focused tests PASS/FAIL/SKIP, all changed files, zero protected raw-body accesses, `REAL_FUNDS_WRITE_AUTHORITY=NONE`.
Do not import/hydrate or merge another role's branch into your branch. Run changed Ruff/compile and L1 focused tests ONCE at terminal, not repeated whole-suite pytest. If native Python3.12 unavailable report `PY312_NOT_CERTIFIED` rather than pretend. No production source integration acceptance.

## Bounded runtime and terminal
Run at most 8 hours of task work per worker; stop earlier if complete or blocked. Avoid unbounded loops, unlimited optimizer jobs or repeated external permission requests. If time expires, persist scope-safe partial artifacts and remote-push with `P0_PARTIAL_EXPLICIT`, not empirical success. Task statuses: `P0_READY_FOR_CONTROLLER` / `P0_PARTIAL` / `P0_BLOCKED_IDENTITY_OR_SCOPE` / `P0_BLOCKED_NOT_PUSHED`. Future R3 empirical campaign requires *new* Controller dispatch, explicit source/license and old-holdout adjudication, **first prereg SHA pushed BEFORE reading market price/rate bodies**.

## Only Gemini A scope
Allowed changed files: `src/btc_quant_agent/strategy_research/r3_overnight/**`, `tests/test_strategy_research_r3_*.py`, `docs/strategy_research/g2_r3/prep_a/**`, `evidence/v0.6/b_line/g2_overnight_p0_a/**`. New research-sidecar only; do not touch production Tactical/MarketWatch, G1/G3 or any shared CI, `pyproject.toml`, root config, R3 previous design, R2, RC2, A-line, provider/execution modules.

Read only the eight-candidate **proposal** at exact design SHA and append-only method addendum at `cf2d5cc33774cdcff7d709636305bba830e977ef`. Register exact eight IDs only: STRUCTURAL_CONTINUATION and CLOSED_RETEST, LONG/SHORT, 4h/12h. Implement replay framework against generated **synthetic** 1m trades+mark candle fixtures with deterministic event log and separate virtual books. Baseline 22bp round trip base, 44bp higher friction, funding scenarios only as assumptions and explicit withheld future clock. Ledger uses ex-post vs decision-available clocks, bar close+60s lag, earliest next available minute entry, 1m pessimistic SL-first, gap stop, delayed acknowledgments, 1x accounting, 5% reserve and 10% MTM drawdown latch. Source unverified/missing => STOP/NOT_COMPUTABLE, never synthesized market outcome; 12h stressed reserve ineligibility => named `STRESS_COST_GEOMETRY_INELIGIBLE` not loss.

Before testing any actual candidate return, exercise hermetic **nonmarket** fixtures: constructed wins/losses, no-fill, stop-before-target collision, future price-leak attempt, mark-vs-trade-mismatch, funding publication before/after, double-fee, negative collateral, and both directions. No market archive path reads, no old sealed holdout/price inspection, no actual alpha results.

Prepare **proposal** (not frozen prereg) for reusing legacy BTC 2021-2025 existing development partitions; do not silently overwrite original Jan warm-up / Feb–Apr window, do not inspect local market contents, and do not infer ETH/SOL coverage. Record needed alternative future frozen window/missing-asset inventory. The candidate registry stays eight across ALL verdicts.

End with code, deterministic synthetic hash receipts, focused tests, mock result schemas with `NO_EMPIRICAL_RESULTS`, and future source/method questions. NO market signal ranking/shortlist, no orders.

**Handoff to B:** Publish immutable `A_IMPL_SHA` with tests before terminal evidence; optionally publish `A_P0_FINAL_SHA` after completed receipts. If B asks before push, return `NOT_FROZEN_YET`, not local path or mutable artifacts. B may audit this exact pushed SHA but may not edit A source.

**Terminal**: `P0_A_SYNTHETIC_REPLAY_READY_FOR_CONTROLLER` or fail-closed partial/blocker. Automation/LLM trader remains NONE.