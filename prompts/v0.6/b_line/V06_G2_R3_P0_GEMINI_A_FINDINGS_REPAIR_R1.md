# G2 R3 P0 — Gemini A bounded findings repair R1 (ACTIVE ONLY FOR A)

**Role:** Gemini A repair executor, not trade strategy optimizer. **CONTROLLER_DISPATCH_SHA=e94d53c1f98f16d8d3881737564f773bc2584f28**.
- Immutable authorizing [Controller dispatch](https://github.com/EXASHXE/btc-quant-agent-public/blob/e94d53c1f98f16d8d3881737564f773bc2584f28/evidence/v0.6/controller/B_LINE_G2_R3_P0_A_FINDINGS_REPAIR_R1_DISPATCH.json)
- Immutable [L2 three-agent findings review](https://github.com/EXASHXE/btc-quant-agent-public/blob/e94d53c1f98f16d8d3881737564f773bc2584f28/reviews/v0.6/b_line/V06_G2_R3_TRIPLE_P0_CONTROLLER_L2_REVIEW.md)
- Repository `EXASHXE/btc-quant-agent-public`; expected exact A branch `feature/v06-bline-g2-overnight-discovery-a` at SHA `3b8befb0112cfe2d314ad65964762a3fb251e710`.
- Frozen A initial implementation `3ebb7db9a1043e58843b518af9381218d9f25af1`, original A baseline `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`, R3 design-method exact `cf2d5cc33774cdcff7d709636305bba830e977ef`.
- Independent B verdict `P0_B_DISCREPANCY_BLOCKED`, immutable branch B SHA `a0aacd105ac3f3173b15d91c869990748178e222`, [8 numbered findings](https://github.com/EXASHXE/btc-quant-agent-public/blob/a0aacd105ac3f3173b15d91c869990748178e222/evidence/v0.6/b_line/g2_overnight_p0_b/A_IMPL_STATIC_COMPARISON_RECEIPT.json). Treat these as testable allegations and reproduce them, not mere prose; do not suppress B assertions.

## Objective and irreversible gates

Fix exactly the 8 B findings, build explicit red-before / green-after hermetic regression proofs (including 4h/12h duration, zombie ACK, retest state isolation). No strategy formulas/IDs, stop risk geometry, cost assumptions or candidate count may be silently changed to pass a test. Maintain exactly 8 declared candidates, no market-data access, no profit claims, no TESTNET/orders. A's green previous suite **2813 PASS** was insufficient to catch these code bugs. Your final answer is `P0_A_REPAIR_IMPLEMENTED_PENDING_INDEPENDENT_B_REAUDIT` not accepted PASS.

**Worktree:** from user shell initial CWD `~/workspace/project/quant-v0.6`, reuse EXISTING `~/workspace/project/quant-v0.6/g2-overnight-discovery-a` only if local clean and exact remote identity. **Do not create a new directory, reset, clean, switch branches or modify Gemini B/Sol checkout.** Confirm remote owner/name, branch, base commit ancestry and the exact pre-repair head. Stop on any drift, dirty files, concurrent running executor or unknown branch. Do not forcibly remove user files.

```bash
set -euo pipefail
ROOT="$(cd "$HOME/workspace/project/quant-v0.6" && pwd -P)"
WT="$ROOT/g2-overnight-discovery-a"
BRANCH='feature/v06-bline-g2-overnight-discovery-a'
EXPECTED='3b8befb0112cfe2d314ad65964762a3fb251e710'
test -d "$WT" || { echo BLOCKED_MISSING_EXISTING_WORKTREE; exit 2; }
test "$(git -C "$WT" branch --show-current)" = "$BRANCH" || { echo BLOCKED_WRONG_BRANCH; exit 2; }
test "$(git -C "$WT" rev-parse HEAD)" = "$EXPECTED" || { echo BLOCKED_LOCAL_HEAD_DRIFT; exit 2; }
test -z "$(git -C "$WT" status --porcelain=v1 --untracked-files=all)" || { echo BLOCKED_DIRTY_USER_WORKTREE; exit 2; }
remote="$(git -C "$WT" remote get-url origin)"
case "$remote" in
 'https://github.com/EXASHXE/btc-quant-agent-public'|'https://github.com/EXASHXE/btc-quant-agent-public.git'|'git@github.com:EXASHXE/btc-quant-agent-public.git'|'ssh://git@github.com/EXASHXE/btc-quant-agent-public.git') ;;
 *) echo BLOCKED_UNEXPECTED_REMOTE; exit 2;;
esac
test "$(git -C "$WT" ls-remote --heads origin "$BRANCH" | awk '{print $1}')" = "$EXPECTED" || { echo BLOCKED_REMOTE_HEAD_DRIFT; exit 2; }
cd "$WT"
```

## Scope and original source

Allowed modifications only:
- `src/btc_quant_agent/strategy_research/r3_overnight/**`
- `tests/test_strategy_research_r3_*.py`
- `docs/strategy_research/g2_r3/prep_a/**`
- NEW append-only `evidence/v0.6/b_line/g2_overnight_p0_a/repair_r1/**`
- **Special one-time exception:** `src/btc_quant_agent/strategy_research/__init__.py` **DELETE ONLY** to repair previous A01 out-of-allowlist addition. Verify package imports continue working after deletion. Do not edit/add another file outside allowed prefixes.

Old evidence receipts outside `repair_r1/**` remain immutable, including A's wrong first receipt. Publish a CORRECTION artifact referencing old SHA, not an in-place overwrite. No `.github`, pyproject, root config, producer data cache, RC2 protected, H40/H41, G1/G3/Tactical/MarketWatch production, Gemini B branch/source, Sol docs, external execution client, signed API. Zero real/local Binance or market bodies; synthetic fixture generators ONLY. No need to rerun whole-suite per individual tiny edit.

## 8 reproducible findings — every defect must have a matching regression

**A01 scope:** remove only the extra `src/btc_quant_agent/strategy_research/__init__.py` and certify the research sidecar imports through Python3.12/3.13. If import layout cannot work without this file, STOP and report `SCOPE_REPAIR_NEEDS_CONTROLLER_AMENDMENT`; don't keep an unauthorized file.

**A02 manifest:** old receipt reported `2933280` rows; canonical Git manifest `artifacts/research/run0-dev-frozen-v022-seed7-20260825/data_manifest.json` has `2934720`, delta1440 including leap day. Generate new append-only correction receipt with old artifact path/hash, actual fields, exact source manifest blob and reason; invariant asserts total row_count equals sum of 67 per-month recorded metadata lengths where available (no raw Parquet). Do not change canonical manifest, old audit, or market bytes. ETH/SOL physical availability UNKNOWN, not FALSE based only on missing manifest.

**A03 CRITICAL ACK:** `ledger.py` Stage5 economically opens original Position with candidate `max_hold_ms=4h|12h`, Stage1 fill acknowledgment currently replaces with `max_hold_ms=0` and can resurrect same-minute stop/TP closed position. Model economic position identity separately from delayed acknowledgment and reservation. An entry ACK must never create a second economic position, reset stop/target/hold/funding or resurrect a closed position. Debit taker fee exactly once, preserve settlement/fill identity, maintain negative equity and pending exit ack. Test durable 4h/12h holding across 3+ subsequent minutes, immediate SL/TP with next-minute ack, no duplicate close, no zombie, fee once, delayed buy/sell account.

**A04 CRITICAL candidate isolation:** `ReplayEngine.signal_generator` shared across 8 and `_active_breakouts[(symbol,direction)]` missing candidate ID, so 04H and12H retest corrupt state. Design per-candidate isolated generator or `(candidate_id,symbol,direction)` keys and event consumed identities. Reorder candidate evaluation and verify identical signals/trades; sequential R3 base/stress runs cannot leak state. Test both long and short 4h/12h in same symbol/time event, confirm no cross-consumption.

**A05 retest formula:** for LONG require **bar LOW inside exact inclusive `[B−0.25ATR,B+0.25ATR]`** rather than merely 1h range intersects. For SHORT require bar HIGH inside band. Stop extremum includes breakout bar AND all intervening+confirmation bars. Tests reject deep wick below/above band even if ranges overlap; accept boundary touches on both directions and check correct breakout extreme stop.

**A06 mark/PIT:** process available mark messages in Stage1 and use **completed mark close event time** for freshness; do not stamp minute open or admit future mark. Test boundary 120s freshness, t+60s publication, stale veto/delayed liquidation, true market event vs decision clock. Never substitute trade close for mark.

**A07 cooldown/dedup:** start 4h cooldown from `ceil_to_minute(economic_exit_at)` not delayed exit acknowledgment; use decision/available clock semantics correctly, pass last_exit and last_entry_4h dedup state from ReplayEngine to SignalGenerator; test two signals same 4h structure, rejected pre-cooldown, accepted after, no clock backdating.

**A08 reserve accounting:** include required `tick_size*quantity` exit cost buffer as specified; retain commitments for open positions and unsettled funding/exit while acknowledgments pending, release each exactly once, respect 1x notional /5% reserve/10% equity loss and no capital double spend. Test adverse gap, zero/negative collateral, late ACK, two pending symbols with independent virtual books.

Potential extra correctness faults encountered while implementing these tests may be included ONLY if they are true adjacent defects inside allowed code and tightly evidenced. Do not use bug repair as a reason to change strategy rules, candidate universe/parameters, economic thresholds or run historical studies.

## Red-green test and publication authority

1. Pin accepted R3 mechanical source with immutable git `cf2d5cc33774cdcff7d709636305bba830e977ef`; frozen B evidence branch `a0aacd105ac3f3173b15d91c869990748178e222`. Reproduce red failures against original source (for newly designed test assertions) and save actual failing test IDs/outputs, or state `RED_EVIDENCE_UNAVAILABLE` and reason; never invent red results.
2. Fix core source then run changed-file Ruff, compile, Python3.12 pytest on `tests/test_strategy_research_r3_*.py` with all 8 independent regression groups. Keep before/after test summaries and reproducible command+environment in `repair_r1/**`. Python3.13 optional; Python3.12 required. Add synthetic property/metamorphic negative cases for ACK/strategy isolation, not only happy path.
3. One full-suite CI will run after terminal push according to existing planner; do not overwrite golden or disable CI checks. Report exact CI state; don't claim integration acceptance pending checks.
4. Build `repair_r1/FINDINGS_REPAIR_MATRIX.json`: each B A01-A08 -> original observed finding, minimal patch SHA/path, negative regression test ID, before/after evidence, remaining caveats and terminal status. Add `repair_r1/TEST_RECEIPT.json` and `repair_r1/CONTROLLER_HANDOFF.md`; they must say `PENDING_INDEPENDENT_B_REAUDIT`, `NO_EMPIRICAL_OUTCOMES`, `REAL_FUNDS_WRITE_AUTHORITY=NONE`.
5. Only `git add --` allowed prefixes, explicit delete-only A01, `git diff --cached --name-status`, `git diff --cached --check`, no protected paths. Commit+push to EXISTING `feature/v06-bline-g2-overnight-discovery-a`, no force. Fresh `git ls-remote --heads origin "$BRANCH"` and verify remote parent+changed files. Do not push to `v0.6`, `v0.6-docs`, B or Sol branch.
6. Return exact final A_REPAIR_SHA and current parent, code/test counts/CI URL, 8 finding statuses, any unresolved blocks, all market-source-body access counts 0, **no TESTNET or LIVE**. Terminal `P0_A_REPAIR_IMPLEMENTED_PENDING_INDEPENDENT_B_REAUDIT` / `P0_A_REPAIR_PARTIAL_STILL_BLOCKED` / `BLOCKED_NOT_PUSHED`.

**Stop early on completion; no artificial 8-hour loop. Correctness + independent audit, not runtime, is the goal.**