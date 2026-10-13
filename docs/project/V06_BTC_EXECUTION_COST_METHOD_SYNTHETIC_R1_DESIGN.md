# BTCUSDT execution-cost method and synthetic calibration R1 — design handoff

Date: 2026-10-13. Status: **COST_RECALIBRATION_METHOD_DESIGNED_PENDING_MEASURED_SOURCE**. This is a design artifact, not a Controller dispatch, implementation acceptance, measured calibration, or Alpha promotion.

## Authority and exact identities

Task: [pinned English instructions](https://github.com/EXASHXE/btc-quant-agent-public/blob/cd0b55e21f85b8d4bf313a4081c9cc1625856267/prompts/v0.6/b_line/V06_BTC_EXECUTION_COST_METHOD_SYNTHETIC_R1.md), commit `cd0b55e21f85b8d4bf313a4081c9cc1625856267`.

Planning authority: [cost recalibration plan](https://github.com/EXASHXE/btc-quant-agent-public/blob/198d0a931cfd610e86553c1f427c57ae60608a65/docs/project/V06_BTC_EXECUTION_COST_RECALIBRATION_PLAN.md), commit `198d0a931cfd610e86553c1f427c57ae60608a65`; Git blob `ab8051bc71997d7aab2c9b38f954330b28a913a9`.

Read-only source baseline: commit `3af438490da4497132a5c32c786752ca527e0d99`:

- [engine.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/3af438490da4497132a5c32c786752ca527e0d99/scripts/strategy_research/g2_btc_exit_aware_r3/engine.py), blob `bf187ace012619eb3f6aee5d9051999459967100`.
- [portfolio.py](https://github.com/EXASHXE/btc-quant-agent-public/blob/3af438490da4497132a5c32c786752ca527e0d99/scripts/strategy_research/g2_btc_exit_aware_r3/portfolio.py), blob `33528e62084feba7c657a657204ccbf41a82cf54`.

GitHub tree responses reported the exact requested planning/source SHAs and were not truncated. All three downloaded plan/source blobs were verified by recomputing Git's blob SHA-1 over their decoded contents. Local controller-review HEAD was `d6500140f3141d179181f2360ad815b5bfe9c954`; it was not substituted for either baseline. During design preparation, no branch was reset, no repository file was changed, and no repository code was executed. Network reads were confined to public GitHub method/source and Binance documentation. No quote feed, market outcome, historical return label, private account, protected/owner/reserved data, or exchange action was accessed. Design-preparation downloads and this report were initially kept in `/tmp` only. No tests were committed. The subsequent user instruction `push` authorizes publication of this design document alone, on a new documentation branch based on the pinned task SHA; it grants no code, test, market-data, or outcome access.

## Reference fees and evidentiary limits

[Binance's USDT-M fee FAQ](https://www.binance.com/en/support/faq/detail/360033544231), updated 2026-05-01 and accessed 2026-10-13, supports the ordinary reference: maker `0.02% = 2 bp = 0.0002`; taker `0.05% = 5 bp = 0.0005`. The public fee-table search rendering also showed that ordinary USDT column. Direct rendering of the dynamic [fee table](https://www.binance.com/en/fee/futureFee) returned no fee rows; therefore this review verifies a documented public reference, not a fully captured currently effective fee schedule. Before operational use, preserve the rendered product/column, access timestamp, effective dates, applicable promotions, and account assumptions.

The FAQ also establishes liquidity removal/addition and execution-notional fee calculation. A marketable LIMIT is taker for the immediately matched quantity; a resting remainder can later fill as maker. Classification belongs to each fill, not the order's name. Unfilled quantity incurs no execution commission. A resting order has uncertain queue priority and fill probability.

User VIP tier, BNB discount, promotions, fee currency, rebates, and actual maker mix remain UNKNOWN. Never apply COIN-M, USDC, TradFi, or another tier's column. The synthetic ledgers below explicitly assume USDT commissions at the ordinary undiscounted reference. A separate fee-currency conversion contract would be required for BNB-paid commissions.

## Decimal ledger contract and proof

Use Decimal values created from canonical decimal strings, not binary floats, with finite-input validation and sufficient declared precision. Units: quantity `q` in BTC; fill price `P`, bid `b`, ask `a`, mid `m=(a+b)/2`, and settlement Mark `M` in USDT/BTC; fee and funding rates dimensionless; amounts in USDT; `1 bp = 0.0001`. Side `s=+1` for long and `-1` for short. Signed inventory is `Q=s*abs(Q)`.

For a flat directional episode with equal entered/exited BTC:

`Trading = s * (sum_exit(q*P) - sum_entry(q*P))`

`Fees = sum_fills(abs(q*P) * f_fill)`

`Funding_T = -Q_T * M_T * r_T`

`Net = Trading - Fees + sum(Funding_T) - OtherDistinctCashCosts`

These signed notional sums reconcile derivative PnL; they are not a claim that a futures wallet transfers the full entry/exit notional. Each actual entry and exit notional is distinct. Deduct only costs absent from fills; an impact already reflected in P must not be deducted again. Funding with positive r debits a long and credits a short; negative r reverses both signs.

Choose and freeze the denominator before evaluation: `N_ref=sum_entry(q*P)` in this report. `Net_bp=10000*Net/N_ref`. The legacy engine instead uses raw entry notional; any future change must expose this difference, preserve old labels, and avoid silent comparisons. Equal-notional M/M, M/T, and T/T fee-only identities are 4, 7, and 10 bp. With changing exit price these are reference sums of leg rates, not exact total commission bp on entry notional. Leverage changes margin exposure, not per-notional fee bp; margin return requires a separate collateral/margin contract.

The algebraic spread identity is:

`G_mid = s*(sum_exit(q*m_x)-sum_entry(q*m_e))`

`D_fill = sum_entry[s*q*(P_e-m_e)] + sum_exit[s*q*(m_x-P_x)]`

`Trading = G_mid - D_fill`

For a taker buy, arrival-mid drag is `(ask-mid)*q` plus any distinct further fill deterioration; for a sell it is `(mid-bid)*q`. Each crossing is half the quoted spread at its own arrival. If P already equals executable ask/bid or actual VWAP, spread is explanatory attribution only. With synthetic b=99998, a=100002 and unchanged mid=100000, buying and selling 0.010 BTC produces Trading=-0.040 USDT: two half-spreads consume one full spread, without another spread subtraction.

Where timestamps permit, partition D_fill into decision-to-arrival signed mid change, arrival-side crossing, and fill-versus-arrival executable-price difference. The last term can combine size impact and post-arrival movement. Separate them only with mutually exclusive evidence; do not add overlapping adverse-selection and slippage charges. Maker fills may have negative immediate mid-to-fill drag, but this does not prove positive edge or guaranteed execution. Later adverse-selection markouts are separate diagnostics unless already accounted in the episode's price movement.

For partial inventory, match exits to a frozen lot/weighted-average basis, recognize each matched quantity's realized PnL, and show remaining quantity and Mark-valued unrealized PnL separately. Entry fees are charged once at entry; they are not charged again on every partial exit. Estimated residual liquidation costs must be labeled estimates and excluded from settled cash. Full notional-flow reconciliation applies only once flat. An unfilled entry creates no position and no completed-trade return; a nonfilled exit leaves real inventory and cannot be reported as flat.

Quantization must be declared per cash event and reconciled to the sum of those rounded events. R3's eight-decimal USDT/ROUND_HALF_EVEN convention is suitable for synthetic comparators, not proof of Binance account rounding. Admit instrument-valid tick, step, minimum-notional, and time validity before use; no invented rounding may create quantity. For the synthetic decision path, require execution time strictly after the decision source's receiver-known-at and acknowledgement no earlier than fill. Verify clock domains rather than comparing unsynchronized provider and receiver timestamps as if equivalent. Reject crossed, nonpositive, stale or sequence-invalid quote evidence under predeclared freshness bounds. Identical event-ID redelivery must be rejected or ignored with zero extra cash; same ID with conflicting payload is a hard error.

## Funding, stops, and causality

[Binance funding documentation](https://www.binance.com/en/support/faq/detail/360033525031) describes funding based on position quantity and Mark, with positive-rate longs paying shorts, and timing/interval qualifications. Its [funding-history schema](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#get-funding-rate-history) documents a Mark associated with the funding charge. This review read documentation only, never the endpoint. Trade Last, entry price, and minute high are not substitutes for that settlement Mark.

Maintain at least economic settlement time, provider publication/event time where verifiable, receiver-known-at, receiver sequence, and accounting posting time. Example: invented settlement at 08:00:00, first receiver availability 08:00:03. A long 0.006 BTC at Mark100400 and r=0.0001 owes 0.060240 USDT for settlement exposure. A decision at 08:00:01 cannot consume that realized rate/Mark/cash report. Receipt at 08:00:03 permits posting an idempotent adjustment tagged to settlement; it does not rewrite the earlier information set or assert receipt at 08:00:00. Previously known forecasts must remain separately labeled forecasts. Until the event arrives, any liability reserve is explicitly estimated and the finalized funding ledger remains incomplete.

Use actual economic position at settlement, not inventory at delayed receipt. A 0.004 exit definitely before settlement leaves 0.006 exposure; the same exit definitely after settlement leaves 0.010 exposure for that charge, even if the message arrives after exit. The ±15-second venue timing qualification prevents a nominal timestamp alone proving membership. Missing or conflicting same-clock economic ordering is ambiguous, not a forced zero or convenient fill-first rule. Quarantine or report both bounds under an explicit future contract. Missing settlement rate/Mark/coverage is COST_INCOMPLETE; zero is accepted only with verified zero rate, zero applicable exposure, or verified absence of settlement in a completely covered interval.

Freeze stop trigger stream (Mark or contract price), threshold, protection conditions, trigger known-at, activation/ACK, and executable order arrival. Mark trigger price is not fill price. A stop-market can execute beyond its trigger after a gap, with partial fills and taker fees. A stop-limit can trigger and remain unfilled. Pending break-even protection cannot act retroactively; activation must follow required ACK and known-at ordering. Unresolved intrabar stop/target ordering remains ambiguous. [Binance order documentation](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade) supplies the trigger/order vocabulary; this review did not place any orders.

## Four regimes: independent assessment and provenance

| Regime | Admissible inputs and provenance | Design verdict |
| --- | --- | --- |
| FEE_ONLY_REFERENCE | Documented ordinary 2/5 bp references and explicit synthetic fill roles/notionals; nonfee effects switched off as an abstraction | Valid fee identities and receipt arithmetic; no executable-performance claim |
| NORMAL_EXECUTION | Versioned applicable fee reference; sequence-valid arrival bid/ask/depth; size, latency, partial completion and fill probability with admitted evidence | NOT_CALIBRATED; no invented normal spread/slippage number |
| ADVERSE_EXECUTION | Same contract, conditional higher spread/size-depth/latency and stop gaps, nonfill/cancellation tails and outages; jointly measured p75/p95 where supported | NOT_CALIBRATED; conditional stress design accepted, plausible magnitude unverified |
| EXTREME_STRESS | Independently frozen extreme liquidity/latency/funding/gap/rejection cases, dependence assumptions and an explicit unresolved-inventory branch | Synthetic stress coverage only; no finite worst-loss or calibrated frequency claim |

Legacy BASE22=(6+2+3)*2 and STRESS44=(12+4+6)*2 are sensitivity conventions, including respectively 12/24 fee bp. They are neither observed normal costs nor a ceiling. Retain them under their original names only. These four regimes are separate counterfactual contracts; they must not relabel or replace frozen R3/R3.1/Goal-B outcomes.

Required future measurement: full spread in price and bp; signed fill-to-mid implementation shortfall; depth at intended size; decision-to-arrival and ACK/fill latency; filled fraction; nonfill/cancel/remainder/time-to-fill; stop-gap shortfall; signed funding debit and credit. Stratify by UTC hour/session, volatility known at decision, intended notional, order type/liquidity role, direction, and data grade. Freeze bucket definitions and observation windows before measuring. Report sample count, completeness, missing/censored cases, p50/p75/p95, uncertainty, and worst observed tail. A reproducible proposed quantile is sorted nearest-rank x[ceil(p*n)], with the rule fixed in the later permit; no quantile is defined for n=0. Tail support and independent-event count must be assessed rather than inferred from raw message volume.

Do not sum marginal p95 components and call it a measured p95 total. Use matched joint execution observations for total-cost quantiles; separately label constructed component shocks. Signed funding quantiles must keep side/rate signs; signed credits cannot all be relabeled positive costs. Nonfill and cancellation are outcomes of all submitted intents, not just successful fills; right-censored resting orders must remain in the denominator.

Public top-of-book alone cannot measure our ACK, actual fill role/VWAP, queue position, maker nonfill probability, or latent market impact. Sequence-valid public depth supports spread/capacity diagnostics, not complete execution distributions. Public tape/book-touch is insufficient to assert a passive fill. This is the hard stop even after a limited future public collection.

## Invented synthetic proof results

All values below are invented, not historical fills or strategy results. Independent inline standard-library Decimal arithmetic at precision40 asserted the stated net values. No repository simulator or data loader was imported.

| Case | Entry and exits (BTC @ USDT/BTC) | Trading USDT | Fees USDT | Funding USDT | Net USDT |
| --- | --- | ---: | ---: | ---: | ---: |
| Long, taker/taker | .010@100003 → .010@100997 | 9.940000 | 1.005000 | -0.100400 | 8.834600 |
| Short, taker/taker | .010@99997 → .010@99003 | 9.940000 | .995000 | +.099600 | 9.044600 |
| Partial long | .010@100003 → .004@100497, .006@100997 | 7.940000 | 1.004000 | -.060240 | 6.875760 |
| Partial short | .010@99997 → .004@99503, .006@99003 | 7.940000 | .996000 | +.059760 | 7.003760 |
| Flat mid, crossed spread | .010@100002 → .010@99998 | -.040000 | 1.000000 | 0 (explicit synthetic no settlement) | -1.040000 |
| Larger adverse fill drag, long | .010@100010 → .010@100990 | 9.800000 | 1.005000 | -.100400 | 8.694600 |
| Stop-market gap, long | .010@100003 → .010@98997, trigger99500 | -10.060000 | .995000 | 0 (explicit synthetic no settlement) | -11.055000 |
| Mixed entry roles | .004 maker@100000 + .006 taker@100003 → .010 taker@100997 | 9.952000 | .884994 | 0 (explicit synthetic no settlement) | 9.067006 |

Long arrival mids are 100000 and 101000; quotes are mid±2, with an additional adverse price unit on each fill. The short uses mids100000/99000 with the same crossing/adverse units. Both have total fill drag .060000 USDT. Long fees are .500015+.504985; short fees .499985+.495015, proving actual exit notionals differ. Their reference-entry bp are approximately 88.3433497 and 90.4487135 respectively. Positive funding uses full quantity at Mark100400 for long and Mark99600 for short; partial cases assume .004 exits strictly before settlement and use only .006 exposure. At identical Mark100400 and full .010 quantity, r=+0.0001 gives long/short cash -.100400/+.100400; r=-0.0001 reverses them exactly.

Mixed-role fees are .080000 maker entry + .300009 taker entry + .504985 taker exit. A marketable LIMIT is tested as taker even though its order type is LIMIT. A no-fill maker intent has zero fill quantity, fee and inventory, with no completed-trade return. An extreme rejected exit has no invented liquidation proceeds and leaves the economic episode incomplete. The adverse row is an arithmetic shock example, not a NORMAL or p95 estimate.

## Finite negative-case plan for a separate implementation grant

Use 24 named cases, fixed invented inputs and exact expected outcomes; no random search, replay expansion, or data access:

1. Long T/T reconciliation, including different entry/exit notionals.
2. Short T/T reconciliation with positive funding credit.
3. Positive/negative funding side symmetry at identical settlement Mark.
4. Equal-notional M/M, M/T and T/T reference fee identities.
5. Marketable LIMIT taker classification.
6. Mixed taker-now/maker-later fills on one order.
7. Maker nonfill: zero inventory/commission and absent completed-trade return.
8. Same-mid bid/ask roundtrip; reject an additional spread deduction.
9. Increasing adverse buy price/decreasing adverse sell price preserves signed loss of execution quality.
10. Partial long exits and one-time entry fee; match the table.
11. Partial short exits and residual settlement exposure; match the table.
12. Open residual: realized and unrealized separated, no fabricated full exit.
13. Valid tick/step rounding and exact quantity conservation with rounded remainders.
14. Off-grid quantity, over-close, nonpositive price, and invalid/min-notional filter rejection (parameterized invalid inputs).
15. Decimal nonfinite inputs, binary-float input, missing mandatory provenance and crossed/stale/sequence-invalid quote evidence rejected.
16. Duplicate fill redelivery changes no cash/inventory; conflicting duplicate rejected.
17. Duplicate settlement redelivery changes no funding; conflicting duplicate rejected.
18. Stop-market gap uses executable fill, not trigger, and correct taker fee.
19. Stop-limit triggers without fill and preserves residual inventory.
20. Break-even cannot activate before prerequisite ACK/known-at; same-clock ambiguity fails closed.
21. Delayed funding retains settlement exposure and cannot enter earlier features; before/after partial-fill variants.
22. Missing settlement Mark/rate/coverage and ambiguous settlement boundary yield incomplete status, not zero.
23. Identical fills with synthetic Last/mid/quote attribution yield identical cash; proxy mismatch and overlapping costs rejected.
24. Identical notional/fills at 1x/10x/15x produce identical fee cash and notional bp; margin-return fields remain separate.

Implementation validation must include an independent financial/PIT review required by the planning document. The present turn verifies design arithmetic only; it does not claim that the future cases passed against code, that Consumer C was repaired, or that a reviewer approved implementation.

## Pinned source implications

R3 engine.py lines20–77 already provide finite Decimal conversion, eight-decimal cash rounding, synthetic adverse tick rounding, one shared fee reference, and actual-effective-notional fees. Lines130–140 conserve residual quantity and reject duplicate exit IDs. Lines298–315 expose explanatory spread/slip/tick drag; lines393–432 reconcile cash but label funding UNKNOWN and fills hypothetical without L2 proof. These foundations can be reused only within a new grant. Cost.effective applies spread+slip to its raw input; feeding an already executable quote into that path without an explicit basis change would double count crossing. The current single fee_bps contract cannot establish per-fill maker/taker mixtures.

portfolio.py lines144–173 uses assumed cadence, adverse rates and Last high as an explicitly labeled sensitivity. It is not signed observed funding at settlement Mark. Preserve it as a legacy comparator; do not silently turn it into settled cash. R3 synthetic stop/ACK paths are conventions, not measurements of venue ACK, queue, or gap distributions.

## Exact proposed next scopes — no authorization issued here

**Next code dispatch:** Controller must name a full 40-hex reviewed base SHA (explicitly naming `3af438490da4497132a5c32c786752ca527e0d99` only if it chooses that baseline), dispatch ID/hash, isolated branch/worktree and write allowlist. Proposed minimal branch name: `v06-btc-cost-synthetic-r1`. Proposed exact initial write paths:

- `scripts/strategy_research/g2_btc_exit_aware_r3/engine.py`
- `tests/test_v06_g2_btc_exit_aware_r3_engine.py`

Scope: synthetic-only per-fill fee/basis contracts, signed partial-position settlement ledger, no-double-count attribution, idempotence and 24 bounded cases. First freeze the fill/funding clock schema and rounding rule; reuse existing Decimal/conservation primitives. Read-only review of necessary related source is allowed only as the new dispatch specifies. No run.py, portfolio.py, source loader, production execution, frozen evidence, protected/private files, dependency, or outcome changes. If delayed-funding Consumer C requires a different path, stop that repair until Controller identifies its exact file and separately expands the allowlist; the initial two-path proposal is not authority to repair unspecified consumers. Grant must state permitted test commands and project final gate, plus independent financial/PIT reviewer and acceptance ownership. Neither a task-prompt SHA nor an old unrelated dispatch supplies this authority.

**Separate next public-data permit:** proposed prospective source-readiness assessment only, BTCUSDT USDⓈ-M, no strategy signals/orders/return labels/repricing. Controller must separately name exact collector SHA/path, output root, wall-clock window and expiration. Proposed hard caps: 24 hours, 100000 quote/depth events, 50 MiB output, stopping at the first limit. Exact source families: public BTCUSDT bookTicker; depth snapshot plus sequence-valid depth deltas for continuity; instrument exchangeInfo filters; and at most four bounded funding-history requests for settlements within that permitted prospective window, including each charge-associated Mark. Restrict exchangeInfo retention to BTCUSDT fields. Preserve receive clocks, sequence gaps, hashes and redaction/retention rules. Only spread/depth/receiver availability diagnostics; no unknown fill distribution may be manufactured from these streams. Endpoint/version details, snapshot retries, rate limits and permitted networking must be frozen in the permit before use. Any additional fetch, historical window, larger budget, actual execution evidence, account evidence, or economic trial needs its own grant. No acquisition occurred here.

The prospective permit would still leave actual ACK, passive queue/fill probabilities, own fill-role/VWAP and complete impact/tail distributions unknown. A finite source assessment cannot resolve every tail. Public-only restrictions remain; do not seek private account data or place orders to fill those gaps. Maintain **NOT_CALIBRATED / COST_INCOMPLETE** as appropriate and halt economic promotion until Controller accepts sufficient permitted measurement evidence.

## Acceptance disposition

Design completed: units/formulas and signed ledger; four regimes with provenance and measurement requirements; ordinary public reference versus unknown user fees; verified invented long/short/partial/stop/mixed-role arithmetic; finite negative-case plan; proposed exact separately gated code/data scopes. Unresolved by design: complete execution distributions, user-effective fee schedule, market calibration, actual settlement receiver contract and implementation validation. Terminal: **COST_RECALIBRATION_METHOD_DESIGNED_PENDING_MEASURED_SOURCE**. No Alpha promotion.
