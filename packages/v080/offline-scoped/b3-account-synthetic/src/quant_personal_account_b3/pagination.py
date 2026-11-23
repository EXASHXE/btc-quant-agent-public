"""Bounded resumable pagination, retention-gap tracking, and crash-safe checkpoints."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .client import (
    ROUTE_ALL_ALGO_ORDERS,
    ROUTE_ALL_ORDERS,
    ROUTE_INCOME,
    ROUTE_OPEN_ALGO_ORDERS,
    ROUTE_OPEN_ORDERS,
    ROUTE_USER_TRADES,
    EndpointCallReceipt,
    PrivateUserDataClient,
)
from .models import (
    DAY_MS,
    NINETY_DAYS_MS,
    SCHEMA_CHECKPOINT,
    SEVEN_DAYS_MS,
    THREE_DAYS_MS,
    AccountB3Error,
    PrivateRequestRejectedError,
)
from .normalize import (
    DEFAULT_HISTORY_FRESHNESS_MS,
    EndpointCoverage,
    NormalizedAlgoOrder,
    NormalizedFill,
    NormalizedIncome,
    NormalizedOrder,
    build_endpoint_coverage,
    normalize_algo_orders,
    normalize_fills,
    normalize_income,
    normalize_orders,
)
from .storage import PaginationCheckpoint, PrivateAccountStore

HISTORICAL_ENDPOINTS = frozenset(
    {ROUTE_USER_TRADES, ROUTE_ALL_ORDERS, ROUTE_ALL_ALGO_ORDERS, ROUTE_INCOME}
)
CURRENT_OPEN_ONLY_ENDPOINTS = frozenset({ROUTE_OPEN_ORDERS, ROUTE_OPEN_ALGO_ORDERS})

# Strictly under 7 days for allOrders / allAlgoOrders; <= 7 days for userTrades / income default.
MAX_WINDOW_USER_TRADES_MS = SEVEN_DAYS_MS
MAX_WINDOW_ORDERS_MS = SEVEN_DAYS_MS - 1
DEFAULT_INCOME_WINDOW_MS = SEVEN_DAYS_MS


@dataclass(frozen=True)
class PaginationResult:
    endpoint: str
    symbol: str | None
    checkpoint: PaginationCheckpoint
    coverage: EndpointCoverage
    fills: tuple[NormalizedFill, ...] = ()
    orders: tuple[NormalizedOrder, ...] = ()
    algo_orders: tuple[NormalizedAlgoOrder, ...] = ()
    income_rows: tuple[NormalizedIncome, ...] = ()


def plan_bounded_windows(
    *,
    endpoint: str,
    start_ms: int,
    end_ms: int,
    as_of_venue_ms: int,
) -> tuple[list[tuple[int, int]], list[dict[str, Any]], list[str]]:
    """Split a requested range into endpoint-legal bounded windows and detect retention gaps."""
    if endpoint in CURRENT_OPEN_ONLY_ENDPOINTS:
        raise PrivateRequestRejectedError(
            "OPEN_ORDERS_NOT_HISTORICAL_SOURCE",
            f"{endpoint} is a current-open view, not a historical paginated endpoint",
        )
    if endpoint not in HISTORICAL_ENDPOINTS:
        raise PrivateRequestRejectedError("NOT_A_HISTORICAL_ENDPOINT", endpoint)
    if end_ms < start_ms:
        raise PrivateRequestRejectedError("INVALID_TIME_WINDOW_ORDER", f"{start_ms} > {end_ms}")

    gaps: list[dict[str, Any]] = []
    warnings: list[str] = []
    retention_cutoff = as_of_venue_ms - NINETY_DAYS_MS

    effective_start = start_ms
    if start_ms < retention_cutoff:
        gap_end = min(end_ms, retention_cutoff - 1)
        reason = "RETENTION_GAP_3M_INCOME" if endpoint == ROUTE_INCOME else "RETENTION_GAP_90D"
        gaps.append({"start_ms": start_ms, "end_ms": gap_end, "reason": reason})
        warnings.append(reason)
        effective_start = retention_cutoff

    if endpoint in (ROUTE_ALL_ORDERS, ROUTE_ALL_ALGO_ORDERS) and start_ms < as_of_venue_ms - THREE_DAYS_MS:
        warnings.append("CANCELED_UNFILLED_ORDERS_OLDER_THAN_3_DAYS_MAY_DISAPPEAR")

    if endpoint == ROUTE_INCOME:
        warnings.append("INCOME_WEIGHT_30_USE_INCREMENTAL_POLLING")

    if effective_start > end_ms:
        return [], gaps, warnings

    if endpoint == ROUTE_USER_TRADES:
        max_span = MAX_WINDOW_USER_TRADES_MS
    elif endpoint in (ROUTE_ALL_ORDERS, ROUTE_ALL_ALGO_ORDERS):
        max_span = min(6 * DAY_MS, MAX_WINDOW_ORDERS_MS)
    else:
        max_span = DEFAULT_INCOME_WINDOW_MS

    windows: list[tuple[int, int]] = []
    cur = effective_start
    while cur <= end_ms:
        win_end = min(end_ms, cur + max_span)
        windows.append((cur, win_end))
        if win_end == end_ms:
            break
        cur = win_end + 1
    return windows, gaps, warnings


class HistoryPaginator:
    """Resumable, bounded paginator with durable SQLite checkpoints and idempotent replay."""

    def __init__(
        self,
        *,
        client: PrivateUserDataClient,
        store: PrivateAccountStore,
        max_pages_per_window: int = 50,
        freshness_limit_ms: int = DEFAULT_HISTORY_FRESHNESS_MS,
    ) -> None:
        self._client = client
        self._store = store
        self._max_pages_per_window = max_pages_per_window
        self._freshness_limit_ms = freshness_limit_ms

    def sync_user_trades(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        as_of_venue_ms: int,
        page_limit: int = 500,
        use_from_id: bool = False,
        initial_from_id: int | None = None,
        before_page_commit: Callable[[int], None] | None = None,
    ) -> PaginationResult:
        """Paginate /fapi/v1/userTrades with <=7d windows or fromId cursor and crash-safe checkpoints."""
        windows, gaps, warnings = plan_bounded_windows(
            endpoint=ROUTE_USER_TRADES,
            start_ms=start_ms,
            end_ms=end_ms,
            as_of_venue_ms=as_of_venue_ms,
        )
        if use_from_id:
            windows = [(start_ms, end_ms)]

        existing_cp = self._store.load_checkpoint(
            endpoint=ROUTE_USER_TRADES,
            symbol=symbol,
            window_start_ms=start_ms,
            window_end_ms=end_ms,
        )
        pages_done = existing_cp.pages_completed if existing_cp else 0
        last_id = int(existing_cp.last_accepted_id) if (existing_cp and existing_cp.last_accepted_id is not None) else None
        last_time = existing_cp.last_accepted_time_ms if existing_cp else None
        last_receipt: EndpointCallReceipt | None = None
        seen_cursors: set[str] = set()
        error_code: str | None = None
        error_detail: str | None = None
        complete = len(gaps) == 0

        if existing_cp and existing_cp.status == "COMPLETE":
            fills = self._store.load_all_fills(symbol=symbol)
            filtered = tuple(f for f in fills if start_ms <= f.trade_time_ms <= end_ms)
            cov = build_endpoint_coverage(
                endpoint=ROUTE_USER_TRADES,
                symbol=symbol,
                as_of_venue_ms=as_of_venue_ms,
                receipt=None,
                record_count=len(filtered),
                freshness_limit_ms=self._freshness_limit_ms,
                pages_fetched=existing_cp.pages_completed,
                page_coverage_complete=len(existing_cp.gap_windows) == 0,
                gap_windows=existing_cp.gap_windows,
                retention_warnings=existing_cp.retention_warnings,
            )
            return PaginationResult(
                endpoint=ROUTE_USER_TRADES,
                symbol=symbol,
                checkpoint=existing_cp,
                coverage=cov,
                fills=filtered,
            )

        if use_from_id:
            cursor_id = (last_id + 1) if last_id is not None else (initial_from_id if initial_from_id is not None else 0)
            for _ in range(self._max_pages_per_window):
                cursor_key = f"fromId:{cursor_id}"
                if cursor_key in seen_cursors:
                    gaps.append({"start_ms": start_ms, "end_ms": end_ms, "reason": "REPEATED_CURSOR_DISCONTINUITY"})
                    complete = False
                    break
                seen_cursors.add(cursor_key)
                try:
                    raw, receipt = self._client.get_user_trades(symbol=symbol, from_id=cursor_id, limit=page_limit)
                    last_receipt = receipt
                    page_fills = normalize_fills(raw)
                except AccountB3Error as exc:
                    error_code, error_detail = exc.code, exc.detail
                    gaps.append({"start_ms": last_time or start_ms, "end_ms": end_ms, "reason": exc.code})
                    complete = False
                    break

                ordered = tuple(sorted(page_fills, key=lambda f: (f.trade_id, f.trade_time_ms)))
                pages_done += 1
                if ordered:
                    max_tid = max(f.trade_id for f in ordered)
                    max_t = max(f.trade_time_ms for f in ordered)
                    if last_id is not None and max_tid <= last_id:
                        gaps.append({"start_ms": last_time or start_ms, "end_ms": end_ms, "reason": "NON_ADVANCING_CURSOR"})
                        complete = False
                        cp = PaginationCheckpoint(
                            endpoint=ROUTE_USER_TRADES,
                            symbol=symbol,
                            window_start_ms=start_ms,
                            window_end_ms=end_ms,
                            schema_version=SCHEMA_CHECKPOINT,
                            cursor_type="fromId",
                            cursor_value=str(cursor_id),
                            last_accepted_id=str(last_id),
                            last_accepted_time_ms=last_time,
                            pages_completed=pages_done,
                            status="PARTIAL",
                            gap_windows=tuple(gaps),
                            retention_warnings=tuple(warnings),
                            error_code="NON_ADVANCING_CURSOR",
                        )
                        self._store.commit_paginated_page(cp, fills=ordered)
                        break
                    last_id = max_tid if last_id is None else max(last_id, max_tid)
                    last_time = max_t if last_time is None else max(last_time, max_t)
                    next_cursor = last_id + 1
                else:
                    next_cursor = cursor_id

                is_done = len(ordered) < page_limit
                cp_status = ("COMPLETE" if complete else "PARTIAL") if is_done else "IN_PROGRESS"
                cp = PaginationCheckpoint(
                    endpoint=ROUTE_USER_TRADES,
                    symbol=symbol,
                    window_start_ms=start_ms,
                    window_end_ms=end_ms,
                    schema_version=SCHEMA_CHECKPOINT,
                    cursor_type="fromId",
                    cursor_value=str(next_cursor),
                    last_accepted_id=str(last_id) if last_id is not None else None,
                    last_accepted_time_ms=last_time,
                    pages_completed=pages_done,
                    status=cp_status,
                    gap_windows=tuple(gaps),
                    retention_warnings=tuple(warnings),
                )
                hook = (lambda p=pages_done: before_page_commit(p)) if before_page_commit else None
                self._store.commit_paginated_page(cp, fills=ordered, before_commit=hook)
                if is_done:
                    break
                cursor_id = next_cursor
            else:
                gaps.append({"start_ms": last_time or start_ms, "end_ms": end_ms, "reason": "PAGE_LIMIT_REACHED"})
                complete = False
        else:
            for win_start, win_end in windows:
                cur_start = win_start
                if last_time is not None and last_time >= win_start and last_time <= win_end:
                    # Resume safely with overlap at last_time so records sharing the same ms are never dropped;
                    # stable trade_id primary key prevents double-counting.
                    cur_start = last_time
                for _ in range(self._max_pages_per_window):
                    cursor_key = f"win:{cur_start}:{win_end}"
                    if cursor_key in seen_cursors:
                        gaps.append({"start_ms": cur_start, "end_ms": win_end, "reason": "REPEATED_CURSOR_DISCONTINUITY"})
                        complete = False
                        break
                    seen_cursors.add(cursor_key)
                    try:
                        raw, receipt = self._client.get_user_trades(
                            symbol=symbol,
                            start_time=cur_start,
                            end_time=win_end,
                            limit=page_limit,
                        )
                        last_receipt = receipt
                        page_fills = normalize_fills(raw)
                    except AccountB3Error as exc:
                        error_code, error_detail = exc.code, exc.detail
                        gaps.append({"start_ms": cur_start, "end_ms": win_end, "reason": exc.code})
                        complete = False
                        break

                    ordered = tuple(sorted(page_fills, key=lambda f: (f.trade_time_ms, f.trade_id)))
                    pages_done += 1
                    if ordered:
                        page_max_id = max(f.trade_id for f in ordered)
                        page_max_t = max(f.trade_time_ms for f in ordered)
                        last_id = page_max_id if last_id is None else max(last_id, page_max_id)
                        last_time = page_max_t if last_time is None else max(last_time, page_max_t)
                    is_window_done = len(ordered) < page_limit
                    next_start = (ordered[-1].trade_time_ms + 1) if (ordered and not is_window_done) else (win_end + 1)
                    if not is_window_done and next_start <= cur_start:
                        gaps.append({"start_ms": cur_start, "end_ms": win_end, "reason": "NON_ADVANCING_TIME_CURSOR"})
                        complete = False
                        is_window_done = True

                    cp = PaginationCheckpoint(
                        endpoint=ROUTE_USER_TRADES,
                        symbol=symbol,
                        window_start_ms=start_ms,
                        window_end_ms=end_ms,
                        schema_version=SCHEMA_CHECKPOINT,
                        cursor_type="time",
                        cursor_value=str(next_start),
                        last_accepted_id=str(last_id) if last_id is not None else None,
                        last_accepted_time_ms=last_time,
                        pages_completed=pages_done,
                        status="IN_PROGRESS",
                        gap_windows=tuple(gaps),
                        retention_warnings=tuple(warnings),
                        error_code=error_code,
                    )
                    hook = (lambda p=pages_done: before_page_commit(p)) if before_page_commit else None
                    self._store.commit_paginated_page(cp, fills=ordered, before_commit=hook)
                    if is_window_done or next_start > win_end:
                        break
                    cur_start = next_start
                if error_code is not None:
                    break

        final_status = "COMPLETE" if (complete and error_code is None and len(gaps) == 0) else "PARTIAL"
        if error_code is not None and pages_done == 0:
            final_status = "ERROR"
        final_cp = PaginationCheckpoint(
            endpoint=ROUTE_USER_TRADES,
            symbol=symbol,
            window_start_ms=start_ms,
            window_end_ms=end_ms,
            schema_version=SCHEMA_CHECKPOINT,
            cursor_type="fromId" if use_from_id else "time",
            cursor_value=str(last_id + 1) if (use_from_id and last_id is not None) else str(last_time or end_ms),
            last_accepted_id=str(last_id) if last_id is not None else None,
            last_accepted_time_ms=last_time,
            pages_completed=pages_done,
            status=final_status,
            gap_windows=tuple(gaps),
            retention_warnings=tuple(warnings),
            error_code=error_code,
        )
        self._store.commit_paginated_page(final_cp)
        stored_fills = self._store.load_all_fills(symbol=symbol)
        if not use_from_id:
            stored_fills = tuple(f for f in stored_fills if start_ms <= f.trade_time_ms <= end_ms)
        cov = build_endpoint_coverage(
            endpoint=ROUTE_USER_TRADES,
            symbol=symbol,
            as_of_venue_ms=as_of_venue_ms,
            receipt=last_receipt,
            record_count=len(stored_fills),
            freshness_limit_ms=self._freshness_limit_ms,
            pages_fetched=pages_done,
            page_coverage_complete=final_status == "COMPLETE",
            gap_windows=gaps,
            retention_warnings=warnings,
            error_code=error_code,
            error_detail=error_detail,
        )
        return PaginationResult(
            endpoint=ROUTE_USER_TRADES,
            symbol=symbol,
            checkpoint=final_cp,
            coverage=cov,
            fills=stored_fills,
        )

    def sync_all_orders(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        as_of_venue_ms: int,
        page_limit: int = 500,
        before_page_commit: Callable[[int], None] | None = None,
    ) -> PaginationResult:
        """Paginate /fapi/v1/allOrders with strictly <7d windows and 90d/3d retention tracking."""
        windows, gaps, warnings = plan_bounded_windows(
            endpoint=ROUTE_ALL_ORDERS,
            start_ms=start_ms,
            end_ms=end_ms,
            as_of_venue_ms=as_of_venue_ms,
        )
        existing_cp = self._store.load_checkpoint(
            endpoint=ROUTE_ALL_ORDERS,
            symbol=symbol,
            window_start_ms=start_ms,
            window_end_ms=end_ms,
        )
        pages_done = existing_cp.pages_completed if existing_cp else 0
        last_id = int(existing_cp.last_accepted_id) if (existing_cp and existing_cp.last_accepted_id is not None) else None
        last_time = existing_cp.last_accepted_time_ms if existing_cp else None
        last_receipt: EndpointCallReceipt | None = None
        seen_cursors: set[str] = set()
        error_code: str | None = None
        error_detail: str | None = None
        complete = len(gaps) == 0

        for win_start, win_end in windows:
            cur_start = last_time if (last_time is not None and win_start <= last_time <= win_end) else win_start
            for _ in range(self._max_pages_per_window):
                cursor_key = f"orders:{cur_start}:{win_end}"
                if cursor_key in seen_cursors:
                    gaps.append({"start_ms": cur_start, "end_ms": win_end, "reason": "REPEATED_CURSOR_DISCONTINUITY"})
                    complete = False
                    break
                seen_cursors.add(cursor_key)
                try:
                    raw, receipt = self._client.get_all_orders(
                        symbol=symbol, start_time=cur_start, end_time=win_end, limit=page_limit
                    )
                    last_receipt = receipt
                    page_orders = normalize_orders(raw, source_endpoint=ROUTE_ALL_ORDERS)
                except AccountB3Error as exc:
                    error_code, error_detail = exc.code, exc.detail
                    gaps.append({"start_ms": cur_start, "end_ms": win_end, "reason": exc.code})
                    complete = False
                    break

                ordered = tuple(sorted(page_orders, key=lambda o: (o.update_time_ms or 0, o.order_id)))
                pages_done += 1
                if ordered:
                    max_oid = max(o.order_id for o in ordered)
                    max_t = max(o.update_time_ms or o.create_time_ms or cur_start for o in ordered)
                    last_id = max_oid if last_id is None else max(last_id, max_oid)
                    last_time = max_t if last_time is None else max(last_time, max_t)
                is_win_done = len(ordered) < page_limit
                next_start = ((ordered[-1].update_time_ms or cur_start) + 1) if (ordered and not is_win_done) else (win_end + 1)
                if not is_win_done and next_start <= cur_start:
                    gaps.append({"start_ms": cur_start, "end_ms": win_end, "reason": "NON_ADVANCING_TIME_CURSOR"})
                    complete = False
                    is_win_done = True

                cp = PaginationCheckpoint(
                    endpoint=ROUTE_ALL_ORDERS,
                    symbol=symbol,
                    window_start_ms=start_ms,
                    window_end_ms=end_ms,
                    schema_version=SCHEMA_CHECKPOINT,
                    cursor_type="time",
                    cursor_value=str(next_start),
                    last_accepted_id=str(last_id) if last_id is not None else None,
                    last_accepted_time_ms=last_time,
                    pages_completed=pages_done,
                    status="IN_PROGRESS",
                    gap_windows=tuple(gaps),
                    retention_warnings=tuple(warnings),
                    error_code=error_code,
                )
                hook = (lambda p=pages_done: before_page_commit(p)) if before_page_commit else None
                self._store.commit_paginated_page(cp, orders=ordered, before_commit=hook)
                if is_win_done or next_start > win_end:
                    break
                cur_start = next_start
            if error_code is not None:
                break

        final_status = "COMPLETE" if (complete and error_code is None and len(gaps) == 0) else "PARTIAL"
        if error_code is not None and pages_done == 0:
            final_status = "ERROR"
        final_cp = PaginationCheckpoint(
            endpoint=ROUTE_ALL_ORDERS,
            symbol=symbol,
            window_start_ms=start_ms,
            window_end_ms=end_ms,
            schema_version=SCHEMA_CHECKPOINT,
            cursor_type="time",
            cursor_value=str(last_time or end_ms),
            last_accepted_id=str(last_id) if last_id is not None else None,
            last_accepted_time_ms=last_time,
            pages_completed=pages_done,
            status=final_status,
            gap_windows=tuple(gaps),
            retention_warnings=tuple(warnings),
            error_code=error_code,
        )
        self._store.commit_paginated_page(final_cp)
        stored_orders = self._store.load_all_orders(symbol=symbol, source_endpoint=ROUTE_ALL_ORDERS)
        cov = build_endpoint_coverage(
            endpoint=ROUTE_ALL_ORDERS,
            symbol=symbol,
            as_of_venue_ms=as_of_venue_ms,
            receipt=last_receipt,
            record_count=len(stored_orders),
            freshness_limit_ms=self._freshness_limit_ms,
            pages_fetched=pages_done,
            page_coverage_complete=final_status == "COMPLETE",
            gap_windows=gaps,
            retention_warnings=warnings,
            error_code=error_code,
            error_detail=error_detail,
        )
        return PaginationResult(
            endpoint=ROUTE_ALL_ORDERS,
            symbol=symbol,
            checkpoint=final_cp,
            coverage=cov,
            orders=stored_orders,
        )

    def sync_all_algo_orders(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        as_of_venue_ms: int,
        page_limit: int = 100,
        before_page_commit: Callable[[int], None] | None = None,
    ) -> PaginationResult:
        """Paginate /fapi/v1/allAlgoOrders with strictly <7d windows and page/time cursors."""
        windows, gaps, warnings = plan_bounded_windows(
            endpoint=ROUTE_ALL_ALGO_ORDERS,
            start_ms=start_ms,
            end_ms=end_ms,
            as_of_venue_ms=as_of_venue_ms,
        )
        existing_cp = self._store.load_checkpoint(
            endpoint=ROUTE_ALL_ALGO_ORDERS,
            symbol=symbol,
            window_start_ms=start_ms,
            window_end_ms=end_ms,
        )
        pages_done = existing_cp.pages_completed if existing_cp else 0
        last_id = int(existing_cp.last_accepted_id) if (existing_cp and existing_cp.last_accepted_id is not None) else None
        last_time = existing_cp.last_accepted_time_ms if existing_cp else None
        last_receipt: EndpointCallReceipt | None = None
        error_code: str | None = None
        error_detail: str | None = None
        complete = len(gaps) == 0

        for win_start, win_end in windows:
            page_num = 1
            seen_page_digests: set[tuple[int, ...]] = set()
            for _ in range(self._max_pages_per_window):
                try:
                    raw, receipt = self._client.get_all_algo_orders(
                        symbol=symbol, start_time=win_start, end_time=win_end, page=page_num, limit=page_limit
                    )
                    last_receipt = receipt
                    page_algos = normalize_algo_orders(raw, source_endpoint=ROUTE_ALL_ALGO_ORDERS)
                except AccountB3Error as exc:
                    error_code, error_detail = exc.code, exc.detail
                    gaps.append({"start_ms": win_start, "end_ms": win_end, "reason": exc.code})
                    complete = False
                    break

                ordered = tuple(sorted(page_algos, key=lambda a: (a.update_time_ms or a.create_time_ms or 0, a.algo_id)))
                page_sig = tuple(a.algo_id for a in ordered)
                pages_done += 1
                if ordered and page_sig in seen_page_digests:
                    gaps.append({"start_ms": win_start, "end_ms": win_end, "reason": "REPEATED_PAGE_DISCONTINUITY"})
                    complete = False
                    break
                if ordered:
                    seen_page_digests.add(page_sig)
                    max_aid = max(a.algo_id for a in ordered)
                    max_t = max(a.update_time_ms or a.create_time_ms or win_start for a in ordered)
                    last_id = max_aid if last_id is None else max(last_id, max_aid)
                    last_time = max_t if last_time is None else max(last_time, max_t)

                is_win_done = len(ordered) < page_limit
                cp = PaginationCheckpoint(
                    endpoint=ROUTE_ALL_ALGO_ORDERS,
                    symbol=symbol,
                    window_start_ms=start_ms,
                    window_end_ms=end_ms,
                    schema_version=SCHEMA_CHECKPOINT,
                    cursor_type="page",
                    cursor_value=str(page_num + 1),
                    last_accepted_id=str(last_id) if last_id is not None else None,
                    last_accepted_time_ms=last_time,
                    pages_completed=pages_done,
                    status="IN_PROGRESS",
                    gap_windows=tuple(gaps),
                    retention_warnings=tuple(warnings),
                    error_code=error_code,
                )
                hook = (lambda p=pages_done: before_page_commit(p)) if before_page_commit else None
                self._store.commit_paginated_page(cp, algo_orders=ordered, before_commit=hook)
                if is_win_done:
                    break
                page_num += 1
            if error_code is not None:
                break

        final_status = "COMPLETE" if (complete and error_code is None and len(gaps) == 0) else "PARTIAL"
        if error_code is not None and pages_done == 0:
            final_status = "ERROR"
        final_cp = PaginationCheckpoint(
            endpoint=ROUTE_ALL_ALGO_ORDERS,
            symbol=symbol,
            window_start_ms=start_ms,
            window_end_ms=end_ms,
            schema_version=SCHEMA_CHECKPOINT,
            cursor_type="page",
            cursor_value=str(last_id) if last_id is not None else None,
            last_accepted_id=str(last_id) if last_id is not None else None,
            last_accepted_time_ms=last_time,
            pages_completed=pages_done,
            status=final_status,
            gap_windows=tuple(gaps),
            retention_warnings=tuple(warnings),
            error_code=error_code,
        )
        self._store.commit_paginated_page(final_cp)
        stored_algos = self._store.load_all_algo_orders(symbol=symbol, source_endpoint=ROUTE_ALL_ALGO_ORDERS)
        cov = build_endpoint_coverage(
            endpoint=ROUTE_ALL_ALGO_ORDERS,
            symbol=symbol,
            as_of_venue_ms=as_of_venue_ms,
            receipt=last_receipt,
            record_count=len(stored_algos),
            freshness_limit_ms=self._freshness_limit_ms,
            pages_fetched=pages_done,
            page_coverage_complete=final_status == "COMPLETE",
            gap_windows=gaps,
            retention_warnings=warnings,
            error_code=error_code,
            error_detail=error_detail,
        )
        return PaginationResult(
            endpoint=ROUTE_ALL_ALGO_ORDERS,
            symbol=symbol,
            checkpoint=final_cp,
            coverage=cov,
            algo_orders=stored_algos,
        )

    def sync_income(
        self,
        *,
        symbol: str | None,
        start_ms: int | None,
        end_ms: int | None,
        as_of_venue_ms: int,
        income_type: str | None = None,
        page_limit: int = 500,
        before_page_commit: Callable[[int], None] | None = None,
    ) -> PaginationResult:
        """Incrementally paginate /fapi/v1/income (default 7d window, 3-month retention, weight 30)."""
        eff_end = as_of_venue_ms if end_ms is None else end_ms
        eff_start = (eff_end - DEFAULT_INCOME_WINDOW_MS) if start_ms is None else start_ms
        sym_key = symbol or ""
        windows, gaps, warnings = plan_bounded_windows(
            endpoint=ROUTE_INCOME,
            start_ms=eff_start,
            end_ms=eff_end,
            as_of_venue_ms=as_of_venue_ms,
        )
        existing_cp = self._store.load_checkpoint(
            endpoint=ROUTE_INCOME,
            symbol=sym_key,
            window_start_ms=eff_start,
            window_end_ms=eff_end,
        )
        pages_done = existing_cp.pages_completed if existing_cp else 0
        last_id = existing_cp.last_accepted_id if existing_cp else None
        last_time = existing_cp.last_accepted_time_ms if existing_cp else None
        last_receipt: EndpointCallReceipt | None = None
        seen_cursors: set[str] = set()
        error_code: str | None = None
        error_detail: str | None = None
        complete = len(gaps) == 0

        for win_start, win_end in windows:
            cur_start = last_time if (last_time is not None and win_start <= last_time <= win_end) else win_start
            for _ in range(self._max_pages_per_window):
                cursor_key = f"inc:{cur_start}:{win_end}"
                if cursor_key in seen_cursors:
                    gaps.append({"start_ms": cur_start, "end_ms": win_end, "reason": "REPEATED_CURSOR_DISCONTINUITY"})
                    complete = False
                    break
                seen_cursors.add(cursor_key)
                try:
                    raw, receipt = self._client.get_income(
                        symbol=symbol,
                        income_type=income_type,
                        start_time=cur_start,
                        end_time=win_end,
                        limit=page_limit,
                    )
                    last_receipt = receipt
                    page_rows = normalize_income(raw)
                except AccountB3Error as exc:
                    error_code, error_detail = exc.code, exc.detail
                    gaps.append({"start_ms": cur_start, "end_ms": win_end, "reason": exc.code})
                    complete = False
                    break

                ordered = tuple(sorted(page_rows, key=lambda r: (r.time_ms, r.tran_id, r.income_type, r.asset)))
                pages_done += 1
                if ordered:
                    last_id = ordered[-1].tran_id
                    max_t = max(r.time_ms for r in ordered)
                    last_time = max_t if last_time is None else max(last_time, max_t)
                is_win_done = len(ordered) < page_limit
                next_start = (ordered[-1].time_ms + 1) if (ordered and not is_win_done) else (win_end + 1)
                if not is_win_done and next_start <= cur_start:
                    gaps.append({"start_ms": cur_start, "end_ms": win_end, "reason": "NON_ADVANCING_TIME_CURSOR"})
                    complete = False
                    is_win_done = True

                cp = PaginationCheckpoint(
                    endpoint=ROUTE_INCOME,
                    symbol=sym_key,
                    window_start_ms=eff_start,
                    window_end_ms=eff_end,
                    schema_version=SCHEMA_CHECKPOINT,
                    cursor_type="time",
                    cursor_value=str(next_start),
                    last_accepted_id=last_id,
                    last_accepted_time_ms=last_time,
                    pages_completed=pages_done,
                    status="IN_PROGRESS",
                    gap_windows=tuple(gaps),
                    retention_warnings=tuple(warnings),
                    error_code=error_code,
                )
                hook = (lambda p=pages_done: before_page_commit(p)) if before_page_commit else None
                self._store.commit_paginated_page(cp, income_rows=ordered, before_commit=hook)
                if is_win_done or next_start > win_end:
                    break
                cur_start = next_start
            if error_code is not None:
                break

        final_status = "COMPLETE" if (complete and error_code is None and len(gaps) == 0) else "PARTIAL"
        if error_code is not None and pages_done == 0:
            final_status = "ERROR"
        final_cp = PaginationCheckpoint(
            endpoint=ROUTE_INCOME,
            symbol=sym_key,
            window_start_ms=eff_start,
            window_end_ms=eff_end,
            schema_version=SCHEMA_CHECKPOINT,
            cursor_type="time",
            cursor_value=str(last_time or eff_end),
            last_accepted_id=last_id,
            last_accepted_time_ms=last_time,
            pages_completed=pages_done,
            status=final_status,
            gap_windows=tuple(gaps),
            retention_warnings=tuple(warnings),
            error_code=error_code,
        )
        self._store.commit_paginated_page(final_cp)
        stored_income = self._store.load_all_income(symbol=symbol)
        stored_income = tuple(r for r in stored_income if eff_start <= r.time_ms <= eff_end)
        cov = build_endpoint_coverage(
            endpoint=ROUTE_INCOME,
            symbol=symbol,
            as_of_venue_ms=as_of_venue_ms,
            receipt=last_receipt,
            record_count=len(stored_income),
            freshness_limit_ms=self._freshness_limit_ms,
            pages_fetched=pages_done,
            page_coverage_complete=final_status == "COMPLETE",
            gap_windows=gaps,
            retention_warnings=warnings,
            error_code=error_code,
            error_detail=error_detail,
        )
        return PaginationResult(
            endpoint=ROUTE_INCOME,
            symbol=symbol,
            checkpoint=final_cp,
            coverage=cov,
            income_rows=stored_income,
        )
