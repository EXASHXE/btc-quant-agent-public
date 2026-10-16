# V065-M3 — Conditional Owner Decision, Release Prerequisites and No-Deletion Receipt R2

**Terminal:** `M3_CONDITIONAL_OWNER_DECISION_EXPLICIT_HOLDS`. **No deletions, no PR closure and no archive rewrite.** Owner's separately submitted decision in this conversation: **"I authorize retirement only after individually applicable ownership/control release, protected-history isolation, and independently durable restoration proofs. This is not a waiver of those conditions. PR #3: KEEP. PR #5: KEEP."** This **does not** satisfy individually applicable release or control restrictions by itself.

**Frozen authority:** `repository-maintenance/v065-m1-prune-r2/HELD_REFS.json`, blob `27bbadacbcf9026f2e2c22ca569fb901ba160a2c`; previous M3 report `repository-maintenance/V065_M3_OWNER_RELEASE_AND_RESTORE_GATE_RECEIPT_R1.md`, commit `c7751167726cd0493cb90a7c2d14b7f0916f98a3`, blob `561830affe4e420a9ad024d3f66b23c28179b570`. This receipt is a separately appended documentary decision record, not retroactive rewrite.

## Ref and PR reconciliation

- **Before 49 / after 49** (final independently refetch after this docs commit required); exactly **3 permanent + 46 governed hold refs**. All **46/46 branch names and full remote HEAD SHAs match exact frozen ledger**; zero unexpected moves. Default `v0.6.5@941f24af8f1e12c1f314e2d970e7af8f97293b21`, research archive `legacy/research-archive@0176cdde836a660420e5e4b5693591cb8108a4f6`, engineering docs previous HEAD `c7751167726cd0493cb90a7c2d14b7f0916f98a3`.
- Governed 42 refs = **26 `HOLD_A_LINE`**, **15 `HOLD_PROTECTED_CONTROL`** and **1 `HOLD_DEFAULT_AND_A_LINE`**. **No independently verified A-line owner / scientific-controller exact-ref release** and **no applicable H40/holdout/control steward release or affirmative safe public exposure review** were presented. The owner's *conditional* retirement preference is recorded, not equated with those independent authorizations. **42 remain held** with individually named original SHA/reason/end condition in immutable HELD_REFS.
- The other **four `HOLD_ACTIVE_PR_OR_BASE`** refs remain held. [PR #3](https://github.com/EXASHXE/btc-quant-agent-public/pull/3) and [PR #5](https://github.com/EXASHXE/btc-quant-agent-public/pull/5) are still **OPEN / DRAFT**. Explicit user choice **KEEP / KEEP** prohibits their withdrawal; preserve heads and bases, no adoption or merge.
- Current GitHub REST repository access reports `admin=true/push=true`, default `v0.6.5`, branch flags `protected=false`; GET rulesets **[]**. Local authenticated `gh` under EXASHXE returned ruleset count **0**, and canonical protection reads **404 Branch not protected** for current main, old default and one H40 validation head. This confirms the sampled protection gate, **not** blanket per-ref deletion-time authorization. No destructive branch API or `git push origin --delete` was invoked.

## Restorability and sensitivity boundary

- Prior independently executed M3 bundle verification recorded owner-approved private M1 bundle SHA256 **`44e9b94242bff4bf950018d61c026639746774aeaab2472c1a65d575d537c8da`**, complete-history `git bundle verify`, a fresh isolated bare-clone **46/46 original SHA commit-object existence** check, connectivity fsck success, and no raw protected content sent to the model or public repo.
- Current local read-only `ls` of M1 approved backup directory reports **two bundle files** `pre-prune-allrefs.bundle` and `pre-prune-execution.bundle` **in the same directory**. **No independently durable second location, new complete restore proof for that second bundle or independent Gemini receipt has been established.** Two files in one directory do **not** substantiate independent failure-domain durability. No new public archive parents created: restricted H40/holdout graph stays isolated from any new public archive merge.
- Hence **eligible deletion set empty**, no batches, no deleted named refs, no response receipts, no rollback pushes and no false claim of a 49→7 or 49→3 outcome. No source/config/test/protection/workflow/market/funds operations.

## Effective action and remaining exact blockers

1. **42 governed refs:** individually applicable independent A-line/control releases binding each frozen name/SHA; before any graph extension, separate positive classification/sensitivity/visibility decision for H40/holdout history.
2. **Backup:** actual independent Gemini 46/46 proof if required, **second independently durable** restorable backup and remote/ref re-fetch for an eligible batch. The current one-location pair is insufficient.
3. **Deletion transport:** fresh branch-specific protection and active dependency checks **only after release**, no force/wildcard commands. PR #3/#5 KEEP requires all four PR dependency refs remain untouched.
4. **CI:** M1 CI #38918484549 at the old main commit was SUCCESS but is not an M3 CI run; docs-only author receipt has no assumed workflow result. Check actual new commit separately. No code/config touched; no tests were run.

**Gates unchanged:** `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`. No successor or scientific approval is inferred.
