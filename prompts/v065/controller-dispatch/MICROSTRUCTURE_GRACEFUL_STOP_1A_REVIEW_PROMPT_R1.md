# V065-MICROSTRUCTURE-NONKILL-STOP-1A-REVIEW-R1

You are ChatGPT-1-A, independent consequential reviewer for quant v0.6.5. Review ONE frozen R3 SYNTHETIC graceful shutdown qualification, not the operational data migration itself. You are not the R3 operator.

## Exact sources
- Host hyz-laptop. Repo EXASHXE/btc-quant-agent-public; local/remote main v0.6.5@12b74b4c2fd3a22a9f4b35dbf331cfb1166aae77 at dispatch.
- Report /root/workspace/project/crypto-data/_control/MICROSTRUCTURE_GRACEFUL_STOP_QUALIFICATION_R3.md
  SHA256 183853bb262c6934c295a1372171621ce5ecb36564ba60d7f30e2d064dc79444
- Controller limited authority /root/workspace/project/crypto-data/_control/MICROSTRUCTURE_GRACEFUL_STOP_CONTROLLER_DECISION_R3.md
  SHA256 65cfffcdeebea814bce18c561e7d8a69d340df1d0f9457e592dcd2767a8ef68c
- Prior R2 STOP /root/workspace/project/crypto-data/_control/ACTIVE_DATA_CUTOVER_REPORT_R2.md
  SHA256 8da2395ec5efd92f1db2c929c6d48c2b7928eff0708410eb7f09e22ae4e61fd9
- Production unit /root/.config/systemd/user/btc-quant-microstructure-forward.service
  SHA256 eaabde7fdfd9074835c5beb655cadefa4e3bc1262718f1e6bcb1bd2bef74980b
- Legacy source /root/workspace/project/Quant-agent/src/btc_quant_agent/microstructure.py
  SHA256 e4201e10f10ee8038d1245adca5ec03644ac1b79a9bfdebbfa01a4cc114f88c6
- Proposed NOT INSTALLED user systemd drop-in:
  /root/.config/systemd/user/btc-quant-microstructure-forward.service.d/90-v065-nonkill-stop.conf
  Exact content as three newline-terminated lines: [Service], TimeoutStopSec=infinity, SendSIGKILL=no
  Proposed SHA256 8782e9353f633e260dcb29b2b645f316d2de959131b210f9f4ae743bf95718f8.

## Review questions
1. Recheck report and input identities, byte hashes and systemd-v255 behavior. Validate stop-policy semantics: TimeoutStopSec=infinity, SendSIGKILL=no, KillSignal SIGINT, KillMode control-group, Restart on-failure, PrivateTmp true. Did static fixture grammar verification and dynamic probes actually test intended settings? No claim of guaranteed real finalization is allowed.
2. Independently assess report's exact two synthetic cases and original bounded journal evidence: after approximately 2.035s deactivating with original PID alive; after approximately 5.16s inactive/dead, Result=success, exit status 0, no SIGKILL and no restart. Verify that the earlier two observer failures remain classified failures and that the 2s STOP_PENDING_GRACEFUL_EXIT deadline caused NO additional kill/restart/signal/copy. SIGCONT is not a second kill.
3. Evaluate proposed two-property production drop-in as an UNINSTALLED design, preserving actual ExecStart, WorkingDirectory, Environment, KillSignal, PrivateTmp, restart configuration, original fragment and no unexpected drop-ins. Do not install or reload anything.
4. Challenging question: the real finalizer may read/audit/checkpoint/hash more than 60GB. Thirty minutes is only a supervisor DECISION deadline. Verify fail-closed state if still deactivating: preserve pending stop, old timers paused, no forced kill/second signal/snapshot/migration/resume and explicit missed-origin evidence. Evaluate operator availability, power loss, OOM, watchdog interruption, unexpected restart, stale reader, real finalizer error and management of an indefinitely stopping process. If Owner has not accepted possible indefinite pause, require an Owner operations-tolerance decision before any real stop. Do not confuse lack of SIGKILL with guaranteed orderly exit.
5. Check provenance and non-actions: R3 had only synthetic fixture actions; actual microstructure PID, unit, timers and protected data unchanged; synthetic scratch/units cleaned. No re-running full tests absent an exact discrepancy. Read-only independent verification is allowed.
6. Produce ONE evidence-grounded independent report with exact terminal verdict and SHA256, identify residual production gate, and hand off a narrowly justified next action. No repeat R1/R2 broad audit, 67 clock tests, data trial or strategy review.

## Verdict — choose one only
ACCEPT_SYNTHETIC_NONKILL_POLICY_WITH_LIMITS — sound synthetic policy; separate Owner approval and bounded production-drop-in preflight may be considered, but NO production install/stop/cutover authorized by this verdict.
HOLD_EXACT_BLOCKER — identify exact falsifiable remaining discrepancy.
FAIL_R3_SYNTHETIC_POLICY — genuine contradiction in claimed evidence/semantics.

## Absolute non-actions
DO NOT signal/stop/restart/reload/configure any production service/timer/drop-in; DO NOT open protected original market databases; no source-QA market REST/WS, account, trade, testnet/live or source migration; no Git branch/worktree/commit/push, no CI changes. Produce report ONLY outside Git at:
/root/workspace/project-review-output/v065-microstructure-nonkill-r3-1/INDEPENDENT_REVIEW.md

Preserve SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE.

