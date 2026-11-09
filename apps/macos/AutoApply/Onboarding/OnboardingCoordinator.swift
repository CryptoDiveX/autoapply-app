import Foundation

/// Native macOS Onboarding & Operating Controls state coordinator (P06).
///
/// Enforces:
/// - 13 resumable onboarding steps (`O-01`..`O-13`) from `03-ONBOARDING-AND-NATIVE-UX.md`.
/// - `C-02`: Selecting trial on `O-02` reserves the path without starting the 120-hour clock;
///   explicit trial activation on `O-13` requires essential readiness checks to pass first.
/// - `AA-UX-001`..`002`: Visibility (`background`, `visibleBrowser`, `userTakeover`) is independent
///   from Autonomy (`draftOnly`, `reviewEachApplication`, `boundedAutoSubmitMandate`).
/// - `AA-MAIL-001`: Exact separate Google account warning footer on `O-05`.
/// - Zero secrets persisted in saved UI state (`T-SEC-02`).
public final class OnboardingCoordinator {
    public enum Step: String, CaseIterable, Codable, Sendable {
        case o01WelcomeAndTrust = "O-01"
        case o02LicenceOrTrial = "O-02"
        case o03ProvisionComponents = "O-03"
        case o04AIConnection = "O-04"
        case o05Gmail = "O-05"
        case o06CapSolver = "O-06"
        case o07TealAndLinkedIn = "O-07"
        case o08MacPermissions = "O-08"
        case o09ImportResume = "O-09"
        case o10TargetPreferences = "O-10"
        case o11GuidedInterview = "O-11"
        case o12DocumentsAndPolicy = "O-12"
        case o13ReadinessAndFirstJob = "O-13"
    }

    public enum VisibilityMode: String, Codable, Sendable {
        case background
        case visibleBrowser = "visible_browser"
        case userTakeover = "user_takeover"
    }

    public enum AutonomyMode: String, Codable, Sendable {
        case draftOnly = "draft_only"
        case reviewEachApplication = "review_each_application"
        case boundedAutoSubmitMandate = "bounded_auto_submit_mandate"
    }

    public enum TrialState: String, Codable, Sendable {
        case unselected
        case reservedNotStarted = "reserved_not_started"
        case activeCountdown = "active_countdown"
        case paidKeyActive = "paid_key_active"
        case expiredReadOnly = "expired_read_only"
    }

    public struct EssentialReadiness: Codable, Equatable, Sendable {
        public var isolatedRuntimeReady: Bool
        public var authorizedOrchestrationAndWriterReady: Bool
        public var candidateFactsConfirmed: Bool
        public var supportedSubmissionFixtureReady: Bool

        public init(
            isolatedRuntimeReady: Bool = false,
            authorizedOrchestrationAndWriterReady: Bool = false,
            candidateFactsConfirmed: Bool = false,
            supportedSubmissionFixtureReady: Bool = false
        ) {
            self.isolatedRuntimeReady = isolatedRuntimeReady
            self.authorizedOrchestrationAndWriterReady = authorizedOrchestrationAndWriterReady
            self.candidateFactsConfirmed = candidateFactsConfirmed
            self.supportedSubmissionFixtureReady = supportedSubmissionFixtureReady
        }

        public var isReadyForTrialActivation: Bool {
            isolatedRuntimeReady &&
            authorizedOrchestrationAndWriterReady &&
            candidateFactsConfirmed &&
            supportedSubmissionFixtureReady
        }
    }

    public struct PersistedUIState: Codable, Equatable, Sendable {
        public var currentStep: Step
        public var completedSteps: [Step]
        public var trialState: TrialState
        public var serverTrialExpiresAtEpochSeconds: Int64?
        public var visibilityMode: VisibilityMode
        public var autonomyMode: AutonomyMode
        public var documentMode: String
        public var openRouterConfigured: Bool
        public var readiness: EssentialReadiness
    }

    public enum OnboardingError: Error, Equatable {
        case readinessIncompleteForTrialActivation
        case trialNotReserved
        case secretValueForbiddenInUIState
    }

    public static let gmailFooterNotice =
        "Use a separate Google account for job searching, not your main account."

    public static let trialDurationSeconds: Int64 = 48 * 3600

    public private(set) var state: PersistedUIState

    public init() {
        self.state = PersistedUIState(
            currentStep: .o01WelcomeAndTrust,
            completedSteps: [],
            trialState: .unselected,
            serverTrialExpiresAtEpochSeconds: nil,
            visibilityMode: .background,
            autonomyMode: .reviewEachApplication,
            documentMode: "tailored_approved",
            openRouterConfigured: false,
            readiness: EssentialReadiness()
        )
    }

    /// O-02: Reserves the 2-day free trial path WITHOUT starting the 48-hour countdown (`C-02`).
    public func selectTwoDayTrialOnO02() {
        state.trialState = .reservedNotStarted
        state.serverTrialExpiresAtEpochSeconds = nil
        markStepCompleted(.o02LicenceOrTrial)
        state.currentStep = .o03ProvisionComponents
    }

    /// Legacy alias for O-02 trial reservation.
    public func selectFiveDayTrialOnO02() {
        selectTwoDayTrialOnO02()
    }

    /// O-13: Explicitly activates the server-issued 48-hour (2-day) trial only after readiness passes (`C-02`).
    public func activateTrialOnO13(serverIssuedNowEpochSeconds: Int64) throws {
        guard state.trialState == .reservedNotStarted else {
            throw OnboardingError.trialNotReserved
        }
        guard state.readiness.isReadyForTrialActivation else {
            throw OnboardingError.readinessIncompleteForTrialActivation
        }
        state.trialState = .activeCountdown
        state.serverTrialExpiresAtEpochSeconds = serverIssuedNowEpochSeconds + Self.trialDurationSeconds
        markStepCompleted(.o13ReadinessAndFirstJob)
    }

    public func updateReadiness(_ readiness: EssentialReadiness) {
        state.readiness = readiness
    }

    public func setVisibilityMode(_ mode: VisibilityMode) {
        state.visibilityMode = mode
    }

    public func setAutonomyMode(_ mode: AutonomyMode) {
        state.autonomyMode = mode
    }

    public func advanceTo(_ step: Step) {
        markStepCompleted(state.currentStep)
        state.currentStep = step
    }

    public func saveState(to fileURL: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(state)
        let jsonString = String(decoding: data, as: UTF8.self)
        if jsonString.contains("sk-or-v1-") || jsonString.contains("AGE-SECRET-KEY-") || jsonString.contains("CAP-") {
            throw OnboardingError.secretValueForbiddenInUIState
        }
        try data.write(to: fileURL, options: .atomic)
    }

    public func restoreState(from fileURL: URL) throws {
        let data = try Data(contentsOf: fileURL)
        self.state = try JSONDecoder().decode(PersistedUIState.self, from: data)
    }

    private func markStepCompleted(_ step: Step) {
        if !state.completedSteps.contains(step) {
            state.completedSteps.append(step)
        }
    }
}
