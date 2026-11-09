#!/usr/bin/env python3
"""List or check companies with submitted VB Jobs applications in a rolling window.

Default output is JSON with submitted companies found in applications-log.md over the last
30 days. Use --company to check whether a target company should be skipped before drafting
or submitting another role.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

DEFAULT_LOG = Path(
    "~/.hermes/profiles/vb-jobs/skills/productivity/"
    "vb-job-application-operator/references/project-docs/claude/applications-log.md"
)
SUBMITTED_PATTERNS = [
    re.compile(r"(?m)^- Status:\s*SUBMITTED\b", re.I),
    # A legitimate no-file native application still blocks another employer role,
    # even when excluded from the approved-PDF delivery campaign checkpoint.
    re.compile(r"(?m)^- Status:\s*VERIFIED NATIVE APPLICATION\b", re.I),
    re.compile(r"SUBMITTED through|SUBMITTED by direct email", re.I),
    re.compile(r"verified as Applied(?:[^A-Za-z]|$)", re.I),
]
DUPLICATE_PATTERN = re.compile(r"DUPLICATE SUBMISSION INCIDENT", re.I)
QUALITY_STATUS_PATTERN = re.compile(
    r"(?mi)^(?:.*?(?:QUALITY INCIDENT|DO NOT COUNT)|- Status:\s*.*?(?:QUALITY INCIDENT|DO NOT COUNT)|- Count status:\s*(?:QUALITY INCIDENT|DO NOT COUNT))"
)
DATE_PATTERNS = [
    re.compile(r"(?m)^- Date applied:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})"),
    re.compile(r"applied_at [`']?([0-9]{4}-[0-9]{2}-[0-9]{2})", re.I),
]


def norm_company(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def section_heading(section: str) -> str:
    return section.splitlines()[0].strip() if section.splitlines() else ""


def heading_company(heading: str) -> str:
    parts = [part.strip() for part in heading.split(",")]
    source_prefixes = {
        "LinkedIn Easy Apply",
        "LinkedIn",
        "HH.ru",
        "Direct email",
        "Workable",
        "Greenhouse",
        "Lever",
        "Ashby",
        "Factorial",
        "HubSpot form",
        "BambooHR",
        "Pinpoint",
    }
    if parts and parts[0] in source_prefixes and len(parts) >= 2:
        return parts[1]
    return heading.split(",", 1)[0].strip()


def section_date(section: str) -> dt.date | None:
    for pattern in DATE_PATTERNS:
        match = pattern.search(section)
        if match:
            try:
                return dt.date.fromisoformat(match.group(1))
            except ValueError:
                return None
    return None


def collect(log_text: str, days: int, today: dt.date) -> dict:
    cutoff = today - dt.timedelta(days=days)
    rows = []
    companies: dict[str, list[dict]] = {}
    for section in re.split(r"(?m)^## ", log_text)[1:]:
        if DUPLICATE_PATTERN.search(section) or QUALITY_STATUS_PATTERN.search(section):
            continue
        if not any(p.search(section) for p in SUBMITTED_PATTERNS):
            continue
        date = section_date(section)
        if date is None or date < cutoff:
            continue
        heading = section_heading(section)
        company = heading_company(heading)
        row = {"company": company, "company_key": norm_company(company), "heading": heading, "date": date.isoformat()}
        rows.append(row)
        companies.setdefault(row["company_key"], []).append(row)
    return {"window_days": days, "cutoff": cutoff.isoformat(), "submitted_companies": rows, "by_company_key": companies}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("log_path", nargs="?", default=str(DEFAULT_LOG))
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--company", help="Company name to check against the rolling window")
    parser.add_argument("--today", help="Override today's date as YYYY-MM-DD for deterministic tests")
    args = parser.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(dt.timezone.utc).date()
    data = collect(Path(args.log_path).expanduser().read_text(errors="ignore"), args.days, today)
    if args.company:
        key = norm_company(args.company)
        matches = data["by_company_key"].get(key, [])
        data = {"company": args.company, "company_key": key, "skip_due_recent_submission": bool(matches), "matches": matches, "window_days": args.days, "cutoff": data["cutoff"]}
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
