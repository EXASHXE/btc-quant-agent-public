"""Metadata-only audit of frozen public sources; never read response bodies."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from btc_quant_agent.strategy_research.source import MONTHS, SYMBOLS, archive_url, digest


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise URLError("REDIRECT_NOT_AUTHORIZED")


def audit() -> dict[str, object]:
    opener = build_opener(NoRedirect())
    records: list[dict[str, object]] = []
    for symbol in SYMBOLS:
        for month in MONTHS:
            url = archive_url(symbol, month)
            row: dict[str, object] = {
                "symbol": symbol,
                "month": month,
                "url": url,
                "market_type": "SPOT",
                "exposure": "PRIOR_EXPOSED_OR_DEVELOPMENT",
                "body_bytes_read": 0,
                "archive_digest": None,
                "price_rows_read": 0,
                "historical_contemporaneous_receipts": "ABSENT",
                "empirical_eligible": False,
                "usage": "METADATA_ONLY",
            }
            try:
                with opener.open(Request(url, method="HEAD"), timeout=15) as response:
                    row.update(
                        {
                            "status": response.status,
                            "content_length": response.headers.get("Content-Length"),
                            "last_modified": response.headers.get("Last-Modified"),
                            "final_url": response.url,
                        }
                    )
                    row["header_digest"] = digest(
                        {
                            k: row[k]
                            for k in (
                                "url",
                                "status",
                                "content_length",
                                "last_modified",
                                "final_url",
                            )
                        }
                    )
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                row.update(
                    {
                        "status": "UNAVAILABLE",
                        "error_type": type(exc).__name__,
                        "header_digest": None,
                    }
                )
            row["retrieved_utc"] = datetime.now(UTC).isoformat()
            records.append(row)
    return {
        "schema": "G2_R1_SOURCE_AND_EXPOSURE_LEDGER_V1",
        "sources": records,
        "source_kind": "OFFICIAL_PUBLIC_ARCHIVE_HEADERS_ONLY",
        "archive_bodies_read": 0,
        "new_empirical_outcome_reads": 0,
        "local_fixture_permission": "NONE_VERIFIED; NO_LOCAL_MARKET_FIXTURE_READ",
        "prior_exposure": {
            "RC1": "BTC/ETH/SOL development previously analyzed",
            "RC2": "protected targets never queried; no target manifest read",
        },
        "actual_historical_online_latency": "UNKNOWN; DO_NOT_REPLACE_WITH_ASSUMPTION",
        "archive_publication_lag": "Last-Modified captured per monthly object, not online lag",
        "availability_gate": "BLOCKED_NO_CONTEMPORANEOUS_RECEIPT_PROOF",
        "empirical_minute_coverage": None,
        "protected_reads": 0,
        "exchange_writes": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    # Fail if output already exists, keeping evidence append-only.
    with args.out.open("x", encoding="utf-8") as output:
        json.dump(audit(), output, indent=2, sort_keys=True)
        output.write("\n")


if __name__ == "__main__":
    main()
