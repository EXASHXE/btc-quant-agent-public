"""Fabricated local REST fixture only; never a market source."""

import time
from urllib.parse import urlsplit, parse_qs
from btc_quant_agent.platform.rc_fixture import TRIGGER
from btc_quant_agent.platform.swing import INTERVALS
from local_rest import RestVenue


class SwingVenue(RestVenue):
    def __init__(self, directory, *, minutes=30, market_fault=None, **kwargs):
        self.minutes = minutes
        self.market_fault = market_fault
        super().__init__(directory, **kwargs)

    def body(self, path):
        url = urlsplit(path)
        if url.path == "/fapi/v1/time":
            return {
                "serverTime": TRIGGER + self.minutes * 60000 + int((time.monotonic() - self.epoch) * 1000)
            }
        if url.path == "/fapi/v1/klines":
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            if q.get("limit") == "1":
                c = float(self.data[(q["symbol"], "4H")][-1][4])
                if self.market_fault == "chase":
                    c += 1000
                row = [
                    TRIGGER,
                    str(c),
                    str(c + 0.01),
                    str(c - 0.01),
                    str(c),
                    "10",
                    TRIGGER + INTERVALS["4H"] - 1,
                    "1000",
                    1,
                    "0",
                    "0",
                    "0",
                ]
                if self.market_fault == "pivot":
                    row[3] = "0.01"
                if self.market_fault == "wrong_interval":
                    row[6] = TRIGGER + INTERVALS["1H"] - 1
                if self.market_fault == "wrong_cycle":
                    row[0] -= INTERVALS["4H"]
                if self.market_fault == "no_current":
                    return []
                return [row]
        return super().body(path)
