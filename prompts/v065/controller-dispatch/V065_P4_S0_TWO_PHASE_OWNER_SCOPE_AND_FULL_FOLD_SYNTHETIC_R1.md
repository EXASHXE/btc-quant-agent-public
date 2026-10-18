# quant v0.6.5 — P4-S0 executable scope handshake and full-fold synthetic verification

You are the direct engineering implementer already running in the current agent session. Continue immediately with actual code and tests; no need to relaunch an agent, choose a model, create a schedule, or write a lengthy plan.

Working repo: /root/workspace/project/quant-0.6.5, current branch v0.6.5, previously verified HEAD 12b74b4c2fd3a22a9f4b35dbf331cfb1166aae77. Verify HEAD and dirty status before edits. All Owner R4 docs, existing dirty D2, P0/P1/P2 and data acquisition code must be preserved. No stash, reset, checkout, clean, commit, push, production services, downloads, original Quant-agent or protected OOS access.

Facts independently checked by Controller:
- P1 cost-aware X vs X+Z evaluation, P2 cross-venue bridge, P3 source bridge and P3-R3 adapter exist. P3-R3 acceptance receipt: /tmp/v065-p3-r3-acceptance-pz801jjw/acceptance_receipt.json.
- New Controller scoped P3+P1 pytest: 217 passed, exit 0. P3-R3 runs only a 120-hour synthetic bridge, explicitly says FULL_FOLD_SYNTHETIC_NOT_RUN, and reads zero real historical outcome labels.
- Existing P1 84-day synthetic demo may already run 3 outer folds; REUSE it if appropriate and demonstrate *P3-to-P1* complete full-fold integration rather than duplicating P1 code.
- P3_ACCESS_SCOPE_HOLD remains. The private A-line / Final / Forward protected date overlaps are unresolved, Owner v2 template is UNSIGNED, and real X/XZ historical returns have not been authorized. Do not read or calculate them.
- Bounded BTC Mechanism A candidate source envelope [2026-03-31T16:00Z, 2026-09-01T00:00Z) with 632 pinned archive objects, initial hourly origins [2026-04-03T00:00Z, 2026-09-01T00:00Z). For 24h horizon final allowed origin is 2026-08-30T23:01Z. No September historical result access. Q2 June Binance BTC markPriceKlines has 1440-minute gap despite PASS and OKX Aug 26 ALL_SWAPS funding has 3 aggregate gaps; missing Q2 April OKX L2 is not needed for position-state mechanism.

## Primary engineering defect — output SHA circular dependency

Current P3 archive_adapter.materialize_authorized() invokes authorization.authorize_dual_gate(). That requires a preexisting Owner v2 scope with a pinned exact normalized output panel SHA and exact P1 allowlist SHA, and an existing P1 allowlist with this same panel SHA, all BEFORE ANY label read. But the normalized panel SHA depends on the not-yet-generated true archive-derived outcome panel. Thus this contract cannot be satisfied for a new real dataset without either prematurely reading results or inventing an output hash.

Implement an executable two-phase Owner-permission versus derived-panel-integrity protocol, preserving fail-closed behavior and explaining any contract change:
- Phase 0: unsigned or private-dates-unknown always denies real outcome reads.
- Phase 1: after a FUTURE valid preexisting Owner-signed EXPOSED_DEV v2 scope explicitly permitting outcome PANEL MATERIALIZATION (not OOS or trading), verify private date attestations, market/file hashes, original manifest stability, frozen origin and maturation bounds. THEN and ONLY THEN may an authorized future run stream real source outcomes into a fresh confined staging panel, without demanding its unknowable output hash beforehand. This task itself has no authorization, so do NOT run the phase on real data.
- Phase 2: after stable panel completion, calculate exact derived panel SHA and deterministic P1 allowlist with panel path/start/end/SHA. This derived allowlist is an integrity binding, NOT an Owner signature or independent authorization. Existing P1 authorized_panel must recheck it before any evaluation. Handle partial failure/changed inputs/hash mismatch cleanly with quarantine and no publish.
- If an existing authoritative contract expressly requires two INDEPENDENT approvals BEFORE any outcome label read, DO NOT bypass. Return P4_S0_AUTHORITY_CONTRACT_DECISION_REQUIRED, cite the exact invariant and propose workable alternatives. No fabricated permission or implicit owner signature. Existing permission boundary cannot be weakened silently.
- Add negative tests for UNSIGNED scope, unknown private dates, missing attestation, wrong contract/market/symbol, forged SHA, symlink/path aliases, archive/date intersection with H39, 24h exit beyond right edge, incomplete mark/funding, interrupted staging and post-stage tampering.

## Secondary engineering goal — full 84+ day end-to-end synthetic folds

Produce a synthetic-only deterministic P3 panel fixture of at least 84 days hourly (2016+ origins), with explicit fixed 24h warmup or NO_ACTION, missing Z, 4/8/12/24h outcome maturation and sparse-missing label keys. Avoid large minute-level fixtures under low RAM; test native minute parsing separately with small synthetic ZIPs. Never use real 2026 market outcomes.
- Through actual P1 code, execute frozen chronological outer development endpoints 42/56/70 days and their following 14-day validation, inner seven-day tuning, 24h purge and 1h embargo.
- Verify folds genuinely execute rather than remaining empty/INSUFFICIENT_HISTORY; if impossible because the frozen P1 protocol lacks valid inner-training history or support, record concrete per-fold reason, DO NOT change the frozen protocol to force a green outcome.
- Keep 8h primary, 4/12/24h secondary, same eligible X/XZ population, original 16bp and 32bp assumed costs, funding direction, overlapping capital sleeves, no-action denominator, stable hashes. All results carry TEST_ONLY_SYNTHETIC and NO_ALPHA_ESTABLISHED.
- Record actual execution time and memory where available, but never run whole-repo CI or large archive decompression. The host has ~1.9GiB RAM and ~5GiB swap.

Code ownership: prefer edits only to scripts/research/exposed_dev_bridge and tests/research/exposed_dev_bridge. P1 math files read-only unless you reproduce an exact defect and write a regression test. Write outputs exclusively to new isolated /tmp directories and preserve all original raw historical data.

## Verification and terminal

Provide runnable one-command CLI for synthetic full folds, actual targeted pytest (P3 and P1 critical tests), deterministic fold_summary.json, provenance, derived P1 integrity allowlist demo, per-origin NO_ACTION/eligibility, pairwise X versus XZ cost-sensitive result, actual exit codes and file hashes. Negative no-scope real archive path must read ZERO outcome rows. Do not publish false scientific wins from synthetic examples.

Return either P4_S0_SYNTHETIC_FULLFOLD_AND_TWO_PHASE_READY (3 executed synthetic outer folds + executable future Owner-permission route), P4_S0_PARTIAL (concrete unmet fold/adapter check), or P4_S0_AUTHORITY_CONTRACT_DECISION_REQUIRED (non-negotiable frozen pre-label dual authority). Report exact changed paths, tests, real label reads = 0 and smallest remaining Owner authorization decision.

Scientific gates stay HISTORICAL_OFFLINE, SOURCE_NOT_ADMITTED, PIT_UNKNOWN, NO_ALPHA_ESTABLISHED, COST_UNVALIDATED_REAL_FILL, G2_ALPHA_NO_GO, G4_TESTNET_NO_GO, LIVE_NO_GO, REAL_FUNDS_WRITE_NONE.