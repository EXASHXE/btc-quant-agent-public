# GEMINI GOAL-A — 超长自主策略探索：BTC 方向趋势 × 成交主动性

**MODE: GOAL / CONTINUOUS AUTONOMOUS RESEARCH / MULTI-WAVE**
**TASK_ID:** \`V06_G2_GEMINI_GOAL_A_TREND_FLOW_MULTI_WAVE_DISCOVERY_R1\`
**CONTROLLER_DISPATCH_SHA:** \`6c6ff831868701cea05499d0b0adb0e62db67f0e\`
**必须完整阅读裁决：** https://github.com/EXASHXE/btc-quant-agent-public/blob/6c6ff831868701cea05499d0b0adb0e62db67f0e/reviews/v0.6/b_line/V06_G2_TWO_GEMINI_GOAL_LONG_HORIZON_PARALLEL_STRATEGY_DISCOVERY_DISPATCH_R1.md

## 0. 你的终极目标和长任务行为

你是 quant-v0.6 项目 **B-line 内部独立 Gemini-A 策略研究员**，不是项目 A-line Controller，不是 CI/安全验证器。任务不是写计划或输出看似合理的指标解释，而是：**在真正下载且校验的 BTCUSDT U本位永续历史1m行情上，连续探索有经济学理由的 4h、8h、12h、24h 方向策略，找到有多市场阶段支持、扣除成本后仍有正向开发期证据的候选，或用真实实验完整否证固定预算中的全部假设。**

**Goal 持续执行约束：** 不允许“提出4个想法—写些单测—得出继续观察”后结束。自行组织四个研究 Wave，先实现真实可重复行情数据与轻量回测，再依次推进理论构造、逐笔回测、成本、统计、否证与下一 Wave。只要没有达到证据晋级门槛、没有硬阻断、且预先定义的 4×6 候选预算未耗尽，就自动进入下一 Wave，不需要反复征求用户确认。严禁为了“直到找到盈利”进行无限调参或只展示盈利结果；最多 **4 Wave，每 Wave≤6 个事先冻结的不同候选，累计≤24**（另一个并行 Gemini-B 也≤24，合计≤48；跨 Agent 多重比较不可忽略）。连续运行受 Goal 客户端实际资源/会话/算力限制，无法自行保证运行时长；每 Wave 都必须持久化 Git checkpoint，以支持下次续跑。禁止空转、sleep、假装后台工作。只有拿到足够强的开发候选或预算耗尽/合法权限阻断才给终态。

**目标达成定义不是“保证实盘赚钱”。** 强候选 \`PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT\` 至少满足：2021–2023年合计≥100笔压力成本下完整交易，覆盖≥2个不同年份、≥6个UTC月份；每年等权的44bp压力成本后单笔净bps均值>0；相对同入场时间随机方向或平衡多空的预注册对照增量均值>0；压力成本下Profit Factor≥1.15；最差年份平均净收益≥-10bp；1x、初始1000USDT、明确仓位模型下的逐日/逐分钟保守账户最大回撤≤12%；按共同UTC周/14日块重抽样、并考虑两 Agent 合计最多48个试验后的**保守净收益下界>0**（样本不足则不得晋级，只能记 \`WEAK_DEV_LEAD\` 并继续下一Wave）。任何开发期达标都是待独立未来时间区间验证的假设，不是 Alpha，更不允许实盘推荐。

## 1. Git 身份、工作树、权限、分工

- 仓库：\`EXASHXE/btc-quant-agent-public\`。
- Controller 已预先创建分支：\`feature/v06-bline-gemini-goal-trend-flow-r1\`，**初始 exact SHA**：\`920b244d06541da5cb9fc3dcaa39e5b15e914d32\`。
- 必须使用自己单独的 worktree：\`/root/workspace/project/quant-v0.6/gemini-goal-trend-flow-r1\`。如果不存在，在主仓借助 \`git worktree add\` 创建；若已存在只核验 ownership/status/HEAD，不得覆盖/强制 reset/clean/stash。任何 Git 操作先确认 \`pwd\` \`git status --short\` \`git rev-parse HEAD\` \`git branch --show-current\`。初次 push 不得 force。
- **只新建你自己的文件**，允许：\`scripts/strategy_research/g2_gemini_goal_trend_flow_r1/**\`、\`tests/test_v06_gemini_goal_trend_flow_r1_*.py\`、\`docs/strategy_research/g2_r3/gemini_goal_trend_flow_r1/**\`、\`evidence/v0.6/b_line/g2_gemini_goal_trend_flow_r1/**\`。绝对不写 \`reviews/**\` 到代码分支；不改 R1 原始信号/回测/账本、Controller Authority、全仓CI、旧 golden。
- 并行 Gemini-B 分支 \`feature/v06-bline-gemini-goal-range-reversal-r1\` 和 Codex R2 \`feature/v06-bline-g2-btc-flow-regime-discovery-r2\` 正在独立研究。不得修改、切换、合并、cherry-pick 或窥视它们的未封存 outcome / worktree；也不得共享可写缓存。你主要研究 **方向趋势/量价主动流确认/高低时间框架结构**，不把 Gemini-B 的区间反转领域作为主体。两个 Gemini 都属于 B-line，并非主项目 A/B 两线。
- 原主线 \`v0.6\`、项目 A-line、Performance 不变。**严禁**对 \`/root/workspace/project/Quant-agent/data\` 做任何 \`stat/lstat/open/list/scandir/realpath/hash/read\`，绝不碰 \`Quant-agent-sanitized\`、2026任何结果、Forward/H39/H40/H41、用户 Binance 私有API/账户或真金交易。P2 S3A 自研读取器没有通过安全验收，**不要使用、修补或继承其真实路径读取器**；P1 engine 已终止，不要复活。

## 2. 实际行情和隔离

**官方来源** Binance Vision \`data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM.zip\` 和同名 \`.CHECKSUM\`，仅 BTCUSDT USD-M 永续，**仅允许读取2021–2023 UTC月份**，不能读取2024/2025/2026任何价格数据，哪怕官网公开。2024–25为 Controller/Codex 预留后置验证。行情只允许新下载的官方 ZIP/CSV 加密摘要核验，不允许依赖旧 owner 文件、Spot、Coin-M 或臆测OI/清算/盘口深度/Mark/Funding。先用每个ZIP的官方CHECKSUM匹配、交易所/合约来源、UTC毫秒/微秒实际时间单位、每分钟连续性、重复、缺失、OHLC自洽、taker-buy volume≤total volume检查。Binance 官方当期文件不等于历史发布时间PIT证据；明确标为 \`ARCHIVE_RECONSTRUCTION_DEV_ONLY\`。

指定首次可复核数据范围：2021年1月到2023年12月，36个逐月档案；如容量/源限制，按固定时间顺序下载、披露不可得月份，**不能跳到某个收益较好的月份**。每个分析评分月使用之前至少30天指标预热，2021年1月只能作预热，2021年2月起才可评分；完整月边缘留24h embargo，跨缺口不得拼接趋势。2021–23 所有开发结果可用于探索，但不能称它们是未见过的盲验证（R1已看过其中多个April窗口）。若数据不完整且缺失严重，报告阻断；不得补造K线。将ZIP/CSV/完整逐笔成交和每分钟账户账本保存在你自己不入Git的私有临时 scratch，源manifest、哈希、统计、实验代码入Git；遵守 Binance 数据当前条款与 noncommercial CC BY-NC-SA 使用限制，未经单独授权不商用/分发原始数据。

## 3. 固定研究假设方向；不是重复R1失败组合

先在 \`WAVE_01_FROZEN_REGISTRY.json\` 写明 Wave1 最多六个**有不同入场条件**的假设。首个Wave可以选择以下独立机制中的≤6项，**全部数学定义冻结在先，读实际 outcomes 在后**：

1. \`MULTISCALE_TREND_ADOPTION\`：4h EMA20/50趋势及斜率+1h较长结构确认；15m 价格不追最后一根极端棒，等待成交主动比率二次连续确认，止损以1h ATR尺度，持有8或12h。
2. \`PERSISTENT_TAKER_PRESSURE\`：前若干根已闭合15m K的signed taker-buy volume比率持续同向、强度及成交量归一化显著高于自己过去固定窗口，4h趋势一致，持仓8h。
3. \`MULTIHOUR_BREAKOUT_RETEST_WITH_FLOW\`：过去已闭合 4h/1h 边界突破后对该边界的15m再次接受，成交量/主动流确认，持仓4h或8h；不是复制R1 24h-hour retest条款。
4. \`ATR_EXPANSION_TREND_FOLLOW\`：长时间中等波动后的可观测波动率扩张和价格方向一致、且进入时不高于固定追涨gap上限，持仓12h。
5. \`CROSS_SESSION_CONTINUATION\`：UTC时段转换+连续2个已闭合1h趋势/量价同向，剔除不可交易低流动性，持仓4h或8h；时间区段及阈值必须事先固定。
6. \`PERSISTENT_TREND_24H\`：明确更长期4h结构上升/下降、累计主动流一致及当下15m入场，持有24h，必须有样本；如果无事件诚实记0。

你可以用更有经济理由的新家族取代，但**单Wave≤6，累计≤24**，每个都必须有 family-ID、经济机制、完整多空对称/非对称公式、观测列、时间可用性、15m/1h/4h窗口、静态趋势Regime、具体入场/止损ATR倍数/2R或不同已冻结TP/持仓终止/冷却、哪些情况下 \`WAIT\`、构造时可被否证的逻辑。不要在看到结果后仅把某个阈值0.3改0.35当“新策略”。Wave2–4可转向不同趋势机制，但每次先公开 exposure ledger 和新 roster 才评估。

## 4. 回测可信度 / 成本 / 比较

优先安全复用固定 R1 \`scripts/strategy_research/g2_btc_empirical_fast_r1\` 的 stdlib ZIP读取、确定性分钟成交重放、成本模型，只读/引用，不修正旧文件。如果独立最小对照发现其会造假（同棒前视、滑点重复或资金簿错误），在自己的代码里只作最小明确隔离并报告/独立对照，不得悄悄让原始错误“通过”。新行为测试≥12个：分钟close→available→nextopen、15m与1h及4h聚合无lookahead、双触发优先STOP、gap worse fill、timecap、资金/手续费只扣一次、1x限额、data-gap STOP、失真时间戳、复跑一致、随机方向control、drawdown。

每条交易输入最少：symbol/market, strategy-ID, Wave, side, signal_time, available_time, decision_time, intended fill time, actual fill raw/effective, fee, spread, slippage, size, max_hold, stop/target, exit reason/time/price, gross+net USDT/bps/R, capital/equity, no-trade reasons。使用**基础22bp/压力44bp名义往返成本**（两腿真实名义差异导致实际略偏；费用仅扣一次），资金费率若无可验证官方时钟及费率，不把0写作真实无费，出一个不利8h结算和hourly极端敏感性。真实 Mark/OI/L2 不存在则标未知；绝不把 taker-buy volume 称为现货净流入或真实买卖盘口吸收。杠杆不得放大策略净bp。

所有实验必须报告：全部候选每年/每月/各方向交易量， gross / base / stress mean/median bp，均值净R，trade + dense-equity drawdown，胜率、PF、资金利用/周转、持仓时长、最大单笔亏损/最差5%及滑点成本敏感性；逐年等权、周块/14日块bootstrap、不知道的资金费率敏感性。与PAUSE、同样信号时间固定多空配对control和简单无信号随机方向做比较；不能只选择盈利多头、最佳月份、最高Sharpe切片。

对每Wave输出至少一份完整机器\`WAVE_0x_RESULTS.json\`和简短\`WAVE_0x_DECISION.md\`，包含每笔交易ledger SHA、下载校验、参数冻结sha、全部fail、哪些信号未触发，下一Wave具体机制空间。每个Wave完成即commit/push一个**非强制 checkpoint**，确保超长Goal中断可续。第一checkpoint在读新行情outcomes前先push Wave1冻结manifest；以后每Wave先独立freeze commit或有可核验的 hash/time 先行记录，再实证并push结果。总提交数按checkpoint合理增长，不限两次，但不能几十个无意义提交。Scoped测试即可；GitHub 全量CI若已启动要如实报告红/绿，已知 H40旧哈希失败不要修。

## 5. Goal 自我推进算法

执行以下循环直到强候选、硬阻断或24个真实不同的试验预算用尽：

1. \`RESTART_IDENTITY\`：查远端分支HEAD及自己上次checkpoint是否匹配；读自身Wave日志，未完成wave直接续跑，**不要重启实验预算**。
2. \`FREEZE\`：先写Wave目标、各候选数学不等式、固定测试市场与成本、各自假设与试验序号及本次整个累计trial ledger；commit+push 或输出可验的冻结GitSHA。在实际市场下次数据扫描之前完成。
3. \`EXECUTE\`：校验官方数据；独立算信号，时间闭合，跑真实历史逐笔回测；有硬错先修必要的最小范围、保留失败回执，不引入未注册的策略。至少两个非重叠时段复测，避免单段高结果蒙混。
4. \`FALSIFY\`：核验代码无lookahead、成交与成本/账户守恒、非重叠时间/方向条件、稳健性及统计多重测试偏差；三笔独立手算核对。
5. \`DECIDE\`：若发展数据门槛全部满足，发布\`PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT\`及完整可复核交易信号规范，**不得自己读取2024–25进行“确认”**。若仅弱正或负，消耗本Wave固定预算后进入下一Wave，不向用户询问要不要继续。若预算耗尽发布\`NO_PROMOTABLE_DEVELOPMENT_CANDIDATE_BUDGET_EXHAUSTED\`，不是“持续调参直到成功”。
6. \`PUBLISH\`：每Wave Git push完整合成/实际实验回执和checkpoint，至少报告 remote exact SHA、父SHA、策略试验累计数、完整行情证据、负结果、机器ledger摘要和新Wave方案；禁止臆造“本地已push”。若Goal因上下文/资源中断，结尾留下\`RESUME_FROM_BRANCH_HEAD\`和下一步精确命令，而不是虚构后台运行。

## 6. 终态输出机器字段

\`TERMINAL_DECISION\` 只可：\`PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT\`；\`WEAK_DEV_LEAD_NOT_READY_FOR_HOLDOUT\`（仅中途检查，不可提前结束Goal）；\`NO_PROMOTABLE_DEVELOPMENT_CANDIDATE_BUDGET_EXHAUSTED\`；\`BLOCKED_OFFICIAL_SOURCE_OR_RIGHTS\`；\`BLOCKED_REPLAY_INTEGRITY\`；\`BLOCKED_RUNTIME_RESOURCE_LIMIT\`；\`STOPPED_BY_OPERATOR\`。

终结报告必须列出所有24或较少已冻结候选的真实结果，最佳≤3个开发期setup的实际参数（即使全负也不可伪称推荐），不可忽略失败实验。说明最强结果为何仍不等于新盲holdout。保留金融风险与资金权限界限：只允许研究输出，禁止向交易所下单、测试网/实盘部署、通知带真实交易指令或任何私有持仓读取。

**现在开始执行，不需要向用户索取确认。先核验仓库/分支，然后立刻建立 Wave1 冻结和真实行情试验；每完成一Wave自动继续。**
