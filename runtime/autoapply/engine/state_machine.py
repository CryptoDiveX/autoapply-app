"""Durable SQLite application state machine, attempts, and crash-to-uncertain recovery (P17).

Enforces 02-TECHNICAL-SPECIFICATION.md (§7), AA-JOB-006, AA-TRACK-001, NFR-03, C-10:
- Persists durable Attempt with idempotency key before dispatching any external submit.
- Recovers in-flight `submitting` applications after a crash/timeout to `uncertain`
  (`uncertain_effect=True`), blocking blind retry until reconciled.
- Keeps Teal tracker sync state (`TrackerSyncState`) strictly orthogonal to submission state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sqlite3
import uuid


class ApplicationStateError(RuntimeError):
    """Raised on illegal state transitions or blind retries of uncertain submissions."""


class ApplicationState(str, Enum):
    """Canonical application lifecycle states from 02-TECHNICAL-SPECIFICATION.md (§7)."""

    DISCOVERED = "discovered"
    NORMALIZED = "normalized"
    ELIGIBILITY_REVIEW = "eligibility_review"
    SHORTLISTED = "shortlisted"
    RESERVED = "reserved"
    PREPARING = "preparing"
    AWAITING_DOCUMENT_REVIEW = "awaiting_document_review"
    READY = "ready"
    FILLING = "filling"
    AWAITING_USER = "awaiting_user"
    READY_TO_SUBMIT = "ready_to_submit"
    SUBMITTING = "submitting"
    SUBMITTED_UNVERIFIED = "submitted_unverified"
    SUBMITTED_VERIFIED = "submitted_verified"
    INELIGIBLE = "ineligible"
    DUPLICATE = "duplicate"
    CLOSED = "closed"
    SKIPPED = "skipped"
    PAUSED = "paused"
    UNCERTAIN = "uncertain"
    FAILED_RECOVERABLE = "failed_recoverable"
    FAILED_FINAL = "failed_final"
    WITHDRAWN = "withdrawn"


class TrackerSyncState(str, Enum):
    """Orthogonal Teal tracker synchronization states (02-TECHNICAL-SPECIFICATION.md §7)."""

    NOT_CONNECTED = "not_connected"
    PENDING = "pending"
    SYNCING = "syncing"
    VERIFIED = "verified"
    FAILED = "failed"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class ApplicationRecord:
    """Stored application state and orthogonal tracker sync status."""

    application_id: str
    job_id: str
    account_id: str
    state: ApplicationState
    revision: int
    mandate_id: str
    fact_revision: int
    approved_artifact_sha256: str
    uncertain_effect: bool
    tracker_sync_state: TrackerSyncState
    remote_receipt_id: str | None


class ApplicationStateMachine:
    """SQLite-backed durable state machine and attempt ledger."""

    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path.resolve()
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS applications (
                    application_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    mandate_id TEXT NOT NULL,
                    fact_revision INTEGER NOT NULL,
                    approved_artifact_sha256 TEXT NOT NULL,
                    uncertain_effect INTEGER NOT NULL,
                    tracker_sync_state TEXT NOT NULL,
                    remote_receipt_id TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS submission_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    application_id TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    owner_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    remote_receipt_id TEXT
                )
                """
            )

    def create_application(
        self,
        *,
        job_id: str,
        account_id: str,
        mandate_id: str,
        fact_revision: int,
        approved_artifact_sha256: str,
    ) -> str:
        app_id = f"app_{uuid.uuid4().hex[:12]}"
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO applications (
                    application_id, job_id, account_id, state, revision,
                    mandate_id, fact_revision, approved_artifact_sha256,
                    uncertain_effect, tracker_sync_state, remote_receipt_id
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, 0, ?, NULL)
                """,
                (
                    app_id,
                    job_id,
                    account_id,
                    ApplicationState.DISCOVERED.value,
                    mandate_id,
                    fact_revision,
                    approved_artifact_sha256,
                    TrackerSyncState.PENDING.value,
                ),
            )
        return app_id

    def get_application(self, application_id: str) -> ApplicationRecord:
        row = self._conn.execute(
            "SELECT * FROM applications WHERE application_id = ?", (application_id,)
        ).fetchone()
        if row is None:
            raise ApplicationStateError(f"application_not_found: {application_id}")
        return ApplicationRecord(
            application_id=row["application_id"],
            job_id=row["job_id"],
            account_id=row["account_id"],
            state=ApplicationState(row["state"]),
            revision=int(row["revision"]),
            mandate_id=row["mandate_id"],
            fact_revision=int(row["fact_revision"]),
            approved_artifact_sha256=row["approved_artifact_sha256"],
            uncertain_effect=bool(row["uncertain_effect"]),
            tracker_sync_state=TrackerSyncState(row["tracker_sync_state"]),
            remote_receipt_id=row["remote_receipt_id"],
        )

    def transition(self, application_id: str, target_state: ApplicationState) -> ApplicationRecord:
        current = self.get_application(application_id)
        if current.uncertain_effect and target_state == ApplicationState.SUBMITTING:
            raise ApplicationStateError("uncertain_submission_requires_reconciliation")
        with self._conn:
            self._conn.execute(
                """
                UPDATE applications
                SET state = ?, revision = revision + 1
                WHERE application_id = ?
                """,
                (target_state.value, application_id),
            )
        return self.get_application(application_id)

    def begin_submission_attempt(
        self,
        application_id: str,
        *,
        idempotency_key: str,
        owner_id: str,
    ) -> str:
        current = self.get_application(application_id)
        if current.uncertain_effect or current.state in (
            ApplicationState.UNCERTAIN,
            ApplicationState.SUBMITTED_UNVERIFIED,
            ApplicationState.SUBMITTED_VERIFIED,
        ):
            raise ApplicationStateError(
                f"uncertain_submission_requires_reconciliation: state is '{current.state.value}'"
            )
        if current.state != ApplicationState.READY_TO_SUBMIT:
            raise ApplicationStateError(
                f"cannot_submit_from_state: '{current.state.value}'"
            )

        attempt_id = f"att_{uuid.uuid4().hex[:12]}"
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO submission_attempts (
                        attempt_id, application_id, idempotency_key,
                        owner_id, status, remote_receipt_id
                    ) VALUES (?, ?, ?, ?, 'dispatched_in_flight', NULL)
                    """,
                    (attempt_id, application_id, idempotency_key, owner_id),
                )
                self._conn.execute(
                    """
                    UPDATE applications
                    SET state = ?, revision = revision + 1
                    WHERE application_id = ?
                    """,
                    (ApplicationState.SUBMITTING.value, application_id),
                )
        except sqlite3.IntegrityError as exc:
            raise ApplicationStateError(f"duplicate_idempotency_key: {idempotency_key}") from exc

        return attempt_id

    def recover_in_flight_after_crash(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT application_id FROM applications WHERE state = ?",
            (ApplicationState.SUBMITTING.value,),
        ).fetchall()
        recovered = [r["application_id"] for r in rows]
        if recovered:
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE applications
                    SET state = ?, uncertain_effect = 1, revision = revision + 1
                    WHERE state = ?
                    """,
                    (ApplicationState.UNCERTAIN.value, ApplicationState.SUBMITTING.value),
                )
                self._conn.execute(
                    """
                    UPDATE submission_attempts
                    SET status = 'uncertain_after_crash'
                    WHERE status = 'dispatched_in_flight'
                    """
                )
        return recovered

    def record_verified_receipt(
        self,
        application_id: str,
        *,
        attempt_id: str,
        remote_receipt_id: str,
    ) -> ApplicationRecord:
        if not remote_receipt_id:
            raise ApplicationStateError("empty_remote_receipt_id")
        with self._conn:
            self._conn.execute(
                """
                UPDATE submission_attempts
                SET status = 'verified', remote_receipt_id = ?
                WHERE attempt_id = ? AND application_id = ?
                """,
                (remote_receipt_id, attempt_id, application_id),
            )
            self._conn.execute(
                """
                UPDATE applications
                SET state = ?, uncertain_effect = 0, remote_receipt_id = ?, revision = revision + 1
                WHERE application_id = ?
                """,
                (ApplicationState.SUBMITTED_VERIFIED.value, remote_receipt_id, application_id),
            )
        return self.get_application(application_id)

    def update_tracker_sync_state(
        self,
        application_id: str,
        sync_state: TrackerSyncState,
    ) -> ApplicationRecord:
        with self._conn:
            self._conn.execute(
                """
                UPDATE applications
                SET tracker_sync_state = ?
                WHERE application_id = ?
                """,
                (sync_state.value, application_id),
            )
        return self.get_application(application_id)
