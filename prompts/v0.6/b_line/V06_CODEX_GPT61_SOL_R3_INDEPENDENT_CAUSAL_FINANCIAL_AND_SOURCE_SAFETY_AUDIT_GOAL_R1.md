# quant-agent v0.6 — Codex GPT-6.1 Sol Independent R3 L2 Audit Goal R1
## Funding known-at × Mark/L2 correctness × Cross-branch identity × 2026 Binance+Clash public-source trust

你是 **Codex GPT-6.1 Sol — B-line Independent Consequential Correctness Auditor**。本任务以独立工程安全审计为目标，不是 Gemini R3 的第二套实现，不负责策略搜索，不修改 Gemini 的分支。Controller 为 ChatGPT-0；Gemini 正在独立实现 R3。你必须真实检查源代码、独立设计并运行反例、公开可复现证据，最后给出**有依据的 PASS/FAIL/BLOCKED**，不能仅复述 Gemini 报告。

## I. 固定身份与严格隔离

TASK_ID: V06_CODEX_GPT61_SOL_R3_INDEPENDENT_CAUSAL_SAFETY_AUDIT_R1
REPO: EXASHXE/btc-quant-agent-public
AUDIT_BRANCH: feature/v06-bline-codex-r3-independent-causal-audit-r1
FROZEN_AUDIT_BASE_SHA: 632d2e37f28b8c3efbd2b818ecdb74783f0df238
GEMINI_R3_BRANCH_READ_ONLY: feature/v06-bline-gemini-r3-portable-ci-funding-pit-source-qualification
GEMINI_R3_AT_DISPATCH_SHA: 632d2e37f28b8c3efbd2b818ecdb74783f0df238
B_ORIGINAL_READ_ONLY_SHA: 51cdd4e17503fbd18ad22aaeeaba3580f5efacf8
C_ORIGINAL_READ_ONLY_SHA: 91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b
G1_ORIGINAL_READ_ONLY_SHA: 861a9d148f72db00e6079e53af78220bdd7e84ce
ORIGINAL_A_SOURCE_SHA: df00997f344eba82f7cca0d03ee1617948abee44
CONTROLLER_R2_L2_DECISION_SHA: 5cb218255578e87771042491decb11afd2d493a9
CONTROLLER_R2_L2_DECISION_URL: https://github.com/EXASHXE/btc-quant-agent-public/blob/5cb218255578e87771042491decb11afd2d493a9/reviews/v0.6/b_line/V06_ABC_CLASH_ROUTED_BRIDGE_R2_EXACT_SHA_CONTROLLER_L2_DECISION.md
GEMINI_R3_GOAL_URL: https://github.com/EXASHXE/btc-quant-agent-public/blob/8bb8ba2b784c40350f477c16e6a554408814480e/prompts/v0.6/b_line/V06_GEMINI_R3_PORTABLE_CI_FUNDING_PIT_PUBLIC_SOURCE_QUALIFICATION_GOAL.md
WORKTREE: /root/workspace/project/quant-v0.6/codex-r3-independent-causal-audit-r1
SCRATCH: /tmp/btc-codex-r3-independent-audit-r1

只允许写入以下**独立审计命名空间**：
- scripts/audits/r3_codex_causal_audit_r1/**
- tests/test_v06_r3_codex_causal_audit_r1_*.py
- docs/audits/r3_codex_causal_audit_r1/**
- evidence/v0.6/b_line/r3_codex_causal_audit_r1/**

禁止任何修改、merge、cherry-pick、reset、force-push Gemini R3 分支及 A/B/C 原业务代码、tests/.github、生产 src/**、历史项目政策或受保护数据。禁止访问/列出/stat 用户 Quant-agent/data、Quant-agent-sanitized，H39-H41/Forward，2024–25 protected holdout、此前受保护的 2026 记录和个人交易账户。**任何真实 Binance 账户调用、Order、Testnet/Live 交易、资金写入、真实 LLM 与飞书网络均禁止。** 源码检查只允许当前 public repository 及 pinned public detached checkout，在独立临时目录完成；不得读取任何密钥/Clash 订阅或代理配置。审计**默认全程禁用外部 Binance 网络**；通过 synthetic fixtures/mocks 定位逻辑即可。不要以模型推断/代码直觉代替复现实证。

## II. 原始缺陷必须作为最小独立再现

以下问题已由 Controller 对 R2 frozen HEAD 作静态确证。**请用可执行 witness 重现，然后在审计中寻找尚未发现的相邻错误，不能仅抄写已知结论：**

1. **C Funding PIT backdating（BLOCKER）**：scripts/integration/market_event_bridge_r2/bridge_engine.py C wrapper observed_wall_utc_ms、available_at_ms 采用 entry.funding_time_ms；B wrapper 采用实际 observer ingress。用 settlement T、arrival T+200ms/T+30s/T+3h、C 认证入口，证明 C 提早获取本来迟到的信息。适配器不能通过伪造 C 的 wall timestamp 过时钟和序列检查。
2. **Mark witness freshness/source isolation（BLOCKER）**：bridge_engine 用 last_mark_tick_price float，没绑定最近 VERIFIED mark 的 source SHA、available_at、route_epoch、book/session reset、标价 time。构造 stale, negative, NaN/Inf, cross-epoch, network reconnection, delayed funding 与 source race，验证能否误报 COST_COMPLETE；一旦不完整必须 NO_REALIZED_CASH_BASIS/UNKNOWN，不能把 0 当准确结果。尤其需要审查真实 Binance REST funding history 通常没有结算当刻 Mark 行情：不能把**接收时间附近**的 Mark 当作**结算时刻真实已知**的 Mark 来算历史资金费用；对于晚到的 funding 必须区分“到账后才发现的资金费率”与“持仓结算市值参考”并强制 provenance。
3. **PUBLIC_SMOKE_VERIFIED false positive（HIGH）**：scripts/market_data/forward_public_feed_r1/connector.py run_bounded_public_stream 在 REST snapshot 已计入 events_received，若 market 和 public WSS 同时连接失败也可能返回 PUBLIC_SMOKE_VERIFIED，且 per-stream exception 被内部捕获写 error 不向 gather 传播。构造 REST-only、仅 depth、只有 market 但无 closed kline、15s short run、Depth chain broken、WS failed 两路、SSL EOF、运行结束仍有任务；审计终态必须按来源分级而不是总条数。
4. **CI non-hermetic imports（BLOCKER）**：GitHub [38252226915](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38252226915) 最终 Pytest collection 5 PermissionError，因为 tests/test_v06_market_event_bridge_r2_* 中硬编码 /root/... B/C worktree。真正可复现 CI 不能假设主机文件系统；Gemini R3 会修。Codex 应审查它选择的 exact SHA 加载方法是否真的执行 B/C 源码而不是跳过或误加载同名包，GitHub clean checkout/egress失败应 FAIL-CLOSED，不可把 docs-only green 当 PASS。
5. **已公开报告对网络来源夸大**：R2 15s evidence 261 events 不能证明 >=2 completed 1m Last, >=120 sec mark, complete top10 continuous; source smoke 的一个 REST 200 或 WSS depth frame 不是可交易 Market+Depth 来源。审计断言必须区分 CLIENT_CONNECT_OK / WS_FRAME_OBSERVED / MULTICHANNEL_PIT_QUALITY_VERIFIED / SOURCE_CONTINUITY_WINDOW_VERIFIED。公共行情市场源本身不代表真实 fill / L2 queue / signal Alpha。已有公开诊断曾存环境代理细节、gateway；不要复制敏感信息到新报告。

## III. 新增独立深层验证面（Codex 高价值工作）

### A. 时间/因果不变量
- 对 event E/T/receiver observed_wall_utc_ms/observed_monotonic_ns/available_at_ms、derived feature_known_at_ms、decision_at_ms 采用显式时钟元组；证明 future mutation 不影响 earlier decision。WS Market vs Public 两个 connection epochs 和各自 monotonic times 未必跨 epoch 可全序比较；时间回拨应 CLOCK_UNCERTAIN。测试同毫秒多通道交换顺序、一个 WS 延迟 1–30sec、route epoch 改变、NTP backward jump。
- Mark-derived minute bar: 实际算法据 provider E 分桶，最晚 tick ingress 可能晚于下一分钟 tick；检查封口以后是否能回溯补发、缓存断线是否导致错误复用上一 Mark bar、晚到 tick 变成过去可用；max jitter/sample_count 阈值是否保证覆盖窗口起末；是否把 Derived Kline 错标 Official Kline 造成信号来源混淆。
- Book: A OrderBookIntegrityV1 与 R2 的 top10 ladder extraction 是否真正和对应 depth event 原子绑定；snapshot/update ID、last_update_wall 与 decoder 连贯，纯数量统计不代表 quote liquidity。测试 inverted U/u/pu、DELTA 乱序、REST snapshot before buffered diff、duplicate, gap, crossed, zero qty, liquidity exhaustion, depth stale 1s.
- Cash: Funding, fee, spread, slippage 的量纲和符号、zero/negative qty、重复 settle、缺失结算 Mark、独立 Decimal，可能出现正方向反了或者同一结算时间跨 route 重放重复收费；ledger 中 position_state 与 settlement cutoff。模拟 10x/15x 杠杆不必要，也不得触碰真钱。
- **Atomicity**：C 出账模拟 sidecar 写 WAL 与 B shadow 现金估算之间不可默许“部分成功”造成非对称审计，必要时停止并报告跨系统尚未具备事务性。

### B. 2026 公共 WebSocket × Clash/Mihomo 路由
- verify /public/stream depth vs /market/stream Kline/Mark/AggTrade，并对旧/stream、/private、ws-fapi、spot、coin-M fail closed；阅读官方协议有无消息速率或 24h rollover 类型误配。
- 阅读 proxy_route.py 的 SOCKS5h/HTTP CONNECT/TLS 验证/urllib/ws side egress；验证 direct mode 不受环境 HTTPS_PROXY 污染、explicit proxy 失败不降级直连、若以 proxy provider 403/451 拒绝则不尝试其他地域节点。
- 断网时是否向 stats 传递完整失败而不误判 READY；是否在 WebSocket 重连或代理切换时 reset book, route_epoch, source digest，而不是继续旧 orderbook。
- 不产生任何 live network 行为；使用假 urllib/WS transport 与 scripted frames。不要探测用户代理端口或收集节点/IP。

### C. 源、冻结与完整性
- 验证 B freeze SHA 原报告不在 git 中，科学预注册 INVALID，不允许任何源数据新收益测试被误记作正式 OOS；CI success 不代表 policy Alpha。
- R2 final receipt 源 SHA 引用旧 Stage3 2d8cd7... 而真实 R2 final 632d2e...；检查生成 manifest/JSON 是否真的能重新计算，不可通过发布“新报告说 PASS”掩盖旧错误。
- 发布可复现 wrong-hash, wrong-origin, fixture-not-real, F3 sample already-exposed 负例；无需再读取历史 F3 数据或者受保护日志。

## IV. 实际审计操作与输出

**按强约束 Goal 执行，直到完成可复现审计证据或记录有界 BLOCKED。**

阶段 1（初始只读）：冻结 current commit 的 \`git rev-parse\`、parents、文件 sha、合法写入范围。读取 R2 最终代码及 4 项原始 mismatch，起草 machine-invariant matrix。固定独立 audit harness 的目标集合。C1 在审计命名空间 push 初始方法文档/测试计划。
阶段 2（真实独立负例）：独立设计输入 JSON，令每个已知缺陷在未修 R2 产生可确定失败；生成至少 **36 个有意义的测试情景**，其中不少于 **12 个 C Funding/MARK/Decimal、8 个 PIT/bar alignment、8 个 book/quote/source reset、8 个 CI/public route and anti-bypass**。不要只算空参数化测试；测试代码应作为“探测器”输出 observed vs expected，**不允许通过 xfail 掩盖严重失败**。可将有意观察现有 FAIL 的 repro 脚本写入审计 namespace，而不篡改 CI 算法或保护其他分支；自有 tests 若产生红色 CI 必须诚实标为 detection success vs engineering gate failure。
阶段 3（额外隐藏风险）：针对 Mark record late-binding、C composite data acceptance、Funding rest source/mark at settlement、REST snapshot-only spoof success 进行至少 **4 项跨模块独立攻击路径分析**，每项至少一个可运行最小 witness；再检查 source code 其他真实高风险问题，但不要无限扩张。
阶段 4（独立 evidence）：执行 Python3.12 脚本与 pytest（如果环境允许），输出 PASS/FAIL by invariant；以 \`R2_BASELINE_FINDINGS.json\`、\`REPRO_CASES.json\`、\`TEST_EXECUTION_EXACT_SHA.json\`、\`FINDINGS_BY_SEVERITY.json\`、\`SOURCE_PROVENANCE_MATRIX.json\` 和 \`INDEPENDENT_FINAL_AUDIT.md\` 为终态。注意两个不同状态：**Repro test 成功触发预期脆弱行为，不等于工程不变量 PASS**；报告用 \`BUG_REPRODUCED\` 和 \`INVARIANT_VIOLATED\` 双字段表达。
阶段 5（与 Gemini R3 松耦合）：如果远端 R3 HEAD 在 Codex 完成审计时已经出现新增 SHA，可**额外**对新 SHA 进行 **read-only exact-SHA delta review**，但绝不能等待 Gemini push、修改 Gemini branch、推测未来修复已通过。审计输入的基础固定为 R2 632d2e...；补丁 review 若存在必须绑定准确 R3 HEAD+CI run，不得混淆两者。

**工程边界：独立 audit，不改业务代码、不直接将修复合并。** 可提供 Gemini 可应用的最小修复建议、API contract 与负例的完整输入，但不要直接在其分支写 patch。无需用户发本地数据。当前 Codex额度珍贵，不必做整仓重复跑 3000+ tests，也不必新增策略搜索；应把 token/测试预算投入严重不可见风险与可信复现。

## V. GitHub 提交/测试审计纪律

- 最多 **3 个非强推审计提交**：C1 方法/冻结; C2 可运行 adversarial harness; C3 证据+终态。只在自己的审计分支及允许命名空间写。
- 所有外部 B/C 参考必须使用真实 pinned SHA；如果测试环境没有对应 checkout，可根据 public repo exact SHA 建立只读 checkout，不可依赖用户本地绝对路径；失败要终态 \`PINNED_SOURCE_UNAVAILABLE\`。
- 禁止触及 GitHub CI 配置以优化某个测试结果；如果自有 detection tests 因记录已知 bug 在 GitHub 上红，只能报告预期失败，不说 CI gate green。
- 所有 findings 提供 precise file:line，前置条件、真实现象、影响边界、Severity（BLOCKER/HIGH/MEDIUM/LOW）、最小可重放命令、测试 SHA、修复目标不变量、最低验收场景。
- 报告中不写用户本机 Clash 代理 URL、gateway、用户名、token、个人持仓、账户余额、私有数据路径内容；除已公开源码的 namespace 以外，不披露用户设备可识别信息。
- 旧 B 样本、保护 holdout、历史 2026 私有数据未访问；所有测试行情必须自造 synthetic with explicit labels.

## VI. 必须交付清单
- docs/audits/r3_codex_causal_audit_r1/INDEPENDENT_FINAL_AUDIT.md
- docs/audits/r3_codex_causal_audit_r1/CAUSAL_AND_FINANCIAL_INVARIANTS.md
- docs/audits/r3_codex_causal_audit_r1/CONTROLLER_REMEDIATION_ORDER.md
- evidence/v0.6/b_line/r3_codex_causal_audit_r1/R2_BASELINE_FINDINGS.json
- evidence/v0.6/b_line/r3_codex_causal_audit_r1/REPRO_CASES.json
- evidence/v0.6/b_line/r3_codex_causal_audit_r1/TEST_EXECUTION_EXACT_SHA.json
- evidence/v0.6/b_line/r3_codex_causal_audit_r1/FINDINGS_BY_SEVERITY.json
- evidence/v0.6/b_line/r3_codex_causal_audit_r1/SOURCE_PROVENANCE_MATRIX.json
- scripts/audits/r3_codex_causal_audit_r1/** deterministic replay and report generation
- tests/test_v06_r3_codex_causal_audit_r1_*.py (run baseline defect probes safely)

## VII. 终态和最终回答格式

严格返回：
TASK_ID:
AUDIT_BRANCH:
EXACT_FROZEN_INPUT_SHA:
FINAL_REMOTE_AUDIT_SHA:
COMMIT_CHAIN/PARENTS:
B_C_REFERENCE_EXACT_SHAS:
CODE_MODIFIED_OUTSIDE_AUDIT_NAMESPACE: MUST_BE_ZERO
GEMINI_R3_BRANCH_TOUCHED: MUST_BE_ZERO
EXECUTION_ENV/PYTHON:
ADVERSARIAL_TEST_CASES_RUN/OBSERVED_BUG_REPRO/INVARIANTS_VERIFIED:
FUNDING_RECEIVER_PIT_VERDICT:
FUNDING_MARK_SETTLEMENT_PROVENANCE_VERDICT:
CASH_DECIMAL_CONSERVATION_VERDICT:
BOOK_ATOMICITY_AND_ROUTE_EPOCH_VERDICT:
PUBLIC_SMOKE_FALSE_POSITIVE_VERDICT:
PINNED_CI_PORTABILITY_VERDICT:
EXACT_SHA_EVIDENCE_FILES:
CONTROLLER_PRIORITY_FIX_LIST:
PRIVATE_ACCOUNT_OR_ORDER_CALLS: ZERO
PROTECTED_FILES_ACCESSED: ZERO
ALPHA_PROMOTION_AUTHORITY: NONE
G3/G4_LIVE_AUTHORITY: NONE
TERMINAL_DECISION: ONE OF
  - R2_INDEPENDENT_AUDIT_COMPLETED_WITH_BLOCKING_FINDINGS
  - R2_INDEPENDENT_AUDIT_COMPLETED_NO_ADDITIONAL_BLOCKERS
  - R2_INDEPENDENT_AUDIT_BLOCKED_WITH_EXACT_EVIDENCE

**审计不会自动改变 R2、R3 的既有治理结论。** 即使所有新测试都正常，也不能绕过 Gemini R3 的可移植 CI 验收、交易回测科学预注册和真实行情可用性门槛。Controller 将独立按 exact SHA 判定下一步。
