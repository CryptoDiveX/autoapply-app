"""Mail reply suppression policy and durable hard-bounce no-send register (AA-MAIL-003, AA-MAIL-004, C-06)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


NON_REPLY_CLASSIFICATIONS = frozenset(
    {
        "application_rejection",
        "application_receipt",
        "newsletter_broadcast",
        "survey_request",
    }
)


class NoSendRegister:
    """Durable SQLite register of hard-bounced email addresses that must never be retried."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hard_bounce_no_send (
                email TEXT PRIMARY KEY,
                application_id TEXT NOT NULL,
                smtp_diagnostic TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def record_hard_bounce(self, email: str, application_id: str, smtp_diagnostic: str) -> None:
        normalized = email.strip().lower()
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO hard_bounce_no_send (email, application_id, smtp_diagnostic, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                (normalized, application_id, smtp_diagnostic, now),
            )

    def is_blocked(self, email: str) -> bool:
        normalized = email.strip().lower()
        row = self._conn.execute(
            "SELECT 1 FROM hard_bounce_no_send WHERE email = ?",
            (normalized,),
        ).fetchone()
        return row is not None


@dataclass(frozen=True)
class InboundMailDecision:
    classification: str
    auto_reply_allowed: bool
    create_user_action: bool
    action_type: str | None
    direct_mailbox_url: str


@dataclass(frozen=True)
class HardBounceDecision:
    application_id: str
    bounced_recipient: str
    application_status_update: str


class MailPolicyEngine:
    """Enforces no auto-replies to automated mail and creates user Actions for human responses."""

    def __init__(self, no_send_register: NoSendRegister) -> None:
        self._register = no_send_register

    def evaluate_inbound(
        self,
        *,
        classification: str,
        sender: str,
        thread_id: str,
        application_id: str,
    ) -> InboundMailDecision:
        direct_url = f"https://mail.google.com/mail/u/0/#all/{thread_id}"
        if classification in NON_REPLY_CLASSIFICATIONS:
            return InboundMailDecision(
                classification=classification,
                auto_reply_allowed=False,
                create_user_action=False,
                action_type=None,
                direct_mailbox_url=direct_url,
            )
        return InboundMailDecision(
            classification=classification,
            auto_reply_allowed=False,
            create_user_action=True,
            action_type="respond_to_recruiter",
            direct_mailbox_url=direct_url,
        )

    def process_hard_bounce(
        self,
        *,
        application_id: str,
        bounced_recipient: str,
        smtp_diagnostic: str,
    ) -> HardBounceDecision:
        self._register.record_hard_bounce(bounced_recipient, application_id, smtp_diagnostic)
        return HardBounceDecision(
            application_id=application_id,
            bounced_recipient=bounced_recipient.strip().lower(),
            application_status_update="bounce_detected",
        )

    def assert_outbound_allowed(self, recipient: str) -> None:
        if self._register.is_blocked(recipient):
            raise PermissionError(
                f"NO_SEND_HARD_BOUNCE: recipient '{recipient}' is permanently blocked due to prior hard bounce"
            )
