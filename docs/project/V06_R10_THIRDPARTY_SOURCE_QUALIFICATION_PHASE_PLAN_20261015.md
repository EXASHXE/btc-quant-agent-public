# quant v0.6 — R10 Third-Party Source Qualification Phase Plan R1

**Date:** 2026-10-15 (UTC+08). **Controller:** ChatGPT-0 B-line. **Scope:** ONE new-source DOCUMENTARY intake/rights/PIT feasibility preflight, not source admission, data access, Alpha trial, purchase, brokerage or legal opinion.

**CONTROLLER TERMINAL: R10_S0_NEW_EXTERNAL_VENDOR_PRIMARY_DOCUMENTARY_EVIDENCE_FOUND / ONLY_2E_PREFLIGHT_DISPATCHED.**

## 1. Binding R9 status and changed evidence

- R9-G0 independent Auditor: commit `54d5d8c665814a53b0424e1584ac72a98a45c465`, report blob `639cb57263fecbe14ecb5f14cfbffe81bc7fcd8d`; `R9_G0_STRATEGY_RESEARCH_PAUSE_UNTIL_SOURCE_EVIDENCE`.
- R9-L1 Controller: commit `ab0761ac81d0877e017673b8af40d64299107563`, report `reviews/v0.6/b_line/V06_CONTROLLER_R9_L1_PROGRAM_RESEARCH_PAUSE_AND_RESTART_GATE_R1.md`, blob `f2e49abe26f2bf088cb473704df90b109c9794e7`; `R9_L1_PAUSE_NEW_ALPHA_RESEARCH_PENDING_EXTERNAL_SOURCE_EVIDENCE`.
- R7-B0 Binance native USD-M REST/WS rights STOP commit `d10653b8220521b6091ab69aa426657c479f6e3e`, report blob `8e451d14f002cab2f316c934416aa1be38081cf4`. R8 H-M1 duplicate H18-D1 STOP remains closed; no new Alpha.
- **NEW distinct outside-vendor PRIMARY documentation identified on 2026-10-15, NOT previously adjudicated by R7/R9:** `https://docs.tardis.dev/legal/terms-of-service` clauses 1 definition of `Permitted Use`, 9.1, 9.2, 9.4, 9.5, 10.5, 19 and 23, `https://docs.tardis.dev/historical-data-details/binance-futures` and `https://docs.tardis.dev/faq/billing-and-subscriptions` plus `https://docs.tardis.dev/faq/data` and `https://docs.tardis.dev/historical-data-details`. These are provider-authored public online documents, **not** a signed owner agreement or source payload. Pin access time/visible version text and quote no unsupported immutable webpage SHA. Any future subsequent terms revision is outside this snapshot.
- Tardis documentation for the `binance-futures` USD(S)-M product states historical native L2/bookTicker/trades/forceOrder/markPrice and **generated REST-polled openInterest** around every 30 seconds, with `localTimestamp` in native replay/normalization. It also describes snapshot generation, sequencing, reconnect gaps and historical coverage. These claims are **documentary assertions, NOT checked or independently certified raw observations**.
- Provider's published licence (9.1) states subject-to-terms rights to access/manipulate/derive and store Data on Customer System for defined internal business, research, educational or personal `Permitted Use`. 9.4 describes perpetual retained access to lawfully downloaded data **subject to licensor restrictions/10.5**. 9.5 allows internal task-specific quantitative/statistical model work but **explicitly excludes general-purpose AI/foundation models/LLMs** and governs external disclosure; no raw vendor data to ChatGPT, Gemini, Codex, external app or repo without separately established compliant authorization. Third-party/exchange/licensor restrictions, customer eligibility, paid access and actual permitted retention/use remain **UNVERIFIED**.
- This is a **different potential pathway** from source directly taken from Binance REST/WS or Binance Vision public archive, and is concrete enough to justify ONE bounded new document audit per R9 external-evidence hinge. It **does not** reverse R9 pause for strategy creation.

## 2. Research objective and minimal science dependency

Ultimate objective stays independent, source-qualified, after-full-cost BTCUSDT USDT-M 4–24h Alpha. Scientific prerequisite is genuinely incremental external information Z beyond previously used price/flow baseline X, plausible native original first-arrival/vintage and accurate execution/account costs. Data qualification ≠ strategy edge, legal agreement ≠ truthful PIT, and even valid historical bid/ask ≠ private historical order ACK, fills or causal PnL.

**R10 one-task plan:**

| Phase | Owner | Allowed deliverable | Prerequisite / STOP |
| --- | --- | --- | --- |
| **R10-S0 NOW** | **2-E Direct Operator** | ONE official-provider-rights/product/channel/PIT/price-tier preflight REPORT, exact sources, no payload | Compare supplier Terms to source product BTCUSDT USDS-M; inspect vendor receive timestamp and OI poll semantics; if legal/clock blockers remain, return documentary STOP |
| **R10-S1 CONDITIONAL** | 1 Independent Auditor | Consequential legal-source/time provenance suitability audit on frozen S0 report (no legal advice/entitlement certification) | Controller must explicitly dispatch after verifying exact author SHA/blob, with materially decision-relevant S0 findings |
| **R10-L2 CONDITIONAL** | 0 Controller | Choose rights/provenance fail-closed or a future one-file rights-qualified isolated sample QC protocol | Owner-specific purpose/licensor/retention/account/product/subscription entitlement and independent source audit must support. No automatic S2 |
| **R10-S2 NOT AUTHORIZED** | 2-E limited one file *only if separately granted* | One exact date/symbol/data type/byte-budget/quarantine trial, integrity/payload/clock QC only; no scores, backtest or protected source | Separate explicit owner+Controller permit, vendor account and lawful rights, archive/safe chronology, independent reviewer; default STOP |
| **R10-R/G2/G4 NOT AUTHORIZED** | 2-R/2-C/1/0 and later Codex/Gemini | Distinct Z novelty and full-cost preregistration/evaluation only after all appropriate gates | No source = no trial. No Alpha, TESTNET, LIVE or funds |

**Model routing:** S0 is M1/M2 *documentary source-rights provenance* work; 2-E acts directly rather than unnecessary Gemini BOOST/Codex. If later source-clock and ledger cross-module implementation becomes authorized, evaluate Codex Sol High / Gemini BOOST under immutable scope and independent 1 audit. No custom subagents.

## 3. Three decisive R10-S0 gates (documentary only)

1. **Provider rights vs customer-specific entitlement:** vendor's exact primary clause on internal use, raw storage, derived research, internal quantitative ML, external AI/data disclosure, third-party licensor, termination and redistribution. Identify product-specific rights conflicts/UNKNOWN, user legal purpose and subscription applicability, no account number or credentials.
2. **Native feed + timestamps:** historical earliest dates and fields for BTCUSDT futures depth/bookTicker, native mark/funding, REST 30-second OI generated polls, force orders; event vs vendor local receive vs durable complete known-at and correction-vintage. Check native partial-order and clock bounds plausibility, time breaks, sequence continuity and vendor availability on required date; UNKNOWN if no original timestamp trust/durability.
3. **Economic representativeness:** data-tier CSV vs Pro/Business native replay and permitted 4h–24h sample design, funding/Mark, L2 quote, no private own queue/fill/ACK. Proof requirements for eventual taker vs maker utility; no fee/impact or profitable signal assumed.

**Hard stop before bytes:** licence/supplier permissions do not automatically permit ChatGPT upload or consumer ML training; no raw datasets, sample CSV, trial signup, subscriptions, external data services, endpoint requests, downloads, private account, conversion/normalization, market REST/WS or ZIP/CHECKSUM. Avoid private/protected H39/H40/H41/Forward/Final/OOS and Quant-agent/data / Quant-agent-sanitized.

## 4. Terminal and re-entry

R10-S0 must terminate after one report with clear `THIRDPARTY_DOCUMENTARY_CANDIDATE_WITH_LIMITS`, `THIRDPARTY_SOURCE_RIGHTS_OR_CLOCK_STOP`, or `THIRDPARTY_PRODUCT_SCOPE_INCONCLUSIVE_STOP`. A **candidate** is NOT `SOURCE_ADMITTED`. No model training, G2, G4 or LIVE permission.

**Preserved:** `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`. T6 and H-M1 remain STOP. Main `v0.6-docs` and code `v0.6` branches unaffected by isolated dispatch.
