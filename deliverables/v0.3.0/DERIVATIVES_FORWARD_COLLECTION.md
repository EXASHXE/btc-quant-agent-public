# Derivatives 前向采集规范

## 目的

Run 0 没有可靠覆盖 2021–2026 的 point-in-time derivatives 历史，因此 D/E 不能回填或推断。本规范用于未来真实采集；它不会改变当前 `EXPERIMENTAL` 状态，也不会自动开启交易。

## 字段与时间语义

每个快照至少记录：

- `observed_at_ms`：本机收到并解析响应的 UTC 时间；as-of join 的唯一可见性边界。
- funding rate 及其原始 Binance 时间戳。
- open interest 与可计算的历史变化率；不得用未来一条记录计算过去变化率。
- taker buy/sell ratio、global long/short account ratio、perpetual basis。
- 每个字段的 source timestamp、请求 endpoint、HTTP 状态、缺失原因和 stale 状态。
- 可选 order book：bid/ask、spread bps、前五档 imbalance、snapshot sequence；默认关闭。

策略只能使用 `observed_at_ms <= decision_time` 且未超过配置 stale window 的快照。没有记录即为 unavailable，禁止前向填充跨越 stale window。

## 采集与存储

- 建议频率：每 15 分钟边界后采集一次；funding 结算窗口可提高频率。
- 原始响应 append-only 保存，规范化表按 UTC 日期分区 Parquet。
- 每批写 manifest：起止时间、行数、字段覆盖率、缺口、重复、乱序、source endpoint、程序版本和 SHA-256。
- 写入先使用临时文件并校验，再原子替换；禁止静默覆盖已有快照。
- 定期执行时钟偏移、API 限流、字段 schema 漂移和异常值告警。

## Order book 限制

公开 REST depth 是抓取时刻的横截面，不是可追溯的历史订单簿。只有连续维护 snapshot + diff sequence、能证明无序列缺口时，才允许 E 进入研究。否则 order book 始终标记 unavailable，不能把当前盘口用于历史回放。

## 进入下一轮研究的最低条件

- 至少覆盖多个市场状态和足够的实际信号窗口。
- 逐字段 point-in-time 覆盖率、缺口和 stale 比例可审计。
- A/B/C 共同安全核不变，D/E 只增量加入声明字段。
- 重新预注册假设、样本门、参数范围和选择规则。
- 不得把本次 holdout 用作 derivatives 调参开发集。

仓库已有 `quantctl collect-derivatives` 手动采集入口。没有创建定时任务：持续调度会产生外部请求和长期状态，应在用户明确同意频率、运行主机和保留策略后单独启用。
