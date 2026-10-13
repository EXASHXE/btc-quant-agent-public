# Controller L2: Accept P1C R2 Independent REVIEW_FAIL

**2026-10-13. Decision: REVIEW_FAIL_ACCEPTED / P1C_R2_NOT_ACCEPTED / CORRECTION_R3_REQUIRED.**
**G2 Alpha, TESTNET, LIVE:** NO_GO.

## Identity and evidentiary boundary

User supplied the complete independent reviewer findings in the current Controller conversation. The reviewer reported verifying four immutable sources and all 42 source-field comparisons using Decimal arithmetic and 1e-10 declared-unit comparison tolerance. This review is not misrepresented as an independently uploaded/signed GitHub review artifact.
- Independent review dispatch `a818bd186be625b3be0bdd7f49e6592ebf1148df`.
- R2 manuscript and JSON `b4f24c763895c97a0c304dc422db76a73761251d`.
- H18 frozen summary/narrative `397a62c1a0fbd6ad14a569a5be0058b1f684f08e`.
- Exit R1 frozen summary `55ac4c631c69f6edbd275462ad23e4486b9782ed`.

Controller separately inspected H18 published STRESS44 description and R2 crosswalk JSON. Recomputing the correctly rounded canonical value for all 42 R2 fields gives **24 original published mismatches, 18 matches**; the JSON correctly flags both 2023 delta errors, unlike the R2 Markdown. These checks do **not** establish historical event-ledger reproducibility.

## Corrected Table 4 (STRESS44; units in headings)

H1−E0 display is the unrounded source difference rounded once at the end; it must not be recomputed from displayed rounded means. Account values are %; arithmetic differences of two such returns must be labelled **pp**.

| Candidate | Year | N | E0 bp | H1 bp | H2 bp | H1−E0 bp | Account E0 % | Account H1 % |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W1_C04 | 2021 | 8 | 104.58 | 107.52 | 91.56 | 2.94 | 7.50 | 7.72 |
| W1_C04 | 2022 | 10 | -11.92 | 21.68 | 48.83 | 33.61 | -1.05 | 1.83 |
| W1_C04 | 2023 | 16 | -21.03 | 35.86 | 17.36 | 56.88 | -2.93 | 4.75 |
| W2_C05 | 2021 | 10 | 131.22 | 130.96 | 182.14 | -0.26 | 12.18 | 12.14 |
| W2_C05 | 2022 | 21 | 39.31 | 66.89 | 28.30 | 27.58 | 6.74 | 11.44 |
| W2_C05 | 2023 | 24 | -45.49 | -18.11 | -24.98 | 27.39 | -8.40 | -3.23 |

## Accepted objections / required corrections

1. **HIGH STRESS44 units:** H18 defines **44 bp round-trip research proxy**: 24bp assumed fees +8bp spread +12bp slippage. The R2 erratum's "4.4bp taker / 8.8bp round-trip" is incorrect; none are verified actual exchange fills or personal fees.
2. **HIGH Markdown/JSON mismatch:** W1 2023 H1−E0 is **56.88bp**, not 56.89bp; W2 2023 is **27.39bp**, not 27.38bp. R2 Markdown marks both MATCH_ROUNDED despite JSON MISMATCH.
3. **HIGH overstated evidence:** Only six annual source event counts and six paired-delta means are shared and numerically reconciled between the two machine summaries (within declared tolerance). The other 30 crosswalk cells have H18 machine value null. No event-level/all-timestamp, full reproducing-ledger, complete regime identity, or absence-of-ledger-defects finding is justified.
4. **HIGH invented cohort origin:** W2 narrative N=(14,17) in 2021/2022 differs from canonical N=(10,21); totals are equal 31. The specific four event identities, claimed cross-year transfer or manuscript drafting boundary and human intent are **UNKNOWN**.
5. **MEDIUM timestamp source:** Exit R1, not H18, has the accepted event identifiers encoding 2021 ten events between 2021-04-26T01:45:00Z and 2021-12-23T20:45:00Z, and 2022 21 between 2022-01-13T18:45:00Z and 2022-12-11T21:00:00Z. These are not receiver-known-at evidence.
6. **HIGH unsupported copying:** The arithmetic coincidence +104.58+23.95=+128.53 and Exit E2 SHORT +23.950589... support an explanatory hypothesis but not an actual manuscript-copy provenance. Provenance is **UNKNOWN**.
7. **HIGH unsupported statistical inference:** 26/56=46.428571...% adverse continuation is **DESCRIPTIVE_ONLY**, not a dependence-aware hypothesis test nor proof of a coin flip/no edge. Four W1 targets contribute 98.06425062826763% and three W2 targets 74.63624800688082% of retrospective reported deltas; **not** an actionable ex-ante classifier.
8. **MEDIUM units:** E0/H1 account returns are %; differences of returns are **percentage points**, not percent.

## Controller disposition

R2 remains an immutable, **failed** erratum version. Commission a new R3 corrected sidecar + machine-readable 42-cell crosswalk with explicit field paths, corrected units/status/causal qualifications, and independent second-review. Do not alter H18/Exit frozen reports, original R2 bytes, historic market/return records, scientific code, or held-out/protected inputs. No historical re-score, new research trial or G2 Alpha authorization is implied.
