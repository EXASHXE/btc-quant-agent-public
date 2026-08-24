from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, cast


class BinanceExecutionError(RuntimeError):
    pass


@dataclass
class BinanceSignedClient:
    base_url: str
    api_key: str
    api_secret: str
    recv_window_ms: int = 5_000
    timeout_seconds: float = 10.0

    def _signed_request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        payload = dict(params or {})
        payload["timestamp"] = int(time.time() * 1000)
        payload["recvWindow"] = self.recv_window_ms
        query = urllib.parse.urlencode(payload)
        signature = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        signed_payload = f"{query}&signature={signature}"
        url = f"{self.base_url.rstrip('/')}{path}"
        body = None
        if method in {"POST", "PUT"}:
            body = signed_payload.encode()
        else:
            url = f"{url}?{signed_payload}"
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-MBX-APIKEY": self.api_key,
                "User-Agent": "btc-quant-agent/0.2.1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise BinanceExecutionError(
                f"Binance order request failed: {exc.code} {detail}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise BinanceExecutionError(f"Binance order request failed: {exc}") from exc

    def change_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._signed_request(
                "POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage}
            ),
        )

    def change_margin_type(self, symbol: str, margin_type: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._signed_request(
                "POST", "/fapi/v1/marginType", {"symbol": symbol, "marginType": margin_type}
            ),
        )

    def position_mode(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._signed_request("GET", "/fapi/v1/positionSide/dual"))

    def place_order(self, **params: Any) -> dict[str, Any]:
        return cast(dict[str, Any], self._signed_request("POST", "/fapi/v1/order", params))

    def test_order(self, **params: Any) -> dict[str, Any]:
        return cast(dict[str, Any], self._signed_request("POST", "/fapi/v1/order/test", params))

    def query_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._signed_request("GET", "/fapi/v1/order", {"symbol": symbol, "orderId": order_id}),
        )

    def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._signed_request(
                "DELETE", "/fapi/v1/order", {"symbol": symbol, "orderId": order_id}
            ),
        )

    def positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        payload = self._signed_request("GET", "/fapi/v3/positionRisk", params)
        return payload if isinstance(payload, list) else [payload]

    def realized_pnl(self, start_time_ms: int) -> float:
        rows = cast(
            list[dict[str, Any]],
            self._signed_request(
                "GET",
                "/fapi/v1/income",
                {"incomeType": "REALIZED_PNL", "startTime": start_time_ms, "limit": 1000},
            ),
        )
        return sum(float(item.get("income", 0.0)) for item in rows)

    def place_protective_order(self, **params: Any) -> dict[str, Any]:
        return cast(dict[str, Any], self._signed_request("POST", "/fapi/v1/algoOrder", params))

    def cancel_protective_order(self, _symbol: str, algo_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._signed_request("DELETE", "/fapi/v1/algoOrder", {"algoId": algo_id}),
        )
