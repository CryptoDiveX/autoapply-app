"""App-owned browser path isolation, profile partitioning, and 1-session lease management (P01).

Enforces AA-INS-002, AA-INS-004, AA-AUTH-003, AA-AUTH-004, NFR-01, C-01, C-07:
- All browser binaries, caches, licences, and profiles stay inside app-owned roots.
- Four partitioned profiles (auth_trusted, ats_operator, teal_tracker, linkedin_session).
- CapSolver extension is permitted ONLY in ats_operator, never in auth_trusted/teal/linkedin.
- Trusted auth mode disables agent DOM observation and screenshots.
- Single-session lease manager time-multiplexes profiles within CloakBrowser's 1-session limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping
import uuid


FORBIDDEN_GLOBAL_BROWSER_VARS: tuple[str, ...] = (
    "CLOAKBROWSER_KEY",
    "CLOAKBROWSER_CACHE_DIR",
    "CLOAKBROWSER_PROFILE_DIR",
    "CLOAKBROWSER_BINARY_PATH",
    "PLAYWRIGHT_BROWSERS_PATH",
    "CHROME_DEVEL_SANDBOX",
    "REMOTE_DEBUGGING_PORT",
)


class BrowserProfileKind(str, Enum):
    """Partitioned app-owned browser profiles per C-07."""

    AUTH_TRUSTED = "auth_trusted"
    ATS_OPERATOR = "ats_operator"
    TEAL_TRACKER = "teal_tracker"
    LINKEDIN_SESSION = "linkedin_session"


class BrowserSessionLeaseError(RuntimeError):
    """Raised when attempting to violate the 1-session browser concurrency limit."""


@dataclass(frozen=True)
class BrowserSessionLease:
    """Active single-session lease for an app-owned browser profile."""

    lease_id: str
    profile: BrowserProfileKind
    owner_id: str


class BrowserSessionLeaseManager:
    """Enforces at most one concurrent active browser session across partitioned profiles."""

    def __init__(self) -> None:
        self._active_lease: BrowserSessionLease | None = None

    @property
    def active_lease(self) -> BrowserSessionLease | None:
        return self._active_lease

    def acquire(self, profile: BrowserProfileKind, *, owner_id: str) -> BrowserSessionLease:
        if self._active_lease is not None:
            raise BrowserSessionLeaseError(
                f"concurrent_session_limit: profile '{self._active_lease.profile.value}' "
                f"is already leased by '{self._active_lease.owner_id}' "
                f"(lease_id={self._active_lease.lease_id}). Release it before multiplexing."
            )
        lease = BrowserSessionLease(
            lease_id=f"blease_{uuid.uuid4().hex[:12]}",
            profile=profile,
            owner_id=owner_id,
        )
        self._active_lease = lease
        return lease

    def release(self, lease_id: str) -> None:
        if self._active_lease is None or self._active_lease.lease_id != lease_id:
            raise BrowserSessionLeaseError(f"unknown_or_inactive_lease: {lease_id}")
        self._active_lease = None


@dataclass(frozen=True)
class BrowserLaunchConfig:
    """Deterministic launch parameters for an app-owned browser profile."""

    profile: BrowserProfileKind
    profile_dir: Path
    cache_dir: Path
    licence_file: Path
    enabled_extensions: tuple[Path, ...]
    agent_dom_observation_allowed: bool
    screenshots_allowed: bool


class BrowserWorkspace:
    """Manages isolated filesystem layout and launch configurations for the app-owned browser."""

    def __init__(self, *, app_support_root: Path, app_cache_root: Path) -> None:
        self._app_support_root = app_support_root.resolve()
        self._app_cache_root = app_cache_root.resolve()
        self._lease_manager = BrowserSessionLeaseManager()

    @property
    def browser_root(self) -> Path:
        return self._app_support_root / "browser"

    @property
    def binary_dir(self) -> Path:
        return self.browser_root / "bin"

    @property
    def licence_dir(self) -> Path:
        return self.browser_root / "licence"

    @property
    def licence_file(self) -> Path:
        return self.licence_dir / "cloak_entitlement.json"

    @property
    def profiles_root(self) -> Path:
        return self.browser_root / "profiles"

    @property
    def cache_dir(self) -> Path:
        return self._app_cache_root / "browser-cache"

    @property
    def session_lease_manager(self) -> BrowserSessionLeaseManager:
        return self._lease_manager

    def profile_dir(self, kind: BrowserProfileKind) -> Path:
        return self.profiles_root / kind.value

    def ensure_directories(self) -> None:
        self.binary_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.licence_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.profiles_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        for kind in BrowserProfileKind:
            self.profile_dir(kind).mkdir(parents=True, exist_ok=True, mode=0o700)

    def build_launch_config(
        self,
        kind: BrowserProfileKind,
        *,
        capsolver_extension_dir: Path | None = None,
        capsolver_enabled: bool = False,
    ) -> BrowserLaunchConfig:
        prof_path = self.profile_dir(kind)
        if kind == BrowserProfileKind.AUTH_TRUSTED:
            return BrowserLaunchConfig(
                profile=kind,
                profile_dir=prof_path,
                cache_dir=self.cache_dir,
                licence_file=self.licence_file,
                enabled_extensions=(),
                agent_dom_observation_allowed=False,
                screenshots_allowed=False,
            )

        extensions: tuple[Path, ...] = ()
        if (
            kind == BrowserProfileKind.ATS_OPERATOR
            and capsolver_enabled
            and capsolver_extension_dir is not None
        ):
            extensions = (capsolver_extension_dir.resolve(),)

        return BrowserLaunchConfig(
            profile=kind,
            profile_dir=prof_path,
            cache_dir=self.cache_dir,
            licence_file=self.licence_file,
            enabled_extensions=extensions,
            agent_dom_observation_allowed=True,
            screenshots_allowed=True,
        )

    def build_sanitized_env(self, parent_env: Mapping[str, str]) -> dict[str, str]:
        allowlisted_keys = ("PATH", "HOME", "TMPDIR", "USER", "LOGNAME", "LANG", "LC_ALL")
        clean: dict[str, str] = {}
        for key in allowlisted_keys:
            if key in parent_env and key not in FORBIDDEN_GLOBAL_BROWSER_VARS:
                clean[key] = parent_env[key]
        clean["AUTOAPPLY_BROWSER_ROOT"] = str(self.browser_root)
        clean["AUTOAPPLY_BROWSER_CACHE_DIR"] = str(self.cache_dir)
        clean["AUTOAPPLY_BROWSER_LICENCE_PATH"] = str(self.licence_file)
        return clean
