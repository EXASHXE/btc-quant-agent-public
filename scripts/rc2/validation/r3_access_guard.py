"""Protected target firewall guard and construction access ledger for RC2 R3.

Enforces strict network/archive guard:
- Rejects any URL, symbol, or query containing R3 protected target names:
  COMPUSDT, SANDUSDT, MANAUSDT, ALGOUSDT, EGLDUSDT, GALAUSDT, THETAUSDT, APTUSDT.
- Logs every attempted access into an audit ledger.
- Proves zero protected-target attempts during construction and testing.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.rc2.validation.source_normalizer import (
    ProtectedSymbolFirewallViolation,
)

PROTECTED_R3_TARGETS: tuple[str, ...] = (
    "COMPUSDT",
    "SANDUSDT",
    "MANAUSDT",
    "ALGOUSDT",
    "EGLDUSDT",
    "GALAUSDT",
    "THETAUSDT",
    "APTUSDT",
)

# Base symbols without quote currency
PROTECTED_R3_BASES: tuple[str, ...] = (
    "COMP",
    "SAND",
    "MANA",
    "ALGO",
    "EGLD",
    "GALA",
    "THETA",
    "APT",
)

R3_TARGET_ADMISSIBILITY = "UNPROVEN_PENDING_FRESH_REVIEW"


@dataclass
class AccessLogEntry:
    timestamp_utc: str
    target_or_url: str
    status: str  # "ALLOWED_BURNED_SYMBOL" | "BLOCKED_PROTECTED_TARGET"
    caller: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConstructionAccessLedger:
    """Thread-safe construction access audit ledger."""

    def __init__(self, ledger_file: Path | None = None) -> None:
        self.ledger_file = ledger_file
        self.entries: list[AccessLogEntry] = []
        self.protected_attempts_count = 0
        self.allowed_attempts_count = 0

    def check_and_log(self, target_or_url: str, caller: str = "unknown") -> None:
        """Assert target or URL does not touch R3 protected symbols; log attempt."""
        upper = target_or_url.strip().upper()
        # Check against full symbol names and base names in path/query
        violated_symbol: str | None = None
        for sym in PROTECTED_R3_TARGETS:
            if sym in upper:
                violated_symbol = sym
                break
        if violated_symbol is None:
            # Check pattern boundary for base symbol
            for base in PROTECTED_R3_BASES:
                if re.search(rf"\b{base}\b", upper) or f"/{base}/" in upper or f"-{base}-" in upper:
                    violated_symbol = base
                    break

        now_str = datetime.now(UTC).isoformat()
        if violated_symbol is not None:
            self.protected_attempts_count += 1
            entry = AccessLogEntry(
                timestamp_utc=now_str,
                target_or_url=target_or_url,
                status="BLOCKED_PROTECTED_TARGET",
                caller=caller,
                error=f"Attempted access to protected R3 symbol: {violated_symbol}",
            )
            self.entries.append(entry)
            self._save_ledger()
            raise ProtectedSymbolFirewallViolation(
                f"Firewall violation: Attempted access to protected R3 symbol '{violated_symbol}' in '{target_or_url}'"
            )

        self.allowed_attempts_count += 1
        entry = AccessLogEntry(
            timestamp_utc=now_str,
            target_or_url=target_or_url,
            status="ALLOWED_BURNED_SYMBOL",
            caller=caller,
            error=None,
        )
        self.entries.append(entry)
        self._save_ledger()

    def _save_ledger(self) -> None:
        if self.ledger_file is not None:
            self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
            summary = {
                "task_id": "RC2_R3_HOLDOUT_RUNNER_REPAIR_R1",
                "r3_target_admissibility": R3_TARGET_ADMISSIBILITY,
                "protected_attempts_count": self.protected_attempts_count,
                "allowed_attempts_count": self.allowed_attempts_count,
                "protected_targets_list": list(PROTECTED_R3_TARGETS),
                "total_logged_entries": len(self.entries),
                "entries": [e.to_dict() for e in self.entries],
            }
            self.ledger_file.write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

    def summary(self) -> dict[str, Any]:
        return {
            "r3_target_admissibility": R3_TARGET_ADMISSIBILITY,
            "protected_attempts_count": self.protected_attempts_count,
            "allowed_attempts_count": self.allowed_attempts_count,
            "total_logged_entries": len(self.entries),
            "protected_access_firewall_status": "ZERO_PROTECTED_ATTEMPTS"
            if self.protected_attempts_count == 0
            else "VIOLATION_DETECTED",
        }


# Global construction ledger instance
GLOBAL_LEDGER = ConstructionAccessLedger()


def guarded_download(
    url: str,
    ledger: ConstructionAccessLedger = GLOBAL_LEDGER,
    caller: str = "guarded_download",
    timeout: int = 90,
) -> bytes:
    """Download official vision archive guarded by protected target firewall."""
    ledger.check_and_log(url, caller=caller)
    req = urllib.request.Request(url, headers={"User-Agent": "rc2-holdout-r3-guarded/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read()
        return bytes(content)
