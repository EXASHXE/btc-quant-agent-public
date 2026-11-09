"""Finite real-loopback E capture into F qualification/S1/Shadow/HTML/C, QA only."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests/native")]
from helpers import LocalVenue, QAClock, authority, key, sign  # noqa:E402
from btc_quant_agent.platform.native.contract import authorize, source_hash, digest  # noqa:E402
from btc_quant_agent.platform.native.journal import Journal  # noqa:E402
from btc_quant_agent.platform.native.runtime import capture  # noqa:E402
from btc_quant_agent.platform.native.transport import Transport  # noqa:E402
from btc_quant_agent.platform.native.audit import challenge  # noqa:E402
from btc_quant_agent.platform.native.contract import Envelope, AuditBody, AuditEnvelope  # noqa:E402
from btc_quant_agent.platform.qualification.evidence import Ledger, Plan, PlanEnvelope, SCHEMA_HASH  # noqa:E402
from btc_quant_agent.platform.qualification.source import Qualification  # noqa:E402
from btc_quant_agent.platform.qualification.product import Product  # noqa:E402
from btc_quant_agent.platform.rc_fixture import mixed_fixture, future_fixture, TRIGGER, DECISION  # noqa:E402


from btc_quant_agent.platform.qualification.evidence import (  # noqa:E402
    TimedAuditBody as CaptureAuditBody,
    TimedAuditEnvelope as CaptureAuditEnvelope,
)


def main(output, max_closes=None):
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    journal = Journal(output / "native.sqlite")
    ledger = Ledger(output / "qualification.sqlite")
    owner, owner_keys = key("SYNTHETIC_OWNER")
    auditor, auditor_keys = key("SYNTHETIC_AUDITOR")
    roots = {"owner": owner_keys, "auditor": auditor_keys, "rights_sha256": "b" * 64}
    server = LocalVenue(output / "tls", QAClock(TRIGGER), [])
    policy = server.policy
    start = TRIGGER - 60 * 86400000
    plan = Plan(
        evidence_class="SYNTHETIC_NETWORK_QA",
        source_sha256=source_hash(),
        executable_sha256="a" * 64,
        config_sha256=digest(policy.model_dump(mode="json")),
        rights_sha256="b" * 64,
        created_ms=start - 1000,
        start_ms=start,
        availability_start_ms=TRIGGER - 7 * 86400000,
        end_ms=TRIGGER,
        required_symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        auditor_key_id="SYNTHETIC_AUDITOR",
    )
    ledger.register(
        sign(plan, "SYNTHETIC_OWNER", owner, PlanEnvelope),
        sign(plan, "SYNTHETIC_AUDITOR", auditor, PlanEnvelope),
        roots,
        qa=True,
        observed_ms=start - 500,
    )
    qa_schema = {
        "accepted_product_schema_sha256": SCHEMA_HASH,
        "host_clock_admission_sha256": "FABRICATED_QA_ONLY",
    }
    qualification = Qualification(journal, ledger, qa_roots=roots, qa_schema_roots=qa_schema)
    product = Product(qualification, output / "shadow.sqlite")
    from btc_quant_agent.platform.qualification.admission import HostBody, HostEnvelope

    sessions = []

    def ingest(rows):
        for end, members in itertools.groupby(rows, key=lambda r: r.bar.end_ms):
            if max_closes is not None and len(sessions) >= max_closes:
                return
            members = list(members)
            clock = QAClock(end + 110)
            server.clock = clock
            messages = []
            for r in members:
                c = r.bar.candle
                i = {"1H": "1h", "4H": "4h", "1D": "1d"}[c.interval]
                messages.append(
                    {
                        "stream": f"{c.symbol.lower()}@kline_{i}",
                        "data": {
                            "e": "kline",
                            "E": end + 100,
                            "s": c.symbol,
                            "k": {
                                "s": c.symbol,
                                "i": i,
                                "t": c.open_time_ms,
                                "T": c.close_time_ms,
                                "x": True,
                                "o": str(c.open),
                                "h": str(c.high),
                                "l": str(c.low),
                                "c": str(c.close),
                                "v": str(c.volume),
                            },
                        },
                    }
                )
            server.messages = messages
            g, _, _, _ = authority(
                policy, output / f"session_{len(sessions):03d}", clock.wall, retention_seconds=7776000
            )
            env = sign(g, "SYNTHETIC_OWNER", owner, Envelope)
            adm = sign(
                AuditBody(
                    grant_sha256=digest(g.model_dump(mode="json")),
                    rights_sha256="b" * 64,
                    independent_reference="ISOLATED_SYNTHETIC_NETWORK_TEST",
                ),
                "SYNTHETIC_AUDITOR",
                auditor,
                AuditEnvelope,
            )
            authorize(
                env,
                adm,
                roots,
                policy,
                source_hash=source_hash(),
                executable_hash="a" * 64,
                now_ms=clock.wall,
                exposure="SYNTHETIC_NETWORK",
            )
            transport = Transport(policy, g, journal, clock, qa_ca=server.cert, qa_proxy=True)
            terminal = capture(g, policy, journal, clock, transport)
            assert terminal["reason"] == "PEER_CLOSED_NO_RECONNECT", terminal
            samples = [p[k] for p in clock.estimate["probes"] for k in ("request", "receive")]
            diagnostics = {
                "samples": [
                    {
                        "wall_ns": s["wall_ms"] * 1000000,
                        "mono_before_ns": s["mono_before_ms"] * 1000000,
                        "mono_after_ns": s["mono_after_ms"] * 1000000,
                    }
                    for s in samples
                ]
            }
            native_probes = [
                {
                    "source": policy.clock_endpoint,
                    "original_target_tls_verified": True,
                    "request_mono_ms": p["request"]["mono_before_ms"],
                    "receive_mono_ms": p["receive"]["mono_after_ms"],
                    "receive_wall_ms": p["receive"]["wall_ms"],
                    "server_ms": p["server_ms"],
                }
                for p in clock.estimate["probes"]
            ]
            host_body = HostBody(
                evidence_class="SYNTHETIC_NETWORK_QA",
                boot_id="SYNTHETIC_QA_BOOT",
                valid_start_ms=g.start_ms,
                valid_end_ms=g.end_ms,
                source_sha256=g.source_sha256,
                config_sha256=g.config_sha256,
                executable_sha256=g.executable_sha256,
                raw_diagnostics=diagnostics,
                native_clock_probes=native_probes,
                independent_reference="SYNTHETIC_ONLY",
            )
            host_envelope = sign(host_body, "SYNTHETIC_AUDITOR", auditor, HostEnvelope)
            ledger.attach_host(journal, g.session_id, host_envelope, roots, qa=True)
            body = CaptureAuditBody(
                **challenge(journal, g.session_id),
                independently_verified_reference="SYNTHETIC_AUDITOR_NOT_GENUINE",
                audited_ms=clock.wall,
                host_admission_sha256=digest(host_envelope.model_dump(mode="json")),
            )
            ledger.attach_audit(
                journal, sign(body, "SYNTHETIC_AUDITOR", auditor, CaptureAuditEnvelope), roots, qa=True
            )

            sessions.append({"session": g.session_id, "completed": len(members), "terminal": terminal})

    try:
        ingest(mixed_fixture())
        before = qualification.assess(DECISION)
        (output / "qualification.json").write_text(
            json.dumps({k: v for k, v in before.items() if k != "records"}, indent=2) + "\n"
        )
        if max_closes is not None:
            print(json.dumps({k: v for k, v in before.items() if k != "records"}))
            return
        assert before["status"] == "ELIGIBLE", before["reason"]
        decisions = [product.review(s, TRIGGER, DECISION) for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]
        assert [d.market_state for d in decisions] == ["ARMED", "NO_SETUP", "NO_SETUP"]
        initial = product.dashboard(output / "initial")
        frozen = [d.model_dump(mode="json") for d in product.decisions()]
        ingest(future_fixture(decisions[0]))
        observation = product.observe(decisions[0].episode_id, TRIGGER + 50 * 3600000 + 1000)
        final = product.dashboard(output / "product")
        assert [d.model_dump(mode="json") for d in product.decisions()] == frozen
        restarted = Product(
            Qualification(
                Journal(output / "native.sqlite"),
                Ledger(output / "qualification.sqlite"),
                qa_roots=roots,
                qa_schema_roots=qa_schema,
            ),
            output / "shadow.sqlite",
        )
        assert [d.model_dump(mode="json") for d in restarted.decisions()] == frozen
        replay = restarted.review("BTCUSDT", TRIGGER, DECISION)
        assert replay == decisions[0]
        product.export_c(output / "evaluation")
        # Persist only PUBLIC QA identities for deterministic offline evidence replay.
        (output / "qa_roots.json").write_text(
            json.dumps({"roots": roots, "schema": qa_schema}, indent=2) + "\n"
        )
        result = {
            "status": "PASS",
            "evidence_class": "SYNTHETIC_NETWORK_QA",
            "local_sessions": len(sessions),
            "completed_candles": sum(s["completed"] for s in sessions),
            "qualification_stages": before["stages"],
            "states": {d.symbol: d.market_state for d in decisions},
            "original_plans_preserved": True,
            "restart_and_replay": "IDENTICAL_DECISIONS_AND_EPISODE_IDS",
            "later_outcome": observation.outcome,
            "later_lifecycle": final["lifecycle"][-1]["state"],
            "scientific_decision": "INSUFFICIENT_SUPPORT",
            "source_qualified": False,
            "shadow_qualified": False,
            "economic_validation": False,
            "native_requests": 0,
            "dashboard": str((output / "product/latest.html").relative_to(ROOT)),
            "report": str((output / "evaluation/scientific_report.md").relative_to(ROOT)),
            "snapshot_initial_sha256": initial["snapshot_sha256"],
            "snapshot_final_sha256": final["snapshot_sha256"],
        }
        (ROOT / "F4_NATIVE_PRODUCT_OFFLINE_ACCEPTANCE.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
        print(json.dumps(result))
    finally:
        server.close()


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
