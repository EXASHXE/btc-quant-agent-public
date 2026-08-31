# Forward evidence operations

Install with `deploy/systemd/install-user-forward-derivatives.sh` and
`deploy/systemd/install-user-opportunity-forward.sh`. Inspect with:

```bash
quantctl forward-evidence status
quantctl forward-evidence audit
quantctl derivatives diagnose-network
systemctl --user status btc-quant-forward-derivatives.timer
systemctl --user status btc-quant-opportunity-forward.timer
systemctl --user status btc-quant-opportunity-resolve.timer
```

Keep `~/.config/btc-quant-agent/network.env` mode 0600 and outside Git. Never delete
archive failures, move the epoch start, use manual runs for eligibility, reconstruct
missed observations, or resolve outcomes before maturity.
