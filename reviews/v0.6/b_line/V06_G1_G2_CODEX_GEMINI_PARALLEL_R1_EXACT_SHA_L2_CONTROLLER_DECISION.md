# Quant v0.6 B-line Controller L2 — Codex G1 + Gemini A/B exact-SHA decisions (2026-10-12)

**Controller:** ChatGPT-0 B-line. **Decision:** CODEx_G1_OFFLINE_PREVIEW_BOUNDED_ACCEPT; GEMINI_A_NEGATIVE_AND_SPARSE_F3_EVIDENCE_ONLY; GEMINI_B_CONDITIONAL_EXITS_INSUFFICIENT_SUPPORT. **Protected holdout/TESTNET/LIVE/real funds:** NONE. The user reports Codex quota exhausted NOW; that does **not** undo historical commits/tests and is not evidence that Codex failed to execute.

## Exact GitHub remote evidence

| Track | Starting immutable SHA | Freeze/implementation SHA | Terminal SHA | Commit ancestry/scope | Final GitHub Actions |
|---|---|---|---|---|---|
| Codex GPT-6.1 Sol G1 offline preview | 55ac4c631c69f6edbd275462ad23e4486b9782ed | C1 cf76ef99b47dc91b7f062877679172bacf1d6c9f -> C2 b792c613cac70324e66f6fb6958ce269f1a55dd1 -> C3 84c4764a2f1c46c81f43b144f5daf1f54cccc5d3 | **861a9d148f72db00e6079e53af78220bdd7e84ce** | 4 direct descendant commits, all limited to g1_offline_preview_r1 own files | [38200928294](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38200928294) SUCCESS: pytest/Ruff/compile **actually executed**; compatibility manual suite skipped |
| Gemini A: three causal flow/funding/basis entries | 55ac4c631c69f6edbd275462ad23e4486b9782ed | frozen **c0296ad38739281b69bcc3294b7706c1009d426a** | **f25954b45577cebb7624fae86cd91df9071a87ab** (intermediate 846de388877d8292adcc7bb49f01230607a6ecec) | 3 commits, freeze code unchanged on commits 2 and 3, extra final docs-only erratum | [38198046881](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38198046881) SUCCESS **compile+JSON only**; implementation freeze [38194406184](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38194406184) CANCELLED during pytest, NOT full tested CI |
| Gemini B: conditional exits | d5e3a8407b1b84111dc7f4276865ffd68cb0a7d2 | frozen **cb7445ef0cec515a6cf737b32d22d241788dc470** | **a862eece9733a614df7624449a8499716d9e6cb3** | 2 commits, code frozen and result evidence-only | [38196551827](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38196551827) SUCCESS **compile+JSON only**; implementation freeze [38196024516](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38196024516) CANCELLED during pytest, NOT full tested CI |

## G1 Codex bounded engineering evidence

Report: https://github.com/EXASHXE/btc-quant-agent-public/blob/861a9d148f72db00e6079e53af78220bdd7e84ce/docs/engineering/g1_offline_preview_r1/OFFLINE_PREVIEW_EXECUTION_REPORT.md

Terminal `G1_OFFLINE_PREVIEW_VERIFIED`. Synthetic 24h LONG/SHORT finite event workflow with deterministic mock LLM, explicit local fixture approval token (NOT authenticated person), synthetic fill/fee/funding/Mark, immutable WAL/checkpoint, signed causal ACK, local Feishu outbox (NO network), crash/restart and trace. Local Python3.12 task-focused 145 pass/0 fail/0 skip, 30 actual process kills/restarts over 15 checkpoints, 2 torn-WAL fail-closed cases, independent Decimal 12 cash effects. GitHub C4 full risk-based test step actually succeeded (not merely artifact mode); preceding C3 CI failed inherited H40 graph hash, C4 success does NOT imply protected science authorization. Fake fixture sizes and min-notional 1 differ from real exchange production rules; no real LLM, Feishu, authenticated approval, exchange queue, power failure and live safety demonstrated. Accept **OFFLINE NONTRADING G1 PREVIEW**, not integrated G1/G3 release and not TESTNET.

## G2 Gemini A: new entries development only

Report: https://github.com/EXASHXE/btc-quant-agent-public/blob/f25954b45577cebb7624fae86cd91df9071a87ab/docs/strategy_research/g2_flow_funding_entries_r1/FLOW_FUNDING_EMPIRICAL_REPORT.md

Three new entry identities x 12/18h, pre-outcome frozen method/source. All six STRESS44 configs fail preregistered evidence gates:
- **F1 aggressor-flow absorption**: n=2, PF=0, -91.30bp/trade, insufficient samples and negative.
- **F2 prior settled Funding sign reversal**: n=37, STRESS PF 0.37 (12h), 0.52 (18h); net -175.21/-134.44 USDT; reject as simple standalone directional Alpha.
- **F3 Mark–Last dislocation repair**: n=12 only, STRESS PF 2.15 (12h) /1.77 (18h), mean +96.39/+101.93bp, net +108.11/+109.70 USDT. In 2023 only ONE trade; insufficient independent calendar spread. **F3 is a sparse positive observational hypothesis, NOT independently validated Alpha; no eligible candidate**.

Statistical correction concern: frozen `statistics.py` uses per-boot draw SE floored at 1e-6 and takes simultaneous max|T| of sparse 7/14d blocks across n2/n12 low-support families. Committed critical value about **1,201,357.8** produces CI intervals hundreds of thousands/millions of bp wide. Such pathological studentization is not a calibrated useful statistical interval; DO NOT describe the CI as strong proof of zero edge or as a successful uncertainty-bound calibration. Sample support gate (F3 n12 < 30) already independently blocks promotion; no ex-post F3 threshold relaxation or backfill on 2021–23. A extra 3rd docs-only commit exceeded original 2-commit target, but no code or trade output mutation; report procedural exception rather than re-authorizing Alpha.

## G2 Gemini B: conditional exits study development only

Report: https://github.com/EXASHXE/btc-quant-agent-public/blob/a862eece9733a614df7624449a8499716d9e6cb3/docs/strategy_research/g2_conditional_exit_r1/G2_CONDITIONAL_EXIT_R1_EMPIRICAL_REPORT.md

Fixed original W1 n34, W2 n55 E0(12h) and H1(18h) versus precommitted X1 (positive as-of Mark net at 12h) and X2 (last complete 4h trend at 12h). STRESS mean relative to E0, bp per trade:
- W1 X1 +4.60, X2 +34.14; versus H1: X1 -32.75, X2 -3.21.
- W2 X1 +19.77, X2 +8.96; versus H1: X1 -2.67, X2 -13.48.
- Familywise 7d/14d joint simultaneous intervals ALL cross zero; W2 absolute 2023 performance remains negative. 88 Decimal witnesses, baseline E0/H1 identity reported exact. Terminal `X1_X2_INSUFFICIENT_SUPPORT`. No conditional policy ready, nor "18h universal optimum".

CI caveat BOTH research tasks: final green Actions are compile/JSON artifact lanes, full test at freeze cancelled; task-provided local tests were not independently run in completed GitHub CI. Preserve distinct SOURCE/NUMERICS/INFRA/METHOD assessment. No need to spend unavailable Codex quota for repeat work.

## Next science and engineering gate

G1 next: optional independent targeted G1 offline safety inspection with Gemini (no production wiring, no real credentials); G1 backend integration, true human identity, live LLM and Feishu transport deferred until separate future authority. G2 next: research-method/independent F3 hypothesis source+known-at feasibility and sparse bootstrap failure localization **without additional empirical strategy variants**, and data/experimental design to obtain independent observations. All 2021–23 outputs are multiply exposed, thus do not use incremental same-history P&L sweeps to "rescue" F3; 2024–25 protected chronology, 2026, H39–H41/Forward remain sealed. Avoid a compulsory new multi-agent cycle or new protected sample use. A-line/Performance independent and unchanged.
