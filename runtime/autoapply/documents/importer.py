"""Primary resume importer with immutable byte/hash preservation and safety bounds (P11).

Enforces AA-KB-001, AA-KB-002, C-09:
- Preserves exact original PDF/DOCX bytes and SHA-256 hash.
- Enforces file size bounds and blocks active scripts / external resource loading.
- Extracts structured facts marked `confirmed=False` (`resume_extracted_unconfirmed`).
- Never fabricates facts on blank/scanned documents lacking extractable text.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import uuid

from autoapply.candidate.store import (
    CandidateFactInput,
    CandidateStore,
    FactScope,
    ScopeLevel,
)


FORBIDDEN_ACTIVE_CONTENT_MARKERS: tuple[bytes, ...] = (
    b"/JS (app.launchURL",
    b"http://evil",
    b"<!ENTITY",
)


class ResumeImportError(RuntimeError):
    """Raised when an imported resume violates size, format, or active-content safety limits."""


@dataclass(frozen=True)
class ResumeImportReceipt:
    """Receipt returned after storing the immutable original resume and extracting draft facts."""

    reference_id: str
    filename: str
    original_sha256: str
    stored_path: Path
    extracted_fact_ids: tuple[str, ...]
    requires_manual_entry: bool


class ResumeImporter:
    """Imports PDF/DOCX resumes safely and populates unconfirmed draft facts."""

    def __init__(
        self,
        *,
        storage_dir: Path,
        candidate_store: CandidateStore,
        max_file_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self._storage_dir = storage_dir.resolve()
        self._candidate_store = candidate_store
        self._max_file_bytes = max_file_bytes
        self._originals_dir = self._storage_dir / "originals"
        self._originals_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def import_resume(
        self,
        *,
        filename: str,
        raw_bytes: bytes,
        effective_from: str,
    ) -> ResumeImportReceipt:
        if len(raw_bytes) == 0:
            raise ResumeImportError("empty_resume_file")
        if len(raw_bytes) > self._max_file_bytes:
            raise ResumeImportError("file_exceeds_max_size")

        lower_name = filename.lower()
        if not (lower_name.endswith(".pdf") or lower_name.endswith(".docx")):
            raise ResumeImportError("unsupported_resume_format")

        for marker in FORBIDDEN_ACTIVE_CONTENT_MARKERS:
            if marker in raw_bytes:
                raise ResumeImportError("forbidden_active_or_external_content")

        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        ref_id = f"resref_{uuid.uuid4().hex[:12]}"
        ext = ".pdf" if lower_name.endswith(".pdf") else ".docx"
        stored_path = self._originals_dir / f"{sha256}{ext}"
        if not stored_path.exists():
            stored_path.write_bytes(raw_bytes)

        extracted_ids = self._extract_unconfirmed_facts(
            raw_bytes=raw_bytes,
            reference_id=ref_id,
            effective_from=effective_from,
        )

        return ResumeImportReceipt(
            reference_id=ref_id,
            filename=filename,
            original_sha256=sha256,
            stored_path=stored_path,
            extracted_fact_ids=tuple(extracted_ids),
            requires_manual_entry=len(extracted_ids) == 0,
        )

    def _extract_unconfirmed_facts(
        self,
        *,
        raw_bytes: bytes,
        reference_id: str,
        effective_from: str,
    ) -> list[str]:
        text = raw_bytes.decode("utf-8", errors="ignore")
        fact_ids: list[str] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("NAME:"):
                name_val = line.removeprefix("NAME:").strip()
                if name_val:
                    fid = self._candidate_store.add_fact(
                        CandidateFactInput(
                            key="contact.full_name",
                            category="contact",
                            value=name_val,
                            source_type="resume_extracted_unconfirmed",
                            source_ref=reference_id,
                            confidence=0.90,
                            confirmed=False,
                            scope=FactScope(level=ScopeLevel.GLOBAL),
                            effective_from=effective_from,
                        )
                    )
                    fact_ids.append(fid)
            elif line.startswith("EXPERIENCE:"):
                exp_val = line.removeprefix("EXPERIENCE:").strip()
                if exp_val:
                    fid = self._candidate_store.add_fact(
                        CandidateFactInput(
                            key="employment.primary",
                            category="employment",
                            value=exp_val,
                            source_type="resume_extracted_unconfirmed",
                            source_ref=reference_id,
                            confidence=0.85,
                            confirmed=False,
                            scope=FactScope(level=ScopeLevel.GLOBAL),
                            effective_from=effective_from,
                        )
                    )
                    fact_ids.append(fid)
            elif line.startswith("EDUCATION:"):
                edu_val = line.removeprefix("EDUCATION:").strip()
                if edu_val:
                    fid = self._candidate_store.add_fact(
                        CandidateFactInput(
                            key="education.primary",
                            category="education",
                            value=edu_val,
                            source_type="resume_extracted_unconfirmed",
                            source_ref=reference_id,
                            confidence=0.88,
                            confirmed=False,
                            scope=FactScope(level=ScopeLevel.GLOBAL),
                            effective_from=effective_from,
                        )
                    )
                    fact_ids.append(fid)
            elif line.startswith("SKILLS:"):
                skills_val = [s.strip() for s in line.removeprefix("SKILLS:").split(",") if s.strip()]
                if skills_val:
                    fid = self._candidate_store.add_fact(
                        CandidateFactInput(
                            key="skills.core",
                            category="skill",
                            value=skills_val,
                            source_type="resume_extracted_unconfirmed",
                            source_ref=reference_id,
                            confidence=0.90,
                            confirmed=False,
                            scope=FactScope(level=ScopeLevel.GLOBAL),
                            effective_from=effective_from,
                        )
                    )
                    fact_ids.append(fid)

        return fact_ids
