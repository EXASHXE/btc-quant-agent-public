# Reference strategy backlog

This backlog is intentionally isolated from v0.3.9 and contains no implemented strategy arms.

## RANGE_EXECUTION_FAMILY

- Bounded grid: may monetize oscillation in a verified bounded regime. It cannot enter v0.3.9 because inventory, fill semantics, caps, adverse selection, and regime qualification are separate hypotheses. Prerequisites: causal RANGE classifier, inventory/risk limits, realistic fill simulation, and a standalone protocol.
- Bollinger mean reversion: may describe deviations in a stationary range. It cannot be mixed with direction qualification or tuned on the same Development outcomes. Prerequisites: preregistered band/window rules, walk-forward evaluation, costs, and regime-specific risk controls.

## PRICE_TRANSFORM_DIAGNOSTICS

- RSRS, SSA, and ARBR: may expose structure or transformed trend/mean-reversion states. Existing price-only direction results do not validate them, and adding them now would restart indicator mining. Prerequisites: one independently motivated feature identity per study, causal implementation, fixed thresholds, and incremental tests against existing BTC state.

## FUTURE_MODELING_ONLY

- ML/LSTM/RL: may combine independently validated features or optimize policies under controlled simulations. They cannot manufacture trustworthy features or convert in-sample selection into OOS evidence. Prerequisites: validated data families, frozen labels, walk-forward splits, leakage tests, simple baselines, model governance, and untouched final evaluation data.

## OPERABILITY

- Strategy registry, simulated-versus-real execution separation, observability, reconciliation, and run manifests can improve engineering safety. They do not establish Alpha and should proceed only with explicit operational scope. Prerequisites: idempotent state transitions, actual fill confirmation, alerting, audit logs, kill switches, and environment-specific permissions.

Martingale/doubling, uncapped grids, treating submitted orders as fills, and selecting parameters by final equity are excluded.
