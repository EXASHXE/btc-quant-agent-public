# QUANT v0.8.0 — Controller 0-C V1 P0 Interoperability Dispositions (2026-11-20)

Status: CONTROLLER_DECIDED / H1_REMEDIATION_REQUIRED / P2_NOT_AUTHORIZED

Normative baseline is unchanged: V080_QUANT_AGENT_CONTRACT_V1, SHA-256 622677b019120ed18d9bfea057589f7bf923f7f15e17adb3ac59831a0bfd8cc2. This companion decision resolves diagnostic/error/canonicalization ambiguities; it does not rewrite V1, accepted B2–B5 or P1. If a consumer cannot implement these decisions without breaking V1, stop and propose an explicitly versioned new contract.

Independently verified: P1 7/7 sealed docs; H1 57/57 sealed files and QA 17/17 clean, 17/17 mixed, 20/20 Hermes v0.16.0. Despite successful H1 QA, full H1 reference V1 acceptance is HOLD for the following P0 semantic defects.

## P0-C01 — NO_SETUP without episode

Decision: A Core card/event without a Core-assigned episode_id is a DIAGNOSTIC record, not a SignalSnapshot or notification event.

- B2 can generate NO_SETUP/NOT_EVALUATED with episode_id=null. Preserve the original status/reasons/card_id/source/as-of in get_signal_history diagnostic records or get_market_context diagnostics. Mark diagnostic_only=true and not_eligible_for_alert=true, with episode_id=null.
- list_active_signals must never emit records with missing episode_id, even if the caller explicitly filters for NO_SETUP or NOT_EVALUATED. No fake noep:<card_id> public identifier or synthesized SignalEpisode.
- get_signal_detail requires an authentic episode_id. No-episode diagnostics may be viewed through supported history/context queries, but cannot be fetched with a fake episode ID.
- The V1 outbox identity is undefined for an absent episode ID. Never enqueue, notify or hash a no-episode market opportunity.
- Controller independently reproduced: H1 history has NO_SETUP/NOT_EVALUATED with episode_id=null, and list_active_signals with statuses=["NO_SETUP","NOT_EVALUATED"] returned NOT_EVALUATED with episode_id=null. P0-C01 is an observed issue requiring correction, not hypothetical.

## P0-C02 — Pre-evidence errors and mixed aggregates

Decision: For an ERROR without verified source evidence, use source_evidence_class="UNKNOWN" as a non-evidence sentinel; server_as_of_ms=null if no qualified source clock. UNKNOWN is never a genuine/synthetic source class and must not appear in actionable SignalSnapshot. V1 response field remains present.

- Authorization, argument validation, missing-source or timeout failures BEFORE any verified source read: status=ERROR, typed redacted error, source_evidence_class=UNKNOWN, server_as_of_ms=null. Never inject a synthetic or genuine banner into an evidence-free error.
- If source was already verifiably homogeneous, the exact accepted class/as-of MAY be reported on a subsequent error. Otherwise UNKNOWN.
- Mixed-source aggregate or page response: envelope class UNKNOWN, but each individually verified item retains its exact original evidence class. Require explicit aggregate/heterogeneous notice and prohibit affirmative aggregate notification.
- Empty collection without verified market source likewise uses UNKNOWN and no invented source time.
- Controller independently reproduced H1 unknown principal denial: ERROR / UNAUTHORIZED / SYNTHETIC_QA_ONLY / null as-of, because handle_request defaults evidence_class to EVIDENCE_SYNTHETIC before authorization. This is false evidence attribution.
- H1 uses min(classes) on heterogeneous verified-source classes. Lexicographic ordering cannot determine source provenance; replace with exact homogeneous class or UNKNOWN. Do not use a hardcoded synthetic banner for mixed collections.
- No change to B2/B4/B5 stored source labels or accepted market engine.

## P0-C03 — Python/TypeScript canonical bytes, card version, event identity

Freeze a byte-level V1 interoperability profile; Controller-independent golden set:
docs/architecture/V080_QUANT_AGENT_V1_P0_CROSS_LANGUAGE_GOLDENS_20261120.json

- Notification event_id = SHA256(UTF8(canonical_json([contract_id,channel,recipient,episode_id,card_id,card_version,market_status]))). Exactly seven strings, original order, original opaque case-sensitive spelling. Notification identifiers must be verified approved ASCII forms; no normalization, silent trimming, lowercasing or JavaScript Number conversion.
- Canonical JSON follows Python 3.12 json.dumps(value, sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False), encoded as UTF-8. Node/TS implementation recursively sorts ASCII property names and uses JSON string escaping. Reject non-ASCII property names, unpaired Unicode surrogates, nonfinite numbers and numeric identity/version fields in this conformance profile. Arrays preserve order, prices and ratios stay decimal strings.
- Card version of form jseq:13:ae85486779f47312:3ec61364d9d6677c is an opaque immutable string mapped to its original verified card publication and source witness. Never derive it from a subsequent unrelated event or current mutable cursor/time.
- Controller independently checked seven cases in Python 3.12 and Node 24.13.1: exact matching preimage UTF-8 bytes and SHA-256 for changed status, version, recipient, real B2-style identity, Chinese value strings and recursive ASCII key sorting.
- Controller oracle is not a substitute for H1 publishing sealed implementation-owned Python/TS golden vectors and their executable comparisons; current H1 sealed manifest has no golden/vector fixture. H1 must export version mapping, no-episode diagnostic, pre-source ERROR bytes, heterogeneous pages, cursor/filter normalization, hashes, deterministic rendered card bytes, mock DM transcripts and outbox crash/ack trace before P2 can begin.
- A plain JSON.stringify of arbitrary objects without stable key ordering is NOT canonical.

## Additional H1 security and sender rules

The isolated H1 tests support restricted Unix-domain socket, SO_PEERCRED UID negative cases, B3-sentinel isolation, installed Hermes Plugin integration, mocked Feishu standalone outbound/Gateway inbound, stale-card suppression, outbox unknown-delivery transitions and model-free rendering. Those tests do NOT establish a real service-account/UID production deployment, actual Feishu delivery or actual QUANT/Binance data. Real-world OS principal separation and Feishu credentials remain separate gates.

Hermes H1 retains sole intended notification outbox/sender authority. Pi P2, if separately dispatched, may only consume H1's verified read facade, mocked conversations, golden vectors and deterministic alert proof; no second production sender, new Feishu gateway or competing outbox.

## Final decisions

- P1: SCOPED_ACCEPTED_ARCHITECTURE_ONLY; Pi v1.5.2 / commit b4afdddf44e059c67ccf5097e5317d913521b470 packages corroborated using upstream GitHub commit/manifests. No Pi installed, no SDK runtime test. This does not dispatch P2.
- H1: HOLD_P0_CONTRACT_SEMANTICS_AND_GOLDEN_EXPORT. Existing 54 QA checks PASS, but P0-C01/C02/C03 must be corrected and proven together in a newly sealed isolated correction package. Do not modify the original 57-item sealed H1 in place.
- P2: BLOCKED_BY_H1_INTERFACE / NOT_DISPATCHED. P1's draft is not a forwardable Controller task. Only after H1 reference vectors are accepted may 0-C prepare one integrated P2 engineering card.
- B5 Phase B genuine public data, real Feishu app/bot/messages, real model OAuth/provider, private Futures data, recurring polling and Layer3 TRADE remain NOT AUTHORIZED.

Immediate Owner action: forward one integrated H1 P0 remediation task to Gemini 4 Neon XHigh; do not start P2 yet.
