import CryptoKit
import Foundation

/// Native macOS IPC client for authenticated stdio/Unix socket communication with the worker (P08).
///
/// Enforces:
/// - Protocol version 1 envelope validation.
/// - Per-session HMAC-SHA256 caller authentication (`T-SEC-04`).
/// - Immediate emergency-stop cancellation broadcast (`T-UX-03`).
public final class IPCChannel: Sendable {
    public enum MessageType: String, Codable, Sendable {
        case command
        case proposal
        case approvalRequest = "approval_request"
        case userDecision = "user_decision"
        case progress
        case health
        case heartbeat
        case cancellation
        case result
        case evidenceReference = "evidence_reference"
        case recoverableError = "recoverable_error"
        case fatalError = "fatal_error"
    }

    public struct Envelope: Codable, Equatable, Sendable {
        public let protocolVersion: Int
        public let requestId: String
        public let runId: String
        public let jobId: String?
        public let type: MessageType
        public let operation: String
        public let expectedRevision: Int?
        public let idempotencyKey: String?
        public let deadlineMs: Int?
        public let callerId: String
        public let authTag: String
        public let payload: [String: String]

        enum CodingKeys: String, CodingKey {
            case protocolVersion = "protocol_version"
            case requestId = "request_id"
            case runId = "run_id"
            case jobId = "job_id"
            case type
            case operation
            case expectedRevision = "expected_revision"
            case idempotencyKey = "idempotency_key"
            case deadlineMs = "deadline_ms"
            case callerId = "caller_id"
            case authTag = "auth_tag"
            case payload
        }
    }

    public static func computeAuthTag(
        sessionSecret: Data,
        requestId: String,
        runId: String,
        type: String,
        operation: String,
        callerId: String
    ) -> String {
        let canonical = "\(requestId)|\(runId)|\(type)|\(operation)|\(callerId)"
        let key = SymmetricKey(data: sessionSecret)
        let mac = HMAC<SHA256>.authenticationCode(for: Data(canonical.utf8), using: key)
        return mac.map { String(format: "%02x", $0) }.joined()
    }
}
