# Program O — opt-in operational clock remediation

**Current outcome: O_HOST_CLOCK_STABILITY_REQUIRED. Offline implementation only; no new market requests authorized or made.** The measured WSL host fails RAW/MONOTONIC coherence. This package is a conditional successor, not a claim that the existing machine or N capture is qualified.

Python 3.13/Linux was tested. From the extracted offline packet (the source-only review packet requires the same frozen release directory supplied separately):

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links release/wheelhouse --require-hashes -r release/toolchain-lock.txt
.venv/bin/python -m pip check
.venv/bin/quant live doctor --review-policy O_EXPLORATORY_VENUE_CLOCK_V1
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B tools/run_o_tests.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B tools/build_o.py
```

Doctor makes zero requests. Offline tests enforce loopback only. They use fabricated HTTPS responses, certificates and stable QA clock counters, never real authority or N prices. The measured host counterexample must remain a failing admission case. `tools/clock_o_telemetry.py` records read-only host clock evidence for 30 seconds and does not qualify UTC.

The immutable policy is `src/btc_quant_agent/platform/live/operational_clock.json`; its canonical contract hash is printed by doctor. Default J V1, explicit accepted L V2, S1, Strict Research, and frozen C are unchanged. Use a fresh ordinary operator path. Existing N/L stores cannot be migrated to the new policy.

Only **after independent Controller acceptance, stable host checks, current rights/cache/exclusion validation and a new separate single-scan authorization**, a future operator may use:

```bash
quant live scan --access operator/access.json --output work/public \
  --review-policy O_EXPLORATORY_VENUE_CLOCK_V1 --review-window-minutes 120 \
  --grace-seconds 120 --holding-hours 24
```

This command is **not executed or authorized by O**. It remains bounded to 24 GETs/40 weight/120 seconds; no retries/reconnect/polling/proxy switching, private credentials, accounts, orders or alerts. Normal acquisition is12 GETs/15 weight. Any observed >50ms wall-offset change quarantines the initial pass; one full later pass raises the maximum to23 GETs/29 weight. A further change in that witness blocks with no third pass. Boot change, control-clock inconsistency, incompatible venue-time bounds, stale/incomplete/revised data or failed actionability block regardless of warning labels.

The source time is an HTTPS exchange-time interval projected on boot-scoped monotonic counters, **not authenticated exchange publication time or independently qualified UTC**. Actual local wall/receive/durable/review samples remain separate and immutable. Two fresh venue probes bracket each complete pass. Width≤5s, reference age≤120s, price age≤30s, review after120s and within configured5–120min of completed4H close. S1 structure, no-chase, pivot/target touch, costs, expiry and account veto remain enforced at actual review time. Old decisions are never backdated or rewritten.

Read-only commands (no extra market requests):

```bash
quant live status --output work/public
quant live opportunities --output work/public
quant live episodes --output work/public
quant live dashboard --output work/public
quant live evaluate --output work/public --report-output work/C
```

A future `observe` is a separate bounded authorized network action. Do not execute it under O. Existing C rejects this public operational evidence (`SOURCE_CLASS_INVALID`); retain `INSUFFICIENT_SUPPORT`. No real fills or PnL are inferred. SOURCE_QUALIFIED=false, SHADOW_QUALIFIED=false, ECONOMICALLY_VALIDATED=false; ACCOUNT_UNKNOWN/ACCOUNT_VETO; S2/S3 disabled.

Review the measured host decision in `O5_HOST_REMEDIATION_AND_FUTURE_PREFLIGHT.md` and exact N deadline handling in `O5_N_RETENTION_PURGE_CHECKLIST.md`. Synthetic HTML/SQLite/C examples are under `artifacts/SYNTHETIC_OFFLINE_QA/`; they are not current-market results.
