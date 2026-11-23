"""Verify zero raw hostnames, private IPs, tokens, or secrets across text files."""

from __future__ import annotations

import re
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_SUFFIXES = {".whl", ".pyc", ".sqlite", ".png"}
TEXT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PRIVATE_KEY_HEADER", re.compile(r"BEGIN\s+[A-Z0-9 ]*PRIVATE KEY")),
    ("BEARER_LITERAL", re.compile(r"\bBearer\s+(?!\[REDACTED\])[A-Za-z0-9._\-+/=]{6,}")),
    ("TENANT_TOKEN_LITERAL", re.compile(r"\bt-[A-Za-z0-9_-]{6,}")),
    ("BINANCE_API_KEY_HEADER", re.compile("X-MBX-" + "APIKEY")),
    (
        "PRIVATE_IPV4",
        re.compile(r"\b(?:10\.\d+|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d+\.\d+\b"),
    ),
)


def main() -> None:
    hostname = socket.gethostname()
    hits: list[str] = []
    scanned = 0
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT).as_posix()
        if rel == ".qa" or rel.startswith(".qa/") or not path.is_file():
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        if rel == "tools/sanitize_check.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        scanned += 1
        if hostname and len(hostname) > 2 and hostname in text:
            hits.append(f"{rel}:RAW_HOSTNAME")
        for label, pat in TEXT_RULES:
            if pat.search(text):
                hits.append(f"{rel}:{label}")
    if hits:
        raise SystemExit(f"SANITIZATION_FAILED {hits}")
    print(f"PASS sanitization_check scanned={scanned} hits=0")


if __name__ == "__main__":
    main()
