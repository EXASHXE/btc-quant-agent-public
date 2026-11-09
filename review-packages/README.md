# Quant v0.7.0 — Incremental public-safe Q0 source export (2026-11-09)

The [v070-app/](../v070-app/) directory is the previously exported **Program O offline-accepted** 334-file application source snapshot. This branch **does not mutate that baseline**.

This directory adds three **unintegrated** isolated delivery packages for code review, separated by their actual Controller state:

| Package | Source | Qualification |
| --- | --- | --- |
| [program-s-windows-offline](program-s-windows-offline/) | lt-program-s-windows-handoff-hardening-01 | Controller 0-C accepted **offline historical/Windows simulation evidence only** on 2026-11-09 08:03 UTC; CURRENT_MANUAL_REVIEW=SOURCE_BLOCKED, real Source not admitted |
| [q0b-mtf-offline-pending](q0b-mtf-offline-pending/) | lt-q0b-intraday-mtf-v2-01 | Worker reported 100 synthetic tests; **pending 0-C acceptance**, no actual native integration |
| [q0c-feishu-offline-pending](q0c-feishu-offline-pending/) | lt-q0c-feishu-outbox-offline-01 | Worker delivered a durable MOCK-only outbox; **pending 0-C acceptance**, no real Feishu webhook or messages |

This is a **public source-code export**, not a ready-to-run unified app or approved release. Program S's 14 simulated HTTPS requests were local fabricated TLS, not public exchange calls. Q0B synthetic timestamps and Q0C provider responses are test data, not market proof.

## Inclusion rules

Only specifically allowlisted application/adapter, tests, synthetic examples, contract and package metadata source files were copied. Each byte is hashed in [REVIEW_MANIFEST.json](REVIEW_MANIFEST.json). No private grants, real market payloads, protected research, signing keys, environment variables, production alert destinations, execution logs, local artifact databases or sealed native audit receipts are included.

**Do not join these modules by hand without independent Controller evaluation**: Source custody, temporal semantics, schema migration and authorization/notification safety remain hard gates. The old v070-app/ represents historical O only; its presence next to Q0 packages does not imply integration.

Canonical status and new-conversation onboarding are maintained separately at:
https://github.com/EXASHXE/btc-quant-agent-public/blob/docs/engineering/docs/project/V070_HANDOFF_HOME_20261109.md

The next actual product objective is a bounded read-only multi-symbol 4H/1H/15m opportunity monitor with safe simulated-to-real Feishu delivery gating and 5–10 minute human response. Actual exchange access and actual outbound Feishu remain explicitly unapproved and untested as of this export.
