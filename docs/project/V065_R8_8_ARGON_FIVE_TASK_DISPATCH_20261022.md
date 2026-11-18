# R8-8 / Argon — Five-Task Dispatch and Completion Evidence, 2026-10-22

**Final status at 09:33 Beijing: 5/5 completed, all exit code 0, no retry required.** The three first-batch jobs started at 01:54 Beijing; the two post-06:00 jobs started at 06:05 and 06:15. Every run has a real Codex thread-start event, task-specific output and an exit receipt. All five are separate detached worktrees at baseline `40c70c740f352d1b444decb75276196d17a72dd2`.

## Frozen economic starting point

R8-7 completed with 545 frozen BTCUSDT X-only 8h modeled reference events (2021–2023). Gross cash PnL -3,081.947168 USDT; base ex-funding -11,802.832667; stress ex-funding -20,523.718167; base Profit Factor 0.719279; all three years base-negative. Funding-inclusive net remains unknown. The five tasks do not rerun R8-7 or authorize new strategy outcome reads.

## Remote process evidence

| Task | PID | Start (Beijing) | Exit (Beijing) | Terminal | Validation |
|---|---:|---|---|---|---|
| R8_8_LOSS_ATTRIBUTION | 73712 | 01:54:20 | 02:01:07 | exit 0 | 3,772 existing-ledger checks; read-only verify passed |
| R8_INDICATORS | 73964 | 01:54:31 | 02:04:17 | exit 0 | 48 synthetic tests; Ruff and compile pass |
| R8_EXIT_ENGINE | 74214 | 01:54:39 | 02:02:18 | exit 0 | 82 tests; Ruff and diff checks pass |
| R8_TREND_DESIGN | 91812 | 06:05:44 | 06:13:43 | exit 0 | 76 synthetic tests; Ruff and compile pass |
| R8_CARRY_DESIGN | 93324 | 06:15:25 | 06:22:47 | exit 0 | 43 synthetic tests; Ruff, compile and reproducibility pass |

Process proof is stored under `/root/workspace/project/crypto-data/lakehouse/r8-argon-parallel-20261022/runs/<TASK>/attempt_1.log` and `exit.code`. `monitor_latest.tsv` records all five as `COMPLETED_EXIT0`; `future_schedule_monitor.log` records the post-06:00 launch and output checks. Each attempt count is 1.

## Launch supervisor and retry evidence

The launch tooling used an exclusive `flock` mutex per task, active-PID and prior-completion checks, and a maximum of three attempts per task. A future supervisor scheduled the two post-06:00 jobs; the all-task monitor checked task-specific output and completion receipts at roughly 60-second intervals. One-shot scheduled checks at approximately 06:25 and 07:10 independently checked later-job startup and completion. The terminal receipts show all five tasks completed on attempt 1, so no retry was needed. A scheduled job was not labeled RUNNING until an actual thread/task command and task-specific output were observed.

## Results and boundary

- **R8-8:** reconciles the existing R8-7 economics only. It selects forced-liquidation inventory-pressure relaxation for a future independent registration; no new outcome or performance claim.
- **R8-A:** causal closed-hour indicator primitives, synthetic-only.
- **R8-B:** E0–E3 exit engine, synthetic-only. E0 has a hard ATR stop and is a new control, not the original R8-7 no-stop rule.
- **R8-C:** synthetic trend candidate, 60 declared cells with one primary comparison; the candidate family requires multiplicity control for any future family-wide inference.
- **R8-D:** synthetic carry/basis-flow features. Real joint feature coverage is unknown; the old 35,250 funding-z count is not transferable to this joint feature.

The task worktrees have not been merged or pushed. No protected 2024–2026 outcomes were read, no new real historical PnL was calculated, and no source was admitted. Before a new historical study, first verify the selected mechanism's data completeness and receiver clocks, freeze a separate registration, align the R8-A/R8-C indicator seed mismatch, and obtain explicit Owner authorization.

See [R8-8 and Argon Research Results](V065_R8_ARGON_RESEARCH_RESULTS_20261022.md) for the diagnosis, caveats, integration blockers and next gates.
