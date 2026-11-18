# QUANT v0.8.0 — Roadmap, Task Ownership and Exit Gates

Baseline date: 2026-11-18. This is the current Owner-directed roadmap; Controller 0-C must independently reconcile and maintain task states.

| Stage | Scope | Owner/model | State | Exit gate |
|---|---|---|---|---|
| R0 | Rebaseline, roles, API boundaries, local source baseline | Owner / 1-A draft / 0-C review | Prepared; 0-C review pending | Controller confirms baseline, source hashes and task boundaries |
| R1 | Layer 1 PUBLIC_MARKET personal mode | GPT-6.2 Sol; Astra architecture challenge; Hydrogen QA | Prompt ready; pending 0-C dispatch | Offline/mock tests pass, five timeframes and market context integrated, no real network or credential |
| R2 | Layer 2 PRIVATE_USER_DATA read-only connector | GPT-6.2 Sol; Astra review; Hydrogen QA | Draft only; gated on R1 acceptance | Signed GET mock tests, permission fail-closed gate, local credential-store adapter, private-data isolation |
| R3 | Account/signal overlay and fill reconciliation | GPT-6.2 Sol; Astra challenge | Draft only; gated on R1+R2 acceptance | Actual position/entry/SL/TP and PnL overlay; honest match states; Layer 2 unavailable does not block public market data |
| R4 | Full local personal MVP | GPT-6.2 Sol; Hydrogen QA | Planned | Repeatable local run: market data → signal → optional account overlay → risk card → local journal/dashboard |
| R5 | Universe expansion and notifications | Sol / Hydrogen | Planned | Add ZEC/HYPE/INJ/ARB/ARIA/ERA/AAVE/INIT and other liquid USDT-M contracts; optional market-only Feishu |
| R6 | Prospective evaluation | Sol / Astra analysis / 0-C review | Planned | Track real manual fills, fees, funding, slippage, net R, win rate, drawdown and signal quality; no profitability claim before evidence |
| R7 | TRADE_EXECUTION | No owner assigned | Disabled / excluded | Requires separate future Owner decision and entirely separate design/credentials |

## Immediate next action
Controller 0-C reviews R0 and the R1 task card, verifies the copied Program J baseline and confirms no v0.7 worker is already running. The v0.7 dispatch receipt says the old task was NOT_STARTED and its work root was not created. If no conflict exists, 0-C issues a new v0.8.0 dispatch to GPT-6.2 Sol.

R1 is offline/mock-only. It must not perform live Binance GETs, inspect credentials, or implement Layer 2 or Layer 3.

After R1 scoped acceptance, complete the one-time local PUBLIC_MARKET operating-scope template and have 0-C review it before the first live public scan. No per-request consent is required while requests remain inside that approved scope.

## Acceptance ladder
1. Worker delivers code, tests, baseline-preservation record, handoff and manifest.
2. Astra reviews architecture only where a material cross-layer decision exists; this does not count as implementation acceptance.
3. Hydrogen performs mechanical QA on a separate bounded scope where assigned.
4. Controller 0-C independently checks actual files, test output, hashes, negative cases and scope.
5. Only Controller 0-C may issue scoped acceptance.
6. Live operation, private credentials, account reads and any expanded external action remain separately gated by the applicable Owner/Controller operating envelope.

## Personal versus Strict Research
PERSONAL_MVP uses normal OS synchronization + venue serverTime offset, configurable freshness, dynamic rate budgets and Owner-controlled local persistence. Strict Research and protected/holdout history remain unchanged. Personal data never qualifies Strict Source/E1, Strict Shadow or economic validation.

## No overbuilding
Do not create new generic synthetic work merely to advance a milestone. Prioritize a working Layer 1 five-timeframe market path, then the read-only account connector, then the actual account overlay. Keep R2 and R3 sequential so each permission and accounting boundary can be reviewed independently.
