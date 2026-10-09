# v0.6 G2 R3 Gemini B — Independent P0 A Findings Repair R1 Re-audit

**ACTIVE B RE-AUDIT ONLY** — never strategy optimization or market replay.

- **TASK_ID**: `V06_G2_R3_P0_B_INDEPENDENT_REAUDIT_R1`
- **CONTROLLER_DISPATCH_SHA**: `3fb4508110c031eb0ff9226a7e42d918684c554f`
- [Frozen Controller dispatch](https://github.com/EXASHXE/btc-quant-agent-public/blob/3fb4508110c031eb0ff9226a7e42d918684c554f/evidence/v0.6/controller/B_LINE_G2_R3_P0_B_INDEPENDENT_REAUDIT_R1_DISPATCH.json)
- [L2 identity/initial CI review](https://github.com/EXASHXE/btc-quant-agent-public/blob/3fb4508110c031eb0ff9226a7e42d918684c554f/reviews/v0.6/b_line/V06_G2_R3_A_REPAIR_R1_CONTROLLER_IDENTITY_AND_CI_REVIEW.md)
- **A_REPAIR_SHA**: `5c542edd418a74b440162610fd540b1f01e423d3` (exact remote immutable review target, not moving A HEAD).
- Original A repair `2f0383816127cb7d87cf5deb559aeda0b04f1624`; subsequent Controller edit is exactly one `from typing import Any` import in repair tests. No A strategy source mutated by Controller.
- **B_EXPECTED_HEAD**: `a0aacd105ac3f3173b15d91c869990748178e222` on `feature/v06-bline-g2-overnight-verifier-b`; original code base `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`.
- R3 method `cf2d5cc33774cdcff7d709636305bba830e977ef`; original 8 candidate registry `e5b2006a89441f7eb2ec900e508aff451106b87a`.
- A first CI [37873215393](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37873215393) **FAILED Ruff F821**, repaired by direct Controller one-line correction. New [CI 37875087577](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37875087577) **SUCCESS focused mode, 7 passed**, not full-suite certification; B must report this precise scope and not upgrade quality authority.

## Shared project and worktree guard

Start B terminal in `~/workspace/project/quant-v0.6`. **REUSE only existing** `~/workspace/project/quant-v0.6/g2-overnight-verifier-b`. Do NOT create another branch/worktree, delete user files or modify A or old protected trees. Before any edits:
```bash
set -euo pipefail
ROOT="$(cd "$HOME/workspace/project/quant-v0.6" && pwd -P)"
WT="$ROOT/g2-overnight-verifier-b"
BRANCH="feature/v06-bline-g2-overnight-verifier-b"
A_REPAIR_SHA="5c542edd418a74b440162610fd540b1f01e423d3"
EXPECTED_B="a0aacd105ac3f3173b15d91c869990748178e222"
test -d "$WT" || { echo BLOCKED_B_WORKTREE_MISSING; exit 2; }
test "$(git -C "$WT" branch --show-current)" = "$BRANCH" || { echo BLOCKED_B_BRANCH; exit 2; }
test "$(git -C "$WT" rev-parse HEAD)" = "$EXPECTED_B" || { echo BLOCKED_B_HEAD_DRIFT; exit 2; }
test -z "$(git -C "$WT" status --porcelain=v1 --untracked-files=all)" || { echo BLOCKED_B_DIRTY; exit 2; }
remote="$(git -C "$WT" remote get-url origin)"
case "$remote" in
  'https://github.com/EXASHXE/btc-quant-agent-public'|'https://github.com/EXASHXE/btc-quant-agent-public.git'|'git@github.com:EXASHXE/btc-quant-agent-public.git'|'ssh://git@github.com/EXASHXE/btc-quant-agent-public.git') ;;
  *) echo BLOCKED_REMOTE; exit 2;;
esac
test "$(git -C "$WT" ls-remote --heads origin "$BRANCH" | awk '{print $1}')" = "$EXPECTED_B" || { echo BLOCKED_REMOTE_B_DRIFT; exit 2; }
test "$(git -C "$WT" ls-remote --heads origin feature/v06-bline-g2-overnight-discovery-a | awk '{print $1}')" = "$A_REPAIR_SHA" || { echo BLOCKED_REMOTE_A_DRIFT_REBIND; exit 2; }
```

Independently fetch/verify exact immutable Controller dispatch GitHub JSON, not docs HEAD alone. The A commit object might be absent locally. If so, use a **single serialized** `git fetch --no-tags origin "$A_REPAIR_SHA"` under `flock -x` on shared parent `.g2_p0_worktree.lock`; check `git cat-file -e "$A_REPAIR_SHA^{commit}"`, direct parent, tree and exact changed-path scope. NEVER checkout, reset or write A's live worktree, use remote Git objects or isolated synthetic scratch only.

## Independent verification mandate

B is an **independent adversarial oracle**, not a copy of A's regression tests. The existing B audit at `a0aacd105ac3f3173b15d91c869990748178e222` listed [8 A findings](https://github.com/EXASHXE/btc-quant-agent-public/blob/a0aacd105ac3f3173b15d91c869990748178e222/evidence/v0.6/b_line/g2_overnight_p0_b/A_IMPL_STATIC_COMPARISON_RECEIPT.json). Recheck **each A01–A08** against exactly `5c542edd418a74b440162610fd540b1f01e423d3`, including diff from `3b8befb0112cfe2d314ad65964762a3fb251e710`; preserve unchanged frozen original registry, candidate count 8, original cost assumptions and 4h/12h horizons.

1. **A01/A02**: verify out-of-allowlist `strategy_research/__init__.py` is deleted ONLY and namespace imports work; compare corrected metadata receipt with immutable BTC manifest 2,934,720 rows including leap day. Old incorrect A receipt must remain intact with explicit supersession.
2. **A03 (CRITICAL)**: independently attack Stage5 economic open → Stage1 delayed fill ACK → intact 4h/12h lifetime, entry fee charged once, immediate SL/TP on entry minute → no resurrected position or duplicate close; stale/double ACK, delayed exit funding and reserve accounting. Don't treat static AST or A's own test as proof.
3. **A04 (CRITICAL)**: per-candidate retest breakout identity, 04H/12H long+short candidate isolation, candidate iteration permutation and base/stress repeat hash invariance. No state consumption by sibling candidate.
4. **A05/A06**: retest low/high inside precise ±0.25 ATR band and stop extrema including breakout, reject deep wicks; mark 1m completed-close timestamp+delayed availability, Stage1 ingestion and 120s boundary; no future mark leak.
5. **A07/A08**: economic exit vs ACK-cooldown ordering and four-hour same-signal dedup; tick-size × quantity exit buffer, per-book funding and 1x/5% equity commitment, repeated ACK and negative-equity stop.
6. **Other material interactions** discovered from exact source are reportable as **NEW_BLOCKER** with a minimal deterministic synthetic reproduction; no changing cost/strategy constants or waiving authority. Original 8 B findings cannot be silently marked waived.
7. **Actual executable cross-check**: run A repaired source in a **scoped, isolated scratch environment** built only from immutable Git source objects and generated synthetic fixtures (no A live checkout). Compare event-level signals/entry IDs/fill ACKs/SL-TP/fees/funding/cash/MTM and output hash against B's independently computed expectations. If such execution cannot be isolated under repository constraints, explicitly `INCOMPLETE_DYNAMIC_CROSSCHECK`, not PASS. No market data/Parquet/ZIP/funding-rate body access or historic replay.
8. Run B focused test suite under Python3.12, Ruff and compile on owned checker changes; optional exact A targeted tests as secondary confirmation. Read remote CI run `37875087577` and report **mode=focused, 7 tests**; do not claim full-suite run. Produce machine observed test outputs, SHA provenance and before/after mismatch list.

Allowed changes **only** `scripts/strategy_research/r3_verification/**`, `tests/test_v06_g2_r3_verifier_*.py`, `docs/strategy_research/g2_r3/prep_b/repair_r1/**`, `evidence/v0.6/b_line/g2_overnight_p0_b/repair_r1/**`. Original B report and artifacts untouched; never edit A code/branch, Sol/science, production, root CI or configs, H40/H41/RC2/v0.3 protected outcomes.

## Terminal evidence and Git publication

Write `repair_r1/A01_A08_INDEPENDENT_MATRIX.json`, `repair_r1/INDEPENDENT_SYNTHETIC_EXECUTION_RECEIPT.json`, `repair_r1/B_REAUDIT_CONTROLLER_HANDOFF.md` and any scoped deterministic synthetic regression tests. Each finding must have before/after status, exact A SHA, concrete B test/trace, residual risk, severity. B terminal one of `P0_B_REPAIR_REAUDIT_PASS_SCOPED_SYNTHETIC`, `P0_B_REPAIR_DISCREPANCY_BLOCKED`, `P0_B_INCOMPLETE_DYNAMIC_CROSSCHECK`, `BLOCKED_SCOPE_OR_GIT`, `BLOCKED_NOT_PUSHED`. A PASS still does not grant empirical quality/release authority.

Run `git diff --check`, staged allowlist test and `git diff --cached --name-status`; commit and `git push -u origin "$BRANCH"` **without force**, fresh remote `ls-remote` verifying commit/parent and changed paths. Do not merge to `v0.6` or modify another branch. Stop when done, max 4h. Return CONTROLLER_DISPATCH_SHA, A_REPAIR_SHA, B final SHA, covered independent cases and CI status.

**EMPIRICAL_PRICE_BODY_AUTHORITY=NONE; G4_TESTNET=NOT_AUTHORIZED; REAL_FUNDS_WRITE_AUTHORITY=NONE.**
