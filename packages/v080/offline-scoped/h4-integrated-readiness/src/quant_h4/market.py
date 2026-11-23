"""Read the accepted B5 planning and B2 source contracts without enabling collection."""

from quant_personal_live_public_b5.offline import plan
from quant_personal_live_public_b5.stages import market_floor


def packet():
    prospective = plan()
    count, known, funding = market_floor()
    assert (count, known, funding) == (37, 37, 3)
    return {
        "schema": "H4_S3_PROPOSED_V1",
        "status": "FUNDING_WEIGHT_UNRESOLVED",
        "authority": prospective["authority"],
        "request_plan": prospective["requests"],
        "market_requests": count,
        "market_known_weight": known,
        "combined_requests": count + 2,
        "combined_known_weight": known + 2,
        "funding_calls": funding,
        "funding_general_debit": None,
        "signed_total_weight": None,
        "family_capped": {
            "funding_history_and_info_5m_ip": 500,
            "open_interest_history_5m_ip": 1000,
        },
        "grant": None,
        "retry_authorization": None,
        "real_collection_authorized": False,
    }
