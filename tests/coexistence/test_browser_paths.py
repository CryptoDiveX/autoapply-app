"""Coexistence and isolation tests for app-owned browser paths, profiles, and 1-session lease (P01).

Covers: AA-INS-002, AA-INS-004, AA-AUTH-003, AA-AUTH-004, NFR-01, C-01, C-07
Scenarios: T-INS-02, T-AUTH-04, T-SEC-03
"""

from __future__ import annotations

from pathlib import Path
import pytest

from autoapply.browser.paths import (
    BrowserProfileKind,
    BrowserSessionLeaseError,
    BrowserWorkspace,
    FORBIDDEN_GLOBAL_BROWSER_VARS,
)


def test_browser_paths_remain_strictly_inside_app_owned_roots(tmp_path: Path) -> None:
    """T-INS-02: App browser paths never touch existing user home/browser directories."""
    fake_user_home = tmp_path / "user_home"
    existing_cloak = fake_user_home / ".cloakbrowser"
    existing_cloak.mkdir(parents=True)
    sentinel = existing_cloak / "personal_licence.key"
    sentinel.write_text("user-personal-cloak-key", encoding="utf-8")

    app_support = tmp_path / "AppSupport" / "AutoApply"
    app_cache = tmp_path / "Caches" / "AutoApply"

    ws = BrowserWorkspace(app_support_root=app_support, app_cache_root=app_cache)
    ws.ensure_directories()

    # All resolved paths must reside strictly under app_support or app_cache
    for kind in BrowserProfileKind:
        prof_dir = ws.profile_dir(kind)
        assert prof_dir.is_dir()
        assert app_support in prof_dir.parents

    assert app_support in ws.binary_dir.parents
    assert app_support in ws.licence_file.parents
    assert app_cache in ws.cache_dir.parents

    # Existing personal ~/.cloakbrowser must remain completely untouched
    assert sentinel.read_text(encoding="utf-8") == "user-personal-cloak-key"
    assert not any(p for p in existing_cloak.iterdir() if p != sentinel)


def test_profile_partitioning_and_capsolver_extension_isolation(tmp_path: Path) -> None:
    """C-07 / T-SEC-03: CapSolver extension is permitted only in ATS profile, never in auth/Teal/LinkedIn."""
    ws = BrowserWorkspace(
        app_support_root=tmp_path / "AppSupport" / "AutoApply",
        app_cache_root=tmp_path / "Caches" / "AutoApply",
    )
    ws.ensure_directories()

    ext_dir = tmp_path / "ext" / "capsolver"
    ext_dir.mkdir(parents=True)

    ats_launch = ws.build_launch_config(
        BrowserProfileKind.ATS_OPERATOR,
        capsolver_extension_dir=ext_dir,
        capsolver_enabled=True,
    )
    assert ext_dir in ats_launch.enabled_extensions
    assert ats_launch.agent_dom_observation_allowed is True

    # Trusted auth mode must reject extensions and suppress agent DOM/screenshots (C-04, C-07)
    auth_launch = ws.build_launch_config(
        BrowserProfileKind.AUTH_TRUSTED,
        capsolver_extension_dir=ext_dir,
        capsolver_enabled=True,
    )
    assert auth_launch.enabled_extensions == ()
    assert auth_launch.agent_dom_observation_allowed is False
    assert auth_launch.screenshots_allowed is False

    # Teal and LinkedIn profiles must also exclude CapSolver
    for kind in (BrowserProfileKind.TEAL_TRACKER, BrowserProfileKind.LINKEDIN_SESSION):
        cfg = ws.build_launch_config(
            kind,
            capsolver_extension_dir=ext_dir,
            capsolver_enabled=True,
        )
        assert cfg.enabled_extensions == ()


def test_single_concurrent_session_time_multiplexing_lease(tmp_path: Path) -> None:
    """C-01 / C-07: Enforce 1-session CloakBrowser concurrency limit via time-multiplexed leases."""
    ws = BrowserWorkspace(
        app_support_root=tmp_path / "AppSupport" / "AutoApply",
        app_cache_root=tmp_path / "Caches" / "AutoApply",
    )
    lease_mgr = ws.session_lease_manager

    lease_ats = lease_mgr.acquire(BrowserProfileKind.ATS_OPERATOR, owner_id="worker-1")
    assert lease_ats.profile == BrowserProfileKind.ATS_OPERATOR

    # Attempting to open a second concurrent profile without releasing fails closed
    with pytest.raises(BrowserSessionLeaseError, match="concurrent_session_limit"):
        lease_mgr.acquire(BrowserProfileKind.TEAL_TRACKER, owner_id="worker-1")

    # After releasing the first profile, time-multiplexing into Teal succeeds
    lease_mgr.release(lease_ats.lease_id)
    lease_teal = lease_mgr.acquire(BrowserProfileKind.TEAL_TRACKER, owner_id="worker-1")
    assert lease_teal.profile == BrowserProfileKind.TEAL_TRACKER


def test_sanitized_browser_environment_strips_global_variables(tmp_path: Path) -> None:
    """AA-INS-002: Strip parent browser/CDP/Cloak environment variables."""
    ws = BrowserWorkspace(
        app_support_root=tmp_path / "AppSupport" / "AutoApply",
        app_cache_root=tmp_path / "Caches" / "AutoApply",
    )
    dirty_env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/Users/example",
        "CLOAKBROWSER_KEY": "leaked-global-key",
        "CLOAKBROWSER_CACHE_DIR": "/Users/example/.cloakbrowser",
        "PLAYWRIGHT_BROWSERS_PATH": "/Users/example/pw-browsers",
        "REMOTE_DEBUGGING_PORT": "9222",
    }
    clean_env = ws.build_sanitized_env(dirty_env)
    for forbidden in FORBIDDEN_GLOBAL_BROWSER_VARS:
        assert forbidden not in clean_env
    assert clean_env["AUTOAPPLY_BROWSER_CACHE_DIR"] == str(ws.cache_dir)
    assert clean_env["AUTOAPPLY_BROWSER_LICENCE_PATH"] == str(ws.licence_file)
