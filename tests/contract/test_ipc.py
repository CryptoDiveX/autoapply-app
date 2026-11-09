"""Contract tests for versioned JSON IPC envelopes, authentication, and emergency stop (P08).

Covers: AA-UX-003, NFR-02, NFR-05, C-06
Scenarios: T-SEC-04, T-UX-03
"""

from __future__ import annotations

import pytest

from autoapply.ipc.protocol import (
    IPCDispatcher,
    IPCProtocolError,
    MessageType,
    build_signed_envelope,
)


SESSION_SECRET = b"ipc-session-secret-key-32-bytes!"


def test_valid_proposal_round_trip_and_commit_boundary_fields() -> None:
    """P08: Valid protocol v1 proposal round-trips and returns a structured result."""
    dispatcher = IPCDispatcher(session_secret=SESSION_SECRET)

    raw_msg = build_signed_envelope(
        session_secret=SESSION_SECRET,
        protocol_version=1,
        request_id="req_01",
        run_id="run_01",
        job_id="job_01",
        msg_type=MessageType.PROPOSAL,
        operation="application.submit",
        caller_id="worker_main",
        expected_revision=7,
        idempotency_key="idem_submit_job_01_v7",
        deadline_ms=5000,
        payload={"application_id": "app_01", "approval_id": "appr_01"},
    )

    response = dispatcher.handle_raw_message(raw_msg)
    assert response["protocol_version"] == 1
    assert response["request_id"] == "req_01"
    assert response["type"] == MessageType.RESULT.value
    assert response["payload"]["status"] == "proposal_received_pending_policy_broker"


def test_rejects_invalid_protocol_version_unknown_fields_and_unauthenticated_callers() -> None:
    """T-SEC-04: Reject wrong protocol version, forged auth tag, or unknown top-level/payload fields."""
    dispatcher = IPCDispatcher(session_secret=SESSION_SECRET)

    # 1. Wrong protocol version
    bad_ver = build_signed_envelope(
        session_secret=SESSION_SECRET,
        protocol_version=2,
        request_id="req_bad_v",
        run_id="run_01",
        job_id="job_01",
        msg_type=MessageType.HEALTH,
        operation="runtime.ping",
        caller_id="supervisor",
        payload={},
    )
    with pytest.raises(IPCProtocolError, match="unsupported_protocol_version"):
        dispatcher.handle_raw_message(bad_ver)

    # 2. Unauthenticated caller (wrong session secret)
    forged = build_signed_envelope(
        session_secret=b"wrong-unauthenticated-local-key!",
        protocol_version=1,
        request_id="req_forged",
        run_id="run_01",
        job_id="job_01",
        msg_type=MessageType.PROPOSAL,
        operation="application.submit",
        caller_id="rogue_local_process",
        expected_revision=1,
        idempotency_key="idem_1",
        deadline_ms=1000,
        payload={"application_id": "app_01", "approval_id": "appr_01"},
    )
    with pytest.raises(IPCProtocolError, match="unauthenticated_ipc_caller"):
        dispatcher.handle_raw_message(forged)

    # 3. Missing mandatory commit-boundary fields (idempotency_key / expected_revision / deadline_ms)
    missing_commit_fields = build_signed_envelope(
        session_secret=SESSION_SECRET,
        protocol_version=1,
        request_id="req_no_idem",
        run_id="run_01",
        job_id="job_01",
        msg_type=MessageType.PROPOSAL,
        operation="application.submit",
        caller_id="worker_main",
        payload={"application_id": "app_01", "approval_id": "appr_01"},
    )
    with pytest.raises(IPCProtocolError, match="missing_commit_boundary_fields"):
        dispatcher.handle_raw_message(missing_commit_fields)

    # 4. Unknown privileged operation
    unknown_op = build_signed_envelope(
        session_secret=SESSION_SECRET,
        protocol_version=1,
        request_id="req_unknown_op",
        run_id="run_01",
        job_id="job_01",
        msg_type=MessageType.PROPOSAL,
        operation="shell.exec_arbitrary",
        caller_id="worker_main",
        expected_revision=1,
        idempotency_key="idem_2",
        deadline_ms=1000,
        payload={},
    )
    with pytest.raises(IPCProtocolError, match="unknown_privileged_operation"):
        dispatcher.handle_raw_message(unknown_op)


def test_rejects_secrets_or_private_keys_inside_ipc_payload() -> None:
    """02-TECHNICAL-SPECIFICATION.md (§5): Never include passwords, OTPs, or age private keys in IPC."""
    dispatcher = IPCDispatcher(session_secret=SESSION_SECRET)

    leaked_msg = build_signed_envelope(
        session_secret=SESSION_SECRET,
        protocol_version=1,
        request_id="req_secret_leak",
        run_id="run_01",
        job_id="job_01",
        msg_type=MessageType.PROGRESS,
        operation="job.progress",
        caller_id="worker_main",
        payload={"step": "filling", "otp_code": "123456"},
    )
    with pytest.raises(IPCProtocolError, match="forbidden_secret_field_in_ipc"):
        dispatcher.handle_raw_message(leaked_msg)


def test_emergency_stop_cancellation_blocks_all_subsequent_proposals() -> None:
    """T-UX-03 / NFR-05: Emergency stop acknowledges immediately and blocks new tool proposals."""
    dispatcher = IPCDispatcher(session_secret=SESSION_SECRET)

    cancel_msg = build_signed_envelope(
        session_secret=SESSION_SECRET,
        protocol_version=1,
        request_id="req_cancel_1",
        run_id="run_99",
        job_id="job_99",
        msg_type=MessageType.CANCELLATION,
        operation="run.emergency_stop",
        caller_id="supervisor",
        payload={"reason": "user_clicked_emergency_stop"},
    )
    ack = dispatcher.handle_raw_message(cancel_msg)
    assert ack["type"] == MessageType.RESULT.value
    assert ack["payload"]["cancelled"] is True

    # Any subsequent proposal on run_99 must be rejected at the IPC gate
    after_cancel = build_signed_envelope(
        session_secret=SESSION_SECRET,
        protocol_version=1,
        request_id="req_after_cancel",
        run_id="run_99",
        job_id="job_99",
        msg_type=MessageType.PROPOSAL,
        operation="application.submit",
        caller_id="worker_main",
        expected_revision=1,
        idempotency_key="idem_after_cancel",
        deadline_ms=1000,
        payload={"application_id": "app_99", "approval_id": "appr_99"},
    )
    with pytest.raises(IPCProtocolError, match="run_cancelled_gate_closed"):
        dispatcher.handle_raw_message(after_cancel)
