"""Native Source inspection and explicitly synthetic network-to-D compatibility.

Genuine native observations stay in their native ledger. The accepted D model is
synthetic-only: this adapter cannot silently relabel genuine data or promote it.
"""

from __future__ import annotations

import json
from pathlib import Path

from ...domain import Candle
from ..qualified_source import NativeQuarantineRecord
from ..rc_source import canonical as d_canonical, normalize
from ..reporting import document, table
from .contract import require


def replay_synthetic_session(journal, session, store):
    records = journal.records(session)
    converted = []
    for value in records:
        require(value["exposure"] == "SYNTHETIC_NETWORK", "GENUINE_NATIVE_CANNOT_ENTER_SYNTHETIC_MODEL")
        record = NativeQuarantineRecord.model_validate(value["record"])
        candle = Candle(
            symbol=record.symbol,
            interval=record.interval,
            open_time_ms=record.open_time_ms,
            close_time_ms=record.close_time_ms,
            open=record.open,
            high=record.high,
            low=record.low,
            close=record.close,
            volume=record.volume,
            available_at_ms=record.available_ms,
        )
        from dataclasses import asdict

        raw = d_canonical(
            {
                "schema": "SYNTHETIC_CLOSED_BAR_V1",
                "venue": "SYNTHETIC_SIMULATOR",
                "source_id": "PROGRAM_A_SYNTHETIC_V1",
                "candle": asdict(candle),
                "source_event_ms": record.source_event_ms,
                "received_ms": record.received_ms,
                "available_ms": record.available_ms,
                "durable_ms": record.durable_ms,
                "revision": 0,
            }
        )
        converted.append(normalize(raw))
    admitted = store.admit(converted)
    # Bind both independent raw wire and D synthetic projection without changing either schema.
    with journal.db() as db:
        journal.append(
            db,
            session,
            "SYNTHETIC_D_COMPATIBILITY_ONLY",
            {
                "source_native_identities": [x["identity"] for x in records],
                "D_receipt_ids": [x.identity for x in converted],
                "admitted": admitted,
                "causal_times": "PRESERVED_WITHOUT_RETIMING",
                "source_qualified": False,
            },
        )
    return admitted


def source_status(journal, session, asof_ms):
    journal.verify()
    from .contract import strict, digest

    with journal.db() as db:
        selected = db.execute("SELECT grant_json FROM sessions WHERE id=?", (session,)).fetchone()
        require(selected is not None, "SESSION_MISSING")
        exposure = strict(selected[0])["exposure"]
        records = [strict(raw) for (raw,) in db.execute("SELECT value FROM receipts ORDER BY frame")]
    records = [r for r in records if r["exposure"] == exposure]
    visible = [r for r in records if r["record"]["durable_ms"] <= asof_ms]
    output = []
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        bars = [r["record"] for r in visible if r["record"]["symbol"] == symbol]
        counts = {i: len([b for b in bars if b["interval"] == i]) for i in ("1H", "4H", "1D")}
        from ..swing import INTERVALS

        trigger = asof_ms // INTERVALS["4H"] * INTERVALS["4H"]
        gaps = []
        latest = {}
        for interval in ("4H", "1D"):
            ends = sorted({b["end_time_ms"] for b in bars if b["interval"] == interval})
            latest[interval] = ends[-1] if ends else None
            if len(ends) < 60:
                gaps.append("WARMUP_INCOMPLETE:" + interval)
            if not ends or ends[-1] != trigger // INTERVALS[interval] * INTERVALS[interval]:
                gaps.append("LATEST_COMPLETED_BAR_MISSING:" + interval)
            if any(b - a != INTERVALS[interval] for a, b in zip(ends, ends[1:])):
                gaps.append("MISSING_INTERVAL:" + interval)
        if asof_ms - trigger > 300000:
            gaps.append("STALE_TRIGGER")
        output.append(
            {
                "Symbol": symbol,
                "Source": "NATIVE_UNQUALIFIED"
                if any(r["exposure"] == "NATIVE_UNQUALIFIED" for r in visible)
                else "SYNTHETIC_NETWORK",
                "State": "SOURCE_BLOCKED",
                "Warmup": counts,
                "Latest completed": latest,
                "Clock": "RUNTIME_CHECKED_INDEPENDENT_AUDIT_PENDING",
                "Evidence gaps": gaps or ["WARMUP_COMPLETE_NATIVE_ADMISSION_PENDING"],
                "Durable prefix": digest(visible),
                "Reason": "INDEPENDENT_SOURCE_ADMISSION_PENDING; WARMUP_NOT_PROMOTED",
                "Account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
                "Strategy": "trend_pullback; S2/S3 RESEARCH_ONLY_DISABLED",
            }
        )
    return output


def render_blocked_native(journal, session, output, asof_ms):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows = source_status(journal, session, asof_ms)
    value = {
        "schema": "E_SOURCE_BLOCKED_VIEW_V1",
        "asof_ms": asof_ms,
        "rows": rows,
        "source_qualified": False,
        "shadow_qualified": False,
        "economic_validation": False,
        "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
    }
    # Uses the accepted document/table renderer and CSS; no new frontend.
    (output / "latest.html").write_text(
        document(
            "Swing advisory — native source blocked",
            table(rows),
            label="NATIVE_UNQUALIFIED / SYNTHETIC_NETWORK · SOURCE_BLOCKED · ACCOUNT UNKNOWN / VETO",
        ),
        encoding="utf-8",
    )
    (output / "latest.json").write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return value
