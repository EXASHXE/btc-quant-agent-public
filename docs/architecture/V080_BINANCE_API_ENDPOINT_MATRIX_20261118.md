# QUANT v0.8.0 — Binance USDⓈ-M Endpoint and Permission Matrix

Reference date: 2026-11-18. Verify current endpoint weights and response schemas before implementation; exchange APIs can change.

## Layer 1 — PUBLIC_MARKET

| Method | Endpoint | Data | Notes |
|---|---|---|---|
| GET | /fapi/v1/time | Venue server time | Offset/freshness bracket |
| GET | /fapi/v1/exchangeInfo | Symbols, filters, rate limits | Verify PERPETUAL, USDT margin/quote, TRADING |
| GET | /fapi/v1/klines | 1D/4H/1H/15m/5m OHLCV | Completed bars only for confirmation |
| GET | /fapi/v1/ticker/24hr | 24h turnover and price change | 1 weight per symbol; all symbols cost more |
| GET | /fapi/v1/ticker/bookTicker | Best bid/ask | RPI not included |
| GET | /fapi/v1/depth | Normal order book | RPI orders excluded; depth weight depends on limit |
| GET | /fapi/v1/rpiDepth | RPI order book | Optional; separate semantics |
| GET | /fapi/v1/openInterest | Current OI | Symbol-scoped |
| GET | /futures/data/openInterestHist | Historical OI | Latest one month only |
| GET | /fapi/v1/fundingRate | Funding history | Persist forward |
| GET | /fapi/v1/premiumIndex | Mark/index price and current funding | Mark-price context |
| GET | /fapi/v1/aggTrades | Recent aggregate trades | Optional taker-flow context |

## Layer 2 — PRIVATE_USER_DATA

All listed endpoints are signed USER_DATA requests. They are not called in R1.

| Method | Endpoint | Data | Important limitation |
|---|---|---|---|
| GET | /fapi/v3/account | Account balances and margin state | Snapshot as-of time required |
| GET | /fapi/v3/positionRisk | Position risk | V3 returns symbols with position or open orders |
| GET | /fapi/v1/openOrders | Current ordinary open orders | All-symbol call is more expensive |
| GET | /fapi/v1/openAlgoOrders | Current TP/SL/trailing conditional orders | All-symbol call can cost 40 weight; symbol call is cheaper |
| GET | /fapi/v1/userTrades | Fills | Symbol required; time range max 7 days; no unlimited history assumption |
| GET | /fapi/v1/allOrders | Ordinary order history | 90-day availability; canceled/expired unfilled orders may disappear after 3 days; query windows under 7 days |
| GET | /fapi/v1/allAlgoOrders | Conditional order history | 90-day availability; canceled/expired unfilled orders may disappear after 3 days; query windows under 7 days |
| GET | /fapi/v1/income | Realized PnL, commission, funding and other income | Last 3 months only; default recent 7 days; weight 30 |
| GET | /fapi/v1/commissionRate | Account-specific commission rate | Optional; verify current permission and weight |
| GET | /fapi/v1/accountConfig | Account configuration | Optional; verify current schema |
| GET | /fapi/v1/positionSide/dual | Hedge/One-way mode | Optional if not derivable safely |
| GET | /fapi/v1/multiAssetsMargin | Multi-Assets mode | Optional if relevant |
| GET | /sapi/v1/account/apiRestrictions | API key permission flags | Optional permission introspection; SAPI scope |

## History and polling constraints

- userTrades: current USD-M documentation requires a symbol and limits the requested time interval to 7 days. The docs do not establish a safe unlimited backfill promise. Persist forward and use fromId/time-window pagination as supported.
- income: only the latest 3 months; default query is the latest 7 days; request weight is 30. Keep calls incremental and avoid frequent full backfills.
- allOrders and allAlgoOrders: records are not returned beyond 90 days; canceled/expired orders with no fills may disappear after 3 days. Query intervals must be less than 7 days.
- openOrders and openAlgoOrders: current open orders only. Do not use them as order history.
- OI history: latest one month only.
- Start local durable forward capture immediately after Layer 2 is configured and accepted.

## API key permission rule

Binance documents Enable Reading as GET-only. API restrictions also expose a separate enableFutures field. The exact key-scope combination needed to call Futures USER_DATA must be tested against current official documentation and the Owner's current key UI without widening to a TRADE-capable permission.

Fail closed: if Enable Reading alone cannot call Futures USER_DATA, and the only apparent workaround requires enabling a Futures permission whose trade capability is not proven read-only, keep Layer 2 disconnected. Do not enable that permission.

## Official references

- Binance USDⓈ-M Futures REST API — Trade: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade
- Binance USDⓈ-M Futures REST API — Market Data: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data
- Binance API Key FAQ: https://www.binance.com/en/support/faq/detail/360002502072
- Binance Account API Restrictions: https://developers.binance.com/en/docs/catalog/core-trading-wallet/api/rest-api/account
- Binance Get Income History: https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Income-History

[executed on device: hyz-laptop (bfc916f4-e88a-469a-9999-cf08962f68ed)]