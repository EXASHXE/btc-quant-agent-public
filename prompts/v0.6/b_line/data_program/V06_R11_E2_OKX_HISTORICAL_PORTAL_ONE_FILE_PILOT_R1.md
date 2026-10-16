# R11-E2 — OKX Historical Data Portal One-File Pilot

**Executor:** local Codex High, one isolated session.  
**State:** READY / BOUNDED.  
**Channel:** official OKX Historical Data Portal only; do not substitute generic public REST/WS API data.

## Rights basis

The official OKX Historical Data Terms state that the historical Data available through the portal may be downloaded/accessed for personal use, explicitly including possession, retention and development of the user's own trading strategy, under a limited, revocable, non-exclusive, royalty-free personal-use license. It prohibits commercial use/redistribution. This task is strictly personal, noncommercial, nonproduction research.

Official terms: https://www.okx.com/en-sg/help/historicaldata-terms-and-conditions

## Scope

Primary instrument: **BTC-USDT-SWAP**.

Use a newly selected bounded date that is not the existing Binance R10-D1 2022-09-15..21 interval; prefer **2024-01-15 UTC** if the portal offers that exact date/file.

Acquire at most one representative file per available portal family:

- Trade history;
- Candlestick/OHLC;
- Funding rate;
- L2 order book only if the portal actually exposes a downloadable file for the selected instrument/date.

Do not download OI through generic OKX public API in this task. The current official historical-data portal advertises Trade, Candlestick, Funding and Order Book, but does not advertise historical OI. Treat OKX historical OI as unresolved until a separate applicable source/right/path is proven.

## Required QC

For every file:

- exact portal URL/file identity and instrument;
- available date range and file date;
- compressed/raw bytes and checksum/integrity evidence;
- schema and units;
- native timestamp semantics;
- UTC vs UTC+8 presentation;
- contract multiplier/contract-size metadata;
- trade size units;
- funding timestamps/intervals;
- L2 depth level, snapshot/delta sequence and recovery semantics if present;
- duplicate/gap checks;
- provenance manifest and immutable receipt hash.

Do not claim historical receiver first-known/PIT merely from file timestamps. Do not claim data completeness beyond the exact file/date tested.

## Hard boundaries

No API market calls, no private account data, no credentials, no trading, no TESTNET/LIVE, no protected project data, no strategy scoring, no model training, no redistribution, no LLM upload of raw market data.

If the portal requires a login, regional eligibility, or an additional acceptance step that the executor cannot lawfully satisfy, STOP and report the exact missing condition. Do not bypass it.

Publish one report and only deterministic acquisition/QC code necessary for this pilot. Exact commit/blob/parent/diff/CI required.

Terminal: `R11_E2_OKX_PORTAL_PILOT_ACCEPTED_WITH_LIMITS` or `R11_E2_OKX_PORTAL_PILOT_STOP`.