# Quant v0.7.0 — Verified Status and Owner Handoff (2026-11-09)

> **SUPERSEDING Q0 STATE — later on 2026-11-09:** [New status ledger](V070_STATUS_AND_WORKPACKAGES_20261109_Q0.md) · [Handoff Home](V070_HANDOFF_HOME_20261109.md). This earlier A–P snapshot precedes the 0-C scoped S decision and Q0B/Q0C worker deliveries; older planned cadence is superseded, earlier historical evidence remains valid.\n\n> Canonical dated planning update for \`docs/engineering\`. This supersedes older *planning/status interpretations* where they conflict, but does not alter historical sealed results, implementation manifests, or legal permissions. Controller 0-C is the sole engineering dispatcher and acceptance authority.

## Executive assessment

**Offline software/product loop exists; real-market, clock-qualified Source → S1 → Shadow → dashboard loop is NOT completed.** The first release must deliver a correct read-only intraday review experience; a scientifically supported trading edge is a separate later gate.

- **Controller-accepted offline baseline:** Program A (179 tests), B (210), C method evaluator (154, scientific decision INSUFFICIENT_SUPPORT), F (480), H exploratory MVP (543), J public REST adapter (595), L swing review V2 (632 distinct accumulated regression cases), O clock-policy work (672 distinct offline cases). Counts refer to separate phase receipts and MUST NOT be summed as a single suite.
- **Latest application source candidate:** \`lt-program-o-clock-remediation-01/\` (accepted *offline* by 0-C on 2026-11-08). Includes CLI, S1, source interfaces, Shadow, persistence, dashboard, research protocol and native/read-only admission components. O does not qualify the current host or live data.
- **Actual public capture:** Program N recorded 22 HTTP 200 GETs, 28 request weight, 240 distinct completed 1D and 300 completed 4H candles across BTCUSDT/ETHUSDT/SOLUSDT, but two wall-vs-monotonic discontinuities (~-799ms and +918ms) triggered a fail-closed **before source admission**. No valid real S1 decision, real dashboard, qualified Shadow or economic result emerged. The N approval was consumed.
- **Clock:** P0 observed 549 paired Windows/WSL samples. Over ~120.191 s Windows QPC, Linux MONOTONIC elapsed ~113.009 s; RAW was near reference rate. Several ~2s wall-clock-offset changes occurred. Hypothesis of WSL guest time discipline vs Hyper-V implicit sync is NOT proven as the only cause.
- **P2 update:** Owner-authorized one-component stop experiment of Ubuntu \`systemd-timesyncd\` was attempted once, stopped after ~3.29s due to \`O_MONOTONIC_RAW_OR_BOOTTIME_DISCONTINUITY\`, and successfully rolled back to active/enabled. The planned 600s and separate 120s post-change validations did not complete; \`HOST_CLOCK_QUALIFIED=false\`. This worker result requires independent Controller acceptance; do not repeat/change host settings under spent authorization.
- **Retention:** Owner-approved exact-scope purge of Program N raw payload/failed audit SQLite completed per \`controller-decisions/V070_N_RAW_RETENTION_PURGE_20261109.json\`: 23 scoped files unlinked, target directory absent, sanitized hashes/receipts preserved; secure deletion of backups is NOT proved.
- **Qualification flags:** \`SOURCE_QUALIFIED=false\`, \`SHADOW_QUALIFIED=false\`, \`ECONOMICALLY_VALIDATED=false\`, \`ACCOUNT_UNKNOWN/ACCOUNT_VETO\`. S2/S3 remain research-only. No authorized orders, real trading, account operations or automation.

## Owner-confirmed next product direction

The new **target contract**, not yet demonstrated in actual forward markets:

- Mainly **2–12h holding**, with individually justified overnight extension and a **maximum intended 24h** horizon.
- **4H** regime/structure, **1H** setup and decision, optional **15m** tactical price optimization; **1D** macro-risk context, NOT a mandatory per-entry close gate.
- Scheduled manual review once/twice daily; decisions must include no-chase, review-time actionability, expiry and explicit UNKNOWN.
- Small, clear candidate universe expansion through liquidity screening. First prove 10–20 symbols; evaluate 20–50 only after measured source costs, rights and stable runtime.
- Regime-aware candidate routing, initially S1 trend pullback only; research secondary breakout/retest and range or failed-breakout challengers with no automatic promotion.
- No account/trading/order automation investment in this release; \`TODO\` only.

## Current release gap

| Gate | Verified outcome | Required next |
| --- | --- | --- |
| Deterministic offline app / S1 / Shadow / HTML | Accepted scoped offline | Freeze one O-derived clean publishable code snapshot and exact lineage |
| Public REST adapter | Built/tested; N transport worked | Qualify a safe host, source rights, clock/time and preflight for a new bounded native trial |
| Latest host clock | Not qualified | Independent, specifically approved stable-host proof / carefully scoped alternative; never raise original stop threshold |
| Real 1H/4H warmup and candle causality | Unqualified; N received only 1D/4H and failed admission | Native admitted data, full warmup, completed candle and sequence checks |
| Actual review card / NO_SETUP / dashboard | Synthetic only | At least one genuine read-only review, with auditable evidence |
| Forward Shadow evaluation | No qualified independent episodes | Observe real entry availability, outcomes, censoring and cost fields |
| Economic edge | Insufficient support | Predeclared prospective sample sufficiency and controls |
| Broad universe / regime routing | Target only, not accepted | Costed discovery/filtering and research-only router |

## Highest-value next Controller decisions

1. Independently close the P2 failed intervention + rollback receipt and select one testable **clock-qualified runtime path**. A previously working public REST request path alone does not qualify the host.
2. Build the **smallest legitimate real S1/NO_SETUP → Shadow → existing HTML** validation; no new generic framework.
3. After a passing narrow scan, expand to a filtered dynamic universe through an explicit endpoint/request-weight, cache, rights and freshness budget.
4. Freeze 4H/1H/1D roles and route market-regime classification as deterministic research code, not an auto-enabled strategy catalog.
5. Keep source/data custody, original historical/FINAL_HOLDOUT blocks (2026-02-01 through 2026-08-01), no PRIMARY registration, per-source grants and exact UTC windows. Existing grants never cover new symbols/endpoints implicitly.

## Provenance and review references

- Source-of-truth local audit: \`lt-program-o-clock-remediation-01/CONTROLLER_0C_PROGRAM_O_SCOPED_ACCEPTANCE.json\`;
  \`lt-program-n-korea-one-shot-public-01/CONTROLLER_0C_PROGRAM_N_SCOPED_ACCEPTANCE.json\`;
  \`lt-program-p-wsl-clock-recovery-01/P2_POST_CHANGE_STATUS.json\`;
  \`lt-program-p-wsl-clock-recovery-01/P2_FINAL_CONTROLLER_HANDOFF.md\`;
  \`controller-decisions/V070_N_RAW_RETENTION_PURGE_20261109.json\`.
- Earlier source and research decisions: M1/M1B, R11, R14, R16C/R17, Program A–C.
- GitHub code-review snapshot (separate non-authoritative branch) is a source export for outside architecture review, NOT an accepted production integration, canonical writable documentation, or authorization artifact.
