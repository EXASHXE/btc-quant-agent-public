# METHOD_REPAIR_R1: source and licence admission R1.1

Known-source lead narrowed: official `binance/binance-public-data@f446ce3812bd4e5521f21faecd4ae3c6460e49fc` establishes monthly markPriceKlines path assembly. [Python README](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/python/README.md), [downloader](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/python/download-futures-markPriceKlines.py), [utility](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/python/utility.py), [enums](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/python/enums.py) were fetched/hash-recorded as static technical source; none was imported or executed. Defaults can scan all symbols/daily history; they are expressly NOT adopted. Construct only `https://data.binance.vision/data/futures/um/monthly/markPriceKlines/<SYMBOL>/1m/<SYMBOL>-1m-2026-<MM>.zip` for BTCUSDT/ETHUSDT/SOLUSDT and01..04.

## Actual metadata versus unknown bodies

All12 exact ZIP paths returned HEAD200/FOUND_OBJECT_METADATA. Last-Modified,ETag,Content-Length,UTC and final host are in MARK_ARCHIVE_METADATA_HEAD_LEDGER.json; no redirects,17 operations total,30,785 static-doc body bytes. HEAD body bytes0; no ZIP/CSV/range GET/decoder or funding-rate history. Optional checksum GET was not used, so expected archive SHA256 and body integrity are not verified. ETag is not treated as SHA256; server Last-Modified is not historic receipt or guaranteed publication.

Every month coverage is **NOT_ASSESSED**, not complete or potentially verified candles. Schema, actual UTC rows, missingness/duplicates, symbol/contract contents, close timing and alignment to trade/funding feeds must be independently checked only after a separately pushed preregistration and body-admission authority. Current object metadata may reflect later revisions. A future permitted download must bind expected official checksum, raw ZIP/CSV hashes and retrieval/available assumptions, fail on any active path gap, and never fill1m outcomes.

| Source | Admission / limitation before future replay |
|---|---|
| TradeK1m | Exact three-symbol USDT-M perpetual product and constant Jan–Apr window required; no trade archive HEAD/body here. Identity/schema/hash/continuity still open. No spot substitution. |
| Mark1m | Official path closed for design;12 object HEADs found. Actual continuous body quality completely unassessed. Cannot borrow trade close for MTM. |
| Symbol filters | Current explicit-symbol metadata and historical effective PRICE_FILTER/LOT_SIZE/MARKET_LOT_SIZE/minimum notional open; all-symbol exchangeInfo unsupported. A declared dated proxy is diagnostic only. |
| Fee schedule | Applicable regular-user current/2026 fee unknown; no private probe.6/12bp model assumptions unchanged. |
| Funding/mark cashflow | Calculation/publication/settlement/caps/interval ownership open;4/8bp is scenario only. Minute mark source existence does not identify payment mark or schedule. |
| Public receipt lag |60s bar/mark and acknowledgment lags are explicit reconstruction assumptions; zero original receipt proof. Future live receipt proof requires separate authority/source clock evidence. |
| Spread/slip |2/3bp and4/6bp per leg proxies; no depth/queue/fill source, no maker grid. |
| Licence/redistribution | Current bounded metadata audit only. Future dataset/derived-row permissions remain conditional; raw ZIP redistribution prohibited by this task. Commercial/live use not established. |

## Terms and scope

Licence status: **NONCOMMERCIAL_RESEARCH_SUITABILITY_UNDER_REVIEW**. [Current issuer dataset terms](https://raw.githubusercontent.com/binance/binance-public-data/master/TERMS_AND_CONDITIONS.md) were retrieved after pinned source files, version1.0/updated2026-08-26. They distinguish noncommercial research, attribution/share-alike redistribution conditions and separate commercial permission; repository-code MIT does not settle dataset rights. This is a recorded issuer claim and scoped assessment, not a legal guarantee or retroactive judgement of prior downloads.

Present task exercises only noncommercial specification/object-metadata feasibility and publishes no raw prices. No downstream compensated service or live execution is exercised or approved. Before any future body admission/derived-row publication, Controller must record stated research use, applicable terms/version, attribution to Binance Vision and compatible publication rights. For intended commercial/live use without established permission, stop data transfer; never silently reuse these URLs/licences. No source route for raw redistribution is authorized. Dataset rights are separate from code acceptance and trading authority.

## Resource decision

Twelve known monthly mark ZIPs could replace hundreds of hypothetical REST pages; HEAD lengths sum is recorded in the ledger, not bytes downloaded. This checks a mark component estimate only, not compression/schema/other feeds or whole-pipeline affordability. Future1GB compressed/250-request ceiling must be rechecked prospectively for price+mark+checksums+funding/filter/terms/redirects/retries. Use declared worst-case ceilings and stop on429/403/geo/unknown host; never enlarge responses or substitute symbols/months after outcomes. If objects later disappear/change, publish missingness and retire/block the route, not unbounded discovery.

Current collection budget40 operations/1MB allowed metadata; actual17/30,785 body bytes plus separately counted retained headers. Git ref/publication transport is separately authorized and wire traffic is not instrumented. HEAD Content-Length is object size, not fetched bytes. Default TLS verification, no proxy switching/recovery/credentials, no all-symbol/bucket listing, no archive checksum/price body. Licensing and source admission stay conditional even though all objects were found.
