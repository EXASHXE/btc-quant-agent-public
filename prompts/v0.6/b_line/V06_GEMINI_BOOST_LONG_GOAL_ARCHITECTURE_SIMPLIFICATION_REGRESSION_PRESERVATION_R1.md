# quant-agent v0.6 — GEMINI BOOST LONG GOAL R1
## End-to-end architecture lean-down, duplicate removal and test-runtime optimization under research validity / PIT / financial invariants

**指定执行模式：Gemini BOOST。** 这是跨模块的高复杂度设计 + 实现任务，而不是简单代码整理。用户明确关心 Boost 因冗长 Worker 迭代产生 1,117 次交互和 55 分钟中间耗时；因此此 Goal 必须使用**收敛式执行策略**，避免无效自我循环与重复 CI。正常模式的轻量 CI 风险映射已单独安排，不要重复其工作。

任务不能只交报告。必须完成一次覆盖全仓的**静态架构/测试负担清查**，然后在安全授权的 A/R2/R3 命名空间实施具有实证价值的有限精简，并提交源码、测试、性能对比、严格来源证据。对于保护范围内的 H40/H41/2024–26 Holdout，只能从公开测试源码/元数据计算耗时与依赖关系；**不得打开、重跑、复制或推断任何历史保护数据及科学结果，也不得删除其测试**。

## 一、固定身份与隔离权限

TASK_ID: V06_GEMINI_BOOST_ARCHITECTURE_LEAN_TEST_RUNTIME_R1
ROLE: Senior Systems Architect / Quant Research Infrastructure Engineer / Scientific Test Preservation Reviewer
REPO: EXASHXE/btc-quant-agent-public
BRANCH: feature/v06-bline-gemini-boost-architecture-lean-test-r1
EXACT_START_SHA: 97f4040b9380f2069575a989c066d1daeef15194
AUTHORITY_L2_SHA: 23a5e3ca99e4224550dfd04d44c908e4e38adaf1
AUTHORITY_URL: https://github.com/EXASHXE/btc-quant-agent-public/blob/23a5e3ca99e4224550dfd04d44c908e4e38adaf1/reviews/v0.6/b_line/V06_GEMINI_R3_CODEX_AUDIT_AND_CI_ARCHITECTURE_OPTIMIZATION_CONTROLLER_L2_R1.md
WORKTREE: /root/workspace/project/quant-v0.6/gemini-boost-architecture-lean-r1
SCRATCH: /tmp/btc-boost-architecture-lean-r1
UPSTREAM_B_READ_ONLY_SHA: 51cdd4e17503fbd18ad22aaeeaba3580f5efacf8
UPSTREAM_C_READ_ONLY_SHA: 91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b
ORIGINAL_G1_READ_ONLY_SHA: 861a9d148f72db00e6079e53af78220bdd7e84ce

可写路径（仅这些）：
- scripts/market_data/forward_public_feed_r1/**
- scripts/integration/market_event_bridge_r2/**
- tests/test_v06_forward_public_feed_r1_*.py
- tests/test_v06_market_event_bridge_r2_*.py
- docs/engineering/architecture_lean_r1/**
- evidence/v0.6/b_line/architecture_lean_r1/**
- scripts/engineering/architecture_lean_r1/**（分析/benchmark 工具，必须只读项目源码与单元测试；禁止读取存储的市场数据）
- tests/test_v06_architecture_lean_r1_*.py

禁止改动：
- scripts/ci/test_plan.py、tests/test_ci_test_plan.py 和 .github/workflows（交给并行 Gemini NORMAL 执行）
- 任意 src/btc_quant_agent/** 生产主线、B 原冻结分支、C G1/G3、original G1、A-line、旧 archive/holdout、策略参数/权益/真钱状态；
- H39/H40/H41、任何旧 2024–25 历史科学方法、受保护的 2026 真实交易/forward、用户 Quant-agent/data 与 Quant-agent-sanitized（禁止包括 stat/list/open）、git 中的私密配置、GitHub 之外的私人账户；
- 真实交易、订单、API key、真实飞书/LLM、TESTNET/LIVE、资金写入、网络节点切换/修改 Clash、TLS 校验削弱。所有数据测试为 synthetic-only；不得使用真正网络行情测试作为本任务的回归输入。

并行协作边界：
- NORMAL 正在 feature/v06-bline-gemini-normal-ci-riskmap-fastpath-r1 只改 CI planner 与其自测；
- BOOST 完全不接触该分支、CI 文件和其 worktree；不可 merge/rebase/cherry-pick 对方结果；
- Controller 在两项任务结束后按 exact SHA 独立验收并协调合并，禁止 Agent 自行融合；
- 如果已有其他执行者/工作树，保持独立，不覆盖、清理或 reset 他人工作。

## 二、工程现实和底线

最新 Gemini R3 at EXACT_START_SHA 已经 [Actions 38270967488](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38270967488) 完成 Python3.12 FULL 回归 **3454 passed, 2 skipped in 904.17s**，并有 394 项 feed+bridge scoped 测试（本地报告约 15.28s）。旧 B scientific prereg 因第三提交修改算法且清单 SHA 不存在，仍无 VALID ALPHA。R3 已通过公开 Clash 短时数据抓取 180 秒、4,730 events、3 closed Last bars、178 Mark ticks，但其 **book_continuous=false、rebootstrap_count=1**，L2 持续性尚未通过，不许把它升级为可交易价差证据。

当前 test planner 因 feed/bridge 路径未映射无条件 full，已经有专门 NORMAL 修复，不是本 Goal 的责任。H40/H41 的大型科学测试占时很高，不是“冗余证明”，**不得用跳过/删除/重命名/xfail/参数削减、减少随机种子、共享跨隔离科学状态等形式虚构加速**。

Codex 在 frozen R2 独立复现 13 项缺陷，新版 R3 改善了 Funding receiver time、Mark witness 和 CI，但至少以下 **R3 源码静态残余风险** 必须优先记录/给出有效反例：
1. funding_adapter.py 当前使用 observed_wall_utc_ms（历史 Funding REST 被收到的时刻）来验证 Mark witness 的 freshness，这不等于官方 settlement at funding_time_ms 的 Mark price。晚到 3 小时 funding 时，收到时的价格不应被宣称为结算计价基准。
2. settlement_id 包含原始 rate_str，等价格式 0.0001 与 0.00010000 可能重复计入；
3. funding_adapter.py 仍允许把直接传入的 bare scalar 转为 VERIFIED 的手工 witness；严格科学边界需要 source SHA/clock/timestamp provenance；
4. NaN/Inf 或负数资金费率和 Mark，应在状态写入前验证有限性与明确定义合法边界；
5. Mark-derived 1m proxy 必须持续标注 DERIVED，不等价 Binance 官方 mark kline；
6. 公开源 Book L2 初始重建间断不能声称连续盘口或者可真实成交。
**这些属于先验财务/因果正确性审查问题**。不能在架构优化中静默改变策略经济定义。先有失败复现，再明确独立修复小提交；若必须改 original C 接口才能完整通过，停止该路径并记录 EXTERNAL_C_CONTRACT_CHANGE_REQUIRES_CONTROLLER，不得修改 C。

## 三、Boost 收敛式执行纪律（重点避免重复耗时）

这次明确不要复制此前“55min Worker + 1117 steps + 35min remote CI”的工作方式：
- 一个主 Agent 即可；子 Agent 仅在真正独立的静态目录梳理有增益时使用，最多两个短时只读 helper，**禁止递归启动无限 Goal/Worker**、重复分配同一模块到多人。
- 进入执行前只做 **一次架构/测试依赖规划**；冻结本轮可修改的**最多 3 个局部重构 wave**。同一 wave 不得在没有新失败证据时反复重写。每 wave 的目标必须是“删除一个真正重复的事实源/编码重复”，不是改行数。
- 源码修复和架构重构每 wave 后只运行相应 focused pytest + Ruff/compile；不在每个 commit/Worker 完成后跑全仓 3454 项；**最多一次本地全仓最终验证**（只有资源充裕、必要时）和**一次最终远端 full CI**。因为旧 planner 尚未合并，Boost 最终源码变更预计触发一次全仓 GitHub full；尽量在本地完成并固定源码后**一次 push**，不要中途多次 push 造成 repeated 15min GH Actions。
- 最多 **4 个非强推、线性 git commits**，至多 1 个主要 push（仅终态）；错误修复可再一次 push，但记录为何需重试。不要以外部 CI 等待为理由频繁轮询，在后台断开进程不能声称自动完成。
- 若内部测试出现新增 FAIL：先生成最小可复现差异，不超过两轮逻辑修复；仍失败则保留原行为/回退该 wave（只限自己的 worktree），以真实 BLOCKED 签收，不要无限修改策略阈值来求全绿。
- 不要运行/等待远端 Full 和本地 Full 多次：目前可信的 904.17s 基准已经存在；performance before/after 对比的 focused 测试应在同类 Python3.12 环境复测且明确噪声、CPU/IO。
- 不要在任务末尾批量生成几十份冗长重复文档；只需指定 4 个精炼工程文档和对应机器 JSON，内容必须源于代码与可重复命令。

## 四、Stage 0：全仓代码/测试负担静态盘点（只读，跨仓但不碰受保护数据）

从固定 git tree、公开 Python 源码 AST、pytest --collect-only（若需科学测试 collection，禁止读取外部数据并证明 collect-only 无副作用；否则退化为静态测试文件扫描）构建机器化架构 inventory：
- tracked Python modules 和每个公开 package 的源码 LOC、循环 import、最大模块、公共语义重复的 AST family（区分名字相同但合同不同）、无引用/legacy 的候选（不能依据 grep 0 即删除）、runner/CLI/fixtures 层次、行为合同所在位置。
- Test inventory: 每个测试文件测试方法数、参数化数、fixture 文件依赖、重复生成 fixture、启动 interpreter/subprocess/cold authority 有无可测重用、与 source 引用反向图、changed-path planner 覆盖率；
- 从 CI 38270967488 现有日志提取 Top slow tests 和现有语义作用（例如 H40 runtime scaling ~59.62s; H40 producer/verifier roundtrip ~50.61s; 其他 20–40s），但**不运行不编辑**这些旧保护科学测试。将测试分为 ACTUALLY_REDUNDANT_CANDIDATE / SAME_METHOD_DIFFERENT_INVARIANT / SCIENCE_AUTHORITY_IMMUTABLE / UNKNOWN_NEEDS_REVIEW。没有独立证据不得判定冗余。
- 区分编译、依赖安装、本地 focused、远端 full、Agent Worker 迭代实际时间；估计收益时只用测量，不基于行数猜性能。
- 输出 BASELINE_ARCHITECTURE_INVENTORY.json 和 TEST_COVERAGE_OWNERSHIP_MATRIX.json。写出至少 5 个**有证据**的简化机会，按效益、语义风险、实现工作量排序；若受保护目录只报告结构/文件名，不输出科学内容。

**只选 2–3 个低风险实际重构 wave，不许一口气改整仓 800+ 文件。** 其他发现纳入未来建议。

## 五、Stage 1：先验财务与因果不变量防回归（独立证据）

加入不依赖 GitHub 网络与旧数据的 targeted synthetic-negative tests（>=20 meaningful cases），覆盖：
- settled Funding (funding_time T) 与 REST receipt (T+0.2s、T+30s、T+3h) 的已知性；
- Mark observed at receipt does NOT prove Mark at settlement; official settlement-price evidence missing => unknown cash basis, not COST_COMPLETE;
- rates 0.0001/0.00010000 duplicate settlement => exactly once; same symbol+settlement with conflicting revised rate => detectable conflict, cannot double journal;
- nonfinite Decimal rate/price, negative qty, no source SHA, route switch, provider epoch difference, stale Mark vs verified at settlement, repeated side effects before/after C adapter rejection;
- C late-funding contract rejects legitimate later receiver time? If so stop C integration and mark blocked, do not rewrite C;
- book continuous with U/u/pu gap/stale => no P2 fill eligibility, source reconnect resets book and Mark lineage.

Repair permission: you may make **minimal fail-closed corrections** in your authorized local R2/R3 modules only, in a dedicated safety-fix commit distinguished from purely equivalent refactors. Default to evidence of INCOMPLETE rather than invent a trustworthy historical funding cash price. For official cash price not present, preserve verified funding rate as source data but classify economic cash basis INCOMPLETE and do not dispatch claimed precise realized PnL; never allow price-at-receipt to masquerade as price-at-settlement. If consumer C needs core contract modifications to accept late events correctly, do NOT edit it; isolate and report C_CONSUMER_REQUIRES_NEW_AUTHORITY. Measure impact of any changed finance semantics and do not assert historical Alpha improvement.

Stage 1 guard: if safety tests fail and safe local repair impossible, **do not continue sensitive ledger restructuring**. You may still simplify unrelated network diagnostics/fixtures with frozen behavior and deliver blocking report.

## 六、Stage 2：按证据执行有限源码去重/架构收敛

For each of at most 3 declared refactor waves, do:
1. Before: explicit SOURCE_SHA+contract before fixtures; behavior spec; shortest API surface and known consumers; independent 10–20 cases for observed behavior not already covered; test count/LOC/AST function overlaps.
2. Implementation: unify a REAL duplicate owner rather than simply make helpers call each other; typical candidates:
   - A connector + integration bridge duplicate MarketEvent canonical serialization, source manifest hashing, quality/clock/known-at validation;
   - A/B consumer boundary and Mark Price observation normalization; never change B original source, only adapt known versioned schema in permitted namespace;
   - funding/Mark/Top10 parent SHA and source metadata duplicated in many dataclasses, with immutable typed source envelope;
   - Python runner CLI/network route setup and redacted diagnostic output repeated in A vs R2, with single consistently tested route configuration;
   - test fixture generators and clock helpers duplicated across 12+ bridge/source suites; centralize deterministic fixtures in NEW versioned helper, never share mutable state across independent tests or combine different PIT/provenance cases;
   - expensive double initialization in current own 394 focused tests; per-test fixture caching only for immutable canonical inputs with verified input SHA and process isolation, no mutable book/ledger/strategy state.
3. After: prove exact source->derived mapping, replay digest equivalence for **intended unchanged behavior** (except safety fixes explicitly recorded), no events lost/duplicated, no rollback in PIT clock, settled funding Decimal and source-quality gate; no runtime network; same suite IDs / explicit migrated parametrized case mapping; no silent case drop.
4. Define measurable benefits: eliminated duplicate implementation (LOC/AST semantic owner), reduced independent imports/decision points, focused pytest wall duration before/after and I/O/memory, reduced maintenance dependencies. A more complex abstraction with fewer lines but more dynamic ambiguity is NOT an improvement: reject it.
5. Mutation-sensitivity: add at least 10 deliberately mutated synthetic inputs (time shift, wrong funding, wrong route, hash mismatch, order-book gap) and prove at least one independently owned test rejects each; if a merged parametrized test replaces N test IDs, publish old→new invariant case map and explain why equal scientific assurance is preserved.
6. Keep original A/B/C branches immutable, no runtime or science compatibility loss. All changes are in authorized A feed/R2 bridge/new helpers/tests namespace; do not import private user data, B/C source as file fixture unless exact public code SHA and solely read-only.
7. Any candidate removing historical H40/H41 tests, altering 2024–25/2026 scientific graph hashes, test selection semantics, method prereg/holdout, A-line policy or financial release gates must be recorded as PROHIBITED_WITHOUT_CONTROLLER_AUTHORITY, NOT executed.

Mandatory explicit NON-goals:
- Do not attempt blanket delete tests/test_v051_h40_*.py or tests/h41.
- Do not disable tests globally, mark xfail, tune timeout to conceal failure, lower coverage/closed-bar sample count, change scientific threshold.
- Do not repurpose a synthetic derived Mark 1m as official historical Kline.
- Do not connect to private user wallet or allow real funds.
- Do not merge NORMAL's CI mapping work or change scripts/ci.

## 七、Stage 3：稳定性/CI 和成本证明

Local:
- Static and clean import/compile check on modified source.
- Ruff check modified source + affected tests, bounded old EXE001 policy intact.
- Run targeted R3/R2 feed+bridge suite (~394 baseline) and new architecture tests; record actual passed/failed/skipped, elapsed wall and py version.
- For explicitly changed financial behavior, run 20+ independent PIT/Decimal/quantity/settlement chronology negative tests with source+hash receipts; do not call it observational 2026 Alpha.
- Check no changed file outside allowlist; changed consumer provenance must be exact.
- Execute final whole repository pytest only if local resources permit once; otherwise rely on **actual final remote full CI** as independent exhaustive regression gate. On branch without NORMAL mapper, expect full CI for touched A/R2 modules; allow sufficient time for a single run, do not spam new pushes.
- Run memory/cpu benchmark only on bounded local synthetic traces, no 24h daemon.
- For failure on an unrelated inherited H40 test, provide exact failing ID and compare to baseline; NEVER delete or weaken that legacy test.
- Evidence: Before/after SHA-locked input/output digests, test identity retention, wall time, LOC, import edges, duplicated canonical fact owners, regression story and non-goals. Avoid claims of across-the-board 5x boost inference speedup; execution orchestration savings ≠ model capability.

**Target goals (aspirational, NOT permissions to weaken tests)**:
- remove >=15% truly duplicated lines only **within safely chosen and modified module families**, if measured and independently justified; otherwise leave code intact and explain why;
- cut focused wall-time >=20% if fixture reuse genuinely safe, without changing independent test number/case detection; do not fake speedup by dropping expensive tests;
- keep or strengthen all PIT/finance, book sequence and source-time guards;
- no new file longer than necessary, no circular imports, no changing approved API in-place without versioned compatibility witness.

## 八、文件交付

Required reports (do not create additional hundreds of pages):
- docs/engineering/architecture_lean_r1/EXECUTIVE_DECISION_AND_SCOPE.md
- docs/engineering/architecture_lean_r1/SOURCE_AND_TEST_DUPLICATION_MATRIX.md
- docs/engineering/architecture_lean_r1/THREE_WAVE_REFACTOR_AND_BEHAVIOR_EQUIVALENCE.md
- docs/engineering/architecture_lean_r1/CONTROLLER_NEXT_STEPS_AND_BLOCKERS.md
- evidence/v0.6/b_line/architecture_lean_r1/BASELINE_ARCHITECTURE_INVENTORY.json
- evidence/v0.6/b_line/architecture_lean_r1/TEST_COVERAGE_OWNERSHIP_MATRIX.json
- evidence/v0.6/b_line/architecture_lean_r1/BEFORE_AFTER_SOURCE_AND_TEST_METRICS.json
- evidence/v0.6/b_line/architecture_lean_r1/FINANCIAL_PIT_NEGATIVE_WITNESSES.json
- evidence/v0.6/b_line/architecture_lean_r1/EXACT_SHA_CI_AND_BEHAVIOR_PARITY.json
- optional bounded scripts/engineering/architecture_lean_r1 and hermetic tests/test_v06_architecture_lean_r1_*.py needed to reproduce above.

## 九、终态检查与报告格式

Strict final fields:
TASK_ID / AGENT_MODE=BOOST / START_SHA / BRANCH / FINAL_REMOTE_SHA / LINEAR_COMMIT_CHAIN / WRITE_SCOPE_PASS / EXISTING_GEMINI_NORMAL_CI_BRANCH_TOUCHED=NO / BASELINE_ALL_TESTS=3454_PASS_2_SKIP_AT_R3_SHA / FOCUSED_BASELINE_TIME / FOCUSED_FINAL_TIME / OWNED_CODE_LOC_BEFORE_AFTER / OWNED_TEST_IDS_BEFORE_AFTER / DUPLICATE_IMPLEMENTATION_ELIMINATED / FINANCIAL_PIT_BEFORE_AFTER / L2_CONTINUITY_UNCHANGED_NOT_VERIFIED / PROTECTED_METHODS_TESTS_TOUCHED=0 / REAL_ACCOUNT_ORDERS=0 / TESTNET_LIVE_AUTHORITY=NONE / SCIENTIFIC_ALPHA_AUTHORITY=NONE / FINAL_CI_RUN_AND_HEAD_SHA / FINAL_CI_ACTUAL_PYTEST_STEP / NONREGRESSION_EVIDENCE / REMAINING_BLOCKERS.

Terminal status is one of:
- LEAN_ARCHITECTURE_PROVEN_AND_FULL_CI_PASS__SCIENTIFIC_ALPHA_UNAUTHORIZED
- LEAN_ARCHITECTURE_SCOPED_PASS__FULL_CI_PENDING_OR_FAIL
- ARCHITECTURE_REFACTOR_BLOCKED_WITH_EVIDENCE

Do not interpret failure to reach a numerical LOC target as reason to remove protected tests. The **scientifically reliable minimal design** is the goal, not maximal deletion or artificial CI green. Controller L2 will decide integration only at exact immutable SHA.
