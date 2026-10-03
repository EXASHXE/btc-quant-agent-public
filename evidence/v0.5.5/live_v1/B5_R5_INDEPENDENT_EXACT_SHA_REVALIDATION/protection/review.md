# Independent R5 protective-order review

Target: clean clone `/tmp/b5-r5-independent-code` at `a663921abf90504412d0d67b2b9c9f134f204d85` (parent `4bc05e1a7c7fae86f41c1dd9b5a1635d0540ee58`). Source and tests remained unchanged. Attack driver: `attack.py`; machine-readable observations: `attack-results.json`. It uses the repository's fixture setup with newly authored mutations and assertions, temporary SQLite files, fake clients, and no real endpoints.

## Blocking correctness issue

**R5-02: boolean numeric alias can confirm an invalid protective contract.** `protective_field()` uses Python `!=` to decide whether two aliases conflict (`src/btc_quant_agent/execution/protection.py:64-72`). For a one-unit stop, `quantity=1.0` and `origQty=True` compare equal. `_validate_protective_contract()` checks the returned primary quantity for boolean type (`src/btc_quant_agent/execution/backend.py:693-698`) and never checks the alias. The independent `contract:boolean_numeric_alias_conflict` attack passed a complete otherwise valid exact response with these two fields and observed the validator return `('r5-independent', 1.0)` instead of `PROTECTION_CONTRACT_MISMATCH`. A malformed exact response can therefore satisfy the full-contract gate and advance pending ownership to `ACTIVE` for an ordinary one-unit position. The same type-equality issue applies to `triggerPrice=1.0`, `stopPrice=True` when the intended trigger is one unit. The fixture uses a direct validator call for this rare value; the production path invokes this same validator before `record_stop()`.

## Verified behaviors

50 of 51 independent attacks met their expected fail-closed or recovery assertions. The single failure is the blocking issue above. The attacks cover mutations and omissions of `algoType`, `orderType`/`type`, `workingType`, `priceProtect`, `closePosition`, `reduceOnly`, `positionSide`, `symbol`, `side`, trigger and quantity fields, `clientAlgoId`, exchange ID, and mandatory status; NaN and infinity; contradictory aliases; and exact query/cancellation restarts.

- Pending exact-query failures survived two restarts with one protective POST, three exact queries total, and no aggregate promotion. An exact complete response then promoted the owner to `ACTIVE` while POST remained at one call.
- A POST failure before any exchange ID was known retained `PENDING_CONFIRMATION` and the client ID; a restart did not blindly resubmit or query an unknown ID.
- Flat pending ownership survived unstructured `-2013` text and an empty aggregate list. Only a structured exact provider `code=-2013` released it. Neither path called cancel.
- After a flat cancel became uncertain, the restart retained `CANCEL_PENDING` and the exact IDs, rejected a later same-symbol owner, and did not repeat cancel. Exact `NEW` remained pending; exact `CANCELED` released it once.

No other blocking issue was established in the assigned scope. These are fake-client state-machine attacks; they do not establish exchange schema behavior or network timing guarantees.
