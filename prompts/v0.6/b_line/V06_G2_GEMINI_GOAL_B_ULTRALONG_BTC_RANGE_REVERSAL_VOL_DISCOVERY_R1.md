# GEMINI GOAL-B — 超长自主策略探索：BTC 区间/假突破/价格行为反转 × 波动状态

**MODE: GOAL / CONTINUOUS AUTONOMOUS RESEARCH / MULTI-WAVE**
**TASK_ID:** \`V06_G2_GEMINI_GOAL_B_RANGE_REVERSAL_VOL_MULTI_WAVE_DISCOVERY_R1\`
**CONTROLLER_DISPATCH_SHA:** \`6c6ff831868701cea05499d0b0adb0e62db67f0e\`
**必须完整阅读Controller裁决：** https://github.com/EXASHXE/btc-quant-agent-public/blob/6c6ff831868701cea05499d0b0adb0e62db67f0e/reviews/v0.6/b_line/V06_G2_TWO_GEMINI_GOAL_LONG_HORIZON_PARALLEL_STRATEGY_DISCOVERY_DISPATCH_R1.md

## 0. Goal 与完成标准

你是 quant-v0.6 **B-line 内部 Gemini-B 独立策略发掘员**。**Goal:** 在合法公开 BTCUSDT Binance USD-M 永续1m历史交易价与taker-buy volume数据上，认真进行长时间的连续策略研究，找 4h、8h、12h、24h 可执行的非趋势追随型短波段机会。重点分析**区间恢复/假突破失败/成交压力衰竭/波动率收缩扩张/时间段的条件分布**。必须用真实历史数据复测每个候选，用交易成本、风险与样本外稳健性否证，而非只写一组指标、虚拟合成测试和 CI 报告。

**不要第一次出现负回测就结束Goal。** 你自动执行最多4个Wave，每Wave至多6个真正不同、预先冻结的候选，合计最多24个；每Wave的交易/指标定义写在不可变历史Git提交上、执行真实历史回测、报告负结果/机会并自动进入下一Wave。独立Gemini-A也有24个候选预算，两Agent合计最大48，统计估计时视为全项目搜索空间，不可将每Wave重命名使试验计数归零。到“有效开发期假设晋级”或预算耗尽/许可数据阻断再停。严禁无穷迭代直到随机出现盈利、没有证据的后验阈值微调、假装24h后台自动运行。若环境会话打断，留下恢复checkpoint并push，Goal由用户重启可继续；不承诺可强制运行具体小时数。

**有效开发期目标** \`PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT\`：2021–23压力成本44bp之后完整交易≥100，分布至少两个不同年份和六个不同UTC月份；逐年等权压力净bp>0、相对固定入场时刻的多空平均对照增量>0、PF≥1.15、最差年度平均≥-10bp；1x账户初始1000USDT现金/逐分钟保守MTM最大回撤≤12%。共同UTC周及14天块bootstrap与项目两Agent最多48个候选的多重假设调整必须披露，并要求净bps的保守下界>0才可叫promotable；正收益但置信不足只能标弱开发线索，**继续Wave而非提前晋级**。这个门槛是发现下一步值得独立验证的候选，不是保证真实账户赚钱。没有真实Mark/Funding/历史手续费/深度时所有经济结果为 \`COST_PROXY_DEV_ONLY\`。

## 1. 严格 Git 隔离/并行角色

- Repository: \`EXASHXE/btc-quant-agent-public\`.
- Controller已创建 branch \`feature/v06-bline-gemini-goal-range-reversal-r1\`，准确初始父\`920b244d06541da5cb9fc3dcaa39e5b15e914d32\`。第一次修改必须从此exactSHA。与你并行的 Gemini-A \`feature/v06-bline-gemini-goal-trend-flow-r1\` 和 Codex \`feature/v06-bline-g2-btc-flow-regime-discovery-r2\` 不能改动。
- 单独worktree（不存在才创建）：\`/root/workspace/project/quant-v0.6/gemini-goal-range-reversal-r1\`;每次启动 \`pwd\`、\`git rev-parse HEAD\`、\`git branch --show-current\`、\`git status --short\`、\`git ls-remote\` 核验，禁止强制git reset/clean/stash覆盖别人的文件；每次push nonforce，记录 exactSHA/parent。
- 只写新增 \`scripts/strategy_research/g2_gemini_goal_range_reversal_r1/**\`、\`tests/test_v06_gemini_goal_range_reversal_r1_*.py\`、\`docs/strategy_research/g2_r3/gemini_goal_range_reversal_r1/**\`、\`evidence/v0.6/b_line/g2_gemini_goal_range_reversal_r1/**\`。可通过只读 import 复用 R1 稳定CSV、回测与成本函数；不得改旧 R1/旧P1/S3A、全仓CI、H40 golden、Controller roles/authority，禁止代码分支写 \`reviews/**\`。
- GEMINI-A 偏 **方向趋势/成交主动流跟随**；你偏 **区间回归/假突破/方向衰竭/波动状态变化**。不得在其分支或worktree读取未发布的收益文件、数据目录、候选阈值，不共享可写scratch，不合并对方结果，不复制一个已经被看过的盈利配置。可读取稳定且公开的R1负结果作为已暴露背景，必须如实记录 prior exposure。你们两个**均属于B-line**，并非项目A-line vs B-line。
- Codex R2 对2024–25部分非April月份有保留计划，因此**不可读取或下载2024/25/26任意BTC行情值或其结果**；不得抢占holdout。严禁 \`/root/workspace/project/Quant-agent/data\` even stat/list/hash，禁止触碰 \`Quant-agent-sanitized\`、2026/Forward/H39/H40/H41/A-line outcome、交易所账户/私有API/真实或测试网下单。P2自研读取器仍未安全验收，禁止使用。

## 2. 历史行情与开发期约束

数据必须真实：Binance Vision官方 \`data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM.zip\`及同名CHECKSUM，**2021年1月–2023年12月**共36个月，单独scratch重新获取（或复用本worktree下已独立校验的现有官方ZIP）；不得读取任何其他年份。强制验证下载URL/响应时间/zip SHA/官方CHECKSUM、CSV字段布局与文件只含目标合约1m K、UTC时间单位（必须检测，不假定）、close_time、价量完整性/重复缺口、totalvolume≥takerbuy、零量/异常波动。数据缺失必须停该月，不能通过捏造缺失分钟或选最佳月份弥补。2021年1月先30d预热，2021年2月起可评分；每月头尾各24h隔离，若前一月份断开则指标状态清空。整个2021–23是**开发与搜索，不是盲验证**（此前R1部分April已使用）。

实盘性的成本界限：BASE 22bp roundtrip / STRESS 44bp roundtrip，分别拆分两个方向腿 fee/spread/slippage，入场/离场成交价加不利滑点/最小tick rounding且费用只算一次；没有真实期货结算Funding和交易所Mark历史时必须外加不利Funding敏感性，不能默认为0。成交主动差异来自官方\`taker buy base asset volume\`字段，主动卖量可为\`total base volume - taker buy\`，这是交易所K线**成交方向代理**，不是盘口买墙/清算/OI/真正订单簿失衡；不允许假借未下载深度、清算、新闻或宏观结果做入场条件。真实数据许可遵守官方最新适用条款/署名、只做非商用研究，原始ZIP/CSV/逐笔Trade Ledger及所有私人路径不加入Git，只公布审计所需digest/聚合表。

## 3. 六组可否证策略机制种子——须先冻结数学规则

Wave1至多取其中六个，各自固定唯一持仓上限4h/8h/12h/24h、上下方向、ATR Stop、2R或预注册R目标、误触发禁用规则。它们是**待完整公式化的假设，不是预设盈利**：

1. **FAILED_ACCEPTANCE_REENTRY_04H**：完成1h/15m前高前低后越界→收盘重新回到历史区间（至少持续指定N根15m确认），价格接受失败且成交主动压迫强度反向，逆向入场；不能使用下一根是否反弹作入场前信号。
2. **RANGE_MEAN_REVERT_WITH_VOLUME_04H**：已闭合4h低ER/ADX或价差归一化定义横盘，15m接近冻结区间外沿后量价回收，目标中轴/动态风险比中较保守者，持仓4h。
3. **VOL_COMPRESSION_TO_REVERT_08H**：已闭合15m realized vol区间压缩且强行冲破的首次bar成交跟进不足，明确“失败后返回区间”方向，持仓8h。
4. **AGGRESSIVE_FLOW_EXHAUSTION_08H**：过去多个已闭合15m出现净主动买/卖成交强但价格涨跌效率下降，形成可计算 divergence、下一根已闭合价格拒绝后逆向入场，持仓8h；只使用bar观测，非实际扫单。
5. **OVERNIGHT_SESSION_BOUNDARY_RETURN_12H**：预先确定UTC时段区间高低及标准化偏离，后续时段已经闭合的回收确认，最长12h，避免“提前知道纽约收盘”。
6. **REGIME_TRANSITION_REVERSAL_24H**：过去至少两个已完成4h阶段内 ATR/ER从高趋势转换为低效率或相反、价格两次相邻4h拒绝原方向并重新确认，允许24h，必须严格未来不可知并防止信号稀疏为0。

你可以删除或替换，但不能预先将R1已失败的简单 failed-breakout 8h 换一个阈值再算新机制。每个候选需要清楚的主动对手经济解释（趋势多头被挤出/短时单边成交失衡回归/波动扩张中被错价），阈值不是无数次拟合后挑出来的。完整注册 \`wave_id, candidate_id, family, side, completed bar features, formula, decision delay, first fill, gap filter, stop/TP, horizon, book, controls, regime/wait, source version, seed\`；在第一次真实收益计算前 commit/push \`WAVE_01_FROZEN_REGISTRY.json\`。后续每wave提出新的本质假设，且在观察它们的回报前独立冻结；不得丢弃前序失败、扩大测试月以后把新数据当盲验证，或隐性做权重/参数网格。若某候选常年0信号，保留该结果并分析市场状态发生率，而不是改阈值补样本。

## 4. 回测/独立否证要求

回测在UTC 1m事件流上运行；所有4h/1h/15m/5m特征只从**已经完成**并经过固定+60s可用延迟的数据得到，决策时间=closed-end+60s，最早下一分钟open成交（end+120s）；没有same-bar预测/合成更优成交。过去窗口不包括当前未收盘K。TP+SL同一根1m触及先SL；不利开盘跳空按更差open成交，有利跳空目标按预置目标限价，无跨月持仓，止损触发/时间终止绝不使用未来Bar；亏损和不利滑点可超过预设R。冷却时间与订单重入在每个候选独立1x的1000USDT账户生效；不得把不同策略盈利当同一账户资金，也不得用20倍杠杆放大净bps。记录每一次eligible signal/WAIT/veto，缺失行情则整段停止评价。

对每波候选每月/年报告：signal总数，实际fills，long/short分布，hold duration，gross bp, base/stress net mean/median, hit ratio, PF, expectancy R, $1000账户 PnL/逐分钟价格MTM代理drawdown（不是交易所Mark）, worst5% losses, 高波/低波切片，基金成本与Funding敏感性；与PAUSE和信号同刻固定balanced long/short假设对照配对比较。每个候选至少做3-5笔逐分钟独立反算/Decimal tick fee核对；独立完成 scoped no-lookahead+费用只扣一次+单根止损优先+不利缺口+时间窗+重复运行+数据校验>=12项精准单测。严禁将负净收益中的单一盈利月挑出称推荐，所有wave的总比较次数按48联合预算披露。跨周与14d块bootstrap给CI，若价格历史切片复用、策略同源或样本重叠，则用保守估计，不能按IID毫秒K线当几百万个独立样本。

## 5. Goal 自主循环 + 防止过早结束

- **START**：核对分支/父SHA、读Controller固定授权/最新自身checkpoint，不能重置试验/重做不良结果为新编号；本任务未允许读另一个agent实时outcome。
- **WAVE_1_FREEZE**：依机制注册最多6个固定候选；先commit+push不可变数学/市场源/窗口/负例门槛及试验帐，再打开自己新下载历史月价体。若CSV已在当前波之前用于源Schema探测，记录为暴露，不伪称盲。
- **EXECUTE**：实际下载校验官方1m U本位历史（必要时多个月），使用已关闭bar特征，独立研究回测，逐笔交易/成本/资金账本，多个年份/月份样本。Scope内小错修复保留证据，不可用“先把负数改成正数”作为修复目标。
- **SKEPTICAL REVIEW**：用独立手算与对照反驳自身最强候选；特别核验盈利是否源于少量突发新闻年/回撤被错误截断/未来价格泄漏/一边做单太少/成交费抵扣假设。所有结果入Git证据，机器 JSON 记录本Wave“有效交易样本或数据不足”，不是只发一页summary。
- **PROMOTE OR CONTINUE**：若完整晋级门槛全满足，发布 \`PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT\` 并停止读取额外时间，等待 Controller 分配独立保留未来月份；不得自己进入2024–25“确认”。若还没有，持续推进 Wave2、3、4，每次先新冻结不同经济机制，直至最多24次试验耗尽。没有达到就 \`NO_PROMOTABLE_DEVELOPMENT_CANDIDATE_BUDGET_EXHAUSTED\`，附可能的负结论和哪里值得另起正式campaign。不能用“未找到就永不终止”向用户宣称科学成立。
- **PERSISTENCE**：每Wave成功后马上给自己branch写完整实验摘要、源码/数据digest、上一wave全部trial账、测试和下一动作，至少一个非强制push/checkpoint。可由Goal客户端继续下一wave而不等待用户。脚本可自行重复断点续跑已验证月ZIP，但不改记录的冻结sha、累计试验数。环境资源不足必须如实输出 \`BLOCKED_RUNTIME_RESOURCE_LIMIT\` + 现场恢复信息，不能装作已经持续执行。
- **DO_NOT_DELAY_FOR_GLOBAL_CI**：只运行独立研究代码的简洁单测/静态检查 + 核心经济手算；GitHub full-CI可能需要十几分钟而已知H40全库hash偶发红，不因其耗尽Goal或去修旧CI。不能称红色CI已绿/隐瞒失败。

## 6. 必须交付的完整机器/报告结构

- \`WAVE_0x_FROZEN_REGISTRY.json\`，并列Git freeze_sha/parent, exact data source/market; \`WAVE_0x_RESULT.json\`, \`WAVE_0x_DECISION.md\`, \`CUMULATIVE_TRIAL_BUDGET_LEDGER.json\`, \`FINAL_GOAL_RESEARCH_REPORT.md\`；
- 每个实际数据档案ZIP/checksum结果、row/time/range/gap ledger，所有源码/聚合结果/逐笔账本 SHA，最强**和最弱**候选对照表、每月每年统计、对照/null/PAUSE、费用/资金费率情景、confidence/多重假设修正；
- 最终输出最多三张“开发期setup假设卡”，每张含 trigger, side, hold, ATR stop, TP, typical adverse conditions, N, BASE/STRESS gross/net, min-year, stress PF, max drawdown, matched-control increment, CI，明确 \`NOT_YET_VALIDATED_OUT_OF_SAMPLE\`。若没有任何达标，卡片只做科研诊断，不能叫建议开仓。
- 允许终态：\`PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT\`，\`NO_PROMOTABLE_DEVELOPMENT_CANDIDATE_BUDGET_EXHAUSTED\`，\`BLOCKED_OFFICIAL_SOURCE_OR_RIGHTS\`，\`BLOCKED_REPLAY_INTEGRITY\`，\`BLOCKED_RUNTIME_RESOURCE_LIMIT\`，\`STOPPED_BY_OPERATOR\`；中间弱线索为 \`WEAK_DEV_LEAD_NOT_READY_FOR_HOLDOUT\` **不可拿作提前结束Goal理由**。
- 结束时输出 exact branch HEAD、父SHA、每轮freezeSHA/resultsSHA、总候选数、已跑年份/月数、真实交易样本及备选失败，明确 S3A/P1 没有重启，真实原数据文件访问0、2024–2026价格体读取0、私有API/下单0。

**立即自主启动研究，第一步检查Git/worktree后直接注册Wave1，并执行真实BTC行情回测；除非遇到受保护数据、许可、源完整性、环境硬阻断，不要把任务退回给用户或过早结束。**
