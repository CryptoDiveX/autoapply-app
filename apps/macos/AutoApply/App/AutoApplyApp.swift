import Foundation

/// Main navigation destinations and menu-bar status model for AutoApply.app (P06 / AA-UX-001..003).
public struct NavigationModel: Equatable, Sendable {
    public enum Section: String, CaseIterable, Sendable {
        case today = "Today"
        case jobs = "Jobs"
        case applicationDetail = "Application detail"
        case profile = "Profile"
        case documents = "Documents"
        case inbox = "Inbox"
        case networking = "Networking"
        case settings = "Settings"
    }

    public enum MenuBarAction: String, CaseIterable, Sendable {
        case pause = "Pause"
        case resume = "Resume"
        case takeOver = "Take over"
        case openApp = "Open app"
        case stopSafely = "Stop safely"
        case emergencyStop = "Emergency stop"
        case quit = "Quit"
    }

    public enum StatusCopy: String, Sendable {
        case preparingDocuments = "Preparing documents"
        case awaitingUserAnswer = "Awaiting your answer"
        case submittedVerifyingReceipt = "Submitted — verifying receipt"
        case submissionUncertain = "Submission uncertain — checking before retry"
        case verifiedTealPending = "Application verified; Teal sync pending"
        case providerCreditUnavailable = "Provider credit unavailable"
        case browserEntitlementRenewal = "Browser entitlement needs renewal"
        case permissionRevoked = "Permission revoked"
        case platformAutomationNotPermitted = "Paused: platform does not permit this automation"
    }

    public var selectedSection: Section
    public var currentStatus: StatusCopy
    public var accessibilityVoiceOverEnabled: Bool

    public init(
        selectedSection: Section = .today,
        currentStatus: StatusCopy = .preparingDocuments,
        accessibilityVoiceOverEnabled: Bool = true
    ) {
        self.selectedSection = selectedSection
        self.currentStatus = currentStatus
        self.accessibilityVoiceOverEnabled = accessibilityVoiceOverEnabled
    }
}
