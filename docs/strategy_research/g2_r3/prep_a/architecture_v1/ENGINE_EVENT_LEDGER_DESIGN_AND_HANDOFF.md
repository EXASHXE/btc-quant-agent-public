# P1 Engine Architecture Rebuild V1 — Event Ledger Design and Handoff

**TASK_ID:** `V06_G2_R3_P1_ENGINE_ARCHITECTURE_REBUILD_V1`
**CONTROLLER_DISPATCH_SHA:** `e5fcd76370a1b03d7d83b825af6a8cac842b1ae5`
**A_START_SHA:** `2c60b0653d3619eedf457753511a9ecc84c1cd5b`
**B_EVIDENCE_SHA:** `068a4005f68b5ee4a970063cb1f3bc524a08784a`
**TARGET_BRANCH:** `feature/v06-bline-g2-overnight-discovery-a`
**STATUS:** `ARCH_V1_DESIGN_FREEZE`

---

## 1. Executive Summary and Architectural Principles

This document defines the formal architecture design for the v0.6 G2 R3 research execution engine rebuild (`P1 Engine Architecture Rebuild V1`). Based on Controller adjudication `e5fcd76370a1b03d7d83b825af6a8cac842b1ae5` and independent verifier B findings `068a4005f68b5ee4a970063cb1f3bc524a08784a` (defects B01-D1, B03-D1/D2/D3, B05-D1/D2, B06-D1/D2, B07-D1/D2), the engine transitions from an ad-hoc mutable state container to a formal, causally sound, event-driven ledger.

### 1.1 Non-Negotiable Invariants
1. **Primary Accounting Identity by `position_id`**: Every economic exposure, trade lifecycle, funding debit, and reserve allocation belongs to a unique `position_id`. Symbol indexing is strictly a view/lookup for single-position concurrency constraints, never a ledger key.
2. **Strict Per-Owner Capital and Reserve Conservation**:
   $$\text{cost\_commitment\_o} = \sum_{o \in \text{owners}} \text{cost\_commitment}(o)$$
   $$\text{funding\_reserve\_rf} = \sum_{p \in \text{owners}} \text{funding\_reserve}(p)$$
   No `max(0, ...)` clamping may conceal negative balances. Reserve deficits are booked as liabilities against the specific owner, preventing cross-asset or cross-position reserve theft.
3. **Two-Clock Causality (Economic vs Available/ACK)**:
   - Economic execution occurs at valid simulation minute opens/closes.
   - Message delivery (ACKs) occurs at `available_at_ms`.
   - Pre-ACK positions are economically live: losses participate in conservative drawdown risk supervisor, while unacknowledged gains never inflate decision capital.
4. **Funding Attribution Window `[S-15000, S+15000]`**:
   - Evaluated per `(position_id, S)`.
   - Close→reopen at $S$ charges both positions according to their individual exposure and quantities.
   - Delayed finalization ensures pre-$S$ exits (economic exit at $S-1$ ms) retain an active funding owner until Stage 7 settlement at $S$ resolves.
5. **Monotonic Mark Ingress**:
   - Effective availability $\tau_{\text{eff}} = \max(\text{close\_ms}, \text{available\_at\_ms})$.
   - Out-of-order mark streams select the maximum eligible completed $\text{close\_ms}$. Older marks never regress or overwrite newer market state.
6. **Wall-Clock Retest Progression**:
   - Elapsed hours $\Delta h = (\text{close\_ms} - \text{breakout\_hour\_ms}) // 3{,}600{,}000$ advance monotonically with wall-clock time.
   - Cooldown, volatility, or EMA filters do not freeze elapsed time.
   - Unconfirmed breakouts expire at the end of the 3rd completed hour and immediately permit evaluation of a new breakout on that bar.

---

## 2. Textual System Architecture & Relationship Diagrams

### 2.1 Entity & Identity Relationship Diagram

```
+-----------------------------------------------------------------------+
|                             VirtualOrder                              |
|  - order_id: str (unique)                                             |
|  - candidate_id, symbol, direction, quantity                          |
|  - cost_commitment_usdt, funding_reserve_usdt                         |
+-----------------------------------------------------------------------+
                                   |
                                   | Stage 5: Fill Execution
                                   v
+-----------------------------------------------------------------------+
|                               Position                                |
|  - position_id: str ("POS_" + order_id, unique)                       |
|  - symbol: str (view index: book.positions[symbol])                   |
|  - quantity: Decimal                                                  |
|  - entry_time_ms: int (economic entry)                                |
|  - is_acknowledged: bool (False until fill ACK processed)             |
|  - cost_commitment_exit_usdt: Decimal (owned exit reserve)            |
|  - funding_reserves_usdt: Decimal (owned remaining funding reserve)   |
|  - total_funding_charged_usdt: Decimal                                |
+-----------------------------------------------------------------------+
        |                                       |
        | Exposure Interval                     | Exit Event (Stage 4 or 6)
        v                                       v
+-----------------------------+     +-----------------------------------+
|      ExposureInterval       |     |          CompletedTrade           |
|  - position_id: str         |     |  - trade_id: str (unique)         |
|  - start_ms: int            |     |  - position_id: str               |
|  - end_ms: int | None       |     |  - total_funding_usdt: Decimal    |
+-----------------------------+     |  - net_pnl_usdt: Decimal          |
        |                           |  - is_finalized: bool             |
        | Overlaps [S-15s, S+15s]   +-----------------------------------+
        v                                       |
+-----------------------------+                 | Stage 7 Attribution
|     FundingEventRecord      |                 |
|  - key: (position_id, S)    |-----------------+
|  - debit_usdt: Decimal      |
+-----------------------------+
```

### 2.2 Lifecycle State Machine

```
[ ORDER_SCHEDULED ]
        |
        | Stage 5 (Minute Open T)
        v
[ ECONOMIC_FILL_UNACKED ]  <--- Loss affects risk equity; entry commitment held
        |
        | Stage 1 (Minute Open T + 60s: Fill ACK processed)
        v
[ ACKED_OPEN ]             <--- Entry fee debited to cash; entry notional released
        |
        | Stage 4 or Stage 6 (Economic Exit at T_exit)
        v
[ ECONOMIC_EXIT_UNFINALIZED ] <--- Exit commitment held; exposure interval closed
        |
        +-----------------------------------+
        |                                   |
        | Exit ACK at S before Stage 7      | Exit ACK at T != S or post-S
        v                                   v
[ EXIT_ACK_SETTLEMENT_PENDING ]     [ RECONCILED_FINAL ]
        |                                   ^
        | Stage 7 at S charges funding      |
        +-----------------------------------+
```

---

## 3. Per-Minute 8-Stage Execution Lifecycle

In every simulation minute step at `open_time_ms`, the engine executes 8 distinct sequential stages:

| Stage | Name | Timing & Causality | Model Obligations & State Changes |
|---|---|---|---|
| **Stage 1** | Available Messages Ingress | Processes messages with $\text{available\_at\_ms} \le \text{open\_time\_ms}$ | 1. Ingest marks monotonically: select $\max(\text{close\_ms})$ among eligible.<br>2. Process Fill ACKs: debit entry fee to cash, mark position acknowledged, release entry commitment.<br>3. Process Exit ACKs: realize cash PnL, release exit reserve. If position interval intersects upcoming settlement $S$ at this same minute, defer funding reserve release to Stage 7.<br>4. Process Funding ACKs: debit cash once per event ID.<br>5. Exactly-once idempotence: duplicate ACKs safely ignored. |
| **Stage 2** | Account Risk & Kill Supervisor | As-of risk evaluation | 1. Freshness check: if symbol mark close $> 120\text{s}$ old, schedule `MARK_STALENESS` exit.<br>2. Asymmetric valuation: Acknowledged positions value full unrealized PnL; unacknowledged positions value $\min(0, \text{unrealized\_pnl})$ (losses count against risk equity; gains do not inflate decision equity).<br>3. Kill Latch: If $\text{drawdown} \ge 100\text{ USDT}$ or equity $\le 0$, trip kill latch, cancel pending orders, release unallocated commitments, queue immediate liquidation. |
| **Stage 3** | Candidate Signal Scheduling | Scheduled decisions available at $\le \text{open\_time\_ms}$ | If not killed, size orders using conservative available capital. Reserve entry commitment and funding reserve. Append to `pending_orders`. |
| **Stage 4** | Due Exits Execution | Exits due at $\text{open\_time\_ms}$ (Expiry, Staleness, Kill) | Execute at bar open price (adjusted for friction/spread). Calculate PnL and exit fee. Remove from active symbol index. Record `end_ms = open_time_ms`. Queue exit ACK for $\text{open\_time\_ms} + 60\text{s}$. |
| **Stage 5** | Due Entries Execution | Orders targeting $\text{open\_time\_ms}$ in canonical symbol order | Check gap filter and risk filters. If passed, execute at bar open (with spread/slippage). Create `Position` with `is_acknowledged = False`. Create `ExposureInterval(start_ms=open_time_ms)`. Queue Fill ACK for $\text{open\_time\_ms} + 60\text{s}$. |
| **Stage 6** | Intraminute Protection | Evaluates 1m OHLCV of current minute | Check SL and TP. **Invariant: If both touched, SL resolves first!** Adverse stop gap uses worse open. If hit, calculate economic exit at $\text{open\_time\_ms} + 60\text{s} - 1\text{ms}$. Queue exit ACK for $\text{open\_time\_ms} + 60\text{s}$. If expiry reached, queue due exit for next minute. |
| **Stage 7** | Hourly Funding Settlement | Active only at whole UTC hours $S$ | Evaluate all exposure intervals intersecting $[S-15\text{s}, S+15\text{s}]$ per `position_id`. Charge each `(position_id, S)` once. Deduct from position's owned funding reserve; if debit exceeds reserve, book excess as owner liability without stealing other positions' reserves. Update completed trade records. Release any remaining funding reserve for closed positions. |
| **Stage 8** | Ex-Post Reporting | Minute close valuation | Compute mark-to-market `economic_equity` using 1m close marks. Append to equity history. |

---

## 4. Exact Capital & Reserve Conservation Proof

### 4.1 Ledger Balances and Ownership
At any timestamp $T$:
1. **Total Cash**: $K(T)$
2. **Cost Commitment Ledger**:
   $$C_o(T) = \sum_{o \in \text{pending\_orders}} \text{cost\_commitment\_usdt}(o) + \sum_{p \in \text{unacked\_positions}} \text{entry\_notional\_res}(p) + \sum_{p \in \text{all\_open\_positions}} \text{cost\_commitment\_exit\_usdt}(p) + \sum_{e \in \text{pending\_exit\_acks}} \text{exit\_reserve}(e)$$
3. **Funding Reserve Ledger**:
   $$R_f(T) = \sum_{o \in \text{pending\_orders}} \text{funding\_reserve\_usdt}(o) + \sum_{p \in \text{all\_active\_positions}} p.\text{funding\_reserves\_usdt} + \sum_{e \in \text{settlement\_pending\_exits}} e.\text{funding\_reserve}$$
4. **Conservation Invariant**:
   $$\text{book.cost\_commitment\_o} \equiv C_o(T)$$
   $$\text{book.funding\_reserve\_rf} \equiv R_f(T)$$

### 4.2 Handling Funding Reserve Exhaustion
When funding debit $D$ exceeds owner position's remaining reserve $R_{\text{pos}}$ ($D > R_{\text{pos}}$):
- Owned reserve consumed: $\Delta R_{\text{pos}} = R_{\text{pos}}$.
- Position reserve updated: $R_{\text{pos}}' = 0$.
- Aggregate funding reserve decremented by owner consumption only:
  $$\Delta R_f = \Delta R_{\text{pos}} = R_{\text{pos}}$$
- Uncovered expense: $U = D - R_{\text{pos}}$.
- The uncovered amount $U$ is booked directly as an economic liability of that position, debited to cash upon funding ACK.
- **Other positions' reserves ($R_{\text{other}}$) remain strictly untouched**:
  $$\Delta R_{\text{other}} = 0$$

### 4.3 Terminal Conservation at Flat Book
When all positions are closed, all orders executed or cancelled, and all ACKs processed:
$$C_o = 0, \quad R_f = 0$$
$$\text{cash}_{\text{final}} - \text{cash}_{\text{initial}} = \sum_{t \in \text{completed\_trades}} t.\text{net\_pnl\_usdt}$$

---

## 5. Fail-Closed Error Catalog

The engine fails closed with explicit exceptions rather than silently corrupting state:

| Error Type | Trigger Condition | Engine Action |
|---|---|---|
| `FuturePriceLeakError` | Bar or mark timestamp $> \text{decision\_time}$ accessed during signal evaluation | Halt simulation immediately |
| `InsolventBookError` | Decision equity $\le 0$ | Trigger permanent insolvency kill latch |
| `InvalidStateTransitionError` | ACK received for unknown entity or invalid lifecycle state | Fail closed / record diagnostic |
| `ReserveUnderflowError` | Reserve debit exceeds owner reservation and attempt is made to clamp negative balance | Reject illegal release |
| `MarkStalenessVeto` | Symbol mark close $> 120\text{s}$ old | Force emergency position liquidation |

---

## 6. Compatibility and Public API Preservation

The external API remains 100% backward-compatible:
- `ReplayEngine.run_simulation(bars_1m, marks_1m)` signature and return type `dict[str, list[CompletedTrade]]` preserved.
- `VirtualBook.positions` provides symbol-keyed lookup compatible with legacy assertions.
- Candidate definitions and registry IDs unchanged.
- Deterministic receipt hash computation preserved.

---

## 7. Appendix: Maintenance Pass CI/Type and Executed Evidence Convergence

This appendix records the maintenance convergence under Controller Dispatch `dca82909aeaef380a5c2e9866238ccbbe0114fad` and Prompt `97a3708d5c6063c6926b2aa1c26be3d98e7a7c78`:

1. **Stage 7 Funding Attribution Typing**: In `ledger.py`, the Stage 7 owner position resolution variable was typed cleanly as `owner_pos: Position | None = None`, eliminating the `[assignment]` / `[no-redef]` mypy CI failure without modifying runtime branching or using type suppressions.
2. **Authoritative Candidate Registry**: Machine receipts and before-after matrices reflect the frozen 8 strategy candidate IDs (`STRUCTURAL_CONTINUATION_LONG_04H`, `STRUCTURAL_CONTINUATION_LONG_12H`, `STRUCTURAL_CONTINUATION_SHORT_04H`, `STRUCTURAL_CONTINUATION_SHORT_12H`, `CLOSED_RETEST_LONG_04H`, `CLOSED_RETEST_LONG_12H`, `CLOSED_RETEST_SHORT_04H`, `CLOSED_RETEST_SHORT_12H`) directly verified against `CandidateRegistry().list_candidates()`.
3. **Executable Non-Empty Synthetic E2E Evidence**: Verified two separate production-path test fixtures:
   - `test_synthetic_e2e_empty_book_case`: Verifies flat invariant with zero signals, zero trades, zero fees, zero funding, and exact 1000.00000000 -> 1000.00000000 USDT cash preservation.
   - `test_synthetic_e2e_nonempty_executed_book_case`: Verifies non-empty end-to-end execution through `ReplayEngine.run_simulation` covering 240h warmup, Donchian breakout, 1h closed retest confirmation, order sizing, fill ACK, 4h holding crossing multiple UTC hourly funding settlements, max-hold expiry exit, and final exit ACK. Realized:
     - `CLOSED_RETEST_LONG_04H`: 1 trade (`0.006 BTC`), Entry Fee: `0.18010836 USDT`, Exit Fee: `0.17992764 USDT`, Total Funding: `0.48004800 USDT`, Net PnL: `-1.14128400 USDT`, Cash: `1000.00000000 -> 998.85871600 USDT`, with exact algebraic cash conservation: $\Delta \text{Cash} == \text{Net PnL}$.
     - `CLOSED_RETEST_LONG_12H`: 1 trade (`0.006 BTC`), Total Funding: `1.44014400 USDT`, Net PnL: `-2.10138000 USDT`, Cash: `1000.00000000 -> 997.89862000 USDT`, with exact algebraic cash conservation.
   - Terminal flat books possess exactly zero owner reserves ($R_f = 0$), zero cost commitments ($C_o = 0$), and zero pending obligations.
