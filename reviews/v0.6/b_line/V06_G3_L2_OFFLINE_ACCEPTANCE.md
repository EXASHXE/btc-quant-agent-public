# V06 G3 R1 — Controller L2 scoped offline engineering acceptance

**Exact terminal G3 feature SHA:** `1b4ba5ace44a84af03a734462b468e597e62c85b`, original G3 `2db580bb8c9e4e7811a4d892312584e55b4fa8e6`; Controller two-file executable-mode fix `9e753972beab43b4ea8397150dab42f7f66d6968`; L2 evidence integrity implementation `4cb7bfa35c611eaed45b16f5b91d2a7edf0c2fbc`, evidence terminal `1b4ba5ace44a84af03a734462b468e597e62c85b`.

**Controller limited decision: `ACCEPT_G3_SCOPED_OFFLINE_EVIDENCE_REPAIR__INTEGRATED_IN_V06__DEPLOYMENT_PROVIDER_PENDING`.** This is an accepted engineering/reporter and synthetic safety test sidecar, **not** complete G3 deployed release readiness.

### Core verified evidence

- Remote G3 original [37784968745](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37784968745) FAILED `EXE001` because 2 new shebang files were mode 100644. Controller fixed them to mode 100755 at `9e753...`, content SHA unchanged.
- Final independent G3 [CI 37796933670](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37796933670): **2785 PASSED / 2 SKIPPED / 0 FAILED / 9 warnings** on exact `1b4ba5ace44a84af03a734462b468e597e62c85b`, Python3.12. New test planner mode FULL for G3 code changes, not docs-only. L1 local scoped 21 PASS, 0 FAIL/SKIP, separate JUnit case mappings, injected negative controls.
- G3 reporter no longer writes hardcoded scenario PASS. Its 7 claims are sourced from exact pytest JUnit test outcomes, and deliberately failed, missing or skipped cases cannot become PASS. `ENABLED_PASS` is now unreachable from environmental credential presence alone, no external provider call was made. Process peak RSS is correctly labelled instead of steady-state memory; cold-start timing uses actual measured clock, no migration-time multiplier; WSL2 kernel is explicitly identified as `WSL2_LINUX_KERNEL`. Worktree preservation uses pre/post metadata comparison (branch/HEAD and dirty counts); do not mistake this for file-content integrity audits of G2. Scoped mock signed exchange calls observed 0, not global cryptographic absence guarantee.
- **Remaining limited caveat:** `G3_PERFORMANCE_SNAPSHOT.json` `extrapolation_disclaimer` still says “isolated Linux VM fixture”, while platform receipts say WSL2. Treat the WSL2 source and bounded benchmark as authoritative and **do not use the VM-description phrase for deployment certification**. Process simulation mock SIGTERM is NOT actual uvicorn process lifecycle; Dockerfile static lint is NOT launched container; OpenAI and Feishu external nontrade are both `NOT_RUN`.
- No core application `src/**`, H40/H41, frozen MarketWatch or G2 research files changed. Feature diff to merged G1 origin contains 13 G3-scoped paths. G3 therefore qualifies for **non-executable operations/test infrastructure merge only**, with no production release manifest binding.

### Controlled integration

Two-parent non-force Controller merge `v0.6@e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`, first parent `a56cc413d87a71111f2be02f10052dced9ff0275`, second parent `1b4ba5ace44a84af03a734462b468e597e62c85b`. 13 exact G3 scoped paths, no protected diffs. [Post-G3 mainline CI 37799770194](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37799770194) launched — **PENDING at time of this review**; do not assert passed before its final result.

### G3 completeness and forward gates

**Completed:** scoped offline Linux/WSL2 Python3.12 test harness, worker locks, simulated SIGTERM, negative approval replay/TTL/hash, recovery fixtures, fail-closed smoke status, honest test receipts. **Still missing:** native Linux environment / actual app service lifecycle, container run under isolated test-only mode and authenticated OpenAI/Feishu **nontrading** request/response with dedicated operator test credentials (if supported). Any external smoke must never accept live trade commands or customer account data. These are operational prerequisites to G4 release; no need to rerun the same 2785 tests for each edit.

`G3_DEPLOYMENT_RELEASE_AUTHORITY=NONE`, `G4_TESTNET=NOT_AUTHORIZED`, `REAL_FUNDS_WRITE_AUTHORITY=NONE`. A limited engineering merge does not upgrade either gate.
