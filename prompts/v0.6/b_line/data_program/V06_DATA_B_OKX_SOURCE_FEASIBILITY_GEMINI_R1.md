# Wave 1 / B — OKX Official BTC+ETH Spot+USDT-SWAP Source and Rights Feasibility R1

**Task:** `V06_DATA_B_OKX`. **READY_PARALLEL** with A and C; no dependencies on the active R10-D1. **Executor:** a separate Gemini NORMAL local session (Codex acceptable), no other parallel writes to its branch. **Reviewer:** Controller 0; independent 1 for material license and PIT questions. **Budget:** $0. **Only read official public pages/index metadata; NO archives, market APIs, keys, trial or local private data.** Verify immutable Controller dispatch SHA, parent, THIS blob and linked plan/DAG.

## Primary official evidence

- [OKX historical data portal](https://www.okx.com/historical-data): landing page currently advertises venue-wide trade tick records from Sep 2021, candles from Jul 2023, funding from Mar 2022, L2 order books from Mar 2023, borrowing from Dec 2021. These are **portal-wide availability claims, not per-product availability or entitlement**.
- [Official OKX V5 API documentation](https://www.okx.com/docs-v5/en/): last-3-month public `market/history-trades`, `market/history-candles`, `public/funding-rate-history`, `public/open-interest`, `public/market-data-history`, instrument metadata, and the appropriate market/orderbook APIs; determine present limits/field units from relevant pages rather than guessing.
- [OKX official SDK public endpoint constants](https://github.com/okxapi/python-okx/blob/master/okx/consts.py) are supporting developer docs only and do not by themselves prove historical coverage or legal authority.
- Research permission, downloading, retention, derivatives, API limits, geography, downstream later proprietary trade strategy use must be separated and quoted from official controlling **current** OKX terms if available; if not, `RIGHTS_UNRESOLVED` not an invented grant.

## Scope of investigation

For each `BTC-USDT`, `ETH-USDT` (SPOT) and `BTC-USDT-SWAP`, `ETH-USDT-SWAP` (USDT-margined perpetual), tabulate actual source portal family/file/index/coverage, time granularity, funding settlement interval/currency, contract multiplier/min trade unit, mark/index/premium, OI history, order-book L2 snapshot/delta original event availability and depth. Distinguish archive vs REST endpoint, current/near-history versus downloadable long history, and only claim `AVAILABLE_VERIFIED` if a specific official object/listing is independently observed. Venue-wide earliest date may be `AVAILABLE_UNMEASURED` or `COVERAGE_UNKNOWN` for a given contract.

Check timestamp fields `ts` and where applicable `uTime`/sequence/contract-value fields, whether time units are ms, exchange event/publisher timestamp or historical first-known-at; identify UTC vs UTC+8 partitions before future join. If only orderbook 5,000 level snapshots from a later date are documented, do not relabel earlier records as identical full L2. Funding API with historical fields is not complete continuous account cash ledger; `public/open-interest` current snapshot is not multi-year historical OI unless first-party evidence specifically proves one.

Create potential future single-file pilot menu with `file_family+symbol+legal right+tested checksum+estimated bytes` but **NO DOWNLOAD** and do not invent explicit approved dates/checksums. Use an explicit source-rights/PIT/cost gap list and lower-bound storage classes to inform C. No trading, strategy backtest, or private user path access.

## Deliverable

New isolated branch `docs/v06-data-b-okx-source-feasibility-r1`, rooted directly in frozen Controller dispatch; ADD ONLY `docs/project/V06_DATA_B_OKX_SOURCE_RIGHTS_AND_COVERAGE_R1.md`. Include matrix, exact official URLs/access date/version where possible, one evidence table per product, license/technical caveats, possible E gating and terminal `B_DOCUMENTARY_READY_WITH_LIMITS` or `B_RIGHTS_PRODUCT_STOP`. Report exact author commit, parent SHA, blob, path diff, branch HEAD, actual CI. Do not self-authorize E or data purchases. Keep R9 source/Alpha and TESTNET/LIVE NO_GO.
