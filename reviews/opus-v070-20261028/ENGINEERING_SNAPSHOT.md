# Engineering Assets, Gaps, and Evidence Quality
**Snapshot:** 2026-10-28. This is a dated synthesis; remote-only Opus cannot verify uncommitted local branch or current service state. Do not infer changes since snapshot.

## Distinct worktrees / code status
| Worktree | Last observed Git ref | Function and limitation |
|---|---|---|
| R: `/root/workspace/project/quant-0.7.0/research-loop-bootstrap` | local `40c70c7`, 12 pre-existing added research paths plus docs modifications | More complete advisory/research source; not demonstrated as current deployed live service |
| M: `/root/workspace/project/Quant-agent-market-watch` | `fde61da` with six modified tracked paths and one untracked test at prior observation | Product/PositionSupervisor/outbox branch; **its uncommitted source is not available through the public repository** |
| Q: `/root/workspace/project/Quant-agent` | `6bd63db` | Existing forward-collector runtime points here; running collector is NOT a deployed opportunity/position advisor |

The public [`v0.7.0` code branch](https://github.com/EXASHXE/btc-quant-agent-public/tree/v0.7.0) is a reference source snapshot. It includes separate historical copied documentation and is not the canonical future project-doc source. Full M local changes and newer isolated repair code are not publicly accessible from this pack; proposals depending on those internals are assumptions until independently verified.

## Existing assets on public code branch
The following publicly accessible implementation **exists in source**, not necessarily tested or operating end-to-end:
- [`market_watch/scanner.py`](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/market_watch/scanner.py): multi-symbol collection, benchmark-relative assessment, opportunity ranking, alerts.
- [`market_watch/playbooks.py`](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/market_watch/playbooks.py): trend pullback / breakout-retest and invalidation/targets.
- [`market_watch/entry_quality.py`](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/market_watch/entry_quality.py): trading-cost and plan-screening rules.
- [`strategies.py`](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/strategies.py): structural entry and exit candidate logic.
- [`position_supervisor/supervisor.py`](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/position_supervisor/supervisor.py): position events, including STOP_NEAR, regime reversal and derivatives shocks.
- [`decision/service.py`](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/decision/service.py), [`notify/feishu.py`](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/notify/feishu.py), [`economic/`](https://github.com/EXASHXE/btc-quant-agent-public/tree/v0.7.0/src/btc_quant_agent/economic): state/action, notification and economic accounting modules.
- [`data/binance.py`](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/data/binance.py): data receipt/availability semantics worth scrutiny.

## Known issues from prior Astra review and independent code spot-check
- Some target levels fall back to fixed multiples of ATR, without proving they are structural support/resistance.
- Some entry-quality funding assumptions effectively use a fixed number of settlements, inappropriate for endogenous holding.
- Core 15m close can be confused with current executable quote; server-time-before-request is not equivalent to receiver-known time.
- Derivatives error path can invoke uninitialized optional timestamp variables.
- Outbound notifications were sent before durable state updates in baseline scanner, and `notify=False` could incorrectly consume notification dedup.
- `PositionSupervisor` defines risk-event types but existing runtime wiring did not supply all necessary trend/OI/funding observations in the reviewed version.
- `STOP_NEAR` is not a full stop-breached/execution-unknown lifecycle.
- A rendered trading card / candidate score is not evidence of successful fill, calibrated probability or successful deployment.

These are *reviewed source findings*, not a measured count of incidents in live users.

## Isolated Controller engineering packages — not integrated/deployed
| Workstream | Prior documented status | What it does NOT prove |
|---|---|---|
| T2B canonical MARKET expiry | 118/118 original, 124/124 regression, 31/31 new in isolated checkout | Repair not established in R/M/Q runtime |
| F0/F0A source health | INSUFFICIENT_EVIDENCE / PARTIAL_EVIDENCE | Running systemd process and file mtime != healthy/complete source |
| F0B payload-free health publisher | 51/51 synthetic checks; isolated optional hooks | Does not prove deployment, current collector identity or healthy market feed |
| DIAG exit-policy preflight | PARTIAL; E0/E1/E3 parity blocked by entry-clock and ATR provenance | No new authorized dynamic economic outcome |
| Foundation engineering, original isolated package | PARTIAL: 17/34 new and 129/141 affected tests passed; usage-limit interruption | No ACCEPT, no merged patch or production launch |
| Foundation Completion successor | Isolated worktree created on 2026-10-28, initial failures reproduced; additional activity observed | Current completion terminal verdict **UNKNOWN in this snapshot**; investigate independently if a fresh public receipt is supplied |

### Foundation failure-family characterization
- Invalid nonexistent `GridDecision.WAIT` reference raised AttributeError.
- Same natural decision key recalculated divergent tactical evidence: `TacticalEvidenceConflictError`.
- Malformed/mocked timestamps, tick-size and serialization handling raised TypeError.
- Missing actionable quote could accidentally suppress valid degraded WATCH/RISK notifications.
- Correct persistence-before-send, definite-no-send retry and ambiguous remote notification outcomes remain nontrivial.

These aggregate facts came from local summary receipts `advisory-foundation-01/FOUNDATION_SYNTHETIC_TEST_RESULTS.json`, `FOUNDATION_LIMITATIONS_AND_NEXT.md`, `FOUNDATION_COMPLETION_TASK.md`, and observed `advisory-foundation-completion-01`. The original local logs and patch are intentionally not published.

## Architecture question
Existing modules can likely be reused. Opus may choose reuse, replacement, simplification or an independent research/prototype path, but must identify exactly why architecture choice affects time-to-useful-advice and scientific validity. A proposed live integration must acknowledge the unverified M/Q diffs and the isolation boundaries.
