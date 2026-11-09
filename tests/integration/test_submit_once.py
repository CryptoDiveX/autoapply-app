"""Integration tests for committed field readback, background/takeover handoff, and submit-once protocol (P18, P19, P20).

Covers: AA-JOB-004..008, AA-UX-001..003, NFR-03, C-10
Scenarios: T-JOB-03, T-JOB-04, T-JOB-05, T-JOB-06, T-JOB-07, T-UX-01, T-UX-02
"""

from __future__ import annotations

from pathlib import Path
import pytest

from autoapply.browser.fields import (
    BrowserFieldCommitter,
    FieldVerificationError,
)
from autoapply.browser.session import (
    BrowserExecutionSession,
    TakeoverPauseError,
    VisibilitySetting,
)
from autoapply.documents.approval import (
    ArtifactApprovalRegistry,
    DocumentOperatingMode,
)
from autoapply.engine.dedupe import EmployerDedupeLedger
from autoapply.engine.reconcile import SubmissionReconciler
from autoapply.engine.state_machine import (
    ApplicationState,
    ApplicationStateMachine,
)
from autoapply.engine.submit import (
    SubmissionCoordinator,
    SubmissionProtocolError,
)
from tests.fixtures.ats.fixture_server import SyntheticATSFormServer


def test_committed_field_verification_rejects_uncommitted_clicks_and_reads_back_values() -> None:
    """T-JOB-03 / AA-JOB-004: Click return alone is insufficient; verify committed DOM value."""
    ats = SyntheticATSFormServer.default_form()
    committer = BrowserFieldCommitter(ats)

    # Naive click without committing value fails verification
    ats.click_without_committing("el_full_name")
    with pytest.raises(FieldVerificationError, match="field_value_not_committed"):
        committer.verify_field_committed("el_full_name", expected_value="Jordan Taylor")

    # Committing controlled text, radio, dropdown, and iframe fields verifies via readback
    committer.fill_and_verify("el_full_name", "Jordan Taylor")
    committer.fill_and_verify("el_work_auth_ca", "Yes")
    committer.fill_and_verify("el_sponsorship_ca", "No")
    committer.fill_and_verify("el_iframe_eeo", "Decline to self-identify")


def test_background_visibility_never_touches_desktop_and_takeover_forces_revalidation() -> None:
    """T-UX-01 / T-UX-02 / AA-UX-002: Background mode preserves focus/cursor; takeover re-reads form."""
    ats = SyntheticATSFormServer.default_form()
    session = BrowserExecutionSession(
        session_id="sess_owned_01",
        ats_server=ats,
        visibility=VisibilitySetting.BACKGROUND,
    )

    assert session.physical_cursor_moved is False
    assert session.mac_focus_stolen is False

    # If a desktop-level or MFA challenge occurs in background mode, pause for takeover (never steal focus)
    with pytest.raises(TakeoverPauseError, match="desktop_or_security_handoff_required"):
        session.request_desktop_or_security_step(reason="mfa_challenge_detected")
    assert session.physical_cursor_moved is False
    assert session.mac_focus_stolen is False

    # Switching to VISIBLE_BROWSER keeps the exact same session_id
    session.switch_visibility(VisibilitySetting.VISIBLE_BROWSER)
    assert session.session_id == "sess_owned_01"

    # Entering takeover holds a lease and records user manual edits; resuming forces form re-read
    session.begin_user_takeover(reason="user_clicked_take_over")
    ats.commit_field_value("el_full_name", "Jordan A. Taylor")
    revalidated = session.resume_from_takeover()
    assert revalidated.form_snapshot["el_full_name"] == "Jordan A. Taylor"
    assert revalidated.requires_fresh_approval is True


def test_submit_once_protocol_handles_timeout_crash_recovery_without_duplicate_submission(
    tmp_path: Path,
) -> None:
    """T-JOB-06 / T-JOB-07 / C-10: Network timeout after server accept reconciles without 2nd submit."""
    ats = SyntheticATSFormServer.default_form()
    committer = BrowserFieldCommitter(ats)
    committer.fill_and_verify("el_full_name", "Jordan Taylor")
    committer.fill_and_verify("el_work_auth_ca", "Yes")
    committer.fill_and_verify("el_sponsorship_ca", "No")

    resume_path = tmp_path / "approved_resume.pdf"
    resume_bytes = b"%PDF-1.4\nApproved Resume Jordan Taylor\n%%EOF\n"
    resume_path.write_bytes(resume_bytes)

    approvals = ArtifactApprovalRegistry()
    manifest = approvals.approve_artifact(
        job_id="job_4002",
        mode=DocumentOperatingMode.FROZEN_ORIGINAL,
        file_path=resume_path,
        fact_revision=1,
        approved_by_user=True,
    )

    dedupe = EmployerDedupeLedger(db_path=tmp_path / "dedupe.db")
    sm = ApplicationStateMachine(db_path=tmp_path / "state.db")
    coordinator = SubmissionCoordinator(
        state_machine=sm,
        dedupe_ledger=dedupe,
        approval_registry=approvals,
    )

    app_id = coordinator.prepare_application_for_submit(
        job_id="job_4002",
        direct_employer_id="acme_corp",
        canonical_role_id="gh_4002",
        canonical_url="https://boards.greenhouse.io/acme/jobs/4002",
        account_id="cand_01",
        mandate_id="mandate_review_first",
        fact_revision=1,
        approval_id=manifest.approval_id,
        owner_id="worker_1",
        now_epoch_seconds=1_760_812_000,
    )

    # Simulate network timeout AFTER the ATS server recorded the submission
    ats.simulate_network_timeout_after_accept = True
    outcome = coordinator.execute_submit_once(
        application_id=app_id,
        ats_server=ats,
        approval_id=manifest.approval_id,
        resume_file_path=resume_path,
        current_fact_revision=1,
        idempotency_key="idem_job_4002_v1",
        owner_id="worker_1",
        consent_current=True,
        cancelled=False,
    )

    # Must recover to UNCERTAIN rather than claiming success or blindly retrying
    assert outcome.state == ApplicationState.UNCERTAIN
    assert len(ats.submissions_by_role) == 1

    # Attempting to call execute_submit_once again while UNCERTAIN is blocked (no 2nd submission!)
    with pytest.raises(SubmissionProtocolError, match="uncertain_submission_requires_reconciliation"):
        coordinator.execute_submit_once(
            application_id=app_id,
            ats_server=ats,
            approval_id=manifest.approval_id,
            resume_file_path=resume_path,
            current_fact_revision=1,
            idempotency_key="idem_job_4002_v2",
            owner_id="worker_1",
            consent_current=True,
            cancelled=False,
        )
    assert len(ats.submissions_by_role) == 1

    # Reconciler checks ATS confirmation receipt and transitions UNCERTAIN -> SUBMITTED_VERIFIED
    reconciler = SubmissionReconciler(state_machine=sm)
    reconciled = reconciler.reconcile_uncertain_application(
        application_id=app_id,
        attempt_id=outcome.attempt_id,
        ats_server=ats,
        canonical_role_id="gh_4002",
    )
    assert reconciled.state == ApplicationState.SUBMITTED_VERIFIED
    assert reconciled.remote_receipt_id is not None
    assert len(ats.submissions_by_role) == 1
