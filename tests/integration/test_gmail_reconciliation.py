"""Integration tests for Gmail thread reconciliation, mail policy, Teal outbox, and LinkedIn drafts.

Covers:
- T-MAIL-01: Unrelated personal mail, unread state, stars, and user labels are untouched.
- T-MAIL-03: Rejections, receipts, broadcasts, surveys, and recruiter replies are classified accurately.
- T-MAIL-04: Zero auto-replies to rejections/receipts/broadcasts/surveys; human replies/scheduling/ambiguity become user Actions.
- T-MAIL-05: Hard bounces update application record and populate durable no-send register.
- T-TRACK-01: Local durable outbox commits before external Teal sync; transient error retries idempotently.
- T-TRACK-02: Teal sync requires exact record/URL/account match, preserves sibling notes, and reads back fields.
- T-SOC-01 / T-SOC-02: LinkedIn outreach drafts require explicit approval and cancel follow-up reminders when a reply arrives.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autoapply.connectors.gmail import GmailConnector, GmailMessage, GmailThread
from autoapply.connectors.mail_policy import MailPolicyEngine, NoSendRegister
from autoapply.connectors.networking import LinkedInNetworkingManager
from autoapply.connectors.teal import TealAdapter, TealRecord
from autoapply.engine.sync_outbox import DurableSyncOutbox


def test_gmail_thread_correlation_preserves_personal_mail_and_classifies_threads() -> None:
    """T-MAIL-01 & T-MAIL-03: Personal mail untouched; application threads correlated across Inbox/Sent/labels."""
    threads = [
        GmailThread(
            thread_id="th_personal_01",
            messages=[
                GmailMessage(
                    message_id="msg_p1",
                    sender="mom@example.com",
                    recipient="jane@example.com",
                    subject="Weekend family dinner",
                    body="Are you free Sunday at 6pm?",
                    folder="INBOX",
                )
            ],
            unread=True,
            starred=True,
            user_labels=["Family", "Important"],
        ),
        GmailThread(
            thread_id="th_receipt_01",
            messages=[
                GmailMessage(
                    message_id="msg_r1",
                    sender="no-reply@greenhouse.io",
                    recipient="jane@example.com",
                    subject="Thank you for applying to Acme Corp - Senior Staff Backend Engineer",
                    body="We have received your application for Senior Staff Backend Engineer at Acme Corp.",
                    folder="INBOX",
                )
            ],
            unread=True,
            starred=False,
            user_labels=["CustomJobLabel"],
        ),
        GmailThread(
            thread_id="th_reject_01",
            messages=[
                GmailMessage(
                    message_id="msg_rej1",
                    sender="careers@globex.com",
                    recipient="jane@example.com",
                    subject="Update on your application with Globex",
                    body="Unfortunately, we have decided to move forward with other candidates at this time.",
                    folder="INBOX",
                )
            ],
            unread=True,
            starred=False,
            user_labels=[],
        ),
        GmailThread(
            thread_id="th_human_01",
            messages=[
                GmailMessage(
                    message_id="msg_h1",
                    sender="jane@example.com",
                    recipient="sarah.recruiter@acme.com",
                    subject="Following up on Senior Staff Backend Engineer application",
                    body="Hi Sarah, excited about the role at Acme Corp.",
                    folder="SENT",
                ),
                GmailMessage(
                    message_id="msg_h2",
                    sender="sarah.recruiter@acme.com",
                    recipient="jane@example.com",
                    subject="Re: Following up on Senior Staff Backend Engineer application",
                    body="Hi Jane! Would love to schedule a 30-minute intro call this week. Please pick a time on my Calendly.",
                    folder="INBOX",
                ),
            ],
            unread=True,
            starred=True,
            user_labels=["Starred-Recruiter"],
        ),
    ]

    connector = GmailConnector(account_email="jane@example.com")
    reconciled = connector.reconcile_threads(
        threads=threads,
        tracked_applications=[
            {"application_id": "app_acme", "company_name": "Acme Corp", "job_title": "Senior Staff Backend Engineer"},
            {"application_id": "app_globex", "company_name": "Globex", "job_title": "Platform Lead"},
        ],
    )

    # Personal thread must be completely untouched (unread, starred, labels preserved) and ignored
    assert "th_personal_01" not in reconciled
    personal = threads[0]
    assert personal.unread is True
    assert personal.starred is True
    assert personal.user_labels == ["Family", "Important"]

    # Application threads correlated and classified
    assert reconciled["th_receipt_01"].classification == "application_receipt"
    assert reconciled["th_receipt_01"].application_id == "app_acme"
    # Existing unread state, stars, and custom labels preserved!
    assert threads[1].unread is True
    assert "CustomJobLabel" in threads[1].user_labels

    assert reconciled["th_reject_01"].classification == "application_rejection"
    assert reconciled["th_reject_01"].application_id == "app_globex"

    assert reconciled["th_human_01"].classification == "interview_invitation"
    assert reconciled["th_human_01"].application_id == "app_acme"
    assert reconciled["th_human_01"].direct_mailbox_url == "https://mail.google.com/mail/u/0/#all/th_human_01"
    assert threads[3].unread is True
    assert threads[3].starred is True


def test_mail_policy_blocks_auto_reply_and_registers_hard_bounces(tmp_path: Path) -> None:
    """T-MAIL-04 & T-MAIL-05: Never auto-reply to rejections/receipts/broadcasts/surveys; hard bounces block future sends."""
    register = NoSendRegister(tmp_path / "no_send.sqlite3")
    policy = MailPolicyEngine(no_send_register=register)

    for non_reply_class in ("application_rejection", "application_receipt", "newsletter_broadcast", "survey_request"):
        decision = policy.evaluate_inbound(
            classification=non_reply_class,
            sender="no-reply@acme.com",
            thread_id=f"th_{non_reply_class}",
            application_id="app_acme",
        )
        assert decision.auto_reply_allowed is False
        assert decision.create_user_action is False

    # Real human reply / interview invitation / ambiguous message creates user Action without auto-sending
    human_decision = policy.evaluate_inbound(
        classification="interview_invitation",
        sender="sarah.recruiter@acme.com",
        thread_id="th_human_01",
        application_id="app_acme",
    )
    assert human_decision.auto_reply_allowed is False
    assert human_decision.create_user_action is True
    assert human_decision.action_type == "respond_to_recruiter"
    assert human_decision.direct_mailbox_url == "https://mail.google.com/mail/u/0/#all/th_human_01"

    # Hard bounce updates application status and registers address in durable no-send register
    bounce_decision = policy.process_hard_bounce(
        application_id="app_acme",
        bounced_recipient="old.recruiter@acme.com",
        smtp_diagnostic="550 5.1.1 <old.recruiter@acme.com>: User unknown",
    )
    assert bounce_decision.application_status_update == "bounce_detected"
    assert register.is_blocked("old.recruiter@acme.com") is True

    with pytest.raises(PermissionError, match="NO_SEND_HARD_BOUNCE"):
        policy.assert_outbound_allowed("old.recruiter@acme.com")


def test_teal_durable_outbox_and_exact_record_matching(tmp_path: Path) -> None:
    """T-TRACK-01 & T-TRACK-02: Outbox persists before sync, retries cleanly, preserves user notes, and verifies post-write."""
    outbox = DurableSyncOutbox(tmp_path / "sync_outbox.sqlite3")
    teal = TealAdapter(authenticated_account="jane@example.com")

    # Seed two sibling Teal records
    teal.seed_record(
        TealRecord(
            record_id="teal_rec_01",
            account_email="jane@example.com",
            company_name="Acme Corp",
            job_title="Senior Staff Backend Engineer",
            canonical_url="https://boards.greenhouse.io/acme/jobs/101",
            status="Bookmarked",
            notes="User manual note: Referral from Alex.",
        )
    )
    teal.seed_record(
        TealRecord(
            record_id="teal_rec_02",
            account_email="jane@example.com",
            company_name="Sibling Co",
            job_title="Principal Engineer",
            canonical_url="https://jobs.lever.co/sibling/202",
            status="Applied",
            notes="Keep this sibling record untouched.",
        )
    )

    # Enqueue sync in durable outbox BEFORE external call
    entry_id = outbox.enqueue(
        application_id="app_acme",
        target_system="teal",
        payload={
            "record_id": "teal_rec_01",
            "account_email": "jane@example.com",
            "company_name": "Acme Corp",
            "job_title": "Senior Staff Backend Engineer",
            "canonical_url": "https://boards.greenhouse.io/acme/jobs/101",
            "status": "Applied",
            "autoapply_note": "Submitted via AutoApply confirmation #GH-991",
        },
    )
    assert outbox.get_entry(entry_id)["status"] == "pending"

    # Simulate transient Teal failure on first attempt: outbox remains pending_retry
    teal.set_Simulated_failure(True)
    with pytest.raises(RuntimeError, match="TEAL_TRANSIENT_FAILURE"):
        outbox.process_entry(entry_id, teal)
    assert outbox.get_entry(entry_id)["status"] == "pending_retry"
    assert outbox.get_entry(entry_id)["attempts"] == 1

    # Restore Teal and retry idempotently
    teal.set_Simulated_failure(False)
    outbox.process_entry(entry_id, teal)
    assert outbox.get_entry(entry_id)["status"] == "synced"

    # Verify user notes preserved and sibling record untouched
    updated = teal.get_record("teal_rec_01")
    assert updated.status == "Applied"
    assert "User manual note: Referral from Alex." in updated.notes
    assert "Submitted via AutoApply confirmation #GH-991" in updated.notes

    sibling = teal.get_record("teal_rec_02")
    assert sibling.notes == "Keep this sibling record untouched."

    # Mismatched account or canonical URL must fail closed
    with pytest.raises(PermissionError, match="TEAL_IDENTITY_OR_URL_MISMATCH"):
        teal.update_record(
            record_id="teal_rec_01",
            account_email="wrong@example.com",
            canonical_url="https://boards.greenhouse.io/acme/jobs/101",
            status="Interviewing",
            autoapply_note="Should fail",
        )


def test_linkedin_drafts_require_approval_and_cancel_followup_on_reply() -> None:
    """T-SOC-01 & T-SOC-02: LinkedIn drafts never auto-send without approval; follow-up reminder cancels when reply arrives."""
    mgr = LinkedInNetworkingManager()
    ranked = mgr.rank_contacts(
        [
            {"contact_id": "c_peer", "name": "Dev Peer", "relationship": "2nd_degree_peer"},
            {"contact_id": "c_hm", "name": "Eng Director", "relationship": "hiring_manager"},
            {"contact_id": "c_mut", "name": "Warm Mutual", "relationship": "1st_degree_mutual"},
        ]
    )
    assert [c["contact_id"] for c in ranked] == ["c_mut", "c_hm", "c_peer"]

    draft = mgr.create_outreach_draft(
        application_id="app_acme",
        contact_id="c_mut",
        message_body="Hi Warm Mutual, I just applied for the Senior Staff Backend Engineer role at Acme Corp.",
        follow_up_business_days=5,
    )
    assert draft.status == "pending_user_approval"

    with pytest.raises(PermissionError, match="LINKEDIN_APPROVAL_REQUIRED"):
        mgr.send_message(draft.draft_id, user_approved=False)

    sent = mgr.send_message(draft.draft_id, user_approved=True)
    assert sent.status == "sent"
    assert mgr.is_follow_up_due(draft.draft_id, elapsed_business_days=5) is True

    # Once a reply or status change is recorded, follow-up reminder is suppressed
    mgr.record_reply_or_status_change(draft.draft_id, reason="recipient_replied")
    assert mgr.is_follow_up_due(draft.draft_id, elapsed_business_days=5) is False
