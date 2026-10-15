# Wave 1 / Task A — Binance BTC+ETH source and existing-data reuse audit R1

**Task:** `V06_DATA_A_BINANCE`. **Terminal:** **`A_METADATA_READY_WITH_LIMITS`**. **Mode:** public documentary and object-listing metadata only; `LOCAL_INVENTORY_UNKNOWN`. Observation date **2026-10-15 UTC / 2026-10-16 UTC+08**. Executor: Codex, one substantive Task A author, no agents delegated. Controller 0 review pending; independent 1 is required before any PIT/rights acceptance, neither of which is asserted here.

**Outcome:** Binance-owned listings corroborate the requested BTCUSDT/ETHUSDT Spot and USD-M families, including actual **monthly fundingRate** and **daily metrics** object names for both instruments. Forty bounded listings establish representative object identities, not full history or content integrity. The now-published R10-D1 report is a **PARTIAL_STOP**, with bar-QC success and incomplete/timing-ambiguous metrics. It is a reuse witness to preserve, not a task to repeat. Existing private-copy inventory and incremental required bytes remain unknown.

## 1. Frozen authority, evidence and publication boundary

| Evidence | Exact immutable identity / observation |
| --- | --- |
| Task A dispatch | [`ade4df19872122686432cd955d8f139f16069449`](https://github.com/EXASHXE/btc-quant-agent-public/commit/ade4df19872122686432cd955d8f139f16069449) |
| Dispatch sole direct parent | `4d83123243db8cf5ac4fd7b1c00608cb149f7bdc` |
| Full Task A prompt | [frozen prompt](https://github.com/EXASHXE/btc-quant-agent-public/blob/ade4df19872122686432cd955d8f139f16069449/prompts/v0.6/b_line/data_program/V06_DATA_A_BINANCE_SOURCE_INVENTORY_LOCAL_CODEX_R1.md), blob `0b757f0a06482b0656cdd6b337cab8d6f6590b63`; complete text read and identity verified |
| Co-committed stage/storage plan | [plan](https://github.com/EXASHXE/btc-quant-agent-public/blob/ade4df19872122686432cd955d8f139f16069449/docs/project/V06_MULTI_VENUE_DATA_PROGRAM_AND_STORAGE_PLAN_R1.md), blob `805ac2524a9c28e167601603a36187b3a4398619`; complete text read |
| Co-committed DAG/queue | [DAG](https://github.com/EXASHXE/btc-quant-agent-public/blob/ade4df19872122686432cd955d8f139f16069449/docs/project/V06_PARALLEL_TASK_DAG_AND_EXECUTION_QUEUE_R1.md), blob `67de9b2a1c924effb5466f0f6da26d709405f537`; complete text read |
| R10-D1 frozen dispatch/prompt | `4d83123243db8cf5ac4fd7b1c00608cb149f7bdc` / `0e78a8a91205c7c8d531f7a4b101612dcdd83290` |
| R10-D0 historical author/STOP | `980a4b6f79de5ad6dbff8d8b674ce3ca2d056c4b`, report blob `14b993d63195b7970a4b1326ffe03b67212a0a47`; zero acquisitions/QC/tests then, not proof archives are absent |
| Intended isolated publication | `docs/v06-data-a-binance-source-inventory-r1`; one new report, sole author-commit parent equals this dispatch |
| Only authorized changed path | `docs/project/V06_DATA_A_BINANCE_SOURCE_INVENTORY_R1.md` |

No Task A read-only local data roots or new local execution workspace were designated. Earlier R10-D1 workspace grants do not extend to this task. No D1 workspace, original/private data root, protected data, account, local Git checkout or current disk inventory was inspected. The prompt bootstrap used a transient local copy of the public prompt; remaining audit state, report preparation and publication use in-memory GitHub connector operations, with no local inventory or clone. No private paths or licensed raw rows are published.

The author commit and report blob are verified through remote Git objects and the one-file compare after creation; exact final commit/blob/diff/remote head and actual hosted CI are returned in the execution receipt. These self-referential hashes and future CI are not pre-invented in report content. The Task A branch is not merged with the separate R10-D1 author branch. No PR merge, source intake or successor dispatch is performed.

## 2. Public source evidence and witness strength

| Source | Frozen Git identity or bounded live observation | What it proves / limit |
| --- | --- | --- |
| [Provider README](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/README.md) | Publisher `f446ce3812bd4e5521f21faecd4ae3c6460e49fc`; blob `e01e34a0b0cd91d62386a5a237190a3167138bae` | Family documentation, Spot timestamp change, general retrospective publication, checksums and revisions; not per-partition completeness |
| [Python helper README](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/python/README.md) | Blob `77671f0b61ae35f3de9d7d8aed0b8370c1ca12c4` | Spot/um daily/monthly helpers and futures reference bars; helper default year is not archive inception |
| [Premium helper implementation](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/python/download-futures-premiumIndexKlines.py) | Blob `74bfae744bce78f99fc675cf6788a417b3795a9b` | Actual family is `premiumIndexKlines`; README's `premiumPriceKlines` naming is inconsistent |
| [Path construction helper](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/python/utility.py) | Blob `72d3ee62cd727bfbfc412783d65a7dca151f1773` | Product/period/family/symbol/interval path construction; read as source only, never executed |
| [Dataset Terms](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md) | Blob `87d04e216f62c86a2c797fbb7637404d6d602687`, v1.0, 2026-08-26 | Conditional archival purpose restrictions; no owner-specific legal or future-live acceptance |
| [Official directory UI](https://data.binance.vision/) | Its HTML config names bucket `https://s3-ap-northeast-1.amazonaws.com/data.binance.vision` and website origin `https://data.binance.vision` | Establishes provenance of the metadata endpoint below; rendered UI alone returned only table headings |
| [USD-M daily family listing](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2F&delimiter=%2F&max-keys=100) / [monthly family listing](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2F&delimiter=%2F&max-keys=100) | Both root-prefix responses untruncated; names only | Daily includes metrics; monthly includes fundingRate. No daily fundingRate or monthly metrics family appeared in these root listings at observation; not a timeless nonexistence claim |
| Forty symbol/family/period metadata listings in section 5 | At most **2 keys/listing**, concurrency at most 4, no retries; **32,973 XML response bytes**; window **2026-10-15T17:47:22.945218+00:00–17:47:31.033621+00:00** | 40 ZIP names and their 40 paired checksum filenames, with publisher-advertised byte sizes and Last-Modified. Every response `IsTruncated=true`; no full catalog pagination or coverage census |
| [Current provider master](https://api.github.com/repos/binance/binance-public-data/commits/master) | Observed master still equals frozen `f446ce3812bd4e5521f21faecd4ae3c6460e49fc` | No newer publisher commit/terms at this check; moving pointer is not itself immutable |
| [Issue #491](https://github.com/binance/binance-public-data/issues/491) | Reporter `adebrief`; created 2026-08-24, updated 2026-09-09; open, 0 comments when checked | Alleged 2026-06-25 metrics label change; no publisher adjudication or independent reproduction by A |

**Task A acquisition ledger:** zero archive HEAD requests, zero ZIP-body requests, zero CHECKSUM-content requests, zero archive data bytes, zero source parsing/QC runs, zero strategies or PnL trials, USD 0. Directory XML and public Git/docs are metadata, not market payloads. No market REST/WS endpoint was called. The two root-family listings are additional to the forty bounded object-name listings. Metadata reads do not establish possession, license acceptance, payload checksums, historical original availability or broad source admission.

## 3. R10-D1 remote status — published witness, no rerun

Remote `refs/heads/feature/v06-r10-d1-local-binance-vision-dev-qc-r1` resolves to **`5630b178bf2f497f67a7e2db2d730f0b2aacabfe`**, whose sole parent is **`4d83123243db8cf5ac4fd7b1c00608cb149f7bdc`**. Its [exact report](https://github.com/EXASHXE/btc-quant-agent-public/blob/5630b178bf2f497f67a7e2db2d730f0b2aacabfe/docs/project/V06_R10_D1_CODEX_LOCAL_BINANCE_VISION_DEV_QC_R1.md) has blob **`7e8f126287e428c739d8c65230eb4366cc8c3256`**. Remote comparison confirms one commit ahead, zero behind its dispatch and exactly the three authorized D1 additions. The dispatch plan's earlier no-author-branch observation is historical; the remote author is now observed.

**Published D1 terminal: `R10_D1_LOCAL_DEV_QC_PARTIAL_STOP`.** For USD-M BTCUSDT, 2022-09-15..21 EXPOSED_DEV only, the author reports 21 ZIPs/21 matched SHA-256 checksums, 758,218 compressed bytes and 2,343,412 expanded bytes. Trade and mark-price 1m each have 10,080 complete unique bars. Daily metrics have 288 labels/day, zero internal gaps/duplicates, but `count_toptrader_long_short_ratio` and `sum_toptrader_long_short_ratio` are each empty for all 2,016 rows. Labels are 00:00..23:55; the rejected candidate end-grid's boundary discrepancies are not lost interior observations. True content-close semantics remain unknown.

D1 reports 24 passing synthetic cases, 1,213 full pytest passes with 9 warnings, local mypy/compileall success, and repeat offline receipt identity. Its [actual hosted CI](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38779186106) is **completed/failure**: the remote job failed `ruff check .`, then skipped mypy/pytest/compileall. The author attributes six existing H41 lint findings; A verifies the remote failing step/status and preserves that attribution without accessing H41 files. None of D1's tests, checksums or row-QC were rerun in A.

The D1 report's local aggregate-receipt hashes are `027a5776c1ea225048cc13103db093ddefb1e93b7f68e02f86210f102a0d44b0` (acquisition) and `0e79e8932da2a8b3f0cebc9dad0e6fd73e7f1208228a2e76d6d8e9e13302bcd3` (offline QC). A did not open those local files. This session previously authored D1; checking its remote immutable receipt is not independent source QC. Local persistence/current copy identity remains unverified. Do not transfer its seven-day findings to ETH, Spot, another date or another family.

## 4. Rights, units, clocks, checksums and missingness dimensions

The matrix below is relational: every per-object row in section 5 inherits these explicit common fields and joins its U/C/M family codes here. This supplies venue/product/instrument/family/UTC partition/status/URL/rights/units/clock/checksum/existing-copy/history without manufacturing content witnesses.

| Common manifest field | Value for every A listing row |
| --- | --- |
| Publisher / source type | Official Binance Vision archive, witnessed through provider-owned directory metadata |
| Inventory status | `AVAILABLE_UNMEASURED`: exact object name listed; payload not fetched or verified by A |
| Source-rights code R1 | Conditional personal noncommercial nonproduction archive category; owner/entity/geographic entitlement `RIGHTS_UNRESOLVED`; future live rights not granted |
| Checksum code K1 | Paired checksum filename listed; publisher documents SHA-256; **digest=NULL, payload verification=NOT_RUN_IN_A** |
| Existing-copy code L1 | `LOCAL_INVENTORY_UNKNOWN`; existence, current size, hash, completeness and vintage of private copies unknown |
| History/completeness | Earliest **listed filename witness** below; true event bounds, full missing-date set, latest coverage, row/schema continuity and complete month counts unknown |
| Measured storage | `compressed_bytes=NULL, expanded_bytes=NULL, retained_bytes=NULL, parquet_bytes=NULL`; advertised listing size is a distinct field |
| Source vintages | Provider Git documentation frozen; object listings mutable at recorded check; Last-Modified is not original publication or first receiver arrival |
| Availability / admission | `PIT_UNKNOWN / SOURCE_NOT_ADMITTED`; original publication and receiver-first-known NULL |
| Exposure | No exposure eligibility assigned to metadata-only candidate dates; D1's specific slice remains EXPOSED_DEV, never fresh OOS |

**Rights interpretation (R1):** the frozen Dataset Terms' sections 4.1/4.2 distinguish qualifying personal historical research from prohibited live proprietary execution. Sections 2.4/3/4.3–4.5 cover derived work, commercial exclusions and redistribution; attribution/share-alike and applicable third-party restrictions remain. General/entity/local conditions require a separate decision before intake or acceptance. The helper repository's MIT code label does not relicense data. No commercial, production-feed, future personal LIVE, redistribution or source-admission right is asserted by A. Binance direct REST/WS rights are a separate unresolved source contract. Attribution: Binance Vision; sanitized D1-derived metadata retains CC BY-NC-SA 4.0 obligations to the extent applicable, with no sponsorship claim.

| Units code | Field/units contract and remaining unknowns |
| --- | --- |
| U1 — klines 1m | OHLC quote USDT/base BTC or ETH; base volume in the instrument base, quote volume USDT, counts dimensionless integers; taker-base/taker-quote correspond. Exact schema/header/nullability needs partition validation |
| U2 — trades | Trade ID, price, base quantity, quote quantity where documented, exchange trade timestamp and maker flags; price USDT/base, quantities base/quote. Public prints are not own fills |
| U3 — aggTrades | Provider-compressed trades, separate aggregate IDs and underlying-ID ranges; price/quantity base/quote as appropriate. Aggregation rules are product/version specific; not an independent duplicate sample or interchangeable raw full tape |
| U4 — mark/index 1m | Reference OHLC in USDT/base for the specified USD-M instrument/reference pair. Mark and index are distinct; bar-shaped ignored/count/volume fields are not executable traded size |
| U5 — premiumIndexKlines 1m | Premium index ratio/bar, dimensionless and potentially negative; do not apply positive-price or traded-volume validation blindly. Exact archive fields remain unparsed |
| U6 — fundingRate monthly | Funding-rate observation, not an account cash ledger. Rate is dimensionless; interval, rate scale, archive field names/time unit, instrument revision, position/notional membership and cash-currency accounting must be verified; never assume fixed 8h for all history |
| U7 — metrics daily | Aggregated OI stock snapshot/value and long/short ratios; taker-volume ratio is interval flow. Ratios dimensionless; native OI quantity/value units and contract conversion require official versioned economic definitions, not guessed CSV names |

For current semantic context only, [Binance market-data documentation](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) separately defines funding rates/times and aggregate open-interest statistics with an end-period millisecond timestamp. That does not establish historical archive column layouts or clocks. The premium-index endpoint's signed OHLC is another reason not to reuse a strictly positive price parser. Documentation was read; endpoints were not invoked.

| Clock code | Semantics and causal boundary |
| --- | --- |
| C1 — closed-bar candidate | Open label and interval/close time are distinct. A complete 1m bar cannot be used at its own opening. Spot archives from 2025-01-01 use microseconds per frozen README; older Spot candidates require ms validation. Do not apply Spot's change to USD-M; D1 only witnesses ms on its own seven USD-M BTC days |
| C2 — trade event | Exchange event label and trade ID are not archive release or first receiver-known. Validate Spot us/ms by partition and USD-M time units independently; ordering/ID gap checks need payloads |
| C3 — funding | Settlement/assessment label, rate-observation window, publication and user cash posting are distinct. Archive time unit and schedule unverified; archive availability is retrospective |
| C4 — metrics | `create_time` is a provider label, true window-close unknown. OI stock is not taker interval flow. End-label hypothesis: stock T/flow [T-5m,T); start-label hypothesis: stock T+5m/flow [T,T+5m). Both require separate evidence. D1's predeclared assumed-end +5/+10/+15m are diagnostic proxies, not original receiver proof |

The provider's general policy is daily archive availability the following day and monthly availability on the first Monday of the following month; it is not a family-specific original-release SLA or proof of when 2017/2020 bytes first existed. Archive replacements are documented. Record original/revised digest and source vintage before reuse; later paired checksum success proves current object consistency only. No ZIP, kline close, funding label or S3 Last-Modified can supply historical original receiver-first-known, durable ACK, bid/ask queue/size/latency, maker fill, fees, full funding membership or after-cost Alpha.

| Missingness/history code | Expected checks before any reuse; present A knowledge |
| --- | --- |
| M1 — bars | Validate day/month boundaries, 1,440 1m/day when applicable, UTC grid, duplicate labels, missing minutes, close-time precision and schema changes. Monthly/daily overlap is not extra coverage. Payload-level findings unknown except the attributed D1 slice |
| M2 — trades | Check product-scoped trade IDs, missing/duplicate IDs/events, symbol launch/partial months and schema vintages. Zero-trade minutes are not automatically missing files; current private-copy completeness unknown |
| M3 — aggTrades | Check aggregate/underlying-ID meaning and product-specific aggregation, gaps/duplicates and overlap with raw trades. Keep economic duplication separate from byte duplication |
| M4 — reference bars | Separate mark/index/premium identities; validate real observation gaps and ignored fields. A matching trade bar does not prove mark/index completeness. Premium can be signed |
| M5 — funding | Monthly family is catalogued; daily family not observed in the untruncated USD-M root listing. Check actual assessment intervals and records; absence of a daily product is not a lost funding payment |
| M6 — metrics | Daily family catalogued; monthly family not observed in USD-M root listing. Check all required numeric fields, 5m grid, duplicate boundary labels and timing semantics. D1's two missing columns are observed only on its BTC seven-day slice; ETH/other-date field completeness unknown |

The reporter-only [#491 allegation](https://github.com/binance/binance-public-data/issues/491) concerns a 2026-06-25 start/end-label shift. It is not a confirmed publisher contract. D1's 2022 start-grid observations cannot reproduce that later transition or independently prove when contents were observable. The archived OI field here is **a derived aggregate statistic**, not a venue-native continuous per-position event stream.

Spot has no perpetual funding/OI/mark/premium product in this audit: mark/index/premium/funding/metrics are not silently mapped to Spot. A separately named margin/derivatives statistic would require its own identity. Adjacent daily `bookDepth` and daily/monthly `bookTicker` prefixes were visible at the USD-M root; those names alone establish neither symbol coverage nor reconstructible continuous full L2. No Tier C or forward-recorder permission follows.

## 5. Product/instrument/family/partition matrix — bounded object metadata

**Source URI rule:** prepend `https://data.binance.vision/` to each exact object key in the URL/identity column. The linked metadata URL is the evidence actually read; **the resulting ZIP URI was never requested**. All rows carry R1/K1/L1 and the common status fields above. Each exact ZIP key's paired `.CHECKSUM` key also appeared in the same 2-key response. No checksum bytes, ETag-as-checksum inference, CRC, rows or derived features were obtained.

The advertised byte column is a publisher listing attribute, not measured compressed data or a capacity benchmark. Last-Modified is a mutable object observation, not historical release. First keys are lexically first returned by the bounded prefix queries, not proof of genuine event inception or a complete earliest month.

| Venue | Product | Instrument | Family | Representative UTC filename partition | Evidence URL / exact source key | Advertised ZIP bytes | Listed Last-Modified | Units / clock / missingness |
| --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| Binance | SPOT | BTCUSDT | klines 1m | daily: 2017-08-17 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Fspot%2Fdaily%2Fklines%2FBTCUSDT%2F1m%2F&max-keys=2); `data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2017-08-17.zip` | 29,761 | 2023-07-18T04:11:20.000Z | U1 / C1 / M1 |
| Binance | SPOT | BTCUSDT | klines 1m | monthly: 2017-08 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Fspot%2Fmonthly%2Fklines%2FBTCUSDT%2F1m%2F&max-keys=2); `data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2017-08.zip` | 595,271 | 2021-06-22T11:33:31.000Z | U1 / C1 / M1 |
| Binance | SPOT | BTCUSDT | trades | daily: 2017-08-17 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Fspot%2Fdaily%2Ftrades%2FBTCUSDT%2F&max-keys=2); `data/spot/daily/trades/BTCUSDT/BTCUSDT-trades-2017-08-17.zip` | 63,039 | 2023-05-25T15:29:56.000Z | U2 / C2 / M2 |
| Binance | SPOT | BTCUSDT | trades | monthly: 2017-08 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Fspot%2Fmonthly%2Ftrades%2FBTCUSDT%2F&max-keys=2); `data/spot/monthly/trades/BTCUSDT/BTCUSDT-trades-2017-08.zip` | 1,172,057 | 2021-06-10T11:38:55.000Z | U2 / C2 / M2 |
| Binance | SPOT | BTCUSDT | aggTrades | daily: 2017-08-17 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Fspot%2Fdaily%2FaggTrades%2FBTCUSDT%2F&max-keys=2); `data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2017-08-17.zip` | 51,003 | 2023-06-08T04:34:15.000Z | U3 / C2 / M3 |
| Binance | SPOT | BTCUSDT | aggTrades | monthly: 2017-08 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Fspot%2Fmonthly%2FaggTrades%2FBTCUSDT%2F&max-keys=2); `data/spot/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2017-08.zip` | 921,437 | 2021-06-10T10:14:04.000Z | U3 / C2 / M3 |
| Binance | SPOT | ETHUSDT | klines 1m | daily: 2017-08-17 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Fspot%2Fdaily%2Fklines%2FETHUSDT%2F1m%2F&max-keys=2); `data/spot/daily/klines/ETHUSDT/1m/ETHUSDT-1m-2017-08-17.zip` | 32,149 | 2023-07-18T08:55:23.000Z | U1 / C1 / M1 |
| Binance | SPOT | ETHUSDT | klines 1m | monthly: 2017-08 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Fspot%2Fmonthly%2Fklines%2FETHUSDT%2F1m%2F&max-keys=2); `data/spot/monthly/klines/ETHUSDT/1m/ETHUSDT-1m-2017-08.zip` | 614,912 | 2021-06-22T11:34:33.000Z | U1 / C1 / M1 |
| Binance | SPOT | ETHUSDT | trades | daily: 2017-08-17 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Fspot%2Fdaily%2Ftrades%2FETHUSDT%2F&max-keys=2); `data/spot/daily/trades/ETHUSDT/ETHUSDT-trades-2017-08-17.zip` | 78,809 | 2023-05-25T21:41:02.000Z | U2 / C2 / M2 |
| Binance | SPOT | ETHUSDT | trades | monthly: 2017-08 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Fspot%2Fmonthly%2Ftrades%2FETHUSDT%2F&max-keys=2); `data/spot/monthly/trades/ETHUSDT/ETHUSDT-trades-2017-08.zip` | 1,181,333 | 2021-06-10T11:45:09.000Z | U2 / C2 / M2 |
| Binance | SPOT | ETHUSDT | aggTrades | daily: 2017-08-17 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Fspot%2Fdaily%2FaggTrades%2FETHUSDT%2F&max-keys=2); `data/spot/daily/aggTrades/ETHUSDT/ETHUSDT-aggTrades-2017-08-17.zip` | 64,274 | 2023-06-07T16:01:50.000Z | U3 / C2 / M3 |
| Binance | SPOT | ETHUSDT | aggTrades | monthly: 2017-08 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Fspot%2Fmonthly%2FaggTrades%2FETHUSDT%2F&max-keys=2); `data/spot/monthly/aggTrades/ETHUSDT/ETHUSDT-aggTrades-2017-08.zip` | 1,024,768 | 2021-06-10T10:19:25.000Z | U3 / C2 / M3 |
| Binance | USD-M PERP | BTCUSDT | klines 1m | daily: 2019-12-31 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2Fklines%2FBTCUSDT%2F1m%2F&max-keys=2); `data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2019-12-31.zip` | 56,711 | 2022-03-21T08:58:10.000Z | U1 / C1 / M1 |
| Binance | USD-M PERP | BTCUSDT | klines 1m | monthly: 2020-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2Fklines%2FBTCUSDT%2F1m%2F&max-keys=2); `data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2020-01.zip` | 1,829,116 | 2021-06-14T06:12:38.000Z | U1 / C1 / M1 |
| Binance | USD-M PERP | BTCUSDT | trades | daily: 2019-09-08 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2Ftrades%2FBTCUSDT%2F&max-keys=2); `data/futures/um/daily/trades/BTCUSDT/BTCUSDT-trades-2019-09-08.zip` | 55,253 | 2022-03-04T23:40:33.000Z | U2 / C2 / M2 |
| Binance | USD-M PERP | BTCUSDT | trades | monthly: 2019-09 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2Ftrades%2FBTCUSDT%2F&max-keys=2); `data/futures/um/monthly/trades/BTCUSDT/BTCUSDT-trades-2019-09.zip` | 14,243,543 | 2022-03-02T04:38:59.000Z | U2 / C2 / M2 |
| Binance | USD-M PERP | BTCUSDT | aggTrades | daily: 2019-12-31 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2FaggTrades%2FBTCUSDT%2F&max-keys=2); `data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2019-12-31.zip` | 1,518,388 | 2022-03-03T23:05:43.000Z | U3 / C2 / M3 |
| Binance | USD-M PERP | BTCUSDT | aggTrades | monthly: 2020-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2FaggTrades%2FBTCUSDT%2F&max-keys=2); `data/futures/um/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2020-01.zip` | 102,586,079 | 2021-06-14T06:04:10.000Z | U3 / C2 / M3 |
| Binance | USD-M PERP | BTCUSDT | markPriceKlines 1m | daily: 2019-12-23 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2FmarkPriceKlines%2FBTCUSDT%2F1m%2F&max-keys=2); `data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2019-12-23.zip` | 22,946 | 2023-07-07T06:39:13.000Z | U4 / C1 / M4 |
| Binance | USD-M PERP | BTCUSDT | markPriceKlines 1m | monthly: 2020-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2FmarkPriceKlines%2FBTCUSDT%2F1m%2F&max-keys=2); `data/futures/um/monthly/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2020-01.zip` | 1,375,518 | 2021-03-29T13:23:45.000Z | U4 / C1 / M4 |
| Binance | USD-M PERP | BTCUSDT | indexPriceKlines 1m | daily: 2019-12-23 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2FindexPriceKlines%2FBTCUSDT%2F1m%2F&max-keys=2); `data/futures/um/daily/indexPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2019-12-23.zip` | 20,790 | 2023-07-07T06:39:05.000Z | U4 / C1 / M4 |
| Binance | USD-M PERP | BTCUSDT | indexPriceKlines 1m | monthly: 2020-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2FindexPriceKlines%2FBTCUSDT%2F1m%2F&max-keys=2); `data/futures/um/monthly/indexPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2020-01.zip` | 1,246,885 | 2021-03-29T13:19:06.000Z | U4 / C1 / M4 |
| Binance | USD-M PERP | BTCUSDT | premiumIndexKlines 1m | daily: 2019-12-24 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2FpremiumIndexKlines%2FBTCUSDT%2F1m%2F&max-keys=2); `data/futures/um/daily/premiumIndexKlines/BTCUSDT/1m/BTCUSDT-1m-2019-12-24.zip` | 14,666 | 2023-07-07T07:10:16.000Z | U5 / C1 / M4 |
| Binance | USD-M PERP | BTCUSDT | premiumIndexKlines 1m | monthly: 2020-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2FpremiumIndexKlines%2FBTCUSDT%2F1m%2F&max-keys=2); `data/futures/um/monthly/premiumIndexKlines/BTCUSDT/1m/BTCUSDT-1m-2020-01.zip` | 509,858 | 2021-03-29T13:44:52.000Z | U5 / C1 / M4 |
| Binance | USD-M PERP | BTCUSDT | fundingRate | monthly: 2020-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2FfundingRate%2FBTCUSDT%2F&max-keys=2); `data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2020-01.zip` | 825 | 2023-05-09T22:02:30.000Z | U6 / C3 / M5 |
| Binance | USD-M PERP | BTCUSDT | metrics | daily: 2020-09-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2Fmetrics%2FBTCUSDT%2F&max-keys=2); `data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2020-09-01.zip` | 12,191 | 2026-03-18T12:30:27.000Z | U7 / C4 / M6 |
| Binance | USD-M PERP | ETHUSDT | klines 1m | daily: 2019-12-31 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2Fklines%2FETHUSDT%2F1m%2F&max-keys=2); `data/futures/um/daily/klines/ETHUSDT/1m/ETHUSDT-1m-2019-12-31.zip` | 50,701 | 2022-03-21T09:09:59.000Z | U1 / C1 / M1 |
| Binance | USD-M PERP | ETHUSDT | klines 1m | monthly: 2020-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2Fklines%2FETHUSDT%2F1m%2F&max-keys=2); `data/futures/um/monthly/klines/ETHUSDT/1m/ETHUSDT-1m-2020-01.zip` | 1,606,210 | 2021-06-14T06:12:39.000Z | U1 / C1 / M1 |
| Binance | USD-M PERP | ETHUSDT | trades | daily: 2019-11-27 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2Ftrades%2FETHUSDT%2F&max-keys=2); `data/futures/um/daily/trades/ETHUSDT/ETHUSDT-trades-2019-11-27.zip` | 180,775 | 2022-03-04T23:44:26.000Z | U2 / C2 / M2 |
| Binance | USD-M PERP | ETHUSDT | trades | monthly: 2019-11 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2Ftrades%2FETHUSDT%2F&max-keys=2); `data/futures/um/monthly/trades/ETHUSDT/ETHUSDT-trades-2019-11.zip` | 1,470,226 | 2022-03-02T04:39:58.000Z | U2 / C2 / M2 |
| Binance | USD-M PERP | ETHUSDT | aggTrades | daily: 2019-12-31 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2FaggTrades%2FETHUSDT%2F&max-keys=2); `data/futures/um/daily/aggTrades/ETHUSDT/ETHUSDT-aggTrades-2019-12-31.zip` | 518,596 | 2022-03-03T23:08:18.000Z | U3 / C2 / M3 |
| Binance | USD-M PERP | ETHUSDT | aggTrades | monthly: 2020-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2FaggTrades%2FETHUSDT%2F&max-keys=2); `data/futures/um/monthly/aggTrades/ETHUSDT/ETHUSDT-aggTrades-2020-01.zip` | 24,840,055 | 2021-06-14T06:04:10.000Z | U3 / C2 / M3 |
| Binance | USD-M PERP | ETHUSDT | markPriceKlines 1m | daily: 2019-12-23 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2FmarkPriceKlines%2FETHUSDT%2F1m%2F&max-keys=2); `data/futures/um/daily/markPriceKlines/ETHUSDT/1m/ETHUSDT-1m-2019-12-23.zip` | 19,453 | 2023-07-07T06:39:13.000Z | U4 / C1 / M4 |
| Binance | USD-M PERP | ETHUSDT | markPriceKlines 1m | monthly: 2020-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2FmarkPriceKlines%2FETHUSDT%2F1m%2F&max-keys=2); `data/futures/um/monthly/markPriceKlines/ETHUSDT/1m/ETHUSDT-1m-2020-01.zip` | 1,182,821 | 2021-03-29T13:24:07.000Z | U4 / C1 / M4 |
| Binance | USD-M PERP | ETHUSDT | indexPriceKlines 1m | daily: 2019-12-23 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2FindexPriceKlines%2FETHUSDT%2F1m%2F&max-keys=2); `data/futures/um/daily/indexPriceKlines/ETHUSDT/1m/ETHUSDT-1m-2019-12-23.zip` | 15,868 | 2023-07-07T06:39:05.000Z | U4 / C1 / M4 |
| Binance | USD-M PERP | ETHUSDT | indexPriceKlines 1m | monthly: 2020-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2FindexPriceKlines%2FETHUSDT%2F1m%2F&max-keys=2); `data/futures/um/monthly/indexPriceKlines/ETHUSDT/1m/ETHUSDT-1m-2020-01.zip` | 965,891 | 2021-03-29T13:19:29.000Z | U4 / C1 / M4 |
| Binance | USD-M PERP | ETHUSDT | premiumIndexKlines 1m | daily: 2019-12-24 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2FpremiumIndexKlines%2FETHUSDT%2F1m%2F&max-keys=2); `data/futures/um/daily/premiumIndexKlines/ETHUSDT/1m/ETHUSDT-1m-2019-12-24.zip` | 14,487 | 2023-07-07T07:10:16.000Z | U5 / C1 / M4 |
| Binance | USD-M PERP | ETHUSDT | premiumIndexKlines 1m | monthly: 2020-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2FpremiumIndexKlines%2FETHUSDT%2F1m%2F&max-keys=2); `data/futures/um/monthly/premiumIndexKlines/ETHUSDT/1m/ETHUSDT-1m-2020-01.zip` | 510,421 | 2021-03-29T13:45:15.000Z | U5 / C1 / M4 |
| Binance | USD-M PERP | ETHUSDT | fundingRate | monthly: 2020-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fmonthly%2FfundingRate%2FETHUSDT%2F&max-keys=2); `data/futures/um/monthly/fundingRate/ETHUSDT/ETHUSDT-fundingRate-2020-01.zip` | 795 | 2023-05-09T22:02:43.000Z | U6 / C3 / M5 |
| Binance | USD-M PERP | ETHUSDT | metrics | daily: 2021-12-01 | [metadata](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data%2Ffutures%2Fum%2Fdaily%2Fmetrics%2FETHUSDT%2F&max-keys=2); `data/futures/um/daily/metrics/ETHUSDT/ETHUSDT-metrics-2021-12-01.zip` | 14,930 | 2023-06-16T11:35:54.000Z | U7 / C4 / M6 |

For history comparison, the following is a **22-dataset summary of the same forty observations**, not additional requests or a complete date inventory:

| Product | Instrument | Family | First returned daily filename date | First returned monthly filename month |
| --- | --- | --- | --- | --- |
| spot | BTCUSDT | klines | 2017-08-17 | 2017-08 |
| spot | BTCUSDT | trades | 2017-08-17 | 2017-08 |
| spot | BTCUSDT | aggTrades | 2017-08-17 | 2017-08 |
| spot | ETHUSDT | klines | 2017-08-17 | 2017-08 |
| spot | ETHUSDT | trades | 2017-08-17 | 2017-08 |
| spot | ETHUSDT | aggTrades | 2017-08-17 | 2017-08 |
| um | BTCUSDT | klines | 2019-12-31 | 2020-01 |
| um | BTCUSDT | trades | 2019-09-08 | 2019-09 |
| um | BTCUSDT | aggTrades | 2019-12-31 | 2020-01 |
| um | BTCUSDT | markPriceKlines | 2019-12-23 | 2020-01 |
| um | BTCUSDT | indexPriceKlines | 2019-12-23 | 2020-01 |
| um | BTCUSDT | premiumIndexKlines | 2019-12-24 | 2020-01 |
| um | BTCUSDT | fundingRate | no daily family observed | 2020-01 |
| um | BTCUSDT | metrics | 2020-09-01 | no monthly family observed |
| um | ETHUSDT | klines | 2019-12-31 | 2020-01 |
| um | ETHUSDT | trades | 2019-11-27 | 2019-11 |
| um | ETHUSDT | aggTrades | 2019-12-31 | 2020-01 |
| um | ETHUSDT | markPriceKlines | 2019-12-23 | 2020-01 |
| um | ETHUSDT | indexPriceKlines | 2019-12-23 | 2020-01 |
| um | ETHUSDT | premiumIndexKlines | 2019-12-24 | 2020-01 |
| um | ETHUSDT | fundingRate | no daily family observed | 2020-01 |
| um | ETHUSDT | metrics | 2021-12-01 | no monthly family observed |

The different start-name witnesses matter: Spot keys predate the helper's 2020 default; USD-M raw trades predate some kline/aggTrade witnesses; mark/index/premium witnesses differ from trade bars; BTC/ETH metrics witnesses differ. Latest keys, absent intervening dates and actual first/last event times were not enumerated. No claimed continuous coverage, complete sample size or shared product inception follows.

## 6. Historic owner inventory and nonduplicate reuse decision

**`LOCAL_INVENTORY_UNKNOWN`** applies to every historic observation. A neither restatted current disk nor opened any legacy copy. These are prior owner-reported facts quoted from the frozen plan, not measurements made for A:

| Historic receipt | Candidate reuse value | Unresolved witness / incremental implication |
| --- | --- | --- |
| 172.33 GiB Binance BTC research/forward | Potential overlap with future BTC intake | Scope, compression, provenance, dates and safe read-only locations unknown; not extra independent observations |
| 724 GiB free on about 1 TiB | Historical planning context | Not current free space, quota, safe capacity or authorization to consume it |
| 61 BTC Spot+USD-M aggTrades months, about 79.6 GiB compressed | Candidate Tier B reuse before considering new transfers | Product split, whether 61 is joint or per-product, exact months, checksums, archive vintage and continuity unknown; do not multiply counts or assume full tapes |
| 67 USD-M BTC 1m months | Candidate core bar reuse | Month names, missing days, overlaps and actual hashes unknown |
| 61 Spot BTC 1m months | Separate Spot bar reuse candidate | Not interchangeable with USD-M; 2025 us conversion and versions need verification |
| About 92 GiB forward microstructure | Historical existence statement only | Forward is excluded from A access/use; no original-receiver, clock or reusable-L2 certification inferred |
| ETH/BNB/ADA/LTC/XRP hourly series | Potential existing higher-timeframe context | **ETH hourly is not ETH 1m**, not raw ETH trades/OI/funding or a verified Vision archive. Other assets are outside A's requested BTC+ETH scope |
| Remote D1 BTC USD-M 2022-09-15..21 receipt | Preserve existing exact bar objects/digests as possible future narrow DEV-QA reuse | Local persistence unverified in A. No repeat download; metrics remain restricted; owner must separately authorize any future local reuse |

Do not add 79.6 GiB, 92 GiB and 172.33 GiB as disjoint totals. No new byte requirement, compressed-to-expanded ratio or BTC-to-ETH/Spot-to-perp extrapolation is established.

**Incremental needs are candidate manifest gaps, not confirmed absent files or permissions:**

1. Reconcile exact legacy BTC Spot/USD-M 1m and aggTrade partitions against official publisher identities under future named read-only grants. Prefer already matching digests; quarantine mismatches/revisions and preserve original vintages rather than overwrite or redownload blindly. Exclude monthly/daily duplicate UTC coverage.
2. Preserve the D1 seven-day bar witness without another intake. Resolve its partial metrics finding separately; no source schema/timing repair or imputation is authorized by A.
3. ETH 1m Spot/USD-M, ETH trades/aggTrades and reference bars are plausible additions because reported hourly data do not establish these families; local presence still unknown.
4. BTC/ETH mark/index/premium/funding and metrics may need new verified partitions, but existing-copy absence and sizes cannot be asserted. The first-party funding and metrics keys above establish a candidate path, not their actual economic contracts or complete history.
5. Full raw trades in addition to aggTrades require a named incremental scientific requirement; overlapping economic content is not independent sample expansion. Continuous L2, own fills and historical receiver timing remain separate gaps that neither tape supplies.

## 7. Finite Task D prerequisites — no dispatch

The co-committed DAG requires **A + C + the actual D1 receipt** before Controller can consider D. D1 is a PARTIAL_STOP, so a Controller-adjusted narrow purpose or explicit stop is necessary; a fictional D1 blanket PASS cannot be substituted. B proceeds independently and supplies E, not a reason to serialize or widen A. D/E precede independent F; G/H remain unauthorized.

Before a new D grant, obtain all of:

1. Frozen accepted A/C author SHAs and report blobs plus the actual D1 author/blob/status. Controller explicitly records the scope consequence of D1's partial metrics result.
2. A new exact owner-selected isolated workspace and named nonprotected read-only source roots, mutually exclusive with D1. No guessed path, reuse of prior broad authority, private/protected traversal or forward access.
3. A purpose/entity/jurisdiction-specific source-rights and retention/derivation decision under then-current terms. Any claimed PIT/rights acceptance needs independent 1 review; no inferred future LIVE right.
4. An exact product/instrument/family/UTC-partition manifest and current local-copy hash/coverage/vintage reconciliation to avoid duplicating D1 or legacy files. Exposed DEV remains distinct from protected/unexposed OOS; no protected-mask lookup in A.
5. Versioned archive schema, timestamp units, economic units and source-clock assumptions. Resolve missing metric columns or exclude them; preserve OI stock versus taker flow and original historical first-known as unknown absent proof.
6. C's measured capacity/disk/quota/temporary-space evidence and safe floor, with every unmeasured field NULL. The plan's default floor is max(100 GiB, 25% verified filesystem capacity), not permission to spend historical free space.
7. A **new** explicit exact-file/date/host/compressed/expanded/retained-byte/request/concurrency/retry/USD cap, outcome-blind sample selection, and fresh approved rights check. C's at-most-three representative partitions per family/instrument/venue is a future sampling constraint, not A download authority.
8. A reviewed integrity/idempotence/quarantine plan and synthetic negatives for hash, ZIP safety, time-unit/label shifts, gaps/duplicates, wrong instrument, budget and disk failure; originals remain local, only sanitized evidence published.
9. Controller's explicit D authorization and subsequent independent consequential audit. No strategy scoring, Alpha, private exchange/account operation, TESTNET/LIVE, funds write or automatic E/F/G/H action is bundled.

## 8. Verification and limitations

Actual A checks performed: complete frozen prompt and plan/DAG reads; exact dispatch-parent and prompt-blob checks; D1 remote head/parent/report-blob/diff and failing hosted-CI step checks; provider frozen docs/terms/current-head checks; official directory endpoint provenance; two untruncated family-root listings; forty capped object listings; consistency checks for forty exact ZIP/checksum-name pairs, twenty-two logical datasets and all four product/instrument combinations; report-only remote Git tree/diff verification on publication.

**No new source-QC, synthetic test suite, pytest, backtest, strategy or benchmark was run by A.** D1 tests are reported only as D1's remote evidence. For this docs-only addition, proportional validation is frozen identity, metadata matrix consistency, content-boundary checks and the exact one-file Git diff. Existing CI policy is unchanged and will run on the published docs path; actual status/run URL is returned in the final execution receipt, never presumed green. No unrelated H41 lint/CI fix is permitted.

Limits: all forty catalogs are truncated; coverage/corrections and schema need later authorized verification; listing sizes are not measured payload storage; private copies and current disk are unknown; archive checksum contents were not read; no original historical receiver timing, costs, own fills or legal/source acceptance is established. This is a documentary Task A completion with limits, not `SOURCE_ADMITTED`.

**Preserved:** `R9_L1_PAUSE_NEW_ALPHA_RESEARCH_PENDING_EXTERNAL_SOURCE_EVIDENCE / SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.
