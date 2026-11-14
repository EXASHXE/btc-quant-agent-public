> **LATEST OWNER ROUTING CORRECTION — 2026-11-14:** Cancel Gemini Orchestrator **for future tasks**. Keep the **already assigned P1C04** exactly as originally scoped (**Argon + Hydrogen within that one current task**)—do not stop, restart, or reissue it. From **P1D onward**, use **Hydrogen for simple bounded engineering**, **Sol for complex engineering**, and **Sol Max only for specialist architecture when needed**. Controller 0-C alone performs independent acceptance. One stage per future handoff. The older Orchestrator references below describe the P1C04 exception only and must not be extrapolated to future phases.

# Quant v0.7.0 — P1C03 Scoped Acceptance and One-Stage-At-A-Time Roadmap

**Owner instruction (2026-11-14):** Only assign ONE next phase at a time. Gemini Orchestrator may coordinate **Argon (architecture/validation) + Hydrogen (bounded code/tests)**. Sol remains core-engineering escalation lead; Sol Max remains complex architecture fallback. No worker dispatch by Controller.

## Controller ruling: P1C03

**`ACCEPT_P1C03_SYNTHETIC_DISPOSABLE_L0_SCOPED`**; local Controller acceptance: `controller-decisions/V070_P1C03_SYNTHETIC_L0_CONTROLLER_ACCEPTANCE_20261114.json`. Original worker `STATUS_P1C03.json` remains a truthful historical `PENDING` handoff.

Controller independently ran complete WSL 3.12 tests: **241 PASS, 2 Windows-only SKIP, 58 subtests PASS, exit 0**. Windows native original worker log: **243 PASS, 0 SKIP, exit 0** (Controller inspected native fixed C: NTFS receipts, not a second independent Windows native full run). Original worker Windows/WSL synthetic E2E logs both exit 0.

Controller independent ad-hoc probes: day-1 tick permitted; at **86,400,000 ms exactly** replay rejected; purge only newly enrolled disposable raw yielded `PURGED_TOMBSTONED`; cold restart showed `RECOVERY_RETENTION_EXPIRED`, `can_replay=false`, metadata continuity preserved; same cycle retry `REJECTED_RAW_EXPIRED`; identical raw restoration `RESURRECTION_DETECTED` and replay denied. Controller independently checked **995/995** inherited P1C02 file SHA256 identical to original; frozen Q0A5 **287/287** and P1A **308/308**.

Detached source modules:
- `win_capture/p1c03_retention_index.py` SHA256 `390d31d65c421328235e7cadd0f7482a13f5baedae274b98d8698edbd672ad28`
- `win_capture/p1c03_purge_simulator.py` SHA256 `d1a3f538ee47f85c03f8fedf3fee344997a9f44a383bb5493115bf3fedf061d9`
- `win_capture/p1c03_retention_recovery.py` SHA256 `1d6af526918d29ffd58c8a2981e578e5d10dadc7698634a2a9490b9819a0d6d8`

**Accepted only in detached synthetic fixture scope.** Not a live P1C02 retention integration, not a 24h independently authenticated UTC guarantee, and not secure physical erasure. Independent high-water witness survives is assumed. If the witness commits before SQLite and then SQLite fails, the stored image may be conservatively fenced; recovery availability is not guaranteed. No arbitrary privileged writer/power-loss guarantee. P1C02 SQLite WAL engine remains `SQLITE_WAL_ENGINE_NOT_QUALIFIED` (Windows 3.50.4, WSL 3.45.1, unknown fix provenance). No accepted evidence was purged and no real external API/Feishu invoked.

## Stage map — only next task is assigned

| Stage | Objective | Recommended lead | Entry/exit gate |
|---|---|---|---|
| **P1C04 — NEXT** | Disabled-by-default local TLS/loopback, strictly synthetic Source→E1→Shadow/Producer-owned mock Outbox, correct blocked/NO_SETUP counts and recovery | **Gemini Orchestrator: Argon lead & review / Hydrogen bounded implementation** | New isolated checkout, no real egress, full Windows/WSL regression, independent Controller acceptance |
| **P1D — LATER** | Portable/fixed SQLite WAL provenance, independent UTC time trust, Source access/rights/budget readiness and restart durability constraints | Sol engineering + Sol Max architecture; Hydrogen QA optional | Verified runtime & clock evidence; no live authority until separate grants |
| **P2 — LATER** | Finite 3-symbol BTC/ETH/SOL public read-only Source diagnostic under separate Owner envelope; diagnostic cannot mint qualified current Source when UTC/rights unqualified | Sol | 24 GET/40 weight/120s or narrower approved scope; raw and manifest evidence; Controller approval |
| **P3 — LATER** | Qualified current Source Shadow, human Feishu canary, 5–10min human actionability recheck, 2–12h decision support | Sol; Gemini QA | Separate Feishu grant, fresh quote/OI/depth/funding evidence, dedup and acknowledgement |
| **P4 — LATER** | >=10 liquid symbols, factor registry 69 baseline / 21 strategies / 7 portfolios, prospective V3.8 evaluation and observability | Sol Max research design; Sol implementation; Gemini test/reports | Qualified 3-symbol MVP before universes or Alpha claims |

**Gemini Orchestrator mechanics for P1C04:** Argon must own bounded design, dependencies, work decomposition and non-author review; Hydrogen may author new isolated adapters/tests/fixtures. Orchestrator may coordinate these two inside *this one task* only. Do not let Argon both author and independent-accept, or automatically dispatch subsequent stages. No changes to frozen modules or protected archives, no real Binance/Feishu, no external DNS/HTTP other than OS-local TLS loopback, no host clock modification. All real Source/Shadow/Alpha/economic/execution/Feishu authority flags remain disabled.

## P1C04 concrete scope

- New isolated workspace based on latest P1C03 synthetic baseline. Add `p1c04_offline_mock_integration.py`, local fake TLS server and exact certificates for test only (never ship private keys as production secrets), deterministic mocked Source clock/5TF/quote payloads.
- Explicit **test-only** activation token, default blocked. Preserve `WindowsHttpsTransport(qa=None)` block and `Q0APublicToE1Bridge.LIVE_ENABLED=False`; no bypass via forged localhost origin. Actual socket destinations restricted and asserted to 127.0.0.1/::1; reject redirects/CONNECT/DNS proxy/external egress.
- Only mock qualified-looking values **inside synthetic fixture namespace**; never set `SOURCE_QUALIFIED=true` or render live `EXECUTABLE`. Preserve E1/Shadow semantics, including scheduled vs blocked vs evaluated NO_SETUP. Mock Producer/Outbox uses accepted single-writer interfaces but never real send.
- Test newly integrated handling: pre/post-retention expiration, quarantined bundle, stale quote, future quote, forming Kline, missing OI/depth, UTC unqualified, sequence rewind, duplicate cycle, crash/ACK retries, mock Feishu failure and idempotent Producer semantics (no actual Feishu sends).
- Owner work distribution: one Orchestrator assignment, Argon design/review, Hydrogen bounded code/test modules. If frozen contracts need changes, STOP with exact controller decision request, do not modify them.
- Controller independent final review before P1D. No task started automatically by this document.

**Authority invariants:** `SOURCE_BLOCKED=true; SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false; REAL_FEISHU_SEND=false; R1.2 disabled`.
