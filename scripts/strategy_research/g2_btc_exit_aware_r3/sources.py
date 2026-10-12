"""Whitelist-only public historical development admission; no private transports."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from scripts.strategy_research.g2_btc_empirical_fast_r1.sources import validate_zip_checksum
from scripts.strategy_research.g2_btc_flow_regime_r2.sources import parse_month

ROOT = Path(__file__).resolve().parents[3]
SCRATCH = Path("/tmp/btc-g2-codex-exit-aware-r3")
EVIDENCE = ROOT / "evidence/v0.6/b_line/g2_btc_exit_aware_r3"
FREEZE = "45bf7cc72eb9a870323c5da056fc9287d42b7b22"
BASE = "3df7a9a490a06c398d20da57bf19fc48d3b1c74e"
BRANCH = "feature/v06-bline-g2-codex-btc-exit-aware-research-r3"
ALLOWED = frozenset((y, m) for y in (2021, 2022, 2023) for m in (1, 2, 5, 6, 8, 9, 11, 12))


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write(name: str, obj: dict) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n")


def verify_freeze() -> dict:
    names = ("FROZEN_ROSTER_27_CELLS.json", "FREEZE_AND_SOURCE_IDENTITY.json")
    for name in names:
        relative = (EVIDENCE / name).relative_to(ROOT)
        raw = subprocess.check_output(["git", "show", f"{FREEZE}:{relative}"], cwd=ROOT)
        if raw != (EVIDENCE / name).read_bytes():
            raise ValueError("FROZEN_FILE_MUTATED")
    identity = json.loads((EVIDENCE / names[1]).read_text())
    for path, expected in identity["pinned_read_only_source_sha256"].items():
        if digest((ROOT / path).read_bytes()) != expected:
            raise ValueError("PINNED_R2_SOURCE_MUTATED")
    receipt = json.loads((SCRATCH / "freeze-push-receipt.json").read_text())
    if receipt["freeze_sha"] != FREEZE or receipt["verified_remote_head"] != FREEZE:
        raise ValueError("FREEZE_PUSH_NOT_VERIFIED")
    roster = json.loads((EVIDENCE / names[0]).read_text())
    if digest((EVIDENCE / names[0]).read_bytes()) != identity["roster_sha256"]:
        raise ValueError("FROZEN_ROSTER_HASH_MISMATCH")
    if len(roster["candidates"]) != 27:
        raise ValueError("CANDIDATE_COUNT_DRIFT")
    protocol = ROOT / "docs/strategy_research/g2_r3/exit_aware_r3/EXPERIMENT_FROZEN_PROTOCOL.md"
    if digest(protocol.read_bytes()) != identity["protocol_sha256"]:
        raise ValueError("FROZEN_PROTOCOL_MUTATED")
    if (
        subprocess.check_output(["git", "rev-parse", f"{FREEZE}^"], cwd=ROOT, text=True).strip()
        != BASE
    ):
        raise ValueError("FREEZE_PARENT_MISMATCH")
    return roster


def authorize(year: int, month: int) -> str:
    # This check precedes ANY path construction/stat or download for data.
    if (year, month) not in ALLOWED:
        raise ValueError("RESERVED_OR_UNAUTHORIZED_PERIOD")
    return f"BTCUSDT-1m-{year}-{month:02d}.zip"


def parse(raw: bytes, year: int, month: int):
    authorize(year, month)
    return parse_month(raw, year, month)


def fetch(url: str, destination: Path) -> dict:
    allowed_urls = {
        f"https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/{authorize(y, m)}{suffix}"
        for y, m in ALLOWED
        for suffix in ("", ".CHECKSUM")
    }
    if url not in allowed_urls:
        raise ValueError("SOURCE_URL_NOT_WHITELISTED")
    env = dict(os.environ)
    for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        env.pop(k, None)
    attempts = []
    for n in range(3):
        p = subprocess.run(
            [
                "curl",
                "--silent",
                "--show-error",
                "--proto",
                "=https",
                "--connect-timeout",
                "15",
                "--max-time",
                "90",
                "--output",
                str(destination),
                "--write-out",
                "%{http_code}",
                url,
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=100,
            check=False,
        )
        code = int(p.stdout) if p.stdout.isdigit() else 0
        attempts.append({"attempt": n + 1, "http_status": code, "curl_exit": p.returncode})
        if code == 200 and p.returncode == 0:
            return {"status": "HTTP200", "url": url, "attempts": attempts}
        if code in (403, 451):
            return {"status": "PROVIDER_ACCESS_DENIED_STOP", "url": url, "attempts": attempts}
        if code not in (0, 408, 429, 500, 502, 503, 504):
            break
    return {"status": "DATA_SOURCE_UNAVAILABLE", "url": url, "attempts": attempts}


def download() -> dict:
    roster = verify_freeze()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    old = json.loads(
        (
            ROOT / "evidence/v0.6/b_line/g2_btc_flow_regime_r2/SOURCE_MANIFEST_DEVELOPMENT.json"
        ).read_text()
    )
    result = {
        "schema": "R3_PUBLIC_DEVELOPMENT_SOURCE_V1",
        "freeze_sha": FREEZE,
        "freeze_push_receipt": json.loads((SCRATCH / "freeze-push-receipt.json").read_text()),
        "started_utc": datetime.now(UTC).isoformat(),
        "records": [],
        "historical_ingress_grade": "CURRENT_ARCHIVE_EVENT_TIME_RECONSTRUCTION_DELAY_ASSUMPTION",
        "rights": roster["source_rights"],
        "reserved_period_reads": 0,
        "gate": "NOT_COMPLETED",
        "development_scoring": "NOT_EXECUTED",
    }
    for plan in roster["authorized_archives"]:
        year, month = plan["year"], plan["month"]
        name = authorize(year, month)
        archive = SCRATCH / name
        checksum = SCRATCH / (name + ".CHECKSUM")
        record = {**plan, "zip": fetch(plan["url"], archive)}
        result["records"].append(record)
        if record["zip"]["status"] != "HTTP200":
            result["gate"] = record["zip"]["status"]
            break
        record["checksum"] = fetch(plan["url"] + ".CHECKSUM", checksum)
        if record["checksum"]["status"] != "HTTP200":
            result["gate"] = record["checksum"]["status"]
            break
        try:
            raw = archive.read_bytes()
            record["zip_sha256"] = validate_zip_checksum(raw, checksum.read_text(), name)
            record["checksum_sha256"] = digest(checksum.read_bytes())
            array, metadata = parse(raw, year, month)
            record.update(metadata)
            cache = SCRATCH / f"validated-{year}-{month:02d}.npy"
            np.save(cache, array, allow_pickle=False)
            record["validated_npy_sha256"] = digest(cache.read_bytes())
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                (SCRATCH / name.replace(".zip", ".csv")).write_bytes(
                    z.read(name.replace(".zip", ".csv"))
                )
            prior = next(x for x in old["records"] if (x["year"], x["month"]) == (year, month))
            record["matches_R2_public_zip_hash"] = record["zip_sha256"] == prior["zip_sha256"]
            record["status"] = "VERIFIED_COMPLETE_PUBLIC_MONTH"
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            record["status"] = "SOURCE_INTEGRITY_FAIL"
            record["error_type"] = type(exc).__name__
            result["gate"] = "SOURCE_INTEGRITY_FAIL"
            break
        write("PUBLIC_DEVELOPMENT_SOURCE_MANIFEST.json", result)
        print(
            json.dumps(
                {"source": f"{year}-{month:02d}", "status": record["status"], "rows": len(array)}
            ),
            flush=True,
        )
    if len(result["records"]) == 24 and all(
        x.get("status") == "VERIFIED_COMPLETE_PUBLIC_MONTH" for x in result["records"]
    ):
        result["gate"] = "PASS_PUBLIC_TRADE_PRICE_ONLY"
    result["finished_utc"] = datetime.now(UTC).isoformat()
    result["required_archives"] = 24
    result["rows_admitted"] = sum(x.get("price_rows", 0) for x in result["records"])
    write("PUBLIC_DEVELOPMENT_SOURCE_MANIFEST.json", result)
    print(json.dumps({"gate": result["gate"], "admitted": len(result["records"])}), flush=True)
    return result


if __name__ == "__main__":
    download()
