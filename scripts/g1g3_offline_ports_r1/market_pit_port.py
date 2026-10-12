"""MarketPitPort: Validates synthetic local MarketEventV1 envelopes against Controller contract.

Rejects incomplete/unclosed bars, stale or future-known timestamps, provenance drift,
wrong symbol/product/channel, clock uncertainty (wall vs monotonic regression),
book sequence gaps/crossed spreads, bar gaps (no forward fill), and estimated/unsettled
funding rates. Deduplicates idempotently while recording observable counters.
"""

from __future__ import annotations

import copy
from typing import Any

from scripts.g1_offline_preview_r1.fixtures import bar as g1_synthetic_bar
from scripts.g1_offline_preview_r1.model import SafetyViolation, decimal, digest, exact, timestamp

VALID_CHANNELS = {
    "last_kline_1m",
    "mark_price",
    "agg_trade",
    "depth_delta",
    "depth_snapshot",
    "funding_settled",
    "health",
}
VALID_QUALITIES = {"VERIFIED", "DEGRADED", "UNKNOWN", "INVALID"}
PINNED_SYNTHETIC_STREAM_ID = "SYNTHETIC_LOCAL_PIT_V1"
PINNED_RAW_MANIFEST_SHA256 = digest(
    {"stream": PINNED_SYNTHETIC_STREAM_ID, "contract": "market-event-v1", "synthetic_only": True}
)

ENVELOPE_REQUIRED_KEYS = {
    "schema_version",
    "symbol",
    "product",
    "channel",
    "provider_event_ms",
    "provider_transaction_ms",
    "observed_wall_utc_ms",
    "observed_monotonic_ns",
    "available_at_ms",
    "source_stream_id",
    "connection_epoch",
    "source_sequence",
    "payload_sha256",
    "payload",
    "quality",
    "reason_codes",
    "raw_source_manifest_sha256",
}

BOOK_REQUIRED_KEYS = {
    "snapshot_update_id",
    "first_update_id",
    "final_update_id",
    "previous_final_update_id",
    "continuous",
    "best_bid",
    "best_ask",
    "observed_depth_levels",
    "stale_age_ms",
    "quality",
    "reason_codes",
}


def _check_no_secrets_in_obj(value: Any) -> None:
    text = str(value).lower()
    if any(
        tok in text for tok in ("api_key", "secret", "password", "bearer ", "token=", "listenkey")
    ):
        raise SafetyViolation("MARKET_EVENT_SECRET_OR_PRIVATE_FIELD")


def compute_market_event_dedupe_key(envelope: dict[str, Any]) -> str:
    """Canonical deduplication key: sha256(symbol, channel, epoch, provider-id-or-raw-sha)."""
    seq = envelope.get("source_sequence")
    prov_id = f"seq:{seq}" if seq is not None else f"sha:{envelope.get('payload_sha256', '')}"
    return digest(
        [
            envelope.get("symbol"),
            envelope.get("channel"),
            envelope.get("connection_epoch"),
            prov_id,
        ]
    )


class MarketPitPort:
    """Fail-closed validator and translator for synthetic local MarketEventV1 envelopes."""

    def __init__(
        self,
        *,
        expected_stream_id: str = PINNED_SYNTHETIC_STREAM_ID,
        expected_manifest_sha256: str = PINNED_RAW_MANIFEST_SHA256,
        max_stale_ms: int = 60000,
    ) -> None:
        self.expected_stream_id = expected_stream_id
        self.expected_manifest_sha256 = expected_manifest_sha256
        self.max_stale_ms = max_stale_ms
        self.last_wall_utc_ms: int = -1
        self.last_monotonic_ns: int = -1
        self.last_bar_open_ms: int | None = None
        self.last_book_final_update_id: int | None = None
        self.seen_dedupe_keys: dict[str, str] = {}
        self.duplicate_envelope_count: int = 0
        self.accepted_envelope_count: int = 0
        self.rejected_envelope_count: int = 0
        self.max_feature_known_at_ms: int = -1

    def validate_book_integrity(self, book: Any) -> dict[str, Any]:
        """Validate BookIntegrityV1 optional sub-envelope."""
        exact(book, BOOK_REQUIRED_KEYS, "BOOK_SCHEMA_INVALID")
        for id_key in ("snapshot_update_id", "first_update_id", "final_update_id"):
            if type(book[id_key]) is not int or book[id_key] < 0:
                raise SafetyViolation("BOOK_INTEGRITY_INVALID")
        prev_id = book["previous_final_update_id"]
        if prev_id is not None and (type(prev_id) is not int or prev_id < 0):
            raise SafetyViolation("BOOK_INTEGRITY_INVALID")
        if type(book["continuous"]) is not bool or not book["continuous"]:
            raise SafetyViolation("BOOK_SEQUENCE_GAP")
        if self.last_book_final_update_id is not None and prev_id != self.last_book_final_update_id:
            raise SafetyViolation("BOOK_SEQUENCE_GAP")
        if book["first_update_id"] > book["final_update_id"]:
            raise SafetyViolation("BOOK_INTEGRITY_INVALID")
        bid = decimal(book["best_bid"], positive=True)
        ask = decimal(book["best_ask"], positive=True)
        if bid >= ask:
            raise SafetyViolation("BOOK_CROSSED_SPREAD")
        if type(book["observed_depth_levels"]) is not int or book["observed_depth_levels"] <= 0:
            raise SafetyViolation("BOOK_INTEGRITY_INVALID")
        if (
            type(book["stale_age_ms"]) is not int
            or book["stale_age_ms"] < 0
            or book["stale_age_ms"] > self.max_stale_ms
        ):
            raise SafetyViolation("BOOK_STALE")
        if book["quality"] != "VERIFIED":
            raise SafetyViolation("BOOK_QUALITY_INVALID")
        if not isinstance(book["reason_codes"], list) or not all(
            isinstance(rc, str) for rc in book["reason_codes"]
        ):
            raise SafetyViolation("BOOK_SCHEMA_INVALID")
        self.last_book_final_update_id = book["final_update_id"]
        return copy.deepcopy(book)

    def ingest_envelope(
        self,
        envelope: dict[str, Any],
        *,
        reference_at_ms: int | None = None,
    ) -> dict[str, Any]:
        """Validate one MarketEventV1 envelope and translate to G1 event if applicable."""
        try:
            if not isinstance(envelope, dict):
                raise SafetyViolation("MARKET_EVENT_SCHEMA")
            keys = set(envelope.keys())
            optional_keys = {"book"}
            if keys - optional_keys != ENVELOPE_REQUIRED_KEYS:
                raise SafetyViolation("MARKET_EVENT_SCHEMA")
            if envelope["schema_version"] != "market-event-v1":
                raise SafetyViolation("MARKET_EVENT_SCHEMA_VERSION")
            if envelope["symbol"] != "BTCUSDT":
                raise SafetyViolation("MARKET_EVENT_SYMBOL_INVALID")
            if envelope["product"] != "BINANCE_USDT_M_PERP":
                raise SafetyViolation("MARKET_EVENT_PRODUCT_INVALID")
            channel = envelope["channel"]
            if channel not in VALID_CHANNELS:
                raise SafetyViolation("MARKET_EVENT_CHANNEL_INVALID")
            if not isinstance(envelope["reason_codes"], list) or not all(
                isinstance(x, str) for x in envelope["reason_codes"]
            ):
                raise SafetyViolation("MARKET_EVENT_SCHEMA")

            prov_e = envelope["provider_event_ms"]
            if prov_e is None:
                if not envelope["reason_codes"]:
                    raise SafetyViolation("PROVIDER_EVENT_MS_MISSING_WITHOUT_WHY")
            else:
                timestamp(prov_e)

            prov_t = envelope["provider_transaction_ms"]
            if prov_t is not None:
                timestamp(prov_t)

            wall_ms = timestamp(envelope["observed_wall_utc_ms"])
            mono_ns = envelope["observed_monotonic_ns"]
            if type(mono_ns) is not int or mono_ns < 0:
                raise SafetyViolation("MONOTONIC_NS_INVALID")
            avail_ms = timestamp(envelope["available_at_ms"])

            # available_at_ms is the no-earlier-than receiver ingress wall time of record
            if avail_ms < wall_ms:
                raise SafetyViolation("AVAILABLE_AT_BEFORE_INGRESS_WALL")
            if prov_e is not None and avail_ms < prov_e:
                raise SafetyViolation("AVAILABLE_AT_BEFORE_PROVIDER_EVENT")
            if reference_at_ms is not None:
                timestamp(reference_at_ms)
                if avail_ms > reference_at_ms:
                    raise SafetyViolation("MARKET_EVENT_FUTURE_KNOWN")
                if reference_at_ms - avail_ms > self.max_stale_ms:
                    raise SafetyViolation("MARKET_EVENT_STALE")

            # Provenance & public-only checks
            stream_id = envelope["source_stream_id"]
            if not isinstance(stream_id, str) or not stream_id:
                raise SafetyViolation("SOURCE_STREAM_ID_INVALID")
            _check_no_secrets_in_obj(stream_id)
            if stream_id != self.expected_stream_id:
                raise SafetyViolation("MARKET_PROVENANCE_DRIFT")

            if (
                not isinstance(envelope["raw_source_manifest_sha256"], str)
                or envelope["raw_source_manifest_sha256"] != self.expected_manifest_sha256
            ):
                raise SafetyViolation("MARKET_PROVENANCE_DRIFT")

            epoch = envelope["connection_epoch"]
            if type(epoch) is not int or epoch < 1:
                raise SafetyViolation("CONNECTION_EPOCH_INVALID")
            seq = envelope["source_sequence"]
            if seq is not None and (type(seq) is not int or seq < 0):
                raise SafetyViolation("SOURCE_SEQUENCE_INVALID")

            payload = envelope["payload"]
            if not isinstance(payload, dict):
                raise SafetyViolation("MARKET_EVENT_PAYLOAD_INVALID")
            _check_no_secrets_in_obj(payload)
            if digest(payload) != envelope["payload_sha256"]:
                raise SafetyViolation("MARKET_EVENT_PAYLOAD_HASH_MISMATCH")

            quality = envelope["quality"]
            if quality not in VALID_QUALITIES:
                raise SafetyViolation("MARKET_EVENT_QUALITY_INVALID")
            if quality != "VERIFIED":
                raise SafetyViolation("MARKET_EVENT_QUALITY_UNUSABLE")
            if "CLOCK_UNCERTAIN" in envelope["reason_codes"]:
                raise SafetyViolation("CLOCK_UNCERTAIN")

            # Deduplication check before monotonic advancement or state mutation
            dedupe_key = compute_market_event_dedupe_key(envelope)
            if dedupe_key in self.seen_dedupe_keys:
                if self.seen_dedupe_keys[dedupe_key] != envelope["payload_sha256"]:
                    raise SafetyViolation("MARKET_EVENT_PROVENANCE_DRIFT")
                self.duplicate_envelope_count += 1
                return {
                    "status": "DUPLICATE_IGNORED",
                    "dedupe_key": dedupe_key,
                    "duplicate_count": self.duplicate_envelope_count,
                    "g1_event": None,
                }

            # Monotonic vs wall clock consistency check
            if self.last_monotonic_ns >= 0:
                if mono_ns <= self.last_monotonic_ns:
                    raise SafetyViolation("MONOTONIC_REGRESSION")
                if wall_ms < self.last_wall_utc_ms:
                    raise SafetyViolation("CLOCK_UNCERTAIN")

            if "book" in envelope and envelope["book"] is not None:
                self.validate_book_integrity(envelope["book"])
            elif channel in ("depth_delta", "depth_snapshot"):
                raise SafetyViolation("BOOK_SCHEMA_INVALID")

            g1_event: dict[str, Any] | None = None
            if channel == "last_kline_1m":
                g1_event = self._translate_bar(payload, avail_ms=avail_ms, seq=seq)
            elif channel == "funding_settled":
                g1_event = self._translate_funding(payload, avail_ms=avail_ms, wall_ms=wall_ms)

            self.last_wall_utc_ms = wall_ms
            self.last_monotonic_ns = mono_ns
            self.max_feature_known_at_ms = max(self.max_feature_known_at_ms, avail_ms)
            self.seen_dedupe_keys[dedupe_key] = envelope["payload_sha256"]
            self.accepted_envelope_count += 1
            return {
                "status": "ACCEPTED",
                "dedupe_key": dedupe_key,
                "available_at_ms": avail_ms,
                "feature_known_at_ms": self.max_feature_known_at_ms,
                "payload_sha256": envelope["payload_sha256"],
                "g1_event": g1_event,
            }
        except SafetyViolation:
            self.rejected_envelope_count += 1
            raise

    def _translate_bar(
        self, payload: dict[str, Any], *, avail_ms: int, seq: int | None
    ) -> dict[str, Any]:
        exact(
            payload,
            {
                "bar_open_ms",
                "bar_close_ms",
                "closed",
                "last_open",
                "last_high",
                "last_low",
                "last_close",
                "mark_close",
                "event_id",
            },
            "BAR_PAYLOAD_SCHEMA_INVALID",
        )
        if payload["closed"] is not True:
            raise SafetyViolation("BAR_INCOMPLETE_UNCLOSED")
        open_ms = timestamp(payload["bar_open_ms"])
        close_ms = timestamp(payload["bar_close_ms"])
        if open_ms % 60000 != 0 or close_ms != open_ms + 59999 or avail_ms < close_ms:
            raise SafetyViolation("BAR_PIT_INVALID")
        if avail_ms - close_ms > self.max_stale_ms:
            raise SafetyViolation("MARKET_EVENT_STALE")
        if self.last_bar_open_ms is not None and open_ms != self.last_bar_open_ms + 60000:
            raise SafetyViolation("NO_DATA_UNKNOWN_GAP")
        o, h, low, c, _mark = [
            decimal(payload[k], positive=True)
            for k in ("last_open", "last_high", "last_low", "last_close", "mark_close")
        ]
        if low > min(o, c) or h < max(o, c) or low > h:
            raise SafetyViolation("BAR_OHLC_INVALID")
        self.last_bar_open_ms = open_ms
        bar_idx = open_ms // 60000
        event_id = payload["event_id"] if isinstance(payload["event_id"], str) else f"BAR-{bar_idx}"
        del seq
        return {
            "id": event_id,
            "kind": "BAR",
            "at": avail_ms,
            "payload": {
                "source": "SYNTHETIC_V1",
                "open_time": open_ms,
                "close_time": close_ms,
                "available_at": avail_ms,
                "last_open": payload["last_open"],
                "last_high": payload["last_high"],
                "last_low": payload["last_low"],
                "last_close": payload["last_close"],
                "mark_close": payload["mark_close"],
            },
        }

    def _translate_funding(
        self, payload: dict[str, Any], *, avail_ms: int, wall_ms: int
    ) -> dict[str, Any]:
        exact(
            payload,
            {
                "event_id",
                "settlement_id",
                "settlement_at_ms",
                "rate_fraction",
                "settled",
                "rate_type",
            },
            "FUNDING_PAYLOAD_SCHEMA_INVALID",
        )
        if payload["settled"] is not True or payload["rate_type"] != "SETTLED_REALIZED":
            raise SafetyViolation("FUNDING_ESTIMATED_NOT_SETTLED")
        settlement_at = timestamp(payload["settlement_at_ms"])
        if wall_ms < settlement_at or avail_ms != settlement_at:
            raise SafetyViolation("FUNDING_PIT_INVALID")
        rate = decimal(payload["rate_fraction"])
        if abs(rate) > decimal("0.1"):
            raise SafetyViolation("FUNDING_RATE_BOUNDS")
        return {
            "id": payload["event_id"],
            "kind": "FUNDING",
            "at": settlement_at,
            "payload": {
                "settlement_id": payload["settlement_id"],
                "settlement_at": settlement_at,
                "rate_fraction": payload["rate_fraction"],
            },
        }

    def validate_decision_pit(self, decision_at_ms: int) -> None:
        """Ensure decision timestamp is never earlier than feature_known_at_ms."""
        timestamp(decision_at_ms)
        if self.max_feature_known_at_ms < 0 or decision_at_ms < self.max_feature_known_at_ms:
            raise SafetyViolation("DECISION_BEFORE_FEATURE_KNOWN_AT")


def make_synthetic_market_event_v1_from_g1_bar(
    g1_bar_event: dict[str, Any],
    *,
    sequence: int,
    monotonic_ns: int,
    connection_epoch: int = 1,
    stream_id: str = PINNED_SYNTHETIC_STREAM_ID,
    manifest_sha256: str = PINNED_RAW_MANIFEST_SHA256,
) -> dict[str, Any]:
    """Wrap a synthetic G1 BAR event into a canonical MarketEventV1 envelope."""
    b = g1_bar_event["payload"]
    payload = {
        "event_id": g1_bar_event["id"],
        "bar_open_ms": b["open_time"],
        "bar_close_ms": b["close_time"],
        "closed": True,
        "last_open": b["last_open"],
        "last_high": b["last_high"],
        "last_low": b["last_low"],
        "last_close": b["last_close"],
        "mark_close": b["mark_close"],
    }
    avail = b["available_at"]
    return {
        "schema_version": "market-event-v1",
        "symbol": "BTCUSDT",
        "product": "BINANCE_USDT_M_PERP",
        "channel": "last_kline_1m",
        "provider_event_ms": b["close_time"],
        "provider_transaction_ms": b["close_time"],
        "observed_wall_utc_ms": avail,
        "observed_monotonic_ns": monotonic_ns,
        "available_at_ms": avail,
        "source_stream_id": stream_id,
        "connection_epoch": connection_epoch,
        "source_sequence": sequence,
        "payload_sha256": digest(payload),
        "payload": payload,
        "quality": "VERIFIED",
        "reason_codes": [],
        "raw_source_manifest_sha256": manifest_sha256,
    }


def make_synthetic_market_event_v1_from_g1_funding(
    g1_funding_event: dict[str, Any],
    *,
    sequence: int,
    monotonic_ns: int,
    connection_epoch: int = 1,
    stream_id: str = PINNED_SYNTHETIC_STREAM_ID,
    manifest_sha256: str = PINNED_RAW_MANIFEST_SHA256,
) -> dict[str, Any]:
    """Wrap a synthetic G1 FUNDING event into a canonical MarketEventV1 envelope."""
    f = g1_funding_event["payload"]
    at = g1_funding_event["at"]
    payload = {
        "event_id": g1_funding_event["id"],
        "settlement_id": f["settlement_id"],
        "settlement_at_ms": f["settlement_at"],
        "rate_fraction": f["rate_fraction"],
        "settled": True,
        "rate_type": "SETTLED_REALIZED",
    }
    return {
        "schema_version": "market-event-v1",
        "symbol": "BTCUSDT",
        "product": "BINANCE_USDT_M_PERP",
        "channel": "funding_settled",
        "provider_event_ms": at,
        "provider_transaction_ms": at,
        "observed_wall_utc_ms": at,
        "observed_monotonic_ns": monotonic_ns,
        "available_at_ms": at,
        "source_stream_id": stream_id,
        "connection_epoch": connection_epoch,
        "source_sequence": sequence,
        "payload_sha256": digest(payload),
        "payload": payload,
        "quality": "VERIFIED",
        "reason_codes": [],
        "raw_source_manifest_sha256": manifest_sha256,
    }


def make_synthetic_bar_envelope(
    index: int = 0,
    *,
    side: str = "LONG",
    exit_kind: str = "STOP",
    sequence: int | None = None,
    monotonic_ns: int | None = None,
) -> dict[str, Any]:
    """Build a standalone synthetic MarketEventV1 bar envelope for unit tests."""
    b = g1_synthetic_bar(index, side=side, exit_kind=exit_kind)
    seq = index if sequence is None else sequence
    mono = (index + 1) * 1_000_000 if monotonic_ns is None else monotonic_ns
    return make_synthetic_market_event_v1_from_g1_bar(
        {"id": f"BAR-{index}", "kind": "BAR", "at": b["available_at"], "payload": b},
        sequence=seq,
        monotonic_ns=mono,
    )
