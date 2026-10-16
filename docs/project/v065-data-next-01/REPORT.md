# V065-DATA-NEXT-01 — D2 QC repair and source-admission proposal

Disposition: **ENGINEERING_DELIVERED / INDEPENDENT_ACCEPTANCE_PENDING**. Current scientific disposition remains `SOURCE_OR_ECONOMIC_BLOCKED`. ChatGPT-1 / Controller 0 retain acceptance and dispatch authority. This report grants no acquisition permission.

## Frozen identity and scope

Observed public `EXASHXE/btc-quant-agent-public` remote `v0.6.5` HEAD on 2026-10-17: **`275bb5fc71fa21944375d8118945a6074030353e`**, matching the previously observed SHA. Local branch **`engineering/v065-data-next-01`** is directly parented to that commit, in isolated sparse worktree `/tmp/v065-data-next-01`, backed by `/tmp/v065-data-next-01-base`. The supplied `/root/workspace/project/quant-0.6.5` contained no code/Git metadata. No existing checkout was switched or reset.

D2 code/tests are **absent from this main tree**. The patch selectively brings forward the following two frozen files and repairs the script; it merges no historical branch. The frozen report is unchanged and remains the evidence of what its author claimed.

| Required evidence | Frozen commit | Selected path / blob |
|---|---|---|
| D2 implementation | `803a4173717ace9c03ff97051b7696210e183bef` | `scripts/research/r11_d2/binance_core_pilot.py` / `dbc724f0dfd0a3f537e7ddb6bd1f818913ef7707` |
| D2 original synthetic tests | same | `tests/research/r11_d2/test_binance_core_pilot.py` / `3285d80ebf63a39f91dddeb01f307851d8e16b89` (carried forward unchanged) |
| D2 author report | same | [frozen report](https://github.com/EXASHXE/btc-quant-agent-public/blob/803a4173717ace9c03ff97051b7696210e183bef/docs/project/V06_R11_D2_BINANCE_CORE_DATA_FOUNDATION_PILOT_R1.md) / `f7bb0f322dd8317d983abe143b0dcf86c21414c2` |
| Independent Sol consequential gate | `e010154a7592f89b325445fad94c6d34dd0f509a` | [review](https://github.com/EXASHXE/btc-quant-agent-public/blob/e010154a7592f89b325445fad94c6d34dd0f509a/reviews/v0.6/b_line/V065_R3_1_INDEPENDENT_SOL_WHOLE_REPO_CONSEQUENTIAL_GATE_REVIEW_R1.md) |
| Q1 negative source/PIT/capacity audit | `8c3e53f8fe37d9a8acd340944b843e04f05d2fdc` | [review](https://github.com/EXASHXE/btc-quant-agent-public/blob/8c3e53f8fe37d9a8acd340944b843e04f05d2fdc/reviews/v0.6/b_line/V06_R11_Q1_1_INDEPENDENT_WAVE1_SOURCE_PIT_CAPACITY_AUDIT_R1.md) |
| Q2 bounded pilot decision | `c07c60385479f0d595352ad751c1c49150b4cbbc` | [decision](https://github.com/EXASHXE/btc-quant-agent-public/blob/c07c60385479f0d595352ad751c1c49150b4cbbc/reviews/v0.6/b_line/V06_R11_Q2_CONTROLLER_CAPACITY_EXPANSION_AND_NEXT_STAGE_DECISION_R1.md) |
| Supplemental OKX report, documentary metadata only | `7f8c6acadead47dccdeba80b2ae27c2497ee8cdf` | [E2 report](https://github.com/EXASHXE/btc-quant-agent-public/blob/7f8c6acadead47dccdeba80b2ae27c2497ee8cdf/docs/project/V06_R11_E2_OKX_HISTORICAL_PORTAL_ONE_FILE_PILOT_R1.md) / `6a6b172ea734d8c62f0c581faaca0d4e86dc48c1` |

Evidence labels: `VERIFIED_CODE` means inspected code/metadata, `SYNTHETIC_TESTED` means generated fixtures, `AUTHOR_REPORTED` means inherited documentary claims, and `UNKNOWN` means no qualifying witness. No original market archive, acquisition manifest or local source receipt was inspected or replicated here. Git/source-code access and official documentation reads are distinct from market-data acquisition. Runtime model-mode attestation is not independently verified.

## Changed invariants

1. Metrics numeric failures now put `INVALID_METRIC_VALUE` into object errors. Invalid text, negative values, NaN/sNaN and positive/negative infinity fail every numeric metric column, including both OI fields. Zero remains permitted. Missing values stay explicit `PARTIAL_PASS`; neither missing nor invalid values count as fully valid rows, and nothing is zero-imputed.
2. Funding requires the actual UTC calendar month's exact set of 8-hour settlement slots, exact row count, strictly increasing raw timestamps and one observation per slot. Coverage allows **0..5000 ms nonnegative delay** from each slot; a one-hour phase shift, adjacent-month substitution, missing endpoint, duplicate slot with different jitter or empty file fails. Raw timestamps remain unchanged. This is a bounded D2 engineering tolerance, not independent proof of matching-engine behavior or a universal funding schedule.
3. Monthly bars now enforce full calendar coverage and endpoints, rather than merely assigning `expected_rows=44640`. Leap February and December/year rollover are exercised synthetically. Daily row counts and metrics row counts are also explicit.
4. The unchanged frozen source plan is shared by execution and manifest reconciliation: exact family/symbol/period/cadence/reuse/URI identities, duplicate records, incomplete QC, contradictory PASS diagnostics and unverified checksum status fail closed. Missing ZIP/checksum pairs are explicit `MISSING_OBJECT` and STOP. Existing daily/monthly parity still gates execution; parity means equal parsed CSV headers/rows, not literal archive bytes or independent economic observations.
5. Receipt **manifest_version=2** separates expected, attempted and evaluated objects. A failed/unfinished object cannot inflate evaluated counts. `calibration_sample_objects` is a source-plan classification; `newly_acquired_objects` counts successful archive fetches with nonzero attempts and is zero during offline verification. This intentionally corrects the old offline field meaning; consumers must inspect the manifest version.

The inherited `...ACCEPTED_WITH_LIMITS` program terminal is an engineering receipt label, never independent source/scientific acceptance. Existing `receiver_first_known=UNKNOWN`, `economic_period_end=UNPROVEN_FROM_ARCHIVE_LABEL`, `PIT_UNKNOWN` and gates are preserved. The inherited T+1 publication label denotes a documented batch cadence, not a measured first-release timestamp.

## Reconciliation: 215 versus 222

`VERIFIED_CODE` frozen task-plan arithmetic:

| Archive representation | Correct planned objects | Reused | Calibration/sample |
|---|---:|---:|---:|
| Daily 1m Last klines | **69** | 7 | 62 |
| Monthly 1m Last klines | 2 | 0 | 2 |
| Daily 1m Mark klines | 69 | 7 | 62 |
| Monthly fundingRate | 2 | 0 | 2 |
| Daily metrics (also contains OI) | 69 | 7 | 62 |
| Daily aggTrades sample | 2 | 0 | 2 |
| Daily trades sample | 2 | 0 | 2 |
| Total | **215** | **21** | **194** |

The author family table says **76** daily Last objects, **69** new, rather than 69/62. That single seven-object overcount produces **222** family objects and 201 new, inconsistent with its total row. Correcting it makes the family-status arithmetic **208 PASS + 7 PARTIAL_PASS = 215**, consistent with the author's total; these statuses remain **AUTHOR_REPORTED, not a replayed result**. It is not evidence of seven extra physical ZIPs. The planned monthly Last archives overlap daily representations; Trades/AggTrades also describe overlapping executions.

Additional arithmetic inconsistency: family compressed-byte figures sum to the stated **63,817,097 B**. Family expanded-byte figures sum to **338,479,481 B**, whereas the total claims **323,945,031 B**, a **14,534,450 B** difference. Neither expanded total can be certified without the original manifests and permitted local byte replay. Their reported SHA-256 identifiers are not proof that the files are accessible or complete. Do not repair this discrepancy by inventing replacement byte totals or new manifest hashes.

## Admission matrix and rights basis

[SOURCE_ADMISSION_MATRIX.csv](SOURCE_ADMISSION_MATRIX.csv) contains **33 rows × 18 fields**: Binance BTCUSDT USD-M, Binance BTCUSDT Spot, and OKX BTC-USDT-SWAP, each covering Last, Mark, Index, Premium, Funding, Trades, AggTrades, OI, Metrics, quote and depth. Fields for **rights, source identity, physical bytes, schema QC, original timestamps, revision, receiver-known PIT, execution cost, coverage, sample exposure, OFFLINE_DEV eligibility and causal scientific eligibility** are separate. Spot derivative-only families are explicitly N/A; N/A is not evidence that a similarly named vendor product exists or does not exist.

| Sources / families | OFFLINE_DEV disposition proposed | Causal scientific disposition |
|---|---|---|
| Binance USD-M Last / Mark | Conditional parser/integrity DEV after rights and patched actual-byte QC | Blocked: historical receiver PIT and execution cost absent |
| Binance USD-M Funding / OI / Metrics | Conditional QA; retain settlement/label ambiguity and missingness | Blocked: no original announcement/first-known proof; OI and Metrics share source objects |
| Binance USD-M Trades / AggTrades | Conditional native-schema DEV for 2024-01-01 | Blocked: not executable quotes, queue or receiver clocks; no independent sample multiplication |
| Binance USD-M Index / Premium | Candidate only; no D2 family-byte witness | Blocked: source/PIT unqualified; reference prices nonexecutable |
| Binance USD-M quote / depth | Unknown exact historical object and rights/channel; no acquisition | Blocked: no reconstructible/receiver-stamped execution witness |
| Binance Spot Last / Trades / AggTrades | Candidate only; Q2 D2 USD-M permit cannot silently expand to Spot | Blocked: exact bytes/QC/clocks/exposure unresolved; no Spot/perp identity substitution |
| Binance Spot quote / depth | Candidate only, rights and native object unknown | Blocked; derivative-only Spot cells N/A |
| OKX portal Last / Trades / Funding | Conditional auxiliary DEV; E2 author claims require independent verification | Blocked: confirm semantics, calendar/version, original clocks and costs unresolved |
| OKX portal depth / derived quote | Prefix-schema DEV only; no full L2 reconstruction | Blocked: prefix cannot establish whole-day integrity, sequences or executable quotes |
| OKX Mark / Index / Premium / AggTrades / OI / Metrics | No verified exact portal witness; OI API rights separate | Blocked; no invented absence/availability or universal multiplier/8h interval |

Matrix evidence keys map to the frozen links above plus:

- **Binance-Terms:** [frozen Vision Terms](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md), original blob `87d04e216f62c86a2c797fbb7637404d6d602687`. The grant is conditional personal/noncommercial/nonproduction research; it cannot be transferred to unrelated REST/WS sources or live execution. Owner applicability and third-party indicator restrictions remain unresolved. **Fresh documentation read found current blob `d47bf55acfd83456d6fe57b31f400b42bda83c19` despite the same displayed version/date** ([exact current blob](https://api.github.com/repos/binance/binance-public-data/git/blobs/d47bf55acfd83456d6fe57b31f400b42bda83c19)). The script retains its pinned terms guard: changed bytes require review, not automatic repinning.
- **Binance-README:** [frozen official README](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/README.md), blob `e01e34a0b0cd91d62386a5a237190a3167138bae`. Spot timestamps switch to microseconds from 2025-01-01; USD-M source schemas differ. Neither documented family names nor release cadence prove complete actual historical objects.
- **OKX-Terms:** [official Historical Data Terms](https://www.okx.com/en-sg/help/historicaldata-terms-and-conditions), published/updated 2023-10-26, read 2026-10-17. Portal personal use includes retention and own-strategy development; its license is revocable and requires deletion on revocation/expiry. This narrows Q1's portal-rights blocker as Q2 records; it is not a blanket generic API/OI grant or owner-specific eligibility decision.

E2's reported 2024-01-15 trade/kline partition is UTC+8, while its L2 prefix is UTC. Contract sizes require date/version-specific instrument metadata; a same-day volume ratio alone is not a universal multiplier attestation. Its `confirm=0` completion claim is unresolved, and its verify path is network-dependent per the independent gate. This task makes no E2 code changes.

## Two missing witnesses, ranked by information value — proposals only

Neither card is dispatched. Use only an independently approved local nonprotected workspace; no source payload to Git, chat or an LLM. An object hash currently marked UNKNOWN must be established by a later authorized operator, never fabricated here. Existing sample dates are **EXPOSED_DEV**, usable for source diagnostics only. If the original contemporaneous evidence does not exist, return STOP rather than build a collector, buy data, substitute a current API snapshot, or manufacture a timestamp.

### W1 — Historical metrics clock / revision witness

**Question changed:** can any D2 OI/metrics observation be treated as originally known, rather than just retrospectively labeled?

**Exact source/date:** already-held official Vision `data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2024-01-01.zip` and its exact checksum, paired with **contemporaneously retained original publication/receiver evidence for the same source fields** at labels `2024-01-01 00:00:00`, `00:05:00`, `00:10:00`, `00:15:00` UTC. A current OI endpoint is not a substitute for the archived aggregate fields. Source/receiver log file identities and original hashes are **UNKNOWN**, hence a prerequisite, not an assertion of availability.

**Rights:** Vision retention/personal research basis plus the owner's applicable terms at original acquisition; any independent receiver/provider logs require a separate written retention/research grant. Terms-vintage mismatch requires review. No new archive GET is proposed where the D2 object already exists.

**Cap:** one existing ZIP/checksum pair, at most **1 MiB compressed / 8 MiB expanded**, four selected native observation labels, at most **32 matching original messages**, and **256 KiB** of provider clock/schema/revision attestations. Stop at any cap; do not substitute a larger window or a new date.

**Protocol:** freeze local object identities and selection before inspection; locally verify checksum, schema, values and stock-versus-flow definitions without exposing raw rows. Obtain issuer-level definition of the observation window and the original revision/publication process. Match each label to its original unchanged message and contemporaneous receiver log, retaining conflicting versions. Export only counts, hashes, clock bounds, missingness and the accepted/unaccepted claims.

**Required raw clocks:** original label, economic observation/window start and end (nullable), venue event/transaction time where actually present, original publisher emission/availability with uncertainty bound, receiver first-byte and complete-message UTC plus monotonic clock, UTC synchronization/error bound, durable-write ACK, actual historical available-at bound, archive download time and revision/vintage. Keep each field separate; an archive Last-Modified, fresh transfer receipt or assumed five-minute lag supplies none of the missing historical clocks.

**Acceptance:** all four observations have matching identity/units, documented window semantics and a provenance-verifiable original availability/receiver interval. Native event/receipt uncertainty must support an ordering at the proposed decision boundary; overlapping uncertainty intervals cannot establish causality. Missing native clocks stay null. Semantic evidence alone may upgrade only the semantic field, **not receiver-known PIT**. Even a positive four-label witness proves only those observations, not all January/history or Alpha.

**STOP:** no original matching receiver logs; unresolved source-field equivalence/window; unknown applicable rights; missing original clock bound or revision identity; mismatching hashes; cap/exposure breach. Terminal `STOP_HISTORICAL_PIT_UNPROVEN`, while a separate verified semantic finding may still be retained for DEV.

### W2 — Receiver-stamped executable quote / conservative taker-cost witness

**Question changed:** is there any auditable native executable-price/cost evidence beyond Last/Mark candles and trade prints?

**Exact source/date:** an **already-existing, lawfully retained** Binance **USD-M BTCUSDT** native full depth snapshot plus contiguous depth updates, best bid/ask and raw trades for **2024-01-01T00:00:00Z ≤ t < 2024-01-01T00:15:00Z**. Include one boundary snapshot immediately before the window solely as the reconstruction anchor. Snapshot/update/BBO/trade original file identities are **UNKNOWN**; this is an evidence request, not an assertion that Vision has these receiver logs. Do not replace with Spot, COIN-M, bookDepth summaries, synthetic BBO from candles, OKX L2 prefix or present-day endpoints.

**Rights:** independently establish the exact feed/archive/provider's retention and personal offline research license and owner applicability. Vision rights do not automatically cover unrelated historical REST/WS captures. No paid data, live endpoint, account access or collector is authorized by this proposal.

**Cap:** one instrument, 15 minutes, one anchor snapshot and at most **250,000 messages / 64 MiB compressed / 256 MiB expanded** total; stop at whichever bound occurs first. Additional metadata/fee documents at most **1 MiB**, no account identifiers. No wider date, extra instrument or automatic retry acquisition.

**Protocol:** freeze hashes, sequence schema, depth limits, contract units, date-specific instrument metadata and clock bounds. Replay original snapshot/updates locally; check every sequence link/reset, checksum where defined, positive finite prices, nonnegative sizes and uncrossed BBO. Produce counts/coverage/gap/hash summaries. At fixed UTC second boundaries, measure bid/ask spread and visible taker book-walk cost for the predeclared **100 and 1,000 USDT** notionals in both directions; require complete visible depth or report unavailable. Apply a documented conservative date-applicable taker fee assumption and expose its uncertainty. No order, strategy signal, trade return or parameter search. This is a sample execution-cost diagnostic, not a strategy trial.

**Required raw clocks:** unmodified venue event and transaction times where supplied, update/sequence IDs, snapshot generation/request-response times if preserved, receiver first-byte/complete-message UTC and monotonic time, bounded UTC clock error (target **≤10 ms**, otherwise STOP for timing claims), durable ACK, gap/reset periods, original available-at, source vintage/correction metadata and local transfer completion. Own order/fill ACKs remain **UNKNOWN** because no orders are requested. Without actual ACK/fill evidence, do not claim maker fills, queue position or realized slippage.

**Acceptance:** verified rights and original receiver lineage; exact instrument/units; complete sequence/anchor and measured bounds; causal timing only when clock intervals permit ordering; auditable costs for the two notionals with explicit unavailable cases. Qualification is limited to these 15 EXPOSED_DEV minutes and a conservative taker book-walk bound. Latency-dependent impact, maker queue/fills, funding account effects, broader cost regimes and no-action account utility remain unaccepted.

**STOP:** original receiver history absent; rights or exact source unknown; any unbridged gap/invalid sequence/checksum; incomplete anchor; timestamp rewriting; insufficient depth; fee/contract ambiguity; clock error above threshold; any byte/message/window cap; any need for a live/private endpoint or protected data. Terminal `STOP_EXECUTION_WITNESS_UNAVAILABLE` or a narrower cost-only DEV result with timing explicitly unknown. No automatic fallback acquisition.

## Validation and handoff

Only changed-invariant T2 checks were run. `test_data_next_01.py` contains synthetic OI/funding/calendar/duplicate/manifest tests, including mocked execution-path receipts. Those receipt tests deliberately stub source QC/terms validation to isolate manifest behavior; parser tests exercise the actual parser. Mocked acquisition-path tests make **zero network calls**. Generated temporary archives contain only test-generated rows, never exchange bytes.

- Frozen implementation regression evidence: three selected new test methods against `803a417...` produced **46 expected failing negative subtests, zero errors** (invalid metrics, incomplete/shifted funding). No raw data was used.
- Patched changed-invariant suite: `python -m unittest discover -s tests/research/r11_d2 -p test_data_next_01.py -v` — **17 test methods PASS**. Covers finite/zero positives, invalid/negative/NaN/Inf OI, missing values, missing endpoints, same-slot duplicates, off-grid/adjacent-month funding, leap/year boundaries, monthly bar coverage, real synthetic ZIP parity, 215-object plan, duplicate/missing/contradictory manifests and early STOP.
- Focused compatibility controls from the frozen test module: Last bars, metrics/PIT, funding and daily/monthly parity — **4 PASS**.
- `ruff check scripts/research/r11_d2/binance_core_pilot.py tests/research/r11_d2/test_data_next_01.py` and scoped `git diff --check` — PASS.
- Matrix shape/family coverage, unique identities and separate admission dimensions — checked as a document artifact.
- **NOT_RUN_BY_SCOPE:** original market archive/manifest replay, new acquisition, historical backtests, strategy scores/trials, unrelated global suites, protected tests/data, hosted CI, E2 parser repair, release validation. Branch remains local; no remote publication/merge or workflow change.

No historical source PIT, source rights applicability, real physical-byte completeness, execution economics or Alpha is independently accepted by this engineering delivery. The exact author commit, parent, changed-path Git blobs and final test receipt are supplied outside this self-referential report after committing.

**STOP now at engineering delivery.** Neither witness may proceed without a separate exact source/date/byte/rights/exposure authorization and independent acceptance process. Preserve `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`. No H39/H40/H41, Forward/Final/OOS, account/trading/fund access, collector, paid data, bulk download, CI modification or unauthorized merge.
