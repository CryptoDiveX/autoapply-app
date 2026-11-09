"""Security tests for the 10-step PolicyBroker outbound gate and prompt-injection defense (P09).

Covers: AA-DOC-004, AA-JOB-005..007, AA-MAIL-005, NFR-02, C-09, C-10
Scenarios: T-DOC-03, T-JOB-04, T-JOB-08, T-MAIL-05, T-SEC-05
"""

from __future__ import annotations

from autoapply.policy import (
    OutboundProposalContext,
    PolicyBroker,
    can_submit,
    validate_target_url_and_fields,
)


def test_changed_artifact_revokes_submission() -> None:
    """07-IMPLEMENTATION-PLAN.md (§8) / T-DOC-03: Changed artifact hash blocks submission."""
    decision = can_submit(
        approved_hash="approved_example",
        actual_hash="changed_example",
        consent_current=True,
        cancelled=False,
    )
    assert decision.allowed is False
    assert decision.reason == "artifact_changed"


def test_ten_step_policy_decision_order_enforced_deterministically() -> None:
    """02-TECHNICAL-SPECIFICATION.md (§5): Verify strict 10-step policy precedence order."""
    broker = PolicyBroker()

    base = OutboundProposalContext(
        cancelled=False,
        platform_permissions_granted=True,
        account_identity_matches=True,
        licence_active=True,
        consent_current=True,
        mandate_revision_matches=True,
        facts_all_confirmed=True,
        approved_hash="sha256_good_doc",
        actual_hash="sha256_good_doc",
        target_domain_allowed=True,
        recipient_hard_bounced=False,
        dedupe_reservation_held=True,
        within_spend_and_rate_limits=True,
    )
    assert broker.evaluate(base).allowed is True
    assert broker.evaluate(base).reason == "authorized"

    # 1. Cancellation outranks everything else
    ctx_cancel = OutboundProposalContext(**{**base.__dict__, "cancelled": True, "licence_active": False})
    assert broker.evaluate(ctx_cancel).reason == "run_cancelled"

    # 2. Platform permissions
    ctx_perm = OutboundProposalContext(**{**base.__dict__, "platform_permissions_granted": False})
    assert broker.evaluate(ctx_perm).reason == "platform_permission_denied"

    # 3. Installation / account ownership
    ctx_acct = OutboundProposalContext(**{**base.__dict__, "account_identity_matches": False})
    assert broker.evaluate(ctx_acct).reason == "account_identity_mismatch"

    # 4. Licence policy (AA-LIC-003)
    ctx_lic = OutboundProposalContext(**{**base.__dict__, "licence_active": False})
    assert broker.evaluate(ctx_lic).reason == "licence_expired_or_invalid"

    # 5. User mandate / approval revision (T-JOB-08)
    ctx_mandate = OutboundProposalContext(**{**base.__dict__, "mandate_revision_matches": False})
    assert broker.evaluate(ctx_mandate).reason == "consent_missing_or_revoked"

    # 6. Truthful confirmed facts (T-JOB-04)
    ctx_facts = OutboundProposalContext(**{**base.__dict__, "facts_all_confirmed": False})
    assert broker.evaluate(ctx_facts).reason == "unconfirmed_truth_sensitive_facts"

    # 7. Artifact approval hash (T-DOC-03)
    ctx_hash = OutboundProposalContext(**{**base.__dict__, "actual_hash": "sha256_tampered"})
    assert broker.evaluate(ctx_hash).reason == "artifact_changed"

    # 8. Domain allowlist & hard-bounce suppression (T-MAIL-05)
    ctx_bounce = OutboundProposalContext(**{**base.__dict__, "recipient_hard_bounced": True})
    assert broker.evaluate(ctx_bounce).reason == "recipient_hard_bounced"

    # 9. Dedupe reservation (T-JOB-02)
    ctx_dedupe = OutboundProposalContext(**{**base.__dict__, "dedupe_reservation_held": False})
    assert broker.evaluate(ctx_dedupe).reason == "dedupe_reservation_missing"

    # 10. Spending / rate limits (T-MODEL-03)
    ctx_spend = OutboundProposalContext(**{**base.__dict__, "within_spend_and_rate_limits": False})
    assert broker.evaluate(ctx_spend).reason == "spend_or_rate_limit_exceeded"


def test_blocks_localhost_private_network_ssrf_and_suspicious_financial_fields() -> None:
    """C-09 / T-SEC-05: Reject localhost/private IPs and escalate bank/payment/SSN fields."""
    # Private/loopback destinations are blocked
    for bad_url in (
        "http://127.0.0.1:8080/admin",
        "https://localhost/internal",
        "https://192.168.1.10/apply",
        "https://10.0.0.5/upload",
        "file:///etc/passwd",
    ):
        decision = validate_target_url_and_fields(
            target_url=bad_url,
            allowed_domains={"boards.greenhouse.io"},
            requested_field_labels=["First Name", "Email"],
        )
        assert decision.allowed is False
        assert decision.reason == "forbidden_target_origin_or_ssrf"

    # Suspicious bank / wire / SSN / passport number fields pause for explicit human review
    decision_sensitive = validate_target_url_and_fields(
        target_url="https://boards.greenhouse.io/example/jobs/1",
        allowed_domains={"boards.greenhouse.io"},
        requested_field_labels=["First Name", "Bank Routing Number", "Social Security Number"],
    )
    assert decision_sensitive.allowed is False
    assert decision_sensitive.reason == "suspicious_sensitive_field_requires_human_review"
