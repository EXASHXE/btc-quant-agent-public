"""Generate reviewable offline acceptance evidence with DNS/socket calls forbidden."""

from pathlib import Path
import json
import socket


def main():
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append("NETWORK_ATTEMPT")
        raise AssertionError("OFFLINE_BRIDGE_NETWORK_FORBIDDEN")

    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    socket.getaddrinfo = blocked

    from btc_quant_agent.platform.bridge.cli import execute, readiness
    from btc_quant_agent.platform.bridge.config import load
    from btc_quant_agent.platform.bridge.fixtures import SCENARIOS, OfflineFixtureProvider
    from btc_quant_agent.platform.bridge.runtime import BridgeStore, ReadOnlyScanner
    from btc_quant_agent.platform.core import UserReportedFill, dec
    from btc_quant_agent.platform.reporting import source_identity, write_json
    from types import SimpleNamespace

    root = Path(__file__).resolve().parents[1]
    output = root / "artifacts/final"
    output.mkdir(parents=True, exist_ok=True)
    config = load(root / "configs/bridge/offline.yaml")
    results = {}
    for scenario in SCENARIOS:
        source = OfflineFixtureProvider(config, scenario)
        store = BridgeStore(output / (scenario + ".sqlite"))
        scanner = ReadOnlyScanner(config, store)
        rows = [scanner.scan(source.snapshot(bar)) for bar in (50, 51)]
        write_json(output / (scenario + ".json"), {"exposure": "SYNTHETIC", "results": rows})
        results[scenario] = {
            "states": [
                [
                    {
                        "symbol": x["symbol"],
                        "state": x.get("state"),
                        "action": x["action"],
                        "veto_reasons": x.get("veto_reasons", []),
                    }
                    for x in row["records"]
                ]
                for row in rows
            ]
        }
        if scenario == "normal":
            plan = next(x["plan"] for x in rows[-1]["records"] if x["symbol"] == "BTCUSDT")
            assert plan["state"] == "ENTRY_ELIGIBLE"
            fill = UserReportedFill(
                "synthetic-user-report",
                "synthetic-user-position",
                "BTCUSDT",
                "LONG",
                dec(plan["entry_price"]),
                dec("1"),
                rows[-1]["decision_ts"] + 1,
                rows[-1]["decision_ts"] + 2,
            )
            registered = store.report_plan_fill(plan["candidate"]["id"], fill)
            managed = scanner.scan(source.snapshot(52))
            assert any(x["kind"] == "POSITION_RISK" for x in managed["records"])
            assert not any(
                x["symbol"] == "BTCUSDT" and x.get("state") == "ENTRY_ELIGIBLE" for x in managed["records"]
            )
            assert store.position(fill.position_id).status == "OPEN"
            write_json(
                output / "user_position.json",
                {
                    "fixture": "fabricated USER_REPORTED input, not an Owner fill",
                    "registered": registered,
                    "managed": managed,
                    "actual_state_after_recommendations": "OPEN",
                },
            )
    replays = {}
    for name in ("offline", "okx", "spot", "delay5"):
        args = SimpleNamespace(
            config=str(root / "configs/bridge" / (name + ".yaml")),
            bridge_operation="replay",
            fixture="normal",
            output=str(output / name),
            store=None,
            bars=[50, 51, 55, 57],
        )
        replays[name] = execute(args)
        btc = [r for r in replays[name]["states"] if r["symbol"] == "BTCUSDT"]
        assert btc[-1]["state"] == "EXPIRED"
        assert any(r["state"] == "ENTRY_ELIGIBLE" for r in btc)
    write_json(output / "source_readiness.json", readiness(config))
    summary = {
        "status": "OFFLINE_BRIDGE_VALIDATED; REAL_SOURCE_ACTIVATION_BLOCKED",
        "exposure": "SYNTHETIC",
        "source_hash": source_identity(),
        "config_hash": config.hash,
        "scenarios": results,
        "replays": replays,
        "network_calls_attempted": len(attempts),
        "orders_or_account_operations": 0,
        "limitations": [
            "Provider payloads and clock evidence are generated fixtures, not measured connectivity.",
            "No profitability, production deployment or real-market validation is established.",
        ],
    }
    write_json(output / "acceptance.json", summary)
    print(
        json.dumps(
            {
                "artifact": str(output / "acceptance.json"),
                "scenarios": len(results),
                "replays": len(replays),
                "network_calls_attempted": len(attempts),
                "source_hash": summary["source_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
