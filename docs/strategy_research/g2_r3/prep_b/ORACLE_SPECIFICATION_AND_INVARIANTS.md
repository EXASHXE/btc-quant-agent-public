# G2 R3 Role B (`GEMINI_B`) — Independent Synthetic Oracle Specification & Invariants

- **Task ID**: `V06_G2_R3_PARALLEL_P0_OFFLINE_PREPARATION`
- **Controller Dispatch SHA**: `56f8a9faa1a4539124ab006b49bf42b6e7c997e3`
- **Frozen Code Base SHA**: `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`
- **Accepted Design Addendum HEAD**: `cf2d5cc33774cdcff7d709636305bba830e977ef`
- **Original Eight-Candidate Design SHA**: `e5b2006a89441f7eb2ec900e508aff451106b87a`
- **Source Audit SHA**: `12793bc04db7414d11a0961684fd14f5df3ce16e`
- **Role**: `GEMINI_B` (`feature/v06-bline-g2-overnight-verifier-b`)
- **Authority**: Offline/synthetic code preparation only (`EMPIRICAL_EXECUTION_AUTHORITY=NONE`, `REAL_FUNDS_WRITE_AUTHORITY=NONE`).

## 1. Independent Oracle Architecture

The Role B verifier (`scripts/strategy_research/r3_verification/`) is implemented from first-principles mathematical invariants and handcrafted synthetic event sequences rather than copying any Role A replay engine:

1. [`oracle_specs.py`](../../../../scripts/strategy_research/r3_verification/oracle_specs.py): Frozen authority SHAs, 8 candidate registry IDs, base (`22bp`) and stress (`44bp`) cost scenarios, hermetic `Decimal(prec=50, rounding=ROUND_HALF_EVEN)` context, 12-decimal ledger quantizer, and directional tick/lot rounding functions.
2. [`pit_bar_and_signal_oracle.py`](../../../../scripts/strategy_research/r3_verification/pit_bar_and_signal_oracle.py): PIT 1m-to-1h/4h bar aggregation, `T+60s` availability and `T+120s` earliest next-minute entry verification, `ATR20`/`EMA20`/`EMA50`/`ER12` calculators, `STRUCTURAL_CONTINUATION` and `CLOSED_RETEST` invariant evaluators, and the 12h funding stress cost geometry verifier.
3. [`two_clock_accounting_oracle.py`](../../../../scripts/strategy_research/r3_verification/two_clock_accounting_oracle.py): Dual-clock Economic Ledger ($E_e$) and Decision Ledger ($E_d$), deterministic message bus, 8-stage minute-open execution contract, intraminute barrier resolution, bounded funding ownership, release-once reserve accounting, 1x supervisor, delayed drawdown kill latch, and unfunded overlapping matched counterfactual episodes.
4. [`manifest_and_boundary_oracle.py`](../../../../scripts/strategy_research/r3_verification/manifest_and_boundary_oracle.py): Static metadata schema verifier for `artifacts/research/run0-dev-frozen-v022-seed7-20260825/data_manifest.json`, v0.3 BTC final holdout `[2026-02-01, 2026-08-01)` overlap detector, calendar-only pre-2026 historic window cataloger, and lexical source/product/date boundary guard.
5. [`a_impl_static_auditor.py`](../../../../scripts/strategy_research/r3_verification/a_impl_static_auditor.py): Read-only Git object auditor for immutable remote `A_IMPL_SHA` commits (`origin/feature/v06-bline-g2-overnight-discovery-a`) with zero live worktree reads.

## 2. Verified Mathematical & Temporal Invariants

| Invariant Domain | Enforced Rule in Independent Oracle |
|---|---|
| **Bar Identity & Availability** | 1m bar covers $[O, O+60000)$, exclusive end $T = O+60000$, inclusive close $T-1\text{ ms}$, archival reconstructed availability $T+60000$. Source grade must be `ARCHIVAL_EVENT_TIME_RECONSTRUCTED`. |
| **1h / 4h Aggregation** | Epoch-aligned 1h (`60` x 1m) and 4h (`240` x 1m) bars require 100% present, contiguous, valid 1m constituents with `available_at <= decision_at`. Unfinished bars are dropped; missing past minutes flag `INCOMPLETE_BUCKET`. |
| **Signal & Entry Clock** | Hourly decision at $H_{\text{end}} + 60000$; earliest signal entry at next minute open $H_{\text{end}} + 120000$. No feature from the entry minute may enter decision lookbacks. |
| **Two Clocks ($E_e$ vs $E_d$)** | $E_e$ records ex-post fills, fees, funding, and minute-close mark MTM at event time. $E_d$ consumes only messages with `available_at <= O`. Ex-post $E_e$ insolvency or leverage breach never backdates a kill or erases prior fills. |
| **Message Ordering** | Sorted by `(available_at, event_at, type_priority, sub_priority, parent_order_id, symbol, source_id)` with `FILL_ACK=0` (exit/reduction before entry), `FUNDING_ACK=1`, `TRADE_BAR=2`, `MARK_BAR=3`. Duplicate `source_id` halts as `DUPLICATE_MESSAGE_ID`. |
| **Same-Minute SL/TP & Gaps** | If a 1m bar touches both SL and TP, **SL resolves first** (`INTRABAR_SL_FIRST_COLLISION`). Adverse stop gap executes at worse open (`GAP_SL`); favorable TP gap credits only fixed target (`FIXED_TARGET_NO_OVERCREDIT`). |
| **Forced/Time Exit Target Cap** | Every risk/time market exit at an open beyond a favorable standing target caps its raw price at that target (`LONG min(open, target)`, `SHORT max(open, target)`) before applying adverse friction and tick rounding. |
| **Funding Ownership & Stress** | Inclusive window $[S-15000, S+15000]$ finalized after all intersecting 1m bars complete. Charges once per `settlement_id`; reductions charge $\max(|q_{\text{pre}}|, |q_{\text{post}}|)$, never pre + post. Selection stress grants zero positive funding credit (`allow_positive_funding_credit=False`). |
| **Fees & Friction Reconciliation** | Base `6+2+3 = 11bp/leg` (`22bp` RT); stress `12+4+6 = 22bp/leg` (`44bp` RT). Spread and slippage are embedded once in effective execution price; taker fees debit executed notional once. Never double-debited in cash. |
| **5% Buffer, Reserves & 1x Cap** | Admissible capital $A = \max(0, 0.95 E_d - R_f - C_o)$; per-asset budget $B = \max(0, \min(333.333333333333, A/3, A-G))$ sized from pre-entry snapshot in canonical `BTCUSDT`, `ETHUSDT`, `SOLUSDT` order. Reserve buffer multiplier is `1.10`; each reserve releases at most once. |
| **Mark Staleness & Delayed Kill** | Mark event age $> 120000\text{ ms}$ vetoes entries and queues delayed exit at $O+60000$. Decision drawdown $\ge 100\text{ USDT}$ from high-water (or $E_d \le 0$) latches permanent `DISABLED` and liquidates known positions at $O+60000$. |
| **12h Stress Geometry** | Under unknown hourly funding cadence, 12h max hold has $C_s = 44 + 12 \times 8 = 140\text{ bp} \implies 2 C_s = 280\text{ bp} > 250\text{ bp}$ maximum allowed stop. Flagged `STRESS_COST_GEOMETRY_INELIGIBLE` (`NEGATIVE_UNDERPOWERED_DIAGNOSTIC`); all 8 candidate IDs remain intact in the registry. |
