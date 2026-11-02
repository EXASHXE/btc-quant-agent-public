from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, cast


class BinanceExecutionError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CredentialAuthority:
    environment: str
    credential_namespace: str
    rest_base_url: str


@dataclass
class BinanceSignedClient:
    base_url: str
    api_key: str
    api_secret: str
    recv_window_ms: int = 5_000
    timeout_seconds: float = 10.0
    environment: str = "UNBOUND"
    credential_namespace: str = "UNBOUND"

    @property
    def authority(self) -> CredentialAuthority:
        return CredentialAuthority(
            environment=self.environment,
            credential_namespace=self.credential_namespace,
            rest_base_url=self.base_url,
        )

    def _signed_request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        if method.upper() != "GET":
            self._require_mutation_authority()
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
            code = None
            try:
                error = json.loads(exc.read(65536))
                if isinstance(error, dict) and type(error.get("code")) is int:
                    code = error["code"]
            except (ValueError, OSError):
                pass
            raise BinanceExecutionError(f"Binance request failed: HTTP {exc.code}", code=code) from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            raise BinanceExecutionError("Binance request failed") from None

    def _api_key_request(self, method: str, path: str) -> dict[str, Any]:
        """USER_STREAM requests authenticate with the key header, never a signature."""
        self._require_mutation_authority()
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}{path}", method=method,
            headers={"X-MBX-APIKEY": self.api_key, "User-Agent": "btc-quant-agent/0.2.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
                parsed = json.loads(payload) if payload else {}
                if not isinstance(parsed, dict):
                    raise BinanceExecutionError("invalid Binance user stream response")
                return parsed
        except urllib.error.HTTPError as exc:
            raise BinanceExecutionError(f"Binance user stream request failed: HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            raise BinanceExecutionError("Binance user stream request failed") from None

    def _require_mutation_authority(self) -> None:
        from .guard import ExecutionBlocked
        from .policy import ExecutionCapabilityPolicyV1

        ExecutionCapabilityPolicyV1.check_capability(
            self.environment,
            "SIGNED_MUTATION",
            env_id=self.environment,
            cred_ns=self.credential_namespace,
            rest_url=self.base_url,
        )
        if self.environment.upper() != "TESTNET":
            raise ExecutionBlocked(
                f"signed client mutation requires TESTNET environment, got '{self.environment}'"
            )

    def account_information(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._signed_request("GET", "/fapi/v3/account"))

    def balances(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._signed_request("GET", "/fapi/v3/balance"))

    def open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        return cast(list[dict[str, Any]], self._signed_request("GET", "/fapi/v1/openOrders", params))

    def query_order_by_client_id(self, symbol: str, client_order_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._signed_request(
            "GET", "/fapi/v1/order", {"symbol": symbol, "origClientOrderId": client_order_id},
        ))

    def query_protective_order(self, algo_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._signed_request(
            "GET", "/fapi/v1/algoOrder", {"algoId": algo_id},
        ))

    def open_protective_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        return cast(list[dict[str, Any]], self._signed_request(
            "GET", "/fapi/v1/openAlgoOrders", params,
        ))

    def start_user_stream(self) -> str:
        key = self._api_key_request("POST", "/fapi/v1/listenKey").get("listenKey")
        if not isinstance(key, str) or not key:
            raise BinanceExecutionError("invalid Binance user stream response")
        return key

    def keepalive_user_stream(self, _listen_key: str) -> None:
        self._api_key_request("PUT", "/fapi/v1/listenKey")

    def close_user_stream(self, _listen_key: str) -> None:
        self._api_key_request("DELETE", "/fapi/v1/listenKey")

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


def create_testnet_signed_client(
    base_url: str = "https://testnet.binancefuture.com",
    recv_window_ms: int = 5_000,
    timeout_seconds: float = 10.0,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> BinanceSignedClient:
    cleaned_url = base_url.rstrip("/").lower()
    if cleaned_url != "https://testnet.binancefuture.com":
        raise BinanceExecutionError(f"invalid testnet endpoint: {base_url}")

    key = api_key if api_key is not None else os.getenv("BINANCE_TESTNET_API_KEY", "")
    secret = api_secret if api_secret is not None else os.getenv("BINANCE_TESTNET_API_SECRET", "")

    if not key or not secret:
        raise BinanceExecutionError("missing required BINANCE_TESTNET_API_KEY or BINANCE_TESTNET_API_SECRET")

    return BinanceSignedClient(
        base_url=base_url,
        api_key=key,
        api_secret=secret,
        recv_window_ms=recv_window_ms,
        timeout_seconds=timeout_seconds,
        environment="TESTNET",
        credential_namespace="BINANCE_TESTNET",
    )
