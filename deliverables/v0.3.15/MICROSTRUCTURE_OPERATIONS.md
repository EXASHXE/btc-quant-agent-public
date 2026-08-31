# Microstructure operations

## Install and start

From the repository root:

```bash
deploy/systemd/install-user-microstructure-forward.sh
systemctl --user status btc-quant-microstructure-forward.service
```

The committed unit uses the repository virtual environment, optional `%h/.config/btc-quant-agent/network.env`, and the frozen v0.3.15 campaign. The process waits until the fixed campaign start if launched early.

## Observe and audit

```bash
quantctl microstructure-forward status
quantctl microstructure-forward audit
quantctl derivatives status
quantctl opportunity-forward report
quantctl forward-evidence status
systemctl --user show btc-quant-microstructure-forward.service \
  -p ActiveState -p SubState -p MainPID -p NRestarts
journalctl --user -u btc-quant-microstructure-forward.service --since today
```

Inspect `state`, event counts, connected/expected seconds, uptime ratio, sequence continuity ratio, gaps/resyncs, aggregate completeness, duplicates/conflicts, latency percentiles, and chunk integrity. `COLLECTING` is expected early in the campaign. Do not interpret any count or imbalance as Alpha.

## Stop and restart

```bash
systemctl --user stop btc-quant-microstructure-forward.service
systemctl --user start btc-quant-microstructure-forward.service
```

SIGINT triggers session closure, SQLite commit/close, and a manifest update for closed UTC partitions. After any restart, the depth collector creates a new empty local book and performs REST snapshot plus buffered-diff synchronization. It never attaches a new WebSocket sequence to the previous in-memory book.

## Gap response

Any malformed frame, disconnect, or `pu` continuity failure records a gap. A depth fault discards the book and resynchronizes from REST; trade faults reconnect independently. Never edit a gap away, replay historical events into the formal campaign, or move the campaign start. If gaps persist:

1. Check the service journal and `network.env` without exposing secrets.
2. Confirm the official `/public` depth and `/market` aggregate-trade routes.
3. Verify REST depth bootstrap access.
4. Preserve the affected partition and audit records.
5. Repair code/configuration, restart naturally, and report the degraded interval.

## Partition integrity and retention

SQLite uses one UTC-day database to bound file growth. Do not commit raw databases. Back up complete partitions and `closed-partitions.sha256.json` together. Verify a partition with `sha256sum` and SQLite `PRAGMA integrity_check`; a mismatched digest or failed integrity check makes the partition unusable until separately investigated.

## Isolation guarantees

The service writes only the microstructure directory. It does not write derivatives, opportunity observations, research registry, runtime signals, execution plans, or Holdout artifacts. Existing derivatives/opportunity systemd timers must remain enabled during microstructure repair.

