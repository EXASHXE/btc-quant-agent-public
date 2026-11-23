"""Synthetic responses matching the B4 venue response shape."""

from .routes import FUNDING, OI_HISTORY


def usd_m_fixture(route, params, body):
    if route == FUNDING:
        return [{**{k: v for k, v in row.items() if k != "fundingRateType"},
                 "rateType": row.get("fundingRateType", "Regular")} for row in body]
    if route == OI_HISTORY:
        return [{**row, "CMCCirculatingSupply": "000123.4500"} for row in body
                if params["startTime"] <= row["timestamp"] <= params["endTime"]]
    return body


