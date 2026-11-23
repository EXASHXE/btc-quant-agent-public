"""Unsigned offline plan with explicit unknown general funding-rate debit."""

from .contract import AUTHORITY, FUNDING, PublicRequest
from .stages import CANARY_ROUTES, STAGE_CONTRACT, TIMEOUT_PROFILE, market_floor, market_requests

FIXTURE_CUTOFF = 1_735_689_720_000


def _row(request):
    return {"method":"GET","path":request.route,"params":dict(request.params),
            "documented_debit":None if request.route == FUNDING else request.validate()[0]}


def preview():
    count, known, funding = market_floor()
    return {
        "contract":STAGE_CONTRACT, "authorization":"NOT_AUTHORIZED", "authority":AUTHORITY,
        "fixture_cutoff_venue_ms":FIXTURE_CUTOFF,
        "canary":{"requests":[_row(PublicRequest(path,{})) for path in CANARY_ROUTES],
                  "request_count":2, "known_weight":2, "automatic_retries":0},
        "conditional_market":{"requires":"SIGNED_MARKET_SCOPE_AND_QUALIFIED_CANARY",
                              "requests":[_row(request) for request in market_requests(FIXTURE_CUTOFF)],
                              "nominal_request_count":count,"known_weight":known,"funding_calls":funding,
                              "funding_debit":"PENDING_EXTERNAL_REVIEW",
                              "per_logical_request_retry_ceiling":1},
        "nominal_full":{"request_count":count+2,"known_weight":known+2,"funding_calls":funding},
        "approved_budget":None,"shared_egress_headroom":None,
        "timeout_profile":TIMEOUT_PROFILE,"timed_refresh":"DISABLED","request_reprice":"DISABLED",
    }
