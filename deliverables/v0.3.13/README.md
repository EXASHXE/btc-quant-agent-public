# BTC Quant Agent v0.3.13 delivery

This directory is the complete v0.3.13 delivery bundle. The formal code SHA is
`03caa112e046949389e48260723430d39934276d`; the campaign was preregistered before
its first real observation with start SHA `8e0dfd662acbf21244e817decc475762ff451ccb`.

## Outcome

- Opportunity Forward Campaign: **ACTIVE**, with one real successful scheduled scan,
  one immutable missed slot, and no synthetic opportunity.
- Derivatives PIT Collector: **DEGRADED**. The systemd proxy inheritance failure is
  fixed and a full systemd-context collection succeeded, but the first post-fix natural
  timer run was partial because `openInterest` timed out.
- H35: **FORWARD_CAMPAIGN_ACCUMULATING**; no edge verdict is permitted.
- Runtime maximum: **OPPORTUNITY_ONLY**; qualified Direction Engine: **NONE**.
- Execution: **DISABLED**; Candidate Freeze: **NONE**; Final Holdout: **SEALED**.

The raw SQLite stores remain ignored. The committed files contain only aggregate
status, protocol, operations, and audit evidence.

## Files

- `V0.3.13_OPPORTUNITY_FORWARD_SHADOW_REPORT.md`: engineering and research report.
- `V0.3.13_NUMERIC_ANSWERS.json`: required numeric answers.
- `V0.3.13_RECOMMENDATION.md`: v0.3.14 decision.
- `FORWARD_DERIVATIVES_RELIABILITY_AUDIT.json`: collector ledger audit.
- `OPPORTUNITY_FORWARD_CAMPAIGN_STATUS.json`: current campaign state.
- `OPPORTUNITY_FORWARD_OPERATIONS.md`: installation and operation runbook.
- `NETWORK_DIAGNOSTIC_SUMMARY.json`: redacted network diagnosis.
- `RESEARCH_REGISTRY_UPDATE.md`: registry non-regression record.

