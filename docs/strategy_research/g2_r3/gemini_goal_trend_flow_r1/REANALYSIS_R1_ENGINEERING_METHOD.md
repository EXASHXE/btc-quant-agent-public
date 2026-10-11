# Fixed-24 exposed-development economic correction: method stop

Task `V06_G2_GEMINI_A_FROZEN_24_HYPOTHESIS_ECONOMIC_MODEL_CORRECTION_AND_RECOMPUTE_R1`.
Original Gemini-A code/results SHA `a37721eaa1f3cd176146df6bdb63fbd17746189e`.
Prompt SHA `ed36be58f6c6a539a92322a2274b58ee23bae8a8`; Controller SHA `62723dcc25dab88187e2d3f96e032a562121324e`.
Requested parent model: Codex GPT-6 Sol High. Exact root model/effort are not exposed by the session; no unsupported identity attestation.

This branch contains `CORRECTED_REANALYSIS_OF_EXPOSED_DEVELOPMENT_DATA` engineering work, **not completed empirical reanalysis**. All four original freezes, results, reports and cumulative ledger remain immutable. No new hypotheses, periods, thresholds, horizons, stop multipliers, targets or cooldown settings are selected. Signal function ASTs remain identical to the original implementation (one unused import removed). The 24 IDs and 72 horizon/stop-multiplier/target-R constants match the frozen registries; this is not full formula/temporal admission.

## Corrections supported by synthetic checks

Each leg of BASE charges 6bp fee, 2bp half-spread, 3bp slip; STRESS charges 12/4/6. At flat raw prices and tick-aligned legs the long and short roundtrip is exactly 22/44bp on original notional. Fees use actual executed entry/exit notional; other prices/tick rounding need not total exactly the nominal number. Net PF uses net USDT; gross PF is separately identified. Zero support/undefined PF and block lower bounds are null, never manufactured zeros or evidence of edge.

Replay accepts one position, 1x entry budget capped at min(settled equity,1000USDT), 5% reserve, conservative entry/exit/funding reservation, continuous settled account equity across folds, separate true minute-close liquidation-cost proxy equity, and explicit exit ACK before new spendable-cash use. Funding reserve is not an invented bill. 12% drawdown is a promotion criterion, not a newly introduced trading kill rule. Adverse short moves may increase marked notional/equity above 1x; entry admission and marked-exposure diagnostics are separate. No new dynamic reductions are invented.

Statistics accept actual minute-equity curves, distinguish trade-close DD, and fail closed if MTM/control evidence is absent. Fixed UTC Feb2021–Dec2023 7/14d calendars include empty blocks; identical seed42/10,000 calendar draws, 48-familywise one-sided alpha=0.05/48. Both bounds, positive absolute/equal-year mean, net PF>=1.15, worst year>=−10bp, MTM DD<=12%, n>=100/2years/6months, and positive matched-control increment are required. Balanced LONG/SHORT control execution has not been empirically produced; no claim of paired evidence is made.

The legacy `execute_wave` writer is explicitly disabled in this correction branch because it overwrites immutable WAVE results/decisions and the original cumulative ledger. This API behavior change is intentional and tested. The old inner pass binds `cand` and `cand_id` explicitly; synchronous original execution is not characterized as an exploited late-binding bug.

## Hard method conflicts before source body access

1. W1_C06 says recent 4h cumulative signed taker volume. Original code indexes a 1h ratio array with a 4h bar index and sums unweighted ratios. Both time and volume units differ. Synthetic witnesses reverse the signal sign.
2. Frozen TIME_CAP says horizon-bar close. Original replay takes horizon-minute open, capped at target. Different clocks/prices yield different returns.
3. Frozen next-open rule enters immediately after the last 1m signal bar closes. Original signal code enters another 60s later. This affects all24 models.

The immutable Prompt says: “If the exact forms cannot be recovered or coherent, stop”. Controller requires `BLOCKED_FIXED_REGISTRY_REPLAY` in this case. Choosing prose versus executable behavior would change the strategy/temporal identity, outside economic-only correction authority. Method clarification was requested; no alternative is presumed approved. The authorized default is **STOP**, terminal `CORRECTION_INCOMPLETE_FAIL_CLOSED`.

No historical source body, header/footer or price list was read for this task. Only existence/count of permitted A-owned 2021–2023 scratch archives was checked; no source checksum is claimed revalidated. No protected2024–2026, owner Quant-agent/data, account/API or other worktree outcomes were accessed. No corrected real return, matched control, source integrity PASS, promotion or five-real-episode Decimal audit is claimed. The original negative conclusion remains economically untrusted until coherent reanalysis is authorized.

## Scoped validation

44 actual synthetic/contract pytest checks passed; task-local Ruff and Python compile passed. A manual strict mypy invocation on scripts returned53 errors in6 files; these scripts are outside configured `files=["src/btc_quant_agent"]`. This is reported as FAIL, not relabeled success. No whole-repository CI or typing repair loop was run.

Reproduce only the no-market preflight and synthetic checks:

```bash
python3.12 -m scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_preflight
python3.12 -m pytest -q tests/test_v06_gemini_goal_trend_flow_r1_*.py
ruff check scripts/strategy_research/g2_gemini_goal_trend_flow_r1 tests/test_v06_gemini_goal_trend_flow_r1_*.py
python3.12 -m compileall -q scripts/strategy_research/g2_gemini_goal_trend_flow_r1
```

A separately resolved method contract must identify W1_C06 flow clock/units, TIME_CAP open/close, and first/second eligible open before any real rerun. Recompute would then still be exposed DEVELOPMENT, `COST_PROXY_DEV_ONLY`, not blind validation; true Mark, Funding, historical fees/filters and source known-at remain UNKNOWN. No reserved validation, Alpha or trading authority follows from this branch.
