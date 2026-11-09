# Q0C 离线交接 — V070-Q0C-FEISHU-DURABLE-ALERT-OFFLINE-01

交付状态：**等待 Controller 0-C 验收；Worker 未自验收。** 全部 provider 结果、价格、事件和延迟数据均来自合成测试。没有真实飞书消息、真实 webhook、私有凭据、行情接口、交易/持仓/账户动作、定时任务或生产部署。实现不导入 HTTP/socket 客户端，也不提供真实传输入口。

## 文件与运行

- `Q0C_EVENT_CONTRACT.json`：JSON Schema Draft 2020-12，契约 `Q0C_ALERT_EVENT_V1`，独立适配未来 `S1_INTRADAY_MTF_V2`，无策略代码依赖。
- `alerts/`：纯 Python 标准库包；SQLite durable outbox、严格离线准入、卡片、签名选项、内存 provider mock。
- `tests/`：`unittest`、合成事件和可控时钟；套件主动阻止 socket 创建、DNS、连接和 UDP，连 loopback 也不发送。
- `examples/`：六种事件及对应 JSON 卡片、一个公开合成签名示例。`dashboard.invalid` 为保留测试域名，不会打开。
- `Q0C_VALIDATION.json`：离线验证结果和合成延迟统计。
- `Q0C_DIGEST_MANIFEST.json`：SHA-256 与字节数，仅覆盖本次交付，不包含控制器/worker 原文件、缓存或清单本身。

在本目录运行 `python3 -m unittest -q`。已验证 Python 3.12.3，无第三方依赖，无安装/网络步骤。SQLite 数据库路径由调用方提供，调用方必须关闭 dispatcher 后再重启。主程序无循环、后台线程或自动调度。

最小离线用法（示例时间固定在合成时钟，不能冒充当前 Source）：

```python
import json
from alerts import Dispatcher, MockFeishuTransport
from tests.fixtures import FakeClock

clock = FakeClock()
dispatcher = Dispatcher("outbox.sqlite3", MockFeishuTransport(), clock=clock)
with open("examples/mock_entry_ready.event.json", encoding="utf-8") as source:
    key = dispatcher.enqueue(json.load(source))
dispatcher.dispatch_one()
print(dispatcher.get(key)["state"])  # PROVIDER_ACCEPTED，仅 MOCK_PROVIDER
dispatcher.close()
```

## 输入与准入边界

所有时间是 UTC epoch 秒，与主机时区无关。`eligible_at` 是生产者声称的可通知时点，`expires_at` 是本次通知的硬 TTL；`candidate_expires_at` 是候选交易计划失效时点。Schema 拒绝未知字段、缺失字段、NaN、无限值和错误类型；运行时使用 schema 实际采用的受限关键字及语义校验，不声称实现通用 JSON Schema 引擎。

候选事件必须携带 symbol、LONG/SHORT、4H regime、1H/15m 完成和有效性、source 观测/可信接收时间、当前 quote/价格/路径门禁、entry area、hard stop、1–3 个有依据及权重的 TP、planned after-cost R 与 fee/slippage/entry-reference/最低 R/模型假设、episode 与 transition ID、失效条件/原因和候选 expiry、5/10 分钟人类响应假设、数据准入、UNKNOWN/VETO、双 synthetic/test 标记和 HTTPS dashboard URL。URL 禁止内嵌凭据、query、fragment。系统降级使用独立精简 schema，不虚构候选入场计划。

`ENTRY_READY` 要求完成的有效 1H/15m bar、准入的 4H regime、GOOD source、可信且新鲜的 quote，当前价格位于 entry area，stop 在区域外，TP 位于盈利方向且顺序合法、权重合计 1。planned 和延迟 R 均不得夸大按模型复算的 R，且满足声明的最低值：

`R = (加权方向性目标收益 − entry × (round-trip fee bps + slippage bps)/10000) / (abs(entry − stop) + 同一成本)`。

5/10 分钟门禁还要求两时点最坏 entry 均在区域内，随延迟按 LONG/SHORT 的不利方向保守变化，评估新鲜，候选与模型有效期覆盖**实际 dispatch 时刻起至少 600 秒**。这是条件化的合成模型假设，不保证未来价格、流动性或成交。WATCH/SETUP_READY 优先级较低，允许尚未完成的后续阶段；仍需完整计划快照和当前 quote 门禁。

默认 source 最大年龄 60 秒、quote 30 秒、eligible signal 120 秒，1H/15m bar 最大年龄分别 3600/900 秒；入队与每次尝试前均重新校验。事件不可修改：刷新价格/时间/计划需要新的真实 transition，而不是覆写旧幂等键。UNKNOWN 不代表账户获批；VETO 阻止 ENTRY/WATCH/SETUP，允许终止候选或系统降级通知。没有读取账户或解释为下单许可的路径。

`INVALIDATED`/`EXPIRED` 按 episode 定位，保留历史市场快照，要求新鲜可信的终止事件 source receipt；历史 quote 变旧不应阻止撤销提醒。EXPIRED 必须确实超过 candidate expiry，通知 TTL 仍需有效。终止原子取消该 episode 的 QUEUED 和可重试 FAILED 入场类提醒，阻止迟到的新入场；既有 ACCEPTED/UNKNOWN 证据不改写。不同事件种类和 transition 独立去重。

source trusted/admitted 等是**离线 fixture 断言**，不是来源认证。任何真实事件（synthetic/test 为 false）或真实 channel 均被拒绝；即使提供凭据也不会启用真实发送。终止事件需要未来 adapter 主动提交，本包不运行行情监控或自动推断策略失效。

## Durable outbox 与证据

SQLite `journal_mode=WAL`、`synchronous=FULL`、显式事务。状态严格区分：

| 状态 | 含义与后续 |
| --- | --- |
| QUEUED | 已持久化、未提交；可因 expiry/失效被取消为 FAILED |
| ATTEMPTED | 提交前已提交数据库事务和 append-only audit；崩溃恢复为 UNKNOWN_DELIVERY |
| PROVIDER_ACCEPTED | mock 独立返回 HTTP 200 且 provider code 为**整数 0**；保存响应 SHA-256、HTTP/code、观察时间及 MOCK_PROVIDER 来源 |
| FAILED | 明确拒绝或本地准入失败；只有 mock 明确证明未投递/未提交且未越界时可重试 |
| UNKNOWN_DELIVERY | timeout、提交后响应丢失、含糊 HTTP/body、重启遗留 ATTEMPTED；永不自动重放 |

接受证据不等于人已读、已确认、已行动或交易成功。HTTP 200 本身、非零/字符串/bool code、异常和签名失败均不会产生 ACCEPTED。mock 的 `proven_not_delivered=True` 是可信的测试注入证据；真实适配器不能凭猜测将 429/5xx/超时标为未投递。普通异常文本和 provider msg 不写入日志/错误字段；接受时仅保存响应摘要，避免凭据进入异常输出。

幂等键是 `[strategy, episode_id, event_type, transition_id, channel, contract_version]` 规范 JSON 的 SHA-256（version 指契约版本）；同键同 payload 重复返回原记录，跨重启/过期仍去重；同键不同 payload 拒绝，不悄悄更新。SQLite 中保留原 payload。不要删除 DB、状态或 audit 来“重试”；UNKNOWN 必须经未来另行设计的人工/provider 核对流程处理，本实现无重放按钮。

默认最大 3 次，明确未投递时指数退避 5/10 秒，受 expiry、新鲜度、每 channel 30 秒 cooldown、60 秒最多 3 次尝试限制；重试与失败尝试也计入限流。SYSTEM_DEGRADED 另有同 channel 300 秒 cooldown，不占用 ENTRY_READY 的优先级。政策写入 DB，重启拒绝更换政策以绕过限制。所有延迟均由调用方下次显式调用处理，无 sleep/调度任务。

时钟用 wall 与 monotonic 比较；默认偏差 >5 秒则持久隔离，重启也保持隔离；停机期间倒退通过 high-water 检出。停机期间前跳不能凭 monotonic 推断，但旧队列按 TTL/年龄失败。跳变发生于发送期间时仍保留实际 provider 证据，隔离后不输出延迟 P95。隔离需操作者核对可靠 UTC 和现存投递证据，保留 DB/幂等历史后另行审查修复；本交付不提供自动清除或绕过隔离的方法。

## 签名、反馈与统计

`alerts.card.Secret(getter)` 由受保护注入函数取值，repr 脱敏，不读取环境/私有文件、不写入 DB/卡片。可选签名采用本地 Feishu 形状的 timestamp 与 HMAC-SHA256 构造；测试固定向量经本地 OpenSSL 独立复算。**未与真实飞书、有效 webhook、官方当前行为或回调联调验证**，不能当作上线凭据验证。公开样例使用非凭据的固定 fixture，不包含真实 secret。

反馈只能显式写入 `SYNTHETIC_TEST`，且关联已有 ACCEPTED 的 outbox ID；允许 ACKNOWLEDGED/MISSED/TOO_LATE/ACTIONABLE/NOT_ACTIONABLE，一次反馈幂等，相互矛盾的二次反馈拒绝。没有 HTTP 回调端点、自动已读或真实反馈认证。MISSED 等仍是显式反馈标签，不据此推断读过消息。

`metrics()` 分别报告各状态、去重 admission 总数、实际尝试过的独立通知分母、provider accepted 分子、含重试的总尝试数、feedback 分子/accepted 分母。准入拒绝未进入 outbox，不计 admitted；重复输入不扩大分母。反馈分母包括全部已接受通知类型，不等于入场交易机会分母；若未来需候选级转化率，必须单独定义并取得完整真实反馈。

**FUTURE SLO：eligible signal → provider ACCEPTED 的 P95 ≤120 秒。** `synthetic_latency()` 只统计有接受证据的 ENTRY_READY，nearest-rank P95，无样本返回 null；必须同时看失败/未知与接受覆盖率，不能用条件成功样本宣称整体达标。20 个无等待的可控时钟合成样本（1–20 秒）P95=19 秒；这是模拟测量，不是真实网络、生产负载、人类响应或现网 SLO 达成证据。

## 上线前置条件（未授权、未实施）

1. Owner 明确飞书目的地/群/接收对象，确认允许通知的内容与环境；真实 webhook 与签名 secret 通过受保护注入，禁止进入代码、卡片、日志或报告。
2. 在单独受控范围内验证当前 provider API/code、签名时间窗、secret/目的地与测试接收；若接入反馈回调，另验证回调签名/令牌/挑战、时间窗、去重、防重放及接收人授权。当前包只有本地 mock，不能完成这些检查。
3. 完成真实且当前的 Source admission：来源身份与可信时间、已闭合 bar、quote/路径与数据质量、策略快照/过期/失效、费用滑点及人类延迟模型；不能把 synthetic 标记改成 false 便视为可信。
4. 取得**另行明确范围的 Owner live-notification 授权**：接收对象、channel、时间窗口/到期、消息类型、最大数量/频率、事故停止和 UNKNOWN 人工核对流程；凭据存在不等于通知权限，离线任务授权不覆盖 live。
5. 由 Controller 0-C 审核本交付，再另行实现/评审真实 transport 与权限校验，验证单消费者、持久存储/备份、时钟和 provider 拒绝/未知投递语义。调度、部署、真实网络接收试验均需单独授权；本交付未注册任何 cron/automation。

本任务无可用 Git 仓库元数据（`git status` 返回非 Git 仓库），因此不报告虚构 commit SHA。交付完整性以摘要清单核对，最终验收权保留 Controller 0-C。
