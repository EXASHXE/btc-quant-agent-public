# Current architecture — v0.5 R01

## One current research authority

```text
explicit versioned formal job
  -> quantctl backtest / research / replay OR tools/run_formal_research.py
  -> formal_research.run_formal_job_file / run_formal_job
  -> accepted P5/P6 economic kernel and bound signal/input evidence
  -> canonical candidate run, benchmark suite, qualification
  -> cold semantic replay verification and immutable publication
  -> optional explicit validated P5 registry phase
```

`economic/` owns fills, fees, funding, ledger, benchmarks, random/CASH replay
and qualification. `research_contract/` owns canonical identity and registry
authority. `formal_research.py` is the consumer facade, not another simulator.
These accepted owners and publication/storage semantics are frozen in R01.
An engineering catalog, diagnostic R result or relabeled historical payload
cannot bypass these owners or acquire promotion authority.

Formal commands require `--job` and `--output`, dispatch before operational
service construction, and never fall back to CSV or removed legacy runners.
Protocol/evidence identity, closed/available candle requirements and cold
verification remain mandatory. Registry decisions are opt-in; failure is closed.

## Separate protected science and operations

H39 retains its own protocol, freeze/blindness manifests, source and gate tools.
`microstructure_research.py` and relevant `deliverables/v0.3.22+` remain protected;
R01 does not run or reinterpret them. Final Holdout stays sealed.

Forward data stores and their frozen campaign/epoch registries remain separate
operational data-quality authority, not generic formal qualification. Their
versioned configs are retained because current code and guards machine-read them.

`service.py`, `api.py`, runtime scanning and execution remain independently gated.
Defaults remain `DISABLED`, `auto_execute=false`, `allow_live=false`.
The legacy performance reader remains explicitly diagnostic-only and read-only.

## Deliberately retained leaves

`data/funding.py` and `data/resample.py` provide neutral data primitives.
`backtest.py` still supplies compatibility leaves and protected contrast tests;
`mechanism_research.py` still supplies the historical development/holdout firewall
and imports development boundaries/diagnostic summaries from `research.py`.
They are not peer current research entrypoints. Their split is deferred rather
than weakening a guard or altering scientific identity to delete more lines.

Historical strategy/symbolic owners and exclusively coupled runners/configs/tests
are deleted, not relocated to a new archive. Forward evidence lineage and an
independent older design document remain deferred where a safe authority split
has not been established. Current use follows this document and the README,
not historical design proposals.

## Engineering validation and lineage

Run the full Ruff, mypy, pytest, coverage, compileall and whitespace gate from the
README in a fresh editable `.[dev,research]` environment before first push.
CI validates exact HEAD on Python 3.11/3.12/3.13. Protected economic/adversarial,
H39, holdout, execution and hermetic-runtime guards are retained.

`tools/catalog_surfaces.py` reports actual tracked paths, parser leaves, API
routes and resolved static import consumers. It reads code/metadata only, with
stdout as its default destination; it does not create a reviews tree on this
branch. Historical inventory/report outputs belong on `v0.5-refactor-docs`.

R01 implementation is pending fresh independent review. Alpha research and R02
are not part of this task.
