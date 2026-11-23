"""Append-only redacted H3 measurements. Payload and identity never enter this schema."""

import hashlib
import math
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

LANE = "OFFLINE_SYNTHETIC"
LANES = (LANE, "GENUINE_PUBLIC", "REAL_FEISHU", "REAL_MODEL_AUTHORIZED", "UNOBSERVED")
METRICS = {
    "SOURCE_TO_CARD": ("SOURCE_PUBLICATION", "CARD_COMMIT"),
    "CARD_TO_ENQUEUE": ("CARD_COMMIT", "OUTBOX_ENQUEUE"),
    "ENQUEUE_TO_ACK": ("OUTBOX_ENQUEUE", "PROVIDER_ACK"),
    "INBOUND_TO_FIRST_RESPONSE": ("INBOUND_DM", "FIRST_DM_RESPONSE"),
    "INBOUND_TO_FINAL_RESPONSE": ("INBOUND_DM", "FINAL_DM_REPLY"),
    "TOOL_DURATION": ("TOOL_BEGIN", "TOOL_END"),
    "MODEL_DURATION": ("MODEL_BEGIN", "MODEL_END"),
    "RECOVERY_DURATION": ("RECOVERY_BEGIN", "RECOVERY_END"),
}
EVENTS = frozenset(event for pair in METRICS.values() for event in pair) | {
    "GET_DISPATCH",
    "GET_RESPONSE",
    "RAW_RECEIPT_VERIFIED",
    "B2_BEGIN",
    "B2_END",
    "SOURCE_GAP",
    "DUPLICATE",
    "SENDER_ATTEMPT",
    "DELIVERY_FAILURE",
    "INBOUND_REJECT",
    "REPRICE_5",
    "REPRICE_10",
    "RESTART",
    "START",
    "STOP",
    "OPERATOR_FEEDBACK",
}
CODES = frozenset(
    {
        "OK",
        "ACK",
        "MOCK",
        "RETRYABLE",
        "PERMANENT",
        "UNKNOWN_DELIVERY",
        "SUPPRESSED",
        "EXPIRED",
        "UNAUTHORIZED",
        "SOURCE_BLOCKED",
        "NOT_EVALUATED",
        "NO_SETUP",
        "WATCH",
        "INVALID",
        "EXECUTABLE",
        "CANCELLED",
        "TIMEOUT",
        "REJECTED",
        "DUPLICATE",
        "FALLBACK",
        "NO_MODEL",
        "MARKED_FOR_REVIEW",
        "REPRICE_UNOBSERVED",
    }
)
MIN_PERCENTILE_SAMPLES = 30


def correlate(*parts):
    return hashlib.sha256("\0".join(str(part) for part in parts).encode()).hexdigest()


class Measurements:
    def __init__(self, path):
        self.path = Path(path)
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS measurements (
                    seq INTEGER PRIMARY KEY, lane TEXT NOT NULL, event TEXT NOT NULL,
                    correlation TEXT NOT NULL, code TEXT NOT NULL,
                    wall_ns INTEGER NOT NULL, mono_ns INTEGER NOT NULL,
                    count INTEGER, weight INTEGER, venue_ms INTEGER
                );
                CREATE TRIGGER IF NOT EXISTS no_update BEFORE UPDATE ON measurements
                BEGIN SELECT RAISE(ABORT, 'append only'); END;
                CREATE TRIGGER IF NOT EXISTS no_delete BEFORE DELETE ON measurements
                BEGIN SELECT RAISE(ABORT, 'append only'); END;
            """)

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def record(self, event, correlation, *, code="OK", count=None, weight=None, venue_ms=None):
        if (
            event not in EVENTS
            or code not in CODES
            or not re.fullmatch(r"[0-9a-f]{64}", correlation)
            or any(
                value is not None and (type(value) is not int or value < 0)
                for value in (count, weight, venue_ms)
            )
        ):
            raise ValueError("UNSCHEMATIZED_TELEMETRY")
        stamp = time.time_ns(), time.monotonic_ns()
        with closing(self._connect()) as db, db:
            db.execute(
                """INSERT INTO measurements(lane,event,correlation,code,wall_ns,mono_ns,count,weight,venue_ms)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (LANE, event, correlation, code, *stamp, count, weight, venue_ms),
            )

    def rows(self):
        with closing(self._connect()) as db:
            return [dict(row) for row in db.execute("SELECT * FROM measurements ORDER BY seq")]

    def report(self):
        rows = self.rows()
        result = {}
        for lane in LANES:
            lane_rows = [row for row in rows if row["lane"] == lane]
            samples = {}
            for label, (begin, end) in METRICS.items():
                starts, values = {}, []
                for row in lane_rows:
                    key = row["correlation"]
                    if row["event"] == begin:
                        starts.setdefault(key, row["mono_ns"])
                    if row["event"] == end and key in starts:
                        duration = row["mono_ns"] - starts.pop(key)
                        if duration >= 0:
                            values.append(duration)
                values.sort()
                enough = len(values) >= MIN_PERCENTILE_SAMPLES
                samples[label] = {
                    "status": "OBSERVED" if enough else "INCONCLUSIVE",
                    "raw_ns": values,
                    "p50_ns": values[math.ceil(len(values) * 0.50) - 1] if enough else None,
                    "p95_ns": values[math.ceil(len(values) * 0.95) - 1] if enough else None,
                }
            result[lane] = {
                "status": "OBSERVED" if lane_rows else "UNOBSERVED",
                "samples": samples,
                "get_dispatches": sum(row["event"] == "GET_DISPATCH" for row in lane_rows),
                "synthetic_request_weight": sum(
                    row["weight"] or 0 for row in lane_rows if row["event"] == "GET_DISPATCH"
                )
                if lane_rows
                else None,
                "delivery_failures": sum(row["event"] == "DELIVERY_FAILURE" for row in lane_rows),
                "unknown_delivery": sum(row["code"] == "UNKNOWN_DELIVERY" for row in lane_rows),
                "source_gaps": sum(row["event"] == "SOURCE_GAP" for row in lane_rows),
                "restarts": sum(row["event"] == "RESTART" for row in lane_rows),
                "duplicate_suppression": sum(row["event"] == "DUPLICATE" for row in lane_rows),
                "model_tokens": None,
                "model_cost": None,
                "human_read": None,
            }
        return result


def pi_export():
    """No operational row qualifies for P2 until an independent live baseline receipt."""
    return {
        "schema": "H3_TO_PI_P2_V1",
        "status": "UNOBSERVED",
        "controller_baseline_receipt_sha256": None,
        "operational_samples": [],
    }
