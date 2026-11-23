"""Portable JSON/CSV and self-contained HTML/SVG engineering reports."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from .core import fingerprint, primitive


def source_identity(root: Path | None = None) -> str:
    root = root or Path(__file__).resolve().parents[1]
    return fingerprint(
        {str(f.relative_to(root)): fingerprint(f.read_bytes().hex()) for f in sorted(root.rglob("*.py"))}
    )


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(primitive(value), indent=2, sort_keys=True, allow_nan=False) + "\n"
    if path.exists() and path.read_text() != encoded:
        raise ValueError(f"immutable artifact differs: {path}")
    path.write_text(encoded, encoding="utf-8")


def table(rows):
    if not rows:
        return "<p>No observations.</p>"
    keys = list(dict.fromkeys(k for row in rows for k in row))
    return (
        "<table><thead><tr>"
        + "".join("<th>" + html.escape(k) + "</th>" for k in keys)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join("<td>" + html.escape(str(row.get(k, ""))) + "</td>" for k in keys) + "</tr>"
            for row in rows
        )
        + "</tbody></table>"
    )


def chart(points):
    if not points:
        return ""
    values = [float(p["equity"]) for p in points]
    low, high = min(values), max(values)
    coords = " ".join(
        f"{20 + i * 860 / max(1, len(values) - 1):.2f},{200 - (v - low) * 170 / max(high - low, 1e-9):.2f}"
        for i, v in enumerate(values)
    )
    return f'<svg viewBox="0 0 900 230" role="img" aria-label="Synthetic marked equity"><text x="20" y="18">Synthetic marked equity · {low:.2f}–{high:.2f}</text><polyline points="{coords}" fill="none" stroke="#187b68" stroke-width="2"/></svg>'


def document(title, body, *, label="SYNTHETIC · ENGINEERING ONLY · NOT ECONOMIC VALIDATION"):
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'
        + html.escape(title)
        + """</title><style>
    body{font:15px system-ui;max-width:1200px;margin:35px auto;padding:0 20px;color:#172b38;background:#f7faf9}
    table{border-collapse:collapse;width:100%;font-size:13px;background:white;margin:18px 0}td,th{border:1px solid #dce5e1;padding:8px;text-align:left}th{background:#e4efeb}
    svg{width:100%;background:white;border:1px solid #dce5e1}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#076c61} .label{padding:10px;background:#fff1d0}
    </style><h1>"""
        + html.escape(title)
        + '</h1><p class="label">' + html.escape(label) + '</p>'
        + body
        + "</html>"
    )


def save_run(result, output):
    id = result["run"]["run_id"]
    path = Path(output) / id
    path.mkdir(parents=True, exist_ok=True)
    write_json(path / "run.json", result)
    for key in ("trades", "equity", "cashflows"):
        rows = result[key]
        if not rows:
            continue
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with (path / (key + ".csv")).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)
    body = chart(result["equity"]) + table(
        [{"metric": k, "value": v} for k, v in result["run"]["metrics"].items() if k != "attribution"]
    )
    body += (
        "<h2>Closed trades</h2>"
        + table(result["trades"])
        + "<h2>Provenance and limitations</h2><pre>"
        + html.escape(json.dumps(result["run"], indent=2))
        + "</pre>"
    )
    (path / "report.html").write_text(document("Quant synthetic replay", body), encoding="utf-8")
    return path


def compare(configs, output):
    from .backtest import run
    from .data import SyntheticProvider

    base = configs[0]
    shared = ("universe", "market", "scenario", "bars", "seed", "interval_seconds", "benchmark")
    costs = ("fee_bps", "slippage_bps", "spread_bps", "funding", "fill_fraction", "volume_participation")
    for c in configs[1:]:
        if any(getattr(c, k) != getattr(base, k) for k in shared):
            raise ValueError("comparison dataset definitions differ")
        if any(getattr(c.execution, k) != getattr(base.execution, k) for k in costs):
            raise ValueError("comparison cost assumptions differ")
    events = SyntheticProvider().events(base)
    source = source_identity()
    results = [run(c, events, source) for c in configs]
    paths = [str(save_run(r, Path(output) / "runs")) for r in results]
    rows = []
    for c, r, path in zip(configs, results, paths):
        m = r["run"]["metrics"]
        rows.append(
            {
                "configuration": c.name,
                "run_id": r["run"]["run_id"],
                "dataset": "SYNTHETIC",
                "return": m["modeled_return"],
                "drawdown": m["max_drawdown"],
                "trades": m["closed_trades"],
                "fees": m["fees"],
                "funding": m["funding_cashflow"],
                "slippage": m["slippage"],
                "path": path,
            }
        )
    result = {
        "comparison_id": fingerprint(rows),
        "source_hash": source,
        "dataset_hash": results[0]["run"]["dataset_hash"],
        "exposure": "SYNTHETIC",
        "rows": rows,
        "assumptions": base.execution.model_dump(mode="json"),
        "limitations": [
            "Identical source and costs. No winner is economically validated.",
            "Entry selection and management require separate paired ablations; aggregate PnL cannot identify either contribution.",
        ],
    }
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "comparison.json", result)
    (output / "comparison.html").write_text(document("Strategy comparison", table(rows)), encoding="utf-8")
    return result
