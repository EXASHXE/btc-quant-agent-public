# Exploratory retrospective without a holdout claim — v1

Task: `V065-GOV-EXPLORATORY-RETROSPECTIVE-IMPL-01`.
Contract authority: [Issue #9](https://github.com/EXASHXE/btc-quant-agent-public/issues/9).
Mode: `EXPLORATORY_RETROSPECTIVE_NO_HOLDOUT_CLAIM`.
Schema: `quant.v065.exploratory-retrospective-no-holdout-claim.v1`.

## Status and authority

This is isolated implementation and synthetic-only verification. The mode is
disabled by default. It has no real-source adapter, evaluator, backtest, outcome
loader, panel materializer, network client, trading client or production hook.
`runner.execute()` always rejects execution. No existing P3 CLI imports this
package. A passing structural check confers no owner approval, source rights,
source/PIT admission, historical evaluation or promotion permission.

The sole CLI operation is an explicit artificial self-check:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 -m scripts.research.exploratory_retrospective_v1 --synthetic-self-check
```

This generates one fixed artificial coordinate in a fresh temporary directory,
checks it, publishes a structural receipt there and removes the temporary files.
It accepts no caller-supplied input/output path, scope, signer or trust catalog.
Without the flag, or with research/data-path arguments, the CLI fails closed.
The synthetic timestamps and simulated acceptance pins are test facts only;
they are never presented as real human decisions or historical provenance.

## Registration and separate acceptance

Registration alone is never authorization. Validation needs a pre-existing,
unique experiment ID and version pinned by its SHA-256 in an independently
provided immutable `Trust.registrations` catalog. Duplicate experiment IDs,
including alternative versions under the same ID, fail closed. A changed
hypothesis, feature, parameter, manifest, output path or label changes the hash
and invalidates the registration. A new experiment requires a new ID.

A separate `Trust.acceptances` entry pins the complete scope digest and exact
UTC acceptance time, later than registration and no later than verification.
There must be exactly one matching entry. Scope mutation invalidates acceptance.
These frozen tuples are a structural trust boundary, not a signature scheme or
human-identity authenticator. Never derive a real trust catalog from caller
claims. This implementation constructs catalogs only for its artificial fixture;
there is no real authority ingestion, persistent registration service or approval
workflow. A future real route requires a separately authorized, authenticated,
durable registry and acceptance integration, with separate implementation review.

Canonical hashes use ASCII JSON, sorted keys, compact separators, no NaN or
Infinity, followed by one newline. Metadata APIs accept already decoded objects;
there is no on-disk metadata parser or recursive discovery. All contract objects
have exact key sets. Unknown top-level operation or claim fields are rejected.

## Exact bounded contract

`registration` requires all of:

| Field | Contract |
| --- | --- |
| `schema`, `mode` | Exact constants above |
| `experiment_id`, `version` | Nonempty identity, independently pinned and unique |
| `hypothesis`, `falsification` | Explicit falsifiable proposition and rejection condition |
| `registered_at` | Exact UTC `YYYY-MM-DDTHH:MM:SSZ` |
| `windows` | Exactly `source`, `feature`, `entry`, `exit`, `settlement`, each a nonempty half-open UTC interval |
| `features`, `parameters` | Nonempty feature definitions and frozen parameter mapping |
| `entry_rule`, `exit_rule`, `settlement_rule` | Explicit frozen definitions, including missingness/fill assumptions where applicable |
| `outcome_horizon_seconds` | Positive integer, at most 366 days; exit interval equals entry interval shifted by this horizon |
| `cost_assumptions` | Exactly `fees`, `slippage`, `funding`, `borrow`, `fill_policy`; unknown costs are explicit nulls |
| `manifest_sha256` | Exact complete source manifest digest |
| `output_path` | Exact isolated fresh receipt file, under the accepted output root |
| `labels` | Exactly the immutable result claims below |

Every role interval lies within the source envelope; feature data ends no later
than the first entry; settlements are bounded by the entry/exit envelope. These
are structural timestamps, not evidence of receiver-first-known availability.
Exact old private-partition exclusion dates are deliberately not required by
this schema. Do not invent them. Existing P3 exclusion requirements remain intact.

`scope` requires exactly `schema`, `mode`, `registration_sha256`,
`manifest_sha256`, `input_paths`, `output_path`, `purpose`.
Purpose must be `STRUCTURAL_SYNTHETIC_ONLY`. Its ordered exact input paths must
equal the manifest paths, with no duplicates, and its output must equal registration.

`manifest` requires exactly `schema` and `sources` (1–8 explicit files).
Each source requires exactly `path`, `root`, `classification`, `identity`,
`sha256`, `size`, `file_signature`. Identity explicitly binds source, venue,
product, symbol, field list and rights. The signature binds device, inode, size,
mtime-nanoseconds and ctime-nanoseconds at synthetic acceptance.

The current implementation accepts only explicitly classified `SYNTHETIC_RAW`
roots strictly beneath `/tmp`, the fixed generated identity/rights in
`contract.IDENTITY`, and the exact SHA-256/size of `ARTIFICIAL_BYTES`. No real
source identity, market venue/product, claimed rights or arbitrary file hash
can be admitted. The check API is an internal synthetic verification primitive;
arbitrary in-process Python code capable of constructing its own trust objects
is outside this authority boundary. The CLI never accepts such objects.

## File and publication boundary

All metadata, paths and claims are checked before source descriptors open.
No arbitrary recursive discovery or date-only denylist is used. Raw path spelling
rejects traversal, relative paths, aliases, backslashes and NULs. Denied path
components include protected/private archives, credentials, panels, labels,
returns, A-line, Final, Forward, OOS, holdout and H39/H40/H41 artifacts.
Names alone do not grant authority: exact roots, identity, paths, hashes and
synthetic payload restrictions are all required.

POSIX access traverses every ancestor using directory descriptors and
`O_NOFOLLOW`; payloads must be single-link regular files, of exact bounded size.
Before any payload read, stat metadata must match acceptance. The opened
descriptor must match that stat, and both descriptor/path metadata are rechecked
after hashing. Symlinks, ancestor symlinks, hardlinks, FIFOs, directories, missing
files and changed files fail closed. Unsupported platforms fail closed;
Windows support is not claimed and no repository configuration is changed.

Checked metadata is stored as immutable canonical bytes. Before publication,
all gates, file signatures and payload hashes are checked again. Output roots
must be disjoint from input roots. Existing files, directories and dangling
symlinks are rejected. Receipt creation is exclusive and descriptor-relative,
with mode 0600; no overwrite or symlink following occurs. A write failure may
leave an incomplete fresh receipt; it must not be treated as acceptance and
must never be automatically overwritten. This is not a transactional lock over
external writers: checks authenticate snapshots at check time. No real execution
is available, and hostile concurrent writers are not granted authority.

## Result claims and forbidden operations

Every result carries exactly these claims; no caller-provided result body is
accepted and no outcomes or net economics are calculated:

```json
{
  "classification": "EXPLORATORY",
  "holdout_relationship": "UNKNOWN_OR_POSSIBLE_OVERLAP",
  "selection_status": "SELECTION_CONTAMINATED_OR_UNKNOWN",
  "pit_status": "PIT_UNKNOWN",
  "cost_status": "COST_INCOMPLETE",
  "source_status": "SOURCE_NOT_ADMITTED",
  "authority": "SYNTHETIC_STRUCTURAL_CHECK_ONLY",
  "promotion": "BLOCKED",
  "complete_net_pnl": false,
  "real_execution_enabled": false
}
```

Never upgrade these results to OOS, untouched, independent, forward-only or
holdout-clean. Unknown PIT and incomplete costs persist even if a synthetic
fixture supplies more metadata. Formal P3, confirmatory validation, Alpha,
TESTNET, LIVE, orders and real-funds operations remain blocked.

No protected outcomes, private labels, private credentials or protected archives
may be read. No market-data acquisition, research/backtest execution or outcome
panel materialization is authorized. Any future separately accepted exploratory
evaluation must derive new outcomes solely from explicitly allowlisted raw
sources; it must never reuse the existing P3 outcome panel. Future confirmation
requires separate authority and an appropriate design. Where old boundaries
cannot be authenticated, a prospective period may be considered only after
candidate/protocol freeze; this implementation authorizes neither route.

## Verification and preservation

Focused tests live only in `tests/research/exploratory_retrospective_v1/` and
generate artificial temporary fixtures. They cover every Issue #9 negative gate,
positive structure without authority, immutable snapshots, exclusive output and
identical-byte source replacement. An autouse audit instruments POSIX and Python
payload opens and rejects any read outside that test's fresh artificial directory;
it asserts zero forbidden attempts, protected payload reads and real-label reads.

Existing `historical_tlob_dev`, `historical_p3_synthetic_v1`, `exposed_dev_bridge`,
cross-venue path policy, production gates, CI and trading permissions must remain
byte-identical to the executable baseline. Validation is limited to the new
synthetic tests, focused Ruff, available type checks and CLI checks. Local evidence
records commands/results, source-code hashes, unchanged-path checks, publication
identity and limitations. It stays outside Git. Terminal engineering status:
`IMPLEMENTED_SYNTHETIC_TESTS_PASS_NOT_ACTIVE` only after all required checks pass;
otherwise `IMPLEMENTATION_BLOCKED`. Neither status activates research.
