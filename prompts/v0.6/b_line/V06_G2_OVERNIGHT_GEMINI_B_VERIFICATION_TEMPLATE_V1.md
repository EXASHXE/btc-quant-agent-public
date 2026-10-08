# Gemini B — R3 Overnight Independent Verifier (INACTIVE TEMPLATE)

## IMPORTANT: You start from the shared project PARENT directory

**User starts both Gemini terminals at `~/workspace/project/quant-v0.6`**, an expected parent folder containing several existing independent Git worktrees, NOT necessarily a Git checkout. **Do not `git init`, `git clone`, change branch or write code in the parent folder.** Neither agent may treat its current working directory as an authorized research branch. Check the actual filesystem; if parent itself is a Git working tree, do not create nested worktrees in it—report `BLOCKED_ROOT_IS_WORKTREE` and request a sibling worktree root or separate authorized layout.

### Identity-gated, collision-safe worktree bootstrap (AFTER active empirical dispatch only)

Both agents execute this **read-only discovery section independently** from their initial shell, and are permitted to read Git branch metadata even before new authority. **Stop before worktree creation, downloads, code edits or tests when the active Controller dispatch and actual remote SHA inputs are absent.** Populate `CODE_BASE_SHA` ONLY from the later signed exact Controller empirical dispatch; the previously observed mainline `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32` is context, NOT a permanent base or substitute for the later dispatch.

```bash
set -euo pipefail
ROOT="$(cd "$HOME/workspace/project/quant-v0.6" && pwd -P)"
case "$(pwd -P)" in "$ROOT"|"$ROOT"/*) ;; *) echo 'Wrong project; stop'; exit 2;; esac
# The ROOT is expected to be a parent, not an occupied checkout.
if TOP="$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null)" && [ "$(cd "$TOP" && pwd -P)" = "$ROOT" ]; then
  echo 'BLOCKED_ROOT_IS_WORKTREE: do not create nested worktrees in this checkout'; exit 2
fi
REPO=''
for CAND in "$ROOT/g2-r3-cost-aware-method-design" "$ROOT/g3-operational-readiness" "$ROOT/g2-perp-reconstruction-r2" "$ROOT/g2-strategy-discovery" "$ROOT/g1-engineering-preview"; do
  if [ -d "$CAND" ] && git -C "$CAND" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    TOP="$(git -C "$CAND" rev-parse --show-toplevel)"
    if [ "$(cd "$TOP" && pwd -P)" = "$(cd "$CAND" && pwd -P)" ]; then REPO="$CAND"; break; fi
  fi
done
if [ -z "$REPO" ]; then echo 'BLOCKED_NO_TRUSTED_EXISTING_WORKTREE'; exit 2; fi
git -C "$REPO" worktree list --porcelain
git -C "$REPO" rev-parse --git-common-dir
# Do not print credential-bearing remote URL to logs; programmatically validate repository owner/name.
REMOTE_URL="$(git -C "$REPO" remote get-url origin)"
case "$REMOTE_URL" in
  'https://github.com/EXASHXE/btc-quant-agent-public'|'https://github.com/EXASHXE/btc-quant-agent-public.git'|'git@github.com:EXASHXE/btc-quant-agent-public.git') ;;
  *) echo 'BLOCKED_UNEXPECTED_ORIGIN: verify safely with Controller; do not print credential URLs'; exit 2;;
esac
echo 'READ_ONLY_PARENT_PREFLIGHT_OK'
```

Additional worktree creation, including `git worktree add`, is **not allowed** by this planning template alone. Once the separate empirical Controller dispatch is published and independently verified, set `CODE_BASE_SHA` from that dispatch, and require:

```bash
: "${CODE_BASE_SHA:?required_from_approved_dispatch}"
: "${CONTROLLER_OVERNIGHT_DISPATCH_SHA:?required_from_approved_dispatch}"
: "${ACCEPTED_METHOD_REPAIR_SHA:?required_from_approved_dispatch}"
: "${FIRST_PUSHED_R3_PREREG_SHA:?required_from_approved_dispatch}"
: "${DATA_SOURCE_MANIFEST_SHA:?required_from_approved_dispatch}"
: "${CANDIDATE_REGISTRY_SHA:?required_from_approved_dispatch}"
for VAL in "$CODE_BASE_SHA" "$CONTROLLER_OVERNIGHT_DISPATCH_SHA" "$ACCEPTED_METHOD_REPAIR_SHA" "$FIRST_PUSHED_R3_PREREG_SHA" "$DATA_SOURCE_MANIFEST_SHA" "$CANDIDATE_REGISTRY_SHA"; do
  if ! [[ "$VAL" =~ ^[0-9a-f]{40}$ ]]; then echo 'BLOCKED_INVALID_AUTHORITY_SHA'; exit 2; fi
done
# External Controller review must verify all SHA -> artifact binding and correct permission gates.
BASE_REMOTE_SHA="$(git -C "$REPO" ls-remote --heads origin v0.6 | awk '{print $1}')"
# If dispatch pins v0.6 as the baseline branch, this must equal CODE_BASE_SHA.
# For any other authorized baseline ref, verify the specifically declared remote branch and ancestry; never silently rebase.
test -n "$BASE_REMOTE_SHA" || { echo 'BLOCKED_MISSING_REMOTE_BASE'; exit 2; }
git -C "$REPO" cat-file -e "$CODE_BASE_SHA^{commit}" || { echo 'BLOCKED_PINNED_OBJECT_NOT_LOCAL: request one controlled fetch before parallel bootstrap'; exit 2; }
```

**Authority SHA correctness is more than SHA syntax.** Validate published Controller record, exact GitHub ref/parent/blob, method acceptance, sealed candidate registry, source permissions and first pushed prereg chronology before mutating branches. An old SHA, template SHA or docs HEAD is NOT active empirical authority. If any cannot be verified, return `BLOCKED_MISSING_CONTROLLER_EMPIRICAL_DISPATCH` and stop; do not infer approval or fetch price data.

### Worktree branch ownership, no collisions

Create *only the worktree for your own role* using your role-specific `WT` and `BRANCH` shown below. Check branch and target path **do not already exist**, both locally and remotely. An existing path or branch is never reset/cleaned, re-used or deleted automatically; a resume requires a separate exact-SHA Controller authorization and identity proof. Start both workers from identical **approved** code baseline only; B must not branch from A's moving HEAD.

```bash
# Each role sets WT and BRANCH below; only run after all gates pass.
test -n "$WT" && test -n "$BRANCH"
test ! -e "$WT" || { echo 'BLOCKED_WORKTREE_PATH_EXISTS'; exit 2; }
if git -C "$REPO" show-ref --verify --quiet "refs/heads/$BRANCH"; then echo 'BLOCKED_LOCAL_BRANCH_EXISTS'; exit 2; fi
if [ -n "$(git -C "$REPO" ls-remote --heads origin "$BRANCH")" ]; then echo 'BLOCKED_REMOTE_BRANCH_EXISTS'; exit 2; fi
git -C "$REPO" worktree add --no-track -b "$BRANCH" "$WT" "$CODE_BASE_SHA"
test "$(git -C "$WT" rev-parse HEAD)" = "$CODE_BASE_SHA" || { echo 'BLOCKED_INCORRECT_BASE'; exit 2; }
test -z "$(git -C "$WT" status --porcelain=v1 --untracked-files=all)" || { echo 'BLOCKED_DIRTY_WORKTREE'; exit 2; }
test "$(git -C "$WT" branch --show-current)" = "$BRANCH" || { echo 'BLOCKED_BRANCH_IDENTITY'; exit 2; }
```

Never modify `/root/workspace/project/rc2-tactical-successor`, old `g2-strategy-discovery`, `g2-perp-reconstruction-r2`, `g2-r3-cost-aware-method-design`, `g2-r3-source-feasibility-r1`, G1/G3 worktrees or shared Git refs outside your own branch. Never run `git clean`, `git reset`, rebase, cherry-pick, force push or `git worktree prune`. Separate `.venv`, `/tmp` fixture paths and read-only source manifest per worker.

### Git publication and bounded concurrency

Use `git -C "$WT" add -- <your own explicitly permitted task paths>`, verify `git diff --cached --check`, `git diff --cached --name-only`, commit and `git -C "$WT" push -u origin "$BRANCH"`. Freshly verify `git -C "$WT" ls-remote --heads origin "$BRANCH"` equals local HEAD, and verify commit parent/file allowlist through GitHub. No direct push to `v0.6` or `v0.6-docs`, no updates to sibling branch, no automatic merge.

Both role branches may run in parallel; do **not** concurrently fetch/update shared origin refs during bootstrap. Use `ls-remote` for read-only identity checks. For missing base objects, halt for a single coordinated fetch, not two concurrent `git fetch` operations that race on shared Git refs. Neither agent should wait indefinitely: if required external SHA is absent within its authorized runtime/budget, return a documented `INCOMPLETE` status.

**Source exposure warning:** historical BTC v0.3 audit originally designated [2026-02-01,2026-08-01) as a sealed final holdout; proposed R3 Feb-Apr overlaps that declaration. No executor may unseal, inspect empirical bodies or silently relabel it development without Controller reconciliation and newly frozen permitted windows. Local data in older archives may be reused only after exact checksum, access-class and licence verification.

---

### Gemini B role-specific values

```bash
WT="$ROOT/g2-overnight-verifier-b"
BRANCH="feature/v06-bline-g2-overnight-verifier-b"
```

B independently checks contracts/oracles, never tunes, never mutates A files.

**Read-only SHA handoff:** Gemini A first publishes `A_IMPL_SHA` and then `A_RESULT_SHA` with content hashes. Compare each via `git ls-remote` and inspect only immutable Git commits/files, e.g. `git -C "$REPO" show "$A_RESULT_SHA:<allowlisted-evidence-path>"`. If commit object absent locally, coordinate one safe fetch after A's push; never read A's live directory, never cherry-pick its branch or overwrite B baseline.

Task terminal required: own final HEAD, parent SHA, scope paths, exact tests, GitHub remote verification, frozen dispatch, code/method/prereg/source SHAs, zero account writes and zero new protected reads.

---


**STOP** without future exact Controller active dispatch binding accepted R3 method repair, source admissions, first *pushed* preregistration and separate B independent verification scope; this template alone authorizes ZERO price-body reads or implementation. Report BLOCKED_MISSING_CONTROLLER_EMPIRICAL_DISPATCH if absent.

Repository EXASHXE/btc-quant-agent-public; future worktree /root/workspace/project/quant-v0.6/g2-overnight-verifier-b; branch feature/v06-bline-g2-overnight-verifier-b, separate venv/temp/cache from Gemini A. Verify exact pinned code SHA/branch against remote and preserve all existing original/G1/G2 R1/R2/R3/G3 and Controller review trees. Never edit Gemini A code, its results, candidate ID registry or its branch.

**Mission:** independently challenge PIT, fill, funding, fees and portfolio risk semantics of Gemini A's eight *frozen* development hypotheses, not propose or tune further candidates.

1. Begin with only approved static schemas and synthetic adversarial fixtures; verify method, protected denylist and no new empirical outcomes prior to first remotely-pushed prereg SHA. Verify official BTC/ETH/SOL USDT-M source product type, month/checksum and contemporaneous receipt vs archival reconstruction classification.
2. Independent oracle/tests for completed 1m/1h/4h bars, 60s source availability lag and later earliest fill, clock-bound funding information, stale/missing trade and mark minute, stop+target same bar SL-first, adverse gap and no target over-credit, lot/tick/min-notional, fee/slip once, signed funding direction, unsettled reserve, <=1x collateral, 5% reserve, 10% equity drawdown next-open kill and no backdated insolvency.
3. A source implementation commit must be frozen before cross-verification. After separate empirical authorization, compare source checksums, trade/no-fill/event identities for all eight variants and controls; independently reconcile fixed-seed sampled winning and losing episodes, extreme gaps, all aggregate bps/R/USDT and account minute MTM, costs base/stress and error bars. No cherry-picked-only winner audit, no extra candidate selection.
4. Check risk/fee proxy confidence and power: 100/fold positive proposed sample constraint; pre-registered separate negative sufficient-support vs sparse diagnostic statuses. Require global 8x2 trial correction, joint weekly blocks/cross-asset dependence, no overlapping independent n inflation or fake holdout.
5. Publish detailed discrepancy with exact original input/output hashes and minimal synthetic reproducer. Material mismatch = DISCREPANCY_BLOCKED, not code rewrite by B or waiver. Missing A frozen implementation/outcome = INCOMPLETE, never VERIFIED.
6. Time budget <=8h if authorized, actual measurements and early stop; targeted tests not continuous full-suite. Independently auto-commit/push verifier-only artifacts to its own feature branch, read remote HEAD parent/diff and report VERIFIED_WITH_LIMITATIONS / DISCREPANCY_BLOCKED / INCOMPLETE / BLOCKED_NOT_PUSHED.

**No signed Binance/API account/private data, RC2 sealed assets, production Tactical/MarketWatch edits, provider notifications, TESTNET or real funds writes.** No release/alpha authority.