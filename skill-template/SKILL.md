---
name: btc-quant-signal
description: Operate the local BTCUSDT quantitative engine for deterministic multi-factor scans, immutable signal explanations, Shadow performance, and explicitly confirmed execution-plan operations. Use for LONG, SHORT, WAIT, entry, stop, target, RR, sizing, signal status, or when the user explicitly asks to prepare, submit, reconcile, cancel, or close a BTCUSDT order. Execution is disabled by default and remains separately gated.
---

# BTC Quant Signal

Use the bundled `scripts/quant_tool.py` wrapper. Treat QuantCore output as authoritative. The wrapper uses `BTC_QUANT_API_URL` when set and otherwise falls back to a local `quantctl` executable.

## Workflow

1. Run `health` before a live scan. If data is invalid or degraded, state that clearly.
2. Run `scan` for a current decision. Never infer LONG or SHORT yourself.
3. If QuantCore returns `WAIT` or `NO_SIGNAL`, preserve that result and its machine-readable
   `reason_code`; do not reinterpret stale data or a rejected setup as tradable.
4. For a signal, report validation status, direction, entry range, stop, target, net RR, planned loss, notional, display margin, reasons, risks, and expiry.
5. Use `show` before discussing an existing signal so TTL/status is current.
6. Use `decision` only after the user explicitly says they accepted or ignored a signal.
7. For any order-related request, run `execution-status` first. Do not proceed when mode is `disabled`.
8. Prepare a short-lived plan and show its exact immutable fields before submission. Submission requires the user to explicitly provide the returned plan hash.
9. After a submitted entry, use `execution-reconcile` to verify fill state and protective orders.

## Hard constraints

- Never alter Direction, Entry, SL, TP, RR, probability, expected R, or position size.
- Never invent market data or statistical probability.
- Treat `setup_score` as rule completeness, not win probability.
- If `p_win` or `expected_r` is null, say it has not been statistically calibrated.
- Reject expired or invalidated entries.
- Treat `expires_at_ms` as anchored to market decision data, not the time the user requested a scan.
- Never invoke an execution action from a market-scan request. The user must explicitly ask for that specific action.
- Never enable `auto_execute`, change execution mode, set credentials, or relax a risk limit.
- A plan hash is single-purpose confirmation, not general consent. Never infer, abbreviate, or reuse it for another plan.
- Never submit a LIVE plan unless status says `allow_live=true`, credentials are present, validation is `VALIDATED_FORWARD`, and the user explicitly confirms real-order intent.
- `WAIT`, expired signals, invalidated signals, missing protection, or degraded execution health must not create an order.
- Explain that leverage changes margin usage, not the risk-sized notional.
- Keep the warning concise: research/Shadow signal, not guaranteed profit.

## Commands

```bash
python scripts/quant_tool.py health
python scripts/quant_tool.py scan
python scripts/quant_tool.py latest
python scripts/quant_tool.py show SIGNAL_ID
python scripts/quant_tool.py explain SIGNAL_ID
python scripts/quant_tool.py decision SIGNAL_ID accept --entry 77450
python scripts/quant_tool.py performance --days 30
python scripts/quant_tool.py execution-status
python scripts/quant_tool.py execution-plan SIGNAL_ID
python scripts/quant_tool.py execution-submit PLAN_ID --confirm PLAN_HASH
python scripts/quant_tool.py execution-reconcile PLAN_ID
python scripts/quant_tool.py execution-plan-close
python scripts/quant_tool.py execution-submit-close PLAN_ID --confirm PLAN_HASH
python scripts/quant_tool.py execution-cancel PLAN_ID --confirm PLAN_HASH
```

The wrapper exposes only allow-listed signal actions and the separately gated execution workflow.
