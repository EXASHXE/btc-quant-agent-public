import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal as D, ROUND_CEILING, ROUND_FLOOR, localcontext
from pathlib import Path

from quant_personal_decision_b2.fixtures import AFTER_TRIGGER, FabricatedMarket
from quant_personal_decision_b2.model import DecisionError
from quant_personal_public_b1.fixture import FixtureClock, FixtureTransport, fixture_reply
from quant_personal_public_b1.policy import SourceBlocked
from quant_personal_public_b1.session import RunIdentity
from quant_personal_public_b1.store import encode, sha
from quant_personal_public_b1.wire import Reply

from quant_personal_public_bridge_b4.admission import MarketAdapter
from quant_personal_public_bridge_b4.collector import Collector, observation_query
from quant_personal_public_bridge_b4.decision import DecisionJournal, compose, observe, verify_card
from quant_personal_public_bridge_b4.demo import SCENARIOS, SYMBOL, advance, run
from quant_personal_public_bridge_b4.fixtures import usd_m_fixture
from quant_personal_public_bridge_b4.live import DISABLED, LiveDisabled, open_live
from quant_personal_public_bridge_b4.normalize import observation
from quant_personal_public_bridge_b4.routes import (
    DAY, DEPTH, FUNDING, INSTRUMENTS, INTERVALS, KLINES, MARK, OI, OI_HISTORY, QUOTE, ROUTES, TICKER, TIME, Request,
)
from quant_personal_public_bridge_b4.session import Session
from quant_personal_public_bridge_b4.source import Ledger
from quant_personal_public_bridge_b4.transport import FIXTURE, GENUINE, LOOPBACK


def run_child(script, *args):
    return subprocess.run([sys.executable, "-c", script, *map(str, args)], capture_output=True, text=True, check=True)


class LocalCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "source.sqlite"
        self.clock = FixtureClock()
        self.identity = RunIdentity("test-boot", "test-session")

    def collector(self, mutate=usd_m_fixture):
        return Collector.fixture(self.path, self.clock, FixtureTransport(self.clock, mutate=mutate), self.identity)

class BridgeCase(LocalCase):
    def test_allowlist_and_reject_before_mock(self):
        collector = self.collector()
        ledger = collector.ledger
        start = self.clock.sample()
        scan = ledger.start(self.identity.stamp(start))
        session = Session(scan, self.clock, self.identity, collector.transport, ledger, start)
        k = {"symbol": SYMBOL, "interval": "5m", "limit": 1, "startTime": DAY, "endTime": DAY}
        self.assertEqual(set(ROUTES), {TIME, INSTRUMENTS, KLINES, TICKER, QUOTE, DEPTH, OI, OI_HISTORY, FUNDING, MARK})
        negatives = [
            Request(TIME, {}, method=m) for m in ("POST", "PUT", "PATCH", "DELETE", "HEAD", "get")
        ] + [Request(p, {}) for p in ("/fapi/v1/order", "/fapi/v3/account", "/fapi/v1/rpiDepth",
                                      "/fapi/v1/aggTrades", "//fapi/v1/time", TIME + "?x=y",
                                      "/fapi/v1/%74ime", "/fapi/v1/../v1/time", "https://fapi.binance.com" + TIME)]
        negatives += [Request(TIME, {}, host="127.0.0.1"), Request(TIME, {}, port=80)]
        negatives += [Request(TICKER, p) for p in ({}, {"symbol": "bnbusdt"}, {"symbol": "XRPUSDT"},
                    {"symbol": SYMBOL + "%00"}, {"symbol": SYMBOL + "\r\n"}, {"symbol": SYMBOL, "signature": "fake"})]
        negatives += [Request(KLINES, {**k, **p})
                      for p in ({"interval": "1m"}, {"interval": "1H"}, {"startTime": False}, {"limit": 2})]
        negatives += [Request(FUNDING, {"symbol": SYMBOL, "limit": 256}),
                      Request(OI_HISTORY, {"symbol": SYMBOL, "period": "1h", "limit": 5, "startTime": 1, "endTime": 2})]
        for req in negatives:
            with self.subTest(req=req), self.assertRaises(SourceBlocked):
                session.request(req)
        self.assertEqual(collector.transport.calls, [])
        self.assertEqual(session.budget.evidence(scan), [])
        for size, expected in ((1, 1), (99, 1), (100, 2), (499, 2), (500, 5), (1000, 5), (1001, 10), (1500, 10)):
            self.assertEqual(Request(KLINES, {**k, "limit": size, "endTime": DAY + (size - 1) * 300_000})
                             .validate()[0], expected)
        for depth, weight in ((5, 2), (50, 2), (100, 5), (500, 10), (1000, 20)):
            self.assertEqual(Request(DEPTH, {"symbol": SYMBOL, "limit": depth}).validate()[0], weight)

    def test_bootstrap_and_incremental_all_symbols(self):
        collector = self.collector()
        adapter_path = self.path
        first = collector.scan()
        adapter = MarketAdapter(adapter_path)
        self.assertEqual(len(collector.transport.calls), 39)
        self.assertEqual(sum(Request(route, params).validate()[0] for route, params, _ in collector.transport.calls), 42)
        for symbol in first["stage"]["symbols"]:
            market = adapter.read(symbol, scan=first["scan_id"])
            self.assertEqual(set(market.bars), set(INTERVALS))
            self.assertTrue(all(len(frame) == 32 for frame in market.bars.values()))
            self.assertTrue(all(b.source["source_publication"] == "UNKNOWN" for rows in market.bars.values() for b in rows))
            self.assertEqual(market.context["depth"]["source_publication"]["field"], "E")
            self.assertEqual(market.context["quote"]["source_publication"], "UNKNOWN")
            self.assertEqual(observe(adapter, symbol, scan=first["scan_id"], as_of_ms=market.evaluated_ms)["market_status"],
                             "NOT_EVALUATED")
        self.clock.advance(300_000)
        self.assertIsNotNone(collector.scan()["visible_venue_upper_ms"])
        calls = collector.transport.calls[39:]
        self.assertNotIn(FUNDING, [route for route, _, _ in calls])
        self.assertNotIn(INSTRUMENTS, [route for route, _, _ in calls])
        self.assertEqual(sum(route == KLINES for route, _, _ in calls), 3)
        self.assertTrue(all(params["limit"] == 3 for route, params, _ in calls if route == KLINES))

    def test_global_stops_and_cooldown_across_process_restart(self):
        for status, expected in ((429, "RETRY_AFTER_ACTIVE"), (418, "HTTP_418"),
                                 (403, "HTTP_403"), (451, "HTTP_451"), (200, "VENUE_RESTRICTED")):
            with self.subTest(status=status):
                self.path = self.root / f"{status}.sqlite"
                body = {"msg": "Service unavailable from a restricted location"}
                reply = fixture_reply(body if status == 200 else {}, status=status, headers={"Retry-After": "120"})
                collector = self.collector(lambda *_: reply)
                stage = collector.scan()["stage"]
                self.assertEqual(stage["issue"]["code"], f"HTTP_{status}" if status != 200 else expected)
                self.assertEqual(len(collector.transport.calls), 1)
                script = """
import sys
from pathlib import Path
from quant_personal_public_b1.fixture import FixtureClock
from quant_personal_public_b1.session import RunIdentity
from quant_personal_public_bridge_b4.collector import Collector
c = Collector.fixture(Path(sys.argv[1]), FixtureClock(), identity=RunIdentity('new-boot','second-process'))
print(c.scan()['stage']['issue']['code'], len(c.transport.calls))
"""
                self.assertEqual(run_child(script, self.path).stdout.strip(), f"{expected} 0")
                with sqlite3.connect(self.path) as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 1)

    def test_cooldown_expires_monotonically(self):
        collector = self.collector(lambda *_: fixture_reply({}, status=429, headers={"Retry-After": "2"}))
        self.assertEqual(collector.scan()["stage"]["issue"]["code"], "HTTP_429")
        self.clock.advance(1999)
        self.assertEqual(self.collector().scan()["stage"]["issue"]["code"], "RETRY_AFTER_ACTIVE")
        self.clock.advance(1)
        self.assertIsNone(self.collector().scan((SYMBOL,))["stage"]["issue"])

    def test_atomic_competing_reservations(self):
        collector = self.collector()
        ledger = collector.ledger
        start = self.clock.sample()
        ledger.start(self.identity.stamp(start))
        with ledger.store.connect(write=True) as db:
            db.execute("INSERT INTO rules VALUES ('REQUEST_WEIGHT',60000,1)")
        script = """
from pathlib import Path
import sys
from quant_personal_public_b1.budget import Budget
from quant_personal_public_b1.store import Stamp
from quant_personal_public_bridge_b4.routes import TIME, Request
from quant_personal_public_bridge_b4.source import Ledger
from quant_personal_public_bridge_b4.transport import FIXTURE
ledger = Ledger(Path(sys.argv[1]), FIXTURE)
sys.stdin.readline()
try:
    Budget(ledger.store, bootstrap=120).reserve(1, int(sys.argv[2]), 0, Request(TIME, {}), Stamp('test-boot','proc',10000,10000))
    print('reserved')
except ValueError as error:
    print(error)
"""
        procs = [subprocess.Popen([sys.executable, "-c", script, str(self.path), str(i)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) for i in (1, 2)]
        for proc in procs:
            proc.stdin.write("\n")
            proc.stdin.flush()
        self.assertEqual(sorted(p.communicate(timeout=10)[0].strip() for p in procs), ["VENUE_WEIGHT_LIMIT", "reserved"])
        with self.assertRaisesRegex(SourceBlocked, "DISPATCH_OUTCOME_UNKNOWN"):
            self.collector().scan((SYMBOL,))

    def test_actual_headers_and_exchange_limits(self):
        def add_header(route, params, body):
            if route == INSTRUMENTS:
                body["rateLimits"][0]["limit"] = 15
                return fixture_reply(body, headers={"X-MBX-USED-WEIGHT-1M": "15"})
            return usd_m_fixture(route, params, body)

        collector = self.collector(add_header)
        self.assertEqual(collector.scan((SYMBOL,))["stage"]["issue"]["code"], "VENUE_WEIGHT_LIMIT")
        self.assertEqual([r for r, _, _ in collector.transport.calls], [TIME, INSTRUMENTS])
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT used FROM headers").fetchone()[0], 15)
            self.assertEqual(db.execute("SELECT ceiling FROM rules WHERE family='REQUEST_WEIGHT'").fetchone()[0], 15)

    def test_unreliable_book_header_is_audited(self):
        def mutate(route, params, body):
            if route == QUOTE:
                return fixture_reply(body, headers={"X-MBX-USED-WEIGHT-1M": "999999"})
            return usd_m_fixture(route, params, body)
        pub = self.collector(mutate).scan((SYMBOL,))
        market = MarketAdapter(self.path).read(SYMBOL, scan=pub["scan_id"])
        self.assertEqual(market.context["quote"]["reply_headers"]["x-mbx-used-weight-1m"], "999999")
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM headers").fetchone()[0], 0)

    def test_transient_retry_charges_and_then_stops(self):
        collector = self.collector(lambda *_: fixture_reply({}, status=408))
        self.assertEqual(collector.scan((SYMBOL,))["stage"]["issue"]["code"], "TRANSIENT_HTTP_EXHAUSTED")
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT retry,weight FROM attempts ORDER BY id").fetchall(), [(0, 1), (1, 1)])

    def test_wrong_clock_and_malformed_json(self):
        for tag, expected in (("disagree", "CLOCK_BRACKETS_DISAGREE"), ("malformed", "MALFORMED_JSON")):
            self.path = self.root / f"{tag}.sqlite"

            def mutate(route, params, body):
                if route == TIME and tag == "malformed":
                    return Reply(200, {"content-type": "application/json"}, b'{"serverTime":')
                if route == TIME and len(collector.transport.calls) > 1:
                    body["serverTime"] += 2000
                return usd_m_fixture(route, params, body)

            collector = self.collector(mutate)
            pub = collector.scan((SYMBOL,))
            self.assertIsNone(pub["visible_venue_upper_ms"])
            self.assertEqual(pub["stage"]["issue"]["code"], expected)

    def test_symbol_gap_then_backfill_and_revision(self):
        def missing(route, params, body):
            if route == KLINES and params["symbol"] == SYMBOL and params["interval"] == "15m":
                return body[:-1]
            return usd_m_fixture(route, params, body)

        old = self.collector(missing).scan((SYMBOL, "ETHUSDT"))
        adapter = MarketAdapter(self.path)
        self.assertEqual(old["stage"]["markets"][SYMBOL]["issue"]["code"], "KLINE_GAP")
        eth = adapter.read("ETHUSDT", scan=old["scan_id"])
        self.clock.advance(300_000)
        filled = self.collector().scan((SYMBOL,))
        new = adapter.read(SYMBOL, scan=filled["scan_id"])
        with self.assertRaisesRegex(DecisionError, "LATE_SOURCE_PUBLICATION"):
            adapter.read(SYMBOL, scan=filled["scan_id"], as_of_ms=old["visible_venue_upper_ms"])
        with self.assertRaisesRegex(DecisionError, "SYMBOL_INPUT_BLOCKED"):
            adapter.read(SYMBOL, scan=old["scan_id"])
        self.assertEqual(eth, adapter.read("ETHUSDT", scan=old["scan_id"]))
        first_bar = new.bars["5m"][-1]
        self.clock.advance(300_000)

        def revise(route, params, body):
            if route == KLINES and params["interval"] == "5m":
                for row in body:
                    if row[0] == first_bar.open_ms:
                        row[4] = str(D(row[4]) + D("0.01"))
            return usd_m_fixture(route, params, body)

        refreshed = self.collector(revise).scan((SYMBOL,))
        changed = adapter.read(SYMBOL, scan=refreshed["scan_id"]).bars["5m"][-2]
        self.assertEqual(changed.source["revision"], 2)
        self.assertEqual(changed.source["previous_revision_sha256"], first_bar.source["source_row_sha256"])
        self.assertEqual(adapter.read(SYMBOL, scan=filled["scan_id"]).bars["5m"][-1], first_bar)
        with self.assertRaisesRegex(DecisionError, "SUPERSEDED"):
            adapter.read(SYMBOL, scan=filled["scan_id"], as_of_ms=refreshed["visible_venue_upper_ms"])

    def test_bars_are_closed_before_wire_request(self):
        def forming(route, params, body):
            if route == KLINES and params["interval"] == "15m":
                body[-1][6] += int(INTERVALS["15m"])
            return usd_m_fixture(route, params, body)

        pub = self.collector(forming).scan((SYMBOL,))
        self.assertEqual(pub["stage"]["markets"][SYMBOL]["issue"]["code"], "KLINE_BOUNDARY")

    def test_stage_crash_reopens_without_lookahead(self):
        collector = self.collector()

        def fail():
            raise RuntimeError("simulated stage crash")

        with self.assertRaisesRegex(RuntimeError, "simulated"):
            collector.scan((SYMBOL,), after_stage=fail)
        self.assertIsNone(collector.ledger.publication())
        before = len(collector.transport.calls)
        recovered = collector.scan((SYMBOL,))
        self.assertEqual(len(collector.transport.calls) - before, 15)
        self.assertNotEqual(recovered["scan_id"], 1)
        with sqlite3.connect(self.path) as db:
            self.assertIsNotNone(db.execute("SELECT abandoned FROM scans WHERE id=1").fetchone()[0])

    def test_process_crash_after_durable_stage(self):
        script = """
import os, sys
from pathlib import Path
from quant_personal_public_b1.fixture import FixtureClock
from quant_personal_public_b1.session import RunIdentity
from quant_personal_public_bridge_b4.collector import Collector
c = Collector.fixture(Path(sys.argv[1]), FixtureClock(), identity=RunIdentity('old-boot','crashed'))
c.scan(('BTCUSDT',), after_stage=lambda: os._exit(47))
"""
        crashed = subprocess.run([sys.executable, "-c", script, str(self.path)], check=False)
        self.assertEqual(crashed.returncode, 47)
        self.assertIsNone(Ledger(self.path, FIXTURE).publication())
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 15)
        restarted = self.collector().scan((SYMBOL,))
        self.assertEqual(restarted["scan_id"], 2)
        self.assertEqual(len(MarketAdapter(self.path).read(SYMBOL, scan=2).bars["1h"]), 32)

    def test_quote_and_depth_contradiction_blocks_admission(self):
        def mutate(route, params, body):
            if route == DEPTH:
                for key in ("bids", "asks"):
                    for row in body[key]:
                        row[0] = str(D(row[0]) * D("1.01"))
            return usd_m_fixture(route, params, body)
        pub = self.collector(mutate).scan((SYMBOL,))
        with self.assertRaisesRegex(DecisionError, "QUOTE_DEPTH_CONTRADICTION"):
            MarketAdapter(self.path).read(SYMBOL, scan=pub["scan_id"])

    def test_late_and_stale_fast_observations(self):
        for route, field, delta, expected in ((DEPTH, "E", 600_000, "LATE_CONTEXT"),
                                              (MARK, "time", 60_000, "LATE_CONTEXT"),
                                              (OI, "time", 60_000, "LATE_CONTEXT"),
                                              (QUOTE, "time", -60_000, "STALE_OR_LATE_CONTEXT")):
            with self.subTest(route=route):
                self.path = self.root / f"{field}{route.rsplit('/', 1)[-1]}.sqlite"

                def mutate(path, params, body):
                    if path == route:
                        body[field] += delta
                    return usd_m_fixture(path, params, body)

                pub = self.collector(mutate).scan((SYMBOL,))
                self.assertEqual(pub["stage"]["markets"][SYMBOL]["issue"]["code"], expected)
                engine = compose(self.path, self.root / f"j-{field}-{route.rsplit('/',1)[-1]}", FIXTURE)
                status = engine.evaluate(SYMBOL, scan=pub["scan_id"], as_of_ms=pub["visible_venue_upper_ms"])
                self.assertEqual(status["market_status"], "SOURCE_BLOCKED")
                self.assertFalse(status["strategy_evaluated"])

    def test_funding_windows_and_oi_missing_periods(self):
        now = self.clock.venue_ms
        query = observation_query("funding", SYMBOL, now)
        row = {"symbol": SYMBOL, "fundingTime": now, "fundingRate": "0.00010", "markPrice": "100.10"}
        _, data = observation(query, [{**row, "rateType": "Regular"}, {**row, "rateType": "Special"}], SYMBOL)
        self.assertEqual([row["fundingRateType"] for row in data["rows"]], ["Regular", "Special"])
        self.assertEqual(observation(query, [row], SYMBOL)[1]["rows"][0]["fundingRateType"], "UNKNOWN")
        with self.assertRaisesRegex(SourceBlocked, "FUNDING_OUTSIDE_REQUEST_WINDOW"):
            observation(query, [{**row, "fundingTime": now + 1}], SYMBOL)
        with self.assertRaisesRegex(SourceBlocked, "FUNDING_WINDOW_SATURATED"):
            observation(Request(FUNDING, {**query.params, "limit": 1}), [row], SYMBOL)
        interest = {"symbol": SYMBOL, "sumOpenInterest": "12.34", "sumOpenInterestValue": "654.4321"}
        query = observation_query("oi_history", SYMBOL, now)
        _, result = observation(query, [{**interest, "timestamp": t} for t in (now - 600_000, now)], SYMBOL)
        self.assertEqual(result["documented_retention"], "LATEST_ONE_MONTH")
        self.assertEqual(result["omitted_periods"][0]["missing_periods"], 1)
        with self.assertRaisesRegex(SourceBlocked, "OI_HISTORY_OUTSIDE_WINDOW"):
            observation(query, [{**interest, "timestamp": now - 31 * DAY}], SYMBOL)

    def test_forgery_wrong_publication_or_missing_raw(self):
        pub = self.collector().scan((SYMBOL,))
        adapter = MarketAdapter(self.path)
        proof = adapter.read(SYMBOL, scan=pub["scan_id"]).source
        with self.assertRaisesRegex(DecisionError, "PUBLICATION_DIGEST_MISMATCH"):
            adapter.read(SYMBOL, scan=pub["scan_id"], publication_sha="0" * 64)
        with self.assertRaisesRegex(LiveDisabled, DISABLED):
            MarketAdapter(self.path, GENUINE)
        with self.assertRaisesRegex(DecisionError, "UNQUALIFIED_SOURCE_LEDGER"):
            MarketAdapter(self.path, LOOPBACK)
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT payload,sha256 FROM publications WHERE scan_id=1").fetchone()
            relabel = json.loads(row[0])
            relabel["origin"] = GENUINE
            text_value = encode(relabel)
            db.execute("UPDATE publications SET payload=?,sha256=? WHERE scan_id=1", (text_value, sha(text_value.encode())))
        with self.assertRaisesRegex(DecisionError, "UNQUALIFIED_SOURCE_PUBLICATION"):
            adapter.read(SYMBOL, scan=1)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE publications SET payload=?,sha256=? WHERE scan_id=1", row)
            raw_id = next(x["receipt_id"] for x in proof["raw_receipts"] if x["route"] == DEPTH)
            db.execute("UPDATE attempts SET raw=NULL WHERE id=?", (raw_id,))
        with self.assertRaisesRegex(DecisionError, "SOURCE_RECEIPT_MISSING"):
            adapter.read(SYMBOL, scan=1)

    def test_normalized_digest_cannot_override_raw(self):
        self.collector().scan((SYMBOL,))
        with sqlite3.connect(self.path) as db:
            data = json.loads(db.execute("SELECT payload FROM publications WHERE scan_id=1").fetchone()[0])
            data["stage"]["markets"][SYMBOL]["observations"]["mark"]["normalized_sha256"] = "a" * 64
            staged = encode(data["stage"])
            data["stage_sha256"] = sha(staged.encode())
            raw = encode(data)
            db.execute("UPDATE scans SET staged=? WHERE id=1", (staged,))
            db.execute("UPDATE publications SET payload=?,sha256=? WHERE scan_id=1", (raw, sha(raw.encode())))
        with self.assertRaisesRegex(DecisionError, "SOURCE_CONTEXT_DIGEST"):
            MarketAdapter(self.path).read(SYMBOL, scan=1)

    def test_genuine_disabled_before_scope_reads(self):
        class FakeActivation:
            def __bool__(self):
                raise AssertionError("Capability read")
        with self.assertRaisesRegex(LiveDisabled, DISABLED):
            open_live(operating_scope=FakeActivation(), controller_activation=FakeActivation())
        with self.assertRaisesRegex(LiveDisabled, DISABLED):
            Ledger(Path("/no-ledger-may-be-read"), GENUINE)


class Decisions(LocalCase):
    def test_four_directions_and_risk_reconciliation(self):
        checked_paths = 0
        for key, pair in SCENARIOS.items():
            with self.subTest(case=key):
                target = self.root / key
                case = run(target, key)
                watch, initial, five, ten = case["cards"]
                self.assertEqual([c["market_status"] for c in case["cards"]],
                                 ["WATCH", "EXECUTABLE", "EXECUTABLE", "EXECUTABLE"])
                self.assertEqual((initial["episode"]["family"], initial["episode"]["direction"]), pair)
                self.assertEqual([five["reprice"]["requested_delay_minutes"], ten["reprice"]["requested_delay_minutes"]], [5, 10])
                self.assertEqual(initial["episode"], ten["episode"])
                self.assertGreaterEqual(initial["trigger"]["open_ms"], initial["episode"]["earliest_trigger_open_ms"])
                self.assertEqual(initial["warnings"], ["SYNTHETIC_QA_ONLY", "NOT_GENUINE_MARKET"])
                self.assertEqual(initial["account_context_status"], "UNAVAILABLE")
                self.assertEqual(initial["account_overlay"], "MANUAL_ACCOUNT_CHECK_REQUIRED")
                journal = DecisionJournal(target / "journal.sqlite")
                self.assertEqual(journal.read(card_id=initial["card_id"]), initial)
                self.assertEqual(journal.events()[-1]["kind"], "MANUAL")
                self.assertTrue(verify_card(MarketAdapter(target / "source.sqlite"), initial)["raw_receipts"])
                ledger = Ledger(target / "source.sqlite", FIXTURE)
                for card in (initial, five, ten):
                    checked_paths += self.recalculate(card, ledger)
        self.assertEqual(checked_paths, 48)

    def recalculate(self, card, ledger):
        with localcontext() as ctx:
            ctx.prec = 40
            plan = card["plan"]
            sign = card["episode"]["sign"]
            def raw(name):
                ref = card["card_context"][name]
                return json.loads(ledger.store.raw(ref["receipt_id"]))

            quote, depth = raw("quote"), raw("depth")
            products = raw("instrument")["symbols"]
            filters = next(row["filters"] for row in products if row["symbol"] == card["symbol"])
            tick = D(next(rule["tickSize"] for rule in filters if rule["filterType"] == "PRICE_FILTER"))
            self.assertEqual(tick, D(plan["tick"]))
            rate = D(card["policy"]["fee_rate"])
            slippage = D(card["policy"]["slippage_bps"]) / 10_000
            bid, ask = D(quote["bidPrice"]), D(quote["askPrice"])
            best = max(ask, D(depth["asks"][0][0])) if sign == 1 else min(bid, D(depth["bids"][0][0]))
            outward = ROUND_CEILING if sign == 1 else ROUND_FLOOR
            inward = ROUND_FLOOR if sign == 1 else ROUND_CEILING

            def grid(price, mode):
                return (price / tick).to_integral_value(rounding=mode) * tick

            entry = grid(best + sign * best * slippage, outward)
            self.assertEqual(entry, D(plan["entry_fill"]))
            stop = D(plan["hard_stop"])
            stress = max(tick, D(card["episode"]["atr14"]) * D(card["policy"]["stop_stress_atr"]))
            stop_fill = grid(stop - sign * ((ask - bid) / 2 + stop * slippage + stress), inward)
            mark = raw("mark")
            crosses = int(mark["nextFundingTime"] <= card["evaluated_ms"] + 6 * 3_600_000)
            funding = crosses * max(D(mark["markPrice"]), entry) * max(D(mark["lastFundingRate"]) * sign, D("0.00010"))

            def pnl(price):
                return sign * (price - entry) - entry * rate - price * rate - funding

            risk = -pnl(stop_fill)
            self.assertEqual(risk, D(plan["unit_stop_loss_usdt"]))
            self.assertEqual(funding, D(plan["funding"]["stress_cost_usdt_per_base"]))
            for row in plan["targets"]:
                target = D(row["price"])
                fill = grid(target - sign * ((ask - bid) / 2 + target * slippage), inward)
                self.assertEqual(D(row["exit_fill"]), fill)
                self.assertLess(abs(D(row["net_r"]) - pnl(fill) / risk), D("1e-36"))
            fractions = list(map(D, card["policy"]["exit_fractions"]))
            local_returns = [pnl(D(row["exit_fill"])) for row in plan["targets"]]
            for n, combined in enumerate(plan["conditional_paths"]):
                cost = sum(fractions[i] * local_returns[i] for i in range(n)) - (1 - sum(fractions[:n])) * risk
                self.assertLess(abs(D(combined["net_r"]) - cost / risk), D("1e-36"))
            return 1 + len(plan["targets"])

    def test_no_chase_and_atomic_journal_recovery(self):
        case = run(self.root / "chase", "trend_pullback-long", chase=True)
        self.assertNotEqual(case["cards"][2]["market_status"], "EXECUTABLE")
        self.assertIn("MISSED_NO_CHASE", case["cards"][2]["reasons"])
        pub = self.collector().scan((SYMBOL,))
        engine = compose(self.path, self.root / "journal.sqlite", FIXTURE)

        def fail():
            raise RuntimeError("power failure")

        args = {"scan": pub["scan_id"], "as_of_ms": pub["visible_venue_upper_ms"]}
        with self.assertRaisesRegex(RuntimeError, "power failure"):
            engine.evaluate(SYMBOL, **args, before_commit=fail)
        self.assertIsNone(engine.journal.read())
        self.assertEqual(engine.journal.events(), [])
        actual = engine.evaluate(SYMBOL, **args)
        self.assertEqual(actual["market_status"], "NO_SETUP")
        self.assertEqual(actual, engine.evaluate(SYMBOL, **args))
        with self.assertRaises(sqlite3.DatabaseError), engine.journal.connect(write=True) as db:
            db.execute("UPDATE cards SET payload='{}'")

    def test_nonzero_funding_charge_reconciles_from_raw(self):
        feed = FabricatedMarket(self.path, *SCENARIOS["trend_pullback-long"])
        feed.transport.mutate = lambda route, params, body: usd_m_fixture(route, params, feed.respond(route, params, body))
        collector = Collector.fixture(self.path, feed.clock, feed.transport, self.identity)
        first = collector.scan((SYMBOL,))
        engine = compose(self.path, self.root / "funding-journal.sqlite", FIXTURE)
        engine.evaluate(SYMBOL, scan=first["scan_id"], as_of_ms=first["visible_venue_upper_ms"])
        advance(feed, AFTER_TRIGGER, "funding")
        second = collector.scan((SYMBOL,))
        card = engine.evaluate(SYMBOL, scan=second["scan_id"], as_of_ms=second["visible_venue_upper_ms"])
        self.assertEqual(card["market_status"], "EXECUTABLE")
        self.assertGreater(D(card["plan"]["funding"]["stress_cost_usdt_per_base"]), 0)
        self.assertEqual(self.recalculate(card, collector.ledger), 4)

    def test_cli_and_module_reject_hostile_configuration(self):
        cfg = self.root / "config.json"
        cfg.write_text('{"status":"ACTIVE","live_requests_enabled":true}')
        env = {**os.environ, "QUANT_B4_LIVE": "1", "B4_ACTIVATION": str(cfg), "HTTPS_PROXY": "http://127.0.0.1:7",
               "BINANCE_API_KEY": "fabricated-for-test", "BINANCE_API_SECRET": "fabricated-for-test"}
        invoked = subprocess.run([sys.executable, "-m", "quant_personal_public_bridge_b4", "live-scan", "--config",
                                  str(cfg)], env=env, capture_output=True, text=True)
        self.assertEqual((invoked.returncode, invoked.stderr.strip(), invoked.stdout), (3, DISABLED, ""))

