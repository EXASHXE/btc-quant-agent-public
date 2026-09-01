# BTC Quant Agent v0.3.16 — Forward Evidence Recovery & Microstructure Reliability Hardening

## 0. 任务定位

本轮是 **Forward Evidence / Data Reliability 修复轮**，不是 Alpha 研究轮，不允许新增 Direction 因子、不允许参数寻优、不允许打开 Final Holdout、不允许启用 Paper/Testnet/Live Execution。

v0.3.15 正式交付结果 SHA：

`97693e146b139f64b0b1a565de157572f5ae67eb`

v0.3.15 预注册 Microstructure Campaign SHA：

`75a18a562ed6f8ef1b778bfcc21138b1cce8e0cb`

v0.3.15 正式 collector implementation SHA：

`d3e248c3519fd4777a10ec665f74f8b47d612826`

当前 v0.3.16 分支已由 v0.3.15 正式交付 HEAD 创建：

`codex/v0.3.16-forward-evidence-recovery-microstructure-reliability`

请在该分支继续开发。不要修改/重写历史 deliverables、历史 PIT 记录或旧 campaign 起点。

---

## 1. v0.3.15 已验收通过的内容

以下内容视为本轮基线，不得破坏：

1. `quantctl derivatives status` 与 `quantctl forward-evidence status` 已统一到 v0.3.14 active Evidence Epoch 作为正式 derivatives eligibility source of truth。
2. all-time / pre-epoch ledger 保留，但必须继续标记为 `NOT_FOR_ELIGIBILITY`。
3. Microstructure campaign 已在实现前预注册：
   - diff depth：`btcusdt@depth@100ms`
   - aggTrade：`btcusdt@aggTrade`
   - REST depth 仅用于 bootstrap / resync
4. Local order book 使用 `U/u/pu` 语义：
   - buffer depth
   - REST snapshot
   - discard `u < lastUpdateId`
   - first bridge `U <= lastUpdateId <= u`
   - subsequent `pu == previous_u`
   - gap 后清空 book 并重新同步
5. 原始 exchange timestamp 与 local receive wall/monotonic timestamp 分离。
6. SQLite WAL daily partitions、raw events、book samples、1s/1m/15m mechanical aggregates 已存在。
7. Microstructure 不进入 Runtime，不生成 LONG/SHORT，不声明 Alpha。
8. Runtime maximum 仍为 `OPPORTUNITY_ONLY`；Execution `DISABLED`；Final Holdout `SEALED`。

---

## 2. 本轮发现的 P0 问题

### P0-A：v0.3.14 Derivatives Evidence Epoch 已经触发不可逆 gap failure

v0.3.15 delivery snapshot：

- epoch：`DERIVATIVES_PIT_EPOCH_V0314_001`
- expected scheduled slots：27
- recorded：27
- fully available：9
- failed：18
- required field coverage：33.33%
- max consecutive bad/missing：18
- frozen gate：`maximum_consecutive_failed_or_missing_scheduled_slots = 4`

因此从数学上讲，这个固定 epoch **已经不可能再通过 max-gap gate**。未来再连续成功也不会让 all-epoch 最大 gap 从 18 降回 <=4。

当前把它继续显示为泛化的 `INSUFFICIENT_FORWARD_HISTORY` 不够准确。

必须新增终态语义，例如：

`FAILED_GAP_GATE_TERMINAL`

或同等明确命名，并证明其 monotonic / terminal，不得未来因新增成功数据自动恢复为 eligible。

### P0-B：必须找到 18 个连续失败 slot 的真实根因

不要只看 timer 是 active。

必须使用：

- SQLite `collection_runs`
- endpoint telemetry
- systemd journal
- proxy / VPN / WSL 网络环境
- DNS/TLS/timeout 分类
- 当前 `network.env`
- collector service environment

输出逐 slot failure chronology，并回答：

1. 哪些 endpoint 失败？
2. error class 分布是什么？
3. 是否全部 endpoint 同时失败？
4. 是否与 systemd/proxy 环境变化相关？
5. retry 是否被执行？是否有 retry 后恢复？
6. 是否发生 scheduler missed invocation，还是 invocation 本身失败？
7. 当前环境下 collector 是否已自然恢复？

不能删除失败记录，不能把事后 REST 数据 backfill 成成功 PIT。

### P0-C：Opportunity Forward 当前 56 slots 中仅 28 successful scans

当前 H35 campaign：

`OPPORTUNITY_FORWARD_V0313_20260831T050656Z`

v0.3.15 snapshot：

- scheduled slots recorded：56
- successful scans：28
- `MISSED_DECISION_SLOT`：28
- opportunities：0

这是 50% 的 scan miss rate，存在明显 selection-bias 风险。

必须把 28 个 missed slots 按 root cause 分类：network、market-data-health、config/registry mismatch、runtime exception、scheduler/environment、其他。

本轮 **不得直接宣布 H35 invalid，也不得偷偷重启 campaign**。先做完整 data-quality audit；如果当前 campaign 的缺失机制无法被证明近似独立于市场状态，则交付中明确标记 `H35_DATA_QUALITY_AT_RISK`，并给出下一轮是否应创建 successor campaign 的建议。

---

## 3. Derivatives Evidence Epoch Recovery 设计要求

### 3.1 旧 epoch 必须保留

`DERIVATIVES_PIT_EPOCH_V0314_001` 永久保留；不得改 start time、不得删失败、不得覆盖 config。

新增 machine-readable epoch lifecycle / registry，例如：

`configs/forward/derivatives_evidence_epochs.json`

至少包含：

- epoch_id
- config_path
- start_ms
- status
- terminal_reason
- terminal_at_ms
- superseded_by
- formal_eligibility_role
- immutable_history

### 3.2 Terminal gate 语义

当固定 epoch 的任何不可逆 gate 已经被违反，例如：

`max_consecutive_bad_or_missing > frozen maximum`

状态必须立即转为 terminal failure，而不是继续 `INSUFFICIENT_FORWARD_HISTORY`。

至少区分：

- `INITIALIZING`
- `ACCUMULATING`
- `ELIGIBLE_FOR_PREREGISTERED_RESEARCH`
- `FAILED_GAP_GATE_TERMINAL`
- 如需要，可增加其他明确 terminal failure，但不能模糊化。

必须有测试证明：一旦进入 terminal gap failure，追加任意数量成功 slot 后仍不可恢复。

### 3.3 Successor epoch 规则

只有在完成真实根因修复并验证自然 scheduled collector 恢复后，才允许创建 successor derivatives evidence epoch。

要求：

1. successor config 单独文件，旧 config 不修改。
2. start 必须是 **未来固定 UTC 15m boundary**。
3. start 选择规则必须在 start 之前写入并 commit。
4. start 不得根据未来数据表现移动。
5. manual/legacy/backfill 继续不计正式 eligibility。
6. gate 不得弱化：仍为 `30d / 2500 full / >=95% each required field / max gap <=4`。
7. 若本轮无法在可信方式下完成 successor preregistration，则允许交付 `NO_SUCCESSOR_EPOCH_STARTED`，不要为了版本完成强行启动。

推荐流程：

- commit collector reliability fix
- 运行自然 scheduled burn-in，作为 operations diagnostic，明确 `NOT_FOR_FORMAL_ELIGIBILITY`
- 确认 root cause 已解除
- 再 commit successor epoch preregistration，start 设为至少若干小时后的机械固定 UTC boundary
- 不等待/筛选 successor 未来结果后再改 start

---

## 4. Microstructure Reliability Semantics 修复

v0.3.15 data foundation 通过，但当前 status 指标存在若干会在长时间运行中误导研究资格的风险。本轮必须处理。

### P0-D：session `end_ms=NULL` 不能永远视为连接存活

当前 status 把未关闭 session 的 `end_ms=NULL` 解释为连接持续到 `now`。如果进程 crash / host suspend / WSL shutdown，没有机会调用 `session_end()`，旧 session 可能永久虚增 uptime。

修复要求：

- 引入 service instance / process session identity；
- 引入 heartbeat 或 lease；
- 至少每数秒持久化 last heartbeat；
- 新进程启动时识别 orphan session；
- orphan session 不能计为一直 connected 到当前时刻；
- 对 crash/suspend 造成的未知区间写明确 coverage gap；
- 不允许通过重启清除 gap。

必须测试：模拟进程无 clean shutdown 后重新启动，旧 session 不会持续抬高 uptime。

### P0-E：aggregate completeness 不能以“是否至少有一笔 trade/event”为充分条件

当前 `trade_count > 0 && book_sample_count > 0 && gap_count == 0` 并不能严格代表完整覆盖：

- quiet bucket 可以真实没有成交，不应因此自动认为丢数据；
- service 中途离线但 bucket 里恰好已有一个 event，也不应被标成 complete。

请将 completeness 改为 **coverage/liveness + sequence-validity 语义**。

建议至少记录：

- trade_stream_covered_ms
- depth_stream_covered_ms
- depth_sequence_valid_ms 或 equivalent
- explicit_gap_overlap
- process/service coverage
- bucket duration

然后定义 mechanical data-quality completeness，不依赖未来价格、不依赖 Alpha outcome。

如果采用阈值（例如 coverage ratio），阈值必须在本轮 protocol 中提前冻结并解释；不得根据未来方向/PnL选择。

### P0-F：`resync_count` 不得简单等于所有 gap count

区分至少：

- `DEPTH_SEQUENCE_GAP`
- `DEPTH_BOOTSTRAP_FAILURE`
- `DEPTH_RECONNECT`
- `TRADE_DISCONNECT`
- `PROCESS_OR_HOST_GAP`
- `REST_BOOTSTRAP_FAILURE`

`resync_count` 只能统计实际触发 local-book resync 的事件。

### P1-G：clock skew / latency audit

v0.3.15 实测 local wall clock 约落后 Binance server 1232ms，因此 raw `receive_time_ms - exchange_event_time_ms` 出现负 p50。

要求：

1. 原始 wall/monotonic/exchange timestamps 永不修改。
2. 增加定期 clock-offset measurement：使用 Binance server time 与本地 request send/receive midpoint 估计 offset，并保存 RTT / uncertainty。
3. status 同时报告：
   - raw signed latency
   - measured clock offset
   - offset measurement RTT
   - diagnostic clock-adjusted latency
4. corrected latency 仅作为 diagnostics，不回写 raw event timestamp。
5. 若 clock uncertainty 太大，标记 latency quality degraded，而不是强行修正。

### P1-H：UTC daily partition finalization

当前 closed partition manifest 需要强化：

- 明确何时 partition 变为 finalized；
- finalized 后不得再被 session_end 或其他操作改写；
- 跨 UTC midnight 的 session 要么切 session，要么采用明确、安全的 finalize grace rule；
- checkpoint 后记录 SHA-256 manifest；
- manifest 再次计算必须稳定；
- 如果 finalized 文件发生变化，audit 必须报 integrity failure，不得静默重写 manifest 掩盖变化。

---

## 5. 本轮禁止事项

严格禁止：

- 不新增任何 LONG/SHORT feature；
- 不测试 OFI/imbalance/microprice 的未来收益；
- 不按 PnL/return/MFE/MAE 做筛选；
- 不修改 TP/BR detector；
- 不修改 RR、stop、target、factor threshold；
- 不打开 Final Holdout；
- 不启用 execution；
- 不把历史缺失 REST backfill 算入 forward eligibility；
- 不删除/重写 v0.3.14/v0.3.15 forward history；
- 不因为当前 epoch 失败就移动原 epoch 起点；
- 不把“service active”当作“data healthy”。

---

## 6. 实际运行验收

代码写完后必须在真实运行环境执行，而不是只跑 unit tests。

至少需要：

1. `systemctl --user` 检查三个链：
   - derivatives collector
   - opportunity forward + resolver
   - microstructure collector
2. 对 derivatives 当前失败 chronology 做真实 journal + DB audit。
3. 验证修复后至少若干个**自然 scheduled** derivatives collection，而非手工 `collect-once` 伪装。
4. Microstructure 做自然连续运行验证；建议至少 15 分钟，如执行环境允许更长则更好。
5. 模拟/验证 collector restart 后 orphan session accounting 正确。
6. `forward-evidence status/audit` 输出三条链相互隔离。
7. 不允许删除失败数据以提高指标。

若运行环境在任务期间网络不可用，必须如实交付 `ENVIRONMENT_BLOCKED`，不要制造成功数据。

---

## 7. 必须新增/更新的测试

至少覆盖：

1. old derivatives epoch max gap >4 -> terminal failure；
2. terminal epoch 后追加大量 full success 仍不可恢复；
3. successor epoch 不使用 old epoch rows；
4. manual/legacy/backfill 不提高 successor eligibility；
5. successor start 不可移动；
6. derivatives status 与 forward-evidence status formal answer 完全一致；
7. Opportunity missed-slot root cause telemetry deterministic；
8. microstructure orphan session 不会被计到 `now`；
9. heartbeat/lease timeout 生成 coverage gap；
10. quiet trade bucket 在 stream 健康时可以是 valid，而非因为 trade_count=0 自动 invalid；
11. 部分覆盖 bucket 即使已有 events 也不能被错误标 complete；
12. depth gap 与 trade disconnect/resync 分类分离；
13. raw timestamps immutable；clock adjustment only diagnostic；
14. partition finalized 后不可修改；checksum drift 能被 audit 检出；
15. microstructure chain 仍不能改变 derivatives/H35 gate；
16. Direction claim NONE；Execution DISABLED；Holdout SEALED。

继续要求：

- pytest 全通过
- Ruff PASS
- strict Mypy PASS
- compileall PASS

---

## 8. Deliverables

必须将正式交付件 commit + push 到 GitHub：

`deliverables/v0.3.16/`

至少包含：

- `README.md`
- `V0.3.16_FORWARD_EVIDENCE_RECOVERY_REPORT.md`
- `V0.3.16_NUMERIC_ANSWERS.json`
- `V0.3.16_RECOMMENDATION.md`
- `DERIVATIVES_V0314_TERMINAL_EPOCH_AUDIT.json`
- `DERIVATIVES_FAILURE_ROOT_CAUSE_AUDIT.json`
- `DERIVATIVES_SUCCESSOR_EPOCH_STATUS.json`
- `OPPORTUNITY_MISSED_SLOT_AUDIT.json`
- `MICROSTRUCTURE_SESSION_COVERAGE_AUDIT.json`
- `MICROSTRUCTURE_CLOCK_AUDIT.json`
- `MICROSTRUCTURE_PARTITION_INTEGRITY_AUDIT.json`
- `FORWARD_EVIDENCE_COMBINED_STATUS.json`

如果没有创建 successor epoch，`DERIVATIVES_SUCCESSOR_EPOCH_STATUS.json` 必须清楚说明原因和下一步，不能缺文件。

大型 SQLite/raw L2 数据继续 `.gitignore`，不要 push 到 GitHub；但正式 audits、status、report、protocol/config/provenance 必须 push。

---

## 9. 最终报告必须明确回答

1. `DERIVATIVES_PIT_EPOCH_V0314_001` 是否已经 terminal failed？为什么？
2. 18 个连续失败 slot 的具体 root cause 是什么？
3. 修复后自然 scheduled success 的实际结果如何？
4. 是否创建了 successor derivatives epoch？如有，其固定 start / gate / freeze SHA 是什么？
5. Opportunity 28/56 miss 的原因分布是什么？H35 是否存在 data-quality bias 风险？
6. Microstructure crash/restart 后 uptime 是否仍可能虚高？
7. 新 completeness 语义如何区别“真实无成交”和“数据断流”？
8. Depth resync、trade disconnect、host/process gap 是否已分开统计？
9. host clock offset 如何测量？raw timestamps 是否保持不变？
10. closed daily partition 是否真正可审计不可篡改？
11. 当前是否有任何 Direction Candidate？答案应仍是 `NONE`。
12. Execution 是否仍 `DISABLED`，Final Holdout 是否仍 `SEALED`。

---

## 10. Recommendation 枚举

本轮最终 recommendation 只能从以下选择一个主项：

- `CONTINUE_FORWARD_EVIDENCE_ACCUMULATION`
- `DERIVATIVES_SUCCESSOR_EPOCH_STARTED_CONTINUE_ACCUMULATION`
- `FORWARD_COLLECTION_ENVIRONMENT_NOT_RELIABLE`
- `OPPORTUNITY_FORWARD_DATA_QUALITY_REQUIRES_SUCCESSOR_CAMPAIGN`
- `MICROSTRUCTURE_DATA_PIPELINE_NOT_YET_RELIABLE`

可以附 secondary flags，但不得输出 Alpha/Candidate/Live recommendation。

---

## 11. Git / GitHub 完成条件

任务只有在以下全部满足后才算完成：

1. 所有代码、测试、config/protocol、deliverables 已 commit；
2. `git status` clean；
3. push 到：
   `codex/v0.3.16-forward-evidence-recovery-microstructure-reliability`
4. GitHub 远端可实际读取 `deliverables/v0.3.16/`；
5. GitHub CI 成功；
6. 创建正式 v0.3.16 PR 到 `main`，不要自动 merge，也不要关闭历史 PR；如果已有同分支 placeholder/closed PR，不要复用错误历史，创建可追溯的正式 PR 或在 GitHub 限制下清楚记录阻塞原因。

结束前输出：

```bash
git status
git log --oneline --decorate -15
git ls-tree -r --name-only HEAD deliverables/v0.3.16
```

并在最终回复中给出：

- branch
- formal implementation SHA
- final delivery SHA
- CI run/result
- PR number
- successor epoch freeze SHA（如有）
- 关键真实运行指标

本轮目标不是让系统更接近“能下单”，而是让未来用于 Alpha 判断的 Forward Evidence **真正可信、不会被 collector/runtime 语义欺骗**。
