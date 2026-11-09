"""LinkedIn networking contact ranking, approval-gated drafts, and follow-up state machine (AA-SOC-001..003)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
import uuid


RELATIONSHIP_PRIORITY = {
    "1st_degree_mutual": 1,
    "recruiter": 2,
    "hiring_manager": 3,
    "team_lead": 4,
    "2nd_degree_peer": 5,
}


@dataclass(frozen=True)
class OutreachDraft:
    draft_id: str
    application_id: str
    contact_id: str
    message_body: str
    follow_up_business_days: int
    status: str = "pending_user_approval"
    reply_or_status_change: str | None = None


class LinkedInNetworkingManager:
    """Manages contact ranking, explicit user approval for outreach drafts, and N-day follow-up reminders."""

    def __init__(self) -> None:
        self._drafts: dict[str, OutreachDraft] = {}

    @staticmethod
    def rank_contacts(contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            contacts,
            key=lambda c: RELATIONSHIP_PRIORITY.get(str(c.get("relationship", "")), 99),
        )

    def create_outreach_draft(
        self,
        *,
        application_id: str,
        contact_id: str,
        message_body: str,
        follow_up_business_days: int = 5,
    ) -> OutreachDraft:
        draft_id = f"li_draft_{uuid.uuid4().hex[:10]}"
        draft = OutreachDraft(
            draft_id=draft_id,
            application_id=application_id,
            contact_id=contact_id,
            message_body=message_body,
            follow_up_business_days=follow_up_business_days,
            status="pending_user_approval",
        )
        self._drafts[draft_id] = draft
        return draft

    def send_message(self, draft_id: str, *, user_approved: bool) -> OutreachDraft:
        if not user_approved:
            raise PermissionError("LINKEDIN_APPROVAL_REQUIRED: outreach message cannot be sent without explicit user approval")
        draft = self._drafts[draft_id]
        updated = replace(draft, status="sent")
        self._drafts[draft_id] = updated
        return updated

    def record_reply_or_status_change(self, draft_id: str, *, reason: str) -> OutreachDraft:
        draft = self._drafts[draft_id]
        updated = replace(draft, reply_or_status_change=reason)
        self._drafts[draft_id] = updated
        return updated

    def is_follow_up_due(self, draft_id: str, *, elapsed_business_days: int) -> bool:
        draft = self._drafts[draft_id]
        if draft.status != "sent":
            return False
        if draft.reply_or_status_change is not None:
            return False
        return elapsed_business_days >= draft.follow_up_business_days
