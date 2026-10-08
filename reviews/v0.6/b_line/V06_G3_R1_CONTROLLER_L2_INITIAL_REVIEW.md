# G3 R1 — Controller L2 first-pass review and bounded integrity repair dispatch

**Exact G3 initial remote SHA:** `2db580bb8c9e4e7811a4d892312584e55b4fa8e6`; direct parent merged `v0.6@a56cc413d87a71111f2be02f10052dced9ff0275`. G3 changed 11 new files, all in intended G3 test/operations/evidence directories, zero application source edits. G1 integrated postmerge CI [37778010147](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37778010147) **SUCCESS**, hence G3 dispatch precondition fulfilled.

**Controller disposition:** `G3_R1_L2_EVIDENCE_INTEGRITY_BLOCKED_BOUNDED_REPAIR_DISPATCHED`, not whole G3 PASS. Executor's reported 11 locally passing hermetic tests is acknowledged but insufficient for deployment/provider certification.

### CI finding and direct mechanical repair
[Original G3 CI 37784968745](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37784968745) FAILED before tests: the two new operational scripts have Python shebangs but git mode `100644`, triggering `New/touched EXE001 violation`. Controller pushed a mode-only commit **`9e753972beab43b4ea8397150dab42f7f66d6968`** to the existing G3 branch, changing both to `100755` without touching contents. [Follow-up CI 37789769108](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37789769108) was launched; its terminal result must be read, not assumed success.

### Evidence integrity BLOCKER/HIGH findings

1. **Hardcoded 7 scenario PASS receipts** in `scripts/ops_g3/run_operational_readiness.py` before `run_tests()` — a failed or missing test could still publish PASS. Needs parse-backed per-scenario evidence/negative tests.
2. **False external success:** only `BTC_QUANT_G3_EXTERNAL_SMOKE=1` and existence of any env credential leads to `ENABLED_PASS` with zero actual network calls, while the same receipt says OpenAI and Feishu NOT_RUN. No external provider smoke has been demonstrated. Must fail closed until separately authorized observed request proof.
3. **Invented measurement:** `runtime_cold_start_ms = migration_ms * 1.1` without a corresponding timed startup; `steady_state_rss_mb` derives from process peak `ru_maxrss`, not steady state. Actual host reports `6.6.87.2-microsoft-standard-WSL2`, not native production Linux VM; Docker daemon unavailable.
4. **Preservation/write claims:** `WORKTREE_PRESERVATION.json` unconditionally asserts `preserved=true` for all extant worktrees; zero write statements have test-only mock scope and must not imply global verification.
5. **Simulation vs deployment:** SIGTERM scenario exercises synthetic standalone daemon, not actual deployed uvicorn app; Docker is string-search static lint. This is valid as limited mock testing only, not certified native deployment.

The current G3 scenario matrix and review conflate reported local pytest success with broader capabilities, so Controller **cannot** accept G3 as a completed operational gate. No application source was changed, so accepted G1 engineering remains unchanged. G2 R2 `66aad50500bf6e860e76bf3ae8c0ef70799d5f47` is an independent pre-registration task in progress and is not to be modified or promoted as alpha.

[Bounded G3 evidence integrity repair prompt](../../prompts/v0.6/b_line/V06_G3_EVIDENCE_INTEGRITY_L2_REPAIR_R1.md) authorizes edits only within G3 scripts, tests, docs and task receipts. Original G3/G1 source behavior, scientific code, protected RC2, exchanges and providers remain fenced. **TESTNET=NOT_AUTHORIZED, REAL_FUNDS_WRITE_AUTHORITY=NONE.**
