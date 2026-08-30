# Changelog

## 0.3.11 - Runtime Alignment, Registry, Forward PIT Foundation

- 将正常 Runtime 默认切换为 Registry-gated 模式；TP/BR 保留为 `OPPORTUNITY_ONLY`，不再生成 actionable `LONG/SHORT`。
- 新增机器可读 Research Registry、validator/status/show CLI，以及 Execution 的前置 fail-closed Registry Gate。
- 旧 v0.2.2 研究仅可通过 `LEGACY_RESEARCH_V022` 与冻结配置显式重放。
- 新增 WAL SQLite append-only derivatives store、collection run ledger、status/audit/export 与 UTC 15 分钟 systemd user timer。
- 修正 PIT `observed_at_ms` 为所有已尝试 endpoint 处理完成后的本地可用时间，并保留各字段 source timestamp。
- Final Holdout 保持 `SEALED`，执行保持 `disabled`；本版本没有 Alpha、Candidate、Paper、Testnet 或 Live 声明。

## 0.3.0 - Formal Research, Inconclusive Low Sample

- 构建并校验 Binance 官方 BTCUSDT USD-M 永续 1m、funding 与 mark-price 研究数据；
  2,934,720 根 K 线零缺失、零重复、零合成。
- 增加 UTC 开发/holdout 硬边界、候选配置/提交/标签证书及 exactly-once holdout 门。
- 修复月度 mark-price 缺日，使用带官方 SHA-256 的 daily 归档回填；高周期抽样 OHLC
  全部一致，并记录 Binance 1m/高周期成交活动差异。
- A/B/C 消融保留共同硬安全核；成本压力只重定价冻结成交，不改变策略决策。
- 优化滚动特征计算并增加同一不可变数据集的跨消融缓存，附完整序列等价性测试。
- 冻结 Run 0 在开发集只有 13 笔 filled trades，expectancy `-0.1035R`、PF `0.8627`；
  结论为 `INSUFFICIENT_SAMPLE_FOR_OPTIMIZATION`。
- 按预注册停止规则跳过参数研究、候选标签和最终 holdout；策略仍为 `EXPERIMENTAL`，
  执行仍默认 `disabled`。

## 0.2.2 - Research Hardening

- 将回测改为逐根 1m 事件推进，统一 pending、fill、失效、TTL、cooldown、fingerprint 与持仓生命周期。
- 用有界 Live 等价历史窗口和 bisect as-of 查询移除主循环二次复杂度。
- Funding 改为跨 settlement timestamp 才发生的现金流，并在风险端加入事件数压力预算。
- 新增 point-in-time derivatives collector、checksum/coverage/gap data manifest，OrderBook 默认关闭。
- 修复 SQLite connection leak；执行前拒绝 DEGRADED、刷新信号并按方向取整后重算风险/RR。
- API 全路由增加 Bearer token；拆分 `pattern_score` 与 `factor_score` 并兼容旧数据库 JSON。
- 新增 replay、ablation、walk-forward、holdout、stability、cost stress、bootstrap 与可复现研究产物。
- 策略状态仍为 `EXPERIMENTAL`，执行仍默认 `disabled`，不包含 Edge 或收益声明。

## 0.2.1 - Quant Correctness Fix

- 按止损、双边费用、双边滑点和不利 Funding 的完整损失率计算仓位；增加最小名义本金拒绝。
- 新增 `HistoricalDerivativeStore`、CSV 契约、backward as-of join 和逐字段陈旧清洗。
- 修复 Trend Pullback 仅检查 EMA 区域单边上界的问题。
- Funding 改为方向/拥挤度上下文评分；OI 改为价格 × OI 联合解释。
- TTL 改为锚定决策数据时间，并启用 `max_data_age_seconds` 与 `max_signal_age_bars`。
- 新增 ACTIVE 信号动态失效、机器可读原因码及已推送信号的飞书失效通知。
- 修复 TIMEOUT 使用截止时间后第一根子 K 线的问题；按 Setup 配置 12h/8h 最大持仓。
- `/performance` 支持 `days` 查询参数；读取信号前先执行过期检查。
- 增加因果、确定性、策略边界、风险预算、历史衍生品、API 与回测边界测试。
- 保持执行默认 `disabled`、`auto_execute=false`、`allow_live=false`，策略状态保持
  `EXPERIMENTAL`。

## 0.2.0

- 实现 4H Macro、1H Regime、15m Setup、五组因子、Shadow Trading 和受控执行适配器。
