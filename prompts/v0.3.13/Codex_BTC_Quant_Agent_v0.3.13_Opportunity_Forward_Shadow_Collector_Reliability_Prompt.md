# Codex 完整任务 Prompt — BTC Quant Agent v0.3.13 Opportunity Forward Shadow + Collector Reliability

项目：`EXASHXE/btc-quant-agent`
本地目录：`/root/workspace/project/Quant-agent`
Windows：`\\wsl.localhost\Ubuntu\root\workspace\project\Quant-agent`

当前目标分支已经创建：
`codex/v0.3.13-opportunity-forward-shadow-reliability`

v0.3.12 验收时最终交付 HEAD：
`6791bfd5e03245e0b7123e310503399923a85164`

v0.3.12 Formal Code SHA：
`d8c9fee21ed7c2926385c5ff8355cf0c0054054f`

v0.3.12 Preregistration SHA：
`ca647f23f75a452ba4af28ad8a1ba503f05fc9a1`

---

# 0. 本轮定位

本轮版本：

`v0.3.13 Opportunity Forward Shadow + Forward Collector Reliability`

本轮**不是新的 Direction Alpha family**，不继续用已经反复研究过的 Development Set 搜索新参数。

核心目标只有两个：

1. **P0：修复/明确 Forward Derivatives Collector 的实际可靠性问题**
   - systemd timer 已 active/enabled，但 v0.3.12 交付时 51 条 observation 只有约 1.96% required-field coverage；绝大多数定时采集为 `FAILED_NETWORK_UNREACHABLE`。
   - 如果不解决这一点，30 天 / 2500 snapshots / 95% availability 的 frozen gate 永远无法真正通过。

2. **P0：立即开始真正的 Opportunity Forward Shadow Campaign**
   - 当前唯一重复获得 Development 支持的是 TP/BR 的 Movement / Opportunity 能力。
   - v0.3.13 从“未来真实时间”开始冻结并记录 TP/BR `OPPORTUNITY_ONLY` 事件及 matched non-opportunity controls。
   - 本轮不预测 LONG/SHORT，不计算交易 PnL，不生成 Entry/SL/TP/Size。
   - 目标是让真正的 Forward evidence 从现在开始积累，而不是继续反复消耗旧 Development。

本轮允许实现长期运行基础设施，但不允许 Paper/Testnet/Live。

---

# 1. v0.3.12 已冻结结论

不得通过换窗口、阈值、符号或子组重新打开 Spot–Perp Flow family。

v0.3.12：

```text
H32 standalone Spot–Perp Flow = INCONCLUSIVE_MECHANISM
H33 incremental vs BTC 1h momentum = FALSIFIED
H34 TP/BR-conditioned direction = FALSIFIED
Recommendation = INCONCLUSIVE_FLOW_FAMILY
```

关键数字：

```text
Flow episodes = 34,552
LONG = 17,275
SHORT = 17,277

4h signed median = +0.002573 ATR
8h signed median = -0.003086 ATR

H34 pooled:
4h = -0.080181 ATR
8h = -0.007496 ATR

H34 matched delta:
4h = -0.042283 ATR
8h = -0.031764 ATR
```

Registry：

```text
spot_perp_taker_flow_direction
research_status = INCONCLUSIVE
runtime_eligibility = BLOCKED
eligible_for_reuse = false
```

正常 Runtime：

```text
maximum_stage = OPPORTUNITY_ONLY
qualified Direction Engine = NONE
Execution = DISABLED
Final Holdout = SEALED
```

注意：H33 的 paired median 因 54.8% aligned events 存在大量 delta=0，统计量退化成 0。记录为 methodology limitation 即可；因为 H32 本身不稳定且 H34 为负，本轮**禁止借此重新打开 Flow family**。

---

# 2. Git / GitHub 工作流

先执行：

```bash
cd /root/workspace/project/Quant-agent
git status
git remote -v
git branch --show-current
git log --oneline --decorate -15
gh auth status
```

使用已有分支：

```text
codex/v0.3.13-opportunity-forward-shadow-reliability
```

确认该分支包含本 Prompt。

不要自动 merge `main`。

完成任务后：

- 所有正式交付件必须 commit 到 `deliverables/v0.3.13/`
- 必须 `git push` 到 GitHub
- 必须创建/更新 v0.3.13 PR
- 只有 GitHub 远端能实际读取交付件，任务才算完成

原始 SQLite、市场数据、大型 Parquet 仍保持 ignored，不要提交大型二进制数据。

---

# 3. 开始前质量基线

执行：

```bash
python -m pip install -e '.[dev,research]'
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src tools tests skill-template/scripts
```

记录：

- tests passed
- overall coverage
- critical module coverage
- Ruff
- strict Mypy
- compileall
- current CI

不得通过削弱旧测试完成本轮。

---

# 4. P0-A：先诊断 Forward Derivatives 网络失败

v0.3.12 交付状态：

```text
sample_count = 51
coverage_days ≈ 0.515
required_field_coverage_each ≈ 1.96%
latest_collection_status = FAILED_NETWORK_UNREACHABLE
scheduler_active = true
scheduler_enabled = true
```

这说明 scheduler 存活，但业务采集基本失败。

必须先复现并判断原因。

至少执行并保存结果：

```bash
systemctl --user status btc-quant-forward-derivatives.timer --no-pager
systemctl --user status btc-quant-forward-derivatives.service --no-pager
systemctl --user list-timers btc-quant-forward-derivatives.timer --all
journalctl --user -u btc-quant-forward-derivatives.service --since '24 hours ago' --no-pager

env | grep -Ei '(^|_)(http|https|all|no)_proxy=' || true
systemctl --user show-environment | grep -Ei 'proxy' || true

.venv/bin/quantctl derivatives collect-once
.venv/bin/quantctl derivatives status
.venv/bin/quantctl derivatives audit
```

还必须区分：

```text
DNS failure
TCP/network route failure
proxy/VPN environment not inherited by systemd
HTTP/TLS failure
Binance endpoint-specific failure
```

不得只写“network problem”。

---

# 5. Systemd 网络环境修复要求

当前 unit 只有：

```text
Environment=PYTHONUNBUFFERED=1
```

如果人工 shell 能访问而 systemd service 不能访问，优先检查 proxy/VPN 环境差异。

实现安全、可审计、可持久的可选网络环境机制。

推荐：

```text
~/.config/btc-quant-agent/network.env
```

由 systemd 使用：

```ini
EnvironmentFile=-%h/.config/btc-quant-agent/network.env
```

允许用户自行配置：

```text
HTTP_PROXY=
HTTPS_PROXY=
ALL_PROXY=
NO_PROXY=
```

要求：

- 该文件绝不能 commit；
- 不打印包含密码/token 的完整 proxy URL；
- installer 不应把 secret 写进 Git；
- 没有代理时仍可正常运行；
- 不硬编码用户当前网络地址；
- 不把 `sudo` 作为默认方案。

如果失败根因不是 proxy，按实际根因修复。

---

# 6. 新增 Forward Network Diagnostic

新增类似：

```bash
quantctl derivatives diagnose-network
```

至少检查：

```text
DNS resolve fapi.binance.com
HTTPS connectivity /fapi/v1/ping
premiumIndex
openInterest
openInterestHist
takerlongshortRatio
globalLongShortAccountRatio
basis
```

输出必须区分：

```text
OK
DNS_ERROR
NETWORK_UNREACHABLE
TIMEOUT
HTTP_ERROR
TLS_ERROR
PARSE_ERROR
```

不要求交易 API key。

敏感 proxy 字段只能输出：

```text
configured=true/false
scheme
host redacted or safely summarized
```

不能泄露 credentials。

---

# 7. Collector 健康指标增强

保留 append-only PIT 语义。

禁止 retrospective backfill。

新增/明确：

```text
scheduled_attempt_count
fully_available_snapshot_count
partial_snapshot_count
failed_attempt_count
scheduled_slot_success_rate
required_field_availability
coverage_days
largest_gap_slots
last_success_at_ms
last_failure_at_ms
consecutive_failure_count
```

注意：

> failed attempt 不是有效 PIT snapshot，但仍必须保留在 collection ledger 中，不能删除来美化 coverage。

30d / 2500 / 95% / max-4-gap gate 不得降低。

如果历史失败导致 30 日窗口数学上已经不可能达到 95%，audit 必须明确给出：

```text
CURRENT_WINDOW_GATE_MATHEMATICALLY_UNREACHABLE
```

如果仍可恢复则给出所需后续成功率。

---

# 8. P0-B：启动 Opportunity Forward Shadow Campaign

当前 Registry 已确认：

```text
trend_pullback_opportunity = SUPPORTED_MOVEMENT / ANALYSIS_ONLY
breakout_retest_opportunity = SUPPORTED_MOVEMENT / ANALYSIS_ONLY
```

Direction role 均已 rejected。

v0.3.13 必须建立新的、与交易 Shadow 分开的：

```text
Opportunity Forward Shadow
```

它回答：

> 在真正未来、从冻结版本开始运行后，TP/BR 是否仍然比普通相似市场时点更容易出现较大的未来运动？

它**不回答**应该 LONG 还是 SHORT。

---

# 9. Campaign Freeze

建立 campaign manifest，例如：

```text
configs/forward/v0.3.13_opportunity_shadow_campaign.json
```

在首次正式 campaign observation 前 commit。

必须冻结：

```text
campaign_id
start_git_sha
registry_version
strategy_version
feature_version
config_hash
detector_ids
normal_runtime_mode = RUNTIME_GATED
horizons = [4h, 8h]
control_matching_rules
minimum_opportunity_events = 30
preferred_opportunity_events = 50
minimum_calendar_days = 30
seed
```

Campaign 一旦启动：

- 不得因结果调整 TP/BR detector；
- 不得调整 horizon；
- 不得用 legacy_pattern_side 当方向；
- detector 代码发生改变必须开启新 campaign ID，不得混在旧 campaign 中。

---

# 10. Forward Opportunity Store

建议新增本地 ignored 数据库：

```text
data/forward/BTCUSDT/opportunity_shadow.sqlite3
```

WAL、append-safe、restart-safe。

至少存：

## 10.1 scan_observations

每一个真实计划的 15m decision slot 都记录：

```text
scheduled_slot_ms
collection_started_at_ms
observed_at_ms
status
market_data_health
regime
atr_15m
atr_percentile / fixed bucket fields needed for matching
opportunity_present
opportunity_id
detector_id
setup
registry_version
git_sha
config_hash
network/data errors
```

如果网络失败：

```text
MISSED_DECISION_SLOT
```

禁止以后历史回放补成真实 Forward opportunity。

## 10.2 outcomes

独立存：

```text
observation_id
horizon
reference_time
reference_price
future_high
future_low
future_close
future_range_atr
max_abs_excursion_atr
resolved_at_ms
resolution_source
```

Outcome 可以在事件发生以后通过历史 Kline 补取，因为它是 label，不是当时 feature。

但必须保证：

```text
Feature/Opportunity 不允许 retrospective reconstruction
Outcome label 允许事件发生后 deterministic resolution
```

---

# 11. Forward movement labels

不使用 Direction。

冻结 primary movement metrics：

```text
future_range_atr = (max_future_high - min_future_low) / frozen_atr
max_up_excursion_atr = max(0, max_high - reference) / frozen_atr
max_down_excursion_atr = max(0, reference - min_low) / frozen_atr
max_abs_excursion_atr = max(max_up_excursion_atr, max_down_excursion_atr)
```

Primary horizons：

```text
4h
8h
```

reference：

```text
OPEN of first fully available 1m bar strictly after decision close
```

frozen ATR：

使用当次 scan 时已经可用的 frozen ATR，不可在结果出来后重算成未来 ATR。

---

# 12. Forward Control Population

不要只记录 Opportunity；每个成功的正常 15m scan 都写 observation。

后续 control 从同一真实 Forward campaign 中选择。

对于每个 Opportunity，固定匹配最多：

```text
K = 5
```

non-opportunity controls。

匹配只能用当时字段，建议冻结：

```text
same 1H regime
same ATR percentile decile
same calendar month or closest available within campaign（如果月样本不足，不强制月）
minimum time separation = 24h
nearest deterministic by absolute time
```

严禁使用 outcome 做 matching。

需要输出 control reuse diagnostics。

如果 Forward campaign 尚短导致无法匹配，保留事件等待未来 control pool 扩充；不要降低规则。

---

# 13. H35 — Opportunity Forward Movement Edge

本轮可以启动 H35 campaign，但除非样本 gate 已经自然满足，不必强行在 v0.3.13 宣判。

Hypothesis：

```text
Frozen TP/BR OPPORTUNITY_ONLY events have larger subsequent movement than matched Forward non-opportunity market states.
```

Primary：

```text
4h candidate-minus-control future_range_atr
8h candidate-minus-control future_range_atr
```

Secondary：

```text
max_abs_excursion_atr
TP-only
BR-only
```

样本 gate：

```text
>=30 resolved opportunity events
>=30 calendar days
>=100 unique matched controls
>=20 distinct UTC days containing resolved opportunities or controls
```

Preferred：

```text
>=50 resolved opportunities
```

如果未满足：

```text
FORWARD_CAMPAIGN_ACCUMULATING
```

绝不能因为当前只有几笔就给 SUPPORTED/FALSIFIED。

如果未来满足 gate，再使用预注册 cluster bootstrap；本轮把算法和 protocol 写好即可。

---

# 14. Scheduled Opportunity Collection

建立持久化 scheduler，例如：

```text
btc-quant-opportunity-forward.service
btc-quant-opportunity-forward.timer
```

建议运行：

```text
UTC 00/15/30/45 分钟后的 40~60 秒
```

确保完整 15m bar 已闭合。

不要与 Derivatives timer 在完全同一秒制造网络竞争。

命令建议：

```bash
quantctl opportunity-forward collect-once
quantctl opportunity-forward status
quantctl opportunity-forward audit
quantctl opportunity-forward resolve
quantctl opportunity-forward report
```

`collect-once`：

- 调正常 `RUNTIME_GATED` scan；
- 不 notify；
- 不执行；
- 记录所有 successful scan / missed slot；
- Opportunity 只能来自 normal Runtime。

`resolve`：

- 对已经跨过 4h/8h 的 unresolved observation 获取 outcome；
- 网络失败则保留 unresolved，之后重试；
- 不改变原 observation。

---

# 15. Execution / Safety Firewall

整个 v0.3.13：

```text
Execution = DISABLED
qualified Direction Engine = NONE
Runtime max stage = OPPORTUNITY_ONLY
Candidate Freeze = NONE
Final Holdout = SEALED
```

Opportunity Forward Shadow 不得：

- 生成 Signal；
- 生成 LONG/SHORT；
- 使用 legacy_pattern_side；
- 生成 Entry/SL/TP/size；
- 调 Execution Plan；
- 写 `shadow_trades` 作为交易盈亏；
- 伪装成 Signal Shadow。

建议 terminology：

```text
Opportunity Forward Shadow = movement validation
Signal Shadow = future Direction/Alpha validation（当前不存在 qualified Direction）
Execution Shadow = fill/latency/slippage validation（以后）
```

---

# 16. Runtime / Registry 不回退

必须新增 regression：

```text
normal runtime cannot emit actionable LONG/SHORT
opportunity forward collector cannot access legacy mode
opportunity store has no direction field used for action
execution remains registry-blocked
```

`legacy_pattern_side` 可以存为原始解释 metadata，但 Forward 分析代码不得引用它生成 signed return / direction。

---

# 17. Forward Collector 网络恢复验收

本阶段 Agent 必须实际验证，不接受“代码写好了”。

至少：

1. 手工 `collect-once` 成功一次；
2. systemd context 下成功一次；
3. 等待/触发至少一次 timer scheduled run；
4. `status/audit` 显示新增 fully available snapshot；
5. endpoint errors 为 0 或明确剩余 blocker；
6. 不删除过去失败记录；
7. 无 retrospective backfill。

如果因为用户当前 VPN/代理/WSL 环境无法让 systemd 成功，必须输出：

```text
FORWARD_COLLECTOR_RELIABILITY_BLOCKED
```

并给出精确 blocker 和人工最小动作。

不要虚报 PASS。

---

# 18. Opportunity Campaign 实际启动验收

本阶段至少必须：

1. campaign manifest 已 commit；
2. timer installed + enabled + active；
3. 至少一个真实 successful scheduled scan 写入 local forward store；
4. 如果真实 TP/BR Opportunity 恰好出现，则正确写入；
5. 如果没有出现，不允许制造测试 opportunity；
6. `status` 能显示：
   - campaign age
   - scheduled slots
   - successful scans
   - missed slots
   - opportunity count
   - TP / BR count
   - resolved 4h count
   - resolved 8h count
   - control availability
   - H35 state = ACCUMULATING / EVALUABLE

Formal tests 可用 fixture 创建 synthetic Opportunity，但真实 campaign store 不允许 synthetic rows。

---

# 19. 测试要求

至少新增：

```text
test_network_diagnostic_redacts_proxy_credentials
test_systemd_env_file_is_optional_and_not_repo_secret
test_failed_derivative_attempt_remains_in_ledger
test_collector_reports_scheduled_success_rate
test_collector_gate_not_weakened
test_opportunity_campaign_manifest_is_frozen
test_forward_scan_uses_runtime_gated_only
test_forward_scan_never_emits_signal
test_missed_slot_cannot_be_backfilled_as_opportunity
test_outcome_can_be_resolved_later_without_mutating_observation
test_future_range_atr_is_directionless
test_legacy_pattern_side_not_used_in_forward_metrics
test_control_matching_uses_no_outcome_fields
test_control_time_separation_24h
test_h35_low_sample_returns_accumulating
test_forward_store_restart_safe
test_forward_store_duplicate_idempotency_and_conflict_behavior
test_execution_remains_disabled
test_final_holdout_remains_sealed
```

---

# 20. Engineering Quality

执行：

```bash
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src tools tests skill-template/scripts
```

目标：

- 全部 PASS
- 新关键 causal / forward / network paths 有直接测试
- 不以无意义测试刷 overall coverage

---

# 21. Deliverables — 必须上传 GitHub

完成后创建并 commit：

```text
deliverables/v0.3.13/
├── README.md
├── V0.3.13_OPPORTUNITY_FORWARD_SHADOW_REPORT.md
├── V0.3.13_NUMERIC_ANSWERS.json
├── V0.3.13_RECOMMENDATION.md
├── FORWARD_DERIVATIVES_RELIABILITY_AUDIT.json
├── OPPORTUNITY_FORWARD_CAMPAIGN_STATUS.json
├── OPPORTUNITY_FORWARD_OPERATIONS.md
├── NETWORK_DIAGNOSTIC_SUMMARY.json
└── RESEARCH_REGISTRY_UPDATE.md
```

不要只把文件留在本地。

正式交付必须：

```bash
git add ...
git commit -m 'docs: deliver v0.3.13 opportunity forward shadow and collector reliability'
git push -u origin codex/v0.3.13-opportunity-forward-shadow-reliability
```

然后验证 GitHub：

```bash
gh api repos/EXASHXE/btc-quant-agent/contents/deliverables/v0.3.13?ref=codex/v0.3.13-opportunity-forward-shadow-reliability
```

如果 GitHub 远端看不到交付件，任务未完成。

---

# 22. Numeric Answers 必须回答

`V0.3.13_NUMERIC_ANSWERS.json` 至少包含：

1. start SHA / final SHA？
2. latest tests / coverage / Ruff / Mypy / compileall？
3. Derivatives collector 失败根因是什么？
4. manual collection 是否成功？
5. systemd-context collection 是否成功？
6. scheduler 是否 active/enabled？
7. 修复前/后 total attempts？
8. fully available snapshots 数？
9. required-field availability？
10. scheduled slot success rate？
11. consecutive failure count？
12. largest gap slots？
13. 是否发生 backfill？必须 false。
14. 30d coverage gate 当前状态？
15. Opportunity campaign ID / start time / start SHA？
16. successful forward scan count？
17. missed decision slots？
18. observed TP opportunities？
19. observed BR opportunities？
20. resolved 4h / 8h opportunity count？
21. unique eligible controls？
22. H35 state？
23. normal Runtime 是否仍只到 OPPORTUNITY_ONLY？
24. qualified Direction count？必须 0。
25. Execution？必须 DISABLED。
26. Final Holdout？必须 SEALED。
27. v0.3.14 推荐是什么？

---

# 23. v0.3.14 决策规则

本轮不要直接创建新的历史 Alpha family。

优先根据真实 Forward 状态决定：

## A. Derivatives PIT gate 尚未通过

```text
CONTINUE_FORWARD_ACCUMULATION
```

继续 Opportunity Forward + Derivatives collection。

不要为了版本号继续挖 Development。

## B. Derivatives PIT 已满足 frozen gate

才允许下一版设计：

```text
v0.3.14 Genuine PIT Derivatives Feature Qualification
```

候选 family 才可以包括：

```text
OI change
Taker buy/sell ratio
Basis
Global Long/Short positioning
```

仍需 preregistration，不能一口气参数扫描。

## C. Opportunity Forward 已 >=30 events / >=30d

可在下一版正式评价 H35。

如果 Forward Movement Edge 不复现：

```text
DOWNGRADE TP/BR OPPORTUNITY
```

而不是继续假设它有效。

## D. Collector 仍无法可靠采集

先修基础设施，不启动 Derivatives Alpha research。

---

# 24. GitHub PR

完成后创建或更新 PR：

```text
research: v0.3.13 opportunity forward shadow and collector reliability
```

不要 merge。

PR body 必须包含：

```text
collector root cause
collector operational state
forward campaign state
sample counts
H35 = accumulating/evaluable
Direction Engine = NONE
Execution = DISABLED
Holdout = SEALED
```

---

# 25. 最终原则

> 当前最稀缺的不是第 20 个历史指标，而是新的、未被反复消费的真实 Forward evidence。

> TP/BR 目前只获得 Movement/Opportunity 资格，所以应该先在未来数据里验证“有没有大行情”，而不是恢复其 LONG/SHORT。

> Derivatives PIT 数据只有在采集可靠、覆盖 gate 真正通过以后，才有资格进入 Direction Alpha 研究。

> 网络失败记录是研究数据质量的一部分，不能删掉或历史补齐来美化结果。

> v0.3.13 的成功标准不是盈利，而是：真实 Forward campaign 已经开始持续积累，并且 PIT collector 从“timer 存活”升级为“实际数据采集可靠”。

任务结束状态必须打印：

```text
Strategy: EXPERIMENTAL
Runtime maximum: OPPORTUNITY_ONLY
Qualified Direction Engine: NONE
Execution: DISABLED
Candidate Freeze: NONE
Final Holdout: SEALED
Opportunity Forward Campaign: ACTIVE / BLOCKED（真实状态）
Derivatives PIT Collector: HEALTHY / DEGRADED / BLOCKED（真实状态）
```
