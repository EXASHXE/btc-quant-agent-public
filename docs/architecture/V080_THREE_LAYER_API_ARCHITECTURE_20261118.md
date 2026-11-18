# QUANT v0.8.0 — Three-Layer Binance API Architecture

Version: 1.0 · Date: 2026-11-18
Product mode: PERSONAL_MVP · Holding horizon: 2–12h · Execution: Human only

## 1. Architecture decision

Separate data access by capability and credential boundary:
- PUBLIC_MARKET: anonymous public market data.
- PRIVATE_USER_DATA: signed account reads with a dedicated read-only key.
- TRADE_EXECUTION: disabled, no credential, no client and no reachable route.

Use independent clients, configuration, storage and evidence labels. A shared low-level HTTP transport may be reused only if method/path allowlists and the credential boundary remain independently enforced. The private signer must never be available to the public client.

## 2. Layer 1 — PUBLIC_MARKET

Credential: none.
Evidence class: PERSONAL_PUBLIC_MARKET.
Initial symbols: BTCUSDT, ETHUSDT, SOLUSDT.
Later candidates: ZEC, HYPE, INJ, ARB, ARIA, ERA, AAVE, INIT and other liquid USDT-M perpetuals.

Required public data:
- Contract metadata and filters: /fapi/v1/exchangeInfo.
- Venue time: /fapi/v1/time.
- OHLCV: /fapi/v1/klines, intervals 1d, 4h, 1h, 15m, 5m.
- 24h ticker: /fapi/v1/ticker/24hr.
- Best bid/ask: /fapi/v1/ticker/bookTicker.
- Depth: /fapi/v1/depth.
- Optional RPI book: /fapi/v1/rpiDepth; keep it as a separate liquidity observation, not silently merged with normal depth.
- Current OI: /fapi/v1/openInterest.
- Historical OI: /futures/data/openInterestHist.
- Funding history: /fapi/v1/fundingRate.
- Mark price / current funding: /fapi/v1/premiumIndex.
- Optional recent trade flow: /fapi/v1/aggTrades.

REST is the initial bootstrap and MVP path. Public WebSocket streams may be added later for efficiency; they are not required for R1.

### Five-timeframe contract

1D background → 4H regime → 1H setup → 15m trigger → 5m actionability.

Only completed candles may confirm setup/trigger. Forming candles are context only and must be explicitly labeled. Kline closeTime is inclusive; normalize to an exclusive end boundary (closeTime + 1). Preserve source open/close times, local request/receive times, raw response hash, gaps, duplicates, revisions and freshness. If REST does not provide source publication time, keep it UNKNOWN; do not relabel local receipt time as exchange publication time.

### Public market quality

- Validate exchangeInfo: symbol, contractType=PERPETUAL, quoteAsset=USDT, marginAsset=USDT, status=TRADING, tick size, step size, minimum quantity/notional and other filters.
- Parse exchange numeric strings with Decimal; do not use binary float for price/quantity/fee calculations.
- Book spread and depth are time-sensitive snapshots, not a complete execution guarantee.
- Standard /fapi/v1/depth excludes RPI orders. /fapi/v1/rpiDepth is optional and has different aggregation/visibility semantics.
- OI history only exposes the latest one month; persist forward if longer history is needed.
- Query selected symbols rather than repeatedly pulling all symbols. Account for per-endpoint weights and response headers.

## 3. Layer 2 — PRIVATE_USER_DATA

Credential: separate Owner-created read-only key; never shared with Layer 1.
Evidence class: PERSONAL_PRIVATE_ACCOUNT.
Transport: signed GET only.

Core endpoint allowlist:
- GET /fapi/v3/account
- GET /fapi/v3/positionRisk
- GET /fapi/v1/openOrders
- GET /fapi/v1/openAlgoOrders
- GET /fapi/v1/userTrades
- GET /fapi/v1/allOrders
- GET /fapi/v1/allAlgoOrders
- GET /fapi/v1/income

Optional read-only endpoints after documentation and weight review:
- GET /fapi/v1/commissionRate
- GET /fapi/v1/accountConfig
- GET /fapi/v1/positionSide/dual
- GET /fapi/v1/multiAssetsMargin
- GET /sapi/v1/account/apiRestrictions for permission introspection, only if supported by the chosen read-only key.

### Conditional orders are first-class account state

/openOrders is not enough. Current TP/SL and trailing conditional orders must also be read from /fapi/v1/openAlgoOrders; historical conditional order lifecycle comes from /fapi/v1/allAlgoOrders.

Normalize at least algoId, clientAlgoId, algoType, orderType, algoStatus, symbol, side, positionSide, quantity, triggerPrice, price, workingType, closePosition, reduceOnly, createTime, updateTime and trigger state. Preserve raw fields and unknown enum values.

The all-symbol current-order query can be materially more expensive than a per-symbol query. Use symbol-scoped requests where possible; do not poll all symbols at high frequency.

### Position and account normalization

Read actual:
- position amount, side/positionSide, entryPrice, breakEvenPrice, markPrice, unrealized PnL, liquidation price, leverage, margin type, isolated margin and notional where returned;
- account balances, wallet/margin balance, available balance and total unrealized PnL;
- ordinary open orders and conditional TP/SL/algo orders;
- fills, realized PnL, commissions, funding fees and other income rows.

positionRisk V3 may return only symbols with a position or open order. Do not infer that omitted symbols have a zero position without checking the endpoint contract and account snapshot.

### Key permissions and hard stop

Start with Enable Reading only. Binance describes this as GET-only access. Binance also exposes a separate enableFutures permission flag in API restrictions. The exact current permission combination needed for USD-M Futures USER_DATA must be proven without enabling a TRADE-capable permission.

If read-only permission cannot access the required Futures USER_DATA endpoints, stop and keep Layer 2 DISCONNECTED. Do not enable Futures/TRADE, spot/margin trade, withdrawals or transfer permissions as a workaround. No credential is requested from the Owner during engineering; the Owner configures it locally after offline acceptance.

### Signed GET and credential handling

- Use a dedicated local credential-store reference; do not store secret material in repository files, .env, task prompts or logs.
- Sign locally; redact API key, signature and full signed query from all diagnostics.
- Use a venue-time offset bracketed by Layer 1 /fapi/v1/time; initial recvWindow 5000ms, configurable within Binance's documented limit.
- Enforce exact method=GET and exact endpoint allowlist in the transport immediately before sending.
- POST/PUT/DELETE must fail closed before any transport call.
- Do not start private user-data WebSocket streams in the current GET-only layer because listenKey lifecycle uses non-GET control calls. REST polling is the initial scope.

## 4. Layer 3 — TRADE_EXECUTION

Disabled and absent from the personal MVP:
- no trading API key;
- no new order, cancel, amend, close, leverage, margin, transfer or withdrawal client;
- no POST/PUT/DELETE path;
- no execution scheduler or background order worker.

Static tests must prove forbidden methods and routes are unreachable from both read-only clients. A future execution feature requires a separate Owner decision, new design, new credentials and new risk review; it is not an automatic phase after R6.

## 5. Personal time, rate and cache policy

- Use normal OS time synchronization for local wall time.
- Use monotonic time for elapsed durations and local causal ordering.
- Bracket /fapi/v1/time requests and calculate venue/local offset plus uncertainty.
- Use exchange candle timestamps for bar identity and a configurable close grace/freshness policy.
- Do not impose independent NTS, hardware witness or unconditional 50ms wall/monotonic rejection on PERSONAL_MVP.
- If a run's venue offset cannot be reconciled, quarantine that run and reacquire; do not permanently block the whole application.
- Keep Strict Research's original clock rules unchanged.
- Build a versioned endpoint-weight table from current official docs; combine it with exchangeInfo rate-limit ceilings and response headers. Do not retain 24 requests / 40 weight / 120 seconds as permanent product ceilings.
- Respect 429 and Retry-After; stop/back off on 418. At most one bounded retry for clearly transient idempotent GET failures. Never retry permission denial, malformed data, or an explicit venue/region restriction.
- Cache candles incrementally; refresh 15m/5m and quote context when a candidate approaches its entry zone. Before a human acts 5–10 minutes after a notification, refresh price/book/mark/funding and recompute entry, hard SL, TP1/2/3, fee, spread, slippage, net R and first 4H/1D obstacle.

## 6. Storage and privacy

Use separate local stores or strict schema/ACL separation:
- public market store: bars, ticker, book, OI, funding, mark and provenance;
- private account store: account snapshots, positions, orders, fills, income and reconciliation state.

Private data is local-only by default. Apply restrictive OS ACLs and full-disk/backup encryption where available. Do not put private account payloads into Git, Controller handoffs, cloud uploads or Feishu. The Owner controls retention; no mandatory 24-hour purge. Keep idempotent persistence, deduplication and backup/restore tests. Do not claim production durability beyond tests actually performed.

## 7. Strategy/account output contract

Keep market setup and account context as separate dimensions:
- market_setup_status: EXECUTABLE, WATCH, INVALID, NO_SETUP, SOURCE_BLOCKED.
- account_context_status: CONNECTED, UNAVAILABLE, STALE, PARTIAL.
- human_actionability: explicit reason, including manual account check when context is unavailable.

When Layer 2 is unavailable, public market analysis continues, but the system must not imply that existing exposure, conflicting positions or existing TP/SL have been checked. No order is sent.

When Layer 2 is connected, match fills to signal episodes using symbol, side/positionSide, timestamps, quantity, order/trade IDs and price proximity. Preserve MATCHED, PROBABLE_MATCH, UNMATCHED and AMBIGUOUS; never force a match.

## 8. Accounting contract

- userTrades is fill-level evidence: price, quantity, side, realizedPnl, commission, commissionAsset, orderId, tradeId and time.
- income is the account cash-flow ledger: REALIZED_PNL, FUNDING_FEE, COMMISSION and other income types.
- Use a single canonical accounting treatment and reconcile the other endpoint as a cross-check; never add trade-level commission and income commission twice.
- Parse Decimal strings exactly and deduplicate with exchange IDs (tranId, trade ID, order ID and symbol-scoped sequence as appropriate).
- Multi-endpoint snapshots are NON_ATOMIC; record each response's request time, receive time, server-time estimate and data age.
- If a page or time window is missing, label history PARTIAL; never fill gaps with synthetic values.

## 9. Research separation

Personal evidence does not qualify Strict Source/E1, strict Shadow, protected historical data or economic validation. Preserve all old protected/holdout exclusions. Personal forward evaluation is a separate ledger and cannot be used to claim Alpha without a later explicit methodology and evidence review.
