"""Guided voice and text candidate self-interview with consent and audio retention controls (P12).

Enforces AA-KB-003, AA-KB-004, NFR-04, D-15:
- Requires explicit microphone permission before recording audio; always offers typed alternative.
- Requires explicit cloud transcription consent before using a cloud transcription route.
- Shows editable transcript for user correction before promoting facts to CandidateStore.
- Deletes raw audio automatically upon saving reviewed transcript/facts unless retention is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
import uuid

from autoapply.candidate.store import (
    CandidateFactInput,
    CandidateStore,
    FactScope,
    ScopeLevel,
)


class InterviewError(RuntimeError):
    """Raised when microphone permission or cloud transcription consent is missing."""


class TranscriptionRoute(str, Enum):
    """Supported transcription routes (AA-KB-003, D-15)."""

    ON_DEVICE_LOCAL = "on_device_local"
    CLOUD_CONSENTED = "cloud_consented"


@dataclass(frozen=True)
class AudioRecording:
    """Staged raw audio recording awaiting transcription and review."""

    recording_id: str
    question_id: str
    audio_path: Path


@dataclass(frozen=True)
class TranscriptDraft:
    """Transcribed answer awaiting user correction and confirmation."""

    recording: AudioRecording
    route: TranscriptionRoute
    transcript_text: str


class InterviewSession:
    """Manages optional voice/text interview answers, transcript editing, and audio cleanup."""

    def __init__(
        self,
        *,
        candidate_store: CandidateStore,
        audio_staging_dir: Path,
        microphone_granted: bool,
        cloud_transcription_consented: bool = False,
        retain_raw_audio_after_save: bool = False,
    ) -> None:
        self._store = candidate_store
        self._audio_dir = audio_staging_dir.resolve()
        self._microphone_granted = microphone_granted
        self._cloud_consented = cloud_transcription_consented
        self._retain_audio = retain_raw_audio_after_save
        self._audio_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def record_audio_answer(self, *, question_id: str, raw_audio_bytes: bytes) -> AudioRecording:
        if not self._microphone_granted:
            raise InterviewError(
                "microphone_permission_denied: use submit_typed_answer or grant Microphone access"
            )
        rec_id = f"rec_{uuid.uuid4().hex[:12]}"
        audio_path = self._audio_dir / f"{rec_id}.wav"
        audio_path.write_bytes(raw_audio_bytes)
        return AudioRecording(
            recording_id=rec_id,
            question_id=question_id,
            audio_path=audio_path,
        )

    def transcribe_recording(
        self,
        recording: AudioRecording,
        *,
        route: TranscriptionRoute,
        raw_transcript: str,
    ) -> TranscriptDraft:
        if route == TranscriptionRoute.CLOUD_CONSENTED and not self._cloud_consented:
            raise InterviewError("cloud_transcription_consent_missing")
        return TranscriptDraft(
            recording=recording,
            route=route,
            transcript_text=raw_transcript.strip(),
        )

    def edit_transcript(
        self,
        draft: TranscriptDraft,
        *,
        corrected_transcript: str,
    ) -> TranscriptDraft:
        return TranscriptDraft(
            recording=draft.recording,
            route=draft.route,
            transcript_text=corrected_transcript.strip(),
        )

    def confirm_and_promote_transcript(
        self,
        draft: TranscriptDraft,
        *,
        fact_key: str,
        category: str,
        effective_from: str,
        country: str | None = None,
    ) -> str:
        scope = (
            FactScope(level=ScopeLevel.COUNTRY, country=country)
            if country
            else FactScope(level=ScopeLevel.GLOBAL)
        )
        fact_id = self._store.add_fact(
            CandidateFactInput(
                key=fact_key,
                category=category,
                value=draft.transcript_text,
                source_type="user_confirmed_interview",
                source_ref=draft.recording.recording_id,
                confidence=1.0,
                confirmed=True,
                scope=scope,
                effective_from=effective_from,
            )
        )
        if not self._retain_audio and draft.recording.audio_path.exists():
            draft.recording.audio_path.unlink()
        return fact_id

    def submit_typed_answer(
        self,
        *,
        question_id: str,
        fact_key: str,
        category: str,
        value: Any,
        effective_from: str,
        country: str | None = None,
    ) -> str:
        scope = (
            FactScope(level=ScopeLevel.COUNTRY, country=country)
            if country
            else FactScope(level=ScopeLevel.GLOBAL)
        )
        return self._store.add_fact(
            CandidateFactInput(
                key=fact_key,
                category=category,
                value=value,
                source_type="user_confirmed_interview",
                source_ref=f"typed_{question_id}",
                confidence=1.0,
                confirmed=True,
                scope=scope,
                effective_from=effective_from,
            )
        )
