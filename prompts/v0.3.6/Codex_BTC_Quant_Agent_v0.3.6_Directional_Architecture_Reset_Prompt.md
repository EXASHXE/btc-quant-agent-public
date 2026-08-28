# Codex 完整任务 Prompt — BTC Quant Agent v0.3.6 Directional Architecture Reset

项目：`EXASHXE/btc-quant-agent`
本地目录：`/root/workspace/project/Quant-agent`

当前研究分支：`codex/v0.3.5-breakout-edge-qualification`
当前已知 HEAD：`2601388a142be10f2881677c27df23bb69e54c34`
v0.3.5 正式研究代码 SHA：`778dfc7e9bd91b9c1fc2053855fe456538f0c509`

状态必须保持：
- Strategy/feature version `0.2.2 / 0.2.2`
- `validation_status = EXPERIMENTAL`
- execution disabled / auto_execute=false / allow_live=false
- Holdout `[2026-02-01, 2026-08-01)` 完全封存
- no candidate freeze / no paper / no testnet / no live

---

## 1. 已确认研究结论

v0.3.4 Trend Pullback：
- H9 directional edge = `FALSIFIED`
- H10 causal retrace = `INCONCLUSIVE_MECHANISM`
- TP 继续 `TP_RESEARCH_SUSPENDED_AFTER_V0.3.4`

v0.3.5 Breakout Retest：
- BR Pattern/Post-factor/Gross-RR/Risk/Filled = `546 / 185 / 63 / 14 / 13`
- H11 raw BR incremental directional edge = `FALSIFIED`
- H12 frozen factor gates add information = `FALSIFIED`
- H13 RR/risk selection = `INCONCLUSIVE_LOW_SAMPLE`
- Recommendation = `RECOMMEND_STRATEGY_ARCHITECTURE_RESET`

BR Pattern vs matched controls signed-return delta：
- 1h -0.145603 ATR
- 2h -0.258071
- 4h -0.141729
- 8h -0.062329
- 12h +0.284189

Primary 4h/8h 均为负。BR/TP 都表现出更高 MFE/reach，但没有证明更好的方向收盘收益。

核心解释：
> 当前 TP/BR 更像“高波动/机会事件探测器”，而不是可靠的方向预测器。下一步不能继续微调 setup，而要把“方向层”和“机会层”拆开验证。

---

## 2. v0.3.5 验收后需要先修的 research-harness 一致性问题

这些问题不改变 v0.3.5 当前 FALSIFIED 结论，但 v0.3.6 正式研究前必须修正并测试：

1. v0.3.5 Protocol 的 H12 `SUPPORTED` 条件要求：
   - 4h/8h post-factor minus pattern > 0
   - both bootstrap p05 >= -0.05 ATR
   - +1ATR reach delta nonnegative at both
   - positive direction in at least four complete years

   当前实现的 H12 support branch 只检查 signed-return delta 与 p05。必须让代码与 Protocol **逐项完全一致**，并加 unit test。不要修改 v0.3.5 已发布 artifact。

2. H13 当前因 risk-pass n=14 被直接赋 `INCONCLUSIVE_LOW_SAMPLE`，结果正确，但逻辑要改成显式执行 protocol gate（`n < 20 -> INCONCLUSIVE_LOW_SAMPLE`），并测试未来 n>=20 分支，避免 hard-code verdict。

3. BR matched control 中沿用了 `is_tp_pattern` 字段名来排除 BR pattern。新代码使用语义正确名称（如 `is_excluded_pattern` / `is_br_pattern`），旧 artifact 不重写。

以上 correctness/hygiene fix 单独 commit。

---

# 3. 本轮目标：Architecture Reset，不是新策略优化

版本：
`v0.3.6 Directional Architecture Reset`

本轮只回答：

1. 当前价格/结构基础特征中，**到底有没有一个独立的 Direction Engine 能预测 LONG/SHORT 方向？**
2. 4H Macro、1H Trend Regime、Structure、Momentum 各自是否提供 incremental directional information？
3. TP/BR 是否可以保留为 **Opportunity/Volatility Event Layer**，而不再承担方向预测职责？
4. 如果现有 direction primitives 都没有稳定 Edge，是否应该停止继续用同一套 price-only architecture，转向新的 feature/data family？

本轮禁止创建可交易策略，不运行 Final Holdout。

---

## 4. Git

从最新 v0.3.5 HEAD 创建：

```bash
cd /root/workspace/project/Quant-agent
git status
git log --oneline --decorate -20
git switch -c codex/v0.3.6-directional-architecture-reset
```

不 rewrite 历史 formal artifacts。

---

## 5. 开始前验收

```bash
python -m pip install -e '.[dev,research]'
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src skill-template/scripts
```

记录最新 tests、coverage、critical-path coverage、CI。

---

## 6. 预注册 Protocol

任何正式结果前创建并 commit：

`configs/research/v0.3.6_directional_architecture_protocol.json`

必须固定：
- Development `[2021-01-01, 2026-02-01)` only
- Holdout forbidden
- event definitions
- feature definitions
- matching/null construction
- primary horizons
- bootstrap cluster unit
- hypotheses H14-H18
- verdict rules
- seed 36
- no parameter scan
- no PnL-based architecture selection
- no reverse-the-failed-signal trick

Protocol commit 必须早于正式 run。

---

# 7. 关键架构思想：Direction 与 Opportunity 解耦

目标概念架构：

```text
Market data
   ├── Direction Engine  -> LONG / SHORT / NO_BIAS
   ├── Opportunity Layer -> MOVEMENT_EVENT / NONE
   └── Risk/Execution    -> 后续版本再研究
```

本轮只验证前两层的信息含量。

严禁：
- 因为 BR/TP signed return 为负，就简单反向做单
- 重新扫描 BR/TP 参数
- 用 PnL 挑选 feature combination

---

# 8. Direction Engine Primary Event Unit

不要把 29,580 个 15m Trend decision 当 IID 样本。

构建 **1H trend-regime episodes**：
- 基于 closed 1H bars
- 连续相同 `TREND_UP` 或 `TREND_DOWN` 为一个 episode
- episode 开始：状态从非同方向 trend -> TREND_UP/DOWN
- episode 结束：离开该状态
- 所有特征必须只使用 episode anchor 时已经关闭的数据

Primary event：
`episode onset` 对应的第一可交易 closed decision timestamp。

Secondary analysis：
- episode 内每个 closed 1H continuation bar
- 但 bootstrap/CI 必须以 `episode_id` 为 cluster，不能当 IID。

输出：
- episode count
- median duration
- LONG/SHORT episodes
- year distribution

---

# 9. H14 — 1H Trend Regime Directional Information

Statement：
`The frozen 1H TREND_UP/TREND_DOWN regime contains directional information at regime-episode onset.`

Direction：
- TREND_UP -> LONG
- TREND_DOWN -> SHORT

未来 labels（ATR-normalized）：
- signed close return
- MFE
- MAE
- +1/+1.5/+2.5 ATR reach

Horizons：
- 1h
- 2h
- 4h
- 8h
- 12h

Primary：4h / 8h。

Null / control 不要用 BR/TP controls。

至少做两种 null：

### Null A — Direction permutation
在同 year + ATR decile 内，对 episode direction labels 做 deterministic seeded permutation，保持 LONG/SHORT 频率。

### Null B — Matched opposite-direction episodes
尽量匹配：
- same year
- same ATR decile
- opposite regime direction
- >=24h separation

比较真实 regime-direction signed return vs null。

Bootstrap：episode-cluster，2000 sims，seed 36。

H14 support 必须要求：
- 4h/8h real-vs-null signed delta > 0
- lower bound 不明显为负（protocol 固定阈值）
- LONG 与 SHORT 不能只有单边贡献
- leave-one-year-out 不依赖一个年份

---

# 10. H15 — 4H Macro Alignment Incremental Value

仅在 1H trend episode onset 中比较：

```text
4H macro aligned
vs
4H macro not aligned
```

匹配：
- same year
- same direction
- same ATR decile
- episode onset only

Primary：4h/8h signed return delta。

同时 MFE/MAE/reach。

这是增量条件，不改变任何阈值。

---

# 11. H16 — Structure Alignment Incremental Value

定义必须复用 frozen causal structure primitives，不能创建新 swing 参数。

在 1H trend episodes 中比较：
- direction-consistent structure
- non-confirming / inconsistent structure

例如 LONG 只使用当时已确认 HH/HL 相关结构语义；SHORT 镜像。

具体字段与规则在 Protocol 中用现有代码的真实定义写死。

匹配 same year/direction/ATR decile。

Primary 4h/8h signed-return delta。

---

# 12. H17 — Momentum Incremental Value

只使用 frozen momentum primitives：
- RSI alignment
- ROC alignment

不要扫描 RSI/ROC 参数。

分别分析：
- RSI aligned vs non-aligned
- ROC aligned vs non-aligned
- both aligned vs not-both

同 year/direction/ATR decile episode matching。

如果某 reject scope 太少，标 `INCONCLUSIVE_LOW_SAMPLE`，不要强行结论。

---

# 13. Limited Nested Direction Architecture

只允许一个预注册 nested ladder，禁止组合爆炸：

```text
D0 = 1H Trend Regime direction
D1 = D0 + 4H Macro aligned
D2 = D1 + Structure aligned
D3 = D2 + frozen Momentum aligned
```

这不是 strategy arm，不计算交易 PnL。

每层仅输出：
- episode/sample count
- 4h/8h signed-return
- MFE/MAE
- reach rates
- year/direction stability

相邻：D1-D0, D2-D1, D3-D2。

不要创建几十种 feature combinations。

---

# 14. Architecture Selection Rule

不能简单“选开发集最好的一层”。

Protocol 预注册 deterministic hierarchy：

- 如果 D0 不支持 H14：现有 Direction Engine foundation FAIL。
- D0 支持后，只有当 D1 在 4h/8h 不降低 directionality 且稳定，才允许 Macro 进入 proposed architecture。
- D2/D3 同理按顺序增量判断。
- 一旦某层明显恶化，不继续把它加入 proposed direction architecture。

输出：
`PROPOSED_DIRECTION_ARCHITECTURE = D0/D1/D2/D3/NONE`

注意：这只是下一版本研究候选，不是 strategy candidate。

---

# 15. H18 — Opportunity Layer / Movement Detection

正式验证当前发现：TP/BR 是否更像 movement detector。

对：
- BR_PATTERN
- TP_PATTERN

分别与对应 matched trend-regime controls 比较 **无方向性 movement metrics**：

Primary：
- future high-low range / ATR
- max(MFE, MAE)
- `MFE + MAE`
- absolute close return / ATR
- probability movement >= 1.5 ATR
- probability movement >= 2.5 ATR

Horizons：4h / 8h。

这里不评价 LONG/SHORT 对错。

H18 Statement：
`Existing TP/BR patterns detect elevated future movement even though they do not provide reliable direction.`

如果 supported：允许未来把 TP/BR 仅保留为 Opportunity Layer。
如果 falsified：连 event layer 也应该淘汰。

---

# 16. Multiple-Testing / Stability Discipline

本轮有 H14-H18，多 hypothesis 必须避免“看哪个显著就用哪个”。

要求：
- hypotheses pre-registered
- primary horizons fixed 4h/8h
- yearly splits
- LONG/SHORT splits
- leave-one-year-out
- episode-cluster bootstrap
- 不把每个 1h/15m bar当独立样本
- 不以单个 p-value 宣称 alpha

可以报告 confidence intervals，但最终 verdict 按预注册稳定性 Gate。

---

# 17. Development 内部 chronological confirmation

由于 Development 已经被多轮研究使用，不能把任何新切分称为 pristine OOS。

但为了减少进一步过拟合，额外报告：
- Early Development: `[2021-01-01, 2024-01-01)`
- Late Development Confirmation: `[2024-01-01, 2026-02-01)`

规则：
- 不允许基于 Early 调参数
- 只比较同一冻结定义在 Early/Late 的方向一致性
- Late 只能称 `internal chronological confirmation`，不能叫 Holdout/OOS

如果某 primitive 只在 Early 有效、Late 反向：不得进入 proposed architecture。

---

# 18. Final Holdout Firewall

所有：
- episode construction
- future labels
- matched controls
- permutation null
- TP/BR movement labels

必须 `< 2026-02-01T00:00:00Z`。

临近边界的 12h window incomplete -> exclude。

新增测试确保没有任何读到 Holdout。

---

# 19. 不允许做的事情

本轮禁止：
- 修改 EMA periods
- 修改 ADX/ATR/regime threshold
- 修改 swing/pivot parameters
- 修改 RSI/ROC parameters
- 新增技术指标后挑结果
- BR/TP reverse trading
- RR/Stop/Target/TTL scan
- PnL backtest selection
- ML / hyperparameter search
- derivatives backfill fabrication
- orderbook historical fabrication
- Holdout
- candidate freeze

---

# 20. Artifacts

输出：
`artifacts/research/v0.3.6_directional_architecture_<run_id>/`

至少：
- protocol.json
- protocol.sha256
- data_manifest.json
- regime_episodes.parquet
- episode_summary.json
- h14_regime_directionality.json
- h14_null_permutation.json
- h14_matched_opposite.json
- h15_macro_increment.json
- h16_structure_increment.json
- h17_momentum_increment.json
- direction_ladder.json
- early_late_confirmation.json
- br_opportunity_layer.json
- tp_opportunity_layer.json
- opportunity_bootstrap.json
- by_year_direction.json
- experiment_summary.json

Provenance：git/config/data/protocol checksum + seed。

---

# 21. Tests

至少新增：
- `test_v035_h12_verdict_matches_protocol`
- `test_v035_h13_uses_sample_gate_not_hardcode`
- `test_regime_episode_construction_is_causal`
- `test_episode_has_no_future_feature_access`
- `test_episode_cluster_ids_are_stable`
- `test_permutation_null_preserves_year_atr_direction_frequency`
- `test_matched_opposite_is_opposite_direction`
- `test_macro_increment_matching_uses_no_future_labels`
- `test_structure_alignment_uses_confirmed_structure_only`
- `test_momentum_uses_frozen_parameters`
- `test_direction_ladder_is_nested`
- `test_opportunity_metrics_are_direction_agnostic`
- `test_early_late_split_is_fixed`
- `test_all_v036_future_windows_stay_before_holdout`
- `test_bootstrap_deterministic_seed36`
- `test_no_candidate_freeze_or_execution_enable`

---

# 22. Performance

目标：
- runtime < 30 min
- peak RSS < 6 GiB

复用 existing feature/replay caches。
避免重复扫描/O(N²)。

---

# 23. Final Verdicts

H14 — 1H Regime directional information
H15 — 4H Macro incremental value
H16 — Structure incremental value
H17 — Momentum incremental value
H18 — TP/BR opportunity/movement detection

Allowed：
- `SUPPORTED`
- `FALSIFIED`
- `INCONCLUSIVE_LOW_SAMPLE`
- `INCONCLUSIVE_MECHANISM`

Overall：
- `DIRECTIONAL_ARCHITECTURE_RESET_COMPLETE`
- `DIRECTIONAL_ARCHITECTURE_RESET_BLOCKED`

---

# 24. Final Recommendation Gate

只允许：

1. `RECOMMEND_DIRECTION_PLUS_OPPORTUNITY_PROTOTYPE`
   - Direction Engine 至少 D0 supported 且 Late confirmation 同方向
   - Opportunity Layer 至少 BR 或 TP movement detection supported

2. `RECOMMEND_DIRECTION_ONLY_PROTOTYPE`
   - Direction Engine supported
   - TP/BR opportunity layer 不支持

3. `RECOMMEND_NEW_FEATURE_FAMILY_RESEARCH`
   - D0/H14 falsified 或所有 Direction primitives 无稳定方向信息
   - 意味着不要继续在同一 frozen price-only architecture 上微调

4. `INCONCLUSIVE_CONTINUE_ARCHITECTURE_DIAGNOSTIC`

不允许 Candidate Research / Holdout。

---

# 25. 如果需要 New Feature Family

本轮只给研究路线，不实现。

优先候选可包括：
- point-in-time derivatives（OI / basis / taker / long-short），但仅使用真实 forward-collected history，禁止伪回填
- cross-asset / market breadth
- higher-timeframe momentum/state primitives

不得在本轮开始自由挖特征。

---

# 26. Deliverables

生成：
- `docs/V0.3.6_DIRECTIONAL_ARCHITECTURE_RESET_REPORT.md`
- `deliverables/v0.3.6/README.md`
- `deliverables/v0.3.6/V0.3.6_DIRECTIONAL_ARCHITECTURE_RESET_REPORT.md`
- `deliverables/v0.3.6/V0.3.6_NUMERIC_ANSWERS.json`
- `deliverables/v0.3.6/V0.3.6_RECOMMENDATION.md`

---

# 27. 最终必须回答

1. 1H Trend episodes 总数、LONG/SHORT、每年数量？
2. H14 4h/8h real direction vs permutation null delta 与 CI？
3. vs matched opposite-direction episodes 结果？
4. H14 verdict？
5. 4H Macro alignment 的 4h/8h incremental delta？H15？
6. Structure alignment 增量？H16？
7. RSI/ROC/both momentum 增量？H17？
8. D0/D1/D2/D3 各自 sample、4h/8h signed return？
9. `PROPOSED_DIRECTION_ARCHITECTURE` 是哪个或 NONE？
10. Early vs Late confirmation 是否方向一致？
11. BR/TP 4h/8h absolute movement / range 增量？
12. H18 verdict，哪个 setup 可作为 Opportunity Layer？
13. 是否存在 Direction Engine + Opportunity Layer 的可继续路线？
14. 是否需要 New Feature Family？
15. Final recommendation？
16. Holdout 是否仍完全未消费？

---

# 28. Git / PR

```bash
ruff check .
mypy
pytest -q
python -m compileall -q src skill-template/scripts
git status
git push -u origin codex/v0.3.6-directional-architecture-reset
```

创建最新 research PR，不自动 merge/close 旧 PR。

---

# 29. 原则

> 当前失败不是“再调一个参数”能解释的问题，而是 Direction 与 Opportunity 被混在一个 Setup 中。

> 先验证方向信息来自哪里，再谈 Entry/Stop/Target。

> 高 MFE / 高 reach 不等于方向 Edge。

> 29k 个 15m bars 不是 29k 个独立样本；使用 regime episode cluster。

> 如果 1H Regime 本身没有稳定方向信息，应停止在同一 price-only architecture 上继续微调。

> Final Holdout 继续封存。

现在开始执行：
`v0.3.6 Directional Architecture Reset`
