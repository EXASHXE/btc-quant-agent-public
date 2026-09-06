# BTC Quant Agent v0.3.25 — Acceptance Repair: Committed Freeze Boundary, Exactly-Once Unblind, and WAL-Safe Evidence Snapshot

Repository:

```text
EXASHXE/btc-quant-agent
```

Stage branch:

```text
agent/v0.3.25-h39-one-shot-unblind-preregistration
```

Accepted baseline on `main`:

```text
e99964a3ced0c40424a4ace6dd59cc2376a2dea6
```

Existing v0.3.25 lineage:

```text
04d1ea87827e7645bbcb2481f2dbf9fff4473b94  preregistration prompt
1a439f9ed18fa6f0b7ee499816595744c09adbf3  implementation
45c9e2d7779338e2064879e83c2859771bd2ce48  lint/style repair
bcf259c890c0ad75660868c865e1d6daeda7b1bc  reviewed implementation SHA
56d03ad4ad42a0584f3a834e9152eb5603833b38  Gemini one-pass audit
```

Gemini already consumed the single v0.3.25 audit at `56d03ad...` and reviewed exact implementation SHA `bcf259c...` with `PASS_WITH_NONBLOCKING_FOLLOWUPS`.

ChatGPT final acceptance found protocol-level gaps in the future one-shot execution boundary. Therefore:

```text
v0.3.25 = REPAIR_REQUIRED
```

This is an acceptance repair only. Do not reopen H39 scientific design, M1-M8, horizons, signs, statistics, sample gates, or safety invariants.

No second Gemini audit is required for this repair. After implementation, stop at an exact repair SHA and hand it directly to ChatGPT for final acceptance.

---

## 0. Preserve all frozen science and safety

Keep unchanged:

```text
hypothesis = H39_MICROSTRUCTURE_DIRECTIONAL_INFORMATION
validation_start = 2026-09-04T11:15:00Z
primary horizon = 60m
secondary horizon = 240m supporting only
formal feature universe = M1-M8 exactly
predefined signs = frozen
Holm-Bonferroni FWER alpha = 0.05
minimum distinct UTC days = 14
minimum eligible observations = 750
minimum eligible-boundary coverage = 90%
```

Keep safety unchanged:

```text
strategy = EXPERIMENTAL
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
live trading = NOT AUTHORIZED
final_holdout = SEALED
```

H38 remains permanently `DATA_QUALITY_TERMINAL_ARCHIVE`.

Do not run real H39 one-shot validation during this repair because current H39 readiness is still false.

---

# 1. Finding A — Freeze artifact is not required to be committed before labels

The frozen v0.3.25 prompt requires:

```text
Only after the freeze artifact is committed may the one-shot process construct real validation outcomes.
```

Current implementation permits:

```text
create_freeze_manifest(...)
-> immediately execute_one_shot_unblind(...)
```

without proving that the exact freeze manifest bytes were committed to Git first. Existing synthetic tests also exercise this uncommitted flow.

This defeats the intended immutable pre-label audit boundary.

## Required repair

Before any validation outcome/candle/label read in `one-shot-unblind`, verify all of the following:

1. The supplied freeze manifest path is tracked by Git.
2. The exact on-disk freeze manifest bytes equal the blob committed in Git.
3. The commit containing that exact freeze blob is identifiable as `freeze_commit_sha`.
4. `freeze_commit_sha` is an ancestor of the current execution HEAD.
5. The freeze file has no staged or unstaged modifications relative to the committed blob.
6. The freeze commit predates the one-shot execution start.
7. Any failure occurs before `get_canonical_1m_candles()`, any outcome construction, any label materialization, or any formal statistical function.

Do not rely on a user-provided `freeze_commit_sha` flag. Resolve and verify it from Git state.

A valid implementation may use deterministic read-only Git subprocesses such as:

```text
git ls-files --error-unmatch <freeze-path>
git status --porcelain -- <freeze-path>
git log -n 1 --format=%H -- <freeze-path>
git show <freeze_commit_sha>:<repo-relative-freeze-path>
git merge-base --is-ancestor <freeze_commit_sha> HEAD
```

or an equivalently strict mechanism.

The result artifacts must record:

```text
freeze_manifest_sha256
freeze_commit_sha
freeze_blob_verified = true
freeze_commit_is_ancestor = true
```

Do not require the freeze manifest to contain its own future commit SHA; that is circular. Instead, verify the commit externally and record `freeze_commit_sha` in the execution receipt/results.

---

# 2. Finding B — No exactly-once enforcement exists

The frozen prompt requires formal unblind to execute exactly once for a frozen cutoff.

Current implementation can rerun the same `one-shot-unblind --freeze-manifest ...` repeatedly and overwrite/recreate result artifacts.

## Required repair

Implement a durable, fail-closed single-use execution identity.

Define a deterministic execution key, for example:

```text
execution_key = SHA256(
    freeze_manifest_sha256
    + freeze_commit_sha
    + unblind_cutoff_ms
    + frozen_protocol_hash
    + frozen_clarification_hash
)
```

Persist it in a dedicated research execution registry separate from the blind evidence ledger, e.g.:

```text
data/research/h39_validation/h39_one_shot_execution_registry.sqlite3
```

or an equivalently durable store.

Required semantics:

```text
BEFORE labels are loaded:
  atomically reserve execution_key with state = STARTED

if execution_key already exists in STARTED or COMPLETED:
  refuse with H39_ONE_SHOT_ALREADY_CONSUMED

on successful artifact completion:
  transition exactly that key to COMPLETED

if process crashes after STARTED:
  remain fail-closed
  do NOT automatically retry or clear the record
  require a future explicit governance repair, not a force flag
```

Do not add:

```text
--force
--retry-unblind
--reset-execution
--override
--ignore-consumed
```

The execution registry must record at minimum:

```text
execution_key
freeze_manifest_sha256
freeze_commit_sha
unblind_cutoff_ms
protocol_hash
clarification_hash
started_at_utc
completed_at_utc
state = STARTED | COMPLETED
result_manifest_sha256 when completed
exact executing Git SHA
```

A second invocation for the same frozen evidence identity must fail before labels are loaded.

---

# 3. Finding C — WAL-safe ledger identity

`H39BlindLedger` uses:

```text
PRAGMA journal_mode = WAL
```

Current freeze code hashes only the live main `.sqlite3` file. A file hash of the main database alone is not a sufficiently explicit logical-state identity when WAL state/concurrency may exist.

## Required repair

At legitimate readiness/freeze time, create a consistent read snapshot using SQLite's online backup API before labels are read.

Recommended artifact:

```text
data/research/h39_validation/frozen/H39_ONE_SHOT_LEDGER_SNAPSHOT_<cutoff>.sqlite3
```

Requirements:

1. Use `sqlite3.Connection.backup()` or equivalent consistent SQLite snapshot mechanism.
2. Verify snapshot with `PRAGMA integrity_check`.
3. Record row counts and eligible row counts in the snapshot.
4. SHA-256 the completed snapshot file.
5. Include snapshot path/name and SHA-256 in freeze metadata.
6. Future one-shot execution reads validation feature/baseline rows from this frozen snapshot, not the mutable live blind ledger.
7. The snapshot itself must be included in the freeze evidence identity and must not be modified after freeze.
8. Source partition hash verification remains mandatory.

The freeze manifest must retain/live-report the live ledger provenance as useful metadata, but the authoritative one-shot evidence identity must include a consistent snapshot hash.

At execution, verify the frozen snapshot SHA before any label read.

Do not issue destructive WAL checkpoints against the live blind ledger merely to make hashing convenient.

---

# 4. Finding D — Readiness artifact/hash missing from freeze manifest

The original v0.3.25 prompt explicitly requires:

```text
readiness artifact/hash
```

in the immutable one-shot freeze evidence.

## Required repair

When readiness first legitimately passes, serialize the exact authoritative readiness result used for authorization to a deterministic machine-readable artifact, e.g.:

```text
deliverables/v0.3.25/H39_ONE_SHOT_UNBLIND_READINESS.json
```

The freeze manifest must record:

```text
readiness_artifact_path
readiness_sha256
readiness_status = H39_READY_FOR_ONE_SHOT_UNBLIND
ready_for_unblind = true
```

The readiness artifact must include the exact wall-clock/as-of cutoff, expected/observed/eligible counts, coverage, distinct days, integrity result summary, protocol/clarification hashes, and safety firewalls.

Before one-shot execution, verify the readiness artifact hash against the committed freeze evidence before labels are loaded.

If readiness remains false, do not create a fake readiness-pass artifact and do not create a freeze artifact.

---

# 5. Freeze package and commit boundary

At true maturity, the intended workflow must become:

```text
A. authoritative readiness passes
B. create deterministic readiness artifact
C. create consistent frozen ledger snapshot
D. create freeze manifest binding:
     cutoff
     readiness hash
     snapshot hash
     source partition hashes
     protocol/clarification hashes
     pre-freeze implementation SHA
E. STOP — no labels read yet
F. user/agent commits the freeze package to Git
G. one-shot-unblind verifies exact committed freeze blob + ancestor relation
H. atomically reserves exactly-once execution_key
I. only now load real validation labels/outcomes
J. run fixed formal analysis once
K. write immutable result artifacts and mark execution COMPLETED
```

The CLI may expose separate commands such as:

```text
quantctl h39 freeze-cutoff ...
quantctl h39 one-shot-unblind --freeze-manifest ...
```

but `freeze-cutoff` must never automatically call `one-shot-unblind`.

If desired, `freeze-cutoff` may print an explicit machine-readable state:

```text
FREEZE_CREATED_AWAITING_GIT_COMMIT
```

It must not imply formal validation has run.

---

# 6. Committed freeze verification must be pre-label

Add an explicit internal boundary such as:

```python
verify_committed_freeze_package(...)
reserve_one_shot_execution(...)
# only after both succeed:
load_validation_outcomes(...)
```

Tests must prove that failure in either of the first two steps prevents the outcome loader from being called at all.

Use mocks/spies if necessary.

---

# 7. Exactly-once result immutability

Result artifacts must not silently overwrite an existing completed execution for the same execution key.

On successful one-shot completion, write a compact execution receipt, e.g.:

```text
deliverables/v0.3.25/H39_ONE_SHOT_EXECUTION_RECEIPT.json
```

containing:

```text
execution_key
freeze_manifest_sha256
freeze_commit_sha
frozen_ledger_snapshot_sha256
readiness_sha256
unblind_cutoff_ms
executing_git_sha
started_at_utc
completed_at_utc
scientific_verdict
result_artifact_hashes
```

The execution registry and receipt must agree.

Do not allow an existing COMPLETED receipt to be overwritten by another run.

---

# 8. Preserve cutoff and formal statistics

Do not change the existing formal procedure except where necessary to read from the frozen snapshot instead of the mutable live ledger.

Keep:

```text
validation_start_ms <= decision_close_ms <= unblind_cutoff_ms
eligible = true
reference_time_ms = decision_close_ms + 60_000
60m target = reference_time_ms + 59*60_000
240m target = reference_time_ms + 239*60_000
M1-M8 exactly
one-sided predefined signs
Holm-Bonferroni across all 8 arms
fixed baseline trio
fixed L2 logistic lambda=1.0
240m supporting only
no runtime promotion
```

Do not use this repair to tune candidate gates or inspect real H39 performance.

---

# 9. Required regression tests

Retain all existing v0.3.25 tests and add at least:

### A. Uncommitted freeze cannot unblind

```text
create freeze package locally
DO NOT git commit it
call one-shot-unblind
=> refuse before label loader is invoked
```

### B. Dirty freeze cannot unblind

```text
commit freeze
modify manifest bytes afterward
call one-shot-unblind
=> refuse before labels
```

### C. Exact committed blob is required

```text
commit freeze manifest
verify git blob bytes == on-disk bytes
=> committed-freeze verification passes
```

### D. Freeze commit must be ancestor

Use a synthetic git repo/branch state showing a freeze commit not ancestral to execution HEAD.

```text
=> refuse before labels
```

### E. Exactly-once reservation

```text
first execution identity => STARTED reservation succeeds
second reservation same identity => H39_ONE_SHOT_ALREADY_CONSUMED
```

### F. Completed execution cannot rerun

```text
registry state COMPLETED
same freeze identity invoked again
=> refuse before labels
```

### G. Crash fail-closed

```text
registry state STARTED from prior interrupted run
same identity invoked again
=> refuse; no auto reset
```

### H. WAL-safe snapshot

Create a WAL-mode blind ledger with committed logical rows, build the freeze snapshot using SQLite backup, then verify:

```text
snapshot integrity = OK
snapshot row count == logical ledger row count at freeze
snapshot SHA pinned
one-shot reads snapshot
```

Do not rely on the main `.sqlite3` file hash alone as the logical snapshot identity.

### I. Readiness artifact hash

Tamper with committed readiness artifact after freeze:

```text
=> one-shot refuses before labels
```

### J. Label-loader ordering

Mock/spy outcome/candle loading:

```text
uncommitted freeze -> loader call count = 0
dirty freeze -> loader call count = 0
consumed execution key -> loader call count = 0
valid committed unused freeze -> loader may be called
```

### K. No real unblind during current repair

Current real H39 state remains below maturity. Deliverables produced during this repair must contain no real validation p-values, effects, ranks, directions, or candidate performance.

---

# 10. Existing tests requiring correction

The current synthetic test pattern:

```text
create_freeze_manifest(...)
execute_one_shot_unblind(...)
```

without a Git commit in between is no longer valid.

Refactor synthetic end-to-end tests to use a temporary Git repository or another hermetic committed-freeze fixture so the test proves the actual governance boundary.

Do not weaken production committed-freeze verification merely to keep old tests convenient.

---

# 11. CI and quality

Require exact repair SHA green on:

```text
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src skill-template/scripts
```

GitHub Actions Python matrix:

```text
3.11
3.12
3.13
```

all SUCCESS.

---

# 12. Deliverables

While current real H39 readiness remains false, update/create only preregistration/repair metadata, for example:

```text
deliverables/v0.3.25/V0.3.25_COMMITTED_FREEZE_EXACTLY_ONCE_REPAIR.json
deliverables/v0.3.25/V0.3.25_COMMITTED_FREEZE_EXACTLY_ONCE_REPAIR.md
```

These must explicitly state:

```text
scientific_state = FORWARD_DATA_INSUFFICIENT
real_one_shot_executed = false
real_validation_labels_loaded = false
real_validation_performance_artifacts_created = false
```

Do not create a fake `H39_ONE_SHOT_UNBLIND_FREEZE.json` for current immature real evidence.

---

# 13. Governance handoff

After repair:

1. Stop editing.
2. Push the exact repair SHA to:

```text
agent/v0.3.25-h39-one-shot-unblind-preregistration
```

3. Report:

```text
exact repair SHA
CI run ID
Python 3.11/3.12/3.13 status
number of tests
confirmation real H39 one-shot was NOT executed
confirmation no real validation labels/performance were exposed
```

4. Do NOT ask Gemini for another v0.3.25 audit.
5. Hand the exact repair SHA directly to ChatGPT for final acceptance.
6. Do not merge to `main` until ChatGPT accepts the repair.

---

# 14. Acceptance criteria

ChatGPT may accept v0.3.25 only when all are true:

```text
[ ] readiness remains authoritative and wall-clock based
[ ] no labels before readiness
[ ] no labels before exact freeze package is committed
[ ] committed freeze blob is verified against Git
[ ] freeze commit is ancestor of execution HEAD
[ ] readiness artifact/hash is bound into freeze evidence
[ ] WAL-safe consistent ledger snapshot is bound into freeze evidence
[ ] exactly-once execution key is durably reserved before labels
[ ] duplicate/STARTED/COMPLETED executions fail closed
[ ] no force/reset bypass exists
[ ] one-shot reads frozen snapshot, not mutable live ledger
[ ] current real H39 remains FORWARD_DATA_INSUFFICIENT
[ ] no real one-shot run occurred during repair
[ ] all frozen H39 scientific definitions unchanged
[ ] safety invariants unchanged
[ ] CI green on Python 3.11/3.12/3.13
```

This repair is about making the future H39 unblind genuinely preregistered, immutable, and one-shot. It is not permission to accelerate the evidence clock or inspect H39 performance early.
