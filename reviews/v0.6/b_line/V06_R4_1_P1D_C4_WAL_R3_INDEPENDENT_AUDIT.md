# ChatGPT-1 — P1D R3 Exact-SHA Independent C4 / WAL / Funding / ACK Architecture Audit

**Terminal verdict: `R3_DESIGN_REVIEW_PASS_WITH_LIMITS` — DOCUMENTARY ARCHITECTURE ONLY.** The frozen R3 has materially corrected the independently rejected B01–B07 R2 design. **Option A (separate R4 module/storage/import namespace with immutable V1 C4) is scientifically and procedurally viable *as a design***. No proposed R4 implementation, external immutable R4 manifest, trusted launcher/receiver, real crash/ACK RED-GREEN execution, native venue source, or executable integration has been accepted. This PASS is **not** a green C4 integration gate or waiver of any failing CI, H40, real-source, release or money-control authority.

**Role/date:** ChatGPT-1, independent Supervisory Auditor, 2026-10-14 Asia/Singapore. The reviewer separately read immutable Git source and design, independently recomputed the original C4 SHA-256 file bytes, compared V1 model/reducer/storage and old blocked prototype, checked R3's synthetic timestamp/cash arithmetic, and constructed causal/crash counterexamples. **No independent R3 Python code or test exists to execute under this documentary target; test status `NOT_RUN_DESIGN_ONLY`.** No protected H39/H40/H41/Forward/Final Holdout, private data, market REST/WS, historical returns/PnL, orders, code or CI changes.

## 1. Immutable authority, independently verified identity

| Purpose | Frozen exact evidence |
|---|---|
| **Controller review dispatch** | Commit **`3e8ea27604574c63caf43b5e6d4bff7feb979908`**, blob **`a171c556caebffca74ce3ce19a1b08e255b5b28a`**, path `prompts/v0.6/b_line/V06_R4_NEXT_1_P1D_R3_DESIGN_AUDIT.md`; direct parent `6750150ba88be5a036abc712af7657a43797ef4b`. |
| **Exact frozen R3 design** | Commit **`8c7693700c15f32329614a23b737d34cc7e2b0c4`**, blob **`a5b9af68bf1ddfd0ada5e047e0b6a11bf880e7a0`**, sole path `docs/engineering/v0.6/V06_NEXT_P1D_R4_C4_WAL_VERSION_DESIGN_CORRECTIVE_R3.md`, **164 content lines**. Git compare from `6750150b...`: **ahead 1, behind 0, exactly one ADD doc (164 lines)**; direct parent exactly `6750150b...`; remote `docs/v06-next-p1d-c4-wal-design-r3` HEAD equals the frozen target. |
| Prior R2 design independent fail | Commit **`019682bc0178504ef233e4560bb1e91508954f76`**, blob **`898e5f0fdebf7f60a7f3ef14a540c2f756e5fe2d`**, terminal **`DESIGN_REVIEW_FAIL`**, seven B01–B07 defects; design R2 target **`931ee5c5ae1cbf341ce771269d4829d3eafa3deb`**, blob `b8f18153f17468a64d6772e6abb2097c7705dc68`. |
| Original immutable V1/C4 diagnostic base | **`04cbc46497ed26b0c4e889f30fa10eb8d666a79e`**. Original guard `scripts/g1g3_offline_ports_r1/no_order_port.py` blob **`1aabd107acf8365cfdb7485b754f89a05df4efd2`**. Original model **`78f77d424a4186a2377413c387b2eeae146066c6`**, reducer **`df6a68f4797950f1b9bdbdebc6591745cdea76d5`**, storage **`4d250f5123d57d4df7430b9dc911b5b5208ba81e`**, MarketPitPort **`3c2198325649ea3a64986218ec60953cbb889403`**, durable_supervisor **`9c0fec44287911fad6a64d274f44b9a8c90388d4`**. These original files were fetched read-only at the exact base. |
| Blocked earlier **in-place** R4 diagnostic | Commit **`81a71467ac7a9b852587b6e5f826d8ee28fc769c`**, whose in-place original C4 changes were rejected. Existing actual CI [run `38446896902`](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38446896902) at **that earlier prototype**: 3408 passed, **2 failed** (direct `G1_CORE_MUTATED` plus H40), 2 skipped. **Not** an R3 run or a proof that a future isolated R4 fails/passes. |

**Independence:** 2-E/Gemini document authorship, prior ChatGPT-1 findings and Controller intake are not treated as acceptance. A single report is authored by this auditor on an isolated branch at the exact dispatch base. No old review, frozen design or baseline was modified.

## 2. Original C4 identity: independently recomputed all 13 pinned file SHA-256s — `13/13 MATCH`

**Stronger than a copied table check:** Independently fetched the original no_order_port.py **at `04cbc464...`**, extracted each of its **13 `PINNED_G1_C4_MANIFEST` path→SHA-256 literals**, fetched **each exact content file at the same frozen baseline**, calculated SHA-256 over the returned UTF-8 file bytes using a separate SHA-256 implementation sanity-checked against the standard SHA-256("abc") vector, and compared the hashes individually. **13 match; zero mismatch or unavailable file.** Independently parsed the R3 table at **L17–31**: exactly the same **13 path/hash pairs**, with no addition, deletion or replacement. This independently proves that the R3 *document's* proposed fixed guard matches the actual baseline bytes. It does **not** prove preservation by code which does not yet exist.

| C4 pinned file | Independent byte-hash result |
|---|---|
| `scripts/g1_offline_preview_r1/__main__.py` | MATCH |
| `scripts/g1_offline_preview_r1/analysis_schema.json` | MATCH |
| `scripts/g1_offline_preview_r1/fixtures/long_24h.json` | MATCH |
| `scripts/g1_offline_preview_r1/fixtures/short_24h.json` | MATCH |
| `scripts/g1_offline_preview_r1/fixtures.py` | MATCH |
| `scripts/g1_offline_preview_r1/model.py` | MATCH |
| `scripts/g1_offline_preview_r1/reducer.py` | MATCH |
| `scripts/g1_offline_preview_r1/storage.py` | MATCH |
| `tests/test_v06_g1_offline_preview_r1_core.py` | MATCH |
| `tests/test_v06_g1_offline_preview_r1_decimal_and_ports.py` | MATCH |
| `tests/test_v06_g1_offline_preview_r1_exit_safety.py` | MATCH |
| `tests/test_v06_g1_offline_preview_r1_process_recovery.py` | MATCH |
| `tests/test_v06_g1_offline_preview_r1_wal.py` | MATCH |

**No re-pinning or editing of old C4 paths or literal digests is allowed.** Full legacy runtime behavior and transitive sidecars must be independently re-run on any future R4 implementation SHA; original bytes alone cannot establish unchanged integration behavior.

## 3. B01–B07 consequential matrix

| Finding | Specific correction in frozen R3 | Independent verdict | Residual gate |
|---|---|---|---|
| **B01** author-editable Manifest, original C4 mutation/AST and import trust | **R3 L17–39** preserves 13 originals; **L33–39** makes the Controller/reviewer independently pin the candidate commit, manifest blob, import closure, launcher/verifier and environment; launcher verifies no-follow roots, all files, AST/imports and locks tree **before** candidate import or persistence. | **DESIGN_PASS_WITH_LIMITS**. 13/13 real original SHA-256 content independently matched; no self-approved runtime candidate manifest. | **HIGH, UNIMPLEMENTED:** no new independently pinned R4 manifest, trusted launcher hash/executable, sealed import proof, dependency audit or TOCTOU tests exist yet. |
| **B02** schema v1/v2 ambiguity and cross-version replay | **R3 L41–67** fixes sole R4 identity **`G1_CAUSAL_R4_V2`**, Genesis 7 fields, state 12 fields/43 V1-core projection, domain-tagged SHA-256, exact WAL/record/ACK/checkpoint versions, separate V1↔R4 failure matrix and no implicit migration. | **DESIGN_PASS_WITH_LIMITS**; independently compared R3's **43** listed core keys against V1 initial_state's **48** top-level keys less exactly 5 excluded; no key mismatch. | **HIGH, UNIMPLEMENTED:** exact payload-schema validators per event-kind, transitive import closure, executable V1/R4 cross-replay rejection and receipt validation remain prospective. |
| **B03** after_append/fsync confusion and corrupt-WAL-prefix salvage | **R3 L69–93** calls after_append **pre-fsync**, separates valid pre-fsync survivor, absent survivor, torn tail HARD STOP, fsync/parent directory, checkpoint pending/final and ACK recovery. Original V1 storage append at L274–301 and recovery L153–221 independently checked. | **DESIGN_PASS_WITH_LIMITS**; causal durability ordering and failure semantics now internally coherent. | **HIGH, NOT RUN:** actual interrupted fsync, process crash vs power-loss, checkpoint no-clobber/dir fsync, valid-survivor vs missing/torn retry and receipt single-effect demonstration. Unsupported filesystem adapters must stop. |
| **B04** Funding cash, first-known and durable economic ACK | **R3 L95–107** keys one settlement by venue/contract/settlement UTC/source version under a **source-version-independent uniqueness anchor**, excludes transport ID and retry clock from economic fingerprint, freezes as-known fill/Mark/rate proof, forward cash, WAL POST/TRANSPORT_ALIAS/ACK_READY/ACK_EMITTED; ACK receipt ties to **original** POST chain without circular state hash. | **DESIGN_PASS_WITH_LIMITS**; the original transport-vs-cash identity and delayed ACK race are materially specified. | **HIGH, NO EVIDENCE:** issuer/receiver attestation, fsynced original-ingress token, signed exact as-known fill/Mark/rate witness, crash-safe WAL-indexed ACK reuse and no-real-order boundary remain future verified components. |
| **B05** separate directory does not alone isolate legacy V1 | **R3 L109–111** demands external selector/verification **before import**, distinct R4-only modules/storage/run_id, no V1 imports, no implicit fallback, no broker/network client. | **DESIGN_PASS_WITH_LIMITS**; direct old V1 import/dependency isolation is a stated gate, not claimed finished. | **HIGH:** trusted launcher/router is outside implementer authority and does not yet exist; V1 sidecar parity and real class/exception isolation untested. |
| **B06** negative matrix and code allowlist | **R3 L113–143** proposes exactly **12 ADD paths**, **zero MODIFY**, independently signed trust artifacts outside implementer scope, targeted hard-negative matrix, legacy same-commit tests, full clean CI. | **SPECIFICATION PASS_WITH_LIMITS**; meaningful coverage of the seven defects. | **HIGH:** no red/green tests, new R4 module/files, full repository CI, independent manifest/launcher tests on an implementation SHA. Source design **does not authorize** those future ADDs. |
| **B07** inconsistent R2 October ID vs April epoch millis | **R3 L145–162** uses exactly one 2026-10-14 UTC key/timeline and signed Funding examples. | **SYNTHETIC ARITHMETIC PASS** (10/10 timestamps, explicit key, positive/negative/partial-exit signed cash). | **MEDIUM:** example bytes and Mark/rate/fill signatures are invented, not valid original live-source witnesses or empirical cash receipts. |

## 4. Independent attack cases, invariants and evidence limits

### I01 — independent C4 content proof is a baseline fact, not a new implementation PASS

Original guard `PINNED_G1_C4_MANIFEST` hashes are immutable and validated at the old code SHA. An author-provided fresh `PINNED_G1_R4_MANIFEST` cannot be its **own** acceptance root. R3 now requires Controller/reviewer acceptance SHA+blob external to the implementer. A future candidate that changes original model/reducer/storage, rewrites guard expected digests, adds non-manifested executable R4 files/import shims, mutates original tests or changes shared V1 sidecar imports must **hard fail**, even if its own tests pass. AST-path scanning must include the **entire** new R4/import closure and block symlink/hardlink, dynamic module loading, root redirection and import shadow in a sealed tree. R3's externally pinned launcher is **a future dependency**, not a hidden permission to author it under the 12 implementation paths.

### I02 — exact version fields now resolve the dual-schema ambiguity but executable payload semantics still need final freezing

The R3 state envelope lists **12** top-level keys, and independent parser comparison found **43/43** core keys exactly equal to V1's intended 43-field projection. Its hash ordering (Genesis first, then state; WAL record excludes own record_hash; ACK_READY references already-finalized original POST; receipt_id excludes self) avoids obvious self-reference. No accepted R4 process can read V1 WAL, event, journal, checkpoint or ACK or allow `schema_version=1+causal_funding`. Yet `event.payload` is listed only as an exact outer field at R3 L57; per-kind nested payload exact keys/validation and bounded file/resource behavior need a separately frozen code-level contract and adversarial unknown/extra-payload tests before executable acceptance. Never infer payload completeness from an exact outer envelope.

### I03 — pre-fsync survival and corrupt prefix form three genuinely different recovery cases

At the existing baseline, `after_append` is before `os.fsync`. R3 correctly distinguishes:
1. **complete, valid pre-fsync POST survives** → independently verify chain/state and fsync recovered record before ACK; one cash journal;
2. **POST absent** → retry only with original **durably attested ingress token**; one POST if complete source evidence remains;
3. **partial/torn/wrong-state tail** → quarantine original bytes and HARD STOP; never drop partial cash, silently truncate, synthesize a receipt or ACK an unverified prefix.

R3 also requires checkpoint file fsync, atomic no-clobber promotion and parent directory fsync. This is an appropriate fail-closed specification, but process-kill tests alone cannot establish arbitrary device/fs power-loss guarantees. A supported platform/filesystem and actual verified bytes/receipt evidence are still required.

### I04 — original economic identity, alias and ACK READY must bind the same *single* WAL cash effect

Invented duplicate trace: a genuine external synthetic ingress token with settlement anchor `(VENUE,CONTRACT,t_settle)`, signed fill coverage and Mark/rate generates POST at WAL seq N and ACK_READY at N+k. A new transport event ID from a reconnect carries the **same economic fingerprint**, but not the same `transport_received_at_ms`. Correct result: append and fsync only a `TRANSPORT_ALIAS`; no second economic row, original POST N and receipt_id remain unchanged; ACK delivery envelope is a new attempt without another cash post. A changed Mark, rate, source version, fill proof or attempted first-receiver reset for that **same source-independent anchor** ⇒ `FUNDING_SETTLEMENT_CONFLICT` and no cash/ACK. If ACK_READY was lost pre-fsync, the original durable POST remains and *only* one new ACK_READY is created before send; if it was durable the exact original receipt is replayed. No `ACK_EMITTED` status alone proves remote receipt. R3 now specifies this; **no actual such trace/CI was run**.

The sealed Mark/rate/fill provenance described is **synthetic** and externally attested only once implemented. Neither a local SHA nor a public REST period-end stamp proves real exchange Mark, first-known-at, signed fills or legal data rights. Unknown evidence => `COST_INCOMPLETE`, no economic action.

### I05 — B07 mock calculation independently correct; source is still invented

All **10** R3 UTC timestamp/epoch pairs at L149–160 independently converted with exact UTC `Date.parse`; **10/10 MATCH**. Settlement instant `2026-10-14T08:00:00.000Z` is **`1791964800000`** and human ID `SYNTHETIC_VENUE:BTC-PERP:20261014T080000000Z` decodes to that instant. LONG signed position +0.010 BTC after 0.020 entry and 0.010 TP1, synthetic Mark 60000 and funding rate 0.0001 gives `−0.06000000`; SHORT −0.010 gives `+0.06000000`; exit **after** settlement leaves exposure ±0.020, giving ∓0.12000000. Computed with exact elementary decimal units; the JavaScript numeric sanity check has irrelevant IEEE decimal output noise, while R3's prescribed Decimal quantization is explicit. A fully closed pre-settlement inventory implies zero cash from that settlement, still requiring verified proof. **No real Funding receipt or executed order is implied.**

## 5. Gate disposition and future Controller action

**Independent approval is documentary and limited:** `R3_DESIGN_REVIEW_PASS_WITH_LIMITS`. Previous frozen **`DESIGN_REVIEW_FAIL`** on R2 and the failing old in-place prototype CI are retained as true historical receipts, not erased or rebranded. The safe future architectural direction is still isolated **Option A**; the new document closes the key *contract* ambiguities but does not exercise the physical implementation. The new R4 externally pinned Manifest, trusted launcher, source issuer/ingress recorder and functional CI remain **UNCREATED/NOT_VERIFIED** under this R3 target.

**Future authority is explicitly required for every operation:** Controller may separately consider a tightly bounded **12 ADD-only implementation dispatch**, with external trust/launcher/issuer owner, exact build/CI inputs, same-commit V1 13-hash and behavior parity, R4 runtime AST/import gating, falsifiable RED/GREEN crash/clock/cash/ACK fixtures and full repository CI. The existing R3 allowlist is merely a proposal; **it does not grant any implementation write rights**. If trusted launcher, file-system adapter, test compatibility or per-event strict payload schema cannot be supplied without modifying V1 or broad shared-sidecar scope, STOP and obtain a fresh reviewed design/grant; never re-pin old C4 or silently widen paths.

**Status remains:** `P1D_IMPLEMENTATION_NOT_AUTHORIZED / G1_P1D_INTEGRATION_NOT_AUTHORIZED / SOURCE_NOT_ADMITTED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`. No merge, required-CI switch, H40/A-line waiver, production order/network, private funds, protected data, source admission or Alpha implication.

## 6. Allowed one-file frozen publication only

Audit output is solely **ADD** `reviews/v0.6/b_line/V06_R4_1_P1D_C4_WAL_R3_INDEPENDENT_AUDIT.md` on isolated `docs/v06-r4-1-p1d-wal-design-audit` rooted at **`3e8ea27604574c63caf43b5e6d4bff7feb979908`**. No source/golden/CI/manifest/config/test change; no merge or test run. Verify actual report commit/blob/direct parent/full one-file diff and remote branch HEAD after publishing. This report **cannot independently certify its own future R4 implementation**.

**FINAL: `R3_DESIGN_REVIEW_PASS_WITH_LIMITS` / `P1D_IMPLEMENTATION_NOT_AUTHORIZED` / `SOURCE_NOT_ADMITTED` / `G2_ALPHA_NO_GO`.