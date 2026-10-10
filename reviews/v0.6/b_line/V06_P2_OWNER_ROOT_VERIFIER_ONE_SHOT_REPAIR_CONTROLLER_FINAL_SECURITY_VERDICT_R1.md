# v0.6 B-line — Controller final one-shot P2 verifier adjudication R1

**Decision: P2_VERIFIER_ONE_SHOT_REPAIR_FAILED_SECURITY_SEMANTICS__STOP_THIS_VERIFIER_PATCH_BUDGET__PRESERVE_METADATA_EVIDENCE**

Date: 2026-10-10. Limited data-location evidence ACCEPTED; verifier code-quality CI PASS; production fail-closed safety **NOT accepted**. Do not conflate these three independent gates.

## 1. Immutable identity and actual CI

- Original Controller repair dispatch SHA: 52830a73adf9e8c318da8efa8f10c6323a6292b8. Prompt SHA: 6ef27e3d6a646786da691ad784497211a775fe83.
- Exact remote branch: feature/v06-bline-p2-owner-exact-root-metadata-r1 at 4a1fcc2871708f0e9e3a7c40036ecaab39ba99b8, exactly one direct child of c6823dbc46249cac43aa10400aacbbe9f4542410. Nine changed paths: five P2 verifier package Python files, two P2 verifier test files, two new supplemental scoped repair docs/evidence. All within authorized scope, and the historical original six-month receipt/report/matrix were NOT modified.
- Actual [GitHub Actions 38017621125](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38017621125) **SUCCESS**, not inherited H40 failure. Ruff PASS with 0 of the previous 20 new errors; mypy zero issues in 161 source files; compile and JSON checks PASS; **2,831 pytest passed, 2 skipped, 9 warnings in 875.97 seconds**. Manual compatibility suite skipped. The original 20 Ruff CI violations are indeed fixed.
- [Executor repair receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/4a1fcc2871708f0e9e3a7c40036ecaab39ba99b8/evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_VERIFIER_REPAIR_EXECUTION_RECEIPT_R1.json) reports 25 scoped tests and 46 combined P2 tests, all synthetic only; full GitHub result independently corroborates broad test execution, not the precise security assertions below.

## 2. Material source-level security defects remain at exact repaired SHA

**F01 — CLI bypasses fixed owner-root production restriction.** At scripts/strategy_research/p2_owner_root_metadata/cli.py, run_cli around lines 296–297:
- is_custom = args.allow_custom_root or (args.data_root != DEFAULT_OWNER_WSL_DATA_ROOT)
- probe = OwnerRootProbe(data_root=args.data_root, allow_custom_root=is_custom)
A caller passing ANY non-default --data-root **automatically disables** OwnerRootProbe.__init__ exact owner-root production restriction, even without explicitly requesting the test-only --allow-custom-root option. Direct-constructor test asserting reject when allow_custom_root=False does NOT cover the vulnerable CLI behavior. Violates prospective fixed-path access contract. This is a source-level attack surface, NOT proof an unauthorized path was actually read.

**F02 — actual lstat calls exceed protected call counter.** At scripts/strategy_research/p2_owner_root_metadata/probe.py, scan_selected_months and scan_additional_targets around lines 183, 226 and 355 call **os.lstat** directly after _verify_path_components_non_symlink has already run _safe_lstat checks. _safe_lstat alone increments counters and enforces MAX_LSTAT=100; the subsequent direct calls are uncounted. The cache of previously checked components also means only unique component observations count, not actual filesystem stat invocations. Therefore reported counters.lstat_calls cannot be used to certify the hard execution ceiling for real system calls. CI lacks an instrumented OS-level call-count assertion. Six-month original receipt was generated using the previous source and remains immutable; do not backfill/alter its numbers.

**Ancillary limitations:** probe.py around 422–425 maps root PermissionError to terminal P2_OWNER_ROOT_NOT_PRESENT_AT_EXACT_PATH (reason text says permission), merging inaccessible with absent in machine status. verify_ancestors checks symlink but an existing non-directory ancestor need not set all_ok=False. These are additional unaccepted quality limitations, not claims of actual compromised data.

The repair did add substantial protections: component-by-component symlink checks, more specific exception handling, commonpath checks and new adversarial tests. Those are credited, but do not negate F01/F02. All claims of real market dataset corruption, protected data access, nonzero market body reads, or strategy returns are **UNSUPPORTED** and NOT asserted by Controller.

## 3. Scientific and data location consequences

- Preserve executor metadata-only location evidence from c6823dbc46249cac43aa10400aacbbe9f4542410: owner-declared /root/workspace/project/Quant-agent/data/research/BTCUSDT and 6 regular 1-minute BTC perpetual candidate monthly Parquet files (2021-03/04, 2023-03/04, 2025-03/04) with nonzero sizes. It is evidence of exact stat-only executor observation, not independent Controller WSL remeasurement or full source admission.
- Confirmed metadata file/dir presence does NOT validate schema/rows/monotone clock/hash/true continuous minute Mark, Funding known-at/settlement, historical filter and fee/impact assumptions, licences and user rights, or ETH/SOL perp minute data.
- **One-shot verifier repair budget exhausted and terminal:** P2_VERIFIER_REPAIR_FAILED_STOP. No automatic second hotfix or reuse of this unaccepted verifier for next source-admission gate. Do not reopen old P1 VirtualBook or event ledger; both terminal NO-GO.
- A separately approved NEW, document/science-only source admission design may use frozen metadata receipts as input and design restricted selected historical source/provenance/Mark/Funding audits **without reading any real market data bytes**. Any later actual data-body reading or verifier implementation needs new explicit Controller authority with an independently verified path/limit safeguard; P3 prereg and protected periods remain sealed.
- A-line and Performance unaffected. R4 Sol opportunity research conditional not validated Alpha; P2 SOURCE_ADMITTED=NONE; P3 first-pushed prereg NONE; P4 market-body read NONE; TESTNET/LIVE/REAL_FUNDS authority NONE.

**Final machine interpretation:** SIX_SELECTED_BTC_METADATA_LOCATED; REPAIR_CI_GREEN; PRODUCTION_VERIFIER_FAIL_CLOSED_NOT_ACCEPTED; ONE_SHOT_PATCH_CAMPAIGN_TERMINATED; NEXT=P2_SOURCE_ADMISSION_DESIGN_ONLY_UNDER_NEW_SCOPE.
