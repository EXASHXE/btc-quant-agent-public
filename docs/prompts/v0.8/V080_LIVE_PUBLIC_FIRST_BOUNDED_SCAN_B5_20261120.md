# QUANT v0.8.0 — B5 Genuine Public Origin & First Bounded Market Scan
Task ID: V080-PERSONAL-MVP-LIVE-PUBLIC-B5-01
Primary executor: GPT-6.2 Sol Extra High; peer fallback: Gemini 4 Neon XHigh
Architectural escalation: GPT-6.2 Astra only for material source-trust, causal or security design conflicts
Dispatcher and independent acceptance: Controller 0-C
Status: CONTROLLER_SCOPE_APPROVED / AWAITING_OWNER_FORWARD / NOT_STARTED
Authorization: PHASE A OFFLINE ENGINEERING ONLY. PHASE B GENUINE NETWORK REQUESTS NOT AUTHORIZED BY THIS PROMPT.

## 0. Mission and delivery protocol

Implement one cohesive B5 package that advances the accepted B4 offline public-source bridge into an independently reviewable, genuine Binance USDⓈ-M public HTTPS origin binding, real-origin evidence admission and a prospective one-time bounded public market scan with B2 market-only human decision cards. The first genuine scan remains an explicit Owner+Controller capability decision, not an implied development permission.

Keep one task ID, one isolated engineering writer and one integrated final audit; do not create many implementation sub-tasks.

Work in two sequential phases:
- PHASE A — Implement the real-origin transport and source-to-B2 integration, including all negative cases and a genuinely disabled default. Complete code, build, installation, mock/loopback E2E, documents and sealed offline evidence. Then return READY_FOR_ACTIVATION_REVIEW. The worker MUST NOT contact Binance API, resolve Binance API DNS, inspect real account credentials, or exercise the physical network adapter against any external host.
- GATE A — Owner locally supplies/approves the actual region/egress route, artifact storage and retention and one-run envelope; Controller independently reviews the sealed implementation, exact physical-origin binding, route/venue obligations and final scope/release digest. A standing Owner personal public-data attestation already exists; do NOT ask for it again.
- PHASE B — Only after explicit separate Owner authorization AND recorded Controller activation for this exact release/scope, execute at most the approved bounded genuine-public scan, preserve all raw evidence and source-to-card causal verification and immediately stop on denial. This remains the SAME B5 task, with a final READY_FOR_CONTROLLER_REVIEW handoff. If Gate A has not been satisfied, stop after Phase A; never self-activate or infer approval from this dispatch.

No unattended daemon, no automatic recurring scans, no direct Feishu messages and no Layer 3 order capabilities. B3 private account integration stays disconnected and is not a dependency of B5. Real account equity, safe position size and actual order protection remain UNAVAILABLE/UNKNOWN.

## 1. Current accepted baseline — inspect and pin

Code root: /root/workspace/project/quant-0.8.0/
Code: v0.8.0 @ bd144f2d15836bb84786c91aec571df77351bf5c
Canonical docs root: /root/workspace/project/quant-docs-engineering/
Docs branch at B5 preparation: docs/engineering @ 933c33e1e86087959566b4f36b07aa893ddec469
New isolated work root: workspaces/lt-v080-personal-mvp-live-public-b5-01/

B4 accepted offline source bridge:
workspaces/lt-v080-personal-mvp-public-source-bridge-b4-01/
B4 acceptance:
controller-decisions/V080_CONTROLLER_B4_PUBLIC_SOURCE_BRIDGE_OFFLINE_SCOPED_ACCEPTANCE_20261120.json
Acceptance SHA-256:
095dc79a730b843257947f6d77760a741efb67a6973880c4f9a806ef9ec86b58
B4 SHA256SUMS SHA-256:
127fcb635d70096bace47949c69d2bb9c5629460d27b3adf02c457f02c438216
B4 wheel SHA-256:
c30332d0028b14f2c7ee89ef941be3e9d51f1ff500231bb9cbcaae95a63c7710

B1 / B2 / B3 SHA256SUMS SHA-256:
B1 73af3d2e273e9d4c6865fe3fe935939c4ae64a7a1475c4bb0ab99ceef319f7a5
B2 8c908905eaa8002e12f53f1d78939b15726658726c20b19abc66c673c6a58368
B3 b652ffdc79a0392612c19f02542df3713baf0ab82bd12af5c0eae017c596e54b

Before coding, confirm both tracked trees clean, acceptance hashes, upstream wheels/manifests and no overlapping B5 writer. Read B4 SOURCE_CONTRACT.md, ENDPOINT_WEIGHTS.md, PRE_ACTIVATION_CHECKLIST.md, FIRST_BOUNDED_SCAN_RUNBOOK.md, PROPOSED_PUBLIC_OPERATING_SCOPE.json, collector.py, admission.py, routes.py, session.py, source.py, transport.py, live.py, decision.py and tests. Read B2 strategy/risk/episode/journal contracts and B1 TLS/budget implementation. Read current docs/engineering Project Home, Roadmap, Three-Layer API Architecture, Endpoint Matrix, Model Routing Policy and active role matrix.

Do not change accepted B1/B2/B3/B4 wheels, original tests, source journals, baseline Program J, R1/Astra or Controller decisions. If B4's fake-only constructors prevent reuse, implement an isolated B5-specific physical ledger/reader interface that composes shared pure B4/B2 functions without mutating or monkeypatching accepted wheels. Document the exact duplicated validations and prove they do not weaken admission. New source, tests, fixtures and evidence only in the B5 work root. Track exact execution-interface model ID and thinking effort; never infer from model branding.

## 2. Real production HTTPS binding, initially disabled

Produce one independently installable namespace, e.g. quant_personal_live_public_b5, with hash-pinned accepted B1+B2+B4 wheel dependencies. No B3, private signer, real API key or legacy trading imports. Genuine physical access must NOT be enabled by a CLI flag, environment variable, arbitrary JSON, synthetic receipt, wheel mixing or fixture-origin relabel.

Implement a narrow official-host HTTPS adapter with:
- Exact host https://fapi.binance.com:443, pinned HTTPS authority and SNI; validated system certificate chain, hostname and TLS 1.2+, bounded connect/read/overall timeouts and response body/framing limits.
- No alternate host, redirect, IP literal, custom insecure CA, user-provided arbitrary URL, proxy/regional bypass, TLS verification disable, HTTP downgrade or private authentication header.
- DNS and connected peer verification bound to the approved egress identity; no silent failover or origin change. A known restricted jurisdiction/route or HTTP 403/451/WAF must hard-stop, not trigger bypass.
- Transport boundary enforces exact signed-free GET method/path/parameter allowlist immediately before physical dispatch, even after higher-layer validation.
- Explicit disabled default. A local activation gate must bind the Controller-reviewed release digest, Owner-approved local scope digest, actual region/route, expiry, one-run identifier, request/weight limits and durable consumed/revoked state. A fabricated config, forged approval label or stale approval must fail BEFORE DNS/egress and budget mutation. Do not falsely claim this local control is tamper-proof against an administrator with full machine access; document the trust model.
- No worker self-issued activation credentials, signing keys or approval tokens. If the active release requires a separately provisioned Controller trust root, Stage A must still ship with no usable production activation token and all live paths dormant. Do not create or distribute real signing secrets.

Allowed 10 public unsigned GET routes ONLY:
GET /fapi/v1/time
GET /fapi/v1/exchangeInfo
GET /fapi/v1/klines
GET /fapi/v1/ticker/24hr
GET /fapi/v1/ticker/bookTicker
GET /fapi/v1/depth
GET /fapi/v1/openInterest
GET /futures/data/openInterestHist
GET /fapi/v1/fundingRate
GET /fapi/v1/premiumIndex

Initial universe BTCUSDT, ETHUSDT, SOLUSDT, and five frames 1d,4h,1h,15m,5m. No scope widening, no private/TRADE routes, no websocket and no execution. Inspect the current official Binance USDⓈ-M REST specification and changelog as of implementation; do not use Spot or COIN-M semantics as substitutes. Store official documentation URLs, review dates, contract uncertainties, headers and a versioned endpoint matrix.

FundingRate has a separately documented shared 500 requests/5min/IP bucket, but its exact numeric IP weight is not separately explicit in the referenced official catalog. B4's synthetic reserve of 1 is an assumption, not proven actual cost; reconcile conservatively and record any unresolved uncertainty as an activation blocker. The USDⓈ-M bookTicker docs warn that the X-MBX-USED-WEIGHT-1M header may be inaccurate for this route; do not treat it as trustworthy budget evidence. Also handle OI history omissions and its 1-month retention.

## 3. Durable egress/venue budgets and denial recovery

Reuse the accepted B1/B4 durable SQLite budget algorithms where possible while keeping separate B5 identities and public data stores. Before ANY physical call: verify valid activation, exact GET scope, physical route, TLS constraints, persisted global stop, request/weight reservation and an enforced one-run ceiling.

The B4 scope candidate proposes initial bootstrap 39 requests/42 reserved units for BTC/ETH/SOL and 48 requests/64 units hard maximum per scan including retries. These are candidates, not production facts or automatic approval. Determine the final lower of Owner-approved local ceilings and documented/current venue limits; do not silently loosen them. Separate first bootstrap and optional later +5/+10-minute refresh budgets, each explicitly included in the future approval envelope. No auto-retry of rejected/forbidden methods.

Persist and honor across crashes and process restarts: 429 Retry-After/rate holds, 418 ban, 403/451/regional/WAF sticky denial, reserved debits, unknown dispatch outcomes, one-shot activation consumption/revocation and global halt. Never clear bans by restart or change of IP/host. Do not assume all programs behind a shared NAT IP use the same budget; require headroom or stop on questionable cumulative headers. Treat 5xx/408 with bounded idempotent GET-only retry charged again; preserve uncertainty and original raw errors. Do not spin on rate denials.

Use venue time bracketed by /time witnesses and local monotonic checks. WSL wall-clock discontinuity or wide offset must yield CLOCK_BLOCKED; do not relax finality or backdate source publication to force a card.

## 4. Genuine-origin ledger, source admission and B2 decision cards

Build B5_PUBLIC_GENUINE_RECEIPT_V1 and B5_PUBLIC_GENUINE_PUBLICATION_V1 (or clearly versioned equivalents) in an independent append-only public ledger. All genuine-origin receipt constructors must be internal to the verified physical transport path and bind requested URL, exact method and params, canonical host/SNI, TLS/certificate proof, resolved/connected peer identity, request-start, receipt, raw bytes/hash, response headers/weight, source venue event/close time, durable publication and evaluation as-of. No external caller-supplied "GENUINE" label or QA replay may be promoted. Explicitly state local log integrity is not third-party attestation.

Reuse B4's causal 32 closed-candle warmup and bounded incremental overlap, five timeframes and as-of availability. Validate exchangeInfo filters, closed 15m independent confirmation, gap-free finality, 1H Signal K freeze, 4H regime/1D barrier, 5m actionability; do not allow later revisions/backfills or fast context to affect an earlier decision. OI/funding/mark/depth/bookTicker must be semantically consistent, fresh and asset-symbol bound. Preserve first eligible availability, unknown exchange publication, source revision chain and immutable earlier decisions.

Connect verified genuine-source Market objects to accepted unchanged B2 strategy, Decimal risk math, episode state and append-only human journal via a B5-owned adapter. Do not fake B4 QA evidence as genuine, rewrite B2 source rows or import B3 account data. Card states must separate source readiness from genuine market setup: SOURCE_BLOCKED / NOT_EVALUATED / NO_SETUP / WATCH / INVALID / EXECUTABLE. Only genuine physical-source receipts may carry a marked PERSONAL_PUBLIC_MARKET_GENUINE evidence class. Even a genuine EXECUTABLE card is MARKET_SIDE only, not permission or evidence to open a position. Always include entry range, hard SL, TP1/TP2/TP3 when supported, after-fee/slippage/funding net R, first 4H/1D opposing barrier, spread/depth and OI provenance, no-chase, expiry and +5/+10 reprice when explicitly allowed. Account remains UNAVAILABLE; safe_position_size UNKNOWN; no automatic trade or Feishu.

A genuine scan that results only in NO_SETUP, WATCH or SOURCE_BLOCKED is a valid, reportable outcome. Never insert a synthetic profitable card to satisfy acceptance.

## 5. Two-stage operation under the same task ID

PHASE A — OFFLINE / IMMEDIATE:
- Build B5 package, official-host physical transport, activation gate and real-shaped receipt/adapter in its dormant state.
- Run all tests under network namespace with no external route. Real TLS regression uses local loopback test server, including forged CA, wrong SAN/SNI, DNS rebinding simulations, HTTP redirect/downgrade, IP mismatch, oversized/truncated responses, stale/inconsistent venue clock, synthetic-to-genuine forgery, double activation, crash and denial restart.
- Verify both production CLI and module imports fail closed without legitimate activation before any socket/DNS. Prove no user secrets/private APIs imported or inspected.
- Exercise all ten routes with offline contract fixtures and cross-check exact B4/B2 interface output. Rebuild two setup families × both directions, replay original market cards and independently recompute Decimal net R. Preserve all inherited seals.
- Prepare a completed-as-possible local Owner scope candidate, a future exact activation envelope, first real scan dry-run request list/weight forecast and a one-page Owner decision sheet. Do not invent actual egress country/IP/route, actual retention preference, or approved filesystem locations. No repeat requests for identity documents, standing attestation or SHA256 approvals.
- Return READY_FOR_ACTIVATION_REVIEW with wheel, source contract, QA, route/weight uncertainty, sealed hashes, dry-run and all remaining exact Owner fields. DO NOT run live scan.

GATE A — EXTERNAL CAPABILITY CHECK:
The Owner explicitly approves the actual local operating region/egress route, evidence/ledger paths, retention and one-shot limits for the first genuine scan; Controller 0-C independently reviews the exact B5 wheel/source, Owner scope, binding provenance, current Binance docs and denial logic, and records the precise activation. This is a permission boundary, not a new engineering project. The Owner can reject or defer activation without invalidating completed Phase A.

PHASE B — ONLY AFTER RECORDED OWNER + CONTROLLER ACTIVATION:
- Execute exactly one operator-visible bounded genuine-public run on the preapproved host and route. Begin with /time plus /exchangeInfo as a canary within the same approved request budget; stop immediately on region, WAF, TLS, clock or rate denial; do not switch proxy/region/host.
- If allowed and feasible under remaining scope, bootstrap 32 completed bars across five frames for BTC/ETH/SOL and collect the permitted remaining quote/depth/mark/OI/funding sources, recording request weights/headers and any uncertainty. Never exceed the approved one-run cap or silently turn a canary into a general crawl.
- If the activation also expressly permits refreshes, use separately bounded +5/+10-minute samples for actionability and immutable reprice. No implicit daemon/recurrence.
- Inspect the produced genuine receipts, source availability, bars and B2 market-card provenance. When evidence is insufficient or contradicts the accepted model, mark SOURCE_BLOCKED/NOT_EVALUATED and preserve the reason. Do not claim an execution-ready signal without all hard gates.
- Record the local audit trail, symbol outcomes, accepted/rejected source schema, observed weight headers, clock residuals, stop/cooldown, card states and incident handling. Mask local egress identifiers and sensitive operating details from public handoffs; raw evidence stays Owner-local.
- Submit one final READY_FOR_CONTROLLER_REVIEW handoff for independent B5 acceptance. No further live run without a new explicit scope decision.

## 6. Engineering deliverables and test acceptance

Keep all new files under workspaces/lt-v080-personal-mvp-live-public-b5-01/. Build one standalone installable B5 wheel pinned to B1/B2/B4 wheels, without embedding accepted modules. Provide local CLI: inspect/readiness/dry-run/preflight/live-once (activation gated)/card/replay; no background schedules. Include:
- B5_SOURCE_AND_ACTIVATION_CONTRACT.md, B5_ENDPOINT_AND_WEIGHT_MATRIX.md, B5_QA_REPORT.md and B5_RUNBOOK.md.
- OWNER_B5_FIRST_SCAN_DECISION_SHEET.md and local proposed scope JSON, both **NOT_AUTHORIZED** until separately reviewed.
- Deterministic offline fixture and malicious activation/real-origin forgery suite, TLS/route tests, restart-safe durable ledger/one-shot tests, clock and provenance tests, installed CLI/mixed install and B1/B2/B4 targeted regression.
- One sealed SHA256SUMS covering every final file, including source/tests/fixture/log/wheel/pinned dependency and handoff docs; no symlinks, path escape, missing entries or self-reference.
- WORKER_RESULT.md and CONTROLLER_HANDOFF.md, with actual executor label, reasoning, code/doc baseline, exact PASS/FAIL/SKIP, hashes, known gaps and activation status.

If only Phase A is authorized, handoff status is READY_FOR_ACTIVATION_REVIEW, and maximum Controller decision is SCOPED_ACCEPTED_OFFLINE_PHYSICAL_BINDING_READY. Never claim real market activated. If Phase B is separately authorized and completed, handoff status is READY_FOR_CONTROLLER_REVIEW; the Controller may accept only the exact genuine scan and evidence actually observed, not indefinite live permission or trading performance.

Stop for material architecture mismatch, unapproved route, need for a trade/private endpoint, unverifiable physical identity, source forgery, unresolved rate limit that makes the approved budget unsafe, broken upstream seal, shared writer conflict or evidence corruption. An abnormal stop with zero or partial requests is a valid result; never conceal it or use alternate network paths.

End of task.