# S3A R2 独立 native FD/syscall 安全审计

**`S3A_CODEX_INDEPENDENT_AUDIT_FAIL_HARD_SYSCALL_ACCOUNTING_OR_ROOT_ISOLATION`。** 固定实现能够在100-call grant下实际执行144次open/fstat/pread/close而返回ALLOWED，只报告27；硬上限不成立。两种close故障下还存在“tracked FD=0、实际仍持有1”的财务之外资源清理错误。拒绝reader/security admission，未进行任何实现修复或真实源读取。

TASK=`V06_P2_S3A_CODEX_SOL_HIGH_INDEPENDENT_EXACT_SHA_FD_SYSCALL_AND_SOURCE_AUDIT_R1`；Controller=`874c42e8e3e4121955710f3207870aebb473e5da`；Prompt=`a6338e86a61c9349c3236da1d3e4ce81d03a54a2`；audit start/target=`999cf7005c741bdbabae727f10f90f23330fb035`，target parent=`30833953804bd965c80913ee6a3ecd4ae7457b40`。独立分支`feature/v06-bline-p2-s3a-codex-sol-audit-r1`不修改Gemini分支。请求Codex GPT-6 Sol High；具体model/effort控制未暴露，回执标NOT_EXPOSED并保留系统描述Codex/GPT-6，不伪称选择成功。

## 真正kernel trace与观测边界

冻结输入27场景及invented Parquet bytes，fixture SHA256=`534f9cbfc2b7f7bbe5e1fae19abd697fb18b66a8a7c358d90913a42a3134caf9`。文件由已安装PyArrow25.0.1在RAM里生成，列名invented_tick/invented_level、值1/2和7/8、synthetic KV marker；所有落盘都在新建`/tmp/s3a-ind-audit-*`，真实owner及pilot alias只作为禁止literal/临时相对路径模板。

本机无strace，沙箱TRACEME不支持；授权的提升环境成功。使用stdlib ctypes调Linux x86-64 `ptrace(TRACEME)`，只跟踪审计新fork的自己的child，不枚举其他进程、不读/proc。两个SIGSTOP标记界定reader或attestation操作；GET_SYSCALL_INFO分别给出实际kernel entry/exit和errno，避免猜测交替状态。并以独立Python OS-boundary hooks代理到原始os.open/fstat/pread/close/stat/scandir，一对一核对四种核心调用数与kernel计数。

监测不是R2自己的raw_kernel_invocation_log，也不是注释/预期数。所有失败调用都计数；successful FD归属独立维护。os.open代理在os.supports_dir_fd中保留真实capability，仅为避免instrumentation让平台检测误拒；不替换目标预算算法。仅在内存捕获原wrapper对象及OS调用，原目标源码、旧tests/docs/receipts不改。

Reader native scope排除fixture写入、grant attestation、额外攻击准备、auditor native fstat验证及审计cleanup。normal初次grant attestation的boundary记录为12，另单独attestation native实验也为12；不是把它们算进36或把两个独立实验伪称一次整体测量。27个场景中26个reader-operation与一个attestation-only。特定fixture额外grant/注册等setup不冒称已做整体kernel预算计量。

四核心计数对应R2公式open+fstat+pread+close；另保留stat/rename等已记录FS family。forbidden surrogate原生stat1、wrapper0；TOCTOU attack hook的rename1单列，属于攻击动作，不能错算reader预算。这是实际已列native syscall families的观测，不是全Linux syscall全集/全机器遥测证明。

## F01：漏记祖先遍历与实际超预算

[fd_syscall_wrapper.py:433–528](https://github.com/EXASHXE/btc-quant-agent-public/blob/999cf7005c741bdbabae727f10f90f23330fb035/scripts/strategy_research/p2_s3_footer_reader/fd_syscall_wrapper.py#L433) 直接os.open('/'), open ancestor, close, fstat；只末尾root leaf用_raw_open。浅层root为`/tmp/<fresh-base>/root`，原生各open11/fstat12/pread2/close11=36；wrapper8/9/2/8=27，差9是原生实际数，不靠静态乘法得出。

| grant cap | 目标decision | actual核心native | target reported | delta |
|---:|---|---:|---:|---:|
|1|BUDGET_INSUFFICIENT_STOP|0|0|0|
|2|BUDGET_INSUFFICIENT_STOP|11|2|9|
|3|BUDGET_INSUFFICIENT_STOP|12|3|9|
|25|BUDGET_INSUFFICIENT_STOP|33|24|9|
|27|ALLOWED|36|27|9|
|100 shallow|ALLOWED|36|27|9|
|100 +36合法temp祖先层|ALLOWED|144|27|117|

cap1在初始化即拒绝，这个正控予以认可，不能说所有low caps都越界。cap2/3/25虽然wrapper返回STOP，实际已经超cap；deep100是最强反例：原生open47/fstat48/pread2/close47=144，reader还返回允许读取。缺少总ancestor-depth/统一计量使绝对100调用保证失败，与成功CI不冲突。

## F02：错误路径第二次open与typed denial

由合法custody后改变临时ancestor，产生真正native ENOENT、ENOTDIR（symlink/regular file）和EACCES；后者只在child内降低UID至65534并chmod临时gate0，没有改全局账户/parent UID。原生trace中每个gate的前两次open errno相同；第一次失败后R2 line450调用_raw_open进行第二次真正失败open，而非记录前一次。

missing返回S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN，permission返回DENIED_EACCES_PERMISSION，symlink与non-directory分别拒绝。typed fail-closed分类的这些正项保留；重复open和计数漏记不因此消失。ENOTDIR后的不同flags disambiguation probe另列，不能拿“需要probe”掩盖相同失败open的重试。

## F03：原生close故障与FD责任

两个独立fault都将一次os.close的native参数显式改成−1，产生真实kernel EBADF；这是明确参数替换的故障注入，不声称普通valid FD自然会常常close失败。

* root ancestor close失败：line470在next_fd已打开、cur_fd尚未换成next_fd时失败，finally只关闭旧cur_fd。actual open2/close2=4，wrapper0；目标抛未结构化OSError，无完整reader error receipt；wrapper tracked remaining0，但next tmp FD仍在process中。
* tracked leaf close失败：`close_fd` line686先pop追踪，再line691执行native close；失败后无法再清理已pop的reopen leaf。目标返回DENIED_FD_CLEANUP_CLOSE_FAILED，拒绝被认可，但reported open_fds_remaining0与process仍持有1不相符。

每个held FD在native reader scope结束后用独立native os.fstat成功核验，由auditor在excluded cleanup关闭；不是通过/proc或只相信Python dict断言。失败注入的argument、native errno、原FD label、post-target held与cleanup均在trace。该测试证明错误分支不能认证“所有FD已close”；不宣称已发生真实用户数据或正常运行泄漏。

## P2正控、未证明事项及parser范围

27场景覆盖预算6、正常/深root、missing/symlink/non-dir/权限、close2、attestation、root replacement、multi-hop alias、同设备registered forbidden surrogate、hardlink、trailer后leaf replacement、oversize/corrupt Footer、无custody自mint、公开fixture factory自mint、production、simulated crossdevice、borrowed custody及'..' escape。raw结果逐项在机器trace。

Root/parent inode replacement、symlink/multi-hop、hardlink、借别root custody、temp '..'均拒绝；production及显式grant-root冲突在reader主体前拒绝。Known registered same-device fake owner拒绝且不读其body。模拟st_dev改变验证了对应分支，不是实际WSL mount/bind-mount实验；未获授权做真实mount。不同WSL路径/平台及全部并发races不被本次测试证明。

公开create_valid_synthetic_grant可自mint并通过自己临时root的测试；无registry custody不能通过。正确边界为TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION，不是external issuer、secret MAC或owner permission。Registry/checksum不能替未来真实source权益/独立issuer；本审计也不声称该synthetic factory攻破实际owner禁止域。

正常synthetic文件1007byte，只有两次native pread：(offset999,length8)、(offset208,length791)，总799bytes≤65544；没有native ordinary read或额外parser文件open，数据页[4,208)与file header未读，目标如实FILE_HEADER_NOT_VERIFIED。RAM BufferReader解析；统计/KV仅suppression flags，无实际min/max/KV marker泄露。oversize只读trailer8后拒绝，corrupt RAM Footer拒绝。此是测试到的bounded byte/parser行为，不认证任何真实Footer/schema/PIT；malicious all-Thrift CPU/RSS ceilings及全部库版本未经穷举。

## P3来源矛盾独立核验

权威为`c6823dbc...`实际JSON，正确keys为candidate_month_observations与additional_target_observations，不存在target_Checks。六candidate+七additional regular files=13。R2 Python constants及R2机器JSON全部13 row-wise一致，此修复应认可；R2 narrative §4.3仍两错误size、五未受原receipt支持的paths，见配套erratum。错误prose不能转成source/rights权威，不代表真实数据损坏。

原R1四份docs/evidence与3083395 parent byte-identical；21个固定source对象hash及目标模块getfile/hash被核验。既有target CI38039633974元数据已独立核实SUCCESS且head999cf700；2843passed/2skipped计数取自固定Controller，未读取H40或其他结果log。CI只表示其既有QA，不认证实际计量。

## 实际QA、边界与终态行动

新focused tests实时重新执行27个kernel场景，另fixture/provenance两测试；Python3.12/3.13各29PASS/0FAIL/0SKIP，27 fork-with-threads warnings如实保留。初次各4FAIL/25PASS是审计断言误把统计suppression标志名称当值泄漏，修正审计断言后核验实际字段；未改目标或冻结fixture。scoped Ruff和compileall PASS；无full-suite本地重跑。

PyArrow/pytest进程存在threads，CPython报告fork潜在deadlock；本次无hang，但不宣称多线程fork通用安全。native tracer有step/output上限，未认证所有native阻塞下wall-clock watchdog。这些审计工具限制与已经完整取得的144/27 native反例分开，不能被冒称生产reader接受。

真实Quant-agent/data无stat/lstat/realpath/open/read/hash/scandir；零市场API、2026/forward/H39/H40/H41/A-line结果/凭据/交易访问。仅public Git governance/metadata/code、已安装依赖及tmp invented文件。Parent/root inode和source sizes来自published Git，未重测WSL。只新增审计文件，所有实现、原tests、docs/receipts和CI保持原字节，不做修复。

**NEXT_CONTROLLER_ACTION：拒绝S3A security reader admission，维持S3B/real-source HOLD；选择另一个显式有界Codex实现dispatch或停止S3路线。** 本审计没有授予任何整改预算、真实Footer/row读取、P2 source、P3/P4、Alpha、TESTNET/LIVE权限。一个commit/nonforce push后返回exact audit SHA、direct parent999cf700、files及实际audit CI final结论；CI无论是否绿，都不能推翻FAIL_HARD。
