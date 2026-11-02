# Quant v0.7.0 — Independent External Code Review Bundle

**Status: REVIEW-ONLY / NOT INTEGRATED / NO NATIVE SOURCE AUTHORIZATION.**

This is a convenient, public GitHub source-and-document review branch.
It DOES NOT demonstrate that Session04 Source and LONG Shadow have been merged, tested,
deployed, authorized, or run together in a real market session.

## Read this code first
- [Root business code](src/btc_quant_agent/platform/) — the isolated LONG/Shadow implementation is promoted into normal src paths for easier GitHub source browsing.
- [Current LONG runtime](src/btc_quant_agent/platform/canary/longhorizon_runtime.py)
- [Current LONG authorization](src/btc_quant_agent/platform/canary/longhorizon.py)
- [Source consumer and journal](src/btc_quant_agent/platform/canary/public_runtime.py)
- [Source rate budget](src/btc_quant_agent/platform/canary/control.py)
- [Journal](src/btc_quant_agent/platform/canary/public_journal.py)
- [Selector](src/btc_quant_agent/platform/selection/selector.py)
- [Original SHORT/Session04 diagnostics and telemetry](engineering_snapshots/source-session04/)
- [Original LONG/Shadow frozen snapshot](engineering_snapshots/longhorizon-shadow/)
- [Snapshot preservation manifest](engineering_snapshots/SNAPSHOT_MANIFEST.json)

The root src/, tests/, tools/, configs/ include original v0.7.0 baseline paths
plus overlay of the sanitized LONG/Shadow snapshot. Treat root as a navigable review
projection, NOT an integrated, releasable or currently verified executable.

**Important**: Source/Session04 telemetry and diagnostic code is in
engineering_snapshots/source-session04/, not integrated into root LONG runtime.
The two snapshots contain conflicting canary implementations and require deliberate
reconciliation before a combined runtime is executable. Do NOT execute live collectors.

## Canonical current documents (copied at pinned docs commit)
- [Source-to-Advisory Status](docs/project/V070_SOURCE_TO_ADVISORY_CLOSURE_STATUS_20261102.md)
- [Handoff](docs/project/V070_CURRENT_STATE_AND_HANDOFF.md)
- [Roadmap](docs/project/V070_ADVISORY_ROADMAP.md)
- [Scope and mission](docs/project/V070_ADVISORY_MISSION_AND_SCOPE.md)
- [Role boundaries](docs/roles/V070_ADVISORY_AGENT_ROLES.md)

Docs original: docs/engineering @ 6d774007cac8320f64eb1fb23d49983eec872cc8.
Source original: snapshot/v070-l4-session04-long-20261102 @ ab5a9be2f520f82a6e77d62d632f1a70a88164b3.

## Claude instructions / access fallback
Read regular GitHub blob file URLs from THIS branch, not PR links.
If your browser tool blocks GitHub tree or raw URLs, use an authenticated GitHub
Connector with exact repository/path/ref. Alternatively, have the user download
this branch as a ZIP using GitHub Code > Download ZIP and upload the ZIP as a file.
A new branch cannot bypass browser robots restrictions by itself.

## Excluded
Actual market payloads, receipts, live grants, trusted signer key provision,
private account data, compiled caches, sqlite DBs and deployment secrets.

No approved permission for new acquisition, alerts, trading or execution.
