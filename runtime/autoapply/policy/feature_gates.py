"""Release gate enforcement, platform permission boundaries, and macOS TCC matrix (P03).

Enforces AA-AUTH-005, AA-MAIL-001..005, AA-TRACK-001..002, AA-SOC-001..002, AA-UX-004,
C-04, C-05, C-06, C-07, C-08, C-10, C-12:
- Reads docs/release/gates.json and denies unapproved vendor/platform operations.
- Hard-blocks all automated LinkedIn reads, polls, invitations, and messages while G-08 is closed.
- Default-denies sending Google-derived data to cloud LLMs while G-05 is closed.
- Enforces honest Gmail App-Password account eligibility and trusted_auth profile boundary.
- Enforces exact Teal record identity matching and falls back to sync_pending_local_outbox when G-07 is closed.
- Models individual macOS TCC permissions without requesting Full Disk Access or Input Monitoring.
"""

from __future__ import annotations

from enum import Enum
import json
from pathlib import Path
from typing import Any


AUTOMATED_LINKEDIN_OPERATIONS: frozenset[str] = frozenset(
    {
        "linkedin.read_profile",
        "linkedin.navigate_for_collection",
        "linkedin.poll_connection_status",
        "linkedin.poll_message_replies",
        "linkedin.send_connection_request",
        "linkedin.send_message",
        "linkedin.send_followup",
    }
)

MANUAL_LINKEDIN_OPERATIONS: frozenset[str] = frozenset(
    {
        "linkedin.prepare_local_draft",
        "linkedin.schedule_local_reminder",
        "linkedin.open_user_handoff_tab",
    }
)


class FeatureGateError(RuntimeError):
    """Raised when a requested operation violates an unapproved release or security gate."""


class AccountEligibilityState(str, Enum):
    """Google account eligibility states for guided app-password creation (AA-MAIL-002, C-04)."""

    ELIGIBLE_2SV_ACTIVE = "eligible_2sv_active"
    TWO_STEP_NOT_ENABLED = "two_step_not_enabled"
    ADVANCED_PROTECTION_ENABLED = "advanced_protection_enabled"
    WORKSPACE_POLICY_DISABLED = "workspace_policy_disabled"


class MacPermissionKind(str, Enum):
    """macOS TCC permission capabilities (AA-UX-004, O-08)."""

    MICROPHONE = "microphone"
    ACCESSIBILITY = "accessibility"
    SCREEN_RECORDING = "screen_recording"
    AUTOMATION = "automation"
    INPUT_MONITORING = "input_monitoring"
    FULL_DISK_ACCESS = "full_disk_access"


class MacPermissionState(str, Enum):
    """States for macOS permission onboarding (O-08)."""

    NOT_NEEDED = "not_needed"
    NOT_REQUESTED = "not_requested"
    AWAITING_USER = "awaiting_user"
    GRANTED = "granted"
    DENIED = "denied"
    REVOKED = "revoked"


class FeatureGateEnforcer:
    """Enforces release gates (G-01..G-09) outside LLM discretion."""

    def __init__(self, gates_by_id: dict[str, dict[str, Any]]) -> None:
        self._gates = dict(gates_by_id)

    @classmethod
    def from_gates_file(cls, gates_path: Path) -> FeatureGateEnforcer:
        raw = json.loads(gates_path.read_text(encoding="utf-8"))
        by_id = {entry["id"]: entry for entry in raw.get("gates", [])}
        return cls(by_id)

    def is_gate_approved(self, gate_id: str) -> bool:
        gate = self._gates.get(gate_id)
        if gate is None:
            return False
        return gate.get("status") == "approved" and bool(gate.get("approval_artifact"))

    def authorize_linkedin_operation(
        self,
        operation: str,
        *,
        session_authenticated: bool,
        user_consent_granted: bool,
    ) -> bool:
        if not user_consent_granted:
            raise FeatureGateError("linkedin_user_consent_missing")
        if operation in MANUAL_LINKEDIN_OPERATIONS:
            return True
        if operation in AUTOMATED_LINKEDIN_OPERATIONS:
            if not self.is_gate_approved("G-08"):
                raise FeatureGateError(
                    f"gate_G_08_unapproved: automated LinkedIn operation '{operation}' "
                    "is prohibited without platform approval (even with session login and user consent)"
                )
            if not session_authenticated:
                raise FeatureGateError("linkedin_session_not_authenticated")
            return True
        raise FeatureGateError(f"unknown_linkedin_operation: {operation}")

    def authorize_gmail_processing(
        self,
        *,
        destination: str,
        user_consent_granted: bool,
    ) -> bool:
        if not user_consent_granted:
            raise FeatureGateError("gmail_user_consent_missing")
        if destination == "local_deterministic_parser":
            return True
        if not self.is_gate_approved("G-05"):
            raise FeatureGateError(
                "gate_G_05_google_data_to_cloud_llm_denied: Google-derived mail data "
                "cannot be transmitted to cloud models until G-05 verification and processor "
                "approval are complete"
            )
        return True

    def validate_app_password_eligibility(
        self,
        *,
        eligibility: AccountEligibilityState,
        trusted_auth_profile_active: bool,
    ) -> bool:
        if eligibility != AccountEligibilityState.ELIGIBLE_2SV_ACTIVE:
            raise FeatureGateError(
                f"gmail_app_password_ineligible: {eligibility.value}"
            )
        if not trusted_auth_profile_active:
            raise FeatureGateError(
                "untrusted_browser_profile_for_secret_capture: app-password capture requires "
                "auth_trusted profile with agent DOM, screenshots, and extensions suppressed"
            )
        return True

    def evaluate_teal_sync_target(
        self,
        *,
        expected_account_id: str,
        actual_account_id: str,
        expected_canonical_url: str,
        target_record_canonical_url: str,
    ) -> str:
        if (
            expected_account_id != actual_account_id
            or expected_canonical_url != target_record_canonical_url
        ):
            raise FeatureGateError(
                "tracker_record_identity_mismatch: account or canonical job URL does not match target Teal record"
            )
        if not self.is_gate_approved("G-07"):
            return "sync_pending_local_outbox"
        return "remote_write_authorized"


class MacPermissionMatrix:
    """Tracks per-capability macOS TCC states and isolates denied/revoked permissions."""

    REQUESTED_CAPABILITIES: frozenset[MacPermissionKind] = frozenset(
        {
            MacPermissionKind.MICROPHONE,
            MacPermissionKind.ACCESSIBILITY,
            MacPermissionKind.SCREEN_RECORDING,
            MacPermissionKind.AUTOMATION,
        }
    )

    def __init__(self) -> None:
        self._states: dict[MacPermissionKind, MacPermissionState] = {
            kind: (
                MacPermissionState.NOT_REQUESTED
                if kind in self.REQUESTED_CAPABILITIES
                else MacPermissionState.NOT_NEEDED
            )
            for kind in MacPermissionKind
        }

    def set_state(self, kind: MacPermissionKind, state: MacPermissionState) -> None:
        self._states[kind] = state

    def get_state(self, kind: MacPermissionKind) -> MacPermissionState:
        return self._states[kind]

    def is_permission_requested_by_product(self, kind: MacPermissionKind) -> bool:
        return kind in self.REQUESTED_CAPABILITIES

    def can_record_voice_interview(self) -> bool:
        return self._states[MacPermissionKind.MICROPHONE] == MacPermissionState.GRANTED

    def can_use_typed_interview(self) -> bool:
        return True

    def can_run_owned_browser_dom_automation(self) -> bool:
        return True
