"""Canonical URL normalization, direct-employer identity dedupe, and rolling 30-day window (P16).

Enforces AA-JOB-003, 06-VB-JOBS-PARITY-AND-LESSONS.md (Lessons 5 & 6):
- Normalizes URLs (strips tracking query parameters, fragments, and trailing slashes).
- Dedupes across canonical role ID, normalized URL, and direct employer (end-client) identity.
- Enforces configurable rolling employer submission window (default 30 days).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import uuid


TRACKING_QUERY_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gh_jid",
        "gh_src",
        "source",
        "ref",
    }
)


class DedupeConflictError(RuntimeError):
    """Raised when a job violates role, URL, or rolling direct-employer dedupe rules."""


def normalize_job_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    # Lowercase path for case-insensitive canonical comparison while keeping clean query params
    clean_query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in TRACKING_QUERY_PARAMS
    ]
    return urlunparse((scheme, netloc, path.lower(), "", urlencode(clean_query), ""))


@dataclass(frozen=True)
class JobReservation:
    """Atomic SQLite reservation record for a job and direct employer."""

    reservation_id: str
    job_id: str
    direct_employer_id: str
    canonical_role_id: str
    normalized_url: str
    owner_id: str
    reserved_at_epoch: int


class EmployerDedupeLedger:
    """SQLite-backed dedupe and reservation ledger across roles, URLs, and direct employers."""

    def __init__(self, *, db_path: Path, rolling_window_days: int = 30) -> None:
        self._db_path = db_path.resolve()
        self._rolling_window_seconds = rolling_window_days * 86400
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_reservations (
                    reservation_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    direct_employer_id TEXT NOT NULL,
                    canonical_role_id TEXT NOT NULL,
                    normalized_url TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    reserved_at_epoch INTEGER NOT NULL
                )
                """
            )

    def reserve_job(
        self,
        *,
        job_id: str,
        direct_employer_id: str,
        canonical_role_id: str,
        canonical_url: str,
        owner_id: str,
        now_epoch_seconds: int,
    ) -> JobReservation:
        norm_url = normalize_job_url(canonical_url)
        window_start = now_epoch_seconds - self._rolling_window_seconds

        with self._conn:
            existing = self._conn.execute(
                """
                SELECT * FROM job_reservations
                WHERE canonical_role_id = ?
                   OR normalized_url = ?
                   OR (direct_employer_id = ? AND reserved_at_epoch >= ?)
                """,
                (canonical_role_id, norm_url, direct_employer_id, window_start),
            ).fetchone()

            if existing is not None:
                raise DedupeConflictError(
                    f"duplicate_role_or_rolling_employer_window: conflicts with reservation "
                    f"{existing['reservation_id']} for employer '{direct_employer_id}'"
                )

            res_id = f"res_{uuid.uuid4().hex[:12]}"
            self._conn.execute(
                """
                INSERT INTO job_reservations (
                    reservation_id, job_id, direct_employer_id,
                    canonical_role_id, normalized_url, owner_id, reserved_at_epoch
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    res_id,
                    job_id,
                    direct_employer_id,
                    canonical_role_id,
                    norm_url,
                    owner_id,
                    now_epoch_seconds,
                ),
            )

        return JobReservation(
            reservation_id=res_id,
            job_id=job_id,
            direct_employer_id=direct_employer_id,
            canonical_role_id=canonical_role_id,
            normalized_url=norm_url,
            owner_id=owner_id,
            reserved_at_epoch=now_epoch_seconds,
        )
