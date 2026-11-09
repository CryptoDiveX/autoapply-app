import Foundation

/// App-owned RuntimeSupervisor launcher and process provenance tracker (P07 / AA-INS-002 / C-06).
///
/// Guarantees:
/// - Constructs child process environment strictly from an allowlist.
/// - Pins `HERMES_HOME` and `PYTHONNOUSERSITE=1` under `~/Library/Application Support/AutoApply/`.
/// - Tracks PID + start timestamp + executable path before any termination signal is sent,
///   never invoking broad `pkill python` or touching unrelated user processes.
public final class RuntimeLauncher: Sendable {
    public struct ProcessProvenance: Equatable, Sendable {
        public let pid: Int32
        public let startTimestampNanoseconds: UInt64
        public let executablePath: String
        public let runId: String

        public init(pid: Int32, startTimestampNanoseconds: UInt64, executablePath: String, runId: String) {
            self.pid = pid
            self.startTimestampNanoseconds = startTimestampNanoseconds
            self.executablePath = executablePath
            self.runId = runId
        }
    }

    public enum SupervisorError: Error, Equatable {
        case untrustedExecutablePath(String)
        case provenanceMismatch(Int32)
    }

    public let appSupportRoot: URL
    public let bundledPythonExecutable: URL

    public init(appSupportRoot: URL, bundledPythonExecutable: URL) {
        self.appSupportRoot = appSupportRoot
        self.bundledPythonExecutable = bundledPythonExecutable
    }

    public func buildSanitizedEnvironment(parentEnv: [String: String]) -> [String: String] {
        var env: [String: String] = [:]
        for key in ["HOME", "USER", "LOGNAME", "TMPDIR", "LANG", "LC_ALL"] {
            if let value = parentEnv[key] {
                env[key] = value
            }
        }
        let runtimeState = appSupportRoot.appendingPathComponent("runtime-state", isDirectory: true)
        env["PATH"] = "/usr/bin:/bin"
        env["HERMES_HOME"] = runtimeState.appendingPathComponent("hermes", isDirectory: true).path
        env["AUTOAPPLY_APP_SUPPORT"] = appSupportRoot.path
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env
    }

    public func verifyProvenanceBeforeKill(
        recorded: ProcessProvenance,
        observedPid: Int32,
        observedStartNs: UInt64,
        observedExecutablePath: String
    ) throws {
        guard recorded.pid == observedPid,
              recorded.startTimestampNanoseconds == observedStartNs,
              recorded.executablePath == observedExecutablePath,
              observedExecutablePath == bundledPythonExecutable.path else {
            throw SupervisorError.provenanceMismatch(observedPid)
        }
    }
}
