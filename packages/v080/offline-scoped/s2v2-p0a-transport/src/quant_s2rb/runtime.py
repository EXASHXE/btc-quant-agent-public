"""Compose the sealed S2 V2 ledger and console with the release-bound adapter."""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from quant_personal_public_b1.normalize import exchange_info, obj
from quant_personal_public_b1.normalize import integer as exchange_integer
from quant_personal_public_b1.policy import SYMBOLS, SourceBlocked
from quant_personal_public_b1.wire import json_body
from quant_s2v2 import RESIDUAL
from quant_s2v2.console import tty_check
from quant_s2v2.ledger import open_ledger
from quant_s2v2.protocol import (
    GETS,
    WINDOW_MS,
    Clock,
    Denied,
    digest,
    file_bytes,
    integer,
    require,
    sha,
    strict_json,
)

from . import CLOSED, FIXTURE_DOMAIN, FIXTURE_EVIDENCE, LIVE_DOMAIN, LIVE_EVIDENCE, SCHEMA
from ._inherited import check_envelope, confirm, read_config, runtime_identity
from .policy import Egress, loopback_namespace, no_proxy
from .release import production_roots, verify_release
from .wire import Wire


@dataclass(frozen=True)
class Paths:
    configuration: Path
    grant: Path
    wheel: Path


def _accept_reply(reply, index, sent, received, weight_upper, weight_cap, count_cap, previous):
    if 300 <= reply.status < 400:
        raise Denied("REDIRECT_FORBIDDEN")
    if reply.status != 200:
        raise Denied(f"HTTP_{reply.status}")
    require(
        reply.complete
        and reply.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        == "application/json",
        "MALFORMED_CONTENT_TYPE",
    )
    used = int(reply.headers["x-mbx-used-weight-1m"])
    require(
        index <= used <= weight_upper and (previous is None or used == previous + 1),
        "UNRECONCILED_SHARED_WEIGHT",
    )
    try:
        payload = obj(json_body(reply.body))
        if index == 1:
            require(payload.keys() == {"serverTime"}, "MALFORMED_TIME_REPLY")
            server = exchange_integer(payload["serverTime"], "serverTime", minimum=1)
            require(sent - 500 <= server <= received + 500, "VENUE_TIME_OUTSIDE_BOUND")
        else:
            # The metadata endpoint is not an authoritative venue time sample.
            _, limits = exchange_info(payload, tuple(sorted(SYMBOLS)))
            require(
                ("REQUEST_WEIGHT", WINDOW_MS) in limits
                and max(used, weight_cap) <= limits[("REQUEST_WEIGHT", WINDOW_MS)]
                and (
                    ("RAW_REQUESTS", WINDOW_MS) not in limits
                    or count_cap <= limits[("RAW_REQUESTS", WINDOW_MS)]
                ),
                "VENUE_ROLLING_LIMIT_UNVERIFIED",
            )
    except SourceBlocked as exc:
        raise Denied(
            "MALFORMED_OR_INELIGIBLE_METADATA" if index == 2 else "MALFORMED_TIME_REPLY"
        ) from exc
    return used, digest(
        {
            "tls": reply.tls,
            "request": GETS[index - 1],
            "used_weight": used,
            "body_sha": sha(reply.body),
        }
    )


def _stop(ledger, grant, index, clock, code, reply):
    now = clock.now()
    cooldown = 0
    if code == "HTTP_429" and reply is not None:
        after = reply.headers.get("retry-after")
        if (
            type(after) is str
            and re.fullmatch(r"[0-9]{1,4}", after)
            and integer(int(after), 1, 3600)
        ):
            cooldown = now + int(after) * 1000
    ledger.result(grant, index, now, code, latch=cooldown == 0, hold_until=cooldown)


def _execute(paths, evidence, domain):
    live = evidence == LIVE_EVIDENCE
    if live:
        roots = production_roots()
        require(
            sys.flags.isolated and sys.flags.dont_write_bytecode, "TRUSTED_ISOLATED_LAUNCH_REQUIRED"
        )
        require(
            paths == Paths(roots.configuration, roots.grant, roots.wheel) and domain == LIVE_DOMAIN,
            "PRODUCTION_ENROLLMENT_MISMATCH",
        )
    else:
        require(evidence == FIXTURE_EVIDENCE and domain == FIXTURE_DOMAIN, "FIXTURE_SCOPE_REQUIRED")
        loopback_namespace()
    no_proxy()
    tty_check()
    config = read_config(paths.configuration, evidence)
    if live:
        require(
            config.controller_key == roots.controller_key and config.route_sha == roots.policy_sha,
            "PRODUCTION_ENROLLMENT_MISMATCH",
        )
    runtime_identity(config)
    verify_release(paths.wheel, config.release_sha)
    policy = Egress.read(config, evidence)
    pem = file_bytes(config.ca_path, maximum=1_048_576, protected=True)
    require(sha(pem) == config.ca_sha, "CA_PIN_CHANGED")
    original = file_bytes(paths.grant, protected=True)
    grant = check_envelope(
        strict_json(original), config, schema=SCHEMA, domain=domain, evidence=evidence
    )
    clock = Clock()

    def check_inputs(now):
        grant.check_time(now)
        policy.check(now)
        require(read_config(paths.configuration, evidence) == config, "CONFIG_CHANGED")
        require(file_bytes(paths.grant, protected=True) == original, "GRANT_FILE_CHANGED")
        require(
            file_bytes(config.ca_path, maximum=1_048_576, protected=True) == pem, "CA_PIN_CHANGED"
        )
        config.check_storage()

    with open_ledger(config) as ledger:
        now = clock.now()
        check_inputs(now)
        ledger.available(grant, now)
        ledger.budget(grant, now, 2)

        def pre_effect():
            check_inputs(clock.now())
            require(ledger.verify() == ledger.lines, "STATE_CHANGED_DURING_INVOCATION")
            pending = ledger.events[-1]
            require(
                pending["kind"] == "reserve"
                and pending["index"] == index
                and pending["run_id"] == grant.run_id
                and pending["debit"] == 1,
                "DURABLE_RESERVATION_REQUIRED",
            )

        wire = Wire(policy, pem, pre_effect)
        confirm(grant, clock)
        verify_release(paths.wheel, config.release_sha)
        now = clock.now()
        check_inputs(now)
        ledger.claim(grant, now)
        previous = None
        for index, request in enumerate(grant.scope["requests"], 1):
            verify_release(paths.wheel, config.release_sha)
            now = clock.now()
            check_inputs(now)
            local_used = ledger.reserve(grant, request, now, index)
            sent = clock.now()
            check_inputs(sent)
            deadline_ms = min(
                grant.scope["expires_ms"],
                policy.expires_ms,
                grant.budget["shared_observed_ms"] + WINDOW_MS,
            )
            reply = None
            try:
                reply = wire.exchange(request, (deadline_ms - sent) / 1000)
                received = clock.now()
                check_inputs(received)
                previous, receipt = _accept_reply(
                    reply,
                    index,
                    sent,
                    received,
                    local_used + grant.budget["shared_weight_upper"],
                    grant.budget["weight_cap"],
                    grant.budget["count_cap"],
                    previous,
                )
            except (Denied, OSError) as exc:
                _stop(
                    ledger,
                    grant,
                    index,
                    clock,
                    str(exc) if isinstance(exc, Denied) else "WIRE_AMBIGUOUS",
                    reply,
                )
                raise
            ledger.result(grant, index, received, "OK", receipt=receipt)
    return {
        "authorization": CLOSED if evidence == FIXTURE_EVIDENCE else "EXACT_SCOPE_CONSUMED",
        "evidence": evidence,
        "status": "NOT_EVALUATED",
        "cards": [],
        "attempts": 2,
        "weight": 2,
        "retry_count": 0,
        "residual": RESIDUAL,
    }


def run_production():
    roots = production_roots()
    return _execute(
        Paths(roots.configuration, roots.grant, roots.wheel), LIVE_EVIDENCE, LIVE_DOMAIN
    )


def rehearse_loopback(paths):
    """Test harness API strictly limited to the reserved name and a private loopback network."""
    return _execute(paths, FIXTURE_EVIDENCE, FIXTURE_DOMAIN)
