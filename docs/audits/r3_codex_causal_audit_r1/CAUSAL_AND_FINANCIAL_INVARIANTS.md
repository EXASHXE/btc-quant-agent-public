# Focused review method and frozen inputs

The latest controller request narrows this assignment to 20 local Python
accounting and import probes. The earlier 36-case, network-source and book audit
is superseded for this review. No broader readiness or release decision follows.

Frozen R2: `632d2e37f28b8c3efbd2b818ecdb74783f0df238`.
Parent: `b86843bb11a10e0a3a293d4d918671c6c41d08fa`.
B: `51cdd4e17503fbd18ad22aaeeaba3580f5efacf8`.
C: `91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b`.

| Invariant | Independent witness |
|---|---|
| Settlement time remains provider time; receipt/available time remain actual ingress for both consumers | T=180000; receipts T+200, T+30000, T+10800000; run actual B adapter and C MarketPitPort |
| C admits correctly delayed receipt; decisions preceding receipt reject | Correct the synthetic wrapper without editing source; invoke pinned C validation |
| Funding mark has finite positive price, settlement timestamp, ingress, source digest, and same valid epoch | Missing, 60-second-old, three-hour post-settlement, route-switch, Infinity, NaN references |
| Incomplete input produces explicit incomplete status and no realized cash valuation | Inspect actual bridge result, journal mutations and local consumer callbacks |
| Cash uses BTC quantity × USDT/BTC price × fractional rate; positive-rate long pays, short receives | Four signed Decimal cases with 1.5 BTC and 60000 USDT/BTC; long/short symmetry; half-even 8-decimal rounding |
| One economic settlement yields one entry regardless of equivalent rate formatting | Identical replay and 0.0001 versus 0.00010000 |
| Missing rate is incomplete, not accurate zero | Direct ledger input without fundingRate |
| Imports execute exact public revisions and reject source/hash drift | Git object staging, isolated child processes, actual imported module origins/hashes, synthetic tamper and foreign-origin rejection |
| Existing tests do not inspect development-machine directories | Execute the five existing filesystem import preambles against a synthetic permission-denying runner |

All market-like records are invented in the worker. Temporary staging contains
only named public Python blobs read with `git show SHA:path`; no full checkout,
local B/C working tree fallback, fixture-data loading, or network fetch occurs.
Missing Git objects raise `DEPENDENCY_UNAVAILABLE` including revision and file.
The same paths cannot be supplied by an already-imported `scripts` package:
each probe starts in a fresh Python `-I` process and checks module origin/hashes.
Socket connection and DNS functions are blocked before application imports.

B's adapter and schema are real pinned code. Its accounting destination is a
small in-memory callback sink; no strategy or full account simulation runs.
C's validator and translator are real pinned code. There is no WAL sidecar,
broker, order operation, or service. The legacy-import witness executes only
the actual filesystem preambles under patched Path.exists, not a GitHub job.

`BUG_REPRODUCED=true` and `INVARIANT_PASSED=false` describe unsafe baseline
behavior. A green pytest probe means the exact expected observation occurred;
it is not an application invariant pass. There are no skips or xfails.

Run from the audit checkout with the three pinned commits in its object store:

```sh
PYTHONDONTWRITEBYTECODE=1 python3.12 -m pytest -q --noconftest tests/test_v06_r3_codex_causal_audit_r1_focused.py --tb=short -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3.12 scripts/audits/r3_codex_causal_audit_r1/review.py
```

`--noconftest` makes these standalone probes independent of repository-wide
fixtures and unrelated application imports. Child processes impose their own
network guard. No existing fixture, policy, CI configuration or test is edited.
