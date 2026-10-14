# ChatGPT-1 — Independent P1D G1-C4 Immutable Versioning Design Audit R1

**Terminal verdict: DESIGN_REVIEW_FAIL.** Option A, a separately rooted R4 engine preserving all original C4 files and their immutable identities, remains the **preferred conditional architectural direction**, but frozen R2 is **NOT IMPLEMENTATION-READY**. Blockers in new manifest trust, Genesis/WAL version selection, fsync/crash recovery, finance-ledger ACK and compatibility isolation are not closed. This is not approval to alter C4 pinned hashes, implement code, merge, use testnet/live, collect market data or rerun outcomes.

**Reviewer:** ChatGPT-1, Independent Supervisory Auditor; 2026-10-14 Asia/Singapore. This is a read-only independent, exact-SHA, static architecture audit of public materials. No R4 isolated implementation or newly executed R4 tests exist in this submission. The author's design labels, numeric architecture scores, and claimed guarantees are not independent verification.

## 1. Frozen objects and exact publication lineage

| Object | Independently verified identity |
|---|---|
| **Controller dispatch** | Commit **f445267562d6c7638f80bc7ab33b70082d866377**, file prompts/v0.6/b_line/V06_NEXT_1_P1D_C4_VERSION_DESIGN_INDEPENDENT_AUDIT_R1.md; Git blob **c0a5db30e320ecaf7012b75832d402b1fe348f26** |
| **Frozen architecture R2 target** | Commit **931ee5c5ae1cbf341ce771269d4829d3eafa3deb**, file docs/engineering/v0.6/V06_NEXT_P1D_R4_C4_VERSIONED_DESIGN_R2.md; Git blob **b8f18153f17468a64d6772e6abb2097c7705dc68** |
| **R2 Git ancestry/scope** | Remote branch docs/v06-next-p1d-c4-versioned-design-r2 HEAD equals target. Relative to original design dispatch **8de03d93b53c0c9f6cc40af1045b954300d6f699**, ahead **2** commits, behind **0**, cumulative **one ADD document, 494 lines**. Target's direct parent **40ba8db1dd53575b194f53ba27eda803b003344b**; final commit only revised the same document (+99/-60). No code changed in this *design* branch. |
| **Previously blocked in-place P1D R4 prototype** | Commit **81a71467ac7a9b852587b6e5f826d8ee28fc769c**, parent **04cbc46497ed26b0c4e889f30fa10eb8d666a79e**; it **modified original C4 model.py, reducer.py, storage.py**, and multiple ports/tests. Prototype storage Git blob **29b76b39a4079ac82177f16d9f1b74d7c74610c1**. Not an accepted version-isolated implementation. |
| **Predecessor independent causal audit** | Commit **e11f84963adddc29b1dc106c1e0d2a984dd6add2**, path reviews/v0.6/b_line/V06_P1D_FINAL_SHA_INDEPENDENT_CAUSAL_REVIEW_R1.md, Git blob **da837ba4f1c4caaacd6e791bac7d0935a68c75ea**; prior status **INTEGRATION_BLOCKED**. |
| **Existing C4 safety guard** | Exact target-code no_order_port.py at scripts/g1g3_offline_ports_r1/no_order_port.py, Git blob **1aabd107acf8365cfdb7485b754f89a05df4efd2**; pinned 13 old C4 SHA-256 values. Earlier V1 storage at prototype parent Git blob **4d250f5123d57d4df7430b9dc911b5b5208ba81e**. |
| **Real full CI for blocked prototype** | [GitHub Actions run 38446896902](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38446896902), head_sha **81a71467...**, overall **FAILURE**. Actual Python 3.12 quality logs (job **115467527971**) show **3408 passed / 2 failed / 2 skipped / 9 warnings**: independent failures **G1_CORE_MUTATED:scripts/g1_offline_preview_r1/model.py** and original H40 graph digest. Compatibility job skipped, not passed. |

## 2. Alternative decision

**Option A CONDITIONALLY PREFERRED:** retain the original scripts/g1_offline_preview_r1 directory and every one of its 13 C4-pinned sources/tests/fixtures completely unchanged; add a physically separate scripts/g1_offline_preview_r4 engine and independently pinned manifest, with explicit version-specific storage and imports. This avoids attempting to hold two different contents under the same path in a single checkout. The design's claim that A guarantees a 0% regression risk or instant clean CI is unsupported: proposed changes to no_order_port, market_pit_port and durable_supervisor can still change legacy behavior without modifying any of the 13 files. Only an independently checked future candidate with 13 independently rehashed legacy bytes, manifest trust, import/AST parity and V1 replay tests could prove preservation.

**Option B REJECTED AS PROPOSED:** dual manifests on one mutable legacy file tree or history-dependent dynamic aliases cannot preserve the original C4 path identity without additional high-risk versioning machinery. Never edit historical C4 expected SHA-256 values or regenerate golden identities to make the existing failing prototype green.

**Neither is authorized for code implementation by this audit.**

## 3. Consequential independent findings

### B01 — BLOCKER — R4 manifest root/AST coverage not independently pinned

The existing no_order_port guard explicitly loops over **13 original PINNED_G1_C4_MANIFEST paths** (lines 315–330). Existing verify_static_ast_and_core_immutability AST-walks only **scripts/g1g3_offline_ports_r1/*.py** (lines 333–382), **not the proposed R4 engine directory**. Design R2 §3.1/§5.1 would let the implementer both write new R4 files and insert new expected R4 hashes into the mutable no_order_port file. An author-generated same-commit checksum is **not** an independent acceptance root. New R4 modules and transitive dependencies can evade old static scanning unless coverage is explicitly expanded and externally frozen.

**Required:** Controller/reviewer-pinned, independent exact-SHA manifest authority covering the entire R4 module tree and imports; retain original 13 C4 hash literals unchanged; verify all original bytes and old test/AST contracts. Require missing/extra files, symlinks, unauthorized imports, altered guard or manifest, and swapped runtime roots to fail closed. Independent reviewer rehash and separate author/reviewer evidence; never self-refresh pins. Current design's **C4 Identity FULLY_PRESERVED** is only a future aspiration: no R4 versioned implementation has been provided or executed.

### B02 — BLOCKER — ambiguous Genesis, WAL and ACK versions

Design R2 Pillar 1 explicitly allows **R4 schema_version=1 with causal_funding=True OR schema_version=2**, but does not choose a single canonical on-disk and replay schema. The existing prototype reducer accepts **only state.schema_version=1**; prototype storage writes the fixed **G1_OFFLINE_WAL_V1** header, even with the new funding behavior. The document also proposes a future **G1_OFFLINE_WAL_R4** header and a new manifest, without fully fixing compatible snapshot/checkpoint, journal, event, initial-state and ACK combinations. A mutable router could pick the wrong engine from only a generic schema version. These are not operationally interchangeable contracts.

**Required:** one canonical R4 engine/Genesis version and exact version-tagged WAL header, payload, checkpoint, journal and ACK; cross-bind each to the independently pinned engine manifest, storage namespace and immutable event schema. Explicit V1 versus R4 versus unknown routing and rejection matrix, including both cross-version replay directions, unknown event kinds, stale/replayed ACK, and future unsupported schemas. No opportunistic fallback or implicit migration. Any V1→R4 migration is separately authorized and audited, not bundled into this design.

### B03 — BLOCKER — after_append is BEFORE fsync; corrupt tail must hard-fail

This is a concrete contradiction with source. Prototype storage.Engine.apply lines **301–310** write WAL bytes then invoke the **after_append hook at line 306**, followed by **os.fsync(fd) at line 307**, then **after_fsync at 308**. Design §4 Pillar 5 classifies after_append as post-fsync and promises replay from an already persisted record. That is incorrect: a pre-fsync complete WAL record **may or may not survive** a crash; no durability guarantee holds at that boundary. A valid surviving record may replay; a missing record must be safely retried; a torn/corrupt record must not silently be accepted.

The actual V1/prototype _recover rejects missing terminal newline as **WAL_TRUNCATED**, bad chain/hash as **WAL_CHAIN/WAL_STATE_IDENTITY**, and checkpoint ahead of WAL; it quarantines original bytes and **raises SafetyViolation**, blocking operation (prototype lines **160–228**; baseline equivalent). Design §4 instead describes continuing at the last good prefix after quarantine. This is not the observed recovery contract and could silently erase a financial cash effect if implemented incorrectly. Snapshot os.replace also does not prove crash durability without exact ordering and directory sync/anchor validation.

**Required:** separately test before_append, after_append_before_fsync, after_fsync_before_state_update, before/after checkpoint write/fsync/rename/directory sync, before/after ACK and process restart. Test both valid-pre-fsync-survivor and no-survivor outcomes, torn tail and hash-valid but wrong-state records, and ahead-of-WAL checkpoint. Corrupt/truncated chain => quarantine plus STOP, **not** automatic truncation/resume without separate repair authority. Exactly one recoverable cash journal post or explicit fail-closed stop at every crash edge.

### B04 — BLOCKER — economic fingerprint, signed cash and ACK protocol not fully closed

The signed cash proposal **cash_delta = - signed settlement exposure × settlement Mark × funding rate** is directionally correct for the synthetic long/short convention, and the proposed pre-settlement fill ledger, Mark/rate/coverage checks, Decimal precision and ±15s ambiguity guard are useful design subcomponents. But strings such as **SYNTHETIC_SETTLEMENT_MARK** and caller-supplied witness known_at values are *not authenticated Mark, first-receiver timing, fill completeness or actual venue data*. A port-level in-memory seen-set is not durable financial authority.

R2 shows ACK with contract_version, settlement_id, g1_seq and g1_chain, but lacks a mandatory atomic binding to one WAL-persisted economic fingerprint, engine manifest and ACK replay identity. Same economic settlement retransmitted under a **new transport event ID/time** may be misclassified as conflict if the fingerprint includes transport identity; omitting actual economic identity could instead accept changed Mark/rate. The natural-time receipt and economic settlement must stay separate. New receipt after later bars must not reorder prior G1 events, and late correction must never recompute previously decided state. Exact once means one persisted *economic* cash effect, not the absence of repeated transport messages.

**Required:** explicit immutable economic key (venue, contract, effective settlement clock, source version), original Mark/rate/first-known-at provenance, executed fill-history at settlement with signed side and size; reject LONG-negative qty, missing TP1/EXIT fill or unverified ±15s boundary. Define RECEIVED → WAL_PERSISTED → ACK_READY/EMITTED plus crash-recoverable identical-duplicate versus conflicting-replay transitions, and settle idempotence in WAL only. Same event with changed economic identity must STOP; same economic event with different transport epoch must not double-debit. Prove old versus new journal/event kinds are not cross-routed.

### B05 — HIGH — isolate runtime selection and imports, not just folders

The actual prototype durable_supervisor.py imports **Engine as G1Engine** and fixtures/model directly from scripts.g1_offline_preview_r1 at module load time, and no_order_port imports **SafetyViolation** from the original model. R2 adds a new engine tree but does not fully pin explicit selector behavior, exception class interoperation, version-specific durable storage path, or when the correct AST/no-network/old C4 hash guards run relative to import and WAL opening. Its own proposed allowlist edits shared supervisor/market/no-order sidecars; therefore **zero risk to old C4 behavior** and **trivial rollback** are unsupported.

**Required:** old-engine / new-engine explicit dispatcher checked before persistence, distinct WAL/checkpoint/storage roots and identity, no mixed module/class imports, forbidding fallback from R4 to V1 on errors. Independently run frozen V1 behavior/AST/sha tests and all R4 tests on the **same frozen commit** with no AST or import bypass; compare separately restarted V1 and R4 WAL/ACK outcomes. Exclude all protected and production order/network access.

### B06 — HIGH test coverage / acceptance gap

R2's NEG-01 through NEG-12 are a reasonable **starting matrix**, not a sufficient acceptance suite. Add: (a) mutated/missing/symlink each original pinned C4 file, R4 extra source and altered R4 manifest; (b) dual-direction mismatched WAL/snapshot/checkpoint/journal/event/ACK and unknown versions; (c) pre/post-fsync crashes including complete pre-fsync survivor, torn tail, checksum and checkpoint corruption, ACK loss; (d) duplicate economic settlement with changed transport ID versus changed Mark/rate/source, journal seq/cash unchanged; (e) later receiver-known-at Funding with newer BARs, true settlement-time partial fills, CLOSED/FLAT, ±15s inclusive limits, missing witnesses, contradictory signed quantity; (f) old-only regression suites, zero network/orders, exact full CI on implementation SHA. Require individually attributable RED/GREEN synthetic tests and machine WAL/cash receipts. **None are evidenced executed for the proposed isolated R4**. Do not relabel target CI red as a passing test result.

### B07 — MEDIUM synthetic timestamp mismatch

In R2 Pillar 1 the invented settlement_id **BTC-PERP-20261014-080000** claims October 14, 2026, while its numeric **settlement_at=1776153600000** is **2026-04-14T08:00:00.000Z**, **event at=1776153675000** is **2026-04-14T08:01:15.000Z**, and **ack_at_ms=1776153675050** is **2026-04-14T08:01:15.050Z**. Arithmetic chronology is consistent but the economic identity/date is not. This is a synthetic documentation defect; it cannot serve as an exact identity regression fixture until repaired. Use one date, one temporal namespace and assert canonical settlement-to-receipt-to-ACK binding.

## 4. Independent test/CI and evidentiary limits

- **Remote CI independently verified:** [38446896902](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38446896902), quality job **115467527971**. Full pytest executed: **3408 passed / 2 failed / 2 skipped**. The direct C4 immutability failure and unrelated H40 hash failure remain **separately blocking**. Python 3.11/3.13 compatibility was skipped and is NOT accepted.
- **Source design audit only:** read immutable Git blobs for R2, prototype, original storage, no_order_port, durable_supervisor, predecessor independent audit and quality logs; independently calculated the invented timestamp conversions. **No local pytest, process crash, WAL write, collector or CI invocation** on this design review; `NOT_RUN_DESIGN_ONLY` is the correct test command receipt. No independent rehash of all 13 historical files' contents or clean version-isolated R4 code/test output is claimed. Future complete 13-hash preservation is a testable **requirement**, not a completed fact.
- **Previous author's INTEGRATION_BLOCKED remains binding**, and original H40 failure is not altered by this design. No code, original manifests, frozen research evidence or protected files were modified.

## 5. Minimal bounded future dispatch, WITHOUT implementation grant

1. **Reject the frozen R2 as implementation-ready:** issue a new **document-only R3** exact-SHA corrective task addressing B01–B07; freeze one external immutable R4 manifest authority, exact one R4 version, full V1/R4 WAL/event/checkpoint/ACK namespace matrix and a no-migration default.
2. Correct after_append/pre-fsync semantics and corrupted WAL **hard-stop**; freeze append/fsync/snapshot/ACK transaction and full crash-state matrix. Bind economic settlement/Mark/fill provenance, transport-independent idempotence and receiver-known-at before any financial event.
3. Freeze a future exact path allowlist and import/security scope **only after** independent R3 design review. If old C4 byte hashes or V1 import/replay behavior would need modification, STOP; no pin refresh to green.
4. Author must deliver independently reproducible synthetic negatives and exact-SHA full CI; separate reviewer must verify; Controller retains subsequent L2 implementation/integration authority. In this audit: **NO CODE MODIFICATIONS, NO INTEGRATION GRANT, NO MERGE**.

**Final gate status:** **DESIGN_REVIEW_FAIL / OPTION_A_CONDITIONAL / G1_P1D_C4_BLOCKED / FULL_CI_FAIL / SOURCE_NOT_ADMITTED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE**. Never inspect H39/H40/H41/Forward/Final Holdout contents, owner local data roots, private accounts, reserved outcomes or market feeds.

## 6. Authorized report publication

Add **ONLY** reviews/v0.6/b_line/V06_NEXT_P1D_C4_VERSIONED_DESIGN_INDEPENDENT_AUDIT.md on separate **docs/v06-next-p1d-c4-independent-design-audit-r1** branch rooted at Controller dispatch commit **f445267562d6c7638f80bc7ab33b70082d866377**. No modification to the R2 target, original C4 sources or manifests, tests, workflows, frozen history or release gates. Publication commit SHA, report blob SHA, branch HEAD and one-file Git diff must be independently retrieved **after** publication.

**Terminal: DESIGN_REVIEW_FAIL; architecture Option A conditional only; no implementation or integration permission.**