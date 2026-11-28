# Embedded report — QUANT v1.0 Wave B Sol WEB Audit

> **Current navigation (2026-11-28):** [Wave D checkpoint](V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../prompts/v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../prompts/v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.


> HISTORICAL SNAPSHOT — superseded for current status and startup by [Wave D checkpoint](V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) and [current roadmap](V100_WAVED_ROADMAP_20261128.md). Use [Sol WEB bootstrap](../prompts/v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) / [Neon WEB bootstrap](../prompts/v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Retained as historical evidence; do not follow obsolete dispatch instructions.


> Historical receipt: superseded for current status by [Wave C final checkpoint](V100_WAVEC_FINAL_CHECKPOINT_20261127.md). Original disposition and evidence below remain historical.

Reference: QUANT-V100-WAVEB-SOL-QA-20261127
Status: SOL_REVIEW_RECORDED / PEER_RECONCILIATION_REQUIRED
Date: 2026-11-27 UTC+8. This records the preceding Sol review, not a new rerun or joint acceptance.

## 1. Current baseline
Personal local noncommercial read-only trading intelligence; four packages quant_transport, quant_core, quant_research, quant_agent_bridge. PUBLIC_MARKET bounded; real PRIVATE_USER_DATA not authorized; TRADE disabled. Initial BTCUSDT/ETHUSDT/SOLUSDT; 1D background, 4H regime, 1H setup, 15m trigger, 5m/quote actionability. Frozen B2 V1; M_global=19 (9 P3 + 10 Track C); NO_CANDIDATE_PROMOTED; sealed final holdout. P3 NO_CANDIDATE_BEATS_B2_V1.
S4-INTEGRATE joint offline acceptance: RC2 cd8cef634df6075c0bc02ba67240e782e03eb39d on feat/stage4-integration-rc2-20261126. Neon independent wheel lane 445/445, 104 hashed RECORD entries, 3/3 stored replay matches, four kernel fingerprints unchanged. Inputs: RC1 2a404719a9875acba2706b2cd9f292343ff263b0; 4A bedd2d753b7f64910f551fa70d7f9ad8177daaea; 4B cdfdfcf1f4105577f3898b55db0a1530c9b8b4c3; Track C beb3d572879b3ccd0d2d50f7decd87757970cf61. Main v1.0.0 remained RC1 at audit.
Source: /root/workspace/project/quant-1.0.0. RC2 worktree: [private isolated worktree] QRKP root: /root/workspace/project/quant-qrkp.
QR-R1/R3 CONDITIONALLY_ACCEPTED by Sol, QR-R2 CONTROLLER_ACCEPTED per Neon. Sampled source verification only; QR-R1 blind-freeze chronology worker-reported. QR-SYNTH is joint reconciliation, not blanket empirical approval. Wave 2 QR-R4 dynamic universe, QR-R5 news/sentiment/events, QR-R6 cross-asset/equity-linked instruments and proposed Stage 9 remain proposals; REV03 not approved. Existing REV02 draft: drafts/QUANT_V100_PARALLEL_ENGINEERING_RESEARCH_PLAN_20261126_REV02.md under docs root.

All four Wave B T3 threads observed COMPLETED, not settled; completion is not acceptance. S5/S6 executedModel exposed; S7/S8 requested Neon XHigh, executedModel not exposed. Private thread IDs retained locally.

## 2. S5-DEPLOY — TASK-S5-DEPLOY-20261126
Codex Sol, S4 thread [private identifier omitted] ordinal 3. Independent reviewer Neon WEB. Evidence /tmp/quant-s5-deploy-20261126/ (DEPLOY_RECEIPT.md, deploy-evidence.json, wheels-rc2/, wheel-pins.sha256, sqlite-pins.sha256, verify-install.py, activate.py, snapshot.py). Mode STAGED_VENV_REFRESH; worker READY_FOR_INDEPENDENT_QA.
Sol directly verified four distributions 1.0.0rc2 in /root/.quant-v080-venv, pip check PASS, three CLI shebangs, four wheel digests, installed payload 89/89 (11+17+51+10), hashed RECORD 104/104 (15+21+55+13), zero mismatches. Current operator SQLite hashes match previous baselines:
bridge_outbox.sqlite 45ab1c91e7f07b1d5a7a1ea1a6877f1c0918bb388347e68f996c8f9f5fc85094
decision.sqlite 29004b5c11dbd58611a156180001f42ede8fcd2e7adf12e0b5fb877490a8dcd0
market_evidence.sqlite 30233f11220e131d985d1beb884d5c89cc2c627f287647922b642f5251b5a6f4
RC1 backup /root/.quant-v080-venv.backup-1.0.0rc1-20261126 exists mode 0700. Hermes PID 1270815 remained present, start Wed Nov 25 01:33:50 2026. User systemd bus failed No medium found; loaded units unverified. Main RC1 and candidate RC2 refs matched.
Worker reports atomic renameat2 exchange, verified rollback fingerprints including 0.8.0 backup, six replay calls through both CLIs (BTC 2fb6e77f..., ETH 45f92b9d..., SOL aa8e8ce9...), default preflight PASS, approval-required MISSING_REQUIRED, disconnected namespace/Landlock, no outbound scan/delivery. Sol did not rerun all deployment checks or backup fingerprint. STALE_PRE_RC2_RISK worker verifier result supported by unchanged PID, not in-process import proof.
Sol supports staged refresh only pending Neon independent QA. Suggested ceiling CONTROLLER_ACCEPTED_STAGED_VENV_REFRESH_ONLY. Separately authorize quiet-window Hermes restart and PID-bound actual module import proof; no repeat venv refresh without defect. Field and recurrence separate Owner gates; bounded 39 GET/3 truthful cards/delivery evidence. No inferred merge/tag/push or unit activation.

## 3. S6-DESIGN — TASK-S6-DESIGN-20261126
Codex Astra, thread [private identifier omitted] ordinal 2. Neon WEB independent reviewer. Six files under s6-design/; hashes matched worker receipt. Support immutable cache revisions/PIT, pure descriptive factors, separate B2 card context, actual measured benchmarks, Plan A all 39 slots consumed, no transport expansion or live warm-up, OI UNIT_UNKNOWN without unit proof. Worker reports 26 internal reserved paths and 41 pinned input hashes; not fully independently reproduced.
WAVEC-F01 HIGH: S6-BRIDGE and S8-AGENT both reserve packages/quant_agent_bridge/hermes_assets/plugins/quant-s5/__init__.py. S6 quant_query(kind=market_context) requires one symbol or card_id, S6_CONTEXT_QUERY_V1; S8 quant_market_context allows neither (bounded three) and another envelope. Freeze one canonical stored reader/validation contract; thin UX wrapper only if useful; one writer or sequential integration; recompute global write-set intersections. S6 cache/factor can proceed after their independent design acceptance and freeze. S6 substantive design supported; Neon QA and shared contract reconciliation pending.

## 4. S7-DESIGN — TASK-S7-DESIGN-20261126
AGY-A standard Neon requested XHigh, thread [private identifier omitted] ordinal 1. Sol independent reviewer. Five files under s7-design/; four substantive hashes matched manifest, manifest digest computed.
Six slots ES-01 taker/OI range, ES-02 flow variance, ES-03 funding tail, ES-04 funding RV, ES-05 4H breakout, ES-06 sweep recovery. First two descriptive; four directional/RV mechanisms. Zero strategy-trial budget, M_global=19, DEVELOPMENT_EXPLORATORY only, joint calendar-block bootstrap, Holm, 144h purge/embargo, dynamic funding and dual execution. Worker 12/12 vectors, 15/15 negative +3/3 positive registry tests are not comprehensive.
S7D-F01 HIGH REPRODUCED_OFFLINE: exact SQL fenced block from S7_PILOT_ENGINEERING_SPEC.md executed in sqlite3.connect(":memory:"). Six adverse operations ACCEPTED: arbitrary slot; wrong split; CONFIRMATORY event with unapproved digest; invalid metrics string "{x"; strategy trial after sealing incomplete meta; INSERT OR REPLACE resets COMPLETED to RESERVED. Require complete metadata before seal, fixed six slot/spec/dataset/split binding, authorized scope, valid JSON, immutable terminal state, reject replacement; reproduce six negatives and positive lifecycle. No deployed registry yet.
S7D-F02 HIGH: RC2 ingestion.py parses archived OI numeric fields, no proven contract-to-base conversion. Notional/(quantity*price) ratio is plausibility not unit proof. Adopt S6 UNIT_UNKNOWN/certificates; preserve OI-free ES-01/05 and +5/+15m visibility masks. No holdout or live calls.
S7D-F03 HIGH: S6 48-bar population variance, 5m clock, prior 288-observation z-score, zero-volume invalidation; S7 ES-02 144-bar sample variance, hourly clock, log/30d percentile, limited zero-volume exclusion. Distinct versioned feature IDs and validation; both adapted proxies, original source metric replication unestablished.
S7D-F04 MEDIUM: inverse-vol weights not beta neutrality. Distinguish ex-ante exposure/hedge and ex-post regression; reconcile partial-fill stress text, gross denominator and actual funding crossings.
S7D-F05 MEDIUM: distinguish low power, failure to reject, negative net economics and falsification. Scarcity -> INSUFFICIENT_POWER_INCONCLUSIVE. Define bootstrap estimator/denominator, empty event days, WF time gaps and cross-symbol dependence. Design concern, not an observed outcome defect.
Disposition MATERIAL_CORRECTIONS_REQUIRED before final S7-PILOT contract. One bounded methodology correction if needed (Astra XHigh proposed), no new outcomes or local QA-only task.

## 5. S8-DESIGN — TASK-S8-DESIGN-20261126
AGY-B standard Neon requested XHigh, thread [private identifier omitted] ordinal 1. Sol independent reviewer. Five files under s8-design/; hashes matched worker receipt. Support Hermes/AgentFacade reuse, four packages, synthetic account, UNKNOWN Owner limits, non-radar exposure inclusion, eligibility vs account suitability, no WATCH upgrade, journal noncausal attribution, deferred L2/disabled L3. Ten account and five journal fixtures, 30 designed Agent cases across seven categories, not executed PASS. JSON parse and Draft 2020-12 metaschema check passed, not full nested-instance coverage.
S8D-F01 HIGH: candidate protective stop is not verified full coverage. Unknown qty/trigger direction, partial coverage, invalid/nonprotective trigger and stop-limit execution uncertainty must not pass configured require-stop-protection. Distinguish candidate, verified quantity coverage, partial, unknown, invalid and execution uncertainty. Live endpoint semantics UNKNOWN.
S8D-F02 MEDIUM: quant-bridge journal-add lacks CLI reservation in S8-SYNTH; S6-BRIDGE reserves cli.py. Choose local-only entry point and single writer; no chat mutation.
S8D-F03 MEDIUM: harness regression and scripted replay cannot prove actual LLM selection, injection robustness or model task success. Separate deterministic PASS, scripted replay and separately authorized model evaluation. Also resolve WAVEC-F01.
Disposition MATERIAL_CORRECTIONS_REQUIRED for affected contracts, not architecture rejection.

## 6. Wave C and required Neon response
Keep S5 operational closure independent. After respective design acceptance, S6-CACHE/FACTOR can progress without waiting for all S7/S8 findings. Fix S7 methods/registry before empirical contract; S7-PILOT synthetic offline tooling only until separate empirical approval. S8-SYNTH after protection/CLI correction; sequence S6-BRIDGE then S8-AGENT or unique shared writer. No new mandatory serial QA layer. Keep QRKP Wave 2 and REV03 research independent.
Neon directly verify S5/S6, reproduce or challenge six SQL counterexamples, respond WAVEC-F01, S7D-F01..05, S8D-F01..03 individually AGREE / AGREE_WITH_REFINEMENT / DISAGREE_WITH_EVIDENCE. Reconcile OI/factor/plugin/CLI contracts and global write sets; propose minimal dependency-aware Wave C, actual scoped dispositions where authorized, exact task cards only when needed. Gemini-authored S7/S8 independent QA remains Sol WEB; Neon peer reconciliation cannot substitute.
Evidence ceiling: prior Sol review read actual T3, selected source/design, 16 design file hashes, installed bytes/RECORD, current operator SQLite and six in-memory counterexamples. Not full Worker reproduction, all historical input/backup verification or historical zero-access proof. No empirical outcomes, holdout access, source edits, external calls, private account, trades, deployment, restart or dispatch in that review. Preserve immutable historical evidence, frozen B2, M_global=19, NO_CANDIDATE_PROMOTED and sealed holdout. No authorization implied.
## 7. Current artifact SHA-256 manifest (recomputed during documentation sync)
s6-design/
DESIGN_CHECKPOINT_AND_MANIFEST.md 9eb60cce70d32e319817e4dc1c1286078ebd75924efd35d7212dd1a8e468a792
S6_BRIDGE_AND_CARD_UX_SPEC.md 5ce9fe2c83d3fca027779cca6c77f83b22e7a1ed718f580d42ed18f52c407850
S6_CACHE_CONTRACT.md 6a060335a8b7b56b556bc112f7ce3b8ee992ba05a5c74f59fb0da2716ab246c5
S6_FACTOR_CONTRACT.md 520c3876568fe47474397109767561011d6549293109378acc909ac1c91e04cf
S6_SCHEMAS_AND_TEST_MATRIX.json 20ac31bc55c23d9d4cf4b584d82a28b8a803bf745f62e259e39e9600a6b4097d
WAVE_C_PARALLEL_EXECUTION_PLAN.md bd42788c859b042bf07ca5ee0fea2c3871f06031e9c61dd1fc64c4e9c43f55e3
s7-design/
DESIGN_CHECKPOINT_AND_MANIFEST.md 89d7198f122c69ae116e864db7ad929f6bd007ad32f1941043b0c07574b747af
S7_HYPOTHESIS_CARDS_LOCKED.md 72107731c1a7e0b6b9b53a25d3e48b828301b94a402f8522ef535d6ee711771b
S7_MACHINE_GATES_AND_SPECS.json 974c442a7be44cc94d4d1ca04e3ad9899101d6705b782d1dfe584608c34ca5bb
S7_PILOT_ENGINEERING_SPEC.md 7d45a01adf81eedec325164f8f3b2c70044459cb3522b067ab4b7144710438e9
S7_PREREGISTRATION_PROTOCOL_V1.md abcd17572f1d56b94652ed9da1d91256b2a44c2179b3a0e9daec1c82b9f14fdc
s8-design/
DESIGN_CHECKPOINT_AND_MANIFEST.md 4c016bcc71e687495e0985968606144d5408f3c776aa98095aa283738f9f41dd
S8_ACCOUNT_AND_JOURNAL_CONTRACT.md b6e8081d44bc6a96a13ec77988e5ae4fc8dc4c82228594bd351f4bd658cf14e8
S8_AGENT_EVAL_SUITE_SPEC.md 69d440976293b3cb8549fb27e80bed8ff93347cd91099bcfc3a7818e4462e49f
S8_HERMES_AGENT_TOOLS_SPEC.md c2f7b9074fbb330789bd015c0ae1ba3bdb0c6ebcb9119a582f9586decc6fa541
S8_LAYER2_LIVE_GATE_AND_SCHEMAS.json 75cde09564fcf6987ee9a3523c99e83a8e8fb79e7b18f909677ccb4c46943d6d
S5 wheels-rc2/
quant_agent_bridge-1.0.0rc2-py3-none-any.whl 54e5426db1840a8dc90c05a2dd466ced45de471d3d528c1dc998ddfda41d0cac
quant_core-1.0.0rc2-py3-none-any.whl 2fd24a0dd07d449fab40b4469f7600efdb106db1c32c1c567f2b5e0cf447a3f9
quant_research-1.0.0rc2-py3-none-any.whl 7a1231512bef2b6ba19912ca68236b093c46baddd022d3b032e7a376e5ad1942
quant_transport-1.0.0rc2-py3-none-any.whl 6d84be973c40c9d50861a0288f18e969a0a29f474d6c20874164424a4b2ef8e0
