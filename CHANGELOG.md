# Changelog

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
