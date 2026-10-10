# P2 S2 — Mark/Funding PIT scientific admission gate R1

**Terminal: `P2_S2_PIT_SCIENCE_AND_DIAGNOSTIC_PREREG_DESIGNED_PENDING_CONTROLLER`.** 实际完成52个固定合成算例，其中39个敌意时钟/来源/经济见证；13项metamorphic断言；Python3.12/3.13各69项focused pytest通过。当前真实source、rights、reader及measurement仍未准入；不是`SOURCE_ADMITTED`、有效P3或Alpha。

TASK=`V06_P2_S2_SOL_HIGH_PIT_FUNDING_MARK_AND_BTC_DIAGNOSTIC_PREREG_R1`。Controller=`b176f4361cd97d1d89c3e25173b2c72a6af93ec4`；published Prompt=`90b20f441ebefff3da0bf8457604b2ef98e25326`，通过固定路径最近发布commit与blob定位，与用户本轮完整指令相符；code/start=`e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`。当前系统描述Codex/GPT-6；Sol High请求已记录，variant/effort没有可核验/切换接口，未伪称选择成功。新独立分支不等待或读取Gemini可变产物。

## 权威与真实source blocker map

只有一个前瞻接口：`PIT_SOURCE_EVIDENCE_REQUIREMENTS.json`，在实验前冻结，所有真实权利/clock/cadence/source outcomes保持UNKNOWN。原八记录和公式身份保留；R1.1与R1.2区分；future method choices标 `NEEDS_CONTROLLER_METHOD_CHOICE`。敌意输入产生METHOD_CONFLICT不等于规范自身被证明矛盾，未据此替Controller选择。

| Source/permission | 固定证据 | 当前阻断 |
|---|---|---|
| BTC USD-M perp Kline 1m | `c6823dbc...` executor报告六个2021/2023/2025 March/April regular Parquet元数据 | 本任务没有重测；schema、完整minute、内容hash、交易所lineage、PIT与rights UNKNOWN |
| BTC true-minute Mark | `raw/mark_price`父目录metadata仅此 | exact child files、真实1m frequency、连续性、independent endpoint、revision/availability UNKNOWN；月filename不是证明 |
| Funding | `funding_events.csv`及raw funding父目录存在报告 | predicted/settled rate、initial known-at、corrected-at、settlement ID、rate/Mark proof、ACK UNKNOWN；不能读CSV header或rate |
| Filters/fees/friction | manifests/legacy hourly来源位置提示 | historical effective/published tick、lot、minnotional、fee applicability、spread/impact/caps UNKNOWN；当前规则不替代历史 |
| Spot | BTC_SPOT单独树 | 不是perp执行或Mark，不可alias |
| ETH/SOL | ETH cross_asset_1h为hourly auxiliary；SOL1m未证明 | 不是ETH perp1m；不满足原三资产positive条件 |
| Reader | 旧locator CI绿，但`ca0b6ea...` security NO-GO | 不导入/修补/复用；新reader独立接受UNKNOWN，mock/science tests不授真实读能力 |
| Measurement | `fd3c136...`旧/新P1引擎均TERMINAL_NO_GO | 本任务无engine；外部库、双trace、前瞻观察均需新独立验收 |
| Rights/protected | owner位置声明不是许可；BTC2026-02至08封闭 | 六文件footer/schema/timestamps/price/rate各权限分离；A-line/H39/H40/H41/forward/私密凭据仍零访问 |

## Clock dimensions 与精确proof floor

UTC整数ms：minute `[O,O+60000)`、exclusive close=`O+60000`、publisher inclusive close=`O+59999`。`event_start/close`、原始`source_observed_at`、`available_at`、`corrected_at`、`settlement_at`各有独立意义；现在archive retrieval绝不是过去receipt。缺任一需要的原始证明返回SOURCE_UNPROVEN，不捏造A=event，也不把未知资金费当零。

原冻结reconstructed完整Kline/Mark minute availability≥O+120000，标ARCHIVAL_EVENT_TIME_RECONSTRUCTED而非真实exchange receipt。小时close H的signal≥H+60000、earliest hypothetical execution H+120000；legal features仅用其各输入proof的最大值。固定slot缺proof则WAIT/blocked，不事后回写slot、重复尝试Retest或用未来minute open生成signal。

R1.1 modeled ACK=execution+60000不是实时receipt。R1.2 prospective ACK≥max(economic+60000,所有required proof,声明extra delay)，不是历史相同R1.1。例如H=0，execution120000，所需entry-minute `[120000,180000)` 完整proof240000，则180000 ACK不满足R1.2。此差异会影响资金锁定/support，不得隐去或靠代码“选择较快”解决。

Genuine LOOKAHEAD包含event>D，即使available谎称较早；available>D；宣称availability在source observation/correction/required proof之前；使用较晚最终rate/Mark correction选择较早entry。合法未来数据在较早asof中不出现；如果只是缺证明、timestamp字段未知或没有所需minute，则SOURCE_UNPROVEN，不能将所有未知一律断言为已发生lookahead。

## True Mark 与更正/排列的准入条件

必须证明独立perp Mark endpoint、matching symbol、明确1m interval与每个已准入UTC minute唯一/完整/原始物理ordering。Trade-price OHLC或9个daily Mark不能制造1m Mark；价格数值恰好相等不是alias证据，endpoint/source identity混用才是。缺minute不interpolate、不forward fill。

Oracle接受少量invented observation tuples，分别检验raw physical-monotonic声明和tuple canonicalization。list排列可不同，合法asof必须相同；它没有替真实文件认证排序/连续性。同source/symbol/close/revision相矛盾price或clock及同ID改payload，正反排列都CONFLICT_SOURCE_FAIL_CLOSED。合法retransmission只有完整相同envelope可以idempotent；这不是把真实source重复行当unique proof。

更正必须有不可变version/parent、同source/symbol/close、original known-at与corrected-at，按cut选当时已可见版本；未来correction不能改变旧snapshot。Funding也须保留原始/更正publication来源，scalar rate oracle检查更正不能backdate；它不假称已经实现真实funding全版本档案的reader。多Mark provider无法在本任务选择“较好”source，须Controller预先固定authority，否则METHOD_CONFLICT。

## Funding signed cash 与时点/geometry

Observed predicted rate可在其event/publication已知后作明确预测输入，但不证明eventual settled actual rate或cash。Final actual rate必须在settlement及发布proof之后；过去entry不得读取未来最终值。正rate的cashflow=−side×notional×settlement-Mark倍率×rate/10000：LONG付、SHORT收；负rate反转。未ACK credit不得增加已确认现金；debit仍是非负unpaid liability。Selection stress永远是4/8bp adverse proxy，不因SHORT正rate有利而减免。

Oracle的`rate_event`严格指invented forecast-publication或settled-final事件，不是交易所`calc_time`。原始calc_time可能不同于settlement/publication，应独立保存，不snap也不强制改成S；真实CSV若只有该列而无可证明的字段映射/known-at则SOURCE_UNPROVEN/NEEDS_CONTROLLER_METHOD_CHOICE，不能据此宣称早calc_time必然lookahead。

S ownership window为 `[S−15000,S+15000]` inclusive，必须等所有相交minute完整proof。最后相交minute end+60000与rate proof都满足才FINAL，ACK再不早于这些proof及declared delay。S=0的右侧minute要到120000才proof，不是60000；S=45000的+15s触及下一minute边界，保守proof180000。提前FINAL/ACK会产生LOOKAHEAD；尚无proof则UNKNOWN/conditional，不清账。

常数例N1000、rate4bp ⇒LONG cashflow−.4；ACK前cash0/liability.4，1.10 reserve.44；knowledge179999仍未ACK，180000 equality才cash−.4/owed0。SHORT正ratecredit.4、ACK前cash0/owed0但未决receivable仍不terminal-clear。1.20 Mark shock下payable.48、cover.44、shortfall.04，1.10不是保证。已经paid却still liable是ACCOUNTING_CONTRADICTION；paid Funding而fee2未付仍UNPAID_TERMINAL，不用Co/Rf/Lf/Pf四个零代替全面财务清零。

单一已FINAL结算的cover在该笔ACK后为0；已证明的credit无debit cover，未ACK credit仍不入现金。其他future/conditional obligations不在本scalar投影内，不能据此释放别笔reserve。自查修复初版ACK后仍显示cover的错误并增加断言；冻结fixture/expected未改，最终实测结果与QA以receipt为准。

固定stress C=44+8n+adverse tick bound；stop≥2C、TP2stop≥3C、stop30–250bp。4h/12h起点与funding clock须显式：

| Clock scenario（纯合成，非来源事实） | n | stress C / minstop |
|---|---:|---:|
| 4h known8h，已固定相位 | 至多1 | 52 / 104bp before tick |
| 12h known8h，已固定相位 | 至多2 | 60 / 120bp before tick，条件可能 |
| 4h hourly、入场H+120s避开端点 | 4 | 76 / 152bp before tick |
| 12h hourly、入场H+120s避开端点 | 12 | 140 / 280bp，超过250 |
| 含S±15s端点的合成4h/12h区间 | 5 / 13 | 84 / 168bp；148 / 296bp |

本任务固定oracle起点0供边界压力检查，不声称实际hourly signal会在0入场；原H+120s在不同相位可只交4/12个event，结论仍12h STRESS不合固定stop。UNKNOWN cadence只能使用完整声明hourly proxy grid，不能取两个8h timestamps冒称其已验证；proxy grid也不是所有真实event/cap的绝对上界。12h静态不合格不是实证亏损，4h几何可行也不是正期望。

Fee/gap另外进入成本：22/44是交易代理，不认证费用或流动性。静态同minute SL+TP按SL先；stop200bp、额外gap30bp、交易44bp、两个8bp event，closed-form损失为−290bp，不能clip−1R或只扣−200。TP有利gap只能计固定2R；embedded friction不能再cash扣一遍。此算术例不模拟bar/fill，未来工具必须独立执行原worst-case/资金不变量。

## Source falsifiers before data：52实测行

所有fixture在第一次运行前冻结，SHA256=`a3b53bcf823045db4cae80ce91b049375ff68b0a6b0ce1f58fb0f45ab1ff38a3`。下表每个expected code事前固定，actual对比有真实assert；机器文件保存完整causal clocks、availability、输入、expected values、actual。39hostile包括一个1.10覆盖失败的经济反例；其正确输出为shortfall而非拒绝合法输入，不能将其误算成39个实际source读取失败。

| ID / hostile | Synthetic causal clocks | 事前expected与actual（相同） | 待证明source证据 |
|---|---|---|---|
| C01 / False — Legal exclusive-minute visibility | event=60000,observed=120000,A=120000,proof=120000,D=180000 | VISIBLE_SYNTHETIC | 原始event/receipt/available与required feature/ACK proof envelope |
| C02 / True — Future event despite early availability | event=200000,observed=120000,A=120000,proof=120000,D=180000 | LOOKAHEAD | 原始event/receipt/available与required feature/ACK proof envelope |
| C03 / True — Availability after decision | event=60000,observed=120000,A=200000,proof=120000,D=180000 | LOOKAHEAD | 原始event/receipt/available与required feature/ACK proof envelope |
| C04 / True — Historical available_at missing | event=60000,observed=120000,A=None,proof=120000,D=180000 | SOURCE_UNPROVEN | 原始event/receipt/available与required feature/ACK proof envelope |
| C05 / True — Availability before original observation | event=60000,observed=120000,A=90000,proof=120000,D=180000 | LOOKAHEAD | 原始event/receipt/available与required feature/ACK proof envelope |
| C06 / True — R1.2 minute proof floor backdated | event=59999,observed=60000,A=60000,proof=120000,D=180000 | LOOKAHEAD | 原始event/receipt/available与required feature/ACK proof envelope |
| C07 / True — Stale current-decision Mark | event=59999,observed=120000,A=120000,proof=120000,D=180000 | SOURCE_UNPROVEN | 原始event/receipt/available与required feature/ACK proof envelope |
| C08 / False — Genuine Mark asof | D=180000; source close/A/revision见机器observation tuples | ASOF_SYNTHETIC | selected exact minute源、完整UTC timestamp/identity/canonical内容与physical ordering |
| C09 / True — Trade-price alias masquerades as Mark | D=180000; source close/A/revision见机器observation tuples | SOURCE_UNPROVEN | 唯一预选Mark endpoint、instrument、frequency原始manifest |
| C10 / True — Daily Mark does not prove minute stream | D=180000; source close/A/revision见机器observation tuples | SOURCE_UNPROVEN | 唯一预选Mark endpoint、instrument、frequency原始manifest |
| C11 / True — Missing required middle minute | D=180000; source close/A/revision见机器observation tuples | SOURCE_UNPROVEN | selected exact minute源、完整UTC timestamp/identity/canonical内容与physical ordering |
| C12 / True — Contradictory same source-close price | D=180000; source close/A/revision见机器observation tuples | CONFLICT_SOURCE_FAIL_CLOSED | selected exact minute源、完整UTC timestamp/identity/canonical内容与physical ordering |
| C13 / True — Immutable ID clock contradiction | D=180000; source close/A/revision见机器observation tuples | CONFLICT_SOURCE_FAIL_CLOSED | selected exact minute源、完整UTC timestamp/identity/canonical内容与physical ordering |
| C14 / False — Future correction preserves earlier asof | D=180000; source close/A/revision见机器observation tuples | ASOF_SYNTHETIC | immutable原/更正version parent、各known-at与corrected-at |
| C15 / False — Later legal correction changes later snapshot | D=300000; source close/A/revision见机器observation tuples | ASOF_SYNTHETIC | immutable原/更正version parent、各known-at与corrected-at |
| C16 / True — Correction lacks parent provenance | D=300000; source close/A/revision见机器observation tuples | SOURCE_UNPROVEN | immutable原/更正version parent、各known-at与corrected-at |
| C17 / True — Future correction substituted into old snapshot | D=180000; source close/A/revision见机器observation tuples | LOOKAHEAD | immutable原/更正version parent、各known-at与corrected-at |
| C18 / True — Minute starts not UTC aligned | D=180000; source close/A/revision见机器observation tuples | SOURCE_UNPROVEN | selected exact minute源、完整UTC timestamp/identity/canonical内容与physical ordering |
| C19 / True — Raw physical timestamp ordering unproven | D=180000; source close/A/revision见机器observation tuples | SOURCE_UNPROVEN | selected exact minute源、完整UTC timestamp/identity/canonical内容与physical ordering |
| C20 / True — Source usage rights missing | D=180000; source close/A/revision见机器observation tuples | SOURCE_UNPROVEN | exact source owner consent/provider terms与分层byte许可 |
| C21 / False — Independent Mark may numerically equal trade price | D=180000; source close/A/revision见机器observation tuples | ASOF_SYNTHETIC | selected exact minute源、完整UTC timestamp/identity/canonical内容与physical ordering |
| C22 / True — Multiple Mark providers not preselected | D=180000; source close/A/revision见机器observation tuples | METHOD_CONFLICT | 唯一预选Mark endpoint、instrument、frequency原始manifest |
| C23 / True — Eventual actual rate used before settlement | S=120000,rateA=120000,ownership=120000,FINAL=120000,ACK=180000,knowledge=150000 | LOOKAHEAD | predicted vs settled原始publication、S身份、ownership-window与rate/ACK proof |
| C24 / True — Actual final rate event backdated before settlement | S=0,rateA=30000,ownership=120000,FINAL=120000,ACK=180000,knowledge=150000 | LOOKAHEAD | predicted vs settled原始publication、S身份、ownership-window与rate/ACK proof |
| C25 / True — Prediction treated as settled cash | S=0,rateA=30000,ownership=120000,FINAL=120000,ACK=180000,knowledge=150000 | SOURCE_UNPROVEN | predicted vs settled原始publication、S身份、ownership-window与rate/ACK proof |
| C26 / True — Funding initial publication missing | S=0,rateA=None,ownership=120000,FINAL=120000,ACK=180000,knowledge=150000 | SOURCE_UNPROVEN | predicted vs settled原始publication、S身份、ownership-window与rate/ACK proof |
| C27 / True — Funding FINAL before intersecting minute proof | S=0,rateA=30000,ownership=120000,FINAL=60000,ACK=180000,knowledge=150000 | LOOKAHEAD | predicted vs settled原始publication、S身份、ownership-window与rate/ACK proof |
| C28 / True — ACK before legal source proof | S=0,rateA=30000,ownership=120000,FINAL=120000,ACK=60000,knowledge=150000 | LOOKAHEAD | predicted vs settled原始publication、S身份、ownership-window与rate/ACK proof |
| C29 / True — Ownership proof absent | S=0,rateA=30000,ownership=None,FINAL=120000,ACK=180000,knowledge=150000 | SOURCE_UNPROVEN | predicted vs settled原始publication、S身份、ownership-window与rate/ACK proof |
| C30 / True — Terminal unpaid fee cannot disappear | S=0,rateA=30000,ownership=120000,FINAL=120000,ACK=180000,knowledge=180000 | UNPAID_TERMINAL | 固定cut的itemized owed/paid/ACK与fee/funding残项独立会计证明 |
| C31 / True — Paid funding still shown liable | S=0,rateA=30000,ownership=120000,FINAL=120000,ACK=180000,knowledge=180000 | ACCOUNTING_CONTRADICTION | 固定cut的itemized owed/paid/ACK与fee/funding残项独立会计证明 |
| C32 / True — Unknown cadence silently replaced by8h | prospective hold[0,14400000],UNKNOWN; source actualA=UNKNOWN | METHOD_CONFLICT | 历史effective tick/lot/fee、cadence/cap、friction与Mark bounds；proxy不得代替 |
| C33 / True — Historical lot/tick provenance absent | prospective hold[0,14400000],UNKNOWN; source actualA=UNKNOWN | COST_UNKNOWN | 历史effective tick/lot/fee、cadence/cap、friction与Mark bounds；proxy不得代替 |
| C34 / True — Historical fee applicability absent | prospective hold[0,14400000],UNKNOWN; source actualA=UNKNOWN | COST_UNKNOWN | 历史effective tick/lot/fee、cadence/cap、friction与Mark bounds；proxy不得代替 |
| C35 / True — 12h hourly STRESS cannot fit250stop | prospective hold[0,43200000],UNKNOWN; source actualA=UNKNOWN | STRESS_COST_GEOMETRY_INELIGIBLE | 历史effective tick/lot/fee、cadence/cap、friction与Mark bounds；proxy不得代替 |
| C36 / True — BTC-only inheriting multiasset positive | protocol choice before outcomes; synthetic static review; actual market clock N/A/UNKNOWN | METHOD_CONFLICT | Controller新protocol身份/权限边界与original-positive/diagnostic区别 |
| C37 / True — Sparse fold hidden by pooled counts | protocol choice before outcomes; synthetic static review; actual market clock N/A/UNKNOWN | INSUFFICIENT_SUPPORT | future unique event/fold IDs、共同calendar block与support统计合同 |
| C38 / True — Eight aliases used to cut sixteen endpoints | protocol choice before outcomes; synthetic static review; actual market clock N/A/UNKNOWN | METHOD_CONFLICT | 唯一预选Mark endpoint、instrument、frequency原始manifest |
| C39 / True — Exposed development relabeled blind OOS | protocol choice before outcomes; synthetic static review; actual market clock N/A/UNKNOWN | METHOD_CONFLICT | prior-exposure ledger与first-pushed freeze在body前的proof |
| C40 / True — R1.1 and R1.2 called identical | protocol choice before outcomes; synthetic static review; actual market clock N/A/UNKNOWN | METHOD_CONFLICT | Controller新protocol身份/权限边界与original-positive/diagnostic区别 |
| C41 / True — Proxy spread/slippage called actual cost | protocol choice before outcomes; synthetic static review; actual market clock N/A/UNKNOWN | COST_UNKNOWN | Controller新protocol身份/权限边界与original-positive/diagnostic区别 |
| C42 / True — Synthetic tests claimed to grant real-body access | protocol choice before outcomes; synthetic static review; actual market clock N/A/UNKNOWN | METHOD_CONFLICT | Controller新protocol身份/权限边界与original-positive/diagnostic区别 |
| C43 / False — Long positive rate pending debit | S=0,rateA=30000,ownership=120000,FINAL=120000,ACK=180000,knowledge=150000 | FUNDING_SYNTHETIC | predicted vs settled原始publication、S身份、ownership-window与rate/ACK proof |
| C44 / False — Short positive rate unACKed credit | S=0,rateA=30000,ownership=120000,FINAL=120000,ACK=180000,knowledge=150000 | FUNDING_SYNTHETIC | predicted vs settled原始publication、S身份、ownership-window与rate/ACK proof |
| C45 / False — Short negative rate debit sign reversal | S=0,rateA=30000,ownership=120000,FINAL=120000,ACK=180000,knowledge=150000 | FUNDING_SYNTHETIC | predicted vs settled原始publication、S身份、ownership-window与rate/ACK proof |
| C46 / False — Long negative rate unACKed credit | S=0,rateA=30000,ownership=120000,FINAL=120000,ACK=180000,knowledge=150000 | FUNDING_SYNTHETIC | predicted vs settled原始publication、S身份、ownership-window与rate/ACK proof |
| C47 / False — ACK equality settles debit once | S=0,rateA=30000,ownership=120000,FINAL=120000,ACK=180000,knowledge=180000 | FUNDING_SYNTHETIC | predicted vs settled原始publication、S身份、ownership-window与rate/ACK proof |
| C48 / False — 12h synthetic known8h conditionally feasible | prospective hold[0,43200000],KNOWN_SYNTHETIC_8H; source actualA=UNKNOWN | GEOMETRY_POSSIBLE_CONDITIONAL | 历史effective tick/lot/fee、cadence/cap、friction与Mark bounds；proxy不得代替 |
| C49 / False — 4h conservative hourly conditionally feasible | prospective hold[0,14400000],UNKNOWN; source actualA=UNKNOWN | GEOMETRY_POSSIBLE_CONDITIONAL | 历史effective tick/lot/fee、cadence/cap、friction与Mark bounds；proxy不得代替 |
| C50 / False — Known prediction visible but never settlement cash | S=600000,rateA=60000,ownership=120000,FINAL=120000,ACK=180000,knowledge=150000 | PREDICTION_VISIBLE_NOT_SETTLED | predicted vs settled原始publication、S身份、ownership-window与rate/ACK proof |
| C51 / True — Unknown cadence sparse grid cannot pass | prospective hold[0,14400000],UNKNOWN; source actualA=UNKNOWN | METHOD_CONFLICT | 历史effective tick/lot/fee、cadence/cap、friction与Mark bounds；proxy不得代替 |
| C52 / True — Current Mark shock exceeds1.10 reserve | S=0,rateA=30000,ownership=120000,FINAL=120000,ACK=180000,knowledge=150000 | FUNDING_SYNTHETIC | 当时可用Mark/cover与合法source-proof后的真实liability |

13项实测metamorphic：availability延后不得提高准入；future correction不改变旧asof；同clock冲突两排列拒绝；adverse funding增加不能改善cashflow；terminal fee不能消失；unknown cadence不得偷换8h；BTC-only不得继承multiasset positive；12h hourly不合格而known8h仅conditional；负rate反转方向；ACK equality之前cash不清；合法输入排列deterministic；±15s edge/±1ms outside；纯scalar oracle无network/real-body reader。`oracle.py`只import Decimal与future annotations；runner只读自己固定JSON并写一个固定研究artifact，CLI拒绝--data-root。

独立pytest另核验derived feature proof max、Funding correction provenance、four-way signed cash、extra ACK delay、nonpositive Mark/mismatched symbol、负notional/fee/tick、Decimal global context和真实CLI。初次执行C43失败为zero-string `0E-12` vs固定12位小数，修正serialization，不改fixture或expected；初次test lint缺check=False已修正，记录在receipt，不隐去失败。

真实source code disposition不能从synthetic PASS推得：LOOKAHEAD是已提供非法clock的见证；SOURCE_UNPROVEN是证明缺口；COST_UNKNOWN是cost识别缺口；INSUFFICIENT_SUPPORT是有限样本缺口；METHOD_CONFLICT需prospective Controller choice；ACCOUNTING_CONTRADICTION/UNPAID_TERMINAL需财务合同修复/拒绝；全部都不能叫NO EDGE。

## Scope、QA与后续门

零本地market body/footer/CSV header、零owner-root重扫、零market API/私密账户、零protected/A-line/H39/H40/H41结果读取。来源仅固定Git governance/method/metadata报告与invented数字；访问计数证明针对任务命令/read provenance，非OS-wide遥测保证。没有导入旧locator/P1、没有order/fill/journal/event reducer或strategy indicator。

JSON、原八ID/公式/source身份、freeze hashes、scope paths和exact parent分别验证；69 focused tests每Python均0fail/0skip，scoped Ruff PASS，CLI完整output bytes跨Python一致。未跑本地full research suite；GitHub CI仅读取head/job状态，不取protected outcome logs。发布后remote SHA/parent/files/实际CI外部核验，不写不可能自引用的commit SHA。

Controller下一门：审核科学interface、未来source-right/capability选择以及独立Gemini最终证据；本任务不自动准入reader/source或冻结策略。最小未来读取草案及BTC-only估计量见配套blueprint。

| Fixed source | Commit / blob |
|---|---|
| [prompt](https://github.com/EXASHXE/btc-quant-agent-public/blob/90b20f441ebefff3da0bf8457604b2ef98e25326/prompts/v0.6/b_line/V06_P2_S2_SOL_HIGH_PIT_FUNDING_MARK_AND_BTC_DIAGNOSTIC_PREREG_R1.md) | `90b20f441ebefff3da0bf8457604b2ef98e25326` / `c39c1616e157dc41e686c455daaec63a155a8389` |
| [dispatch](https://github.com/EXASHXE/btc-quant-agent-public/blob/b176f4361cd97d1d89c3e25173b2c72a6af93ec4/reviews/v0.6/b_line/V06_P2_S2_SOURCE_READINESS_AND_PIT_PROSPECTIVE_PARALLEL_DISPATCH_R1.md) | `b176f4361cd97d1d89c3e25173b2c72a6af93ec4` / `05da916ce5d6590067c45fae6056017d3d9e0057` |
| [source_design](https://github.com/EXASHXE/btc-quant-agent-public/blob/519b2e9ba2ca847e76ad9c0a7fbafcec5fcda158/reviews/v0.6/b_line/V06_P2_POST_LOCATOR_TRUE_MINUTE_MARK_FUNDING_PIT_SOURCE_ADMISSION_DESIGN_R1.md) | `519b2e9ba2ca847e76ad9c0a7fbafcec5fcda158` / `a28e88792f4198cb6524421a475cd37eecfa695f` |
| [metadata_report](https://github.com/EXASHXE/btc-quant-agent-public/blob/c6823dbc46249cac43aa10400aacbbe9f4542410/docs/strategy_research/g2_r3/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_METADATA_REPORT.md) | `c6823dbc46249cac43aa10400aacbbe9f4542410` / `de98309b554546354815ae13a0f2a659001bed65` |
| [reader_security_no_go](https://github.com/EXASHXE/btc-quant-agent-public/blob/ca0b6ea62613e6981b6f818f37f45be8c1d74901/reviews/v0.6/b_line/V06_P2_OWNER_ROOT_VERIFIER_ONE_SHOT_REPAIR_CONTROLLER_FINAL_SECURITY_VERDICT_R1.md) | `ca0b6ea62613e6981b6f818f37f45be8c1d74901` / `2e19a3e570593a5d665393d0d6e18933330cd317` |
| [method](https://github.com/EXASHXE/btc-quant-agent-public/blob/e5b2006a89441f7eb2ec900e508aff451106b87a/docs/strategy_research/g2_r3/METHOD_DESIGN.md) | `e5b2006a89441f7eb2ec900e508aff451106b87a` / `fb701b0be825f85801377f86eb80ba4f766ebaed` |
| [original_register](https://github.com/EXASHXE/btc-quant-agent-public/blob/e5b2006a89441f7eb2ec900e508aff451106b87a/evidence/v0.6/b_line/g2_r3_design/CANDIDATE_REGISTER_PROPOSAL.json) | `e5b2006a89441f7eb2ec900e508aff451106b87a` / `d337542f6482938c37eb6b4e43255cdf4d09751a` |
| [r11](https://github.com/EXASHXE/btc-quant-agent-public/blob/cf2d5cc33774cdcff7d709636305bba830e977ef/docs/strategy_research/g2_r3/method_repair/METHOD_R1_1_PIT_COST_ACCOUNTING.md) | `cf2d5cc33774cdcff7d709636305bba830e977ef` / `7def37d7c8aad02dd0c2769882fad61622e262db` |
| [r12](https://github.com/EXASHXE/btc-quant-agent-public/blob/821d23427a5f6d0b4635f32f226ddc779358ab72/reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_AM01_AM02_CONTROLLER_SPEC_FREEZE_R1.md) | `821d23427a5f6d0b4635f32f226ddc779358ab72` / `ecafeec0100f8881a700f9e3372a717aeab93b2b` |
| [prior_science](https://github.com/EXASHXE/btc-quant-agent-public/blob/5032259954e001635c97110c9c50e4a35a2c95b5/docs/strategy_research/g2_r3/postp1_opportunity_science_r1/SCIENCE_OPPORTUNITY_PRIORITIES_AND_FALSIFIERS.md) | `5032259954e001635c97110c9c50e4a35a2c95b5` / `ab4c6f8b12dccc75e4dbe335b917e53cba2543c2` |
| [p1_no_go](https://github.com/EXASHXE/btc-quant-agent-public/blob/fd3c13645df9ad2506293b109d3891cf57936208/reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_FINAL_INDEPENDENT_AUDIT_CONTROLLER_TERMINAL_NO_GO_R1.md) | `fd3c13645df9ad2506293b109d3891cf57936208` / `9dfcf9f4ff8284765240c212550beb460438c0a5` |
