# Post-P1 opportunity science R1 — 条件性研究优先级

**终态 `R4_SCIENCE_PRIORITIES_DESIGNED_PENDING_CONTROLLER_AND_P2`。设计完成，当前全部11项假设为 `SOURCE_BLOCKED_PENDING_P2`，无任何可执行科学研究准入或收益结论。** 本任务完成实际离线代数、反例与功效敏感性；没有执行策略、读取行情、验证Alpha或接受第三个引擎。

TASK_ID=`V06_POST_P1_SOL_HIGH_LONG_OPPORTUNITY_SCIENCE_AND_MEASUREMENT_REPLAN_R1`；Controller=`858735e0ae81b1ca0ced8cfa4c2e9ee5d01532e2`；Prompt=`d029a8f974c3809652f6a54c0f99dc1c7abfebc6`；代码起点=`e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`。当前执行器的系统描述是Codex/GPT-6；请求Sol High已记录，但variant/effort核验接口未暴露，没有伪称完成模型切换。

## 原八与前瞻方法权威

原始八ID与公式绑定 `e5b2006a89441f7eb2ec900e508aff451106b87a`；机器注册表保留每个原始candidate record、逐字family公式、共用指标及执行段、公式文件SHA256和family段SHA256，未修改旧注册表。两family×LONG/SHORT×4h/12h仍为八，不因稀疏、12h不合几何或排序而删除。原四个未用名额已经放弃，新增概念不继承它们的执行权。

STRUCTURAL_CONTINUATION：已闭合4h close/EMA20/EMA50方向次序、EMA20三根前斜率、ER12≥.35；1h突破前三根高/低、方向body≥.5ATR20、range≤2ATR20，距4h EMA20≤一4h ATR20；stop为decision close∓1.5小时ATR20。CLOSED_RETEST：同EMA次序但无ER/斜率门；突破前24h边界≥.25ATR、body≥.5ATR，固定边界/ATR；仅随后三根闭合小时，first confirmation，触及±.25ATR带、向外收盘≥.10ATR、方向body；先前反向越界.25ATR即取消；stop为突破至确认极值外.25 frozen ATR。

共用指标使用完整epoch-UTC分钟组成1h/4h，缺分钟则无有效bar；ATR20为20根TR算术平均，EMA以SMA种子和2/(N+1)，至少60根已闭合4h；ER零分母不合格。decision ATR/close30–250bp；实际入场stop30–250bp，TP2R，不移动stop求可行；绝对gap≤.25ATR；SL/TP同分钟SL先，stop gap按更差open，TP gap只计固定target，time exit在4h/12h上限的首个合法minute open且gap stop先。四小时cooldown，结构策略需更新4h，Retest一事件一次且veto不重试。详细逐字规范以机器注册表和固定原文为准。

R1.1 `cf2d5cc33774cdcff7d709636305bba830e977ef` 与前瞻AM01/AM02 R1.2 `821d23427a5f6d0b4635f32f226ddc779358ab72`分别保留。R1.2的同小时终结不得再seed、逐小时完整cursor、ACK proof floor和待确认负债不可被叫作“历史上已冻结的相同R1.1”。分钟[O,O+60000)的完整交易/Mark proof在O+120000；小时decision H+60000，最早fill H+120000；ACK≥max(economic+60000,所需proof,声明extra delay)。Funding S±15s需整个相交分钟proof，不能在S盲目FINAL。

每candidate×cost及单独资助control为独立1000USDT book；三资产allocation ceiling333.333333333333，5%buffer，预期≤1x，资金费reserve1.10，100USDT drawdown永久kill。R1.2可开资金A=max(0,.95Ec−Co−Rf−Lf)，kill参考Er=Ec−Pf；资金费union不能再重复扣Pf。此处只记录权威，不实现book/ACK/归约器。

原方法2026拟议calendar中“nonprotected”字样不能覆盖新Controller封锁：BTC `[2026-02-01,2026-08-01)`保持封闭，包括Option B Feb–Apr。2021/2023/2025 March warmup/April folds只作为此前Sol草案备选，未准入、未读取。旧收益已暴露的研究不能改称blind OOS。旧P1两条引擎路线永久终止；此前`SCIENCE_READY`只适用于有限proxy诊断设计，不是可重复使用的工程许可。

## 机制与机会：研究谁可能支付成本

延续的可证伪假说是价格结构反映较慢信息调整/被吸收的流动性，延迟入场后仍有足够同向调整；支付方是假设的迟到流动性，而不是已观测的“聪明钱”。反例是震荡、趋势耗竭与一次冲击的回落。Retest假说是边界回踩恢复可筛掉追价的 adverse selection；支付方是假设的迟到追随者或受困反向仓位。反例是虚假恢复、确认延迟错过主行情，以及同一冲击使两个family重复暴露。

LONG的拥挤/向下gap与SHORT的squeeze/向上gap并不经济对称；正资金费通常对LONG不利、负费率对SHORT不利，但没有在本任务观察这些事实发生。镜像公式使本次研究优先级同分，不构成选多或选空建议。hypothesized payer必须在未来固定对照下区分方向、时机与一般crypto风险暴露。

新增三项仅 `PROPOSED_ONLY_NOT_FROZEN`，具有不同预测方向或输入机制，参数没有偷偷加入原八：

| 新概念 | 区别与可证伪预测 | 需要的未来来源及明确阻断 |
|---|---|---|
| FAILED_BREAKOUT_REVERSAL_SHORT_04H | 抵抗位突破失败后受困LONG平仓导致反转，区别于两个原family的延续；持久信息趋势会否定反转解释 | Kline/true Mark/资金费/过滤器/成本权利；边界、recross与stop定义仍NOT_FROZEN |
| POSITIVE_FUNDING_CROWDING_SHORT_12H | 因可预见融资成本而拥挤LONG解除；资金费可能反映信息趋势而非拥挤，须用固定对照区分 | 可用时点已证明的funding、同步basis/index、Kline/Mark等；没有OI准入，不能将公布rate当真实仓位证据 |
| LIQUIDITY_ABSORPTION_LONG_04H | 主动卖压被bid补充吸收、卖方耗竭，区别于仅看闭合bar的延续；撤单/虚假depth/不利选择会否定 | sequence-correct L2、signed trades、同步receipt及Mark等全部未建立；不授予maker/queue收益 |

每项的输入proof、入场/stop/TP/horizon草案、失效机制、低样本/低流动性风险、source missingness与no-go均在注册表逐行给出。新概念的精确阈值和状态语义必须在独立未来预算中先冻结；不实施、不扫描、不以合成算例寻找最优阈值。

## 实际140组经济代数与边界

输入在计算前写入 `scenario_inputs.json` 并固定SHA256 `e41b232cfbc608b41ec7408fa02e21b631a429bba3f6d917db46514da3c598ba`。128组笛卡尔输入覆盖2 horizons×2 frictions×2 sides×4 invented signed payoffs×4 explicit schedules；额外12组覆盖±15s端点±1ms、tick、stop精确相等/略低、adverse gap、TP cap与1.20Mark shock。所有输入为 invented1000-notional/标量价格/毫秒列表，没有Kline reader或指标计算。

每行实际输出eligible synthetic settlements、gross/fee/drag/funding/net bp、USDT、R、binary break-even、reserve/liability、stress geometry；另输出两个人造价格的effective price、adverse tick与实际各腿notional fee桥。每个net都通过独立恒等式，不以“字典存在”认证。两价格代数不模拟成交，不是原方法全部监管与交易路径，也不是1000USDT book可以全额入场的权限。

恒定notional理想化：c=2(fee+halfspread+slip)+n×adverse funding+tick，net=d×move−c，USDT=N×net/10000，R=net/stop。没有leverage收益放大。固定stop s、TP2s、二点win/loss下 pBE=(s+c)/(3s)；timeouts/gaps/变化成本或变量risk会破坏二点解释。举例200bp gross、100bp stop、BASE两次4bp event ⇒ net170bp/17USDT/1.7R，pBE=.433333333333。此stop未必通过stress admission，算例不能变成候选可交易结论。

两腿实际notional不会恰好等于名义22/44bp：原价1000→1010、N1000、无spread/slip、每腿fee6bp ⇒ fee1.206USDT、net8.794USDT。将它默认为1.2会漏exit-notional差异。执行价格已嵌入spread/slip，不能再扣同一cash drag。R不是保证损失上限，gap可超过−1R；TP有利gap不能过计。reserve1.10覆盖恒定Mark合成责任，但.44不足以覆盖1.20Mark下.48责任，是已执行的反例，非保证金保险。

原固定stop≥2 stress C，TP=2stop≥3C，且stop≤250；因此C≤125只是必要几何，不是正期望。

| 明确合成clock | n范围示例 | STRESS C before tick | 必要stop |
|---|---:|---:|---:|
| 4h、已验证8h假设 | 最多1 | 52 | 104bp |
| 12h、已验证8h假设 | 最多2 | 60 | 120bp |
| 4h、unknown-hourly | 4，含端点可5 | 76/84 | 152/168bp |
| 12h、unknown-hourly | 12，含端点可13 | 140/148 | 280/296bp，超过250，静态不合格 |

“已验证8h”仅假设比较，不是当前来源事实。零次event仅在明确synthetic schedule/hold交集为空时计算0；实际missing proof输出UNKNOWN。时点FINAL正确可防重复收费/过早花钱，不能利用更晚得知的有利interval减少先前cost budget。Endpoint、tick、cap和Mark倍数可进一步恶化成本；hourly grid也不是交易所绝对event/cap上界。12h不合格应记WAIT/几何，不应报“12h实证亏损”。

LOW11bp+2bp/event只是非选择性乐观敏感性，BASE22+4与STRESS44+8是原proxy；绝不以LOW替换原stress admission。对于含端点hourly5/13 event，LOW C21/37、BASE42/74、STRESS84/148；BASE的便宜算术不能解开12h的STRESS gate。

## 真正执行的16 mutants与14机制反例

16个mutants实际改变了费用符号、slippage符号、funding数量、区间外charge、边界遗漏、方向、实测signed funding、重复计算、reserve、gap、TP overcredit、notional倍数、missing proof、12h eligibility、loss clipping与Mark shock结论。每个都有独立手算control，正常表达式被接受、错误表达式被断言拒绝；未对原引擎做patch或测试。

F01–F14分别为：stale Mark；SL+TP乐观排序；adverse gap clipping；同小时terminal/seed；缺中间Retest小时；S±15s的过早FINAL；known8h偷换hourly；12h STRESS假合格；低于100的fold被pooled修补；暴露OOS假blind；同source close不同Mark last-wins；paid仍计liability；候选A损失杀B；exit2/fill1。机器文件保存每个合法control、敌意输入、actual predicate结果与被否定机制。它们是有限合成审计predicate，不是某个外部engine已执行这些防护的证据。

旧输入中含HALF_TICK的label不能单凭名称证明精确half tie；冻结输入未改。另外两个明确10.005/.01、无drag手控验证buy向上/sell向下的half-tick算术。没有为了绿灯事后换掉失败fixture。

## 样本、成本与功效是不同门

实际计算18组均值normal planning、8组比例planning、6组有限N AR(1)敏感性；独立控制核验错误输入拒绝、multiplicity/信息量单调性与13/52/205 weeks手控。原positive proposal仍≥100 unique/fold、≥12 joint weekly blocks、stress mean≥5bp、median≥−5bp、至少两个fold非负、MTM drawdown≤10%、worst5% mean≥−300bp、single asset≤60%；改成30/fold的futility或occupied-week条件仍是旧草案，未获本任务执行效力。

原八×BASE/STRESS是16个描述性cost路径，不是16独立新策略。higher-cost net与paired incremental两个estimands保留8×2=16 one-sided multiplicity、alpha .05/16；LOW不可选。新增3 concepts是另一个未冻结family，不用“正交”措辞降低原8比较数。若未来共同发布positive claim，必须先分配全局错误预算；此处没有统计检验真实数据。

normal toy公式 n≈ceil[(z(1−.05/16)+z(.8))²(σ/5)²]。12独立等信息weeks、block influence σ=5/10/20bp的toy power分别76.72%/15.81%/3.09%，80%所需13/52/205weeks，MDE5.16/10.32/20.65bp。这些σ是人造假设，不是实际volatility或ratio estimator可靠variance。真实n、fat tails、异质block、缺失和serial correlation未知；normal近似和bootstrap10000 draws都不认证coverage。比例n公式仅二点/比例近似，[NIST公式](https://www.itl.nist.gov/div898/handbook/prc/section2/prc242.htm)说明其normal近似基础，不能把resolved TP hit rate当完整net expectancy。

29 eligible-day illustration下fill/day .5/1/2/4 ⇒ expected14.5/29/58/116/fold；100/fold需要3.448/day，只是期望，未知trigger×fill fraction不能伪造support。若full-duration，4h+4h cooldown约3/day/asset、12h+4h约1.5/day/asset，ACK/过滤器还会降低。Overlap reduces information：n12、ρ=.5的有限AR1 toy有效N约4.5，不是测得值；同时3资产等相关ρ=.8的有效资产数3/(1+2ρ)=1.154而不是3。不能相乘8 policies×3assets×weeks造功效。BTC-only100% exposure违反≤60% positive gate；只有BTC最多为另行批准的诊断宇宙，不能默默改原八。

future common-UTC-week bundles、fold隔离/12h purge embargo、empty blocks与14d敏感性需预先冻结；旧era不拼成相邻时间，empty fold/无效inference不得删draw求正。暴露历史development只能做固定诊断，不是独立OOS。正点估计、宽CI与成本proxy均为不充分证据；有adequate support且所有固定可评估family成员失败方可按未来批准规则经济no-go，不能用source-blocked/12h-ineligible推断全家族无edge。

## 事前rubric、条件优先级与不稳定性

Rubric在rank计算前固定：causal20%、falsifiable20%、economics20%、power15%、source15%、audit cost10%；各0–4。`priority_inputs.json`和`priority_rubric.json`分别固定hash，包含每行分数和原因。分数来自概念/审计复杂度、unknown source与几何，不来自任何行情收益或合成positive payoff平均。未验证Mark/rights为硬gate；metadata-only不提升到可执行。

实际9套source-state×LOW/BASE/STRESS排名、99行；54套leave-one-dimension-out、594行。UNKNOWN+STRESS展示：

| Hypothesis | rubric score / tied rank | 实际准入 |
|---|---:|---|
| STRUCTURAL_CONTINUATION_LONG_04H | 63.75 / 1 | SOURCE_BLOCKED_PENDING_P2 |
| STRUCTURAL_CONTINUATION_SHORT_04H | 63.75 / 1 | SOURCE_BLOCKED_PENDING_P2 |
| CLOSED_RETEST_LONG_04H | 55.00 / 3 | SOURCE_BLOCKED_PENDING_P2 |
| CLOSED_RETEST_SHORT_04H | 55.00 / 3 | SOURCE_BLOCKED_PENDING_P2 |
| PROPOSED_FAILED_BREAKOUT_REVERSAL_SHORT_04H | 52.50 / 5 | SOURCE_BLOCKED_PENDING_P2 |
| STRUCTURAL_CONTINUATION_LONG_12H | 50.00 / 6 | SOURCE_BLOCKED_PENDING_P2 |
| STRUCTURAL_CONTINUATION_SHORT_12H | 50.00 / 6 | SOURCE_BLOCKED_PENDING_P2 |
| CLOSED_RETEST_LONG_12H | 45.00 / 8 | SOURCE_BLOCKED_PENDING_P2 |
| CLOSED_RETEST_SHORT_12H | 45.00 / 8 | SOURCE_BLOCKED_PENDING_P2 |
| PROPOSED_LIQUIDITY_ABSORPTION_LONG_04H | 43.75 / 10 | SOURCE_BLOCKED_PENDING_P2 |
| PROPOSED_POSITIVE_FUNDING_CROWDING_SHORT_12H | 23.75 / 11 | SOURCE_BLOCKED_PENDING_P2 |

条件性Top4为STRUCTURAL_CONTINUATION LONG/SHORT04H（同分），随后CLOSED_RETEST LONG/SHORT04H（同分）。**不是四个已准入测试，更不是shortlist收益胜者。** 原八未来campaign如获授权仍披露全部8及WAIT，不按本排序偷偷删预算。Retest的更具体否证性与更高cursor成本分别计分；12h未知hourly不合格，只有独立有效schedule证据和原stop几何才能成为后续可评估政策。

54个删维比较有21个Top4成员变化：忽略特定因果/否证或信息量权重可让未冻结failed-breakout proposal或12h条目进入。侧向完全同分的显示顺序只是lexical。排序依赖价值权重，不能作为稳定效果rank；source gate仍对每套排名保持0 admission。READY_METADATA_ONLY仍需rights/true Mark/PIT/body新权限；UNKNOWN不执行；MULTIASSET_INCOMPLETE不得改宇宙求positive。

Controller下一门为独立检查本次SHA、预算/冻结/观察证据，结合另一路P2的最终证据裁决compatibility。未读取、等待或协调Gemini可变产物。设计完整与经济可验证并不等同；当前所有source-blocked已明确写入readiness。交付路径、P1缺陷覆盖和停止条件见配套measurement文件。

## 可重现与验证

运行 `PYTHONDONTWRITEBYTECODE=1 python scripts/strategy_research/postp1_science_algebra/run.py --output /tmp/payoff.json`，然后 `python scripts/strategy_research/postp1_science_algebra/priorities.py --output /tmp/priorities.json`。脚本仅读冻结合成JSON；不安装、不联网、不导入旧engine，不读market roots。Python3.12/3.13代数output bytes完全一致，output SHA256=`676d316a3febb441018df209f6f2b07f3f5cce83295e5874f61c6f577d1c759c`。实际pytest/ruff/JSON/scope/source checks见receipt；remote CI单独如实返回，不以本地QA为市场/engine/science验收。

| Pinned source | SHA / SHA256 |
|---|---|
| [prompt](https://github.com/EXASHXE/btc-quant-agent-public/blob/d029a8f974c3809652f6a54c0f99dc1c7abfebc6/prompts/v0.6/b_line/V06_POST_P1_SOL_HIGH_LONG_OPPORTUNITY_SCIENCE_AND_MEASUREMENT_REPLAN_R1.md) | `d029a8f974c3809652f6a54c0f99dc1c7abfebc6` / `740413b85423d399dd8dceb7aa12ba1692cf482a60364c914494f8c3bb876bd1` |
| [dispatch](https://github.com/EXASHXE/btc-quant-agent-public/blob/858735e0ae81b1ca0ced8cfa4c2e9ee5d01532e2/reviews/v0.6/b_line/V06_POST_P1_TERMINAL_PARALLEL_P2_METADATA_AND_OPPORTUNITY_SCIENCE_CONTROLLER_DISPATCH_R1.md) | `858735e0ae81b1ca0ced8cfa4c2e9ee5d01532e2` / `dcf84d5ab8966ec582f85c65c227c19ceb8bcd4702ab85043cea581e28705f8a` |
| [method](https://github.com/EXASHXE/btc-quant-agent-public/blob/e5b2006a89441f7eb2ec900e508aff451106b87a/docs/strategy_research/g2_r3/METHOD_DESIGN.md) | `e5b2006a89441f7eb2ec900e508aff451106b87a` / `14378dde7668291dc87aef91e3e55fadddad3a444d1d49284efa2c3cbcba9a77` |
| [register](https://github.com/EXASHXE/btc-quant-agent-public/blob/e5b2006a89441f7eb2ec900e508aff451106b87a/evidence/v0.6/b_line/g2_r3_design/CANDIDATE_REGISTER_PROPOSAL.json) | `e5b2006a89441f7eb2ec900e508aff451106b87a` / `d0f89bddfaec0e57c959cec043969059da10fec8aa45f81669dde8b80ea35a9b` |
| [r11](https://github.com/EXASHXE/btc-quant-agent-public/blob/cf2d5cc33774cdcff7d709636305bba830e977ef/docs/strategy_research/g2_r3/method_repair/METHOD_R1_1_PIT_COST_ACCOUNTING.md) | `cf2d5cc33774cdcff7d709636305bba830e977ef` / `a2943c9a541d93eaceb62a664edf0d03f0c9bbab6f4c4f73752831bcf14eb026` |
| [support](https://github.com/EXASHXE/btc-quant-agent-public/blob/cf2d5cc33774cdcff7d709636305bba830e977ef/docs/strategy_research/g2_r3/method_repair/R1_1_FUNDING_COST_AND_SUPPORT.md) | `cf2d5cc33774cdcff7d709636305bba830e977ef` / `f64520650a00e6784da94c4687caa8809430895fa268b56600ed7b47aad71415` |
| [r12](https://github.com/EXASHXE/btc-quant-agent-public/blob/821d23427a5f6d0b4635f32f226ddc779358ab72/reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_AM01_AM02_CONTROLLER_SPEC_FREEZE_R1.md) | `821d23427a5f6d0b4635f32f226ddc779358ab72` / `cea538034ea7695a326a2f2c91dcf4d246f2fafaa456f5935f4f375ce1d6e16f` |
| [prior_science](https://github.com/EXASHXE/btc-quant-agent-public/blob/57818b967a836382caa3fa95516d3e027e990f61/docs/strategy_research/g2_r3/scientific_strategy_review_r1/ECONOMIC_MECHANISM_COST_POWER_REPORT.md) | `57818b967a836382caa3fa95516d3e027e990f61` / `46db2d32e250bc6ecc464f80f3490bb02a2afdd7632fdef0ebc28f0f036104f0` |
| [p1_terminal](https://github.com/EXASHXE/btc-quant-agent-public/blob/fd3c13645df9ad2506293b109d3891cf57936208/reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_FINAL_INDEPENDENT_AUDIT_CONTROLLER_TERMINAL_NO_GO_R1.md) | `fd3c13645df9ad2506293b109d3891cf57936208` / `b9eba432a5a61a1e9a110279c8fc157173abaf62a588e36b7d8b22c9784a59ce` |
