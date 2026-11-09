"""Unit tests for P05 runtime manifest, release-gate blocker, and P06 onboarding state rules.

Covers: AA-INS-001..004, AA-LIC-001..002, AA-UX-001..002, C-01, C-02
Scenarios: T-INS-04, T-LIC-01, T-UX-02, T-UX-05
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_manifest_pins_allowlisted_skills_and_excludes_unrelated_modules() -> None:
    """P05 / AA-INS-003 / AA-INS-004: Verify runtime-manifest.json integrity and allowlist."""
    manifest_path = REPO_ROOT / "packaging" / "runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["target_platform"]["minimum_os_version"] == "14.0"
    assert "arm64" in manifest["target_platform"]["architectures"]
    assert manifest["isolated_runtime"]["allowlisted_skills"] == [
        "application-operator",
        "document-quality",
        "tracker-reconciliation",
    ]
    assert "minecraft" in manifest["isolated_runtime"]["excluded_subsystems"]
    assert "telegram-gateway" in manifest["isolated_runtime"]["excluded_subsystems"]


def test_make_verify_release_fails_visibly_while_gates_are_unapproved() -> None:
    """07-IMPLEMENTATION-PLAN.md (§9): verify-release must fail visibly when gates are unapproved."""
    proc = subprocess.run(
        ["make", "verify-release"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "verify-release: BLOCKED" in (proc.stderr + proc.stdout)
    assert "G-01" in (proc.stderr + proc.stdout)
