"""8-step atomic commit and submit-once protocol (P20).

Enforces 02-TECHNICAL-SPECIFICATION.md (§7 Commit protocol), AA-JOB-006, C-10:
1. Atomically reserve employer/role/application in SQLite.
2. Re-evaluate eligibility and user mandate.
3. Verify approved artifact SHA-256 hash at the actual outbound boundary and attach bytes.
4. Create durable Attempt record and idempotency key before dispatch.
5. Execute permitted external submit once.
6. Capture immediate response and remote receipt ID.
7. On timeout/crash after dispatch, recover to `uncertain` (`uncertain_effect=True`) and
   block duplicate submission until reconciled.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from autoapply.documents.approval import ArtifactApprovalError, ArtifactApprovalRegistry
from autoapply.engine.dedupe import EmployerDedupeLedger
from autoapply.engine.state_machine import (
    ApplicationState,
    ApplicationStateError,
    ApplicationStateMachine,
)
from autoapply.policy.broker import can_submit


class ATSSubmitTargetProtocol(Protocol):
    """Protocol for an ATS submission endpoint."""

    def attach_file(self, field_id: str, file_bytes: bytes) -> str: ...

    def submit_form(self, *, candidate_account_id: str) -> str: ...


class SubmissionProtocolError(RuntimeError):
    """Raised when submission is blocked by policy, TOCTOU hash mismatch, or uncertain state."""


@dataclass(frozen=True)
class SubmissionOutcome:
    """Result of executing a single submission attempt."""

    application_id: str
    attempt_id: str
    state: ApplicationState
    remote_receipt_id: str | None


class SubmissionCoordinator:
    """Coordinates reservation, action-boundary hash check,PolicyBroker gate, and single dispatch."""

    def __init__(
        self,
        *,
        state_machine: ApplicationStateMachine,
        dedupe_ledger: EmployerDedupeLedger,
        approval_registry: ArtifactApprovalRegistry,
    ) -> None:
        self._sm = state_machine
        self._dedupe = dedupe_ledger
        self._approvals = approval_registry

    def prepare_application_for_submit(
        self,
        *,
        job_id: str,
        direct_employer_id: str,
        canonical_role_id: str,
        canonical_url: str,
        account_id: str,
        mandate_id: str,
        fact_revision: int,
        approval_id: str,
        owner_id: str,
        now_epoch_seconds: int,
    ) -> str:
        # Step 1: Atomically reserve in dedupe ledger
        self._dedupe.reserve_job(
            job_id=job_id,
            direct_employer_id=direct_employer_id,
            canonical_role_id=canonical_role_id,
            canonical_url=canonical_url,
            owner_id=owner_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        manifest = self._approvals._manifests[approval_id]
        app_id = self._sm.create_application(
            job_id=job_id,
            account_id=account_id,
            mandate_id=mandate_id,
            fact_revision=fact_revision,
            approved_artifact_sha256=manifest.approved_sha256,
        )
        self._sm.transition(app_id, ApplicationState.RESERVED)
        self._sm.transition(app_id, ApplicationState.READY_TO_SUBMIT)
        return app_id

    def execute_submit_once(
        self,
        *,
        application_id: str,
        ats_server: ATSSubmitTargetProtocol,
        approval_id: str,
        resume_file_path: Path,
        current_fact_revision: int,
        idempotency_key: str,
        owner_id: str,
        consent_current: bool,
        cancelled: bool,
    ) -> SubmissionOutcome:
        app = self._sm.get_application(application_id)
        if app.uncertain_effect or app.state == ApplicationState.UNCERTAIN:
            raise SubmissionProtocolError("uncertain_submission_requires_reconciliation")

        # Step 3: Action-boundary artifact hash & fact-revision check
        try:
            verified_bytes = self._approvals.verify_at_outbound_boundary(
                approval_id=approval_id,
                file_path=resume_file_path,
                current_fact_revision=current_fact_revision,
            )
        except ArtifactApprovalError as exc:
            raise SubmissionProtocolError(str(exc)) from exc

        attached_sha256 = ats_server.attach_file("el_resume_upload", verified_bytes)

        decision = can_submit(
            approved_hash=app.approved_artifact_sha256,
            actual_hash=attached_sha256,
            consent_current=consent_current,
            cancelled=cancelled,
        )
        if not decision.allowed:
            raise SubmissionProtocolError(f"policy_broker_denied: {decision.reason}")

        # Step 4: Create durable Attempt record before dispatch
        try:
            attempt_id = self._sm.begin_submission_attempt(
                application_id,
                idempotency_key=idempotency_key,
                owner_id=owner_id,
            )
        except ApplicationStateError as exc:
            raise SubmissionProtocolError(str(exc)) from exc

        # Step 5: Dispatch once; recover timeout/crash to UNCERTAIN (never auto-repeat)
        try:
            receipt_id = ats_server.submit_form(candidate_account_id=app.account_id)
        except TimeoutError:
            self._sm.recover_in_flight_after_crash()
            updated = self._sm.get_application(application_id)
            return SubmissionOutcome(
                application_id=application_id,
                attempt_id=attempt_id,
                state=updated.state,
                remote_receipt_id=None,
            )

        verified = self._sm.record_verified_receipt(
            application_id,
            attempt_id=attempt_id,
            remote_receipt_id=receipt_id,
        )
        return SubmissionOutcome(
            application_id=application_id,
            attempt_id=attempt_id,
            state=verified.state,
            remote_receipt_id=verified.remote_receipt_id,
        )
