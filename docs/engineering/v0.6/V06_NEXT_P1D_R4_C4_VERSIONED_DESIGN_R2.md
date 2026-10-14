# Gemini BOOST / Codex Sol High — P1D G1-C4 Immutable Versioning Architecture Design R2

- **Document Identifier**: `docs/engineering/v0.6/V06_NEXT_P1D_R4_C4_VERSIONED_DESIGN_R2.md`
- **Owner**: `ChatGPT-0`
- **Author**: `Gemini BOOST / Codex Sol High`
- **Authority**: Immutable dispatch commit `8de03d93b53c0c9f6cc40af1045b954300d6f699` (`prompts/v0.6/b_line/V06_NEXT_P1D_C4_VERSIONED_DESIGN_R2.md`)
- **Target Branch**: `docs/v06-next-p1d-c4-versioned-design-r2`
- **Dispatch Root SHA**: `8de03d93b53c0c9f6cc40af1045b954300d6f699`
- **Terminal Status**: `DESIGN_READY_PENDING_INDEPENDENT_REVIEW`
- **Operational Limits**: Read-only architecture design. Strictly NO implementation grant, no code editing, no manifest SHA refresh, no test skips, no merge, no protected H39/H40/H41/Forward/holdout access, no historical outcome runs, no exchange market collection, credentials, orders, or TESTNET/LIVE operations. `SOURCE_NOT_ADMITTED` and `G2_ALPHA_NO_GO` remain strictly binding.

---

## 1. Publication Check of Predecessor R1 Design

Under the dispatch mandate, we first executed an exhaustive search across the entire Git history and local workspace to determine whether the predecessor R1 design document (`docs/engineering/v0.6/V06_P1D_R4_C4_DUAL_VERSION_IDENTITY_DESIGN_GATE_R1.md`) was previously published:

- **Command**: `git log --all --full-history -- "**/V06_P1D_R4_C4_DUAL_VERSION_IDENTITY_DESIGN_GATE_R1.md"`
  - **Result**: `0 commits found` (empty output).
- **Command**: `git log --all --grep="V06_P1D_R4_C4_DUAL_VERSION_IDENTITY_DESIGN_GATE_R1" --oneline`
  - **Result**: `0 commits found` (empty output).
- **Workspace Search**: `find_by_name(Pattern="*DUAL_VERSION*")`
  - **Result**: `0 results found`.

**Conclusion**: The predecessor R1 design file was never published to any branch or commit in this repository. In strict adherence to the dispatch protocol, we proceed with publishing the authorized, comprehensive, design-only R2 specification.

---

## 2. Background, Ground Truth Audit Triangulation & CI Root Cause Analysis

### 2.1 The P1D R4 Implementation Prototype (`81a71467ac7a9b852587b6e5f826d8ee28fc769c`)

Commit `81a7146` introduced a prototype for causal funding integration (`SYNTHETIC_CAUSAL_R4`), addressing chronological funding receipt, signed cash flow calculations, and crash recovery. However, it made in-place modifications to three files within the frozen Codex G1 C4 core directory:
- `scripts/g1_offline_preview_r1/model.py` (blob `337d3aa1637bb5aa0037b17deab334acde653061`)
- `scripts/g1_offline_preview_r1/reducer.py` (blob `480eae7b3034bb5def8da3e1fef618c1a567cc98`)
- `scripts/g1_offline_preview_r1/storage.py` (blob `29b76b39a4079ac82177f16d9f1b74d7c74610c1`)
- `scripts/g1g3_offline_ports_r1/durable_supervisor.py` (blob `625885778505eee1aef1f193b8bfe9ee7be909fc`)
- `scripts/g1g3_offline_ports_r1/market_pit_port.py` (blob `f2e88b2339bf8702f29de8862aea51eb972a9bb0`)
- `tests/test_v06_g1g3_offline_ports_r1_core_integration.py` (blob `3c5c62de616132d06e9d6f7ef79e9777c39971a1`)
- Added: `tests/test_v06_p1d_r4_late_funding_g1_economic_recovery.py` (blob `70cc6796353a8539b100e7e10b7da351f1854cc6`)
- Added: `docs/engineering/v0.6/V06_P1D_R4_SYNTHETIC_CAUSAL_INTEGRATION_EVIDENCE.md`

### 2.2 Independent Causal Review Audit (`e11f84963adddc29b1dc106c1e0d2a984dd6add2`)

Independent audit sidecar `reviews/v0.6/b_line/V06_P1D_FINAL_SHA_INDEPENDENT_CAUSAL_REVIEW_R1.md` identified three major findings:
1. **F1 (HIGH) — Event-Clock Boundary Conflict**: Replaying funding at historical settlement time $t_{\text{settle}}$ after newer 1-minute `BAR` events have already been ingested violated the strict monotonic order of G1's chronological event sequencer, raising `EVENT_REORDERED` on unchanged bases.
2. **F2 (HIGH) — Mark / Exposure Integration Gap**: The economic cash calculation required an immutable, fill-ledger-backed position exposure snapshot at $t_{\text{settle}}$, witnessed Mark and rate identities, signed directionality (LONG vs SHORT vs FLAT), pre-settlement partial exit valuation (TP1), and a $\pm 15\,\text{s}$ boundary uncertainty guard. Incomplete coverage must fail closed as `COST_INCOMPLETE`.
3. **F3 (HIGH) — In-Memory Deduplication vs Durable Financial Completeness**: Ephemeral port memory (`seen_dedupe_keys`, `seen_funding_settlements`) does not constitute durable ledger ACK. Upon port restart, a re-sent funding record must not double-post cash. Cash posting authority belongs exclusively to the G1 hash-chained WAL.

The audit rendered a terminal verdict of `INTEGRATION_BLOCKED` and recommended an advisory `BOUNDED_REPAIR` path with a versioned G1 contract redesign.

### 2.3 CI Execution Run `38446896902` & Immutability Violation Root Cause

Remote CI Run `38446896902` on commit `81a7146` executed full pytest: **3408 passed, 2 failed, 2 skipped**.
- **Failure 1 (`G1_CORE_MUTATED`)**:
  - `tests/test_v06_g1g3_offline_ports_r1_recovery_and_guards.py::test_static_ast_and_c4_core_immutability_verification`
  - Calls `verify_static_ast_and_core_immutability()` in `scripts/g1g3_offline_ports_r1/no_order_port.py`.
  - The static verifier computes SHA-256 digests of 13 pinned G1 C4 files:
    ```python
    PINNED_G1_C4_MANIFEST = {
        "scripts/g1_offline_preview_r1/__main__.py": "65dcb3d726ed5a8b828ed0288d10fa9f51340f4cf3a70cf44b4a2c62e21cd5fb",
        "scripts/g1_offline_preview_r1/analysis_schema.json": "dea9da8a0f03740894f117a7da56cd7c99476aa3058bdf2a665107019a98e1cb",
        "scripts/g1_offline_preview_r1/fixtures/long_24h.json": "ae6c70f7c26b752df1cfc2cc803d6a941a62e1699749365f4902d335cb93fe4f",
        "scripts/g1_offline_preview_r1/fixtures/short_24h.json": "d6bf849411f82db75f433f91985b7c8698fbbd1834685fb706453de3cad1dc11",
        "scripts/g1_offline_preview_r1/fixtures.py": "9999418e5cb1f9fd98d1f4cae5c1d460a9593b28c9f7f338a3043374fa4ea8b0",
        "scripts/g1_offline_preview_r1/model.py": "086d6ec8747f82d59b6f8f42bfefd2d9c61e5f962707b4f9119f784741dd206e",
        "scripts/g1_offline_preview_r1/reducer.py": "c0114c8cc0480b3c4c637217363833590fb231ad8529c93f85f574ce161ed89e",
        "scripts/g1_offline_preview_r1/storage.py": "9e4ac21c501e48734a750021f8ea2f51f4f06ecc0ee2e798647718b4c453f101",
        "tests/test_v06_g1_offline_preview_r1_core.py": "d5679c583d1122f2ce877f7686e477acc869637e7ee21643fbee1f5058e52da3",
        "tests/test_v06_g1_offline_preview_r1_decimal_and_ports.py": "7a0fef994f1548ebe0813836b41340519f49dcefbe46a5d5850b23392ee731e2",
        "tests/test_v06_g1_offline_preview_r1_exit_safety.py": "8efc412469fa5be183bca05dacd7ba255e7ad1f20f93e39706698e8bc4cd71f0",
        "tests/test_v06_g1_offline_preview_r1_process_recovery.py": "d6c99ea559f9c4a8c384568af52ed6aa556ecca896d9add58ca9aa5c07f04249",
        "tests/test_v06_g1_offline_preview_r1_wal.py": "41d53a583502b4d28da92dfa9f8c9e2dde73522509009739418d9dfff42c8585",
    }
    ```
  - In `81a7146`, modifying `model.py`, `reducer.py`, and `storage.py` directly caused `verify_g1_core_immutability()` to immediately fail:
    `SafetyViolation: G1_CORE_MUTATED:scripts/g1_offline_preview_r1/model.py`.
- **Failure 2 (H40 Protected Golden)**:
  - Unrelated pre-existing hold on H40 golden doc hash, quarantined under separate controller dispatch `c9b3663`.
- **2 Skipped**:
  - Full git compatibility history suite.

---

## 3. Architectural Evaluation: Architecture (A) vs Architecture (B)

To resolve the immutability deadlock without weakening cryptographic verification, we evaluate two architectural paradigms:

```
                    ┌────────────────────────────────────────────────────────┐
                    │               ARCHITECTURAL ALTERNATIVES               │
                    └────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┴────────────────────────┐
            ▼                                                ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
│           ARCHITECTURE (A)           │  │           ARCHITECTURE (B)           │
│   ISOLATED VERSIONED ENGINE ROOT     │  │   FORMALLY DUAL-VERSIONED MANIFEST   │
│                                      │  │                                      │
│ • scripts/g1_offline_preview_r1/     │  │ • scripts/g1_offline_preview_r1/     │
│   (100% frozen, original C4 hashes)  │  │   (modified in place or branched)    │
│ • scripts/g1_offline_preview_r4/     │  │ • PINNED_G1_C4_MANIFEST_V1 (C4)      │
│   (new isolated R4 package)          │  │ • PINNED_G1_C4_MANIFEST_R4 (R4)      │
│ • PINNED_G1_C4_MANIFEST unchanged    │  │ • Version selector in no_order_port  │
│ • PINNED_G1_R4_MANIFEST added        │  │ • In-tree coexistence conflict if    │
│                                      │  │   paths collide!                     │
└──────────────────────────────────────┘  └──────────────────────────────────────┘
```

### 3.1 Detailed Option Definitions

#### Architecture (A): Preserving Original Immutable 13-File C4 Hashes & Creating an Isolated Versioned R4 Engine
- **Filesystem Layout**:
  - `scripts/g1_offline_preview_r1/` remains strictly unmodified and frozen byte-for-byte. All 13 original files retain their exact pinned SHA-256 hashes.
  - A new isolated engine root is established at `scripts/g1_offline_preview_r4/` (containing `__init__.py`, `model.py`, `reducer.py`, `storage.py`, `fixtures.py`, `analysis_schema.json`).
  - `scripts/g1g3_offline_ports_r1/no_order_port.py` keeps `PINNED_G1_C4_MANIFEST` completely intact, and defines a separate immutable dictionary `PINNED_G1_R4_MANIFEST`.
  - Static AST scanning in `verify_static_ast_and_core_immutability()` checks both roots independently.
  - Ports and supervisor select between `EngineV1` and `EngineR4` based on the declared contract version.

#### Architecture (B): Formally Dual-Versioned Immutable Engine/Manifest Selection Without Changing Old C4 Identity
- **Filesystem & Manifest Structure**:
  - `scripts/g1g3_offline_ports_r1/no_order_port.py` is updated to support dual-version manifest selection (`PINNED_MANIFEST_REGISTRY = {"C4_V1": PINNED_G1_C4_MANIFEST_V1, "R4_V2": PINNED_G1_R4_MANIFEST_V2}`).
  - If applied to a single directory (`scripts/g1_offline_preview_r1/`), the filesystem cannot simultaneously store two different SHA-256 hashes for the same file path in a single Git checkout. Thus, Architecture (B) requires either:
    1. Submodule/versioned file suffixes (e.g., `model_v1.py` vs `model_r4.py`), or
    2. Dynamic runtime fallback to Git object storage for historical C4 verification.
  - If versioned file suffixes are used, legacy imports across the test suite break unless aliased dynamically.

### 3.2 Side-by-Side Trade-Off Matrix

| Evaluation Dimension | Architecture (A): Isolated Versioned Engine Root (`g1_offline_preview_r4`) | Architecture (B): Dual Manifest on Shared Directory |
| :--- | :--- | :--- |
| **1. C4 Immutability & Hash Preservation** | **SUPERIOR (10/10)**: Original 13 files are completely untouched. Original `PINNED_G1_C4_MANIFEST` verification passes with zero diff. | **RISKY (4/10)**: If paths collide, C4 working tree files cannot match original hashes. Requires artificial Git object extraction or renaming. |
| **2. Static AST & Import Verification** | **SUPERIOR (10/10)**: Clear lexical boundaries. AST scanner scans both directory trees independently. Zero risk of cross-import contamination. | **COMPLEX (5/10)**: AST scanner must understand conditional branches, dynamic imports, or renamed files, weakening static safety guarantees. |
| **3. Blast Radius & Fault Isolation** | **SUPERIOR (10/10)**: Complete blast containment. R4 engine changes cannot break C4 V1 execution. Regression risk to frozen baseline is 0%. | **MODERATE (5/10)**: Shared modules risk latent regression in V1 execution pathways when edge conditions are triggered. |
| **4. Maintenance & Code Duplication** | **ACCEPTABLE (7/10)**: Duplicates ~1,400 LOC from G1 core. However, G1 is a frozen offline preview engine; immutability takes precedence over DRY. | **MODERATE (8/10)**: Avoids full duplication but introduces high conditional cyclomatic complexity inside reducer and storage. |
| **5. CI & Golden Hash Stability** | **SUPERIOR (10/10)**: 100% stable. No historical test or golden digest fails. `test_static_ast_and_c4_core_immutability_verification` passes immediately. | **FRAGILE (4/10)**: Requires modifying test expectations or manifest verification signatures, risking ripple failures across test suites. |
| **6. Rollback & Deprecation Safety** | **SUPERIOR (10/10)**: Trivial rollback. Deleting `scripts/g1_offline_preview_r4/` cleanly reverts to baseline without touching C4. | **COMPLEX (5/10)**: Rollback requires disentangling merged conditional code in core files. |

### 3.3 Architectural Verdict & Recommendation

**Authoritative Decision: Adopt Architecture (A) with Dual-Manifest Registration.**
Preserving the byte-for-byte integrity of the original 13 C4 files in `scripts/g1_offline_preview_r1/` is a non-negotiable governance requirement. Establishing `scripts/g1_offline_preview_r4/` as an isolated, versioned engine root guarantees:
1. Complete cryptographic immutability of the legacy C4 baseline (`PINNED_G1_C4_MANIFEST` remains unaltered).
2. Explicit, cryptographically pinned identity for the new R4 engine (`PINNED_G1_R4_MANIFEST`).
3. Total elimination of the `G1_CORE_MUTATED` CI failure without weakening any assertion.

---

## 4. The Six Pillars of the R4 Versioned Contract Specification

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                   THE SIX PILLARS OF THE R4 VERSIONED CONTRACT                    │
├───────────────────────────────────────────────────────────────────────────────────┤
│  1. GENESIS / WAL / ACK HANDSHAKE      │  4. CASH IDEMPOTENCE & DEDUPE            │
│     • Strict schema_version negotiation │     • Port REPLAY_TO_LEDGER transport    │
│     • Cross-version WAL replay guard    │     • G1 deterministic fingerprinting    │
│     • Durable supervisor ACK receipt    │     • Exactly-once financial journal     │
├─────────────────────────────────────────┼──────────────────────────────────────────┤
│  2. SIGNED FUNDING & MARK WITNESS       │  5. TAMPER / RESTART / FAULT ISOLATION   │
│     • Historical fill exposure snapshot │     • 9 process-kill injection edges     │
│     • Banker's rounding Decimal-128     │     • Bit-for-bit WAL replay recovery    │
│     • ±15s settlement ambiguity window  │     • Crash-consistent checkpointing     │
├─────────────────────────────────────────┼──────────────────────────────────────────┤
│  3. RECEIVER-KNOWN-AT & PIT ISOLATION   │  6. EXHAUSTIVE NEGATIVE MATRIX           │
│     • Monotonic ingress event.at clock  │     • 12 fail-closed validation guards   │
│     • Zero EVENT_REORDERED exceptions   │     • Invariant violation trapping       │
│     • Forward-only ledger adjustment    │     • Zero unauthorized silent fallbacks │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Genesis / WAL / ACK Version Handshake

The contract enforces strict bidirectional version negotiation across all engine lifecycles:

#### 1.1 Genesis Initial State Specification
- **Legacy C4 (V1) Genesis**:
  - `schema_version`: `1`
  - `funding_contract`: `None` (omitted from `initial_state()` in frozen V1)
  - Permitted funding event: `FUNDING` only.
  - Rejects `FUNDING_RECEIPT` with `SafetyViolation("EVENT_KIND_UNKNOWN")` (the frozen V1 `transition()` dispatcher raises `EVENT_KIND_UNKNOWN` for any unrecognized event kind).
- **R4 Causal (V2) Genesis**:
  - `schema_version`: `1` (with explicit causal opt-in `causal_funding=True`) or `2`
  - `funding_contract`: `"SYNTHETIC_CAUSAL_R4"`
  - `fill_history`: `[]` (chronological list of executed fills)
  - `used_settlements`: `[]` (set/list of settled settlement IDs)
  - `used_settlement_clocks`: `[]` (timestamps of processed settlements)
  - Permitted funding event: `FUNDING_RECEIPT` only.
  - Rejects legacy `FUNDING` with `SafetyViolation("LEGACY_FUNDING_REQUIRES_LEGACY_GENESIS")`.

#### 1.2 WAL Header, Record Envelope & Version Tagging
WAL storage enforces bit-for-bit integrity and strict schema validation:

1. **WAL Header (Line 0)**:
   In G1 `storage.py`, `_init_wal()` writes line 0 as:
   `{"format": "G1_OFFLINE_WAL_V1", "genesis_hash": digest(self.initial)}` (or `"format": "G1_OFFLINE_WAL_R4"`).
   Because `initial_state(causal_funding=True)` contains `"funding_contract": "SYNTHETIC_CAUSAL_R4"` and `"fill_history": []`, its `digest(self.initial)` is cryptographically distinct from the legacy V1 genesis.
   - **Cross-Version Replay Invariant**: When an `Engine` initializes from an existing WAL file, line 38 of `storage.py` verifies `strict_json(lines[0]) == {"format": ..., "genesis_hash": digest(self.initial)}`. Replaying an R4 WAL into a legacy V1 engine (or a legacy V1 WAL into an R4 engine without an explicit migration adapter) immediately raises `SafetyViolation("WAL_GENESIS_MISMATCH")`.

2. **WAL Record Envelope (Lines 1+)**:
   Every record appended to disk strictly adheres to the 6-key canonical schema required by `storage.py:_recover()` (`set(rec) == {"seq", "previous", "event", "event_hash", "state_hash", "record_hash"}`):
   ```json
   {
     "seq": 42,
     "previous": "a1b2c3d4e5f6...",
     "event": {
       "id": "mkt-fund-rec-20261014-080000",
       "kind": "FUNDING_RECEIPT",
       "at": 1776153675000,
       "payload": {
         "contract_version": "SYNTHETIC_CAUSAL_R4",
         "settlement_id": "BTC-PERP-20261014-080000",
         "settlement_at": 1776153600000,
         "mark_price": "60000.0",
         "rate_fraction": "0.0001",
         "mark_witness": {
           "at": 1776153600000,
           "known_at": 1776153600100,
           "source": "SYNTHETIC_SETTLEMENT_MARK"
         },
         "rate_witness": {
           "at": 1776153600000,
           "known_at": 1776153600100,
           "source": "SYNTHETIC_SETTLED_RATE"
         },
         "fill_coverage": {
           "from_at": 0,
           "through_at": 1776153600000,
           "known_at": 1776153600100,
           "source": "G1_SYNTHETIC_WAL"
         }
       }
     },
     "event_hash": "b2c3d4e5f607...",
     "state_hash": "c3d4e5f60718...",
     "record_hash": "d4e5f6071829..."
   }
   ```
   Where `record_hash = digest(body)` with `body = {k: v for k, v in record.items() if k != "record_hash"}`. The contract version is explicitly carried within `event["payload"]["contract_version"]` and verified by `funding_receipt_fingerprint()`.

#### 1.3 Durable Supervisor ACK Envelope
The supervisor issues an ACK only after successful G1 WAL fsync (`engine.apply()` returning `"COMMITTED"` or `"IDEMPOTENT_DUPLICATE"`):
```json
{
  "status": "COMMITTED",
  "contract_version": "SYNTHETIC_CAUSAL_R4",
  "settlement_id": "BTC-PERP-20261014-080000",
  "g1_seq": 42,
  "g1_chain": "d4e5f6071829...",
  "scope": "SYNTHETIC_INTEGRATION_ONLY",
  "ack_at_ms": 1776153675050
}
```
If the settlement was already processed, the supervisor returns:
```json
{
  "status": "IDEMPOTENT_DUPLICATE",
  "contract_version": "SYNTHETIC_CAUSAL_R4",
  "settlement_id": "BTC-PERP-20261014-080000",
  "g1_seq": 42,
  "g1_chain": "d4e5f6071829...",
  "scope": "SYNTHETIC_INTEGRATION_ONLY",
  "ack_at_ms": 1776153675050
}
```

---

### Pillar 2: Signed Funding Settlement Exposure & Mark Price Witness

#### 2.1 Historical Fill Exposure Snapshot Formulation
To prevent causal leakage and ensure economic accuracy, exposure is computed strictly from pre-settlement executed fills:
$$\text{exposure}(t_{\text{settle}}) = \sum_{\substack{f \in \text{fill\_history} \\ t(f) < t_{\text{settle}}}} \text{side}(f) \cdot \text{action}(f) \cdot \text{quantity}(f)$$
Where:
- $\text{side}(f)$: $+1$ for $\text{"LONG"}$, $-1$ for $\text{"SHORT"}$
- $\text{action}(f)$: $+1$ for $\text{"ENTRY"}$, $-1$ for $\text{"EXIT"}$
- $\text{quantity}(f)$: Executed lot quantity ($\text{Decimal} > 0$)

Before computing pre-settlement exposure, the engine validates internal consistency against active portfolio state:
$$\text{current\_portfolio} = \sum_{f \in \text{fill\_history}} \text{side}(f) \cdot \text{action}(f) \cdot \text{quantity}(f)$$
$$\text{expected\_portfolio} = \text{decimal}(\text{state}[\text{"remaining\_qty"}]) \cdot \text{position\_side}(\text{state})$$
$$\text{assert } \text{current\_portfolio} == \text{expected\_portfolio} \quad (\text{else } \text{raise SafetyViolation("COST\_INCOMPLETE")})$$

#### 2.2 Boundary Invariants & Partial Exit Handling
1. **Partial Exits (TP1)**: Executed partial exit fills prior to $t_{\text{settle}}$ reduce the signed quantity. If an initial ENTRY was $0.020$ BTC LONG at $t_1 < t_{\text{settle}}$, and a TP1 EXIT of $0.010$ BTC occurred at $t_{\text{exit}} < t_{\text{settle}}$, the active exposure at $t_{\text{settle}}$ is exactly $+0.010$ BTC. If the TP1 EXIT occurred after $t_{\text{settle}}$, the exposure at $t_{\text{settle}}$ remains $+0.020$ BTC.
2. **Flat Position**: If all positions closed prior to $t_{\text{settle}}$, $\text{exposure} = 0.000$. Cash delta is $0.00000000$, recorded in the journal with complete witness evidence.
3. **Post-Settlement Position Exit & Operational Phases**: Unlike legacy `FUNDING` which strictly asserted `_phase(s, "WAIT_ENTRY_ACK", "OPEN", "OPEN_RESIDUAL", "WAIT_TP1_ACK")`, `FUNDING_RECEIPT` permits receipt and forward-cash posting across all operational phases, including `"CLOSED"` and `"EXIT_WAIT_ACK"`. If an active position closed after $t_{\text{settle}}$ but prior to $t_{\text{receipt}}$, the pre-settlement exposure remains economically valid and must be settled without raising `SafetyViolation("PHASE_INVALID")`.
4. **Temporal Ambiguity Window ($\pm 15\,\text{s}$)**:
   If any fill in `fill_history` satisfies $|t(f) - t_{\text{settle}}| \le 15,000\,\text{ms}$, the engine raises:
   `SafetyViolation("AMBIGUOUS_SETTLEMENT_BOUNDARY")`.
   This is a closed interval: both $-15,000\,\text{ms}$ and $+15,000\,\text{ms}$ trigger the guard, guaranteeing that trade execution fills occurring anywhere near the boundary fail closed without ambiguous classification.
5. **Fill Ledger Invariant**: The list of `fill_id`s in `fill_history` must match `used_fill_ids` in `state` exactly. Any discrepancy raises `SafetyViolation("COST_INCOMPLETE")`.

#### 2.3 Cash Flow Precision & Quantization
Cash delta is calculated within a `localcontext(prec=128)`:
$$\Delta \text{cash} = - \left( \text{exposure} \cdot \text{mark\_price} \cdot \text{rate\_fraction} \right)$$
Quantized to 8 decimal places using Banker's Rounding:
`cash_delta = raw_cash.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)`

**Economic Sign Verification**:
- LONG position ($\text{exposure} > 0$), positive funding rate ($\text{rate} > 0$): Longs pay shorts $\implies \Delta \text{cash} < 0$ (deducted from balance).
- SHORT position ($\text{exposure} < 0$), positive funding rate ($\text{rate} > 0$): Shorts receive funding $\implies \Delta \text{cash} > 0$ (credited to balance).
- LONG position ($\text{exposure} > 0$), negative funding rate ($\text{rate} < 0$): Longs receive funding $\implies \Delta \text{cash} > 0$.
- SHORT position ($\text{exposure} < 0$), negative funding rate ($\text{rate} < 0$): Shorts pay funding $\implies \Delta \text{cash} < 0$.

#### 2.4 Fail-Closed Witness Integrity
Payload must contain three complete witnesses:
1. `mark_witness`: `{"at": t_settle, "known_at": t_mark_known, "source": "SYNTHETIC_SETTLEMENT_MARK"}`
2. `rate_witness`: `{"at": t_settle, "known_at": t_rate_known, "source": "SYNTHETIC_SETTLED_RATE"}`
3. `fill_coverage`: `{"from_at": 0, "through_at": t_settle, "known_at": t_cov_known, "source": "G1_SYNTHETIC_WAL"}`

**Validation Rules**:
- $t_{\text{settle}} \le t_{\text{known}} \le t_{\text{receipt}}$ for all witnesses.
- If $t_{\text{settle}} > t_{\text{receipt}}$: raises `SafetyViolation("FUNDING_PIT_INVALID")`.
- If $t_{\text{known}} < t_{\text{settle}}$ or $t_{\text{known}} > t_{\text{receipt}}$: raises `SafetyViolation("COST_INCOMPLETE")`.
- If $|\text{rate\_fraction}| > 0.10$: raises `SafetyViolation("FUNDING_RATE_BOUNDS")`.
- If any witness key is missing or source string drifts: raises `SafetyViolation("COST_INCOMPLETE")`.

---

### Pillar 3: Receiver-Known-At & PIT Causal Protection

```
Timeline:
------------------------------------------------------------------------------------> (Wall Clock)
   08:00:00 UTC               08:00:30 UTC       08:01:00 UTC       08:01:15 UTC
   [Settlement t_settle]      [BAR-1 Ingested]   [BAR-2 Ingested]   [FUNDING_RECEIPT Ingested]
                                                                     at = 08:01:15 UTC
                                                                     settlement_at = 08:00:00 UTC
   ◄─────────────────────────────────────────────────────────────────
   Exposure calculated using portfolio state AT 08:00:00 UTC.
   Ledger cash entry posted forward AT 08:01:15 UTC.
   NO retroactive modification of decisions at 08:00:30 or 08:01:00!
   NO EVENT_REORDERED exception!
```

#### 3.1 Dual-Clock Architecture
To resolve Finding F1 without breaking chronological determinism:
1. **Sequencer Clock ($event[\text{"at"}]$)**: Set to `available_at_ms` ($t_{\text{receipt}}$), representing the receiver ingress wall time.
   - Because $t_{\text{receipt}} \ge t_{\text{last\_bar}}$, the event satisfies $event[\text{"at"}] \ge \text{last\_event\_at}$.
   - The G1 event sequencer advances monotonically without raising `EVENT_REORDERED`.
2. **Economic Settlement Clock ($payload[\text{"settlement\_at"}]$)**: Preserves the historical exchange settlement timestamp $t_{\text{settle}}$.
   - $t_{\text{settle}} \le t_{\text{receipt}}$ is enforced (`FUNDING_PIT_INVALID` if violated).
   - Used strictly for fill history exposure lookup and Mark price evaluation.

#### 3.2 Non-Retroactive Decision Immutability
- All trade decisions made between $t_{\text{settle}}$ and $t_{\text{receipt}}$ were evaluated using the portfolio cash and state available at those moments.
- The arrival of `FUNDING_RECEIPT` at $t_{\text{receipt}}$ applies a forward-only cash journal adjustment at $t_{\text{receipt}}$.
- Prior decisions, fills, and stop-loss/take-profit triggers are NEVER recalculated or retroactively unwound. Causal point-in-time conservation is preserved absolutely.

---

### Pillar 4: Cash Idempotence & Multi-Layer Deduplication

#### 4.1 Layer Separation: Port Filter vs G1 Ledger
- **MarketPitPort Layer**:
  - In-memory dictionaries (`seen_dedupe_keys`, `seen_funding_settlements`) serve solely as transient network transport deduplication filters.
  - If a duplicate transport envelope arrives, the port does NOT silently swallow it or emit an unconfirmed ACK.
  - The port returns `{"status": "REPLAY_TO_LEDGER", "g1_event": event, ...}`, forwarding the record to the durable G1 engine to ensure the ledger state matches disk reality.
- **G1 Storage / Ledger Layer**:
  - The durable G1 WAL owns financial idempotence.
  - In `Engine.apply()`, every `FUNDING_RECEIPT` is hashed into a canonical economic fingerprint via `funding_receipt_fingerprint(event)`.
  - The engine checks `self.state["journal"]` for `funding:<settlement_id>`.

#### 4.2 Deterministic Idempotence Resolution
```python
def apply(self, event, hook=None):
    if event.get("kind") == "FUNDING_RECEIPT":
        fingerprint = funding_receipt_fingerprint(event)
        key = "funding:" + event["payload"]["settlement_id"]
        previous = next((r for r in self.state["journal"] if r["key"] == key), None)
        if previous is not None:
            if previous.get("funding_fingerprint") != fingerprint:
                raise SafetyViolation("FUNDING_SETTLEMENT_CONFLICT")
            return "IDEMPOTENT_DUPLICATE"
```
- **Identical Replay**: If the `settlement_id` exists and its `funding_fingerprint` matches, the engine returns `"IDEMPOTENT_DUPLICATE"` immediately. No cash is debited/credited, no duplicate journal entry is added, and `seq` does not increment.
- **Payload Conflict**: If the `settlement_id` matches but the Mark price, rate, or event identity differs, the engine raises `SafetyViolation("FUNDING_SETTLEMENT_CONFLICT")`.
- **Restart Immunity**: Because `journal` is rebuilt directly from the hash-chained WAL upon restart, deduplication is 100% crash-consistent and immune to process restarts or memory loss.

---

### Pillar 5: Tamper, Restart & Fault Isolation

#### 5.1 Process-Death Injection Lifecycle Edges
The architecture guarantees atomic durability across 9 critical process-death injection edges, matching the execution hooks exercised by `test_real_process_crash_replay_cash_exactly_once_with_chronological_ack`:

```
[Supervisor Ingress] ───────────────> (1) before_receipt
                                          │
[Supervisor Post-Ingest] ───────────> (2) after_receipt
                                          │
[Engine Pre-Append] ────────────────> (3) before_append
                                          │
[Engine Post-Append] ───────────────> (4) after_append
                                          │
[Engine Post-Fsync] ────────────────> (5) after_fsync
                                          │
[Engine Pre-Snapshot] ──────────────> (6) before_snapshot
                                          │
[Engine Post-Snapshot] ─────────────> (7) after_snapshot
                                          │
[Supervisor Pre-ACK] ───────────────> (8) before_receipt_ack
                                          │
[Supervisor Post-ACK] ──────────────> (9) after_receipt_ack
```

#### 5.2 Crash Recovery Invariants
1. **Crash before `after_append` (edges 1–3: `before_receipt`, `after_receipt`, `before_append`)**: The record was not committed to disk WAL. Upon supervisor/engine restart, the engine recovers to the clean pre-receipt state with 0 journal rows. Retransmitting the envelope commits cleanly, returning status `"COMMITTED"` with exactly one cash entry.
2. **Crash after WAL Append & Fsync (edges 4–9: `after_append`, `after_fsync`, `before_snapshot`, `after_snapshot`, `before_receipt_ack`, `after_receipt_ack`)**: If the record was fsynced to WAL, engine restart reconstructs the cash journal entry via deterministic WAL replay. Retransmitting the envelope detects the existing `funding:<settlement_id>` key in `state["journal"]`, verifies fingerprint equality, and returns status `"IDEMPOTENT_DUPLICATE"`. Exactly one cash entry exists across arbitrary process deaths and restarts.
3. **Crash during snapshot**: Snapshots are written to a temporary `.tmp` file and atomically renamed (`os.replace`). A crash leaves either the old valid snapshot or the new valid snapshot. Unfinalized temporary files are safely ignored.
4. **WAL Corruption / Truncated Tail**: A trailing un-fsynced partial record from a sudden hard kill fails SHA-256 record verification or newline termination; recovery safely replays up to the last valid chain hash and quarantines corrupted bytes.

---

### Pillar 6: Full Negative Test Matrix

The test suite must validate fail-closed enforcement across all invalid inputs and attack vectors:

| Test ID | Boundary / Scenario | Input Condition | Expected Error Code | Verification Mechanism |
| :--- | :--- | :--- | :--- | :--- |
| **NEG-01** | Future Settlement PIT | $t_{\text{settle}} > t_{\text{receipt}}$ (`settlement_at > at`) | `FUNDING_PIT_INVALID` | Pre-validation in `MarketPitPort` and `model.py` |
| **NEG-02** | Extreme Rate Spike | $|\text{rate\_fraction}| > 0.10$ (10% rate) | `FUNDING_RATE_BOUNDS` | Strict Decimal bound check in `funding_receipt_fingerprint()` |
| **NEG-03** | Missing Mark Witness | `mark_witness` omitted from payload | `COST_INCOMPLETE` | Schema key matching in `model.py` |
| **NEG-04** | Missing Rate Witness | `rate_witness` omitted from payload | `COST_INCOMPLETE` | Schema key matching in `model.py` |
| **NEG-05** | Contradictory Side/Qty | `side="LONG", quantity="-0.010"` | `POSITION_SIDE_QUANTITY_CONTRADICTION` | Guard in `calculate_settled_funding_cash_flow()` |
| **NEG-06** | Ambiguous $\pm 15\,\text{s}$ Fill | Fill at $t_{\text{settle}} - 5000\,\text{ms}$ or $\pm 15,000\,\text{ms}$ | `AMBIGUOUS_SETTLEMENT_BOUNDARY` | Temporal proximity check in `_settlement_exposure()` |
| **NEG-07** | Conflicting Mark Replay | Same `settlement_id`, Mark changed $65000 \to 66000$ | `FUNDING_SETTLEMENT_CONFLICT` | Fingerprint comparison in `Engine.apply()` |
| **NEG-08** | Legacy Event on R4 | Event `kind="FUNDING"` dispatched to R4 engine | `LEGACY_FUNDING_REQUIRES_LEGACY_GENESIS` | Transition guard in `reducer.py` |
| **NEG-09** | R4 Event on Legacy | Event `kind="FUNDING_RECEIPT"` on V1 engine | `EVENT_KIND_UNKNOWN` | Frozen V1 `reducer.py` unhandled kind dispatch |
| **NEG-10** | C4 File Mutation | Modifying 1 byte of `g1_offline_preview_r1/model.py` | `G1_CORE_MUTATED` | Manifest SHA verification in `no_order_port.py` |
| **NEG-11** | Forbidden AST Import | `import binance` inside G1 or sidecar | `FORBIDDEN_IMPORT` | Static AST walk in `verify_static_ast_and_core_immutability()` |
| **NEG-12** | Cross-Version WAL | Replaying R4 WAL into V1 engine | `WAL_GENESIS_MISMATCH` | Frozen V1 `storage.py` line 0 genesis hash verification |

---

## 5. Bounded Future Implementation Plan & Reviewer Route

### 5.1 Strictly Bounded Implementation Allowlist (Future Phase Only)

When authorized under a subsequent controller dispatch, implementation must be restricted to the following exact file whitelist:

| Whitelist Path | Operation | Target Content / Purpose | Maximum Line Budget |
| :--- | :--- | :--- | :--- |
| `scripts/g1_offline_preview_r4/__init__.py` | `ADD` | Package initialization and export | 20 lines |
| `scripts/g1_offline_preview_r4/model.py` | `ADD` | R4 data model, Decimal-128 guards, `funding_receipt_fingerprint` | 260 lines |
| `scripts/g1_offline_preview_r4/reducer.py` | `ADD` | R4 transition reducer, `_settlement_exposure()`, partial exit logic | 680 lines |
| `scripts/g1_offline_preview_r4/storage.py` | `ADD` | R4 durable engine, WAL tagging, idempotence check, checkpointing | 330 lines |
| `scripts/g1_offline_preview_r4/fixtures.py` | `ADD` | R4 test fixture wrappers | 80 lines |
| `scripts/g1_offline_preview_r4/analysis_schema.json` | `ADD` | JSON schema for R4 analysis output | 60 lines |
| `scripts/g1g3_offline_ports_r1/no_order_port.py` | `MODIFY` | Retain `PINNED_G1_C4_MANIFEST`, add `PINNED_G1_R4_MANIFEST`, update AST scan | +45 lines / -0 lines |
| `scripts/g1g3_offline_ports_r1/market_pit_port.py` | `MODIFY` | Support R4 causal funding translation & `REPLAY_TO_LEDGER` | +65 lines / -5 lines |
| `scripts/g1g3_offline_ports_r1/durable_supervisor.py` | `MODIFY` | R4 supervisor funding dispatch, version handshake | +35 lines / -2 lines |
| `tests/test_v06_p1d_r4_c4_dual_version_integration.py` | `ADD` | Comprehensive test suite for all 6 pillars and 12 negative cases | 550 lines |

**Strict Exclusions**:
- NO modification to any file in `scripts/g1_offline_preview_r1/` (remains 100% frozen).
- NO modification to any file in `tests/test_v06_g1_offline_preview_r1_*.py`.
- NO modification to protected H39, H40, or H41 goldens, tests, or scripts.
- NO CI workflow, policy, or manifest hash tampering.

### 5.2 Independent Reviewer Route & Verification Gates

The completed implementation must be submitted to the independent reviewer role (`ChatGPT-2-R` / `Codex Sol High`) along the following route:

1. **Gate 1: Static AST & Dual Manifest Gate**:
   - `verify_static_ast_and_core_immutability()` must verify:
     - All 13 original files in `scripts/g1_offline_preview_r1/` match `PINNED_G1_C4_MANIFEST` exactly.
     - All new files in `scripts/g1_offline_preview_r4/` match `PINNED_G1_R4_MANIFEST` exactly.
     - Zero forbidden imports (`binance`, `requests`, `openai`, `google`, `anthropic`, `btc_quant_agent`).
2. **Gate 2: Executable Pytest Gate**:
   - Execute both legacy and new suites:
     ```sh
     pytest -q tests/test_v06_g1_offline_preview_r1_*.py
     pytest -q tests/test_v06_g1g3_offline_ports_r1_*.py
     pytest -q tests/test_v06_p1d_r4_c4_dual_version_integration.py
     ```
   - Target: 100% pass across all tests with zero skips or xfails.
3. **Gate 3: Process Crash & Durability Gate**:
   - All 9 crash-injection boundary tests must run and verify recovery invariants.
4. **Gate 4: Full CI Compatibility Gate**:
   - Python 3.12 risk-based quality suite and compatibility suite must pass cleanly without AST or immutability violations.

---

## 6. Terminal Declaration

- **Design Verdict**: `DESIGN_READY_PENDING_INDEPENDENT_REVIEW`
- **Implementation Status**: `NO_IMPLEMENTATION_GRANTED` (Design-only deliverable)
- **C4 Identity Status**: `FULLY_PRESERVED` (Byte-for-byte frozen baseline guaranteed)
- **Author**: Gemini BOOST / Codex Sol High
- **Date**: 2026-10-14
