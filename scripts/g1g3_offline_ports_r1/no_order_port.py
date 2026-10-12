"""NoOrderPort: Runtime & static AST guard against real network, orders, and protected paths.

Enforces:
1. Zero broker/exchange order, cancel, transfer, listenKey, or account-read authority.
2. Zero public or private non-loopback network traffic; loopback 127.0.0.1 / ::1
   allowed strictly when allow_loopback=True AND (host, port) is in the explicit allowlist.
3. Lexical denial of protected data/credential paths before any filesystem stat/open.
4. Exact SHA-256 immutability of read-only Codex G1 core C4 and static AST import verification.
"""

from __future__ import annotations

import ast
import hashlib
import os
import socket
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from scripts.g1_offline_preview_r1.model import SafetyViolation

OWN_SCRATCH = Path("/tmp/btc-g1g3_offline_ports_r1")
REPO_ROOT = Path(__file__).resolve().parents[2]

PINNED_G1_C4_MANIFEST: dict[str, str] = {
    "scripts/g1_offline_preview_r1/__main__.py": "65dcb3d726ed5a8b828ed0288d10fa9f51340f4cf3a70cf44b4a2c62e21cd5fb",
    "scripts/g1_offline_preview_r1/analysis_schema.json": "dea9da8a0f03740894f117a7da56cd7c99476aa3058bdf2a665107019a98e1cb",
    "scripts/g1_offline_preview_r1/fixtures/long_24h.json": "ae6c70f7c26b752df1cfc2cc803d6a941a62e1699749365f4902d335cb93fe4f",
    "scripts/g1_offline_preview_r1/fixtures/short_24h.json": "d6bf849411f82db75f433f91985b7c8698fbbd1834685fb706453de3cad1dc11",
    "scripts/g1_offline_preview_r1/fixtures.py": "9999418e5cb1f9fd98d1f4cae5c1d460a9593b28c9f7f338a3043374fa4ea8b0",
    "scripts/g1_offline_preview_r1/model.py": "086d6ec8747f82d59b6f8f42bfefd2d9c61e5f962707b4f9119f784741dd206e",
    "scripts/g1_offline_preview_r1/reducer.py": "c0114c8cc0480b3c4c637217363833590fb231ad8529c93f85f574ce161ed89e",
    "scripts/g1_offline_preview_r1/storage.py": "9e4ac21c501e48734a750021f8ea2f51f4f06ecc0ee2e798647718b4c453f101",
    "tests/test_v06_g1_offline_preview_r1_core.py": "d5679c583d1122f2ce877f7686e477acc869637e7ee21643fbee1f5058e52da3",
    "tests/test_v06_g1_offline_preview_r1_decimal_and_ports.py": "7a0fef994f1548ebe0813836b41340519f49dcefbe46a5d5850b23392ee731e2",
    "tests/test_v06_g1_offline_preview_r1_exit_safety.py": "8efc412469fa5be183bca05dacd7ba255e7ad1f20f93e39706698e8bc4cd71f0",
    "tests/test_v06_g1_offline_preview_r1_process_recovery.py": "d6c99ea559f9c4a8c384568af52ed6aa556ecca896d9add58ca9aa5c07f04249",
    "tests/test_v06_g1_offline_preview_r1_wal.py": "41d53a583502b4d28da92dfa9f8c9e2dde73522509009739418d9dfff42c8585",
}

FORBIDDEN_LEXICAL_SUBSTRINGS = (
    "quant-agent/data",
    "quant-agent-sanitized",
    "final_holdout",
    "final-holdout",
    "h39_validation",
    "data/forward",
    "var/quant.db",
    ".env",
    ".ssh",
    "id_rsa",
    "id_ed25519",
    "credentials",
    "forward_public_feed_r1",
    "forward_shadow_research_r1",
)

FORBIDDEN_EXTERNAL_HOSTS = (
    "binance.com",
    "binancefuture.com",
    "binance.vision",
    "openai.com",
    "googleapis.com",
    "anthropic.com",
    "feishu.cn",
    "larksuite.com",
)


def guard_lexical_path(candidate: str | os.PathLike[str]) -> str:
    """Lexical path check executed BEFORE any stat, exists, open, or resolve syscall."""
    if not isinstance(candidate, (str, os.PathLike)):
        raise SafetyViolation("PATH_INVALID")
    raw = os.fspath(candidate)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not raw or "\x00" in raw:
        raise SafetyViolation("PATH_INVALID")
    normalized = raw.replace("\\", "/").lower()
    parts = [p for p in normalized.split("/") if p]
    if ".." in parts:
        raise SafetyViolation("PATH_TRAVERSAL_FORBIDDEN")
    for forbidden in FORBIDDEN_LEXICAL_SUBSTRINGS:
        if forbidden in normalized:
            raise SafetyViolation("PROTECTED_PATH_FORBIDDEN")
    return raw


def guard_scratch_dir(path: str | os.PathLike[str], *, temporary: bool = False) -> Path:
    """Ensure writable state/outbox directory is strictly inside OWN_SCRATCH (or /tmp in tests)."""
    raw = guard_lexical_path(path)
    p = Path(raw)
    if not p.is_absolute():
        raise SafetyViolation("PATH_SCOPE")
    base = Path("/tmp") if temporary else OWN_SCRATCH
    if p != base and base not in p.parents:
        raise SafetyViolation("PATH_SCOPE")
    for ancestor in [base, *reversed([a for a in p.parents if a != base and base in a.parents]), p]:
        if ancestor.is_symlink():
            raise SafetyViolation("PATH_SYMLINK")
    return p


class NoOrderPort:
    """Explicit fail-closed order/account/broker port guard.

    Rejects any attempt to load signed clients, submit/cancel/modify orders,
    transfer funds, open listenKey, read private accounts, or target TESTNET/LIVE.
    """

    def __init__(self) -> None:
        self.rejected_order_attempts = 0
        self.rejected_account_attempts = 0
        self.rejected_endpoint_attempts = 0
        self.actual_private_or_network_calls = 0

    def _reject_order(self, operation: str) -> None:
        self.rejected_order_attempts += 1
        raise SafetyViolation(f"NO_ORDER_PORT_FORBIDDEN:{operation}")

    def _reject_account(self, operation: str) -> None:
        self.rejected_account_attempts += 1
        raise SafetyViolation(f"NO_ACCOUNT_PORT_FORBIDDEN:{operation}")

    def submit_order(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self._reject_order("SUBMIT_ORDER")

    def place_order(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self._reject_order("PLACE_ORDER")

    def cancel_order(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self._reject_order("CANCEL_ORDER")

    def modify_order(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self._reject_order("MODIFY_ORDER")

    def transfer_funds(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self._reject_order("TRANSFER_FUNDS")

    def create_listen_key(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self._reject_account("CREATE_LISTEN_KEY")

    def read_account_balance(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self._reject_account("READ_ACCOUNT_BALANCE")

    def load_signed_client(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self._reject_account("LOAD_SIGNED_CLIENT")

    def validate_endpoint_url(
        self,
        url: str,
        *,
        allow_loopback: bool,
        allowed_endpoints: set[tuple[str, int]] | None = None,
    ) -> tuple[str, int, str]:
        """Validate that an endpoint URL is strictly allowlisted HTTP loopback."""
        if not isinstance(url, str) or not url:
            self.rejected_endpoint_attempts += 1
            raise SafetyViolation("ENDPOINT_URL_INVALID")
        parsed = urllib.parse.urlsplit(url)
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").lower()
        port = parsed.port
        if any(host == h or host.endswith("." + h) for h in FORBIDDEN_EXTERNAL_HOSTS):
            self.rejected_endpoint_attempts += 1
            raise SafetyViolation("EXTERNAL_PROVIDER_ENDPOINT_FORBIDDEN")
        if not allow_loopback:
            self.rejected_endpoint_attempts += 1
            raise SafetyViolation("NETWORK_DISABLED_BY_DEFAULT")
        if scheme != "http":
            self.rejected_endpoint_attempts += 1
            raise SafetyViolation("NON_HTTP_LOOPBACK_FORBIDDEN")
        if host not in ("127.0.0.1", "::1") or port is None or not (1 <= port <= 65535):
            self.rejected_endpoint_attempts += 1
            raise SafetyViolation("NON_LOOPBACK_HOST_FORBIDDEN")
        if allowed_endpoints is None or (host, int(port)) not in allowed_endpoints:
            self.rejected_endpoint_attempts += 1
            raise SafetyViolation("LOOPBACK_PORT_NOT_ALLOWLISTED")
        return host, int(port), parsed.path or "/"

    def telemetry(self) -> dict[str, int]:
        return {
            "rejected_order_attempts": self.rejected_order_attempts,
            "rejected_account_attempts": self.rejected_account_attempts,
            "rejected_endpoint_attempts": self.rejected_endpoint_attempts,
            "actual_private_or_network_calls": self.actual_private_or_network_calls,
        }


class LoopbackSocketGuard:
    """Context manager that intercepts socket connections and enforces loopback allowlist."""

    def __init__(
        self,
        *,
        allow_loopback: bool = False,
        allowed_endpoints: set[tuple[str, int]] | None = None,
    ) -> None:
        self.allow_loopback = allow_loopback
        self.allowed_endpoints: set[tuple[str, int]] = set(allowed_endpoints or set())
        self.blocked_attempts: list[tuple[str, Any]] = []
        self.allowed_loopback_calls: list[tuple[str, int]] = []
        self._orig_connect: Any = None
        self._orig_connect_ex: Any = None
        self._orig_create_connection: Any = None
        self._orig_getaddrinfo: Any = None
        self._orig_urlopen: Any = None

    def register_loopback_endpoint(self, host: str, port: int) -> None:
        if host not in ("127.0.0.1", "::1") or not (1 <= int(port) <= 65535):
            raise SafetyViolation("NON_LOOPBACK_HOST_FORBIDDEN")
        self.allowed_endpoints.add((host, int(port)))

    def _check_address(self, address: Any) -> tuple[str, int]:
        if not self.allow_loopback:
            self.blocked_attempts.append(("connect_disabled", address))
            raise SafetyViolation("NETWORK_DISABLED_BY_DEFAULT")
        if not isinstance(address, tuple) or len(address) < 2:
            self.blocked_attempts.append(("bad_address", address))
            raise SafetyViolation("NON_LOOPBACK_HOST_FORBIDDEN")
        host, port = address[0], address[1]
        if not isinstance(host, str) or not isinstance(port, int):
            self.blocked_attempts.append(("bad_host_port", address))
            raise SafetyViolation("NON_LOOPBACK_HOST_FORBIDDEN")
        if host not in ("127.0.0.1", "::1"):
            self.blocked_attempts.append(("non_loopback_host", address))
            raise SafetyViolation("NON_LOOPBACK_HOST_FORBIDDEN")
        if (host, port) not in self.allowed_endpoints:
            self.blocked_attempts.append(("unallowlisted_port", address))
            raise SafetyViolation("LOOPBACK_PORT_NOT_ALLOWLISTED")
        self.allowed_loopback_calls.append((host, port))
        return host, port

    def __enter__(self):
        self._orig_connect = socket.socket.connect
        self._orig_connect_ex = socket.socket.connect_ex
        self._orig_create_connection = socket.create_connection
        self._orig_getaddrinfo = socket.getaddrinfo
        self._orig_urlopen = urllib.request.urlopen

        guard = self
        orig_connect = self._orig_connect

        def guarded_connect(sock: socket.socket, address: Any) -> Any:
            guard._check_address(address)
            return orig_connect(sock, address)

        def guarded_connect_ex(sock: socket.socket, address: Any) -> int:
            guard._check_address(address)
            return int(guard._orig_connect_ex(sock, address))

        def guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
            host, port = guard._check_address(address)
            timeout = args[0] if args else kwargs.get("timeout", socket._GLOBAL_DEFAULT_TIMEOUT)
            family = socket.AF_INET if host == "127.0.0.1" else socket.AF_INET6
            sock = socket.socket(family, socket.SOCK_STREAM)
            try:
                if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT and timeout is not None:
                    sock.settimeout(float(timeout))
                orig_connect(sock, (host, port) if family == socket.AF_INET else (host, port, 0, 0))
                return sock
            except Exception:
                sock.close()
                raise

        def guarded_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            if (
                guard.allow_loopback
                and isinstance(host, str)
                and host in ("127.0.0.1", "::1")
                and isinstance(port, int)
                and (host, port) in guard.allowed_endpoints
            ):
                family = socket.AF_INET if host == "127.0.0.1" else socket.AF_INET6
                sockaddr = (host, port) if family == socket.AF_INET else (host, port, 0, 0)
                return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]
            guard.blocked_attempts.append(("dns_forbidden", (host, port)))
            raise SafetyViolation("DNS_RESOLUTION_FORBIDDEN")

        def guarded_urlopen(*args: Any, **kwargs: Any) -> Any:
            guard.blocked_attempts.append(("urlopen_forbidden", args[:1]))
            raise SafetyViolation("URLOPEN_DIRECT_FORBIDDEN")

        socket.socket.connect = guarded_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = guarded_connect_ex  # type: ignore[method-assign]
        socket.create_connection = guarded_create_connection  # type: ignore[assignment]
        socket.getaddrinfo = guarded_getaddrinfo  # type: ignore[assignment]
        urllib.request.urlopen = guarded_urlopen  # type: ignore[assignment]
        return self

    def __exit__(self, *_: object) -> None:
        if self._orig_connect is not None:
            socket.socket.connect = self._orig_connect  # type: ignore[method-assign]
        if self._orig_connect_ex is not None:
            socket.socket.connect_ex = self._orig_connect_ex  # type: ignore[method-assign]
        if self._orig_create_connection is not None:
            socket.create_connection = self._orig_create_connection  # type: ignore[assignment]
        if self._orig_getaddrinfo is not None:
            socket.getaddrinfo = self._orig_getaddrinfo  # type: ignore[assignment]
        if self._orig_urlopen is not None:
            urllib.request.urlopen = self._orig_urlopen  # type: ignore[assignment]


def verify_g1_core_immutability(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Verify every file in the read-only Codex G1 C4 manifest matches its pinned SHA-256."""
    verified: dict[str, str] = {}
    for rel_path, expected_sha in sorted(PINNED_G1_C4_MANIFEST.items()):
        target = repo_root / rel_path
        if not target.is_file() or target.is_symlink():
            raise SafetyViolation(f"G1_CORE_MISSING_OR_SYMLINK:{rel_path}")
        actual_sha = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual_sha != expected_sha:
            raise SafetyViolation(f"G1_CORE_MUTATED:{rel_path}")
        verified[rel_path] = actual_sha
    return {
        "verified_count": len(verified),
        "all_matched": True,
        "files": verified,
    }


def verify_static_ast_and_core_immutability(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Run static AST import/call surface verification on G1 core and G1/G3 sidecar."""
    core_report = verify_g1_core_immutability(repo_root)
    forbidden_top_imports = {
        "btc_quant_agent",
        "binance",
        "openai",
        "google",
        "anthropic",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
        "dotenv",
    }
    forbidden_attr_calls = {
        "system",
        "popen",
        "signed_request",
        "_signed_request",
    }
    sidecar_dir = repo_root / "scripts/g1g3_offline_ports_r1"
    scanned_files: list[str] = []
    for py_file in sorted(sidecar_dir.glob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                for mod in modules:
                    top = mod.split(".")[0]
                    if top in forbidden_top_imports or mod.startswith("btc_quant_agent"):
                        raise SafetyViolation(f"FORBIDDEN_IMPORT:{py_file.name}:{mod}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in forbidden_attr_calls
            ):
                raise SafetyViolation(f"FORBIDDEN_CALL:{py_file.name}:{node.func.attr}")
        scanned_files.append(str(py_file.relative_to(repo_root)))
    return {
        "core_immutability": core_report,
        "sidecar_files_scanned": scanned_files,
        "forbidden_imports_found": 0,
        "forbidden_calls_found": 0,
        "production_src_imported": False,
    }
