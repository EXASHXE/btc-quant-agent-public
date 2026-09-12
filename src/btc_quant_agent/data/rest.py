"""Bounded urllib requester and shared per-origin REST scheduling (GET inputs only)."""

from __future__ import annotations

import math
import threading
import time
import urllib.error
from collections.abc import Callable
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import TypeVar

_T = TypeVar("_T")


class RequestCancelled(RuntimeError):
    pass


class RequestDeadline(TimeoutError):
    pass


@dataclass(frozen=True)
class RequestPolicy:
    attempt_timeout: float
    overall_timeout: float
    max_attempts: int
    backoff_base: float
    backoff_cap: float
    minimum_interval: float

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 10:
            raise ValueError("REST max_attempts must be an integer in [1,10]")
        for name in ("attempt_timeout", "overall_timeout", "backoff_base", "backoff_cap", "minimum_interval"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid REST {name}")
        if self.attempt_timeout <= 0 or self.overall_timeout <= 0 or self.backoff_cap < self.backoff_base:
            raise ValueError("invalid REST deadline/backoff bounds")

    @classmethod
    def for_timeout(cls, timeout: float) -> RequestPolicy:
        # Declared compatibility policy; no new economic/config identity fields.
        return cls(timeout, timeout * 3 + 2, 3, 0.1, 1.0, 0.05)


class RestCoordinator:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.transport_lock = threading.Lock()
        self.not_before = 0.0


_coordinators: dict[str, RestCoordinator] = {}
_coordinators_lock = threading.Lock()


def shared_coordinator(origin: str) -> RestCoordinator:
    with _coordinators_lock:
        return _coordinators.setdefault(origin, RestCoordinator())


def retry_after_seconds(exc: BaseException, cap: float, wall_time: Callable[[], float]) -> float | None:
    if not isinstance(exc, urllib.error.HTTPError) or exc.headers is None:
        return None
    value = exc.headers.get("Retry-After")
    if value is None:
        return None
    try:
        delay = float(value)
    except ValueError:
        try:
            delay = parsedate_to_datetime(value).timestamp() - wall_time()
        except (ValueError, TypeError, OverflowError):
            return None
    if math.isnan(delay) or delay < 0:
        return None
    return min(delay, cap)


class BoundedRequester:
    def __init__(
        self, policy: RequestPolicy, coordinator: RestCoordinator, *,
        monotonic: Callable[[], float] | None = None, wall_time: Callable[[], float] | None = None,
        cancelled: threading.Event | None = None, wait: Callable[[float], bool] | None = None,
    ) -> None:
        if not isinstance(policy, RequestPolicy) or not isinstance(coordinator, RestCoordinator):
            raise TypeError("explicit REST policy/coordinator required")
        self.policy = policy
        self.coordinator = coordinator
        self.monotonic = monotonic or time.monotonic
        self.wall_time = wall_time or time.time
        self.cancelled = cancelled or threading.Event()
        self.wait = wait or self.cancelled.wait
        self._local = threading.local()

    @property
    def transport_timeout(self) -> float:
        return float(getattr(self._local, "timeout", self.policy.attempt_timeout))

    def _remaining(self, deadline: float) -> float:
        if self.cancelled.is_set():
            raise RequestCancelled("REST request cancelled")
        remaining = deadline - self.monotonic()
        if remaining <= 0:
            raise RequestDeadline("REST overall deadline exhausted")
        return remaining

    def _turn(self, deadline: float) -> None:
        while True:
            remaining = self._remaining(deadline)
            with self.coordinator.lock:
                now = self.monotonic()
                delay = self.coordinator.not_before - now
                if delay <= 0:
                    self.coordinator.not_before = now + self.policy.minimum_interval
                    return
            if self.wait(min(delay, remaining)):
                raise RequestCancelled("REST request cancelled during backoff")

    def _invoke(self, operation: Callable[[], _T], deadline: float,
                failed: Callable[[Exception], None]) -> _T:
        # urllib DNS/open/read can outlive its socket timeout. Bound the caller too.
        # The origin lock remains held by a slow daemon transport until it exits:
        # subsequent callers expire/cancel, rather than spawning amplified workers.
        while not self.coordinator.transport_lock.acquire(timeout=min(0.05, self._remaining(deadline))):
            pass
        future: Future[_T] = Future()
        try:
            self._turn(deadline)
            timeout = min(self.policy.attempt_timeout, self._remaining(deadline))
        except BaseException:
            self.coordinator.transport_lock.release()
            raise

        def execute() -> None:
            self._local.timeout = timeout
            try:
                future.set_result(operation())
            except BaseException as exc:  # noqa: BLE001 - propagate worker failures, never retry them blindly
                try:
                    if isinstance(exc, Exception):
                        failed(exc)
                except BaseException as policy_error:  # noqa: BLE001 - forward policy failures too
                    future.set_exception(policy_error)
                else:
                    future.set_exception(exc)
            finally:
                self.coordinator.transport_lock.release()

        try:
            threading.Thread(target=execute, daemon=True).start()
        except BaseException:
            self.coordinator.transport_lock.release()
            raise
        attempt_deadline = min(deadline, self.monotonic() + timeout)
        while True:
            remaining = self._remaining(attempt_deadline)
            try:
                return future.result(timeout=min(0.05, remaining))
            except FutureTimeout:
                if future.done():
                    return future.result()

    def run(self, operation: Callable[[], _T], *, retryable: Callable[[BaseException], bool]) -> _T:
        deadline = self.monotonic() + self.policy.overall_timeout
        for attempt in range(self.policy.max_attempts):
            def failed(exc: Exception, retry_index: int = attempt) -> None:
                # Publish shared cooldown BEFORE releasing the origin transport
                # lock; queued callers must check it after taking ownership.
                if isinstance(exc, (RequestCancelled, RequestDeadline)) or not retryable(exc):
                    return
                cause = exc.__cause__ or exc
                header = retry_after_seconds(cause, self.policy.backoff_cap, self.wall_time)
                delay = header if header is not None else min(self.policy.backoff_base * 2**retry_index, self.policy.backoff_cap)
                with self.coordinator.lock:
                    self.coordinator.not_before = max(self.coordinator.not_before, self.monotonic() + delay)

            try:
                result = self._invoke(operation, deadline, failed)
                self._remaining(deadline)
                return result
            except (RequestCancelled, RequestDeadline):
                raise
            except Exception as exc:
                if not retryable(exc) or attempt + 1 == self.policy.max_attempts:
                    raise
        raise AssertionError("bounded REST attempt budget exhausted")
