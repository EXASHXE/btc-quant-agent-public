# S3A R3 一次性 syscall / FD 修复候选

终态：`S3A_CODEX_R3_ONE_SHOT_SYNTHETIC_SECURITY_CANDIDATE_PENDING_INDEPENDENT_CONTROLLER_AUDIT`。这是实现候选，等待 Controller 独立审计；没有 reader 独立安全签署或真实源授权。

TASK_ID=`V06_P2_S3A_CODEX_ONE_SHOT_NATIVE_FS_ACCOUNTING_AND_FD_CLEANUP_CORRECTNESS_R3`。Controller=`63f21db61980c209a90a5585375f761bf842bfaa`，Prompt=`d194497342076b9cafd24fa94a54e32186c65f06`，精确起点/本次 commit 的唯一直接 parent=`999cf7005c741bdbabae727f10f90f23330fb035`。分支`feature/v06-bline-p2-s3a-codex-one-shot-fd-r3`，从 R2 建立，未继承审计91bf48e的代码或reviews文件。

## 一个 meter，两个有名阶段，100次总上限

`create_valid_synthetic_grant` 的 root-custody preparation 也使用 MeteredPosixSyscallWrapper。root anchor、每个 ancestor open/fstat/close、failed open、分类 probe、finally cleanup 全部计量。grant保留进程内单次 preparation 记录；reader 消费原来的同一个 meter，计数/预算不清零。receipt的attempted_fs_calls_total是preparation+reader+各自cleanup；preparation_attempted_fs_calls和reader_attempted_fs_calls分别公开，按family给出preparation份额。不是把setup报告为0或给两个阶段各100次。

每个native open之前预留当前active FD关闭次数及新FD的一次close；fstat/pread前仍预留active close。预算不够就STOP，不先调用再计数。close只消费已保留slot。全部取得FD先登记，再进行fstat/前一个FDclose，因此祖先异常也有清理责任。代码没有对已失败的open按相同flags重放；ENOTDIR的另一次O_NOFOLLOW非directory分类probe是真实、不同flags、独立计量的调用。

source custody记录绑定根/parent的dev+ino、创建PID和原始syscall/byte limits；同一进程只消费一次，fork继承副本不允许消费。不能更改grant cap/byte上限后沿用prepared meter。无preparation、无custody、expired/forged grant、production/owner literal/非pilot/protected目标均拒绝。grant checksum仍是公开TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION，不能变成外部issuer或owner权限。

path validation使用已确定的tempfile.tempdir字符串或固定/tmp词法边界，不触发gettempdir探测。forbidden-surrogate lookup只查内存快照，不在reader隐藏stat/exists扫描。测试surrogate注册和生命周期清空是明确外部fixture构造/teardown；注销后的旧inode不再借作新case证据。没有通用路径探索器、S1/S2 verifier导入或新交易引擎。

## FD失败的诚实责任

正常close成功后才移除active FD。真实native close错误将FD转移到unconfirmed_fds，保留fd/label/status，open_fds_remaining包括这些可能仍live的FD，close_complete=False，输出FD_CLOSE_UNCONFIRMED_FAIL_CLOSED，不允许sanitized success。清理仍对其他已知active FD各尝试一次，绝不盲目重复关闭未确认的numeric FD（避免数字复用后误关）。异常路径的OSError/MemoryError与constructor/platform错误均成为结构化DENY receipt。

原生故障试验明确将一次close参数替换为-1，以真正kernel EBADF验证错误分支；不声称正常valid FD自然发生EBADF。另一个pre-entry simulated_close控制不进入os.close，记录simulated_pre_close_failures而不计虚构native调用。两个同label leaf FD均可受此test-only控制影响。native fault和pre-entry fault分列；auditor在trace结束后用真实fstat确认仍持有FD并清理，excluded teardown不伪称tool已关闭。若某个真实close错误实际上已经释放FD，也仍保守标unconfirmed，不自动重试。

## native对照与原始反例

独立测试作者维护OS API observer，逐次转发原始os.open/fstat/pread/close及相关stat/lstat/readlink。Linux x86-64自己的新child通过ptrace GET_SYSCALL_INFO读取实际entry/exit与errno；不是读取wrapper自己的log。fixture创建/import在trace外，grant preparation及reader/cleanup全部在trace内。root/leaf swap的rename/mkdir是标明的外部攻击动作单列，不计为reader调用。禁止出现未说明的native read/stat等额外IO。

32个冻结case输入SHA256=`2a5dde13fff75458f0fc78a35c5e4a0108e93b521c3fa25a6b026c500439c1c7`。下面每个actual=report均经真实assert；完整逐次记录在S3A_R3_NATIVE_SYSCALL_AND_FD_RESULTS.json。

|场景|prep|reader|actual = reported|结果|
|---|---:|---:|---:|---|
|cap1|0|0|0|STOP|
|cap2|2|0|2|STOP|
|cap3|3|0|3|STOP|
|cap25|16|9|25|STOP|
|cap27|16|11|27|STOP|
|cap36|16|19|35|STOP|
|normal depth1 cap100|16|40|56|ALLOW|
|depth5 cap100|28|52|80|ALLOW|
|depth36 cap100|99|0|99|STOP|
|ENOENT / true EACCES|16|17|33|DENY，无同flags重放|
|native ancestor close EBADF|6|0|6|unconfirmed1，DENY|
|native leaf close EBADF|16|40|56|unconfirmed1，DENY|
|pre-entry leaf close2|16|38|54|unconfirmed2，DENY|

R2审计短root为/tmp/base/root，其36/27是reader-only，且当时另有未合并setup。R3冻结depth1有一个额外合法ancestor，56=16prep+40reader，不能把不同geometry/scope伪称同一总量。另有精确R2短root geometry的R3对照：50=13prep+37reader，actual=reported；深36的共同反例现在在prep99 STOP，不会出现R2的144/27 ALLOW。Fork反例曾在本次内部交叉审查复现，PID绑定修复后child0 native/DENY，parent保持唯一有效消费。

## Footer与资源边界

仍仅单个2021-03相对pilot string；8byte trailer、Footer<=65536、合计<=65544、无真实header/page/row读取。FILE_HEADER_NOT_VERIFIED保留。实际输入为1009byte invented Parquet；metadata/KV marker及min/max统计不输出。类型门只接受RAM bytes，解析器仅构造bPAR1+footer+trailer的BufferReader。public ParquetFile仅取metadata，pre_buffer=False，Thrift string cap65536/container cap10000；不调用row读取API。旧静态检查仅对此严格RAM构造开放一个具体例外，并保留其余路径/FD便利函数禁令及native IO证明。

输入byte与Thrift容器限制约束本次解析，但没有证明所有Thrift布局的CPU/RSS/walltime；不存在普适parser sandbox/watchdog。原生tracer为Linux x86-64，fork-with-threads warnings保留，自己的child有trace-step/output上限，不证明多线程fork永不hang。

同设备bind mount/真实owner alias不能仅凭dev断言排除，也不能为了验证而检查禁止的owner根。全部测试是自己的/tmp新文件，surrogate只能验证模拟边界；不得称真实WSL隔离已认证。真实owner root filesystem/read count=0，无protected/Forward/H39/H40/H41/A-line outcome读取、市场API、账户/交易操作。

## 工程QA和有限交付

保留全部旧S3A检查，没有delete/skip/xfail。更新所必需的语义：原27计数改为含prep/ancestor的预算；独立invocation换fresh grant；close injection保留unconfirmed责任而非false zero；test fixture生命周期清空过期surrogate快照。原R1/R2docs和machine artifacts逐byte保留，新增R3证据和勘误。未产生reviews/、新source准入、P3/P4或Alpha权限。

实际最终Python版本、测试数量、warnings、code/test digests和JSON/compile/Ruff结果以S3A_R3_CODEX_EXECUTION_RECEIPT.json为准。本次一个commit/nonforce push，remote exactSHA与GitHub CI最终状态在发布后外部报告；receipt不伪造未来自身commit hash。CI失败照实报告，不修改waiver/config或读取受保护结果来推测归因。Controller随后独立核验和决定，不把本次实现测试当独立安全签署。
