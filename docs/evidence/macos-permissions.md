# P03 Evidence — macOS TCC Permissions, Code Signing Identities & Helper Containment

- **Ticket:** `P03`
- **Date:** 2026-10-18
- **Related Gate:** `G-09` (`status: unapproved` — pending Developer ID certificates and clean-Mac notarization test)
- **Requirement IDs:** `AA-INS-001`, `AA-UX-004`, `NFR-02`, `C-01`, `C-06`
- **Acceptance Test IDs:** `T-PERM-01`, `T-PERM-02`, `T-PERM-03`, `T-INS-03`, `T-REL-01`

---

## 1. Per-Capability TCC Permission Model (`AA-UX-004`, `[22]`, `[23]`)

macOS Transparency, Consent, and Control (TCC) binds permissions to specific signed bundle identifiers and code requirements (`CSRequirement`). There is **no** supported macOS mechanism to grant "blanket full control to all child scripts" in one prompt.

| Capability | macOS TCC / Entitlement Key | Required For | Denial / Revocation Behavior (`T-PERM-01`, `T-PERM-02`) |
| :--- | :--- | :--- | :--- |
| **Microphone** | `NSMicrophoneUsageDescription` / `com.apple.security.device.audio-input` | Optional voice self-interview (`O-11`, `AA-KB-003`). | Disables audio recording only; text-based interview and all application features continue unaffected. |
| **Screen Recording** | `CGPreflightScreenCaptureAccess` / `CGRequestScreenCaptureAccess` | Optional native visual fallback inspection outside owned DOM. | Owned-browser DOM automation and document rendering continue; external screen capture pauses with guidance. |
| **Accessibility** | `AXIsProcessTrustedWithOptions` | Optional desktop window handoff positioning; **never** used to hijack cursor/focus in background mode (`AA-UX-002`). | Background DOM automation continues; any desktop-level step pauses and requests human takeover (`T-UX-01`). |
| **Automation (AppleEvents)** | `NSAppleEventsUsageDescription` | Only if explicitly controlling a user-approved external target app. | Disabled by default; owned browser runs directly under `RuntimeSupervisor` without AppleEvents. |
| **Input Monitoring / Full Disk Access** | **NOT REQUESTED** | Explicitly excluded (`AA-UX-004`). Resume import and data export use standard `NSOpenPanel` / `NSSavePanel` user-selected file URLs. | N/A — never demanded from customers. |

---

## 2. Per-Process Authority & Containment Target (`C-06`)

| Component | Signed Identity (Placeholder until `D-09`) | Filesystem Authority | Network Authority | Keychain Authority |
| :--- | :--- | :--- | :--- | :--- |
| `AutoApply.app` (UI Shell) | `app.autoapply.desktop` | App Support read/write + user-selected `NSOpenPanel` files | None directly (delegates to Supervisor/Brokers) | None directly |
| `CredentialBroker` | `app.autoapply.desktop.credential-broker` | `~/Library/Application Support/AutoApply/secrets/` (`0700`) | Loopback OAuth PKCE & short-lived token exchange | Exclusive ACL owner of per-installation `age` private key |
| `PolicyBroker` & `RuntimeSupervisor` | `app.autoapply.desktop.supervisor` | App Support & Caches roots | Local Unix socket IPC to worker | None |
| Python / Hermes Worker | `app.autoapply.desktop.worker` | Scoped to `runtime-state/`, `candidate/`, `jobs/`, `documents/`, `evidence/` | Broker-authorized provider & ATS endpoints only (no localhost/private-IP SSRF per `C-09`) | **Zero direct Keychain access** |
