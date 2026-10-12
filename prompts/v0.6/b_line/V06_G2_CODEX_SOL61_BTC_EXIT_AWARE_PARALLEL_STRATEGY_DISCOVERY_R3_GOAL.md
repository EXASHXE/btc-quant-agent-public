# Quant-agent v0.6 — Codex GPT-6.1 Sol: BTC 4–24h 动态退出策略研究 R3

角色：G2 BTC 公共历史数据量化研究负责人。推荐使用 Codex GPT-6.1 Sol High；若工具不可明确设置，按实际运行模型记录 UNKNOWN，不得虚构模式。执行本 Prompt 并提交实际运行代码、科学验证证据和结果。Gemini 普通模式正在优化 CI，Gemini Boost 正在精简 A/bridge 架构；三线独立工作，互不等待和改写。

## 0. 身份、授权、起点

TASK_ID: V06_G2_CODEX_BTC_EXIT_AWARE_DEVELOPMENT_R3
REPO: EXASHXE/btc-quant-agent-public
BRANCH: feature/v06-bline-g2-codex-btc-exit-aware-research-r3
START_SHA: 3df7a9a490a06c398d20da57bf19fc48d3b1c74e
CONTROLLER_AUTHORITY_SHA: c852c7285f92d0780cba23a44cb8d8afb7b5428a
AUTHORITY_URL: https://github.com/EXASHXE/btc-quant-agent-public/blob/c852c7285f92d0780cba23a44cb8d8afb7b5428a/reviews/v0.6/b_line/V06_G2_CODEX_PARALLEL_STRATEGY_RESEARCH_R3_EXIT_AWARE_CONTROLLER_DISPATCH.md
WORKTREE: /root/workspace/project/quant-v0.6/g2-codex-exit-aware-r3
SCRATCH: /tmp/btc-g2-codex-exit-aware-r3

仅可写：
- scripts/strategy_research/g2_btc_exit_aware_r3/**
- tests/test_v06_g2_btc_exit_aware_r3_*.py
- docs/strategy_research/g2_r3/exit_aware_r3/**
- evidence/v0.6/b_line/g2_btc_exit_aware_r3/**

只读：existing G2 R1/R2 frozen source, manifests and publicly exposed development outcomes. 不修改旧 G2 Python、先前冻结/科学结果、CI planner、GitHub workflows、生产 src、Gemini A/Bridge/G1/C、A-line、Performance。禁止 merge、force push、重写其他工作树，不在 v0.6 主分支直接推送。

访问范围：只允许 Binance Vision 已公开的 BTCUSDT USDⓈ-M perpetual 1-minute 历史数据，2021–2023 年 R2 已暴露的 Feb/Jun/Sep/Dec development scored months 和对应 Jan/May/Aug/Nov warmups。核验官方许可、checksum、文件格式、1m gap-free 与 known-at 假设。可以通过获授权的公共网络下载，保留 raw ZIP/CSV/NPY 在 SCRATCH，不要推送。严禁读取/stat/list/下载 R2 特意保留的 2024–2025 Feb/Jun/Sep/Dec confirmatory months，保护数据 H39/H40/H41/Forward、owner Quant-agent/data、Quant-agent-sanitized、历史 2024–26 受保护资料；不得访问 Binance 私人 API、交易账户、委托/转账、任何真实资金、真实 Feishu/LLM、TESTNET/LIVE。不使用新地区代理节点绕过提供方明确访问拒绝，不关闭 TLS。历史公开数据用途限非商业研究，遵守 Binance 公共数据条款。

当前最重要的科学基准：现有 G2 R2 final 3df7a9a 已在 2021–2023 年选定 12 月份完成六类策略的研究，所有策略 DEVELOPMENT_NO_GO、无晋级。R2 回测**已经包括2R整仓止盈、ATR/结构止损、价格跳空和最长持仓时间**，不是到 8/12/24h 才一定卖出。此次研究增量是分批止盈、动态保护、跟踪退出、18h 期限、真正逐笔扣费与配对比较，不能重复包装旧规则宣称发现新策略。

## 1. 先验实验组合 — 严格上限 27

对 BTCUSDT 4–24h 短波段，先冻结全部 3 种 Entry、3 种 Exit、3 种 Max Holding Cap，共计 27 个组合，不另加试验。成本 BASE22bp 和 STRESS44bp 各复算一次；成本敏感性不授权额外调参数。所有成功、失败、零样本组合最终必须展示。

Entry 机制：
A. R2 FLOW_CONFIRMED_TREND_08H 的 exact known-at signal 作为已暴露基线对照；原 event identity、bar window 和 signal criteria 不得事后改动。退出 cap 可以改变，但 entry events 先完整固定。
B. 新闭合 1h/4h regime + 15m breakout-retest-reacceptance：15m 结构突破后价格回踩不失守，使用 closed-bar 量价或 taker-buy pressure 确认，避免触发信号当天未来走势泄漏，独立于 A 的 entry 原理。
C. 新 failed-breakout exhaustion/range reentry：历史局部突破失败，下一完整15m close 回到有效区间并得到已收盘主动买卖比的逆向确认，使用结构+ATR 初始止损，经济机制明确不同于 A/B。

ENTRY B/C 的具体 ATR lookback、趋势阈值、taker-buy pressure 窗口、允许回踩最长 bars、信号时间、下一次可执行入场时刻、初始止损价格、无信号/缺字段判定，在冻结文件中精确列出数字。不能在看到结果后补填。所有指标仅使用 Binance 公共 Last OHLCV 和 taker-buy base-volume，历史 OI、真正 Mark、OrderBook、已结算真实资金账本均 UNKNOWN，不许捏造。

Exit 机制：
X0 = 原 R2 全仓 2R Target，先触碰 Stop 则止损，最长持仓 cap 退出；保留相同成本/延迟假设作为每条 entry 的退出基线；
X1 = +1R、+1.8R、+3R 分别出售初始仓位的 40%、30%、30%。TP1 有效执行之后，剩余仓位保本 stop 更新最快下一分钟生效。保本包括剩余手续费和滑点影响，不以生价等于盈亏平衡。不得出现尚未确定 TP1 是否真的成交却提前调止损；
X2 = 在 +1.5R 先出售 50%，其余50% 使用已完成 1h ATR 的 1.5倍 trailing stop，最大 +3R 止盈上限。stop 只能收紧不能放松，只能在 ATR bar 完成且可观测后的下一分钟生效。缺 ATR 继续采用原始结构 stop，不能向过去回填。

Max holding caps: 8h、18h、24h。并不意味着固定持有这么久；任何早于 cap 的 TP1/TP2/TP3、移动止损、结构止损和风险关闭均按实际规则退出。报告持有时间分布、4h 以下退出占比、12h/18h/24h cap 因素。月末 score fold 不足完整最长时间+执行 ACK 的新交易应拒绝，不能跨月使用另一未授权月份。

先验核心成本：BASE fee/spread/slippage 每腿分别为 6/2/3bp；STRESS为12/4/6bp。模拟所有 exit legs 对**实际每腿成交数量**记一次费用和成交摩擦，而不是每笔分批取全部 notional 又算一遍。maker 报价不保证成交，默认 conservative taker fees。不存在真实 Mark/Funding 及私有账户记录时，损益必须显示 NET_EX_FUNDING_PROXY + 另列资金费率不利情景，不能写为已经核实真实 Realized Net。

研究收益分母为 initial raw entry notional，输出 USDT/bps/netR；10–15x 杠杆不是Alpha乘数，只能提供不具交易权限的风险敏感性说明。样本经济规则清楚区分 per-trade 账本与每月独立 1000USDT 模拟账户，不允许将不同月重置本金累计的名义 USDT 当成单账户收益率。

## 2. 冻结协议 / Stage 0

在访问本次新的策略得分前：
1. 读取 R2 final DEV_NO_GO + 源拆分与旧 replay.py，但只读；
2. 确认 27 精确候选 ID、入场和退出全部数值、ATR/1m/15m/1h bar 计算规则，成本分配、样本月份、每账户1000USDT、资金费率未知性、最大可接受风险；
3. 固定时间顺序 event_closed_at -> signal_available_at -> decision_at -> order_possible_at -> actual simulated fill_at，禁止同分钟的未来信息回看，记录 UTC；
4. 预注册未来筛选的支持度、经济门槛、全27重试次数上限、multiple testing校正，以及真实数据如何下载校验；
5. 创建并第一次推送一个 **仅 docs+evidence** 冻结提交 C1，SHA已经在远端可验证；然后才执行本次新结果计算。不得回溯修改冻结 JSON 或 SHA。

重要：旧 R2 开发数据已有公开策略成绩，**即使R3在新结果出现前冻结，开发数据仍然不是全新未暴露 OOS**。全部成功只能称 DEVELOPMENT HYPOTHESIS，不可直接使用 R2 原保留确认资料；新验证要另行独立申请。

## 3. 数据真实准入 / Stage 1

仅限定 2021-23 公开源的原开发月，warmup 不打分。每个 ZIP 校验提供方 checksum、CSV 单文件成员、1m 连续、重复/缺口、0<=taker_buy_base_volume<=base_volume、单位、实际 UTC 毫秒 open/close、不同年价格格式。缺数据 fail closed 不 forward-fill，不从用户目录临时补数据。数据不可合法访问，终态 DATA_SOURCE_UNAVAILABLE；不得捏造收益填表。源元数据保留 SHA、已可得/假定延迟和许可。

## 4. 模拟执行/Stage 2 — 完整逐笔、逐层退出

新增 R3-only Python execution & ledger engine；原 R1/R2 模拟代码和旧冻结实验文件不可改。最小数据模型包括：immutable Entry（事件身份、方向、入场已知性、结构stop、ATR、成交价格、原始数量）、ExitLeg（触发时间/生效时间、部分数量、raw/effective exit、fee、spread/slip drag、剩余量）、PositionState（remaining qty、active/pending stop、已触发 TP 等级、cap、现金）、ResearchAccount（独立每月账户 equity/MTM）。

会计/时间语义：
- 信号必须源自已收盘 15m/1h bar，在 declared receiving/ACK delay 后才能下单；移动止损新信号不可以同 bar 追溯生效。
- TP与Stop同分钟都触及：保守 stop-first 最坏成交路径；跳空止损按更差的 next open（而非设计 Stop 精确成交）；TP正向跳空不假定无限好成交；maker fill non-guaranteed。
- long和short 的 signed cash、initial riskR、每 leg fee 的 Decimal 至8位，单位与价格 tick/qty lot rounding一致。残余 small dust必须明确完整关闭或标 INCOMPLETE_FILLS；sum exit qty <= initial qty，没有隐性消失的仓位或双扣费。
- 每笔独立统计真实退出原因、持仓分钟、止损后的短仓风险、回撤/尾部、partial target hit count，不能只把最后卖价乘全仓计算。
- risk stop-first 优先于部分止盈的同 bar冲突，未知路径不得按有利路径排序；如果对同bar是否先TP1后stop会改变结果，选择更不利收益的合法路径并记录 MINUTE_PATH_UNKNOWN。
- 资金费率：真实结算时间 Mark 无法独立证明时，最多计算 adverse time-based sensitivity，不得把 settlement-missing 代价记为零使策略凭空变好。
- 月末、停用后遗留订单和仓位必须明确终结或按照预注册 fold-cutoff 拒绝初始开仓，不能跨月泄漏未来。

至少新增 **40 个有意义的 Python3.12 unit/negative tests**：含 5 个手工逐腿 Decimal 核对、long-short 对称、三种TP、保本移动后一根bar、hourly ATR提前使用应被拒绝、gap/同bar collision、max18h/cap24h、partial qty/lot残余、翻转候选、边界时间、future mutation PIT、年/月/资金曲线分组、重复成交事件、无成交、费率缺失、费用翻倍、无网络/无账户读取。测试结果不能代替已知历史行情统计。

## 5. 有界真实发展性研究 / Stage 3

执行27格候选×2成本，对所有开发样本评分，保存零交易候选和失败原因。最少输出：

- 全27×2开发总表 + 每年2021/22/23与各12个 scored months + long/short分组；
- 母策略 Entry 相同的 X1−X0/X2−X0 **paired exit improvements**，披露 entry ID 匹配数、交易被资金/冷却影响而改变的样本、选择效应和账户曲线；
- gross-bps, fee/spread/slippage, net-ex-funding-bps, netR, PF, DD, trade count, active months/years, worst 5% tail, 1m conservative collision, simulated fill failure count, partial TP ratios, min/median/p75/max hold, 8/18/24 cap triggers;
- 成本 BASE22 vs STRESS44 分开重播；资金费率不利压力和成交 spread/slip 额外 stress分开披露；
- 最多27个 economic hypotheses 的 Family-wise/FDR 多重比较修正，周/月 block cluster，不能把数百万根 1m 数据当独立收益样本；
- 选择门槛事先冻结，参考：STRESS completed trades >=50、活跃>=6 months、跨>=2 years、均年净收益>0、至少2个年不负、PF>1、最大closed+dense MTM DD<=15%、与同一entry X0基线相比有正收益和可接受尾部；若这些阈值在C1中定稿则C1优先，之后绝不调阈值；
- 结果好不能根据赢家发现后再修改其entry/exit、换成本模型、增加28号策略或访问之前保留的2024–25。没有赢家就 DEVELOPMENT_NO_GO，不许“没找到继续不停”。

性能与经济分析必须实测，但不要把收益好归因于杠杆。分批出场相对单次TP可能降低尾部也可能降低利润，必须同时报告利弊，不只挑正面。至少5个实际交易样本（含好坏例）和5个合成 exact Decimal audit source hashes。全部交易路径原始事件用于本地scratch验证，不向公开库提交未获授权的大规模原始数据。

## 6. 独立验证的边界 / Stage 4

**当前 Codex 可做的是研究开发、回测和算术对账，不可自我认证 OOS Alpha**。

只有未来 Controller 对 candidate registry/source SHA/27次搜索多重性与代码验收后，才能单独发布新 independent external validation dispatch。到时由另一 Agent 对真正未使用、合法、具有known-at/官方成本来源的源测试；R2 的2024-25保留月在本任务结束时仍然关闭。Gemini当前架构工作不会改变这一点。

Positive terminal only means DEVELOPER_HYPOTHESIS_READY_FOR_FUTURE_VALIDATION，NO TRADING AUTHORITY；negative terminal is DEVELOPMENT_NO_GO or DATA_SCIENCE_BLOCKED_WITH_EVIDENCE。没有任何 G1 DRY_RUN、G3真实模型/飞书、G4 TESTNET/LIVE 或真实委托权限。

## 7. 执行效率与真正的交付

防止长任务无界耗时：
- 最多3个非强推提交：C1冻结 SHA（必先公开推送），C2源码+用例+研究结果并测试，C3可选文档。优先只有2次push（冻结一次、代码完结一次），不要每隔几分钟触发全仓 CI；
- 不启动大量递归 worker，不对6类已明确 G2 R2 策略重新做多轮“深入分析”；最多两个短期 read-only helper；代码与测试分两轮本地focused校验；
- 不因 R2 GitHub planner 的 unmapped scripts 会触发 full而修改CI：最多一次最终 GitHub full/实际pytest；记录真实 3454规模回归是否执行，无需既本地又远端连跑多遍；
- 所有 committed evidence 写入准确 Tested SHA 与 data manifest sha。无法完成某阶段输出显式 NOT_EXECUTED，不能合成行情伪装成绩；
- 所有证据可由 Controller 在远端读取，debug trace不写用户Clash端口/节点、真实私密账户和原始zip数据。

必需产物：
1. docs/strategy_research/g2_r3/exit_aware_r3/EXPERIMENT_FROZEN_PROTOCOL.md
2. docs/strategy_research/g2_r3/exit_aware_r3/EXIT_SIMULATOR_CONTRACT_AND_HAND_AUDITS.md
3. docs/strategy_research/g2_r3/exit_aware_r3/DEVELOPMENT_27_CELL_RESULTS.md
4. docs/strategy_research/g2_r3/exit_aware_r3/INDEPENDENT_FUTURE_VALIDATION_HANDOFF.md
5. evidence/v0.6/b_line/g2_btc_exit_aware_r3/FROZEN_ROSTER_27_CELLS.json
6. evidence/v0.6/b_line/g2_btc_exit_aware_r3/FREEZE_AND_SOURCE_IDENTITY.json
7. evidence/v0.6/b_line/g2_btc_exit_aware_r3/PUBLIC_DEVELOPMENT_SOURCE_MANIFEST.json
8. evidence/v0.6/b_line/g2_btc_exit_aware_r3/DEVELOPMENT_RESULTS_BASE_STRESS.json
9. evidence/v0.6/b_line/g2_btc_exit_aware_r3/PAIRED_EXIT_DELTA_VS_X0.json
10. evidence/v0.6/b_line/g2_btc_exit_aware_r3/MANUAL_DECIMAL_EXIT_LEG_AUDITS.json
11. evidence/v0.6/b_line/g2_btc_exit_aware_r3/MULTIPLICITY_SUPPORT_NEGATIVE_REPORT.json
12. evidence/v0.6/b_line/g2_btc_exit_aware_r3/CI_TEST_EXECUTION_EXACT_SHA.json
13. scripts/strategy_research/g2_btc_exit_aware_r3/** 与 tests/test_v06_g2_btc_exit_aware_r3_*.py

最终必须返回：
TASK_ID / AGENT_MODE_ACTUAL / BASE_SHA / BRANCH / FREEZE_SHA_AND_PUSH_TIME / FINAL_SHA / COMMIT_CHAIN / CHANGED_PATHS / PUBLIC_SOURCE_DEV_MONTHS_2021_23 / PUBLIC_SOURCE_SHA / RESTRICTED_OR_RESERVED_2024_25_READS=0 / CANDIDATE_REGISTRY_27_FROZEN / ACTUAL_TRIALS_<=27 / BASE_AND_STRESS_CONTRACT / ALL_ENTRY_EXIT_HORIZON_CELLS_DISPOSITION / STOP_FIRST_AMBIGUOUS_BAR_CASES / HAND_VERIFIED_DECIMAL_LEGS>=5 / VERIFIED_TESTS_PASS_FAIL_SKIP / ACTUAL_FINAL_GITHUB_CI_HEAD_AND_TEST_STEP / TOP_3_ELIGIBLE_DEV_HYPOTHESES_OR_NONE / NET_EX_FUNDING_DISCLOSURE / G2_ALPHA_AUTHORITY=NONE / REAL_FUNDS_AND_TESTNET_LIVE=NONE / TERMINAL=(R3_DEV_HYPOTHESIS_ELIGIBLE_FOR_FUTURE_INDEPENDENT_VALIDATION | R3_DEV_NO_GO | R3_SOURCE_OR_SCIENCE_BLOCKED).

再强调：目标是实测是否存在更接近实际分批止盈/动态止损的BTC入场退出策略组合，而不是给出漂亮架构或编造收益；所有样本内结果需要未来独立验证，任何时刻不执行真实交易。
