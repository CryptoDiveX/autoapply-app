"""Versioned JSON IPC protocol dispatcher, HMAC caller auth, and emergency-stop cancellation (P08).

Enforces 02-TECHNICAL-SPECIFICATION.md (§5), AA-UX-003, NFR-02, NFR-05, C-06:
- Validates Protocol v1 envelopes and rejects unknown top-level fields.
- Verifies per-session HMAC-SHA256 caller authentication (`T-SEC-04`).
- Enforces mandatory commit-boundary fields (`expected_revision`, `idempotency_key`, `deadline_ms`).
- Blocks unknown privileged operations and secret-bearing payload keys (`password`, `otp`, `private_key`).
- Propagates emergency-stop cancellation (`T-UX-03`) so no subsequent proposal passes the gate.
"""

from __future__ import annotations

from enum import Enum
import hashlib
import hmac
import json
from typing import Any


ALLOWED_ENVELOPE_FIELDS: frozenset[str] = frozenset(
    {
        "protocol_version",
        "request_id",
        "run_id",
        "job_id",
        "type",
        "operation",
        "expected_revision",
        "idempotency_key",
        "deadline_ms",
        "caller_id",
        "auth_tag",
        "payload",
    }
)

PRIVILEGED_OPERATIONS: frozenset[str] = frozenset(
    {
        "application.submit",
        "browser.fill_approved_field",
        "browser.attach_approved_artifact",
        "gmail.send_approved_reply",
        "tracker.sync_verified_record",
    }
)

NON_PRIVILEGED_OPERATIONS: frozenset[str] = frozenset(
    {
        "runtime.ping",
        "job.progress",
        "run.emergency_stop",
        "human.request_takeover",
    }
)

FORBIDDEN_SECRET_KEYS_IN_IPC: frozenset[str] = frozenset(
    {
        "password",
        "app_password",
        "otp",
        "otp_code",
        "mfa_code",
        "raw_auth_token",
        "age_private_key",
        "private_key",
    }
)


class IPCProtocolError(RuntimeError):
    """Raised when an IPC message violates protocol version, schema, auth, or cancellation rules."""


class MessageType(str, Enum):
    """Required IPC message classes from 02-TECHNICAL-SPECIFICATION.md (§5)."""

    COMMAND = "command"
    PROPOSAL = "proposal"
    APPROVAL_REQUEST = "approval_request"
    USER_DECISION = "user_decision"
    PROGRESS = "progress"
    HEALTH = "health"
    HEARTBEAT = "heartbeat"
    CANCELLATION = "cancellation"
    RESULT = "result"
    EVIDENCE_REFERENCE = "evidence_reference"
    RECOVERABLE_ERROR = "recoverable_error"
    FATAL_ERROR = "fatal_error"


def compute_ipc_auth_tag(
    *,
    session_secret: bytes,
    request_id: str,
    run_id: str,
    msg_type: str,
    operation: str,
    caller_id: str,
) -> str:
    canonical = f"{request_id}|{run_id}|{msg_type}|{operation}|{caller_id}".encode("utf-8")
    return hmac.new(session_secret, canonical, hashlib.sha256).hexdigest()


def build_signed_envelope(
    *,
    session_secret: bytes,
    protocol_version: int,
    request_id: str,
    run_id: str,
    job_id: str | None,
    msg_type: MessageType,
    operation: str,
    caller_id: str,
    payload: dict[str, Any],
    expected_revision: int | None = None,
    idempotency_key: str | None = None,
    deadline_ms: int | None = None,
) -> str:
    auth_tag = compute_ipc_auth_tag(
        session_secret=session_secret,
        request_id=request_id,
        run_id=run_id,
        msg_type=msg_type.value,
        operation=operation,
        caller_id=caller_id,
    )
    envelope: dict[str, Any] = {
        "protocol_version": protocol_version,
        "request_id": request_id,
        "run_id": run_id,
        "job_id": job_id,
        "type": msg_type.value,
        "operation": operation,
        "caller_id": caller_id,
        "auth_tag": auth_tag,
        "payload": payload,
    }
    if expected_revision is not None:
        envelope["expected_revision"] = expected_revision
    if idempotency_key is not None:
        envelope["idempotency_key"] = idempotency_key
    if deadline_ms is not None:
        envelope["deadline_ms"] = deadline_ms
    return json.dumps(envelope, sort_keys=True)


class IPCDispatcher:
    """Validates and dispatches versioned IPC messages with cancellation enforcement."""

    def __init__(self, *, session_secret: bytes) -> None:
        self._session_secret = bytes(session_secret)
        self._cancelled_runs: set[str] = set()

    def handle_raw_message(self, raw_json: str) -> dict[str, Any]:
        try:
            msg = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise IPCProtocolError(f"malformed_ipc_json: {exc}") from exc

        if not isinstance(msg, dict):
            raise IPCProtocolError("ipc_envelope_must_be_object")

        unknown_top = set(msg.keys()) - ALLOWED_ENVELOPE_FIELDS
        if unknown_top:
            raise IPCProtocolError(f"unknown_envelope_fields: {sorted(unknown_top)}")

        if msg.get("protocol_version") != 1:
            raise IPCProtocolError(
                f"unsupported_protocol_version: {msg.get('protocol_version')!r}"
            )

        request_id = str(msg.get("request_id", ""))
        run_id = str(msg.get("run_id", ""))
        msg_type_str = str(msg.get("type", ""))
        operation = str(msg.get("operation", ""))
        caller_id = str(msg.get("caller_id", ""))
        provided_tag = str(msg.get("auth_tag", ""))

        expected_tag = compute_ipc_auth_tag(
            session_secret=self._session_secret,
            request_id=request_id,
            run_id=run_id,
            msg_type=msg_type_str,
            operation=operation,
            caller_id=caller_id,
        )
        if not hmac.compare_digest(provided_tag, expected_tag):
            raise IPCProtocolError("unauthenticated_ipc_caller")

        payload = msg.get("payload")
        if not isinstance(payload, dict):
            raise IPCProtocolError("ipc_payload_must_be_object")

        # Never permit passwords, OTPs, raw tokens, or private keys in IPC payloads
        for key, val in payload.items():
            if key.lower() in FORBIDDEN_SECRET_KEYS_IN_IPC:
                raise IPCProtocolError(f"forbidden_secret_field_in_ipc: {key}")
            if isinstance(val, str) and "AGE-SECRET-KEY-" in val:
                raise IPCProtocolError("forbidden_secret_field_in_ipc: age_private_key_pattern")

        if msg_type_str == MessageType.CANCELLATION.value:
            self._cancelled_runs.add(run_id)
            return {
                "protocol_version": 1,
                "request_id": request_id,
                "run_id": run_id,
                "type": MessageType.RESULT.value,
                "operation": operation,
                "payload": {"cancelled": True, "run_id": run_id},
            }

        if run_id in self._cancelled_runs:
            raise IPCProtocolError(f"run_cancelled_gate_closed: {run_id}")

        if msg_type_str in (MessageType.PROPOSAL.value, MessageType.COMMAND.value):
            if operation not in PRIVILEGED_OPERATIONS:
                raise IPCProtocolError(f"unknown_privileged_operation: {operation}")
            if (
                msg.get("expected_revision") is None
                or not msg.get("idempotency_key")
                or not msg.get("deadline_ms")
            ):
                raise IPCProtocolError(
                    "missing_commit_boundary_fields: expected_revision, idempotency_key, and deadline_ms are required"
                )

            return {
                "protocol_version": 1,
                "request_id": request_id,
                "run_id": run_id,
                "type": MessageType.RESULT.value,
                "operation": operation,
                "payload": {
                    "status": "proposal_received_pending_policy_broker",
                    "idempotency_key": msg["idempotency_key"],
                },
            }

        if operation not in NON_PRIVILEGED_OPERATIONS and operation not in PRIVILEGED_OPERATIONS:
            raise IPCProtocolError(f"unknown_operation: {operation}")

        return {
            "protocol_version": 1,
            "request_id": request_id,
            "run_id": run_id,
            "type": MessageType.RESULT.value,
            "operation": operation,
            "payload": {"status": "ok"},
        }
