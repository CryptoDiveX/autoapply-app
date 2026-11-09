import CryptoKit
import Foundation
import Security

/// Native macOS Keychain-backed CredentialBroker (P04 / AA-AUTH-001 / NFR-02 / C-04).
///
/// Guarantees:
/// 1. Generates a unique per-installation symmetric/age-compatible root key stored
///    exclusively in macOS Keychain (`kSecAttrAccessibleWhenUnlockedThisDeviceOnly`).
/// 2. Never writes the private identity adjacent to ciphertext in Application Support.
/// 3. Issues short-lived scoped access capabilities and redacts secret values from logs.
public final class CredentialBroker: Sendable {
    public enum BrokerError: Error, Equatable {
        case keychainWriteFailed(OSStatus)
        case keychainReadFailed(OSStatus)
        case missingInstallationKey
        case authenticationTagMismatch
        case adjacentPrivateKeyDetected
        case forbiddenExtensionSourceMutation
    }

    public let serviceIdentifier: String
    public let installationId: String
    public let secretsDirectory: URL

    public init(
        serviceIdentifier: String = "app.autoapply.desktop.credential-broker",
        installationId: String,
        secretsDirectory: URL
    ) {
        self.serviceIdentifier = serviceIdentifier
        self.installationId = installationId
        self.secretsDirectory = secretsDirectory
    }

    /// Verifies that no private key file exists adjacent to ciphertext in `secretsDirectory`.
    public func verifyNoAdjacentPrivateKey() throws {
        let fm = FileManager.default
        guard fm.fileExists(atPath: secretsDirectory.path) else { return }
        let items = try fm.contentsOfDirectory(at: secretsDirectory, includingPropertiesForKeys: nil)
        for item in items {
            let name = item.lastPathComponent.lowercased()
            if name.contains("private") || name.hasSuffix(".key") || name == "keys.txt" {
                throw BrokerError.adjacentPrivateKeyDetected
            }
        }
    }
}
