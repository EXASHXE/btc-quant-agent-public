from __future__ import annotations

import ssl
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from email.utils import formatdate

import pytest

from btc_quant_agent.config import DataConfig
from btc_quant_agent.data.binance import (
    BinanceDataError,
    BinancePublicClient,
    classify_public_error,
)
from btc_quant_agent.data.rest import (
    BoundedRequester,
    RequestCancelled,
    RequestDeadline,
    RequestPolicy,
    RestCoordinator,
    retry_after_seconds,
    shared_coordinator,
)


class Clock:
    def __init__(self):
        self.now = 0.0
        self.wall = 1_700_000_000.0
        self.delays = []

    def wait(self, delay):
        self.delays.append(delay)
        self.now += delay
        self.wall -= 10_000  # NTP rollback must not affect elapsed budgets.
        return False


def http_error(code, header=None):
    headers = Message()
    if header is not None:
        headers["Retry-After"] = header
    return urllib.error.HTTPError("https://synthetic.invalid", code, "synthetic", headers, None)


def requester(clock, **kwargs):
    return BoundedRequester(RequestPolicy(1, 10, 3, 0.1, 1, 0), RestCoordinator(),
                            monotonic=lambda: clock.now, wall_time=lambda: clock.wall,
                            wait=clock.wait, **kwargs)


@pytest.mark.parametrize("error", [http_error(500), http_error(503), TimeoutError("synthetic")])
def test_transient_failure_stops_at_budget_despite_wall_rollback(error):
    clock = Clock()
    calls = []

    def operation():
        calls.append(clock.now)
        raise error

    with pytest.raises(type(error)):
        requester(clock).run(operation, retryable=lambda exc: classify_public_error(exc)[1])
    assert len(calls) == 3
    assert clock.delays == pytest.approx([0.1, 0.2])
    assert clock.now == pytest.approx(0.3)


@pytest.mark.parametrize("header,delay", [("0.3", 0.3), ("999999999", 1), ("nan", 0.1), ("bad date", 0.1), ("-1", 0.1)])
def test_retry_after_capped_or_rejected_then_positive_success(header, delay):
    clock = Clock()
    calls = []

    def operation():
        calls.append(clock.now)
        if len(calls) == 1:
            raise http_error(429, header)
        return {"serverTime": 123}

    assert requester(clock).run(operation, retryable=lambda exc: classify_public_error(exc)[1]) == {"serverTime": 123}
    assert clock.delays == pytest.approx([delay])
    assert len(calls) == 2


def test_http_date_and_absurd_wait_cap():
    wall = 1_700_000_000
    error = http_error(429, formatdate(wall + 300, usegmt=True))
    assert retry_after_seconds(error, 1, lambda: wall) == 1
    assert retry_after_seconds(http_error(429, "inf"), 1, lambda: wall) == 1


@pytest.mark.parametrize("error", [http_error(400), http_error(401), http_error(403), ValueError("schema"), urllib.error.URLError(ssl.SSLCertVerificationError("synthetic certificate"))])
def test_deterministic_errors_never_retry(error):
    clock = Clock()
    calls = []

    def operation():
        calls.append(1)
        raise error

    with pytest.raises(type(error)):
        requester(clock).run(operation, retryable=lambda exc: classify_public_error(exc)[1])
    assert calls == [1]
    assert clock.delays == []


def test_slow_transport_bounded_and_quarantined_not_amplified():
    release = threading.Event()
    calls = []
    coordinator = RestCoordinator()
    owner = BoundedRequester(RequestPolicy(0.05, 0.12, 3, 0.01, 0.02, 0), coordinator)

    def operation():
        calls.append(1)
        release.wait(2)
        return "late"

    start = time.monotonic()
    try:
        with pytest.raises(RequestDeadline):
            owner.run(operation, retryable=lambda exc: True)
        with pytest.raises(RequestDeadline):
            owner.run(operation, retryable=lambda exc: True)
        assert len(calls) == 1
        assert time.monotonic() - start < 0.8
    finally:
        release.set()


def test_cancellation_during_backoff_exits_promptly():
    cancelled = threading.Event()
    first = threading.Event()
    calls = []
    owner = BoundedRequester(RequestPolicy(1, 5, 3, 1, 2, 0), RestCoordinator(), cancelled=cancelled)

    def operation():
        calls.append(1)
        first.set()
        raise http_error(429, "2")

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(owner.run, operation, retryable=lambda exc: True)
        assert first.wait(1)
        cancelled.set()
        with pytest.raises(RequestCancelled):
            future.result(timeout=0.5)
    assert calls == [1]


def test_shared_cooldown_honored_by_competing_caller():
    clock = Clock()
    coordinator = RestCoordinator()
    coordinator.not_before = 0.5
    first = requester(clock)
    second = requester(clock)
    first.coordinator = coordinator
    second.coordinator = coordinator
    assert first.run(lambda: "one", retryable=lambda exc: False) == "one"
    assert second.run(lambda: "two", retryable=lambda exc: False) == "two"
    assert clock.now == 0.5
    assert shared_coordinator("synthetic-origin") is shared_coordinator("synthetic-origin")


def test_concurrent_callers_share_429_cooldown_and_start_spacing():
    coordinator = RestCoordinator()
    policy = RequestPolicy(1, 2, 3, 0.1, 0.2, 0.02)
    owners = [BoundedRequester(policy, coordinator) for _ in range(2)]
    barrier = threading.Barrier(2)
    starts = []

    def operation():
        starts.append(time.monotonic())
        if len(starts) == 1:
            raise http_error(429, "0.1")
        return "success"

    def caller(owner):
        barrier.wait(timeout=1)
        return owner.run(operation, retryable=lambda exc: classify_public_error(exc)[1])

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(caller, owners)) == ["success", "success"]
    assert len(starts) == 3
    assert starts[1] - starts[0] >= 0.09
    assert starts[2] - starts[1] >= 0.015


@pytest.mark.parametrize("values", [(1, 1, True, 0, 1, 0), (float("nan"), 1, 3, 0, 1, 0), (1, 0, 3, 0, 1, 0), (1, 1, 3, 2, 1, 0), (1, 1, 11, 0, 1, 0)])
def test_invalid_policy_fails_closed(values):
    with pytest.raises(ValueError):
        RequestPolicy(*values)


def test_missing_typo_policy_and_requester_fail_closed():
    with pytest.raises(TypeError):
        RequestPolicy(attempt_timeout=1)
    with pytest.raises(TypeError):
        RequestPolicy(1, 2, 3, 0.1, 1, 0, typo=1)
    with pytest.raises(TypeError):
        BoundedRequester(None, RestCoordinator())


def test_overall_deadline_cuts_off_remaining_retries():
    clock = Clock()
    owner = requester(clock)
    owner.policy = RequestPolicy(1, 0.15, 3, 0.1, 1, 0)
    calls = []

    def operation():
        calls.append(clock.now)
        raise http_error(500)

    with pytest.raises(RequestDeadline):
        owner.run(operation, retryable=lambda exc: classify_public_error(exc)[1])
    assert len(calls) == 2
    assert clock.now == pytest.approx(0.15)


@pytest.mark.parametrize("body,expected", [(b'{"serverTime":123}', 123), (b"not JSON", None), (b"x" * (2 * 1024 * 1024 + 1), None)])
def test_mocked_urllib_body_bounds_and_schema_are_not_retried(monkeypatch, body, expected):
    calls = []
    clock = Clock()
    client = BinancePublicClient(DataConfig(rest_base_url="https://synthetic.invalid"))
    client._requester = requester(clock)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, maximum):
            assert maximum == 2 * 1024 * 1024 + 1
            return body

    def transport(request, *, timeout):
        assert request.full_url.startswith("https://synthetic.invalid/")
        assert 0 < timeout <= 1
        calls.append(1)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", transport)
    if expected is None:
        with pytest.raises(BinanceDataError, match="SCHEMA_ERROR|size bound"):
            client.server_time_ms()
    else:
        assert client.server_time_ms() == expected
    assert calls == [1]
    assert clock.delays == []
