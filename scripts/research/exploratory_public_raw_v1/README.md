# Public native exploratory bridge v1

This separate package supports offline BTCUSDT Binance USD-M **partial execution-cost
sensitivity** from newly admitted native CSV/ZIP inputs. It never opens old outcome
panels. PR #10 and all historical/P3 routes remain unchanged. No receiver PIT, clean
holdout, Alpha, actual fill, TESTNET, LIVE, or funds authority is conferred.

The shipped `TRUSTED_REGISTRIES` map is empty. There is no real admission, acceptance
writer, self-approval token, environment override, broad auto mode, downloader or
account interface. Synthetic tests inject temporary pins only within their fixtures.
Do not install their fake references as production authority.

## Trust and immutable records

`contract.py` defines the strict schemas. An independent Controller/custodian must
first persist a genuinely accepted scope outside experiment input, raw and output
folders. A separately reviewed deployment pins its **exact file bytes SHA256**,
canonical path, accepting identity and independently verifiable authenticity reference
in `TRUSTED_REGISTRIES`. A hash establishes integrity, not signatory authenticity;
the deployment authority must verify authenticity before installing any pin. This
package cannot perform that human/source attestation or create trusted scope records.

The accepted record binds the content hashes and exact paths of registration and
manifest, output directory, acceptance time, acquisition-time publisher rights and
applicability, named root paths/device/inode, and permitted economics mode. The
registration binds the complete manifest, UTC origins and separate whole-file support,
frozen policy, selection history, and permanent scientific labels. Edits invalidate
acceptance. Changes require a new experiment/acceptance, never retroactive re-pinning
of research outcomes. Deployment must revoke a pin on external source revocation;
removing/changing the persisted scope also blocks execution.

Each exact selected source requires publisher/source identity, SHA256, stat identity,
venue/product/symbol, selected fields, complete native schema, whole-file coverage,
rights-document hash, and accepted UTC event-clock/availability-delay semantics.
Native klines use integer UTC milliseconds, inclusive close = open + 59999ms;
OI `create_time` uses the publisher's naive UTC representation on a 5m grid.
Admission must independently confirm those semantics. These event timestamps and
assumed availability delays **do not establish receiver first-known PIT**.

No glob, root discovery, recursive source scan, protected-root visit, ZIP extraction,
network request or credential lookup occurs. Absolute POSIX paths are explicit
host inputs; no repository configuration depends on this machine. The reader uses
Linux descriptor-relative `O_NOFOLLOW` traversal on every ancestor and final file;
lexical canonical paths with no symlinks consequently equal their real paths. It
rejects traversal, protected components, unsafe links/types/permissions, changed root
or file inodes, missing sources, overlap, changed bytes and output collisions. This
OS security contract must be separately implemented/validated before Windows use;
native Windows success is not assumed. Limits: 200 files, 128MiB total compressed
input, 128MiB expansion per file, 400000 total native rows, 123 days support, 92 days
origins. Existing archives and evidence are never modified.

## Frozen experiment and accounting

X is the 4h log return <= -0.01, using the last completed 1m close at each UTC hour
and its exact 4h predecessor. Optional Z uses native base OI at cutoff and exact
24h/4h predecessors: log changes >= 0.015 / >= -0.005. OI is never forward-filled.
`XZ_common = X AND Z` is a conditional filter, adds no raw trigger timestamps, and
is not the old fitted P1. All masks are computed from feature endpoints and
availability only, before evaluation. `X_full` remains separate from the common
X/XZ population; executed calendars may differ due to per-arm concurrency.

Cutoff HH:00, decision HH:01, exact entry HH:02 open, exit exactly 8h after entry.
Missing exact entry, exit, or any holding minute skips the trade with a reason;
there is no delayed fill. Each arm holds one short at a time. Gross return on unit
entry notional is `(entry_open - exit_open) / entry_open`. Baseline is 8bp aggregate
fees + 8bp aggregate slippage; stress is 8bp fees + 24bp slippage. These are candidate
roundtrip sensitivities deducted on fixed entry notional, not claims about actual
commission tiers or exit-scaled fills. Additive unit-notional returns do not compound.
Drawdown uses closed trades and does not measure intratrade drawdown/liquidation.
Year/regime counts and returns, weekly event counts and nonoverlapping episodes are
reported; nonoverlap never establishes statistical independence.

**Funding is unresolved, never zero.** No independent historical settlement calendar
or exact native calc-time/mark mapping was authenticated by R6-G. This version reads
admitted funding/mark files for native QA only, preserves millisecond offsets and
never snaps to assumed 8h slots. It rejects `VERIFIED_SETTLEMENTS` and any complete
net-PnL request before source reads. Installing a clock adapter requires a separately
reviewed implementation plus independently verified full calendar, sign, boundaries,
corrections and exact marks. Merely adding plausible calendar text to experiment
inputs cannot enable funding. Partial outputs keep funding and modeled net null,
`COST_INCOMPLETE` and `COST_UNVALIDATED_REAL_FILL`.

## Explicit offline CLI

Create registration/manifest metadata and an empty output directory first. After
independent admission and deployment of a real pin, invoke:

```sh
python3 -m scripts.research.exploratory_public_raw_v1 \
  --registration /accepted/experiment/registration.json \
  --manifest /accepted/experiment/manifest.json \
  --accepted-registry-id externally-installed-id
```

With the shipped empty trust map this exits 2 before even reading experiment inputs.
Successful partial-mode execution rechecks acceptance and source identity/bytes
before exclusive immutable publication of the ten named artifacts in `OUTPUTS`.
`HASH_MANIFEST.json`, written last, is the completion marker and hashes the other
nine artifacts (not itself). A crash may leave an incomplete output directory;
preserve it and use a new explicitly accepted output directory for a retry.

## Validation

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. pytest -q --import-mode=importlib \
  tests/research/exploratory_public_raw_v1 \
  tests/research/exploratory_retrospective_v1
ruff check scripts/research/exploratory_public_raw_v1 tests/research/exploratory_public_raw_v1
```

All tests generate inputs beneath temporary `/tmp` directories and audit payload
opens; the new tests prohibit network/subprocess interfaces. Never substitute an
inherited real fixture. No legacy gates, tests or CI policy are changed. Repo-wide
Ruff has an inherited measured baseline of 113 findings; report changed-path and
baseline-versus-head delta separately, without claiming repository-wide lint PASS.
