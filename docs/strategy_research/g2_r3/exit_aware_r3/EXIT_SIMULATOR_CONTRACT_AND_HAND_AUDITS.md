# Exit simulator contract and hand audits

Frozen numerical specification: EXPERIMENT_FROZEN_PROTOCOL.md and FROZEN_ROSTER_27_CELLS.json. Research-only Entry/ExitLeg are immutable; PositionState deduplicates fill IDs and conserves lot-rounded quantity. ResearchAccount is a separate independent monthly1000-USDT book. No broker or production imports.

All five invented fixtures use price10000, stop9970 long/10030 short, declared BASE6/2/3bp per leg, event E=0, decision60000, fill120000. X2 fixture quantity.128BTC; other fixtures.127BTC. Each fixture, expected scalar, full per-leg ledger and SHA256 is in MANUAL_DECIMAL_EXIT_LEG_AUDITS.json.

| Audit | Case | Independent expected net USDT | Observed |
|---|---|---:|---:|
| HAND1 | long stop | -6.60171400 | -6.60171400 |
| HAND2 | long three targets | 6.06198322 | 6.06198322 |
| HAND3 | TP1 then cost-inclusive protected stop | 0.90048198 | 0.90048198 |
| HAND4 | X2 half then3R | 7.88477568 | 7.88477568 |
| HAND5 | short three targets | 6.08532440 | 6.08532440 |

TP1 intrabar239999 ACK300000, stop replacement360000 in HAND3; no retroactive protection. Entry fee is charged once on initial quantity; subsequent fees use actual exit quantity. Raw gross minus entry/exit friction and fees reconciles net within explicitly bounded eight-place rounding. The independent helper also reconciled five examples; its suspected rounding risk was not reproduced.

Last-close dense MTM includes residual liquidation friction/fee. It is an ex-post measurement; account risk decisions only observe its two-minute-shifted prefix. The engine assumes an atomic protective bracket and conservative stop-first minute collisions, so real queue position/capacity/fills remain UNKNOWN. No simulated PnL is verified realized cash.
