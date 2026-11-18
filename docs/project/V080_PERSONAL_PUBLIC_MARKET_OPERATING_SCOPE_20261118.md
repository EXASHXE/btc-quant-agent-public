# QUANT v0.8.0 — One-Time PUBLIC_MARKET Operating Scope

Status: TEMPLATE / NOT ACTIVE. This is a local runtime configuration boundary, not a new rights attestation, legal opinion or per-request approval.

## Purpose

The Owner's existing OWNER_STANDING_M2_AUTHORIZATION_20261024.md remains reusable as OWNER_ATTESTED for the same personal, noncommercial, private/local, read-only public-market-data scope. Do not ask the Owner to repeat it.

Before the first live Layer 1 scan, create and review one bounded PERSONAL_PUBLIC_MARKET operating scope. Once active, repeated public GET requests inside that exact scope do not require per-request consent.

## Scope fields

The local scope configuration records:
- product mode PERSONAL_MVP and Layer 1 PUBLIC_MARKET only;
- initial symbols BTCUSDT, ETHUSDT and SOLUSDT;
- allowed public GET endpoint families and timeframes;
- request cadence and dynamic weight budget;
- local storage and Owner-controlled retention;
- current operating region and approved network route, without proxy/region circumvention;
- clock/freshness policy and stop conditions.

The configuration is a technical control. It does not replace the existing Owner attestation and does not claim third-party legal certification.

## Activation sequence

1. R1 code and offline tests are independently accepted by Controller 0-C.
2. Controller 0-C reviews the template, endpoint matrix and current Binance documentation.
3. Owner/Controller complete the local scope values once.
4. The scope is marked ACTIVE for the defined symbols, endpoints, cadence and local retention.
5. No repeated per-request approval is required while requests remain inside the active scope.
6. A material change to purpose, region, route, symbols beyond the approved universe, endpoint families, data sharing or commercial use requires a scope review.

## Stop conditions

Stop the affected scan and surface a clear status on:
- HTTP 418 or an explicit IP ban;
- HTTP 429 until Retry-After/backoff has elapsed;
- HTTP 403/451 or explicit regional/permission restriction;
- TLS hostname/certificate failure;
- malformed or conflicting market data;
- unreconciled venue-time offset or stale data beyond configured thresholds;
- any unexpected endpoint, non-GET method or request outside the approved symbol/interval scope.

No proxy rotation, alternate-region fallback, DNS manipulation or access-control bypass.

## Layer separation

This operating scope is only for PUBLIC_MARKET. It does not activate PRIVATE_USER_DATA or TRADE_EXECUTION. Layer 2 requires its own local read-only key and permission check after R1 acceptance. Layer 3 remains disabled.
