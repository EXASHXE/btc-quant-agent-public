# R8-8 / Argon — Parallel Research Dispatch, 2026-10-22

Owner instruction: prioritize personal offline strategy research, avoid repeating governance and R8-7, start at most three remote tasks immediately and two after 06:00 Beijing, confirm real process output and retry failures.

## Corrected economic baseline

R8-7 is **COMPLETED** and negative: 545 fixed 8h X-only 2021–2023 events; gross cash PnL -3,081.947168 USDT, baseline ex-funding -11,802.832667, stress ex-funding -20,523.718167, baseline Profit Factor 0.719279, all three baseline years negative. Source: private offline evidence in `/root/workspace/project/crypto-data/lakehouse/r8-7-public-x-economics-20261021/R8_7_DECISION.md`. Do not rerun R8-7. Funding-inclusive net is unknown. R8-8 is the previously planned loss-attribution task; only previously computed R8-7 ledger outcomes are in its scope.

## Five scoped Codex tasks / remote launch evidence

All task clones are isolated detached worktrees at executable SHA `40c70c740f352d1b444decb75276196d17a72dd2` and use focused tests only.

| Task | Scope | Remote launch | Evidence |
|---|---|---|---|
| R8_8_LOSS_ATTRIBUTION | Reconcile and attribute 545 already-computed losses; propose <=2 distinct hypotheses, freeze one. No new outcome scans. | 2026-10-22 01:54 CST, **STARTED**, PID 73712 | thread.started, real R8_8_START command and actual R8-7 ledger lookup |
| R8_INDICATORS | Causal EMA/MACD/KDJ/ATR/ADX/RVOL/VWAP/KER standalone library + synthetic tests. | 01:54 CST, **STARTED**, PID 73964 | thread.started, actual R8_INDICATORS_START and timing-code inspection |
| R8_EXIT_ENGINE | New E0–E3 hard-stop/signal/trailing exit engine + synthetic tests. Does not modify R8-7 no-stop contract. | 01:54 CST, **STARTED**, PID 74214 | thread.started, actual R8_EXIT_START and costs-code inspection |
| R8_TREND_DESIGN | New small trend/regime candidate, synthetic only; integrate above interfaces if ready. | **SCHEDULED** 06:05 CST | Local remote supervisor + 06:25 automation verifies actual process |
| R8_CARRY_DESIGN | New carry/basis + order-flow source-compatible mechanism, synthetic only. | **SCHEDULED** 06:15 CST | Local remote supervisor + 06:25 automation verifies actual process |

**Remote evidence root:** `/root/workspace/project/crypto-data/lakehouse/r8-argon-parallel-20261022/`. `prompts/`, `runs/<TASK>/attempt_N.log`, `runs/<TASK>/pid`, `runs/<TASK>/exit.code`, `worktrees/<TASK>/`, `monitor_latest.tsv`, `future_schedule_monitor.log` and `all_jobs_monitor.log`.

Remote launch script `launch.sh` uses exclusive `flock` launch mutex per task, idempotent active-PID checks, prior-completion checks, and at most 3 launch attempts per task. Remote `future_supervisor.sh` schedules two later jobs and seeks Codex log evidence; `monitor_all.sh` checks all five at ~60-second intervals and retries abnormal exits. Additional one-shot 06:25 and 07:10 scheduled agent checks independently verify and retry if needed, reporting failures honestly. A scheduled future task is not marked RUNNING until its actual thread/task command appears.

## Argon scientific triage

**Use immediately:** timestamp-causal self-contained indicator functions, dimensionless features, seeded deterministic semantics; independent E0–E3 synthetic dynamic exits with mandatory hard stops, worst-case same-minute stop+target ambiguity and delayed hourly signal execution. E0 is a NEW stopped policy, not the old frozen no-stop R8-7. Run paired exit comparisons only under a new independent outcome-study scope, never as retroactive reinterpretation of the failed X baseline.

**Research later:** KER trend-state gate, basic order flow and bar-based liquidity-impact proxies, funding/basis congestion/flow exhaustion. Test whether they improve net economics on matched eligibility after separate historical-outcome authorization, not by claiming causal microstructure knowledge from candle bars.

**Reject unsupported guarantees:** bar-based absolute signed taker-flow imbalance is not classical volume-clock VPIN nor a reliable informed trading probability; bar-based Kyle/Amihud proxies do not directly measure order-book depth or actual fill slippage; ATR exit does not imply easy 4:1 payoff; 240h EMA warmup is a design option, not a universal exact-convergence theorem; reserved P1 Mechanism B slots are not a free post-hoc multiple-testing allowance.

Next decision should come from the actual R8-8 diagnosis and completed synthetic engineering receipts; choose ONE new strategy with predeclared evaluation scope. No new historical return study, no protected 2024–2026 outcome read and no live trading are authorized by these engineering tasks.

## Remote communication

Owner-facing reporting stays Chinese; agent prompts and repository files stay English. Do not re-dispatch currently running tasks. Real status is derived from PID, Codex thread.started, task-specific command output and completion receipt, not from orchestration messages. If the remote device goes offline, disclose inability to verify rather than claiming launch.
