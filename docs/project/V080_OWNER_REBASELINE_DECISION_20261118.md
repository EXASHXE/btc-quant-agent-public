# QUANT v0.8.0 — Owner Product Rebaseline Decision (2026-11-18)

Decision class: Owner-directed product baseline.
Controller state: Pending independent Controller 0-C review; this document is not a Controller acceptance or a live API grant.

## 1. Product
Build a personal, local, noncommercial Binance USDⓈ-M trading decision-support system for a 2–12h holding horizon. It informs human decisions; the human remains responsible for opening, modifying and closing positions.

Decision cadence:
- 1D: background structure and major levels.
- 4H: market regime and structure.
- 1H: primary setup.
- 15m: entry trigger/confirmation.
- 5m: actionability and no-chase refresh.

## 2. Three-layer API decision
1. PUBLIC_MARKET: public market data; no personal account API key.
2. PRIVATE_USER_DATA: optional signed GET-only account reads; separate dedicated local read-only key.
3. TRADE_EXECUTION: disabled; no trade key, order client or mutation route.

Layer 1 must work without Layer 2. When Layer 2 is missing or stale, display ACCOUNT_CONTEXT_UNAVAILABLE / ACCOUNT_CONTEXT_STALE as a separate account overlay. Do not veto all market research. Do not present a market-side setup as account-cleared when account context is unknown.

## 3. Existing Owner attestation
Reuse OWNER_STANDING_M2_AUTHORIZATION_20261024.md for the same explicitly scoped personal/noncommercial/private/local/read-only public-market-data research. Record it as OWNER_ATTESTED. Do not repeatedly request the same statement, do not represent it as a Binance-issued approval or third-party legal opinion, and do not alter the historical source file.

This is not a blanket approval for:
- proxy or region rotation to bypass a restriction;
- a known venue or jurisdiction prohibition;
- commercial activity or redistribution;
- private account access;
- order placement, modification, cancellation, leverage or transfers.

A material change in use, region, distribution or an explicit venue restriction requires review.

## 4. Personal mode versus Strict Research
PERSONAL_MVP is a separate product mode with normal OS time synchronization, monotonic elapsed-time measurement, Binance serverTime offset, configurable freshness/finality, dynamic rate budgets and Owner-controlled local retention.

STRICT_RESEARCH remains unchanged. Strict Source/E1, protected historical windows, holdout rules, independent UTC/NTS, hardware witnesses, strict custody and strict Shadow/economic qualification are neither deleted nor silently weakened. Personal evidence is never promoted to those classes.

## 5. Layer 2 credential policy
- Owner creates and configures the key locally.
- Dedicated key, Enable Reading only.
- No trade, withdrawal, transfer, margin or account mutation permissions.
- Secret stored in OS credential storage / DPAPI / keyring or equivalent.
- Never send key, secret, signed query, private payload or personal account screenshot to ChatGPT, Astra, Sol, Hydrogen, GitHub, logs, Feishu or controller evidence.
- If the current Binance permission UI/API requires a Futures permission whose TRADE implications are not proven read-only, stop and leave Layer 2 disconnected. Do not widen permission to force access.

## 6. Scope sequencing
- R1: PUBLIC_MARKET personal-mode vertical slice; BTC/ETH/SOL first, five timeframes and market context.
- R2: PRIVATE_USER_DATA signed GET connector, only after R1 acceptance.
- R3: account-state and signal matching/overlay, only after R1 and R2 acceptance.
- R4: full local MVP, local journal and dashboard.
- R5: expanded liquid USDT-M symbol universe and optional market-only notifications.
- R6: forward evaluation of actual fills and net outcomes.
- Layer 3: disabled and excluded from the MVP roadmap.

## 7. Owner intent
Reduce institutional-style process that is not necessary for a personal local tool. Do not spend the critical path on repeated rights attestations, per-request approvals, NTS certification, hardware anchors or mandatory 24-hour deletion. Do retain real data integrity, TLS, API permissions, bounded rate limits, completed candles, no-lookahead, cost-aware risk, local privacy and the no-trading boundary.
