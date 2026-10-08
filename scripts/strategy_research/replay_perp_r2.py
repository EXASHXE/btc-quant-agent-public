"""Deterministic frozen R2 replay from the verified task cache, no network."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from fetch_perp_r2 import freeze_gate

from btc_quant_agent.strategy_research.perp_analysis import candidate_result, summary
from btc_quant_agent.strategy_research.perp_replay import (
    CANDIDATES,
    CONTROLS,
    Candidate,
    Series,
    Trade,
    derived,
    execute,
)
from btc_quant_agent.strategy_research.perp_source import (
    SYMBOLS,
    Bar,
    Funding,
    SourceError,
    digest,
    epoch,
    funding_complete,
    parse_funding,
    parse_prices,
    validate_manifest,
    verified_csv,
)

ROOT = Path(__file__).resolve().parents[2]


def write(path: Path, value: object) -> None:
    with path.open("x") as out:
        json.dump(value, out, indent=2, sort_keys=True)
        out.write("\n")


def rows(path: Path, values: list[dict[str, Any]]) -> str:
    data = "".join(
        json.dumps(v, sort_keys=True, separators=(",", ":")) + "\n" for v in values
    ).encode()
    with (
        path.open("xb") as target,
        gzip.GzipFile(filename="", fileobj=target, mode="wb", mtime=0) as out,
    ):
        out.write(data)
    return hashlib.sha256(data).hexdigest()


def replay(cache: Path, out: Path) -> dict[str, Any]:
    if cache.parent != Path("/tmp") or not cache.name.startswith("v06-g2-r2-"):
        raise SourceError("UNKNOWN_CACHE_PERMISSION_BEFORE_READ")
    if cache.is_symlink() or out.parent != cache or out.is_symlink():
        raise SourceError("UNKNOWN_CACHE_OR_OUTPUT_SCOPE")
    freeze = freeze_gate()
    out.mkdir(mode=0o700, exist_ok=False)
    manifest = json.loads((cache / "DOWNLOAD_MANIFEST.json").read_text())
    records = manifest["records"]
    if manifest["pre_reg_r2_sha"] != freeze["pre_reg_r2_sha"]:
        raise SourceError("CACHE_CAMPAIGN_CHANGED")
    validate_manifest(records, str(freeze["verified_utc"]))
    method = json.loads(
        (ROOT / "configs/strategy_research/G2_R2_PERP_PREREGISTRATION.json").read_text()
    )
    partitions = [tuple(epoch(x) for x in p) for p in method["windows"]["partitions"]]
    start, end = partitions[0][0], partitions[-1][1]
    funding_by_symbol = {}
    proxy = False

    def raw(record: dict[str, Any]) -> bytes:
        name = record["url"].rsplit("/", 1)[1]
        data = (cache / name).read_bytes()
        checksum = (cache / (name + ".CHECKSUM")).read_bytes()
        if hashlib.sha256(checksum).hexdigest() != record["checksum_sha256"]:
            raise SourceError("CHECKSUM_RECEIPT_DIGEST_CHANGED")
        value = verified_csv(data, checksum, name)
        if (
            hashlib.sha256(value).hexdigest() != record["csv_sha256"]
            or hashlib.sha256(data).hexdigest() != record["archive_sha256"]
        ):
            raise SourceError("CACHE_DIGEST_CHANGED")
        return value

    for symbol in SYMBOLS:
        values: list[Funding] = []
        for record in records:
            if record["kind"] == "funding" and record["symbol"] == symbol:
                if record["status"] != 200:
                    proxy = True
                    continue
                values.extend(parse_funding(raw(record), symbol, record["month"]))
        fund = tuple(sorted(values, key=lambda f: f.t))
        if not funding_complete(fund, start, end):
            proxy = True
        funding_by_symbol[symbol] = fund
    trades: dict[str, list[Trade]] = defaultdict(list)
    decisions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    matched: dict[str, list[tuple[Trade, Trade]]] = defaultdict(list)
    delayed: dict[str, list[Trade]] = defaultdict(list)
    source_coverage = []
    for symbol in SYMBOLS:
        minutes: list[Bar] = []
        for record in records:
            if record["kind"] == "price" and record["symbol"] == symbol:
                month = parse_prices(raw(record), symbol, record["month"])
                minutes.extend(month)
                source_coverage.append(
                    {
                        "symbol": symbol,
                        "month": record["month"],
                        "n_minutes": len(month),
                        "coverage": 1,
                        "event_start": month[0].t,
                        "event_end_exclusive": month[-1].end,
                        "gaps": 0,
                        "duplicates": 0,
                    }
                )
        series = Series(tuple(minutes))
        busy: dict[str, int] = {}
        late_busy: dict[str, int] = {}
        for f in series.features:
            fold = next(
                ((i + 1, a, b) for i, (a, b) in enumerate(partitions) if a <= f.decision < b), None
            )
            if fold is None:
                continue
            partition, a, b = fold
            for candidate in (*CANDIDATES, *CONTROLS):
                cid = candidate.identity
                result = execute(
                    series,
                    f,
                    candidate,
                    partition,
                    a,
                    b,
                    funding_by_symbol[symbol],
                    proxy=proxy,
                    previous_exit=busy.get(cid, 0),
                )
                decisions[cid].append(
                    {
                        "candidate": cid,
                        "symbol": symbol,
                        "partition": partition,
                        "decision_ms": f.decision,
                        "entry_ms": f.entry,
                        "feature_identity": f.identity,
                        "risk_price": str(f.risk),
                        "regime": f.regime,
                        "data_grade": f.grade,
                        "requested_action": candidate.direction if f.action(candidate) else "WAIT",
                        "status": result.status,
                    }
                )
                if result.trade is None:
                    continue
                t = result.trade
                trades[cid].append(t)
                busy[cid] = t.exit_ms
                if candidate.family == "NAIVE":
                    continue
                pair = []
                for direction in ("LONG", "SHORT"):
                    counter = execute(
                        series,
                        f,
                        Candidate("NAIVE", direction, candidate.hours),
                        partition,
                        a,
                        b,
                        funding_by_symbol[symbol],
                        proxy=proxy,
                    )
                    if counter.trade is None:
                        raise SourceError("MATCHED_CONTROL_FILL_MISMATCH")
                    pair.append(counter.trade)
                matched[cid].append((pair[0], pair[1]))
                later = execute(
                    series,
                    f,
                    candidate,
                    partition,
                    a,
                    b,
                    funding_by_symbol[symbol],
                    proxy=proxy,
                    previous_exit=late_busy.get(cid, 0),
                    delay=60_000,
                )
                if later.trade is not None:
                    delayed[cid].append(later.trade)
                    late_busy[cid] = later.trade.exit_ms
        del series, minutes
    result_table = [
        candidate_result(
            c.identity,
            trades[c.identity],
            decisions[c.identity],
            matched[c.identity],
            delayed[c.identity],
            start,
            proxy,
        )
        for c in CANDIDATES
    ]
    ranking = sorted(
        result_table,
        key=lambda r: (
            -Decimal(r["ranking_score"]) if r["ranking_score"] is not None else Decimal("Infinity"),
            r["candidate_id"],
        ),
    )
    shortlist = [r["candidate_id"] for r in ranking if r["shortlist_eligible"]][:2]
    decision = (
        "G2_R2_EXPLORATORY_SHORTLIST_READY_FOR_CONTROLLER"
        if shortlist
        else (
            "G2_R2_EXPLORATORY_NO_GO"
            if not proxy
            and all(
                r["sample_support"]
                and r["higher_cost"]["mean_net_R"] is not None
                and Decimal(r["higher_cost"]["mean_net_R"]) <= 0
                for r in result_table
            )
            else "G2_R2_DIAGNOSTIC_ONLY"
        )
    )
    all_decisions = [row for c in (*CANDIDATES, *CONTROLS) for row in decisions[c.identity]]
    all_trades = [
        {"role": "candidate" if c.family != "NAIVE" else "unconditional_control", **derived(t)}
        for c in (*CANDIDATES, *CONTROLS)
        for t in trades[c.identity]
    ]
    all_trades.extend(
        {"role": f"matched_counterfactual_{direction}", "parent_candidate": cid, **derived(t)}
        for cid, pairs in matched.items()
        for pair in pairs
        for direction, t in zip(("LONG", "SHORT"), pair, strict=True)
    )
    all_trades.extend(
        {"role": "latency_diagnostic", "parent_candidate": cid, **derived(t)}
        for cid, values in delayed.items()
        for t in values
    )
    all_decisions.sort(key=lambda r: (r["decision_ms"], r["symbol"], r["candidate"]))
    all_trades.sort(key=lambda r: (r["entry_ms"], r["symbol"], r["role"], r["candidate"]))
    if len({t.identity for c in CANDIDATES for t in trades[c.identity]}) != sum(
        len(trades[c.identity]) for c in CANDIDATES
    ):
        raise SourceError("DUPLICATE_TRADE_IDENTITY")
    row_hashes = {
        "decision_rows_uncompressed_sha256": rows(out / "DECISION_ROWS.jsonl.gz", all_decisions),
        "trade_rows_uncompressed_sha256": rows(out / "TRADE_ROWS.jsonl.gz", all_trades),
    }
    write(
        out / "SOURCE_AND_EXPOSURE_LEDGER.json",
        {
            **manifest,
            "coverage": source_coverage,
            "funding_mode": "PROXY_STRESS_ONLY" if proxy else "ACTUAL_RATE_ADVERSE_PRICE_PROXY",
            "funding_counts": {s: len(funding_by_symbol[s]) for s in SYMBOLS},
            "availability_lag_ms": 60000,
            "receipt_proven_PIT": False,
            "source_manifest_sha256": digest(manifest),
        },
    )
    table = {
        "pre_reg_r2_sha": freeze["pre_reg_r2_sha"],
        "data_grade": "ARCHIVAL_EVENT_TIME_RECONSTRUCTED",
        "exposure": "PRIOR_EXPOSED_OR_DEVELOPMENT",
        "candidates": result_table,
        "controls": {
            c.identity: {
                "base": summary(trades[c.identity]),
                "higher_cost": summary(trades[c.identity], stress=True),
            }
            for c in CONTROLS
        },
        "WAIT_NO_TRADE": {
            "decisions": len(decisions[CANDIDATES[0].identity]),
            "trades": 0,
            "PnL": "0",
            "net_R": None,
        },
        "Tactical_reference": {
            "status": "NOT_COMPUTABLE",
            "reason": "frozen derivative/reference-universe inputs unavailable; known RC1 hard FAIL unchanged",
        },
        "ranking": [r["candidate_id"] for r in ranking],
        "shortlist": shortlist,
        "terminal_state": decision,
        "grid": "NO_GRID; zero registered, four candidate slots unused",
        "row_hashes": row_hashes,
        "row_counts": {
            "decisions": len(all_decisions),
            "derived_trades_including_controls": len(all_trades),
        },
        "scientific_digest": digest({"candidates": result_table, "row_hashes": row_hashes}),
        "protected_reads": 0,
        "exchange_writes": 0,
    }
    write(out / "EXPLORATORY_RESULT_TABLE.json", table)
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.cache, args.out)
    print(
        json.dumps(
            {
                "terminal_state": result["terminal_state"],
                "scientific_digest": result["scientific_digest"],
                "candidates": 8,
                "shortlist": result["shortlist"],
            }
        )
    )


if __name__ == "__main__":
    main()
