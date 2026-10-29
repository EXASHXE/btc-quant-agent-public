# V070-L12-OFFLINE-MULTISTRATEGY-ADVISORY-01

ROLE: Codex — Principal Quant Advisory Engineer and Autonomous Phase Executor.
CONTROLLER: Quant v0.7.0 Controller 0-C.
AUTHORITY: Owner-authorized isolated engineering, offline synthetic fixtures and tests only.
EXECUTION: ONE long-running L1+L2 mandate; self-plan, implement, test, fix and report once at the phase boundary. Do not request micro-approvals.
DISPATCH GATE: Current platform-build and Astra research Codex sessions were observed inProgress at 2026-10-29 10:03 Asia/Shanghai. Do NOT start a duplicate worker while overlapping ownership is unresolved. If dispatched to an existing owner session, first confirm its current objective; otherwise wait until the prior build has finished. The Owner's development authorization does not waive concurrency checks.

SOURCE OF TRUTH
1. Read latest EXASHXE/btc-quant-agent-public docs/engineering HEAD: AGENTS.md, policy, mission, roles, roadmap, handoff and this card.
2. Start from /root/workspace/project/quant-0.7.0/multi-strategy-platform-01. Verify FINAL_DELIVERY.md, IMPLEMENTATION_PROGRESS.md, artifacts/acceptance.json, source fingerprint, catalogs, comparison.json, tests, config and source-copy/preservation receipts.
3. Status at handoff: isolated WORKING_BASELINE, SYNTHETIC only, 69 factors, 21 directional plus 7 research portfolio strategies, 158/158 new platform tests, 250/250 affected regressions, 175 passed/3 failed unchanged legacy contract tests, nine demos. Three SYNTHETIC_VALIDATED mechanisms, 25 IMPLEMENTED_UNTESTED. Treat all as evidence to recheck, not a guarantee.
4. R=/root/workspace/project/quant-0.7.0/research-loop-bootstrap; M=/root/workspace/project/Quant-agent-market-watch; Q=/root/workspace/project/Quant-agent. Preserve their exact original dirty work, indexes, HEADs and running collectors. Never replace with clean HEAD or operate in them.

MISSION
Deliver a runnable, failure-injected OFFLINE vertical slice proving authentic-source-contract boundary plus a full multi-strategy, user-reported-position advisory lifecycle. Preserve the existing 69/21/7 platform; do not rebuild architecture or claim market Alpha. Real API/live source activation is OUT OF SCOPE.

WORKSPACE AND METHOD
- Create exactly one new isolated, non-Git task directory under /root/workspace/project/quant-0.7.0/, named l12-offline-multistrategy-advisory-01, after confirming no competing worker owns it.
- Copy only allowlisted source/config/tests/docs and fake test inputs from the platform baseline. Exclude .git, credentials, raw/forward market payloads, runtime DBs, private accounts, caches and large models. Record source hashes and baseline test counts.
- Decompose internal work into short implementation checkpoints but do not create repetitive Owner approvals, standalone review chains or multiple successor agents. Run unit/integration/fault tests and repair defects autonomously within the approved scope.
- Retain and transparently reconcile the three unchanged legacy conflicts:
  test_gated_data_never_attempts_notification;
  test_r2_01_two_run_scanner_breakout_persist_to_retest_triggered;
  test_mocked_provider_market_watch_to_durable_approval.
  Preserve original failure bytes/counts and tests. Add explicit corrected-contract fixtures and tests. Never weaken ACTION fail-closed or suppress useful WATCH/RISK. No arbitrary xfail/skip.

INTERNAL PHASE A — L1 SOURCE ADMISSION AND CONTRACT
- Extend existing platform.DataProvider / PayloadAdapter, do not replace them. Build provider-neutral canonical envelopes for completed candles, native bid/ask quotes, instrument filters, spot/perp references, optional OI, funding, taker flow and provenance. Use fabricated offline Binance/OKX-shaped fixtures; DO NOT call Binance/OKX or read archived payloads.
- Separate exchange event/publish, receiver-known, available, decision, local commit, notification and manual-action clocks. Missing receiver provenance stays UNKNOWN. Never construct an authorized receive clock by simply trusting caller-supplied timestamps.
- Handle out-of-order events, duplicate keys, delayed/wrong-symbol responses, interval mismatch, missing derivatives, benchmark future leakage, quote expiry, tick/step precision and delisted/spec-change cases.
- Provide explicit source-health and admission reason codes, availability coverage report, and deterministic typed snapshots. Unverified/replayed caller payloads may drive offline WATCH/testing but MUST NOT acquire real-market ACTION authority.
- Preserve current platform safety gate. The current code explicitly blocks non-synthetic source ACTION; do not silently remove this barrier or introduce an enabled live provider. If an externally admitted live source needs a design, provide an interface-only adapter and an explicit separately-authorized activation gate.

INTERNAL PHASE B — L2 FULL ADVISORY WALKTHROUGH
- Reuse factor cache/regime/strategy resolution and selected three representative strategies: trend_breakout, bollinger_reversion and shock_reversal. Other 25 remain IMPLEMENTED_UNTESTED unless independently and comprehensively tested.
- Demonstrate universe scan, factor/regime choice, ranking distinct from readiness, WATCH -> ARMED -> ENTRY_ELIGIBLE or CANCEL/EXPIRE, exact symbol/LONG-SHORT/confirmation/tick-aware entry band/max price/structural invalidation/mandatory stop and valid target-or-open-trail policy.
- Include explicit fee, spread, slippage, funding UNKNOWN, worst-entry risk/quantity/exposure/correlation and market-liquidity vetoes. Ranking scores are not win probabilities.
- Model event-to-receive-to-decision-to-commit-to-delivery-to-manual-submission-to-fill. Human reaction scenarios: 1, 3 (primary), 5 min AFTER notification delivery; separate 10–15 min total-delay stress. If delivery is unobserved, retain UNKNOWN; do not assume instant fill. Expired/lost-entry plans must not remain actionable.
- Reuse a versioned user-reported position ledger: a proposal is NOT a fill. Explicit USER_REPORTED vs SIMULATED vs EXCHANGE_VERIFIED (none assumed). Include manual partials, changed stops, stop-cross/gap, stale observations, correlated exposure and risk-first HOLD/TIGHTEN_STOP/PARTIAL_EXIT/REDUCE/EXIT/RECONCILE suggestions. Suggestions NEVER change an actual position without explicit user report.
- Reuse Foundation immutable identity/persist-before-notify outbox: preview/no-send does not consume dedup; definite no-send retries bounded; ambiguous send/remote delivery UNKNOWN does not auto-resend; restart and concurrent claimants remain safe. Fake sender only.
- Implement a runnable CLI/offline fixture workflow with machine-readable JSON report, short human-readable advisory cards, state transitions and evidence/clock hashes. Support at least a trend, range and shock scenario with replay from a clean temporary DB, plus failure injection. Keep UI minimal; no new dashboard rewrite.

INTERNAL PHASE C — PHASE ACCEPTANCE
- Re-run prior new-platform and inherited targeted regression tests against the copied baseline, report EXACT counts and test hashes. Run contract-replacement tests and selected legacy originals separately; never claim all green while any original remains red.
- Fault matrix: missing/stale quote; quote after decision; wrong-symbol tick/spec; benchmark future dependency; delayed OI; incomplete/duplicate/out-of-order bars; lost region after 1/3/5 minutes; gap through stop; missing funding; unknown user fill; multiple positions; repeated reports; notification crash/UNKNOWN; process restart; dual notification claim.
- Include at least one genuine two-process persistence/restart probe using only fabricated temporary SQLite stores and no network. Validate all newly added tests and the full runnable offline CLI with deterministic identities.
- Produce one phase-level result: ACCEPT / PARTIAL / BLOCKED. Distinguish engineering behavior from source admission, live read permission, and economic validation. No real-time or profitable strategy claims.
- Keep one concise L12_CHECKPOINT.md during implementation and only one complete L12_FINAL_DELIVERY.md at terminal. Include changed-file manifest, source SHA256, typed contracts, actual commands/counts, sample CLI invocation, safety failures, old-contract accounting, hash/preservation receipt, limitations and a specific next major phase suggestion (L3 if ready).

STOP AND AUTHORIZATION GATES
No protected 2024–2025 or FINAL_HOLDOUT reads; no 2026 forward payloads; no live/public exchange data calls or downloads; no account access, trade/order/funds changes; no real notification; no collector/service restart; no R/M/Q integration; no commit/push; no PRIMARY or new economic trial. Existing .venv and packaged test dependencies may be reused without network installations; if absent, report the blocker.
If real transport, real-data statistics, collector operation, production integration or external sends become necessary, finish all independent offline work and mark that subfeature BLOCKED_PENDING_OWNER_AUTH. Do not infer authorization from this task.
No automatic next task, no routine Astra/Opus/Gemini review within the build. 0-C will arrange ONE independent phase audit after consolidated delivery if justified.

DELIVERABLES (all in isolated task directory)
L12_CHECKPOINT.md
L12_FINAL_DELIVERY.md
L12_SOURCE_AND_CLOCK_CONTRACT.md
L12_SYNTHETIC_ACCEPTANCE.json
L12_TEST_AND_LEGACY_ACCOUNTING.json
L12_PRESERVATION_RECEIPT.json
an exact source diff/allowlisted manifest and runnable example CLI configs.
Owner report in Chinese; artifacts and code comments in English.