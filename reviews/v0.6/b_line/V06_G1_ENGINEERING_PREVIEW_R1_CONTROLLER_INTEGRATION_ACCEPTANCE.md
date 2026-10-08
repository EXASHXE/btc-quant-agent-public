# G1 Engineering Preview R1 — Controller L2 Engineering Acceptance and v0.6 Integration

**Accepted feature SHA:** `efd73496d01a71a158d67343b64695d33fab16a8`; first implementation `0a37146aa76ae0a113760ebf88bc1ecca27b5123`; bounded fix implementation `9867a4e3994b3ab98064e01f2a20eb446b30d18c`. Engineering preview feature inherits accepted R8 limited safety semantics, WP-A/C/D interfaces, and mock DRY_RUN. It is not an actual release candidate or safety permission to trade.

## Evidence and fail correction

- G1 original full run [37755191706](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37755191706): **2767 PASS, 1 H40 golden FAIL, 2 SKIP**.
- G1 repaired exact SHA [37772124985](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37772124985): **2768 PASS, 2 SKIP, 0 FAIL** in Python 3.12; 8 warnings. This is GitHub-hosted independent CI, not just executor report.
- Pre-G1 baseline exact checkout `d6500140...` running same full suite [37773542782](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37773542782) fails **the identical H40 golden** (`ee185f1fce50...e54526643d` versus frozen `d5a962cd9c95...7c8670bf0b2e0`) even without any G1 code. Baseline job also had **three additional environment/test-runner failures** (`tests/test_ci_test_plan.py` 2 tests with missing comparison/setup and `test_tactical_grid_shadow_evaluation_v1` missing git history), so **4 failed / 2071 passed / 2 skipped** does NOT establish a clean one-failure-only baseline. However exact same scientific digest mismatch is independently demonstrated as present on the pre-G1 code.
- Earlier exact-SHA isolated H40 diagnostic [37759244599](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37759244599) passed both baseline and G1. Cause appears order/runner sensitive; root cause **not proven**. Golden and scientific sources untouched. This known inherited/intermittent scientific test defect remains in separate tracked follow-up; not assumed fixed. Do not hide a future failure or certify A-line scientific correctness from B-line gate.
- G1 repair moved historical `evidence/v0.5.5/**` imported manifest into v0.6 `RELEASE_MANIFEST_TEMPLATE_UNBOUND.json` and rebound API/tests/runbook. One repair evidence file `L2_REPAIR_R1_H40_DIAGNOSIS.json` contains a manually reported golden digest **inconsistent** with the exact immutable test constant; Controller **rejects those fields as source-evidence**, while relying on actual independent GitHub pass/fail and raw traceback for diagnosis.
- G1 plus v0.6 CI patch have **zero path intersections** at common ancestor `d6500140...`; G1's **92 path changed files** contain no `h40/**`, `h41/**`, `market_watch/**`, `evidence/v0.5.5/**` or RC2 protected changes.

## Authority and merge

**Engineering-only L2 disposition:** `ACCEPT_G1_OFFLINE_ENGINEERING_PREVIEW_WITH_KNOWN_H40_TEST_DEFECT`. This accepts the functionality/structural safety/compilation and reports for **mock end-to-end DRY_RUN**, not strategy quality, not G3 real external endpoints, not exact bound production release manifest, not TESTNET, not any real-funds grant.

Controller created two-parent **non-force** merge on `v0.6`:
- **Merge SHA `a56cc413d87a71111f2be02f10052dced9ff0275`**
- First parent `03c4b5ebea299a11a5f0c64f45572b27cc4ad4b8` (post-CI-only fix)
- Second parent `efd73496d01a71a158d67343b64695d33fab16a8` (G1 repaired)
- 92 exact imported changed paths, 0 G1-mainline intersecting paths, 0 protected paths.
- Separate integration CI [37778010147](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37778010147) launched; mark **PENDING until final result**, do not claim post-merge CI success prematurely.

Still **PENDING**: G3 Linux 3.12 startup/service provisioning plus real LLM and Feishu *non-trading* provider smoke; G4 exact bound release candidate + independent TESTNET authorization; G2 valid economic evidence; G5 pre-live safety and G6 tiny manually approved canary. `TESTNET=NOT_AUTHORIZED`, `REAL_FUNDS_WRITE_AUTHORITY=NONE`.
