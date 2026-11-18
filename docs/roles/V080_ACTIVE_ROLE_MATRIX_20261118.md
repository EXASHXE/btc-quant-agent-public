# QUANT v0.8.0 — Active Role Matrix (2026-11-18)

| Role | Responsibility | Boundary |
|---|---|---|
| Owner | Product owner; standing public-data attestation; local Layer 2 key creation/configuration; material scope and future Layer 3 decisions | Never sends API secrets to models or repository; no inferred trading permission |
| GPT-6.2 Astra | Chief architecture and strategy role; cross-module design, critical technical decisions, threat models and independent challenge of Sol's design | Advises/reviews; does not dispatch, implement by default or self-accept |
| GPT-6.2 Sol | Primary engineering executor: public/private API adapters, data engine, strategy implementation, integration and difficult bug fixes | Implements scoped task in isolated workspace; no live calls/credentials during offline task; no self-acceptance |
| GPT-6.2 Sol Max | High-intensity implementation lane within the Sol engineering role for cross-module or unusually complex changes | Not a separate queue or controller; same Sol scope and acceptance boundaries |
| Gemini 4 Hydrogen | Simple engineering, docs, fixtures, mechanical tests, routine lint/format and QA | No architecture authority; does not accept its own work |
| Controller 0-C | Sole engineering queue owner, dispatcher, independent evidence auditor and scoped acceptance authority | No worker self-acceptance; no parallel Orchestrator |
| ChatGPT 1-A | Independent Owner-facing advisor; audits plans, challenges architecture, quantitative strategy and product tradeoffs, prepares prompts/docs on request | Not 0-C; does not dispatch or issue acceptance |
| Layer 1 | Public market data client | No personal account key |
| Layer 2 | Private signed USER_DATA GET client | Dedicated local read-only key; no non-GET route |
| Layer 3 | Trade execution | Disabled; no key/client/routes |

## Default routing

- Consequential architecture fork → GPT-6.2 Astra.
- Core API/data/strategy/integration implementation → GPT-6.2 Sol.
- Cross-module high-complexity implementation → GPT-6.2 Sol Max lane, still under Sol ownership.
- Small deterministic fixtures/docs/mechanical QA → Gemini 4 Hydrogen.
- Dispatch, queue control, independent audit and acceptance → Controller 0-C.
- Independent Owner advice → ChatGPT 1-A.

No Orchestrator role. One active core implementation owner at a time. Worker PASS ≠ independent review PASS ≠ Controller acceptance. A task prompt is not a dispatch.

[executed on device: hyz-laptop (bfc916f4-e88a-469a-9999-cf08962f68ed)]