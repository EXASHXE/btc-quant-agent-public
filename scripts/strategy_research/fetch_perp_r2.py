"""Download exactly the frozen public R2 sources into a fresh task cache."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from btc_quant_agent.strategy_research.perp_source import MONTHS, SYMBOLS, source_url, verified_csv

ROOT = Path(__file__).resolve().parents[2]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise URLError("UNREGISTERED_REDIRECT")


def freeze_gate() -> dict[str, object]:
    method = ROOT / "configs/strategy_research/G2_R2_PERP_PREREGISTRATION.json"
    receipt = json.loads(
        (
            ROOT / "evidence/v0.6/b_line/g2_reconstruction_r2/FIRST_PUSH_VERIFICATION.json"
        ).read_text()
    )
    if hashlib.sha256(method.read_bytes()).hexdigest() != receipt["method_sha256"]:
        raise ValueError("FROZEN_METHOD_CHANGED")
    if receipt["pre_reg_r2_sha"] != receipt["verified_remote_head"]:
        raise ValueError("FIRST_PUSH_UNVERIFIED")
    return cast(dict[str, object], receipt)


def fetch(cache: Path) -> dict[str, object]:
    receipt = freeze_gate()  # no network call before gate
    if (
        cache.is_symlink()
        or not cache.name.startswith("v06-g2-r2-")
        or cache.parent != Path("/tmp")
    ):
        raise ValueError("UNKNOWN_CACHE_PERMISSION")
    if any(p.name not in {"PRESERVATION_PRE.json", "freeze.py"} for p in cache.iterdir()):
        raise ValueError("CACHE_NOT_FRESH")
    with (cache / "FETCH_STARTED.json").open("x") as marker:
        json.dump(
            {
                "pre_reg_r2_sha": receipt["pre_reg_r2_sha"],
                "created_utc": datetime.now(UTC).isoformat(),
            },
            marker,
        )
    # A cache is new for this task. Existing market files are never searched/reused.
    opener = build_opener(NoRedirect())
    records: list[dict[str, object]] = []
    for kind in ("price", "funding"):
        for symbol in SYMBOLS:
            for month in MONTHS if kind == "price" else MONTHS[1:]:
                url = source_url(kind, symbol, month)
                name = url.rsplit("/", 1)[1]
                record: dict[str, object] = {
                    "kind": kind,
                    "symbol": symbol,
                    "month": month,
                    "url": url,
                    "market_type": "USDT_M_PERPETUAL_FUTURES",
                    "grade": "ARCHIVAL_EVENT_TIME_RECONSTRUCTED",
                    "exposure": "PRIOR_EXPOSED_OR_DEVELOPMENT",
                }
                try:
                    with opener.open(Request(url), timeout=30) as r:
                        data = r.read(50_000_001)
                        if len(data) > 50_000_000:
                            raise ValueError("ARCHIVE_TOO_LARGE")
                        record.update(
                            {
                                "status": r.status,
                                "http_date": r.headers.get("Date"),
                                "last_modified": r.headers.get("Last-Modified"),
                            }
                        )
                    with opener.open(Request(url + ".CHECKSUM"), timeout=30) as r:
                        checksum = r.read(1024)
                    raw = verified_csv(data, checksum, name)
                    for file, value in [
                        (name, data),
                        (name + ".CHECKSUM", checksum),
                        (name.removesuffix(".zip") + ".csv", raw),
                    ]:
                        with (cache / file).open("xb") as out:
                            out.write(value)
                    record.update(
                        {
                            "archive_sha256": hashlib.sha256(data).hexdigest(),
                            "csv_sha256": hashlib.sha256(raw).hexdigest(),
                            "checksum_sha256": hashlib.sha256(checksum).hexdigest(),
                            "archive_bytes": len(data),
                            "csv_bytes": len(raw),
                        }
                    )
                except HTTPError as exc:
                    if kind != "funding" or exc.code != 404:
                        raise
                    record.update(
                        {
                            "status": 404,
                            "funding_eligible": False,
                            "reason": "FROZEN_ADVERSE_PROXY_FALLBACK",
                        }
                    )
                record["retrieved_utc"] = datetime.now(UTC).isoformat()
                records.append(record)
    return {
        "pre_reg_r2_sha": receipt["pre_reg_r2_sha"],
        "first_push_verified_utc": receipt["verified_utc"],
        "records": records,
        "protected_reads": 0,
        "exchange_writes": 0,
        "cache_scope": "NEW_TASK_NONPROTECTED_ALLOWLIST_ONLY",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    result = fetch(args.cache)
    with (args.cache / "DOWNLOAD_MANIFEST.json").open("x") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
    print(json.dumps({"sources": len(cast(list[object], result["records"])), "protected_reads": 0}))


if __name__ == "__main__":
    main()
