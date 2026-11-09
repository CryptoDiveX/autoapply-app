"""Unit tests for resume import, style profile extraction, and voice/text interview (P11, P12).

Covers: AA-KB-001..004, AA-DOC-002, NFR-04, C-09, C-11
Scenarios: T-KB-01, T-KB-03, T-KB-04, T-DOC-02
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import pytest

from autoapply.candidate.interview import (
    InterviewError,
    InterviewSession,
    TranscriptionRoute,
)
from autoapply.candidate.store import CandidateStore
from autoapply.documents.importer import (
    ResumeImporter,
    ResumeImportError,
)
from autoapply.documents.style_profile import extract_style_profile


def test_resume_import_preserves_immutable_bytes_hash_and_marks_facts_unconfirmed(
    tmp_path: Path,
) -> None:
    """T-KB-01 / AA-KB-001: Preserve exact original bytes/hash and create unconfirmed extractions."""
    store = CandidateStore(db_path=tmp_path / "candidate.db")
    importer = ResumeImporter(
        storage_dir=tmp_path / "documents",
        candidate_store=store,
        max_file_bytes=5 * 1024 * 1024,
    )

    synthetic_pdf = (
        b"%PDF-1.4\n"
        b"% Synthetic Reference Resume\n"
        b"NAME: Jordan Taylor\n"
        b"EXPERIENCE: Acme Systems | Staff Software Engineer | 2021-03 to 2026-09\n"
        b"EDUCATION: B.S. Computer Science, State University\n"
        b"SKILLS: Python, Swift, Distributed Systems\n"
        b"%%EOF\n"
    )
    expected_sha = hashlib.sha256(synthetic_pdf).hexdigest()

    receipt = importer.import_resume(
        filename="Jordan_Taylor_Resume.pdf",
        raw_bytes=synthetic_pdf,
        effective_from="2026-10-18",
    )

    assert receipt.original_sha256 == expected_sha
    assert receipt.stored_path.read_bytes() == synthetic_pdf
    assert len(receipt.extracted_fact_ids) >= 3

    # Extracted facts must be unconfirmed until explicitly reviewed by the user
    assert store.get_active_confirmed_fact("contact.full_name") is None

    # Poor/scanned OCR input without extractable text does not invent fabricated facts
    blank_scan = b"%PDF-1.4\n% Scanned image only\n%%EOF\n"
    scan_receipt = importer.import_resume(
        filename="Scanned.pdf",
        raw_bytes=blank_scan,
        effective_from="2026-10-18",
    )
    assert scan_receipt.extracted_fact_ids == ()
    assert scan_receipt.requires_manual_entry is True


def test_resume_importer_enforces_size_bounds_and_blocks_external_active_content(
    tmp_path: Path,
) -> None:
    """C-09: Bound file sizes and block active scripts or external resource loading."""
    store = CandidateStore(db_path=tmp_path / "candidate.db")
    importer = ResumeImporter(
        storage_dir=tmp_path / "documents",
        candidate_store=store,
        max_file_bytes=1024,
    )

    # Oversized file rejected
    with pytest.raises(ResumeImportError, match="file_exceeds_max_size"):
        importer.import_resume(
            filename="huge.pdf",
            raw_bytes=b"%PDF-1.4\n" + (b"A" * 2048),
            effective_from="2026-10-18",
        )

    # Active PDF JavaScript / Launch actions rejected
    with pytest.raises(ResumeImportError, match="forbidden_active_or_external_content"):
        importer.import_resume(
            filename="malicious.pdf",
            raw_bytes=b"%PDF-1.4\n/JS (app.launchURL('http://evil.example'))\n%%EOF",
            effective_from="2026-10-18",
        )


def test_style_profile_captures_reference_typography_spacing_and_section_order() -> None:
    """T-DOC-02 / AA-DOC-002 / C-11: Extract deterministic style profile from reference resume."""
    sample_structure = {
        "font_family": "Garamond",
        "heading_scale": 1.35,
        "line_spacing": 1.12,
        "margin_pt": 36,
        "section_order": ["Summary", "Experience", "Education", "Skills"],
        "page_count": 1,
    }
    profile = extract_style_profile(sample_structure)
    assert profile.font_family == "Garamond"
    assert profile.section_order == ("Summary", "Experience", "Education", "Skills")
    assert profile.margin_pt == 36
    assert profile.target_page_count == 1


def test_voice_and_text_interview_handles_mic_denial_consent_and_raw_audio_deletion(
    tmp_path: Path,
) -> None:
    """T-KB-03 / T-KB-04 / AA-KB-003..004 / D-15: Mic denial, transcript correction, and audio cleanup."""
    store = CandidateStore(db_path=tmp_path / "candidate.db")
    audio_staging = tmp_path / "audio_staging"

    # 1. Denied microphone blocks audio recording but permits full typed interview
    session_no_mic = InterviewSession(
        candidate_store=store,
        audio_staging_dir=audio_staging,
        microphone_granted=False,
        cloud_transcription_consented=False,
        retain_raw_audio_after_save=False,
    )
    with pytest.raises(InterviewError, match="microphone_permission_denied"):
        session_no_mic.record_audio_answer(question_id="q_us_auth", raw_audio_bytes=b"RIFF_AUDIO")

    # Typed alternative works seamlessly without microphone
    fact_id = session_no_mic.submit_typed_answer(
        question_id="q_us_auth",
        fact_key="work_authorization",
        category="work_authorization",
        value={"country": "US", "authorized": True, "sponsorship_required": False},
        country="US",
        effective_from="2026-10-18",
    )
    confirmed = store.get_active_confirmed_fact("work_authorization", country="US")
    assert confirmed is not None and confirmed.id == fact_id

    # 2. Cloud transcription without explicit consent fails closed (NFR-04)
    session_with_mic = InterviewSession(
        candidate_store=store,
        audio_staging_dir=audio_staging,
        microphone_granted=True,
        cloud_transcription_consented=False,
        retain_raw_audio_after_save=False,
    )
    recording = session_with_mic.record_audio_answer(
        question_id="q_accomplishment",
        raw_audio_bytes=b"RIFF_SYNTHETIC_VOICE_DATA",
    )
    assert recording.audio_path.exists()

    with pytest.raises(InterviewError, match="cloud_transcription_consent_missing"):
        session_with_mic.transcribe_recording(
            recording,
            route=TranscriptionRoute.CLOUD_CONSENTED,
            raw_transcript="Led migration reducing latency by 40%.",
        )

    # 3. On-device transcription + user transcript edit + save deletes raw audio by default (D-15)
    draft = session_with_mic.transcribe_recording(
        recording,
        route=TranscriptionRoute.ON_DEVICE_LOCAL,
        raw_transcript="Led migration reducing latency by 45 percent.",
    )
    edited_draft = session_with_mic.edit_transcript(
        draft,
        corrected_transcript="Led migration reducing p99 latency by 40% across 12 services.",
    )
    saved_id = session_with_mic.confirm_and_promote_transcript(
        edited_draft,
        fact_key="accomplishment.primary",
        category="employment",
        effective_from="2026-10-18",
    )
    assert store.get_active_confirmed_fact("accomplishment.primary") is not None
    assert saved_id.startswith("fact_")
    # Raw audio file must be deleted after reviewed transcript/facts are saved (D-15)
    assert not recording.audio_path.exists()
