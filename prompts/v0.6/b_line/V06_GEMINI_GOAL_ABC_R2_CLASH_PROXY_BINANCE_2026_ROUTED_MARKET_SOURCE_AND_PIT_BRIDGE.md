# quant-agent v0.6 — Gemini Goal R2：Clash / Binance 2026 Market Streams / A-B-C 联调

你是 Gemini 高复杂度工程执行 Agent，负责 Linux/Windows-WSL2 网络、Binance USDT-M 公共数据、事件时钟/盘口和资金账本的一致性。以可实际运行的程序、负例测试、GitHub 提交、机器报告作为终点；不得只交付规划文字。发现环境阻塞时给出真实分级、完整本地可重复功能和有限终态，不许编造行情或篡改测试。

## I. 身份、边界、固定快照

TASK_ID: V06_GEMINI_GOAL_ABC_R2_CLASH_ROUTED_PUBLIC_SOURCE_PIT_BRIDGE
CONTROLLER_AUTHORITY_SHA: acf59828f878f3b1cc56e257dd952a8cd2c9ea97
AUTHORITY_URL: https://github.com/EXASHXE/btc-quant-agent-public/blob/acf59828f878f3b1cc56e257dd952a8cd2c9ea97/reviews/v0.6/b_line/V06_GEMINI_ABC_BRIDGE_R2_CLASH_AND_2026_BINANCE_ROUTED_STREAM_CONTROLLER_AUTHORITY.md
REPO: EXASHXE/btc-quant-agent-public
BRANCH: feature/v06-bline-gemini-abc-clash-routed-feed-bridge-r2
EXACT_START_SHA: df00997f344eba82f7cca0d03ee1617948abee44
WORKTREE: /root/workspace/project/quant-v0.6/gemini-abc-clash-bridge-r2
SCRATCH: /tmp/btc-abc_clash_bridge_r2
DEPENDENCY_B_READ_ONLY_SHA: 51cdd4e17503fbd18ad22aaeeaba3580f5efacf8
DEPENDENCY_C_READ_ONLY_SHA: 91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b
ORIGINAL_G1_CORE_READ_ONLY_SHA: 861a9d148f72db00e6079e53af78220bdd7e84ce

允许修改的路径仅：
- scripts/integration/market_event_bridge_r2/** 
- tests/test_v06_market_event_bridge_r2_*.py
- docs/integration/market_event_bridge_r2/**
- evidence/v0.6/b_line/market_event_bridge_r2/**
- A 公共数据采集网络层的最小修复：scripts/market_data/forward_public_feed_r1/connector.py、cli.py、新 proxy_route.py 以及 tests/test_v06_forward_public_feed_r1_*.py。

不得修改原 A 的 contracts.py、durability.py、order_book.py 等其他模块；不得修改 B/C/G1 的任何代码或报告，不 cherry-pick、不 merge、不 force push、不覆盖受保护数据，不改 .github 或生产 src/**。B 的研究预注册已经因为提交后算法修改、无效 freeze SHA 而 INVALID；本任务仅可使用 B 的工程接口，不能宣称新 Alpha 及科学验证。

不可读/list/stat/open：用户 Quant-agent/data、Quant-agent-sanitized、H39/H40/H41/Forward、2024–25 保护 holdout、旧 2026 受保护记录，任何个人交易账户或凭证。
禁止：API key、listenKey、UserData 私人通道、任何订单/撤改单、转账、私有 Binance REST、交易 Testnet/Live、真实资金写入、真实飞书/LLM API 调用。
只允许：显式 opt-in 的官方 Binance USDⓈ-M BTCUSDT 公共 GET 与公共 WebSocket，无认证、无订单，公共数据临时观测不得冒充受保护数据或独立 Alpha 样本。

现有 A 已经离线工程验收：完整 CI Python3.12 3194 passed, 2 skipped；但旧实时烟测仅 REST SSL EOF、events_received=0。这不能证明数据源在线。

## II. P0：必须首先修复 Binance 2026-04-23 WebSocket 升级

查并锁定官方资料（日期/URL/字段证据写入 docs）：
https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect
https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Important-WebSocket-Change-Notice
https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly
https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Order-Book
https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Get-Funding-Rate-History

2026-04-23 起 Binance USDⓈ-M Market Streams 对未经分类的旧 /stream URL 不再推送 Market 类消息，必须使用独立路由：
- 深度 Diff. Depth：wss://fstream.binance.com/public/stream?streams=btcusdt@depth@100ms
- 成交、Kline、Mark：wss://fstream.binance.com/market/stream?streams=btcusdt@aggTrade/btcusdt@kline_1m/btcusdt@markPrice@1s
- REST 深度快照：GET https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=1000
- REST 已结算 funding：GET https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=N
- 用 /private、dapi、spot、ws-fapi、未路由的旧 market URL 或将 market/public 混进一条错误 WS 均为 FAIL-CLOSED。

两个路由必须各自拥有连接 epoch、心跳、订阅/断线、backpressure 指标；不同的 provider E/T 与 ingress wall、monotonic 到达时间不得混为一谈。任何不同连接间 Mark/Last 对齐必须在接收后基于最大 available_at 发生。设置 24h 之前有界重连、防止 websocket session 意外永久失效，并按最新官方消息/订阅速率要求限流。必须提供测试证明旧路径不能交付 Mark/Kline，而新 market/public 显式路由配置正确，不能仅修改字符串即宣称通过。

## III. P0：考虑用户 Clash/Mihomo 节点，重点 Windows 主机 ↔ WSL2

用户 Windows 系统可能已运行 Clash Verge/Mihomo 等客户端，工程在 WSL2 Ubuntu。不要自动认为 localhost:7890 可用或把 9090 controller 当网络代理。Clash 的 port、socks-port、mixed-port 可能自定义；TUN 与系统代理可能不覆盖 WSL2；WSL2 NAT/Mirrored 的 localhost 行为可能不同。不得自动修改用户 Clash 配置、节点订阅、Windows 防火墙、allow-lan、bind-address、external-controller，更不得广泛扫描网络端口。

权威参考：
https://wiki.metacubex.one/en/config/inbound/port/
https://wiki.metacubex.one/en/config/general/
https://websockets.readthedocs.io/en/16.0/topics/proxies.html

必须实现可运行的、输出脱敏 JSON 的 network-diagnostic CLI，并展示以下步骤：
1. 确认 OS/Python、WSL2 网络类型、容器命名空间，无法确认则 UNKNOWN。检查代理环境变量是否存在与 scheme，不打印密码、token、出口 IP、订阅 URL、原始节点名称。
2. 只对用户明确指定的本地代理 host:port 作 TCP 探测；或只作 loopback / 安全检测出的 Windows gateway 的低频探测。不可扫描局域网/节点列表，不使用 external-controller API 改节点。
3. 明确四层链路：本地代理端口 TCP → HTTP CONNECT 或 SOCKS5h 协商 → 官方 REST 域名的端到端 TLS 验证与 GET → 分类 public/market WSS 的 TLS Upgrade 和真实合法数据帧。CONNECT 成功不能当成行情源成功，HTTP 200 不能替代 Mark/Last/Depth 源正确。
4. 程序参数必须有 --network disabled|public-direct|public-clash-explicit（默认 disabled）、--proxy-kind http|socks5h、--proxy-host、--proxy-port、--duration-seconds、--report-out；提供含占位符的 Windows Clash GUI 和 WSL2 调试命令。绝不硬编码 7890/7891/7892/9090 为必然值。
5. Python websockets==16.0 使用 connect(proxy=explicit_url) 或 proxy=None 来阻断隐式系统代理；SOCKS5h 须按官方规范安装 python-socks[asyncio] 并显式说明远端 DNS。REST urllib ProxyHandler 或受限客户端也必须走同一个显式路由，不能 REST DIRECT、WS PROXY 混用。route_epoch 变更后全部盘口必须重新 snapshot+diff 连接，不沿用旧 book 状态。
6. 保留 TLS 主机名与证书链验证；禁止 ssl unverified / curl -k / requests verify=False、明文打印代理鉴权、提交任何秘钥。不得悄悄降级到 DIRECT 或自动轮换 Clash 节点；用户在 Clash GUI 选择的节点才能作为固定 probe 路由。若 provider 明确 403/451/区域政策拒绝，则 SOURCE_BLOCKED_BY_PROVIDER_POLICY 并停止；不得将其视作挑其他地区节点绕开限制。SSL EOF/DNS/TLS reset 要按失败阶段分类，不能一律说是地区限制。
7. 禁止重写已有 raw 记录的 as-of；route_epoch 改变/系统时钟回退/源数据晚到 => CLOCK_UNCERTAIN、SOURCE_DEGRADED/UNAVAILABLE 和重新 bootstrap。
8. 仅在 Stage 0～3 离线测试完成后、网络权限明确时执行时限 15–90s 公共 smoke；节点未配置时任务仍应完成离线工程，报告 PUBLIC_SOURCE_UNVERIFIED 而不是伪造成功。允许用户在 GUI 自行切换后再次有界测试，但 Agent 不改节点。
9. 测量 REST GET 成功率、TLS 握手、WS Upgrade、mark/aggTrade/kline/depth 合法帧计数、首帧时延、p50/p95/p99 端到端滞后、抖动、重连/掉包、source quality；不需要存公网 IP，不留下无人值守 daemon。

网络错误映射至少支持：NETWORK_DISABLED, PROXY_PORT_CLOSED, PROXY_AUTH_REQUIRED, PROXY_CONNECT_FAILED, DNS_RESOLUTION_FAILED, REST_TLS_EOF, TLS_CERT_INVALID, BINANCE_ROUTING_INVALID, WS_UPGRADE_FAILED, WS_CONNECTED_NO_EVENTS, MIXED_EGRESS_ROUTE_REJECT, CLOCK_UNCERTAIN, SOURCE_BLOCKED_BY_PROVIDER_POLICY, SOURCE_UNAVAILABLE。

## IV. P0：固定 4 大跨分支数据不兼容，必须先复现再实现证明式适配

原始 A/B/C 契约只读锁定，不修改 B/C/ G1：
(1) A markPriceUpdate 是 E/T/p/i/r Tick，不是 Kline；B 现有 adapter 把 mark_price 当 1m Kline 解析，寻找 t/T/x/o/h/l/c，结果不可生成配对 Mark 1m bar。实现派生 Mark minute_close 时要求该分钟可验证的真实 Mark tick 覆盖，明确定义 coverage/jitter/gap/minute completed 的拒绝阈值；只能派生 DERIVED_MARK_1M，决不能将任意末笔 tick 伪装为官方 1m Mark Kline。必须有原始 source SHA/arrival 证据。若样本不足产生 NO_DERIVED_MARK。
(2) A BookIntegrityV1 的收据仅有 best_bid, best_ask, IDs, level count，无 bids/asks 真实 top10 价量；B P2 用 top10 notional imbalance。读取 A 同一已验证、连续的 OrderBookIntegrityEngine 状态（只读），产生 atomic book snapshot + source update_id + top10 ladders + hash。缺水平档位、gap、crossed、depth stale >1s 或跨 route_epoch => NO_P2_SIGNAL。
(3) A 官方 funding 接收 {fundingTime,fundingRate,symbol}，B 的 parse_funding_payload 读取 {T,r,p}，缺失字段默认为 0；这属于 FINANCIAL_BLOCKER。必须显式字段映射，强制过去已结算、真实 fundingRate、保留 producer arrival/settlement source/Mark known-at，避免 estimated 资金费率记现金。若不可提供可信价和时间，标 COST_INCOMPLETE，不许假定 0 Funding。用独立 Decimal 金额验证 long/short 相反现金方向、避免重复结算、绝不在 settlement_at 时刻倒填当时不可观测信息。
(4) A 原始 Last 1m Binance {k:{...}} 不符合 C 原有 MarketPitPort exact composite BAR {bar_open_ms,bar_close_ms,closed,last_open,last_high,last_low,last_close,mark_close,event_id}；通过严格匹配已闭合 Last 和已知 Mark 派生一分钟得到全新 composite BAR，同时保证 C 原代码及 G1 reducer 未改、资金账本不漂移。

每条派生输出记录至少：
schema/derivation_version、parent_event_sha256[]、raw_source_manifest_sha256、producer_upstream_SHA、route_epoch、connection_epoch、source_observed_wall_utc_ms、source_available_at_ms、derived_available_at_ms、feature_known_at_ms、clock_uncertainty_ms、quality、reason_codes、canonical SHA。
必须证明 feature_known_at >= 每个源 available_at，decision_at >= feature_known_at，禁止 provider E/T 替代。原 A raw 永久不覆写；无可信数据 => NO_DATA 而不是 forward fill。必须生成 INCOMPATIBILITY_BEFORE.json 与 BRIDGE_AFTER_SYNTHETIC_WITNESSES.json，展示原输入如何失败以及隔离适配后成功，且保持 B 科学身份仍 INVALID，未进行真实 forward PnL。

## V. 独立运行程序 / 质量标准

实施：可重放 fixture generator、严格 parse+validate、路由采集安全补丁、public/market 双连接、A→B 和 A→C 合成桥、对 C 的资金/权限负例、route diagnostic、断线持久化 receipt。

至少新建 **140 个可执行、独立有价值的 Python3.12 pytest**（不可只凭一个参数化样例凑数）：
- 20 Binance 2026 路由和分流端点、旧 URL 拒绝、Private/Spot/COIN-M 禁止；
- 25 Windows/WSL2 Clash HTTP/SOCKS/mixed、127.0.0.1 namespace、HTTPS/WSS、一致出口、DNS/TLS/407/403/451 与禁私密泄漏；
- 25 Mark/Last/PIT 时钟、离线一分钟 future mutation、late arrival、双连接 epoch、route switch；
- 25 Depth U/u/pu、REST snapshot、top10 真实价格和数量、跨源乱序、stale、符号/单位一致；
- 20 funding settled vs estimated、缺字段 0 默认保护、long/short Decimal、双重/迟到现金；
- 15 C composite BAR 和 G1 模拟不可变、WAL hash/replay、故障 quarantine；
- 10 安全/pressure stress：禁网络默认、节点切换、磁盘损坏、丢帧、真实网络结束无 daemon。
不得改原 A 已存在的测试来绕过失败，不能把 SKIPPED 统计为 PASSED。模拟的高频帧（>=3 个 deterministic 10–30 min 场景）测试 queue、latency p95/p99、CPU/mem、丢帧和 clock-uncertain；不可将合成吞吐指标冒充 Binance 实测。

指定命令至少提供：
- python -m scripts.integration.market_event_bridge_r2 --help
- python -m scripts.integration.market_event_bridge_r2 proxy-diagnostic --network disabled
- python -m scripts.integration.market_event_bridge_r2 fixture --seed 20261012
- python -m scripts.integration.market_event_bridge_r2 bridge-check
- python -m scripts.integration.market_event_bridge_r2 public-source-smoke --network public-clash-explicit --proxy-kind http --proxy-host <CLASH_HOST> --proxy-port <ACTUAL_PORT> --duration-seconds 60
- python3.12 -m pytest -q tests/test_v06_market_event_bridge_r2_*.py tests/test_v06_forward_public_feed_r1_*.py
使用用户在 GUI 选择的授权代理节点时才运行 public-source-smoke；网络源不允许/不可达只产生有界 BLOCKED 报告，不要无休止重试。

验收必须满足 Ruff+compileall+strict JSON validation，至少 140 新测试、本任务源码 SHA 的最终 CI 实际 pytest 步骤成功。若全仓库 CI 因旧 H40 FAIL，可接受明确记录唯一继承失败及独立 task tests 全绿，但不能声称 full CI 成功。保证最终 commit 与远端 workflow head_sha 精确一致。旧 A 的 3194 或 C 的 142 通过不是本任务的测试收据。

## VI. 五阶段 / 最多六个非强推提交（严格执行）

Stage 0: 读取授权和精确源码，锁定新分支起点，验证官方 WebSocket /public /market 2026 notice，独立复现不兼容，注册测试协议、接入和网络安全状态机。首 commit 并 push。
Stage 1: 实现 A 双路由网络代码和 explicit Clash HTTP/SOCKS (REST & WSS 同 route)、Windows/WSL2 诊断、可读日志不泄密、禁止 default egress。实现单元测试、提交。
Stage 2: 实现所有 A→B/C 因果派生、盘口与资金簿适配，独立合成 fixture 和 SHA 保护，不改 B/C。提交。
Stage 3: 新增 140+ 测试、10–30min 合成负载、process crash/restart、跨 epoch 与延迟滞后，全部离线和 CI run tests。提交。
Stage 4: 如合法/环境可达且有明确固定用户授权的 Clash 或直连路径，做 bounded 公共 smoke（快照、PUBLIC Depth、MARKET Mark/Kline/Agg）。只有真实且有源身份的事件才可标 LIVE_SOURCE_CONFIRMED；连接仅部分有效 = PUBLIC_SOURCE_PARTIAL。SSL EOF/Policy block => SOURCE_UNAVAILABLE/BLOCKED；无 proxy 设置 => PUBLIC_SOURCE_UNVERIFIED；绝不抓取私人源，不可在后台持续运行。
Stage 5: 汇总准确可验证 report、SHA manifests、测试矩阵、来源 URL、两个具体命令场景、负责人能直接运行的 Clash 配置 runbook、网络和策略 release 非授权声明；最终 push 并回读远端 exact SHA 与 CI。不得超过 6 提交，禁止 force push 或更改原 B/C 科学冻结。

## VII. 必须交付文件与终态

至少输出：
- docs/integration/market_event_bridge_r2/ARCHITECTURE_AND_CAUSAL_CONTRACT.md
- docs/integration/market_event_bridge_r2/BINANCE_2026_WEBSOCKET_MIGRATION.md
- docs/integration/market_event_bridge_r2/WINDOWS_WSL2_CLASH_CONNECTIVITY_RUNBOOK.md
- docs/integration/market_event_bridge_r2/CROSS_BRANCH_CONTRACT_ADJUDICATION_REPORT.md
- evidence/v0.6/b_line/market_event_bridge_r2/NETWORK_ROUTE_DIAGNOSTIC.json （严格脱敏）
- evidence/v0.6/b_line/market_event_bridge_r2/INCOMPATIBILITY_BEFORE.json
- evidence/v0.6/b_line/market_event_bridge_r2/BRIDGE_AFTER_SYNTHETIC_WITNESSES.json
- evidence/v0.6/b_line/market_event_bridge_r2/PIT_CLOCK_AND_SOURCE_HASH_AUDIT.json
- evidence/v0.6/b_line/market_event_bridge_r2/SETTLED_FUNDING_DECIMAL_LEDGER.json
- evidence/v0.6/b_line/market_event_bridge_r2/TEST_AND_CI_EXACT_SHA_RECEIPT.json
- evidence/v0.6/b_line/market_event_bridge_r2/FINAL_DELIVERY_MANIFEST.json

最终严格报告字段：
TASK_ID / EXACT_START_SHA / FINAL_REMOTE_SHA / COMMIT_PARENTS / CHANGED_PATHS / CONTROLLER_AUTHORITY_SHA / B_C_PINNED_READONLY_SHA / BINANCE_2026_ROUTE_VALID / CLASH_PROXY_TEST_ROUTE / REAL_REST_STATUS / REAL_PUBLIC_DEPTH_EVENTS / REAL_MARKET_MARK_KLINE_AGG_EVENTS / REAL_VS_SYNTHETIC_EVENT_COUNTS / LIVE_SOURCE_PROVENANCE / L2_TOP10_HASH_VALID / PIT_KNOWN_AT_VALID / FUNDING_REALIZED_DECIMAL_VALID / A_TO_B_AND_C_COMPATIBILITY / NEW_PY312_TESTS_PASS_FAIL_SKIP / A_REGRESSION / GITHUB_RUN_AND_ACTUAL_PYTEST_STEP / NETWORK_EXIT_PROCESSES_CLOSED / PRIVATE_ACCOUNT_OR_ORDER_CALLS_ZERO / PROTECTED_DATA_ACCESS_ZERO / REMAINING_BLOCKERS / TERMINAL_STATUS.

只能选择：
(1) R2_ABC_SYNTHETIC_BRIDGE_PASS__PUBLIC_SOURCE_VERIFIED：工程桥通过且合法的真实公共数据各关键通道有确凿事件与时间来源；
(2) R2_ABC_SYNTHETIC_BRIDGE_PASS__PUBLIC_SOURCE_UNVERIFIED：合成工程桥通过，但网络或节点/地区/政策缺口导致没有完整可靠真实源；
(3) R2_ABC_BRIDGE_FAIL_CLOSED：核心因果、网络安全、账本或消费者接口仍阻塞。

以上均不代表 Alpha、策略推广、生产 Feishu/LLM、TESTNET/LIVE 或实盘交易权限。Goal 要在有界工程范围内完成，而不是无限次改参数/求全绿/等待网络；如果失败就提交真实失败证据与下一步可执行修复建议。