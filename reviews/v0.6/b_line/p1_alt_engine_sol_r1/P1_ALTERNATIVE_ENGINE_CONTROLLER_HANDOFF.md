# P1 替代引擎 Controller 交接 DRAFT

**单一终态：`P1_SPEC_AMENDMENT_REQUIRED`。推荐 A：事件溯源微引擎、双重记账、owner 资金约束与不可变 reducer。** 架构及下游实施合同已完整提出，Controller 须先裁定规范；不存在自动代码、P3/P4、TESTNET 或 LIVE 权限。

TASK_ID=`V06_G2_R3_P1_ALTERNATIVE_ENGINE_ARCHITECTURE_SELECTION_SOL_HIGH_R1`；Controller/start/direct parent=`b74b932da32e4b5bbe2477c2de014f94719d6a93`；Prompt=`770e910596bfbd82c28bd92705cf71ef981f0564`；execution branch=`feature/v06-bline-g2-r3-p1-alternative-engine-design-sol61-r1`。

[完整事件/资金/接口设计](../../../../docs/strategy_research/g2_r3/p1_alt_engine_sol_r1/ENGINE_OPTION_DECISION_AND_EVENT_LEDGER_DESIGN.md) 与 [机器 oracle/合同矩阵](../../../../evidence/v0.6/b_line/g2_r3_p1_alt_engine_sol_r1/ENGINE_OPTIONS_AND_INVARIANT_ORACLE_MATRIX.json) 包含三方案对比、B01–B07 可达性、12 类事件、8 个 record、7 个 owner phase、17 项不变量、34 个未运行用例和精确来源。

## 必须一次裁定的两个规范门

| 实施前门 | 待 Controller 冻结的明确决定 |
|---|---|
| AM01 / P3_METHOD_AMENDMENT_REQUIRED | 原 METHOD_DESIGN 未规定同一 bar 取消/确认/过期旧 Retest 后是否可注册新事件。建议该 bar 只终止旧状态，下一根不同小时才可注册；只是提案。首次确认应按小时顺序识别，即使策略 book WAIT 也不能事后挑下一次确认；各 horizon 独立消费。Controller 必须固定实际解释、version/root。 |
| AM02 / RISK_CONTRACT_ADOPTION_REQUIRED | 按来源合法可见性建立 E_c/E_r pending 风险投影、fee-cover 原子转换和 funding cover/payable 并集；明确模型 ACK 与证据 proof-floor。保持 100 USDT kill、5% buffer、1x、1.10 reserve 和原成本，不假装旧 acknowledged-only E_d 已包含该桥接。 |

原 Retest 没有规定同 bar cancel/rebreakout；旧 A 的测试不能代替冻结规范。AM02 则明确 user Prompt 要求的可见 pending loss/费用/资金费如何作用于风险与入场，保持原风险与成本数字。模型 +60s ACK 与源证明若有冲突，必须在同版本时钟合同中裁定，不能由实现暗自选择更早回执。

## 选择与风险减少

A 保留金融 owner 到实际义务结清，避免已退出亏损消失或资金费 Stage7 提前释放。C 的 reducer 技术纳入 A，但不省略 money journal。外部 B 的 NautilusTrader v1.231.0 commit `27a8e54e7ac3c57d6cbf8891f0283dfbaee97317`/许可/文档已核验；原生 OHLC 路径、next-open、funding/ACK 都需额外 R3 适配，因此不在此有限 build 采用。未安装、未原型、未交易所探测。

精确资金规则：逐 exit slice/fee item 排除未 ACK 正收益，不能 owner 净额抵消亏损；可见 fee 进入 E_c 时原子释放相应 fee cover，notional 留到 FillAck；funding cover 与 payable 取并集，短缺有 owner/S，不重复也不提前释放；free 使用 max0 的精确等式，仅对非负 A_raw 断言未截断上界。

标准化 loss169.336545 在 first legal proof cut 得风险830.663455、kill/free0；证明前不看未来。资金费例 cash1000/C_o7/ETH2/BTC cover.40/payable1/L.60 在 ACK 前 free940，ACK 后 cash999/ETH2/free940.05。T12 对 exit=S−10s 正确安排 ExitAck 首个合法分钟 S+60s，S 时仍 EXIT_PENDING，资金费 final 不早于 S+120s。B03 的 S−5000 API 输入不是 replay 可达证明；Stage8 报告本身不等于决策前视。B04 站立行为保留，但 forced/time 有利退出仍须按接受方法封顶。

## 下游 Gemini 合同与停止条件

建议新分支 `feature/v06-bline-g2-r3-p1-alt-engine-gemini-a-r1`、fresh worktree；代码 baseline `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`，实际 START 为新的 Controller implementation dispatch，绑定此设计 remote SHA 和已接受 AM01/AM02 root。9 功能模块+init、3 实现方测试、1 合成 runner；精确 allowed/forbidden paths、模块接口在完整设计和 JSON。禁止改 A/B、既有 src/tests、registry、P2、H40 golden/CI/状态，禁止市场数据正文、交易或 fetcher。

一次完整 build，聚焦合成验证；随后一次独立 B/Sol 固定 SHA 行为审计。新审计分支、git archive 隔离源、module path/hash 验证；执行 34/34 case，0FAIL/0SKIP/0XFAIL，逐 transition 17 项适用不变量，实际非空 4h 赢/亏、12h BASE run_simulation（>=240h warm-up），明确 12h stress ineligible，终端 pending 全 0、cash/net 精确对账，Python3.12/3.13/Decimal/permutation 确定性。完整 CI 真实报告；旧 H40 失败不得消音或标成 PASS。重大独立语义失败即停止替代引擎路线，不进入 R4/R5。

只有独立 Controller engine acceptance + P2 来源/许可/root/true Mark admission + 已有受限 science 合同后，才另发 NEW first-pushed prereg、核验远端 SHA，随后单独授权 P4 正文读取。现在 Controller action 是冻结 AM01/AM02并批准或拒绝 A 的有限合同，不是市场 replay。

## 本任务实际执行与发布

0 新引擎/业务测试，0 synthetic replay，0 market/protected/private/live/code writes。仅静态 JSON、34-case/12-event/8-ID、来源/hash/链接、算术、whitespace、三文件白名单和 ancestry 检查。自动非强制 commit/push 后外部完成回执给出 exact SHA、parent、remote equality、实际 CI；同 commit 无不可能自哈希。

A/B 及原科学评审不可变；P1 旧架构 NO_GO、仅替代设计；P2 LOCAL_ROOT_UNKNOWN；P3 prereg NONE；P4 market bodies NONE；TESTNET/LIVE NONE。
