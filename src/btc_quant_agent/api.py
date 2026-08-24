from __future__ import annotations

import time

from .config import load_config
from .execution.guard import ExecutionBlocked
from .explain import explain_signal
from .service import QuantService

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover - optional dependency guard
    raise RuntimeError("Install the API extra: pip install -e '.[api]'") from exc


class DecisionRequest(BaseModel):
    decision: str
    actual_entry: float | None = None


class ConfirmationRequest(BaseModel):
    confirmation_hash: str


class ClosePreviewRequest(BaseModel):
    symbol: str = "BTCUSDT"


def create_app() -> FastAPI:
    app = FastAPI(title="BTC Quant Signal API", version="0.2.1")
    service = QuantService.create(load_config())

    @app.get("/health")
    def health() -> dict[str, object]:
        return service.health()

    @app.post("/scan")
    def scan() -> dict[str, object]:
        return service.scan().as_dict()

    @app.get("/signals/latest")
    def latest() -> dict[str, object]:
        service.repository.expire_signals(int(time.time() * 1000))
        signal = service.repository.latest_signal()
        if signal is None:
            raise HTTPException(404, "signal not found")
        return signal.as_dict()

    @app.get("/signals/{signal_id}")
    def get_signal(signal_id: str) -> dict[str, object]:
        service.repository.expire_signals(int(time.time() * 1000))
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

    @app.post("/signals/{signal_id}/decision")
    def decision(signal_id: str, request: DecisionRequest) -> dict[str, str]:
        if request.decision.upper() not in {"ACCEPT", "IGNORE"}:
            raise HTTPException(422, "decision must be ACCEPT or IGNORE")
        try:
            service.mark_decision(signal_id, request.decision, request.actual_entry)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"status": "recorded"}

    @app.get("/performance")
    def performance(days: int = 30) -> dict[str, object]:
        if days < 1 or days > 3650:
            raise HTTPException(422, "days must be between 1 and 3650")
        since_ms = int(time.time() * 1000) - days * 86_400_000
        return service.repository.performance(since_ms)

    @app.get("/execution/status")
    def execution_status() -> dict[str, object]:
        return service.execution.status()

    @app.post("/execution/plans/entry/{signal_id}")
    def execution_entry_plan(signal_id: str) -> dict[str, object]:
        try:
            return service.execution.build_entry_plan(signal_id).as_dict()
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ExecutionBlocked as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/execution/plans/{plan_id}/submit")
    def execution_submit(plan_id: str, request: ConfirmationRequest) -> dict[str, object]:
        try:
            return service.execution.submit_entry(plan_id, request.confirmation_hash).as_dict()
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ExecutionBlocked as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.post("/execution/plans/{plan_id}/reconcile")
    def execution_reconcile(plan_id: str) -> dict[str, object]:
        try:
            return service.execution.reconcile(plan_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ExecutionBlocked as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.post("/execution/close/preview")
    def execution_close_preview(request: ClosePreviewRequest) -> dict[str, object]:
        try:
            return service.execution.prepare_close(request.symbol).as_dict()
        except ExecutionBlocked as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.post("/execution/close/{plan_id}/submit")
    def execution_close_submit(plan_id: str, request: ConfirmationRequest) -> dict[str, object]:
        try:
            return service.execution.submit_close(plan_id, request.confirmation_hash).as_dict()
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ExecutionBlocked as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.post("/execution/plans/{plan_id}/cancel")
    def execution_cancel(plan_id: str, request: ConfirmationRequest) -> dict[str, object]:
        try:
            return service.execution.cancel_entry(plan_id, request.confirmation_hash)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ExecutionBlocked as exc:
            raise HTTPException(403, str(exc)) from exc

    return app


app = create_app()
