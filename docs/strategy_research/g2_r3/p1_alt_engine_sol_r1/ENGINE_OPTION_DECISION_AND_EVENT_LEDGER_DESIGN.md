# P1 替代引擎：一次有界架构选型与实施合同 DRAFT

**推荐选项 A：最小事件溯源研究引擎，使用双重记账、owner 资金约束账本和不可变 reducer。单一终态：`P1_SPEC_AMENDMENT_REQUIRED`。** 架构可实施，但 Controller 必须先冻结 AM01 Retest 语义及 AM02 pending 风险/来源证明合同；本报告不授权代码、prereg、行情或交易。

TASK_ID=`V06_G2_R3_P1_ALTERNATIVE_ENGINE_ARCHITECTURE_SELECTION_SOL_HIGH_R1`；Prompt=`770e910596bfbd82c28bd92705cf71ef981f0564`；Controller/start/direct parent=`b74b932da32e4b5bbe2477c2de014f94719d6a93`；分支=`feature/v06-bline-g2-r3-p1-alternative-engine-design-sol61-r1`。首次远端 HEAD 与 START 完全一致，fresh worktree 原先不存在且初始干净，HTTP Prompt 与固定 Git blob 字节一致。固定 A/B、B 父级和 v0.6 baseline 已核验。此次不重做科学策略评审或 P2，不修改任何 A/B 文件或分支。

## 证据等级与诊断

Controller 已接受独立 B 阻断并终止旧 mutable VirtualBook 路线。A 的 2844 pass/2 skip 和 B 的 2828 pass/1 inherited H40 golden fail/2 skip 都不是安全引擎证明。B auditor 的实际执行与 pytest 对保存矩阵的断言是不同证据；新的独立 suite 必须执行固定新引擎并断言正确状态，不能仅断言旧 bug 存在。

B05 pending 已退出亏损消失，以及 B03/B07 应付款未完整占用资金，足以阻断现有模型。公开数值 −169.336545 是已接受合成 witness，本任务未重跑，未从其价格/数量猜测未披露费用分项。T16 将该数额作为明确标准化 journal 输入，不能宣称复现旧价格 fixture。

| Finding / 严重性 | 真实证据与可达性限定 | 替代规则与独立断言 |
|---|---|---|
| B01 / HIGH | Replay/Stage Mark 同 close 50000/52000 随输入顺序改变，迟到 48000 覆盖；Stage8 报告本身不是已证实决策前视。 | source/symbol/close 冲突无论排列都 fail closed；水位不倒退；经济报告变化不得影响早先订单。 |
| B02 / HIGH | ID set 忽略 payload 冲突，晚旧 ACK 可倒退 cooldown；这些是 staged/API 证据，不宣称每个任意 tuple 完整 replay 可达。 | ID→immutable payload、精确 owner/cause、无 auto-ACK；重复幂等，冲突失败；cooldown=max。 |
| B03 / CRITICAL | 1.00 payable、.40 reserve、.60 未覆盖；POS_1 substring 匹配 POS_10；S−5000 早 ACK 是非对齐 API 输入。 | owner/S 义务和 cover/shortfall 保留至 ACK；精确 ID；拒绝非分钟 step，不夸大 API witness。 |
| B04 / PRESERVE_PASS | 独立站立 stop/target/gap/minute-end/cooldown 样例通过，不覆盖所有 forced/time 分支。 | 纯退出函数保留 SL-first、worse open、target cap；接受方法要求 time/kill/reduction 有利 raw price 同样封顶。 |
| B05 / CRITICAL | 对齐 staged 生命周期注入订单/延迟 ACK 后，pending net −169.336545 被忽略、kill=false、available=933.7769；不是新市场 replay。 | 保留每笔可见 loss/fee；T16 标准化账本输入精确验证风险 830.663455，不杜撰原价格 fixture 费用拆分。 |
| B06 / HIGH + SPEC_BLOCKER | latest-only 小时推进跳过取消/极值；同 bar cancel/rebreakout 没有冻结语义。 | 逐根已完成小时 cursor；迟处理只更新状态，不补发过去订单；AM01 未冻结则停止。 |
| B07 / CRITICAL | Stage7 提前释放资金费覆盖，Stage1 side dict 破坏 owner 总和；公开 witness 941 vs conservative 940。 | 统一 owner ledger；T10 .40 cover + .60 shortfall 覆盖 payable1；ETH2 不动；ACK 前 free940，后940.05。 |

## 三方案与唯一选择

| 项目 | A | B | C |
|---|---|---|---|
| name | A：事件溯源研究微引擎 | B：NautilusTrader v1.231.0 + R3 适配器 | C：确定性事件归约器 + 属性 oracle |
| disposition | 选择；实施前须冻结 AM01/AM02 | 本任务拒绝采用；不否定该框架的一般能力 | 不单独采用快照资金模型；纯 reducer 技术纳入 A |
| surface | 9 个功能模块及 __init__，共 10 个生产文件；3 个实现方测试模块、1 个合成 runner；独立审计方另写 oracle。数量是拟定范围，不是工期承诺。 | 至少需要来源/时钟、撮合、ACK、资金费 owner 账本、风控资本、候选/独立 book 六类适配，以及集成测试；仍需自写核心资金模型。 | 约五类核心职责，较少模块不等于较少资金状态；补上审计分录后接近 A。 |
| state_and_events | 8 immutable records; 12 event kinds; 7 owner phases, an orthogonal permanent book-kill latch, and 5 Retest phases. | Framework state inventory not counted without implementation; additional R3 owner/reserve/payable/proof state remains unavoidable. No fabricated total. | Could omit posting/journal account types and retain state snapshots; same12 economic event semantics and owner liabilities still needed. |
| PIT | 经济执行、可见风险、ACK 现金分离；所有风险事件受 available_at 和来源证明约束。 | 固定版本文档规定 close ts_init 和合成 OHLC 路径；R3 仍需 +60s 可用性、下一分钟开盘及 SL-first。 | 纯函数不自动阻止未来 close 输入或跳过小时。 |
| funding | owner/settlement 子账保留条件覆盖、最终 payable、短缺，直到 ACK；关闭仓位不会删除义务。 | 原生资金费边界结算不证明 ±15s 所有权、延迟 ACK、短缺和关闭 owner 保留。 | 没有 owner 分录时仍可能重复欠款缺失、提前释放和聚合余额错误。 |
| eight_candidates | 八候选不变；仅捕获核验过的纯公式/值类型，重建生命周期和 Retest 状态。 | 可通过策略适配保留，但不能假设原生 netting、撮合和组合账户自动满足八个独立 book。 | 可保留公式，但仍依赖相同 Retest 规范裁定。 |
| testability | 每笔分录守恒、每个 owner 余额可重建；独立 oracle 不调用生产资本函数。 | 需框架集成验证与独立 R3 oracle；框架成熟不替代语义证明。 | 属性测试可能复用错误公式；须独立资金 oracle，不能只镜像实现。 |
| dependency_license | 标准库 Decimal，无新增运行依赖。复制项目源片段保留许可/来源说明。 | 官方 release/tag/commit 已固定；Python >=3.12,<3.15；LGPL-3.0-or-later 元数据和 LGPL3 LICENSE。编译平台、版本与分发义务增加集成风险；未安装。 | 无必需的新运行依赖；确定性排列使用标准库和已安装测试工具即可。 |
| isolation_migration | 独立新包、新分支；禁止导入或继承 VirtualBook，无伪兼容 wrapper。 | 可隔离，但需替换足够多原生行为，额外维护两套调度/账本语义。 | 独立新包可行；仅快照难以证明每次现金/覆盖变动的原因。 |
| incremental_benefit | 相比失败 A，资金权威来自统一账本而非 Stage1/7、ID set、side dict；pending 亏损不会随仓位删除消失。 | 成熟事件运行时对大系统有价值；本次小型 bar 研究无法抵销适配面。 | 保留不可变 reduce 技术；拒绝省略付款义务和 journal 的精简。 |
| stop | 未冻结规范或一次最终独立审计存在重大失败即停止，不进入 R4/R5。 | 不做原型或交易所探测；未来采用需新的版本/适配证明和权限。 | 不另开 C 原型；若 A 的最小完整范围仍不可行，应停止而不是删掉负债。 |

选项 C 的 pure reducer 技术纳入 A；不另做 C 原型。标准库与已安装测试工具优先，不增加框架依赖。A 的最小完整优势是：物理仓位消失后，owner 的亏损、费用、可能资金费和覆盖仍有可审计身份，直到 ACK。

外部 B 已真实核验官方 v1.231.0 release（2026-08-02）、annotated tag 和固定 commit `27a8e54e7ac3c57d6cbf8891f0283dfbaee97317`。固定 pyproject/许可证明 Python >=3.12,<3.15、LGPL-3.0-or-later；未安装。固定 bar 文档描述合成 OHLC 路径和缺少原生 next-bar-open 模式；R3 要求 SL-first、+60s 可用性和下一分钟开盘。固定账户文档的边界资金费结算仍需适配 ±15s 所有权、延迟现金 ACK 与 owner 短缺。固定 execution-flow 定义框架调度，但不证明 R3 语义。这里只判断本任务适配成本，不否定框架一般能力或宣称全部平台已验证。精确文档/许可链接在末尾。

## 实施前规范门

| 实施前门 | 待 Controller 冻结的明确决定 |
|---|---|
| AM01 / P3_METHOD_AMENDMENT_REQUIRED | 原 METHOD_DESIGN 未规定同一 bar 取消/确认/过期旧 Retest 后是否可注册新事件。建议该 bar 只终止旧状态，下一根不同小时才可注册；只是提案。首次确认应按小时顺序识别，即使策略 book WAIT 也不能事后挑下一次确认；各 horizon 独立消费。Controller 必须固定实际解释、version/root。 |
| AM02 / RISK_CONTRACT_ADOPTION_REQUIRED | 按来源合法可见性建立 E_c/E_r pending 风险投影、fee-cover 原子转换和 funding cover/payable 并集；明确模型 ACK 与证据 proof-floor。保持 100 USDT kill、5% buffer、1x、1.10 reserve 和原成本，不假装旧 acknowledged-only E_d 已包含该桥接。 |

这两个门应一次性裁定。AM01 不能由 Gemini 暗自选择；若选择同 bar 可重新注册，必须冻结明确优先级和独立预期，不能继承旧测试的默认。AM02 不改变八候选公式、100 USDT kill、5% reserve、1x、1.10 buffer、22/44bp 交易成本或 4/8bp 资金费情景，只明确 pending 信息可见后如何约束资金。没有任何补丁或新方法立即生效。

## 事件 envelope 与双时钟

8 个不可变 record、12 类事件。每个事件必须有 stable event_id、book/candidate/scenario、symbol、精确 owner/position/order/settlement/source/cause IDs、economic_at_ms、available_at_ms、typed payload digest、journal sequence/chain hash。event_id 来自 version/type/book/source/owner/cause/phase，不能只按 payload 生成以逃避冲突。相同 ID/相同 immutable payload 幂等；不同 payload 为 `CONFLICT_FAIL_CLOSED`。同 source/symbol/close 的冲突 Mark，即使有不同 event ID 也必须失败。

| 事件 | 时间/可用性 | 含义 |
|---|---|---|
| ObservedMinuteBar | 一分钟 [O,O+60000)，完整 bar available=O+120000 | 已完成 OHLCV 和来源身份；当前分钟 H/L/C 不进入当前决策。 |
| ObservedMark | close=T，available=T+60000 | true minute Mark、单调 close 水位、同 close 冲突检查；age<=120000ms。 |
| SignalAtDecision | 小时 close=H，available=H+60000，earliest fill=H+120000 | 冻结 formula、ATR、boundary，禁止 entry-minute feature。 |
| OrderReserved | 决策 cut=O | owner 级 notional/cost/funding cover；due>=O+60000，无未来入场价。 |
| EconomicFill | 经济 fill=F；模型 FillAck 默认 F+60000 | 执行平面记录量/价格/费用；若合法证据要求更晚，ACK 不能早于该证明。任何这种 proof-floor 均须 AM02 明确冻结。 |
| FillAck | available>=max(F+60000, admitted fill proof) | 精确 order/fill/owner/quantity；扣一次 entry fee，notional 转 G，禁止 auto-ACK。 |
| EconomicExit | 开盘 exit=F，或 barrier=O+59999；risk notice 等来源证明 | 关闭物理 inventory，保留每个 slice 的 gross/fee payable/receivable；不回写早先风险。 |
| ExitAck | available>=max(exit+60000, exit proof, declared delay) | 逐 slice 结算；释放已满足成本，不释放尚未解决的 funding cover。 |
| FundingObligation | economic=S；phase=CONDITIONAL/FINAL，各自稳定 ID | S 时只有因果可知的条件覆盖；完整 ±15s 窗口可知后才能最终记 payable。 |
| FundingAck | max(S+60000,last-window-minute-end+60000,rate proof,declared delay) | 最终 owner/S payable 结算一次，关闭 owner 仍保留；现金、cover、shortfall 原子更新。 |
| RiskKill | 合法 as-of checkpoint O | 永久 latch；取消 pending entries，已知仓位退出不早于 O+60000。 |
| EndOfMinuteReport | 已完成分钟的经济标签；无决策回调 | E_e、drawdown/insolvency/exposure 标签与 E_d/E_r 读集隔离。 |

经济执行/报告平面与 available-filtered 决策/风险平面分离。完整一分钟 bar 的 H/L/C 在其 close+60s 前不作为来源可见信息；barrier 经济标签 O+59999ms 的事实风险 notice 必须等待合法证明，通常 O+120000ms。模型 FillAck 的原 +60s 假设与证据可用性都需明确绑定；不得虚构更早执行回执。经济归约可记录过去经济时间，但不能修改已经做出的订单、kill 或 capital。经济 insolvency 早于因果发现时，保留中间损失和 exposure breach，不剪裁或重置。

每个对齐分钟 O 顺序：校验 ID/来源/原因 → eligible ACK/source batch（exit/reduction ACK、entry ACK、funding ACK、trade、mark；按因果拓扑和固定 typed ties）→ 已可见 pending 义务及风险 → closed-hour cursor/原公式/资金承诺 → 已到期退出（kill、reduction、gap SL/TP、expiry）→ 已预留入场 → 执行平面站立保护 → funding window 推进 → 隔离经济报告/不变量。相同 ACK batch 在风险/定价前完整提交；内部每笔仍须分录守恒。只排列因果独立的事件，不能打乱 cause。

## owner 状态机与 Retest

7 个 owner phase：FLAT → RESERVED → UNACKED_OPEN → ACKED_OPEN → EXIT_PENDING → CLOSED_UNSETTLED → COOLDOWN → FLAT。某些经济退出发生在 FillAck 前，仍进入 EXIT_PENDING 并保留未付费用/本金承诺；book kill 是正交永久 latch，不阻碍金融结算。禁止在同一 book/symbol 同时有两个 live/pending-entry owner；不同候选/控制/case 的资金互不共享。

OrderReserved 建 owner notional/cost/funding 承诺；EconomicFill 建 inventory 和 fee accrual；合法 fee notice 原子转换覆盖与风险义务；FillAck 结算 entry fee、转换 notional→G；EconomicExit 关闭/减少 physical quantity，但保留逐 slice payable/receivable；ExitAck 结算 gross/exit fee，保留 unresolved funding；最终 funding ACK 后可终结金融 owner。cooldown=max(previous,ceil(exit/60000)*60000+14400000)，旧 ACK 不倒退、不触碰新 owner。部分减仓保留原 position ID/stop/target，所有 exit slice 数量和不得超过填充量。

Retest feature cursor 以 family/symbol/direction 顺序归约每个已完成未处理小时，不因 cooldown/已有持仓跳过取消或 extrema；各 horizon/cost/policy 的事件消费独立。IDLE→AWAITING；错误方向 close→CANCELED；下三根小时首次确认→CONFIRMED；第三根仍无确认→EXPIRED。真实缺小时是 source failure，不能补造。迟调用可 catch up 状态，但不得在现在补发原本过去的入场。双角色 bar 的额外转移由 AM01 决定。

## 双重记账、资本并集与精确不变量

实际 USDT 账：CASH（asset）、TRADE_RECEIVABLE（asset）、TRADE_PAYABLE/FEE_PAYABLE/FUNDING_PAYABLE（liability）、REALIZED_GAIN（income）、REALIZED_LOSS/FEE_EXPENSE/FUNDING_EXPENSE（expense）、OPENING_EQUITY/itemized flows。另有平衡 memo 账 ENC_COST、ENC_FUNDING、ENC_SHORTFALL 对 ENC_CONTRA，减少 spendability，不当费用/PnL。永续名义本金不是交易现金支出。

分录：初始 Dr CASH/Cr OPENING_EQUITY=1000；fee accrual Dr FEE_EXPENSE/Cr FEE_PAYABLE，关联 ACK Dr FEE_PAYABLE/Cr CASH；负 gross Dr REALIZED_LOSS/Cr TRADE_PAYABLE，正 gross Dr TRADE_RECEIVABLE/Cr REALIZED_GAIN，ExitAck 结清相应 account；Funding FINAL Dr FUNDING_EXPENSE/Cr FUNDING_PAYABLE，FundingAck Dr FUNDING_PAYABLE/Cr CASH。只在因果证明可见后转换风险 memo；不同经济/知识时间不混用。每笔实际/每笔 memo 分录各自 debit=credit。价格已嵌入 spread/slip/tick，现金只扣 fees/funding，不再扣一次摩擦。

`E_d = settled cash + acknowledged live MTM`。

`E_c = CASH + U_ack_live + Σ min(0,U_unack_live) − Σ visible unpaid gross-loss payable (per exit slice) − Σ visible unpaid fee payable (per fee item)`。

所有 pending positive receivable 独立排除；先在组成项截断，再汇总，不能将同 owner 未 ACK 赢 100 抵掉未 ACK 亏 100，也不能让盈利抵掉未付 fee。已可见退出先移除对应 open MTM，避免同时计浮亏与已实现亏损。现金 ACK 后移除对应 payable，避免重复。fee 进入 E_c 的同一原子转移释放匹配的 fee cover；未 ACK notional 保留，剩余费用安全 buffer 保留至相应 ACK。T34 验证这一步。

`P_f = Σ FINAL unpaid funding`；`E_r = E_c − P_f`。条件窗口尚未 final 时是 reserve，而非已知费用。

`R_f = future/conditional reserve + payable dedicated cover`；`L_f = Σ owner max(0,required−cover)`。资金费占用并集为 `R_f+L_f = R_future + Σmax(Rcov, payable_or_conditional_required)`；cover 与 payable 是同一义务，不能再加一次 P_f，也不能提前释放 cover。短缺必须按 owner/S 单独记录，不能偷 ETH 储备。

`A_raw = .95*E_c − C_o − R_f − L_f`；`A = 0 if killed/insolvent else max(0,A_raw)`。只有 A_raw>=0 时才断言未截断上界；资金不足/负净值不是自动 invariant error。max0 仅用于入场资本，不裁剪 cash 或真实损失。原 `B=max(0,min(333.333333333333,A/3,A−G))`、同 snapshot、BTC/ETH/SOL 顺序承诺及 1.10 reserve 公式保留。可见 drawdown>=100 或 E_r<=0 永久 kill，已知退出仅下一合法 open，无法回写。

标准化资金例：cash1000/C_o7/ETH future2/BTC cover.40/payable1/shortfall.60，ACK 前 free=950−7−2−.40−.60=940；ACK 后 cash999，BTC payable/cover/L=0、ETH2不变，free=.95×999−7−2=940.05。差 .05 是 buffer 重算，不是 PnL。标准化 loss169.336545 在 first legal proof cut 风险830.663455/kill/free0，之前不看未来。

flat/all-ACK terminal 必须 `cash−1000 = Σeffective gross−Σentryfees−Σexitfees−Σfunding+itemizedflows = Σfinal trade net+flows`，所有 reserves/payables/ACK queues 为 0。local Decimal precision50/ROUND_HALF_EVEN、12dp postings，tick/lot exact，禁止 ambient context 影响。不能用补读下一月来清尾；证据不足则 SOURCE_BLOCKED。

| 不变量 | 每个 transition 的精确断言 |
|---|---|
| I01 | sum(dr_USDT)==sum(cr_USDT) for everyeconomicposting; independently sum memo dr==cr; currencies never mixed. |
| I02 | total_reserved_funding==sum(ownerR_f for ALL live/pending/closed_unsettled owners). |
| I03 | total_unpaid_funding==sum(owner FINAL FUNDING_PAYABLE); provisional andfinal distinguished. |
| I04 | total_cost_commitments==sum(owner remainingC_o components); no side-state counter authority. |
| I05 | shortfall>0 implies explicit exactowner/settlement ENC_SHORTFALL; no cross-owner cover transfer. |
| I06 | I06: A == (0 if killed/insolvent else max(0, 0.95*E_c-C_o-R_f-L_f)); if A_raw>=0, A<=A_raw. Negative CASH and economic equity are preserved, never floored. |
| I07 | every settledcash change has exactACKposting/cause; allACK flatcashdelta==sumfinalnet+itemizedflows. |
| I08 | within a book one symbol has <=1 live/pendingentry owner; exitedowner retained financially without liveinventory. Booksindependent. |
| I09 | cooldown_until[symbol]==max(previous,ceil_valid_exit+14400000); lateACK cannotlower orresurrectowner. |
| I10 | latestavailablemarkclose monotonically nondecreasing; sameclose conflictingprice fatal regardlessinputpermutation. |
| I11 | idempotentIDs postonce; sameID/differentdigest CONFLICT_FAIL_CLOSED; exactowner/cause IDs match, no substring/fallback. |
| I12 | Every decision/risk cause has available_at <= cut. Full-bar H/L/C need completed-bar proof; Funding FINAL needs the complete ownership-window proof. Reports are outside the decision readset. |
| I13 | quantity/cost/tick/lot checks exactDecimal(localcontextprecision50,ROUND_HALF_EVEN), postingquantize12dp; no ambientcontext dependence. |
| I14 | kill monotonicallyfalse->true; ACK/closedposition/foldtransition cannotreset highwater orkill; preservedlosses/insolvency. |
| I15 | eachRetesthourcursor advances once in chronologicalorder; 3hourlimit and firstconfirmation/consumption fixed; no latebackdatedfill. |
| I16 | eachpartialexitslice quantities sum<=originalfill; funding exposure charge maxprepost notsum; eachowner/S settlesonce. |
| I17 | Pending positive receivables cannot offset any visible negative exit slice or unpaid fee; truncate positive components before aggregation, not owner net PnL. |

## S 的因果资金费

窗口 [S−15000,S+15000]。在 S 或更早只保留已知 schedule/exposure/envelope 下的条件 cover，不能声称已知道 S+15s 的持仓。退出 owner 在交叠窗口内仍保留，部分减仓使用 max(pre,post) absolute quantity，不相加。对整点 S，最后交叠分钟结束 S+60000，加原 60s 可用性，通常 final proof 在 S+120000；rate/mark 可更晚。FundingAck=max(S+60000,last-minute-end+60000,rate_available,declared delay)。最终费用经济日期为 S，但不能改变之前 sizing。此阶段合成资金费验证真实事件/Mark/ownership 语义，金额仍是原 4/8bp 代理情景，不是实际交易所 cashflow。

## 复用与替换

| 来源片段 | 已检查边界 / 下游规则 |
|---|---|
| CandidateRegistry / 原八 IDs | 静态比较 family/direction/hold/symbol 与原 roster；原 docstring 的 pre-registered 不提供有效 prereg 权限。 |
| types.py:55 | Bar1m/MarkBar1m 值字段可复制；Bar1m 本身没有 available_at，须观测 envelope；拒绝混合 symbol/重复分钟。 |
| indicators.py:8 | epoch contiguous 聚合、TR/ATR20、SMA seed EMA 纯源已检查；调用前 enforce completeness，行为独立测试尚未运行。 |
| indicators.py:195 | ER zero denominator 旧函数返回 0，冻结方法规定 ineligible；新调用层必须显式 guard，不能将 0 当完整合同。 |
| signals.py:191 | 结构 EMA/slope/ER/body/range/prior3/stop 谓词静态对应；仅抽纯公式，新的时钟/cooldown 状态不可沿用。 |
| cost_model.py:24 | 纯费用/不利 rounding 公式条件复用；旧 helper 对无效 tick/lot 不抛错，新调用层必须 fail closed；6/12bp fees、5/10bp spread+slip 不变。 |
| B04 退出行为 | 复用规范和正例，重写纯函数；旧 Stage4 else raw-open 分支不能证明全部 forced/time target cap。 |
| VirtualBook / Stage1/7 / ACK sets / side dict | 整体替换，禁止 import/inherit/wrapper、substring owner、auto-ACK、提前释放；没有中间继承旧资金状态。 |
| Replay scheduler / mutable Retest | 整体替换；精确来源证明、逐小时 cursor、独立 policy 消费，无 latest-only 漏洞。 |

“静态检查”仅表示固定 source 与方法对应，不代表已独立重跑 PASS。必须保存固定 source/hash 并在新包捕获纯片段；不得从基线不存在的旧包隐式 import 本地安装版本。所有纯函数仍需独立边界、missingness、availability、context 证明。

## 独立合成 oracle：34 个未运行用例

以下为 implementation-ready 输入/预期，状态都是 NOT_YET_RUN。每次 transition 检查全部适用不变量，不能只末尾对账。API 标准化例明确不充当合规资金的 full replay；T28/T29 才要求实际 run_simulation、>=240h warm-up、合法尺寸及非空结果。任何 hand-built CompletedTrade 不能伪装完整 replay。

| 用例 | 合成输入 | 预期断言（未运行） |
|---|---|---|
| T01 同 close 冲突 | 同一 BTC 来源/close=S，价格 50000 和 52000，两个输入排列。 | 两种排列都在决策前以同一 source key 报 CONFLICT_FAIL_CLOSED，无任意获胜价格。 |
| T02 延迟/未来 Mark | close=S/price=50000/available=S+60s；close=S+60s/51000/available=S+120s；旧 close 迟到；未来 available=S+180s。 | S+60s 只用 50000，S+120s 用 51000；水位不倒退，未来消息不进入读集。 |
| T03 迟到同 close 冲突 | 先接受 close=S/50000，再收到同 close/48000。 | 冲突致命；不回写历史，也不重算早先订单。 |
| T04 报告与决策隔离 | 标准化 API book：cash=1000、LONG q=1、entry=50000；合法 Mark=50000；未来报告 Mark=51000。q=1 明确不作为合规资金入场。 | 证明前 E_d/E_c=1000；经济报告可标记 2000，但任何早先决策不变。该例仅验证读集隔离。 |
| T05 Mark 过期边界 | 最后 Mark close=S；检查 cut=S+120s 和 S+180s。 | 120s 有效；180s WAIT_STALE 并安排下一分钟退出；不得猜测 MTM。 |
| T06 ACK 重复 2x/3x | cash=1000；同一 FillAck 费用 2，完全相同 payload 重复两次、三次。 | cash=998，费用=2，仅一笔现金分录，重复不改变有效 journal。 |
| T07 ACK payload 冲突 | 同一 ACK ID 改费用 2→3 或数量 1→2。 | 第二次分录前 fail closed；原余额不变，不能静默忽略。 |
| T08 旧 ACK 不倒退 cooldown | 新 P2 cooldown=1700017140000；旧 P1 ACK 给出较早 1700010000000。 | cooldown 保持 1700017140000；只能结算 P1，不修改 P2。 |
| T09 ACK owner/cause 错配 | ACK 指向不匹配的 order/fill/position。 | CAUSE_OR_OWNER_FAIL_CLOSED，无 auto-ACK 或 symbol fallback；合法承诺不被释放。 |
| T10 资金费短缺与 owner | cash=1000、C_o=7、BTC Rcov=.40、ETH Rfuture=2；最终 BTC payable=1，ACK 延迟。 | ACK 前 R=2.40、P=1、BTC L=.60、free=940；ACK 后 cash=999、BTC P/Rcov/L=0、ETH=2、free=940.05。 |
| T11 资金费 ACK 延迟/乱序 | T10 的 ACK available=final_cut+120s；到达顺序 ACK 先于 cause，或 ACK 晚可用。 | 等待合法 cause 与 available；独立到达顺序归一化；payable/覆盖/短缺保留到 ACK，重复只扣一次。 |
| T12 S 前退出仍属窗口 | exit=S−10000ms；退出 ACK available 至少 exit+60000ms=S+50000ms，首个对齐 cut=S+60000ms；窗口证明 available=S+120000ms。 | S 时 EXIT_PENDING；S+60s 合法 ExitAck 后 CLOSED_UNSETTLED，仍保留条件资金费覆盖；S+120s 才可 FINAL，FundingAck 不早于该证明。 |
| T13 拒绝非分钟 API | advance_to(S−5000ms)，S 为整分钟。 | INVALID_MINUTE_CLOCK，状态不变；该例是 API 防御，不宣称正常 replay 可达。 |
| T14 精确持仓身份 | POS_1 应付 1，POS_10 应付 .20，独立 exposure/cause。 | 精确键各付一次，无 substring 匹配；各自保留资金 tombstone。 |
| T15 S 时不能知未来所有权 | 窗口至 S+15s；未来入场可能发生；最后交叠分钟证据 available=S+120s。 | S 时只有条件覆盖，不提前确认未来数量/payable；最终数量用 max(pre,post)，不能相加。 |
| T16 标准化 −169.336545 | cash=1000、trade payable=169.336545，无额外费用；economic exit=S−1ms、proof available=S+60s、ExitAck=S+120s。并非原 B05 价格/费用拆分。 | 证明前不见未来亏损；S+60s E_c/E_r=830.663455，drawdown=169.336545，kill=true/free=0；ACK 后 cash=830.663455、payable=0，kill 不复位。 |
| T17 未 ACK 盈利不可复用 | cash=1000、独立 trade receivable=50、费用 0，ACK 延迟。 | ACK 前 E_c=1000/free=950；ACK 后 cash=1050/free=997.5（若无其他约束）。 |
| T18 小亏损仍减少资本 | cash=1000、合法可见 pending loss=20、其他覆盖 0。 | E_c/E_r=980，drawdown=20，不 kill，free=931；不能仍报 950。 |
| T19 kill 永久 | T16 kill 后又到达盈利 ACK、新 fold、信号。 | 合法结算继续，但新订单 WAIT_DISABLED/free=0；high-water/kill 不重置；退出只在下一合法 open。 |
| T20 同 bar SL-first | LONG entry=50000、stop=49000、target=51000；O/H/L/C=50000/52000/48000/50000。 | raw exit=49000/SL，economic_at=O+59999ms；一次成本，无 TP 盈利。 |
| T21 不利 gap | 同 LONG，bar open=48000<stop=49000。 | raw exit=48000；保留 gap 亏损和资本越界标记，不用有利 49000。 |
| T22 所有有利退出封顶 | LONG target=51000/open=52000；SHORT target=49000/open=48000；分别 TP/time/kill/reduction。 | LONG raw=51000、SHORT raw=49000；各类型均封顶，再加一次不利摩擦/tick。 |
| T23 4h/12h 精确到期 | fill=F、hold=4h 或 12h，无提前 SL/TP；到期前一分钟与 F+hold 开盘。 | 不提前到期；首个合法 F+hold open time exit；该 open 的 stop 优先，报告不得回流。 |
| T24 跳过小时仍取消 | LONG boundary=47400、ATR=1000，H25 突破；H26 close=46000/low=45500；H27 恢复；全部已完成小时证据可用。 | 顺序 reduce H26/H27，旧事件在 H26 取消；H27 无旧确认/伪 stop；密集调用与跳过调用的状态一致。 |
| T25 三小时与 extrema | boundary=50000、ATR=1000；H+1 low=49800、不确认，H+2 low=49700、不确认；H+3 low=49900/close=50100/open<close 首次确认。 | stop=49700−250=49450；只在 hour3 确认，hour4 不可确认；迟调用不补发过去入场；各 variant 消费隔离。 |
| T26 双角色规范门 | 同一小时 bar 取消/过期旧事件，并满足新突破谓词。 | 未冻结 AM01 时 SPEC_AMENDMENT_REQUIRED；若 Controller 采纳建议，只终止旧事件，下一根不同小时方可注册。 |
| T27 八候选与成本几何 | 原始 8 IDs；base/stress 22/44bp，小时资金费 4/8bp；4h c=76，12h c=140，stop cap=250。 | 4h 需 d>=152 且其他规则通过；12h stress 需 280>250，明确 ineligible，无虚构亏损；book/case 独立，不降成本。 |
| T28 完整非空 4h replay | >=240h warm-up、固定结构触发和合法尺寸；4h BASE/STRESS 各执行预定义 winning/losing 两条完整路径（共4个 full replay）；synthetic known hourly schedule、原4/8bp费率、stop200bp满足4h stress几何；全部 source/ACK tail 在固定边界内。 | 实际 run_simulation，4h BASE/STRESS 的 winning/losing 路径各 n>=1，所有原费用不变；净值由独立 quantity/fee/funding oracle 重建；terminal positions/ACK/payables/C_o/R/L=0。不是实证或候选参数优化。 |
| T29 完整 12h BASE 与 stress | >=240h warm-up 的12h BASE，明确定义合成 known 8h settlement schedule（费率仍4/8bp，非实际交易所来源），stop200bp按原 stress hurdle c60/d>=120通过；另一个固定12h STRESS unknown-hourly scenario c140/d>=280不通过。两个fixture事前固定，不能由结果切换。 | Known-schedule BASE12h 实际 run_simulation n>=1，cash/net逐笔对账；unknown-hourly STRESS12h=0fills+明确ineligible。不能因为旧 registry helper 的 horizon硬编码跳过funding schedule；该helper只复用ID，不复用eligibility捷径。terminal余额0。 |
| T30 Decimal/排列/部分减仓 | 环境 Decimal precision 28/50、Python3.12/3.13；BTC/ETH 独立输入排列；q=1→.6→0 的部分退出，保留因果顺序。 | 12dp 分录/checkpoint/hash 相同；资金费用 max pre/post=1 而非 1.6；退出 slice 数量和<=1；费用/资金费各一次。 |
| T31 权限/缺失/边界 | 缺 active trade/true-mark、非正 volume、非法 tick/lot/min-notional、fold tail 越界；禁止网络/实证 CLI。 | 按规范 SOURCE/COST_BLOCKED 或命名 WAIT；无伪填充价格、maker 优势、下一月读取；market/protected/private/live=0。 |
| T32 不同 pending slice 盈亏不互抵 | 同 owner 两个已可见未 ACK slice：payable=100、receivable=100、费用 0，cash=1000；两个 ACK 均未来可用且到达排列可交换。 | ACK 前 E_c/E_r=900，drawdown=100，kill=true/free=0；不能先 net 得 0。盈利 ACK 后 cash=1100、仍 pending loss100，kill 保持；全部 ACK 后 cash=1000、余额 0。 |
| T33 资本不足/负净值下界 | 独立 projection 输入：E_c=100、C_o=100，A_raw=−5；以及 E_c=−10。 | free=0 合法，I06 不错误要求 0<=负数；实际 cash/经济亏损不截断；非正风险净值 kill。 |
| T34 费用可见时原子覆盖转换 | cash=1000；entry notional cover=100、entry fee cover=2、exit cover=1，C_o=103；合法费 notice=2，FillAck 延迟。 | notice 同步 E_c=998、entry fee payable=2、C_o=101、free=847.1，未 ACK notional100保留；ACK 后 cash998/payable0/C_o1/free947.1，G=100；无二次费用覆盖释放。 |

## Gemini 下游合同 DRAFT

新实现建议分支 `feature/v06-bline-g2-r3-p1-alt-engine-gemini-a-r1`，fresh sibling `g2-p1-alt-engine-gemini-a-r1`；代码基线 `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`。实际起点必须由新的 Controller implementation dispatch 固定并绑定本设计最终 remote SHA、AM01/AM02 version/root；这里不创建该分支或授权。固定 A 只作为纯片段来源，无全 A merge。

| 新模块 | 接口/职责 |
|---|---|
| model.py | 8 个 frozen records：Event、Posting、OwnerLedger、RetestState、Projection、EngineState、ReplayConfig、ReplayReport；规范 Bar/Mark 值类型与枚举。 |
| journal.py | validate_event、稳定 ID/digest、source-close 冲突、balanced posting batch、append sequence/hash；不读外部 I/O。 |
| money.py | post_owner_flow、project_asof、assert_money_invariants；owner 子账为权威，派生聚合、Decimal 局部上下文。 |
| reducer.py | reduce(state,event,config)->new_state,postings,scheduled_events；事务性不可变归约；报告不能调度风控。 |
| clock.py | ingest/advance_to(aligned O)，available 过滤、因果拓扑/typed tie、ACK queue；执行与知识索引分开。 |
| execution.py | resolve_exit 和 effective_fill 纯函数；SL-first/worse gap/全部有利退出封顶/精确到期/一次摩擦。 |
| signals.py | reduce_completed_hour，规范 Retest cursor 和结构纯谓词；AM01 已冻结才启用，variant 消费不共享。 |
| frozen_primitives.py | 按固定 A/method 捕获原 registry/constants、纯聚合/ATR/EMA/ER/cost/rounding，附 hash；只改 imports，不导入旧生命周期。 |
| replay.py | ReplayEngine.run_simulation(SyntheticDataset,ReplayConfig)->ReplayReport；只接收内存合成输入，无 fetcher/交易接口。 |

允许下游新路径：`src/btc_quant_agent/strategy_research/r3_alt_engine/**`，`tests/test_r3_alt_events_money.py`、`tests/test_r3_alt_clock_execution.py`、`tests/test_r3_alt_retest_replay.py`，合成-only `scripts/strategy_research/r3_alt_engine/run_synthetic.py`，自己 `docs/strategy_research/g2_r3/p1_alt_engine_impl_r1/**`、`evidence/v0.6/b_line/g2_r3_p1_alt_engine_impl_r1/**`。这些只是建议合同，非本任务写权限。现有 src/tests、A/B、P2、registry、H40 golden、CI、project/controller status 全禁止改动；无市场 fetcher、provider、empirical CLI 或 order gateway。

接口：`reduce(state,event,config)->newstate,postings,scheduled_events`；`project_asof(state,cut)->Projection`；`resolve_exit(...)->rawprice,economic_at`；`reduce_completed_hour(...)->RetestState,SignalAtDecision`；`ReplayEngine.run_simulation(SyntheticDataset,ReplayConfig)->ReplayReport`。SyntheticDataset 只在内存，带 input hashes/proof clocks；不能 I/O。ReplayReport 的 schema=`r3_alt_engine_v1`，含 trades/netbp/R/E_d/E_r/E_e/WAIT/ineligible/source/insolvency/owner balances/journal hash；不伪兼容 VirtualBook。

预算是一次完整 build，构建中只跑聚焦合成检查，以及固定实现 SHA 后一次独立 B/Sol 行为审计。独立方新分支从 Controller 指定的固定实现对象开始，git archive 隔离源，验证 imported __file__/hash；oracle 从此账户合同重建预期，不调用生产资本函数、不只断言 saved JSON。要求 34/34 正确、0FAIL/0SKIP/0XFAIL，非空 4h 赢/亏、12h BASE，明确 12h stress ineligible，终端 pending 0、精确 cash/net，Python3.12/3.13 和外部 Decimal context 下确定性，八候选及零行情/保护/私有/交易计数。最终 full CI 真实报告，不能覆盖/豁免旧 H40 golden。一次独立审计有重大失败则 STOP；不回到 R4/R5 循环。

独立 Controller engine acceptance + P2 local root/来源/许可/true-minute-mark admission + 已有受限科学合同之后，才另行创建并 first-push 新 prereg（建议 `docs/strategy_research/g2_r3/preregistration_r1/**`）、核验 remote exact SHA，再单独发 P4 market-body capability。任何这些文件/权限此次都没有创建。

## 单一终态、静态验证与安全

`P1_SPEC_AMENDMENT_REQUIRED`：Controller 先一次性冻结 AM01/AM02，再决定是否另发 Gemini A build 与一次 B/Sol audit。若不接受最小完整合同，就停止引擎路线，而非给旧 VirtualBook 新补丁。

只执行 JSON/34-case/12-event/8-ID、固定 source/blob/hash/链接、路径白名单、whitespace、父级和 hermetic arithmetic 检查；0 新引擎测试/合成 replay。此次 scoped market/protected/private/live/code writes=0，不宣称全环境网络零；读取的是固定代码、合成证据、方法和公共库规格。A/B 与原科学评审不变；P2 LOCAL_ROOT_UNKNOWN、P3 NONE、P4 NONE、TESTNET/LIVE NONE。自动非强制提交/推送后在外部完成回执报告 final SHA、parent、remote exact equality 和实际 CI；不在同 commit 中自引用其 hash。

## 固定项目来源

| 固定来源 | 证据类别 / blob |
|---|---|
| [prompts/v0.6/b_line/V06_G2_R3_P1_ALTERNATIVE_ENGINE_ARCHITECTURE_SELECTION_SOL_HIGH_R1.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/770e910596bfbd82c28bd92705cf71ef981f0564/prompts/v0.6/b_line/V06_G2_R3_P1_ALTERNATIVE_ENGINE_ARCHITECTURE_SELECTION_SOL_HIGH_R1.md) @ `770e910596bfbd82c28bd92705cf71ef981f0564` | TASK_AUTHORITY / `8e25cddcf42b50f5c92cf502c050aa56d34d7449` |
| [reviews/v0.6/b_line/V06_G2_R3_P1_FINAL_B_ARCHITECTURE_NO_GO_AND_ALTERNATIVE_ENGINE_CONTROLLER_R1.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/b74b932da32e4b5bbe2477c2de014f94719d6a93/reviews/v0.6/b_line/V06_G2_R3_P1_FINAL_B_ARCHITECTURE_NO_GO_AND_ALTERNATIVE_ENGINE_CONTROLLER_R1.md) @ `b74b932da32e4b5bbe2477c2de014f94719d6a93` | ACCEPTED_CONTROLLER_TERMINAL_AUTHORITY / `d1a987cd13fded9308bc1fd066efdebde65c352a` |
| [src/btc_quant_agent/strategy_research/r3_overnight/candidate_registry.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/b5d34aacd36dc27454944a22436db555c3f6eeb8/src/btc_quant_agent/strategy_research/r3_overnight/candidate_registry.py) @ `b5d34aacd36dc27454944a22436db555c3f6eeb8` | READ_ONLY_FAILED_ENGINE_SOURCE_NOT_AUTHORITY / `97b283d9292a10e8c5ecd73d1a7f046dea4d527b` |
| [src/btc_quant_agent/strategy_research/r3_overnight/constants.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/b5d34aacd36dc27454944a22436db555c3f6eeb8/src/btc_quant_agent/strategy_research/r3_overnight/constants.py) @ `b5d34aacd36dc27454944a22436db555c3f6eeb8` | READ_ONLY_FAILED_ENGINE_SOURCE_NOT_AUTHORITY / `2afeb4cd3ad5c61c8b95f93933b6f6a81b6677cf` |
| [src/btc_quant_agent/strategy_research/r3_overnight/cost_model.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/b5d34aacd36dc27454944a22436db555c3f6eeb8/src/btc_quant_agent/strategy_research/r3_overnight/cost_model.py) @ `b5d34aacd36dc27454944a22436db555c3f6eeb8` | READ_ONLY_FAILED_ENGINE_SOURCE_NOT_AUTHORITY / `7a1b9138e3039716fe87c7b66bdeb4694611b8ba` |
| [src/btc_quant_agent/strategy_research/r3_overnight/indicators.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/b5d34aacd36dc27454944a22436db555c3f6eeb8/src/btc_quant_agent/strategy_research/r3_overnight/indicators.py) @ `b5d34aacd36dc27454944a22436db555c3f6eeb8` | READ_ONLY_FAILED_ENGINE_SOURCE_NOT_AUTHORITY / `b6b91b7631c9d8ae14c2da8775ea4f7f3087176e` |
| [src/btc_quant_agent/strategy_research/r3_overnight/ledger.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/b5d34aacd36dc27454944a22436db555c3f6eeb8/src/btc_quant_agent/strategy_research/r3_overnight/ledger.py) @ `b5d34aacd36dc27454944a22436db555c3f6eeb8` | READ_ONLY_FAILED_ENGINE_SOURCE_NOT_AUTHORITY / `975fd3c14f98da381efce1089c47d50a07ef7912` |
| [src/btc_quant_agent/strategy_research/r3_overnight/replay_engine.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/b5d34aacd36dc27454944a22436db555c3f6eeb8/src/btc_quant_agent/strategy_research/r3_overnight/replay_engine.py) @ `b5d34aacd36dc27454944a22436db555c3f6eeb8` | READ_ONLY_FAILED_ENGINE_SOURCE_NOT_AUTHORITY / `79c31ecddfac31fef3370631c526d87c69e98585` |
| [src/btc_quant_agent/strategy_research/r3_overnight/signals.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/b5d34aacd36dc27454944a22436db555c3f6eeb8/src/btc_quant_agent/strategy_research/r3_overnight/signals.py) @ `b5d34aacd36dc27454944a22436db555c3f6eeb8` | READ_ONLY_FAILED_ENGINE_SOURCE_NOT_AUTHORITY / `ea0608f1bce4af342560098f8c8fe7604a0350ec` |
| [src/btc_quant_agent/strategy_research/r3_overnight/types.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/b5d34aacd36dc27454944a22436db555c3f6eeb8/src/btc_quant_agent/strategy_research/r3_overnight/types.py) @ `b5d34aacd36dc27454944a22436db555c3f6eeb8` | READ_ONLY_FAILED_ENGINE_SOURCE_NOT_AUTHORITY / `6d37f351e37ead16216194ad18a16da0acfba9b2` |
| [docs/strategy_research/g2_r3/prep_b/architecture_v1/B_FINAL_INDEPENDENT_ARCHITECTURE_VERDICT.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7/docs/strategy_research/g2_r3/prep_b/architecture_v1/B_FINAL_INDEPENDENT_ARCHITECTURE_VERDICT.md) @ `52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7` | INDEPENDENT_SYNTHETIC_VERIFICATION_OR_SOURCE_NOT_MARKET_RESULTS / `13535edd1390ed397b6e145c219faddae94621ae` |
| [evidence/v0.6/b_line/g2_overnight_p0_b/architecture_v1/B01_B07_FINAL_INDEPENDENT_BEHAVIOR_MATRIX.json](https://github.com/EXASHXE/btc-quant-agent-public/blob/52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7/evidence/v0.6/b_line/g2_overnight_p0_b/architecture_v1/B01_B07_FINAL_INDEPENDENT_BEHAVIOR_MATRIX.json) @ `52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7` | INDEPENDENT_SYNTHETIC_VERIFICATION_OR_SOURCE_NOT_MARKET_RESULTS / `bc6adde43086ae3ada328f5b2d52ce44682d976a` |
| [evidence/v0.6/b_line/g2_overnight_p0_b/architecture_v1/B_FINAL_SYNTHETIC_EXECUTION_RECEIPT.json](https://github.com/EXASHXE/btc-quant-agent-public/blob/52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7/evidence/v0.6/b_line/g2_overnight_p0_b/architecture_v1/B_FINAL_SYNTHETIC_EXECUTION_RECEIPT.json) @ `52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7` | INDEPENDENT_SYNTHETIC_VERIFICATION_OR_SOURCE_NOT_MARKET_RESULTS / `8125d548ae2886c95215f5aec6e8313f63d4c081` |
| [scripts/strategy_research/r3_verification/architecture_v1/a_arch_v1_auditor.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7/scripts/strategy_research/r3_verification/architecture_v1/a_arch_v1_auditor.py) @ `52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7` | INDEPENDENT_SYNTHETIC_VERIFICATION_OR_SOURCE_NOT_MARKET_RESULTS / `dface656010d76bf62431242b977786812b059bb` |
| [tests/test_v06_g2_r3_verifier_architecture_v1_audit.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7/tests/test_v06_g2_r3_verifier_architecture_v1_audit.py) @ `52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7` | INDEPENDENT_SYNTHETIC_VERIFICATION_OR_SOURCE_NOT_MARKET_RESULTS / `dabc08e4c0c146d197298d6cef304b0b3de5fb41` |
| [docs/strategy_research/g2_r3/METHOD_DESIGN.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/e5b2006a89441f7eb2ec900e508aff451106b87a/docs/strategy_research/g2_r3/METHOD_DESIGN.md) @ `e5b2006a89441f7eb2ec900e508aff451106b87a` | FROZEN_FORMULA_DESIGN / `fb701b0be825f85801377f86eb80ba4f766ebaed` |
| [evidence/v0.6/b_line/g2_r3_design/CANDIDATE_REGISTER_PROPOSAL.json](https://github.com/EXASHXE/btc-quant-agent-public/blob/e5b2006a89441f7eb2ec900e508aff451106b87a/evidence/v0.6/b_line/g2_r3_design/CANDIDATE_REGISTER_PROPOSAL.json) @ `e5b2006a89441f7eb2ec900e508aff451106b87a` | FROZEN_EIGHT_PROPOSAL_NOT_EFFECTIVE_PREREG / `d337542f6482938c37eb6b4e43255cdf4d09751a` |
| [docs/strategy_research/g2_r3/method_repair/METHOD_R1_1_PIT_COST_ACCOUNTING.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/cf2d5cc33774cdcff7d709636305bba830e977ef/docs/strategy_research/g2_r3/method_repair/METHOD_R1_1_PIT_COST_ACCOUNTING.md) @ `cf2d5cc33774cdcff7d709636305bba830e977ef` | ACCEPTED_LIMITED_DESIGN_METHOD / `7def37d7c8aad02dd0c2769882fad61622e262db` |
| [tests/test_strategy_research_r3_architecture_invariants.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/b5d34aacd36dc27454944a22436db555c3f6eeb8/tests/test_strategy_research_r3_architecture_invariants.py) @ `b5d34aacd36dc27454944a22436db555c3f6eeb8` | IMPLEMENTER_SYNTHETIC_SELF_CHECK_NOT_INDEPENDENT_CLEARANCE / `5673af2f32fbd90d6f9fdf7e70f0c4a68f291269` |
| [evidence/v0.6/b_line/g2_overnight_p0_a/architecture_v1/ARCHITECTURE_SYNTHETIC_EXECUTION_RECEIPT.json](https://github.com/EXASHXE/btc-quant-agent-public/blob/b5d34aacd36dc27454944a22436db555c3f6eeb8/evidence/v0.6/b_line/g2_overnight_p0_a/architecture_v1/ARCHITECTURE_SYNTHETIC_EXECUTION_RECEIPT.json) @ `b5d34aacd36dc27454944a22436db555c3f6eeb8` | IMPLEMENTER_SYNTHETIC_SELF_CHECK_NOT_INDEPENDENT_CLEARANCE / `ae8330671d30f605c31502f00f3998a05e4fbddb` |

## 固定外部版本/许可/事件规格

| 外部固定来源 | SHA256 |
|---|---|
| [LICENSE](https://github.com/nautechsystems/nautilus_trader/blob/27a8e54e7ac3c57d6cbf8891f0283dfbaee97317/LICENSE) | `ee907919ec88c9c017b1f8b608db20960b6598aefcc4fe58820bde955d65ed3c` |
| [pyproject.toml](https://github.com/nautechsystems/nautilus_trader/blob/27a8e54e7ac3c57d6cbf8891f0283dfbaee97317/pyproject.toml) | `5dbc4591408bd65f7b35c2274348a7a02ff7b034a15f46d5f8628d3c8fbafa36` |
| [docs/concepts/backtesting/execution-flow.md](https://github.com/nautechsystems/nautilus_trader/blob/27a8e54e7ac3c57d6cbf8891f0283dfbaee97317/docs/concepts/backtesting/execution-flow.md) | `9f4c4e63c8db9a59c5acbc58f38344d1f59fb1f6ba8b926fb294602d9e6f4686` |
| [docs/concepts/backtesting/bar-execution.md](https://github.com/nautechsystems/nautilus_trader/blob/27a8e54e7ac3c57d6cbf8891f0283dfbaee97317/docs/concepts/backtesting/bar-execution.md) | `01ba774d55f60c4e4e941d7df8e3c1d565697f8e2bde9f30dce8a121b2e0c97c` |
| [docs/concepts/backtesting/accounts-and-margin.md](https://github.com/nautechsystems/nautilus_trader/blob/27a8e54e7ac3c57d6cbf8891f0283dfbaee97317/docs/concepts/backtesting/accounts-and-margin.md) | `91956a8c435fa2d211888b8575dcccb2730fe5c056f1767cfcc0cc11e4c71029` |
