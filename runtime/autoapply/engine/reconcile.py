"""Uncertain submission reconciliation against ATS and email confirmation evidence (P20).

Enforces AA-JOB-006, C-10:
- Binds verification to the exact customer account, canonical role ID, and approved artifact hash.
- Transitions `uncertain` -> `submitted_verified` when matching confirmation evidence is found,
  without ever resending a non-idempotent application.
"""

from __future__ import annotations

from typing import Protocol

from autoapply.engine.state_machine import (
    ApplicationRecord,
    ApplicationStateMachine,
)


class ATSConfirmationReaderProtocol(Protocol):
    """Read-only interface to inspect ATS confirmation state."""

    def query_confirmation_receipt(
        self,
        *,
        candidate_account_id: str,
        canonical_role_id: str,
        expected_resume_sha256: str,
    ) -> str | None: ...


class SubmissionReconciler:
    """Reconciles `uncertain` submissions by reading ATS/email receipts before any retry decision."""

    def __init__(self, *, state_machine: ApplicationStateMachine) -> None:
        self._sm = state_machine

    def reconcile_uncertain_application(
        self,
        *,
        application_id: str,
        attempt_id: str,
        ats_server: ATSConfirmationReaderProtocol,
        canonical_role_id: str,
    ) -> ApplicationRecord:
        app = self._sm.get_application(application_id)
        receipt = ats_server.query_confirmation_receipt(
            candidate_account_id=app.account_id,
            canonical_role_id=canonical_role_id,
            expected_resume_sha256=app.approved_artifact_sha256,
        )
        if receipt is not None:
            return self._sm.record_verified_receipt(
                application_id,
                attempt_id=attempt_id,
                remote_receipt_id=receipt,
            )
        return app
