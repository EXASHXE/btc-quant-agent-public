"""Fail-closed causal admission and immutable revision ledger for offline receipts."""
from dataclasses import asdict
from datetime import datetime, timezone

from .schema import Bar, Batch, ClockProof, INTERVALS, MINUTE, Quote, Snapshot, digest, finite


def utc_ms(text):
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp() * 1000)


PROTECTED = (utc_ms("2024-01-01"), utc_ms("2027-01-01"))
HOLDOUT = (utc_ms("2026-02-01"), utc_ms("2026-08-01"))
MIN_BARS = {"1D": 8, "4H": 16, "1H": 16}
MAX_BARS = 64


class SourceError(ValueError):
    def __init__(self, code, global_veto=False):
        super().__init__(code)
        self.code = code
        self.global_veto = global_veto


def allowed_range(start, end):
    if type(start) is not int or type(end) is not int or start >= end:
        raise SourceError("INVALID_EXCHANGE_RANGE")
    for bounds, code in ((HOLDOUT, "HOLDOUT_EXCLUDED"), (PROTECTED, "PROTECTED_HISTORY_EXCLUDED")):
        if start < bounds[1] and end > bounds[0]:
            raise SourceError(code)


class SourceLedger:
    def __init__(self):
        self.identities = {}
        self.quarantine = {}
        self.last_asof = {}
        self.last_end = {}
        self.global_veto = None

    def veto(self, code):
        self.global_veto = code
        raise SourceError(code, True)

    def admit(self, snapshot: Snapshot):
        """Validate every supplied row before features; commit fingerprints atomically."""
        s, clock = snapshot, snapshot.clock
        if type(s.symbol) is not str or not s.symbol:
            raise SourceError("MALFORMED_SYMBOL")
        if self.global_veto:
            raise SourceError(self.global_veto, True)
        if s.source_veto:
            self.veto("OVERALL_SOURCE_VETO")
        if (not isinstance(clock, ClockProof) or type(s.asof_ms) is not int or clock.strict_ok is not True
                or clock.authority != "SYNTHETIC_STRICT_FIXTURE"
                or not all(type(v) is int for v in (clock.exchange_lower_ms, clock.exchange_upper_ms,
                                                    clock.sampled_ms))
                or not 0 <= s.asof_ms - clock.sampled_ms <= MINUTE
                or not clock.sampled_ms <= clock.exchange_lower_ms <= s.asof_ms
                <= clock.exchange_upper_ms
                or clock.exchange_upper_ms - clock.exchange_lower_ms > 2_000):
            self.veto("STRICT_CLOCK_UNPROVEN")
        if s.asof_ms < self.last_asof.get(s.symbol, s.asof_ms):
            self.veto("ASOF_REWIND")
        if s.symbol in self.quarantine:
            raise SourceError("SYMBOL_QUARANTINED:" + self.quarantine[s.symbol])
        try:
            groups, staged = self._validate(s)
        except SourceError as error:
            self.quarantine[s.symbol] = error.code
            raise
        self.identities.update(staged)
        self.last_asof[s.symbol] = s.asof_ms
        self.last_end.update({(s.symbol, interval): bars[-1].end_ms for interval, bars in groups.items()})
        self.identities = {key: value for key, value in self.identities.items()
                           if key[2] >= self.last_end[key[:2]] - MAX_BARS * INTERVALS[key[1]]}
        return groups

    def _validate(self, s):
        if (type(s.batches) is not tuple or any(not isinstance(b, Batch) for b in s.batches)
                or (s.quote is not None and not isinstance(s.quote, Quote))):
            raise SourceError("MALFORMED_SOURCE_ENVELOPE")
        groups, staged = {}, {}
        for batch in s.batches:
            if (batch.symbol != s.symbol or type(batch.interval) is not str
                    or batch.interval not in INTERVALS):
                raise SourceError("BATCH_IDENTITY_MISMATCH")
            if (type(batch.bars) is not tuple or any(not isinstance(b, Bar) for b in batch.bars)
                    or len(batch.bars) > MAX_BARS):
                raise SourceError("MALFORMED_OR_OVERSIZED_BAR_BATCH")
            if batch.interval in groups:
                raise SourceError("DUPLICATE_INTERVAL_BATCH")
            if batch.provenance != "SYNTHETIC_Q0B_V2":
                raise SourceError("PROVENANCE_NOT_OFFLINE_SYNTHETIC")
            allowed_range(batch.requested_start_ms, batch.requested_end_ms)
            if batch.requested_end_ms > s.asof_ms:
                raise SourceError("FUTURE_REQUEST_RANGE")
            step, previous = INTERVALS[batch.interval], None
            for b in batch.bars:
                if b.symbol != batch.symbol or b.interval != batch.interval:
                    raise SourceError("BAR_IDENTITY_MISMATCH")
                if b.provenance != batch.provenance or b.venue != "BINANCE_USDM_OFFLINE":
                    raise SourceError("BAR_PROVENANCE_MISMATCH")
                if not all(type(v) is int for v in (b.open_ms, b.end_ms, b.exchange_close_ms,
                                                    b.available_ms, b.received_ms,
                                                    b.exchange_observed_lower_ms, b.revision)):
                    raise SourceError("INTEGER_TIMESTAMPS_REQUIRED")
                allowed_range(b.open_ms, b.end_ms)
                if (b.open_ms % step or b.end_ms != b.open_ms + step
                        or b.exchange_close_ms != b.end_ms - 1):
                    raise SourceError("EXCHANGE_INTERVAL_PROOF_FAILED")
                if not batch.requested_start_ms <= b.open_ms < b.end_ms <= batch.requested_end_ms:
                    raise SourceError("ROW_OUTSIDE_REQUEST_RANGE")
                if (b.closed is not True or not b.end_ms <= b.exchange_observed_lower_ms
                        <= b.received_ms <= b.available_ms <= s.asof_ms
                        or b.end_ms > s.clock.exchange_lower_ms):
                    raise SourceError("OPEN_OR_FUTURE_OR_UNAVAILABLE_BAR")
                if (not finite(b.open, b.high, b.low, b.close, b.volume)
                        or not 0 < b.low <= min(b.open, b.close) <= max(b.open, b.close) <= b.high
                        or b.volume < 0):
                    raise SourceError("INVALID_OHLCV")
                if b.revision != 0:
                    raise SourceError("REVISION_QUARANTINED")
                # Re-fetch receipts can arrive later without revising market content.
                content = asdict(b)
                for field in ("received_ms", "available_ms", "exchange_observed_lower_ms"):
                    content.pop(field)
                fingerprint = digest(content)
                if b.key in staged:
                    raise SourceError("DUPLICATE_BAR")
                if b.key in self.identities and self.identities[b.key] != fingerprint:
                    raise SourceError("REVISION_QUARANTINED")
                if previous is not None and b.open_ms != previous + step:
                    raise SourceError("GAP_OR_UNORDERED_BAR")
                previous = b.open_ms
                staged[b.key] = fingerprint
            if (not batch.bars or batch.bars[0].open_ms != batch.requested_start_ms
                    or batch.bars[-1].end_ms != batch.requested_end_ms):
                raise SourceError("REQUEST_EDGE_GAP")
            if batch.bars[-1].end_ms < self.last_end.get((s.symbol, batch.interval), 0):
                raise SourceError("INTERVAL_WATERMARK_REWIND")
            prior_end = self.last_end.get((s.symbol, batch.interval))
            if prior_end is not None and batch.bars[0].open_ms > prior_end:
                raise SourceError("CROSS_SNAPSHOT_GAP")
            groups[batch.interval] = batch.bars
        for interval, count in MIN_BARS.items():
            bars = groups.get(interval, ())
            if len(bars) < count:
                raise SourceError("MISSING_REQUIRED_" + interval)
            if s.asof_ms - bars[-1].end_ms > INTERVALS[interval] + 2 * MINUTE:
                raise SourceError("STALE_REQUIRED_" + interval)
        # Optional 15m/5m absence or staleness cannot erase a finished 1H WATCH.
        q = s.quote
        if q is not None:
            if (q.symbol != s.symbol or q.provenance != "SYNTHETIC_Q0B_V2"
                    or q.venue != "BINANCE_USDM_OFFLINE"):
                raise SourceError("QUOTE_IDENTITY_OR_PROVENANCE")
            if (not all(type(v) is int for v in (q.exchange_ms, q.available_ms, q.received_ms))
                    or not q.exchange_ms <= q.received_ms <= q.available_ms <= s.asof_ms
                    or q.exchange_ms > s.clock.exchange_lower_ms
                    or not finite(q.bid, q.ask, q.bid_size, q.ask_size)
                    or not 0 < q.bid <= q.ask or min(q.bid_size, q.ask_size) < 0):
                raise SourceError("INVALID_OR_FUTURE_QUOTE")
        return groups, staged
