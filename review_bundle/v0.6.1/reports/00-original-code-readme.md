# BTC Quant Agent v0.5

面向 BTCUSDT 永续合约的离线研究与数据验证项目。当前通用研究入口只有
C-lite 接入的正式 P5/P6 工作流（`CURRENT_FORMAL_V043`）。测试通过不代表策略有效，
R01 只减少仓库表面，不改变经济语义、科学结论或资格门槛。

## 正式研究入口

安装后，三个命令使用同一正式 facade，必须提供显式版本化 job 和输出目录：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,research]'

quantctl backtest --job /explicit/path/job.json --output /explicit/path/results
quantctl research --job /explicit/path/job.json --output /explicit/path/results
quantctl replay --job /explicit/path/job.json --output /explicit/path/results
python tools/run_formal_research.py --job /explicit/path/job.json --output /explicit/path/results
```

`job.json` 必须满足现有 `FormalResearchJobSpec.load` 的严格版本化 schema：
显式协议、comparison、dataset evidence、engine、可获得且完整收盘的 candles、
signals、decision inputs、eligible opportunities、funding events 和 observation time。
不会自动从 CSV 猜测协议、生成资格证据或启用默认运行服务／SQLite。
同一 artifact 路径已有不一致内容时拒绝覆盖。

可选 `--registry /explicit/path/registry.json` 只接受现有权威 P5 registry；
只有显式 `--record-decision` 才请求记录经验证的决定。
`NOT_TESTABLE` 不会被转换成通过，注册证据不等于资格晋升。

旧 `legacy-backtest`、`legacy-research`、`legacy-replay` CLI 和已失去当前依赖的历史
研究／symbolic runner 已移除。旧 R 结果、历史标签及只读 performance 仍只是诊断，
不能代替正式 ledger、冷重放或 P5/P6 资格证据。保留的兼容原语不是新的研究入口。

## 科学与执行边界

- H39 是独立、冻结且受保护的实验；协议、blindness、freeze 和一次性门槛保持不变。
  R01 不运行其验证／解盲工作流，也不修改相关证据。
- Final Holdout 保持 sealed；不得读取结果、解封、迁移或用于研究选择。
- Alpha 搜索／调参未启动，R02 未启动。
- 执行默认 `DISABLED`；`auto_execute=false`、`allow_live=false`。
  研究运行不激活 live、testnet、paper 或 shadow-trading。

```toml
[execution]
mode = "disabled"
auto_execute = false
allow_live = false
```

配置入口是 `configs/default.toml`。敏感信息仅通过环境变量提供，不写入配置、
数据库、报告或命令行。保留的执行接口仍受原有独立安全门槛约束。

## 独立数据与运行接口

Forward derivatives、opportunity 和 microstructure 继续使用冻结配置／registry 链；
数据可靠性不构成 Alpha 或执行授权。下列状态命令与正式离线研究分离：

```bash
quantctl derivatives status
quantctl opportunity-forward status
quantctl microstructure-forward status
quantctl forward-evidence health
quantctl research-registry validate
quantctl execution status
quantctl --help
```

运行服务可能打开其显式 operational stores；不要将状态命令与无服务副作用的
正式 job 命令混淆。API 保留原有鉴权与默认本机绑定；勿公开暴露执行接口。

## 验证与当前文档

```bash
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src skill-template/scripts
git diff --check
```

GitHub CI 覆盖 Python 3.11、3.12、3.13；验收必须绑定 exact HEAD。
仓库分析工具 `python tools/catalog_surfaces.py` 默认输出工程 JSON 到 stdout，
不会打开 operational stores 或 sealed evidence，也不是资格权威。

当前路径与所有权见 [CURRENT_ARCHITECTURE.md](docs/CURRENT_ARCHITECTURE.md)。
Forward 运维见 [FORWARD_DERIVATIVES_OPERATIONS.md](docs/FORWARD_DERIVATIVES_OPERATIONS.md)
和 [LINUX_VPS_MIGRATION_RUNBOOK.md](docs/LINUX_VPS_MIGRATION_RUNBOOK.md)。

历史实验叙述保存在 Git history；任务 prompts、reviews 和 R01 实现报告位于
`v0.5-refactor-docs`，不放回活动代码分支。实现报告不等于独立验收。
