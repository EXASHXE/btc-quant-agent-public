# P1D R4 synthetic causal G1 integration evidence

Scope: **SYNTHETIC_INTEGRATION_ONLY**. Controller alone owns integration, merge and release authority; G2 Alpha, TESTNET and LIVE remain NO_GO.

Task identity: `cf9796fe638d9d6046d8a05c3c6a9ca5785765d8`, dispatch blob `bd389123d93d25e0d7e21fdcb695d458f106dc31`. Complete independent F1/F2/F3 audit: `e11f84963adddc29b1dc106c1e0d2a984dd6add2`, report blob `da837ba4f1c4caaacd6e791bac7d0935a68c75ea`. Complete prompt/audit bytes and supplied port/reducer identities were verified against their pinned Git objects.

Exact engineering parent: `04cbc46497ed26b0c4e889f30fa10eb8d666a79e`. Isolated branch: `feature/v06-p1d-r4-synthetic-g1-funding-causal-integration`. The commit containing this file is the immutable candidate; its full SHA, actual remote CI run and independent final-freeze receipt are delivered separately to avoid a self-referential commit assertion.

## Contract and audit disposition

F1: the new `FUNDING_RECEIPT` event is ordered at receiver availability. Economic `settlement_at` remains immutable and is retained in the cash journal along with receipt time. Earlier decision/approval/trace snapshots are preserved; `EVENT_REORDERED` remains enforced. Explicit `initial_state(..., causal_funding=True)` opts into the synthetic R4 contract and a WAL-backed fill history. Default legacy genesis, old `FUNDING` payloads and historical synthetic WAL identities retain their contract. Cross-contract funding is rejected, and opening an old WAL under new genesis quarantines without rewriting the original WAL.

F2: signed exposure comes only from the opt-in G1 execution ledger, whose fill IDs reconcile to `used_fill_ids`. Mark/rate require explicit economic-time synthetic witnesses; fill coverage is bounded from genesis through settlement and must be known no later than receipt. Every fill within the inclusive ±15,000 ms settlement window is quarantined. A 0.010 BTC LONG at Mark 60000 and +0.0001 rate posts -0.0600 despite a later 0.004 exit and receiver inventory 0.006; equivalent SHORT posts +0.0600. A pre-T partial posts -0.0360/+0.0360. Negative rates reverse signs. Complete flat/zero-rate witnesses journal explicit zero; missing/inconsistent/future witnesses reject instead of fabricating zero. Current-bar Mark is not the settlement Mark witness.

R4-only TP1 fixtures may specify actual `executed_quantity`, bounded to positive lot multiples no larger than the unchanged half-tier. Existing exit cash, reservations, ACK timing and position safety checks use that executed quantity. Default legacy TP1 quantity and logic are unchanged. This models a declared synthetic partial execution, not an exchange order lifecycle.

New R4 financial transitions use a fixed local Decimal precision of 128; funding cash rounds once to eight USDT decimal places with ROUND_HALF_EVEN. The journal balance changes by exactly that signed posted delta. Legacy financial arithmetic is unchanged. The standalone helper now defaults to incomplete coverage, rejects LONG/negative quantity contradictions, and accepts explicit SHORT-signed input without unqualified long normalization. Existing helper test assertions remain intact; their invented coverage is now explicit.

F3: one settlement-keyed cash journal is committed through the existing hash-chained G1 WAL. Its persisted economic fingerprint includes event identity, settlement identity/time, normalized rate/Mark and bounded source witnesses, while transport retry clocks are excluded. Conflicting identities/rate/Mark reject; identical retry is idempotent even after a fresh port/supervisor restart. Port acceptance never acts as cash ACK: retries of an already seen transport record are still delivered to G1. Supervisor ACK is returned only after ledger append/fsync/checkpoint. ACK is retryable; the durable cash journal, not ephemeral port memory or a second financial ledger, owns exactly-once cash.

## Actual RED and GREEN evidence

Before implementation, three real tests on the unchanged frozen base failed: late receipt after a newer BAR raised EVENT_REORDERED; settlement Mark was absent from translated payload; LONG negative quantity did not reject. JUnit/log receipts are retained in the task delivery. A further 17 desired causal/WAL cases were executed against the frozen original module checkout: all failed because the R4 opt-in/delivery contract did not exist. Those failures demonstrate a missing protocol, not an observed legacy double charge.

Initial R4 suite: 38 passed, including nine real process-death boundaries. Independent working-tree reviewer separately reproduced 49 expanded cases passing. The final expanded R4 module passed 50/50 locally (10.55 seconds); final exact-SHA CI and the affected legacy suite counts are delivered after completion. The additional legacy-genesis quarantine and cross-contract boundary checks each passed individually.

Process-kill cases call os._exit(91) before/after receipt, before append, after append, after fsync, before/after snapshot and before/after receipt ACK. Recovery checks committed versus pre-append state, one funding WAL record, exactly one signed cash journal effect, preserved receipt chronology, and subsequent exit ACK/restart. These are process-crash witnesses; no power-loss filesystem fidelity is claimed.

Commands:

```sh
PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider -q tests/test_v06_p1d_r4_late_funding_g1_economic_recovery.py
PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider -q tests/test_v06_p1d_r4_late_funding_g1_economic_recovery.py tests/test_v06_g1g3_offline_ports_r1_core_integration.py tests/test_v06_g1g3_offline_ports_r1_recovery_and_guards.py tests/test_v06_g1_offline_preview_r1_core.py tests/test_v06_g1_offline_preview_r1_decimal_and_ports.py tests/test_v06_g1_offline_preview_r1_exit_safety.py tests/test_v06_g1_offline_preview_r1_wal.py tests/test_v06_g1_offline_preview_r1_process_recovery.py
```

The affected legacy suite uses existing fake localhost servers. The first sandboxed run was interrupted after reproducing PermissionError on socket creation; it is not counted as a successful validation. The rerun enables those localhost tests and clears inherited proxy variables, without changing tests, fixtures or network policy in the repository. No external service, market source or exchange was invoked.

Ruff check and format verification pass for all changed executable paths. The unchanged CI risk classifier maps these source changes to `full`. Actual exact-head GitHub CI must be recorded separately; no docs-only green is executable acceptance.

## Source/test blob whitelist

| Path | Frozen original blob | Candidate blob |
| --- | --- | --- |
| `scripts/g1_offline_preview_r1/model.py` | `78f77d424a4186a2377413c387b2eeae146066c6` | `337d3aa1637bb5aa0037b17deab334acde653061` |
| `scripts/g1_offline_preview_r1/reducer.py` | `df6a68f4797950f1b9bdbdebc6591745cdea76d5` | `480eae7b3034bb5def8da3e1fef618c1a567cc98` |
| `scripts/g1_offline_preview_r1/storage.py` | `4d250f5123d57d4df7430b9dc911b5b5208ba81e` | `29b76b39a4079ac82177f16d9f1b74d7c74610c1` |
| `scripts/g1g3_offline_ports_r1/durable_supervisor.py` | `9c0fec44287911fad6a64d274f44b9a8c90388d4` | `625885778505eee1aef1f193b8bfe9ee7be909fc` |
| `scripts/g1g3_offline_ports_r1/market_pit_port.py` | `3c2198325649ea3a64986218ec60953cbb889403` | `f2e88b2339bf8702f29de8862aea51eb972a9bb0` |
| `tests/test_v06_g1g3_offline_ports_r1_core_integration.py` | `92261a755f8ad94cbb0d5d1e8332537cf6e6c40c` | `3c5c62de616132d06e9d6f7ef79e9777c39971a1` |
| `tests/test_v06_p1d_r4_late_funding_g1_economic_recovery.py` | `ADD` | `70cc6796353a8539b100e7e10b7da351f1854cc6` |

Only these six existing files are modified, plus this allowed engineering document and the new R4 test module. `docs/` is permitted by existing catalog checks; `reviews/` is absent. All other tracked mode/blob identities, protected H40/H41 code/tests/goldens, CI workflows/policy, dependencies, historical events and prior report archives remain unchanged. No force push, reset, cross-merge or other worker branch write is authorized.

## Gate and limits

Base true manual full CI `38426601134` failed: Python 3.12 3359 passed / 1 H40 digest failure / 2 skipped; compatibility also had history-object failures. That protected hold and separate CI workstream remain unresolved and are not attributed to this task. No protected golden adoption, history fetch workaround, skipped test, changed CI policy or release claim is made here.

Synthetic Mark/rate/fill witness labels are invented assertions backed only by the controlled G1 execution/WAL contract. They do not certify venue settlement, receiver-source admission, real fills or wallet balances. Final independent review must inspect the exact candidate commit and actual receipts. Candidate terminal: **`CONTRACT_REDESIGN_REQUIRED`**. Functional F1/F2/F3 synthetic witnesses pass, but existing immutable-core conformance is violated by the authorized source changes. This is a bounded prototype, not an accepted integrated contract.

### New blocking identity-contract conflict

The unchanged `tests/test_v06_g1g3_offline_ports_r1_recovery_and_guards.py::test_static_ast_and_c4_core_immutability_verification` invokes `verify_static_ast_and_core_immutability` in `scripts/g1g3_offline_ports_r1/no_order_port.py`. Its `PINNED_G1_C4_MANIFEST` freezes 13 G1 files, including all three authorized modified G1 files. It raises `G1_CORE_MUTATED:scripts/g1_offline_preview_r1/model.py` on this candidate before its AST checks can complete. The exact frozen base passes this test (1 passed / 0 failed); this candidate fails it (0 passed / 1 failed). Thus this conflict is demonstrated by an authorized before/after test; it is distinct from the existing H40/compatibility holds.

`no_order_port.py` is outside this dispatch's MODIFY allowlist. No manifest, test expectation or verifier was altered, skipped, monkeypatched or bypassed. The independent reviewer separately confirmed the contract conflict and gave `CONTRACT_REDESIGN_REQUIRED` for overall acceptance.

Minimum exact-SHA follow-up proposal: retain this isolated candidate and its original parent unchanged; authorize a separately reviewed versioned G1 identity contract in `scripts/g1g3_offline_ports_r1/no_order_port.py`, retaining the original C4 manifest and adding the explicitly approved R4 model/reducer/storage identities. Validate the declared version at the boundary; preserve all 13-file checks, AST restrictions and negative mutation tests. The already allowlisted recovery test may then explicitly exercise both version contracts. Do not adopt new hashes implicitly or modify H40/H41, CI policy, historical data or another worker branch. If Controller instead requires current-path original C4 source bytes to remain frozen, an isolated versioned G1 module/path authorization is needed; that alternative is not implemented here.

The exact candidate SHA in the delivery identifies this proposal and every changed blob. No further contract/policy patch is made under the present scope.
