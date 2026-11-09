// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AutoApplyNative",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .library(
            name: "AutoApplyNative",
            targets: ["AutoApplyNative"]
        ),
        .executable(
            name: "AutoApply",
            targets: ["AutoApply"]
        ),
        .executable(
            name: "AutoApplyNativeTestRunner",
            targets: ["AutoApplyNativeTestRunner"]
        )
    ],
    targets: [
        .target(
            name: "AutoApplyNative",
            path: ".",
            exclude: [
                "README.md",
                "Makefile",
                "pyproject.toml",
                "docs",
                "packaging",
                "runtime",
                "schemas",
                "services",
                "tests",
                "web",
                "dist",
                "apps/macos/AutoApply/Executable"
            ],
            sources: [
                "native/CredentialBroker/CredentialBroker.swift",
                "native/RuntimeSupervisor/Launcher.swift",
                "native/IPC/IPCChannel.swift",
                "native/PolicyBroker/PolicyEngine.swift",
                "apps/macos/AutoApply/Onboarding/OnboardingCoordinator.swift",
                "apps/macos/AutoApply/App/AutoApplyApp.swift"
            ]
        ),
        .executableTarget(
            name: "AutoApply",
            dependencies: ["AutoApplyNative"],
            path: "apps/macos/AutoApply/Executable"
        ),
        .executableTarget(
            name: "AutoApplyNativeTestRunner",
            dependencies: ["AutoApplyNative"],
            path: "tests/e2e/OnboardingUITests"
        )
    ]
)
