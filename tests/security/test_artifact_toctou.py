"""Security and TOCTOU tests for document approval manifests and action-boundary hash guards (P15).

Covers: AA-DOC-004, NFR-02, C-10, C-11
Scenarios: T-DOC-03, T-DOC-04
"""

from __future__ import annotations

from pathlib import Path
import pytest

from autoapply.documents.approval import (
    ArtifactApprovalError,
    ArtifactApprovalRegistry,
    DocumentOperatingMode,
)


def test_frozen_original_and_tailored_approved_modes_enforce_exact_bytes_at_upload_boundary(
    tmp_path: Path,
) -> None:
    """T-DOC-03 / T-DOC-04: Frozen-original is byte-identical; post-approval file edit revokes upload."""
    registry = ArtifactApprovalRegistry()

    original_file = tmp_path / "original_resume.pdf"
    original_bytes = b"%PDF-1.4\nImmutable Customer Original Resume\n%%EOF\n"
    original_file.write_bytes(original_bytes)

    frozen_manifest = registry.approve_artifact(
        job_id="job_101",
        mode=DocumentOperatingMode.FROZEN_ORIGINAL,
        file_path=original_file,
        fact_revision=3,
        approved_by_user=True,
    )

    # Action-boundary check passes when file bytes and fact revision are unchanged
    verified_bytes = registry.verify_at_outbound_boundary(
        approval_id=frozen_manifest.approval_id,
        file_path=original_file,
        current_fact_revision=3,
    )
    assert verified_bytes == original_bytes

    # TOCTOU attack / post-approval file modification must revoke upload at action boundary
    original_file.write_bytes(b"%PDF-1.4\nTampered Resume Content\n%%EOF\n")
    with pytest.raises(ArtifactApprovalError, match="artifact_changed_at_action_boundary"):
        registry.verify_at_outbound_boundary(
            approval_id=frozen_manifest.approval_id,
            file_path=original_file,
            current_fact_revision=3,
        )


def test_changed_fact_revision_or_missing_human_approval_invalidates_tailored_artifact(
    tmp_path: Path,
) -> None:
    """T-DOC-03 / AA-DOC-003: Model self-approval is rejected; fact revision change invalidates approval."""
    registry = ArtifactApprovalRegistry()
    tailored_file = tmp_path / "tailored_resume.pdf"
    tailored_file.write_bytes(b"%PDF-1.4\nTailored Resume v1\n%%EOF\n")

    # LLM review alone cannot approve a tailored document without user approval/mandate
    with pytest.raises(ArtifactApprovalError, match="human_or_mandate_approval_required"):
        registry.approve_artifact(
            job_id="job_202",
            mode=DocumentOperatingMode.TAILORED_APPROVED,
            file_path=tailored_file,
            fact_revision=5,
            approved_by_user=False,
        )

    manifest = registry.approve_artifact(
        job_id="job_202",
        mode=DocumentOperatingMode.TAILORED_APPROVED,
        file_path=tailored_file,
        fact_revision=5,
        approved_by_user=True,
    )

    # If the user later edits an answer/fact (incrementing fact_revision to 6), prepared approval is revoked
    with pytest.raises(ArtifactApprovalError, match="fact_or_answer_revision_stale"):
        registry.verify_at_outbound_boundary(
            approval_id=manifest.approval_id,
            file_path=tailored_file,
            current_fact_revision=6,
        )
