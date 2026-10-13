# P1A-R2 synthetic per-fill cost-contract implementation

Dispatch: `68def8fed3fd290ffbddf00a8f86e4184a8b036f`, `V06_P1A_R2_SYNTHETIC_PER_FILL_COST_ENGINE`.
Execution base and initial source-commit parent: `3af438490da4497132a5c32c786752ca527e0d99`. Branch: `feature/v06-p1a-r2-btc-synthetic-per-fill-cost-engine`.
Accepted P1A R1 design: `a68eeef973a178a68005f7eca247ec15bc9bf2a2`. Prior Controller L2: `efa2df62c02d21b20ce07846c7ca30901716e773`.

## Result and limits

A new isolated standard-library module implements invented-fixture cash contracts. It imports no old experiment, source adapter, account or execution code, and is not connected to scoring or orders. All existing files, including frozen engine.py/portfolio.py and historical evidence, are unchanged. The four dispatch-allowed files are the entire publication diff; no merge or cherry-pick occurred.

Inputs use finite decimal strings/Decimal, bounded to 24 significant digits, maximum adjusted exponent12 and minimum exponent-24. Arithmetic uses a local precision80 context independent of caller settings; USDT cash events use eight decimals and ROUND_HALF_EVEN. Filters declare tick, step, minimum notional and validity interval. No fee-currency conversion or real provider acceptance is implied. Ordinary undiscounted maker0.0002/taker0.0005 rates are fee-only references, not the user's schedule.

Fills have positive BTC quantity, actual USDT/BTC price, independently labeled per-fill liquidity role, source/receiver/execution/ACK clocks and valid arrival quote. Marketable LIMIT cannot claim maker status; an order can have a taker fill followed by a resting maker fill. Only filled quantities incur fees, each on its actual notional. One directional episode allows multiple entries followed by FIFO partial exits; reentry after reduction is outside this finite contract and rejected.

For a flat episode, signed trading cash is side times exit notionals minus entry notionals, with declared per-exit cash-rounding residual. Fees are the sum of independently quantized q*P*f cash events. Funding is -signed economic settlement exposure*settlement Mark*rate. Net cash equals realized trading minus fees plus admitted funding minus explicitly distinct external cash impact. Mid-gross minus fill drag plus rounding equals trading cash. Spread and impact already in actual fills are attribution, not a second deduction. A separately asserted DISTINCT_NOT_IN_FILL cash impact is permitted; overlapping deductions are rejected.

Open inventory shows realized cash, signed remaining BTC and separately valued unrealized PnL. Unknown valuation remains None. Open/no-fill episodes do not report completed net bp. Flat entry-notional bp does not change at 1x/10x/15x; margin ROI is intentionally undefined without a separate margin contract.

Funding snapshots honor receiver-as-of admission and reconstruct economic-time exposure, not inventory at delayed receipt. Missing rate, Mark, chronology, coverage, identity or boundary proof produces COST_INCOMPLETE and None finalized funding/net. A bounded SYNTHETIC witness declares start/end, receiver-known-at and expected settlement IDs; it is an invented fixture assertion, not actual source verification. Inclusive +/-15000ms proximity of any visible fill to settlement is quarantined even when a caller marks the boundary verified. Delayed reports cannot backfill an earlier information set. Same-clock entry/exit and trigger/activation ordering is not invented. Stop-market gaps use supplied actual fill prices/quantities; stop-limit can trigger with no fill. Break-even activates strictly after its activation ACK and after prerequisite receipt/ACK.

## Exact invented results

| Synthetic case | Expected net USDT |
| --- | ---: |
| LONG | `8.834600` |
| SHORT | `9.044600` |
| partial LONG | `6.875760` |
| partial SHORT | `7.003760` |
| flat-mid crossed spread | `-1.040000` |
| adverse LONG | `8.694600` |
| stop gap LONG | `-11.055000` |
| mixed-role | `9.067006` |

These eight values match the accepted design exactly. They are not historical returns or measured cost calibration. All snapshots explicitly carry an invented/not-calibrated label.

## Complete bounded 24-case suite

1. `test_01_long_actual_notionals`
2. `test_02_short_positive_funding_credit`
3. `test_03_signed_funding_symmetry`
4. `test_04_fee_only_reference_identities`
5. `test_05_marketable_limit_is_taker`
6. `test_06_mixed_roles_per_filled_leg`
7. `test_07_maker_nonfill_no_completed_return`
8. `test_08_half_spread_no_double_deduction`
9. `test_09_adverse_direction_and_distinct_impact`
10. `test_10_partial_long_one_entry_fee`
11. `test_11_partial_short_settlement_exposure`
12. `test_12_residual_realized_unrealized_separated`
13. `test_13_tick_step_and_cash_quantization`
14. `test_14_invalid_grid_overclose_and_filters`
15. `test_15_nonfinite_float_and_quote_provenance`
16. `test_16_duplicate_fill_idempotence_and_conflict`
17. `test_17_duplicate_settlement_idempotence_and_conflict`
18. `test_18_stop_market_gap_actual_fill_and_fee`
19. `test_19_stop_limit_nonfill_preserves_inventory`
20. `test_20_ack_delayed_break_even_and_equal_clock`
21. `test_21_delayed_funding_economic_before_after_partial`
22. `test_22_missing_and_ambiguous_funding_fail_closed`
23. `test_23_identical_fills_quote_attribution_not_cash`
24. `test_24_notional_leverage_and_decimal_context_invariance`

The cases contain finite negative subcases for duplicate/conflicting fill and settlement IDs, invalid/nonfinite/binary-float inputs, crossed/stale/sequence-invalid quotes, filter/tick/step/min-notional errors, over-closing, signed cash quantization, maker nonfill, residual MTM, same-clock ambiguity, delayed ACK protection, missing funding data/coverage, future witness receipt, missing settlement identities, and inclusive settlement timing boundaries. There is no randomized search, data collection, market replay or historical scoring.

## Validation and independent review

Targeted pytest: **24 passed, 0 failed, 0 skipped** on Python3.13.13 / pytest8.4.2. Targeted Ruff and format checks passed. Isolated source compilation passed. The repository's existing project lint gate passed using the unchanged bounded EXE001 policy, with no new suppression or allowlist change. Its unmodified risk classifier selects **full** for this new executable; remote CI must retain that selection. A local full suite was not substituted for remote CI.

Frozen source blobs were independently compared to the exact execution base: engine `bf187ace012619eb3f6aee5d9051999459967100`; portfolio `33528e62084feba7c657a657204ccbf41a82cf54`. Module AST imports only dataclasses, decimal, functools and future annotations. Tests run under the repository's existing hermetic guards.

Independent reviewer `/root/independent_cost_review` separately inspected source/tests and recomputed all eight signed ledgers. Initial review blocked the funding boundary boolean and unbounded completeness flag. Both were corrected: inclusive +/-15-second quarantine and typed bounded FundingCoverage. Independent re-review recommended **ACCEPT_SYNTHETIC_CONTRACT** and reran the same24 tests successfully. That review grants no Controller release permission and does not accept actual funding/quote/fill sources.

## Remote CI and terminal

Tested implementation HEAD: `a535fde2aa24e6e0d65a3e353d4a51e532e1abf6`; exact source parent: `3af438490da4497132a5c32c786752ca527e0d99`. This reporting update has that tested implementation commit as its parent and changes only the allowed report and receipt. Source/test hashes are unchanged. The final publication SHA is reported externally because a commit cannot embed its own identity.

[Implementation CI run 38382220675](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38382220675) concluded **FAILURE**. The unchanged CI plan selected **full**, with 2,981 tests: **2,975 passed, 4 failed, 2 skipped, 0 errors**. All 24 new synthetic tests passed in the same full CI run. Full pytest elapsed approximately 780.6 seconds on Python3.12.

| CI step/job | Actual outcome |
| --- | --- |
| Setup, checkout, immutable-base fetch, Python setup, fail-closed plan/classification | PASS |
| Tiny CI-planner dependency install | SKIPPED (normal production/research path used) |
| Production/research dependency install | PASS |
| Ruff with unchanged bounded EXE001 policy | PASS |
| Production package mypy | PASS |
| Compile Python | PASS |
| Changed JSON validation | PASS |
| Full risk-selected pytest | FAIL: 2,975 passed, 4 failed, 2 skipped |
| Scoped evidence artifact retention | PASS |
| Python post-step cleanup | SKIPPED after failure |
| Checkout post-step cleanup | PASS |
| Manual full compatibility job | SKIPPED (push event; not manually requested) |

Exact failing tests:

- `tests.test_v050_r01_surface_reduction::test_catalog_reports_actual_paths_and_parser_without_service`
- `tests.test_v050_r01_surface_reduction::test_catalog_default_stdout_never_recreates_reviews`
- `tests.test_v050_r01_surface_reduction::test_catalog_refuses_agent_documents_on_code_branch`
- `tests.test_v051_h40_m3a_production_discovery_producer::test_p09_through_p18_exact_scientific_graph`

The three catalog tests assert the entire repository `reviews/` directory is absent. This dispatch expressly requires a new report at `reviews/v0.6/b_line/V06_P1A_R2_SYNTHETIC_COST_CONTRACT_REPORT.md`; satisfying that path requirement creates the directory and therefore conflicts with those existing assertions. Moving/deleting the required report or editing those tests is not authorized. The fourth failure compares an existing scientific synthetic-row golden digest: expected `d5a962cd9c9556b573a890b6af8cbeb09d7201187511f477d727c8670bf0b2e0`, observed `ee185f1fce50bdf710295a23506a5c29d83a70c361aff72e2b6be9e54526643d`. No baseline rerun or historical/scientific scoring trial was performed to attribute that mismatch; it remains unresolved outside the new contract. Its test and production scientific source are unchanged. No golden was rewritten.

No H41 lint failure appeared in this run. No failing test was suppressed, CI policy was not changed, and no dependency/configuration/extra path was patched. A documentation-only follow-up CI result cannot clear this failed full implementation gate. The published JSON receipt records actual steps, counts, reviewed code hashes and exact tested SHA.

**TERMINAL: CONTRACT_BLOCKED.** The isolated synthetic cash contract and independent review pass, but complete repository validation is blocked by these four failures. Controller must resolve the required-report/catalog contract conflict and separately adjudicate the scientific golden failure under a new exact-SHA/path dispatch before accepting the implementation gate. No Controller release permission, measured-source acceptance, actual execution calibration, historical repricing, Alpha promotion, TESTNET or LIVE is issued.
