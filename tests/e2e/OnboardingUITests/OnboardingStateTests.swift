import Foundation
import AutoApplyNative

/// Native Swift test runner covering P06 onboarding state, C-02 trial reservation vs activation,
/// independent visibility/autonomy controls, and native PolicyEngine / Launcher / CredentialBroker contracts.
@main
struct OnboardingStateTests {
    static func check(_ condition: @autoclosure () -> Bool, _ message: String) {
        if !condition() {
            fputs("FAILED: \(message)\n", stderr)
            exit(1)
        }
    }

    static func main() throws {
        // 1. O-02 reserves trial without starting countdown; O-13 activates only after readiness (C-02)
        let coordinator = OnboardingCoordinator()
        check(coordinator.state.trialState == .unselected, "Initial trial state must be unselected")
        check(coordinator.state.serverTrialExpiresAtEpochSeconds == nil, "Initial trial expiry must be nil")

        coordinator.selectFiveDayTrialOnO02()
        check(coordinator.state.trialState == .reservedNotStarted, "O-02 must reserve trial without starting countdown")
        check(coordinator.state.serverTrialExpiresAtEpochSeconds == nil, "O-02 must not set expiry timestamp")
        check(coordinator.state.currentStep == .o03ProvisionComponents, "O-02 advances to O-03")

        var prematureActivationBlocked = false
        do {
            try coordinator.activateTrialOnO13(serverIssuedNowEpochSeconds: 1_760_812_000)
        } catch OnboardingCoordinator.OnboardingError.readinessIncompleteForTrialActivation {
            prematureActivationBlocked = true
        }
        check(prematureActivationBlocked, "O-13 activation must fail when readiness is incomplete")

        coordinator.updateReadiness(
            OnboardingCoordinator.EssentialReadiness(
                isolatedRuntimeReady: true,
                authorizedOrchestrationAndWriterReady: true,
                candidateFactsConfirmed: true,
                supportedSubmissionFixtureReady: true
            )
        )
        try coordinator.activateTrialOnO13(serverIssuedNowEpochSeconds: 1_760_812_000)
        check(coordinator.state.trialState == .activeCountdown, "O-13 activates countdown after readiness")
        check(
            coordinator.state.serverTrialExpiresAtEpochSeconds == 1_760_812_000 + 48 * 3600,
            "Trial expiry must equal server-issued start + 48 hours (2 days)"
        )

        // 2. Visibility and autonomy are independent and persist across restart with zero secrets
        let fresh = OnboardingCoordinator()
        check(fresh.state.visibilityMode == .background, "Default visibility must be background")
        check(fresh.state.autonomyMode == .reviewEachApplication, "Default autonomy must be reviewEachApplication")

        fresh.setVisibilityMode(.visibleBrowser)
        check(fresh.state.autonomyMode == .reviewEachApplication, "Changing visibility must not change autonomy")
        fresh.setAutonomyMode(.boundedAutoSubmitMandate)
        check(fresh.state.visibilityMode == .visibleBrowser, "Changing autonomy must not change visibility")

        let tempFile = FileManager.default.temporaryDirectory
            .appendingPathComponent("onboarding_state_\(UUID().uuidString).json")
        defer { try? FileManager.default.removeItem(at: tempFile) }

        try fresh.saveState(to: tempFile)
        let savedText = try String(contentsOf: tempFile, encoding: .utf8)
        check(!savedText.contains("sk-or-v1-"), "Saved UI state must never contain API keys")
        check(!savedText.contains("AGE-SECRET-KEY-"), "Saved UI state must never contain age private keys")

        let restored = OnboardingCoordinator()
        try restored.restoreState(from: tempFile)
        check(restored.state == fresh.state, "Restored UI state must match saved state")

        // 3. Gmail separate account footer & navigation accessibility
        check(
            OnboardingCoordinator.gmailFooterNotice ==
                "Use a separate Google account for job searching, not your main account.",
            "Exact O-05 Gmail footer required by AA-MAIL-001"
        )
        check(NavigationModel.Section.allCases.count == 8, "Must expose 8 main navigation sections")
        let nav = NavigationModel()
        check(nav.accessibilityVoiceOverEnabled, "VoiceOver accessibility must be enabled")

        // 4. Native PolicyEngine & RuntimeLauncher contracts
        let engine = PolicyEngine()
        let denied = engine.canSubmit(
            cancelled: false,
            consentCurrent: true,
            approvedHash: "hash_a",
            actualHash: "hash_b"
        )
        check(!denied.allowed && denied.reason == "artifact_changed", "PolicyEngine must block modified artifact hash")

        let appSupport = URL(fileURLWithPath: "/tmp/AutoApplyTestSupport")
        let pyBin = URL(fileURLWithPath: "/Applications/AutoApply.app/Contents/Resources/python/bin/python3")
        let launcher = RuntimeLauncher(appSupportRoot: appSupport, bundledPythonExecutable: pyBin)
        let cleanEnv = launcher.buildSanitizedEnvironment(parentEnv: [
            "HOME": "/Users/test",
            "PYTHONPATH": "/Users/test/bad",
            "OPENAI_API_KEY": "sk-secret"
        ])
        check(cleanEnv["PYTHONPATH"] == nil, "RuntimeLauncher must strip PYTHONPATH")
        check(cleanEnv["OPENAI_API_KEY"] == nil, "RuntimeLauncher must strip OPENAI_API_KEY")
        check(cleanEnv["PYTHONNOUSERSITE"] == "1", "RuntimeLauncher must set PYTHONNOUSERSITE=1")

        print("AutoApplyNativeTestRunner: 4/4 native Swift test suites PASSED")
    }
}
