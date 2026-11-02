"""SQLite selector state, immutable episode anchors and atomic capacity reservations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from typing import Any

from ..core import fingerprint, primitive
from ..position_management import AdvisoryStore


@dataclass(frozen=True)
class Capital:
    equity: float
    free_margin: float
    available_ts: int
    source: str = "SYNTHETIC_CURRENT_EQUITY"


class SelectorStore(AdvisoryStore):
    def __init__(self, path, clock_ms=None):
        super().__init__(path, clock_ms=clock_ms)
        with self._connect() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS selector_states (
                symbol TEXT PRIMARY KEY, cutoff INTEGER NOT NULL, evidence TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS selector_episodes (
                id TEXT PRIMARY KEY, anchors TEXT NOT NULL, state TEXT NOT NULL,
                revision INTEGER NOT NULL, updated_ts INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS selector_transitions (
                id TEXT NOT NULL, revision INTEGER NOT NULL, evidence TEXT NOT NULL,
                PRIMARY KEY(id,revision));
              CREATE TABLE IF NOT EXISTS selector_delivery (
                event_id TEXT PRIMARY KEY, evidence TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS selector_reservations (
                episode_id TEXT PRIMARY KEY, evidence TEXT NOT NULL, status TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS selector_position_bindings (
                position_id TEXT PRIMARY KEY, episode_id TEXT NOT NULL, evidence TEXT NOT NULL);
            """)

    def regime(self, symbol: str) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT evidence FROM selector_states WHERE symbol=?", (symbol,)).fetchone()
        return (
            json.loads(row[0])
            if row
            else {"state": "UNKNOWN", "pending": "UNKNOWN", "count": 0, "failures": 0, "cutoff": -1}
        )

    def save_regime(self, symbol: str, value: dict) -> dict:
        encoded = json.dumps(value, sort_keys=True, allow_nan=False)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT cutoff,evidence FROM selector_states WHERE symbol=?", (symbol,)
            ).fetchone()
            if row and row[0] > value["cutoff"]:
                raise ValueError("REGIME_CHECKPOINT_ADVANCED_RETRY")
            if row and row[0] == value["cutoff"]:
                if row[0] == value["cutoff"] and row[1] != encoded:
                    raise ValueError("REGIME_SAME_BAR_CONFLICT")
                return json.loads(row[1])
            db.execute(
                "INSERT OR REPLACE INTO selector_states VALUES (?,?,?)", (symbol, value["cutoff"], encoded)
            )
        return value

    def revoke_regime(self, symbol: str, now: int, structural_cutoff: int) -> None:
        """An outage revokes persisted readiness immediately, including between structural bars.

        Recovery requires the ordinary two NEW completed structural observations.
        """
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT evidence FROM selector_states WHERE symbol=?", (symbol,)).fetchone()
            old = json.loads(row[0]) if row else {}
            from ..canary.clock_domain import current_decision, same_epoch

            context = current_decision()
            native = context is not None and old.get("clock_sample") is not None
            if native and context is not None:
                sample, scope = context
                if (
                    scope != old.get("clock_scope_hash")
                    or same_epoch([old["clock_sample"], sample])
                    or old["clock_sample"]["mono_after_ms"] > sample["mono_before_ms"]
                    or old.get("source_override_clock_sample", {}).get("mono_after_ms", -1)
                    >= sample["mono_before_ms"]
                ):
                    return
            elif old.get("source_override_ts", -1) >= now or old.get("cutoff", -1) > now:
                return
            cutoff = max(old.get("cutoff", -1), structural_cutoff)
            value = {
                "state": "UNKNOWN",
                "pending": "UNKNOWN",
                "count": 0,
                "failures": 0,
                "cutoff": cutoff,
                "source_override_ts": now,
                "reason": "SOURCE_HEALTH_OVERRIDE",
            }
            if native and context is not None:
                value.update(
                    clock_sample=old["clock_sample"],
                    clock_scope_hash=context[1],
                    source_override_clock_sample=context[0],
                )
            db.execute(
                "INSERT OR REPLACE INTO selector_states VALUES (?,?,?)",
                (symbol, cutoff, json.dumps(value, sort_keys=True)),
            )

    def episode(self, identity: str) -> dict:
        with self._connect() as db:
            row = db.execute(
                "SELECT anchors,state,revision,updated_ts FROM selector_episodes WHERE id=?", (identity,)
            ).fetchone()
        if row is None:
            raise KeyError(identity)
        return {
            "anchors": json.loads(row[0]),
            "state": json.loads(row[1]),
            "revision": row[2],
            "updated_ts": row[3],
        }

    def create_episode(self, anchors: dict, now: int) -> dict:
        if now < anchors.get("setup_ts", 0):
            from ..canary.clock_domain import NativeProvenance, from_record, native_before

            p = from_record(anchors["setup_provenance"]) if anchors.get("setup_provenance") else None
            if (
                not isinstance(p, NativeProvenance)
                or p.reason(now, 2000)
                or not native_before(p, anchors["setup_ts"], now)
            ):
                raise ValueError("SETUP_NOT_YET_AVAILABLE")
        proof = anchors.get("regime_evidence")
        if proof is not None:
            if (
                proof["state"] != anchors["regime"]
                or proof["cutoff"] != anchors["setup_ts"]
                or proof.get("count", 0) < 2
            ):
                raise ValueError("FROZEN_REGIME_EVIDENCE_INVALID")
        encoded = json.dumps(primitive(anchors), sort_keys=True, allow_nan=False)
        initial = json.dumps(
            {
                "status": "WATCH",
                "reasons": [],
                "confirmation_ids": [],
                "trigger_ids": [],
                "notification_event": None,
                "limit_placed_ts": None,
                "execution": "NOT_REPORTED",
            },
            sort_keys=True,
        )
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT anchors FROM selector_episodes WHERE id=?", (anchors["id"],)).fetchone()
            if row and row[0] != encoded:
                raise ValueError("IMMUTABLE_SETUP_ANCHOR_CONFLICT")
            db.execute(
                "INSERT OR IGNORE INTO selector_episodes VALUES (?,?,?,0,?)",
                (anchors["id"], encoded, initial, now),
            )
            db.execute(
                "INSERT OR IGNORE INTO selector_transitions VALUES (?,0,?)",
                (anchors["id"], json.dumps({"decision_ts": now, "state": json.loads(initial)})),
            )
        if proof is not None and self.regime(anchors["symbol"])["cutoff"] < proof["cutoff"]:
            self.save_regime(anchors["symbol"], proof)
        return self.episode(anchors["id"])

    def transition(self, identity: str, expected_revision: int, state: dict, now: int) -> dict:
        encoded = json.dumps(primitive(state), sort_keys=True, allow_nan=False)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT state,revision,updated_ts FROM selector_episodes WHERE id=?", (identity,)
            ).fetchone()
            if row is None or row[1] != expected_revision:
                raise ValueError("EPISODE_REVISION_CONFLICT")
            if now < row[2]:
                raise ValueError("EPISODE_TIME_REGRESSION")
            old = json.loads(row[0])
            if old["status"] in {"CANCELLED", "EXPIRED"} and state != old:
                raise ValueError("TERMINAL_EPISODE_IMMUTABLE")
            allowed = {
                "WATCH": {"WATCH", "ARMED", "CANCELLED", "EXPIRED"},
                "ARMED": {"ARMED", "ENTRY_ELIGIBLE", "CANCELLED", "EXPIRED"},
                "ENTRY_ELIGIBLE": {"ENTRY_ELIGIBLE", "ARMED", "CANCELLED", "EXPIRED"},
            }
            if old["status"] in allowed and state["status"] not in allowed[old["status"]]:
                raise ValueError("EPISODE_TRANSITION_INVALID")
            if old["trigger_ids"] and state["trigger_ids"] != old["trigger_ids"]:
                raise ValueError("TRIGGER_BAR_IDS_IMMUTABLE")
            if old.get("notification_event") and state.get("notification_event") != old["notification_event"]:
                raise ValueError("NOTIFICATION_IDENTITY_IMMUTABLE")
            if (
                old.get("limit_placed_ts") is not None
                and state.get("limit_placed_ts") != old["limit_placed_ts"]
            ):
                raise ValueError("ORIGINAL_LIMIT_PLACEMENT_IMMUTABLE")
            if old.get("execution") == "USER_REPORTED" and state.get("execution") != "USER_REPORTED":
                raise ValueError("USER_EXECUTION_AUTHORITY_IMMUTABLE")
            if row[0] == encoded:
                return self.episode(identity)
            revision = row[1] + 1
            db.execute(
                "UPDATE selector_episodes SET state=?,revision=?,updated_ts=? WHERE id=?",
                (encoded, revision, now, identity),
            )
            db.execute(
                "INSERT INTO selector_transitions VALUES (?,?,?)",
                (identity, revision, json.dumps({"decision_ts": now, "state": primitive(state)})),
            )
        return self.episode(identity)

    def delivery(self, event_id: str, *, delivered_ts: int | None = None, acknowledged_ts: int | None = None):
        """A sender acknowledgement alone is not actual delivery. Synthetic assumptions are explicit."""
        if delivered_ts is None:
            with self._connect() as db:
                row = db.execute(
                    "SELECT evidence FROM selector_delivery WHERE event_id=?", (event_id,)
                ).fetchone()
            return json.loads(row[0]) if row else {"delivery": "UNKNOWN", "acknowledged_ts": None}
        notice = self.get_notification(event_id)
        if notice["status"] != "SENDER_ACCEPTED" or delivered_ts < notice["persisted_commit_at_ms"]:
            raise ValueError("DELIVERY_WITHOUT_PERSISTED_ACCEPTED_FAKE_SEND")
        if acknowledged_ts is None or acknowledged_ts < delivered_ts:
            raise ValueError("ACK_BEFORE_DELIVERY")
        value = {
            "delivery": "SIMULATED_DELIVERY_ASSUMPTION",
            "delivered_ts": delivered_ts,
            "acknowledged_ts": acknowledged_ts,
        }
        with self._connect() as db:
            old = db.execute(
                "SELECT evidence FROM selector_delivery WHERE event_id=?", (event_id,)
            ).fetchone()
            encoded = json.dumps(value, sort_keys=True)
            if old and old[0] != encoded:
                raise ValueError("IMMUTABLE_DELIVERY_ASSUMPTION")
            db.execute("INSERT OR IGNORE INTO selector_delivery VALUES (?,?)", (event_id, encoded))
        return value

    def reserve(
        self, proposal: dict, capital: Capital, now: int, limits: dict, exposures: tuple[dict, ...] = ()
    ) -> dict:
        """Signed beta and correlation constraints include pending/unknown execution reservations."""
        if (
            capital.available_ts > now
            or now - capital.available_ts > 60_000
            or capital.equity <= 0
            or not isfinite(capital.equity)
            or not isfinite(capital.free_margin)
            or capital.free_margin < 0
        ):
            raise ValueError("CURRENT_EQUITY_UNAVAILABLE")
        if capital.source not in {"SYNTHETIC_CURRENT_EQUITY", "USER_REPORTED_CURRENT_EQUITY"}:
            raise ValueError("EQUITY_SOURCE_NOT_AUTHORIZED")
        for p in (proposal, *exposures):
            if any(p.get(k) is None for k in ("beta", "risk", "notional", "side", "cluster")):
                raise ValueError("INCOMPLETE_ESSENTIAL_PORTFOLIO_EVIDENCE")
            if (
                p["risk"] < 0
                or p["notional"] <= 0
                or p["side"] not in (-1, 1)
                or any(not isfinite(p[k]) for k in ("risk", "notional", "beta"))
            ):
                raise ValueError("INVALID_EXPOSURE")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT evidence,status FROM selector_reservations WHERE episode_id=?",
                (proposal["episode_id"],),
            ).fetchone()
            encoded = json.dumps(proposal, sort_keys=True, allow_nan=False)
            status = "RESERVED"
            if row:
                status = row[1]
                if row[1] == "RELEASED_CONFIRMED":
                    raise ValueError("RESERVATION_ID_CONFLICT")
                if row[1] != "RESERVED":
                    previous = json.loads(row[0])
                    if proposal["risk"] > previous["risk"] or proposal["side"] != previous["side"]:
                        raise ValueError("PENDING_ORDER_RISK_RECONCILIATION_REQUIRED")
                    proposal, encoded = previous, row[0]
            occupied = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT evidence FROM selector_reservations WHERE status != 'RELEASED_CONFIRMED' AND episode_id != ?",
                    (proposal["episode_id"],),
                )
            ]
            # Reconcile actual bound positions against reservations, retaining the larger obligation.
            merged = {p["episode_id"]: dict(p) for p in [*occupied, proposal]}
            actual = {}
            for index, e in enumerate(exposures):
                key = e.get("episode_id", "EXTERNAL:" + str(index))
                if key not in actual:
                    actual[key] = dict(e)
                else:
                    if actual[key]["side"] != e["side"] or actual[key]["symbol"] != e["symbol"]:
                        raise ValueError("BOUND_POSITION_IDENTITY_CONFLICT")
                    for metric in ("risk", "notional", "margin"):
                        actual[key][metric] = actual[key].get(metric, 0) + e.get(metric, 0)
            for key, e in actual.items():
                if key not in merged:
                    merged[key] = e
                else:
                    if merged[key]["side"] != e["side"] or merged[key]["symbol"] != e["symbol"]:
                        raise ValueError("BOUND_POSITION_IDENTITY_CONFLICT")
                    merged[key] = {
                        **merged[key],
                        "beta": e["beta"],
                        **{
                            k: max(merged[key].get(k, 0), e.get(k, 0)) for k in ("risk", "notional", "margin")
                        },
                    }
            all_items = list(merged.values())
            eq = capital.equity
            checks = {
                "TOTAL_RISK_CAPACITY": sum(p["risk"] for p in all_items) <= eq * limits["total_risk"],
                "CLUSTER_RISK_CAPACITY": all(
                    sum(p["risk"] for p in all_items if p["cluster"] == c) <= eq * limits["cluster_risk"]
                    for c in {p["cluster"] for p in all_items}
                ),
                "GROSS_EXPOSURE_CAPACITY": sum(p["notional"] for p in all_items) <= eq * limits["gross"],
                "SYMBOL_EXPOSURE_CAPACITY": all(
                    sum(p["notional"] for p in all_items if p["symbol"] == s) <= eq * limits["symbol"]
                    for s in {p["symbol"] for p in all_items}
                ),
                "SIGNED_BETA_CAPACITY": abs(sum(p["side"] * p["beta"] * p["notional"] for p in all_items))
                <= eq * limits["net_beta"],
                "FREE_MARGIN_CAPACITY": sum(
                    float(p["margin"]) if "margin" in p else float(p["notional"]) for p in all_items
                )
                <= capital.free_margin,
            }
            failed = [k for k, v in checks.items() if not v]
            if failed:
                raise ValueError("|".join(failed))
            db.execute(
                "INSERT OR REPLACE INTO selector_reservations VALUES (?,?,?)",
                (proposal["episode_id"], encoded, status),
            )
        return proposal

    def reservation_status(self, episode_id: str, status: str, *, execution_confirmed: bool = False):
        if status not in {"PENDING_ORDER", "EXECUTION_UNKNOWN", "OPEN", "RELEASED_CONFIRMED"}:
            raise ValueError("INVALID_RESERVATION_STATUS")
        if status == "RELEASED_CONFIRMED" and not execution_confirmed:
            raise ValueError("UNKNOWN_PENDING_CAPACITY_CANNOT_BE_RELEASED")
        with self._connect() as db:
            db.execute("UPDATE selector_reservations SET status=? WHERE episode_id=?", (status, episode_id))

    def reservations(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [
                {**json.loads(r[0]), "status": r[1]}
                for r in db.execute("SELECT evidence,status FROM selector_reservations ORDER BY episode_id")
            ]

    def ledger_exposures(self, marks: dict, now: int) -> tuple[dict, ...]:
        """Include every as-of user position. Unknown external-symbol valuation blocks new capacity."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT id,evidence FROM platform_position_versions ORDER BY id,version"
            ).fetchall()
            bindings = dict(db.execute("SELECT position_id,episode_id FROM selector_position_bindings"))
        latest = {}
        for identity, encoded in rows:
            p = self._decode(encoded)
            if p.updated_ts <= now:
                latest[identity] = p
        exposures = []
        for identity, p in latest.items():
            if p.status == "CLOSED" or p.quantity == 0:
                continue
            mark = marks.get(p.symbol)
            if (
                mark is None
                or len(mark) != 5
                or any(v is None for v in mark)
                or mark[2] > now
                or now - mark[2] > 600_000
                or mark[0] <= 0
                or mark[3] <= 0
                or mark[4] < 0
            ):
                raise ValueError("EXISTING_POSITION_VALUATION_OR_BETA_UNKNOWN")
            if p.status == "STOP_BREACHED":
                raise ValueError("EXISTING_POSITION_EXECUTION_RECONCILIATION_REQUIRED")
            side = 1 if p.direction == "LONG" else -1
            exposures.append(
                {
                    "episode_id": bindings.get(identity, "USER:" + identity),
                    "symbol": p.symbol,
                    "side": side,
                    "beta": mark[1],
                    "risk": float(p.quantity)
                    * (max(0, side * (mark[0] - float(p.stop))) + mark[4])
                    * mark[3],
                    "notional": float(p.quantity) * mark[0] * mark[3],
                    "margin": float(p.quantity) * mark[0] * mark[3] / p.leverage,
                    "cluster": "CONSERVATIVE_CRYPTO_COMMON_CLUSTER",
                }
            )
        return tuple(exposures)

    def notify_episode(self, identity: str, now: int, sender) -> str:
        episode = self.episode(identity)
        if now < episode["updated_ts"]:
            raise ValueError("NOTIFICATION_BEFORE_EPISODE_DECISION")
        if episode["state"]["status"] in {"CANCELLED", "EXPIRED"} or not episode["state"]["trigger_ids"]:
            raise ValueError("TERMINAL_OR_UNTRIGGERED_EPISODE_CANNOT_NOTIFY_ENTRY")
        event = episode["state"].get("notification_event")
        if event:
            self.dispatch(event, sender, now)
            return event
        origin = fingerprint([identity, "TRIGGER_NOTICE"])
        with self._connect() as db:
            prior = db.execute(
                "SELECT decision_id FROM platform_decision_origins WHERE origin=?", (origin,)
            ).fetchone()
        decision = prior[0] if prior else self.commit_decision(episode, now, now, origin=origin)
        event = self.prepare(decision, episode["anchors"]["symbol"], now)
        state = {**episode["state"], "notification_event": event}
        self.transition(identity, episode["revision"], state, now)
        self.dispatch(event, sender, now)
        return event
