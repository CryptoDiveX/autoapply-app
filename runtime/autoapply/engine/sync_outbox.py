"""Durable local outbox for external tracker synchronization (AA-TRACK-001, T-TRACK-01)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid


class DurableSyncOutbox:
    """Commits tracker sync intents to local SQLite before any external write is attempted."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_outbox (
                entry_id TEXT PRIMARY KEY,
                application_id TEXT NOT NULL,
                target_system TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def enqueue(self, *, application_id: str, target_system: str, payload: dict[str, Any]) -> str:
        entry_id = f"outbox_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO sync_outbox (entry_id, application_id, target_system, payload_json, status, attempts, updated_at)
                VALUES (?, ?, ?, ?, 'pending', 0, ?)
                """,
                (entry_id, application_id, target_system, json.dumps(payload, sort_keys=True), now),
            )
        return entry_id

    def get_entry(self, entry_id: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM sync_outbox WHERE entry_id = ?",
            (entry_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown outbox entry: {entry_id}")
        result = dict(row)
        result["payload"] = json.loads(result["payload_json"])
        return result

    def process_entry(self, entry_id: str, adapter: Any) -> None:
        entry = self.get_entry(entry_id)
        payload = entry["payload"]
        now = datetime.now(timezone.utc).isoformat()
        try:
            adapter.update_record(
                record_id=payload["record_id"],
                account_email=payload["account_email"],
                canonical_url=payload["canonical_url"],
                status=payload["status"],
                autoapply_note=payload.get("autoapply_note", ""),
                expected_company_name=payload.get("company_name"),
                expected_job_title=payload.get("job_title"),
            )
        except Exception as exc:
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE sync_outbox
                    SET status = 'pending_retry', attempts = attempts + 1, last_error = ?, updated_at = ?
                    WHERE entry_id = ?
                    """,
                    (str(exc), now, entry_id),
                )
            raise

        with self._conn:
            self._conn.execute(
                """
                UPDATE sync_outbox
                SET status = 'synced', attempts = attempts + 1, last_error = NULL, updated_at = ?
                WHERE entry_id = ?
                """,
                (now, entry_id),
            )
