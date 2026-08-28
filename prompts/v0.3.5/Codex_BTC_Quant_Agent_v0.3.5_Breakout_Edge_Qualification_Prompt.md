# Codex 完整任务 Prompt — BTC Quant Agent v0.3.5 Breakout Retest Edge Qualification

项目：`EXASHXE/btc-quant-agent`
本地目录：`/root/workspace/project/Quant-agent`
Windows：`\\wsl.localhost\Ubuntu\root\workspace\project\Quant-agent`

当前研究分支：`codex/v0.3.4-causal-entry-directionality`
当前最新已知 HEAD：`1035b0beaff1db0afcf675c1f624743d6a89d6ad`
v0.3.4 正式研究代码 SHA：`27f8fc6d2ae833f73a60f13fed84b2124f57b4dc`

当前策略 / 特征版本：`0.2.2 / 0.2.2`

必须保持：
- `validation_status = EXPERIMENTAL`
- `execution.mode = disabled`
- `auto_execute = false`
- `allow_live = false`
- Holdout `[2026-02-01, 2026-08-01)` 完全封存
- 不创建 candidate freeze certificate
- 不消费 Holdout

## 1. v0.3.4 已确认结论

Development：`[2021-01-01, 2026-02-01) UTC`

Trend Pullback：
- 139 post-factor candidates
- historical pullback-extreme static RR-pass = 18/139
- causal post-confirmation retrace limit = 18
- 45m TTL 内真实 causal fill = 2/18
- 两笔均止损
- Expectancy = -0.824651R
- PF = 0
- MDD = 1.649302R
- Win Rate = 0%

Matched-control signed-return delta：
- 1h = -0.062181 ATR
- 2h = -0.537718 ATR
- 4h = -0.409837 ATR
- 8h = -0.109350 ATR
- 12h = -0.037973 ATR

4h bootstrap CI：
`[-0.773594, -0.375107, +0.152714]`

8h：
`[-0.841779, -0.195129, +0.448059]`

Verdict：
- H9 directional edge = `FALSIFIED`
- H10 causal retrace entry = `INCONCLUSIVE_MECHANISM`
- Candidate gate = `NO_CANDIDATE`

解释：
TP 的 favorable excursion 较大，但 signed close return 相比 matched controls 更差。H9 是按预注册规则 FALSIFIED；CI 仍包含正值，因此不要夸大成“TP 已证明负 Alpha”，只能说没有证据支持其为可交易的正向 directional signal。

不要再通过 TTL、limit、stop、target、RR 的放宽来救 TP。

## 2. 本轮为什么转向 Breakout Retest

Frozen baseline 的 13 笔历史成交全部来自 `BREAKOUT_RETEST`。

已知参考：
- BR pattern candidates ≈ 546
- BR post-factor = 185
- Gross RR >= 1.8 = 63
- after fee >= 1.8 = 44
- after fee + slippage >= 1.8 = 32
- frozen risk-pass = 14
- historical filled/resolved baseline = 13

v0.3.3 BR geometry：
- BR post-factor stop median ≈ 0.999 ATR
- target median ≈ 1.273 ATR
- gross RR median ≈ 1.371
- BR risk-pass stop median ≈ 0.869 ATR
- target median ≈ 3.044 ATR
- gross RR median ≈ 3.343

但 13-trade frozen baseline：
- Expectancy = -0.1035R
- PF = 0.8627

所以继续优化 BR 前，先回答：
**BR 本身是否有可重复的方向预测增量？哪些 Gate 在增加或破坏这个增量？**

## 3. 本轮唯一目标

版本：
`v0.3.5 Breakout Retest Edge Qualification`

纯 Development-only qualification，不做正式参数优化。

问题：
1. BR Pattern vs 同类 trend-regime controls 有没有 incremental directional information？
2. Frozen Macro/Momentum/Participation/Factor gates 是否改善 BR 方向质量？
3. RR/Risk gate 是否真的选择了更高质量 BR，还是只选了高几何 RR 尾部？
4. 14 risk-pass 为什么只有 13 baseline fills？
5. BR 值不值得进入下一轮最小机制修改 / Candidate Research？

## 4. Git

```bash
cd /root/workspace/project/Quant-agent
git status
git remote -v
git branch --show-current
git log --oneline --decorate -20
git tag --list
```

创建：
```bash
git switch -c codex/v0.3.5-breakout-edge-qualification
```

不得重写旧 formal artifacts。

## 5. GitHub PR Hygiene

当前 PR #1/#2/#3 存在 lineage 重叠。

本轮：
- 不自动 merge
- 报告 main HEAD / 最新 research branch / PR 状态
- 说明哪些 PR 已被更新版本 supersede
- 不擅自关闭旧 PR
- 创建 v0.3.5 最新 PR，不 merge

## 6. 开始前验收

```bash
python -m pip install -e '.[dev,research]'
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src skill-template/scripts
```

记录最新实际 tests/coverage/Ruff/Mypy/compileall/CI。

## 7. 预注册 Protocol

任何正式结果前创建并 commit：

`configs/research/v0.3.5_breakout_edge_protocol.json`

写死：
- Development range
- Holdout forbidden
- scope definitions
- funnel stages
- matched-control K / matching
- horizons
- metrics
- bootstrap
- hypotheses / verdict rules
- random seed
- no parameter search
- no PnL-based stage selection

生成 SHA-256。

## 8. Frozen BR Scope 精确复现

至少复现：

- `BR_PATTERN`
- `BR_POST_FACTOR`
- `BR_GROSS_RR_PASS`
- `BR_AFTER_FEE_PASS`
- `BR_AFTER_SLIPPAGE_PASS`
- `BR_RISK_PASS`
- `BR_HISTORICAL_FILLED`

参考：
- pattern ≈ 546
- post-factor = 185
- gross RR pass = 63
- after fee = 44
- after slippage = 32
- risk pass = 14
- filled = 13

不能为了匹配参考数而硬改逻辑。

如果不能解释地不一致：
`BREAKOUT_EDGE_QUALIFICATION_BLOCKED`

## 9. BR Funnel Stage Trace

至少：
1. BR_PATTERN
2. MACRO_ALIGNED
3. RSI_GATE
4. PARTICIPATION_AVAILABLE/PASS
5. FACTOR_SCORE_PASS
6. POSITIVE_GROUP_PASS
7. GROSS_RR_PASS
8. FEE_PASS
9. SLIPPAGE_PASS
10. FUNDING_PASS
11. RISK_PASS
12. FILLED
13. RESOLVED

按真实 frozen 代码映射，Instrumentation 不改变决策。

## 10. Matched Trend Controls — H11

每个 BR_PATTERN 固定匹配 `K=5` controls。

必须：
- same year
- same direction
- same 1H trend regime
- same 15m ATR percentile decile
- control 不是任何 BR pattern candidate
- candidate/control 至少相隔 96 个 15m bars
- deterministic nearest-time matching
- Development only

额外报告：
- unique controls
- total matched rows
- control reuse distribution
- max reuse count
- effective unique-control ratio

检查 pseudo-replication。

## 11. Directionality Labels

Reference：decision close。

Horizons：
1h / 2h / 4h / 8h / 12h

LONG：
`(future_close-reference)/ATR`

SHORT：
`(reference-future_close)/ATR`

同时：
- nonnegative MFE
- nonnegative MAE
- MFE/MAE
- +1 ATR reach
- +1.5 ATR
- +2.5 ATR

Primary horizons：
4h / 8h

## 12. H11 — BR Pattern Incremental Edge

Statement：
`Breakout Retest pattern candidates contain incremental directional information beyond same trend regime and volatility bucket.`

输出每 horizon：
- candidate signed return
- controls
- delta
- MFE delta
- MAE delta
- reach delta

Cluster-aware bootstrap：
- candidate cluster + its 5 controls
- 2000 sims
- fixed seed
- p05/p50/p95

Leave-one-year-out：
4h / 8h

Support/falsification 必须 protocol 预注册。

建议：
- 4h、8h signed-return delta >0
- both p05 >= -0.05 ATR
- +1ATR reach delta >0
- LOO 不依赖单一年

若 4h/8h 都 <=0：
FALSIFIED。

## 13. Gate-Ladder — H12

对 frozen BR chain 分层，例如：

- S1 BR_PATTERN
- S2 POST_MACRO/MOMENTUM
- S3 BR_POST_FACTOR
- S4 GROSS_RR_PASS
- S5 FROZEN_RISK_PASS

实际按真实 funnel 映射。

每层计算：
- 4h/8h signed return
- MFE
- MAE
- +1/+2.5ATR reach
- count

输出相邻增量：
- S2-S1
- S3-S2
- S4-S3
- S5-S4

说明这是 observational selection attribution，不冒充因果。

## 14. Gate Near-Miss Matching

至少分析：
- Momentum pass vs reject
- Participation pass vs reject
- Factor Score pass vs immediate reject
- Gross RR pass vs gross RR near-miss

匹配：
- same year
- same direction
- same BR setup
- same ATR decile
- time separation
- 不使用 future labels 匹配

输出：
- pass/reject counts
- matched coverage
- 4h/8h signed-return delta
- MFE/MAE delta
- bootstrap CI

小样本就 INCONCLUSIVE。

## 15. H12 — Factor Gates Add Information

Statement：
`Frozen non-risk factor gates improve BR directional quality beyond raw BR pattern.`

Primary：
BR_POST_FACTOR vs BR_PATTERN，并参考 near-miss matching。

SUPPORTED 不能只靠减少样本或 PnL；要看 directionality 增量和年份稳定性。

## 16. H13 — RR/Risk Gate Selection Value

比较：
- BR_POST_FACTOR 185
- GROSS_RR_PASS 63
- FINAL_RISK_PASS 14

Primary：
- signed return 4h/8h
- MFE/MAE
- frozen target reach-before-stop
- stop-first
- resolved R（仅 risk-pass/fills）

区分：
- directional selection
- payoff geometry selection

输出：
- gross RR vs future signed-return correlation
- net RR vs signed-return
- RR vs MFE/MAE

只诊断，不扫 RR threshold。

## 17. 14 Risk-Pass -> 13 Filled

逐笔输出 14 个：
- timestamp
- direction
- entry range
- stop
- target
- planned RR
- filled?
- lifecycle
- expiry/invalidation/end censor
- outcome

明确第14个为什么没成为 13-trade baseline。

不得猜。

## 18. 13 Trades Deep Audit

逐笔：
- year
- direction
- signal
- entry
- stop
- target
- planned gross/net RR
- fill latency
- hold time
- exit
- gross R
- fee R
- slippage R
- funding R
- net R
- post-fill MFE/MAE

分 winners / losers 比较。

## 19. Loss Path Attribution

预注册分类，例如：
- immediate failure
- favorable excursion then reversal
- never gained >=0.5R
- reached >=1R MFE then stopped
- timeout

输出 counts / avg planned RR / MFE / MAE。

## 20. 禁止参数优化

不得：
- 改 breakout distance
- retest tolerance
- pivot lookback
- EMA
- RSI
- factor threshold
- positive groups
- RR
- stop buffer
- target fallback
- holding
- TTL
- 新指标
- ML
- derivatives alpha
- orderbook

## 21. Trend Pullback 状态

报告标记：
`TP_RESEARCH_SUSPENDED_AFTER_V0.3.4`

含义：
- 不删代码
- 不改 runtime
- 本轮不再研究 TP 参数
- 只有新的独立机制假设才重开

## 22. Holdout

所有数据严格：
`[2021-01-01, 2026-02-01)`

future label 不可越界。

测试：
- all artifacts < DEV_END
- horizon no Holdout
- no freeze certificate
- holdout unconsumed

## 23. Statistical Discipline

546 pattern candidates 仍是时间相关样本。

要求：
- cluster-aware bootstrap
- year stability
- direction stability
- control reuse diagnostics
- 不作 IID 夸大
- 4h/8h 矛盾时不得挑好看的 horizon

## 24. Artifacts

`artifacts/research/v0.3.5_breakout_edge_<run_id>/`

至少：
- protocol.json
- protocol.sha256
- data_manifest.json
- br_funnel_events.parquet
- br_stage_counts.json
- br_pattern_matched_controls.parquet
- br_directionality_by_horizon.json
- br_directionality_bootstrap.json
- gate_ladder.json
- gate_near_miss_matches.parquet
- gate_near_miss_summary.json
- rr_directionality_relationship.json
- risk_pass_14_lifecycle.parquet
- baseline_13_trade_audit.parquet
- loss_path_attribution.json
- by_year_direction.json
- experiment_summary.json

保存 git/config/data/protocol hashes + seed。

## 25. Tests

至少：
- test_br_scope_reproduces_frozen_counts
- test_br_funnel_instrumentation_does_not_change_decisions
- test_br_matched_controls_exclude_br_patterns
- test_br_controls_match_year_direction_regime_atr
- test_control_reuse_is_reported
- test_br_directionality_is_symmetric_long_short
- test_br_future_windows_never_cross_holdout
- test_gate_ladder_is_nested
- test_near_miss_matching_uses_no_future_labels
- test_rr_correlation_does_not_change_threshold
- test_risk_pass_14_lifecycle_is_complete
- test_baseline_13_trade_audit_matches_frozen_outcomes
- test_bootstrap_is_deterministic
- test_all_v035_artifacts_development_only
- test_holdout_remains_unconsumed

## 26. Performance

目标：
- <30 min
- <6 GiB RSS

避免 O(N²)。

## 27. Hypotheses

H11：
BR Pattern incremental directional edge.

H12：
Frozen factor gates improve BR directional quality.

H13：
RR/Risk gate has useful selection value beyond merely enlarging payoff geometry.

Verdict：
- SUPPORTED
- FALSIFIED
- INCONCLUSIVE_LOW_SAMPLE
- INCONCLUSIVE_MECHANISM

## 28. Final Strategy Decision

本轮不 freeze candidate。

Recommendation 只能：
1. RECOMMEND_BR_FOR_MINIMAL_MECHANISM_RESEARCH
2. RECOMMEND_BR_FOR_CANDIDATE_RESEARCH
3. RECOMMEND_STRATEGY_ARCHITECTURE_RESET
4. INCONCLUSIVE_CONTINUE_DIAGNOSTIC

建议判定：

A. H11 FALSIFIED
-> RECOMMEND_STRATEGY_ARCHITECTURE_RESET

B. H11 SUPPORTED、H12 FALSIFIED
-> 下一轮 factor simplification

C. H11/H12 SUPPORTED、H13 unclear
-> 下一轮 BR geometry/risk mechanism

D. H11/H12/H13 都支持且年份稳定
-> 才可推荐 Candidate Research

即便推荐，也不打开 Holdout。

## 29. Deliverables

生成：
- docs/V0.3.5_BREAKOUT_EDGE_QUALIFICATION_REPORT.md
- deliverables/v0.3.5/README.md
- deliverables/v0.3.5/V0.3.5_BREAKOUT_EDGE_QUALIFICATION_REPORT.md
- deliverables/v0.3.5/V0.3.5_NUMERIC_ANSWERS.json
- deliverables/v0.3.5/V0.3.5_RECOMMENDATION.md

## 30. 最终必须数字回答

1. BR Pattern/Post-factor/Gross-RR/Risk/Filled 准确 counts？
2. BR Pattern vs controls 1/2/4/8/12h signed-return delta？
3. 4h/8h bootstrap CI？
4. +1ATR/+2.5ATR reach delta？
5. H11 verdict？
6. Macro/Momentum/Participation/Factor gates 分别删多少？
7. 每 gate 4h/8h directionality 增量？
8. H12 verdict？
9. Gross-RR pass 63 vs Post-factor 185：方向更好还是只是 geometry 更好？
10. Risk-pass 14 vs gross-pass 63 的方向质量？
11. planned RR 与 future signed return correlation？
12. 第14个 risk-pass 为什么没进13-trade baseline？
13. 13 trades 的主要 loss path？
14. 是否存在“大 MFE 后反转止损”系统性现象？
15. H13 verdict？
16. TP 是否保持 research suspended？
17. 下一步 Factor simplification / BR geometry / Candidate Research / Architecture Reset 哪一个？

## 31. Git Final

```bash
ruff check .
mypy
pytest -q
python -m compileall -q src skill-template/scripts
git status
git push -u origin codex/v0.3.5-breakout-edge-qualification
```

创建最新 research PR，不自动 merge。

## 32. 原则

> TP 已经用了足够 Development evidence，不继续通过参数放宽去救。

> BR 是唯一实际产生 frozen trades 的 setup，但“产生交易”不等于“有 Edge”。

> 先证明 Pattern 和 Gate 有信息增量，再谈增加交易数。

> RR 高只代表 payoff geometry 好，不自动代表方向预测更准。

> Development-only 好结果也不能提前打开 Holdout。

> 如果 BR 也无法通过 matched-control qualification，应接受 Strategy Architecture Reset，而不是继续深挖开发集。

现在开始执行：
`v0.3.5 Breakout Retest Edge Qualification`
