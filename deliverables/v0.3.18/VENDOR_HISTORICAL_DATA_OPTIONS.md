# Vendor Historical Data Options

本轮没有购买或导入付费供应商数据。以下均为潜在 `VENDOR_RECORDED_HISTORICAL_PIT_PROXY`，必须通过 exchange timestamp、receive timestamp、instrument mapping、sequence 与许可审计后才能使用。

| Provider | Potential BTCUSDT datasets | Timestamp / reconstruction value | Access / constraints | Assessment |
|---|---|---|---|---|
| Tardis.dev | trades, incremental L2, book snapshots, derivative ticker/OI/funding, liquidations | `timestamp` 与 `local_timestamp` 均为 µs；L2 含 snapshot/reset 语义 | 首月首日样本可用，完整历史通常需付费；不得擅自再分发 | 最适合先做限定样本的 L2/OI receive-time 审计 |
| Amberdata | Binance Futures order-book events/snapshots、funding、OI、liquidations、long/short | 覆盖表显示 Binance Futures 多类历史数据；精确字段仍需样本合同核验 | 商业访问与许可约束 | 适合机构级 OI/liquidation/L2 交叉评估 |
| Kaiko | backdated L2 bids/asks、trades | 提供 `tsExchange`、`tsCollection`、`tsEvent`；历史可通过 CSV/REST | 商业访问与再分发限制 | 适合 exchange-vs-collection timestamp 和 L2 质量审计 |
| CoinGlass | OI、funding、long/short、liquidation 聚合历史 | API 给出时间聚合序列；不是 tick-L2 ground truth | API key/套餐；聚合和 venue mapping 需核验 | 适合作为 derivatives sentiment/positioning proxy，不用于 L2 |

第一方资料：[Tardis data types](https://docs.tardis.dev/downloadable-csv-files/data-types)、[Amberdata CEX coverage](https://docs.amberdata.io/data-dictionary/coverage/exchange-coverage)、[Kaiko L2 bids and asks](https://docs.kaiko.com/cloud-delivery/data-feeds/level-2-tick-level/bids-and-asks)、[CoinGlass endpoint overview](https://docs.coinglass.com/reference/endpoint-overview)。访问日期：2026-09-02。

任何 vendor row 若试图标记为 `TRUE_FORWARD_LOCAL_PIT`，import contract 会拒绝。没有真实 incremental book 时，OFI、microprice、depth imbalance、queue dynamics 保持 `FORWARD_PIT_ONLY`，不会从 OHLCV 合成。
