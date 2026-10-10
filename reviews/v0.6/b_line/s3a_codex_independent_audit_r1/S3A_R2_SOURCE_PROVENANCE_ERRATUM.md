# S3A R2 provenance 独立勘误 — 不修改原记录

权威是[原始c6823dbc JSON](https://github.com/EXASHXE/btc-quant-agent-public/blob/c6823dbc46249cac43aa10400aacbbe9f4542410/evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json)，SHA256=`a3c9169dcbeb31edce492791ef253e42c580411cdb014337e8084229aaaaf3f2`。本次直接git-show并解析其真实结构，不读取任何物理数据根或接受report作为source of truth。

错误所在：[固定R2 report §4.3](https://github.com/EXASHXE/btc-quant-agent-public/blob/999cf7005c741bdbabae727f10f90f23330fb035/docs/strategy_research/g2_r3/p2_s3_footer_reader_r1/S3A_R2_BOUNDED_SECURITY_REPAIR_AND_ERRATA_REPORT.md#L144)，不是R2 constants/新machine JSON。

| 错误位置 | R2 narrative声称 | 原始Git JSON实际 |
|---|---|---|
|line145 schema|target_Checks数组|不存在；candidate_month_observations及additional_target_observations |
|line149 BTC data_manifest|475 bytes|45234 bytes |
|line150 funding_events.csv|424781 bytes|219066 bytes |
|line157 raw/funding/BTCUSDT_funding_rate_2020_202601.csv|679115 bytes|此path不在receipt；不能借作funding_events.csv或其他file alias |
|line158 ETHUSDT_1h_klines.parquet|2522069 bytes|此path不在receipt；实际research/cross_asset_1h/ETHUSDT.parquet=2907000 |
|line159 SOLUSDT_1h_klines.parquet|2000906 bytes|此path不在receipt；没有验证SOL1m或该hourly path |
|line160 BTCUSDT_perp_1h.parquet|2616951 bytes|此path不在receipt |
|line161 BTCUSDT_spot_1h.parquet|2913841 bytes|此path不在receipt；实际spot data_manifest=19855，并非上述file |

这些source替换不是format差异。Six BTC monthly sizes在narrative中确实匹配，应保留认可，不说全部13都错。Line163关于不存在ETH/SOL1m目录的解释无法由有限17 metadata targets推出；原正确结论为UNKNOWN_NOT_VERIFIED_NOT_ADMITTED。其他任意旧source/年份路径不能靠此被当成owner授权或physical证据。

原receipt regular-file13行与R2 constants、`S3A_R2_FS_SYSCALL_SECURITY_ORACLE_RESULTS.json::f04_verified_c6823dbc_file_sizes_bytes` 全部一致：

| 原始相对路径 | 原始 / R2 constants / R2 JSON bytes |
|---|---:|
| `research/BTCUSDT/1m/year=2021/month=03/data.parquet` | 2756024 |
| `research/BTCUSDT/1m/year=2021/month=04/data.parquet` | 2621313 |
| `research/BTCUSDT/1m/year=2023/month=03/data.parquet` | 2415597 |
| `research/BTCUSDT/1m/year=2023/month=04/data.parquet` | 2201521 |
| `research/BTCUSDT/1m/year=2025/month=03/data.parquet` | 2352476 |
| `research/BTCUSDT/1m/year=2025/month=04/data.parquet` | 2329220 |
| `research/BTCUSDT/data_manifest.json` | 45234 |
| `research/BTCUSDT/funding_events.csv` | 219066 |
| `research/BTCUSDT_SPOT/data_manifest.json` | 19855 |
| `research/cross_asset_1h/ETHUSDT.parquet` | 2907000 |
| `research/cross_asset_1h/basket_manifest.json` | 56012 |
| `research/v0.3.19_official_derivatives/hourly_inputs.parquet` | 3101084 |
| `research/v0.3.19_official_derivatives/raw_data_manifest.json` | 420725 |

原 additional_target_observations还包含父directory metadata（非regular file），不能把目录size当文件或1m连续Mark/Funding PIT证据。Narrative的mtime表与原file_mtime来源也不可默认等价；本勘误的必要判定限于明确解析到的keys、paths、sizes，未发布新物理mtime测量。

旧R1四个文件与parent3083395字节保持；其旧数字保留历史记录，不能因为新constants修正就声称旧记录本来正确。该erratum仅新增审计addendum，未补写、修改或删除Gemini report、Python constants、machine receipts或原c6823dbc。

**结论：机器/代码size修复正确，R2 report §4.3证据引用不可信。** 这与native syscall FAIL_HARD分别成立，不声明实际原数据损坏、不认证schema/rights/Mark/PIT，也不授任何source QA或交易权限。完整row-wise机器比较存于本审计execution receipt的source_provenance字段。
