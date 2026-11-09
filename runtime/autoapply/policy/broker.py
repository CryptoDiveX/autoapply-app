"""Deterministic 10-step PolicyBroker outbound gate and SSRF/sensitive-field guard (P09).

Enforces 02-TECHNICAL-SPECIFICATION.md (§5), AA-DOC-004, AA-JOB-005..007, AA-MAIL-005, NFR-02, C-09:
1. Cancellation
2. Platform permissions
3. Installation / account ownership
4. Licence policy
5. User mandate / approval
6. Truthful confirmed facts
7. Artifact approval hash
8. Domain / recipient allowlist (including hard-bounce suppression & SSRF block)
9. Dedupe reservation
10. Spending / rate limits
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from urllib.parse import urlparse


SUSPICIOUS_SENSITIVE_FIELD_KEYWORDS: tuple[str, ...] = (
    "social security",
    "ssn",
    "bank routing",
    "bank account",
    "iban",
    "swift code",
    "credit card",
    "cvv",
    "passport number",
    "driver's license",
    "drivers license",
    "wire transfer",
)


@dataclass(frozen=True)
class PolicyDecision:
    """Outcome of a deterministic policy evaluation."""

    allowed: bool
    reason: str


@dataclass(frozen=True)
class OutboundProposalContext:
    """Full 10-step evaluation inputs for an outbound privileged action."""

    cancelled: bool = False
    platform_permissions_granted: bool = True
    account_identity_matches: bool = True
    licence_active: bool = True
    consent_current: bool = True
    mandate_revision_matches: bool = True
    facts_all_confirmed: bool = True
    approved_hash: str = ""
    actual_hash: str = ""
    target_domain_allowed: bool = True
    recipient_hard_bounced: bool = False
    dedupe_reservation_held: bool = True
    within_spend_and_rate_limits: bool = True


class PolicyBroker:
    """Evaluates privileged proposals in strict 10-step order outside model discretion."""

    def evaluate(self, ctx: OutboundProposalContext) -> PolicyDecision:
        # 1. Cancellation
        if ctx.cancelled:
            return PolicyDecision(allowed=False, reason="run_cancelled")

        # 2. Platform permissions
        if not ctx.platform_permissions_granted:
            return PolicyDecision(allowed=False, reason="platform_permission_denied")

        # 3. Installation / account ownership
        if not ctx.account_identity_matches:
            return PolicyDecision(allowed=False, reason="account_identity_mismatch")

        # 4. Licence policy
        if not ctx.licence_active:
            return PolicyDecision(allowed=False, reason="licence_expired_or_invalid")

        # 5. User mandate / approval
        if not ctx.consent_current or not ctx.mandate_revision_matches:
            return PolicyDecision(allowed=False, reason="consent_missing_or_revoked")

        # 6. Truthful confirmed facts
        if not ctx.facts_all_confirmed:
            return PolicyDecision(allowed=False, reason="unconfirmed_truth_sensitive_facts")

        # 7. Artifact approval hash
        if not ctx.approved_hash or ctx.approved_hash != ctx.actual_hash:
            return PolicyDecision(allowed=False, reason="artifact_changed")

        # 8. Domain / recipient allowlist & bounce suppression
        if ctx.recipient_hard_bounced:
            return PolicyDecision(allowed=False, reason="recipient_hard_bounced")
        if not ctx.target_domain_allowed:
            return PolicyDecision(allowed=False, reason="domain_or_recipient_blocked")

        # 9. Dedupe reservation
        if not ctx.dedupe_reservation_held:
            return PolicyDecision(allowed=False, reason="dedupe_reservation_missing")

        # 10. Spending / rate limits
        if not ctx.within_spend_and_rate_limits:
            return PolicyDecision(allowed=False, reason="spend_or_rate_limit_exceeded")

        return PolicyDecision(allowed=True, reason="authorized")


def can_submit(
    *,
    approved_hash: str,
    actual_hash: str,
    consent_current: bool,
    cancelled: bool,
    platform_permissions_granted: bool = True,
    account_identity_matches: bool = True,
    licence_active: bool = True,
    mandate_revision_matches: bool = True,
    facts_all_confirmed: bool = True,
    target_domain_allowed: bool = True,
    recipient_hard_bounced: bool = False,
    dedupe_reservation_held: bool = True,
    within_spend_and_rate_limits: bool = True,
) -> PolicyDecision:
    """Convenience gate matching 07-IMPLEMENTATION-PLAN.md (§8) TDD contract."""
    broker = PolicyBroker()
    return broker.evaluate(
        OutboundProposalContext(
            cancelled=cancelled,
            platform_permissions_granted=platform_permissions_granted,
            account_identity_matches=account_identity_matches,
            licence_active=licence_active,
            consent_current=consent_current,
            mandate_revision_matches=mandate_revision_matches,
            facts_all_confirmed=facts_all_confirmed,
            approved_hash=approved_hash,
            actual_hash=actual_hash,
            target_domain_allowed=target_domain_allowed,
            recipient_hard_bounced=recipient_hard_bounced,
            dedupe_reservation_held=dedupe_reservation_held,
            within_spend_and_rate_limits=within_spend_and_rate_limits,
        )
    )


def _is_private_or_loopback_host(hostname: str) -> bool:
    lower = hostname.lower().strip("[]")
    if lower in ("localhost", "localhost.localdomain") or lower.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(lower)
        return (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        return False


def validate_target_url_and_fields(
    *,
    target_url: str,
    allowed_domains: set[str],
    requested_field_labels: list[str],
) -> PolicyDecision:
    """Enforces C-09 target origin validation (SSRF/local file block) and sensitive-field escalation."""
    parsed = urlparse(target_url)
    if parsed.scheme != "https" or not parsed.hostname:
        return PolicyDecision(allowed=False, reason="forbidden_target_origin_or_ssrf")

    host = parsed.hostname.lower()
    if _is_private_or_loopback_host(host) or host not in {d.lower() for d in allowed_domains}:
        return PolicyDecision(allowed=False, reason="forbidden_target_origin_or_ssrf")

    for label in requested_field_labels:
        normalized = label.lower()
        if any(keyword in normalized for keyword in SUSPICIOUS_SENSITIVE_FIELD_KEYWORDS):
            return PolicyDecision(
                allowed=False,
                reason="suspicious_sensitive_field_requires_human_review",
            )

    return PolicyDecision(allowed=True, reason="authorized")
