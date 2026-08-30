# Codex 完整任务 Prompt — BTC Quant Agent v0.3.12 Spot–Perpetual Taker Flow Direction Qualification

项目：`EXASHXE/btc-quant-agent`
本地目录：`/root/workspace/project/Quant-agent`
Windows：`\\wsl.localhost\Ubuntu\root\workspace\project\Quant-agent`

起始分支：`codex/v0.3.11-runtime-alignment-forward-data`

本轮版本：`v0.3.12 Spot–Perpetual Taker Flow Direction Qualification`

---

# 0. 本轮定位

v0.3.11 已完成 Research↔Runtime 对齐：正常 Runtime 最高只能输出 `OPPORTUNITY_ONLY`，当前 qualified Direction Engine = `NONE`；Execution = `DISABLED`；Final Holdout = `SEALED`。

本轮重新进入 **新 Alpha Discovery**，但只允许研究一个真正不同的信息家族：

> **BTC Spot aggressive taker flow 与 BTC USD-M Perpetual aggressive taker flow 的相对强弱。**

这是 Market-Flow family，不是重新包装 EMA/RSI/MACD/Structure/Price Momentum。

核心问题：

1. Spot 相对 Perpetual 更强的主动买/卖流，是否对后续 BTC 方向有信息？
2. 该信息是否比 BTC 自己的短期价格 Momentum 提供额外增量？
3. 当已验证的 TP/BR `OPPORTUNITY_ONLY` 出现时，该 Market-Flow Direction 是否能补足“往哪边走”的缺口？

本轮仍然：

- 不生成 actionable Runtime Direction；
- 不生成 Entry / SL / TP / Position Size；
- 不创建 Candidate Freeze；
- 不打开 Final Holdout；
- 不进入 Paper/Testnet/Live；
- 不调整旧 TP/BR、Funding、XAB、Range 参数。

---

# 1. v0.3.11 必须保持的安全不变量

开始前验证：

```bash
quantctl research-registry validate
quantctl research-registry status
quantctl derivatives status
quantctl derivatives audit
quantctl health
```

必须继续满足：

```text
normal runtime max stage = OPPORTUNITY_ONLY
qualified direction count = 0
execution.mode = disabled
final holdout = SEALED
legacy price direction = BLOCKED
TP/BR opportunity = ANALYSIS_ONLY
```

不得因为本轮 Development 结果好就提高 Runtime eligibility。

Forward Derivatives systemd timer 必须继续运行；本轮不得暂停、清空、回填或改写其 SQLite PIT archive。

在任务开始和结束各保存一次 forward collector 状态快照到交付件中。

---

# 2. Git 工作流

先执行：

```bash
cd /root/workspace/project/Quant-agent
git status
git remote -v
git branch --show-current
git log --oneline --decorate -20
gh auth status
```

从包含本 Prompt 的最新 v0.3.11 HEAD 创建：

```bash
git switch -c codex/v0.3.12-spot-perp-taker-flow-qualification
```

如分支已存在则复用，但必须报告真实 start SHA。

不要 merge `main`，不要 force-push。

---

# 3. 开始前质量 Gate

```bash
python -m pip install -e '.[dev,research]'
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src tools tests skill-template/scripts
```

记录：tests、overall coverage、critical-path coverage、Ruff、Mypy、compileall。

不得通过削弱既有测试让基线变绿。

---

# 4. Development / Holdout

严格保持：

```text
Development = [2021-01-01T00:00:00Z, 2026-02-01T00:00:00Z)
Final Holdout = [2026-02-01T00:00:00Z, 2026-08-01T00:00:00Z)
```

Final Holdout 完全禁止访问。

所有 feature、event、matched control、label、future window、artifact timestamp 必须在 Development 内。

任何 future horizon 若跨越 `DEV_END`：标记 incomplete 并排除。

---

# 5. 数据家族：BTCUSDT Spot Market Flow

使用 Binance 官方 Public Data 的 **BTCUSDT Spot 1m Kline archives** 作为新历史 Market-Flow 数据。

只使用 Kline 中因交易产生、当时可实时获得的字段：

```text
open_time
close_time
volume
taker_buy_base_asset_volume
```

不得用未来汇总、排行榜、后验标签或当前 REST 状态回填历史。

## 5.1 Builder

建议新增：

```text
tools/build_spot_market_flow_dataset.py
src/btc_quant_agent/data/binance_spot_archive.py
```

下载/校验 Development 需要的 BTCUSDT Spot 1m monthly archives 及其官方 checksum。

数据写入 `/data/`，不要提交原始大型数据到 Git。

必须生成 manifest，包括：

```text
dataset_id
source URLs / archive identities
per-month checksum
local canonical checksum
coverage start/end
rows
missing minutes
duplicates
invalid volume/taker-volume
normalization rules
```

## 5.2 2025+ 时间戳单位

Binance Spot public archive 在 2025-01-01 后存在 microsecond timestamp 语义变化。

Builder 必须显式检测并统一规范为 **milliseconds**。

不得简单假设所有年份都是 ms。

新增单测覆盖 ms / µs 两种输入，并验证时间轴没有 1000× 偏移。

## 5.3 数据完整性

要求：

```text
volume >= 0
0 <= taker_buy_base_volume <= volume (+ numerical tolerance)
strict monotonic open_time
no duplicates
exact 1m grid or explicit gap
```

Gap 不允许 interpolation / forward fill。

如果某个 decision 所需 60 分钟窗口不完整，该 feature 必须 `DATA_UNAVAILABLE`。

---

# 6. Frozen Feature Identity

本轮只允许一个正式 Direction feature：

```text
SPOT_PERP_TAKER_FLOW_SPREAD_1H
```

每个已完全收盘的 15m decision T，使用紧邻 T 之前 **60 个完整 1m bars**。

Spot：

```text
spot_volume = Σ spot base volume
spot_taker_buy = Σ spot taker buy base volume
spot_imbalance = 2 * spot_taker_buy / spot_volume - 1
```

Perpetual（来自现有 canonical BTCUSDT USD-M 1m）：

```text
perp_volume = Σ perp base volume
perp_taker_buy = Σ perp taker buy base volume
perp_imbalance = 2 * perp_taker_buy / perp_volume - 1
```

若 volume <= 0 或任一窗口不完整：`DATA_UNAVAILABLE`。

正式变量：

```text
flow_spread = spot_imbalance - perp_imbalance
```

冻结 Direction：

```text
flow_spread > 0  -> LONG
flow_spread < 0  -> SHORT
flow_spread == 0 -> NO_BIAS
```

不得加入 magnitude threshold。

不得扫描：

```text
15m / 30m / 2h / 4h lookback
spread threshold
rolling percentile
EMA smoothing
volume weighting variants
quote-volume variant
sign reversal
```

如果这个固定机制失败，就接受失败。

---

# 7. 为什么这不是旧 Price-only family

研究报告必须明确：

- Direction 输入来自 Spot/Perpetual aggressive taker volume relation；
- BTC price 只用于结果 label、ATR normalization 和 matching state；
- 旧 EMA/RSI/ROC/Structure 不参与新 Direction 的生成；
- 不允许用价格结果来选择 flow threshold。

---

# 8. Episode / Serial Dependence

15m decision 每 15 分钟产生，但 1h flow window 强重叠。

正式 inference unit 必须是 **Direction Episode onset**。

定义：

```text
连续 available decisions，flow direction 相同 -> 同 episode
方向变化 / NO_BIAS / DATA_UNAVAILABLE / gap -> break
```

输出：

- raw decisions；
- episode onsets；
- LONG / SHORT；
- length p25/median/p75/max；
- UTC day/week clusters。

Primary statistics 只用 onset。

---

# 9. Outcome Labels

Reference：

```text
first canonical BTCUSDT futures 1m OPEN strictly after decision close
```

Normalization：latest fully closed BTC 1h ATR。

Primary horizons：

```text
4h
8h
```

Secondary：

```text
2h
24h descriptive only
```

LONG：

```text
signed_return_atr = (future_close - reference) / ATR
```

SHORT：

```text
signed_return_atr = (reference - future_close) / ATR
```

同时输出：

- nonnegative MFE / MAE；
- +1 / +1.5 / +2.5 ATR reach；
- Early/Late；
- LONG/SHORT；
- year breakdown。

---

# 10. H32 — Standalone Spot–Perp Flow Direction

Statement：

> `SPOT_PERP_TAKER_FLOW_SPREAD_1H` episode onset contains directional information for subsequent BTCUSDT returns.

Sample gate：

```text
complete 8h episodes >= 1000
LONG >= 300
SHORT >= 300
UTC weeks >= 100
```

统计：

- 4h / 8h signed median；
- UTC-week cluster bootstrap，2000 simulations；
- seed = 42；
- Early / Late；
- LONG / SHORT；
- leave-one-year-out 4h / 8h。

Permutation：在以下 strata 内随机置换 Direction：

```text
year
BTC 1h ATR decile
BTC trailing 1h price return sign
```

必须报告 real-minus-permutation delta。

预注册 support：

```text
4h and 8h signed median > 0
AND 4h and 8h real-minus-permutation delta > 0
AND bootstrap p05 >= -0.05 ATR at both
AND Early/Late median >= -0.05 at both
AND LONG/SHORT median >= -0.05 at both
AND no single leave-one-year-out exclusion flips both primary horizons materially negative
```

Falsify：

```text
both 4h and 8h signed medians <= 0
OR both real-minus-permutation deltas <= 0
```

否则 `INCONCLUSIVE_MECHANISM` / `INCONCLUSIVE_LOW_SAMPLE`。

---

# 11. H33 — Incremental vs BTC Price Momentum

Statement：

> Spot–Perp flow spread adds Direction information beyond BTC's own contemporaneous 1h price momentum.

BTC baseline：

```text
BTC trailing 1h return > 0 -> LONG
< 0 -> SHORT
= 0 -> NO_BIAS
```

在同一个 flow episode onset 上计算：

```text
flow-signed return
btc-momentum-signed return
paired delta = flow - btc_momentum
```

4h/8h primary。

UTC-week clustered paired bootstrap，seed 42，2000 sims。

还输出：

```text
flow vs BTC momentum agreement rate
opposed-event count
aligned vs opposed result
```

Support：

```text
paired median delta > 0 at both 4h/8h
AND bootstrap p05 >= -0.05 at both
AND stratified permutation delta > 0 at both
```

Falsify：both paired deltas <= 0。

另外将 Spot-only taker imbalance sign、Perp-only taker imbalance sign 作为 **diagnostic baselines only**，不得据此事后创建新正式 arm。

---

# 12. H34 — Direction × Frozen Opportunity Layer

Statement：

> Spot–Perp taker-flow Direction provides incremental directional information when the already-supported TP/BR Opportunity Layer fires.

使用 v0.3.11 正常研究定义的 frozen exact-timestamp：

```text
trend_pullback_opportunity
breakout_retest_opportunity
union
```

绝对禁止使用 `legacy_pattern_side` 作为 Direction。

对每个 opportunity timestamp：

- attach latest fully known flow direction as-of opportunity decision close；
- 若 flow feature unavailable/NO_BIAS 则记录无 Direction；
- 只对 available Direction 计算 signed label。

Matched controls：

```text
same year
same flow side
same BTC 1h ATR decile
same BTC trailing 1h momentum sign
not TP/BR opportunity
>=24h separation
K=5 nearest deterministic
```

报告 control reuse distribution。

Primary：4h/8h pooled signed median + matched candidate-control delta。

Bootstrap：UTC-day clusters，2000 sims，seed 42。

Sample gate：

```text
complete 8h opportunities >= 150
LONG >= 30
SHORT >= 30
UTC days >= 60
```

Support：

```text
4h/8h pooled signed median >0
AND 4h/8h matched delta >0
AND signed and matched bootstrap p05 >= -0.05
AND Early/Late >= -0.05
AND LONG/SHORT >= -0.05
```

Falsify：

```text
both pooled medians <=0
OR both matched deltas <=0
```

否则 INCONCLUSIVE。

必须继续单独复现 Opportunity Movement smoke，确认 TP/BR movement capability 没被本轮代码改变。

---

# 13. Anti-mining / Stop Rule

绝对禁止：

- 改 1h flow lookback；
- 加 threshold；
- 反转 Direction；
- 根据结果只选择 Spot 或只选择 Perp；
- 换成 quote-volume 后重跑正式 hypothesis；
- 对 Early/Late 各自选参数；
- 加 RSI/MACD/ADX；
- 重新启用 Funding/XAB；
- 改 TP/BR pattern；
- 打开 Holdout。

Family stop rule：

### 如果 H32 FALSIFIED

```text
STOP_SPOT_PERP_FLOW_FAMILY
```

不再扫窗口/阈值/反转。

### 如果 H32 SUPPORTED 但 H33 FALSIFIED

说明可能只是 BTC momentum 的替代描述：

```text
STOP_AS_NON_INCREMENTAL
```

### 如果 H32/H33 SUPPORTED，H34 FALSIFIED

允许一次独立 follow-up，但不得直接和 TP/BR 组合成 Candidate。

### 如果 H32/H33 SUPPORTED 且 H34 不被 falsified，并达到 stability/sample gate

才允许推荐：

```text
RECOMMEND_DIRECTION_PLUS_OPPORTUNITY_INTEGRATION_RESEARCH
```

仍不等于 Candidate Freeze。

---

# 14. Research Registry

正式结果完成后更新 `configs/research_registry.json` 到 v0.3.12。

新增 component：

```text
spot_perp_taker_flow_direction
role = DIRECTION
feature_family = spot_perp_market_flow
hypothesis_ids = H32/H33/H34
```

状态按结果填写：

- FALSIFIED -> `REJECTED`, `BLOCKED`, stopped family；
- INCONCLUSIVE -> `INCONCLUSIVE`, `BLOCKED`；
- 全面支持 -> 可标 `CANDIDATE` component，但 **runtime_eligibility 仍必须 BLOCKED**，因为这还不是完成 OOS/Forward 的交易策略。

本轮无论结果多好：

```text
active_direction_engine.state = NONE
runtime_maximum_stage = OPPORTUNITY_ONLY
qualified_direction_engine_count = 0
```

不得让 normal `QuantService.scan()` 开始输出 LONG/SHORT。

---

# 15. Forward Derivatives Collector 不得中断

任务开始和结束各执行：

```bash
quantctl derivatives status
quantctl derivatives audit
systemctl --user is-active btc-quant-forward-derivatives.timer
systemctl --user is-enabled btc-quant-forward-derivatives.timer
```

将结果保存到：

```text
deliverables/v0.3.12/FORWARD_COLLECTION_STATUS.json
```

如果期间出现 network gap：诚实记录，不回填。

不要因为本轮研究 Spot Flow 而修改 frozen 30d/2500/95%/max-4-gap derivatives coverage gate。

---

# 16. Preregistration

任何正式研究结果前新增并单独 commit：

```text
configs/research/v0.3.12_spot_perp_flow_protocol.json
```

必须写死：

- dataset identity；
- timestamp normalization；
- feature formula；
- episode rule；
- horizons；
- Early/Late；
- H32/H33/H34；
- sample gates；
- bootstrap/permutation；
- matching；
- verdict rules；
- seed=42；
- prohibitions；
- Holdout forbidden。

记录 protocol SHA-256。

Protocol commit 必须早于 formal research implementation/result commit。

---

# 17. 建议实现文件

```text
src/btc_quant_agent/data/binance_spot_archive.py
src/btc_quant_agent/spot_perp_flow_research.py
tools/build_spot_market_flow_dataset.py
tools/run_spot_perp_flow_qualification.py
configs/research/v0.3.12_spot_perp_flow_protocol.json
tests/test_binance_spot_archive.py
tests/test_spot_perp_flow_research.py
```

研究代码保持 isolated，不污染 normal Runtime Direction path。

---

# 18. Mandatory Tests

至少覆盖：

1. Spot archive ms timestamp normalization；
2. 2025+ µs normalization；
3. taker-buy volume bounds；
4. exact 60 closed 1m window；
5. partial/future 1m 不可用；
6. gap -> DATA_UNAVAILABLE；
7. spot/perp timestamp alignment；
8. imbalance formula；
9. LONG/SHORT sign symmetry；
10. spread==0 -> NO_BIAS；
11. episode onset / side-flip / gap break；
12. label starts strictly after decision close；
13. 4h/8h future label cannot cross Holdout；
14. permutation deterministic；
15. bootstrap deterministic；
16. matched control no future outcome leakage；
17. K<=5 and >=24h；
18. Opportunity union ignores legacy_pattern_side；
19. Registry result remains runtime BLOCKED；
20. normal Runtime stays OPPORTUNITY_ONLY；
21. Execution stays DISABLED；
22. v0.3.11 legacy-research regression remains reproducible。

---

# 19. Formal Artifacts

Canonical run：

```text
artifacts/research/v0.3.12_spot_perp_flow_<UTC_RUN_ID>/
```

至少保存：

```text
protocol.json
protocol.sha256
spot_data_manifest.json
spot_data_audit.json
flow_decisions.parquet
flow_episode_onsets.parquet
flow_labels.parquet
h32_summary.json
h32_bootstrap.json
h32_permutation.json
h33_incremental.json
h33_bootstrap.json
opportunity_flow_events.parquet
opportunity_control_matches.parquet
h34_summary.json
h34_bootstrap.json
by_year_side.json
experiment_summary.json
```

Provenance：

```text
git SHA
protocol SHA
BTC futures dataset SHA
Spot dataset SHA
config hash
seed
Python version
runtime
peak RSS
```

`artifacts/`、raw `/data/`、SQLite 不因交付要求强行提交 Git。

---

# 20. GitHub 交付件 — 必须提交并 push

**从本版本开始，任务完成不允许只在本地生成交付件。**

必须创建并提交到 GitHub：

```text
deliverables/v0.3.12/README.md
deliverables/v0.3.12/V0.3.12_SPOT_PERP_FLOW_QUALIFICATION_REPORT.md
deliverables/v0.3.12/V0.3.12_NUMERIC_ANSWERS.json
deliverables/v0.3.12/V0.3.12_RECOMMENDATION.md
deliverables/v0.3.12/SPOT_DATA_AUDIT.json
deliverables/v0.3.12/RESEARCH_REGISTRY_UPDATE.md
deliverables/v0.3.12/FORWARD_COLLECTION_STATUS.json
```

同时：

```text
docs/V0.3.12_SPOT_PERP_FLOW_QUALIFICATION_REPORT.md
```

必须 commit + push 到：

```text
codex/v0.3.12-spot-perp-taker-flow-qualification
```

在最终回复前执行并记录：

```bash
git status
git log --oneline --decorate -10
git ls-tree -r --name-only HEAD deliverables/v0.3.12
git push -u origin codex/v0.3.12-spot-perp-taker-flow-qualification
```

最终 `git status` 应干净（被 gitignore 的 raw datasets/artifacts 除外）。

**必须确认 GitHub 远端 branch 上确实能看到 `deliverables/v0.3.12/`。**

不要只给用户本地路径。

创建最新 research PR，但不要自动 merge。

---

# 21. Quality / Performance

最终：

```bash
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src tools tests skill-template/scripts
```

目标：

```text
formal run < 30 min
peak RSS < 6 GiB
```

新 v0.3.12 causal/data/matching/verdict 路径必须有直接覆盖；不要用无意义测试刷整体 coverage。

---

# 22. 最终必须数字回答

1. Spot archive coverage / missing / duplicates？
2. 2025+ µs normalization 是否通过 audit？
3. 完整 flow raw decisions 数？
4. episode onset 数、LONG/SHORT 数？
5. episode duration distribution？
6. H32 2h/4h/8h/24h signed medians？
7. H32 4h/8h weekly bootstrap CI？
8. H32 real-minus-permutation delta？
9. Early/Late 与 LONG/SHORT stability？
10. H32 verdict？
11. 与 BTC 1h momentum agreement rate？
12. H33 4h/8h paired delta + CI？
13. Spot-only / Perp-only diagnostic 表现？
14. H33 verdict？
15. TP/BR opportunity union 总数与 flow coverage？
16. H34 pooled 4h/8h return？
17. H34 matched control delta + CI？
18. H34 Early/Late/LONG/SHORT stability？
19. H34 verdict？
20. TP/BR movement smoke 是否仍复现？
21. Research Registry 最终 component 状态？
22. Normal Runtime 是否仍无 actionable Direction？
23. Forward derivatives observations 比任务开始增加多少？
24. scheduler 是否仍 active/enabled？
25. Final Holdout 是否 untouched？
26. tests / coverage / Ruff / Mypy / compileall？
27. runtime / peak RSS？
28. final recommendation？
29. branch / start SHA / prereg SHA / formal-code SHA / delivery SHA / protocol SHA / dataset SHAs？
30. GitHub 上 `deliverables/v0.3.12/` 是否已确认存在？

---

# 23. Allowed Final Recommendations

只能：

```text
RECOMMEND_DIRECTION_PLUS_OPPORTUNITY_INTEGRATION_RESEARCH
RECOMMEND_FLOW_DIRECTION_FOLLOWUP
INCONCLUSIVE_FLOW_FAMILY
STOP_SPOT_PERP_FLOW_FAMILY
STOP_AS_NON_INCREMENTAL
```

无论哪一个：

```text
Strategy = EXPERIMENTAL
Normal Runtime max = OPPORTUNITY_ONLY
Execution = DISABLED
Final Holdout = SEALED
Candidate Freeze = NONE
```

现在开始执行 `v0.3.12 Spot–Perpetual Taker Flow Direction Qualification`，并在任务完成后把完整交付件 commit + push 到 GitHub 仓库。