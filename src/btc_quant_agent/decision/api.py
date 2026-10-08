"""Opt-in Live V1 endpoints, inheriting the host API's bearer dependency."""

from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .service import TacticalLiveService


class LiveScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbols: Annotated[
        list[Annotated[str, Field(pattern=r"^[A-Z0-9]{3,20}$")]],
        Field(min_length=1, max_length=5),
    ] = Field(default_factory=lambda: ["BTCUSDT"])


def create_live_router(live: TacticalLiveService) -> APIRouter:
    router = APIRouter(prefix="/live-v1")

    @router.post("/scan")
    async def live_scan(request: LiveScanRequest) -> dict[str, object]:
        try:
            proposals = await live.scan(request.symbols)
        except ValueError:
            raise HTTPException(422, "live decision unavailable") from None
        return {"account_authority": "DRY_RUN", "exchange_write_count": 0,
                "proposals": [item.model_dump(mode="json") for item in proposals]}

    @router.get("/cases/{case_id}")
    def live_case(case_id: str) -> dict[str, object]:
        try:
            live.store.expire_cases(live.clock_ms())
            case = live.store.get_case(case_id)
            state = live.store.state(case_id)
            proposal = live.store.active_proposal(case_id)
        except (ValueError, KeyError):
            raise HTTPException(404, "case not found") from None
        return {"case": case.model_dump(mode="json"), "state": state.value,
                "proposal": proposal.model_dump(mode="json") if proposal else None}

    @router.post("/reviews")
    async def live_reviews() -> dict[str, object]:
        proposals = await live.process_codex_reviews()
        return {"proposals": [item.model_dump(mode="json") for item in proposals],
                "exchange_write_count": 0}

    return router
