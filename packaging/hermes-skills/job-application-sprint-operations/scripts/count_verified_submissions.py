#!/usr/bin/env python3
"""Count deduped verified VB Jobs submissions from applications-log.md.

Prints JSON with a strict submitted count, latest headings, and blocker/applying headings.
Use this for high-volume sprint reconciliation so duplicate incidents and Applying records
are not mistaken for progress.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DEFAULT_LOG = Path(
    "~/.hermes/profiles/vb-jobs/skills/productivity/"
    "vb-job-application-operator/references/project-docs/claude/applications-log.md"
)

SUBMITTED_PATTERNS = [
    re.compile(r"(?m)^- Status:\s*SUBMITTED\b", re.I),
    re.compile(r"SUBMITTED through|SUBMITTED by direct email", re.I),
    re.compile(r"verified as Applied(?:[^A-Za-z]|$)", re.I),
]
BLOCKER_PATTERNS = [
    re.compile(r"(?m)^- Status:\s*(APPLYING|BLOCKED|PRE-SUBMIT BLOCKED)\b", re.I),
    re.compile(r"blocked before confirmed submit", re.I),
    re.compile(r"Teal verified:\s*Applying", re.I),
]
DUPLICATE_PATTERN = re.compile(r"DUPLICATE(?:[-\\s]COMPANY)?\\s+SUBMISSION INCIDENT", re.I)
QUALITY_INCIDENT_PATTERN = re.compile(r"QUALITY INCIDENT|DO NOT COUNT", re.I)
QUALITY_STATUS_PATTERN = re.compile(
    r"(?mi)^(?:.*?(?:QUALITY INCIDENT|DO NOT COUNT)|- Status:\s*.*?(?:QUALITY INCIDENT|DO NOT COUNT)|- Count status:\s*(?:QUALITY INCIDENT|DO NOT COUNT))"
)


def section_heading(section: str) -> str:
    return section.splitlines()[0].strip() if section.splitlines() else ""


def is_quality_incident(section: str) -> bool:
    """True only when the section itself is marked non-countable.

    Do not exclude a clean submission merely because its notes mention that other
    targets or sibling lanes had quality incidents.
    """
    return bool(QUALITY_STATUS_PATTERN.search(section))


def count(log_text: str) -> dict:
    sections = re.split(r"(?m)^## ", log_text)[1:]
    submitted = []
    blockers = []
    for section in sections:
        heading = section_heading(section)
        if not heading:
            continue
        if any(p.search(section) for p in SUBMITTED_PATTERNS) and not DUPLICATE_PATTERN.search(section) and not is_quality_incident(section):
            submitted.append(heading)
        if any(p.search(section) for p in BLOCKER_PATTERNS) and not DUPLICATE_PATTERN.search(section) and not is_quality_incident(section):
            blockers.append(heading)
    return {
        "verified_submitted_count": len(submitted),
        "latest_verified": submitted[:20],
        "blocker_or_applying_count": len(blockers),
        "latest_blocker_or_applying": blockers[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("log_path", nargs="?", default=str(DEFAULT_LOG))
    args = parser.parse_args()
    path = Path(args.log_path).expanduser()
    print(json.dumps(count(path.read_text(errors="ignore")), indent=2))


if __name__ == "__main__":
    main()
