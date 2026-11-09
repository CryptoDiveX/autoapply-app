"""Coexistence and isolation tests for the private Hermes/Python runtime launcher (P07).

Covers: AA-INS-002, AA-INS-003, NFR-01, C-06
Scenarios: T-INS-02, T-INS-03
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import pytest

from autoapply.isolation import (
    ALLOWED_PRODUCT_SKILLS,
    ALLOWED_PRODUCTION_TOOLS,
    ProcessProvenanceGuard,
    ProcessProvenanceRecord,
    RuntimeEnvironmentIsolator,
    RuntimeIsolationError,
)


def test_sanitized_environment_strips_all_parent_python_hermes_and_api_vars(
    tmp_path: Path,
) -> None:
    """T-INS-02 / T-INS-03: Never inherit PYTHONPATH, global keys, ~/.hermes, or ~/.codex."""
    app_support = tmp_path / "AppSupport" / "AutoApply"
    isolator = RuntimeEnvironmentIsolator(app_support_root=app_support)

    dirty_parent_env = {
        "HOME": str(tmp_path / "user_home"),
        "USER": "candidate",
        "PATH": "/opt/homebrew/bin:/Users/candidate/.local/bin:/usr/bin:/bin",
        "PYTHONPATH": "/Users/candidate/custom_site_packages",
        "PYTHONHOME": "/opt/homebrew/Cellar/python",
        "PYTHONUSERBASE": "/Users/candidate/.local",
        "HERMES_HOME": "/Users/candidate/.hermes",
        "HERMES_PROFILE": "vb-jobs-personal",
        "CODEX_HOME": "/Users/candidate/.codex",
        "OPENAI_API_KEY": "sk-leaked-parent-openai-key",
        "OPENROUTER_API_KEY": "sk-or-v1-leaked-parent-key",
        "ANTHROPIC_API_KEY": "sk-ant-leaked-key",
    }

    clean_env = isolator.build_worker_env(dirty_parent_env)

    assert "PYTHONPATH" not in clean_env
    assert "PYTHONHOME" not in clean_env
    assert "PYTHONUSERBASE" not in clean_env
    assert "HERMES_PROFILE" not in clean_env
    assert "CODEX_HOME" not in clean_env
    assert "OPENAI_API_KEY" not in clean_env
    assert "OPENROUTER_API_KEY" not in clean_env
    assert "ANTHROPIC_API_KEY" not in clean_env

    assert clean_env["PYTHONNOUSERSITE"] == "1"
    assert clean_env["HERMES_HOME"] == str(app_support / "runtime-state" / "hermes")
    assert clean_env["PATH"] == "/usr/bin:/bin"


def test_skill_and_tool_allowlist_blocks_unrelated_or_dangerous_capabilities() -> None:
    """AA-INS-003 / T-INS-03 / T-SEC-05: Reject Minecraft, Telegram gateway, shell, and eval."""
    isolator = RuntimeEnvironmentIsolator(app_support_root=Path("/tmp/autoapply-test"))

    for skill in ALLOWED_PRODUCT_SKILLS:
        isolator.verify_skill_allowed(skill)

    for forbidden_skill in ("minecraft", "telegram-gateway", "fleet-scanner", "crypto-trading"):
        with pytest.raises(RuntimeIsolationError, match="forbidden_skill"):
            isolator.verify_skill_allowed(forbidden_skill)

    for tool in ALLOWED_PRODUCTION_TOOLS:
        isolator.verify_tool_allowed(tool)

    for forbidden_tool in ("shell.exec", "python.eval", "fs.read_arbitrary", "net.raw_http", "skill.install"):
        with pytest.raises(RuntimeIsolationError, match="forbidden_tool"):
            isolator.verify_tool_allowed(forbidden_tool)


def test_process_provenance_guard_prevents_killing_non_owned_or_reused_pids() -> None:
    """02-TECHNICAL-SPECIFICATION.md (§3): Verify PID + start timestamp + executable provenance."""
    guard = ProcessProvenanceGuard(
        expected_executable_Prefix="/Applications/AutoApply.app/Contents/Resources/python/bin/python3"
    )
    record = ProcessProvenanceRecord(
        pid=4242,
        start_timestamp_ns=1760812000000000000,
        executable_path="/Applications/AutoApply.app/Contents/Resources/python/bin/python3",
        run_id="run_01",
    )
    guard.register(record)

    # Matching provenance succeeds
    assert (
        guard.verify_can_terminate(
            pid=4242,
            observed_start_ns=1760812000000000000,
            observed_executable_path="/Applications/AutoApply.app/Contents/Resources/python/bin/python3",
        )
        is True
    )

    # PID reuse (different start timestamp or unrelated user Python binary) fails closed
    with pytest.raises(RuntimeIsolationError, match="pid_provenance_mismatch"):
        guard.verify_can_terminate(
            pid=4242,
            observed_start_ns=1760812999999999999,
            observed_executable_path="/Applications/AutoApply.app/Contents/Resources/python/bin/python3",
        )

    with pytest.raises(RuntimeIsolationError, match="pid_provenance_mismatch"):
        guard.verify_can_terminate(
            pid=4242,
            observed_start_ns=1760812000000000000,
            observed_executable_path="/opt/homebrew/bin/python3",
        )


def test_worker_entrypoint_runs_isolated_without_touching_existing_hermes_or_codex(
    tmp_path: Path,
) -> None:
    """T-INS-02: Launching runtime/autoapply/main.py leaves ~/.hermes and ~/.codex untouched."""
    fake_home = tmp_path / "user_home"
    existing_hermes = fake_home / ".hermes"
    existing_codex = fake_home / ".codex"
    existing_hermes.mkdir(parents=True)
    existing_codex.mkdir(parents=True)
    hermes_config = existing_hermes / "config.json"
    codex_auth = existing_codex / "auth.json"
    hermes_config.write_text('{"profile": "personal-untouched"}', encoding="utf-8")
    codex_auth.write_text('{"token": "personal-codex-untouched"}', encoding="utf-8")

    app_support = tmp_path / "AppSupport" / "AutoApply"
    isolator = RuntimeEnvironmentIsolator(app_support_root=app_support)
    env = isolator.build_worker_env({"HOME": str(fake_home), "USER": "candidate"})
    # Add strictly the local repo's runtime directory for the subprocess invocation
    repo_runtime = Path(__file__).resolve().parents[2] / "runtime"
    env["PYTHONPATH"] = str(repo_runtime)

    proc = subprocess.run(
        [sys.executable, "-m", "autoapply.main", "--health-check"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    status = json.loads(proc.stdout.strip())
    assert status["status"] == "healthy"
    assert status["hermes_home"] == str(app_support / "runtime-state" / "hermes")
    assert status["user_site_disabled"] is True

    # Verify personal ~/.hermes and ~/.codex were never modified or added to
    assert hermes_config.read_text(encoding="utf-8") == '{"profile": "personal-untouched"}'
    assert codex_auth.read_text(encoding="utf-8") == '{"token": "personal-codex-untouched"}'
    assert list(existing_hermes.iterdir()) == [hermes_config]
    assert list(existing_codex.iterdir()) == [codex_auth]
