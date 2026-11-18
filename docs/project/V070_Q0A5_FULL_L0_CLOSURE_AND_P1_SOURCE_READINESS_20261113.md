# Quant v0.7.0 — Q0A5 Full-L0 Scoped Closure & Post-Q0A5 P1 Readiness (2026-11-13)

> **Controller decision:** `ACCEPT_Q0A5_FULL_L0_OFFLINE_SCOPED`. This covers three-symbol synthetic-2030 unified offline Source→E1/Q0B→Q0BC Producer→Mock Q0F→Shadow, G0–G4, and accepted Windows/WSL offline parity. Local authoritative decision: `controller-decisions/V070_Q0A5_FULL_L0_CONTROLLER_CLOSURE_20261113.json`.
>
> **It is NOT approval for public Binance live collection, live Feishu sending, strict UTC/WSL clock qualification, Alpha, V3.8 real-time EXECUTABLE ratings, account access or trading.** The `R1.2` profile remains disabled.

## Evidence summary

- Previously signed: Q0A4 FIX03 synthetic two-stage evidence / E1 bridge, M0+M1, Q0F adapter, G2/G3 post-FIX02 immutable roster and atomic legacy migration, Windows G1 native offline test parity.
- Independent Controller WSL FIX02 suite: **58/58 PASS**, zero skips, 24.64 seconds; independent adversarial migration/restart/cycle identity checks.
- Windows G1 worker: **58/58 PASS**, zero skips on native Python 3.14 AMD64 local NTFS; Controller independently reconciled all **287 actual staged code/evidence files**, **5 actual wheel hashes**, actual Windows NTFS SQLite/Outbox/Shadow contents, and actual summary semantics against WSL. **Controller did not independently launch a second Windows-native test process.** This limitation is explicit and carried into full-L0 decision; repeating a test for count inflation was waived because artifact provenance and semantic checks were independently reviewed.
- Actual synthetic unified Outbox: **2 Mock PROVIDER_ACCEPTED, 1 FAILED EVENT_TTL_EXPIRED retryable=0**, no real Feishu, 17 Shadow observations, 2 schedule manifests, SQLite integrity OK.
- **Post-Q0A5 readiness long-runner**: `lt-post-q0a5-readiness-longrunner-01/`: 14 reports, 2 synthetic fixture JSONs, script, 5 reported unit tests; author reports 10/10 clock/source negative cases, 11/11 V3.8 synthetic opportunity scenarios, 69 factors/21 baseline strategies/7 research combinations reconciled. These are **documentation/contract/reproducibility preparations**, not real Source or strategy qualification. 0-C independently checked the presence of 14 reports, current FIX02 critical file hashes, and live code fences.

## The next real program blocker: trustworthy time and Source

`win_capture/win_clock.py:67` calls `subprocess.run(["w32tm","/query","/status"], capture_output=True, text=True)`. Windows Chinese-locale output produced an observed `UnicodeDecodeError` on raw MBCS bytes. This is **OBS-WINCLOCK-UTF8**, a narrow one-file compatibility defect; fix must not silently change the strict UTC qualification contract.

Author's native Windows read-only snapshot reported `w32tm` **Leap=3 (unsynchronized)**, **Stratum=0**, **Source=Local CMOS Clock**; QPC/Unbiased short-window coherence passed, but **strict UTC remains UNQUALIFIED**. Prior WSL clock jump findings likewise remain unqualified. No privileged time-service modifications are authorized.

Additional bounded L1 preparation gates (currently deliberately fail closed):
- Public REST transport/access excludes `bookTicker`, `15m` and `5m`; `PROTECTED_2024_2026` includes November 2026. Design a present-time Source admission that **never** weakens protected `FINAL_HOLDOUT_2026` or original archives.
- Reconcile Q0B quote TTL `30s` versus Producer `60s`, source snapshot currentness `<=1s`, validated completed 1H/15m/5m and quote arrival time, source epoch/generation and clock steps.
- Stage2 proposed refresh exceeds the 24-request cap (`28>24`). Keep disabled R1.2 until a reviewed plan resolves the budget.
- Build a separately approved (L1) **read-only** public data 3-symbol canary with raw-response/ledger/manifest provenance, bounded runtime and <=24h retention; **no Feishu or account/trading operations** in that canary.
- A later **separate L1** Feishu recipient/secret/hours/card scope is required for real sends. Mock PROVIDER_ACCEPTED does not prove delivery or human read.
- Owner region: Korea. Exchange eligibility, region-specific terms and actual request weights are UNKNOWN until current L1 bounded verification.

## Strategy/Factor Lab handoff

- Product hierarchy: 1D context; 4H regime/obstacles; completed 1H setup; completed 15m trigger; 5m/quote actionability; 2–12h intended holds; human 5–10m response; no auto-orders.
- V3.8 eleven synthetic cases are **research/contract fixtures only**. Proposals such as 4H obstacle room `>=1.2R`, early entry `<=0.45 * ATR_1H`, fee/slippage-adjusted TP1 R or 10m worst-case drift must be pre-registered, challenged and prospectively tested. Do not claim they are authorized current live strategy thresholds.
- Factor registry observed: 69 factors, 21 `WORKING_BASELINE`, seven `RESEARCH_ONLY` multi-leg combinations. The research-only strategy catalog currently exports `required_features=[]`, a metadata discrepancy; `ORDERBOOK_IMBALANCE` and `DEPTH_CHANGE` source coverage is missing, not zero.
- Historical `FINAL_HOLDOUT_2026 [2026-02-01,2026-08-01)` remains protected.

## Next stage queue (no worker dispatched)

1. **P1-A:** narrow `OBS-WINCLOCK-UTF8` fail-first fix in an isolated workspace and Windows native negative replay. Hydrogen can handle a **strictly single-module, decode-only L0-S** implementation with Controller independent review; any change to UTC trust/clock authority must STOP and go to Sol/Astra.
2. **P1-B:** Astra (or Controller interim) architecture ruling on trustworthy clock/Source admission, UTC reference, 30s vs 60s, quote/source freshness, protected present-time vs historical date windows, 24-request budget and UNKNOWN retry; Sol high-risk implementation when capacity available.
3. **P1-C:** safe L0 integration/fixture prep and one bounded Owner Source L1 envelope. After signed Owner scope and Controller checks, allow a finite real public read-only canary. Feishu has an independent L1 envelope.
4. **P2+**: prospective Shadow evaluation, V3.8 risk/cost/response-latency measurement, then 10+ symbol scaling and Factor Registry controlled non-holdout study.

**Authority flags remain unchanged:** `SOURCE_BLOCKED=true`, `SOURCE_QUALIFIED=false`, `SHADOW_QUALIFIED=false`, `ECONOMICALLY_VALIDATED=false`, `ALPHA_CLAIMED=false`, `execution_authority=false`, `REAL_FEISHU_SEND=false`.

**Local document synchronization note:** canonical files are available in GitHub `docs/engineering` under `docs/project`, whereas the partial local mirror in the worker workspace did not contain all them. `MISSING_LOCAL_DOC` means a local mirror gap, **not** a missing canonical GitHub document. Don't invent replacements or silently mutate unrelated frozen snapshots.
