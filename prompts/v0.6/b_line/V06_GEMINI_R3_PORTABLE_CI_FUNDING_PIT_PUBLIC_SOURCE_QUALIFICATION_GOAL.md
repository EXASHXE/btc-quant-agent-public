# quant-agent v0.6 — Gemini Goal R3
## Portable exact-SHA CI × Funding PIT integrity × Clash-routed real public-source qualification

**角色**：Gemini 高级 Python/Linus CI+事件时钟审计工程执行 Agent。你必须以可执行程序、完整实际回归证据与远端 commit 交付成果；不停止在方案/报告。该任务是 **R2 的有限工程修复**，不是交易策略探索。通过修复测试可移植性和资金事件的真实 known-at，才能考虑下一阶段长期前向数据观察。

## 0. 所有输入锁定：不碰科学或资金授权

- TASK_ID: V06_GEMINI_R3_CI_PIT_SOURCE_QUALIFICATION
- CONTROLLER_L2_REVIEW_SHA: 5cb218255578e87771042491decb11afd2d493a9
- L2 报告：https://github.com/EXASHXE/btc-quant-agent-public/blob/5cb218255578e87771042491decb11afd2d493a9/reviews/v0.6/b_line/V06_ABC_CLASH_ROUTED_BRIDGE_R2_EXACT_SHA_CONTROLLER_L2_DECISION.md
- REPOSITORY: EXASHXE/btc-quant-agent-public
- BRANCH: feature/v06-bline-gemini-r3-portable-ci-funding-pit-source-qualification
- EXACT_START_SHA: 632d2e37f28b8c3efbd2b818ecdb74783f0df238
- WORKTREE: /root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source
- SCRATCH: /tmp/btc-r3-ci-pit-source
- UPSTREAM_B_READ_ONLY_SHA: 51cdd4e17503fbd18ad22aaeeaba3580f5efacf8
- UPSTREAM_C_READ_ONLY_SHA: 91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b
- ORIGINAL_G1_READ_ONLY_SHA: 861a9d148f72db00e6079e53af78220bdd7e84ce
- A BASE_ORIGINAL_READ_ONLY_SHA: df00997f344eba82f7cca0d03ee1617948abee44

**允许写入**：
- scripts/integration/market_event_bridge_r2/** （最小修复与新 portable_ci_refs.py、source_qualification.py）
- scripts/market_data/forward_public_feed_r1/connector.py、cli.py、proxy_route.py（仅修改真实行情验证规则与必要的网络状态检查，不得放宽隐私/网络边界）
- tests/test_v06_market_event_bridge_r2_*.py 与 tests/test_v06_forward_public_feed_r1_*.py（用于精确依赖加载及新质量负例）
- docs/integration/market_event_bridge_r3/**、evidence/v0.6/b_line/market_event_bridge_r3/**（**新增**审计证据，不得覆盖原 R2 结论或记录）。

**绝对禁止**修改原 B/C/G1 的任何代码、报告、历史 SHA、策略参数、收益结果或科学冻结；禁止修改生产 src/**、.github/**、受保护 H39/H40/H41/Forward、2024–25 holdout、旧 2026 私有/前向数据；禁止访问（包括 list/stat/open）用户 Quant-agent/data 与 Quant-agent-sanitized。任何 private account/order/cancel/transfer/用户 API key/secret/Feishu 或真实 LLM 外部调用一律为 0。公开 Binance USDⓈ-M 数据诊断仅限已有授权的用户显式本地 Clash 或直接读取，不可绕过明确的 Binance 地区/政策限制。禁止改 Clash 节点、配置、系统代理/TUN/firewall/allow-lan、TLS 证书验证；禁止 force-push；不自动合并、不进入 TESTNET/LIVE 或真实资金。

### 已独立核实的 R2 状态

R2 最终 HEAD 上的 GitHub Actions [38252226915](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38252226915) **FAILURE**，Ruff/compile/JSON PASS，真正 pytest 的 **collection** 出现 5 个 PermissionError，因为测试中的 B/C 路径硬编码到开发机 /root/workspace/project/quant-v0.6/；local fixture 自称 145 R2 + 148 A = 293 通过，尚未经最终远端代码 SHA 的 GitHub pytest 证明。

- 对 B 的资金 settled event 使用正确的 receiver arrival time；对 C 的同一 envelope 却把 observed_wall_utc_ms 和 available_at_ms 设为 funding_time_ms。这是显式 PIT backdating 漏洞。
- R2 在准备 C Funding 时引用 self.last_mark_tick_price（float），没有同时校验 Mark 的 seen-at、source SHA、quality、staleness、route_epoch/connection_epoch；可能用过期或无效 Mark 计算现金并称 COST_COMPLETE。
- 源烟测在 Windows/WSL2 已配置的本地 Clash 显式路由下，记录 proxy CONNECT 成功、Binance REST GET 200、public 深度 WS 真实帧；15 秒烟测记录 261 total，但缺少按 channel 验证的真实 >120 秒 Mark 与 **至少两个已完成** 1m Last；BinancePublicFeedClient 对 events_received >0（REST snapshot 也会加）便标 PUBLIC_SMOKE_VERIFIED，即使两条 WSS 都不成功；需彻底修复状态机。
- 原 NETWORK_ROUTE_DIAGNOSTIC.json 提交了 ambient proxy URL、NO_PROXY 字符串及局域网 gateway（未见密码），违反原本的脱敏合同。新 R3 evidence 必须只报告脱敏类型、boolean、非复原 route session ID；不能修改历史 git 提交使问题消失，不能在文档中再次复制本机私有 host/port。
- 现有 R2 的源和测试修复仍有价值；**严禁把已完成的短时公网观测或 2021–23 历史结果用于挑选新 Alpha**。B 预注册 INVALID，仍须未来单独冻结。

## 1. 目标一：真正可移植的精确 Git SHA 外部消费者测试

现有 C 相关与 B 相关模块至少 5 个硬编码依赖 /root/... worktree，GitHub Runner 不存在；一些模块在 import/collect 阶段 Path.resolve/exists/stat/打开绝对目录、污染 sys.path。

构建可靠的 PortablePinnedSourceHarness：
1. 所有测试必须在 **纯净 GitHub Actions Ubuntu Runner/临时工作目录**下加载，不能存在开发机绝对路径，不允许因为 pinned B/C 缺失就悄悄 skip 真实互操作测试、或用无关 stub 假扮 exact B/C 真消费。普通 unittest 使用本仓独立 fixture 但跨消费者验收必须确实执行 exact B/C。
2. 固定两个 GitHub 公共 repo SHAs；在独立临时目录下以 read-only detached checkout、git archive 或精确路径 materialization 加载原始 B/C；验证 git rev-parse HEAD == pinned SHA、关键文件 SHA256 内容，目录严格为任务 scratch/temp（不进入用户受保护 data）。
3. 如果 GitHub checkout 默认 shallow，支持对 **明确允许的 public repo** 执行精确 SHA fetch；网络仅用于 GitHub 源码准备、不是 Binance 私人 API，也不得将 git fetch 变成无限远端扫描。失败则测试报告明确 PINNED_UPSTREAM_UNAVAILABLE 并 FAIL，绝不能标为 145 PASS。
4. 多版本同名 Python package 不能因 PYTHONPATH 串包；如果需要把 B 与 C 的执行分成两个 isolated subprocess，将 bridge 的签名 JSON artifact 序列化交给各自只读 consumer，分别校验返回的真实 class/sha、PIT 与 Decimal 金额，且保存 stdout/exitstatus/log SHA。严禁复制业务逻辑进入测试目录冒充 B/C 代码。
5. 任意 import、subprocess 在 CI 默认不执行 exchange、LLM、Feishu、订单写操作；动态源禁止默认启用网络；unit test 只允许 tmp scratch, 无凭证。
6. 至少提供 25 个纯净 Runner/临时环境负例：错误 B/C SHA、缺 commit、pinned manifest mismatch、跨包 import 污染、缺网与容错失败、路径遍历、可疑 symlink、复制仓库中不可用绝对路径、重复临时 clone、consumer 返回无效 key、consumer 触发未经批准的 egress 等。

**验收**：pytest collection 在 CI 不再抛 5 个 PermissionError；真正的 GitHub CI（head_sha 必须绑定最终代码）执行 R2 自有测试及 A 基准回归，不允许被 green docs-only 欺骗；如果 legacy H40 产生新的单独失败，以 CI job logs 证明独立继承项，不能遮掩。

## 2. 目标二：彻底解决已识别 Funding PIT 和 Mark 来源财务异常

改变 scripts/integration/market_event_bridge_r2/bridge_engine.py 和必要的 funding_adapter.py 小范围实现，**不能修改 B/C 原始消费者**：

1. 必须将给 C 的 Funding wrapper observed_wall_utc_ms、available_at_ms 设为 **实际收到 funding 记录的 receiver arrival time**（且满足 C 的严格 clock sequence/epoch 边界），绝对不再使用 entry.funding_time_ms 代替。Provider settlement time 只写 funding_time_ms、provider_event_ms 等元信息。接收晚于结算 200ms、30s、3h 的测试均保证 C 只在实际接收时或之后才承认事件；B/C 同源 timestamp 一致。
2. Mark 价格 witness 必须是经认证的最近 VERIFIED Mark 事件对象，而不是裸 float：value Decimal、observed_wall_utc_ms、available_at_ms、provider_event_ms、source_sha、route_epoch、connection_epoch、quality、measured age。只在与 settlement 合规 causal mapping 的时候提供 signed funding cash；年龄超过预注册阈值或原始标记 UNKNOWN/DEGRADED/INVALID、期间断线/切换代理，都必须 COST_INCOMPLETE/NO_REALIZED_BOOKING，不能默认使用旧 Mark。
3. Funding REST历史记录在 T0到达时，不得倒填任何 T<T0 的前向交易状态；未来确实收到已结算 funding 可能晚到，可以在新 timestamp 记可追溯调整，但不能当作此前已知信息。确认 long/short 资金费用符号相反、settlement_id idempotent、重复 REST 记录不会二次记账。没有 mark_at_settlement 可信价则现金效应 UNKNOWN，不凭空估算。
4. 将源接收时间、Mark 可信价版本、settlement_time、Ledger credit/debit、B/C wrapper SHA、source manifest、UTC/route epoch 生成 1:1 机器链路 witness；Mark 一分钟前后变化不能影响以前已封存现金。
5. 严禁采用 json 中浮点缺失字段补0、严禁用 provider timestamp backfill source_available_at。新增 30+ 正反测试，固定 Decimal 至8位，包含极端 funding、异常负号、0 net qty、quarantine、超长延迟、跨 epoch/stale、强行历史性现金事件、不同多头/空头、1000 synthetic account conservation。
6. 财务测试如发现 C 必需 exact payload 不允许正常 late arrival，应在 **桥接器** fail closed 并出具 C_CONSUMER_CONTRACT_BLOCKED 而不是修改 C 原代码或骗过签名/clock；不可降低安全边界。

**验收**：funding PIT late arrival 负例在同一份 exchange receipt 输入下 B/C 一致；没有错时资金写入，B alpha remains forbidden，C G1 is local-only.

## 3. 目标三：真实公共源的分通道质量认定，而非 15 秒泛计数

不重复调优 2021–23 策略。仅修复公开行情 smoke 和源健康判定：
1. connector.py 的 stats 必须按 channel 输出 raw public_depth_update、REST_snapshot、aggTrade、markPriceTick、kline_closed_1m、kline_open_1m、estimatedFunding、settledFunding、invalidFrames、sourceDropped、rebootstrap、clockUncertain；每类包含清晰 receiver ingress + route_epoch + manifest SHA。不要仅 events_received。
2. 把 PUBLIC_SMOKE_VERIFIED 限定为完整观测多通道：**至少两个真实 closed Last 1m**，**>=120 秒持续有效 Mark Tick**（不同 receiver window）、>=1 连续可信 REST snapshot + depth delta bridge、实际 aggTrade 非零并给出计数、无 unrecovered book gap 与不可信 socket error。duration 低于阈值一律 PUBLIC_SOURCE_PARTIAL/SHORT_DIAGNOSTIC，不能标 VERIFIED。
3. 如果只有 REST snapshot 而 WSS 2 路失败，即使事件计数 >0，也必须 SOURCE_UNAVAILABLE/PARTIAL；当某一 WS task 异常时不能被另一任务成功掩盖。停止时必须关闭 socket/文件句柄/worker，不能留下后台永久 daemon。
4. 严格区分 user selected direct 与显式 Clash HTTP/SOCKS5h，REST和两 WS 经同一 route，禁止 TLS verify=False、透明 direct fallback、节点自动旋转、provider explicit geographic policy denial circumvent；系统源不可达的合法结果为 PUBLIC_SOURCE_UNVERIFIED/PROVIDER_BLOCKED。
5. 复用 Windows/WSL2 代理探测，但新报告只写 proxy_enabled、proxy_kind、loopback_or_host 和 route_hash（本机随机且不可复原，未暴露 actual host/IP、port、username、NO_PROXY、Windows gateway）；不要从现有提交复制敏感网络设置进新 docs/evidence。
6. 完全模拟 3min coherent Mark/Last/Depth/Agg，另外模拟 REST-only、market WS absent、public WS absent、closed bar不足、book crossed、SSL EOF、source staleness、频繁路由切换、clock regression 的 falsification tests。要求至少 30 项相关测试。
7. 在**用户授权、所在网络与 Binance 提供方政策允许**、且指定本地 Clash 节点可用时，可以进行一次限定 **3–5 分钟**公开只读采样，用本地 private temp 保存原始小型原件，向 public git 只提交脱敏的 counts/hash/quality; 不允许抓私人账户、不允许自动代理节点变更、不允许24h unattended daemon。无有效可用网络时只提交严格 offline gate + 公网 source UNKNOWN，不影响工程交付。
8. 真实数据可用只能证明数据系统科学输入的技术准入，不能证明 4–24h 策略有 alpha，更不能调用 order/TESTNET/LIVE。

**验收**：最后报告分开 PUBLIC_ROUTE_REACHABLE、PUBLIC_MULTI_CHANNEL_SOURCE_VERIFIED、L2_CONTINUOUS_WINDOW_VERIFIED 三个等级；不足哪项如实标 UNKNOWN/FAIL，不能用总事件数或者 REST 200替代。

## 4. 目标四：测试可追踪、精确代码 SHA 与时间因果性独立核查

R2 最终提交 \`632d2e...\` 修改了代码和用例；它的 TEST_AND_CI_EXACT_SHA_RECEIPT.json却绑定旧 Stage3 \`2d8cd7...\`，因此不能验证最终源码。R3 需：
- 首次在新 worktree中创建独立失败复现实例，C1 commit + push，不能先隐藏原始失败；
- C2 只做 portable pinned checkout/source test harness（含 25+ tests）push;
- C3 修 Funding PIT + Mark provenance（30+ tests）push;
- C4 修来源状态/Clash read-only scanner（30+ tests）push;
- C5 行为验证与有界 public smoke（如果合法且可达）、全套测试、机器收据；push；
- C6 仅报告和索引/审计更新（如需要），不能再修改最后已经声称验证的源码；非强推，最多6提交。

测试总要求：
1. 新增 >=85 个有意义 tests，且原始 R2 145 与 A148 不能被删除、弱化、固定路径 skip 代替；至少在 Runner Python3.12 执行现有 293+85 测试的真实测试步骤；对原 A 稳定全套测试回归。可以保留旧 H40 inherited FAIL 单独报告和隔离分类，但不准绕过/改旧 H40。
2. 临时精确 B/C checkout 的 GitHub SHA、文件摘要、可重复执行命令、root isolation、正常/拒绝事件用例数必须写 source_identity receipt；所有金额用 Decimal；完整 machine JSON 往返 hash 校验和 run provenance。
3. Test plan = 是 full/focused，真实执行的 pytest steps 不允许 SKIPPED；最后代码 SHA 对应 GitHub run head SHA，所有改动测试通过后方可称 ENGINEERING_GATE_PASS。Ruff/compile/JSON 严格；失败就是 BLOCKED。
4. 额外进行安全 AST 与网络栈覆盖：默认 mode 禁网，受限公用 GET & routed WebSocket 才允许显式连接，B/C 不会通过 imports 建立私人网络连接。
5. 不得对未来实际价格收益作统计，不得查看受保护 2024–26 data，不得更改 B 的无效 freeze SHA 并宣布恢复 Alpha。

### R3 交付目录（新增；不得覆盖旧 R2 receipt）
- docs/integration/market_event_bridge_r3/CI_PINNED_SHA_PORTABILITY_REPAIR.md
- docs/integration/market_event_bridge_r3/FUNDING_ASOF_AND_MARK_PROVENANCE_REPAIR.md
- docs/integration/market_event_bridge_r3/PUBLIC_SOURCE_QUALIFICATION_CRITERIA.md
- docs/integration/market_event_bridge_r3/FINAL_L2_REQUEST_REPORT.md
- evidence/v0.6/b_line/market_event_bridge_r3/R2_FAILURE_REPRODUCTION.json
- evidence/v0.6/b_line/market_event_bridge_r3/EXACT_DEPENDENCY_SHA_AND_CONSUMER_WITNESSES.json
- evidence/v0.6/b_line/market_event_bridge_r3/FUNDING_LATE_ARRIVAL_DECIMAL_NEGATIVE_BATTERY.json
- evidence/v0.6/b_line/market_event_bridge_r3/PUBLIC_SOURCE_CHANNEL_QUALITY.json
- evidence/v0.6/b_line/market_event_bridge_r3/PROXY_ROUTE_REDACTED_DIAGNOSTIC.json
- evidence/v0.6/b_line/market_event_bridge_r3/TEST_CI_EXACT_FINAL_CODE_SHA.json
- evidence/v0.6/b_line/market_event_bridge_r3/FINAL_SOURCE_MANIFEST.json

**最终严格输出**：TASK_ID, AUTHORITY_REVIEW_SHA, BASE_SHA, FINAL_SHA, COMMIT_PARENTS, ALL_CHANGED_PATHS, ORIGINAL_R2_CI_ROOT_CAUSE, B_AND_C_PINNED_SHAS, PINNED_CODE_FETCH_AND_SHA_VERIFIED, R2_TESTS_RUN_PASSED_FAILED_SKIPPED, R3_NEW_TESTS_RUN, C_FUNDING_AVAILABLE_AT_SOURCE_PROVEN, MARK_FRESHNESS_AND_SOURCE_VALID, DECIMAL_CASH_CONSERVATION, REAL_PUBLIC_LAST_CLOSED_COUNT, REAL_MARK_COVERAGE_SECONDS, REAL_AGG_TRADE_COUNT, PUBLIC_DEPTH_SEQUENCE_CONTINUITY, LIVE_SOURCE_QUALIFICATION_LEVEL, CLASH_SECRET_REDACTION, ACTUAL_FINAL_GITHUB_CI_ID, ACTUAL_TEST_JOB_STEP, PRIVATE_ACCOUNT_ORDER_CALLS=0, PROTECTED_ACCESS=0, TERMINAL_VERDICT.

合法终态仅：
- R3_PORTABLE_CI_AND_PIT_FINANCIAL_PASS__PUBLIC_SOURCE_VERIFIED;
- R3_PORTABLE_CI_AND_PIT_FINANCIAL_PASS__PUBLIC_SOURCE_PARTIAL_OR_UNAVAILABLE;
- R3_ENGINEERING_GATE_BLOCKED_WITH_EVIDENCE.

绝不出现“所有测试/策略全绿”却使用 docs-only CI、跳过 B/C 或将 15 秒行情短测冒充 2分钟以上完整连续数据的结论。Codex GPT-6.1 Sol 额度不是完成本任务的依赖。Controller independent L2 后才决定真实前向数据观察和新策略预注册授权。
