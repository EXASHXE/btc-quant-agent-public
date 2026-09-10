"""Repository-wide hermeticity guards for the pytest suite.

The low-level file wrappers are deliberately limited to known operational roots.
They complement the SQLite, HTTP, and signed-execution boundary guards so a test
fails before an accidental operational read or write can occur.
"""

from __future__ import annotations

import builtins
import os
import socket
import sqlite3
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from btc_quant_agent.execution.binance_signed import BinanceSignedClient
from btc_quant_agent.microstructure_research import H39ResearchEngine

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ForbiddenTestAccess(BaseException):
    """A test crossed an operational, network, execution, or outcome boundary."""


def _canonical_path(path: str | os.PathLike[str]) -> Path:
    """Resolve symlinks without recursing through monkeypatched ``Path.stat``."""
    resolved = os.path.realpath(os.fspath(path))
    return Path(os.fsdecode(resolved) if isinstance(resolved, bytes) else resolved)


class HermeticAccessGuard:
    """Resolved-path denylist used by the repository-wide pytest fixture."""

    def __init__(self) -> None:
        self._forbidden_roots = {
            _canonical_path(REPOSITORY_ROOT / "data/forward"),
            _canonical_path(REPOSITORY_ROOT / "data/research/h39_validation"),
        }
        self._forbidden_files = {_canonical_path(REPOSITORY_ROOT / "var/quant.db")}
        self._read_bytes_handler: Callable[[Path], bytes] | None = None
        self._write_bytes_handler: Callable[[Path, bytes], None] | None = None
        self._exists_handler: Callable[[Path], bool] | None = None

    def forbid_root(self, path: str | os.PathLike[str]) -> None:
        self._forbidden_roots.add(_canonical_path(path))

    def allow_root(self, path: str | os.PathLike[str]) -> None:
        self._forbidden_roots.discard(_canonical_path(path))

    def forbid_file(self, path: str | os.PathLike[str]) -> None:
        self._forbidden_files.add(_canonical_path(path))

    def allow_file(self, path: str | os.PathLike[str]) -> None:
        self._forbidden_files.discard(_canonical_path(path))

    def read_bytes_unguarded(self, path: Path) -> bytes:
        """Allow test assertions to verify unmutated sentinel bytes without tripping the guard."""
        if self._read_bytes_handler is not None:
            return self._read_bytes_handler(path)
        return path.read_bytes()

    def write_bytes_unguarded(self, path: Path, data: bytes) -> None:
        """Allow test setup to write sentinel bytes to protected paths without tripping the guard."""
        if self._write_bytes_handler is not None:
            self._write_bytes_handler(path, data)
        else:
            path.write_bytes(data)

    def exists_unguarded(self, path: Path) -> bool:
        """Allow test assertions to verify path existence without tripping the guard."""
        if self._exists_handler is not None:
            return self._exists_handler(path)
        return path.exists()

    @staticmethod
    def _is_final_holdout(path: Path) -> bool:
        for component in path.parts:
            normalized = component.lower().replace("-", "_")
            if normalized == "final_holdout" or Path(normalized).stem == "final_holdout":
                return True
        return False

    def check_path(self, candidate: object, operation: str) -> None:
        if isinstance(candidate, int):
            return
        try:
            raw_path = os.fspath(candidate)  # type: ignore[arg-type]
        except TypeError:
            return
        if isinstance(raw_path, bytes):
            raw_path = os.fsdecode(raw_path)
        if raw_path in {"", ":memory:"}:
            return
        resolved = _canonical_path(raw_path)
        if self._is_final_holdout(resolved):
            raise ForbiddenTestAccess(
                f"FORBIDDEN_FINAL_HOLDOUT_ACCESS: {operation} attempted {resolved}"
            )
        if resolved in self._forbidden_files:
            raise ForbiddenTestAccess(
                f"FORBIDDEN_OPERATIONAL_FILE_ACCESS: {operation} attempted {resolved}"
            )
        for root in self._forbidden_roots:
            if resolved == root or root in resolved.parents:
                raise ForbiddenTestAccess(
                    f"FORBIDDEN_OPERATIONAL_ROOT_ACCESS: {operation} attempted {resolved} "
                    f"under {root}"
                )


def _sqlite_candidate(database: object) -> object:
    if not isinstance(database, str) or not database.startswith("file:"):
        return database
    parsed = urllib.parse.urlsplit(database)
    hostname = (parsed.netloc or "").lower()
    if hostname in {"", "localhost"}:
        decoded_path = urllib.parse.unquote(parsed.path)
        if decoded_path in {"", ":memory:"}:
            return ":memory:"
        if (
            os.name == "nt"
            and len(decoded_path) >= 3
            and decoded_path[0] == "/"
            and decoded_path[1].isalpha()
            and decoded_path[2] == ":"
        ):
            decoded_path = decoded_path[1:]
        return decoded_path
    return urllib.parse.unquote(parsed.path)


@pytest.fixture(autouse=True)
def hermetic_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[HermeticAccessGuard]:
    """Block operational filesystem, external network, and execution boundaries."""
    guard = HermeticAccessGuard()

    original_open = builtins.open
    original_path_open = Path.open
    original_exists = Path.exists
    original_is_file = Path.is_file
    original_is_dir = Path.is_dir
    original_stat = Path.stat
    original_iterdir = Path.iterdir
    original_glob = Path.glob
    original_rglob = Path.rglob
    original_mkdir = Path.mkdir
    original_touch = Path.touch
    original_unlink = Path.unlink
    original_os_replace = os.replace
    original_os_rename = os.rename
    original_path_replace = Path.replace
    original_path_rename = Path.rename
    original_sqlite_connect = sqlite3.connect
    original_signed_request = BinanceSignedClient._signed_request

    guard._read_bytes_handler = lambda p: original_path_open(p, "rb").read()
    guard._write_bytes_handler = lambda p, d: original_path_open(p, "wb").write(d)
    guard._exists_handler = lambda p: os.path.exists(os.fspath(p))

    def guarded_open(file: object, *args: Any, **kwargs: Any) -> Any:
        guard.check_path(file, "open")
        return original_open(file, *args, **kwargs)

    def guarded_path_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        guard.check_path(path, "Path.open")
        return original_path_open(path, *args, **kwargs)

    def wrap_path_method(
        operation: str, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        def guarded(path: Path, *args: Any, **kwargs: Any) -> Any:
            guard.check_path(path, operation)
            return original(path, *args, **kwargs)

        return guarded

    def guarded_os_replace(src: object, dst: object, *args: Any, **kwargs: Any) -> Any:
        guard.check_path(src, "os.replace:source")
        guard.check_path(dst, "os.replace:destination")
        return original_os_replace(src, dst, *args, **kwargs)

    def guarded_os_rename(src: object, dst: object, *args: Any, **kwargs: Any) -> Any:
        guard.check_path(src, "os.rename:source")
        guard.check_path(dst, "os.rename:destination")
        return original_os_rename(src, dst, *args, **kwargs)

    def guarded_path_replace(
        path: Path, target: object, *args: Any, **kwargs: Any
    ) -> Path:
        guard.check_path(path, "Path.replace:source")
        guard.check_path(target, "Path.replace:destination")
        return original_path_replace(path, target, *args, **kwargs)

    def guarded_path_rename(
        path: Path, target: object, *args: Any, **kwargs: Any
    ) -> Path:
        guard.check_path(path, "Path.rename:source")
        guard.check_path(target, "Path.rename:destination")
        return original_path_rename(path, target, *args, **kwargs)

    def guarded_sqlite_connect(database: object, *args: Any, **kwargs: Any) -> Any:
        guard.check_path(_sqlite_candidate(database), "sqlite3.connect")
        return original_sqlite_connect(database, *args, **kwargs)

    def forbidden_urlopen(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise ForbiddenTestAccess(
            "FORBIDDEN_EXTERNAL_NETWORK_ACCESS: urllib.request.urlopen was not explicitly mocked"
        )

    def forbidden_dns(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise ForbiddenTestAccess(
            "FORBIDDEN_EXTERNAL_NETWORK_ACCESS: socket.getaddrinfo was not explicitly mocked"
        )

    def guarded_signed_request(
        client: BinanceSignedClient,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        hostname = (urllib.parse.urlsplit(client.base_url).hostname or "").lower()
        if hostname.endswith(("binance.com", "binancefuture.com")):
            raise ForbiddenTestAccess(
                "FORBIDDEN_EXECUTION_TRANSPORT: signed Binance order/testnet/live request blocked"
            )
        return original_signed_request(client, method, path, params)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    monkeypatch.setattr(Path, "exists", wrap_path_method("Path.exists", original_exists))
    monkeypatch.setattr(Path, "is_file", wrap_path_method("Path.is_file", original_is_file))
    monkeypatch.setattr(Path, "is_dir", wrap_path_method("Path.is_dir", original_is_dir))
    monkeypatch.setattr(Path, "stat", wrap_path_method("Path.stat", original_stat))
    monkeypatch.setattr(Path, "iterdir", wrap_path_method("Path.iterdir", original_iterdir))
    monkeypatch.setattr(Path, "glob", wrap_path_method("Path.glob", original_glob))
    monkeypatch.setattr(Path, "rglob", wrap_path_method("Path.rglob", original_rglob))
    monkeypatch.setattr(Path, "mkdir", wrap_path_method("Path.mkdir", original_mkdir))
    monkeypatch.setattr(Path, "touch", wrap_path_method("Path.touch", original_touch))
    monkeypatch.setattr(Path, "unlink", wrap_path_method("Path.unlink", original_unlink))
    monkeypatch.setattr(os, "replace", guarded_os_replace)
    monkeypatch.setattr(os, "rename", guarded_os_rename)
    monkeypatch.setattr(Path, "replace", guarded_path_replace)
    monkeypatch.setattr(Path, "rename", guarded_path_rename)
    monkeypatch.setattr(sqlite3, "connect", guarded_sqlite_connect)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden_urlopen)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden_dns)
    monkeypatch.setattr(BinanceSignedClient, "_signed_request", guarded_signed_request)
    yield guard


@pytest.fixture
def h39_outcome_access_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Fail if a metadata-only H39 test reaches an outcome/future-return loader."""
    calls: list[str] = []

    def block(name: str) -> Callable[..., Any]:
        def blocked(*args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            calls.append(name)
            raise ForbiddenTestAccess(
                f"FORBIDDEN_H39_OUTCOME_ACCESS: metadata-only path called {name}"
            )

        return blocked

    for method_name in (
        "load_outcomes_from_opportunity_shadow",
        "get_canonical_1m_candles",
        "build_observations_for_partition",
    ):
        monkeypatch.setattr(H39ResearchEngine, method_name, block(method_name))
    return calls
