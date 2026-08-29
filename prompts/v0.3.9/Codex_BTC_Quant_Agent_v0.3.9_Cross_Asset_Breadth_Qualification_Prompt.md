# Codex 完整任务 Prompt — BTC Quant Agent v0.3.9 Cross-Asset Breadth Direction Qualification

项目：`EXASHXE/btc-quant-agent`
本地目录：`/root/workspace/project/Quant-agent`

当前研究分支：`codex/v0.3.8-funding-stability-diagnostic`
v0.3.8 已发布结果 HEAD：`3b3f743feff5fb5f53b9a5762bf07d68f23c104c`
v0.3.8 formal code SHA：`25e8a93f8aafaa142edfb45edcfa7c13d8f0f15a`

执行时从 **v0.3.8 分支最新 HEAD（包含本 Prompt commit）** 创建新分支：
`codex/v0.3.9-cross-asset-breadth-qualification`

状态必须保持：
- Strategy/feature version `0.2.2 / 0.2.2`
- `validation_status = EXPERIMENTAL`
- execution disabled / auto_execute=false / allow_live=false
- Final Holdout `[2026-02-01, 2026-08-01)` 完全封存
- no candidate freeze / no paper / no testnet / no live

---

## 1. v0.3.8 已确认事实与 Stop Rule

Funding family 最后一轮 Development diagnostic 已完成：

- 2,765 extreme settlements -> 856 independent same-tail episode onsets
- H22 Funding episode-onset direction = `INCONCLUSIVE_MECHANISM`
- H23 time/state attribution = `INCONCLUSIVE_MECHANISM`
- H24 Funding × TP internal replication = `INCONCLUSIVE_MECHANISM`
- H25 Funding × BR = `FALSIFIED`
- H21 movement layer继续复现：4h/8h future-range delta约 `+0.527/+0.644 ATR`

Funding family stop decision：
`STOP_FUNDING_FAMILY_MOVE_TO_CROSS_ASSET`

因此本轮绝对禁止：
- Funding window/cutoff 扫描
- Funding threshold 改动
- Funding 重新定义 LONG/SHORT
- 根据 v0.3.7/v0.3.8 subgroup 继续挖 Funding

Funding 可以保留为研究历史事实，但本轮不是输入 Alpha。

---

# 2. 外部参考项目带来的边界

参考项目中出现了：网格、Bollinger mean-reversion、ADX/MACD/EMA、ARBR、RSRS、SSA、LSTM/RL、多因子与自动执行等思路。

本轮不要把这些一次性加入策略。

原因：
- v0.3.6 已经反证了当前 price-only Direction family；不能因为换成另一组技术指标就重新大规模挖 Development。
- 网格/均值回归属于独立 RANGE strategy family，应以后单独预注册、独立回测，不能污染 Direction Engine。
- ML/RL 必须建立在已独立验证的 Feature family 和严格 Walk-Forward 上，不应当前直接投入。

本轮只执行一个真正新的信息源家族：
**Cross-Asset Market Breadth**。

---

# 3. 本轮唯一研究目标

版本：
`v0.3.9 Cross-Asset Breadth Direction Qualification`

目标回答：

1. 非 BTC 大型币种的同步上涨/下跌广度，是否对 BTC 后续 4h/8h 收益具有增量方向信息？
2. 这种信息是否只是 BTC 自己刚刚上涨/下跌的重复表达？
3. 如果 Cross-Asset direction 有效，与已验证的 TP/BR Opportunity Layer 结合后是否更强？
4. 如果失败，应停止这一个固定 Breadth definition，而不是扫描币种/窗口/阈值。

本轮是 Feature Qualification，不是交易策略优化。

---

# 4. Git 与开始前验收

```bash
cd /root/workspace/project/Quant-agent
git status
git remote -v
git branch --show-current
git log --oneline --decorate -20
git switch -c codex/v0.3.9-cross-asset-breadth-qualification
```

然后：

```bash
python -m pip install -e '.[dev,research]'
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src skill-template/scripts
```

记录最新实际结果。

---

# 5. 预注册 Protocol 必须先 Commit

任何正式 Cross-Asset 结果运行前，先创建：

`configs/research/v0.3.9_cross_asset_breadth_protocol.json`

然后单独 commit。

Protocol 必须写死：
- Development window
- basket identity
- data source
- missing-data rule
- feature lookback
- breadth rule
- episode construction
- labels/horizons
- BTC-own-momentum redundancy test
- Opportunity interaction
- bootstrap/permutation
- Early/Late split
- sample gates
- H26/H27/H28 verdict rules
- seed
- no parameter search
- Holdout forbidden

建议 seed 固定：`39`
bootstrap/permutation：`2000`

Protocol commit 必须早于 formal implementation/run result commit。

---

# 6. Cross-Asset Basket 完全冻结

固定 basket：

```text
ETHUSDT
BNBUSDT
XRPUSDT
ADAUSDT
LTCUSDT
```

BTCUSDT 不属于 breadth basket。

禁止：
- 看结果后替换币种
- 删除表现差的币种
- 加 SOL/DOGE 等来改善结果
- 权重优化

如果任何固定资产无法获得满足 Development PIT 要求的官方历史数据：
- 先完整记录 coverage
- 不允许静默替换
- 若导致主要时段不足，正式结论 `CROSS_ASSET_QUALIFICATION_BLOCKED`

---

# 7. 数据源与 Data Audit

优先使用 Binance 官方 Public Data：
`data.binance.vision`

为 Cross-Asset feature 使用官方 **1h USD-M Futures Kline** 即可，不需要下载额外 1m 数据。

每个固定币种只读取：
`[2021-01-01, 2026-02-01)`

不要读取 Cross-Asset Final Holdout 内容。

对每个 symbol 输出：
- first/last timestamp
- expected rows
- actual rows
- gaps
- duplicates
- invalid OHLC
- zero volume
- SHA256
- archive checksums

禁止：
- REST API 回填历史缺口后伪装成官方冻结数据
- future interpolation
- backfill/forward-fill跨缺失段制造收益

允许仅在所有 basket 成员都有完整 causal bar 时生成 feature event。

---

# 8. 统一时间语义

Breadth decision grid：每个 fully closed BTC 1h bar close。

对每个 decision `T`：
- 所有 basket 成员只允许使用 `close_time_ms <= T` 的 fully closed 1h bars
- BTC 自身控制变量也只用 `<=T`
- label 从 T 后第一根 canonical BTC 1m 开始

必须有测试证明：
`cross_asset_feature_time <= decision_time`

---

# 9. Frozen Breadth Feature — XAB4H

唯一 primary Cross-Asset feature：
`XAB4H_5ASSET_BREADTH`

对每个 basket asset：

```text
r4h = close(T) / close(T-4 completed 1h bars) - 1
```

只取符号，不按收益幅度加权：

```text
positive_count = count(r4h > 0)
negative_count = count(r4h < 0)
```

方向规则固定：

```text
positive_count >= 4 -> LONG
negative_count >= 4 -> SHORT
otherwise -> NO_BIAS
```

0 return 视为 neutral，不计 positive/negative。

禁止：
- 1h/2h/8h/24h lookback scan
- 3/5、5/5 threshold scan
- 按 market cap/volatility 权重
- 按单个币种历史表现加权

---

# 10. Breadth Episode 去除 Serial Dependence

不要把连续数十小时的相同 breadth state 当成独立样本。

定义：
`maximal consecutive fully-closed 1h decisions with same extreme XAB4H direction`

Episode 在以下情况结束：
- NO_BIAS
- opposite extreme
- data unavailable

Primary event unit：
`episode onset only`

记录：
- direction
- episode length hours
- year
- Early/Late
- BTC 1h ATR
- BTC 1h Regime
- BTC trailing 4h return
- basket individual r4h values

member events只允许做 serial-persistence descriptive diagnostic，不用于 primary verdict。

---

# 11. BTC Label

Primary horizons：
- 4h
- 8h

Secondary descriptive：
- 24h

Reference：episode onset decision close之后第一根 canonical BTC 1m open。

LONG：
`(future_close-reference)/BTC_1h_ATR`

SHORT：
`(reference-future_close)/BTC_1h_ATR`

同时输出：
- signed close return / ATR
- MFE
- MAE
- +1ATR reach
- +1.5ATR reach
- +2.5ATR reach

所有 future window 不得跨 `2026-02-01T00:00:00Z`。

---

# 12. H26 — Cross-Asset Breadth Standalone Direction

Statement：

`Extreme cross-asset breadth episode onset contains directional information for subsequent BTCUSDT returns.`

Primary：episode onsets。

必须输出：
- sample counts
- LONG/SHORT
- week clusters
- 4h/8h signed median
- Early/Late
- LONG/SHORT subgroup
- by-year
- MFE/MAE/reach

Uncertainty：UTC calendar-week cluster bootstrap，2000 sims，seed39。

Null permutation 必须至少 stratify：
- same year
- BTC 1h ATR decile
- BTC trailing 4h return sign bucket (`NEGATIVE/ZERO/POSITIVE`)

在 strata 内 permute Cross-Asset LONG/SHORT，preserve counts。

输出 real-minus-permutation delta。

预注册 sample gate 建议：
- complete 8h episode onsets >=250
- LONG >=75
- SHORT >=75
- week clusters >=80

SUPPORTED 建议要求：
- 4h和8h signed median >0
- 两个 horizon real-minus-permutation >0
- weekly bootstrap p05 >= -0.05 ATR 两个 horizon
- Early/Late 两个 horizon均 >0
- LONG/SHORT 两个 horizon均 >= -0.05

FALSIFIED：
- 4h/8h signed median 都 <=0，或
- 两个 permutation delta 都 <=0

否则：`INCONCLUSIVE_MECHANISM`

---

# 13. H27 — 是否只是 BTC 自己 Momentum 的重复？

这是本轮非常关键的 incremental-information test。

定义 BTC own momentum baseline：

```text
BTC_MOM4H direction:
BTC trailing 4h return >0 -> LONG
<0 -> SHORT
=0 -> NO_BIAS
```

不要优化 BTC momentum window。

在相同 XAB episode onset events 上同时计算：

1. XAB4H direction signed future return
2. BTC_MOM4H direction signed future return

输出：
- agreement rate
- disagreement rate
- XAB signed median
- BTC_MOM signed median
- paired delta: `XAB - BTC_MOM`
- paired cluster bootstrap CI

再做 conditional analysis：
- XAB aligned with BTC_MOM
- XAB opposed to BTC_MOM

仅诊断，不把 subgroup变成新策略。

H27 statement：
`Cross-asset breadth contains incremental directional information beyond BTC's own contemporaneous 4h momentum.`

SUPPORTED：
- XAB-BTC_MOM paired delta >0 at both 4h/8h
- cluster bootstrap p05 >= -0.05 at both
- real-minus-stratified-permutation >0 at both

FALSIFIED：
- paired delta <=0 at both primary horizons

否则：`INCONCLUSIVE_MECHANISM`

---

# 14. H28 — Cross-Asset Direction × Frozen Opportunity Layer

Opportunity 继续使用 frozen：
- TP_PATTERN
- BR_PATTERN
- exact-timestamp union

原 pattern direction 必须丢弃。

对每个 Opportunity event，as-of 使用最近一个 fully closed XAB4H state；只接受极端 LONG/SHORT。

Primary pooled union。
TP-only / BR-only / BR+TP 是预注册 secondary breakdown，但不得替代 pooled verdict。

Matched controls：
- non-pattern BTC decisions
- same year
- same BTC ATR decile
- same XAB side
- same BTC trailing4h return sign bucket
- >=24h separation
- K=5 deterministic nearest
- reuse diagnostics

Primary outputs：
- pooled signed return 4h/8h
- candidate-control delta
- MFE/MAE
- +1ATR reach
- day-cluster bootstrap
- Early/Late
- LONG/SHORT

Sample gate建议：
- complete8h >=150
- LONG>=30
- SHORT>=30
- day clusters>=60

SUPPORTED：
- pooled signed medians >0 both horizons
- matched deltas >0 both
- signed bootstrap p05 >=-0.05 both
- delta bootstrap p05 >=-0.05 both
- Early/Late positive both horizons
- LONG/SHORT >=-0.05 both

FALSIFIED：
- pooled signed medians both <=0，或
- matched deltas both <=0

否则：`INCONCLUSIVE_MECHANISM`

---

# 15. Breadth Composition Audit

必须回答 breadth 是否被单一币种支配，但不得据此删币。

对每个 basket member 输出：
- sign agreement with final breadth
- leave-one-asset-out breadth direction agreement rate
- event count changes under leave-one-out（diagnostic only）
- asset pair sign-correlation matrix

禁止根据 leave-one-out 结果选择更优 basket。

结论只允许：
- diversified breadth representation
- highly redundant breadth representation
- one-asset-sensitive representation

不创建新的 strategy arm。

---

# 16. Opportunity / RANGE Strategy Backlog 与本轮隔离

参考项目中的：
- bounded grid
- Bollinger mean reversion
- RSRS
- ADX/MACD/EMA
- SSA
- LSTM/RL

本轮全部不得成为正式实验 arm。

仅在报告附录建立 `REFERENCE_STRATEGY_BACKLOG.md`：

分类：
1. `RANGE_EXECUTION_FAMILY`：bounded grid / Bollinger mean reversion
2. `PRICE_TRANSFORM_DIAGNOSTICS`：RSRS / SSA / ARBR
3. `FUTURE_MODELING_ONLY`：ML/LSTM/RL
4. `OPERABILITY`：strategy registry / simulated-vs-real execution / observability

每项说明：
- 为什么可能有用
- 为什么当前不能混入 v0.3.9
- 未来需要什么 prerequisite

不要写代码实现这些策略。

---

# 17. 不得复制参考项目的研究缺陷

明确禁止：
- 以最终收益最大化扫描参数
- 大量 grid search 后只报告最好结果
- 同一数据上训练/筛选/宣称 OOS
- 把 submitted order 当成 filled order
- 无 inventory cap 的加仓网格
- martingale/doubling
- 仅凭 Sharpe 或最终净值宣布 Alpha

我们的 causal/event-driven/Protocol/Holdout 规则优先级高于参考仓库实现。

---

# 18. Holdout Firewall

Final Holdout：
`[2026-02-01, 2026-08-01)`

必须保持：
- BTC price labels不跨 Holdout
- cross-asset source不读取 Holdout effect sizes
- no candidate freeze
- no Holdout certificate consumption

新增测试验证所有正式 artifact timestamp < DEV_END。

---

# 19. Artifacts

输出：

`artifacts/research/v0.3.9_cross_asset_breadth_<run_id>/`

至少：
- protocol.json
- protocol.sha256
- basket_manifest.json
- per_symbol_data_audit.json
- breadth_hourly_features.parquet
- breadth_episode_onsets.parquet
- breadth_episode_summary.json
- h26_directionality.json
- h26_bootstrap.json
- h26_permutation.json
- h27_btc_momentum_incremental.json
- h27_bootstrap.json
- opportunity_xab_events.parquet
- opportunity_matched_controls.parquet
- h28_opportunity_directionality.json
- h28_bootstrap.json
- breadth_composition_audit.json
- by_year_direction.json
- experiment_summary.json

Provenance必须包含：
- git SHA
- BTC config hash
- BTC dataset checksum
- all cross-asset checksums
- protocol checksum
- seed

---

# 20. Tests

至少新增：

- `test_cross_asset_basket_identity_is_frozen`
- `test_cross_asset_uses_only_closed_hourly_bars`
- `test_cross_asset_feature_never_reads_future_bar`
- `test_cross_asset_missing_member_invalidates_feature`
- `test_xab4h_rule_exactly_four_of_five`
- `test_xab4h_no_bias_for_three_of_five`
- `test_breadth_episode_breaks_on_no_bias`
- `test_breadth_episode_breaks_on_opposite_side`
- `test_primary_unit_is_episode_onset`
- `test_btc_label_starts_strictly_after_decision`
- `test_xab_permutation_stratifies_btc_momentum_sign`
- `test_btc_mom4h_baseline_is_frozen`
- `test_xab_vs_btc_momentum_pairing_is_deterministic`
- `test_opportunity_original_direction_is_not_used`
- `test_opportunity_controls_match_xab_and_btc_momentum_bucket`
- `test_leave_one_out_is_diagnostic_only`
- `test_no_v039_artifact_crosses_holdout`
- `test_v039_execution_remains_disabled`
- `test_bootstrap_seed_39_is_honored`

---

# 21. Performance

由于 Cross-Asset 仅需要 1h 数据：

目标：
- formal runtime <30min
- RSS <6GiB

不要把 5 个币全部扩成 1m 常驻内存。

---

# 22. Verdicts

H26：Cross-Asset standalone direction

H27：Incremental vs BTC own 4h momentum

H28：Cross-Asset direction × Opportunity union

Allowed：
- `SUPPORTED`
- `FALSIFIED`
- `INCONCLUSIVE_LOW_SAMPLE`
- `INCONCLUSIVE_MECHANISM`

Overall：
- `CROSS_ASSET_QUALIFICATION_COMPLETE`
- `CROSS_ASSET_QUALIFICATION_BLOCKED`

---

# 23. Recommendation Gate

本轮仍然禁止 candidate freeze。

只允许：

### A
`RECOMMEND_CROSS_ASSET_DIRECTION_PLUS_OPPORTUNITY_PROTOTYPE`

要求：
- H26 SUPPORTED
- H27 SUPPORTED
- H28 SUPPORTED 或至少不是 falsified 且机制一致

### B
`RECOMMEND_CROSS_ASSET_DIRECTION_FOLLOWUP`

H26 supported、H27未falsified，但 H28样本/机制不确定。

### C
`RECOMMEND_OPPORTUNITY_CONDITIONED_CROSS_ASSET_FOLLOWUP`

H26 inconclusive，但 H28 preregistered pooled interaction supported，并且 H27不falsified。

### D
`STOP_CROSS_ASSET_BREADTH_MOVE_TO_NEW_DATA_FAMILY`

H26 FALSIFIED 或 H27 FALSIFIED。

下一新数据家族优先候选：
- forward-collected OI / basis / taker ratio / long-short ratio（只有足够真实 PIT 历史后）
- independently sourced on-chain / market-flow family

禁止在同一 Development 上继续扫 Breadth basket/window/threshold。

---

# 24. Deliverables

生成：

- `docs/V0.3.9_CROSS_ASSET_BREADTH_QUALIFICATION_REPORT.md`
- `deliverables/v0.3.9/README.md`
- `deliverables/v0.3.9/V0.3.9_CROSS_ASSET_BREADTH_QUALIFICATION_REPORT.md`
- `deliverables/v0.3.9/V0.3.9_NUMERIC_ANSWERS.json`
- `deliverables/v0.3.9/V0.3.9_RECOMMENDATION.md`
- `deliverables/v0.3.9/REFERENCE_STRATEGY_BACKLOG.md`

---

# 25. 最终必须数字回答

1. 五个 fixed basket symbols 的 coverage / gaps 是否全部通过？
2. XAB4H extreme hourly decisions 数量？
3. 去 serial dependence 后 episode onsets 数量、LONG/SHORT 数量？
4. Episode length p25/median/p75/max？
5. H26 4h/8h signed medians？
6. H26 weekly-bootstrap p05/p50/p95？
7. H26 real-minus-permutation delta？
8. Early/Late 和 LONG/SHORT 是否稳定？
9. H26 verdict？
10. XAB direction 与 BTC_MOM4H agreement/disagreement rate？
11. XAB-BTC_MOM paired delta 4h/8h？
12. paired bootstrap CI？
13. H27 verdict？
14. Opportunity union 中有多少事件获得 extreme XAB direction？coverage？
15. H28 pooled 4h/8h signed return？
16. H28 candidate-control delta 与 bootstrap CI？
17. TP-only / BR-only / BR+TP secondary结果？
18. H28 verdict？
19. Basket 是否被某一个 asset 支配？
20. Final Holdout 是否保持未访问？
21. 是否值得进入 Direction+Opportunity prototype？
22. 如果失败，下一 family 是什么？

---

# 26. Git Final

```bash
ruff check .
mypy
pytest -q
python -m compileall -q src skill-template/scripts
git status
git push -u origin codex/v0.3.9-cross-asset-breadth-qualification
```

创建最新 research PR，不 merge。

---

# 27. 核心原则

> Cross-Asset 的价值必须来自 BTC 之外的增量信息，而不是 BTC 自己近期涨跌的重复编码。

> Breadth basket、lookback、4/5 threshold 在看到结果之前冻结。

> 连续相同 state 必须按 Episode 处理，不能把 serially-correlated hourly bars 当独立样本。

> Qbot / 网格项目提供的是策略思想和工程参考，不提供可以直接继承的 Alpha 证据。

> 不因一个漂亮 subgroup 改写 primary hypothesis。

> Final Holdout 继续封存。

现在开始执行：
`v0.3.9 Cross-Asset Breadth Direction Qualification`
