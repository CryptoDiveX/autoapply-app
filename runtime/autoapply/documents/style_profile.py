"""Deterministic reference resume style profile extraction (P11 / AA-DOC-002 / C-11)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResumeStyleProfile:
    """Typography, hierarchy, spacing, and page-structure profile of the customer's reference resume."""

    font_family: str
    heading_scale: float
    line_spacing: float
    margin_pt: int
    section_order: tuple[str, ...]
    target_page_count: int


def extract_style_profile(reference_metadata: dict[str, Any]) -> ResumeStyleProfile:
    font_family = str(reference_metadata.get("font_family", "Helvetica"))
    heading_scale = float(reference_metadata.get("heading_scale", 1.25))
    line_spacing = float(reference_metadata.get("line_spacing", 1.15))
    margin_pt = int(reference_metadata.get("margin_pt", 36))
    raw_sections = reference_metadata.get(
        "section_order", ["Summary", "Experience", "Education", "Skills"]
    )
    target_pages = int(reference_metadata.get("page_count", 1))
    return ResumeStyleProfile(
        font_family=font_family,
        heading_scale=heading_scale,
        line_spacing=line_spacing,
        margin_pt=margin_pt,
        section_order=tuple(str(s) for s in raw_sections),
        target_page_count=max(1, target_pages),
    )
