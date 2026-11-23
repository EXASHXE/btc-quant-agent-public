"""Replay the installed release against bounded loopback TCP, DNS, and TLS."""

import contextlib
import errno
import json
import os
import pty
import re
import select
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fixture_support import PRIVATE, save, stamp
from loopback_fixture import RB_WHEEL, Lab, Run, certificates, fixture_root
from qa_entry import install_wire_guard
from quant_h4.approval import Claim, Permit, State
from quant_h4.fence import Denied as H4Denied
from quant_h4.fence import Witness, canonical
from quant_personal_live_public_b5.approval import verify_envelope
from quant_personal_live_public_b5.trust import TrustRoots
from quant_personal_public_b1.policy import SourceBlocked
from quant_s2rb import CLOSED, FIXTURE_EVIDENCE, FIXTURE_HOST, LIVE_DOMAIN, LIVE_EVIDENCE
from quant_s2rb.policy import Egress
from quant_s2rb.release import ProductionRoots, production_roots, verify_release
from quant_s2v2.protocol import GETS, ROUTES, Denied, strict_json

LINE = re.compile(rb"CHALLENGE (APPROVE [0-9a-f]{32} [0-9a-f]{64} [0-9a-f]{32})\r?\n")


@pytest.fixture(scope="session")
def certs():
    install_wire_guard()
    return certificates(fixture_root())


@contextlib.contextmanager
def terminal(run, *, fault="none", env=None):
    handle, slave = pty.openpty()
    try:
        with subprocess.Popen(
            [
                "/usr/bin/setpriv",
                "--reuid=64201",
                "--regid=64201",
                "--clear-groups",
                "--no-new-privs",
                "--bounding-set=-all",
                sys.executable,
                "-P",
                "-s",
                "-B",
                "/mnt/qa/qa_entry.py",
                *run.process_args(fault),
            ],
            start_new_session=True,
            cwd="/mnt",
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env={
                "PATH": "/usr/bin:/bin",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": "/mnt/site",
                "LC_ALL": "C.UTF-8",
                **(env or {}),
            },
        ) as child:
            os.close(slave)
            slave = None
            try:
                yield handle
            finally:
                os.close(handle)
                if child.poll() is None:
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        child.wait(timeout=2)
                if child.poll() is None:
                    child.kill()
    finally:
        if slave is not None:
            os.close(slave)
            os.close(handle)


def output(handle, *, challenge=False):
    collected = b""
    cutoff = time.monotonic() + 12
    while time.monotonic() < cutoff:
        ready, _, _ = select.select([handle], [], [], max(0, cutoff - time.monotonic()))
        if not ready:
            break
        try:
            piece = os.read(handle, 4096)
        except OSError as exc:
            if exc.errno != errno.EIO:
                raise
            break
        if not piece:
            break
        collected += piece
        if challenge and (matched := LINE.search(collected)):
            return matched[1]
    if challenge:
        raise AssertionError(collected[-1200:].decode(errors="replace"))
    return collected


def answer(handle, line):
    os.write(handle, line + b"\n")
    return output(handle)


def launch(run, *, fault="none"):
    with terminal(run, fault=fault) as handle:
        challenge = output(handle, challenge=True)
        return answer(handle, challenge)


def rejected(run, reason, env=None):
    with terminal(run, env=env) as handle:
        assert reason.encode() in output(handle)
    assert run.events() == []
    assert run.lab.dns == run.lab.tcp == run.lab.http == []


def http_paths(lab):
    return [request.split(b" ")[1].decode("ascii") for request in lab.http]


def test_real_loopback_dns_tls_and_two_gets(certs):
    with Lab(certs).started() as lab:
        run = Run(lab)
        lab.observe = run.events
        with terminal(run) as handle:
            line = output(handle, challenge=True)
            assert lab.dns == lab.tcp == lab.http == run.events() == []
            raw = answer(handle, line)
        result = next(json.loads(line) for line in raw.splitlines() if line.startswith(b"{"))
        assert result == {
            "authorization": CLOSED,
            "evidence": FIXTURE_EVIDENCE,
            "status": "NOT_EVALUATED",
            "cards": [],
            "attempts": 2,
            "weight": 2,
            "retry_count": 0,
            "residual": "COHERENT_PRIVILEGED_ROLLBACK_RESIDUAL",
        }
        assert tuple(http_paths(lab)) == ROUTES and len(lab.dns) == 1
        assert lab.dns[0] == b"\x06canary\x04s2v2\x04test\x00\x00\x01\x00\x01"
        assert len(lab.tcp) == 2 and lab.sni == [FIXTURE_HOST] * 2
        headers = b"".join(lab.http).lower()
        assert b"host: canary.s2v2.test\r\n" in headers
        assert all(
            bad not in headers for bad in (b"?", b"authorization:", b"x-mbx-apikey:", b"cookie:")
        )
        events = run.events()
        assert [row["kind"] for row in events] == [
            "claim",
            "reserve",
            "result",
            "reserve",
            "result",
        ]
        assert [row["debit"] for row in events if row["kind"] == "reserve"] == [1, 1]
        assert lab.ledger_seen == [
            ("resolver", "reserve", 1, 1),
            ("http", "reserve", 1, 1),
            ("http", "reserve", 2, 1),
        ]
        assert all(
            len(row["synthetic_receipt_sha"]) == 64 for row in events if row["kind"] == "result"
        )
        with terminal(run) as again:
            assert b"RUN_ALREADY_CONSUMED" in output(again)
        assert len(lab.dns) == 1 and len(lab.tcp) == len(lab.http) == 2
        if trace := os.environ.get("RB_TRACE"):
            Path(trace).write_text(
                json.dumps(
                    {
                        "result": result,
                        "dns_queries": len(lab.dns),
                        "tcp_connections": len(lab.tcp),
                        "sni": lab.sni,
                        "routes": http_paths(lab),
                        "ledger_events": [row["kind"] for row in events],
                        "effects_observed_after": lab.ledger_seen,
                        "non_loopback_connections": 0,
                    },
                    indent=2,
                )
                + "\n"
            )


@pytest.mark.parametrize(
    ("case", "denial", "wire_count", "debited"),
    [
        ("dns_question", "DNS_QUESTION_MISMATCH", 0, 1),
        ("dns_peer", "DNS_PEER_NOT_EXACTLY_APPROVED", 0, 1),
        ("untrusted", "TLS_VERIFICATION_OR_HANDSHAKE_FAILED", 0, 1),
        ("hostname", "TLS_VERIFICATION_OR_HANDSHAKE_FAILED", 0, 1),
        ("sni", "TLS_VERIFICATION_OR_HANDSHAKE_FAILED", 0, 1),
        ("legacy_tls", "TLS_VERIFICATION_OR_HANDSHAKE_FAILED", 0, 1),
        ("302", "REDIRECT_FORBIDDEN", 1, 1),
        ("403", "HTTP_403", 1, 1),
        ("418", "HTTP_418", 1, 1),
        ("429", "HTTP_429", 1, 1),
        ("451", "HTTP_451", 1, 1),
        ("500", "HTTP_500", 1, 1),
        ("503", "HTTP_503", 1, 1),
        ("timeout", "TRANSPORT_DEADLINE", 1, 1),
        ("truncated", "TRUNCATED_HTTP_BODY", 1, 1),
        ("malformed", "MALFORMED_TIME_REPLY", 1, 1),
        ("metadata", "MALFORMED_OR_INELIGIBLE_METADATA", 2, 2),
        ("weight_jump", "UNRECONCILED_SHARED_WEIGHT", 2, 2),
        ("counter_missing", "WEIGHT_COUNTER_INVALID", 1, 1),
        ("counter_duplicate", "WEIGHT_COUNTER_INVALID", 1, 1),
    ],
)
def test_each_fault_terminates_with_zero_retries(certs, case, denial, wire_count, debited):
    with Lab(certs, case).started() as lab:
        run = Run(lab)
        if case == "weight_jump":
            run.issue(budget={"shared_weight_upper": 5})
        assert denial.encode() in launch(run)
        events = run.events()
        assert len(lab.dns) == 1
        assert len(lab.http) == wire_count and tuple(http_paths(lab)) == ROUTES[:wire_count]
        assert len(lab.tcp) == (0 if case.startswith("dns") else debited)
        if case == "sni":
            assert lab.sni == [FIXTURE_HOST]
        assert sum(row.get("debit", 0) for row in events) == debited
        end = events[-1]
        assert end["kind"] == "result" and end["code"] == denial
        assert end["latch"] is (case != "429")
        if case == "429":
            assert end["hold_until"] == end["time_ms"] + 8000
            run.issue()
            with terminal(run) as again:
                assert b"PERSISTED_COOLDOWN" in output(again)
        else:
            with terminal(run) as again:
                assert b"RUN_ALREADY_CONSUMED" in output(again)
        assert len(lab.dns) == 1 and len(lab.http) == wire_count


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"peer": "127.0.0.2"}, "FIXTURE_TARGET_FORBIDDEN"),
        ({"hostname": "wrong.s2v2.test"}, "FIXTURE_TARGET_FORBIDDEN"),
        ({"hostname": "fapi.binance.com"}, "FIXTURE_TARGET_FORBIDDEN"),
        ({"resolver": "127.0.0.3"}, "FIXTURE_TARGET_FORBIDDEN"),
        ({"route_table_sha": "f" * 64}, "EGRESS_ROUTE_CHANGED"),
        ({"netns_inode": 123}, "EGRESS_ROUTE_CHANGED"),
        ({"shared_known": None}, "EGRESS_EVIDENCE_UNKNOWN_OR_CONTRADICTORY"),
        ({"product_verified": False}, "EGRESS_EVIDENCE_UNKNOWN_OR_CONTRADICTORY"),
        ({"no_bypass": False}, "EGRESS_EVIDENCE_UNKNOWN_OR_CONTRADICTORY"),
    ],
)
def test_egress_facts_fail_before_network(certs, override, code):
    with Lab(certs).started() as lab:
        rejected(Run(lab, policy=override), code)


@pytest.mark.parametrize(
    "env_name", ["HTTPS_PROXY", "http_proxy", "ALL_PROXY", "NO_PROXY", "SSLKEYLOGFILE"]
)
def test_proxy_and_keylog_injection(certs, env_name):
    with Lab(certs).started() as lab:
        rejected(Run(lab), "PROXY_OR_KEYLOG_FORBIDDEN", {env_name: "127.0.0.1:9009"})


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("ca", "CA_PIN_CHANGED"),
        ("policy", "EGRESS_POLICY_DIGEST_MISMATCH"),
        ("wheel", "RELEASE_DIGEST_MISMATCH"),
        ("scope", "S2V2_SCOPE_BINDING_MISMATCH"),
        ("s3", "S2_ONLY_SCOPE_REQUIRED"),
        ("s4", "S2_ONLY_SCOPE_REQUIRED"),
        ("headroom", "SHARED_HEADROOM_STALE_OR_UNKNOWN"),
        ("expired", "GRANT_EXPIRED_OR_EARLY"),
        ("endpoint", "S2_ONLY_SCOPE_REQUIRED"),
        ("query", "S2_ONLY_SCOPE_REQUIRED"),
        ("tagged_fixture", "S2_ONLY_SCOPE_REQUIRED"),
        ("v1", "S2V2_ENVELOPE_REQUIRED"),
        ("production_domain", "CONTROLLER_SIGNATURE_INVALID"),
    ],
)
def test_substitution_denials(certs, change, code):
    with Lab(certs).started() as lab:
        run = Run(lab)
        if change == "ca":
            run.base.ca.write_bytes(b"changed")
        elif change == "policy":
            save(run.base.route, run.policy | {"peer": "127.0.0.2"})
        elif change == "wheel":
            run.base.data["release_sha"] = "a" * 64
            save(run.base.config, run.base.data)
        elif change == "scope":
            run.issue(scope={"route_sha": "a" * 64})
        elif change in ("s3", "s4"):
            run.issue(scope={"capability": change.upper()})
        elif change == "headroom":
            run.issue(budget={"weight_headroom": None})
        elif change == "expired":
            now = run.now()
            run.issue(scope={"not_before_ms": now - 10_000, "expires_ms": now - 1000})
        elif change == "endpoint":
            run.issue(scope={"requests": [GETS[0], GETS[0]]})
        elif change == "query":
            run.issue(scope={"requests": [GETS[0], GETS[1] | {"params": {"symbol": "BTCUSDT"}}]})
        elif change == "tagged_fixture":
            run.issue(scope={"evidence": LIVE_EVIDENCE})
        elif change == "v1":
            run.base.issue()
        else:
            run.issue(domain=LIVE_DOMAIN)
        rejected(run, code)


def test_rejects_mounted_dependency_mutation(certs):
    with Lab(certs).started() as lab:
        run = Run(lab)
        replacement = Path("/mnt/site/quant_s2v2/unapproved.py")
        replacement.write_bytes(b"# fixture mutation\n")
        replacement.chmod(0o644)
        try:
            rejected(run, "DEPENDENCY_BYTES_MISMATCH")
        finally:
            replacement.unlink()


def test_changed_ca_after_fresh_challenge_denies_before_consumption(certs):
    with Lab(certs).started() as lab:
        run = Run(lab)
        with terminal(run) as handle:
            challenge = output(handle, challenge=True)
            run.base.ca.write_bytes(b"changed after challenge")
            assert b"CA_PIN_CHANGED" in answer(handle, challenge)
        assert run.events() == [] and lab.dns == lab.tcp == lab.http == []


def test_live_terminal_concurrency_one_exact_claimant(certs):
    with Lab(certs).started() as lab:
        run = Run(lab)
        with terminal(run) as first:
            challenge = output(first, challenge=True)
            with terminal(run) as second:
                assert b"CONCURRENT_LAUNCH" in output(second)
            assert b'"retry_count": 0' in answer(first, challenge)
        assert len(lab.dns) == 1 and len(lab.tcp) == 2
        assert sum(row["kind"] == "claim" for row in run.events()) == 1


@pytest.mark.parametrize(
    ("fault", "case", "attempts", "sequence"),
    [
        ("before_debit", "good", 0, ["claim"]),
        ("after_debit", "good", 0, ["claim", "reserve"]),
        ("ambiguity", "truncated", 1, ["claim", "reserve"]),
    ],
)
def test_crash_and_manual_relaunch(certs, fault, case, attempts, sequence):
    with Lab(certs, case).started() as lab:
        run = Run(lab)
        result = launch(run, fault=fault)
        assert b"authorization" not in result
        assert [row["kind"] for row in run.events()] == sequence
        assert len(lab.dns) == len(lab.tcp) == len(lab.http) == attempts
        with terminal(run) as again:
            assert b"RUN_ALREADY_CONSUMED" in output(again)
        run.issue()
        with terminal(run) as again:
            assert b"PRIOR_RUN_UNCERTAIN" in output(again)
        assert len(lab.dns) == len(lab.tcp) == len(lab.http) == attempts


def test_fsync_and_disagreement_prevent_dns(certs):
    with Lab(certs).started() as lab:
        run = Run(lab)
        assert b"STORAGE_DURABILITY_FAILED" in launch(run, fault="fsync")
        assert run.events() == []
        rejected(run, "LOCAL_SPEND_AND_SQLITE_DIVERGED")


@pytest.mark.parametrize("method", ["database", "spend", "both"])
def test_one_sided_restore_and_coherent_residual(certs, method):
    with Lab(certs).started() as lab:
        run = Run(lab)
        database, spend = run.base.db.read_bytes(), run.base.spend.read_bytes()
        assert b'"attempts": 2' in launch(run)
        if method in ("database", "both"):
            run.base.db.write_bytes(database)
        if method in ("spend", "both"):
            run.base.spend.write_bytes(spend)
        if method == "both":
            # The fixture is a coherent restoration of the two mutable stores.
            lab.http.clear()
            assert b'"attempts": 2' in launch(run)
            assert len(lab.tcp) == 4
        else:
            with terminal(run) as again:
                assert b"LOCAL_SPEND_AND_SQLITE_DIVERGED" in output(again)
            assert len(lab.tcp) == 2


def test_live_build_and_fixture_keys_stay_closed(certs):
    with Lab(certs).started() as lab:
        run = Run(lab)
        roots = ProductionRoots(
            run.base.config,
            run.base.grant,
            RB_WHEEL,
            PRIVATE.public_key().public_bytes_raw(),
            "1" * 64,
        )
        with (
            patch("quant_s2rb.release._PRODUCTION_ROOTS", roots),
            pytest.raises(Denied, match="PRODUCTION_ROOT_INVALID_OR_FIXTURE"),
        ):
            production_roots()
        config = type(
            "Config", (), {"route_path": run.base.route, "route_sha": run.base.data["route_sha"]}
        )
        egress = Egress.read(config, FIXTURE_EVIDENCE)
        with pytest.raises(Denied, match=CLOSED):
            replace(egress, evidence=LIVE_EVIDENCE).check_targets()
        env = os.environ | {"QUANT_S2V2_LIVE": "1", "QUANT_S2RB_QA": "1"}
        for verb in ("manual-once", "qa-console", "live-once", "s3", "s4"):
            result = subprocess.run(
                [sys.executable, "-P", "-B", "-s", "-m", "quant_s2rb", verb],
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            assert result.returncode == 3 and result.stderr.strip() == CLOSED
        assert lab.dns == lab.tcp == lab.http == []


def test_frozen_v1_s3_and_s4_do_not_accept_new_envelope(certs):
    with Lab(certs).started() as lab:
        run = Run(lab)
        envelope = strict_json(run.base.grant.read_bytes())
        scope = envelope["scope"]
        roots = TrustRoots(b"1" * 32, b"2" * 32, run.base.db, "1" * 64, 64201, "2" * 64)
        with pytest.raises(SourceBlocked, match="ACTIVATION_FIELDS_INVALID"):
            verify_envelope(envelope, scope, roots, scope["release_sha"], scope["not_before_ms"])
        now = stamp()
        claim = Claim(
            task="H4_FEISHU_SCOPE_V1",
            capability="outbound",
            run_id=scope["run_id"],
            release_sha256="1" * 64,
            state_sha256="2" * 64,
            runtime_uid=64201,
            authority="https://open.feishu.cn",
            app="cli_fixture",
            tenant="fixture",
            owner="ou_fixture",
            chat="oc_fixture",
            sender="fixture",
            channel="feishu",
            not_before_ms=now - 1000,
            expires_ms=now + 30_000,
            event_id="3" * 64,
            message_sha256="4" * 64,
            evidence_class="SYNTHETIC_QA_ONLY",
            message_limit=1,
            accepted_turns=0,
            reply_limit=0,
            auth_bootstrap_limit=0,
            facade_path="/mnt/fixture-facade",
            facade_uid=64202,
        )
        state = State(Witness(None, "5" * 64, fixture_only=True), ())
        owner = Ed25519PrivateKey.generate()
        keys = (owner.public_key().public_bytes_raw(), PRIVATE.public_key().public_bytes_raw())
        transplanted = envelope["controller_signature"]
        with pytest.raises(H4Denied, match="DUAL_APPROVAL_REQUIRED"):
            Permit(claim, state, RB_WHEEL, {"controller": transplanted}, fixture_keys=keys)
        owner_signature = owner.sign(b"H4_FEISHU_SCOPE_V1/owner\n" + canonical(asdict(claim)))
        with pytest.raises(H4Denied, match="APPROVAL_SIGNATURE_INVALID"):
            Permit(
                claim,
                state,
                RB_WHEEL,
                {"owner": owner_signature.hex(), "controller": transplanted},
                fixture_keys=keys,
            )
        assert lab.dns == lab.tcp == lab.http == []


def test_installed_release_exact_bytes(certs):
    with Lab(certs).started() as lab:
        run = Run(lab)
        verify_release(RB_WHEEL, run.base.data["release_sha"])
        scratch = run.base.root / RB_WHEEL.name
        shutil.copyfile(RB_WHEEL, scratch)
        with scratch.open("ab") as target:
            target.write(b"changed")
        with pytest.raises(Denied, match="RELEASE_DIGEST_MISMATCH"):
            verify_release(scratch, run.base.data["release_sha"])
