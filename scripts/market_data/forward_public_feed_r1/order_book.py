"""Order book integrity engine with official Binance USDⓈ-M depth bridging."""

from __future__ import annotations

import decimal
from decimal import Decimal
from typing import Any

from .contracts import (
    BookIntegrityV1,
    ContractValidationError,
)

MAX_STALE_BOOK_AGE_MS: int = 300_000  # 5 minutes stale threshold


class OrderBookIntegrityEngine:
    """Maintains a local L2 order book according to official Binance USDⓈ-M rules.

    Bridge Algorithm (Official Binance USDⓈ-M Futures):
    1. Buffer websocket diff depth events.
    2. Get depth snapshot via REST (`lastUpdateId`).
    3. Drop any buffered event where `u < lastUpdateId`.
    4. The first processed event should satisfy: `U <= lastUpdateId <= u`.
    5. In subsequent events, `event.pu == prev_event.u`.
    6. If `pu` mismatch or sequence break: book is discontinuous, fail closed.
    7. Quantity 0 removes level; non-zero updates/inserts level.
    8. Prices strictly positive; bids descending, asks ascending; best_bid < best_ask.
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        max_stale_age_ms: int = MAX_STALE_BOOK_AGE_MS,
    ) -> None:
        self.symbol = symbol
        self.max_stale_age_ms = max_stale_age_ms

        # State
        self.bids: dict[Decimal, Decimal] = {}  # price -> quantity
        self.asks: dict[Decimal, Decimal] = {}  # price -> quantity
        self.snapshot_update_id: int | None = None
        self.first_update_id: int | None = None
        self.final_update_id: int | None = None
        self.previous_final_update_id: int | None = None
        self.continuous: bool = False
        self.is_bootstrapped: bool = False
        self.last_update_wall_ms: int = 0
        self.quality: str = "UNKNOWN"
        self.reason_codes: list[str] = ["AWAITING_SNAPSHOT"]
        self.needs_rebootstrap: bool = True

        # Buffering
        self._buffered_deltas: list[dict[str, Any]] = []

    def reset(self, reason: str = "RESET") -> None:
        """Reset the order book state and fail-closed until next snapshot."""
        self.bids.clear()
        self.asks.clear()
        self.snapshot_update_id = None
        self.first_update_id = None
        self.final_update_id = None
        self.previous_final_update_id = None
        self.continuous = False
        self.is_bootstrapped = False
        self.last_update_wall_ms = 0
        self.quality = "INVALID"
        self.reason_codes = [reason]
        self.needs_rebootstrap = True
        self._buffered_deltas.clear()

    def buffer_delta(self, delta_event: dict[str, Any]) -> None:
        """Buffer a differential depth update while awaiting snapshot."""
        self._buffered_deltas.append(delta_event)

    def apply_snapshot(
        self,
        snapshot: dict[str, Any],
        observed_wall_ms: int,
    ) -> BookIntegrityV1:
        """Ingest a REST depth snapshot and attempt to bridge buffered deltas."""
        last_update_id = snapshot.get("lastUpdateId")
        if last_update_id is None or not isinstance(last_update_id, int):
            self.reset("INVALID_SNAPSHOT_MISSING_LAST_UPDATE_ID")
            return self.get_integrity_receipt(observed_wall_ms)

        raw_bids = snapshot.get("bids", [])
        raw_asks = snapshot.get("asks", [])

        new_bids: dict[Decimal, Decimal] = {}
        new_asks: dict[Decimal, Decimal] = {}

        seen_snapshot_bids: set[Decimal] = set()
        seen_snapshot_asks: set[Decimal] = set()

        try:
            for p_str, q_str in raw_bids:
                p = Decimal(str(p_str))
                q = Decimal(str(q_str))
                if p in seen_snapshot_bids:
                    raise ContractValidationError(f"Duplicate bid price level in snapshot: {p}")
                seen_snapshot_bids.add(p)
                if p <= 0 or q < 0:
                    raise ContractValidationError("Negative price or quantity in snapshot bids")
                if q > 0:
                    new_bids[p] = q

            for p_str, q_str in raw_asks:
                p = Decimal(str(p_str))
                q = Decimal(str(q_str))
                if p in seen_snapshot_asks:
                    raise ContractValidationError(f"Duplicate ask price level in snapshot: {p}")
                seen_snapshot_asks.add(p)
                if p <= 0 or q < 0:
                    raise ContractValidationError("Negative price or quantity in snapshot asks")
                if q > 0:
                    new_asks[p] = q
        except (decimal.InvalidOperation, ContractValidationError, TypeError) as exc:
            self.reset(f"INVALID_SNAPSHOT_PARSE_ERROR: {exc}")
            return self.get_integrity_receipt(observed_wall_ms)

        # Check crossed book in snapshot
        if new_bids and new_asks:
            best_bid = max(new_bids.keys())
            best_ask = min(new_asks.keys())
            if best_bid >= best_ask:
                self.reset("SNAPSHOT_CROSSED_BOOK")
                return self.get_integrity_receipt(observed_wall_ms)

        self.bids = new_bids
        self.asks = new_asks
        self.snapshot_update_id = last_update_id
        self.first_update_id = last_update_id
        self.final_update_id = last_update_id
        self.previous_final_update_id = None
        self.last_update_wall_ms = observed_wall_ms
        self.continuous = True
        self.is_bootstrapped = True
        self.quality = "VERIFIED"
        self.reason_codes = ["SNAPSHOT_APPLIED"]
        self.needs_rebootstrap = False

        # Now drain and bridge buffered deltas
        if self._buffered_deltas:
            deltas_to_process = list(self._buffered_deltas)
            self._buffered_deltas.clear()
            for delta in deltas_to_process:
                self.apply_delta(delta, observed_wall_ms)
                if self.needs_rebootstrap:
                    break

        return self.get_integrity_receipt(observed_wall_ms)

    def apply_delta(
        self,
        delta: dict[str, Any],
        observed_wall_ms: int,
    ) -> BookIntegrityV1:
        """Apply a differential depth update frame."""
        if not self.is_bootstrapped or self.snapshot_update_id is None:
            # Buffer update if not bootstrapped
            self.buffer_delta(delta)
            return self.get_integrity_receipt(observed_wall_ms)

        U = delta.get("U")
        u = delta.get("u")
        pu = delta.get("pu")

        if U is None or u is None:
            self.reset("CORRUPT_DELTA_MISSING_SEQUENCE")
            return self.get_integrity_receipt(observed_wall_ms)

        # Sequence validation: reversed update IDs are forbidden
        if U > u:
            self.reset(f"REVERSED_SEQUENCE_IDS: U={U} > u={u}")
            return self.get_integrity_receipt(observed_wall_ms)

        # 1. Drop any event where u < snapshot_update_id
        if u < self.snapshot_update_id:
            return self.get_integrity_receipt(observed_wall_ms)

        # 2. First update bridging rule
        if self.final_update_id == self.snapshot_update_id:
            if pu is not None and pu > self.snapshot_update_id:
                self.reset(f"GAP_SNAPSHOT_TO_STREAM: pu={pu} > snap={self.snapshot_update_id}")
                return self.get_integrity_receipt(observed_wall_ms)
            if pu is not None and pu == self.snapshot_update_id:
                if u <= pu:
                    self.reset(f"DUPLICATE_OR_BACKWARDS_UPDATE: u={u} <= pu={pu}")
                    return self.get_integrity_receipt(observed_wall_ms)
            elif U <= self.snapshot_update_id + 1 and u >= self.snapshot_update_id:
                # Overlaps snapshot via U/u or contiguous (U == snapshot + 1)
                pass
            else:
                self.reset(f"GAP_SNAPSHOT_TO_STREAM: pu={pu}, U={U}, u={u} vs snap={self.snapshot_update_id}")
                return self.get_integrity_receipt(observed_wall_ms)
        else:
            # 3. Subsequent event rule: pu == prev_final_update_id
            if pu is not None:
                if pu != self.final_update_id:
                    self.reset(f"GAP_DETECTED: pu={pu} != prev_u={self.final_update_id}")
                    return self.get_integrity_receipt(observed_wall_ms)
                if u <= pu:
                    self.reset(f"DUPLICATE_OR_BACKWARDS_UPDATE: u={u} <= pu={pu}")
                    return self.get_integrity_receipt(observed_wall_ms)
            else:
                # If pu not provided, U must follow prev_final_update_id + 1
                if self.final_update_id is not None and U != self.final_update_id + 1:
                    self.reset(f"GAP_DETECTED: U={U} != prev_u={self.final_update_id}+1")
                    return self.get_integrity_receipt(observed_wall_ms)

            if self.final_update_id is not None and u <= self.final_update_id:
                self.reset(f"DUPLICATE_OR_BACKWARDS_UPDATE: u={u} <= prev_final_u={self.final_update_id}")
                return self.get_integrity_receipt(observed_wall_ms)

        # Apply price level mutations
        raw_bids = delta.get("b", [])
        raw_asks = delta.get("a", [])

        try:
            seen_bids: set[Decimal] = set()
            for p_str, q_str in raw_bids:
                p = Decimal(str(p_str))
                q = Decimal(str(q_str))
                if p in seen_bids:
                    self.reset(f"DEPTH_MUTATION_CONTRADICTION: duplicate bid price level {p}")
                    return self.get_integrity_receipt(observed_wall_ms)
                seen_bids.add(p)
                if p <= 0 or q < 0:
                    self.reset("NEGATIVE_PRICE_OR_QUANTITY")
                    return self.get_integrity_receipt(observed_wall_ms)
                if q == Decimal(0):
                    self.bids.pop(p, None)
                else:
                    self.bids[p] = q

            seen_asks: set[Decimal] = set()
            for p_str, q_str in raw_asks:
                p = Decimal(str(p_str))
                q = Decimal(str(q_str))
                if p in seen_asks:
                    self.reset(f"DEPTH_MUTATION_CONTRADICTION: duplicate ask price level {p}")
                    return self.get_integrity_receipt(observed_wall_ms)
                seen_asks.add(p)
                if p <= 0 or q < 0:
                    self.reset("NEGATIVE_PRICE_OR_QUANTITY")
                    return self.get_integrity_receipt(observed_wall_ms)
                if q == Decimal(0):
                    self.asks.pop(p, None)
                else:
                    self.asks[p] = q
        except (decimal.InvalidOperation, TypeError) as exc:
            self.reset(f"DELTA_PARSE_ERROR: {exc}")
            return self.get_integrity_receipt(observed_wall_ms)

        # Update sequence tracking
        self.previous_final_update_id = self.final_update_id
        self.first_update_id = U
        self.final_update_id = u
        self.last_update_wall_ms = observed_wall_ms

        # Validate book invariants
        if self.bids and self.asks:
            best_bid = max(self.bids.keys())
            best_ask = min(self.asks.keys())
            if best_bid >= best_ask:
                self.reset(f"CROSSED_BOOK: bid {best_bid} >= ask {best_ask}")
                return self.get_integrity_receipt(observed_wall_ms)

        self.continuous = True
        self.quality = "VERIFIED"
        self.reason_codes = ["OK"]

        return self.get_integrity_receipt(observed_wall_ms)

    def get_integrity_receipt(self, current_wall_ms: int) -> BookIntegrityV1:
        """Produce a BookIntegrityV1 receipt snapshot of the current book."""
        stale_age_ms = max(0, current_wall_ms - self.last_update_wall_ms) if self.last_update_wall_ms > 0 else 0

        best_bid_str: str | None = None
        best_ask_str: str | None = None

        if self.bids:
            best_bid_str = str(max(self.bids.keys()))
        if self.asks:
            best_ask_str = str(min(self.asks.keys()))

        quality = self.quality
        reasons = list(self.reason_codes)

        # Check staleness
        if self.is_bootstrapped and stale_age_ms > self.max_stale_age_ms:
            quality = "DEGRADED"
            if "STALE_BOOK" not in reasons:
                reasons.append("STALE_BOOK")

        # Check empty book sides
        if self.is_bootstrapped and (len(self.bids) == 0 and len(self.asks) == 0):
            quality = "DEGRADED"
            if "EMPTY_BOOK" not in reasons:
                reasons.append("EMPTY_BOOK")
        elif self.is_bootstrapped and (len(self.bids) == 0 or len(self.asks) == 0):
            if "EMPTY_BOOK_SIDE" not in reasons:
                reasons.append("EMPTY_BOOK_SIDE")

        # If unbootstrapped
        if not self.is_bootstrapped:
            quality = "UNKNOWN" if quality != "INVALID" else "INVALID"

        total_levels = len(self.bids) + len(self.asks)

        return BookIntegrityV1(
            snapshot_update_id=self.snapshot_update_id,
            first_update_id=self.first_update_id,
            final_update_id=self.final_update_id,
            previous_final_update_id=self.previous_final_update_id,
            continuous=self.continuous,
            best_bid=best_bid_str,
            best_ask=best_ask_str,
            observed_depth_levels=total_levels,
            stale_age_ms=stale_age_ms,
            quality=quality,
            reason_codes=reasons,
        )
