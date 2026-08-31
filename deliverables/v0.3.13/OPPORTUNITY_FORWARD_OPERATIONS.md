# Opportunity Forward and Derivatives Operations

## Install

From `/root/workspace/project/Quant-agent`:

```bash
deploy/systemd/install-user-forward-derivatives.sh
deploy/systemd/install-user-opportunity-forward.sh
```

Both installers install user units, reload systemd, and enable their timer. No `sudo`
is required. Derivatives runs at UTC quarter-hour +20 seconds; Opportunity runs at
+50 seconds to avoid same-second network competition.

## Optional network environment

If the host requires a proxy, copy `deploy/systemd/network.env.example` to:

```text
~/.config/btc-quant-agent/network.env
```

Set only the values needed by the host, then apply `chmod 600`. The units use an
optional `EnvironmentFile=-...`, so the file may be absent on directly routed hosts.
Do not commit it and do not paste authenticated proxy URLs into issue or CI logs.

## Diagnose

```bash
.venv/bin/quantctl derivatives diagnose-network
systemctl --user status btc-quant-forward-derivatives.timer --no-pager
systemctl --user status btc-quant-forward-derivatives.service --no-pager
journalctl --user -u btc-quant-forward-derivatives.service --since '24 hours ago' --no-pager
```

The diagnostic reports DNS, transport/TLS/HTTP/parse class, endpoint status, and a
redacted proxy summary. It never needs a trading API key.

## Operate and inspect

```bash
.venv/bin/quantctl derivatives collect-once
.venv/bin/quantctl derivatives status
.venv/bin/quantctl derivatives audit

.venv/bin/quantctl opportunity-forward collect-once
.venv/bin/quantctl opportunity-forward status
.venv/bin/quantctl opportunity-forward audit
.venv/bin/quantctl opportunity-forward resolve
.venv/bin/quantctl opportunity-forward report
```

Run `collect-once` for Opportunity only shortly after a 15m close. An off-boundary
stale scan becomes an immutable missed decision slot. Never delete or replace it.
`resolve` changes only the separate outcome table; network errors leave labels
unresolved for retry.

## Health interpretation

- `HEALTHY`: recent scheduled runs are fully available and the scheduler is active.
- `DEGRADED`: scheduler works but a recent run is partial/failed or a required endpoint
  is unstable.
- `BLOCKED`: no successful systemd-context collection is possible after configuration.

Research eligibility is stricter than operational health. Do not start PIT derivatives
research until 30d / 2500 fully available / 95% each required field / max four-gap is
actually satisfied. Do not evaluate H35 before its preregistered sample gates.

