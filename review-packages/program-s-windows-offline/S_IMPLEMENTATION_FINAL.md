# Program S — 提交0-C独立审查，状态S_PARTIAL

核验R Controller收据86b412b0ae9127fe8d11c87d44cbbc4c0744ee56cea56eed78b1595544660f7f及12项原POC代码hash。全部修改在S隔离目录，原R/A–P/O/J/L/Strict/C不变。

实际实现：J兼容外层Access及S严格证据内容检查，KR声明/目的/缓存/完整holdout绑定；新Owner会话code/policy/access/output/boot/QPC窗口及消费SQLite；真实连接只许显式127 CONNECT，无直连回退；HTTP拒绝/限速和绝对请求截止；fsync后raw durable采样及独立journal ACK；无频率替代的Windows双内核boot身份，QPC/Unbiased/Tick64控制；固定NTFS与静态reparse/traversal/reuse拒绝；数据束hash/SQLite检查及WSL no-follow私有快照；明确HISTORY_AUDIT与当前SOURCE_BLOCKED。

没有真实Binance/账户/订单/交易调用，没有OS服务/clocksource/WSL修改、重启、部署、PR操作或后继worker。没有使用或恢复已删除的N原数据。未制造真实许可、Owner签名、reviewer或独立市场来源认证。

## 实际证据

- 实际Windows11/Python3.14：原10+新增16=26项unittest最终全部PASS、0SKIP。精确命令/退出码/环境见audit/S_WINDOWS_EXECUTION_RECEIPT.json和S_NATIVE_NTFS_RECEIPT.json。
- 实际Windows约120.025秒、1195组原生QPC/Unbiased/Tick64，保留真实GUID+kernel boot epoch；没有墙钟跳变。睡眠/重启仅故障注入，未真实重启。W32Time实际不可用/未启动，原文本和退出码保留；绝对UTC未合格。
- 实际新NTFS目录产生14个HTTP200、17weight的**本机虚构CONNECT/TLS**束，经DrvFS进入WSL。不是14个Binance请求；真实市场请求为0。
- WSL11例最终PASS，包含实际NTFS束、当前/重复/stale拒绝与raw symlink TOCTOU。未将原Windows-only SKIP算成PASS。
- 本S物化的原O完整新一轮672项全部PASS、0FAIL/ERROR/SKIP。四组478/154/36/4；C的154项（包括此前workspace六例）均在允许workspace内，不改政策。不累计R/O历史结果或反复运行。
- 双构建wheel字节一致，Windows新NTFS venv离线安装成功，已安装boot模块hash等于源；只有live开关仍在创建输出/联网前退出。具体wheelSHA见S_REPRODUCIBLE_BUILD.json。
- Ruff和编译通过；初期fixture、第二次同进程构建、慢滴流截止等失败日志保留，修正后重新测试，不屏蔽case。

## 产品与时间边界

源NTFS/DrvFS、束hash、实际HTML/JSON/Markdown及SQLite路径见audit/S_OPERATOR_ARTIFACT_RECEIPT.json。BTC WATCH、ETH/SOL NO_SETUP全部为**合成历史S1计算**。HTML复用原reporting.table，不新增前端框架。计划、entry/stop/targets/成本几何和source引用来自原S1；不强填无效TP。历史重建不声称捕获时已真实发布，was_prospectively_issued=false。当前建议一律SOURCE_BLOCKED；没有真实机会或后续市场收益。

C保持SOURCE_CLASS_INVALID/INSUFFICIENT_SUPPORT，未改冻结协议或重标来源。SOURCE_QUALIFIED、SHADOW_QUALIFIED、ECONOMICALLY_VALIDATED均false；AccountUNKNOWN/VETO；S2/S3禁用。

## 必须保留的未完成项

本版**不是可批准整条真实当前建议流程的生产发布**。公共真实束仍因缺独立Windows现时/保留期锚而拒绝；CURRENT_MANUAL_REVIEW亦拒绝。不能用WSL时间补齐。

hash链证明完整性，不单独证明Owner/交易所来源真实性；独立可信bundle摘要与真实授权/适用rights尚无证据。生产者目录/reparse竞态还须独立验证；完整进程（含阻塞磁盘I/O）的120秒硬终止尚未实现，本版提供的是请求级截止与会话检查。不能将这些剩余项藏在“待真实授权”标签下。

所有临时目录为合成QA；路径清单见S_QA_CACHE_PATHS.json，无后台清理。未来真实raw必须24h以内且所有副本同一原截止，Owner精确路径手工清理并留hash-only实际回执。未延长N保留、未删除任何原数据。

建议0-C仅考虑独立验收此次Windows离线控制和历史审计的有限范围；在上述锚定、真实性与终止/竞态项补齐前，不签发真实整链扫描许可。S_OWNER_ACTION_PACKET_NON_AUTHORIZING.md不是授权。
