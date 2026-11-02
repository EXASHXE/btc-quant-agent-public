#!/usr/bin/env python3
"""Finite offline clock-proof demonstration using the deterministic test fixtures."""

from __future__ import annotations

import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from canary_public.test_clock_domain import scenario, SCOPE  # noqa: E402
from btc_quant_agent.platform.canary import clock_domain as d  # noqa: E402
from btc_quant_agent.platform.canary.public_data import normalize, quote_from_record  # noqa: E402


def main():
    rows = []
    for offset in (0, 846, -846):
        clock, record = scenario(offset)
        # All inputs are fabricated. Exercise the V2 native-schema arithmetic
        # without relabeling the demonstration as observed PUBLIC_CANARY data.
        record["exposure"] = record["wire"]["exposure"] = "SYNTHETIC"
        record["metadata"]["wire"]["exposure"] = "SYNTHETIC"
        for probe in record["clock"]["probes"]:
            probe["exposure"] = "SYNTHETIC"
        record["clock"] = d.estimate(record["clock"]["probes"], SCOPE, "SYNTHETIC")
        result = normalize(record)
        q = quote_from_record(result["quote"])
        if q is None:
            raise RuntimeError("OFFLINE_POSITIVE_CLOCK_SCENARIO_FAILED:" + str(result["reasons"]))
        clock.advance(10, wall_step=900)
        with d.decision_clock(clock.sample(), SCOPE):
            veto = q.provenance.reason(clock.wall(), 5000)
        if veto != "LOCAL_WALL_CLOCK_JUMP":
            raise RuntimeError("OFFLINE_STEP_DID_NOT_REVOKE_CLOCK_PROOF")
        rows.append(
            {
                "fabricated_exchange_offset_ms": offset,
                "native_event_ms": q.provenance.exchange_event_ts,
                "raw_local_receive_ms": q.provenance.received_ts,
                "clock_report": result["clock"],
                "provenance": result["quote"]["provenance"],
                "subsequent_900ms_step_veto": veto,
            }
        )
    report = {
        "exposure": "SYNTHETIC",
        "description": "Clock-domain engineering fixture; no observed feed quality or Alpha",
        "native_market_requests": 0,
        "source_qualified": False,
        "shadow_advisory_qualified": False,
        "economically_validated": False,
        "cases": rows,
    }
    out = ROOT / "artifacts/clock_remediation_20261030"
    out.mkdir(exist_ok=True)
    (out / "offline_demo.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    table = "".join(
        "<tr>"
        + "".join(
            "<td>" + html.escape(str(v)) + "</td>"
            for v in (
                r["fabricated_exchange_offset_ms"],
                r["native_event_ms"],
                r["raw_local_receive_ms"],
                r["clock_report"]["event_to_receive_estimate_bounds_ms"],
                r["subsequent_900ms_step_veto"],
            )
        )
        + "</tr>"
        for r in rows
    )
    (out / "offline_demo.html").write_text(
        "<!doctype html><html lang='en'><meta charset='utf-8'><title>L4 offline clock remediation</title>"
        "<h1>Synthetic clock-domain engineering</h1><p>No new market requests, source qualification, fills or economic validation.</p>"
        "<table border='1'><tr><th>Fabricated offset (ms)</th><th>Original native event</th><th>Original receiver wall</th>"
        "<th>Bounded event-to-receive estimate (ms)</th><th>Step veto</th></tr>" + table + "</table></html>\n"
    )
    print(
        json.dumps(
            {"cases": len(rows), "native_market_requests": 0, "output": str(out / "offline_demo.json")}
        )
    )


if __name__ == "__main__":
    main()
