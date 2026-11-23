"""Execute the previously written finite low-rate contract against local TLS/WS."""

from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests/native")]
from helpers import LocalVenue, authority  # noqa: E402
from btc_quant_agent.platform.native.clock import Clock  # noqa: E402
from btc_quant_agent.platform.native.contract import authorize, source_hash  # noqa: E402
from btc_quant_agent.platform.native.journal import Journal  # noqa: E402
from btc_quant_agent.platform.native.runtime import capture  # noqa: E402
from btc_quant_agent.platform.native.transport import Transport  # noqa: E402


def main():
    declaration = (ROOT / "audit/low_rate_contract.json").read_bytes()
    spec = json.loads(declaration)
    out = ROOT / "artifacts/native_performance"
    out.mkdir(exist_ok=False)
    runs = []
    for index in range(spec["sessions"]):
        folder = out / str(index)
        folder.mkdir()
        c = Clock()
        now = c.sample()["wall_ms"]
        messages = []
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            for interval, width in [("1h", 3600000), ("4h", 14400000), ("1d", 86400000)]:
                end = now // width * width
                messages.append(
                    {
                        "stream": f"{symbol.lower()}@kline_{interval}",
                        "data": {
                            "e": "kline",
                            "E": now,
                            "s": symbol,
                            "k": {
                                "s": symbol,
                                "i": interval,
                                "x": True,
                                "t": end - width,
                                "T": end - 1,
                                "o": "100",
                                "h": "110",
                                "l": "90",
                                "c": "105",
                                "v": "1000",
                            },
                        },
                    }
                )
        server = LocalVenue(folder / "tls", c, messages)
        server.delay = spec["send_spacing_seconds"]
        started = time.perf_counter()
        try:
            p = server.policy
            g, env, audit, roots = authority(p, folder / "session", now)
            authorize(
                env,
                audit,
                roots,
                p,
                source_hash=source_hash(),
                executable_hash="a" * 64,
                now_ms=now,
                exposure="SYNTHETIC_NETWORK",
            )
            j = Journal(folder / "registry.sqlite")
            t = Transport(p, g, j, c, qa_ca=server.cert, qa_proxy=True)
            result = capture(g, p, j, c, t)
            records = j.records(g.session_id)
            assert len(records) == 9 and j.usage(g.session_id)["incoming"] == 11
            latency = [r["record"]["durable_ms"] - r["record"]["received_ms"] for r in records]
            assert max(latency) <= spec["gates"]["durable_latency_max_ms"]
            assert result["transport_closed"] and result["unsettled_frames"] == 0
            runs.append(
                {
                    "wall_elapsed_ms": (time.perf_counter() - started) * 1000,
                    "completed": len(records),
                    "admitted_frames": j.usage(g.session_id)["incoming"],
                    "durable_latency_ms": latency,
                    "clock_uncertainty_ms": c.estimate["uncertainty_ms"],
                    "TLS_connections": len(t.tls),
                }
            )
        finally:
            server.close()
    receipt = {
        "status": "PASS",
        "exposure": "LOCAL_SYNTHETIC_NETWORK_ONLY",
        "contract_sha256": hashlib.sha256(declaration).hexdigest(),
        "runs": runs,
        "completed": sum(r["completed"] for r in runs),
        "admitted": sum(r["admitted_frames"] for r in runs),
        "native_market_requests": 0,
        "M1B_150_per_second": "PARTIAL_UNCHANGED",
        "native_performance_qualified": False,
    }
    (ROOT / "audit/native_performance.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
