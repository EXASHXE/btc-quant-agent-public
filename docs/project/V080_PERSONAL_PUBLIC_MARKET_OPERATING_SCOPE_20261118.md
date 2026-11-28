# QUANT v0.8.0 — One-Time PUBLIC_MARKET Operating Scope

> **Current navigation (2026-11-28):** [Wave D checkpoint](V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../prompts/v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../prompts/v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.


> Current 2026-11-28 status: Use [Wave D checkpoint](V100_WAVED_ACTIVE_CHECKPOINT_20261128.md), [current roadmap](V100_WAVED_ROADMAP_20261128.md), [Sol WEB bootstrap](../prompts/v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) and [Neon WEB bootstrap](../prompts/v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md) for current state. Wave C closed per Controller handoff; S7 empirical Run 2 completed and scoped accepted, 0/6 advancement; QRKP R4/R7 Rev02 sealed. Product development base 03af5397; S7 research base 3baa0ebb. Owner dispatched D1/D2/D3, original runs delivered; D2 remediation active, joint QA pending. Runtime proof/Field/recurrence not enabled, Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Do not redispatch. Historical sections below are retained, not current gate instructions.


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
