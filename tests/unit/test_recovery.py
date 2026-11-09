"""Unit tests for durable application state machine, single-owner leases, and crash-to-uncertain recovery (P17).

Covers: AA-JOB-006, AA-JOB-008, AA-TRACK-001, NFR-03, C-10
Scenarios: T-JOB-06, T-JOB-07, T-TRACK-02
"""

from __future__ import annotations

from pathlib import Path
import pytest

from autoapply.engine.state_machine import (
    ApplicationState,
    ApplicationStateError,
    ApplicationStateMachine,
    TrackerSyncState,
)


def test_crash_after_dispatch_recovers_as_uncertain_and_blocks_blind_retry(
    tmp_path: Path,
) -> None:
    """T-JOB-06 / T-JOB-07 / C-10: In-flight submitting attempt recovers to 'uncertain', never safe-to-repeat."""
    sm = ApplicationStateMachine(db_path=tmp_path / "engine.db")
    app_id = sm.create_application(
        job_id="job_501",
        account_id="candidate_1",
        mandate_id="mandate_review_first",
        fact_revision=4,
        approved_artifact_sha256="sha256_approved_v1",
    )

    sm.transition(app_id, ApplicationState.RESERVED)
    sm.transition(app_id, ApplicationState.PREPARING)
    sm.transition(app_id, ApplicationState.AWAITING_DOCUMENT_REVIEW)
    sm.transition(app_id, ApplicationState.READY)
    sm.transition(app_id, ApplicationState.FILLING)
    sm.transition(app_id, ApplicationState.READY_TO_SUBMIT)

    # Record durable Attempt BEFORE outbound dispatch
    attempt_id = sm.begin_submission_attempt(
        app_id,
        idempotency_key="idem_job_501_attempt_1",
        owner_id="submission_owner_1",
    )
    assert sm.get_application(app_id).state == ApplicationState.SUBMITTING

    # Simulate process crash / restart before remote receipt is recorded
    recovered_ids = sm.recover_in_flight_after_crash()
    assert app_id in recovered_ids

    recovered_app = sm.get_application(app_id)
    assert recovered_app.state == ApplicationState.UNCERTAIN
    assert recovered_app.uncertain_effect is True

    # Attempting to blindly re-dispatch a second submission while UNCERTAIN is rejected (C-10)
    with pytest.raises(ApplicationStateError, match="uncertain_submission_requires_reconciliation"):
        sm.begin_submission_attempt(
            app_id,
            idempotency_key="idem_job_501_attempt_2",
            owner_id="submission_owner_1",
        )

    # Reconciling with verified ATS/email receipt transitions UNCERTAIN -> SUBMITTED_VERIFIED
    sm.record_verified_receipt(
        app_id,
        attempt_id=attempt_id,
        remote_receipt_id="greenhouse_conf_8899",
    )
    verified_app = sm.get_application(app_id)
    assert verified_app.state == ApplicationState.SUBMITTED_VERIFIED
    assert verified_app.uncertain_effect is False


def test_orthogonal_tracker_sync_state_never_alters_submission_truth(
    tmp_path: Path,
) -> None:
    """AA-TRACK-001 / T-TRACK-02: Teal sync failure does not revert a verified submission."""
    sm = ApplicationStateMachine(db_path=tmp_path / "engine.db")
    app_id = sm.create_application(
        job_id="job_502",
        account_id="candidate_1",
        mandate_id="mandate_review_first",
        fact_revision=1,
        approved_artifact_sha256="sha256_doc",
    )
    sm.transition(app_id, ApplicationState.RESERVED)
    sm.transition(app_id, ApplicationState.READY_TO_SUBMIT)
    attempt_id = sm.begin_submission_attempt(
        app_id,
        idempotency_key="idem_502",
        owner_id="submission_owner_1",
    )
    sm.record_verified_receipt(
        app_id,
        attempt_id=attempt_id,
        remote_receipt_id="conf_502",
    )

    # Mark Teal tracker sync as FAILED; submission state must remain SUBMITTED_VERIFIED
    sm.update_tracker_sync_state(app_id, TrackerSyncState.FAILED)
    app = sm.get_application(app_id)
    assert app.state == ApplicationState.SUBMITTED_VERIFIED
    assert app.tracker_sync_state == TrackerSyncState.FAILED
