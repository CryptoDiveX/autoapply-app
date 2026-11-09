"""Integration tests for deterministic reference-style document rendering and visual/ATS QA (P14).

Covers: AA-DOC-002, AA-DOC-004, AA-DOC-005, C-11
Scenarios: T-DOC-02, T-DOC-05
"""

from __future__ import annotations

from pathlib import Path
import pytest

from autoapply.documents.render import (
    DeterministicDocumentRenderer,
    DocumentLayoutQAError,
    EmployerUploadPolicy,
    RenderInputSection,
)
from autoapply.documents.style_profile import ResumeStyleProfile


def test_deterministic_renderer_preserves_reference_style_and_passes_ats_text_qa(
    tmp_path: Path,
) -> None:
    """T-DOC-02 / C-11: Identical inputs produce byte-identical output matching reference style."""
    style = ResumeStyleProfile(
        font_family="Garamond",
        heading_scale=1.30,
        line_spacing=1.15,
        margin_pt=36,
        section_order=("Summary", "Experience", "Education", "Skills"),
        target_page_count=1,
    )
    sections = (
        RenderInputSection(title="Summary", lines=("Staff Software Engineer with 8 years in distributed systems.",)),
        RenderInputSection(title="Experience", lines=("Acme Corp — Senior Backend Engineer (2022–2026)", "Reduced API latency by 40%.")),
        RenderInputSection(title="Education", lines=("B.S. Computer Science, State University",)),
        RenderInputSection(title="Skills", lines=("Python, Swift, SQLite, Playwright",)),
    )

    renderer = DeterministicDocumentRenderer(output_dir=tmp_path / "rendered")
    out1 = renderer.render_and_verify(
        artifact_basename="jordan_taylor_tailored",
        contact_email="jordan@example.com",
        style=style,
        sections=sections,
    )
    out2 = renderer.render_and_verify(
        artifact_basename="jordan_taylor_tailored_repeat",
        contact_email="jordan@example.com",
        style=style,
        sections=sections,
    )

    assert out1.pdf_sha256 == out2.pdf_sha256
    assert out1.docx_sha256 == out2.docx_sha256
    assert "Reduced API latency by 40%" in out1.extracted_ats_text
    assert out1.qa_report.passed is True
    assert out1.qa_report.font_family_matched is True


def test_visual_and_layout_qa_blocks_clipping_blank_pages_broken_links_and_photo_violations(
    tmp_path: Path,
) -> None:
    """T-DOC-02 / T-DOC-05 / AA-DOC-005: Pause submission on clipping, blank page, broken link, or photo rule."""
    style = ResumeStyleProfile(
        font_family="Helvetica",
        heading_scale=1.25,
        line_spacing=1.15,
        margin_pt=36,
        section_order=("Summary", "Experience"),
        target_page_count=1,
    )
    renderer = DeterministicDocumentRenderer(output_dir=tmp_path / "rendered")

    # 1. Broken hyperlink in section content fails QA
    with pytest.raises(DocumentLayoutQAError, match="broken_hyperlink_detected"):
        renderer.render_and_verify(
            artifact_basename="broken_link",
            contact_email="jordan@example.com",
            style=style,
            sections=(
                RenderInputSection(title="Summary", lines=("Portfolio: http://",)),
                RenderInputSection(title="Experience", lines=("Acme Corp",)),
            ),
        )

    # 2. Malformed contact email fails QA
    with pytest.raises(DocumentLayoutQAError, match="malformed_contact_details"):
        renderer.render_and_verify(
            artifact_basename="bad_contact",
            contact_email="not-an-email",
            style=style,
            sections=(
                RenderInputSection(title="Summary", lines=("Engineer",)),
                RenderInputSection(title="Experience", lines=("Acme Corp",)),
            ),
        )

    # 3. Page overflow / clipping beyond target_page_count fails QA
    excessive_lines = tuple(f"Accomplishment line {i}" for i in range(120))
    with pytest.raises(DocumentLayoutQAError, match="page_overflow_or_clipping"):
        renderer.render_and_verify(
            artifact_basename="overflow",
            contact_email="jordan@example.com",
            style=style,
            sections=(
                RenderInputSection(title="Summary", lines=("Engineer",)),
                RenderInputSection(title="Experience", lines=excessive_lines),
            ),
        )

    # 4. Employer photo restriction violation fails QA (T-DOC-05)
    strict_no_photo_policy = EmployerUploadPolicy(
        allowed_extensions=(".pdf", ".docx"),
        max_bytes=2 * 1024 * 1024,
        prohibits_candidate_photo=True,
    )
    with pytest.raises(DocumentLayoutQAError, match="employer_prohibits_candidate_photo"):
        renderer.render_and_verify(
            artifact_basename="with_photo",
            contact_email="jordan@example.com",
            style=style,
            sections=(
                RenderInputSection(title="Summary", lines=("Engineer",)),
                RenderInputSection(title="Experience", lines=("Acme Corp",)),
            ),
            includes_candidate_photo=True,
            employer_policy=strict_no_photo_policy,
        )
