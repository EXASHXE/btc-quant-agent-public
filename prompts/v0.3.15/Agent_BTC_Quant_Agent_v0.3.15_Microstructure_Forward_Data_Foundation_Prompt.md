# BTC Quant Agent v0.3.15 — Microstructure Forward Data Foundation

## 0. 任务定位

本轮不是新的 Alpha / Direction Feature 研究，不允许为了尽快得到可交易结论而调参，也不允许打开 Final Holdout。

v0.3.14 已完成 Forward Evidence Gate Repair：
- 正式 v0.3.14 交付结果 SHA：`4d0eb90e9cbf5d11689d3d8cf5e5c6f332344d1b`
- Evidence Epoch：`DERIVATIVES_PIT_EPOCH_V0314_001`
- 固定起点：`2026-08-31T12:30:00Z`
- Gate：30 calendar days / 2500 fully available scheduled snapshots / 每个 required field >=95% / 最大连续 failed+partial+missing slots <=4
- Opportunity Forward Campaign：`OPPORTUNITY_FORWARD_V0313_20260831T050656Z`
- Direction Engine：NONE
- Runtime maximum：OPPORTUNITY_ONLY
- Execution：DISABLED
- Candidate Freeze：NONE
- Final Holdout：SEALED

本轮目标是在不污染现有两条 Forward Evidence 的前提下：

1. 消除 v0.3.14 中仍存在的“旧 derivatives status 与新 epoch gate 两套资格口径”的 split-brain 风险；
2. 继续保证 v0.3.14 Derivatives Evidence Epoch 与 Opportunity Forward Campaign 原样运行；
3. 新建一个完全独立、只做数据积累的 BTCUSDT USD-M 微观结构 Forward 数据管线，为未来可能的 OFI / Order Book / Aggressive Flow 独立信息族准备真正 PIT 数据；
4. 本轮绝对不做该数据族的收益筛选、Direction qualification、阈值优化或 Runtime 接入。

不要把“采集了 L2/Trades”表述成“已经有 Alpha”。

---

## 1. Git / Branch 要求

从 `codex/v0.3.14-forward-evidence-gate-repair-operations-hardening` 的**最新远端 HEAD**创建：

`codex/v0.3.15-microstructure-forward-data-foundation`

注意：v0.3.14 正式研究/工程交付 SHA 是 `4d0eb90e...`；如果其后只有本 Prompt 文档 commit，应保留该 commit，并从最新远端 branch HEAD 分支。

禁止：
- merge main；
- 改写历史 commit；
- 删除旧 prompts / deliverables；
- 关闭旧 PR；
- 修改 v0.3.14 Evidence Epoch 起点或 Gate；
- 修改 v0.3.13 Opportunity Campaign 冻结参数。

完成后创建新的 PR，但不要自动 merge。

---

## 2. P0 — 消除 Forward Eligibility Split-Brain

当前 `ForwardDerivativeStore.evidence_epoch_metrics()` 已按 v0.3.14 Evidence Epoch 正确计算正式资格；但是历史 `ForwardDerivativeStore.status()` 仍保留 all-time ledger 的旧 `research_eligibility` 逻辑。旧历史 54-slot outage 会导致这个旧字段长期显示无法通过，与 `forward-evidence status` 的 active epoch 口径产生歧义。

### 2.1 必须修复

正式、唯一的 Derivatives research eligibility source of truth 必须是：

`DERIVATIVES_PIT_EPOCH_V0314_001 -> evidence_epoch_metrics()`

要求任选清晰方案实现，但必须满足：

- `quantctl derivatives status` 不得再把 all-time archive 结果展示为正式 `research_eligibility`；
- 推荐直接加载 active Evidence Epoch 并返回：
  - `active_epoch`
  - `archive_pre_epoch`
  - `research_eligibility = active_epoch.eligibility_state`
- 如果保留旧 all-time 指标，只能明确命名为 `archive_*` / `legacy_diagnostic_*`，且必须写明 `NOT_FOR_ELIGIBILITY`；
- `quantctl forward-evidence status` 与 `quantctl derivatives status` 对正式 eligibility 必须一致；
- 不允许通过删除、重标记、回填历史失败记录解决。

### 2.2 测试

至少增加：
- all-time archive 含 >4 连续失败但 active epoch 连续成功时，两种 CLI/status 对 active eligibility 口径一致；
- manual/legacy/pre-epoch 不能改善 active gate；
- missing scheduled slot 仍计入 active gap；
- frozen epoch start 不能因 status/audit 调用移动。

---

## 3. P0 — 保持 v0.3.14 Forward Evidence 不变

本轮开发期间必须继续尊重：

### Derivatives Evidence
- epoch id 不变；
- epoch start 不变；
- 15m cadence +20s 不变；
- 30d/2500/95%/max4 不变；
- manual runs 不计 eligibility；
- legacy/pre-epoch 不计 eligibility；
- retrospective backfill 不计 eligibility；
- missing invocation 仍必须作为 missing slot。

### Opportunity Forward
- campaign id 不变；
- TP/BR detector 定义不变；
- 4h/8h horizon 不变；
- matching rules 不变；
- Direction claim 仍为 NONE；
- outcome resolver 继续 append-only / idempotent；
- 不生成 Entry/SL/TP/Position/PnL。

在最终 deliverables 中报告这两条 campaign 的最新自然运行状态，但不要因为本轮开发去人工补造任何 slot/event。

---

## 4. P1 — 新建独立 Microstructure Forward Capture Campaign

### 4.1 为什么现在采集，而不是现在研究

v0.3.12 的 Spot-vs-Perp aggregated taker-flow 并未形成合格 Direction Candidate。未来如果要验证 OFI / L2 liquidity / aggressive trade flow 是否包含真正独立信息，必须先积累因果、可审计、事件级 PIT 数据。

本轮只建立数据基础设施，禁止使用未来结果选择特征或阈值。

### 4.2 必须 preregister 后再实现

先创建并 commit：

`configs/forward/v0.3.15_microstructure_capture_campaign.json`

该 freeze commit 必须早于正式 collector implementation commit。

配置至少固定：
- campaign_id；
- symbol = BTCUSDT；
- venue = Binance USD-M Futures；
- source streams；
- capture start UTC / ms；
- local receive timestamp policy；
- sequence validation policy；
- REST snapshot 仅允许 bootstrap/resync；
- no retrospective evidence backfill；
- aggregation intervals；
- raw retention policy；
- data schema version；
- Direction claim = NONE；
- Alpha claim = NONE；
- Runtime integration = DISABLED；
- Execution integration = DISABLED；
- Final Holdout access = false。

起点必须是 freeze commit 后可实际部署的未来固定边界，且不得按采集结果后移。

---

## 5. 数据源与语义

实现前请核对当前 Binance 官方 USD-M Futures 文档，不要照抄过期 WebSocket URL/字段。Binance 2026 年已调整 WebSocket market-stream URL path，必须按当前官方文档实现。

最低要求为公开市场数据，不需要 API Key：

### 5.1 Diff Depth / Order Book

使用当前官方支持的 BTCUSDT USD-M diff-depth market stream，尽可能采用高频更新（如官方当前支持的 100ms 档；以实际官方文档为准）。

REST `/fapi/v1/depth` 仅用于：
- 初始 local book bootstrap；
- sequence gap 后的 re-sync。

REST snapshot 不能回填已经错过的历史 order-book event，也不能让 formal microstructure coverage 变成“成功”。

必须实现 Binance 官方 local order book sequence semantics：
- 缓冲 diff events；
- 拉 REST snapshot；
- 丢弃过旧 update；
- 正确定位第一个衔接 update；
- 后续严格验证 update-id continuity（按当前 USD-M 官方字段/规则，包括官方当前要求的 `U/u/pu` 或等价字段）；
- 任何无法证明连续的 gap -> 记录 GAP -> 重建 book；
- 禁止静默跳过 sequence discontinuity。

### 5.2 Aggregate/Aggressive Trades

订阅当前官方 BTCUSDT USD-M aggregate trade stream。

保存至少：
- exchange event time；
- aggregate trade id；
- price；
- quantity；
- maker/aggressor-side 相关官方字段；
- local receive time。

注意：不得把 `m` 等字段方向解释写反。用单元测试锁定官方语义。

### 5.3 时间戳

每条 event 至少保留：
- exchange event timestamp；
- 若有 transaction timestamp；
- local monotonic/receive timestamp（适合延迟诊断）；
- normalized UTC wall-clock receive timestamp。

禁止用 receive time 冒充 exchange event time。

---

## 6. 存储与可恢复性

推荐独立目录：

`data/forward/BTCUSDT/microstructure/`

禁止把高频原始事件塞进现有 derivatives.sqlite3 或 opportunity_shadow.sqlite3。

设计目标：
- append-only；
- restart-safe；
- crash-safe；
- sequence gap 可审计；
- chunk/partition 可校验；
- 支持长期运行而不会无限单文件膨胀。

可选实现：SQLite + rotated compressed chunks、Parquet/JSONL.zst 等；选择一种简单可靠方案即可，但必须给出 schema 和 checksum/manifest。

不要在仓库 commit 大型 raw market data。GitHub 只提交代码、配置、schema、manifest/sample、状态与审计结果。

---

## 7. 预计算特征：只做机械聚合，不做 Alpha 筛选

允许实时/离线生成下列**预注册、无阈值优化**的基础统计，并输出 1s / 1m / 15m 聚合（如果 1s 存储成本不合理，可在 preregistration 中明确选择 raw+1m+15m，但禁止结果出来后调整）：

### Book side
- spread_bps；
- top-1 depth imbalance；
- top-5 depth imbalance；
- top-20 depth imbalance；
- microprice / microprice deviation；
- best bid/ask depth；
- bid/ask depth change；
- book depletion；
- book replenishment；
- sequence-gap count；
- stale-book duration。

### Trade side
- aggressive buy volume；
- aggressive sell volume；
- trade imbalance；
- aggressive notional imbalance；
- trade count imbalance；
- large-trade descriptive percentiles（只能用过去滚动分布或固定统计，不允许按未来收益调 threshold）。

### OFI
可以实现标准化 Order Flow Imbalance，但必须：
- 在代码/doc 中给出明确数学定义；
- 只使用当时可观察的 book updates；
- 不把简单 top-N depth snapshot imbalance 误称为 event OFI；
- LONG/SHORT 不得由 OFI 直接生成。

### Absorption / Iceberg
只允许实现“observable absorption proxy”，例如 aggressive flow 很大但 mid/price displacement 小、并伴随同侧/对侧 replenishment 的机械统计。

必须明确命名 `absorption_proxy`，不得宣称识别了真实 hidden iceberg order，因为公开 L2 无法直接观察隐藏数量。

---

## 8. Coverage / Reliability Gate（仅数据质量，不是 Alpha Gate）

为 microstructure campaign 建立独立数据质量状态，不得与 v0.3.14 Derivatives Gate 混合。

至少统计：
- campaign age；
- websocket connected seconds / expected seconds；
- depth sequence continuity ratio；
- resync count；
- gap count / gap durations；
- aggTrade coverage；
- event-time vs receive-time latency p50/p95/p99；
- aggregate interval completeness；
- duplicate/conflict counts；
- raw chunk checksum integrity。

建议定义 `COLLECTING / DEGRADED / HEALTHY_FOR_FUTURE_RESEARCH`，但本轮**不得定义任何 Alpha qualification threshold**。

任何掉线区间都必须显式留 gap。允许实时 reconnect/resync；禁止事后伪造连续 L2。

---

## 9. Systemd 与网络运维

新增独立服务，例如：
- `btc-quant-microstructure-forward.service`

这是 long-running WebSocket daemon，不要复用 15m oneshot collector 的执行模型。

要求：
- user-level systemd；
- restart policy 有界且有退避；
- 继承现有安全的 optional network env；
- 不提交 proxy credential；
- graceful shutdown / flush；
- reconnect 后必须重新 snapshot + sequence synchronize；
- 日志中不泄露凭据；
- 与现有 Derivatives/Opportunity timers 隔离，microstructure collector 挂掉不能阻断现有两条正式 evidence campaign。

如果当前运行环境不允许持久在线 WebSocket，必须保留代码/测试/部署件，并把自然运行状态诚实报告为 BLOCKED/DEGRADED，不允许生成模拟“成功采集”交付结果。

---

## 10. Unified Watchdog

扩展 `quantctl forward-evidence status/audit`：

必须仍清楚区分三条证据链：
1. `derivatives.active_epoch` — 正式 v0.3.14 PIT eligibility；
2. `opportunity_forward` — H35 Forward Shadow；
3. `microstructure_forward` — 新的数据积累 campaign，只是 FUTURE_RESEARCH_DATA。

Microstructure 状态不能：
- 改变 Derivatives eligibility；
- 改变 H35；
- 提升 Runtime stage；
- 产生 Direction claim；
- 影响 execution guard。

另外修复第 2 节 split-brain 后，所有 CLI 中出现的正式 derivatives eligibility 必须一致。

---

## 11. 本轮明确禁止事项

禁止：
- 用 L2/OFI/aggTrade 直接做 LONG/SHORT；
- 新增策略参数搜索；
- 对 OFI window/threshold/top-N depth 做 PnL/未来收益扫描；
- 用 Development/Holdout 标签挑选微观结构特征；
- 打开 Final Holdout；
- 修改 TP/BR detector；
- 修改 v0.3.14 Derivatives Evidence Epoch；
- 修改 H35 gate；
- retrospective L2 backfill 计入 formal coverage；
- 自动执行真实订单；
- Maker-First / queue position / cancel-replace 执行引擎开发。

Maker/Taker execution optimization 必须等真正 Candidate Strategy 通过 OOS/robustness 后，在 Paper/Testnet execution-parity 阶段研究。

---

## 12. 测试要求

新增/更新测试至少覆盖：

### Eligibility consistency
- old archive outage 不再污染 active eligibility；
- `derivatives status` == `forward-evidence status` 的 formal active eligibility；
- manual/legacy/backfill 不改善 gate。

### Order book correctness
- snapshot + buffered diff 正确初始化；
- stale updates 被丢弃；
- first bridge update 验证；
- sequence continuity 正常；
- gap 被发现且强制 resync；
- duplicate update 不双计；
- reconnect 不把新 book 接在旧 sequence 上。

### Trade semantics
- maker/aggressor side 映射测试；
- duplicate aggTrade id 处理；
- event-time/receive-time 不混用。

### Aggregation
- 1m/15m boundary 正确；
- incomplete/gap interval 标记不被伪装为完整；
- OFI 数学定义 long/short 对称；
- absorption_proxy 不使用未来 price。

### Safety
- Direction Engine 仍 NONE；
- Runtime maximum 仍 OPPORTUNITY_ONLY；
- execution disabled；
- Holdout 未访问；
- microstructure failure 不影响原两条 collector。

全部现有测试不得退化。

质量要求：
- Ruff PASS；
- strict Mypy PASS；
- pytest PASS；
- compileall PASS。

---

## 13. 正式交付件

所有正式交付件必须 commit + push 到 GitHub：

`deliverables/v0.3.15/`

至少包括：

1. `README.md`
2. `V0.3.15_MICROSTRUCTURE_FORWARD_DATA_FOUNDATION_REPORT.md`
3. `V0.3.15_NUMERIC_ANSWERS.json`
4. `V0.3.15_RECOMMENDATION.md`
5. `ELIGIBILITY_SOURCE_OF_TRUTH_AUDIT.json`
6. `MICROSTRUCTURE_CAMPAIGN_STATUS.json`
7. `ORDERBOOK_SEQUENCE_AUDIT.json`
8. `MICROSTRUCTURE_SCHEMA.md`
9. `MICROSTRUCTURE_OPERATIONS.md`
10. `FORWARD_EVIDENCE_COMBINED_STATUS.json`

Numeric Answers 至少回答：
- branch/head/formal implementation SHA；
- preregistration/freeze SHA 是否早于 implementation；
- microstructure campaign id/start；
- exact streams 与实际官方 URL/path 版本；
- captured depth events / aggTrade events（真实值，若自然运行不足就诚实为少量/0）；
- sequence gap/resync counts；
- connected seconds / coverage；
- latency p50/p95/p99；
- aggregate completeness；
- v0.3.14 active Derivatives epoch 最新状态；
- H35 最新状态；
- tests/Ruff/Mypy/compileall；
- Direction claim；
- execution；
- holdout access。

推荐结论只能是数据/工程层面的，例如：
- `CONTINUE_MICROSTRUCTURE_FORWARD_ACCUMULATION`
- `MICROSTRUCTURE_CAPTURE_BLOCKED_REPAIR_REQUIRED`
- `MICROSTRUCTURE_DATA_HEALTHY_FOR_FUTURE_PREREGISTERED_RESEARCH`

不得输出 `MICROSTRUCTURE_ALPHA_SUPPORTED`。

---

## 14. GitHub 完成条件

任务只有在以下全部完成后才算 done：

- v0.3.15 branch 已 push；
- preregistration commit 顺序正确；
- implementation 已 push；
- 全部 deliverables 已 push 到 `deliverables/v0.3.15/`；
- GitHub CI 已运行；
- 新 PR 已创建；
- PR 中说明：这是 Data Foundation / Forward Infrastructure，不是 Alpha Candidate；
- 不 merge，不关闭历史 PR。

最终回复用户时给出：
- branch；
- final HEAD；
- preregistration SHA；
- implementation SHA；
- CI；
- PR；
- microstructure capture 当前真实状态；
- v0.3.14 evidence epoch 当前真实状态；
- H35 当前真实状态。

---

## 15. 最终安全边界

本轮结束时必须保持：

```text
Strategy: EXPERIMENTAL
Runtime maximum: OPPORTUNITY_ONLY
Qualified Direction Engine: NONE
Execution: DISABLED
Candidate Freeze: NONE
Final Holdout: SEALED
Derivatives PIT Epoch: ACCUMULATING
Opportunity Forward Campaign: ACCUMULATING
Microstructure Forward Campaign: DATA_COLLECTION_ONLY
```

核心原则：

> 高频数据源可以用于低频策略，但必须先证明它含有独立、稳定、可复现的信息。v0.3.15 只负责把未来研究所需的真实 PIT 微观结构数据收集正确，不负责“证明有 Alpha”。
