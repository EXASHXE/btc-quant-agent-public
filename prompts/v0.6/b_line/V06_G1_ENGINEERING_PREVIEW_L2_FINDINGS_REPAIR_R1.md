# V06 G1 Engineering Preview — Controller L2 Findings Repair R1 (Gemini)

**TASK_ID:** `V06_G1_ENGINEERING_PREVIEW_L2_FINDINGS_REPAIR_R1`

**CONTROLLER_DISPATCH_SHA:** `deecefafff67f3ce81962477a17af7cf1c97cb7f` ([immutable development-only repair authority](https://github.com/EXASHXE/btc-quant-agent-public/blob/deecefafff67f3ce81962477a17af7cf1c97cb7f/evidence/v0.6/controller/G1_ENGINEERING_PREVIEW_L2_BOUNDED_REPAIR_R1_DISPATCH.json)).

**Repository:** `EXASHXE/btc-quant-agent-public`; current implementation branch `feature/v06-bline-engineering-preview-r1`; exact required starting HEAD `6eef811961bfbe1341eee79b2450a4266d277302`. This is an **in-place bounded repair on G1 branch**, not a new feature branch, not G2 research, not release or protected authority.

**Local G1 worktree:** `/root/workspace/project/quant-v0.6/g1-engineering-preview`. **Existing** original repository checkout `/root/workspace/project/rc2-tactical-successor`, detached review worktree, and G2 worktree `/root/workspace/project/quant-v0.6/g2-strategy-discovery` are **hands off**. Do not recreate/reset/delete worktrees.

Note: `v0.6` moved **only through a Controller-approved CI docs-only fix** to `03c4b5ebea299a11a5f0c64f45572b27cc4ad4b8` while G1 independently worked from `d6500140f3141d179181f2360ad815b5bfe9c954`. **Do not rebase, merge or cherry-pick the CI fix into G1**; the Controller handles integration lineage after exact-SHA acceptance.

## Controller review: two narrow unresolved findings

Authoritative [Controller L2 review](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/reviews/v0.6/b_line/V06_G1_G2_PARALLEL_CONTROLLER_L2_REVIEW_R1.md):

**FINDING 1 — unauthorized historical evidence import.**
G1 imported a new historical file `evidence/v0.5.5/live_v1/RC1/WP_D/B_LINE_INITIAL_USABLE_RELEASE_V1_RC1_MANIFEST.json`, which was forbidden by the original engineering-preview dispatch. This historical source identity MUST NOT become an asserted v0.6 release manifest.

Required:
1. Inspect all actual code/test/docs references to this newly imported file by **targeted static text search** (do not inspect protected paths).
2. Remove only the **newly introduced G1 file** at the path above from the G1 feature branch. This deletion is an explicit one-path exception to forbidden `evidence/v0.5.5/**`, **not** permission to touch other historical files or Controller archives.
3. If a legitimate preview template is needed by tests/docs, place a **clearly UNBOUND, non-authoritative, non-secret** copy under `evidence/v0.6/b_line/engineering_preview_r1/RELEASE_MANIFEST_TEMPLATE_UNBOUND.json`, adjust only direct source/test/runbook references needed for G1 offline preview. A template cannot self-certify `SOURCE_SHA`, `WP-A` authority, Python runtime, RC or TESTNET; retain pending markers.
4. Record before/after consumer/path proof and historical evidence firewall conformance. No broad refactoring, no changing accepted WP-D safety gates to accommodate an import error.

**FINDING 2 — full-suite H40 scientific golden mismatch, despite unchanged science code.**
Independent G1 CI [#37755191706](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37755191706) at `6eef8119...`: **2767 PASS / 1 FAIL / 2 SKIP**, failing `tests/test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph` (observed `ee185f1f...` vs expected `d5a962cd...`). Separate exact SHA [baseline-vs-G1 H40 isolated CI #37759244599](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37759244599) confirms **same golden test passes on both code identities** in fresh Python 3.12 checkouts; Git blob comparison proves H40/H41 and their tests are byte-identical. Thus **cause is unresolved combined-suite collection/order/state**, NOT an established H40 algorithm change, and not automatically an inherited issue.

Required:
1. Reproduce narrow H40 golden in the G1 pinned tree with ordinary repository tests/conftest, then with selective collection/import/relevant cross-module fixtures. Search for global state, leaked monkeypatch/runtime config, module namespace pollution, PRNG/Decimal context, file caches or test ordering, using **nonprotected synthetic fixtures only**.
2. If a newly integrated G1 source/test import has collection-time side effects, correct that minimal source/test path **without** modifying H40/H41 source/golden, changing scientific constants, deleting tests, marking tests xfail/skip, or weakening H40 precision. Prove the causality with a before/after focused regression.
3. If failure still cannot be attributed within a **maximum of two targeted diagnosis passes**, STOP and return `G1_L2_H40_CROSS_SUITE_BLOCKED` with exact reproduction commands, collected test set/order, environment hashes and unresolved hypotheses. Do not run full all-suite repeatedly to hide a problem; recommend one independently controlled baseline full run later if necessary. Do not fabricate a green result.
4. Distinguish `ISOLATED_BOTH_PASS`, `COMBINED_REPRODUCED`, `ATTRIBUTED_TO_G1`, `INHERITED_BASELINE_REPRODUCED`, `UNRESOLVED` precisely.

## Source ownership and safety

**Allowed limited changes:** (a) exact new historical file **deletion** named above, (b) v0.6 preview manifest location and append-only evidence under `evidence/v0.6/b_line/engineering_preview_r1/**`, (c) `src/btc_quant_agent/api.py`, a directly referencing WP-D test, and `docs/LIVE_V1_RC1_OPERATIONAL_RUNBOOK.md` **only if references actually require it**, (d) minimal G1-owned initialization/preview test changes if reproducibly linked to Finding 2, (e) optional new focused test `tests/test_v06_engineering_preview_r1.py` that reproduces the identified nonprotected issue.

**Absolutely forbidden:** editing `src/btc_quant_agent/h40/**`, `h41/**`, `tests/h40/**`, `tests/h41/**`, golden digests, `src/btc_quant_agent/market_watch/**` (frozen Tactical), RC2 validation/protected data, `evidence/v0.5.5/**` except the one **explicit deletion**, G2 `strategy_research/**`, shared `.github/workflows/**` and `scripts/ci/test_plan.py`. No Binance trading, provider/Feishu credential use, TESTNET, protected outcomes or real-funds capabilities.

Preserve structural defaults `DRY_RUN`, one serialized POSIX/Python3.12 initializer, R8 guards, approval hash/TTL/non-replay, kill and stop/protection, signed-client zero, release manifest pending certification. Treat prior WP-A/C/D accepted source evidence as immutable.

## Git and local filesystem protocol

Run read-only `git -C /root/workspace/project/quant-v0.6/g1-engineering-preview status --porcelain=v1 --untracked-files=all`, `git rev-parse HEAD`, branch name, `git worktree list --porcelain`, and verified public remote identity. Expected exact task branch and starting HEAD as above. Do not run this in original entry checkout. If task G1 worktree dirty with user changes or moving HEAD/another Agent ownership, stop `BLOCKED_G1_WORKTREE_DRIFT`, **do not reset/clean/stash**.

No rebase, `git reset --hard`, `git clean`, worktree deletion/relocation, `git push --force`, global config mutation, collateral file edits, secrets or high-volume data imports. All temporary test output must stay in unique `/tmp/v06-g1-l2-repair-r1-<pid>`; no shared G2 caches or original protected/archived inputs.

## Targeted L1 tests and terminal proof

- Scope: `git diff --name-status 6eef811... HEAD`, `git diff --check`; explicit absolute scientific/Tactical zero-diff against initial G1 baseline; secrets scan and exact historical-path deletion check.
- Run changed-file Ruff, compile, targeted mypy if runtime source touched; a single focused pytest for manifest path consumption and integration preview safety; **never** drop normal repository hermetic fixtures.
- For H40, record narrowly bounded test selections demonstrating isolation vs combined collection behavior. The independently verified H40 isolated PASS is a valid known datum, **not** a full-suite PASS. If a code fix is made, run one decisive combined reproduction and no broad all-suite until terminal need is specifically justified.
- If functionality remains correct but H40 combined behavior unresolved, stop with blocker and publish evidence; do not claim `READY_FOR_CONTROLLER` release/integration.
- Recheck at least positive synthetic DRY_RUN and negative approval REFUSE/TTL/replay/signed client zero, plus relevant WP-A/C/D tests if touched. No encrypted/provider/exchange I/O.

Add repair receipts under `evidence/v0.6/b_line/engineering_preview_r1/L2_REPAIR_R1_*.json` (exact changed code files + source before/after + test environment/results, whether H40 science test was isolated/combined/full, original worktree/G2 unchanged and `real_funds_write_authority=NONE`). Use an implementation commit and optional evidence-only second commit to avoid circular SHA references.

**MANDATORY ACTIVE PUSH:** after the appropriate scoped tests, proactively stage only allowed paths, commit, and **`git push` to existing `feature/v06-bline-engineering-preview-r1` branch**, not `v0.6`. Verify via fresh remote fetch/query that terminal HEAD, parent chain and changed file list match your claims; report `REMOTE_PUSH_VERIFIED=true`. No need for user to ask push. If cannot push, report `BLOCKED_NOT_PUSHED`. Do not auto-merge or claim TESTNET/LIVE.

Terminal one of:
- `G1_L2_BOUNDED_REPAIR_READY_FOR_CONTROLLER` only if both findings demonstrably resolved and decisive negative tests PASS;
- `G1_L2_H40_CROSS_SUITE_BLOCKED` if collection/order/contamination remains unexplained;
- `G1_L2_SCOPE_REPAIR_BLOCKED` if historical manifest cannot be removed without violating agreed semantics;
- `BLOCKED_NOT_PUSHED`.

Include exact G1 source branch and HEAD, `CONTROLLER_DISPATCH_SHA=deecefafff67f3ce81962477a17af7cf1c97cb7f`, allowed changed paths, original/historical manifest removal, science test comparison status, Python 3.12, focused pass/fail/skips/durations, actual CI links/status if available, no protected reads/writes, and next Controller L2 decision. **Successful repair is not strategy-quality PASS, Protected Retry, TESTNET or real-funds permission.**
