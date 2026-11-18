[Reading 52 lines from start (total: 52 lines, 0 remaining)]

# DRAFT TASK — QUANT v0.8.0 | R3 Account-Aware Signal Overlay
## V080-SOL62-PERSONAL-MVP-ACCOUNT-OVERLAY-01

- **Executor:** GPT-6.2 Sol
- **Architecture challenger:** GPT-6.2 Astra
- **QA:** Gemini 4 Hydrogen
- **Independent acceptance:** Controller 0-C
- **Status:** DRAFT ONLY — gated on R1 and R2 independent acceptance
- **Canonical documentation branch:** docs/engineering (sole project-document authority)
- **Executable code/runtime branch:** v0.8.0
- **Documentation write rule:** Keep canonical project docs, role docs, task cards and handoffs on docs/engineering; keep implementation/test evidence in the approved local work root.
- **Target work root:** workspaces/lt-v080-sol62-personal-mvp-account-overlay-01/

## Mission

Join accepted PUBLIC_MARKET signals with the optional PRIVATE_USER_DATA account snapshot to show whether a market setup conflicts with actual positions, average entry, current TP/SL, outstanding orders, fees, funding and realized results. This is an advisory overlay, not an execution system.

## Required output dimensions

- market_setup_status: EXECUTABLE / WATCH / INVALID / NO_SETUP / SOURCE_BLOCKED
- account_context_status: CONNECTED / UNAVAILABLE / STALE / PARTIAL
- position_relation: NO_POSITION / SAME_DIRECTION / OPPOSITE_DIRECTION / MULTIPLE / UNKNOWN
- protection_status: PROTECTED / PARTIAL / UNPROTECTED / CONFLICTING / UNKNOWN
- signal_trade_match: MATCHED / PROBABLE_MATCH / UNMATCHED / AMBIGUOUS
- human_actionability: explicit next manual check and stale-data warning

When Layer 2 is absent or stale, market analysis continues. The UI must not imply that account exposure or protective orders were checked. A market-side EXECUTABLE label is never an order instruction or an order API call.

## Reconciliation rules

- Match by symbol, side, positionSide, time window, order/trade IDs, quantity and price proximity.
- Do not force ambiguous matches.
- Preserve partial fills and multiple entries/exits.
- Separate current position state from historical trade episodes.
- Compare current TP/SL from both normal and Algo order sources.
- Do not infer an active stop from a stale historical order.
- Keep all timestamps and snapshot ages visible.

## Accounting

Use the R2 accepted canonical accounting policy. Do not double-count userTrades commission/realizedPnl with income ledger entries. Keep assets and currencies distinct. Show actual fees/funding separately from projected fees/funding. Recompute net R using actual fill prices, commission, funding, spread and slippage assumptions where supported.

## Privacy and safety

Private payloads remain in the local private database. The signal overlay and dashboard must not send account data to Feishu or any cloud service. Controller handoff includes only sanitized tests and hashes. No API key or secret in prompts/logs.

## Prohibitions

No POST/PUT/DELETE, order placement, cancellation, modification, leverage/margin changes, transfers, withdrawals, auto-stop, auto-take-profit or trading. No change to Strict Research qualification or protected history.

## Tests and deliverables

Use fake account fixtures only. Cover no-position, long/short, hedge mode, multiple positions, stale snapshot, missing Layer 2, missing Algo orders, partial fills, ambiguous matches, fees/funding reconciliation, private-data leakage and disabled Layer 3 reachability.

Deliver code, fixtures, tests, local dashboard fields, sanitized handoff, acceptance evidence and SHA256 manifest. This draft must not start before R1 and R2 are independently accepted.
