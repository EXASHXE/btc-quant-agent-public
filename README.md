# BTC Quant Agent v0.3.13

一个面向 `BTCUSDT` USDⓈ-M 永续合约的低频量化研究项目。v0.3.13 启动真实、无方向的 TP/BR Opportunity Forward Shadow，并增强 Derivatives PIT collector 的网络诊断与可靠性账本；正常 Runtime 仍由 Research Registry 限制为 `OPPORTUNITY_ONLY`，不能输出 actionable `LONG/SHORT`。执行默认 `disabled`，默认配置不会读取密钥或发送订单。

> 风险提示：这是研究与 Shadow Trading 工具，不是收益承诺。默认策略状态为 `EXPERIMENTAL`。在完成足量样本外验证与 30–60 天前向观察前，不应据此进行真实高杠杆交易。

## 本阶段交付边界

- 因果化 4H 宏观门槛、1H Regime 与 15m 入场逻辑
- Trend Pullback 与 Breakout Retest 两类候选
- 结构失效止损、目标位、净盈亏比和风险仓位
- Binance 公开 REST 数据：K 线、Funding、OI 变化、Taker Flow、基差、多空比和订单簿
- 五组正交因子评分：趋势结构、动量、参与度、衍生品、波动与流动性
- SQLite 信号/用户决策/Shadow 结果持久化
- 1m 子 K 线保守成交与 Stop/TP 解析
- CLI、可选 FastAPI、飞书单向推送适配器
- 薄层 Agent Skill 模板
- `disabled / paper / testnet / live` 执行模式、短时计划哈希和完整审计表
- LIMIT/MARKET 入场、成交对账、条件保护单、撤单与 `reduceOnly` 平仓接口
- 因果、风控、状态与回测单元测试
- 历史衍生品 backward as-of 对齐、逐字段陈旧清洗和可复现快照
- 信号 TTL 锚定决策数据时间，15m 新收盘后动态失效检查
- Research / Strategy / Feature Registry 与 fail-closed Runtime Gate
- append-only SQLite 前向衍生品 PIT archive、审计、导出和 systemd user timer

Meta Model、NautilusTrader 适配和飞书交互回调被保留为后续里程碑。没有校准模型时，`p_win` 和 `expected_r` 必须为 `null`，避免把规则评分冒充统计胜率。

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

quantctl health
quantctl scan BTCUSDT
quantctl signal latest
pytest -q
ruff check .
mypy
```

`scan` 读取 Binance 公开市场数据。`OPPORTUNITY_ONLY` 中的 `legacy_pattern_side` 仅是研究元数据，Agent/API/Execution 不得把它恢复为方向。若所在网络无法访问 Binance，先使用 CSV/Parquet 数据做离线回放；程序不会为缺失数据生成信号。

## 常用命令

```bash
quantctl scan BTCUSDT
quantctl signal latest
quantctl signal show <signal_id>
quantctl decision <signal_id> accept --entry 77450
quantctl performance --days 30
quantctl health
quantctl execution status
quantctl research-registry validate
quantctl research-registry status
quantctl derivatives collect-once
quantctl derivatives status
quantctl derivatives audit
quantctl derivatives export
quantctl daemon --once
quantctl download ./data/BTCUSDT-1m.csv --start-ms 1754006400000 --end-ms 1756684800000 --interval 1m
quantctl backtest ./data/BTCUSDT-1m.csv
quantctl backtest ./data/BTCUSDT-1m.csv --derivatives ./data/BTCUSDT-derivatives.csv
quantctl collect-derivatives --path ./data/BTCUSDT-derivatives.csv
quantctl replay ./data/BTCUSDT-1m.csv --start-ms 1609459200000 --end-ms 1612137600000
quantctl research ./data/BTCUSDT-1m.csv \
  --data-manifest ./data/BTCUSDT-1m.csv.manifest.json \
  --derivatives ./data/BTCUSDT-derivatives.csv \
  --funding-events ./data/BTCUSDT-funding.csv

# 正式 v0.3.0 数据与开发集研究（不会读取 holdout 策略结果）
quantctl build-official-dataset --root ./data/research/BTCUSDT \
  --start 2021-01-01 --end-exclusive 2026-08-01
quantctl audit-official-timeframes --root ./data/research/BTCUSDT
python tools/run_formal_research.py --root ./data/research/BTCUSDT \
  --output ./artifacts/research/<unique_run_id>
```

执行工作流（默认配置的第二步会被拒绝）：

```bash
quantctl execution plan-entry <signal_id>
quantctl execution submit <plan_id> --confirm <完整plan_hash>
quantctl execution reconcile <plan_id>
quantctl execution cancel <plan_id> --confirm <完整plan_hash>
quantctl execution plan-close --symbol BTCUSDT
quantctl execution submit-close <close_plan_id> --confirm <完整plan_hash>
```

可选 API：

```bash
pip install -e '.[api]'
uvicorn btc_quant_agent.api:app --host 127.0.0.1 --port 8787
```

使用 Docker 时，`docker compose up -d --build` 会启动扫描进程和仅绑定本机
`127.0.0.1:8787` 的 API。将 Agent 环境中的 `BTC_QUANT_API_URL` 设置为
`http://127.0.0.1:8787`，技能即可通过 HTTP 调用 QuantCore；不要把未鉴权 API
直接暴露到公网。

## 配置

默认配置在 `configs/default.toml`。敏感信息只通过环境变量传入：

```bash
export BTC_QUANT_DB_PATH=./var/quant.db
export BTC_QUANT_API_TOKEN='generate-a-long-random-token'
export FEISHU_WEBHOOK_URL='https://open.feishu.cn/open-apis/bot/v2/hook/...'
export FEISHU_WEBHOOK_SECRET='...'
```

默认配置：

```toml
[execution]
mode = "disabled"
auto_execute = false
allow_live = false
```

只有切换到 `testnet` 或 `live` 才读取对应环境变量。不要把密钥写进 TOML、数据库或命令行：

```bash
export BINANCE_TESTNET_API_KEY='...'
export BINANCE_TESTNET_API_SECRET='...'
# live 另用 BINANCE_API_KEY / BINANCE_API_SECRET
```

`live` 还要求 `allow_live=true`、`VALIDATED_FORWARD` 信号和
`BTC_QUANT_LIVE_CONFIRM=I_UNDERSTAND_REAL_ORDERS`。自动执行另要求
`auto_execute=true` 与 `BTC_QUANT_AUTO_EXECUTE_CONFIRM=ENABLE_AUTO_EXECUTION`。
默认 5x 执行上限独立于信号中 20x 的展示保证金。

风险仓位使用完整计划损失率反推：止损距离、双边 taker fee、双边滑点和候选方向的
不利 Funding 合计后不得超过 `account_equity_usdt × risk_per_trade`。若计算仓位低于
`min_notional_usdt`，系统直接返回 `WAIT`，不会为满足交易所最小名义本金而超出风险预算。

REST API 的所有路由都要求 `Authorization: Bearer <BTC_QUANT_API_TOKEN>`，并继续默认只绑定可信本机；不要把执行 API 直接暴露到公网。

## 设计与验证

优化后的完整设计、精确规则和验收边界见 `docs/OPTIMIZED_DESIGN.md`。核心原则是：

1. 只使用已经收盘且在决策时刻可获得的数据。
2. 同一数据、配置和版本必须生成相同输出。
3. 正常服务显式使用 `RUNTIME_GATED`；冻结研究显式使用 `LEGACY_RESEARCH_V022` 和 `configs/frozen/v0.2.2.toml`。
4. `WAIT` 是默认状态；数据失效时强制 `NO_SIGNAL`。
5. 代码完成不等于策略有效；`VALIDATED` 必须由样本外证据取得。
6. 增加指标不能证明胜率提高；必须用时间序列 Walk-forward、消融和成本压力测试验证。

v0.2.1 只完成量化正确性修复，仍保留 `EXPERIMENTAL`。Pivot 序列/BOS/CHOCH、供需区、
Funding 分位与更完整 OI 状态机属于 v0.2.2；Walk-forward、消融、成本压力和 Bootstrap
研究报告属于 v0.3.0，不能因本版本测试通过而视为已验证盈利能力。

正式 `research` 运行需要 `pip install -e '.[research]'` 以写入 Parquet。每个 run 会在
`artifacts/research/<run_id>/` 保存报告、交易、权益曲线、冻结配置、数据清单和 Git/config/
dataset/random-seed provenance。v0.3.0 的冻结 Run 0 只有 13 笔 filled trades，结论为
`INCONCLUSIVE_LOW_SAMPLE` / `INSUFFICIENT_SAMPLE_FOR_OPTIMIZATION`；未运行参数网格，未打开
最终 holdout。没有真实 point-in-time derivatives 时，baseline 会显式关闭
derivatives 与 order-book 分组，相关消融不会被当作有效多年证据。

v0.3.11 的 Registry、Runtime 对齐和前向数据运维见 `docs/RESEARCH_REGISTRY.md`、
`docs/V0.3.11_RUNTIME_ALIGNMENT_FORWARD_DATA_REPORT.md` 与
`docs/FORWARD_DERIVATIVES_OPERATIONS.md`。策略状态继续为 `EXPERIMENTAL`，这些研究结果不构成交易建议。
