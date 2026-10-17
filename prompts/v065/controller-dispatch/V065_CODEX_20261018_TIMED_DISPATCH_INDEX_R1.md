# Three timed Codex dispatches — 18 October 2026, Asia/Shanghai

Owner request: maximize useful long-horizon Codex 6.1 Sol HIGH work in three 5-hour quota windows, without overlapping current Codex P0 + Agy acquisition or queued F-R2 production migration.

* NOW: read-only strategy/mechanism and data feasibility analysis (no writing slot required).
* 06:55: P1 cost-aware BTC 4–24h evaluation engine, only if Controller releases a writer slot.
* 11:56: cross-venue adapters / OI and L2 research integration, only if a free nonconflicting writer exists.
* Local Codex CLI: 0.163.0, model gpt-6.1-sol and model_reasoning_effort=high observed in local config. Max not confirmed.
* At last observation WSL MemAvailable around 542 MiB and swap ~full; do not launch another heavyweight session into unsafe memory pressure.
* Automations should try to launch via connected authorized host when available; if not or resource/writer gate fails, report precisely and deliver frozen prompt/link, no false STARTED claim.
* Future time tasks are one-off, not recurring. Do not create a cron daemon, scheduled local prompt files or alter production jobs.
