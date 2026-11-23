"""Deterministic synthetic private-account fixtures covering all required B3 QA and demo scenarios.

ALL DATA IN THIS MODULE IS 100% FABRICATED / SYNTHETIC_PRIVATE_QA_ONLY.
Contains zero real account rows, zero real balances, and zero real credentials.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .client import (
    ROUTE_ACCOUNT,
    ROUTE_ALL_ALGO_ORDERS,
    ROUTE_ALL_ORDERS,
    ROUTE_INCOME,
    ROUTE_OPEN_ALGO_ORDERS,
    ROUTE_OPEN_ORDERS,
    ROUTE_POSITION_RISK,
    ROUTE_USER_TRADES,
    DeterministicFakeClock,
    DeterministicFakeSigner,
    FakeCredentialProvider,
    OfflineFixtureTransport,
    PrivateUserDataClient,
    SignedPrivateRequest,
    TransportResponse,
)
from .models import MINUTE_MS

DEFAULT_SYNTHETIC_AS_OF_MS = 1_735_691_600_000  # ~80s after B2 pullback-long card_1 trigger (1735691520157)

SCENARIO_NAMES: tuple[str, ...] = (
    "no_position",
    "one_way_protected",
    "hedge_long_short",
    "short_opposite",
    "multiple_position_legs",
    "ordinary_and_algo_protection",
    "partial_protection",
    "no_protection",
    "conflicting_orders",
    "partial_fills_multi_leg",
    "funding_and_commission",
    "funding_and_commission_discrepancy",
    "stale_endpoint",
    "partial_missing_algo",
    "ambiguous_matching",
    "probable_matching",
    "public_only_fallback",
)


@dataclass(frozen=True)
class SyntheticScenarioBundle:
    scenario: str
    symbol: str
    as_of_venue_ms: int
    clock: DeterministicFakeClock
    credentials: FakeCredentialProvider
    signer: DeterministicFakeSigner
    transport: OfflineFixtureTransport
    client: PrivateUserDataClient
    stale_endpoints: frozenset[str]
    missing_endpoints: frozenset[str]
    stale_age_ms: int = 0


def _json_resp(payload: Any, *, status: int = 200, source_id: str) -> TransportResponse:
    return TransportResponse(
        status_code=status,
        raw_body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        source_identity=source_id,
    )


def _base_account(
    *,
    wallet: str = "10000.00000000",
    available: str = "9500.00000000",
    margin: str = "10025.00000000",
    upnl: str = "25.00000000",
    pos_im: str = "500.00000000",
    update_ms: int = DEFAULT_SYNTHETIC_AS_OF_MS,
    positions: list[dict[str, Any]] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "totalWalletBalance": wallet,
        "availableBalance": available,
        "totalMarginBalance": margin,
        "totalUnrealizedProfit": upnl,
        "totalInitialMargin": pos_im,
        "totalMaintMargin": "50.00000000",
        "totalPositionInitialMargin": pos_im,
        "totalOpenOrderInitialMargin": "0.00000000",
        "totalCrossWalletBalance": wallet,
        "totalCrossUnPnl": upnl,
        "maxWithdrawAmount": available,
        "multiAssetsMargin": False,
        "feeTier": 0,
        "canTrade": False,
        "canDeposit": False,
        "canWithdraw": False,
        "updateTime": update_ms,
        "assets": [
            {
                "asset": "USDT",
                "walletBalance": wallet,
                "availableBalance": available,
                "marginBalance": margin,
                "unrealizedProfit": upnl,
                "crossWalletBalance": wallet,
                "maxWithdrawAmount": available,
                "marginAvailable": True,
                "updateTime": update_ms,
            }
        ],
        "positions": positions if positions is not None else [],
    }
    if extra_fields:
        data.update(extra_fields)
    return data


def _ep_tag(episode_id: str | None) -> str:
    if not episode_id:
        return "b2-noep00000000"
    return f"b2-{episode_id[:12]}"


def build_synthetic_scenario(
    scenario: str,
    *,
    symbol: str = "BTCUSDT",
    episode_id: str | None = None,
    as_of_venue_ms: int = DEFAULT_SYNTHETIC_AS_OF_MS,
) -> SyntheticScenarioBundle:
    """Construct a complete deterministic offline client + fixture transport for a named scenario."""
    if scenario not in SCENARIO_NAMES:
        raise ValueError(f"Unknown synthetic scenario: {scenario}")

    tag = _ep_tag(episode_id)
    # Place synthetic orders shortly after B2 trigger (~30s before as_of_venue_ms).
    entry_t = as_of_venue_ms - 40_000
    exit_t = as_of_venue_ms - 15_000
    source_id = f"SYNTHETIC_FIXTURE_{scenario.upper()}"

    account_payload = _base_account(update_ms=as_of_venue_ms)
    positions_payload: list[dict[str, Any]] = []
    open_orders_payload: list[dict[str, Any]] = []
    open_algo_payload: list[dict[str, Any]] = []
    all_orders_payload: list[dict[str, Any]] = []
    all_algo_payload: list[dict[str, Any]] = []
    fills_payload: list[dict[str, Any]] = []
    income_payload: list[dict[str, Any]] = []

    stale_endpoints: set[str] = set()
    missing_endpoints: set[str] = set()
    stale_age_ms = 0

    if scenario == "no_position":
        account_payload = _base_account(
            wallet="10000.00000000",
            available="10000.00000000",
            margin="10000.00000000",
            upnl="0.00000000",
            pos_im="0.00000000",
            update_ms=as_of_venue_ms,
            positions=[{"symbol": symbol, "positionAmt": "0.000"}],
        )
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "0.000",
                "positionSide": "BOTH",
                "entryPrice": "0.00",
                "breakEvenPrice": "0.00",
                "markPrice": "100.74",
                "unRealizedProfit": "0.00000000",
                "liquidationPrice": "0.00",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "0.00000000",
                "notional": "0.00000000",
                "updateTime": as_of_venue_ms,
            }
        ]

    elif scenario == "one_way_protected":
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "0.500",
                "positionSide": "BOTH",
                "entryPrice": "100.75",
                "breakEvenPrice": "100.80",
                "markPrice": "100.85",
                "unRealizedProfit": "0.05000000",
                "liquidationPrice": "91.20",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "5.08750000",
                "notional": "50.42500000",
                "updateTime": as_of_venue_ms,
                "syntheticExtraField": "preserved_value",
            }
        ]
        entry_ord = {
            "symbol": symbol,
            "orderId": 10001,
            "clientOrderId": f"{tag}-ent1",
            "side": "BUY",
            "positionSide": "BOTH",
            "type": "LIMIT",
            "status": "FILLED",
            "origQty": "0.500",
            "executedQty": "0.500",
            "price": "100.75",
            "avgPrice": "100.75",
            "stopPrice": "0",
            "workingType": "CONTRACT_PRICE",
            "closePosition": False,
            "reduceOnly": False,
            "timeInForce": "GTC",
            "time": entry_t,
            "updateTime": entry_t + 1000,
        }
        sl_algo = {
            "symbol": symbol,
            "algoId": 50001,
            "clientAlgoId": f"{tag}-sl1",
            "algoType": "CONDITIONAL",
            "orderType": "STOP_MARKET",
            "algoStatus": "NEW",
            "side": "SELL",
            "positionSide": "BOTH",
            "quantity": "0.500",
            "triggerPrice": "98.72",
            "price": "0",
            "workingType": "MARK_PRICE",
            "closePosition": True,
            "reduceOnly": True,
            "timeInForce": "GTE_GTC",
            "createTime": entry_t + 2000,
            "updateTime": entry_t + 2000,
        }
        tp_algo = {
            "symbol": symbol,
            "algoId": 50002,
            "clientAlgoId": f"{tag}-tp1",
            "algoType": "CONDITIONAL",
            "orderType": "TAKE_PROFIT_MARKET",
            "algoStatus": "NEW",
            "side": "SELL",
            "positionSide": "BOTH",
            "quantity": "0.250",
            "triggerPrice": "103.33",
            "price": "0",
            "workingType": "MARK_PRICE",
            "closePosition": False,
            "reduceOnly": True,
            "timeInForce": "GTC",
            "createTime": entry_t + 2500,
            "updateTime": entry_t + 2500,
        }
        open_algo_payload = [sl_algo, tp_algo]
        all_orders_payload = [entry_ord]
        all_algo_payload = [sl_algo, tp_algo]
        fills_payload = [
            {
                "symbol": symbol,
                "id": 90001,
                "orderId": 10001,
                "side": "BUY",
                "positionSide": "BOTH",
                "price": "100.75",
                "qty": "0.500",
                "quoteQty": "50.375",
                "realizedPnl": "0",
                "commission": "0.02518750",
                "commissionAsset": "USDT",
                "time": entry_t + 1000,
                "maker": False,
                "buyer": True,
            }
        ]
        income_payload = [
            {
                "tranId": "700001",
                "symbol": symbol,
                "incomeType": "COMMISSION",
                "income": "-0.02518750",
                "asset": "USDT",
                "info": "90001",
                "time": entry_t + 1000,
                "tradeId": "90001",
            }
        ]

    elif scenario == "hedge_long_short":
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "0.400",
                "positionSide": "LONG",
                "entryPrice": "100.75",
                "breakEvenPrice": "100.80",
                "markPrice": "100.80",
                "unRealizedProfit": "0.02000000",
                "liquidationPrice": "90.50",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "4.05000000",
                "notional": "40.32000000",
                "updateTime": as_of_venue_ms,
            },
            {
                "symbol": symbol,
                "positionAmt": "-0.300",
                "positionSide": "SHORT",
                "entryPrice": "101.10",
                "breakEvenPrice": "101.05",
                "markPrice": "100.80",
                "unRealizedProfit": "0.09000000",
                "liquidationPrice": "111.20",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "3.12000000",
                "notional": "-30.24000000",
                "updateTime": as_of_venue_ms,
            },
        ]
        open_algo_payload = [
            {
                "symbol": symbol,
                "algoId": 51001,
                "clientAlgoId": f"{tag}-hsl-long",
                "algoType": "CONDITIONAL",
                "orderType": "STOP_MARKET",
                "algoStatus": "NEW",
                "side": "SELL",
                "positionSide": "LONG",
                "quantity": "0.400",
                "triggerPrice": "98.72",
                "workingType": "MARK_PRICE",
                "closePosition": False,
                "reduceOnly": True,
                "createTime": entry_t,
                "updateTime": entry_t,
            },
            {
                "symbol": symbol,
                "algoId": 51002,
                "clientAlgoId": "hedge-short-sl",
                "algoType": "CONDITIONAL",
                "orderType": "STOP_MARKET",
                "algoStatus": "NEW",
                "side": "BUY",
                "positionSide": "SHORT",
                "quantity": "0.300",
                "triggerPrice": "103.50",
                "workingType": "MARK_PRICE",
                "closePosition": False,
                "reduceOnly": True,
                "createTime": entry_t,
                "updateTime": entry_t,
            },
        ]
        all_algo_payload = list(open_algo_payload)

    elif scenario == "short_opposite":
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "-0.500",
                "positionSide": "BOTH",
                "entryPrice": "101.00",
                "breakEvenPrice": "100.95",
                "markPrice": "100.74",
                "unRealizedProfit": "0.13000000",
                "liquidationPrice": "110.50",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "5.18000000",
                "notional": "-50.37000000",
                "updateTime": as_of_venue_ms,
            }
        ]
        open_algo_payload = [
            {
                "symbol": symbol,
                "algoId": 52001,
                "clientAlgoId": "short-sl-1",
                "algoType": "CONDITIONAL",
                "orderType": "STOP_MARKET",
                "algoStatus": "NEW",
                "side": "BUY",
                "positionSide": "BOTH",
                "quantity": "0.500",
                "triggerPrice": "103.00",
                "workingType": "MARK_PRICE",
                "closePosition": True,
                "reduceOnly": True,
                "createTime": entry_t,
                "updateTime": entry_t,
            }
        ]
        all_algo_payload = list(open_algo_payload)

    elif scenario == "multiple_position_legs":
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "0.500",
                "positionSide": "LONG",
                "entryPrice": "100.75",
                "markPrice": "100.80",
                "unRealizedProfit": "0.025",
                "liquidationPrice": "91.00",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "5.05",
                "notional": "50.40",
                "updateTime": as_of_venue_ms,
            },
            {
                "symbol": symbol,
                "positionAmt": "-0.250",
                "positionSide": "SHORT",
                "entryPrice": "101.20",
                "markPrice": "100.80",
                "unRealizedProfit": "0.100",
                "liquidationPrice": "111.00",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "2.60",
                "notional": "-25.20",
                "updateTime": as_of_venue_ms,
            },
            {
                "symbol": "ETHUSDT",
                "positionAmt": "2.000",
                "positionSide": "LONG",
                "entryPrice": "3000.00",
                "markPrice": "3010.00",
                "unRealizedProfit": "20.00",
                "liquidationPrice": "2750.00",
                "leverage": "10",
                "marginType": "cross",
                "isolatedMargin": "0.00",
                "notional": "6020.00",
                "updateTime": as_of_venue_ms,
            },
        ]
        # Only LONG leg on BTCUSDT has SL; SHORT leg has NO SL -> PARTIAL across multiple legs!
        open_algo_payload = [
            {
                "symbol": symbol,
                "algoId": 53001,
                "clientAlgoId": f"{tag}-multi-long-sl",
                "algoType": "CONDITIONAL",
                "orderType": "STOP_MARKET",
                "algoStatus": "NEW",
                "side": "SELL",
                "positionSide": "LONG",
                "quantity": "0.500",
                "triggerPrice": "98.72",
                "workingType": "MARK_PRICE",
                "closePosition": False,
                "reduceOnly": True,
                "createTime": entry_t,
                "updateTime": entry_t,
            }
        ]
        all_algo_payload = list(open_algo_payload)

    elif scenario == "ordinary_and_algo_protection":
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "1.000",
                "positionSide": "BOTH",
                "entryPrice": "100.75",
                "markPrice": "100.90",
                "unRealizedProfit": "0.15",
                "liquidationPrice": "90.80",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "10.20",
                "notional": "100.90",
                "updateTime": as_of_venue_ms,
            }
        ]
        # 0.400 covered by ordinary STOP_MARKET + 0.400 by Algo STOP_MARKET + 0.200 by Algo TRAILING_STOP_MARKET = 1.000!
        open_orders_payload = [
            {
                "symbol": symbol,
                "orderId": 20001,
                "clientOrderId": f"{tag}-ord-sl",
                "side": "SELL",
                "positionSide": "BOTH",
                "type": "STOP_MARKET",
                "status": "NEW",
                "origQty": "0.400",
                "executedQty": "0.000",
                "price": "0",
                "stopPrice": "98.72",
                "workingType": "MARK_PRICE",
                "closePosition": False,
                "reduceOnly": True,
                "timeInForce": "GTC",
                "time": entry_t + 1000,
                "updateTime": entry_t + 1000,
            }
        ]
        open_algo_payload = [
            {
                "symbol": symbol,
                "algoId": 54001,
                "clientAlgoId": f"{tag}-algo-sl",
                "algoType": "CONDITIONAL",
                "orderType": "STOP_MARKET",
                "algoStatus": "WORKING",
                "side": "SELL",
                "positionSide": "BOTH",
                "quantity": "0.400",
                "triggerPrice": "98.60",
                "workingType": "MARK_PRICE",
                "closePosition": False,
                "reduceOnly": True,
                "createTime": entry_t + 1500,
                "updateTime": entry_t + 1500,
            },
            {
                "symbol": symbol,
                "algoId": 54002,
                "clientAlgoId": f"{tag}-algo-trail",
                "algoType": "CONDITIONAL",
                "orderType": "TRAILING_STOP_MARKET",
                "algoStatus": "NEW",
                "side": "SELL",
                "positionSide": "BOTH",
                "quantity": "0.200",
                "activatePrice": "102.00",
                "callbackRate": "1.0",
                "workingType": "CONTRACT_PRICE",
                "closePosition": False,
                "reduceOnly": True,
                "createTime": entry_t + 1600,
                "updateTime": entry_t + 1600,
            },
            {
                "symbol": symbol,
                "algoId": 54003,
                "clientAlgoId": f"{tag}-algo-tp",
                "algoType": "CONDITIONAL",
                "orderType": "TAKE_PROFIT_MARKET",
                "algoStatus": "NEW",
                "side": "SELL",
                "positionSide": "BOTH",
                "quantity": "0.500",
                "triggerPrice": "103.33",
                "workingType": "MARK_PRICE",
                "closePosition": False,
                "reduceOnly": True,
                "createTime": entry_t + 1700,
                "updateTime": entry_t + 1700,
            },
        ]
        all_orders_payload = list(open_orders_payload)
        all_algo_payload = list(open_algo_payload)

    elif scenario == "partial_protection":
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "1.000",
                "positionSide": "BOTH",
                "entryPrice": "100.75",
                "markPrice": "100.80",
                "unRealizedProfit": "0.05",
                "liquidationPrice": "91.00",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "10.10",
                "notional": "100.80",
                "updateTime": as_of_venue_ms,
            }
        ]
        # Only 0.400 of 1.000 is covered by active SL -> PARTIAL (0.600 uncovered).
        open_algo_payload = [
            {
                "symbol": symbol,
                "algoId": 55001,
                "clientAlgoId": f"{tag}-part-sl",
                "algoType": "CONDITIONAL",
                "orderType": "STOP_MARKET",
                "algoStatus": "NEW",
                "side": "SELL",
                "positionSide": "BOTH",
                "quantity": "0.400",
                "triggerPrice": "98.72",
                "workingType": "MARK_PRICE",
                "closePosition": False,
                "reduceOnly": True,
                "createTime": entry_t + 1000,
                "updateTime": entry_t + 1000,
            }
        ]
        all_algo_payload = list(open_algo_payload)

    elif scenario == "no_protection":
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "0.800",
                "positionSide": "BOTH",
                "entryPrice": "100.75",
                "markPrice": "100.80",
                "unRealizedProfit": "0.04",
                "liquidationPrice": "91.00",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "8.10",
                "notional": "80.64",
                "updateTime": as_of_venue_ms,
            }
        ]
        # Only a TP order is open, plus a CANCELED/EXPIRED historical SL -> MUST be UNPROTECTED!
        open_algo_payload = [
            {
                "symbol": symbol,
                "algoId": 56001,
                "clientAlgoId": f"{tag}-tp-only",
                "algoType": "CONDITIONAL",
                "orderType": "TAKE_PROFIT_MARKET",
                "algoStatus": "NEW",
                "side": "SELL",
                "positionSide": "BOTH",
                "quantity": "0.800",
                "triggerPrice": "103.33",
                "workingType": "MARK_PRICE",
                "closePosition": False,
                "reduceOnly": True,
                "createTime": entry_t + 1000,
                "updateTime": entry_t + 1000,
            },
            # Even if an API bug returned a CANCELED algo in openAlgoOrders, it must NOT count!
            {
                "symbol": symbol,
                "algoId": 56002,
                "clientAlgoId": f"{tag}-canceled-sl",
                "algoType": "CONDITIONAL",
                "orderType": "STOP_MARKET",
                "algoStatus": "CANCELED",
                "side": "SELL",
                "positionSide": "BOTH",
                "quantity": "0.800",
                "triggerPrice": "98.72",
                "workingType": "MARK_PRICE",
                "closePosition": True,
                "reduceOnly": True,
                "createTime": entry_t + 500,
                "updateTime": entry_t + 900,
            },
        ]
        all_algo_payload = [
            *open_algo_payload,
            {
                "symbol": symbol,
                "algoId": 56003,
                "clientAlgoId": f"{tag}-expired-sl",
                "algoType": "CONDITIONAL",
                "orderType": "STOP_MARKET",
                "algoStatus": "EXPIRED",
                "side": "SELL",
                "positionSide": "BOTH",
                "quantity": "0.800",
                "triggerPrice": "98.72",
                "workingType": "MARK_PRICE",
                "closePosition": True,
                "reduceOnly": True,
                "createTime": entry_t - 5000,
                "updateTime": entry_t - 1000,
            },
        ]

    elif scenario == "conflicting_orders":
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "0.500",
                "positionSide": "BOTH",
                "entryPrice": "100.75",
                "markPrice": "100.80",
                "unRealizedProfit": "0.025",
                "liquidationPrice": "91.00",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "5.06",
                "notional": "50.40",
                "updateTime": as_of_venue_ms,
            }
        ]
        # Two conflicting closePosition=True stop-losses at different prices!
        open_algo_payload = [
            {
                "symbol": symbol,
                "algoId": 57001,
                "clientAlgoId": f"{tag}-sl-a",
                "algoType": "CONDITIONAL",
                "orderType": "STOP_MARKET",
                "algoStatus": "NEW",
                "side": "SELL",
                "positionSide": "BOTH",
                "quantity": "0.500",
                "triggerPrice": "98.72",
                "workingType": "MARK_PRICE",
                "closePosition": True,
                "reduceOnly": True,
                "createTime": entry_t + 1000,
                "updateTime": entry_t + 1000,
            },
            {
                "symbol": symbol,
                "algoId": 57002,
                "clientAlgoId": f"{tag}-sl-b",
                "algoType": "CONDITIONAL",
                "orderType": "STOP_MARKET",
                "algoStatus": "NEW",
                "side": "SELL",
                "positionSide": "BOTH",
                "quantity": "0.500",
                "triggerPrice": "97.50",
                "workingType": "MARK_PRICE",
                "closePosition": True,
                "reduceOnly": True,
                "createTime": entry_t + 1100,
                "updateTime": entry_t + 1100,
            },
        ]
        all_algo_payload = list(open_algo_payload)

    elif scenario == "partial_fills_multi_leg":
        # Completed closed round-trip with 2 entry orders (3 partial fills) + 2 exit orders (2 partial fills) + funding!
        # Entry total: 0.600 @ 100.75 + 0.400 @ 100.80 -> 1.000 base total, avg entry = 100.77.
        # Exit total: 0.500 @ 103.33 (TP1, pnl=+1.28) + 0.500 @ 104.56 (TP2, pnl=+1.895) -> total realizedPnl = +3.175 USDT.
        # Commissions (all USDT, 0.0005):
        #   fill 1 (0.300*100.75=30.225): 0.0151125
        #   fill 2 (0.300*100.75=30.225): 0.0151125
        #   fill 3 (0.400*100.80=40.320): 0.0201600
        #   fill 4 (0.500*103.33=51.665): 0.0258325
        #   fill 5 (0.500*104.56=52.280): 0.0261400
        #   Total commission = 0.1023575 USDT.
        # Funding fee = -0.0100000 USDT.
        # Net realized cashflow = 3.175 - 0.1023575 - 0.0100000 = 3.0626425 USDT.
        account_payload = _base_account(
            wallet="10003.06264250",
            available="10003.06264250",
            margin="10003.06264250",
            upnl="0.00000000",
            pos_im="0.00000000",
            update_ms=as_of_venue_ms,
            positions=[{"symbol": symbol, "positionAmt": "0.000"}],
        )
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "0.000",
                "positionSide": "BOTH",
                "entryPrice": "0.00",
                "markPrice": "104.56",
                "unRealizedProfit": "0.00000000",
                "liquidationPrice": "0.00",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "0.00",
                "notional": "0.00",
                "updateTime": as_of_venue_ms,
            }
        ]
        all_orders_payload = [
            {
                "symbol": symbol,
                "orderId": 30001,
                "clientOrderId": f"{tag}-ent-a",
                "side": "BUY",
                "positionSide": "BOTH",
                "type": "LIMIT",
                "status": "FILLED",
                "origQty": "0.600",
                "executedQty": "0.600",
                "price": "100.75",
                "avgPrice": "100.75",
                "closePosition": False,
                "reduceOnly": False,
                "timeInForce": "GTC",
                "time": entry_t,
                "updateTime": entry_t + 2000,
            },
            {
                "symbol": symbol,
                "orderId": 30002,
                "clientOrderId": f"{tag}-ent-b",
                "side": "BUY",
                "positionSide": "BOTH",
                "type": "LIMIT",
                "status": "FILLED",
                "origQty": "0.400",
                "executedQty": "0.400",
                "price": "100.80",
                "avgPrice": "100.80",
                "closePosition": False,
                "reduceOnly": False,
                "timeInForce": "GTC",
                "time": entry_t + 3000,
                "updateTime": entry_t + 4000,
            },
            {
                "symbol": symbol,
                "orderId": 30003,
                "clientOrderId": f"{tag}-exit-tp1",
                "side": "SELL",
                "positionSide": "BOTH",
                "type": "TAKE_PROFIT_MARKET",
                "status": "FILLED",
                "origQty": "0.500",
                "executedQty": "0.500",
                "price": "103.33",
                "avgPrice": "103.33",
                "stopPrice": "103.33",
                "closePosition": False,
                "reduceOnly": True,
                "timeInForce": "GTC",
                "time": exit_t - 5000,
                "updateTime": exit_t - 4000,
            },
            {
                "symbol": symbol,
                "orderId": 30004,
                "clientOrderId": f"{tag}-exit-tp2",
                "side": "SELL",
                "positionSide": "BOTH",
                "type": "TAKE_PROFIT_MARKET",
                "status": "FILLED",
                "origQty": "0.500",
                "executedQty": "0.500",
                "price": "104.56",
                "avgPrice": "104.56",
                "stopPrice": "104.56",
                "closePosition": False,
                "reduceOnly": True,
                "timeInForce": "GTC",
                "time": exit_t,
                "updateTime": exit_t + 1000,
            },
        ]
        fills_payload = [
            {
                "symbol": symbol,
                "id": 91001,
                "orderId": 30001,
                "side": "BUY",
                "positionSide": "BOTH",
                "price": "100.75",
                "qty": "0.300",
                "quoteQty": "30.225",
                "realizedPnl": "0",
                "commission": "0.0151125",
                "commissionAsset": "USDT",
                "time": entry_t + 1000,
                "maker": False,
                "buyer": True,
            },
            {
                "symbol": symbol,
                "id": 91002,
                "orderId": 30001,
                "side": "BUY",
                "positionSide": "BOTH",
                "price": "100.75",
                "qty": "0.300",
                "quoteQty": "30.225",
                "realizedPnl": "0",
                "commission": "0.0151125",
                "commissionAsset": "USDT",
                "time": entry_t + 2000,
                "maker": False,
                "buyer": True,
            },
            {
                "symbol": symbol,
                "id": 91003,
                "orderId": 30002,
                "side": "BUY",
                "positionSide": "BOTH",
                "price": "100.80",
                "qty": "0.400",
                "quoteQty": "40.320",
                "realizedPnl": "0",
                "commission": "0.0201600",
                "commissionAsset": "USDT",
                "time": entry_t + 4000,
                "maker": False,
                "buyer": True,
            },
            {
                "symbol": symbol,
                "id": 91004,
                "orderId": 30003,
                "side": "SELL",
                "positionSide": "BOTH",
                "price": "103.33",
                "qty": "0.500",
                "quoteQty": "51.665",
                "realizedPnl": "1.2800000",
                "commission": "0.0258325",
                "commissionAsset": "USDT",
                "time": exit_t - 4000,
                "maker": False,
                "buyer": False,
            },
            {
                "symbol": symbol,
                "id": 91005,
                "orderId": 30004,
                "side": "SELL",
                "positionSide": "BOTH",
                "price": "104.56",
                "qty": "0.500",
                "quoteQty": "52.280",
                "realizedPnl": "1.8950000",
                "commission": "0.0261400",
                "commissionAsset": "USDT",
                "time": exit_t + 1000,
                "maker": False,
                "buyer": False,
            },
        ]
        income_payload = [
            {
                "tranId": "710001",
                "symbol": symbol,
                "incomeType": "COMMISSION",
                "income": "-0.1023575",
                "asset": "USDT",
                "info": "multi-leg-comm",
                "time": exit_t + 1000,
                "orderId": "30004",
            },
            {
                "tranId": "710002",
                "symbol": symbol,
                "incomeType": "REALIZED_PNL",
                "income": "3.1750000",
                "asset": "USDT",
                "info": "multi-leg-rpnl",
                "time": exit_t + 1000,
                "orderId": "30004",
            },
            {
                "tranId": "710003",
                "symbol": symbol,
                "incomeType": "FUNDING_FEE",
                "income": "-0.0100000",
                "asset": "USDT",
                "info": "funding-settlement",
                "time": entry_t + 10_000,
            },
        ]

    elif scenario in ("funding_and_commission", "funding_and_commission_discrepancy"):
        # Multi-asset commission (USDT + BNB) + FUNDING_FEE + other categories + unknown field/enum!
        account_payload = _base_account(
            wallet="10000.00",
            available="10000.00",
            margin="10000.00",
            upnl="0.00",
            pos_im="0.00",
            update_ms=as_of_venue_ms,
            positions=[{"symbol": symbol, "positionAmt": "0.000"}],
            extra_fields={"futureUnknownAccountField": "keep_me"},
        )
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "0.000",
                "positionSide": "BOTH",
                "entryPrice": "0",
                "markPrice": "100.74",
                "unRealizedProfit": "0",
                "liquidationPrice": "0",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "0",
                "notional": "0",
                "updateTime": as_of_venue_ms,
            }
        ]
        all_orders_payload = [
            {
                "symbol": symbol,
                "orderId": 40001,
                "clientOrderId": f"{tag}-fx-ent",
                "side": "BUY",
                "positionSide": "BOTH",
                "type": "LIMIT",
                "status": "FILLED",
                "origQty": "0.500",
                "executedQty": "0.500",
                "price": "100.75",
                "avgPrice": "100.75",
                "closePosition": False,
                "reduceOnly": False,
                "time": entry_t,
                "updateTime": entry_t + 1000,
            },
            {
                "symbol": symbol,
                "orderId": 40002,
                "clientOrderId": f"{tag}-fx-exit",
                "side": "SELL",
                "positionSide": "BOTH",
                "type": "LIMIT",
                "status": "FILLED",
                "origQty": "0.500",
                "executedQty": "0.500",
                "price": "103.33",
                "avgPrice": "103.33",
                "closePosition": False,
                "reduceOnly": True,
                "time": exit_t,
                "updateTime": exit_t + 1000,
            },
        ]
        fills_payload = [
            {
                "symbol": symbol,
                "id": 92001,
                "orderId": 40001,
                "side": "BUY",
                "positionSide": "BOTH",
                "price": "100.75",
                "qty": "0.500",
                "quoteQty": "50.375",
                "realizedPnl": "0",
                "commission": "0.00010000",
                "commissionAsset": "BNB",
                "time": entry_t + 1000,
                "maker": False,
                "buyer": True,
            },
            {
                "symbol": symbol,
                "id": 92002,
                "orderId": 40002,
                "side": "SELL",
                "positionSide": "BOTH",
                "price": "103.33",
                "qty": "0.500",
                "quoteQty": "51.665",
                "realizedPnl": "1.29000000",
                "commission": "0.02583250",
                "commissionAsset": "USDT",
                "time": exit_t + 1000,
                "maker": False,
                "buyer": False,
            },
        ]
        rpnl_income_str = "1.29000000" if scenario == "funding_and_commission" else "1.19000000"
        income_payload = [
            {
                "tranId": "720001",
                "symbol": symbol,
                "incomeType": "COMMISSION",
                "income": "-0.00010000",
                "asset": "BNB",
                "info": "92001",
                "time": entry_t + 1000,
                "tradeId": "92001",
            },
            {
                "tranId": "720002",
                "symbol": symbol,
                "incomeType": "COMMISSION",
                "income": "-0.02583250",
                "asset": "USDT",
                "info": "92002",
                "time": exit_t + 1000,
                "tradeId": "92002",
            },
            {
                "tranId": "720003",
                "symbol": symbol,
                "incomeType": "REALIZED_PNL",
                "income": rpnl_income_str,
                "asset": "USDT",
                "info": "92002",
                "time": exit_t + 1000,
                "tradeId": "92002",
            },
            {
                "tranId": "720004",
                "symbol": symbol,
                "incomeType": "FUNDING_FEE",
                "income": "-0.01500000",
                "asset": "USDT",
                "info": "funding",
                "time": entry_t + 5000,
            },
            {
                "tranId": "720005",
                "symbol": "",
                "incomeType": "TRANSFER",
                "income": "500.00000000",
                "asset": "USDT",
                "info": "wallet-transfer",
                "time": entry_t - 60_000,
            },
            {
                "tranId": "720006",
                "symbol": "",
                "incomeType": "FUTURE_NEW_INCOME_TYPE_V9",
                "income": "0.50000000",
                "asset": "USDC",
                "info": "unknown-enum-test",
                "time": entry_t - 30_000,
                "extraUnknownField": 42,
            },
        ]

    elif scenario == "stale_endpoint":
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "0.500",
                "positionSide": "BOTH",
                "entryPrice": "100.75",
                "markPrice": "100.80",
                "unRealizedProfit": "0.025",
                "liquidationPrice": "91.00",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "5.06",
                "notional": "50.40",
                "updateTime": as_of_venue_ms - 5 * MINUTE_MS,
            }
        ]
        stale_endpoints = {ROUTE_POSITION_RISK, ROUTE_OPEN_ALGO_ORDERS}
        stale_age_ms = 5 * MINUTE_MS

    elif scenario == "partial_missing_algo":
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "0.500",
                "positionSide": "BOTH",
                "entryPrice": "100.75",
                "markPrice": "100.80",
                "unRealizedProfit": "0.025",
                "liquidationPrice": "91.00",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "5.06",
                "notional": "50.40",
                "updateTime": as_of_venue_ms,
            }
        ]
        open_orders_payload = [
            {
                "symbol": symbol,
                "orderId": 60001,
                "clientOrderId": "ord-sl-only",
                "side": "SELL",
                "positionSide": "BOTH",
                "type": "STOP_MARKET",
                "status": "NEW",
                "origQty": "0.500",
                "executedQty": "0",
                "price": "0",
                "stopPrice": "98.72",
                "workingType": "MARK_PRICE",
                "closePosition": True,
                "reduceOnly": True,
                "time": entry_t,
                "updateTime": entry_t,
            }
        ]
        # openAlgoOrders fails -> protection MUST be UNKNOWN, NOT PROTECTED!
        missing_endpoints = {ROUTE_OPEN_ALGO_ORDERS}

    elif scenario == "ambiguous_matching":
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "0.600",
                "positionSide": "BOTH",
                "entryPrice": "100.76",
                "markPrice": "100.80",
                "unRealizedProfit": "0.024",
                "liquidationPrice": "91.00",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "6.06",
                "notional": "60.48",
                "updateTime": as_of_venue_ms,
            }
        ]
        # Two unlabelled entry orders inside the entry band and window -> MUST be AMBIGUOUS!
        all_orders_payload = [
            {
                "symbol": symbol,
                "orderId": 70001,
                "clientOrderId": "manual-entry-1",
                "side": "BUY",
                "positionSide": "BOTH",
                "type": "LIMIT",
                "status": "FILLED",
                "origQty": "0.300",
                "executedQty": "0.300",
                "price": "100.75",
                "avgPrice": "100.75",
                "closePosition": False,
                "reduceOnly": False,
                "time": entry_t,
                "updateTime": entry_t + 500,
            },
            {
                "symbol": symbol,
                "orderId": 70002,
                "clientOrderId": "manual-entry-2",
                "side": "BUY",
                "positionSide": "BOTH",
                "type": "LIMIT",
                "status": "FILLED",
                "origQty": "0.300",
                "executedQty": "0.300",
                "price": "100.77",
                "avgPrice": "100.77",
                "closePosition": False,
                "reduceOnly": False,
                "time": entry_t + 2000,
                "updateTime": entry_t + 2500,
            },
        ]
        open_algo_payload = [
            {
                "symbol": symbol,
                "algoId": 58001,
                "clientAlgoId": "manual-sl-1",
                "algoType": "CONDITIONAL",
                "orderType": "STOP_MARKET",
                "algoStatus": "NEW",
                "side": "SELL",
                "positionSide": "BOTH",
                "quantity": "0.600",
                "triggerPrice": "98.72",
                "workingType": "MARK_PRICE",
                "closePosition": True,
                "reduceOnly": True,
                "createTime": entry_t + 3000,
                "updateTime": entry_t + 3000,
            }
        ]
        all_algo_payload = list(open_algo_payload)

    elif scenario == "probable_matching":
        positions_payload = [
            {
                "symbol": symbol,
                "positionAmt": "0.250",
                "positionSide": "BOTH",
                "entryPrice": "100.76",
                "markPrice": "100.80",
                "unRealizedProfit": "0.010",
                "liquidationPrice": "91.00",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "2.52",
                "notional": "25.20",
                "updateTime": as_of_venue_ms,
            }
        ]
        # Single consistent unlabelled order inside B2 entry band & window -> PROBABLE_MATCH!
        all_orders_payload = [
            {
                "symbol": symbol,
                "orderId": 80001,
                "clientOrderId": "unlabelled-human-entry",
                "side": "BUY",
                "positionSide": "BOTH",
                "type": "LIMIT",
                "status": "FILLED",
                "origQty": "0.250",
                "executedQty": "0.250",
                "price": "100.76",
                "avgPrice": "100.76",
                "closePosition": False,
                "reduceOnly": False,
                "time": entry_t + 1000,
                "updateTime": entry_t + 1500,
            }
        ]
        fills_payload = [
            {
                "symbol": symbol,
                "id": 98001,
                "orderId": 80001,
                "side": "BUY",
                "positionSide": "BOTH",
                "price": "100.76",
                "qty": "0.250",
                "quoteQty": "25.190",
                "realizedPnl": "0",
                "commission": "0.012595",
                "commissionAsset": "USDT",
                "time": entry_t + 1500,
                "maker": False,
                "buyer": True,
            }
        ]
        income_payload = [
            {
                "tranId": "780001",
                "symbol": symbol,
                "incomeType": "COMMISSION",
                "income": "-0.012595",
                "asset": "USDT",
                "info": "98001",
                "time": entry_t + 1500,
                "tradeId": "98001",
            }
        ]
        open_algo_payload = [
            {
                "symbol": symbol,
                "algoId": 59001,
                "clientAlgoId": "unlabelled-sl",
                "algoType": "CONDITIONAL",
                "orderType": "STOP_MARKET",
                "algoStatus": "NEW",
                "side": "SELL",
                "positionSide": "BOTH",
                "quantity": "0.250",
                "triggerPrice": "98.72",
                "workingType": "MARK_PRICE",
                "closePosition": True,
                "reduceOnly": True,
                "createTime": entry_t + 2000,
                "updateTime": entry_t + 2000,
            }
        ]
        all_algo_payload = list(open_algo_payload)

    elif scenario == "public_only_fallback":
        missing_endpoints = {
            ROUTE_ACCOUNT,
            ROUTE_POSITION_RISK,
            ROUTE_OPEN_ORDERS,
            ROUTE_OPEN_ALGO_ORDERS,
            ROUTE_USER_TRADES,
            ROUTE_ALL_ORDERS,
            ROUTE_ALL_ALGO_ORDERS,
            ROUTE_INCOME,
        }

    route_payloads: dict[str, Any] = {
        ROUTE_ACCOUNT: account_payload,
        ROUTE_POSITION_RISK: positions_payload,
        ROUTE_OPEN_ORDERS: open_orders_payload,
        ROUTE_OPEN_ALGO_ORDERS: open_algo_payload,
        ROUTE_ALL_ORDERS: all_orders_payload,
        ROUTE_ALL_ALGO_ORDERS: all_algo_payload,
        ROUTE_USER_TRADES: fills_payload,
        ROUTE_INCOME: income_payload,
    }

    clock = DeterministicFakeClock(
        wall_ms=as_of_venue_ms - 500,
        monotonic_ms=2_000_000,
        venue_offset_ms=100,
        offset_uncertainty_ms=8,
    )
    credentials = FakeCredentialProvider(
        key_id=f"fake-key-{scenario}",
        api_key=f"FAKE_API_KEY_{scenario.upper()}_DO_NOT_USE",
        secret=f"FAKE_API_SECRET_{scenario.upper()}_DO_NOT_USE",
    )
    signer = DeterministicFakeSigner()

    def _handler(req: SignedPrivateRequest) -> TransportResponse:
        if req.path in missing_endpoints:
            return _json_resp(
                {"code": -2015, "msg": "Synthetic simulated endpoint unavailable / permission denied"},
                status=403 if scenario == "public_only_fallback" else 503,
                source_id=source_id,
            )
        return _json_resp(route_payloads[req.path], status=200, source_id=source_id)

    transport = OfflineFixtureTransport(handler=_handler, clock=clock, latency_ms=10, source_identity=source_id)
    client = PrivateUserDataClient(
        transport=transport,
        credentials=credentials,
        signer=signer,
        clock=clock,
    )
    return SyntheticScenarioBundle(
        scenario=scenario,
        symbol=symbol,
        as_of_venue_ms=as_of_venue_ms,
        clock=clock,
        credentials=credentials,
        signer=signer,
        transport=transport,
        client=client,
        stale_endpoints=frozenset(stale_endpoints),
        missing_endpoints=frozenset(missing_endpoints),
        stale_age_ms=stale_age_ms,
    )
