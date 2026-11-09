# Q0B 离线交付 — 待 Controller 0-C 验收

任务：`V070-Q0B-S1-INTRADAY-MTF-V2-01`。版本：`S1_INTRADAY_MTF_V2`。
本交付不自验收，不主张正 alpha，不构成实盘执行许可。没有网络实现、市场账户访问、飞书或告警发送；没有使用受保护历史做调参或评估。

## 文件与运行

- `Q0B_CONTRACT.json`：规范、固定方法、时点规则、成本和容量假设。
- `q0b/schema.py`、`q0b/card.schema.json`：独立版本的数据模型与输出 schema。
- `q0b/source.py`：1H/15m 及相关周期的闭合、身份、因果、缺口、修订与隔离检查。
- `q0b/transport.py`、`q0b/transport.schema.json`：纯 fixture 解码与收据 schema；不负责获取数据或签发时钟资格。
- `q0b/planner.py`：3/10/50 品种预算、有限回补、固定分母、单品种隔离和全局 veto；仅允许 `OfflineStub`。
- `q0b/strategy.py`：独立编译器、内存状态机和 `CONTROL_1H_ONLY` 配对比较。
- `tests/q0b/`：pytest 证明；测试时封锁 socket、连接及 DNS。
- `artifacts/synthetic_cards.json`：涵盖全部八种状态的合成卡片。
- `artifacts/paired_comparison.json`：3 品种、两个预声明复核点的配对决策；未来结果与 realized R 均为空。
- `artifacts/collector_plans.json`：3 与 10 品种的确定性 bootstrap 请求计划。
- `artifacts/readonly_baseline.json`：186 个原有本地文件的 SHA256 基线，含原 S1、C frozen、Strict/O 与 `pyproject.toml`。
- `SHA256SUMS`：新增代码、测试、规范、样例及交付说明的 SHA256 清单。

在当前工作区根目录运行；不需要导入或安装原平台。运行时仅用 Python 标准库；测试依赖列于 `requirements-q0b-test.txt`，当前环境已具备，无安装操作。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m q0b --output artifacts
PYTHONDONTWRITEBYTECODE=1 pytest -q
ruff check q0b tests/q0b
sha256sum -c SHA256SUMS
```

## 行为与边界

1H 已完成的恢复/拒绝形态先登记 `WATCH`，即使没有 15m 数据也成立。方向与结构几何来自 1H；止损位于已确认结构之外，加 `0.20 × ATR14`。入场区固定为 setup close ± `0.15 × ATR14`。TP1、TP2 必须来自已可观察的 1H/4H 确认 pivot；仅有两个层级时不补造 TP3。采用一根左侧、一根完整右侧 bar 确认 pivot。

15m 必须匹配已登记且仍有效的 1H 候选，完成对固定 1H close 的恢复/拒绝，才可尝试升级。只考虑最新的新增确认；确认在尝试中消耗，即使随后拒绝入场也不重放。首次收到已有 15m 的快照仍先登记 WATCH。5m 或新鲜 venue quote 只决定价格可操作性和拒绝条件。

1D 逆势允许，但附风险警告并将纸面风险预算减半；4H 反向保持 WATCH 并阻止 READY，RANGE 可允许。每次准入复核都刷新当前 1D/4H 背景，包括迟到的闭合收据；1H 入场区、止损、目标及候选 ID 保持固定。

入场寿命是 setup close 后 45 分钟，独立于从假设成交开始的 2–12 小时持有寿命。可在构造策略前明确声明更长、至多 24 小时的计划扩展；没有成交时不生成持有到期时间。READY 复核要求剩余窗口覆盖声明的 5–10 分钟反应时间（默认 10 分钟），并同时受入场过期和本次 15m 确认后 15 分钟限制。到用户响应时仍须重新检查源、入场区、止损与目标；不保证未来窗口内价格继续合适。

触及止损或 TP1 会在入场前作废候选；同 bar 双触及按止损先行拒绝，不推造行情顺序。过期、作废不能由相同 1H setup 复活。旧 READY 不缓存到下一次复核；重复 15m 回到 WATCH。新 1H setup 必须重新登记。进程重启也从 WATCH 开始，没有持久化 READY 恢复路径。

`CONTROL_1H_ONLY` 使用相同快照、1H 几何、风险、成本、过期规则及可操作性检查，省去 15m 方向过滤；它的路径拒绝只读 1H/5m/quote。每个 1H 信号只尝试一次。配对输出只比较决策资格，没有编造填单、胜率、收益或 realized R。

## 源、成本与采集约束

所有示例价格均为人为构造，时点为 2030 年的离线虚拟时钟。禁止区间为 UTC `[2024-01-01, 2027-01-01)`；其中 `[2026-02-01, 2026-08-01)` 单列 holdout 原因。即使标称 synthetic，落入这些区间的请求或 bar 也拒绝。测试仅计算区间边界，不加载历史样本。

源要求 exchange-aligned 半开区间，交易所 inclusive closeTime 必须等于 exclusive end−1；end 不晚于收据和复核时刻的 exchange lower bound。`received ≤ available ≤ review`，检查完整 OHLCV、每品种/周期身份、连续性、请求两端、重复、修订、未来访问及水位回退。每批至多 64 根，保留每 stream 最近 64 个身份指纹；跨快照缺口也拒绝。后到的同内容收据不视为修订。没有用本地 wall clock 替代 Strict；fixture proof 只能用于离线合成证明。

单品种源错误会隔离该品种；共享源、时钟资格或 as-of 回退引发全局锁存 veto。恢复需外部重核资格并丢弃旧 engine；不自动恢复旧候选。所有输入先整体校验再计算特征，失败不部分提交指纹。

卡片分列 gross planned R、conservative/stress after-cost planned R 和空的 realized R。收费、spread、双边滑点、向上取整的完整 adverse funding 窗口均计入，计划扩展按全时长收费。纸面尺寸受风险预算、notional cap 和可见盘口 10% 限制；只有 5m 时容量标 UNKNOWN。盘口容量、滑点和止损跳空仍不确定，没有账户授权或成交承诺；示例不要求达到原 S1 的 2R 门槛，新版本方法详见规范。

采集器每个周期至多规划一轮/分钟，无即时重试。Bootstrap 每周期 32 根；wire limit 64；增量最多 32 根新 bar 并重读两根重叠 bar。超过回补上限整品种隔离，不截短缺口。固定分母保留隔离、缺失与 NO_SETUP 品种。共享 endpoint 失败全局 veto，品种失败丢弃其部分结果并继续其他品种。

| 预声明 universe | bootstrap 请求数 | 总权重 | 保留 20% 后预算 |
|---|---:|---:|---|
| 3 | 20 | 23 | ≤320 请求 / ≤640 权重 |
| 10 | 62 | 72 | 同上 |
| 50 | 302 | 352 | 同上 |

Endpoint 与权重是固定离线假设，不是已验证的现行 Binance 规则；没有实际调用。未来传输集成须由 Controller 另行确认权威规则、instrument 规格、账户风险与外部已接受 Strict/O proof。解码后的 payload 仍属未准入，必须经过 `SourceLedger`；本交付未激活生产接线。

## 验证与交接

最终门禁：100 项 pytest、Ruff 和 SHA256 校验；具体执行记录见 `artifacts/validation.json`。覆盖 1H 缺 15m、确认/虚假触发、未来与未完成 bar、迟到背景、4H 冲突、日线逆势、stop/target、陈旧 5m/quote、5–10 分钟反应窗、重复 15m、过期终态、holdout 两端、容量预算、异常隔离、source 水位/修订和 1H-only control。独立只读审查已复核背景刷新和 collector 异常隔离的修复。

`src/` 及原配置均未编辑，字节保全测试也检查只读根目录的文件集合。没有访问或编辑父 O/J/L/C、strict research 或 S worktree。当前目录不具备可用 Git 元数据，因此未提交、无 commit SHA；交付身份使用 SHA256 清单。Controller 0-C 保留最终验收权，本状态为 **待验收**。
