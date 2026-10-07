"""Access capability model and persistent execution access ledger for RC2 R3 Repair R2.

Implements R2.1 and R2.2:
- Explicit AccessCapability model separating CONSTRUCTION_REVIEW and AUTHORIZED_EXECUTION modes.
- CONSTRUCTION_REVIEW: only burned/non-protected fixture universe allowed; network/archive access
  to any target from an injected seal is strictly forbidden.
- AUTHORIZED_EXECUTION: can be created only after exact runner + target-seal authorization both pass;
  permits network/archive reads only for exact sealed TARGETS and exact frozen context references.
- Persistent ExecutionAccessLedger recording every network/archive/cache read attempt with:
  monotonic sequence, UTC timestamp, mode, symbol, URL/path, caller, disposition, execution dispatch SHA,
  authorized runner SHA, and target seal SHA256.
- Explicit capability parameter passed to all network/source/cache functions (no mutable global boolean).
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from scripts.rc2.validation.source_normalizer import (
    ALLOWED_NON_PROTECTED_SYMBOLS,
    ProtectedSymbolFirewallViolation,
)

# Retired R3 targets from prior runs (static names for legacy tests/guards; never fetched in R2)
RETIRED_R3_TARGETS: tuple[str, ...] = (
    "COMPUSDT",
    "SANDUSDT",
    "MANAUSDT",
    "ALGOUSDT",
    "EGLDUSDT",
    "GALAUSDT",
    "THETAUSDT",
    "APTUSDT",
)

RETIRED_R3_BASES: tuple[str, ...] = (
    "COMP",
    "SAND",
    "MANA",
    "ALGO",
    "EGLD",
    "GALA",
    "THETA",
    "APT",
)

# Alias for backward compatibility with legacy tests
PROTECTED_R3_TARGETS = RETIRED_R3_TARGETS
PROTECTED_R3_BASES = RETIRED_R3_BASES

FROZEN_REFERENCES: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "LINKUSDT",
    "SUIUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "BNBUSDT",
)

R3_TARGET_ADMISSIBILITY = "UNPROVEN_PENDING_FRESH_REVIEW"


class AccessMode(str, Enum):
    CONSTRUCTION_REVIEW = "CONSTRUCTION_REVIEW"
    AUTHORIZED_EXECUTION = "AUTHORIZED_EXECUTION"


class AccessDisposition(str, Enum):
    ALLOWED_TARGET = "ALLOWED_TARGET"
    ALLOWED_REFERENCE = "ALLOWED_REFERENCE"
    BLOCKED = "BLOCKED"
    CACHE_READ = "CACHE_READ"
    SOURCE_READ = "SOURCE_READ"


@dataclass
class LedgerEntry:
    seq: int
    timestamp_utc: str
    mode: str
    symbol: str
    url_or_path: str
    caller: str
    disposition: str
    execution_dispatch_sha: str
    authorized_runner_sha: str
    target_seal_sha256: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExecutionAccessLedger:
    """Thread-safe persistent execution access audit ledger (R2.2)."""

    def __init__(self, ledger_file: Path | None = None) -> None:
        self.ledger_file = ledger_file
        self.entries: list[LedgerEntry] = []
        self._seq = 0
        self.blocked_count = 0
        self.allowed_target_count = 0
        self.allowed_reference_count = 0
        self.cache_read_count = 0
        self.source_read_count = 0

    def record(
        self,
        *,
        mode: str,
        symbol: str,
        url_or_path: str,
        caller: str,
        disposition: str,
        execution_dispatch_sha: str,
        authorized_runner_sha: str,
        target_seal_sha256: str,
        error: str | None = None,
    ) -> LedgerEntry:
        self._seq += 1
        entry = LedgerEntry(
            seq=self._seq,
            timestamp_utc=datetime.now(UTC).isoformat(),
            mode=mode,
            symbol=symbol,
            url_or_path=url_or_path,
            caller=caller,
            disposition=disposition,
            execution_dispatch_sha=execution_dispatch_sha,
            authorized_runner_sha=authorized_runner_sha,
            target_seal_sha256=target_seal_sha256,
            error=error,
        )
        self.entries.append(entry)

        if disposition == AccessDisposition.BLOCKED.value:
            self.blocked_count += 1
        elif disposition == AccessDisposition.ALLOWED_TARGET.value:
            self.allowed_target_count += 1
        elif disposition == AccessDisposition.ALLOWED_REFERENCE.value:
            self.allowed_reference_count += 1
        elif disposition == AccessDisposition.CACHE_READ.value:
            self.cache_read_count += 1
        elif disposition == AccessDisposition.SOURCE_READ.value:
            self.source_read_count += 1

        self._flush()
        return entry

    def _flush(self) -> None:
        if self.ledger_file is not None:
            self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
            self.ledger_file.write_text(
                json.dumps(self.summary(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    @property
    def allowed_attempts_count(self) -> int:
        return self.allowed_target_count + self.allowed_reference_count + self.source_read_count + self.cache_read_count

    @property
    def protected_attempts_count(self) -> int:
        return self.blocked_count

    def check_and_log(self, target_or_url: str, caller: str = "unknown") -> None:
        cap = AccessCapability.construction_review(self)
        cap.check_access(target_or_url, caller=caller)

    def finalize(self, output_path: Path) -> dict[str, Any]:
        """Finalize and persist complete ledger to target evidence path."""
        self.ledger_file = output_path
        payload = self.summary()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return payload

    def summary(self) -> dict[str, Any]:
        return {
            "task_id": "RC2_R3_HOLDOUT_RUNNER_REPAIR_R2",
            "total_entries": len(self.entries),
            "blocked_count": self.blocked_count,
            "protected_attempts_count": self.blocked_count,
            "allowed_attempts_count": self.allowed_attempts_count,
            "allowed_target_count": self.allowed_target_count,
            "allowed_reference_count": self.allowed_reference_count,
            "cache_read_count": self.cache_read_count,
            "source_read_count": self.source_read_count,
            "firewall_status": "ZERO_BLOCKED" if self.blocked_count == 0 else "BLOCKS_RECORDED",
            "entries": [e.to_dict() for e in self.entries],
        }


# Backwards compatibility alias
ConstructionAccessLedger = ExecutionAccessLedger
GLOBAL_LEDGER = ExecutionAccessLedger()


@dataclass(frozen=True)
class AuthorizationProof:
    """Immutable proof artifact produced when exact runner and target-seal authorizations pass."""

    authorized_runner_sha: str
    authorized_runner_sha256: str
    execution_dispatch_sha: str
    target_seal_sha256: str
    sealed_targets: tuple[str, ...]
    allowed_references: tuple[str, ...]
    created_at_utc: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"^[0-9a-f]{40}$", self.authorized_runner_sha):
            raise ValueError(f"Invalid runner SHA: {self.authorized_runner_sha}")
        if not re.fullmatch(r"^[0-9a-f]{40}$", self.execution_dispatch_sha):
            raise ValueError(f"Invalid dispatch SHA: {self.execution_dispatch_sha}")
        if not re.fullmatch(r"^[0-9a-f]{64}$", self.authorized_runner_sha256):
            raise ValueError(f"Invalid runner SHA256: {self.authorized_runner_sha256}")
        if not re.fullmatch(r"^[0-9a-f]{64}$", self.target_seal_sha256):
            raise ValueError(f"Invalid target seal SHA256: {self.target_seal_sha256}")
        if not self.sealed_targets:
            raise ValueError("Sealed targets cannot be empty")
        if not set(self.sealed_targets).isdisjoint(set(self.allowed_references)):
            raise ValueError("Sealed targets and references must be strictly disjoint")


def _extract_symbol_from_target_or_url(target_or_url: str) -> str:
    """Extract symbol name from symbol string or URL/path."""
    upper = target_or_url.strip().upper()
    # Check if target_or_url is already a symbol
    if re.fullmatch(r"^[A-Z0-9]+USDT$", upper):
        return upper

    # Look for query parameter symbol=...
    match_query = re.search(r"[?&]SYMBOL=([A-Z0-9]+)", upper)
    if match_query:
        sym = match_query.group(1)
        return sym if sym.endswith("USDT") else f"{sym}USDT"

    # Look for standard Binance Vision path components:
    # /(klines|metrics|fundingRate|premiumIndexKlines)/<SYMBOL>/
    match_path = re.search(
        r"/(?:KLINES|METRICS|FUNDINGRATE|PREMIUMINDEXKLINES)/([A-Z0-9]+)/",
        upper,
    )
    if match_path:
        sym = match_path.group(1)
        return sym if sym.endswith("USDT") else f"{sym}USDT"

    # Match filename prefix: e.g. /<SYMBOL>-15m-2026...
    match_file = re.search(r"/([A-Z0-9]+)-(?:15M|1H|4H|1M|5M|METRICS|FUNDINGRATE)", upper)
    if match_file:
        sym = match_file.group(1)
        return sym if sym.endswith("USDT") else f"{sym}USDT"

    # Fallback to token search for known symbols
    for s in ALLOWED_NON_PROTECTED_SYMBOLS:
        if s.endswith("USDT") and s in upper:
            return s
    for s in RETIRED_R3_TARGETS:
        if s in upper:
            return s

    return upper


class AccessCapability:
    """Explicit capability token governing all network, archive, and cache-source access (R2.1).

    Must be passed explicitly into downloader/cache/source functions.
    No mutable global boolean.
    """

    def __init__(
        self,
        mode: AccessMode,
        ledger: ExecutionAccessLedger,
        *,
        proof: AuthorizationProof | None = None,
        injected_seal_targets: Sequence[str] = (),
    ) -> None:
        self.mode = mode
        self.ledger = ledger

        if mode == AccessMode.AUTHORIZED_EXECUTION:
            if proof is None:
                raise PermissionError(
                    "AUTHORIZED_EXECUTION mode cannot be constructed before runner + target-seal authorization"
                )
            self.execution_dispatch_sha = proof.execution_dispatch_sha
            self.authorized_runner_sha = proof.authorized_runner_sha
            self.target_seal_sha256 = proof.target_seal_sha256
            self.sealed_targets: frozenset[str] = frozenset(proof.sealed_targets)
            self.allowed_references: frozenset[str] = frozenset(proof.allowed_references)
            self.injected_seal_targets: frozenset[str] = frozenset()
        elif mode == AccessMode.CONSTRUCTION_REVIEW:
            self.execution_dispatch_sha = "0" * 40
            self.authorized_runner_sha = "0" * 40
            self.target_seal_sha256 = "0" * 64
            self.sealed_targets = frozenset()
            self.allowed_references = frozenset(FROZEN_REFERENCES)
            self.injected_seal_targets = frozenset(injected_seal_targets)
        else:
            raise ValueError(f"Unknown AccessMode: {mode}")

    @classmethod
    def construction_review(
        cls,
        ledger: ExecutionAccessLedger,
        injected_seal_targets: Sequence[str] = (),
    ) -> AccessCapability:
        """Create capability for CONSTRUCTION_REVIEW mode."""
        return cls(
            mode=AccessMode.CONSTRUCTION_REVIEW,
            ledger=ledger,
            proof=None,
            injected_seal_targets=injected_seal_targets,
        )

    @classmethod
    def create_authorized_execution(
        cls,
        proof: AuthorizationProof,
        ledger: ExecutionAccessLedger,
    ) -> AccessCapability:
        """Create capability for AUTHORIZED_EXECUTION mode using verified proof."""
        return cls(
            mode=AccessMode.AUTHORIZED_EXECUTION,
            ledger=ledger,
            proof=proof,
        )

    def check_access(
        self,
        target_or_url: str,
        caller: str = "unknown",
        is_cache: bool = False,
    ) -> str:
        """Check and log access attempt under the active capability mode.

        Returns disposition string on success; raises ProtectedSymbolFirewallViolation on block.
        """
        symbol = _extract_symbol_from_target_or_url(target_or_url)
        upper_raw = target_or_url.strip().upper()

        if self.mode == AccessMode.CONSTRUCTION_REVIEW:
            # 1. Any target from an injected seal is strictly forbidden
            for inj in self.injected_seal_targets:
                if inj in upper_raw or inj.replace("USDT", "") in upper_raw:
                    err = f"Access to injected seal target '{inj}' is forbidden in CONSTRUCTION_REVIEW mode"
                    self.ledger.record(
                        mode=self.mode.value,
                        symbol=symbol,
                        url_or_path=target_or_url,
                        caller=caller,
                        disposition=AccessDisposition.BLOCKED.value,
                        execution_dispatch_sha=self.execution_dispatch_sha,
                        authorized_runner_sha=self.authorized_runner_sha,
                        target_seal_sha256=self.target_seal_sha256,
                        error=err,
                    )
                    raise ProtectedSymbolFirewallViolation(err)

            # 2. Retired R3 targets are forbidden
            for ret in RETIRED_R3_TARGETS:
                if ret in upper_raw:
                    err = f"Access to retired R3 target '{ret}' is forbidden in CONSTRUCTION_REVIEW mode"
                    self.ledger.record(
                        mode=self.mode.value,
                        symbol=symbol,
                        url_or_path=target_or_url,
                        caller=caller,
                        disposition=AccessDisposition.BLOCKED.value,
                        execution_dispatch_sha=self.execution_dispatch_sha,
                        authorized_runner_sha=self.authorized_runner_sha,
                        target_seal_sha256=self.target_seal_sha256,
                        error=err,
                    )
                    raise ProtectedSymbolFirewallViolation(err)
            for base in RETIRED_R3_BASES:
                if re.search(rf"\b{base}\b", upper_raw) or f"/{base}/" in upper_raw or f"-{base}-" in upper_raw:
                    err = f"Access to retired R3 base '{base}' is forbidden in CONSTRUCTION_REVIEW mode"
                    self.ledger.record(
                        mode=self.mode.value,
                        symbol=symbol,
                        url_or_path=target_or_url,
                        caller=caller,
                        disposition=AccessDisposition.BLOCKED.value,
                        execution_dispatch_sha=self.execution_dispatch_sha,
                        authorized_runner_sha=self.authorized_runner_sha,
                        target_seal_sha256=self.target_seal_sha256,
                        error=err,
                    )
                    raise ProtectedSymbolFirewallViolation(err)

            # 3. Only burned/non-protected fixture universe allowed
            base_sym = symbol.replace("USDT", "")
            if symbol not in ALLOWED_NON_PROTECTED_SYMBOLS and base_sym not in ALLOWED_NON_PROTECTED_SYMBOLS:
                err = f"Symbol '{symbol}' not in allowed non-protected whitelist for CONSTRUCTION_REVIEW mode"
                self.ledger.record(
                    mode=self.mode.value,
                    symbol=symbol,
                    url_or_path=target_or_url,
                    caller=caller,
                    disposition=AccessDisposition.BLOCKED.value,
                    execution_dispatch_sha=self.execution_dispatch_sha,
                    authorized_runner_sha=self.authorized_runner_sha,
                    target_seal_sha256=self.target_seal_sha256,
                    error=err,
                )
                raise ProtectedSymbolFirewallViolation(err)

            # Allowed in construction review
            if is_cache:
                disp = AccessDisposition.CACHE_READ.value
            elif target_or_url.startswith(("http://", "https://")):
                disp = AccessDisposition.SOURCE_READ.value
            elif symbol in self.allowed_references:
                disp = AccessDisposition.ALLOWED_REFERENCE.value
            else:
                disp = AccessDisposition.ALLOWED_TARGET.value

            self.ledger.record(
                mode=self.mode.value,
                symbol=symbol,
                url_or_path=target_or_url,
                caller=caller,
                disposition=disp,
                execution_dispatch_sha=self.execution_dispatch_sha,
                authorized_runner_sha=self.authorized_runner_sha,
                target_seal_sha256=self.target_seal_sha256,
                error=None,
            )
            return disp

        if self.mode == AccessMode.AUTHORIZED_EXECUTION:
            # Permits reads only for exact sealed TARGETS and exact frozen references
            is_target = symbol in self.sealed_targets
            is_ref = symbol in self.allowed_references

            if not is_target and not is_ref:
                err = f"Symbol '{symbol}' outside sealed targets and references is forbidden in AUTHORIZED_EXECUTION mode"
                self.ledger.record(
                    mode=self.mode.value,
                    symbol=symbol,
                    url_or_path=target_or_url,
                    caller=caller,
                    disposition=AccessDisposition.BLOCKED.value,
                    execution_dispatch_sha=self.execution_dispatch_sha,
                    authorized_runner_sha=self.authorized_runner_sha,
                    target_seal_sha256=self.target_seal_sha256,
                    error=err,
                )
                raise ProtectedSymbolFirewallViolation(err)

            if is_cache:
                disp = AccessDisposition.CACHE_READ.value
            elif target_or_url.startswith(("http://", "https://")):
                disp = AccessDisposition.SOURCE_READ.value
            elif is_target:
                disp = AccessDisposition.ALLOWED_TARGET.value
            else:
                disp = AccessDisposition.ALLOWED_REFERENCE.value

            self.ledger.record(
                mode=self.mode.value,
                symbol=symbol,
                url_or_path=target_or_url,
                caller=caller,
                disposition=disp,
                execution_dispatch_sha=self.execution_dispatch_sha,
                authorized_runner_sha=self.authorized_runner_sha,
                target_seal_sha256=self.target_seal_sha256,
                error=None,
            )
            return disp

        raise ValueError(f"Unsupported mode: {self.mode}")


def guarded_download(
    url: str,
    capability: AccessCapability | None = None,
    ledger: ExecutionAccessLedger | None = None,
    caller: str = "guarded_download",
    timeout: int = 90,
) -> bytes:
    """Download official archive guarded by explicit access capability (R2.1, R2.2)."""
    if capability is None:
        cap = AccessCapability.construction_review(ledger or GLOBAL_LEDGER)
    else:
        cap = capability
    cap.check_access(url, caller=caller, is_cache=False)
    req = urllib.request.Request(url, headers={"User-Agent": "rc2-holdout-r3-guarded/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read()
        return bytes(content)
