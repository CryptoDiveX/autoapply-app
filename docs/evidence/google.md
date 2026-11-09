# P03 Evidence — Google / Gmail Onboarding, Transport Scopes & Cloud LLM Data Boundary

- **Ticket:** `P03`
- **Date:** 2026-10-18
- **Related Gates:** `G-04` (`status: unapproved`), `G-05` (`status: unapproved`)
- **Requirement IDs:** `AA-MAIL-001`, `AA-MAIL-002`, `AA-MAIL-003`, `AA-MAIL-004`, `AA-MAIL-005`, `NFR-04`, `C-04`, `C-05`
- **Acceptance Test IDs:** `T-MAIL-01`, `T-MAIL-02`, `T-MAIL-03`, `T-MAIL-04`, `T-MAIL-05`, `T-SEC-02`

---

## 1. Separate Job-Search Account Requirement (`AA-MAIL-001`)

- Onboarding (`O-05`) displays the mandatory footer:
  **"Use a separate Google account for job searching, not your main account."**
- Only `@gmail.com` / Google Workspace accounts explicitly connected by the customer are supported in v1.
- Account identity (`email`, `sub`/`account_id`) is verified before permission consent and re-verified on every poll/send (`T-AUTH-03`).

---

## 2. Onboarding & Credential Transport Comparison (`G-04`, `C-04`, `C-05`)

| Dimension | Option A: Desktop OAuth 2.0 + PKCE (`AA-MAIL-003` Recommended Default) | Option B: Guided App-Password Flow (`AA-MAIL-002` Original Brief Request) |
| :--- | :--- | :--- |
| **Account Eligibility (`[19]`, `T-MAIL-02`)** | Supported across standard Gmail, 2SV, passkeys, and eligible Workspace accounts. | Requires 2-Step Verification enabled; **blocked** by Google on Advanced Protection accounts, Workspace orgs disabling app passwords, and certain security-key-only setups. |
| **Scopes & Blast Radius (`[20][21]`, `C-05`)** | Granular Gmail API scopes (`gmail.readonly`, `gmail.modify` for approved label/archive actions, `gmail.send` only when outbound mail is authorized). Never requests permanent full-mailbox deletion (`https://mail.google.com/`). | Broad IMAP/SMTP account access; application label/lookback filters are enforced locally by `GmailConnector` rather than by narrower upstream token scopes. |
| **Secret Capture & Storage (`C-04`, `C-07`)** | Loopback PKCE code exchange directly inside native `CredentialBroker` via system browser; refresh token encrypted in SOPS+age envelope. | User authenticates in `auth_trusted` profile (agent DOM, screenshots, traces, clipboard history, and extensions suppressed). Generated 16-character app password enters via native masked secret channel directly into `CredentialBroker`. |
| **Gate Status** | Requires `G-04` owner confirmation (`D-04`) and `G-05` production OAuth client verification. | Requires `G-04` owner confirmation and eligibility detection (`2SV_DISABLED`, `ADVANCED_PROTECTION`, `WORKSPACE_RESTRICTED` fail honestly without weakening security). |

---

## 3. Default-Deny Cloud LLM Data Boundary (`G-05`, `C-05`)

- **Binding Rule (`C-05`):** Sending any Google-derived data (email bodies, headers, summaries, embeddings, attachments, or screenshots) to external cloud LLM providers (OpenRouter, Anthropic, OpenAI) is **default-denied** by `FeatureGateEnforcer` while `G-05` is `unapproved`.
- Customer local consent alone does not override `G-05`; clearing `G-05` requires documented Google Limited Use compliance, verified processor retention/training terms, and production OAuth verification.
- While `G-05` is closed, `GmailConnector` operates strictly in **local deterministic mode** (header/Message-ID/In-Reply-To correlation, bounce DSN parsing, and receipt matching).
