# BTC Execution Cost Method Synthetic R1 — Controller L2 Review

**Date:** 2026-10-13
**Decision:** L2_ACCEPT_METHOD_DESIGN_SCOPE_ONLY
**No economic calibration or strategy promotion.**

## Source and change identity

Task branch: `docs/v06-btc-execution-cost-method-synthetic-r1`.
Remote final SHA: `a68eeef973a178a68005f7eca247ec15bc9bf2a2`.
Parent SHA: `cd0b55e21f85b8d4bf313a4081c9cc1625856267`.
Exact change: one new 158-line documentation file, `docs/project/V06_BTC_EXECUTION_COST_METHOD_SYNTHETIC_R1_DESIGN.md`. No code/test/frozen-history changes. [Source report](https://github.com/EXASHXE/btc-quant-agent-public/blob/a68eeef973a178a68005f7eca247ec15bc9bf2a2/docs/project/V06_BTC_EXECUTION_COST_METHOD_SYNTHETIC_R1_DESIGN.md).

## Findings accepted

- Frozen R3 source at `3af438490da4497132a5c32c786752ca527e0d99` was read and its Git blob identity matches the report. The existing `Cost.effective` adds a legacy spread/slippage proxy to an input raw price; passing an already executable ask/bid without changing input-basis semantics would double-charge crossing.
- Per-filled-leg actual notional, liquidity role, maker vs taker, partial exits, signed funding at settlement with later receiver-known-at, and mark-versus-executable Last distinction are explicitly specified.
- Legacy BASE22/STRESS44 remain sensitivity identities; public 2/5bp ordinary maker/taker USDT-M reference is not an account-specific achieved schedule. Funding source/Mark completeness must fail closed.
- Four future cost scenarios correctly distinguish FEE_ONLY_REFERENCE from measured NORMAL, ADVERSE and EXTREME. NORMAL/ADVERSE are explicitly NOT_CALIBRATED.
- Controller independently recomputed the eight published invented-ledger net USDT examples (LONG 8.834600, SHORT 9.044600, partial long 6.875760, partial short 7.003760, flat spread -1.040000, adverse long 8.694600, stop-gap long -11.055000, mixed maker/taker 9.067006): values matched displayed arithmetic.
- Twenty-four synthetic negative-case acceptance requirements are described; they were **not** implemented or executed. This was docs-only method design and no real quote depth, fill history, actual user fee or verified market-impact distribution was supplied.

## Actual CI

At the exact branch SHA, GitHub workflow https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38377392019 concluded **FAILURE** in `ruff check .`, with six existing H41 lint findings on paths not changed by this one-file diff. `mypy`, `pytest`, and `compileall` were SKIPPED. Do not call the report a green-CI implementation or claim a full suite ran. This documentation-only scoped review is accepted despite separately recorded inherited lint debt; H41 changes or disabled safeguards are not authorized.

## Authority and next gate

**ACCEPTED:** bounded, published, reproducible scientific cost-calculation methodology and future synthetic test / source-measurement plan.

**NOT ACCEPTED:** actual normal/slippage percentiles, realized maker rate or discount, consumer C late-Funding fix, any full source/financial PIT integration, historical PnL repricing, G2 Alpha, TESTNET or LIVE.

**NEXT:** decide separately scoped source and implementation authorizations only after exact path/time/provider limits, fee-source terms, clock identity and independent financial tests are frozen. Public quote evidence alone does not prove maker queue/fill or user fills. Other P1 tracks (F1–F3 method blocked, H18 erratum pending) remain independent and do not inherit this design acceptance.

**Terminal:** COST_RECALIBRATION_METHOD_DESIGNED_PENDING_MEASURED_SOURCE / G2_ALPHA_NO_GO.
