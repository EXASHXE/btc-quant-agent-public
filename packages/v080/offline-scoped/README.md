# QUANT v0.8.0 — scoped-accepted OFFLINE source snapshots

This directory archives source-only copies of independently accepted v0.8.0
offline work packages. It is NOT an integrated production release and does
not modify original sealed workspaces.

Each component includes the original source, portable tests and tool scripts,
applicable synthetic config, and package pyproject. The full manifest includes
per-file SHA256 and provenance to the original LOCAL Controller decision.
It intentionally excludes raw workspaces, sensitive evidence, actual credentials,
private-account payloads, signed grants, QA logs, and production trust material.

Tests may require inherited sealed fixtures/wheels NOT included in this export.
Root project packaging does not automatically install these nested packages.
The export does not grant genuine Binance, Feishu, private USER_DATA or TRADE.

R1 omits two packaging tools containing embedded private-key test fixtures.
S3 post4 is NOT included while its worker handoff awaits independent
Controller acceptance. Do not mislabel WORKER_READY as accepted.

For current project direction read the docs/engineering branch. For evidence
read the controlled LOCAL v0.8.0 workroot and Controller receipts.
