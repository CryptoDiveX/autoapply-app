"""Immutable artifact approval manifests and action-boundary SHA-256 TOCTOU guard (P15).

Enforces AA-DOC-004, NFR-02, C-10, C-11:
- Supports both `frozen_original` and `tailored_approved` modes.
- Rejects LLM self-approval: requires explicit user or saved mandate approval.
- Re-hashes the file on disk and checks fact/answer revision immediately inside the
  actual upload/send path to prevent TOCTOU tampering or stale submissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from pathlib import Path
import uuid


class ArtifactApprovalError(RuntimeError):
    """Raised when an artifact lacks approval, has been modified on disk, or references stale facts."""


class DocumentOperatingMode(str, Enum):
    """Supported document operating modes (AA-DOC-004, D-13)."""

    FROZEN_ORIGINAL = "frozen_original"
    TAILORED_APPROVED = "tailored_approved"


@dataclass(frozen=True)
class ArtifactApprovalManifest:
    """Immutable approval record binding a job, document mode, SHA-256 hash, and fact revision."""

    approval_id: str
    job_id: str
    mode: DocumentOperatingMode
    approved_sha256: str
    fact_revision: int


class ArtifactApprovalRegistry:
    """Tracks approved artifact manifests and enforces action-boundary hash verification."""

    def __init__(self) -> None:
        self._manifests: dict[str, ArtifactApprovalManifest] = {}

    def approve_artifact(
        self,
        *,
        job_id: str,
        mode: DocumentOperatingMode,
        file_path: Path,
        fact_revision: int,
        approved_by_user: bool,
    ) -> ArtifactApprovalManifest:
        if not approved_by_user:
            raise ArtifactApprovalError(
                "human_or_mandate_approval_required: model self-review does not approve an artifact"
            )
        if not file_path.exists():
            raise ArtifactApprovalError(f"artifact_file_missing: {file_path}")

        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        manifest = ArtifactApprovalManifest(
            approval_id=f"appr_{uuid.uuid4().hex[:12]}",
            job_id=job_id,
            mode=mode,
            approved_sha256=digest,
            fact_revision=fact_revision,
        )
        self._manifests[manifest.approval_id] = manifest
        return manifest

    def verify_at_outbound_boundary(
        self,
        *,
        approval_id: str,
        file_path: Path,
        current_fact_revision: int,
    ) -> bytes:
        manifest = self._manifests.get(approval_id)
        if manifest is None:
            raise ArtifactApprovalError(f"unknown_approval_id: {approval_id}")

        if current_fact_revision != manifest.fact_revision:
            raise ArtifactApprovalError(
                f"fact_or_answer_revision_stale: approved at rev {manifest.fact_revision}, "
                f"current rev is {current_fact_revision}"
            )

        if not file_path.exists():
            raise ArtifactApprovalError(f"artifact_file_missing_at_boundary: {file_path}")

        actual_bytes = file_path.read_bytes()
        actual_sha256 = hashlib.sha256(actual_bytes).hexdigest()
        if actual_sha256 != manifest.approved_sha256:
            raise ArtifactApprovalError(
                "artifact_changed_at_action_boundary: SHA-256 mismatch between approval and upload"
            )

        return actual_bytes
