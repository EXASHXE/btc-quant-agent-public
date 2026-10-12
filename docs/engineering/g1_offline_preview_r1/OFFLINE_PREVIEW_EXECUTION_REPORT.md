# G1 offline preview execution R1

Terminal: G1_OFFLINE_PREVIEW_VERIFIED. This task implements a standalone synthetic workflow; it does not validate strategy Alpha, accept a production engine, or authorize TESTNET, LIVE, protected data or real funds. Requested executor is GPT-6.1 Sol High; actual root model/effort are not exposed by this session. Controller authority: `99df4ed8e820984d69d7b895be8808b892ed7f5f`. Exact clean start: `55ac4c631c69f6edbd275462ad23e4486b9782ed`.

## Runnable workflow

Linux Python3.12; runtime uses only the standard library. Verification environment: Python3.12.3; final task-owned venv pins pytest8.4.2; Ruff0.16.9. No dependency installation, credential or network feed is needed to run:

```sh
python3.12 -m scripts.g1_offline_preview_r1 --fixture long_24h.json --output /tmp/btc-g1_offline_preview_r1/example-long
python3.12 -m scripts.g1_offline_preview_r1 --fixture short_24h.json --output /tmp/btc-g1_offline_preview_r1/example-short
```

Use a fresh output directory or resume the same identical fixture; changing a fixture/genesis is rejected. The two curated JSONs contain invented clocks/prices, explicit local human-token fixtures and 1,455 logical events over24h. No historical data reader exists. Source bars bind completed1m UTC clocks, availability and Last/Mark identity. A descriptive deterministic LLM JSON mock cannot approve. Only a bound, time-valid, one-use trusted human fixture token admits a simulated intent. Entry, TP1, Funding, partial ACK, favorable-only residual stop update, final STOP and ACK produce inspectable WAL, trace logs, immutable checkpoints, a local JSONL Feishu outbox and `RECEIPT.json`. Fixtures are not exchange observations or real human identity authentication.

Synthetic LONG end cash is1000.33834810 and SHORT1000.34054750 from initial1000. Each has6 cash effects: entry fee,3 signed Funding settlements and2 ACK-settled tier exits. These numbers are functional accounting checks, not returns evidence or Alpha. The independent Decimal oracle recomputes every effect using literal invented price clocks and independently specified execution ticks; partial proceeds remain unavailable before ACK. Mark is used for valuation/Funding, Last for fills. Mark equity includes a residual fee but excludes hypothetical exit impact; this is diagnostic valuation, not a liquidation guarantee.

Completed bars require STOP > first-completed TIME_CAP > eligible TP1/TP2 before further clock advancement. Missing exit events reject rather than hide losses. TP tiers require a one-tick trade-through or favorable open gap; fills are capped and adverse tick/fee adjusted. Both pending exit ACK orders conserve cash; a residual exit can occur before a prior ACK, but reserve and net proceeds release only against their own causal fill ACK. Funding clock aliases and used fill IDs reject. Original6h cooldown and one-position constraint remain until all obligations close. Synthetic lot0.001/tick0.1/min-notional1 and fee6bp+impact5bp per leg are explicit invented execution proxies.

## Verification and recovery

Final scoped command:

```sh
PYTHONPATH=$PWD/src /tmp/btc-g1_offline_preview_r1/verification-py312-pytest842/bin/python -m pytest -q --tb=short tests/test_v06_g1_offline_preview_r1_*.py
ruff check scripts/g1_offline_preview_r1 tests/test_v06_g1_offline_preview_r1_*.py
python3.12 -m compileall -q scripts/g1_offline_preview_r1 tests/test_v06_g1_offline_preview_r1_*.py
```

Final local result:145 PASS,0 failed,0 skipped;30 real process crash/restarts across15 edges and2 truncated WAL quarantines. Exact counts are in `FINAL_EXECUTION_RECEIPT.json` and `FINAL_PYTEST_JUNIT.xml`; `TEST_TRACEABILITY.json` binds each executed F001–FNN case. Native process tests issue actual `os._exit(91)` at15 critical edges ×2 sides, then resume through CLI. They cover proposal before/after append, analysis fsync, approval checkpoint, place, entry fill, entry ACK, Funding, TP1, partial ACK, stop update, STOP, final ACK and physical outbox delivery. They compare logical event count, cash, journal, state, WAL chain and terminal immutable checkpoint SHA to clean reference. Existing common checkpoint bytes must match; a checkpoint not yet written at process death may be absent. Two separately truncated WAL cases must exit3, quarantine and expose no ready state. Malformed JSON, corruption, future mutation and schema/approval errors have additional focused witnesses.

Durability distinguishes process death from power loss: a complete pre-fsync record surviving process death is recoverable; a torn tail is quarantined, not silently discarded. Checkpoints are immutable and prefix-validated. Local physical outbox delivery is at-least-once; its key permits logical deduplication. An outbox receipt neither changes portfolio nor advances MarketClock and cannot postpone a required exit. Identical WAL event retransmission is a no-op; body drift is fatal. Readiness remains offline only, with event-scoped trace/span IDs and static retry classification.

Zero counters are accepted-state invariants backed by adversarial rejection, an AST import/surface gate and a socket-connect trap: false approvals, runtime private/network calls, duplicate ledger charges, oversize exposure and phantom spendable ACK are all checked. No native syscall tracer is installed, so this report makes no native syscall interception claim. Git/GitHub transport for authorized delivery is separate from the offline runtime.

## Engineering review and delivery

C1 `cf76ef99b47dc91b7f062877679172bacf1d6c9f`, parent the exact start, was pushed and remote-verified after68 preliminary tests. Independent review found correctness gaps; C2 `b792c613cac70324e66f6fb6958ce269f1a55dd1`, parentC1, repaired them and was pushed/remote-verified. C3 `84c4764a2f1c46c81f43b144f5daf1f54cccc5d3`, parentC2, fixes new BE-stop effectiveness so old minute OHLC cannot be used for a retroactive fill. C3's financial transitions remain fixed; C4 adds only static CLI error handling with a separate final source manifest. Review witnesses confirm mandatory exits, funding/fill dedupe, either ACK order, net-BE tick economics and late operational receipt handling. No proven blocker remained in the reviewed reducer paths; this is not a production security certification.

The unchanged repository conftest loads its existing hermetic guards; the final test harness uses the own worktree src path and installed test dependencies. The sidecar runtime never imports those production/research modules.

The final C4 commit records its own frozen source manifest, synthetic receipts, recovery/Decimal proofs and actual GitHub CI status. It also contains the static CLI-error guard. Its exact SHA/parent and remote HEAD verification are returned in the terminal response; a commit cannot embed its own SHA. Only task allowlist paths changed. Old research, P1/production code, CI configuration, Controller files and other worktrees remain untouched.

GitHub CI: C1 andC2 SUCCESS with test execution; C3 FAIL at test step. Its sole sanitized failing identifier is `tests/test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph`, outside task scope and unchanged. No protected values or test body were read; rootcause is uninspected. The repository gate remains FAIL, not silently reclassified green. C4 actual status is returned after push. The existing unmapped-executable rule can select the full repository suite for C2; local scoped success cannot imply a global CI pass. C4 contains a CLI guard, so its implementation CI must execute rather than qualify as docs-only. Manual Python3.11/3.13 compatibility suites remain separately skipped unless explicitly dispatched. Actual job/step status and skips are recorded separately without reading protected research logs or outcomes. No H40 or other old suite is repaired here.

## Limitations and future prerequisites

This single Linux process validates finite synthetic workflow behavior only. Human fixture trust is not authenticated production identity. No real market/account loader, broker, queue/L2 fills, real messaging or LLM adapter is implemented. Hashes detect corruption under the local writer contract; they do not defeat a malicious filesystem writer able to rewrite all history. Power loss, disk loss, untrusted concurrent filesystem changes and distributed recovery are unproven. Late physical outbox deliveries can repeat.

Outstanding G1 production acceptance requires separate Controller review of real identity, custody, deployment, clock/feed and execution contracts. G3 production monitoring/incident response is not accepted by these local health logs. Future G4 requires separate infrastructure, authentic public-source/execution verification and explicit release authority; no follow-on task, protected inspection, Testnet or live use is automatically authorized. G2 remains development-only and the old P1 NO-GO is neither reopened nor merged.

Version audit correction: the original C1 tool-version statement mistakenly labelled the Python3.12 pytest module8.4.2; final interpreter-local inspection found9.0.3. The initial140-case pass is retained as PRE_PIN_PYTEST903 evidence. A separate task-owned venv with pytest8.4.2 satisfies the repository pytest>=8,<9 pin for the final run. Runtime remains stdlib-only, with no repository dependency changes.

Final C4 output-boundary correction: argparse rejects unknown/invalid arguments with a static JSON error, never echoing caller-supplied fake credential values; two regression witnesses assert exit3 and zero state creation. This last commit includes this small CLI guard plus final evidence, so its CI is an implementation run, not a docs-only test skip. Financial reducer, storage and fixtures remain byte-identical to C3. Source file hashes are in C4_FINAL_SOURCE_MANIFEST.json; the final commit cannot embed its own SHA and its verified exact identity is returned separately.
