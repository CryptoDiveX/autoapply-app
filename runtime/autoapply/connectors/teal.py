"""Teal job tracker adapter with exact record/URL/account verification and post-write readback (AA-TRACK-002)."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class TealRecord:
    record_id: str
    account_email: str
    company_name: str
    job_title: str
    canonical_url: str
    status: str
    notes: str = ""


class TealAdapter:
    """Safely updates matched Teal records while preserving sibling records and user notes."""

    def __init__(self, authenticated_account: str) -> None:
        self._authenticated_account = authenticated_account.strip().lower()
        self._records: dict[str, TealRecord] = {}
        self._simulate_failure = False

    def seed_record(self, record: TealRecord) -> None:
        self._records[record.record_id] = record

    def set_Simulated_failure(self, enabled: bool) -> None:
        self._simulate_failure = enabled

    def get_record(self, record_id: str) -> TealRecord:
        if record_id not in self._records:
            raise KeyError(f"Unknown Teal record: {record_id}")
        return self._records[record_id]

    def update_record(
        self,
        *,
        record_id: str,
        account_email: str,
        canonical_url: str,
        status: str,
        autoapply_note: str,
        expected_company_name: str | None = None,
        expected_job_title: str | None = None,
    ) -> TealRecord:
        if self._simulate_failure:
            raise RuntimeError("TEAL_TRANSIENT_FAILURE: simulated upstream error")

        existing = self.get_record(record_id)
        if (
            account_email.strip().lower() != self._authenticated_account
            or existing.account_email.strip().lower() != self._authenticated_account
            or existing.canonical_url != canonical_url
        ):
            raise PermissionError(
                "TEAL_IDENTITY_OR_URL_MISMATCH: exact record ID, canonical URL, and account match required"
            )

        merged_notes = existing.notes
        if autoapply_note:
            marker = f"[AutoApply] {autoapply_note}"
            if marker not in merged_notes:
                merged_notes = f"{merged_notes}\n{marker}".strip() if merged_notes else marker

        updated = replace(existing, status=status, notes=merged_notes)
        self._records[record_id] = updated

        # Post-write readback verification (T-TRACK-02)
        readback = self.get_record(record_id)
        if readback.status != status or readback.canonical_url != canonical_url:
            raise RuntimeError("TEAL_READBACK_MISMATCH: post-write verification failed")
        if expected_company_name and readback.company_name != expected_company_name:
            raise RuntimeError("TEAL_READBACK_MISMATCH: company_name mismatch after write")
        if expected_job_title and readback.job_title != expected_job_title:
            raise RuntimeError("TEAL_READBACK_MISMATCH: job_title mismatch after write")

        return readback
