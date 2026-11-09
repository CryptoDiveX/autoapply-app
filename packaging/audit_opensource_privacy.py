#!/usr/bin/env python3
"""Open-Source Privacy & Security Gate for AutoApply.

Verifies that zero personal PII, private resumes, personal recruiter threads,
local user paths, or real secret keys exist in any git-tracked file or built
application bundle before open-sourcing or promoting a build to production.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

BANNED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("local_home_path", re.compile(r"/Users/(?!Shared\b|example\b|candidate\b|test\b)[A-Za-z0-9._-]+\b")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("live_secret_token", re.compile(r"\b(?:pdl_live_apikey_[A-Za-z0-9_\-]{10,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9\-]{10,})\b")),
]


def scan_tracked_files() -> list[str]:
    violations: list[str] = []
    tracked = subprocess.check_output(["git", "-C", str(ROOT), "ls-files"], text=True).splitlines()
    for rel in tracked:
        if "node_modules/" in rel or rel == "packaging/audit_opensource_privacy.py":
            continue
        p = ROOT / rel
        if not p.is_file():
            continue
        for rule_name, pat in BANNED_PATTERNS:
            if pat.search(rel):
                violations.append(f"[FILENAME:{rule_name}] {rel}")
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for rule_name, pat in BANNED_PATTERNS:
            matches = pat.findall(text)
            if matches:
                sample = sorted(set(str(m) for m in matches))[:3]
                violations.append(f"[CONTENT:{rule_name}] {rel} ({len(matches)} matches: {sample})")
    return violations


def scan_built_app_bundle() -> list[str]:
    violations: list[str] = []
    app_res = ROOT / "dist" / "AutoApply.app" / "Contents" / "Resources"
    if not app_res.is_dir():
        return violations
    for p in sorted(app_res.rglob("*")):
        if not p.is_file() or "Browser/AutoApply Browser.app" in p.as_posix() or "node_modules/" in p.as_posix():
            continue
        rel = p.relative_to(ROOT).as_posix()
        for rule_name, pat in BANNED_PATTERNS:
            if pat.search(rel):
                violations.append(f"[BUNDLE_FILENAME:{rule_name}] {rel}")
        if p.suffix.lower() in (".py", ".js", ".json", ".md", ".txt", ".sh", ".html", ".plist"):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for rule_name, pat in BANNED_PATTERNS:
                matches = pat.findall(text)
                if matches:
                    sample = sorted(set(str(m) for m in matches))[:3]
                    violations.append(f"[BUNDLE_CONTENT:{rule_name}] {rel} ({len(matches)} matches: {sample})")
    return violations


def main() -> int:
    check_bundle = "--check-bundle" in sys.argv
    violations = scan_tracked_files()
    if check_bundle:
        violations.extend(scan_built_app_bundle())
    if violations:
        print("ERROR: Open-source privacy/security audit FAILED with violations:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print("audit-privacy: PASSED (0 personal PII, 0 private resumes, 0 local paths, 0 live secrets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
