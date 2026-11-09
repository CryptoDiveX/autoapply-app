import Foundation

/// Native macOS PolicyBroker evaluating outbound actions in deterministic 10-step order (P09).
///
/// Order:
/// 1. Cancellation -> 2. Platform permissions -> 3. Account ownership -> 4. Licence policy ->
/// 5. User mandate/approval -> 6. Truthful confirmed facts -> 7. Artifact hash approval ->
/// 8. Domain/recipient allowlist -> 9. Dedupe reservation -> 10. Spending/rate limits.
public final class PolicyEngine: Sendable {
    public struct Decision: Equatable, Sendable {
        public let allowed: Bool
        public let reason: String

        public init(allowed: Bool, reason: String) {
            self.allowed = allowed
            self.reason = reason
        }
    }

    public init() {}

    public func canSubmit(
        cancelled: Bool,
        platformPermissionsGranted: Bool = true,
        accountIdentityMatches: Bool = true,
        licenceActive: Bool = true,
        consentCurrent: Bool,
        factsConfirmed: Bool = true,
        approvedHash: String,
        actualHash: String,
        domainAllowed: Bool = true,
        dedupeReserved: Bool = true,
        withinSpendLimit: Bool = true
    ) -> Decision {
        if cancelled { return Decision(allowed: false, reason: "run_cancelled") }
        if !platformPermissionsGranted { return Decision(allowed: false, reason: "platform_permission_denied") }
        if !accountIdentityMatches { return Decision(allowed: false, reason: "account_identity_mismatch") }
        if !licenceActive { return Decision(allowed: false, reason: "licence_expired_or_invalid") }
        if !consentCurrent { return Decision(allowed: false, reason: "consent_missing_or_revoked") }
        if !factsConfirmed { return Decision(allowed: false, reason: "unconfirmed_truth_sensitive_facts") }
        if approvedHash.isEmpty || approvedHash != actualHash {
            return Decision(allowed: false, reason: "artifact_changed")
        }
        if !domainAllowed { return Decision(allowed: false, reason: "domain_or_recipient_blocked") }
        if !dedupeReserved { return Decision(allowed: false, reason: "dedupe_reservation_missing") }
        if !withinSpendLimit { return Decision(allowed: false, reason: "spend_or_rate_limit_exceeded") }
        return Decision(allowed: true, reason: "authorized")
    }
}
