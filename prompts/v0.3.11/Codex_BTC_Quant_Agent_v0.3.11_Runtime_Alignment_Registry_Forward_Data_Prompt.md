# Codex 完整任务 Prompt — BTC Quant Agent v0.3.11 Research↔Runtime Alignment + Registry + Forward Data Foundation

项目：`EXASHXE/btc-quant-agent`
本地目录：`/root/workspace/project/Quant-agent`
Windows：`\\wsl.localhost\Ubuntu\root\workspace\project\Quant-agent`

当前研究分支：
`codex/v0.3.10-range-mean-reversion-qualification`

当前最新已知 HEAD：
`4aa1dc230bd20a1e8b48d38351b33e169d9079a9`

v0.3.10 formal code SHA：
`3fa0a4f7c2463e0f5f7d696c3790a8e24c4dd6e5`

v0.3.10 结论：
- H29 Range mean reversion = `INCONCLUSIVE_MECHANISM`
- H30 RANGE incremental value = `FALSIFIED`
- H31 = diagnostic only
- Recommendation = `INCONCLUSIVE_RANGE_MECHANISM`
- Final Holdout = SEALED
- Execution = DISABLED

---

# 0. 本轮定位

本轮版本定义：

`v0.3.11 Research↔Runtime Alignment + Strategy/Feature Registry + Forward Data Foundation`

本轮**不是新的 Alpha 参数实验**，也不是 Candidate Freeze、Holdout、Paper、Testnet 或 Live 版本。

本轮的核心目标只有三个：

1. **P0：Research ↔ Runtime 对齐**
   - 研究已经否定的旧 Direction Engine，不允许 Runtime 继续把它输出成 actionable `LONG/SHORT Signal`。
   - 已验证的 TP/BR Movement/Opportunity 能力保留，但必须降级为 `OPPORTUNITY_ONLY`。

2. **P0：真正启动 Point-in-Time Derivatives Forward 数据积累**
   - OI / Taker Flow / Basis / Global Long-Short / Funding 等从现在开始持续积累真实 observed-at 数据。
   - 不允许以后使用 REST 历史接口伪造“当时真实可见”的 PIT 状态。

3. **P1：建立 Strategy / Feature / Hypothesis Registry**
   - 让每个研究组件有明确的研究状态、Runtime 资格、证据路径、数据集使用记录和停止原因。
   - 后续任何 Alpha 必须经历：`Research → Qualification → Registry → Runtime`。

本轮不追求盈利指标。

---

# 1. 已冻结的研究事实

不得在本轮重新解释、重新调参或修改以下结论。

## 1.1 旧 Price-only Direction 已失去运行资格

v0.3.5 / v0.3.6 已确认：

- Trend Pullback directional edge：不成立
- Breakout Retest directional edge：不成立
- 1H Trend Regime directional edge：FALSIFIED
- 4H Macro incremental direction：FALSIFIED
- 15m Structure incremental direction：FALSIFIED
- RSI / ROC incremental direction：FALSIFIED
- `PROPOSED_DIRECTION_ARCHITECTURE = NONE`

因此当前 `v0.2.2` 的：

```text
1H Trend
→ TP / BR
→ Multifactor
→ Risk
→ LONG / SHORT
```

不能继续作为正常 Runtime actionable strategy。

## 1.2 Opportunity / Movement Layer 保留

TP / BR 的 Pattern 对未来 movement / high-low range 有重复支持。

因此：

```text
TP / BR Direction Role = REJECTED
TP / BR Opportunity Role = SUPPORTED_MOVEMENT
```

不得删除 TP/BR Pattern 代码，也不得把其 legacy side 当成交易方向重新包装。

## 1.3 Funding family

Funding Crowding 有弱信号但不稳定；v0.3.8 已停止该 family。

不得在本轮重新扫 Funding percentile/window。

## 1.4 Cross-Asset Breadth

v0.3.9：

```text
H26 = FALSIFIED
H27 = FALSIFIED
H28 = FALSIFIED
```

不得反转 XAB、换币篮子、换窗口、换 4/5 阈值继续挖同一 Development。

## 1.5 Range Mean Reversion

v0.3.10：

- 4h/8h signed return 为正
- H29 `INCONCLUSIVE_MECHANISM`
- H30 `FALSIFIED`
- 不能进入 bounded-grid prototype

本轮不得继续调整 Boll20 / 2σ / stop / horizon / Range 阈值。

---

# 2. Git 工作流

先执行：

```bash
cd /root/workspace/project/Quant-agent
git status
git remote -v
git branch --show-current
git log --oneline --decorate -20
git tag --list
gh auth status
```

从**实际最新** v0.3.10 HEAD 创建：

```bash
git switch -c codex/v0.3.11-runtime-alignment-forward-data
```

如果分支已经存在则复用。

记录：

- start SHA
- current main SHA
- existing research PR 状态

不要自动 merge main。

---

# 3. 开始前完整质量检查

执行：

```bash
python -m pip install -e '.[dev,research]'
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src tools tests skill-template/scripts
```

记录最新：

- tests passed
- overall coverage
- critical runtime/collector coverage
- Ruff
- Mypy
- compileall

如果基线已有失败，先定位，不要通过削弱测试解决。

---

# 4. P0-A：建立 Research / Strategy / Feature Registry

新增项目级 Registry，建议：

```text
configs/research_registry.json
src/btc_quant_agent/research_registry.py
```

Registry 是后续 Runtime Gate 的唯一研究资格来源。

## 4.1 必须支持的研究状态

至少：

```text
REJECTED
DIAGNOSTIC_ONLY
SUPPORTED_MOVEMENT
INCONCLUSIVE
CANDIDATE
FROZEN
VALIDATED_OOS
VALIDATED_FORWARD
```

不要把 `INCONCLUSIVE` 自动视为可运行策略。

## 4.2 Runtime eligibility 独立建模

不要仅靠 research status 猜权限。

至少：

```text
BLOCKED
ANALYSIS_ONLY
SHADOW_ONLY
PAPER_TESTNET_ONLY
LIVE_ELIGIBLE
```

默认规则：

> Registry 缺失、无法解析、组件未知时，一律 fail closed。

本轮当前所有 Direction 组件均不得达到 `SHADOW_ONLY` 以上。

## 4.3 每个 Registry component 至少包含

```text
component_id
component_type
feature_family
role
version
research_status
runtime_eligibility
hypothesis_ids
versions_tested
development_window
dataset_ids
development_reuse_count
final_holdout_accessed
evidence_paths
reason
stopped_family
eligible_for_reuse
last_updated
```

`component_type` 至少支持：

```text
FEATURE
DETECTOR
DIRECTION_ENGINE
STRATEGY
REGIME
```

`role` 至少支持：

```text
OPPORTUNITY
DIRECTION
REGIME
RISK
EXECUTION
DIAGNOSTIC
```

## 4.4 初始 Registry 必须包含并与现有正式报告核对

至少建立以下组件：

### `legacy_price_direction_v022`

```text
role = DIRECTION
research_status = REJECTED
runtime_eligibility = BLOCKED
```

证据引用 v0.3.5 / v0.3.6。

### `trend_pullback_opportunity`

```text
role = OPPORTUNITY
research_status = SUPPORTED_MOVEMENT
runtime_eligibility = ANALYSIS_ONLY
```

同时记录 legacy directional role 已 rejected。

### `breakout_retest_opportunity`

同上。

### `funding_crowding_direction`

```text
role = DIRECTION
research_status = INCONCLUSIVE
runtime_eligibility = BLOCKED
stopped_family = true
```

### `xab4h_direction`

```text
role = DIRECTION
research_status = REJECTED
runtime_eligibility = BLOCKED
```

### `range_boll20_2z_mean_reversion`

```text
role = DIAGNOSTIC / STRATEGY_CANDIDATE_MECHANISM
research_status = INCONCLUSIVE
runtime_eligibility = ANALYSIS_ONLY 或 BLOCKED
```

不得称为 Candidate Strategy。

### `active_direction_engine`

明确：

```text
state = NONE
runtime_eligibility = BLOCKED
reason = no direction component currently qualified
```

## 4.5 Registry validator

实现：

```text
quantctl research-registry validate
quantctl research-registry status
quantctl research-registry show <component_id>
```

Validator 至少检查：

- 唯一 component_id
- 合法 status
- 合法 eligibility
- evidence path 存在
- `final_holdout_accessed=false` 与当前状态一致
- `LIVE_ELIGIBLE` 必须对应 `VALIDATED_FORWARD`
- REJECTED 不得 runtime actionable
- SUPPORTED_MOVEMENT 不得成为 directional actionable
- 未知字段 / schema version 行为明确

新增 Registry schema version。

---

# 5. P0-B：Research ↔ Runtime Alignment

当前 `QuantEngine.scan()` 仍可执行旧：

```text
TREND_UP / TREND_DOWN
→ find_candidate()
→ factors
→ risk
→ Signal(ACTIVE)
→ LONG/SHORT
```

这与研究事实冲突。

v0.3.11 必须纠正。

---

# 6. 新的 Runtime Decision Layer

引入显式分层状态，而不是只有：

```text
LONG / SHORT / WAIT
```

至少支持：

```text
NO_OPPORTUNITY
OPPORTUNITY_ONLY
DIRECTION_CANDIDATE
TRADEABLE_CANDIDATE
ACTIONABLE_SIGNAL
```

当前 v0.3.11 正常 Runtime 实际允许到达的最高层级：

```text
OPPORTUNITY_ONLY
```

因为没有 qualified Direction Engine。

不得制造假的 `DIRECTION_CANDIDATE`。

---

# 7. OpportunityEvidence 数据模型

建议新增：

```text
OpportunityEvidence
```

字段至少：

```text
opportunity_id
symbol
detector_id
setup
detected_at_ms
data_timestamp_ms
expires_at_ms
regime
research_status
runtime_eligibility
movement_evidence
reasons
risks
legacy_pattern_side
legacy_side_is_actionable = false
```

重要：

- `legacy_pattern_side` 可以保留作解释/研究元数据；
- 绝不能被 Agent / API / Execution 当成方向；
- Opportunity 不应包含可执行 `entry/SL/TP/position size`；
- Opportunity 不应写入 `signals` 表；
- Opportunity 不进入当前 `shadow_trades` 交易 PnL 统计。

如需持久化，新增独立：

```text
opportunities
```

表或使用明确 event type，但推荐独立表以便未来 Signal Shadow。

---

# 8. 正常 Runtime 的 TP / BR 行为

Runtime 可以继续调用 deterministic TP / BR detector 来发现机会。

但 pipeline 改为：

```text
1H Regime
↓
TP / BR deterministic pattern found
↓
Research Registry 查资格
↓
TP / BR = SUPPORTED_MOVEMENT + ANALYSIS_ONLY
↓
返回 OPPORTUNITY_ONLY
↓
signal = null
↓
不执行 Direction Factor Gate
↓
不执行 Position Plan
↓
不生成 Entry / SL / TP
↓
不允许 Execution Plan
```

特别注意：

> 已被证伪的旧 multifactor direction chain 不应该继续作为“Opportunity 质量过滤器”偷偷影响正常 Runtime，除非已有正式 Movement evidence 支持该 gate。

因此正常 `OPPORTUNITY_ONLY` 应在确定 TP/BR Pattern 后、旧 Direction factor/risk chain 之前输出。

如果研究报告明确支持的是特定冻结 pattern stage，严格按正式 evidence 对齐；不得擅自扩大或缩小定义。

---

# 9. 保留历史研究可复现性

不能因为 Runtime 修正，就让 v0.3.0–v0.3.10 的 frozen research 无法复现。

当前很多研究代码依赖 `QuantEngine.scan()` 的 legacy v0.2.2 semantics。

必须显式拆分：

```text
RUNTIME_GATED
vs
LEGACY_RESEARCH_V022
```

可采用：

```text
EngineMode
LegacyDirectionResearchEngine
legacy_scan()
```

等实现，但要求：

- `QuantService` 正常服务只能使用 `RUNTIME_GATED`；
- frozen historical backtest/research 必须显式 opt-in `LEGACY_RESEARCH_V022`；
- 禁止默认 fallback 到 legacy；
- 旧研究 replay 的关键 frozen counts 必须保持等价；
- import 新 Registry 不得改变旧 formal research artifact semantics。

新增 regression：

```text
legacy research replay reproduces frozen baseline
runtime gated scan cannot emit legacy actionable LONG/SHORT
```

---

# 10. ScanResult / API 向后兼容

建议扩展 `ScanResult`：

```text
action
health
reason
signal
opportunity
diagnostics
reason_code
runtime_stage
registry_snapshot
```

保持旧消费者可解析：

- 原 `signal` 字段继续存在；
- `OPPORTUNITY_ONLY` 时 `signal = null`；
- 新增字段必须有兼容默认值。

当前无 Direction Engine 时，不允许正常 `scan()` 返回：

```text
LONG
SHORT
CONFIRMED actionable signal
```

如果发现 TP/BR：

```text
action = OPPORTUNITY_ONLY
reason_code = OPPORTUNITY_SUPPORTED_MOVEMENT
```

如果没有：

```text
action = WAIT
```

或 `NO_OPPORTUNITY`，但 CLI/API 语义必须一致并文档化。

---

# 11. Existing legacy signals 必须 fail closed

数据库里可能存在旧 ACTIVE/历史 Signal。

v0.3.11 后：

`ExecutionService.build_entry_plan()` 必须在任何风险计算前重新检查 Registry eligibility。

对于：

```text
legacy_price_direction_v022
TP/BR legacy direction
```

必须拒绝：

```text
RESEARCH_REGISTRY_NOT_ACTIONABLE
```

不要仅依赖：

```text
execution.mode = disabled
```

因为未来有人可能切到 paper/testnet。

Live 原有 `VALIDATED_FORWARD` Gate 保留且不得削弱。

新增 status 输出：

```text
research_registry_gate
qualified_direction_engine
runtime_actionability
```

---

# 12. Runtime Version 对齐

当前默认：

```text
strategy_version = 0.2.2
feature_version  = 0.2.2
```

正常 Runtime 不应继续表现成“仍在运行 v0.2.2 validated direction”。

本轮升级 runtime identity，例如：

```text
strategy_version = 0.3.11
feature_version = 0.3.11
validation_status = EXPERIMENTAL
```

或设计更清晰的：

```text
runtime_policy_version
research_registry_version
```

但最终默认配置必须清楚表达：

```text
No qualified actionable direction strategy exists.
```

同时：

- v0.2.2 frozen research config 必须保留；
- 历史研究重放不得因为默认配置版本变化而失真。

更新：

```text
CHANGELOG
README / skill docs
runtime architecture docs
```

---

# 13. P0-C：Forward Derivatives Data Foundation

这是本轮第二个 P0。

原因：

> 价格历史以后仍能下载；真正 Point-in-Time 的 OI / Taker / Basis / Positioning 数据如果今天没有记录，未来往往无法完整恢复“当时实际可见状态”。

因此本轮必须不仅“写 collector”，还要**真正具备长期运行和审计能力，并尝试启动采集**。

---

# 14. Forward 数据范围

默认 BTCUSDT，每 15 分钟一个 snapshot。

至少采集：

```text
mark_price
index_price
premium_bps
funding_rate
funding source timestamp
open_interest
open_interest source timestamp
open_interest_change_pct
taker_buy_sell_ratio
taker source timestamp
basis_rate
basis source timestamp
global_long_short_account_ratio
long_short source timestamp
```

Orderbook：

```text
default OFF
```

原因：15 分钟一次 L2 snapshot 不足以做可靠 Queue/Microstructure replay。

可以保留 optional collector 能力，但不得把稀疏 orderbook snapshot 当作未来执行验证数据。

---

# 15. 修正 observed_at 语义

当前 `BinancePublicClient.derivatives()` 在网络请求开始前就设置：

```text
observed_at_ms
```

这可能把“完整 snapshot 真正可用时间”提前。

v0.3.11 必须改成保守 PIT semantics：

```text
collection_started_at_ms = first request start
observed_at_ms = all required/attempted endpoint responses processed and snapshot assembled time
```

也就是说：

> 一个 snapshot 只有在 collector 已经收到并组装完数据之后，才可被后续 as-of research 认为可见。

每个字段自己的 source timestamp 继续单独保存。

不得把 exchange source timestamp 当成 local availability timestamp。

新增相关 causality tests。

---

# 16. 不要继续用“每次重写整个 CSV”作为唯一长期存储

当前 collector：

```text
read whole CSV
+ add row
+ rewrite whole CSV
```

适合短期实验，不适合作为长期 PIT archive 的唯一 source of truth。

本轮新增 append-safe Forward Store。

推荐：

```text
data/forward/BTCUSDT/derivatives.sqlite3
```

或同等可靠的 append-only store。

如果使用 SQLite：

```text
WAL
UNIQUE(symbol, observed_at_ms)
transactional insert
busy_timeout
append only
```

不得用 `INSERT OR REPLACE` 静默篡改已有 historical PIT snapshot。

重复 snapshot：

- 可 ignore exact duplicate；
- checksum/payload 不一致时必须报 conflict，不可覆盖。

市场数据目录必须继续 gitignore。

---

# 17. ForwardDerivativeStore schema

至少包含：

```text
symbol
collection_id
collection_started_at_ms
observed_at_ms
collector_version
mark_price
index_price
premium_bps
funding_rate
funding_time_ms
open_interest
open_interest_time_ms
open_interest_change_pct
taker_buy_sell_ratio
taker_time_ms
basis_rate
basis_time_ms
long_short_account_ratio
long_short_time_ms
order_book_imbalance nullable
spread_bps nullable
order_book_time_ms nullable
field_availability_json
endpoint_errors_json
payload_hash
```

另建 `collection_runs` 或等价 audit ledger：

```text
run_id
started_at_ms
finished_at_ms
status
attempted_fields
successful_fields
error_summary
```

Collector 某个 optional endpoint 失败时：

- snapshot 可以部分保存；
- 必须记录 field unavailable / endpoint error；
- 不得无声写 `None` 后假装成功。

---

# 18. 新 CLI

建议新增：

```text
quantctl derivatives collect-once
quantctl derivatives run
quantctl derivatives status
quantctl derivatives audit
quantctl derivatives export
```

兼容旧：

```text
quantctl collect-derivatives
```

可以作为 compatibility alias，但新文档统一使用 `quantctl derivatives ...`。

## collect-once

执行一次真实 PIT collection。

## run

默认：

```text
cadence = 15m
align to UTC 00/15/30/45 boundary
small fixed post-boundary delay e.g. 15–30s
```

避免 drift：

不要简单永久：

```text
sleep(900)
```

而是每轮重新计算下一个 UTC boundary。

## status

至少输出：

```text
store path
sample count
first observed_at
last observed_at
last sample age
coverage since first sample
expected samples
missing cadence slots
gap count
largest gap
per-field availability %
recent endpoint errors
collector/scheduler state if detectable
research_eligibility = NOT_ENOUGH_FORWARD_DATA / ...
```

## audit

检查：

- timestamp ordering
- duplicates
- conflicts
- cadence gaps
- source timestamps > observed_at anomalies
- impossible numerical values
- field coverage

不允许自动填历史 gap。

## export

将已积累 store 导出为现有：

```text
HistoricalDerivativeStore-compatible CSV
```

并生成 manifest + checksum。

这样未来 research 可复用现有 backward-as-of 框架。

---

# 19. Forward Data Research Eligibility 只做覆盖 Gate

本轮不使用这些新采集 snapshot 做 Alpha 选择。

新增 coverage-only 状态，例如：

```text
COLLECTING
INSUFFICIENT_FORWARD_HISTORY
ELIGIBLE_FOR_PREREGISTERED_RESEARCH
```

可采用一个提前写死的 operational minimum，例如：

```text
>= 30 calendar days
>= 2500 snapshots
required field availability >= 95%
no unexplained large persistent gaps
```

这是**数据覆盖资格**，不是统计 Alpha 资格。

报告必须明确：

> 30 days / 2500 samples does not mean the feature has edge; it only means a future preregistered derivatives study has enough genuine PIT coverage to begin.

不得为了更快进入 v0.3.12 降低这个门槛。

如果决定不同数字，必须在实现/查看未来结果前写进文档和测试，并说明原因。

---

# 20. 真正启动长期采集

不仅创建代码。

本轮完成后必须：

1. 真实运行至少一次 `collect-once`；
2. 验证 snapshot / store / status / audit；
3. 尝试启用长期 scheduler。

推荐提供 user-level systemd：

```text
deploy/systemd/btc-quant-forward-derivatives.service
deploy/systemd/btc-quant-forward-derivatives.timer
```

或者更可靠等价方案。

Timer 建议每 UTC 15 分钟运行一次 oneshot collector，而不是依赖 Codex session 常驻。

要求：

- 不需要 API secret；只访问 Binance public endpoints；
- 不使用 sudo 静默修改系统；
- 优先 `systemctl --user`；
- installer 必须显式输出实际 repo/python/store path；
- `Persistent=true` 可以恢复 scheduler，但不能伪造错过时间段的 PIT samples；
- laptop/WSL 关闭期间的 gap 必须保留为 gap。

Codex 在当前环境中：

- 如果 user systemd 可用：安装、enable、start，并验证 timer active；
- 如果不可用：不要假装“已经长期运行”；生成可执行 fallback / deployment instruction，并将最终状态标为 `SCHEDULER_NOT_STARTED`，说明 blocker。

禁止用一个不可审计的后台 `nohup` 进程冒充可靠长期部署。

---

# 21. Collector Health 纳入 `quantctl health`

`quantctl health` 增加：

```text
forward_derivatives:
  store_exists
  sample_count
  last_observed_at
  last_age_seconds
  scheduler_detected
  scheduler_active
  required_field_coverage
  largest_gap
  collection_status
```

Collector 不健康不应让整个 Quant runtime 崩溃，但必须明确 DEGRADED/NOT_COLLECTING。

---

# 22. P1：Researcher Overfitting Governance

当前同一 Development 已执行大量 hypothesis。

单实验 preregistration 做得好，但项目级仍需要记录 repeated research reuse。

新增 Registry / docs 能回答：

```text
这个 feature family 已测试几轮？
用过哪些 Development window？
是否已 stop？
是否允许 reopen？
是否已经消费 Holdout？
是否只是 diagnostic？
```

对 stopped family：

```text
eligible_for_reuse = false
```

重新打开必须有：

```text
new_mechanism_id
new independent information source
written rationale
```

不能只因为换阈值就视为“新 hypothesis”。

---

# 23. `quantctl research-registry status` 推荐输出

例如：

```text
Direction:
  active qualified engine: NONE

Opportunity:
  TP: SUPPORTED_MOVEMENT / ANALYSIS_ONLY
  BR: SUPPORTED_MOVEMENT / ANALYSIS_ONLY

Stopped Direction Families:
  legacy price-only: REJECTED
  funding crowding: INCONCLUSIVE + STOPPED
  XAB4H: REJECTED

Range:
  BOLL20_2Z: INCONCLUSIVE / H30 FALSIFIED / NOT CANDIDATE

Final Holdout:
  SEALED

Runtime maximum stage:
  OPPORTUNITY_ONLY
```

---

# 24. Skill / API / Explanation 层同步

更新 Agent-facing output，使 Skill 能解释：

```text
Market State
Opportunity
Opportunity Research Status
Qualified Direction Evidence
Counter Evidence
Tradeability
Risk
Runtime Eligibility
```

当前正常示例应类似：

```text
Opportunity: BREAKOUT_RETEST
Opportunity status: SUPPORTED_MOVEMENT
Direction: UNQUALIFIED
Actionability: ANALYSIS_ONLY
Action: WAIT / OPPORTUNITY_ONLY
Reason: no research-qualified Direction Engine
```

不得由 LLM 根据 legacy pattern side 自己恢复 LONG/SHORT。

文档明确：

> Agent may explain evidence but may not promote ANALYSIS_ONLY evidence into an actionable Direction.

---

# 25. Shadow 语义拆分设计

本轮只做基础 schema / docs，不要求启动正式 Forward Shadow。

明确未来：

```text
Signal Shadow
```

用于 Alpha / direction validation；

```text
Execution Shadow
```

用于：

- real-time quote
- fillability
- fill latency
- partial fill
- slippage
- protective-order timing

不要继续把两者称为同一个 Shadow 指标。

现有旧 `shadow_trades` 保持兼容，但文档标记它属于 legacy signal shadow semantics。

---

# 26. Backtest / Live Trigger Semantics Backlog

本轮不要求实现完整 Tick/L2 engine，但必须写入明确 engineering backlog：

1. Live protective order 使用 `MARK_PRICE` 时，future backtest Candidate 必须验证相同 trigger semantics；
2. Bar-touch fill ≠ guaranteed fill；
3. future Candidate 需要 partial-fill / fill-probability model；
4. fixed slippage 要升级成 volatility/liquidity-aware model；
5. 这些工作必须在 Candidate Freeze 后、Testnet 前完成。

不要让这些 execution work 取代当前 Direction Alpha 缺口。

---

# 27. Range Family 本轮状态

v0.3.10 Range：

```text
H29 = INCONCLUSIVE_MECHANISM
H30 = FALSIFIED
```

本轮不继续 Range 参数研究。

Registry 中标记：

```text
NOT_CANDIDATE
NOT_RUNTIME_ACTIONABLE
```

可以在 roadmap 记录：未来最多允许一个机制解释型 diagnostic，前提是研究目标是解释：

```text
positive terminal return
vs
weak center-before-adverse ordering
```

而不是重新扫 Boll/stop/horizon。

---

# 28. 新 Direction Alpha 下一版规划

v0.3.11 不正式验证新 Direction Alpha。

输出数据/registry readiness 后，v0.3.12 根据真实可用信息源选择：

优先：

```text
genuine PIT OI / Taker / Basis / Positioning
```

但只有 coverage gate 达标后才允许正式 derivatives qualification。

如果 forward derivatives 尚未积累够：

下一 Direction Study 应选择真正独立、可历史 point-in-time 获取并明确 provenance 的：

```text
on-chain / market-flow
```

而不是又回到 EMA / RSI / MACD / XAB 参数变化。

---

# 29. 必须新增的关键 Tests

至少覆盖：

## Registry

```text
test_registry_rejected_component_cannot_be_actionable
test_registry_supported_movement_is_analysis_only
test_registry_live_eligible_requires_validated_forward
test_registry_unknown_component_fails_closed
test_registry_evidence_paths_exist
test_registry_holdout_state_is_sealed
```

## Runtime alignment

```text
test_runtime_legacy_tp_does_not_emit_actionable_long_short
test_runtime_legacy_br_does_not_emit_actionable_long_short
test_runtime_tp_br_emit_opportunity_only_without_signal
test_opportunity_contains_no_entry_stop_take_profit_size
test_runtime_does_not_apply_rejected_direction_factor_as_actionability_gate
test_quant_service_always_uses_runtime_gated_mode
test_legacy_research_mode_is_explicit_only
test_legacy_research_reproduces_frozen_v022_behavior
```

## Execution gate

```text
test_execution_plan_rejects_registry_blocked_legacy_signal
test_execution_status_reports_no_qualified_direction_engine
```

## Forward collector

```text
test_snapshot_observed_at_is_after_collection_completion
test_source_timestamps_are_preserved
test_partial_endpoint_failure_is_recorded
test_forward_store_is_append_only
test_forward_store_duplicate_exact_row_is_idempotent
test_forward_store_conflicting_duplicate_fails
test_forward_store_ordering
test_forward_store_export_is_backward_asof_compatible
test_derivative_audit_detects_gap
test_derivative_audit_never_backfills_gap
test_status_reports_field_coverage
test_boundary_scheduler_computes_next_utc_quarter_hour
test_order_book_collection_default_off
```

## Safety

```text
test_execution_remains_disabled_by_default
test_final_holdout_remains_sealed
test_runtime_registry_does_not_open_holdout
test_no_market_data_is_committed_to_git
```

---

# 30. 数据和隐私 / Secret Safety

Forward public collector：

- 不读取 Binance trading API secret；
- 不需要签名 endpoint；
- 数据目录不提交 Git；
- manifests 可以提交模板/测试 fixture，但不能提交大规模真实市场数据；
- 日志不得泄漏未来交易 credentials。

Execution credentials 原有机制不改变。

---

# 31. Performance / Reliability

Runtime scan 新 Registry Gate 不应显著增加延迟。

目标：

```text
registry cached/read-once
normal scan no repeated disk parse on every internal step
```

Forward collector：

- 单次网络失败不能破坏既有 store；
- store write atomic；
- collector restart safe；
- scheduler restart safe；
- status/audit 可在 collector 运行时读取。

---

# 32. 本轮 Deliverables

生成：

```text
docs/V0.3.11_RUNTIME_ALIGNMENT_FORWARD_DATA_REPORT.md
docs/RESEARCH_REGISTRY.md
docs/FORWARD_DERIVATIVES_OPERATIONS.md

deliverables/v0.3.11/README.md
deliverables/v0.3.11/V0.3.11_RUNTIME_ALIGNMENT_FORWARD_DATA_REPORT.md
deliverables/v0.3.11/V0.3.11_NUMERIC_ANSWERS.json
deliverables/v0.3.11/V0.3.11_RECOMMENDATION.md
```

`FORWARD_DERIVATIVES_OPERATIONS.md` 必须写清：

```text
安装
启动
停止
status
audit
数据路径
export
scheduler 检查
WSL/关机造成 gap 的语义
恢复方式
```

---

# 33. 最终必须回答的数字/状态

1. 最新测试总数？
2. overall coverage？
3. Registry component 数量？
4. Direction role 中可 actionable 的 component 数量？答案预期应为 0。
5. TP/BR 正常 runtime 是否还会输出 LONG/SHORT Signal？
6. TP/BR 是否能输出 `OPPORTUNITY_ONLY`？
7. Opportunity 是否完全没有 Entry/SL/TP/Size？
8. Legacy research replay 是否保持冻结行为？
9. Existing legacy Signal 是否被 Execution Registry Gate 拒绝？
10. Forward store 路径？
11. 实际已采集 snapshot 数？
12. 首/末 observed_at？
13. OI / Taker / Basis / Long-Short / Funding field availability？
14. 是否发现 endpoint error？
15. 当前最大 gap？
16. scheduler 是否实际 ACTIVE？
17. 如果没 active，具体 blocker 是什么？
18. 下一次计划采集时间？
19. 当前 forward dataset research eligibility？
20. Final Holdout 是否仍 SEALED？
21. execution 是否仍 DISABLED？
22. v0.3.12 推荐进入哪个数据 family？为什么？

---

# 34. Acceptance Gate

本轮只有同时满足以下条件才算 PASS：

### Runtime alignment

```text
normal QuantService cannot emit actionable legacy TP/BR LONG/SHORT
TP/BR can survive as OPPORTUNITY_ONLY
default deny when Registry unavailable
legacy research remains explicitly reproducible
```

### Registry

```text
machine-readable registry exists
validator exists
runtime uses it as gate
current qualified direction engine = NONE
```

### Forward data

```text
append-safe PIT store exists
observed_at semantics corrected
status/audit/export exist
at least one real public snapshot collected
long-term scheduler installation/start attempted and truthfully reported
```

### Safety

```text
execution.mode = disabled
auto_execute = false
allow_live = false
Final Holdout SEALED
no Candidate Freeze
```

如果 Registry Runtime Gate 没有真正进入 `QuantService` 正常路径，只写了 docs，不算 PASS。

如果 collector 只保留原来 CSV `--samples` 逻辑、没有长期 append-safe storage/status/audit/scheduler foundation，不算 PASS。

---

# 35. 禁止项

本轮绝对禁止：

```text
重新把 TP/BR legacy direction 变成 actionable
用 LLM 补 Direction
改 RR
改 TP/BR 参数
改 RANGE/Boll 参数
改 Funding 参数
改 XAB basket/window/threshold
开 Final Holdout
Candidate Freeze
Paper/Testnet/Live
Martingale/Grid execution
使用新 Forward 数据立即挑 Alpha
因为 scheduler gap 而历史 REST 回填成 PIT
```

---

# 36. Git / CI

结束前：

```bash
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src tools tests skill-template/scripts
git status
git log --oneline --decorate -20
```

Push：

```bash
git push -u origin codex/v0.3.11-runtime-alignment-forward-data
```

创建最新 research/runtime PR，但不要自动 merge。

PR 必须明确：

```text
No Alpha claim
No Candidate
Execution disabled
Final Holdout sealed
Legacy direction removed from actionable runtime
Forward derivatives collection foundation added
```

---

# 37. 最终汇报格式

Codex 最终回复必须列出：

```text
branch
start SHA
final HEAD
major commits
CI
pytest / coverage / Ruff / Mypy / compileall
registry schema/version
qualified direction engine count
runtime maximum decision stage
TP/BR runtime behavior
legacy research compatibility status
forward store path
real snapshot count
collector field coverage
scheduler status
canonical docs/deliverables
Final Holdout status
Execution status
v0.3.12 recommendation
```

最后固定输出：

```text
Strategy status: EXPERIMENTAL
Qualified Direction Engine: NONE
Runtime maximum actionability: OPPORTUNITY_ONLY
Execution: DISABLED
Final Holdout: SEALED
```

现在开始执行：

`v0.3.11 Research↔Runtime Alignment + Registry + Forward Data Foundation`
