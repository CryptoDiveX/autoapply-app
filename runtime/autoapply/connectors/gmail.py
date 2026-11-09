"""Gmail thread correlation and non-destructive mailbox classification (AA-MAIL-001, AA-MAIL-002).

Correlates application threads across Inbox, Sent, and existing labels while strictly
preserving personal email, unread state, stars, and user labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GmailMessage:
    message_id: str
    sender: str
    recipient: str
    subject: str
    body: str
    folder: str = "INBOX"


@dataclass
class GmailThread:
    thread_id: str
    messages: list[GmailMessage]
    unread: bool = True
    starred: bool = False
    user_labels: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReconciledThread:
    thread_id: str
    application_id: str
    classification: str
    direct_mailbox_url: str


class GmailConnector:
    """Non-destructive Gmail thread correlator and classifier."""

    def __init__(self, account_email: str) -> None:
        self._account_email = account_email.strip().lower()

    def reconcile_threads(
        self,
        threads: list[GmailThread],
        tracked_applications: list[dict[str, Any]],
    ) -> dict[str, ReconciledThread]:
        results: dict[str, ReconciledThread] = {}
        for thread in threads:
            matched_app_id = self._match_application(thread, tracked_applications)
            if matched_app_id is None:
                # Personal or unrelated thread: never modify unread, starred, or user_labels
                continue
            classification = self._classify_thread(thread)
            results[thread.thread_id] = ReconciledThread(
                thread_id=thread.thread_id,
                application_id=matched_app_id,
                classification=classification,
                direct_mailbox_url=f"https://mail.google.com/mail/u/0/#all/{thread.thread_id}",
            )
        return results

    @staticmethod
    def _match_application(thread: GmailThread, tracked_applications: list[dict[str, Any]]) -> str | None:
        combined = " ".join(f"{m.subject} {m.body} {m.sender} {m.recipient}" for m in thread.messages).lower()
        for app in tracked_applications:
            company = str(app.get("company_name", "")).strip().lower()
            if company and company in combined:
                return str(app["application_id"])
            # Also check domain token of company name (e.g., "acme" from "Acme Corp")
            first_token = company.split()[0] if company else ""
            if len(first_token) >= 4 and f"@{first_token}." in combined:
                return str(app["application_id"])
        return None

    @staticmethod
    def _classify_thread(thread: GmailThread) -> str:
        latest = thread.messages[-1]
        text = f"{latest.subject} {latest.body}".lower()
        sender = latest.sender.lower()

        if any(phrase in text for phrase in ("unfortunately", "other candidates", "not moving forward", "regret to inform")):
            return "application_rejection"
        if any(phrase in text for phrase in ("thank you for applying", "received your application", "application confirmation")):
            return "application_receipt"
        if any(phrase in text for phrase in ("unsubscribe", "monthly newsletter", "talent community digest")):
            return "newsletter_broadcast"
        if any(phrase in text for phrase in ("candidate experience survey", "take our survey", "feedback on your application")):
            return "survey_request"
        if any(phrase in text for phrase in ("schedule", "calendly", "interview", "intro call", "chat this week")):
            return "interview_invitation"
        if "no-reply" in sender or "noreply" in sender:
            return "application_receipt"
        return "recruiter_outreach"
