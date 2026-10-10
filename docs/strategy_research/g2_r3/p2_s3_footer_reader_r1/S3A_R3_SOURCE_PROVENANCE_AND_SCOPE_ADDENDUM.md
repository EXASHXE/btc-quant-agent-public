# S3A R3 来源和权限 addendum

仅新补充说明，不改原R1/R2docs或machine receipts。源码与机器常量正确的13项必须保留；旧R2 narrative §4.3不能替代原始Git证据。

权威：[c6823dbc原JSON](https://github.com/EXASHXE/btc-quant-agent-public/blob/c6823dbc46249cac43aa10400aacbbe9f4542410/evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json)。实际直接git-show解析、SHA256=a3c9169dcbeb31edce492791ef253e42c580411cdb014337e8084229aaaaf3f2。两个数组分别candidate_month_observations、additional_target_observations，没有target_Checks。

固定999cf700 report §4.3 line149的BTC data_manifest.json 475应为45234；line150 funding_events.csv 424781应为219066。Line157 raw/funding/BTCUSDT_funding_rate_2020_202601.csv、line158 ETHUSDT_1h_klines.parquet、line159 SOLUSDT_1h_klines.parquet、line160 BTCUSDT_perp_1h.parquet、line161 BTCUSDT_spot_1h.parquet均不在其声称的原始receipt中，不能作为文件别名或推定真实物理存在/缺失。六个月度尺寸匹配原receipt，R2 constants/JSON的13项均匹配；不声称全部旧文数字错误。

|原始regular-file相对路径|字节数|
|---|---:|
|`research/BTCUSDT/1m/year=2021/month=03/data.parquet`|2756024|
|`research/BTCUSDT/1m/year=2021/month=04/data.parquet`|2621313|
|`research/BTCUSDT/1m/year=2023/month=03/data.parquet`|2415597|
|`research/BTCUSDT/1m/year=2023/month=04/data.parquet`|2201521|
|`research/BTCUSDT/1m/year=2025/month=03/data.parquet`|2352476|
|`research/BTCUSDT/1m/year=2025/month=04/data.parquet`|2329220|
|`research/BTCUSDT/data_manifest.json`|45234|
|`research/BTCUSDT/funding_events.csv`|219066|
|`research/BTCUSDT_SPOT/data_manifest.json`|19855|
|`research/cross_asset_1h/ETHUSDT.parquet`|2907000|
|`research/cross_asset_1h/basket_manifest.json`|56012|
|`research/v0.3.19_official_derivatives/hourly_inputs.parquet`|3101084|
|`research/v0.3.19_official_derivatives/raw_data_manifest.json`|420725|

这些是历史发布的metadata-only observations，不是本次物理扫描、Footer/schema/连续分钟/known-at Funding/rights证明。BTC spot为另一市场；ETH cross_asset_1h并非ETH perp1m；SOL1m、true minute Mark和Funding各时钟/rights仍UNKNOWN_NOT_VERIFIED_NOT_ADMITTED。旧叙述line163不能从有限目标集合推出全根ETH/SOL不存在。本次没有重测source mtime、inode或source内容；R3 native实验的dev/ino来自临时树，真实源尺寸只来自原Git。

审计91bf48e与Controller63f21db仅作固定引用，没有继承其reviews目录、实现文件或修写其reports。R3是一次实现候选，待Controller独立审计，不能接续Gemini无界patch，也没有S3B real-file grant。六BTC月份metadata、S2 PIT/Mark/Funding blueprint、P1 TERMINATED和P3/P4/Alpha/TESTNET/LIVE边界均不升级。

real owner /root/workspace/project/Quant-agent/data只作禁止literal；无stat/lstat/open/read/hash/list/realpath，原Quant-agent/Quant-agent-sanitized worktree不访问。Python包/代码/治理的Git对象、已安装依赖、审计自己的新/tmp invented文件是本次唯一相关读取。未来权益和真实源准入必须另获独立安全接受、精确文件同意和Controller dispatch。
