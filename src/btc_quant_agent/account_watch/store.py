from __future__ import annotations

from pathlib import Path

from ..live_db import connection
from .models import AccountSnapshotV1


class AccountStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with connection(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS live_account_snapshots (
                    snapshot_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_live_account_snapshot_latest
                    ON live_account_snapshots(account_id, observed_at_ms DESC);
                CREATE TABLE IF NOT EXISTS live_account_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_hash TEXT NOT NULL REFERENCES live_account_snapshots(snapshot_hash),
                    event_type TEXT NOT NULL, observed_at_ms INTEGER NOT NULL);
            """)

    def save(self, snapshot: AccountSnapshotV1, event_type: str = "REST_RECONCILED") -> None:
        snapshot.verify()
        if event_type not in {"REST_RECONCILED", "REST_CONFLICT", "WS_UPDATE", "WS_DISCONNECTED", "MARGIN_CALL"}:
            raise ValueError("unsupported account event")
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            inserted = db.execute(
                "INSERT OR IGNORE INTO live_account_snapshots VALUES (?,?,?,?)",
                (snapshot.snapshot_hash, snapshot.account_id, snapshot.observed_at_ms,
                 snapshot.canonical_json()),
            ).rowcount
            if inserted:
                db.execute(
                    "INSERT INTO live_account_events(snapshot_hash,event_type,observed_at_ms) VALUES (?,?,?)",
                    (snapshot.snapshot_hash, event_type, snapshot.observed_at_ms),
                )

    def latest(self, account_id: str) -> AccountSnapshotV1 | None:
        with connection(self.path) as db:
            row = db.execute(
                "SELECT payload FROM live_account_snapshots WHERE account_id=? "
                "ORDER BY observed_at_ms DESC, rowid DESC LIMIT 1", (account_id,),
            ).fetchone()
        if row is None:
            return None
        return AccountSnapshotV1.model_validate_json(row["payload"])
