# Post-P1 最小测量与未来准入路线

**偏好条件性方案B：先以两个独立专用oracle审核有限会计/PIT traces，再决定能否支付一次小型诊断的成本。** 当前B同样 `CONDITIONALLY_UNACCEPTABLE`，因为尚无已准入数据或独立执行的测量语义验收。此为设计选择，不是P1替代引擎第三次实现，也不授予P3/P4。

冻结八公式、R1.1、前瞻R1.2与终止P1的权威见科学报告/机器manifest。旧science报告选择的“A旧八有限诊断”属于此前研究路线字母；这里A/B/C表示新任务的测量交付选项，不能把其“A”历史建议当成本次库选型许可。旧VirtualBook及alternative event-ledger均不得fix/fork/wrap/import，不能借双oracle名称写新的order/fill/scheduler/journal。

## 恰好三项未实现交付选项

| 选项 | 能提供的研究证据 | 当前缺口/边界 | 条件性成本与停止条件 |
|---|---|---|---|
| A 外部成熟库+独立审核adapters | 可复用已有backtesting/accounting组件，未来可能承载完整原八受资助book；以NautilusTrader官方文档作设计比较 | 文档不证明本方法兼容，未安装/运行。库版本、PIT/Mark/funding/cash adapters需独立固定与执行验收；原engine不得包进adapter | 源准入+版本冻结+6缺陷验收+SL-first/next-open兼容；若必须写新general engine或无法满足时点，STOP。不以当前版本名义认证回测 |
| B 独立专用会计/PIT oracle的有限trace测量 | 先验证小型透明资金/clock切片、duplicate/quantity/capital/proof/terminal合同；未来可做冻结的matched event诊断，明确是非受资助episode统计 | 不是全市场fill engine，不产生完整策略portfolio ROI/全路径MTM。原positive screen若仍要求完整受资助book，B自身不足，必须另获合格测量途径或STOP，不能偷偷降低endpoint | 最小source/time/right manifest→固定有限trace→两种独立计算→独立Controller verdict；任何差异STOP，不反复patch同一campaign。偏好作为下一测量门 |
| C 前瞻observational study | 以未来真实causal receipt观察预先固定信号/费用/标记路径，避免历史回测的暴露混淆 | 只观察，不下单；hypothetical returns≠认证fill。Mark/费/impact/时间权利仍需准入；稀疏样本、日历相关、资金费认知与不可控regime使研究很慢 | 固定calendar/support/停止一次，不自动360天/延长收集。若预测信息不够或operator权利不清，STOP；无live/testnet/真实资金许可 |

官方[Nautilus backtesting概览](https://nautilustrader.io/docs/latest/concepts/backtesting/)描述复用的系统组件与结果接口，属于成熟外部框架候选背景，不能认证本任务adapter或原方法。文档审查日期2026-10-10，`latest`是可变页，未来必须冻结真实library version/代码SHA而不是只引用latest。

其官方[testing guide](https://nautilustrader.io/docs/latest/developer_guide/testing/)描述Rust与Python测试、CI测试release wheel及定期doctests，支持“已有上游测试体系”的有限判断；本任务没有运行这些测试，也没有独立核验任一library release的当前完整CI或本方法契约。

该库[bar execution](https://nautilustrader.io/docs/latest/concepts/backtesting/bar-execution/)明确用合成OHLC路径，default open→high→low→close，adaptive也是heuristic；并无原生next-bar-open fill mode。这与原方法SL-first及H+120s的兼容是关键未验证点，不能靠配置名字推断通过。[Data timestamps](https://nautilustrader.io/docs/latest/concepts/data/#timestamps)把ts_init定义为初始化时间，非保证receipt；闭合时点也不自动满足额外60s archival proof lag。[Funding/accounts](https://nautilustrader.io/docs/latest/concepts/backtesting/accounts-and-margin/)说明按funding边界更新账户，但不证明S±15s owner、延迟ACK或R1.2 conservative liability union。这里只审查方法文档，没有下载市场数据或安装库。

## 六个P1材料失败：逐方案必须独立执行的合同

下列都是未来验收合同，NOT_EXECUTED。当前14合成predicate及16代数mutants只验证设计中的反例能被辨认，未证明A/B/C任何工具已执行防护。有限oracle可验证固定结算切片，但不能假称覆盖未测的所有状态。

| P1失败见证 | A 外部库/adapter | B 专用双oracle有限trace | C 前瞻观察 |
|---|---|---|---|
| 重复source/symbol/close不同Mark，输入顺序改变最后price | 入库前canonical identity冲突拒绝；正反排列都error；不可last-wins；库内部再独立观察 | 两独立输入规范核对相同source-close的完整内容/时钟；冲突切片停止计算 | receipt log源identity不可变；矛盾record停止对应观察而非择优quote |
| exit2/fill1超量 | lot/filled inventory/partial bounds独立assert，反例必须拒绝且不clip0掩盖 | 手工有限trace将经济quantity总和与filled上界核对；超量行拒绝，不实施订单处理 | 若仅未资助episode，就不得报告真实inventory或position accounting；未来真实数量声明需单独核验 |
| 多候选共享资金/kill | candidate×scenario独立1000account，A solo/B solo/组合及reverse与loss100对照；不得共享capital | 每有限trace的candidate/case资本范围唯一，cross-policy损失不可改另一trace；未资助matched episodes不加ROI | 同时政策只观察独立hypothetical endpoint；共用真实风险如果发生必须另立估计量，不能称原八独立books |
| funding payable1/cover.4/shortfall0误清 | owned reserve/liability及cash claims外部核对；funding union和ACK once执行 | 预固定940→cash999/A940.05及ETH2不动的Decimal算术与另一独立表格；buffer shock显式不足 | 独立观察public rate/时点和可能ownership，不认证用户cash；没有owner证明则UNKNOWN/proxy，不付费当实测 |
| as-of proof floor与同ID改availability | 完整envelope含clock/hash；decision≤proof非法；ACK≥required proof；不能把ts_init自动当历史可用 | 法定source/available/economic表分离；proof前后1000→830.663455风险见证不得回写早decision；不建event scheduler | 原始receipt和event clock保存且同步；迟到更正只影响以后认知；未知receipt不伪造 |
| terminal clear却仍fee payable2 | 不能只查Co/Rf/Lf/Pf；inventory/fees/funding/receivable/ACK残留逐项及cash-to-net完整核对 | 固定起末余额+itemized fees/funding/gross与所有未决项双算；欠fee2不能ALL_ZERO；未完成trace不补未来price | 最后cut保留未决义务/删失，不把结束观察当义务清零；不能虚构未来ACK来闭合ROI |

另需原方法SL-first、worse stop gap、TP cap、4h/12h time cap、missing Retest hour、AM01 dual-use、known8h/hourly差异、partial quantity和cooldown不回退的专门合同。A如果内建机制与合同冲突而无法在既有允许adapter范围证明等价，停止A；不得转为第三custom engine。B如有限trace无法满足未来估计量，停止扩大解释；C如hypothetical fills/costs无法认证，保留观测/diagnostic等级。

## 偏好B的有限门与独立性

建议新Controller授权最多一套事前固定的12个finite trace tuples（不是本任务实现）：上述六项各一正/一负，共12；另对SL/TP、gap、Retest与资金费proof-clock合同是否需要更大预算由Controller预先明确，不夹带成已通过。输入只包含合法的固定source identities/clock/qty/price scalar/fee/liability切片，不提供市场stream循环、自动order route或全量策略回放。

Oracle1是固定Decimal closed-form表，Oracle2用独立手算/独立表格公式与来源proof核对，不共享同一函数、导入或生成器；独立审核者从exact SHA核验两者与raw admitted trace，不只diff相同实现。必须先写expected numeric/timing outcome再运行。当前algebra/test共享基础函数的QA只是开发验证，不冒称已实现未来双oracle独立验收。

12个tuple预算、工具版本与无body权限需要另行批准；此处是合同草案。输入不足、任一材料矛盾、任一forbidden-source、需要一般fill engine即停止并回Controller。没有R2修补预算，没有“测试通过再加更多trace”的隐式扩展。

若后续选择B做episode diagnostic，它检验有限、固定、非受资助事件的方向/机会时机与成本敏感性，不能覆盖完整原八监管、每分钟Mark MTM和book drawdown；必须用新科学root明确estimand差异并保留原八未被验证。若Controller坚持原方法完整positive-development门，未证明完整source/capital/MTM路径前禁止positive support；B先行会计门不替代完整测量接受。作为资源gate可以停止投入，而非发布“全部原策略无edge”。

## P2三种状态的兼容路线

| 独立未来P2状态 | 本次结论与下一步 |
|---|---|
| READY_METADATA_ONLY | root/文件footer存在也不是body/rights/PIT/true Mark允许；只能送Controller准备source/right admission，不读正文。全部hypotheses仍blocked |
| UNKNOWN | 无来源就停在science design，不运行empirical，不问用户历史行情正文，不等待Gemini才能完成本报告 |
| MULTIASSET_INCOMPLETE | 原BTC/ETH/SOL契约不全；不能删除资产变positive。Controller可另立BTC-only有限诊断科学root，明确100% exposure违反原60%positive gate；不能替换原八 |

不能把一张BTC67-part逻辑manifest解释为physical/data availability，也不把没有发现root解释为市场不存在。三资产可增加机会覆盖，但共同crypto shocks不能变成独立weekly复制。所有新机制涉及L2/OI/basis/publication inputs均没有准入证据，标 `SOURCE_BLOCKED_PENDING_P2`。

## 未来阶段草案：每门均需新权威

1. **P2 source/right admission**：独立P2的exact SHA/实际metadatacertainty，随后单独批准source/rights、continuous true-minute Mark、funding identity/cadence/caps/availability、historical filters、fee/spread/impact、排除protected与exposure ledger。metadata-only不能自授body读取。
2. **Outcome-blind science freeze**：Controller选择一次universe/calendar/estimand/cost等级；引用原八+R1.1+R1.2，冻结baseline budget与proposed budget分开。主路径若原八all-in则保留8，所有WAIT/ineligible披露；Top4是评审顺序而非4试验预算。新增概念最多本次3，没有old-slot复活，任何实际新候选需新campaign先冻结。保持protected BTC2026，原暴露开发窗不称blind。
3. **Minimal independent accounting/PIT acceptance**：从fixed SHA执行已授权finite contracts；A另需vendor version与adapter等价，B双oracle另需独立作者，C另需receipt/删失/cost认证。没有通过就不进入测量。不得用本任务208个QA数或旧P1 self-PASS顶替。
4. **Exact-SHA P3 first-pushed prereg**：future first-push hash远端核验在任何market body前；明确source/version/window/warmup/12h purge-embargo、controls、trade identity、funding/event endpoints、cost格、sampling/cluster/quantile/seed、prior exposure、stop/resource/multiplicity/no extensions。此文件不是effective prereg。
5. **另行授权恰好一次 limited empirical diagnostic**：只有独立新dispatch才准入选定正文与读取预算，固定原八或新的另行proposal budget，不同时试三种交付路线。最初bounded scope以一次固定calendar结尾，报告所有计算/blocked/zero-trade/WAIT；无事后追加month、切低cost、挑asset或换阈值。若source/cost无法识别，proxy-only不授positive shortlist/actual-cost economic no-go。
6. **Controller gate**：exact head/parent/files/actual CI、body capability、计数/会计/causality/missingness和科学预算分别审查。可能SOURCE_BLOCKED、SCIENTIFIC_NOT_READY、PROCEED_TO_SEPARATELY_AUTHORIZED_PREREG_DESIGN或显式new budget；不能授Alpha、live/testnet或复活原P1。

经济停止：12h unknown-hourly STRESS静态不合格，无合格政策时停止测量支出；不通过hard源或成本许可立即停止；support<100/fold、少joint blocks或overlap高则diagnostic-only/无positive。未来若要formal +5bp/80%power，必须在真实variance/dependence未知限制下做独立方法adequacy验收，不能凭100/fold或52toy weeks认证；不得自动开启52/205weeks的收集。少量/宽CI/全部WAIT可以结束资源campaign而经济真相仍不确定。

本任务不需要Astra来认定代数或缺源；未来若Controller要求formal confidence/ratio-estimator功效、组合family error budget或未解决clock/measurement契约，应单独授权方法审计。没有在本任务调用Astra或委托Gemini，也未赋予外部执行器Controller权限。

## 本任务实际交付

新增纯scalar algebra脚本、140固定算例、16检测mutants、14机制反例、32项power/dependence输入及priorities敏感性；没有order/position状态、event scheduler、journal、market ingestion或exchange API。修复初次scoped Ruff的8项开发lint后复核，未改冻结数字以求通过。所有进度checkpoint、输出hash、实际subprocess及pytest数、访问范围限制见机器receipt。最后commit/push一遍、remote exact SHA/direct parent/files/CI状态在最终返回独立核验；文件内部不写不可能自引用的final commit SHA。
