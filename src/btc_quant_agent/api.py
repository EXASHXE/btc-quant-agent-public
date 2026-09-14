from __future__ import annotations

import os
import secrets
import time

from . import __version__
from .config import load_config
from .explain import explain_signal
from .service import QuantService

try:
    from fastapi import Depends, FastAPI, HTTPException
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
except ImportError as exc:  # pragma: no cover - optional dependency guard
    raise RuntimeError("Install the API extra: pip install -e '.[api]'") from exc


_bearer = HTTPBearer(auto_error=False)


def _require_api_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
) -> None:
    expected = os.getenv("BTC_QUANT_API_TOKEN", "")
    if not expected:
        raise HTTPException(503, "BTC_QUANT_API_TOKEN is not configured")
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, expected)
    ):
        raise HTTPException(
            401,
            "invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_app() -> FastAPI:
    app = FastAPI(
        title="BTC Quant Signal API",
        version=__version__,
        dependencies=[Depends(_require_api_token)],
    )
    service = QuantService.create(load_config())

    @app.get("/health")
    def health() -> dict[str, object]:
        return service.health()

    @app.get("/signals/latest")
    def latest() -> dict[str, object]:
        signal = service.repository.latest_signal()
        if signal is None:
            raise HTTPException(404, "signal not found")
        return signal.as_dict()

    @app.get("/signals/{signal_id}")
    def get_signal(signal_id: str) -> dict[str, object]:
        signal = service.repository.get_signal(signal_id)
        if signal is None:
            raise HTTPException(404, "signal not found")
        return signal.as_dict()

    @app.get("/signals/{signal_id}/explanation")
    def explanation(signal_id: str) -> dict[str, object]:
        signal = service.repository.get_signal(signal_id)
        if signal is None:
            raise HTTPException(404, "signal not found")
        return explain_signal(signal)

    @app.get("/performance")
    def performance(days: int = 30) -> dict[str, object]:
        if days < 1 or days > 3650:
            raise HTTPException(422, "days must be between 1 and 3650")
        since_ms = int(time.time() * 1000) - days * 86_400_000
        from .shadow import read_legacy_shadow_performance

        return read_legacy_shadow_performance(service.repository, since_ms)

    @app.get("/execution/status")
    def execution_status() -> dict[str, object]:
        return service.execution.status()

    return app


app = create_app()
