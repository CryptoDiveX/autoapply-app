"""Contract tests for release gates, platform permission boundaries, and TCC isolation (P03).

Covers: AA-AUTH-005, AA-MAIL-001..005, AA-TRACK-001..002, AA-SOC-001..002, AA-UX-004, C-04..C-08, C-10, C-12
Scenarios: T-MAIL-01, T-MAIL-02, T-SOC-01, T-TRACK-01, T-PERM-01, T-PERM-02
"""

from __future__ import annotations

from pathlib import Path
import pytest

from autoapply.policy.feature_gates import (
    AccountEligibilityState,
    FeatureGateEnforcer,
    FeatureGateError,
    MacPermissionKind,
    MacPermissionState,
    MacPermissionMatrix,
)


GATES_JSON = Path(__file__).resolve().parents[2] / "docs" / "release" / "gates.json"


def test_all_initial_gates_are_unapproved_and_block_gated_capabilities() -> None:
    """C-12: Initial gate statuses are unapproved and block gated actions even with login/consent."""
    enforcer = FeatureGateEnforcer.from_gates_file(GATES_JSON)
    assert enforcer.is_gate_approved("G-01") is False
    assert enforcer.is_gate_approved("G-05") is False
    assert enforcer.is_gate_approved("G-07") is False
    assert enforcer.is_gate_approved("G-08") is False


def test_linkedin_automated_reads_polls_and_sends_blocked_when_g08_closed() -> None:
    """C-08 / T-SOC-01: Prohibit automated LinkedIn reads, polls, invitations, and messages without G-08."""
    enforcer = FeatureGateEnforcer.from_gates_file(GATES_JSON)

    for op in (
        "linkedin.read_profile",
        "linkedin.navigate_for_collection",
        "linkedin.poll_connection_status",
        "linkedin.poll_message_replies",
        "linkedin.send_connection_request",
        "linkedin.send_message",
        "linkedin.send_followup",
    ):
        with pytest.raises(FeatureGateError, match="gate_G_08_unapproved"):
            enforcer.authorize_linkedin_operation(
                op,
                session_authenticated=True,
                user_consent_granted=True,
            )

    # Manual user-operated draft generation remains allowed locally
    assert (
        enforcer.authorize_linkedin_operation(
            "linkedin.prepare_local_draft",
            session_authenticated=True,
            user_consent_granted=True,
        )
        is True
    )


def test_google_derived_data_default_denied_to_cloud_llms_until_g05_approved() -> None:
    """C-05 / T-MAIL-01: Default-deny sending any Google-derived mail data to cloud models."""
    enforcer = FeatureGateEnforcer.from_gates_file(GATES_JSON)

    with pytest.raises(FeatureGateError, match="gate_G_05_google_data_to_cloud_llm_denied"):
        enforcer.authorize_gmail_processing(
            destination="cloud_llm_openrouter",
            user_consent_granted=True,
        )

    # Local deterministic header/thread/bounce correlation is allowed while G-05 is closed
    assert (
        enforcer.authorize_gmail_processing(
            destination="local_deterministic_parser",
            user_consent_granted=True,
        )
        is True
    )


def test_gmail_app_password_eligibility_fails_honestly_without_security_weakening() -> None:
    """C-04 / T-MAIL-02: Detect 2SV-disabled, Advanced Protection, and Workspace restrictions."""
    enforcer = FeatureGateEnforcer.from_gates_file(GATES_JSON)

    for ineligible in (
        AccountEligibilityState.TWO_STEP_NOT_ENABLED,
        AccountEligibilityState.ADVANCED_PROTECTION_ENABLED,
        AccountEligibilityState.WORKSPACE_POLICY_DISABLED,
    ):
        with pytest.raises(FeatureGateError, match=ineligible.value):
            enforcer.validate_app_password_eligibility(
                eligibility=ineligible,
                trusted_auth_profile_active=True,
            )

    # Even for an eligible account, app-password capture requires trusted_auth profile (no DOM/extensions)
    with pytest.raises(FeatureGateError, match="untrusted_browser_profile_for_secret_capture"):
        enforcer.validate_app_password_eligibility(
            eligibility=AccountEligibilityState.ELIGIBLE_2SV_ACTIVE,
            trusted_auth_profile_active=False,
        )


def test_teal_tracker_write_requires_exact_identity_and_queues_to_outbox_when_g07_closed() -> None:
    """C-10 / T-TRACK-01 / T-TRACK-02: Never overwrite mismatched records; fallback to local outbox."""
    enforcer = FeatureGateEnforcer.from_gates_file(GATES_JSON)

    # Account or canonical URL mismatch fails immediately
    with pytest.raises(FeatureGateError, match="tracker_record_identity_mismatch"):
        enforcer.evaluate_teal_sync_target(
            expected_account_id="acct_1",
            actual_account_id="acct_2",
            expected_canonical_url="https://jobs.example.com/role-1",
            target_record_canonical_url="https://jobs.example.com/role-1",
        )

    with pytest.raises(FeatureGateError, match="tracker_record_identity_mismatch"):
        enforcer.evaluate_teal_sync_target(
            expected_account_id="acct_1",
            actual_account_id="acct_1",
            expected_canonical_url="https://jobs.example.com/role-1",
            target_record_canonical_url="https://jobs.example.com/sibling-role-2",
        )

    # With matching identity but G-07 unapproved, returns "sync_pending_local_outbox"
    disposition = enforcer.evaluate_teal_sync_target(
        expected_account_id="acct_1",
        actual_account_id="acct_1",
        expected_canonical_url="https://jobs.example.com/role-1",
        target_record_canonical_url="https://jobs.example.com/role-1",
    )
    assert disposition == "sync_pending_local_outbox"


def test_macos_permission_denial_and_revocation_isolate_dependent_features() -> None:
    """T-PERM-01 / T-PERM-02 / AA-UX-004: Denying Microphone or Accessibility does not break core DOM flow."""
    matrix = MacPermissionMatrix()
    matrix.set_state(MacPermissionKind.MICROPHONE, MacPermissionState.DENIED)
    matrix.set_state(MacPermissionKind.ACCESSIBILITY, MacPermissionState.REVOKED)

    # Voice recording is blocked with typed alternative guidance, but typed interview & DOM automation work
    assert matrix.can_record_voice_interview() is False
    assert matrix.can_use_typed_interview() is True
    assert matrix.can_run_owned_browser_dom_automation() is True

    # Unnecessary invasive permissions are never requested
    assert matrix.is_permission_requested_by_product(MacPermissionKind.FULL_DISK_ACCESS) is False
    assert matrix.is_permission_requested_by_product(MacPermissionKind.INPUT_MONITORING) is False
