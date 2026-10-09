# P1 替代引擎最终独立 B 审计

**终态：`ALT_ENGINE_B_TERMINAL_NO_GO__STOP_ENGINE_CAMPAIGN`。** 精确 A 对象 `164243b770f74f98876b55a7f070b1adf2f554d5` 未满足固定 Controller/方法契约。正常完整replay入口会静默覆盖同source/symbol/close冲突Mark；公共归约器接受超量退出；组合政策仅有一个cost-case资金book；终端boolean未覆盖未付fee。Controller应停止本替代引擎campaign，不自动发A修补或再次审计任务。

TASK_ID=`V06_G2_R3_P1_ALT_ENGINE_FINAL_INDEPENDENT_B_AUDIT_R1`；新Sol reassignment dispatch=`d2669953e896850b1bf749b5e5fdcf831ba26b88`；新Prompt=`d4f79c38f6f0dfc3431dcb597bd284b530804644`；原B dispatch/分支START=`ed9dc16f3dbeaada88806b69ad032526886a2ae4`；原详细Prompt=`18ad412969e224bb19e56d77444c23f766b367f6`。复用指定B分支 `feature/v06-bline-g2-r3-p1-alt-engine-final-independent-b-r1`，未reset至reassignment SHA。A directparent=`e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`；B起点parent=`470ef693c4313db4f16da3fe1fe27e1ba492e83d`。起点、远端、Prompt字节、Controller/AM01/AM02均核验。

执行器为当前Codex会话；系统描述GPT-6，但没有可切换/核验variant或effort的接口。请求的GPT-6 Sol High已记录，未伪称外部设置变化。不存在并行Gemini重复审计。

## G1–G5 实际执行与证据等级

| Gate / scope | 真实结果 | 限制 |
|---|---|---|
| G1 / FULL_REPLAY | BLOCKED_REQUIRED_NONEMPTY_REPLAY_EVIDENCE；A T28四条、T29 BASE和独立有效OHLC/240h fixture均0 trades；仅ObservedMark事件。未知小时12h STRESS另有明确ineligible。 | 并未证明每个fixture预先满足全部信号谓词，也不声称引擎在所有数据上永远零交易；原A fixture的后300根OHLC不一致。零结果是实际运行观察，不能认证非空交易/资金费/现金链。 |
| G2 / FULL_REPLAY_AND_PUBLIC_API | BLOCKED_REPRODUCED_MATERIAL_CONTRACT_VIOLATIONS；正常replay入口静默覆盖同close冲突Mark且顺序改变最后价格；归约器接受exit2/fill1；缺短缺和无journal现金通过assert_invariants；同ID仅改时钟被当成重复。 | 超量退出和损坏state为公共API/状态负控，未宣称普通策略会自然生成这些输入；实际source入口冲突属于FULL_REPLAY，无状态注入。 |
| G3 / FULL_REPLAY_AND_PUBLIC_API_NORMALIZED_LOSS | BLOCKED_PER_CANDIDATE_BOOK_COMPLETENESS；A solo、B solo、A+B及B+A都仅BASE一个1000-USDT余额；组合不提供各候选独立余额。公共API的共享BASE损失100令池kill/A0，而B solo是E1000/A950。 | 所有标准fixture成交0，因此真实非空交易、费用、cooldown的候选间干扰未证明；共享资金结构、结果schema与标准化loss/kill已观测，不能冒称独立政策book。 |
| G4 / PUBLIC_API_AND_DOCUMENT_ONLY | RUNTIME_NORMALIZED_SUBCASES_PASS_REPORT_INACCURATE_OTHER_CASES_NOT_RUN；标准资金费free940/ACK后999及940.05；亏损proof前1000、proof后830.663455/kill/A0；ACKed MTM盈利例E_d/E_c1003、E_r1002.9、A952.75均通过。报告E_d=C-Pf、缺.95及E_c<=100与实际source不符。 | 文档错误不是同一个运行公式bug。T34费用覆盖完整链、AM01/Retest复合状态、资金费窗口因果链未运行，保持未验证。 |
| G5 / INSTRUMENTED_FULL_REPLAY_INITIAL_STATE | BLOCKED_TERMINAL_CLEARANCE_PREDICATE；注入cash1000/fee_payable2的closed owner后执行完整run_simulation；终端cash1000/E_c998/A948.1，却terminal_all_zero=True。 | 这是明确的初始state注入，不是普通source naturally生成的未付费路径。正常replay均空，只做了平凡1000-1000=0对账，不能证明非空全部ACK守恒。 |

Source优先级为原八公式、接受R1.1、Controller R1.2、原Sol T01–T34/I01–I17，再是固定运行源和独立观察；A报告/自报PASS不得改写规范。G4的报告错误单独列为PROVENANCE_REPORT_INACCURATE，未冒称源代码也使用了错误算术。原科学评审保持不可变，此处没有新策略收益或Alpha结论。

## G1 非空链：直接运行，不推测

隔离archive只含允许的源/合成测试与报告；`ReplayEngine`、`reduce`、`project_as_of`、`assert_invariants`均以inspect.getfile和SHA256证明来自 `/tmp/p1-final-a-164243-le6kpcae/src`。实际Python3.12命令运行目标 `run_simulation`，observer只记录原函数输入/输出后的状态和event kinds，不改变其结果。

| 实际fixture | trade count | 真正reduce事件 | 现金/资金链 |
|---|---|---|---|
| A_T28_BASE_win | 0 | {'ObservedMark': 14700} | {'BASE': {'A': '950.000000000000', 'C_o': '0E-12', 'E_c': '1000.000000000000', 'E_r': '1000.000000000000', 'L_f': '0E-12', 'R_f': '0E-12', 'cash': '1000.000000000000', 'drawdown': '0E-12'}} |
| A_T28_BASE_loss | 0 | {'ObservedMark': 14700} | {'BASE': {'A': '950.000000000000', 'C_o': '0E-12', 'E_c': '1000.000000000000', 'E_r': '1000.000000000000', 'L_f': '0E-12', 'R_f': '0E-12', 'cash': '1000.000000000000', 'drawdown': '0E-12'}} |
| A_T28_STRESS_win | 0 | {'ObservedMark': 14700} | {'STRESS': {'A': '950.000000000000', 'C_o': '0E-12', 'E_c': '1000.000000000000', 'E_r': '1000.000000000000', 'L_f': '0E-12', 'R_f': '0E-12', 'cash': '1000.000000000000', 'drawdown': '0E-12'}} |
| A_T28_STRESS_loss | 0 | {'ObservedMark': 14700} | {'STRESS': {'A': '950.000000000000', 'C_o': '0E-12', 'E_c': '1000.000000000000', 'E_r': '1000.000000000000', 'L_f': '0E-12', 'R_f': '0E-12', 'cash': '1000.000000000000', 'drawdown': '0E-12'}} |
| A_T29_BASE | 0 | {'ObservedMark': 14700} | {'BASE': {'A': '950.000000000000', 'C_o': '0E-12', 'E_c': '1000.000000000000', 'E_r': '1000.000000000000', 'L_f': '0E-12', 'R_f': '0E-12', 'cash': '1000.000000000000', 'drawdown': '0E-12'}} |
| A_T29_STRESS | 0 | {'ObservedMark': 14700} | {'STRESS': {'A': '950.000000000000', 'C_o': '0E-12', 'E_c': '1000.000000000000', 'E_r': '1000.000000000000', 'L_f': '0E-12', 'R_f': '0E-12', 'cash': '1000.000000000000', 'drawdown': '0E-12'}} |
| INDEPENDENT_FIXED_VALID_OHLC_240H_V1 | 0 | {'ObservedMark': 15360} | {'BASE': {'A': '950.000000000000', 'C_o': '0E-12', 'E_c': '1000.000000000000', 'E_r': '1000.000000000000', 'L_f': '0E-12', 'R_f': '0E-12', 'cash': '1000.000000000000', 'drawdown': '0E-12'}} |

A原T28/T29各候选的completed_trades为空，无trade ID/qty/entry/exit/net可认证；所有G1 reduce事件只有ObservedMark，14700/15360个名字计数不代表17项独立property断言。独立fixture事前固定，OHLC合法，前240h是warm-up；同样零结果，未宣称已经证明其全部候选谓词必然触发。A原4h fixture最后300根bar的close越过其high/low，且12h BASE的known-config只给warm-up早期8h/16h。这些是fixture/证据限制，未事后修改求绿。

**零交易不证明策略无edge，也不证明引擎所有输入永远无法成交。** 它证明本次规定的非空全链没有被展示；idle cash1000−1000=0与net0仅平凡相等，不可代替signal→reserve→fill→ACK→funding→exit→ACK的资金守恒。终态NO_GO还由独立实际入口冲突/公共数量约束等材料支撑，不仅由某个无信号fixture或文档错误决定。

## 材料阻断的最小reproducer

1. **FULL_REPLAY来源冲突**：一根合法一分钟bar，两个相同source/symbol/close、available=open+120s且price100/101的合法Mark；正反顺序均未抛CONFLICT_FAIL_CLOSED，最终Mark分别101/100。`replay.py:104-115`先按symbol/timestamp建dict，只留下最后一条，绕过`journal.py:93-110`。journal的PUBLIC_API正负两个排列确实拒绝冲突；不能据此推断完整入口安全。Python3.12/3.13均复现。
2. **PUBLIC_API超量退出**：已有ACKED_OPEN quantity1，调用原reduce(EconomicExit quantity2)，pending slice记录2、亏损20、remaining quantity被max0裁为0；I16返回True。该负控为公共事件API，不宣称正常策略自然生成超量数量；原接口的fail-closed数量约束仍被实测违反。
3. **PUBLIC_API损坏owner状态**：payable1/cover.4/shortfall0通过assert_invariants，A949.6而正确union应949；cash1234/无journal或ACK分录也通过I07。可能存在正确的正常事件生成分支，不能补成该validator已独立检查损坏状态。结果与reachability如实限定。
4. **不可变envelope**：同ID/payload的RiskKill只改available_at，被当成完全重复并返回同状态；未验证全envelope digest。这不是已经测过的“changed ACK fee”用例，T07保持未运行。
5. **独立book**：solo A/solo B/组合正反顺序的正常完整report均仅BASE:cash1000，没有各candidate×case独立余额。normalized PUBLIC_API池中A亏损100会令共有BASE kill/A0，而B solo E1000/A950；真实非空成交干扰仍未验证，未借0-trade例声称测得每种fee/cooldown串扰。
6. **G5仪器化终端**：仅在审计运行内临时注入closed owner的fee_payable2，执行未改源的run_simulation；report cash1000/E_c998/A948.1但terminal_all_zero=True。该predicate仅查看C_o/R_f/L_f/P_f。状态注入、observer均标明并恢复；所有A源文件字节不变。

## 正确子项与未证明部分

normalized funding union前A940、ACK后cash999/A940.05/ETH reserve2不变；pending loss169.336545在proof前E_r1000、proof后830.663455/kill/A0；ACKed live盈利fixtureE_d/E_c1003、P_f.1、E_r1002.9、A952.75通过。它们验证了实际projector若干核心算术，不能推广为全source-proof/资金费窗口/ACK/latch/fee转换链PASS。G4完整T34/AM01尚未执行。

Source`assert_invariants`的I07、I09–I17十项直接返回True；I01为相同posting.amount两边求和的格式检查；I02–I06/I08存在部分真实检查，不能说17项全无作用。部分规则可能在别的函数中真实执行：如Mark冲突journal guard、cooldown max。下表明确独立mutation是否完成；未完成不借自报counter补PASS。

| 原始I编号 | 状态 / enforcing source | 独立mutation与观察 |
|---|---|---|
| I01 | UNVERIFIED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:200 | unbalanced owner/chart-of-accounts versus postings → not independently tested as I01; posting-format sum alone is tautological |
| I02 | UNVERIFIED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:209 | projection R_f inconsistent with owner covers → not run after terminal blocker |
| I03 | UNVERIFIED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:215 | projection P_f inconsistent with final owner payable → not run after terminal blocker |
| I04 | UNVERIFIED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:221 | projection C_o inconsistent with owner memo sum → not run after terminal blocker |
| I05 | BLOCKED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:227 | FINAL payable1/cover.4/shortfall0 → accepted; I05 True, A949.6 instead of normative949 |
| I06 | UNVERIFIED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:237 | corrupt A versus required max0 equality → not run after terminal blocker; normalized G4 formulas correct |
| I07 | BLOCKED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:240 | owner cash1234 with zero journal/ACK postings → accepted; I07 True |
| I08 | BLOCKED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:249; src/btc_quant_agent/strategy_research/r3_alt_engine/replay.py:79-96,594-602 | two policies share BASE; normalized A loss100 and B cash0 in pooled1000 → FULL_REPLAY one-book report and PUBLIC_API pooled loss-kill; not nonempty trade interference |
| I09 | UNVERIFIED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:252; src/btc_quant_agent/strategy_research/r3_alt_engine/reducer.py:328-333 | late old ACK lowers newer cooldown → not run; reducer source max at333 may enforce it |
| I10 | BLOCKED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:255; src/btc_quant_agent/strategy_research/r3_alt_engine/journal.py:93-110; src/btc_quant_agent/strategy_research/r3_alt_engine/replay.py:104-115 | same source/symbol/close conflicting Mark, both source orderings → PUBLIC_API guard raises; FULL_REPLAY bypass silently picks last row100/101 |
| I11 | BLOCKED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:258; src/btc_quant_agent/strategy_research/r3_alt_engine/journal.py:83-91 | same immutable event ID changes available_at only → accepted as idempotent; no CONFLICT_FAIL_CLOSED |
| I12 | UNVERIFIED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:261 | future source proof admitted before decision cut → not run as an independent clock mutation |
| I13 | UNVERIFIED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:264 | invalid tick/lot or external Decimal context mutation → not run; cross-Python normalized witnesses only |
| I14 | UNVERIFIED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:267 | late ACK resets previously latched kill/highwater → not run as a complete lifecycle |
| I15 | UNVERIFIED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:270 | missing intermediate Retest cancellation hour → not run; first-wave policies structural only |
| I16 | BLOCKED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:273; src/btc_quant_agent/strategy_research/r3_alt_engine/reducer.py:255-293 | exit quantity2 after owned/fill quantity1 → PUBLIC_API accepted; loss20 and pending slice2; I16 True |
| I17 | UNVERIFIED / src/btc_quant_agent/strategy_research/r3_alt_engine/money.py:276 | positive pending slice offsets different negative slice → not run; one negative slice does not prove non-netting |

## 完整T01–T34状态，停止穷举

| 原始ID | 状态 / scope | 执行node或停止原因 |
|---|---|---|
| T01 | BLOCKED / FULL_REPLAY + PUBLIC_API | tests/test_v06_r3_alt_independent_semantics.py::test_capture_full_replay_duplicate_mark_ingestion |
| T02 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T03 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T04 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T05 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T06 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T07 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T08 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T09 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T10 | PASS / PUBLIC_API_NORMALIZED_LEDGER | tests/test_v06_r3_alt_independent_semantics.py::test_normalized_funding_projection |
| T11 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T12 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T13 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T14 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T15 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T16 | UNVERIFIED / PUBLIC_API_NORMALIZED_LEDGER_PARTIAL | tests/test_v06_r3_alt_independent_semantics.py::test_normalized_pending_loss_proof_floor |
| T17 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T18 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T19 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T20 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T21 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T22 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T23 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T24 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T25 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T26 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T27 | BLOCKED / FULL_REPLAY + PUBLIC_API | tests/test_v06_r3_alt_independent_semantics.py::test_capture_shared_book_loss_kills_unrelated_candidate |
| T28 | BLOCKED / FULL_REPLAY | scripts/strategy_research/r3_alt_verification/final_audit.py::g1 |
| T29 | BLOCKED / FULL_REPLAY | scripts/strategy_research/r3_alt_verification/final_audit.py::g1 |
| T30 | BLOCKED / PUBLIC_API_EXTRA_PARTIAL_QUANTITY_COUNTEREXAMPLE | tests/test_v06_r3_alt_independent_semantics.py::test_capture_over_exit_public_reducer |
| T31 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T32 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T33 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |
| T34 | NOT_RUN_DUE_TO_TERMINAL_BLOCKER / NOT_RUN | NOT_RUN_DUE_TO_TERMINAL_BLOCKER |

计数：`{'BLOCKED': 5, 'NOT_RUN_DUE_TO_TERMINAL_BLOCKER': 27, 'PASS': 1, 'UNVERIFIED': 1}`。T16 proof子项通过但ACK后永久latch完整序列未证，所以是UNVERIFIED；T27成本ineligible子项正确但独立book阻断；T30以公共超量退出负控违反数量安全，其普通减仓/Decimal/permutation组合未穷举。其余明确NOT_RUN，不是skip后补PASS。G1/G2阻断后只做了有限根因确认，没有全H40 pytest或新参数/市场搜索。

## 可重复执行与实际测试

在独立B路径的脚本和测试均不改实现。首次standalone命令及原始观察完整收录于receipt。final reproducer固化13个A Python文件SHA256；实际所有archive源也与Gitblob比较。复现需从目标Git对象提取允许路径并设置P1_FINAL_TARGET_ROOT；无env时测试明确skip且不认证，绝不fallback本地/installed实现或暗中联网。

```bash
P1_FINAL_TARGET_ROOT=<exact-A-archive> PYTHONDONTWRITEBYTECODE=1 python3.12 -m pytest -q -p no:cacheprovider tests/test_v06_r3_alt_independent_semantics.py
P1_FINAL_TARGET_ROOT=<exact-A-archive> PYTHONDONTWRITEBYTECODE=1 python3.13 -m pytest -q -p no:cacheprovider tests/test_v06_r3_alt_independent_semantics.py
```

两环境各12passed/0failed/0skipped。**它们是验证器测试，其中capture明确是在复现BLOCKED，而非引擎PASS。** 全策略replay在独立standalone中实际运行；pytest不是只断言A保存的matrix。新增两个Python文件focused Ruff PASS，JSON/来源/allowlist/whitespace另核验。A exact CI37949429222实际FAILURE，Controller已记录2819pass/1 inheritedH40fail/2skip；没有重跑全局，也没修改golden。B发布CI状态在最终外部receipt中真实报告。

## 权限与发布

市场/Mark/funding/OI真实正文、保护结果、exchange/private调用、TESTNET/LIVE、A源修改为0。读取的是固定源、纯合成数据和公共Git/CI元数据；不宣称全环境网络0。B只写scripts/r3_alt_verification、指定新test、final B docs/evidence四个允许范围。P1仍NOT_ACCEPTED，P2LOCAL_ROOT_UNKNOWN，P3/P4/TESTNET/REAL_FUNDS NONE。

一次证据提交，directparent `ed9dc16f3dbeaada88806b69ad032526886a2ae4`，非强制push指定已有B分支；exact final remote SHA在提交后外部核验，避免同commit自哈希。Controller下一步是终止本替代引擎campaign并独立审阅已推送证据，不自动发下一轮补丁、重审或市场授权。

## 固定来源和字节身份

| 固定ref/path | SHA256/Git blob |
|---|---|
| [prompts/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_SOL_HIGH_FINAL_INDEPENDENT_AUDIT_R1.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/d4f79c38f6f0dfc3431dcb597bd284b530804644/prompts/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_SOL_HIGH_FINAL_INDEPENDENT_AUDIT_R1.md) @ `d4f79c38f6f0dfc3431dcb597bd284b530804644` | `a94f31de60d7b3e5c73b599d26e2f761ae08cbfa9a8f3dc17068315247090839` / `f4d71d1d08d38ab5efab6683840907c57fbabe80` |
| [reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_FINAL_AUDIT_SOL_HIGH_EXECUTOR_REASSIGNMENT_R1.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/d2669953e896850b1bf749b5e5fdcf831ba26b88/reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_FINAL_AUDIT_SOL_HIGH_EXECUTOR_REASSIGNMENT_R1.md) @ `d2669953e896850b1bf749b5e5fdcf831ba26b88` | `8d7a68b9d6a1e5578b0d51a7ee9134ce78e4ffdae3ac3effd10f1eb5a0f44c57` / `9ca1acbedeef77f45872fd8e27200613370405dd` |
| [prompts/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_FINAL_INDEPENDENT_B_SOURCE_AND_RUNTIME_AUDIT_R1.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/18ad412969e224bb19e56d77444c23f766b367f6/prompts/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_FINAL_INDEPENDENT_B_SOURCE_AND_RUNTIME_AUDIT_R1.md) @ `18ad412969e224bb19e56d77444c23f766b367f6` | `f19ca8cf86868a5ced5964a475592d934c92dcc83befde6637cd3eb671c9aeb5` / `f84a234fe4f9059c9cacd977708a20288cc7e0cf` |
| [reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_A_DELIVERY_CONTROLLER_EVIDENCE_GATE_AND_FINAL_B_DISPATCH_R1.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/ed9dc16f3dbeaada88806b69ad032526886a2ae4/reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_A_DELIVERY_CONTROLLER_EVIDENCE_GATE_AND_FINAL_B_DISPATCH_R1.md) @ `ed9dc16f3dbeaada88806b69ad032526886a2ae4` | `86769d15e821865fcf79265132ffc4324b8830dde70d3313d9538841b4bde4a2` / `478fe18aa905a99fbcf85a880b7c3a4b11540273` |
| [reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_AM01_AM02_CONTROLLER_SPEC_FREEZE_R1.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/821d23427a5f6d0b4635f32f226ddc779358ab72/reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_AM01_AM02_CONTROLLER_SPEC_FREEZE_R1.md) @ `821d23427a5f6d0b4635f32f226ddc779358ab72` | `cea538034ea7695a326a2f2c91dcf4d246f2fafaa456f5935f4f375ce1d6e16f` / `ecafeec0100f8881a700f9e3372a717aeab93b2b` |
| [evidence/v0.6/b_line/g2_r3_p1_alt_engine_sol_r1/ENGINE_OPTIONS_AND_INVARIANT_ORACLE_MATRIX.json](https://github.com/EXASHXE/btc-quant-agent-public/blob/c0b41d1ce62e0fe852edfc6e162f1bc3dc6dcc01/evidence/v0.6/b_line/g2_r3_p1_alt_engine_sol_r1/ENGINE_OPTIONS_AND_INVARIANT_ORACLE_MATRIX.json) @ `c0b41d1ce62e0fe852edfc6e162f1bc3dc6dcc01` | `88b9660726cdecbf1effa50bcc73a1beb849df2478ef05f2a8d66022c0633a5c` / `998d9df0b3453988b5638a6dce37725ab4388df7` |
| [evidence/v0.6/b_line/g2_r3_design/CANDIDATE_REGISTER_PROPOSAL.json](https://github.com/EXASHXE/btc-quant-agent-public/blob/e5b2006a89441f7eb2ec900e508aff451106b87a/evidence/v0.6/b_line/g2_r3_design/CANDIDATE_REGISTER_PROPOSAL.json) @ `e5b2006a89441f7eb2ec900e508aff451106b87a` | `d0f89bddfaec0e57c959cec043969059da10fec8aa45f81669dde8b80ea35a9b` / `d337542f6482938c37eb6b4e43255cdf4d09751a` |
| [docs/strategy_research/g2_r3/method_repair/METHOD_R1_1_PIT_COST_ACCOUNTING.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/cf2d5cc33774cdcff7d709636305bba830e977ef/docs/strategy_research/g2_r3/method_repair/METHOD_R1_1_PIT_COST_ACCOUNTING.md) @ `cf2d5cc33774cdcff7d709636305bba830e977ef` | `a2943c9a541d93eaceb62a664edf0d03f0c9bbab6f4c4f73752831bcf14eb026` / `7def37d7c8aad02dd0c2769882fad61622e262db` |
| [tests/test_r3_alt_events_money.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/tests/test_r3_alt_events_money.py) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `d25538d756dc41d625128ec01abb54c341f01e276c1d1958eee48dc7f287fe06` / `15996ed3896479f6ac2e66a04f73f9ba48e2f978` |
| [tests/test_r3_alt_retest_replay.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/tests/test_r3_alt_retest_replay.py) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `717bbaca8a03b7854c0deeda8815486a1bcea60fee0bbf337771bf2eaff5ada7` / `b4b01c18b5bc8391e92ab0a3f5836099baacafc5` |
| [tests/test_r3_alt_clock_execution.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/tests/test_r3_alt_clock_execution.py) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `25cc4e97190af3ea6f30aeced0a9a57a110a51d0b2dc98925d66d117d030a8ea` / `49d372e400ae6565101a4b7eafe8d74ea2b93627` |
| [src/btc_quant_agent/strategy_research/r3_alt_engine/clock.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/src/btc_quant_agent/strategy_research/r3_alt_engine/clock.py) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `50f2fa2c66f2952c0729bd8637dd5e8e9f23230c1737e12d466fbca80116cb55` / `d9531b888aa7c55ec8b784cd8b29ffb22be105c5` |
| [src/btc_quant_agent/strategy_research/r3_alt_engine/replay.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/src/btc_quant_agent/strategy_research/r3_alt_engine/replay.py) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `50a80b9242d757e8f69d5ac9f4ad15e3fb348a5ee0c52a8474eec4666147ffdd` / `8956199be3a2c738e6b47c9dbfc655fb17100d4c` |
| [src/btc_quant_agent/strategy_research/r3_alt_engine/reducer.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/src/btc_quant_agent/strategy_research/r3_alt_engine/reducer.py) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `cf3425c9c1b3bf45841945ad473639f42731964432f75208ebb8ae4b005aac9c` / `f53c1df77faf1109b47981e921eed02470ebe94a` |
| [src/btc_quant_agent/strategy_research/r3_alt_engine/execution.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/src/btc_quant_agent/strategy_research/r3_alt_engine/execution.py) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `5a9157e4ae0fe2dba99d4ad4383f600ff1e0efb6db07548b4746841e0dbedad6` / `2bbd0f28d1857c3b333f2dc01d9e6f73688abd12` |
| [src/btc_quant_agent/strategy_research/r3_alt_engine/__init__.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/src/btc_quant_agent/strategy_research/r3_alt_engine/__init__.py) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `b5f8a24f1b141a9c9df8a7e961f18c2b5e7718699e55ff00dfc250385ce35b78` / `cbb48f48a8428c3d137f512277c9c6d454993cab` |
| [src/btc_quant_agent/strategy_research/r3_alt_engine/signals.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/src/btc_quant_agent/strategy_research/r3_alt_engine/signals.py) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `b4ca80132f851842a048e3197f3b4b90a6c8495d0360ee6f4d56045a371b990d` / `6a2fbc6ca9647b854efad60de2d1f2f7fa44f886` |
| [src/btc_quant_agent/strategy_research/r3_alt_engine/journal.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/src/btc_quant_agent/strategy_research/r3_alt_engine/journal.py) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `896986ef11de8d752f6623f2f9d5221288f9b115ed1b9dbb16e7d4e756ba30ee` / `be065551e5762e241b7b30eb9adc60a4dc1c4f28` |
| [src/btc_quant_agent/strategy_research/r3_alt_engine/frozen_primitives.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/src/btc_quant_agent/strategy_research/r3_alt_engine/frozen_primitives.py) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `5d06f3f77993ae9eb1e76e29042d3375250477e5c7efdc67788d7a696ffa054f` / `35ada0b34a2a86ae17ca440d8553e614db2860ca` |
| [src/btc_quant_agent/strategy_research/r3_alt_engine/money.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/src/btc_quant_agent/strategy_research/r3_alt_engine/money.py) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `649d07456d9d567468f584406f471ca7dd34b51c6e693c1cbe9acc3c8a2bd0e7` / `483276a32186a069ca062918c9bb6c7067ad0889` |
| [src/btc_quant_agent/strategy_research/r3_alt_engine/model.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `cb31085e8a389bbb4f58d6472e8890ea29f1606b43c5605e10e46c1ce228b23a` / `45e5c268726da04a32a10b54cb4384c20a8e4180` |
| [docs/strategy_research/g2_r3/p1_alt_engine_impl_r1/ALT_ENGINE_IMPLEMENTATION_AND_HANDOFF.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/docs/strategy_research/g2_r3/p1_alt_engine_impl_r1/ALT_ENGINE_IMPLEMENTATION_AND_HANDOFF.md) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `cb706708ec2912da4e34acecb32ee0d4f6c0386eef3f87f6fe3930f14f91b318` / `84bad6e24f8925ab656ef1bc8f8d7398c2c6c520` |
| [evidence/v0.6/b_line/g2_r3_p1_alt_engine_impl_r1/ALT_ENGINE_IMPLEMENTATION_SYNTHETIC_RECEIPT.json](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/evidence/v0.6/b_line/g2_r3_p1_alt_engine_impl_r1/ALT_ENGINE_IMPLEMENTATION_SYNTHETIC_RECEIPT.json) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `529612a1a5f7e4c7b91839677b2b7b101ba5a2e9a1f1ddca1dcce5addba606e5` / `60557c5d982d5c777ea446c072094e6fdec981f4` |
| [evidence/v0.6/b_line/g2_r3_p1_alt_engine_impl_r1/T01_T34_EXECUTED_TEST_MATRIX.json](https://github.com/EXASHXE/btc-quant-agent-public/blob/164243b770f74f98876b55a7f070b1adf2f554d5/evidence/v0.6/b_line/g2_r3_p1_alt_engine_impl_r1/T01_T34_EXECUTED_TEST_MATRIX.json) @ `164243b770f74f98876b55a7f070b1adf2f554d5` | `9d19ffc0106e1b2a50c3c9a09bbd7a4395d8388df082d80b01ff7348b4774d21` / `48796e50c992c3ef9942baaca33bd15b2567bdf3` |
