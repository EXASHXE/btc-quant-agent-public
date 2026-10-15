# quant v0.6 — R8-D0 2-R 历史 Alpha 失败归因与至多两个假设蓝图 R1

**研究身份：** ChatGPT-2-R / Independent Research Scientist；不是 Controller 0、Auditor 1、Challenger 2-C 或 Operator 2-E。
**时间：** 2026-10-15（Asia/Singapore）。
**任务：** R8-D0；仅固定文档、已发布结论的 outcome-blind 归因和候选方法蓝图；**未运行任何历史策略、行情查询、回测、收益计算、实验或代码**。
**授权根：** Controller dispatch \`046113826f747b6397bda2df6c36d170be813223\`；本任务 prompt \`prompts/v0.6/b_line/V06_R8_D0_2R_STRATEGY_FAILURE_ATTRIBUTION_AND_TWO_HYPOTHESES_R1.md\` Git blob \`b1d6dcd81b64b494ada339e3bc62b1fff8a7b4b0\`；Controller dispatch direct parent \`d10653b8220521b6091ab69aa426657c479f6e3e\`。本文应仅为直接基于 dispatch commit 创建的隔离分支上的单一 ADD 报告；本文不伪造自身未来 commit/blob。
**AUTHOR TERMINAL：\`R8_D0_HYPOTHESIS_BLUEPRINT_READY_FOR_2C_CHALLENGE\`（仅 ONE 个条件式、待证伪的管理政策蓝图；ZERO 已通过来源或 Alpha 的候选；不自动派发审查）。**

## 1. 独立读取的固定证据账本与可信度

| 证据 | 精确身份（commit / blob） | 可依赖的边界 |
| --- | --- | --- |
| R8 Controller 阶段计划 | [R8 plan](https://github.com/EXASHXE/btc-quant-agent-public/blob/046113826f747b6397bda2df6c36d170be813223/docs/project/V06_R8_STRATEGY_FIRST_SOURCE_GATED_PHASE_PLAN_20261015.md) / \`efe6117ff148741072e24d3f3cf572cb21ad76fd\` | D0 仅文档研究，不允许新的历史评分 |
| 战略总登记 | [Validation register](https://github.com/EXASHXE/btc-quant-agent-public/blob/48e33dd722c276c48ce04a6bc4caf816c8b37a01/docs/project/V0.6_B_LINE_STRATEGY_VALIDATION_REGISTER.md) / \`bff9cecf93f249aec2c793fae6b398c25db61ee9\` | 已发表试验的 evidence status、既有试验族与暴露程度；不是新结果 |
| R6 科学状态 | [R6 roadmap](https://github.com/EXASHXE/btc-quant-agent-public/blob/48e33dd722c276c48ce04a6bc4caf816c8b37a01/docs/project/V06_R6_ALPHA_SCIENCE_STATUS_AND_PRIORITY_ROADMAP_20261015.md) / \`77d197e38496b9e2a23f403c26cfb6b545199207\` | 无独立正向 Alpha，仍有 PIT/资金费/经济完整性缺口 |
| R3 27-cell 原始发表结果 | [R3 result](https://github.com/EXASHXE/btc-quant-agent-public/blob/a69ccfdfd578bd0b7d3aa43d75959a659f969782/docs/strategy_research/g2_r3/exit_aware_r3/DEVELOPMENT_27_CELL_RESULTS.md) / \`dbcce8fb6ee125b7807d26b8398174ca70cac555\` | 全部 STRESS NO_GO；旧净值为 ex-funding 代理 |
| R4 已发表独立审查 | [R4 audit](https://github.com/EXASHXE/btc-quant-agent-public/blob/98c99ae2690c9e771f65e8ef9dc6a2124d8d6c3f/docs/strategy_research/g2_r4_independent_science/G2_R3_INDEPENDENT_SCIENTIFIC_AUDIT.md) / \`0d07215993e74c020e5ef98190601b668fd1d24d\` | NO_ADMISSIBLE_NEXT_STRATEGY_TRIAL；入场信息与退出效应尚未独立识别 |
| R6 T6 终止 | [Controller T6 STOP](https://github.com/EXASHXE/btc-quant-agent-public/blob/2b928dd8cd2428e635a20aec4b9b93d03dab7787/reviews/v0.6/b_line/V06_CONTROLLER_R6_T6_PA_B_R2_FINAL_STOP_HANDOFF_20261015.md) / \`5ea49d5a98a16f818d721f298de8c605f98ba67f\` | STOP = 实证不可识别；非负收益证据 |
| R7-L2 | [Controller rights decision](https://github.com/EXASHXE/btc-quant-agent-public/blob/f2fea1c90ff10b45d2bbd38bcd3a6f71ddc7e173/reviews/v0.6/b_line/V06_CONTROLLER_R7_L2_SOURCE_RIGHTS_AND_ROUTE_ADJUDICATION_R1.md) / \`04a45aaf166d8a986b03d2bf72b2cab013526ac9\` | prospective source 只可讨论文档权利/时钟，不授权采集 |
| R7-B0 | [REST/WS rights preflight](https://github.com/EXASHXE/btc-quant-agent-public/blob/d10653b8220521b6091ab69aa426657c479f6e3e/docs/project/V06_R7_B0_USDM_REST_WS_RIGHTS_AND_CLOCK_FEASIBILITY_R1.md) / \`8e451d14f002cab2f316c934416aa1be38081cf4\` | **REST_WS_RIGHTS_NOT_VERIFIABLE_STOP**；不等于普遍违法，也不等于可用 |

辅助原始已发布材料仅使用 Register 明确列出的固定研究结果身份：R1 public April \`920b244d...\`、R2 flow/regime \`3df7a9a...\`、Goal-A corrected \`d2477c1...\`、Goal-B \`b51a001...\`、Mark/Funding R3 \`057c47a...\` 和 R3.1 \`990c02b...\`、Exit-R1 \`55ac4c6...\`、F1–F3 \`f25954b...\`、v0.3.12 prereg \`ca647f23...\` / published conclusion \`8ecff4ec...\`。本报告没有重新提取样本收益或读取未发表历史标签。用户提及的 Sol 中文独立备忘录无已验证的 Git SHA/blob：**UNVERIFIED / ADVISORY ONLY**；任何其中的新增统计结论均未采用。

**证据等级：** 历史试验「开发期已发表结论」可信为其原有试验语境下的结果，不自动证明现实可执行价格；R7 权利与 PIT 为尚未准入的项目性阻断；本文机制推断为作者方法建议，待独立 2-C/1 反证，不是新的数据事实。

## 2. 历史失败归因：区分实证负面、统计不充分、账本缺陷及 SOURCE STOP

分类说明：NEG = 已发表成本假设下的负向开发结果；SUPPORT = 有样本数或有效周、年度稳定性不足；MULT = 同时推断/多重选择未通过；ACCT = 财务实现或身份修正；IDENT = 事件、时钟、权利、成本或成交不可识别；EXPOSED = 已暴露开发集；NONE ≠ 对 BTC 永久无效的证明。

| 历史族 | 冻结发表事实（不重算） | 主要归因与不可推断事项 |
| --- | --- | --- |
| 原始八个 tactical breakout / trend-pullback，多空 4h/12h | Register：BASE/STRESS 的平均净 R 均为负；最不负的 TREND_PULLBACK_SHORT_12H 仍为 BASE −0.129R / STRESS −0.349R | **NEG + EXPOSED**；只说明这些规则在冻结成本代理下不成立；换方向、换时窗、ATR 倍数属于同族重试 |
| G2 preliminary R1 | 无法证明合格真实信号决策 | **IDENT / METHOD_OR_SOURCE_BLOCKED**；无资格把缺失决策当零收益 |
| BTC April public R1（12 候选） | 五个 2021–2025 April 诊断窗，NO_STRATEGY_CLEARS_COST_AND_SUPPORT_GATE；April 2024/25 已暴露 | **NEG/SUPPORT/EXPOSED**；不是全 2024/25 新 OOS，真实可执行成本未识别 |
| BTC public flow/regime R2（6 机制） | 2021–23 12 折，0/6 promotions，DEVELOPMENT_NO_GO；部分机制极少事件 | **NEG/SUPPORT/EXPOSED + causal-ingress assumption**；flow 是 taker 买量代理，不是 OI 或清算；保留当期冻结 2024/25 特定月份 |
| Goal-A 24 臂原始报告 | 原经济算法 22/44bp 成本、净 PF、MTM 与声称不一致，另 W1_C06 事件身份缺陷 | **ACCT / IDENTITY**, 原始 NO_GO 不等于被完整可靠的经济实现证伪 |
| Goal-A 23 臂修正后价格回放 | 35 个打分月的 EX-POST DEVELOPMENT；STRESS 正值只存在极少、非稳健臂，未通过年度、样本及 MULT 门槛；第三个 8h flow collapse 仅 4 fills | **SUPPORT + MULT + EXPOSED**；不能从修错后的开发集正值推进 Alpha，也不能再后验选臂 |
| Goal-B 24 臂 / A+B 共 48 臂 | Goal-B 0/24 promotions；9 个费用前为正但 STRESS 44bp 无一获晋级；failed-breakout reclaim 等已有覆盖 | **NEG + MULT + EXPOSED**；breakout 假突破/回归/波动反转不是空白新领域 |
| 两个 12h leads：R3 → R3.1 | R3 由于 Mark/Funding 缺口 STOP；R3.1 补齐历史 Mark 后出现 W1_C04、W2_C05 稀疏 STRESS 开发均值为正，但 2023 为负，调整下界不支持晋级 | R3 = **IDENT**，不是负策略；R3.1 = **SUPPORT + MULT + EXPOSED**；历史 Mark/签名 Funding 不证明自身成交或原始第一接收时点 |
| Exit/Horizon R1 与 H18 | E0 12h、H1 18h、H2 24h、E1 1R partial、E2 partial+BE；H18 18h 延长收益集中于极少赢家，描述与正式经济记录存在叙述不符 | **EX-POST DIAGNOSTIC + SUPPORT**；不等于条件持有获验证；H18 Table 4 异常不能挑有利叙述代替底层记录 |
| R3 出场 27-cell | 入场 A/B/C × 2R/scale-out/ATR trail × 8/18/24h 全 27 STRESS NO_GO，N 5/34/35；不计入真实 Funding，历史深度与 ingress 未证实 | **NEG + SUPPORT + MULT + COST_INCOMPLETE**；历史并未只做 N 小时强制平仓；成功 CI 非 Alpha |
| W1/W2 exposed leads 与 F1–F3 | W1/W2 少数正向历史均值因年度及 multiplicity 失败；F1 n2、F2 n37 负、F3 n12 的正数只描述性，9/2/1 年度集中；max-T 零 SE 重采样退化 | **SUPPORT + MULT_UNCALIBRATED + BASIS_INCREMENT_UNTESTED + PIT_UNKNOWN**；不能用「换更低费率」追认旧臂 |
| v0.3.12 SPOT_PERP_TAKER_FLOW_SPREAD_1H | H32 INCONCLUSIVE_MECHANISM，H33/H34 FALSIFIED | **MECHANISM INCONCLUSIVE / FALSIFIED SUB-HYPOTHESES**；单改 sign/period/threshold/hold 不可重开 |
| PRICE_SHOCK_OI_CONTRACTION_REVERSAL / PERP_CROWDED_FAKEOUT | 真实 2021–23 OI 不可由价格恢复；OI draft 经独立审计 SOURCE_DRAFT_FAIL；fakeout NOVELTY_CANDIDATE_SOURCE_BLOCKED | **IDENT + rights/PIT + novelty**；OI 下降不是单边爆仓证据；不可合成 OI 补源 |
| R6 T6 PA-B 5m MTR first-vs-second maker | C01–C03 仅作者 R2 合成时钟修补；无真实 native origin、5m post-only ACK/queue/partial/cancel、Funding/Mark/账户效用，Controller 最终 STOP | **IDENT / EMPIRICALLY_INFEASIBLE**, **不是 NEG**；不能迁移到 18h 或 Sol R3-B 自动“复活” |
| R7-S0/R7-L2/R7-B0 | Vision 分类仅可能个人非商业非生产历史研究；持续 REST/WS raw 采集+留存+衍生研究权利仍无可核验肯定授权 | **RIGHTS_NOT_VERIFIED / SOURCE_NOT_ADMITTED**；没有当前可执行的行情研究许可或新 Alpha 试验权限 |

**因果解释限界：** 成本后失败 ≠ 纯入场预测信息已证伪；出场规则失效、入场纯噪声、样本量不足、强迫成交代理的偏差可能共存。相反，只有特定方法的负净值不能导出“再加一因子即有优势”。既有 2021–23 广泛重复使用、April 2024/25 局部曝光与 2024/25 特定 R2 保留月份必须分开记账；没有任何当期新观察可以被本文件解释为 virgin OOS。

## 3. 五个政策构件与识别对象严格分开

1. **Entry signal**：在外生于待比较管理动作的统一 origin 上，于 \`t_decision\` 选择方向/准入。原始八策略、R1/R2、Goal-A/B、R3、v0.3.12 都已施加继承选择负债；复制旧价差/反转/流入准则不是新 entry Alpha。
2. **Position management**：已执行仓位后的有条件继续持有、压缩或平仓决策；与原入场预测收益不同，estimand 是同一原始 episode 在两个动作规则下的终值之差。仅在「事先决策」「相同 origin 与先前交易轨迹」「真实后续来源/费用」同时存在时可识别。
3. **Exit**：stop、take-profit、partial、break-even、trailing、stop-gap、time-cap 均可能发生；既有 E0/E1/E2 和 R3 27-cell 已测试绝大部分朴素更改。ATR 倍数优化、固定 18h/24h 或“10/20/30% 分批”不能再被算作新 Alpha。
4. **Holding horizon**：策略最长 24h，非最少 4h；止损可更早。12h→18h→24h 固定 cap 已暴露，不能靠涨跌回看选择何时延长。任何新条件必须仅用 landmark 时刻之前可验证、完整到达的数据，并在全体 origin 上做 intent-to-treat，而非只汇报延长成功者。
5. **Execution mechanism**：public tape/Last/Mark ≠ 买卖报价/实际订单执行。Marketable/taker 比 passive maker 少一个队列反事实，但仍必须确认可交易 bid/ask/数量、延迟、market impact、交易所过滤、Funding、止损穿越及剩余现金、仓位、风险占用。策略获利推断必须包含从未入场、拒单/部分成交、NO_ACTION 和退出失败，而不仅是一组“成交的交易”。

### 统一账户效用目标（方法定义，非实测）

令 \`E_i\` 为事前固定的、不会因后续管理规则或收益而增删的外部 BTCUSDT 候选 origin。比较同一 \`E_i\` 下基准政策 \`P0\` 与替代政策 \`P1\` 从同一资金、风险、非重叠仓位约束开始，延续至所有对应风险与现金流结清的安全终值 \`W_i(P)\`。首要政策对比为 \`Delta_i = W_i(P1) - W_i(P0)\`；此外两政策分别相对 \`P_NO_ACTION\` 的完整终值必须成立。拒单、不触发、已提前止损、途中资金费率、无仓期、被占用资金、因仓位互斥而错过后续 origin 的机会成本都留在统一时间轴内，不能从分母中删除。对同源不同策略动作及同一周重复事件做 cluster/block 推断，不按独立 fills/分钟虚增 N。

## 4. 唯一保留的条件式假设蓝图 H-M1：12h landmark 因果条件持有

**研究级别：** \`METHOD_BLUEPRINT_CONDITIONAL_SOURCE_PATH\`；**不是一个新入场 Alpha、不是可执行方案、不是权限准入**。

**待证伪的机制陈述：** 在固定同一批事前入场原始事件和截至 12h 完全一致的交易路径后，只有在预先定义、先于决策已知的「方向性延续且结构未破坏」状态中，继续保留既有保护措施至最迟 24h 才可能提高全账户扣全成本效用；对不满足状态者于 12h 首个可成交时刻退出。此种 **time-dependent treatment interaction at a fixed landmark** 有别于旧 H1/H2 所有仓位一律延长，也有别于单纯 ATR trail、E1/E2 partial 或 R3 27-cell 不看 12h 状态的固定退出。这一论点须由 2-C 对 Exit-R1/H18/R3 的策略语义逐条核对，若等价则淘汰，不能换阈值规避等价性。

**同一比较群：** 一套未来独立注册、source-qualified 的 **外生候选 origin**，入场政策冻结不因为是否会活到 12h 而改变。保留所有原始机会：基准也无订单、资金/风控挡住、已在 12h 前 stop/target、无资格报价或 12h 时 source-unknown 均按既定 NO_ACTION/已发生路径记账；不能仅分析 12h 尚存仓位（否则幸存者选择）。账户占用与下一 origin 的阻断由共同调度器计入。旧 W1/W2 等只可作为历史定义/负对照与多重试验负债，不作为新样本筛选。

**候选动作合同（现在不冻结阈值、不进行 prereg）：**
- \`t0\` 为共同原始 episode 的 first-known/durable eligibility；\`t_entry_decision\` 只能不早于全部合格输入 first-known 及固定调度 tick；\`t_entry_ack\`、成交数量/价格由未来确实可观察、合法准入的订单与执行见证确定，否则 NO_ACTION。
- \`t_L\` = 对原始成功入场的同一确定性 anchor 加 12h 的候选判定时刻，而非行情成功时回溯选出的时刻；首个允许动作 \`t_action\` 严格晚于 closed bars、source first-complete-and-durable 与账户状态全部可用的最迟 UTC-safe-high，不能把 12h 的 bar close 当做响应时间。若已退出，两政策既有终止路径不重开。
- 二元状态 \`C_L\` 仅以 \`t_L\` 前已完成、到达且持久化的 BTCUSDT native mark/price 及滚动方向性进展与前定结构边界定义；候选信息族为 signed progress、已完成价格的 directional efficiency 与 adverse excursion（未终止结构）。**具体窗口、门槛、结构定义、入场家族、止损合约须由未来独立前注册一次性冻结；现阶段不能由旧收益挑选。** 当信号资料缺失、修订冲突或时钟无法证明时按预先指定 fail-closed 的共同动作，不倒填先前价格。
- 对同一个 12h 存活仓位：\`P0\` 使用冻结的 12h 限额、最早合规 marketable 清仓；\`P1\` 在 \`C_L=1\` 时 **仅改变一个动作**：不在 12h 主动平仓，保留相同已预先挂设的保护性 stop/target、最多到 24h；\`C_L=0\` 则执行 P0 相同退出。未到 12h 者同动作。不能同时偷偷改 ATR stop、规模、TP 梯度、入场阈值以获取多因子自由度。
- 额外 **P24 unconditional**、原 E0/E1/E2、R3 ATM/ATR trail 固定策略按既有试验定义作为不可重用成绩的 **方法等价性负对照**。可研究的独特增量是预先指定的 12h **C_L × 继续持有动作交互**，而不是无条件多持 12h；若无合法 source-qualified 事件，则 \`SOURCE_BLOCKED\`。

**唯一主要反事实/零假设：** \`H0_M\`：在 source-qualified、共同起始账户的全体外生 origin 上，\`P1\` 的 after-full-cost terminal account wealth 不超过 \`P0\`，并且任何看似增益都不能可靠超过冻结的无条件 24h 管理（控制已有多重选择）；替代假设要求增量的预声明下界正、相对 NO_ACTION 为正，跨独立周/年份不依赖少数极端赢家且尾部/资金占用不可接受损失不显著放大。这是 **相对于具体动作规则的策略政策效应**；即使成立也不证明新的 entry signal alpha。必须独立报告原始来源日历上的 NO_ACTION / invalid / missingness 母数，不能把“执行成功的持仓均值”替代账户净财富。

**所需未来因果源（全部 REQUIRED / NONE presently admitted）：**
- USD-M \`BTCUSDT\` native symbol/contract/version、tick/lot/minNotional、quote asset/size filters、真正 closed 1m/15m/1h price observations 与 bar end、trade IDs/sequence、mark/index cross-clock、同一 origin 的不可变去重/方向/结构边界；完整接收原始字节、payload hash/version、network/local first-complete、monotonic receive、UTC-safe-high/NTP error interval、durable fsync/ACK、correction revisions、watermark、gap/reconnect/route provenance、first-eligible scheduler tick。
- 入场与 landmark/退出时真实 bid/ask、top sizes 与必要 L2 depth/queue staleness、可成交 marketable size 的保守 impact 和 latency；交易所端 post-only 不是本假设交易方式；自身订单 ACK/reject/partial/full/cancel/stop-exit 确证仍是必需的实盘成本证据，不由公共 tape 捏造。
- 每条已成交 leg 的实际 maker/taker 身份、taker fees、bid-ask spread、滑点、冲击、数量约束与未成交/改价、触碰不成交、止损缺口和极端价格、instrument Mark、funding time/settled rate、真实持仓覆盖和 signed fee cash ledger、margin/liquidation risk、账户融资/占用与最终含未实现浮动风险的 NAV、错失的后续机会。BASE22/STRESS44 只是历史代理，**不是**真实成本上界。
- 来源/用途：Binance Vision 文档的历史非生产适用范围不得迁移给 REST/WS 或生产。R7-B0 对原始 prospective REST/WS 接收、持久化、衍生研究用途缺少肯定授权；因此 **不能合法性默认绿色**。须先获控制文件或官方书面用途权利以及 owner/Controller 独立来源许可；否则停在纸面蓝图。

**时间与统计下限（未来筛选设计值，绝非假定已具备）：** 建议未来首次可行性评估前要求 **至少 26 个彼此独立有效 UTC 日历周、至少 50 个 source-qualified 外生原始事件，并至少 30 个发生预定义不同行为的 12h landmark case，分布于至少 12 个独立周**，且有提前固定的功效分析证明对全成本最小经济增益、相关事件相关性、周块 bootstrap、年度稳定、尾部损失/容量与 inherited 家族控制具有足够鉴别力。以上是保守最低 *screening* 数，不是充分统计功效或收益预测；达不到即 STOP，达到也不自动授权试验。若目标约每 48h 一次在这些约束下无法满足，承认不具备可检验性，不降低计数门槛。所有过去试验（八策略、R1/R2、48 A+B、两个 leads、F、27 R3、H18/Exit）计入同一研究脉络，预先界定新的 primary familywise alpha budget 与 negative controls，不得视为一次全新独立机会。

**2-C 最强反对意见/独立 FAIL 测试：**
1. 构造不看收益的语义映射：若 \`C_L\` 条件退出事实上只是 E1/E2、R3 27-cell 的 ATR trail、固定 H1/H2、H18 的观察分组或原 entry filter 的替代命名，则 **NOVELTY_FAIL**。
2. 无成交或先在 12h 前退出仍纳入共同 origin；对 12h 存活者单独报告只能次要诊断。若 primary cohort 排除 loser、无仓、gap、NO_ACTION，**SELECTION_FAIL**。
3. 证明所有 state inputs 先到达且 durable，含延迟、跨源闭包、UTC 误差上界；缺失按共同 fail-closed，不得用当前修订价反写旧决策。否则 **PIT_FAIL**。
4. 对比冻结 \`P0\`、\`P24\` 和共同 \`P_NO_ACTION\` 的完整实际账户经济；任意不对称 partial/slip/Funding、无基线风险、持有延后跨资金费率而不记账，**UTILITY_FAIL**。
5. 最小周块/原始 origin/改变动作数或预注册家族预算不能成立，**POWER_OR_MULTIPLICITY_FAIL**。
6. **立即前置停机：** R7-B0 rights unresolved、源产品条款或合法用途不能证实、唯一所需 raw first-receipt/quote/Mark/funding/own execution 无可信路径时，**SOURCE_RIGHTS_OR_UTILITY_STOP**；不得移交新的实证授权。

## 5. 第二个方向：市场可吃单的价格/波动/regime 入场——明确排除，非候选蓝图

考察过的纸面类别：压缩后释放、波动扩张加速、假突破回收、价格 shock 回归、方向效率/流量持续、吸收/突变、先后反转/延迟进入。R1/R2、Goal-A/B、W2_C05、R3 27-cell、v0.3.12 H32–H34 和 T6 的共同门槛已明确覆盖其经济叙事或时间安排。将 passive maker 换成 marketable/taker **只改变成交假设和估值，不构成新价格信号**；把 1h 改 5m、加 volatility/RSI/ATR threshold 或把 OI 换成推断清算代理也不产生独立来源。更真实的 taker 成本可以用于将来的新 estimand 研究，但没有新价格信息或外生 episode 分离，无法在当前授权下称其为新可注册 signal。

**判定：\`H-E2 = REJECTED_OVERLAP_AND_SOURCE_STOP\`，不计入存活数量，不是第二个承诺研究或待实测候选。** 非价格的 native L2/order-flow、真实 OI 可能是将来不同的信息集合，但目前缺失权利、PIT 和有效样本，也禁止将未观察信号冒充当前第二假设。

## 6. 第一科学问题、终止/审查与后继权限

**只推荐一个 FIRST SCIENTIFIC QUESTION（信息价值优先，而非收益优先）：** 在 **不看任何新收益数据** 的前提下，能否正式写出一个 12h fixed-landmark 的状态条件 \`C_L\`，使它对相同外生 origin 的动作确实不同于 E0/H1/H2/E1/E2 与 R3 27-cell，同时仅依赖明确可受理的未来 source fields，且所有输入有一致 first-complete-and-durable 时钟？这比重新寻找一个 breakout 价格入场规则更容易通过文档语义比对被否定，依赖最少；若答案否定，H-M1 同样淘汰，终态随之是 \`NO_NEW_SOURCE_COMPATIBLE_HYPOTHESIS\`。

**研究风险/置信度：** 历史事实归因 HIGH（仅对应固定报告陈述），「条件政策区别于旧固定退出」METHOD-ONLY LOW/MODERATE，真实 source-feasible rights LOW/NOT VERIFIED，统计功效 UNKNOWN，净 Alpha NONE。一个可设想的因果指标 **不表示** 买卖进场 edge、胜率或收益率；既有 H18 winner concentration 是对该条件路线的强反证风险。

**尚未证实的事实：** 具体状态规则的新颖性、完整合法条款和当事用途、消息到达时钟/修订、可用的合格原始 source、完整实物成交成本、独立有效周与样本功效、完整账户财富、系统容量与真实 expected returns 全部 UNKNOWN。用户所说 Sol memo 无固定 Git 身份，UNVERIFIED；不得将其作为新的裁决来源。

**守护与后继：** 此作者文档 READY 仅表示 **可由 2-C 在未来另行有权任务中提出科学反对**，不代表 2-C、1 已审查或 Controller 已批准；**本任务不会自动派发 2-C、1 或新实验**。没有 source admission、交易、代码、回测、历史结果重新读取、模型训练、holdout、Git merge 的任何后续默许。

**AUTHOR END-STATE：**
- Surviving new conditional methodology blueprints: **1**（H-M1，非新 entry Alpha，尚待新颖性反证）。
- Rejected second signal attempt: **1**（H-E2，旧 signal 等价 / 数据权利阻断）。
- \`REVIEW_2C=PENDING; REVIEW_1=NOT_DISPATCHED; PREREG=NOT_AUTHORIZED; TRIAL=NOT_AUTHORIZED\`.
- \`SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE\`.
- Report author run: **documentation-only**，无本地测试、无 CI 触发/宣称；远端 commit/blob/diff 和实际 GitHub CI 须在提交后由单独 receipt 核验。
