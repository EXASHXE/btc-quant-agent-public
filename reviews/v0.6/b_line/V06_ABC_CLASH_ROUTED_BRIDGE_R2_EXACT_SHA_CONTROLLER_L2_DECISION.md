# quant-agent v0.6 B-line Controller — R2 Clash-routed A/B/C bridge exact-SHA L2 decision

Review date: 2026-10-12 (Asia/Shanghai). Owner: ChatGPT-0 B-line Primary Controller. Authority SHA `acf59828f878f3b1cc56e257dd952a8cd2c9ea97`, prompt SHA `e3c4fffe124d52fba26bbd16cf0c6626fe7809cb`. Repo `EXASHXE/btc-quant-agent-public`. All conclusions are bounded to exact remote evidence; Controller did not run local proprietary/heldout data or independently reproduce a live public session.

**L2 TERMINAL: `R2_PUBLIC_ROUTE_PARTIAL_SMOKE_OBSERVED__SYNTHETIC_ADAPTER_EVIDENCE_BOUNDED__CI_AND_PIT_GATES_FAIL`**.

## 1. Remote identity, scope and actual CI

R2 branch `feature/v06-bline-gemini-abc-clash-routed-feed-bridge-r2`, authorized base `df00997f344eba82f7cca0d03ee1617948abee44`, **final HEAD `632d2e37f28b8c3efbd2b818ecdb74783f0df238`**. Compare: ahead 6, behind 0, linear exact parent chain:
1. `0a105c429ddf505ca3b819556510163121d3c282` Stage0 docs/method;
2. `9189ac321bb45198030a527e00e8c25dc82e3e73` Stage1 Binance routes / public proxy;
3. `6a4c756966733d2aca3ead50eb6c41c05c44fa28` Stage2 adapters;
4. `2d8cd7cbe116e155ad16b2f3b438362bd69e5b15` Stage3 tests;
5. `b86843bb11a10e0a3a293d4d918671c6c41d08fa` Stage4 report;
6. `632d2e37f28b8c3efbd2b818ecdb74783f0df238` Stage5 SOCKS5h/proxy and adapter code changes + evidence.

All files within authorized R2 or named A proxy/connector/CLI/test scope. B `51cdd4e17503fbd18ad22aaeeaba3580f5efacf8`, C `91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b`, G1 `861a9d148f72db00e6079e53af78220bdd7e84ce` not changed. No cross-branch merge.

**Final GitHub Actions [run 38252226915](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38252226915): FAILURE.** Ruff, compile, changed-JSON and typecheck succeeded. Full test invocation `pytest -q --durations=20 --junitxml=ci-junit.xml` fails in **collection** with five `PermissionError: [Errno 13]` on hard-coded development worktree paths `/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1` and `...gemini-forward-shadow-research-r1`. Affected tests:
- `tests/test_v06_market_event_bridge_r2_c_composite_g1.py`
- `tests/test_v06_market_event_bridge_r2_depth_ladder_l2.py`
- `tests/test_v06_market_event_bridge_r2_pit_clock_mark_last.py`
- `tests/test_v06_market_event_bridge_r2_settled_funding_ledger.py`
- `tests/test_v06_market_event_bridge_r2_stress_and_security.py`.

Some tests import pinned B/C via optional absolute path + global `sys.path`; this is NOT a hermetic exact-commit adapter verification. Final manifest **claims** 145 newly passed + 148 A passed = 293 local (Python3.12.3), but at latest remote exact SHA no successful CI test execution; the preceding green [run 38245666888](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38245666888) was **docs-only**, tests SKIPPED. Last code commit changes bridge_engine, mark_aggregator, funding_adapter, book_ladder, proxy_route, tests and evidence. The self-described immutable test receipt still refers to **Stage3 SHA `2d8cd7...`**, not final `632d2e...`; cannot attest latest code.

## 2. Public data and Clash evidence — valuable but insufficiently qualified

[Real-source local diagnostic](https://github.com/EXASHXE/btc-quant-agent-public/blob/632d2e37f28b8c3efbd2b818ecdb74783f0df238/evidence/v0.6/b_line/market_event_bridge_r2/NETWORK_ROUTE_DIAGNOSTIC.json) reports WSL2 and an explicitly configured local HTTP Clash/Mihomo proxy. Layers: proxy TCP SUCCESS, HTTP CONNECT SUCCESS, official Binance REST TLS GET 200, official routed `/public/stream` WebSocket upgrade and one depth frame SUCCESS. Additional terminal local receipt claims **15-second** public smoke with 261 counted events (140 depth/snapshot, 121 combined market/funding). This is more than mere open TCP port; **public connection is observed**.

But there is **no trustworthy per-channel close/continuity proof** that the smoke included >=2 *closed* Last 1m candles, >=120s Mark stream, verified aggTrade counts and continuous, noncrossed post-REST U/u/pu depth through the whole interval. Source-level smoke implementation in `scripts/market_data/forward_public_feed_r1/connector.py` lines ~430–438 sets `PUBLIC_SMOKE_VERIFIED` whenever `events_received>0`. Importantly, REST snapshot alone increments events_received; even if both WSS connections fail, the function may still label the session verified, while exceptions in each WS task set only an error field. Therefore **report's `PUBLIC_SOURCE_VERIFIED` is overstated**. Accept **`PUBLIC_ROUTE_CONNECTIVITY_OBSERVED__MARKET_SOURCE_CONTINUITY_UNVERIFIED`**, not readiness to collect exchange-credible scientific evidence. No proof 24h continuous run, no broker L2 queue or actual cash realization.

The public branch includes a `NETWORK_ROUTE_DIAGNOSTIC.json` with ambient proxy environment host:port strings, `NO_PROXY` details, and a LAN gateway address, contrary to original redaction goal. This is **potential network configuration exposure in a public repository** even without secrets. Do not echo values into further published reports. Future diagnostics must contain only `proxy_configured`, `route_kind`, `loopback_or_host`, redacted user-controlled text and a nonreversible local-only route receipt ID. Never commit authorization headers/node names, IPs or connection credentials. Existing history remains publicly readable unless user separately authorizes history rewrite; don't secretly rewrite it.

## 3. Structural A/B/C adapters: valuable bounded development, with a concrete PIT violation

Synthetic report: 1812 generated frames, 10 derived Mark minutes, 601 top-10 ladders, 1 settled Funding ledger event, 10 composite C BARs; independently asserted through executor evidence only. B Mark tick≠Kline, A book receipt≠ladder, REST Funding≠B T/r/p and C raw Kline≠composite BAR are now mapped under new adapter source. This is **synthetic engineering evidence**, not independently CI-confirmed end-to-end admission.

**Concrete L2 BLOCKER: C funding envelope backdates receiver-known-at to settlement time.** In final `scripts/integration/market_event_bridge_r2/bridge_engine.py` approx lines 325–344, after constructing `SettledFundingEntry`, the **B** envelope correctly records `observed_wall_utc_ms = observed_wall_utc_ms` and `available_at_ms = observed_wall_utc_ms`. The **C** envelope instead sets **both** `observed_wall_utc_ms = entry.funding_time_ms` and `available_at_ms = entry.funding_time_ms`. This violates receiver-known-at/PIT when official funding is delivered AFTER settlement (which normally happens), yet appears temporally valid to C. The committed journal itself records source observed later than funding time, so this is an actual cross-interface contradiction, not a theoretical quibble. **NO ACCEPTANCE of signed funding PIT/financial integration until code and negative tests are repaired**, with no modification to original B/C/G1.

Additional potential issue to test explicitly: `self.last_mark_tick_price` is retained as a float without corresponding ingress time, freshness/quality/epoch or mark SHA in the funding branch; this allows arbitrary stale/unverified Mark binding to an otherwise settled official funding record. Require a provenance-aware contemporaneous Mark witness and reject `COST_COMPLETE` if missing; do not default cash to 0 or use an unverified old mark. Mark-derived 1m bars must remain labeled synthetic derivative, not official Mark Klines; Top10 ladders are synthetic not real queue fills.

The bundle has code implementing correct 2026 `/public/stream` vs `/market/stream` separation and explicit proxy REST+WS route; this remains usable as engineering input. **No Alpha, no successful independent SCIENTIFIC preregistration of B, no confirmed G3 live LLM/Feishu, no G4 TESTNET/LIVE or real funds.**

## 4. Scope-limited repair gate

The next high-value work is ONE **bounded R3 engineering fix** on new exact-SHA branch based R2 head (not another strategy discovery):
1. Eliminate all hardcoded machine-relative imports and make pinned exact B/C checkouts/fixtures accessible hermetically in CI; require explicit non-SKIPPED full/focused tests at final HEAD. Avoid editing `.github` or protected paths.
2. Correct C funding arrival clock, add rate and mark-pit provenance negative tests, deliver independent Decimal signed long/short journal evidence.
3. Enforce multi-channel smoke acceptance (closed Last, Mark time coverage, trade, depth continuity and route-epoch) with genuine public read-only source observations or explicit `PUBLIC_SOURCE_PARTIAL`.
4. Redact public repo network configuration reports and publish **new append-only** evidence, preserving original R2 receipts as evidence of earlier claims.
5. Publish correct final source+test SHA manifests/CI job step and Controller second L2. No TESTNET, PRIVATE, PROTECTED, old holdout or real trading.

A-line and Performance untouched; G1 offline bounded acceptance unchanged; G2 validated Alpha NO; G3 real provider connections NO; G4 real trades NO-GO.
