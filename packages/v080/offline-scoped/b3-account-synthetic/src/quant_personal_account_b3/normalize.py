"""Decimal-only normalization for private account, positions, orders, algo orders, fills, income, and NON_ATOMIC snapshots."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
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
    EndpointCallReceipt,
)
from .models import (
    SCHEMA_ACCOUNT,
    SCHEMA_ALGO_ORDER,
    SCHEMA_ENDPOINT_COVERAGE,
    SCHEMA_FILL,
    SCHEMA_INCOME,
    SCHEMA_ORDER,
    SCHEMA_POSITION,
    SCHEMA_SNAPSHOT,
    ZERO,
    ResponseValidationError,
    decimal_str,
    digest,
    parse_bool,
    parse_decimal,
    parse_int,
    parse_optional_decimal,
    parse_optional_int,
    synthetic_provenance_block,
)

KNOWN_POSITION_SIDES = frozenset({"BOTH", "LONG", "SHORT"})
KNOWN_ORDER_SIDES = frozenset({"BUY", "SELL"})
KNOWN_ORDER_TYPES = frozenset(
    {
        "LIMIT",
        "MARKET",
        "STOP",
        "STOP_MARKET",
        "TAKE_PROFIT",
        "TAKE_PROFIT_MARKET",
        "TRAILING_STOP_MARKET",
    }
)
KNOWN_ORDER_STATUSES = frozenset(
    {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED", "EXPIRED_IN_MATCH"}
)
KNOWN_ALGO_TYPES = frozenset({"CONDITIONAL", "VP", "TWAP"})
KNOWN_ALGO_STATUSES = frozenset(
    {"NEW", "WORKING", "PENDING", "TRIGGERED", "FINISHED", "CANCELED", "EXPIRED", "REJECTED"}
)
KNOWN_WORKING_TYPES = frozenset({"MARK_PRICE", "CONTRACT_PRICE"})
KNOWN_TIF = frozenset({"GTC", "IOC", "FOK", "GTX", "GTD"})
KNOWN_MARGIN_TYPES = frozenset({"isolated", "cross", "ISOLATED", "CROSSED", "CROSS"})
KNOWN_INCOME_TYPES = frozenset(
    {
        "TRANSFER",
        "WELCOME_BONUS",
        "REALIZED_PNL",
        "FUNDING_FEE",
        "COMMISSION",
        "INSURANCE_CLEAR",
        "REFERRAL_KICKBACK",
        "COMMISSION_REBATE",
        "API_REBATE",
        "CONTEST_REWARD",
        "CROSS_COLLATERAL_TRANSFER",
        "OPTIONS_PREMIUM_FEE",
        "OPTIONS_SETTLE_PROFIT",
        "INTERNAL_TRANSFER",
        "AUTO_EXCHANGE",
        "DELIVERED_SETTELMENT",
        "COIN_SWAP_DEPOSIT",
        "COIN_SWAP_WITHDRAW",
        "POSITION_LIMIT_INCREASE_FEE",
    }
)

DEFAULT_LIVE_FRESHNESS_MS = 60_000
DEFAULT_HISTORY_FRESHNESS_MS = 300_000


def _require_dict(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResponseValidationError("EXPECTED_JSON_OBJECT", name)
    return value


def _require_str(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ResponseValidationError("EXPECTED_NONEMPTY_STRING", name)
    return value


def _optional_str(value: object, name: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ResponseValidationError("EXPECTED_STRING", name)
    return value


def _check_enum(value: str | None, known: frozenset[str], field_name: str, unknown_enums: dict[str, str]) -> str | None:
    if value is not None and value not in known:
        unknown_enums[field_name] = value
    return value


@dataclass(frozen=True)
class NormalizedAssetBalance:
    asset: str
    wallet_balance: Decimal
    available_balance: Decimal
    margin_balance: Decimal
    unrealized_profit: Decimal
    cross_wallet_balance: Decimal | None
    max_withdraw_amount: Decimal | None
    margin_available: bool | None
    update_time_ms: int | None
    raw_unknown_fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "wallet_balance": decimal_str(self.wallet_balance),
            "available_balance": decimal_str(self.available_balance),
            "margin_balance": decimal_str(self.margin_balance),
            "unrealized_profit": decimal_str(self.unrealized_profit),
            "cross_wallet_balance": decimal_str(self.cross_wallet_balance),
            "max_withdraw_amount": decimal_str(self.max_withdraw_amount),
            "margin_available": self.margin_available,
            "update_time_ms": self.update_time_ms,
            "raw_unknown_fields": self.raw_unknown_fields,
        }


@dataclass(frozen=True)
class NormalizedAccount:
    wallet_balance: Decimal
    available_balance: Decimal
    margin_balance: Decimal
    total_unrealized_profit: Decimal
    total_initial_margin: Decimal | None
    total_maint_margin: Decimal | None
    total_position_initial_margin: Decimal | None
    total_open_order_initial_margin: Decimal | None
    total_cross_wallet_balance: Decimal | None
    total_cross_un_pnl: Decimal | None
    max_withdraw_amount: Decimal | None
    multi_assets_margin: bool | None
    fee_tier: int | None
    can_trade: bool | None
    can_deposit: bool | None
    can_withdraw: bool | None
    update_time_ms: int | None
    assets: tuple[NormalizedAssetBalance, ...]
    embedded_position_symbols: tuple[str, ...]
    embedded_positions_zero_symbols: tuple[str, ...]
    raw_unknown_fields: dict[str, Any] = field(default_factory=dict)
    unknown_enums: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_ACCOUNT,
            "wallet_balance": decimal_str(self.wallet_balance),
            "available_balance": decimal_str(self.available_balance),
            "margin_balance": decimal_str(self.margin_balance),
            "total_unrealized_profit": decimal_str(self.total_unrealized_profit),
            "total_initial_margin": decimal_str(self.total_initial_margin),
            "total_maint_margin": decimal_str(self.total_maint_margin),
            "total_position_initial_margin": decimal_str(self.total_position_initial_margin),
            "total_open_order_initial_margin": decimal_str(self.total_open_order_initial_margin),
            "total_cross_wallet_balance": decimal_str(self.total_cross_wallet_balance),
            "total_cross_un_pnl": decimal_str(self.total_cross_un_pnl),
            "max_withdraw_amount": decimal_str(self.max_withdraw_amount),
            "multi_assets_margin": self.multi_assets_margin,
            "fee_tier": self.fee_tier,
            "can_trade": self.can_trade,
            "can_deposit": self.can_deposit,
            "can_withdraw": self.can_withdraw,
            "update_time_ms": self.update_time_ms,
            "assets": [item.to_dict() for item in self.assets],
            "embedded_position_symbols": list(self.embedded_position_symbols),
            "embedded_positions_zero_symbols": list(self.embedded_positions_zero_symbols),
            "raw_unknown_fields": self.raw_unknown_fields,
            "unknown_enums": self.unknown_enums,
            **synthetic_provenance_block(),
        }


@dataclass(frozen=True)
class NormalizedPosition:
    symbol: str
    position_amt: Decimal
    abs_qty: Decimal
    position_side: str  # BOTH | LONG | SHORT | preserved unknown
    position_mode: str  # ONE_WAY | HEDGE | UNKNOWN
    effective_direction: str  # LONG | SHORT | FLAT | CONFLICTING
    entry_price: Decimal
    break_even_price: Decimal | None
    mark_price: Decimal | None
    unrealized_profit: Decimal | None
    liquidation_price: Decimal | None
    leverage: Decimal | None
    margin_type: str | None
    isolated_margin: Decimal | None
    isolated_wallet: Decimal | None
    notional: Decimal | None
    update_time_ms: int | None
    raw_unknown_fields: dict[str, Any] = field(default_factory=dict)
    unknown_enums: dict[str, str] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.abs_qty > ZERO

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_POSITION,
            "symbol": self.symbol,
            "position_amt": decimal_str(self.position_amt),
            "abs_qty": decimal_str(self.abs_qty),
            "position_side": self.position_side,
            "position_mode": self.position_mode,
            "effective_direction": self.effective_direction,
            "entry_price": decimal_str(self.entry_price),
            "break_even_price": decimal_str(self.break_even_price),
            "mark_price": decimal_str(self.mark_price),
            "unrealized_profit": decimal_str(self.unrealized_profit),
            "liquidation_price": decimal_str(self.liquidation_price),
            "leverage": decimal_str(self.leverage),
            "margin_type": self.margin_type,
            "isolated_margin": decimal_str(self.isolated_margin),
            "isolated_wallet": decimal_str(self.isolated_wallet),
            "notional": decimal_str(self.notional),
            "update_time_ms": self.update_time_ms,
            "raw_unknown_fields": self.raw_unknown_fields,
            "unknown_enums": self.unknown_enums,
        }


@dataclass(frozen=True)
class NormalizedOrder:
    symbol: str
    order_id: int
    client_order_id: str
    side: str
    position_side: str
    order_type: str
    orig_type: str | None
    status: str
    orig_qty: Decimal
    executed_qty: Decimal
    remaining_qty: Decimal
    price: Decimal
    avg_price: Decimal | None
    stop_price: Decimal | None
    activate_price: Decimal | None
    price_rate: Decimal | None
    working_type: str | None
    close_position: bool
    reduce_only: bool
    time_in_force: str | None
    create_time_ms: int | None
    update_time_ms: int | None
    source_endpoint: str
    raw_unknown_fields: dict[str, Any] = field(default_factory=dict)
    unknown_enums: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_ORDER,
            "symbol": self.symbol,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "side": self.side,
            "position_side": self.position_side,
            "order_type": self.order_type,
            "orig_type": self.orig_type,
            "status": self.status,
            "orig_qty": decimal_str(self.orig_qty),
            "executed_qty": decimal_str(self.executed_qty),
            "remaining_qty": decimal_str(self.remaining_qty),
            "price": decimal_str(self.price),
            "avg_price": decimal_str(self.avg_price),
            "stop_price": decimal_str(self.stop_price),
            "activate_price": decimal_str(self.activate_price),
            "price_rate": decimal_str(self.price_rate),
            "working_type": self.working_type,
            "close_position": self.close_position,
            "reduce_only": self.reduce_only,
            "time_in_force": self.time_in_force,
            "create_time_ms": self.create_time_ms,
            "update_time_ms": self.update_time_ms,
            "source_endpoint": self.source_endpoint,
            "raw_unknown_fields": self.raw_unknown_fields,
            "unknown_enums": self.unknown_enums,
        }


@dataclass(frozen=True)
class NormalizedAlgoOrder:
    symbol: str
    algo_id: int
    client_algo_id: str
    algo_type: str
    order_type: str
    algo_status: str
    side: str
    position_side: str
    quantity: Decimal
    trigger_price: Decimal | None
    price: Decimal | None
    activate_price: Decimal | None
    callback_rate: Decimal | None
    working_type: str | None
    close_position: bool
    reduce_only: bool
    time_in_force: str | None
    create_time_ms: int | None
    update_time_ms: int | None
    trigger_time_ms: int | None
    actual_order_id: int | None
    actual_price: Decimal | None
    trigger_result: str | None
    source_endpoint: str
    raw_unknown_fields: dict[str, Any] = field(default_factory=dict)
    unknown_enums: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_ALGO_ORDER,
            "symbol": self.symbol,
            "algo_id": self.algo_id,
            "client_algo_id": self.client_algo_id,
            "algo_type": self.algo_type,
            "order_type": self.order_type,
            "algo_status": self.algo_status,
            "side": self.side,
            "position_side": self.position_side,
            "quantity": decimal_str(self.quantity),
            "trigger_price": decimal_str(self.trigger_price),
            "price": decimal_str(self.price),
            "activate_price": decimal_str(self.activate_price),
            "callback_rate": decimal_str(self.callback_rate),
            "working_type": self.working_type,
            "close_position": self.close_position,
            "reduce_only": self.reduce_only,
            "time_in_force": self.time_in_force,
            "create_time_ms": self.create_time_ms,
            "update_time_ms": self.update_time_ms,
            "trigger_time_ms": self.trigger_time_ms,
            "actual_order_id": self.actual_order_id,
            "actual_price": decimal_str(self.actual_price),
            "trigger_result": self.trigger_result,
            "source_endpoint": self.source_endpoint,
            "raw_unknown_fields": self.raw_unknown_fields,
            "unknown_enums": self.unknown_enums,
        }


@dataclass(frozen=True)
class NormalizedFill:
    symbol: str
    trade_id: int
    order_id: int
    side: str
    position_side: str
    price: Decimal
    qty: Decimal
    quote_qty: Decimal
    realized_pnl: Decimal
    commission: Decimal
    commission_asset: str
    trade_time_ms: int
    maker: bool | None
    buyer: bool | None
    raw_unknown_fields: dict[str, Any] = field(default_factory=dict)
    unknown_enums: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_FILL,
            "symbol": self.symbol,
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "side": self.side,
            "position_side": self.position_side,
            "price": decimal_str(self.price),
            "qty": decimal_str(self.qty),
            "quote_qty": decimal_str(self.quote_qty),
            "realized_pnl": decimal_str(self.realized_pnl),
            "commission": decimal_str(self.commission),
            "commission_asset": self.commission_asset,
            "trade_time_ms": self.trade_time_ms,
            "maker": self.maker,
            "buyer": self.buyer,
            "raw_unknown_fields": self.raw_unknown_fields,
            "unknown_enums": self.unknown_enums,
        }


@dataclass(frozen=True)
class NormalizedIncome:
    tran_id: str
    symbol: str
    income_type: str
    income: Decimal
    asset: str
    info: str
    time_ms: int
    trade_id: str | None
    order_id: str | None
    raw_unknown_fields: dict[str, Any] = field(default_factory=dict)
    unknown_enums: dict[str, str] = field(default_factory=dict)

    def dedup_key(self) -> tuple[str, str, str, int]:
        return (self.tran_id, self.income_type, self.asset, self.time_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_INCOME,
            "tran_id": self.tran_id,
            "symbol": self.symbol,
            "income_type": self.income_type,
            "income": decimal_str(self.income),
            "asset": self.asset,
            "info": self.info,
            "time_ms": self.time_ms,
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "raw_unknown_fields": self.raw_unknown_fields,
            "unknown_enums": self.unknown_enums,
        }


@dataclass(frozen=True)
class EndpointCoverage:
    """Independent per-endpoint freshness, page coverage, gap, and error status."""

    endpoint: str
    symbol: str | None
    status: str  # OK | PARTIAL | STALE | MISSING | ERROR | PERMISSION_DENIED | RATE_LIMITED | NOT_FETCHED
    request_wall_ms: int | None
    receive_wall_ms: int | None
    venue_time_estimate_ms: int | None
    offset_uncertainty_ms: int | None
    age_ms: int | None
    freshness_limit_ms: int
    source_identity: str | None
    raw_sha256: str | None
    pages_fetched: int
    page_coverage_complete: bool
    record_count: int
    gap_windows: tuple[dict[str, Any], ...] = ()
    retention_warnings: tuple[str, ...] = ()
    error_code: str | None = None
    error_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_ENDPOINT_COVERAGE,
            "endpoint": self.endpoint,
            "symbol": self.symbol,
            "status": self.status,
            "request_wall_ms": self.request_wall_ms,
            "receive_wall_ms": self.receive_wall_ms,
            "venue_time_estimate_ms": self.venue_time_estimate_ms,
            "offset_uncertainty_ms": self.offset_uncertainty_ms,
            "age_ms": self.age_ms,
            "freshness_limit_ms": self.freshness_limit_ms,
            "source_identity": self.source_identity,
            "raw_sha256": self.raw_sha256,
            "pages_fetched": self.pages_fetched,
            "page_coverage_complete": self.page_coverage_complete,
            "record_count": self.record_count,
            "gap_windows": list(self.gap_windows),
            "retention_warnings": list(self.retention_warnings),
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }


@dataclass(frozen=True)
class PrivateAccountSnapshot:
    """NON_ATOMIC multi-endpoint private account snapshot with explicit per-endpoint coverage."""

    snapshot_id: str
    as_of_venue_ms: int
    symbol_scope: str | None
    account: NormalizedAccount | None
    positions: tuple[NormalizedPosition, ...]
    open_orders: tuple[NormalizedOrder, ...]
    open_algo_orders: tuple[NormalizedAlgoOrder, ...]
    all_orders: tuple[NormalizedOrder, ...]
    all_algo_orders: tuple[NormalizedAlgoOrder, ...]
    fills: tuple[NormalizedFill, ...]
    income_rows: tuple[NormalizedIncome, ...]
    endpoint_coverage: dict[str, EndpointCoverage]
    overall_status: str  # SYNTHETIC_CONNECTED | PARTIAL | STALE | UNAVAILABLE
    snapshot_mode: str = "NON_ATOMIC"
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_SNAPSHOT,
            "snapshot_id": self.snapshot_id,
            "snapshot_mode": self.snapshot_mode,
            "as_of_venue_ms": self.as_of_venue_ms,
            "symbol_scope": self.symbol_scope,
            "overall_status": self.overall_status,
            "account": self.account.to_dict() if self.account else None,
            "positions": [p.to_dict() for p in self.positions],
            "open_orders": [o.to_dict() for o in self.open_orders],
            "open_algo_orders": [a.to_dict() for a in self.open_algo_orders],
            "all_orders": [o.to_dict() for o in self.all_orders],
            "all_algo_orders": [a.to_dict() for a in self.all_algo_orders],
            "fills": [f.to_dict() for f in self.fills],
            "income_rows": [i.to_dict() for i in self.income_rows],
            "endpoint_coverage": {k: v.to_dict() for k, v in sorted(self.endpoint_coverage.items())},
            "notes": list(self.notes),
            **synthetic_provenance_block(),
        }


def normalize_account(raw: object) -> NormalizedAccount:
    obj = _require_dict(raw, "account")
    known_keys = {
        "totalWalletBalance",
        "walletBalance",
        "availableBalance",
        "totalMarginBalance",
        "marginBalance",
        "totalUnrealizedProfit",
        "totalInitialMargin",
        "totalMaintMargin",
        "totalPositionInitialMargin",
        "totalOpenOrderInitialMargin",
        "totalCrossWalletBalance",
        "totalCrossUnPnl",
        "maxWithdrawAmount",
        "multiAssetsMargin",
        "feeTier",
        "canTrade",
        "canDeposit",
        "canWithdraw",
        "updateTime",
        "assets",
        "positions",
    }
    wallet_raw = obj.get("totalWalletBalance", obj.get("walletBalance"))
    margin_raw = obj.get("totalMarginBalance", obj.get("marginBalance"))
    wallet = parse_decimal(wallet_raw, "totalWalletBalance")
    available = parse_decimal(obj.get("availableBalance"), "availableBalance")
    margin = parse_decimal(margin_raw, "totalMarginBalance")
    unrealized = parse_decimal(obj.get("totalUnrealizedProfit"), "totalUnrealizedProfit")

    raw_assets = obj.get("assets", [])
    if not isinstance(raw_assets, list):
        raise ResponseValidationError("INVALID_ASSETS_LIST", "account.assets")
    assets: list[NormalizedAssetBalance] = []
    asset_known = {
        "asset",
        "walletBalance",
        "availableBalance",
        "marginBalance",
        "unrealizedProfit",
        "crossWalletBalance",
        "maxWithdrawAmount",
        "marginAvailable",
        "updateTime",
    }
    for idx, item in enumerate(raw_assets):
        row = _require_dict(item, f"account.assets[{idx}]")
        assets.append(
            NormalizedAssetBalance(
                asset=_require_str(row.get("asset"), f"account.assets[{idx}].asset"),
                wallet_balance=parse_decimal(row.get("walletBalance"), f"account.assets[{idx}].walletBalance"),
                available_balance=parse_decimal(
                    row.get("availableBalance"), f"account.assets[{idx}].availableBalance"
                ),
                margin_balance=parse_decimal(row.get("marginBalance"), f"account.assets[{idx}].marginBalance"),
                unrealized_profit=parse_decimal(
                    row.get("unrealizedProfit"), f"account.assets[{idx}].unrealizedProfit"
                ),
                cross_wallet_balance=parse_optional_decimal(
                    row.get("crossWalletBalance"), f"account.assets[{idx}].crossWalletBalance"
                ),
                max_withdraw_amount=parse_optional_decimal(
                    row.get("maxWithdrawAmount"), f"account.assets[{idx}].maxWithdrawAmount"
                ),
                margin_available=(
                    parse_bool(row["marginAvailable"], f"account.assets[{idx}].marginAvailable")
                    if "marginAvailable" in row and row["marginAvailable"] is not None
                    else None
                ),
                update_time_ms=parse_optional_int(row.get("updateTime"), f"account.assets[{idx}].updateTime", minimum=0),
                raw_unknown_fields={k: v for k, v in row.items() if k not in asset_known},
            )
        )

    embedded_symbols: list[str] = []
    embedded_zero_symbols: list[str] = []
    raw_positions = obj.get("positions", [])
    if not isinstance(raw_positions, list):
        raise ResponseValidationError("INVALID_ACCOUNT_POSITIONS", "account.positions")
    for idx, item in enumerate(raw_positions):
        prow = _require_dict(item, f"account.positions[{idx}]")
        sym = _require_str(prow.get("symbol"), f"account.positions[{idx}].symbol")
        amt = parse_decimal(prow.get("positionAmt", "0"), f"account.positions[{idx}].positionAmt")
        embedded_symbols.append(sym)
        if amt == ZERO:
            embedded_zero_symbols.append(sym)

    return NormalizedAccount(
        wallet_balance=wallet,
        available_balance=available,
        margin_balance=margin,
        total_unrealized_profit=unrealized,
        total_initial_margin=parse_optional_decimal(obj.get("totalInitialMargin"), "totalInitialMargin"),
        total_maint_margin=parse_optional_decimal(obj.get("totalMaintMargin"), "totalMaintMargin"),
        total_position_initial_margin=parse_optional_decimal(
            obj.get("totalPositionInitialMargin"), "totalPositionInitialMargin"
        ),
        total_open_order_initial_margin=parse_optional_decimal(
            obj.get("totalOpenOrderInitialMargin"), "totalOpenOrderInitialMargin"
        ),
        total_cross_wallet_balance=parse_optional_decimal(
            obj.get("totalCrossWalletBalance"), "totalCrossWalletBalance"
        ),
        total_cross_un_pnl=parse_optional_decimal(obj.get("totalCrossUnPnl"), "totalCrossUnPnl"),
        max_withdraw_amount=parse_optional_decimal(obj.get("maxWithdrawAmount"), "maxWithdrawAmount"),
        multi_assets_margin=(
            parse_bool(obj["multiAssetsMargin"], "multiAssetsMargin")
            if "multiAssetsMargin" in obj and obj["multiAssetsMargin"] is not None
            else None
        ),
        fee_tier=parse_optional_int(obj.get("feeTier"), "feeTier", minimum=0),
        can_trade=(
            parse_bool(obj["canTrade"], "canTrade")
            if "canTrade" in obj and obj["canTrade"] is not None
            else None
        ),
        can_deposit=(
            parse_bool(obj["canDeposit"], "canDeposit")
            if "canDeposit" in obj and obj["canDeposit"] is not None
            else None
        ),
        can_withdraw=(
            parse_bool(obj["canWithdraw"], "canWithdraw")
            if "canWithdraw" in obj and obj["canWithdraw"] is not None
            else None
        ),
        update_time_ms=parse_optional_int(obj.get("updateTime"), "updateTime", minimum=0),
        assets=tuple(assets),
        embedded_position_symbols=tuple(sorted(set(embedded_symbols))),
        embedded_positions_zero_symbols=tuple(sorted(set(embedded_zero_symbols))),
        raw_unknown_fields={k: v for k, v in obj.items() if k not in known_keys},
    )


def normalize_positions(raw: object) -> tuple[NormalizedPosition, ...]:
    """Normalize positionRisk rows. NEVER fabricates zero rows for omitted symbols."""
    if not isinstance(raw, list):
        raise ResponseValidationError("EXPECTED_JSON_ARRAY", "positionRisk")
    known_keys = {
        "symbol",
        "positionAmt",
        "positionSide",
        "entryPrice",
        "breakEvenPrice",
        "markPrice",
        "unRealizedProfit",
        "liquidationPrice",
        "leverage",
        "marginType",
        "isolatedMargin",
        "isolatedWallet",
        "notional",
        "updateTime",
    }
    results: list[NormalizedPosition] = []
    for idx, item in enumerate(raw):
        row = _require_dict(item, f"positionRisk[{idx}]")
        unknown_enums: dict[str, str] = {}
        symbol = _require_str(row.get("symbol"), f"positionRisk[{idx}].symbol")
        amt = parse_decimal(row.get("positionAmt"), f"positionRisk[{idx}].positionAmt")
        pos_side = _require_str(row.get("positionSide", "BOTH"), f"positionRisk[{idx}].positionSide")
        _check_enum(pos_side, KNOWN_POSITION_SIDES, "positionSide", unknown_enums)
        margin_type = _optional_str(row.get("marginType"), f"positionRisk[{idx}].marginType")
        _check_enum(margin_type, KNOWN_MARGIN_TYPES, "marginType", unknown_enums)

        if pos_side == "BOTH":
            mode = "ONE_WAY"
            direction = "LONG" if amt > ZERO else "SHORT" if amt < ZERO else "FLAT"
        elif pos_side == "LONG":
            mode = "HEDGE"
            direction = "LONG" if amt > ZERO else "FLAT" if amt == ZERO else "CONFLICTING"
        elif pos_side == "SHORT":
            mode = "HEDGE"
            # Binance USD-M Futures reports SHORT hedge positionAmt as negative (or zero when flat).
            direction = "SHORT" if amt < ZERO else "FLAT" if amt == ZERO else "CONFLICTING"
        else:
            mode = "UNKNOWN"
            direction = "LONG" if amt > ZERO else "SHORT" if amt < ZERO else "FLAT"

        results.append(
            NormalizedPosition(
                symbol=symbol,
                position_amt=amt,
                abs_qty=abs(amt),
                position_side=pos_side,
                position_mode=mode,
                effective_direction=direction,
                entry_price=parse_decimal(row.get("entryPrice"), f"positionRisk[{idx}].entryPrice", allow_negative=False),
                break_even_price=parse_optional_decimal(
                    row.get("breakEvenPrice"), f"positionRisk[{idx}].breakEvenPrice", allow_negative=False
                ),
                mark_price=parse_optional_decimal(
                    row.get("markPrice"), f"positionRisk[{idx}].markPrice", allow_negative=False
                ),
                unrealized_profit=parse_optional_decimal(
                    row.get("unRealizedProfit"), f"positionRisk[{idx}].unRealizedProfit"
                ),
                liquidation_price=parse_optional_decimal(
                    row.get("liquidationPrice"), f"positionRisk[{idx}].liquidationPrice", allow_negative=False
                ),
                leverage=parse_optional_decimal(
                    row.get("leverage"), f"positionRisk[{idx}].leverage", allow_negative=False
                ),
                margin_type=margin_type,
                isolated_margin=parse_optional_decimal(
                    row.get("isolatedMargin"), f"positionRisk[{idx}].isolatedMargin"
                ),
                isolated_wallet=parse_optional_decimal(
                    row.get("isolatedWallet"), f"positionRisk[{idx}].isolatedWallet"
                ),
                notional=parse_optional_decimal(row.get("notional"), f"positionRisk[{idx}].notional"),
                update_time_ms=parse_optional_int(row.get("updateTime"), f"positionRisk[{idx}].updateTime", minimum=0),
                raw_unknown_fields={k: v for k, v in row.items() if k not in known_keys},
                unknown_enums=unknown_enums,
            )
        )
    return tuple(results)


def normalize_orders(raw: object, *, source_endpoint: str) -> tuple[NormalizedOrder, ...]:
    if not isinstance(raw, list):
        raise ResponseValidationError("EXPECTED_JSON_ARRAY", source_endpoint)
    known_keys = {
        "symbol",
        "orderId",
        "clientOrderId",
        "side",
        "positionSide",
        "type",
        "origType",
        "status",
        "origQty",
        "executedQty",
        "price",
        "avgPrice",
        "stopPrice",
        "activatePrice",
        "priceRate",
        "workingType",
        "closePosition",
        "reduceOnly",
        "timeInForce",
        "time",
        "updateTime",
    }
    results: list[NormalizedOrder] = []
    for idx, item in enumerate(raw):
        row = _require_dict(item, f"{source_endpoint}[{idx}]")
        unknown_enums: dict[str, str] = {}
        symbol = _require_str(row.get("symbol"), f"{source_endpoint}[{idx}].symbol")
        order_id = parse_int(row.get("orderId"), f"{source_endpoint}[{idx}].orderId", minimum=0)
        client_order_id = _optional_str(row.get("clientOrderId"), f"{source_endpoint}[{idx}].clientOrderId") or ""
        side = _require_str(row.get("side"), f"{source_endpoint}[{idx}].side")
        pos_side = _require_str(row.get("positionSide", "BOTH"), f"{source_endpoint}[{idx}].positionSide")
        order_type = _require_str(row.get("type"), f"{source_endpoint}[{idx}].type")
        orig_type = _optional_str(row.get("origType"), f"{source_endpoint}[{idx}].origType")
        status = _require_str(row.get("status"), f"{source_endpoint}[{idx}].status")
        working_type = _optional_str(row.get("workingType"), f"{source_endpoint}[{idx}].workingType")
        tif = _optional_str(row.get("timeInForce"), f"{source_endpoint}[{idx}].timeInForce")

        _check_enum(side, KNOWN_ORDER_SIDES, "side", unknown_enums)
        _check_enum(pos_side, KNOWN_POSITION_SIDES, "positionSide", unknown_enums)
        _check_enum(order_type, KNOWN_ORDER_TYPES, "type", unknown_enums)
        _check_enum(orig_type, KNOWN_ORDER_TYPES, "origType", unknown_enums)
        _check_enum(status, KNOWN_ORDER_STATUSES, "status", unknown_enums)
        _check_enum(working_type, KNOWN_WORKING_TYPES, "workingType", unknown_enums)
        _check_enum(tif, KNOWN_TIF, "timeInForce", unknown_enums)

        orig_qty = parse_decimal(row.get("origQty", "0"), f"{source_endpoint}[{idx}].origQty", allow_negative=False)
        exec_qty = parse_decimal(
            row.get("executedQty", "0"), f"{source_endpoint}[{idx}].executedQty", allow_negative=False
        )
        remaining = max(ZERO, orig_qty - exec_qty)
        close_pos = parse_bool(row.get("closePosition", False), f"{source_endpoint}[{idx}].closePosition")
        reduce_only = parse_bool(row.get("reduceOnly", False), f"{source_endpoint}[{idx}].reduceOnly")

        results.append(
            NormalizedOrder(
                symbol=symbol,
                order_id=order_id,
                client_order_id=client_order_id,
                side=side,
                position_side=pos_side,
                order_type=order_type,
                orig_type=orig_type,
                status=status,
                orig_qty=orig_qty,
                executed_qty=exec_qty,
                remaining_qty=remaining,
                price=parse_decimal(row.get("price", "0"), f"{source_endpoint}[{idx}].price", allow_negative=False),
                avg_price=parse_optional_decimal(
                    row.get("avgPrice"), f"{source_endpoint}[{idx}].avgPrice", allow_negative=False
                ),
                stop_price=parse_optional_decimal(
                    row.get("stopPrice"), f"{source_endpoint}[{idx}].stopPrice", allow_negative=False
                ),
                activate_price=parse_optional_decimal(
                    row.get("activatePrice"), f"{source_endpoint}[{idx}].activatePrice", allow_negative=False
                ),
                price_rate=parse_optional_decimal(
                    row.get("priceRate"), f"{source_endpoint}[{idx}].priceRate", allow_negative=False
                ),
                working_type=working_type,
                close_position=close_pos,
                reduce_only=reduce_only,
                time_in_force=tif,
                create_time_ms=parse_optional_int(row.get("time"), f"{source_endpoint}[{idx}].time", minimum=0),
                update_time_ms=parse_optional_int(
                    row.get("updateTime"), f"{source_endpoint}[{idx}].updateTime", minimum=0
                ),
                source_endpoint=source_endpoint,
                raw_unknown_fields={k: v for k, v in row.items() if k not in known_keys},
                unknown_enums=unknown_enums,
            )
        )
    return tuple(results)


def normalize_algo_orders(raw: object, *, source_endpoint: str) -> tuple[NormalizedAlgoOrder, ...]:
    if not isinstance(raw, list):
        raise ResponseValidationError("EXPECTED_JSON_ARRAY", source_endpoint)
    known_keys = {
        "symbol",
        "algoId",
        "clientAlgoId",
        "algoType",
        "orderType",
        "algoStatus",
        "side",
        "positionSide",
        "quantity",
        "triggerPrice",
        "price",
        "activatePrice",
        "callbackRate",
        "workingType",
        "closePosition",
        "reduceOnly",
        "timeInForce",
        "createTime",
        "updateTime",
        "triggerTime",
        "actualOrderId",
        "actualPrice",
        "triggerResult",
    }
    results: list[NormalizedAlgoOrder] = []
    for idx, item in enumerate(raw):
        row = _require_dict(item, f"{source_endpoint}[{idx}]")
        unknown_enums: dict[str, str] = {}
        symbol = _require_str(row.get("symbol"), f"{source_endpoint}[{idx}].symbol")
        algo_id = parse_int(row.get("algoId"), f"{source_endpoint}[{idx}].algoId", minimum=0)
        client_algo_id = _optional_str(row.get("clientAlgoId"), f"{source_endpoint}[{idx}].clientAlgoId") or ""
        algo_type = _require_str(row.get("algoType", "CONDITIONAL"), f"{source_endpoint}[{idx}].algoType")
        order_type = _require_str(row.get("orderType"), f"{source_endpoint}[{idx}].orderType")
        algo_status = _require_str(row.get("algoStatus"), f"{source_endpoint}[{idx}].algoStatus")
        side = _require_str(row.get("side"), f"{source_endpoint}[{idx}].side")
        pos_side = _require_str(row.get("positionSide", "BOTH"), f"{source_endpoint}[{idx}].positionSide")
        working_type = _optional_str(row.get("workingType"), f"{source_endpoint}[{idx}].workingType")
        tif = _optional_str(row.get("timeInForce"), f"{source_endpoint}[{idx}].timeInForce")

        _check_enum(algo_type, KNOWN_ALGO_TYPES, "algoType", unknown_enums)
        _check_enum(order_type, KNOWN_ORDER_TYPES, "orderType", unknown_enums)
        _check_enum(algo_status, KNOWN_ALGO_STATUSES, "algoStatus", unknown_enums)
        _check_enum(side, KNOWN_ORDER_SIDES, "side", unknown_enums)
        _check_enum(pos_side, KNOWN_POSITION_SIDES, "positionSide", unknown_enums)
        _check_enum(working_type, KNOWN_WORKING_TYPES, "workingType", unknown_enums)
        _check_enum(tif, KNOWN_TIF, "timeInForce", unknown_enums)

        close_pos = parse_bool(row.get("closePosition", False), f"{source_endpoint}[{idx}].closePosition")
        reduce_only = parse_bool(row.get("reduceOnly", False), f"{source_endpoint}[{idx}].reduceOnly")

        actual_oid_raw = row.get("actualOrderId")
        actual_oid: int | None = None
        if actual_oid_raw is not None and actual_oid_raw != "":
            if isinstance(actual_oid_raw, str) and actual_oid_raw.isdigit():
                actual_oid = int(actual_oid_raw)
            else:
                actual_oid = parse_int(actual_oid_raw, f"{source_endpoint}[{idx}].actualOrderId", minimum=0)

        results.append(
            NormalizedAlgoOrder(
                symbol=symbol,
                algo_id=algo_id,
                client_algo_id=client_algo_id,
                algo_type=algo_type,
                order_type=order_type,
                algo_status=algo_status,
                side=side,
                position_side=pos_side,
                quantity=parse_decimal(row.get("quantity", "0"), f"{source_endpoint}[{idx}].quantity", allow_negative=False),
                trigger_price=parse_optional_decimal(
                    row.get("triggerPrice"), f"{source_endpoint}[{idx}].triggerPrice", allow_negative=False
                ),
                price=parse_optional_decimal(row.get("price"), f"{source_endpoint}[{idx}].price", allow_negative=False),
                activate_price=parse_optional_decimal(
                    row.get("activatePrice"), f"{source_endpoint}[{idx}].activatePrice", allow_negative=False
                ),
                callback_rate=parse_optional_decimal(
                    row.get("callbackRate"), f"{source_endpoint}[{idx}].callbackRate", allow_negative=False
                ),
                working_type=working_type,
                close_position=close_pos,
                reduce_only=reduce_only,
                time_in_force=tif,
                create_time_ms=parse_optional_int(
                    row.get("createTime"), f"{source_endpoint}[{idx}].createTime", minimum=0
                ),
                update_time_ms=parse_optional_int(
                    row.get("updateTime"), f"{source_endpoint}[{idx}].updateTime", minimum=0
                ),
                trigger_time_ms=parse_optional_int(
                    row.get("triggerTime"), f"{source_endpoint}[{idx}].triggerTime", minimum=0
                ),
                actual_order_id=actual_oid,
                actual_price=parse_optional_decimal(
                    row.get("actualPrice"), f"{source_endpoint}[{idx}].actualPrice", allow_negative=False
                ),
                trigger_result=_optional_str(row.get("triggerResult"), f"{source_endpoint}[{idx}].triggerResult"),
                source_endpoint=source_endpoint,
                raw_unknown_fields={k: v for k, v in row.items() if k not in known_keys},
                unknown_enums=unknown_enums,
            )
        )
    return tuple(results)


def normalize_fills(raw: object) -> tuple[NormalizedFill, ...]:
    if not isinstance(raw, list):
        raise ResponseValidationError("EXPECTED_JSON_ARRAY", ROUTE_USER_TRADES)
    known_keys = {
        "symbol",
        "id",
        "tradeId",
        "orderId",
        "side",
        "positionSide",
        "price",
        "qty",
        "quoteQty",
        "realizedPnl",
        "commission",
        "commissionAsset",
        "time",
        "maker",
        "buyer",
    }
    results: list[NormalizedFill] = []
    for idx, item in enumerate(raw):
        row = _require_dict(item, f"userTrades[{idx}]")
        unknown_enums: dict[str, str] = {}
        symbol = _require_str(row.get("symbol"), f"userTrades[{idx}].symbol")
        tid_raw = row.get("tradeId", row.get("id"))
        trade_id = parse_int(tid_raw, f"userTrades[{idx}].id", minimum=0)
        order_id = parse_int(row.get("orderId"), f"userTrades[{idx}].orderId", minimum=0)
        side = _require_str(row.get("side"), f"userTrades[{idx}].side")
        pos_side = _require_str(row.get("positionSide", "BOTH"), f"userTrades[{idx}].positionSide")
        _check_enum(side, KNOWN_ORDER_SIDES, "side", unknown_enums)
        _check_enum(pos_side, KNOWN_POSITION_SIDES, "positionSide", unknown_enums)

        price = parse_decimal(row.get("price"), f"userTrades[{idx}].price", allow_negative=False)
        qty = parse_decimal(row.get("qty"), f"userTrades[{idx}].qty", allow_negative=False)
        quote_qty_raw = row.get("quoteQty")
        quote_qty = (
            parse_decimal(quote_qty_raw, f"userTrades[{idx}].quoteQty", allow_negative=False)
            if quote_qty_raw is not None
            else price * qty
        )
        realized_pnl = parse_decimal(row.get("realizedPnl", "0"), f"userTrades[{idx}].realizedPnl")
        commission = parse_decimal(row.get("commission", "0"), f"userTrades[{idx}].commission")
        commission_asset = _require_str(row.get("commissionAsset", "USDT"), f"userTrades[{idx}].commissionAsset")
        trade_time = parse_int(row.get("time"), f"userTrades[{idx}].time", minimum=1)

        maker = parse_bool(row["maker"], f"userTrades[{idx}].maker") if "maker" in row and row["maker"] is not None else None
        buyer = parse_bool(row["buyer"], f"userTrades[{idx}].buyer") if "buyer" in row and row["buyer"] is not None else None

        results.append(
            NormalizedFill(
                symbol=symbol,
                trade_id=trade_id,
                order_id=order_id,
                side=side,
                position_side=pos_side,
                price=price,
                qty=qty,
                quote_qty=quote_qty,
                realized_pnl=realized_pnl,
                commission=commission,
                commission_asset=commission_asset,
                trade_time_ms=trade_time,
                maker=maker,
                buyer=buyer,
                raw_unknown_fields={k: v for k, v in row.items() if k not in known_keys},
                unknown_enums=unknown_enums,
            )
        )
    return tuple(results)


def normalize_income(raw: object) -> tuple[NormalizedIncome, ...]:
    if not isinstance(raw, list):
        raise ResponseValidationError("EXPECTED_JSON_ARRAY", ROUTE_INCOME)
    known_keys = {
        "tranId",
        "symbol",
        "incomeType",
        "income",
        "asset",
        "info",
        "time",
        "tradeId",
        "orderId",
    }
    results: list[NormalizedIncome] = []
    for idx, item in enumerate(raw):
        row = _require_dict(item, f"income[{idx}]")
        unknown_enums: dict[str, str] = {}
        tran_raw = row.get("tranId")
        if isinstance(tran_raw, int) and type(tran_raw) is int:
            tran_id = str(tran_raw)
        elif isinstance(tran_raw, str) and tran_raw:
            tran_id = tran_raw
        else:
            raise ResponseValidationError("INVALID_TRAN_ID", f"income[{idx}].tranId")

        symbol = _optional_str(row.get("symbol"), f"income[{idx}].symbol") or ""
        income_type = _require_str(row.get("incomeType"), f"income[{idx}].incomeType")
        _check_enum(income_type, KNOWN_INCOME_TYPES, "incomeType", unknown_enums)
        income = parse_decimal(row.get("income"), f"income[{idx}].income")
        asset = _require_str(row.get("asset"), f"income[{idx}].asset")
        info = _optional_str(row.get("info"), f"income[{idx}].info") or ""
        time_ms = parse_int(row.get("time"), f"income[{idx}].time", minimum=1)

        trade_id_raw = row.get("tradeId")
        trade_id = (
            str(trade_id_raw)
            if (isinstance(trade_id_raw, int) and type(trade_id_raw) is int)
            or (isinstance(trade_id_raw, str) and trade_id_raw != "")
            else None
        )
        order_id_raw = row.get("orderId")
        order_id = (
            str(order_id_raw)
            if (isinstance(order_id_raw, int) and type(order_id_raw) is int)
            or (isinstance(order_id_raw, str) and order_id_raw != "")
            else None
        )

        results.append(
            NormalizedIncome(
                tran_id=tran_id,
                symbol=symbol,
                income_type=income_type,
                income=income,
                asset=asset,
                info=info,
                time_ms=time_ms,
                trade_id=trade_id,
                order_id=order_id,
                raw_unknown_fields={k: v for k, v in row.items() if k not in known_keys},
                unknown_enums=unknown_enums,
            )
        )
    return tuple(results)


def build_endpoint_coverage(
    *,
    endpoint: str,
    symbol: str | None,
    as_of_venue_ms: int,
    receipt: EndpointCallReceipt | None,
    record_count: int,
    freshness_limit_ms: int,
    pages_fetched: int = 1,
    page_coverage_complete: bool = True,
    gap_windows: Sequence[dict[str, Any]] = (),
    retention_warnings: Sequence[str] = (),
    error_code: str | None = None,
    error_detail: str | None = None,
) -> EndpointCoverage:
    """Compute independent endpoint status and freshness age at evaluation as-of time."""
    if receipt is None:
        if error_code == "PERMISSION_DENIED_FAIL_CLOSED":
            status = "PERMISSION_DENIED"
        elif error_code in ("RATE_LIMITED_429", "IP_BANNED_418"):
            status = "RATE_LIMITED"
        elif error_code:
            status = "ERROR"
        else:
            status = "MISSING"
        return EndpointCoverage(
            endpoint=endpoint,
            symbol=symbol,
            status=status,
            request_wall_ms=None,
            receive_wall_ms=None,
            venue_time_estimate_ms=None,
            offset_uncertainty_ms=None,
            age_ms=None,
            freshness_limit_ms=freshness_limit_ms,
            source_identity=None,
            raw_sha256=None,
            pages_fetched=pages_fetched,
            page_coverage_complete=False,
            record_count=record_count,
            gap_windows=tuple(gap_windows),
            retention_warnings=tuple(retention_warnings),
            error_code=error_code,
            error_detail=error_detail,
        )

    age_ms = as_of_venue_ms - receipt.venue_time_estimate_ms
    if error_code == "PERMISSION_DENIED_FAIL_CLOSED":
        status = "PERMISSION_DENIED"
    elif error_code in ("RATE_LIMITED_429", "IP_BANNED_418"):
        status = "RATE_LIMITED"
    elif error_code:
        status = "PARTIAL" if pages_fetched > 0 and record_count > 0 else "ERROR"
    elif age_ms < 0 or age_ms > freshness_limit_ms:
        status = "STALE"
    elif not page_coverage_complete or len(gap_windows) > 0:
        status = "PARTIAL"
    else:
        status = "OK"

    return EndpointCoverage(
        endpoint=endpoint,
        symbol=symbol,
        status=status,
        request_wall_ms=receipt.request_wall_ms,
        receive_wall_ms=receipt.receive_wall_ms,
        venue_time_estimate_ms=receipt.venue_time_estimate_ms,
        offset_uncertainty_ms=receipt.offset_uncertainty_ms,
        age_ms=age_ms,
        freshness_limit_ms=freshness_limit_ms,
        source_identity=receipt.source_identity,
        raw_sha256=receipt.raw_sha256,
        pages_fetched=pages_fetched,
        page_coverage_complete=page_coverage_complete,
        record_count=record_count,
        gap_windows=tuple(gap_windows),
        retention_warnings=tuple(retention_warnings),
        error_code=error_code,
        error_detail=error_detail,
    )


LIVE_REQUIRED_ENDPOINTS = (
    ROUTE_ACCOUNT,
    ROUTE_POSITION_RISK,
    ROUTE_OPEN_ORDERS,
    ROUTE_OPEN_ALGO_ORDERS,
)

ALL_CORE_ENDPOINTS = (
    ROUTE_ACCOUNT,
    ROUTE_POSITION_RISK,
    ROUTE_OPEN_ORDERS,
    ROUTE_OPEN_ALGO_ORDERS,
    ROUTE_USER_TRADES,
    ROUTE_ALL_ORDERS,
    ROUTE_ALL_ALGO_ORDERS,
    ROUTE_INCOME,
)


def compute_overall_snapshot_status(coverage: dict[str, EndpointCoverage]) -> str:
    """Derive fail-closed overall NON_ATOMIC snapshot status from per-endpoint coverage."""
    live_statuses = [coverage[ep].status if ep in coverage else "MISSING" for ep in LIVE_REQUIRED_ENDPOINTS]
    if all(st in ("MISSING", "ERROR", "PERMISSION_DENIED", "RATE_LIMITED", "NOT_FETCHED") for st in live_statuses):
        return "UNAVAILABLE"
    if any(st == "STALE" for st in live_statuses):
        return "STALE"
    if any(st != "OK" for st in live_statuses):
        return "PARTIAL"
    # Check if any fetched historical endpoint is stale/partial/error.
    hist_statuses = [
        cov.status
        for ep, cov in coverage.items()
        if ep not in LIVE_REQUIRED_ENDPOINTS and cov.status != "NOT_FETCHED"
    ]
    if any(st == "STALE" for st in hist_statuses):
        return "STALE"
    if any(st != "OK" for st in hist_statuses):
        return "PARTIAL"
    return "SYNTHETIC_CONNECTED"


def build_snapshot_id(
    *,
    as_of_venue_ms: int,
    symbol_scope: str | None,
    coverage: dict[str, EndpointCoverage],
) -> str:
    payload = {
        "as_of_venue_ms": as_of_venue_ms,
        "symbol_scope": symbol_scope,
        "coverage": {
            k: {
                "status": v.status,
                "raw_sha256": v.raw_sha256,
                "venue_time_estimate_ms": v.venue_time_estimate_ms,
                "record_count": v.record_count,
                "pages_fetched": v.pages_fetched,
            }
            for k, v in sorted(coverage.items())
        },
    }
    return digest(payload)
