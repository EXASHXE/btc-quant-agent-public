# QUANT v0.8.0 — H1 P0 Contract Interoperability Consolidated Remediation

> **Current navigation (2026-11-28):** [Wave D checkpoint](../../project/V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](../../project/V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.

Task ID: V080-HERMES-H1-P0-INTEROP-REMEDIATION-01
Primary executor: Gemini 4 Neon XHigh; fallback: GPT-6.2 Sol Extra High
Controller 0-C: sole independent reviewer and acceptance authority
Dispatch state: CORRECTION_PROMPT_READY / NOT_DISPATCHED
Authorization: OFFLINE_SYNTHETIC_ONLY. No real Feishu, Binance, OAuth, private data, trade or external messages.

## Objective

Fix the three independently reproduced blocking H1 Contract V1 semantic gaps together, and produce one sealed canonical H1 reference-export package for future Pi P2. H1 remains the only proposed first notification gateway and deterministic sender; no second outbox/sender, no Pi implementation, no general QUANT audit or model loop rewrite.

P1 architecture was separately accepted ARCHITECTURE_ONLY; P2 is blocked until this package passes Controller review. Do not self-accept or dispatch any worker.

## Immutable input baselines

Code root: /root/workspace/project/quant-0.8.0/, branch v0.8.0, source HEAD bd144f2d15836bb84786c91aec571df77351bf5c.
Docs root: /root/workspace/project/quant-docs-engineering/, branch docs/engineering. Verify latest HEAD and clean tracked tree.
Immutable frozen V1: docs/architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md
V1 SHA-256: 622677b019120ed18d9bfea057589f7bf923f7f15e17adb3ac59831a0bfd8cc2
Controller P0 decisions: docs/architecture/V080_QUANT_AGENT_V1_P0_CONTROLLER_DISPOSITIONS_20261120.md
Controller golden identity and canonical JSON cases: docs/architecture/V080_QUANT_AGENT_V1_P0_CROSS_LANGUAGE_GOLDENS_20261120.json
Accepted H1 original isolated root:
workspaces/lt-v080-gemini-neon-hermes-quant-feishu-h1-01/
Original H1 state: 57/57 sealed files; 17 clean + 17 mixed + 20 Hermes v0.16.0 isolated tests independently passed; CONTROLLER_HOLD_P0.
Original wheel SHA256: aed14d03ee51cafc34b89f5d30adf9ca2a676d7b851863c644c59b57ff4b81cc.
Existing P1 read-only root: workspaces/lt-v080-astra-pi-quant-agent-architecture-p1-01/, seven docs sealed; ARCHITECTURE_ONLY accepted.

Use a NEW isolated work root:
workspaces/lt-v080-gemini-neon-hermes-h1-p0-interop-fix-01/

NEVER modify original H1 sealed files, P1, frozen V1, Controller decisions, canonical docs, installed Hermes /usr/local/lib/hermes-agent, B1–B5, Program J or real Hermes profiles. Copy exact accepted H1 source into isolated correction root, implement there and preserve original wheel and source hashes. Avoid a second worker writing the same package.

## P0-C01: no-episode B2 diagnostics

B2 legitimately emits NO_SETUP and NOT_EVALUATED cards with episode_id=null. Under the Controller profile, represent them as diagnostic-only history/context records, with original source/status/reasons/card_id/time retained plus diagnostic_only=true and not_eligible_for_alert=true.

list_active_signals MUST NEVER include such a null episode card, even if statuses=["NO_SETUP","NOT_EVALUATED"] is supplied. Core episode-bound records only. Do not fabricate noep:cardID or a synthetic episode ID in any public read response. get_signal_detail remains episode-bound. Outbox refuses any null-episode event without creating an event ID or delivery attempt.

Independently reproduce the original issue against the original H1 fixture, add regression tests that fail before fix then pass after fix. Verify the no-episode historical records remain queryable and do not disappear.

## P0-C02: evidence-free failures and heterogeneous aggregate pages

Remove any default EVIDENCE_SYNTHETIC attribution before authorization/verification. Any unverified pre-source error (UNAUTHORIZED, UNKNOWN_TOOL, INVALID_ARGUMENT, TIMEOUT, no data/source) returns status=ERROR, source_evidence_class="UNKNOWN", server_as_of_ms=null if no verified market time, and redacted typed error. UNKNOWN is NOT an admissible genuine or synthetic card class.

After a verified read, class can be carried only if homogeneous; if multiple qualified source classes, top-level envelope source_evidence_class="UNKNOWN" and per-item exact source classes retained, with aggregate/heterogeneous evidence marker. No optimistic lexicographic min(classes), no hardcoded synthetic banner that contradicts items. Empty unqualified collection has UNKNOWN and no invented as-of.

New negatives: unrecognized principal before source, unknown method/tool, invalid args, failure before registry, missing local DB, two-source mixed page, empty page, corrupted source and clock uncertainty. Assert no false source classification or any affirmative send.

Do not mutate original QUANT source receipts or promote QA to genuine.

## P0-C03: H1/Pi cross-language canonical version/hash and reference export

Use the Controller's independently computed Python/Node seven golden JSON vectors. Implement a standalone, deterministic Python golden exporter tied to the corrected H1 implementation, and a TypeScript/Node offline comparator that validates byte-identical UTF-8 canonical preimages and SHA256 digest for all seven cases. Use the specified recursive ASCII key sort, JSON string escaping, stable arrays and decimal strings. Reject malformed Unicode, nonfinite/numeric identity/version fields and ambiguous normalization.

Version must remain an opaque string bound to actual card-publication event sequence/hash and verified source publication; later unrelated events may not renumber a card. Export a two-card/no-episode journal and replay an unrelated later event, checking unchanged original card_version/event ID. Include exact as-of, card/reprice version pairing, pagination/cursor and status filter representation.

Seal golden fixtures as separately consumable, frozen files: Python reference inputs/preimages/sha digests, Node comparison log, H1 facade response envelopes for successful, pre-source error, mixed/empty/no-episode, original ordered reason codes, version mapping, deterministic rendering bytes, duplicate IDs, mock Feishu private DM transcripts and outbox crash/ack generation trace. Original accepted B1–B5/H1 source remains unchanged.

Future P2 must consume only the sealed H1 golden export; P2 cannot compute its own oracle from Pi output.

## Test security and execution boundaries

All tests and demos run in unshare -n with loopback-only no route. No new live environment variables, account keys, real Feishu/Binance/model calls, gateway start, plugin installation into real Hermes HOME, actual private DB reads, TRADE actions or P2 work.

Re-run original H1 clean/mixed/Hermes v0.16.0 integration matrix (17/17,17/17,20/20 inherited case counts may change with new tests; report actual), plus new P0 regression tests and independent Python/TypeScript cross-language roundtrip. Verify original H1 wheel hash and 57/57 sealed original files, P1 7/7, B1–B5/R1/Astra/Program J original baselines and both Git tracked trees. Non-H1 files read-only.

Retest local UNIX domain socket UID, recipient authorization, no privates, mixed class security, model-free first alert, outbox stale suppression, UNKNOWN_DELIVERY, no simultaneous senders, QUANT-only signal status and numeric fidelity.

No need to satisfy arbitrary count quotas; all covered negatives must pass. Do not pretend offline mocks establish real Feishu delivery or a real Pi SDK.

## Final package and handoff

Only in the new fix root deliver installable corrected H1 wheel/plugin (new correction version, not overwriting original), full sources and P0 tests, Python/Node golden exporters/comparators, immutable machine-readable fixture pack with relative paths and hashes, H1_P0_REMEDIATION_REPORT.md, H1_V1_CANONICAL_EXPORT.md, H1_QA_REPORT.md, CONTROLLER_HANDOFF.md, all logs and a full self-consistent SHA256SUMS (no symlinks, path escape or missing entries).

A single integrated package. Correct/fix within the workroot; submit READY_FOR_CONTROLLER_REVIEW once. Worker cannot accept H1 or P2.

Controller acceptance ceiling: SCOPED_ACCEPTED_OFFLINE_HERMES_H1_REFERENCE_WITH_P0_FIXED_ONLY. A successful corrected H1 reference may unblock a future Controller-created ONE integrated P2 offline engineering card. It does not itself authorize P2 dispatch, live Feishu, models, Binance, B3 or Layer3 TRADE.

Final Chinese summary: actual model and effort, exact original and new wheel+manifest digests, P0-C01/C02/C03 per-case before/after proof, source/recipient integrity and OS isolation evidence, tests and cross-language hashes, reference export path, no-live status, READY_FOR_CONTROLLER_REVIEW.

End H1 P0 correction task.