# DRAFT TASK — QUANT v0.8.0 | R2 PRIVATE_USER_DATA

> **Current navigation (2026-11-28):** [Wave D checkpoint](../../project/V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](../../project/V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.

## V080-SOL62-PERSONAL-MVP-LAYER2-USER-DATA-01

- **Executor:** GPT-6.2 Sol
- **Architecture review:** GPT-6.2 Astra
- **Mechanical QA:** Gemini 4 Hydrogen
- **Independent acceptance:** Controller 0-C
- **Status:** DRAFT ONLY — DO NOT START UNTIL R1 IS INDEPENDENTLY ACCEPTED
- **Project root:** /root/workspace/project/quant-0.8.0/
- **Canonical documentation branch:** docs/engineering (sole project-document authority)
- **Executable code/runtime branch:** v0.8.0
- **Documentation write rule:** Do not commit canonical project docs, role docs, roadmaps, task cards or handoffs to v0.8.0. Keep implementation/test evidence in the approved local work root; publish canonical documentation updates on docs/engineering.
- **Target work root:** workspaces/lt-v080-sol62-personal-mvp-layer2-user-data-01/

## 1. Mission

Implement a separate Binance USDⓈ-M PRIVATE_USER_DATA client that reads actual account balances, positions, ordinary orders, conditional TP/SL orders, fills, order history and income. The layer is optional and local-only. It must not block Layer 1 PUBLIC_MARKET if unavailable.

This task is deliberately sequenced after R1 acceptance. This draft is an architecture/implementation contract, not a dispatch.

## 2. Read-first and baseline

Read the project home, Owner rebaseline decision, three-layer architecture, endpoint matrix, roadmap, role matrix and prompt copy standard from the canonical docs/engineering branch. Read the accepted R1 handoff, source code and Program J manifest from the local v0.8.0 workspace. Use only the accepted source baseline and create a new isolated work root. Do not modify baseline/program-j/ or historical v0.7.0 files. Canonical project-document changes must be published on docs/engineering, not v0.8.0.

Do not request, read or configure the Owner's real API key during engineering. Use fake keys and deterministic mock transport only.

## 3. Required signed GET endpoint allowlist

Core:
- GET /fapi/v3/account
- GET /fapi/v3/positionRisk
- GET /fapi/v1/openOrders
- GET /fapi/v1/openAlgoOrders
- GET /fapi/v1/userTrades
- GET /fapi/v1/allOrders
- GET /fapi/v1/allAlgoOrders
- GET /fapi/v1/income

Optional only after documentation/weight review:
- GET /fapi/v1/commissionRate
- GET /fapi/v1/accountConfig
- GET /fapi/v1/positionSide/dual
- GET /fapi/v1/multiAssetsMargin
- GET /sapi/v1/account/apiRestrictions

No endpoint outside the explicit allowlist. Exact path and method must be checked at the final transport boundary.

## 4. Critical API Key permission gate

The Owner's requirement is an independent read-only API key with Enable Reading only. Binance describes Enable Reading as GET-only and exposes enableFutures as a separate permission field.

Before any live configuration, verify the exact current Binance permission semantics. If Futures USER_DATA requires enabling a Futures permission whose TRADE implications are not proven read-only, stop and leave Layer 2 DISCONNECTED. Do not enable Futures, spot/margin trading, withdrawals, internal transfer or any mutation permission to make the request work.

The implementation must support this fail-closed outcome. A 401/403/-2015/permission error must not trigger permission escalation or fallback credentials.

The Owner creates the key locally after offline acceptance. Secret material belongs only in OS credential storage / DPAPI / keyring or an equivalent local secret manager. No plaintext secret in repository, .env, task prompts, shell history, process arguments, logs or handoffs.

## 5. Signer and transport requirements

- Sign locally using the chosen Binance-supported key type.
- Read credential material only through an injected local secret-provider interface.
- Keep the signer in the PRIVATE_USER_DATA package; PUBLIC_MARKET cannot import or access it.
- Exact GET-only method allowlist enforced immediately before transport.
- POST/PUT/DELETE rejected before network.
- Redact API key, signature, signed query, recvWindow and private payloads from logs.
- Use the Layer 1 venue-time offset estimate for timestamp signing; configurable recvWindow, default 5000ms.
- Timestamp errors may trigger one bounded server-time resync; no unbounded retries.
- TLS certificate and hostname validation mandatory.
- No direct/proxy fallback or region bypass.

Do not implement private user-data WebSocket streams in this phase. ListenKey lifecycle uses non-GET control calls, which conflicts with the strict GET-only Layer 2 boundary. Use REST polling.

## 6. Account and position model

Normalize:
- account balances, walletBalance, availableBalance, marginBalance and totalUnrealizedProfit where returned;
- positionAmt, positionSide, entryPrice, breakEvenPrice, markPrice, unRealizedProfit, liquidationPrice, leverage, marginType, isolatedMargin and notional where returned;
- One-way/Hedge semantics and BOTH/LONG/SHORT;
- updateTime and per-response as-of timestamp.

Do not infer zero exposure from a missing positionRisk row without following the current endpoint contract. Treat multi-endpoint account snapshots as NON_ATOMIC and expose data age.

## 7. Orders and TP/SL

Read ordinary open orders from /fapi/v1/openOrders and current conditional TP/SL/trailing orders from /fapi/v1/openAlgoOrders. Both are required; openOrders alone is incomplete.

Historical ordinary orders come from /fapi/v1/allOrders; conditional history comes from /fapi/v1/allAlgoOrders.

Normalize and preserve raw:
- symbol, orderId/algoId, clientOrderId/clientAlgoId;
- side, positionSide, type/orderType, status/algoStatus;
- origQty, executedQty, price, stopPrice/triggerPrice;
- workingType, closePosition, reduceOnly, timeInForce;
- create/update/trigger times and trigger result.

Keep unknown fields and enum values. Do not infer a protective TP/SL from a normal order unless its semantics prove it.

## 8. History limits and forward persistence

- userTrades: symbol-scoped; requested startTime/endTime window must be no more than 7 days. Current docs do not provide a safe unlimited-retention promise. Use fromId/time-window pagination where supported and persist forward.
- income: only the latest 3 months; default recent 7 days; request weight 30. Poll incrementally.
- allOrders and allAlgoOrders: records older than 90 days are unavailable; canceled/expired orders with no fills may disappear after 3 days. Query windows must be less than 7 days.
- openOrders/openAlgoOrders are current-open views, not history.

Implement resumable incremental cursors, idempotent upsert and deduplication. Gaps in unavailable history must be marked PARTIAL, not fabricated.

## 9. Accounting and reconciliation

- userTrades provides fill-level realizedPnl and commission.
- income provides ledger entries including REALIZED_PNL, COMMISSION and FUNDING_FEE.
- Choose one canonical PnL/fee accounting path and reconcile the other endpoint as a cross-check. Never double-count commission or realized PnL.
- Preserve commissionAsset and income asset; do not sum different assets as if they were USDT.
- Use Decimal for all amounts.
- Preserve exchange IDs and timestamps.
- Funding history from PUBLIC_MARKET is a forecast/context series; actual funding cashflows come from private income records.
- Account-specific commissionRate is optional; if unavailable, projected fee assumptions must be labeled as estimates.

## 10. Privacy and local persistence

Use a separate local private-account database or schema with restrictive OS ACLs. Do not place private account payloads in Git, cloud, Controller evidence bundles, Feishu or model prompts. Backups containing account data must be protected by local/disk encryption. Owner controls retention; no 24-hour purge.

The R2 worker handoff must contain only sanitized schema/test evidence, never real account rows or credentials.

## 11. Required mock tests

Positive:
- fake signed GET request canonicalization and deterministic signature fixtures;
- account, position, normal-order, algo-order, trade and income schema parsing;
- Hedge/One-way and long/short normalization;
- cursor pagination and idempotent replay;
- partial history and non-atomic snapshot representation.

Negative/boundary:
- any POST/PUT/DELETE rejected before transport;
- any unlisted path rejected;
- PUBLIC_MARKET cannot access signer or secret provider;
- fake secret never appears in logs or exception text;
- permission denied never escalates scope;
- stale timestamp and bounded resync;
- missing/duplicate/old history correctly marked;
- openOrders without openAlgoOrders cannot be treated as complete TP/SL state;
- income commission and userTrades commission not double-counted;
- different commission/funding assets not mixed;
- stale/private database inaccessible to public layer;
- no external network or real credential access.

## 12. Deliverables and status

Deliver isolated implementation, fake fixtures, tests, credential setup guide, permission preflight checklist, local retention/backup notes, sanitized WORKER_RESULT, CONTROLLER_HANDOFF and SHA256 manifest.

Return READY_FOR_CONTROLLER_REVIEW only after offline tests and fail-closed cases pass. Do not mark accepted, do not connect a real key, and do not dispatch R3 yourself.
