# G1 Engineering Preview L2 Findings Repair R1 — Controller exact-SHA review

**Exact reviewed remote feature HEAD:** `efd73496d01a71a158d67343b64695d33fab16a8`; parent `9867a4e3994b3ab98064e01f2a20eb446b30d18c`; feature start `6eef811961bfbe1341eee79b2450a4266d277302`. This has **two** non-force appended commits. Branch is `feature/v06-bline-engineering-preview-r1`. Development dispatch `deecefafff67f3ce81962477a17af7cf1c97cb7f`.

**Controller disposition: `ACCEPT_G1_R1_MANIFEST_SCOPE_REPAIR__H40_FULL_SUITE_CAUSALITY_UNRESOLVED__HOLD_V06_INTEGRATION`.** This is scoped verification, **not** release or TESTNET authority.

## Finding 1 — CLOSED, limited acceptance

GitHub exact-SHA compare from `6eef811...` to `efd73496d01a71a158d67343b64695d33fab16a8` proves the newly introduced historical path `evidence/v0.5.5/live_v1/RC1/WP_D/B_LINE_INITIAL_USABLE_RELEASE_V1_RC1_MANIFEST.json` was removed from feature, rehomed to `evidence/v0.6/b_line/engineering_preview_r1/RELEASE_MANIFEST_TEMPLATE_UNBOUND.json`. The rename diff shows no broad rewrite; only one self-referential artifact path changed within JSON. Matching references were updated in `src/btc_quant_agent/api.py`, `tests/test_live_v1_rc1_wp_d_release_engineering.py`, and `docs/LIVE_V1_RC1_OPERATIONAL_RUNBOOK.md`. Executor reports 33 WP-D release-engineering and 4 preview tests passed, compiler/Ruff PASS.

The template's `source_sha=UNBOUND_PENDING_RC_INTEGRATION`; it is NOT a bound release manifest. `--verify-manifest` with default `require_bound=false` checks template validity but does **not** certify integration identity or grant release authority. RC integration must later run bound verification with Controller-accepted WP-A source and exact integration SHA.

No new code source change under H40/H41 or Tactical/MarketWatch paths was detected in this fix. Original G1 feature remains **separate** from `v0.6`.

## Finding 2 — UNRESOLVED, no unsound inference

Original [G1 CI 37755191706](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37755191706) on `6eef811...` had **2767 passed / 1 failed / 2 skipped**, H40 test `test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph`, actual `ee185f1fce50bdf710295a23506a5c29d83a70c361aff72e2b6be9e54526643d`, expected `d5a962cd9c9556b573a890b6af8cbeb09d7201187511f477d727c8670bf0b2e0`. H40 source and test byte hashes unchanged vs initial accepted `d6500140...` baseline.

Independent exact-SHA [H40 isolated comparison 37759244599](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37759244599) passed on both baseline and G1. Executor L2 reports an additional H40 golden isolated 1 PASS, producer 26 PASS, a G1-heavy preceding chain 696 PASS, and H40-related chain 189 PASS. **These do not reproduce or resolve the one original full-suite golden mismatch.** Causality remains `UNRESOLVED`. Do not mark inherent/irrelevant/global pollution as proven, edit H40 golden, or weaken tests.

### Additional Controller evidence-quality discrepancy

The appended `L2_REPAIR_R1_H40_DIAGNOSIS.json` claims `observed_graph_digest` and `expected_graph_digest` were both `d5a962cd67a7b819fbc74d8121f64964646700c0f9949d0124ad49b8095b5463`. **This is inconsistent with the unchanged exact test source** at both baseline and G1, where the first scientific-projection expected golden is `d5a962cd9c9556b573a890b6af8cbeb09d7201187511f477d727c8670bf0b2e0`. No per-test runtime digest print of that reported `d5a962cd67...` value has been independently verified.

Consequently, Controller accepts the independent test **pass/fail exit statuses only where substantiated** (GitHub Actions), but **rejects these asserted per-test digest fields as identity evidence**. A future diagnostic receipt must distinguish the actual first `scientific_projection` golden from any other digest and derive observed values from machine captured output, not invented or human-transcribed approximations. This does **not** imply the test failed: both independent isolated test runs did pass.

### One bounded differential run already initiated

To avoid repeated 2770-test development loops, Controller started a single GitHub test on the **pre-G1 baseline** `d6500140f3141d179181f2360ad815b5bfe9c954`, pinned Python 3.12, same editable `.[dev,research]` dependencies, and the full hermetic pytest suite, in separate throwaway validation branch `validation/v06-h40-baseline-full-suite-r1`. [Run 37773542782](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37773542782) — independent only, result not assumed in this record. This directly asks whether the full-suite failure is present without G1 at all. The repaired G1 SHA has its own independent run [37772124985](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37772124985); until both definitive results exist, no full-suite PASS is claimed.

If baseline fails same golden with G1 failing, classify inherited **only after confirming comparable cause**, then isolate global state in a separate science/CI issue; release gating still requires explicit exception or proper fix. If baseline passes and G1 fails, G1 integration remains blocked pending exact culprit. If both pass, the prior failure is intermittent/unreproduced rather than solved. If tests stall/incomplete, status is `INFRA_INCOMPLETE`. **No number of focused PASSES overwrites the original full-suite FAIL automatically.**

## Completion and next authority gate

- `G1_FINDING_1=ACCEPTED_CLOSED`.
- `G1_FINDING_2=UNRESOLVED_PENDING_EXACT_SHA_FULL_SUITE_DIFFERENTIAL`.
- `G1_COMMIT_SHA=efd73496d01a71a158d67343b64695d33fab16a8`.
- `G1_INTEGRATION_INTO_V06=HELD`. Current v0.6: `03c4b5ebea299a11a5f0c64f45572b27cc4ad4b8` (CI-only advancement; source/G1 branches have diverged).
- `RC2_POLICY_QUALITY_AUTHORITY=NONE`, `RC2_PROTECTED_RETRY=NOT_AUTHORIZED`, `TESTNET_OPERATIONAL_RELEASE=HELD`, `REAL_FUNDS_WRITE_AUTHORITY=NONE`.
- Controller next: adjudicate the two bounded independent runs at exact SHA; prefer narrowly scoped source/fixture repair or formally recorded pre-existing baseline failure. Never auto-merge G1, auto-retry protected sources, or authorize orders.
