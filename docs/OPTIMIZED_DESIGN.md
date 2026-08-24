# BTC Quant Agent Skill 第一阶段优化设计

版本：v0.3  
目标：BTCUSDT USDⓈ-M 永续合约，4H Macro + 1H Regime + 15m Setup；执行接口默认关闭  
策略状态：`EXPERIMENTAL`，完成统计验收前不得标记为 `VALIDATED`

当前实现版本：v0.2.1（Quant Correctness Fix）。本版本修正风险预算、历史衍生品因果
对齐、Pullback 区间、TTL、动态失效和 TIMEOUT 边界；不提前实现 v0.2.2/v0.3.0。

## 1. 评审结论

原 v0.1 的核心理念合理，尤其是以下部分应当保留：

- Quant 决策、LLM 解释，Agent 不得修改方向和交易数字。
- 实时与回测共用策略逻辑，严格限制未来函数。
- Regime → Setup → Hard Filter → Risk → Signal 的分层正确。
- 风险按止损距离计算，杠杆只影响保证金，不决定风险仓位。
- Walk-forward、Holdout、成本压力测试、Monte Carlo 和 Shadow Trading 都是必要验证环节。

主要问题不是方向错误，而是首期边界过大、若干概念没有精确定义：

| 原设计问题 | 优化决定 |
| --- | --- |
| 把数据平台、生产实时、两套 Alpha、ML、MCP、飞书交互和 30–60 天验证都列为第一阶段 DoD | 拆成“软件 MVP”和“策略验证 Gate”；代码完成不等于策略有效 |
| NautilusTrader 被同时视为底座和早期必需项 | 首期使用轻量确定性事件核心；保留 Adapter 接口，验证后再接 NautilusTrader |
| `p_win`、`expected_r` 在没有校准模型时仍出现在示例 | 未完成样本外校准时强制为 `null`，只展示规则评分 |
| Signal 状态和用户是否接受混在同一状态机 | Signal 生命周期、用户决策、Shadow 成交三套状态分别存储 |
| Entry 是区间，但 RR/仓位没有说明使用哪个价格 | 统一用区间中点做计划；回测成交采用对策略不利的区间边缘 |
| 飞书“自建机器人 + 交互按钮”边界不清 | 首版 Custom Bot 只推送；按钮回调需应用机器人和回调服务，放到后续 |
| 衍生品数据的事件时间没有定义 | 每个快照同时记录 `observed_at` 与数据自身时间，过期值只能降级或拒绝 |
| 结构、回踩、突破仍有“靠近”“最好”等模糊词 | 全部参数化，并冻结在版本化配置中 |
| 20x 只展示保证金，未强调爆仓/跳空风险 | 增加名义仓位上限、摩擦成本和“止损不保证成交价”的风险说明 |

## 2. 第一阶段的两个 Definition of Done

### 2.1 Software MVP DoD

- 默认使用公开只读 Binance 数据；执行模式关闭时不读取交易 API Key。
- 只将已收盘 K 线送入特征管线。
- 因果 Pivot、结构、EMA、ATR、ADX、量能计算有单元和因果测试。
- 1H Regime 与 15m Trend Pullback / Breakout Retest 使用确定性规则。
- Risk Engine 输出 Entry、SL、TP、净 RR、名义仓位、展示保证金和最大计划损失。
- Signal 带策略、特征、模型、配置哈希和数据时间版本字段。
- SQLite 实现去重、TTL、用户决策和 Shadow 结果。
- 回测与实时复用 `QuantEngine`；同一 1m K 线同时触发 SL/TP 时采用 `stop_first`。
- 提供 CLI、可选 API、飞书单向推送与薄 Agent Skill。
- 提供隔离的执行端点，但默认 `disabled`；必须通过计划哈希、时效、风险限额和模式门禁。

### 2.2 Strategy Validation DoD

这是运行研究流程后才能获得的证据，不能由生成代码直接宣称完成：

- 数据覆盖至少多个趋势、震荡和高波动阶段。
- Walk-forward 的所有参数只在训练/验证窗选择。
- 最终 Holdout 只运行一次，并保留实验记录。
- 样本外交易数建议不少于 150；不足时标记 `LOW_SAMPLE_CONFIDENCE`。
- OOS Expectancy > 0、Profit Factor ≥ 1.2、正收益 Fold ≥ 70%。
- 2× 成本压力下不发生显著崩溃。
- 关键参数 ±10% 存在稳定高原。
- 完成 30–60 天 Shadow Forward，且 Live/Backtest 差异可解释。

只有全部通过，才允许从 `EXPERIMENTAL` 升级为 `VALIDATED_FORWARD`。

## 3. 优化后的架构

```text
Binance Public REST / Future WS Adapter
                  ↓
     Canonical Closed-Candle Store
                  ↓
     Data Quality + Event-time Gate
                  ↓
     Causal Multi-timeframe Feature Pipeline
                  ↓
      4H Macro + 1H Regime + 15m Alpha
                  ↓
   Five-group Score + Hard Filter + Risk
                  ↓
          Immutable Signal
          ↙              ↘
 SQLite / Shadow       CLI / REST
                            ↓
                     Agent Skill / 飞书
                            ↓ explicit request only
        disabled | paper | testnet | live Execution Adapter
```

首期不引入微服务、消息队列、Kubernetes 或在线学习。`QuantEngine.scan()` 是唯一交易判断入口；CLI、API、回测和未来的 MCP 只调用它。

NautilusTrader 仍作为后续 Adapter，而不是当前硬依赖。公开数据扩展到 Kline、Mark/Index、Funding、OI/OI 变化、Taker Flow、基差、全局账户多空比和深度。签名交易客户端位于独立 `execution` 包，扫描路径不会隐式调用它。

参考：

- Binance USDⓈ-M Market Data：https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data
- Binance Public WebSocket Streams：https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/public
- Binance USDⓈ-M Account：https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account
- Binance USDⓈ-M Trade：https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade
- NautilusTrader Binance Integration：https://nautilustrader.io/docs/latest/integrations/binance/
- 飞书 Custom Bot Card：https://open.feishu.cn/document/feishu-cards/quick-start/send-message-cards-with-custom-bot

## 4. 数据契约

### 4.1 时间语义

- 所有时间戳使用 UTC Unix 毫秒。
- `open_time_ms` 表示 K 线开始，`close_time_ms` 表示闭合边界。
- 只有 `closed=true` 且 `close_time_ms <= decision_time` 的 K 线可以参与计算。
- OI、Funding、Taker Flow、Basis、多空比和订单簿同时保存事件时间与抓取时间。
- 15m、1H 和 4H 决策以统一的 UTC 边界对齐。

### 4.2 数据质量

硬错误：

- 缂失或重复 K 线
- 时间乱序或间隔不一致
- 包含未收盘或未来 K 线
- 价格 K 线超过一个周期加宽限时间仍未更新

硬错误强制返回 `DATA_INVALID / NO_SIGNAL`。

衍生品数据首期作为确认特征：缺失或过期时标记 `DEGRADED` 并进入风险字段；Funding 极端逆风可直接拒绝。待历史衍生品数据完整后，可把 OI/Taker 条件升级为 Hard Gate。

## 5. 因果特征

- EMA 7/25/99、EMA25/99 斜率
- ATR14、ATR 历史分位
- ADX14
- 30 根成交量 Z-score
- RSI14、ROC12
- Bollinger Bandwidth 历史分位
- 基于 Taker Buy Volume 的 20 根 CVD 斜率
- Confirmed Swing High/Low
- `HH_HL`、`LH_LL`、混合或未确认结构

Pivot 精确定义：设 `left=2, right=2`，候选 Pivot 位于索引 `i`；只有索引 `i+2` 的 K 线收盘后，才允许确认索引 `i` 的 Pivot。因果测试必须证明修改确认时点之后的数据不会改变此前输出。

## 6. Regime 精确定义

`TREND_UP`：

```text
Close > EMA25 > EMA99
EMA25 slope > 0
EMA99 slope >= 0
ADX >= adx_trend_min
Structure == HH_HL
ATR percentile < high_vol_threshold
```

`TREND_DOWN` 完全镜像。ADX 明显偏低时为 `RANGE`；ATR 达高分位为 `HIGH_VOLATILITY`；其余为 `TRANSITION`。只有 4H EMA25/EMA99、斜率与候选方向一致，才继续处理 1H Regime 与 15m Setup。

### 6.1 多因子确认

新增指标不直接相加，而是按信息来源分组并封顶：

| 分组 | 上限 | 主要证据 |
| --- | ---: | --- |
| 趋势与结构 | 30 | 4H 宏观方向、1H Regime |
| 动量 | 15 | RSI 合理区间、ROC 同向 |
| 参与度与订单流 | 20 | Volume Z、CVD、Taker Buy/Sell |
| 衍生品 | 20 | OI 变化、Funding、Basis、账户多空比 |
| 波动与流动性 | 15 | ATR/带宽分位、Spread、前五档 Imbalance |

缺失分组不伪造中性值，而是从可用分母中移除并标记风险。默认要求归一化分数至少 72，至少四个可用分组为正。4H 不对齐、15m RSI 过度延伸、极端逆风 Funding 或点差超过 5 bps 属于硬拒绝。`pattern_score` 是形态完整度，`factor_score` 是分组规则确认度；两者都不是统计胜率。

## 7. Alpha 规则

### 7.1 Trend Pullback

做多：

1. 1H 为 `TREND_UP`。
2. 最近 5 根 15m 的最低价进入 `EMA25 ± pullback_atr_tolerance × ATR` 区域。
3. 最近 5 根最低价仍高于最近确认 Swing Low。
4. 最新 15m 收盘重新站上 EMA7，并突破上一根 15m 高点。
5. Volume Z-score 不低于冻结阈值。
6. 最近确认压力位位于 Entry 上方，净 RR 达标。

做空完全镜像。

### 7.2 Breakout Retest

做多：

1. 使用至少在三根 K 线前已确认的 Swing High 作为压力。
2. 前一根 15m 收盘超过压力 `breakout_atr_min × ATR`。
3. 最新 K 线回踩压力容差区，收盘仍在压力上方并收阳。
4. Volume Z-score 达标。
5. 有更高确认压力时取最近压力；没有时仅允许使用冻结 ATR 投影目标，并在报告中单独标注。

做空完全镜像。

## 8. 风控与成本

计划入场价：`(entry_low + entry_high) / 2`。

止损：

```text
LONG  = invalidation_level - stop_atr_buffer × ATR
SHORT = invalidation_level + stop_atr_buffer × ATR
```

名义仓位：

```text
desired_risk = equity × risk_per_trade
total_loss_pct = stop_distance_pct
               + round_trip_taker_fee_rate
               + round_trip_slippage_rate
               + adverse_funding_rate
notional = min(desired_risk / total_loss_pct, max_notional)
```

若 `notional < min_notional_usdt`，拒绝候选而不是放大仓位。必须满足：

```text
notional × total_loss_pct <= equity × risk_per_trade
```

净 RR 将双边 taker fee、双边滑点与持仓 Funding 估计计入。20x 仅用于显示 `required_margin = notional / 20`。它不改变名义仓位，也不保证止损一定按指定价格成交。

首期默认值为小账户研究参数：单笔风险 0.5%，名义仓位上限 100 USDT。用户必须根据账户和真实费用修改配置。

## 9. Signal Schema 修订

关键新增/修订字段：

```json
{
  "validation_status": "EXPERIMENTAL",
  "strategy_version": "0.2.1",
  "feature_version": "0.2.1",
  "model_version": null,
  "config_hash": "...",
  "data_timestamp_ms": 0,
  "p_win": null,
  "expected_r": null,
  "estimated_fee_usdt": 0.0,
  "estimated_slippage_usdt": 0.0,
  "estimated_funding_usdt": 0.0
}
```

`pattern_score` 与 `factor_score` 都只是确定性规则分数，不能称为胜率。只有已冻结模型通过样本外校准后，`p_win` 才可非空；`expected_r` 必须同时使用校准概率、真实 RR 和成本计算。

## 10. 三套独立状态

### Signal 生命周期

```text
ACTIVE → EXPIRED | INVALIDATED | RESOLVED_WIN | RESOLVED_LOSS | RESOLVED_TIMEOUT
```

### 用户决策

```text
ACCEPT | IGNORE
```

### Shadow 成交

```text
UNFILLED | WIN | LOSS | TIMEOUT
```

用户点击接受不能改变 Signal 状态，更不能触发交易所下单。

## 11. 回测约束

- 15m 收盘产生信号，最早只能在下一根 1m K 线成交。
- 入场区间被触及时，回测采用对策略更不利的边缘价格。
- 同一 1m K 线同时碰到 SL 与 TP，采用 `stop_first`。
- 每次只允许一个 Shadow 仓位，避免隐含无限资金。
- TIMEOUT 按最后可用价格计算 R。
- 正式研究必须加入 Funding 的事件时间对齐，且输出正常成本和 2× 成本报告。
- 历史 OI/Funding/Taker/Basis/多空比必须使用 backward as-of join；任何字段时间晚于决策
  时点或超过自身最大时效时，在评分前转换为 `null`。
- Trend Pullback 默认最大持仓 720 分钟，Breakout Retest 默认 480 分钟；TIMEOUT 只使用
  截止时点之前最后一根完整 1m 子 K 线。

## 12. Meta Model Gate

Meta 模型不属于软件 MVP 的启用条件。只有规则基线积累足量事件后，才进行：

1. 以 Setup 为样本、Triple Barrier 为标签构建时间序列数据集。
2. 先 Logistic，再与 LightGBM 对比。
3. Walk-forward 内完成训练、特征选择、阈值选择和概率校准。
4. 用 Brier Score、Calibration Curve、Log Loss 和交易指标共同评估。
5. 只有 Baseline + Meta 在多数 OOS Fold 稳定优于 Baseline 才启用。

否则保持 `model_version=null`。

## 13. 执行层与 Agent 安全边界

执行层使用四种互斥模式：

```text
disabled  不读取密钥，任何提交/撤单/平仓都会拒绝
paper     只写 SQLite 审计记录
testnet   只连接 Binance Futures Testnet
live      连接真实账户，但还需额外硬门槛
```

默认值必须始终是：

```toml
mode = "disabled"
auto_execute = false
allow_live = false
```

入场工作流：`ACTIVE Signal → PREPARED Plan → explicit hash confirmation → Entry Order → Reconcile → Stop/TP`。计划只在短时间内有效，哈希覆盖 Signal、方向、数量、价格、止损、止盈、名义本金、杠杆、模式和到期时间。交易所过滤器缺失时拒绝生成数量，不能自行猜测 tick/step。

硬门槛包括：

- 当前模式与计划模式一致；密钥只来自对应环境变量。
- LIVE 同时要求 `allow_live=true`、`VALIDATED_FORWARD` 和固定环境确认短语。
- 自动执行同时要求 `auto_execute=true`、固定自动执行短语和 `VALIDATED_FORWARD`。
- ONE_WAY 持仓模式、名义本金、最大 5x 执行杠杆、单仓、内部/交易所当日已实现亏损上限。
- 成交后必须放置 STOP_MARKET 与 TAKE_PROFIT_MARKET；保护单异常时立即发送 `reduceOnly` MARKET 退出并记录 `FAILSAFE_CLOSED`。
- 手动平仓也采用“预览 Close Plan → 回传完整哈希 → reduceOnly MARKET”两步流程。

签名客户端封装 leverage、margin type、order、test order、query/cancel order、position、income 和 conditional algo order。当前接口依据 Binance USDⓈ-M REST 契约实现，但在用于真实资金前仍必须在 Testnet 做契约测试和小额故障演练。

Agent 默认只调用扫描、读取、解释、决策、绩效和健康检查。只有用户明确提出某个订单动作时，才能依次调用 `execution-status`、计划生成、计划提交、对账、撤单或平仓。Agent 不能改 execution 配置、密钥或风险上限；必须原样保留 Direction、Entry、SL、TP、RR、仓位和哈希；`WAIT`、过期信号或保护失败不得被改写为可入场。

Custom Bot Webhook 仍只做单向推送。飞书按钮不得直接连接执行端点。REST API 当前没有用户认证，必须只绑定可信本机或置于强认证反向代理后，执行模式启用时尤其不得直接暴露公网。

## 14. 里程碑

### M0：可运行软件 MVP

数据、因果特征、Regime、两类 Setup、Risk、Signal、SQLite、回测、CLI/API、测试。

### M1：历史研究与报告

下载并校验 1m/15m/1H/4H 与衍生品历史数据，运行 Walk-forward、按分组消融、参数扰动、成本压力和 Monte Carlo；分别报告“增加因子前/后”的交易数、胜率、期望 R、Profit Factor、最大回撤和稳定性，禁止只挑胜率更高的结果。

### M2：Meta Filter（有条件）

仅在基线样本足够时进行，未改善则删除。

### M3：实时 Shadow

稳定运行 30–60 天，监控数据缺口、信号频率和回测偏差。

### M4：交互与部署

先在 `paper` 和 `testnet` 完成重复提交、部分成交、保护单失败、断网恢复、撤单和平仓演练；之后再评估 WebSocket、Nautilus Adapter、飞书应用回调、MCP 和生产监控。LIVE 仍不得因软件完成而自动启用。

## 15. 当前项目验收结论模板

软件可以被标记为：

```text
IMPLEMENTED_MVP
```

策略只能被标记为：

```text
EXPERIMENTAL / LOW_SAMPLE_CONFIDENCE / VALIDATED_OOS / VALIDATED_FORWARD
```

二者必须分别报告。这样可以避免“代码能运行”被误解为“量化算法已经证明能够盈利”。
