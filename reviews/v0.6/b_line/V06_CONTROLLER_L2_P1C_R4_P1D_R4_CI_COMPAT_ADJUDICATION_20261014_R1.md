# B-line Controller L2 — P1C-R4 closure, Codex P1D-R4 and CI-history validation

**Date:** 2026-10-14 (Asia/Shanghai).
**Owner:** ChatGPT-0, quant v0.6 B-line Controller.
**Dispatch context:** `cf9796fe638d9d6046d8a05c3c6a9ca5785765d8`. **Scope:** read-only adjudication of already published branches, fixed-SHA reviewer artifacts and public CI receipts. This adjudication does NOT retroactively modify old review records or auto-merge code.
**Strategic invariant:** `G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.

## 1. P1C-R4 — accepted for exact documentary correction only

Controller citation-only authorization `a2b81f8b02d76cdb7f10edb393403a5b7472a9c4`.
Stage A author repair: `62b06100eda56ee4af4b5051c5d67ac50dd461df`, one newly added file `reviews/v0.6/b_line/V06_P1C_R4_FIVE_CITATIONS_REPAIR_R1.md`, Git blob `42dbd2b9cf9feeb7324ab3ab43563340e158a66a`.
Separate independent audit: `e7a3f1100f781b8c0ecea6640a454f924b5ffeb3`, one newly added file `reviews/v0.6/b_line/V06_P1C_R4_FIVE_CITATIONS_INDEPENDENT_REVIEW_R1.md`, Git blob `124d5f6fbd7b134336584f5807190ee81c16eba9`.

Independent audit terminal `REVIEW_PASS` applies to FIVE exact replacement citations and ONE qualified reviewer-exclusivity assertion only. All 5 source citations match pinned frozen R3 auditor/JSON source line contents; the qualifier states `the only attributable independent R3 review established in the scoped evidence`. The audit noted JSON #L726-L744 is the required relevant excerpt, not the full object brace-to-brace (#L725-L747); this is non-blocking because #L737 and the required quoted field are correct. Repair author did not self-certify; old frozen documents, failed R3/R4 audit receipts and 42-cell crosswalk remain immutable.

**Controller verdict: `L2_ACCEPT_P1C_R4_DOCUMENTARY_CITATION_CLOSURE`, exact frozen repair + independent audit SHA only.** Historical R3 `REVIEW_FAIL` and prior R4 Stage B `REVIEW_FAIL` are preserved as immutable intermediate outcomes. Previously independent R3 42/42 numeric source-summary crosswalk remains a narrowly supported historical sub-result; there is no new 42-cell historical replay, Alpha proof, economic cost calibration, or strategy approval.

## 2. P1A CI compatibility — accepted at tested exact implementation/workflow SHA

CI forensics docs `4e350fdce4bf79ef4b3cea8e3499a29a7d776f39`, file `reviews/v0.6/b_line/V06_CODEX_CI_COMPAT_GIT_HISTORY_FORENSICS_R1.md`, Git blob identity as published in that commit.
Candidate code `13e3a710b137efeec2e21e3002f748834ec0cc22`, parent `bc91a9d58701f5ace3b7d26e912e2a81ad9502a5`, branch `repair/v06-p1a-compat-full-git-history-r1`. One-file diff only: `.github/workflows/ci.yml` adds `fetch-depth: 0` to the compatibility checkout (the quality job already used it). No test skip, waiver, H40 golden change or source/test diff.

Actual manual `workflow_dispatch` / `profile=full` GitHub Actions run [38494710188](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38494710188), head exact `13e3a710...`, completed **SUCCESS** with THREE successful jobs. Each Python3.11/3.12/3.13 job reported **2,979 passed / 0 failed / 2 skipped** (2,981 selected). Python3.12 includes quality lint/mypy/compile. Previously broken Git history tests and H40 diff guard passed in this candidate run. Two skips are pre-existing, not new.

**Controller verdict: `L2_ACCEPT_P1A_CI_HISTORY_FIX_EXACT_SHA`.** This is engineering workflow gate acceptance on this P1A SHA, **not** cross-branch source integration, source-cost empirical admission, or proof that the previously varying H40 graph digest discrepancy is scientifically resolved on all branches/platforms. Do not adopt this change onto P1D without a new exact-SHA integration/test dispatch. No current merge authorization.

## 3. P1D R4 synthetic G1 causal Funding prototype — not integrated

Independent pre-repair audit `e11f84963adddc29b1dc106c1e0d2a984dd6add2` on old P1D R2: F1 clock semantics BLOCKER; F2 Mark/exposure ledger BLOCKER; F3 dedupe/coverage HIGH.

New candidate `81a71467ac7a9b852587b6e5f826d8ee28fc769c`, parent `04cbc46497ed26b0c4e889f30fa10eb8d666a79e`, branch `feature/v06-p1d-r4-synthetic-g1-funding-causal-integration`. Authorized scope: 6 existing core/port/test paths modified, one new synthetic R4 test module and one engineering evidence note. No H40, H41, CI workflow or `reviews/` code-branch changes. `docs/engineering/v0.6/V06_P1D_R4_SYNTHETIC_CAUSAL_INTEGRATION_EVIDENCE.md` at candidate SHA documents synthetic F1/F2/F3 closure tests, 50 local R4 cases, late receipt event-time separation, pre-settlement exposure, WAL exactly-once and crash tests. Local test claims are author-report evidence, NOT independent post-publication exact-SHA review acceptance.

Actual HEAD push CI [38446896902](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38446896902), exact SHA `81a714...`, Python3.12 **3408 passed / 2 failed / 2 skipped**; two precise failures:
1. `tests/test_v06_g1g3_offline_ports_r1_recovery_and_guards.py::test_static_ast_and_c4_core_immutability_verification`: `G1_CORE_MUTATED:scripts/g1_offline_preview_r1/model.py`. `no_order_port.py` immutable `PINNED_G1_C4_MANIFEST` freezes exactly thirteen old C4 files, including candidate-modified model/reducer/storage. This is a bona fide versioned contract/identity incompatibility introduced by authorized R4 implementation, **not** a safe test skip.
2. `tests/test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph`: expected `d5a962...`, observed `ee185f1...` fixed synthetic graph digest mismatch. This is a separate A-line/H40 authority hold; no exception, waiver or golden updates.

**Controller verdict: `P1D_R4_SYNTHETIC_PROTOTYPE_DELIVERED / INTEGRATION_BLOCKED_C4_IDENTITY + H40_UNRESOLVED`.** No final post-publication independently authored code audit of this precise candidate has been established. The apparent F1/F2/F3 bounded local functional improvement is valuable but remains conditional. A passing P1A CI run is not P1D CI clearance.

### Required next gates, without auto-grant

- **P1D C4 identity design:** independent exact-SHA design review must determine whether retaining old C4 immutable 13-file core **and** introducing new versioned R4 immutable identifiers can safely coexist. Key architectural choice: new isolated versioned G1 engine implementation files vs explicit and separately approved dual-version manifest, with negative tamper/AST/import guard tests and genesis/WAL cross-contract quarantine. Do NOT simply replace pinned C4 SHA hashes in `no_order_port.py` or weaken `G1_CORE_MUTATED`; such work needs fresh exact-SHA, narrowly defined Controller code authority and separate independent review.
- **P1D CI-history integration:** adopt the now-proven checkout `fetch-depth: 0` behavior only after an explicit exact-SHA P1D workflow grant; run genuine full CI on final freeze, not a docs-only or scoped green.
- **H40 independent A-line owner:** investigate public fixed-graph digest and cross-job variation under separate authority, without B-line protected corpus reads/edits. Do not treat P1A's run success as an H40 scientific waiver.
- **P2 BTC feasibility:** existing independent Challenger report `6a35092d280dd35c7d1e81c4b6816540df847a16` retains six methodological/data-source objections; source/cost/frequency remain design only, source permit and G2 development scoring NOT GRANTED.
- Only after P1D versioned contract + independent audit + actual CI/owned H40 gate acceptance may Controller separately consider G1/G3 guarded integration. G2 Alpha/TESTNET/LIVE remain out of scope.

## Write, access and attestation truth

This Controller record is one new document only on `v0.6-docs`, no branch merges. Controller read public GitHub exact commits, changed file lists, summary receipts, H40 public failing test identifiers and job logs; it did not rerun protected H40, inspect owner/private data, reproduce synthetic P1D tests locally, ingest market data, execute backtests, or use exchange/private account. It is an attributed governance adjudication, not a substituted independent engineering audit.
