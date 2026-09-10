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


class HermeticAccessGuard:
    """Resolved-path denylist used by the repository-wide pytest fixture."""

    def __init__(self) -> None:
        self._forbidden_roots = {
            (REPOSITORY_ROOT / "data/forward").resolve(),
            (REPOSITORY_ROOT / "data/research/h39_validation").resolve(),
        }
        self._forbidden_files = {(REPOSITORY_ROOT / "var/quant.db").resolve()}

    def forbid_root(self, path: str | os.PathLike[str]) -> None:
        self._forbidden_roots.add(Path(path).resolve())

    def forbid_file(self, path: str | os.PathLike[str]) -> None:
        self._forbidden_files.add(Path(path).resolve())

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
        resolved = Path(raw_path).resolve()
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
    uri_path = database[5:].split("?", maxsplit=1)[0]
    if uri_path in {"", ":memory:"}:
        return ":memory:"
    return urllib.parse.unquote(uri_path)


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
    original_sqlite_connect = sqlite3.connect
    original_signed_request = BinanceSignedClient._signed_request

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
        if hostname.endswith("binance.com") or hostname.endswith("binancefuture.com"):
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
