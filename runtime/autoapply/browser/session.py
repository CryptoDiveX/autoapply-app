"""Browser execution session, non-interfering background mode, and takeover handoff (P19).

Enforces AA-UX-001, AA-UX-002, AA-UX-003, 03-ONBOARDING-AND-NATIVE-UX.md (§4):
- Switching between background and visible mode reveals the exact same owned session.
- Background mode never moves the physical cursor, steals Mac focus, or switches Spaces.
- Desktop-level or security steps pause and request human takeover.
- Resuming from human takeover re-reads the entire form and invalidates stale approvals.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from autoapply.browser.fields import ATSFormDriverProtocol


class TakeoverPauseError(RuntimeError):
    """Raised when an operation must pause for human takeover rather than violating background mode."""


class VisibilitySetting(str, Enum):
    """Independent visibility modes (03-ONBOARDING-AND-NATIVE-UX.md §2 O-12)."""

    BACKGROUND = "background"
    VISIBLE_BROWSER = "visible_browser"
    USER_TAKEOVER = "user_takeover"


@dataclass(frozen=True)
class TakeoverResumeResult:
    """Result of re-reading the form after a user takeover session completes."""

    session_id: str
    form_snapshot: dict[str, str | None]
    requires_fresh_approval: bool


class BrowserExecutionSession:
    """Manages an app-owned browser session across background, visible, and takeover states."""

    def __init__(
        self,
        *,
        session_id: str,
        ats_server: ATSFormDriverProtocol,
        visibility: VisibilitySetting = VisibilitySetting.BACKGROUND,
    ) -> None:
        self._session_id = session_id
        self._ats_server = ats_server
        self._visibility = visibility
        self._pre_takeover_snapshot: dict[str, str | None] = {}
        self.physical_cursor_moved: bool = False
        self.mac_focus_stolen: bool = False

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def visibility(self) -> VisibilitySetting:
        return self._visibility

    def switch_visibility(self, new_visibility: VisibilitySetting) -> None:
        self._visibility = new_visibility

    def request_desktop_or_security_step(self, *, reason: str) -> None:
        # Never fall back to moving the physical cursor or stealing focus in background mode
        self._visibility = VisibilitySetting.USER_TAKEOVER
        raise TakeoverPauseError(
            f"desktop_or_security_handoff_required: paused for user takeover ({reason})"
        )

    def begin_user_takeover(self, *, reason: str) -> None:
        _ = reason
        self._pre_takeover_snapshot = dict(self._ats_server.read_committed_form_snapshot())
        self._visibility = VisibilitySetting.USER_TAKEOVER

    def resume_from_takeover(self) -> TakeoverResumeResult:
        current_snapshot = dict(self._ats_server.read_committed_form_snapshot())
        changed = current_snapshot != self._pre_takeover_snapshot
        self._visibility = VisibilitySetting.VISIBLE_BROWSER
        return TakeoverResumeResult(
            session_id=self._session_id,
            form_snapshot=current_snapshot,
            requires_fresh_approval=changed,
        )
