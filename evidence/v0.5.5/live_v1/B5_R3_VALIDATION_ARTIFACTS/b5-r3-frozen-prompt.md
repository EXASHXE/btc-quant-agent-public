# V0.5.5 — LIVE_V1 B5 R3 Independent Exact-SHA Revalidation

## Role

Independent fresh-session validator for:

`LIVE_V1_B5_R3_INDEPENDENT_EXACT_SHA_REVALIDATION`

Use a fresh Codex/Sol session/worktree that did not implement R3 and did not perform the Controller
seal. Validation is read-only on implementation code. Do not repair inside this task.

Repository:

`EXASHXE/btc-quant-agent-public`

Target branch:

`feature/b-line-live-v1`

## Frozen dispatch binding

```text
VALIDATION_BINDING_MODE = EXACT_CODE_SHA
B5_R3_TARGET_SHA = c2c7cc83294f44340dd9fa1873bff760501fae12
B5_R3_EXPECTED_PARENT_SHA = 937b2b26518ceea0952a7e17279cc42924c88848
B3_ACCEPTED_SHA = 961a0f4d4b37cdb9365d5e5867813ff3129c14db
LIVE_V1_BASE_SHA = 52c16a28153de307dc6132c0975fe29341a0a918
CONTROLLER_DISPATCH_SHA = <current docs HEAD supplied by Controller at execution>
```

Fail immediately if HEAD, parent, repository, branch or worktree identity differs.

## Authority hydration

Read only the minimum authority:

1. `evidence/v0.5.5/controller/B_LINE_CURRENT_AUTHORITY.json`
   - BINDING_FIELDS_ONLY
2. `evidence/v0.5.5/controller/B_LINE_LIVE_V1_DISPATCH_MANIFEST.json`
   - BINDING_FIELDS_ONLY
3. `reviews/v0.5/live_v1/V0.5.5_LIVE_V1_B4_R3_CONTROLLER_SEAL.md`
   - IDENTITY_ONLY
4. `reviews/v0.5/live_v1/V0.5.5_LIVE_V1_B5_REVALIDATION_CONTROLLER_ADJUDICATION.md`
   - MUST_READ only for the eight failed findings

Do not recursively hydrate historical authority unless immutable Git state conflicts.

## Objective

Independently determine whether the exact R3 SHA is safe for the terminal B5 state:

`LIVE_V1_TESTNET_VALIDATED_LIVE_STILL_DISABLED`

This task does **not** authorize LIVE_APPROVAL_ONLY or real-money writes.

## Mandatory exact-SHA review

Capture:
- exact HEAD and parent;
- complete diff `937b2b26518ceea0952a7e17279cc42924c88848..c2c7cc83294f44340dd9fa1873bff760501fae12`;
- complete Live V1 diff from accepted B2B base;
- changed files;
- runtime/dependency versions;
- full-history H40 diff.

Unexpected H40/A-line mutation is BLOCKER.

## Mandatory re-attack of the 3 BLOCKER findings

### B1 — actual placement-time authorization and current account

Prove risk-increasing placement cannot occur using caller-stale time or a stale account snapshot.

Adversarially test:
- authorization expires before placement;
- authorization expires during margin/leverage setup;
- forced current account read fails;
- account margin/risk changes during setup;
- current conflicting position appears during setup;
- persisted refreshed authorization is reloaded and revalidated immediately before entry;
- original authorization TTL is never extended.

Required invariant:

```text
actual backend clock
+ fresh current account
+ fresh market
+ current risk/headroom
+ still-valid immutable authorization
-> only then placement
```

### B2 — exact protective-stop ownership

Prove protective order ownership is not inferred from prefix/symbol similarity.

Attack:
- foreign similar client ID;
- exact client ID but wrong symbol/side/type/positionSide/reduceOnly/trigger price;
- missing ownership ledger;
- two intents competing for same symbol/position-side;
- restart with owned + foreign protective orders;
- terminal flat owner followed by a later same-symbol position.

Unknown/malformed ownership must fail closed and must never cancel/adopt a foreign stop.

### B3 — remaining loss/drawdown headroom

Independently recompute worst-case proposed loss including configured stop distance and execution
friction. Prove:

```text
new worst-case loss <= remaining daily-loss budget
new worst-case loss <= remaining drawdown budget
```

Test exact boundary, just-over-boundary, inconsistent peak-equity/drawdown state, long and short.

## Mandatory re-attack of the 5 HIGH findings

### H1 — single runtime enable authority
Verify runtime mode is parsed once through LiveV1Config and B4 runtime mode takes precedence over
legacy B3 control-plane registration. Invalid boolean values fail closed.

### H2 — durable flat/reopen lifecycle
Prove durable 0/nonzero transitions survive restart and account separation. Test:
- long -> flat -> reopen long;
- short -> flat -> reopen short;
- direct long -> short sign flip emits CLOSE then OPEN;
- older observation cannot roll lifecycle backwards;
- legacy state cannot be silently rebound to a different account.

### H3 — component freshness
Prove mark, book and kline each have independent source/receipt freshness authority. A fresh update to
one component must not refresh another. Any required stale component must block new risk.

### H4 — canonical execution identities
Prove TradeIntent validation/load recomputes:
- intent_id;
- idempotency_key;
- client_order_id;
- intent_hash.

A self-rehashed noncanonical payload must still fail before first persistence and after persisted-column
tamper.

### H5 — recovery before new-entry rejection
For any already claimed/submitted intent, prove exchange reconciliation occurs before expiry, tactical
validity, kill-switch or other new-entry-only gates can drop recovery.

Test:
- restart with NEW order;
- restart with PARTIALLY_FILLED order;
- expired authorization with active order;
- kill switch active with active order;
- old ABORTED transition with durable side effect;
- proven pre-entry absence and flat state;
- repeated cancellation during in-flight submission.

## Existing B5 safety matrix

Also re-run the broader independent validation:
- schema/hash tamper;
- approval/case/proposal swap;
- executable proposal equivalence;
- persisted PreExecutionAuthorization binding;
- account/environment/credential namespace isolation;
- duplicate submission/idempotency;
- transport uncertainty query-before-retry;
- partial fill/protection resizing;
- SQLite WAL/busy timeout/FULL/foreign_keys and contention;
- PositionSupervisor durable outbox/lease ownership/frozen PositionCase;
- operational runtime startup/shutdown/recovery;
- host API read-only governance in B4 runtime mode;
- Feishu callback cannot carry executable order authority;
- provider boundaries and secret isolation;
- TESTNET-only write fence;
- LIVE and AUTONOMOUS remain hard blocked.

## CI adjudication

Exact-target GitHub Actions run:

`37099190279`

Attempt 1 had two failures: A34 shallow-checkout plus one H40 scientific golden mismatch.
Attempt 2 on the exact same SHA had:

```text
2286 passed
1 failed
2 skipped
```

with only A34 shallow-checkout remaining.

Do not simply inherit Controller classification. Independently confirm:
- same exact target SHA;
- attempt-2 H40 scientific golden test passed;
- full-history H40 source diff is ZERO;
- remaining A34 text is the historical revision missing from shallow checkout.

Any additional current failure must be adjudicated separately.

## Tests/static

Run without modifying source/tests:
- all Live V1 tests;
- focused R3 identity/placement/protection/recovery tests;
- existing execution tests;
- MarketWatch tests;
- B2A/B2B regressions;
- full pytest suite;
- ruff;
- mypy;
- compileall;
- git diff --check.

Record exact counts.

## Network/provider smoke

Never use real-money credentials.

If dedicated TESTNET/provider credentials are unavailable, mark each explicitly NOT_RUN rather than
weakening deterministic validation.

## Required evidence

Publish machine-readable evidence bound to `c2c7cc83294f44340dd9fa1873bff760501fae12` including:
- exact identity;
- complete changed-file list;
- eight-finding adversarial matrix;
- broad safety matrix;
- tests/static counts;
- remote CI adjudication;
- provider/testnet smoke status;
- LIVE write count;
- H40 fence;
- blockers.

No implementation repair in this validation task.

## Terminal states

PASS:

`LIVE_V1_TESTNET_VALIDATED_LIVE_STILL_DISABLED`

FAIL:

`LIVE_V1_INDEPENDENT_VALIDATION_FAILED`

Even on PASS:

```text
LIVE_APPROVAL_ONLY = NOT_AUTHORIZED
REAL_FUNDS_WRITE_AUTHORITY = NONE
AUTONOMOUS_LIVE = FORBIDDEN
```

Real-money enablement requires a separate:
`B_LINE_PRE_LIVE_EXECUTION_INDEPENDENT_SAFETY_AUDIT`
plus explicit Controller authority.

## Final output

Return exactly enough for Controller adjudication:

```text
decision
validated_sha
parent_sha
changed_files
identity_gate
prior_3_blockers
prior_5_highs
schema_identity_attacks
approval_safety
risk_math
execution_idempotency
account_reconciliation
position_supervisor
runtime_governance
provider_boundaries
secret_isolation
testnet_only_fence
live_write_count
testnet_network_smoke
focused_tests
full_suite
ruff
mypy
compileall
h40_fence
remote_ci
blockers
next_state
```
