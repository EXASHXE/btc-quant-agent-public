"""All tests run under an explicit no-network guard (including loopback)."""

from contextlib import ExitStack
import copy
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from alerts import (AmbiguousDelivery, ClockFault, Dispatcher, MockFeishuTransport,
                    NotDelivered, Policy, Response)
from alerts.card import Secret, make_card, signature
from alerts.contract import SCHEMA, after_cost_r
from tests.fixtures import FakeClock, candidate, degraded


class OfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = ExitStack()
        for target in ("socket.socket.__init__", "socket.socket.connect", "socket.socket.connect_ex", "socket.socket.sendto",
                       "socket.create_connection", "socket.getaddrinfo", "socket.socket.bind"):
            cls.guard.enter_context(patch(target, side_effect=AssertionError("ZERO_NETWORK_POLICY")))

    @classmethod
    def tearDownClass(cls):
        cls.guard.close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="q0c-offline-")
        self.path = str(Path(self.tmp.name) / "outbox.sqlite3")
        self.clock = FakeClock()
        self.policy = Policy(cooldown_seconds=0, rate_cap=100)
        self.opened = []

    def tearDown(self):
        for d in self.opened:
            try:
                d.close()
            except sqlite3.ProgrammingError:
                pass
        self.tmp.cleanup()

    def dispatcher(self, outcomes=(), policy=None, secret=None, transport=None):
        d = Dispatcher(self.path, transport or MockFeishuTransport(outcomes), clock=self.clock,
                       policy=policy or self.policy, secret=secret)
        self.opened.append(d)
        return d

    def test_network_policy_blocks_dns_connect_and_udp(self):
        with self.assertRaisesRegex(AssertionError, "ZERO_NETWORK_POLICY"):
            socket.getaddrinfo("example.invalid", 443)
        with self.assertRaises(AssertionError):
            socket.socket()
        with self.assertRaises(AssertionError):
            socket.socket.connect(None, ("127.0.0.1", 12345))
        with self.assertRaises(AssertionError):
            socket.socket.sendto(None, b"offline", ("127.0.0.1", 12345))

    def test_exact_transport_boundary_and_live_input_denied(self):
        with self.assertRaises(ValueError):
            Dispatcher(self.path, object())
        class LiveLookingSubclass(MockFeishuTransport):
            pass
        with self.assertRaises(ValueError):
            Dispatcher(self.path, LiveLookingSubclass())
        d = self.dispatcher()
        e = candidate()
        e["watermark"]["synthetic"] = False
        with self.assertRaisesRegex(ValueError, "offline_only"):
            d.enqueue(e)
        e = candidate()
        e["channel"] = "FEISHU_LIVE"
        with self.assertRaises(ValueError):
            d.enqueue(e)

    def test_durable_append_before_send_and_independent_acceptance(self):
        d = self.dispatcher()
        key = d.enqueue(candidate())
        self.assertEqual(d.get(key)["state"], "QUEUED")
        observer = sqlite3.connect(self.path)
        def observe(card):
            self.assertEqual(observer.execute("SELECT state,attempts FROM outbox").fetchone(), ("ATTEMPTED", 1))
            self.assertEqual(observer.execute("SELECT state FROM audit ORDER BY seq DESC").fetchone()[0], "ATTEMPTED")
            return Response(200, {"code": 0})
        with patch.object(d.transport, "send", side_effect=observe):
            self.assertEqual(d.dispatch_one(), key)
        observer.close()
        row = d.get(key)
        self.assertEqual(row["state"], "PROVIDER_ACCEPTED")
        self.assertFalse(json.loads(row["proof"])["human_read"])
        self.assertEqual(d.metrics()["feedback_numerator"], 0)
        self.assertIsNone(d.dispatch_one())

    def test_http_200_invalid_provider_code_never_success(self):
        d = self.dispatcher([Response(200, {"code": 999, "msg": "rejected"})])
        key = d.enqueue(candidate())
        d.dispatch_one()
        self.assertEqual(d.get(key)["state"], "FAILED")
        self.assertIsNone(d.get(key)["proof"])
        self.assertIsNone(d.dispatch_one())

    def test_malformed_and_ambiguous_responses_never_success(self):
        responses = [Response(200, {"code": False}), Response(200, {"code": "0"}),
                     Response(200, "not json"), Response(200, {}), Response(500, {"code": 0}),
                     Response(429, {"code": 429}), Response(200, {"code": 0, "bad": float("nan")}), object()]
        d = self.dispatcher(responses)
        for i in range(len(responses)):
            key = d.enqueue(candidate(episode=str(i)))
            d.dispatch_one()
            self.assertEqual(d.get(key)["state"], "UNKNOWN_DELIVERY")
            self.assertIsNone(d.get(key)["accepted_at"])
        self.assertEqual(d.metrics()["provider_accepted_numerator"], 0)

    def test_timeout_after_send_is_unknown_without_replay_across_restart(self):
        d = self.dispatcher([AmbiguousDelivery("secret-like exception must not be logged")])
        key = d.enqueue(candidate())
        d.dispatch_one()
        self.assertEqual(len(d.transport.cards), 1)
        self.assertEqual(d.get(key)["state"], "UNKNOWN_DELIVERY")
        d.close()
        restarted = self.dispatcher()
        self.assertEqual(restarted.enqueue(candidate()), key)
        self.assertIsNone(restarted.dispatch_one())
        self.assertEqual(len(restarted.transport.cards), 0)
        self.assertNotIn("secret-like", restarted.get(key)["last_error"])

    def test_generic_timeout_is_ambiguous(self):
        d = self.dispatcher([TimeoutError("sent, response lost")])
        key = d.enqueue(candidate())
        d.dispatch_one()
        self.assertEqual(d.get(key)["state"], "UNKNOWN_DELIVERY")

    def test_crash_after_submission_rehydrates_to_unknown(self):
        d = self.dispatcher([KeyboardInterrupt()])
        key = d.enqueue(candidate())
        with self.assertRaises(KeyboardInterrupt):
            d.dispatch_one()
        self.assertEqual(d.get(key)["state"], "ATTEMPTED")
        d.close()
        restarted = self.dispatcher()
        self.assertEqual(restarted.get(key)["state"], "UNKNOWN_DELIVERY")
        self.assertIsNone(restarted.dispatch_one())

    def test_queued_restart_and_idempotency_payload_conflict(self):
        d = self.dispatcher()
        e = candidate()
        key = d.enqueue(e)
        self.assertEqual(d.enqueue(copy.deepcopy(e)), key)
        changed = copy.deepcopy(e)
        changed["quote"]["price"] = 100.1
        with self.assertRaisesRegex(ValueError, "idempotency_payload_conflict"):
            d.enqueue(changed)
        d.close()
        restarted = self.dispatcher()
        self.assertEqual(restarted.enqueue(e), key)
        restarted.dispatch_one()
        restarted.close()
        again = self.dispatcher()
        self.assertEqual(again.enqueue(e), key)
        self.assertIsNone(again.dispatch_one())
        self.assertEqual(again.metrics()["admitted_distinct"], 1)

    def test_proven_throttle_bounded_retry_and_restart(self):
        d = self.dispatcher([Response(429, {"code": 429}, True)])
        e = candidate()
        key = d.enqueue(e)
        d.dispatch_one()
        self.assertEqual(d.get(key)["state"], "FAILED")
        self.assertTrue(d.get(key)["retryable"])
        self.assertIsNone(d.dispatch_one())
        d.close()
        self.clock.advance(5)
        restarted = self.dispatcher()
        restarted.dispatch_one()
        self.assertEqual(restarted.get(key)["state"], "PROVIDER_ACCEPTED")
        self.assertEqual(restarted.get(key)["attempts"], 2)

    def test_max_attempts_and_retry_expiry(self):
        d = self.dispatcher([NotDelivered(), NotDelivered(), NotDelivered()])
        key = d.enqueue(candidate())
        for wait in (0, 5, 10):
            self.clock.advance(wait)
            d.dispatch_one()
        self.assertEqual(d.get(key)["attempts"], 3)
        self.assertFalse(d.get(key)["retryable"])
        self.assertIsNone(d.dispatch_one())
        e = candidate(self.clock.time(), "short-ttl")
        e["expires_at"] = self.clock.time() + 2
        key = d.enqueue(e)
        with patch.object(d.transport, "send", side_effect=NotDelivered()):
            d.dispatch_one()
        self.assertFalse(d.get(key)["retryable"])

    def test_bad_secret_and_secret_getter_never_logged(self):
        secret = Secret(lambda: "injected-private-synthetic-secret")
        other = Secret(lambda: "different-private-synthetic-secret")
        transport = MockFeishuTransport(expected_secret=other)
        d = self.dispatcher(transport=transport, secret=secret)
        key = d.enqueue(candidate())
        d.dispatch_one()
        self.assertEqual(d.get(key)["state"], "FAILED")
        self.assertNotIn(secret.read(), repr(secret) + repr(transport) + json.dumps(d.get(key)))
        self.assertNotIn(secret.read().encode(), Path(self.path).read_bytes())
        def broken_getter():
            raise RuntimeError("private-secret-value")
        d.secret = Secret(broken_getter)
        key = d.enqueue(candidate(episode="bad-getter"))
        d.dispatch_one()
        self.assertEqual(d.get(key)["state"], "FAILED")
        self.assertEqual(d.get(key)["attempts"], 0)
        self.assertNotIn("private-secret-value", json.dumps(d.get(key)))

    def test_signature_known_vector_and_watermark_card(self):
        # Independent known vector: standard HMAC-SHA256(key='1700000000\nfixture', msg='').
        self.assertEqual(signature("1700000000", "fixture"),
                         "qT3W992ndd1owN4JTL06fR3subaTXfs9Wdun1fU46tw=")
        e = candidate()
        card = make_card(e, self.clock.time(), Secret(lambda: "fixture"))
        self.assertIn("SYNTHETIC", card["card"]["header"]["title"]["content"])
        self.assertIn("Account: UNKNOWN", json.dumps(card, ensure_ascii=False))
        self.assertIn("sign", card)
        self.assertNotIn("fixture", json.dumps(card))

    def test_stale_source_quote_future_or_untrusted_rejected(self):
        d = self.dispatcher()
        edits = [("source", "observed_at", self.clock.time() - 61),
                 ("source", "received_at", self.clock.time() + 1),
                 ("source", "trusted", False), ("source", "admitted", False),
                 ("source", "quality", "REJECTED"),
                 ("quote", "as_of", self.clock.time() - 31),
                 ("quote", "trusted", False), ("quote", "path_admitted", False),
                 ("quote", "gate_passed", False), ("quote", "current", False),
                 ("setup_1h", "completed", False), ("confirmation_15m", "valid", False),
                 ("confirmation_15m", "closed_at", self.clock.time() + 1)]
        for parent, field, value in edits:
            with self.subTest(parent=parent, field=field):
                e = candidate()
                e[parent][field] = value
                with self.assertRaises(ValueError):
                    d.enqueue(e)
        e = candidate()
        e["eligible_at"] -= 121
        with self.assertRaisesRegex(ValueError, "stale_signal"):
            d.enqueue(e)

    def test_admission_rechecked_at_send_and_expiry(self):
        d = self.dispatcher()
        key = d.enqueue(candidate())
        self.clock.advance(31)
        self.assertIsNone(d.dispatch_one())
        self.assertEqual(d.get(key)["state"], "FAILED")
        e = candidate(self.clock.time(), "expired")
        e["expires_at"] = self.clock.time() + 1
        key = d.enqueue(e)
        self.clock.advance(2)
        self.assertIsNone(d.dispatch_one())
        self.assertEqual(d.get(key)["attempts"], 0)

    def test_slow_secret_injection_cannot_send_stale_signal(self):
        def delayed_secret():
            self.clock.advance(31)
            return "public-synthetic-fixture"
        d = self.dispatcher(secret=Secret(delayed_secret))
        key = d.enqueue(candidate())
        self.assertIsNone(d.dispatch_one())
        self.assertEqual(d.get(key)["state"], "FAILED")
        self.assertEqual(len(d.transport.cards), 0)

    def test_clock_jump_during_secret_injection_never_submits(self):
        def jumped_secret():
            self.clock.wall += 10
            return "public-synthetic-fixture"
        d = self.dispatcher(secret=Secret(jumped_secret))
        key = d.enqueue(candidate())
        with self.assertRaises(ClockFault):
            d.dispatch_one()
        self.assertEqual(d.get(key)["state"], "FAILED")
        self.assertEqual(len(d.transport.cards), 0)

    def test_5_to_10_minute_response_gate(self):
        d = self.dispatcher()
        edits = [("feasible", False), ("min_seconds", 299), ("max_seconds", 599),
                 ("valid_until", self.clock.time() + 599),
                 ("worst_entry_at_5m", 102), ("worst_entry_at_10m", 98),
                 ("after_cost_r_at_5m", 100), ("after_cost_r_at_10m", 1.9)]
        for field, value in edits:
            e = candidate()
            e["human_delay"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                d.enqueue(e)
        e = candidate()
        e["candidate_expires_at"] = self.clock.time() + 599
        with self.assertRaises(ValueError):
            d.enqueue(e)
        e = candidate()
        e["human_delay"]["valid_until"] = self.clock.time() + 600
        key = d.enqueue(e)
        self.clock.advance(1)
        d.dispatch_one()
        self.assertEqual(d.get(key)["state"], "FAILED")

    def test_stop_targets_costs_and_schema_strictness(self):
        d = self.dispatcher()
        changes = [("hard_stop", 100), ("after_cost_r", 99), ("entry_area", [101, 99]),
                   ("take_profits", []), ("take_profits", [{"price": 90, "weight": 1, "rationale": "bad"}]),
                   ("take_profits", [{"price": 115, "weight": .5, "rationale": "bad"}])]
        for key, value in changes:
            e = candidate()
            e["plan"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                d.enqueue(e)
        for field, value in (("extra_secret", "forbidden"), ("eligible_at", float("nan")),
                             ("account_status", "KNOWN_APPROVED"), ("account_status", "VETO")):
            e = candidate()
            e[field] = value
            with self.assertRaises(ValueError):
                d.enqueue(e)
        e = candidate()
        e["plan"]["model"]["fee_bps_round_trip"] = 10000
        with self.assertRaises(ValueError):
            d.enqueue(e)

    def test_short_and_three_legitimate_targets(self):
        d = self.dispatcher()
        e = candidate()
        e["side"] = "SHORT"
        e["plan"]["hard_stop"] = 105
        e["human_delay"].update(worst_entry_at_5m=99.5, worst_entry_at_10m=99)
        e["plan"]["take_profits"] = [
            {"price": p, "weight": w, "rationale": "synthetic support"}
            for p, w in ((85, .5), (80, .3), (75, .2))]
        self.assertGreater(after_cost_r(e, 101), 2.8)
        key = d.enqueue(e)
        d.dispatch_one()
        self.assertEqual(d.get(key)["state"], "PROVIDER_ACCEPTED")
        e = candidate(episode="four-targets")
        e["plan"]["take_profits"] *= 4
        with self.assertRaises(ValueError):
            d.enqueue(e)

    def test_invalidation_after_notified_preserves_acceptance(self):
        d = self.dispatcher()
        entry = candidate()
        key = d.enqueue(entry)
        d.dispatch_one()
        self.clock.advance(90)
        invalid = copy.deepcopy(entry)
        invalid.update(event_type="INVALIDATED", transition_id="invalidate-001",
                       eligible_at=self.clock.time(), expires_at=self.clock.time() + 120)
        invalid["source"].update(observed_at=self.clock.time(), received_at=self.clock.time())
        invalid["invalidation"].update(triggered=True, reason="synthetic setup failed")
        invalid_key = d.enqueue(invalid)  # historical quote is deliberately stale
        d.dispatch_one()
        self.assertEqual(d.get(key)["state"], "PROVIDER_ACCEPTED")
        self.assertEqual(d.get(invalid_key)["state"], "PROVIDER_ACCEPTED")
        self.assertNotEqual(key, invalid_key)
        later = candidate(self.clock.time())
        later["transition_id"] = "late-entry"
        with self.assertRaisesRegex(ValueError, "episode_already_terminal"):
            d.enqueue(later)

    def test_terminal_cancels_pending_and_retry_but_not_unknown(self):
        d = self.dispatcher([NotDelivered(), AmbiguousDelivery()])
        retry = d.enqueue(candidate(episode="retry"))
        d.dispatch_one()
        pending = d.enqueue(candidate(episode="pending"))
        unknown = d.enqueue(candidate(episode="unknown"))
        with patch.object(d.transport, "send", side_effect=AmbiguousDelivery()):
            # Select exactly one pending item; no dependency on hash sort order.
            d.db.execute("UPDATE outbox SET next_attempt_at=? WHERE id=?", (self.clock.time()+10, pending))
            d.dispatch_one()
        self.assertEqual(d.get(unknown)["state"], "UNKNOWN_DELIVERY")
        for episode in ("retry", "pending", "unknown"):
            e = candidate(episode=episode, kind="INVALIDATED")
            e["invalidation"]["triggered"] = True
            d.enqueue(e)
        self.assertEqual(d.get(retry)["state"], "FAILED")
        self.assertFalse(d.get(retry)["retryable"])
        self.assertEqual(d.get(pending)["state"], "FAILED")
        self.assertEqual(d.get(unknown)["state"], "UNKNOWN_DELIVERY")

    def test_expired_candidate_uses_fresh_notification_ttl(self):
        d = self.dispatcher()
        e = candidate(kind="EXPIRED")
        e["candidate_expires_at"] = self.clock.time() - 1
        key = d.enqueue(e)
        d.dispatch_one()
        self.assertEqual(d.get(key)["state"], "PROVIDER_ACCEPTED")
        e = candidate(episode="not-expired", kind="EXPIRED")
        with self.assertRaisesRegex(ValueError, "candidate_not_expired"):
            d.enqueue(e)

    def test_account_veto_allows_terminal_and_system_notifications(self):
        d = self.dispatcher()
        pending = d.enqueue(candidate())
        invalid = candidate(kind="INVALIDATED")
        invalid["account_status"] = "VETO"
        invalid["invalidation"]["triggered"] = True
        key = d.enqueue(invalid)
        self.assertEqual(d.get(pending)["state"], "FAILED")
        self.assertEqual(d.dispatch_one(), key)
        system = degraded()
        system["account_status"] = "VETO"
        self.assertEqual(d.dispatch_one(), None)
        key = d.enqueue(system)
        self.assertEqual(d.dispatch_one(), key)

    def test_human_delay_must_model_conservative_worsening(self):
        d = self.dispatcher()
        for first, second in ((99, 101), (101, 100)):
            e = candidate()
            e["human_delay"].update(worst_entry_at_5m=first, worst_entry_at_10m=second)
            with self.assertRaisesRegex(ValueError, "directionally_conservative"):
                d.enqueue(e)

    def test_entry_priority_over_optional_watch_and_setup(self):
        d = self.dispatcher()
        for kind in ("WATCH", "SETUP_READY"):
            e = candidate(episode=kind, kind=kind)
            e["confirmation_15m"]["completed"] = False
            if kind == "WATCH":
                e["setup_1h"]["completed"] = False
            d.enqueue(e)
        entry = d.enqueue(candidate())
        self.assertEqual(d.dispatch_one(), entry)

    def test_per_channel_cooldown_and_rate_cap_survive_restart(self):
        policy = Policy(cooldown_seconds=5, rate_cap=2, rate_window_seconds=20)
        d = self.dispatcher(policy=policy)
        for i in range(3):
            d.enqueue(candidate(episode=str(i)))
        self.assertIsNotNone(d.dispatch_one())
        self.assertIsNone(d.dispatch_one())
        self.clock.advance(5)
        self.assertIsNotNone(d.dispatch_one())
        self.clock.advance(5)
        self.assertIsNone(d.dispatch_one())
        d.close()
        restarted = self.dispatcher(policy=policy)
        self.assertIsNone(restarted.dispatch_one())
        self.clock.advance(10)
        self.assertIsNotNone(restarted.dispatch_one())
        self.assertEqual(len(restarted.transport.cards), 1)

    def test_system_degraded_has_separate_persistent_cooldown(self):
        d = self.dispatcher()
        first = d.enqueue(degraded())
        d.dispatch_one()
        second = d.enqueue(degraded(episode="system:other"))
        self.assertIsNone(d.dispatch_one())
        self.assertEqual(d.get(first)["state"], "PROVIDER_ACCEPTED")
        self.assertEqual(d.get(second)["state"], "QUEUED")
        self.clock.advance(301)
        self.assertIsNone(d.dispatch_one())  # stale queued status is discarded
        fresh = d.enqueue(degraded(self.clock.time(), "system:fresh"))
        self.assertEqual(d.dispatch_one(), fresh)

    def test_wall_clock_jumps_quarantine_and_survive_restart(self):
        d = self.dispatcher()
        d.enqueue(candidate())
        self.clock.wall += 60
        with self.assertRaises(ClockFault):
            d.dispatch_one()
        self.assertEqual(len(d.transport.cards), 0)
        self.assertIsNone(d.synthetic_latency()["p95_seconds"])
        d.close()
        with self.assertRaises(ClockFault):
            self.dispatcher()

    def test_clock_rollback_during_downtime(self):
        d = self.dispatcher()
        d.close()
        self.clock.wall -= 60
        with self.assertRaises(ClockFault):
            self.dispatcher()

    def test_clock_jump_during_send_retains_evidence_without_latency_sample(self):
        d = self.dispatcher()
        key = d.enqueue(candidate())
        def response_after_jump(card):
            self.clock.wall -= 60
            return Response(200, {"code": 0})
        with patch.object(d.transport, "send", side_effect=response_after_jump):
            with self.assertRaises(ClockFault):
                d.dispatch_one()
        row = d.get(key)
        self.assertEqual(row["state"], "PROVIDER_ACCEPTED")
        self.assertIsNone(row["accepted_at"])
        self.assertFalse(json.loads(row["proof"])["observation_clock_trusted"])
        self.assertIsNone(d.synthetic_latency()["p95_seconds"])
        with self.assertRaises(ClockFault):
            d.dispatch_one()

    def test_examples_match_contract_and_cards_without_network(self):
        from alerts.contract import admit
        examples = Path(__file__).resolve().parent.parent / "examples"
        events = sorted(examples.glob("*.event.json"))
        self.assertEqual(len(events), 6)
        for path in events:
            event = json.loads(path.read_text(encoding="utf-8"))
            admit(event, self.clock.time(), self.policy)
            card_path = path.with_name(path.name.replace(".event.json", ".card.json"))
            self.assertEqual(make_card(event, self.clock.time()), json.loads(card_path.read_text(encoding="utf-8")))

    def test_forward_jump_during_downtime_expires_queue(self):
        d = self.dispatcher()
        key = d.enqueue(candidate())
        d.close()
        self.clock.advance(1000)
        restarted = self.dispatcher()
        self.assertIsNone(restarted.dispatch_one())
        self.assertEqual(restarted.get(key)["state"], "FAILED")

    def test_feedback_and_denominators_are_distinct_and_durable(self):
        d = self.dispatcher([Response(200, {"code": 0}), AmbiguousDelivery(), Response(200, {"code": 8})])
        keys = []
        for i in range(3):
            e = candidate(episode=str(i))
            keys.append(d.enqueue(e))
            d.dispatch_one()
            d.enqueue(e)
        metrics = d.metrics()
        self.assertEqual(metrics["admitted_distinct"], 3)
        self.assertEqual(metrics["attempted_distinct_denominator"], 3)
        self.assertEqual(metrics["provider_accepted_numerator"], 1)
        self.assertEqual(metrics["feedback_denominator"], 1)
        self.assertEqual(metrics["feedback_numerator"], 0)
        d.record_feedback(keys[0], "TOO_LATE")
        d.record_feedback(keys[0], "TOO_LATE")
        with self.assertRaises(ValueError):
            d.record_feedback(keys[1], "ACKNOWLEDGED")
        with self.assertRaises(ValueError):
            d.record_feedback(keys[0], "ACTIONABLE")
        d.close()
        restarted = self.dispatcher()
        self.assertEqual(restarted.metrics()["feedback_numerator"], 1)
        self.assertFalse(restarted.metrics()["human_read_inferred"])

    def test_synthetic_latency_simulation_is_future_slo_only(self):
        d = self.dispatcher()
        for i in range(20):
            key = d.enqueue(candidate(self.clock.time(), str(i)))
            self.clock.advance(i + 1)
            d.dispatch_one()
            self.assertEqual(d.get(key)["state"], "PROVIDER_ACCEPTED")
        stats = d.synthetic_latency()
        self.assertEqual(stats["samples"], 20)
        self.assertEqual(stats["p95_seconds"], 19)
        self.assertLessEqual(stats["p95_seconds"], 120)
        self.assertFalse(stats["live_claim"])
        self.assertEqual(SCHEMA["x-semantics"]["future_slo"]["objective"], "P95 <= 120 seconds")

    def test_policy_cannot_be_loosened_on_restart_and_audit_append_only(self):
        d = self.dispatcher()
        d.enqueue(candidate())
        with self.assertRaises(sqlite3.IntegrityError):
            d.db.execute("DELETE FROM audit")
        d.close()
        with self.assertRaisesRegex(ValueError, "policy mismatch"):
            self.dispatcher(policy=Policy(max_attempts=4))

    def test_delimiter_safe_identity(self):
        d = self.dispatcher()
        a, b = candidate(), candidate()
        a.update(episode_id="a|b", transition_id="c")
        b.update(episode_id="a", transition_id="b|c")
        self.assertNotEqual(d.enqueue(a), d.enqueue(b))


if __name__ == "__main__":
    unittest.main()
