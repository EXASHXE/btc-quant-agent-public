# Forward Derivatives Operations (v0.3.11)

The canonical BTCUSDT point-in-time store is:

```text
/root/workspace/project/Quant-agent/data/forward/BTCUSDT/derivatives.sqlite3
```

It is ignored by Git. SQLite uses WAL, a busy timeout, transactional append, and unique `(symbol, observed_at_ms)`. Exact duplicates are idempotent; conflicting payloads fail without overwriting history. A separate `collection_runs` ledger records attempted/successful fields and endpoint errors.

`collection_started_at_ms` is captured before the first request. `observed_at_ms` is captured only after all attempted endpoint responses have been processed. Exchange source timestamps remain separate. Gaps are never backfilled from historical REST data and must remain visible in audit output.

`status` reports `COLLECTING_DEGRADED` and forward health `DEGRADED` when the latest scheduled attempt is partial/failed, while the main Quant process remains available. A fully failed `collect-once` exits nonzero so systemd and monitoring can detect it.

## One-time collection and inspection

```bash
cd /root/workspace/project/Quant-agent
.venv/bin/quantctl derivatives collect-once
.venv/bin/quantctl derivatives status
.venv/bin/quantctl derivatives audit
.venv/bin/quantctl derivatives export
```

Order-book collection is off by default because a 15-minute L2 snapshot cannot support queue or microstructure replay. `--include-order-book` is optional diagnostic collection only.

## Install and start the scheduler

No API key or trading secret is required. The user-level units run one public-data collection at `00/15/30/45:20 UTC`.

```bash
cd /root/workspace/project/Quant-agent
./deploy/systemd/install-user-forward-derivatives.sh
systemctl --user is-enabled btc-quant-forward-derivatives.timer
systemctl --user is-active btc-quant-forward-derivatives.timer
systemctl --user list-timers btc-quant-forward-derivatives.timer --all
```

The installer prints the repository, Python, store, and unit paths before changing user configuration. It does not use `sudo`.

## Stop, restart, logs, and recovery

```bash
systemctl --user stop btc-quant-forward-derivatives.timer
systemctl --user start btc-quant-forward-derivatives.timer
systemctl --user restart btc-quant-forward-derivatives.timer
journalctl --user -u btc-quant-forward-derivatives.service --since today
```

`Persistent=true` causes a current collection after a missed timer activation; it does not recreate a historical PIT sample. WSL shutdown, laptop sleep, network failure, or Binance unavailability therefore creates an honest gap. Restore the environment and restart the timer, then use `status` and `audit`; never fill the gap with a retrospective endpoint.

If user systemd is unavailable, do not use an unaudited `nohup` process. Run `quantctl derivatives run` only under an explicit external supervisor, or deploy the supplied oneshot command in a durable scheduler. Report `SCHEDULER_NOT_STARTED` until that scheduler is verifiably active.

## Coverage gate

A future preregistered derivatives study may begin only after all frozen operational thresholds pass: at least 30 calendar days, at least 2,500 snapshots, at least 95% availability for Funding/OI/Taker/Basis/Global Long-Short, and no unexplained persistent gap larger than four cadence slots.

This is only a genuine-PIT data coverage gate. It is not evidence of edge, a Candidate, or permission for Paper/Testnet/Live.
