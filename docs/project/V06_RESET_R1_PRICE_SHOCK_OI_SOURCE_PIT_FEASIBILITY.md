# BTC PRICE_SHOCK_OI_CONTRACTION_REVERSAL Source & PIT Feasibility R1

**Date:** 2026-10-14  
**Author/Role:** Gemini BOOST Architecture / Codex Read-Only Data-Contract Analyst  
**Task ID:** `V06_RESET_R1_PRICE_SHOCK_OI_SOURCE_PIT`  
**Parent Controller Authority:** ChatGPT-0, B-line Primary Controller  
**Dispatch Prompt Git Blob:** `e7ee11eaee342f7b849ce7626a0c987d27ab5167` (`prompts/v0.6/b_line/V06_RESET_R1_PRICE_SHOCK_OI_SOURCE_PIT.md` in commit `ceb851765b84e8e83b78caa6ceecbc665e57c02f`)  
**Root Doc Parent Commit:** `5d0e639f76d58f7adb3809801421e2b053955d91`  
**Target Repository Code Base:** `13e3a710b137efeec2e21e3002f748834ec0cc22` (`src/btc_quant_agent/data/binance.py` blob `bf4de7511ee1bac0e48bf7a5fac2f49da6d70cbc`)  
**Assigned Working Branch:** `docs/v06-reset-r1-price-shock-oi-source-pit` (isolated docs branch rooted at `ceb851765b84e8e83b78caa6ceecbc665e57c02f`)  
**Independent Verifier:** ChatGPT-1 (Subsequent independent audit required)  
**Governance & Operational Status:** `G2_ALPHA_NO_GO / TESTNET_NOT_AUTHORIZED / LIVE_NOT_AUTHORIZED / REAL_FUNDS_WRITE_NONE`  
**Deliverable Scope:** Documentary Source-First Feasibility, Point-In-Time (PIT) Clock Invariants, Provider Matrix, Outcome-Blind Mechanistic Predicate, and Public Source Permit Draft ONLY. Strictly NO market-data scraping, downloads, streaming, historical outcome/price-label extraction, or PnL backtesting.

---

## 1. Executive Summary & Governance Authority

Following the comprehensive B-line intraday alpha research reset (`docs/project/V06_BTC_INTRADAY_ALPHA_RESEARCH_RESET_CONTROLLER_R1.md` in commit `ceb851765b84e8e83b78caa6ceecbc665e57c02f`), this document executes the **source-first Point-In-Time (PIT) feasibility evaluation** for the Priority 1 candidate mechanism:
$$\text{PRICE\_SHOCK\_OI\_CONTRACTION\_REVERSAL}$$

### 1.1 Binding Governance & Authority Invariants
1. **Immutable Authority Link:** This study is governed strictly by the exact dispatch prompt blob `e7ee11eaee342f7b849ce7626a0c987d27ab5167` under parent commit `5d0e639f76d58f7adb3809801421e2b053955d91`. No substitution of moving heads, subsequent branches, or unverified verbal memos is permitted.
2. **Zero Historical Re-test of Retired Families:** The historical findings of v0.3.12 (prereg `ca647f23f75a452ba4af28ad8a1ba503f05fc9a1`, qualification report `8ecff4ec4b25bf73a35309689fd3ecfacc0d3399` where `SPOT_PERP_TAKER_FLOW_SPREAD_1H` yielded H32 Inconclusive, H33 Falsified, H34 Falsified) remain binding stops. Simple parameter sweeps or sign-reversals of flow, R3, Goal-A/B, and F1–F3 are retired.
3. **Outcome-Blind Primacy:** Data source admissibility, provenance, licensing, and PIT clock integrity must precede any entry formulation, outcome extraction, or trade evaluation.
4. **Data Isolation:** All protected data roots (H39/H40/H41, Forward/Final Holdouts, reserved 2024–2026 OOS, private account credentials) are strictly inaccessible and untraversed.
5. **No Execution Authority:** This document provides a **DRAFT PERMIT ONLY**. No HTTP requests to live exchange data endpoints, WebSocket connections, or historical scrapes were executed in this deliverable.

### 1.2 Key Feasibility Findings
- **API Discontinuity & Historical Non-Existence:** Official Binance USD-M statistical history (`/futures/data/openInterestHist`) maintains a rolling retention window of **approximately 30 days (~1 month)**. The historical 2021–2023 BTC price archives (e.g. Vision 1m klines) do **NOT** contain authentic open interest time series. Reconstructing 2021–2023 open interest via price/volume proxies or synthetic interpolation is strictly rejected as unscientific data fabrication.
- **Clock Asynchrony & Availability Bounds:** Provider period-end timestamps (e.g., `timestamp` in `/futures/data/openInterestHist`) represent retrospective aggregation window boundaries, **not** local availability proof. A defensible receiver-known-at clock requires:
  $$\text{available\_at} \ge \max(\text{local\_receipt\_at}, \text{complete\_period\_end})$$
  Direct publication latency, polling interval delay, and pipeline aggregation jitter must be accounted for before a signal can be deemed readable by an autonomous decision engine.
- **Microstructural Distinction:** Open Interest (OI) contraction measures the net reduction of open derivative positions. Because every derivative contract consists of exactly one long and one short, OI contraction represents a bilateral closure ($\Delta \text{OI} < 0$). It does **not** prove long liquidations, short liquidations, or directional margin insolvency. Any strategy predicate relying on an assumption of "long liquidation cascades" from OI alone constitutes an unverified narrative error.
- **Terminal Gate Verdict:**
  - **Multi-Year Historical Backtest Horizon (2021–2023):** **`SOURCE_NOT_READY`** (Public authentic source data does not exist).
  - **Prospective 30-Day Forward Ingress Horizon:** **`PARTIAL_SOURCE_QC_ONLY`** (Feasible under a strict future Controller-authorized permit; no alpha claim or 48h event-rate guarantee).
  - **Overall Workpackage Status:** **`OI_SOURCE_CONTRACT_DRAFT_READY`** (Independent PIT/Source audit required).

---

## 2. Binance USD-M Derivatives Market-Data API Verification

An exhaustive technical audit of the official Binance USD-M Futures REST API documentation (`https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data`) and the current repository client implementation (`src/btc_quant_agent/data/binance.py` at commit `13e3a710b137efeec2e21e3002f748834ec0cc22`, blob `bf4de7511ee1bac0e48bf7a5fac2f49da6d70cbc`) reveals sharp functional and architectural distinctions between snapshot and windowed statistical endpoints.

### 2.1 Instantaneous Snapshot: `/fapi/v1/openInterest`
- **HTTP Method & URL:** `GET https://fapi.binance.com/fapi/v1/openInterest`
- **Request Weight:** 1 (against 2400/min IP limit).
- **Mandatory Parameters:** `symbol` (e.g., `BTCUSDT`).
- **Forbidden Parameters:** Does **not** accept `startTime`, `endTime`, `period`, or `limit`.
- **Response Schema:**
  ```json
  {
    "openInterest": "20403.637",
    "symbol": "BTCUSDT",
    "time": 1588122438000
  }
  ```
- **Field Semantics:**
  - `openInterest`: Total open positions denominated in **base asset contracts** (i.e. number of BTC contracts).
  - `time`: Matching engine server timestamp (Unix epoch milliseconds) of the instantaneous observation.
- **Critical Architectural Limitations:**
  - **Zero Historical Depth:** The endpoint exposes solely the current engine state. It cannot be queried retrospectively for historical timestamps.
  - **No Notional Valuation:** Quote-denominated notional value (USDT) is not reported; converting to USDT requires multiplying by a contemporaneous Mark or Last price, introducing cross-endpoint clock alignment risk.

### 2.2 Aggregated Statistics: `/futures/data/openInterestHist`
- **HTTP Method & URL:** `GET https://fapi.binance.com/futures/data/openInterestHist`
- **Request Weight:** 1 (against 2400/min IP limit).
- **Parameters:**
  - `symbol`: e.g. `BTCUSDT` (Mandatory).
  - `period`: Granularity choice: `"5m"`, `"15m"`, `"30m"`, `"1h"`, `"2h"`, `"4h"`, `"6h"`, `"12h"`, `"1d"` (Mandatory).
  - `limit`: Integer, default 30, maximum 500.
  - `startTime`: Optional start timestamp in ms.
  - `endTime`: Optional end timestamp in ms.
- **Response Schema:**
  ```json
  [
    {
      "symbol": "BTCUSDT",
      "sumOpenInterest": "20403.637",
      "sumOpenInterestValue": "150570784.07809970",
      "timestamp": 1583127900000
    }
  ]
  ```
- **Field Semantics:**
  - `sumOpenInterest`: Aggregated open contracts in base asset units (BTC).
  - `sumOpenInterestValue`: Aggregated notional open value in quote currency (USDT), computed natively by the venue.
  - `timestamp`: Unix epoch milliseconds indicating the **period-end timestamp** (the closing boundary of the statistical aggregation window).
- **Critical Architectural Limitations:**
  - **Strict ~30-Day (1-Month) Retention:** As verified on 2026-10-14, Binance maintains rolling data retention on the `/futures/data/*` endpoints of approximately 30 days. Queries for timestamps older than ~30 days return empty sets or fail.
  - **Batch Pipeline Propagation Delay:** The record is aggregated via an asynchronous backend pipeline. The `timestamp` field denotes when the window closed, **not** when the record was published or readable over the REST API.
  - **Historical Asymmetry:** Retrospective backfills spanning multiple years (such as 2021–2023) are impossible using this endpoint.

### 2.3 Existing Repo Client Audit (`src/btc_quant_agent/data/binance.py`)
In `src/btc_quant_agent/data/binance.py` (blob `bf4de7511ee1bac0e48bf7a5fac2f49da6d70cbc`), derivative collection is implemented in `collect_derivatives()`:
```python
# Lines 267-275
premium = attempt("funding_mark_index", "/fapi/v1/premiumIndex", {"symbol": symbol}) or {}
oi = attempt("open_interest", "/fapi/v1/openInterest", {"symbol": symbol}) or {}
oi_history = (
    attempt(
        "open_interest_history",
        "/futures/data/openInterestHist",
        {"symbol": symbol, "period": "1h", "limit": 2},
    )
    or []
)
...
# Lines 295-300
oi_change = None
if len(oi_history) >= 2:
    prior_oi = float(oi_history[-2].get("sumOpenInterest", 0.0))
    current_oi = float(oi_history[-1].get("sumOpenInterest", 0.0))
    oi_change = current_oi / prior_oi - 1.0 if prior_oi else None
```

#### Deficiencies Identified in Existing Repo Implementation:
1. **Cadence Mismatch:** The client polls `/futures/data/openInterestHist` with hardcoded `period="1h"` and `limit=2`. For an intraday strategy operating on 5m or 15m decision cadences, a 1h statistical bucket is excessively coarse and lagged.
2. **Buffer Fragility:** Requesting only `limit=2` provides zero redundancy. If the most recent 1h bucket has not completed aggregation, `oi_history[-1]` may represent an incomplete bucket or a delayed prior bucket, resulting in erratic `oi_change` calculations.
3. **Dropped Metadata:** While `sumOpenInterest` is extracted, `sumOpenInterestValue` (the venue's native USDT notional) is discarded. Furthermore, the statistical bucket's `timestamp` is not stored in `DerivativesSnapshot`, preventing downstream consumers from validating whether the bucket matches the decision bar.
4. **No Historical PIT Store:** The repository has no ingestion pipeline or persistent schema for historical open interest series. `historical_klines()` exists for price, and `funding_rate_history()` exists for funding rates, but there is no `historical_open_interest()` facility.

---

## 3. Provider & Source-Capability Matrix

The following matrix documents the exact operational capabilities, constraints, and PIT contracts across candidate Open Interest data sources for BTCUSDT:

| Matrix Dimension | Snapshot Endpoint (`/fapi/v1/openInterest`) | Windowed Statistics Endpoint (`/futures/data/openInterestHist`) | Retrospective Archive (e.g. Vision 2021–2023) |
|---|---|---|---|
| **1. Instrument Target** | BTCUSDT | BTCUSDT | BTCUSDT |
| **2. Market Type** | USDⓈ-M Perpetual Futures | USDⓈ-M Perpetual Futures | USDⓈ-M Perpetual Futures (Price only) |
| **3. Contract Units & Values** | Base asset contract units (BTC). Quote value not provided. | Dual representation: `sumOpenInterest` (BTC contracts) & `sumOpenInterestValue` (USDT notional). | **NONE** (Price klines only; OI completely absent). |
| **4. Architectural Distinction** | Instantaneous point-in-time state of the matching engine. | Periodic aggregated statistical bucket over closed windows. | Retrospective static files (OHLCV). |
| **5. Clocks & Timestamps** | `time`: Server engine clock (Unix ms). | `timestamp`: Period-end boundary of the aggregation window. | Open/Close timestamps of kline bars. |
| **6. Receiver-Known-At Clock** | $\max(\text{local\_receipt\_at}, \text{time})$ | $\max(\text{local\_receipt\_at}, \text{period\_end\_timestamp})$ | Retrospective delivery date; original live receipt unknown. |
| **7. Clock Skew & Invariants** | Server-to-local clock offset verified via `/fapi/v1/time`. Skew capped at 30,000 ms. | Server-to-local clock offset verified via `/fapi/v1/time`. Skew capped at 30,000 ms. | Unverifiable historical clock skew. |
| **8. Cadence / Granularities** | Continuous / On-demand poll (recommended $\ge 15\text{m}$). | Fixed discrete periods: 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d. | 1m, 1h, 1d OHLCV bars. |
| **9. Revisions & Backdating** | None (instantaneous state cannot be revised). | Potential asynchronous batch adjustments or delayed aggregation. | Immutable once archived; unverified for retrospective survivor bias. |
| **10. Deduplication Key** | `(symbol, time)` | `(symbol, period, timestamp)` | `(symbol, open_time_ms)` |
| **11. Missingness & Gaps** | Packet loss or HTTP error yields missing snapshot. Zero forward-fill allowed. | Missing interval if $\Delta \text{timestamp} > \text{period\_ms}$. Forward-fill strictly forbidden. | Missing bars in raw archive; zero OI data present. |
| **12. API Retention Horizon** | **0 days** (current snapshot only). | **~30 days (~1 month)** rolling window. | 2021–2023 (Price only, **0 days OI**). |
| **13. Source License & Legal** | Binance Public REST API Terms; non-commercial research use. | Binance Public REST API Terms; non-commercial research use. | Public Vision dataset / archive license. |
| **14. Current Repository State** | Implemented in `src/btc_quant_agent/data/binance.py` blob `bf4de7511ee1bac0e48bf7a5fac2f49da6d70cbc`. | Implemented in `src/btc_quant_agent/data/binance.py` blob `bf4de7511ee1bac0e48bf7a5fac2f49da6d70cbc` (1h only). | Absent; no connector or archive reader exists. |
| **15. Source Readiness Gate** | **`PARTIAL_SOURCE_QC_ONLY`** (Live forward monitoring only). | **`PARTIAL_SOURCE_QC_ONLY`** (Forward 30 days only; multi-year blocked). | **`SOURCE_NOT_READY`** (Completely unviable for multi-year OI). |

---

## 4. Point-In-Time (PIT) Availability Clocks & Invariants

### 4.1 Frozen Receiver-Known-At Clock Specification
A fatal pitfall in quantitative market-data research is the conflation of a **provider event timestamp** with **local availability time**. For any open interest record $R$:
1. Let $T_{event}$ be the internal matching engine timestamp (for snapshots) or the period-end timestamp (for statistics, e.g. `timestamp = 12:00:00.000` for the 11:45–12:00 15m window).
2. Let $T_{pub}$ be the actual time the provider's API gateway emits the serialized record ($T_{pub} > T_{event}$ due to internal aggregation compute latency).
3. Let $T_{recv}$ be the local system monotonic and wall-clock receipt timestamp recorded upon complete HTTP response read.

**Defensible Receiver-Known-At Invariant:**
$$\text{available\_at} \ge \max(T_{recv}, T_{event\_close})$$
No trading signal or decision logic evaluated at time $t_{decision}$ may consume record $R$ unless:
$$t_{decision} \ge \text{available\_at}$$

```
Provider Window [11:45:00 - 12:00:00]
---|-----------------------------------|--------------------> Time
   11:45:00                           12:00:00 (timestamp)
                                          \
                                           \ Aggregation Pipeline Delay (Δt_pub)
                                            \
                                             12:00:18 (Provider Published)
                                                 \
                                                  \ Network & Polling Delay (Δt_recv)
                                                   \
                                                    12:00:22 (local_receipt_at)
                                                    
==> available_at = max(12:00:22, 12:00:00) = 12:00:22
==> Decision engine CANNOT evaluate this OI bar at 12:00:01!
```

### 4.2 Mandatory Rejection Rules
To preserve causal purity and prevent lookahead bias, any future data intake must strictly enforce the following negative constraints:
1. **Rejection of Future Leakage:** Assuming that a statistical bar with `timestamp = 12:00:00.000` was accessible to the agent at 12:00:00.000 without accounting for aggregation latency ($\Delta t_{pub}$) and network transit ($\Delta t_{recv}$) is strictly prohibited.
2. **Rejection of Silent Backdating:** If a repeated query for period $T$ returns a different `sumOpenInterest` value than previously recorded, the record must be flagged as a revision conflict (`REVISION_WITHOUT_AUDIT_TRAIL`) and failed closed.
3. **Rejection of Heterogeneous Notional Conversions:** The base contract count (`sumOpenInterest`) must never be multiplied by an arbitrary external spot price or mismatched Last price to simulate USDT notional. If notional value is required, only the native `sumOpenInterestValue` or a strictly contemporaneous Mark price may be used.
4. **Rejection of Missing Interval Interpolation:** If an exchange outage or network disconnection creates a missing interval ($\Delta \text{timestamp} > \text{period}$), forward-filling the prior OI value across the gap is forbidden. Open interest changes across unobserved gaps are undefined.
5. **Rejection of Stale Responses:** Any response where the latest available bucket timestamp satisfies $(T_{local} - T_{bucket}) > 2 \times \text{period}$ must be rejected with error classification `STALE_STATISTICAL_BUCKET`.
6. **Rejection of Liquidation / Long-Unwind Causal Inference:**
   - **Microstructural Grounding:** Open interest represents the total number of open contracts outstanding. Every contract is simultaneously held by one buyer (long) and one seller (short):
     $$\text{Total Long Positions} \equiv \text{Total Short Positions} \equiv \text{Open Interest}$$
   - When $\Delta \text{OI} < 0$, exactly $\Delta \text{OI}$ long contracts were closed AND exactly $\Delta \text{OI}$ short contracts were closed.
   - An OI contraction provides **zero mathematical evidence** as to:
     - Whether the closure was initiated by the long or the short.
     - Whether the orders were aggressive market orders or resting limit orders.
     - Whether the closures were voluntary de-risking, take-profit executions, or exchange-mandated margin liquidations.
   - Asserting that a downward price shock accompanied by an OI contraction constitutes "long liquidations cascading" is an unfounded narrative assumption. The predicate must remain strictly descriptive of price shock and aggregate inventory contraction.

### 4.3 Mock Field Record Schema (PIT Specification)
Every admitted Open Interest record must adhere to the following frozen structural schema:
```json
{
  "instrument": "BTCUSDT",
  "market_type": "USDT_M_PERP",
  "source_endpoint": "/futures/data/openInterestHist",
  "schema_version": "v0.6.1_pit",
  "period": "15m",
  "period_start_ms": 1776168000000,
  "period_end_ms": 1776168900000,
  "provider_timestamp_ms": 1776168900000,
  "local_receipt_wall_ms": 1776168922450,
  "local_receipt_mono_ns": 94827103948571,
  "server_offset_ms": 12,
  "available_at_ms": 1776168922450,
  "sum_open_interest_base": 20403.637,
  "sum_open_interest_quote": 150570784.078,
  "prior_period_sum_base": 20850.120,
  "delta_open_interest_pct": -0.021414,
  "staleness_ms": 22450,
  "connection_epoch_id": "epoch_20261014_01",
  "payload_sha256": "3a8f9c1e4b8d7a6e5c2b1f0e9d8c7b6a5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b",
  "qc_status": "VALID"
}
```

---

## 5. Outcome-Blind Prospective Mechanistic Predicate: `PRICE_SHOCK_OI_CONTRACTION_REVERSAL`

To avoid outcome-label data mining and false discovery, the candidate mechanism is formalized purely as a **prospective causal hypothesis**. All parameters, lookbacks, and thresholds are specified structurally without reference to historical profitability or return labels.

### 5.1 Mechanistic Hypothesis & Microstructural Thesis
- **Core Observation:** During acute intraday price displacements (price shocks), directional market participants aggressively absorb liquidity. If open interest simultaneously expands ($\Delta \text{OI} > 0$), new positioning is entering the market, suggesting continuation momentum. Conversely, if open interest sharply contracts ($\Delta \text{OI} < 0$), aggregate inventory is de-leveraging and positioning is being extinguished.
- **Hypothesized Reversal Mechanism:** A price shock accompanied by substantial aggregate inventory contraction indicates exhaustion of the displacement move. Once the forced selling/buying abates, the absence of fresh directional open interest creates structural fragility in the direction of the shock, allowing the price to revert toward pre-shock reference levels.
- **Required Controls:** Because simple price mean-reversion and volatility exhaustion produce similar patterns, the incremental explanatory power of Open Interest must be proven over strictly matched price-only and volume-only baselines.

### 5.2 Mathematical Formalization of the Predicate
Let decisions occur at discrete 15-minute intervals $t \in \{t_0, t_1, t_2, \dots\}$.

#### 1. Predecisional Price Shock Component ($S_{shock}(t)$)
A price shock over lookback window $W_{shock} = 4$ bars (1 hour) is defined relative to trailing realized volatility:
$$\Delta P(t) = P_{close}(t) - P_{close}(t - W_{shock})$$
$$\sigma_{ATR}(t) = \text{ATR}_{14}(t)$$
$$\text{Shock Severity: } Z_{price}(t) = \frac{|\Delta P(t)|}{\sigma_{ATR}(t)}$$
$$S_{shock}(t) = \begin{cases} 
+1 & \text{if } \Delta P(t) \ge \theta_{shock} \cdot \sigma_{ATR}(t) \quad (\text{Upward Shock}) \\
-1 & \text{if } \Delta P(t) \le -\theta_{shock} \cdot \sigma_{ATR}(t) \quad (\text{Downward Shock}) \\
0 & \text{otherwise}
\end{cases}$$
*(Structural threshold $\theta_{shock}$ is prospectively fixed, e.g. 2.5 standard movement units, without tuning).*

#### 2. Open Interest Contraction Component ($C_{OI}(t)$)
Using the PIT-qualified aggregated statistics from `/futures/data/openInterestHist` (period = 15m):
$$\Delta \text{OI}(t) = \frac{\text{sumOpenInterest}(t) - \text{sumOpenInterest}(t - W_{OI})}{\text{sumOpenInterest}(t - W_{OI})}$$
Over lookback $W_{OI} = 4$ bars (1 hour):
$$C_{OI}(t) = \begin{cases} 
1 & \text{if } \Delta \text{OI}(t) \le -\theta_{OI} \quad (\text{Significant Contraction}) \\
0 & \text{otherwise}
\end{cases}$$
*(Contraction threshold $\theta_{OI}$ is prospectively fixed, e.g. 1.5% or 2.0% net contraction, without return-label fitting).*

#### 3. Structural Confirmation & Invalidation ($R_{conf}(t)$)
Within confirmation horizon $W_{conf} \in [1, 2]$ bars (15–30 minutes post-shock):
- For a **Downward Shock** ($S_{shock} = -1$): Reversal confirmation requires $P_{close}(t) > P_{high}(t-1)$ (bullish reclaim bar), while remaining strictly above the shock low ($P_{low} > \min_{k \in [0, W_{shock}]} P_{low}(t-k)$). Violation of the shock low constitutes **immediate invalidation**.
- For an **Upward Shock** ($S_{shock} = +1$): Reversal confirmation requires $P_{close}(t) < P_{low}(t-1)$ (bearish rejection bar), while remaining strictly below the shock high. Violation of the shock high constitutes **immediate invalidation**.

#### Composite Entry Alert Function:
$$\text{Alert}(t) = \begin{cases}
\text{LONG\_CANDIDATE} & \text{if } S_{shock}(t) = -1 \land C_{OI}(t) = 1 \land R_{conf}(t) = \text{BULL\_CONFIRMED} \\
\text{SHORT\_CANDIDATE} & \text{if } S_{shock}(t) = +1 \land C_{OI}(t) = 1 \land R_{conf}(t) = \text{BEAR\_CONFIRMED} \\
\text{NONE} & \text{otherwise}
\end{cases}$$

### 5.3 Mandatory Baseline Controls & Incremental Null Hypothesis

To scientifically establish whether Open Interest contributes genuine predictive signal rather than serving as a proxy for existing indicators, two explicit controls and a direct incremental null hypothesis are mandated:

#### Control (A): Price-Shock / Reversal Only (No OI)
$$\text{Alert}_A(t) = \begin{cases}
\text{LONG\_CANDIDATE} & \text{if } S_{shock}(t) = -1 \land R_{conf}(t) = \text{BULL\_CONFIRMED} \\
\text{SHORT\_CANDIDATE} & \text{if } S_{shock}(t) = +1 \land R_{conf}(t) = \text{BEAR\_CONFIRMED} \\
\text{NONE} & \text{otherwise}
\end{cases}$$
*Purpose:* Measures the baseline predictive power of pure mechanical price reversal / volatility mean-reversion without any positioning data.

#### Control (B): Price Shock + Realized Volatility + Volume / Momentum (No OI)
$$\text{Alert}_B(t) = \begin{cases}
\text{LONG\_CANDIDATE} & \text{if } S_{shock}(t) = -1 \land \text{VolSpike}(t) = 1 \land \text{MomExhaust}(t) = 1 \land R_{conf}(t) = \text{BULL\_CONFIRMED} \\
\text{SHORT\_CANDIDATE} & \text{if } S_{shock}(t) = +1 \land \text{VolSpike}(t) = 1 \land \text{MomExhaust}(t) = 1 \land R_{conf}(t) = \text{BEAR\_CONFIRMED} \\
\text{NONE} & \text{otherwise}
\end{cases}$$
Where $\text{VolSpike}(t) \equiv \text{Volume}(t) > 2.0 \times \text{MA}_{20}(\text{Volume})$.  
*Purpose:* Isolates whether Open Interest contraction provides any distinct information beyond conventional high-volume exhaustion bars and momentum divergence.

#### Direct Incremental $\Delta \text{OI}$ Null Hypothesis ($H_0$):
Let $Y_{t+h}$ be the subsequent price return over evaluation horizon $h \in \{4\text{h}, 8\text{h}, 24\text{h}\}$.
$$H_0: \mathbb{E}[Y_{t+h} \mid \text{Alert}(t)] - \mathbb{E}[Y_{t+h} \mid \text{Alert}_B(t)] \le 0$$
$$H_1: \mathbb{E}[Y_{t+h} \mid \text{Alert}(t)] - \mathbb{E}[Y_{t+h} \mid \text{Alert}_B(t)] > 0$$
If the incremental Sharpe, median return, or win rate of $\text{Alert}(t)$ over $\text{Alert}_B(t)$ fails to reject $H_0$ under calibrated synthetic inference, Open Interest is ruled **computationally redundant**, and the mechanism is falsified.

### 5.4 Operational Feasibility & Unknowns
- **Episode Frequency:** Completely **UNKNOWN**. The B-line planning assumption of approximately 1 candidate per 48 hours is an operational guideline, not an empirically observed event rate. Under severe shock and contraction filters, episodes may occur as rarely as 1–2 times per month.
- **4h–24h Holding Feasibility:** **UNKNOWN**. Whether structural reversal targets can be achieved within 4–24h before hitting trailing or stop levels cannot be evaluated without admitted market observations.
- **Projected PnL:** Strictly **NONE**. Projecting simulated profits or multiplying edges by arbitrary leverage is forbidden under this feasibility gate.

---

## 6. Future Public BTC Open Interest Collector Permit (DRAFT — NOT AUTHORIZED TO EXECUTE)

This section specifies a rigorous future data collector permit draft. **EXECUTION OF THIS PERMIT IS STRICTLY FORBIDDEN** until a separate, exact-SHA Controller authorization is issued and independent novelty and synthetic calibrations have cleared.

### 6.1 Purpose & Scoped Rights
- **Authorized Purpose:** Automated prospective verification of Open Interest availability clocks, latency, schema integrity, and gap frequency for BTCUSDT USDⓈ-M perpetual contracts.
- **Entitlement / Legal Basis:** Binance Public REST API Terms of Service (public market data, unauthenticated, non-commercial algorithmic research).
- **Network Constraints:** Single outbound HTTPS connection. Strict prohibition of proxy auto-rotation or anti-ban bypass techniques.

### 6.2 Candidate Endpoints & Rate Limits
1. `GET /fapi/v1/openInterest?symbol=BTCUSDT` (IP Weight: 1)
2. `GET /futures/data/openInterestHist?symbol=BTCUSDT&period=15m&limit=30` (IP Weight: 1)
3. `GET /fapi/v1/time` (IP Weight: 1, clock synchronization reference)

#### Strictly Forbidden Subscriptions / Endpoints:
- **NO** WebSocket `aggTrade` streaming.
- **NO** L2 order book delta (`depthDiff`) or full depth streams.
- **NO** Liquidation order streams (`/ws/<symbol>@forceOrder`).
- **NO** Private user-data streams or authenticated account endpoints.

### 6.3 Resource Caps & Safety Limits
| Constraint | Value | Rationale / Enforcement |
|---|---|---|
| **Max Ingress Duration** | 120 seconds | Bound process execution time strictly. |
| **Max Record Cap** | 500 records | Prevent unbounded disk or memory allocation. |
| **Max Total Ingress Bytes** | 5.0 MB | Hard payload cap; fail closed if exceeded. |
| **Max Polling Frequency** | 1 request per 15 minutes | Align strictly with strategy decision cadence. |
| **Rate Limit Ceiling** | 5 requests/sec max | Less than 5% of Binance 2400/min IP limit. |
| **Abort Policy** | `STOP_ON_FIRST_LIMIT` | Immediate shutdown on HTTP 429, 418, or `x-mbx-used-weight-1m` > 1800. |

### 6.4 Observability, Clock Auditing & Provenance
Every collected response must log:
1. `client_request_monotonic_ns` and `client_response_monotonic_ns`.
2. `local_receipt_wall_ms` (UTC).
3. `binance_server_time_ms` (obtained from `/fapi/v1/time`).
4. Computed clock skew: $\Delta t_{skew} = |T_{server} - T_{local}|$. (If $\Delta t_{skew} > 5000\text{ms}$, trigger `CLOCK_SKEW_ABORT`).
5. SHA-256 digest of the raw unmodified JSON response bytes.
6. Git commit SHA and collector version tag (`0.6.0_oi_pit_collector`).

### 6.5 Source Quality Control (QC) Gates
Prior to admitting any record to prospective storage:
1. **Schema Integrity:** Verify all fields (`symbol`, `sumOpenInterest`, `sumOpenInterestValue`, `timestamp`) exist and parse to valid positive floats and integers.
2. **Monotonicity:** Verify that successive buckets have $T_{timestamp}(k) = T_{timestamp}(k-1) + 15\text{m}$. Any reversal or non-15m gap triggers `CADENCE_IRREGULARITY_FLAG`.
3. **Deduplication:** Reject identical `(symbol, period, timestamp)` keys unless SHA-256 payload is identical.
4. **Staleness Bound:** Reject statistical responses where $(T_{local} - T_{timestamp}) > 30\text{m}$.

---

## 7. Falsification Gates & Terminal Feasibility Dispositions

### 7.1 Historical Horizon Gate: `SOURCE_NOT_READY`
- **Assessment:** Evaluation of historical multi-year backtests (e.g. 2021–2023) using authentic Open Interest is structurally blocked. Official Binance USD-M `/futures/data/openInterestHist` provides only ~30 days of retention, and historical price archives (e.g. Vision) do not contain OI.
- **Rule Enforcement:** Reconstructing historical OI via price/volume proxies, synthetic regression, or interpolating 30-day distributions onto 2021–2023 is strictly rejected.
- **Verdict:** **`SOURCE_NOT_READY`** for any retrospective multi-year strategy trial.

### 7.2 Prospective Monitoring Gate: `PARTIAL_SOURCE_QC_ONLY`
- **Assessment:** Live prospective monitoring of 15m Open Interest is architecturally feasible via `/fapi/v1/openInterest` snapshots and `/futures/data/openInterestHist` statistical buckets.
- **Limitation:** A 30-day prospective sample cannot validate long-term seasonal stability, tail-risk behavior, or a 48h event-rate candidate frequency.
- **Verdict:** **`PARTIAL_SOURCE_QC_ONLY`**. Does not constitute authorization for strategy trading or claim of independent alpha.

### 7.3 Workpackage Terminal Disposition
$$\mathbf{OI\_SOURCE\_CONTRACT\_DRAFT\_READY}$$

### 7.4 Summary of Missing Data & Unknowns
1. **Historical 2021–2023 OI Series:** Permanently missing from public Binance REST infrastructure.
2. **Aggregation Latency Distribution ($\Delta t_{pub}$):** Empirical delay between window close and REST publication is unmeasured; requires prospective observation under a future permit.
3. **Natural Episode Frequency:** The true frequency of co-occurring price shocks ($> 2.5 \sigma$) and OI contractions ($> 1.5\%$) on BTCUSDT is unobserved and unknown.
4. **Execution Slippage & Realized Costs:** Intraday fee regimes, queue non-fills, and spread costs during shock regimes remain uncalibrated (governed by P1A cost engine).

### 7.5 Handoff & Next Steps
- This deliverable is frozen on isolated branch `docs/v06-reset-r1-price-shock-oi-source-pit`.
- Handoff to **ChatGPT-1** for independent Source/PIT verification.
- No source data collection or strategy execution may commence until independent reviews for Task P0 (Crosswalk) and P1 (Synthetic calibration & Episode accounting) are completed and Controller L2 acceptance is published.
