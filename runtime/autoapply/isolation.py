"""Isolated runtime environment construction, skill/tool allowlists, and process provenance (P07).

Enforces AA-INS-002, AA-INS-003, NFR-01, C-06:
- Constructs worker environment from a strict allowlist; strips parent PYTHONPATH, PYTHONHOME,
  HERMES_PROFILE, CODEX_HOME, and ambient API keys.
- Pins HERMES_HOME and PYTHONNOUSERSITE=1 inside ~/Library/Application Support/AutoApply/.
- Allowlists only job-search skills and typed domain tools; rejects Minecraft, Telegram gateway,
  fleet scanners, shell execution, and eval.
- Verifies PID + start timestamp + executable path before terminating any worker process.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


ALLOWED_PRODUCT_SKILLS: frozenset[str] = frozenset(
    {
        "application-operator",
        "document-quality",
        "tracker-reconciliation",
    }
)

ALLOWED_PRODUCTION_TOOLS: frozenset[str] = frozenset(
    {
        "job.read_page",
        "browser.inspect_field_state",
        "browser.fill_approved_field",
        "browser.attach_approved_artifact",
        "application.propose_submit",
        "application.commit_submit",
        "candidate.retrieve_confirmed_facts",
        "document.generate_draft",
        "document.render_artifact",
        "gmail.query_authorized_threads",
        "tracker.sync_verified_record",
        "human.request_takeover",
    }
)

REQUIRED_SUBDIRECTORIES: tuple[str, ...] = (
    "runtime-state",
    "runtime-state/hermes",
    "candidate",
    "jobs",
    "documents",
    "evidence",
    "browser",
    "secrets",
    "licensing",
    "updates",
)


class RuntimeIsolationError(RuntimeError):
    """Raised when an isolation, skill/tool allowlist, or process provenance check fails."""


class RuntimeEnvironmentIsolator:
    """Constructs a sanitized worker environment confined to app-owned roots."""

    ALLOWLISTED_PARENT_KEYS: tuple[str, ...] = (
        "HOME",
        "USER",
        "LOGNAME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
    )

    def __init__(self, *, app_support_root: Path) -> None:
        self._app_support_root = app_support_root.resolve()

    @property
    def app_support_root(self) -> Path:
        return self._app_support_root

    @property
    def hermes_home(self) -> Path:
        return self._app_support_root / "runtime-state" / "hermes"

    def ensure_owned_directories(self) -> None:
        self._app_support_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for rel in REQUIRED_SUBDIRECTORIES:
            (self._app_support_root / rel).mkdir(parents=True, exist_ok=True, mode=0o700)

    def build_worker_env(self, parent_env: Mapping[str, str]) -> dict[str, str]:
        self.ensure_owned_directories()
        env: dict[str, str] = {}
        for key in self.ALLOWLISTED_PARENT_KEYS:
            if key in parent_env:
                env[key] = parent_env[key]

        env["PATH"] = "/usr/bin:/bin"
        env["AUTOAPPLY_APP_SUPPORT"] = str(self._app_support_root)
        env["HERMES_HOME"] = str(self.hermes_home)
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    def verify_skill_allowed(self, skill_name: str) -> None:
        if skill_name not in ALLOWED_PRODUCT_SKILLS:
            raise RuntimeIsolationError(
                f"forbidden_skill: '{skill_name}' is not in the product skill allowlist"
            )

    def verify_tool_allowed(self, tool_name: str) -> None:
        if tool_name not in ALLOWED_PRODUCTION_TOOLS:
            raise RuntimeIsolationError(
                f"forbidden_tool: '{tool_name}' is not permitted in the production runtime"
            )


@dataclass(frozen=True)
class ProcessProvenanceRecord:
    """Identity record for an app-owned child process."""

    pid: int
    start_timestamp_ns: int
    executable_path: str
    run_id: str


class ProcessProvenanceGuard:
    """Prevents PID-reuse termination mistakes or broad process killing."""

    def __init__(self, *, expected_executable_Prefix: str) -> None:
        self._expected_prefix = expected_executable_Prefix
        self._records: dict[int, ProcessProvenanceRecord] = {}

    def register(self, record: ProcessProvenanceRecord) -> None:
        if not record.executable_path.startswith(self._expected_prefix):
            raise RuntimeIsolationError(
                f"untrusted_worker_executable: {record.executable_path}"
            )
        self._records[record.pid] = record

    def verify_can_terminate(
        self,
        *,
        pid: int,
        observed_start_ns: int,
        observed_executable_path: str,
    ) -> bool:
        rec = self._records.get(pid)
        if rec is None:
            raise RuntimeIsolationError(f"pid_provenance_mismatch: unregistered pid {pid}")
        if (
            rec.start_timestamp_ns != observed_start_ns
            or rec.executable_path != observed_executable_path
            or not observed_executable_path.startswith(self._expected_prefix)
        ):
            raise RuntimeIsolationError(
                f"pid_provenance_mismatch: pid {pid} does not match recorded start identity/executable"
            )
        return True
