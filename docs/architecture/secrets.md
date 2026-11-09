# P04 Architecture & Spike — Secret Envelopes, Keychain Custody & Local Data Protection Inventory

- **Ticket:** `P04`
- **Date:** 2026-10-18
- **Related Gates:** `G-04`, `G-06`, `G-09`
- **Requirement IDs:** `AA-AUTH-001`, `AA-AUTH-004`, `NFR-02`, `C-04`, `C-07`, `C-09`
- **Acceptance Test IDs:** `T-SEC-01`, `T-SEC-02`, `T-SEC-03`

---

## 1. SOPS + `age` Architecture & Clean-Mac Bundling (`A-01`, `D-14`, `AA-INS-004`)

1. **Interpretation (`A-01`):** The original brief's `"SOP using SOP Age Key"` is implemented as **SOPS + `age`** envelope encryption with zero end-user CLI setup.
2. **Clean-Mac Finding:** Neither `sops` nor `age`/`age-keygen` is preinstalled on standard macOS installations (verified absent on clean PATH). Therefore, `AutoApply.app` bundles pinned, Developer ID-signed `sops` and `age` binaries in `AutoApply.app/Contents/Resources/bin/` verified by `packaging/manifests/runtime-manifest.json` (`AA-INS-004`), while `CredentialBroker` also supports native authenticated AEAD (`AES-256-GCM` / `ChaCha20-Poly1305` via Apple `CryptoKit` / Python envelope fallback) wired to the installation's Keychain-protected private key.
3. **Strict Custody Separation (`T-SEC-01`, `C-04`):**
   - On first launch, `CredentialBroker` generates a unique per-installation asymmetric identity (`AGE-SECRET-KEY-1...`) and public recipient (`age1...`).
   - The **private identity** is stored exclusively in the macOS Keychain (`kSecClassGenericPassword`, service `app.autoapply.desktop.credential-broker`, `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`).
   - The **ciphertext envelope** (`secrets/credentials.sops.json`) and public recipient metadata (`secrets/recipient.pub`) live under `~/Library/Application Support/AutoApply/secrets/` (`0700`).
   - **Invariant:** The private key is **never** written next to ciphertext in `~/Library/Application Support/AutoApply/`, never exported in support bundles, and never passed in command-line arguments or generic worker environment variables (`[25]`).

---

## 2. Complete Local Data Protection Inventory (`C-09`)

| Surface | Path Under App Root | At-Rest Protection | In-Use / Plaintext Lifetime & Residual Exposure |
| :--- | :--- | :--- | :--- |
| **1. Upstream API Keys & Tokens** (OpenRouter, CapSolver, Gmail OAuth/App Password) | `secrets/credentials.sops.json` | Encrypted per-field via SOPS+age envelope; private key in macOS Keychain. | Decrypted in memory only inside `CredentialBroker` to issue a short-lived capability or perform a brokered request; zeroed after call. |
| **2. Candidate Database & Journals** (`SQLite` + `WAL` + `-shm`) | `candidate/candidate.db`, `.db-wal`, `.db-shm` | Encrypted database page layer (SQLCipher / application-level authenticated field encryption derived from Keychain master key via HKDF-SHA256). | Decrypted pages exist only in the active worker memory while unlocked (`C-09`). |
| **3. Original & Tailored Document Artifacts** (`PDF`, `DOCX`, Previews) | `documents/blobs/<sha256>.enc` | Encrypted object store (`AEAD` envelope per artifact keyed via HKDF from installation key) + immutable SHA-256 plaintext hash manifest. | Materialized to a restricted `0700` ephemeral upload staging file only during an authorized `attach_approved_artifact` action, then unlinked. |
| **4. Derived Search Indexes** | `candidate/index/` | Reconstructible in-memory or encrypted SQLite FTS5 table inside `candidate.db`. | No separate unencrypted on-disk text index. |
| **5. Browser Profiles & Cookies** (`auth`, `ats`, `teal`, `linkedin`) | `browser/profiles/<kind>/` | When session lease is released, profile state is checkpointed into an encrypted archive (`<kind>.tar.enc`) and working cookie files are scrubbed (`C-07`, `C-09`). | **Explicit Disclosure (`C-09`):** While a browser session is actively running, the browser engine requires live disk/memory access to its active profile directory (`0700`). |
| **6. CapSolver Extension Key** | Ephemeral session storage in `ats_operator` profile | Stored in `secrets/credentials.sops.json`; injected at runtime via extension session messaging. | **Never** written to `assets/config.js` or any distributed extension file (`T-SEC-03`). |
| **7. Voice Interview Raw Audio** | `candidate/audio_staging/` | Restricted `0700` temporary buffer during active recording/transcription. | Deleted automatically upon user confirmation of extracted transcript/facts (`D-15`), unless user explicitly toggles retention. |
| **8. Diagnostic Logs & Support Bundles** | `~/Library/Logs/AutoApply/` | Deterministic regex + canary-value redaction filter runs **before** any log line hits disk or support archive (`T-SEC-02`). | Bounded 30-day retention (`D-17`); previewable before user export. |

---

## 3. Verification Artifacts

- **Native Custody Implementation:** `native/CredentialBroker/CredentialBroker.swift`
- **Runtime Envelope & Redaction Module:** `runtime/autoapply/security/sops_age.py`
- **Automated Security Test Suite:** `tests/security/test_secret_envelope.py` (`T-SEC-01`, `T-SEC-02`, `T-SEC-03`)
