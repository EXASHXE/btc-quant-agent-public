# Task Prompt — Forward Evidence Health Lightweight Runtime Acceptance

## Repository

```text
EXASHXE/btc-quant-agent
```

## Purpose

Perform a runtime acceptance of the emergency Forward Evidence health-resource fix.

This is an acceptance/verification task, not a redesign task.

Do not modify H40, research semantics, discovery/backtest behavior, or protocol authority.

---

# Expected implementation under test

Local branch:

```text
forward-evidence-health-lightweight
```

Expected local commit:

```text
743c936e6fcb93346435c99bc00abd0b4f69c969
```

Expected commit message:

```text
fix(forward-evidence): make health check lightweight read-only and bound daemon memory
```

Important remote-state note:

At prompt-authoring time, GitHub did NOT yet contain the above commit or branch.

Therefore the first step is to verify the exact local repository state.

Do not silently test a different commit.

---

# Preflight

Run:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git show --stat --oneline 743c936e6fcb93346435c99bc00abd0b4f69c969
git diff --stat <parent-of-743c936>..743c936e6fcb93346435c99bc00abd0b4f69c969
```

Confirm:

```text
branch = forward-evidence-health-lightweight
HEAD   = 743c936e6fcb93346435c99bc00abd0b4f69c969
```

If HEAD differs:

- stop;
- report exact mismatch;
- do not reinterpret the task against another commit.

If the branch/commit exists locally but not on origin, that is acceptable for runtime validation.

---

# Known root causes addressed by the implementation

The patch claims to fix:

1. `quantctl forward-evidence health` incorrectly executing the deep historical audit path.
2. Full historical microstructure partition scanning over roughly 35 GB.
3. Full-table in-memory subtraction in `OpportunityForwardStore.unresolved()`.
4. Unbounded websocket bootstrap depth-event buffering in `MicrostructureStore.depth_loop()`.

Expected architectural separation:

```text
health
  -> lightweight, bounded, read-only runtime probe

status / audit / doctor
  -> deep historical / integrity inspection
```

---

# Acceptance scope

Verify the implementation in the real local runtime/data environment.

Do NOT alter production/research data.

Do NOT run H40 discovery, backtest, walk-forward, confirmation, H39 unblind, or execution.

---

# Acceptance Test A — One-shot health behavior

Run:

```bash
/usr/bin/time -v .venv/bin/quantctl forward-evidence health
```

Capture at minimum:

- exit code;
- elapsed wall-clock time;
- maximum resident set size;
- user CPU time;
- system CPU time;
- resulting JSON state.

Acceptance target:

```text
wall time: normally < 2 seconds
peak RSS:  < 128 MiB preferred
           < 256 MiB hard acceptance ceiling
no background process left behind
```

A DEGRADED/UNHEALTHY health state is not itself a performance failure if it truthfully reflects runtime service state.

The command must terminate.

---

# Acceptance Test B — Process cleanup

Before and after health execution inspect:

```bash
pgrep -af "quantctl forward-evidence health" || true
ps -eo pid,ppid,rss,%cpu,etime,cmd | grep -E "quantctl|forward-evidence" | grep -v grep || true
```

Acceptance:

- no orphan health process;
- no child worker/thread process remains after command exit;
- no process continuously consumes CPU as a side effect of the health probe.

---

# Acceptance Test C — Repeated execution stability

Run at least 100 sequential health checks.

Example:

```bash
for i in $(seq 1 100); do
  .venv/bin/quantctl forward-evidence health >/dev/null || rc=$?
done
```

Measure aggregate elapsed time and sample process/system memory before and after.

Where practical, also collect per-run maximum RSS for a smaller repeated sample using `/usr/bin/time -v`.

Acceptance:

- no monotonic RSS growth across invocations;
- no persistent child processes;
- no accumulation of temporary files/WAL/SHM sidecars caused by health;
- average runtime remains bounded;
- repeated runs do not progressively slow down.

---

# Acceptance Test D — Read-only store behavior

Verify that running health does not mutate forward stores.

Inspect before/after metadata for:

```text
data/forward/BTCUSDT/derivatives.sqlite3
data/forward/BTCUSDT/opportunity_shadow.sqlite3
data/forward/BTCUSDT/microstructure/
```

Check:

- database mtime where meaningful;
- WAL/SHM sidecars;
- file counts;
- latest partition hashes/mtimes where practical.

Health must not:

- initialize/migrate schemas;
- checkpoint or write SQLite state;
- append observations/outcomes;
- modify historical microstructure partitions.

If a non-empty WAL requires fail-closed read-only behavior, preserve that design rather than forcing recovery from health.

---

# Acceptance Test E — Deep path separation

Verify that:

```text
forward-evidence health
```

uses the new lightweight path.

And that:

```text
forward-evidence status
forward-evidence audit
forward-evidence doctor
```

retain deep inspection semantics.

Do not require deep commands to meet the health latency/RSS budget.

The fix must not achieve low RSS by silently deleting deep-audit checks from the commands where they belong.

---

# Acceptance Test F — Microstructure bounded inspection

Verify by code inspection and targeted tests that health reads only the configured bounded latest-partition window, expected:

```text
LATEST_TWO_PARTITIONS
```

It must not recursively inspect all historical microstructure partitions.

On the production data root, confirm health runtime does not scale with the full ~35 GB historical archive.

---

# Acceptance Test G — Opportunity unresolved SQL path

Verify `OpportunityForwardStore.unresolved()` no longer performs:

```text
self.observations()
self.outcomes()
Python set subtraction over full tables
```

Confirm it uses a SQL anti-join / LEFT JOIN query and returns only pending mature observations.

Where safe, compare the new SQL result against the old logical semantics on a small synthetic fixture.

Do not load the full production table into Python merely for acceptance.

---

# Acceptance Test H — Depth bootstrap buffer bound

Inspect and test `MicrostructureStore.depth_loop()`.

Verify:

- obsolete events are pruned after SequenceGap/snapshot reconciliation;
- the temporary bootstrap buffer is bounded;
- prolonged REST failure / websocket input cannot grow `buffered` without limit.

Exercise this with synthetic mocked events/network failures only.

Do not induce an outage against production services.

---

# Quality gates

Run:

```bash
ruff check .
mypy
pytest -q
python -m compileall -q src skill-template/scripts
```

Expected baseline from implementation report:

```text
pytest: 1220 passed, 8 warnings
```

If the exact count differs because unrelated tests changed locally, explain the delta.

---

# Runtime benchmark comparison

Record a compact before/after table using the known pre-fix observation and your measured post-fix values.

Known pre-fix:

```text
RSS:        ~3 GB
CPU:        ~75%
wall time:  >30 s / effectively hanging
micro scan: all historical partitions (~35 GB)
```

Do not fabricate post-fix values. Measure them on this machine.

---

# Git / branch handling

This acceptance task must not merge the emergency fix into `v0.5-refactor`.

If and only if:

- exact local commit 743c936... is verified;
- runtime acceptance passes;
- quality gates pass;

then push the existing implementation branch:

```bash
git push -u origin forward-evidence-health-lightweight
```

Do not squash/rebase/amend the tested implementation commit after acceptance measurements.

If additional code changes are required, acceptance FAILS for 743c936... and a new repair commit must be created and reviewed separately.

---

# Required acceptance report

Return:

```text
verdict: PASS / FAIL

tested branch
tested exact commit SHA

health exit code
health reported state
wall-clock time
peak RSS
CPU observation

100-run repeated execution result
orphan-process result
read-only mutation check result
microstructure bounded-scan result
opportunity SQL result
depth buffer bound result

ruff result
mypy result
pytest result
compileall result

remote push status
remote branch URL if pushed

any remaining risk
```

## PASS state

Only if all acceptance conditions hold:

```text
FORWARD_EVIDENCE_HEALTH_LIGHTWEIGHT_RUNTIME_ACCEPTED
READY_FOR_CONTROLLED_INTEGRATION
H40_UNCHANGED
RESEARCH_SEMANTICS_UNCHANGED
EXECUTION_UNCHANGED
```

Do not merge into v0.5-refactor in this task.
