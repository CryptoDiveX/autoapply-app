# ADR 0001 — Product Scope, Invariants, Release Gates & Consolidated Owner Decisions

- **Status:** Proposed (Awaiting Founder Approval on `D-01`–`D-18`)
- **Date:** 2026-10-18
- **Ticket:** `P00` (Phase 0 — Requirements Lock)
- **Baseline:** `AutoApply-MASTER-HANDOFF.md` v1.0 (18 October 2026), including `14-REVIEW-CLARIFICATIONS.md` (`C-01`–`C-12`)

---

## 1. Product Invariants (Non-Negotiable Engineering Rules)

1. **Zero Contamination / Clean Room (`AA-INS-002`, `AA-INS-003`, `NFR-01`, `C-01`):**
   - Never import the founder's personal VB Jobs profile, resume facts, contact details, fixed ports, auth files, cookies, jobs, private endpoints, scheduled jobs, or unrelated skills.
   - Ship a pinned, minimal, allowlisted Hermes/Python runtime isolated under `~/Library/Application Support/AutoApply/` with sanitized child environments. Never touch `~/.hermes`, `~/.codex`, global Python, Homebrew, shell profiles, or personal browsers.
   - No customer terminal or CLI setup required.
2. **External Policy Enforcement & Containment (`NFR-02`, `C-06`):**
   - Permissions, secrets, licensing, budgets, file/domain/account checks, consent, document hashes, and outbound authorization are enforced deterministically by the native `PolicyBroker` and `CredentialBroker` outside LLM discretion.
   - No unrestricted shell, `eval`, arbitrary file read, or generic network exfiltration tool exists in production.
   - Untrusted content (job postings, DOM, emails, screenshots, downloads, tool outputs) cannot alter instructions, mandates, or capabilities (`T-SEC-05`).
3. **Truthful Candidate Canon & Scoped Learning (`AA-KB-001`..`005`, `C-11`):**
   - Never fabricate employment history, metrics, degrees, dates, work authorization, or protected demographic disclosures.
   - Facts carry provenance, confidence, confirmation status, effective dates, version, and explicit scope (`form`, `employer`, `country`, or `global`).
   - Residence, nationality, travel permission, and country-specific work authorization/sponsorship remain strictly separate.
   - Passwords, OTPs, MFA codes, security answers, and page instructions are never stored or learned as candidate facts.
4. **Reference-Preserving Document Pipeline & Hash Guard (`AA-DOC-001`..`005`, `C-11`):**
   - Support **both** `frozen-original` mode (byte-identical original resume) and `tailored-approved` mode (preserving the customer's reference typography, hierarchy, spacing, density, and structure via deterministic rendering and visual/ATS text QA).
   - Writing uses `anthropic/claude-sonnet-5.5` with explicit role routing and claim-to-fact verification.
   - Every upload/send verifies the immutable approved artifact SHA-256 hash at the exact outbound action boundary (`T-DOC-03`). Any post-approval edit invalidates submission immediately.
5. **Durable State Machine, Single Submission Owner & Honest Verification (`AA-JOB-003`..`008`, `C-10`):**
   - One submission owner and one authenticated browser session by default; read-only scouts cannot mutate authenticated pages or trackers.
   - Every irreversible action writes a durable reservation and `Attempt` with an idempotency key before dispatch.
   - A crash or timeout between dispatch and receipt recovers to `uncertain` (`submitted_unverified`), triggering ATS/email reconciliation rather than blind resubmission.
   - Prepared, clicked, or queued never counts as submitted.
6. **Orthogonal State Planes (`AA-TRACK-001`..`002`, `AA-MAIL-004`..`005`, `AA-SOC-001`..`002`):**
   - Application submission state, Teal tracker sync state (`not_connected | pending | syncing | verified | failed | conflict`), Gmail thread state, and LinkedIn outreach state are tracked independently.
   - Every external write requires exact target identity matching and post-write field readback.
7. **Independent Visibility & Autonomy Controls (`AA-UX-001`..`003`):**
   - Visibility (`Background` vs. `Visible browser` vs. `User takeover`) is independent of Autonomy (`Draft only` vs. `Review each application` vs. `Bounded auto-submit mandate`).
   - Background mode never steals focus, moves the physical cursor, switches macOS Spaces, or falls back to desktop control (`T-UX-01`). If desktop interaction or human security/login/MFA is needed, pause and request takeover.
8. **Per-Installation Key Custody & Partitioned Browser Secrets (`NFR-02`, `C-04`, `C-07`, `C-09`):**
   - Generate a unique per-installation `age` keypair; store the private identity in macOS Keychain ACL-bound to the signed `CredentialBroker` binary and encrypt secret envelopes via SOPS+age under the app root.
   - Partition browser profiles (`auth/security`, `ats`, `teal`, `linkedin`), time-multiplexed within the 1-session CloakBrowser concurrency limit so extensions (e.g., CapSolver) never have ambient access to Google security pages or unrelated logins.
9. **Commercial & Trial Integrity (`AA-LIC-001`..`004`, `C-02`):**
   - Five days (120 hours) free trial, then USD 20/month application licence purchased on the website and pasted into the app; third-party AI/CapSolver/Teal costs are separate and disclosed upfront.
   - Selecting the trial in `O-02` reserves the path without starting the clock; the server-issued 120-hour trial starts only at `O-13` upon explicit user confirmation after essential readiness checks pass.
   - Expiry stops new paid automation while preserving read-only access, in-flight uncertain reconciliation, and full data export (`AA-LIC-003`, `NFR-08`).

---

## 2. Conflicting, Uncertain & Constrained Items Preserved from Brief vs. Reality

Where the founder's original brief conflicts with published vendor terms, technical capabilities, or security constraints, **no feature is silently dropped or substituted**. Each conflict is preserved below and bound to an explicit release gate (`G-01`–`G-09`) and owner decision (`D-01`–`D-18`):

| Conflict / Uncertainty | Original Brief Request | Primary-Source / Technical Reality (`05-INTEGRATIONS`, `14-CLARIFICATIONS`) | Disposition & Gate |
| :--- | :--- | :--- | :--- |
| **1. CloakBrowser Free Tier vs. OEM Distribution** | Bundle/install free CloakBrowser and authenticate licence via GitHub (`AA-AUTH-003`). | CloakBrowser's binary licence prohibits third-party redistribution, bundling, embedding, and customer-facing browser control without an OEM/SaaS agreement; README and binary licence also differ on latest-build free tier eligibility (`F-02`, `C-01`). | **Retained in scope; gated by `G-01` / `D-01`.** Do not bundle binary commercially without written vendor clearance; verify isolated profile/cache/licence paths (`P01`). |
| **2. ChatGPT Login for Paid Product** | Ask user to log into ChatGPT subscription and click to enable Codex remote sessions (`AA-AUTH-002`). | OpenAI's Sign in with ChatGPT docs distinguish open-source local tools from paid commercial products and require partner client registration (`F-03`). Also, security toggles must be user-consented, not invisibly clicked (`C-03`). | **Retained in scope; gated by `G-02` / `D-02`.** Keep disabled until commercial registration is approved; guide user to official settings page for manual security consent. |
| **3. Dolphin 24B Fallback Orchestration** | Fallback to `cognitivecomputations/dolphin-mistral-24b-venice-edition` for clicking through websites (`AA-AUTH-001`). | Public OpenRouter snapshot (`2026-10-18`) shows this exact model ID is `text->text` only and does **not** advertise native `tools`/`tool_choice` (nor a `:free` variant) (`F-04`, `C-03`). | **Exact ID preserved; gated by `G-03` / `D-03`.** Build and test a strict schema-validated DOM text action-proposal adapter in `P02`; if it fails or hits vision-only steps, mark blocked rather than silently substituting another model. |
| **4. Automatic Gmail App-Password Creation** | Navigate to Google app-passwords page, set up an app password automatically, and store in SOPS (`AA-MAIL-002`). | App passwords require 2-Step Verification and are blocked on Advanced Protection / Workspace / security-key accounts (`F-05`). Scraping Google security pages in an agent DOM leaks secrets (`C-04`). Google recommends OAuth 2.0 PKCE (`AA-MAIL-003`). | **Intent preserved as eligibility-gated native flow; gated by `G-04` / `G-05` / `D-04`.** Spike trusted native secret capture (with agent DOM/screenshots/extensions suppressed) alongside recommended Desktop OAuth PKCE default. Default-deny sending Google mail data to cloud LLMs until `G-05` clears (`C-05`). |
| **5. Scripted CapSolver Key Configuration** | Preinstall CapSolver extension, ask user for API key, and enable it (`AA-AUTH-004`). | Vendor developer examples write the API key into plaintext `assets/config.js` (`F-06`), violating `NFR-02`/`C-07`. Ambient extension access on auth pages is also unsafe. | **Retained in scope; gated by `G-06` / `D-07`.** Spike ephemeral runtime key injection in isolated ATS profile only; exclude extension from auth/Google/Teal/LinkedIn profiles (`C-07`). |
| **6. Teal Job Tracker Automation** | Log into `https://app.tealhq.com/job-tracker` and track all jobs (`AA-TRACK-001`). | No official public write API was verified; customer login does not grant commercial scraping/API rights, and private VB Jobs endpoints are not a redistributable contract (`F-07`, `C-10`). | **Retained in scope; gated by `G-07` / `D-05`.** Build authoritative local SQLite ledger + durable outbox (`sync_pending`) and exact-record readback verifier while vendor permission is pursued. |
| **7. LinkedIn Automated Connections, Messages & Follow-Ups** | Send connection requests, messages, and follow-ups automatically using preserved LinkedIn session (`AA-SOC-001`). | LinkedIn policy explicitly prohibits bots/extensions automating profile scraping, status polling, invitations, and messaging (`F-08`, `C-08`). | **Full scope preserved in PRD; automated reads/sends gated by `G-08` / `D-06`.** Hard-block automated LinkedIn reads/polls/sends in `PolicyBroker` until partner approval exists; offer reviewed drafts, reminders, and user-operated handoff if `D-06` is approved for beta. |
| **8. Blanket Mac Control Permission Prompt** | Prompt user in initial stage to allow bundle and all child scripts full control of Mac, Accessibility, mouse, keyboard, screen, apps (`AA-UX-004`). | macOS TCC does not provide a single blanket prompt for arbitrary child scripts; permissions bind to signed identities and must be requested per capability (`F-09`, `C-06`). Background mode also forbids physical cursor/focus hijacking (`AA-UX-002`). | **Redesigned to native capability checklist (`O-08`); gated by `G-09` / `D-08` / `D-09`.** Request only verified per-feature TCC permissions (`Microphone`, `Accessibility`, `Screen Recording`, `Automation`) on signed helpers; never demand unnecessary Full Disk Access or global Input Monitoring. |
| **9. "SOP Age Key" Wording** | Store passwords in SOP using SOP Age Key with no user setup (`AA-AUTH-001`, `NFR-02`). | Interpreted as **SOPS + `age`** with per-installation key generation and macOS Keychain custody (`F-10`, `C-04`, `C-09`). SOPS does not automatically encrypt live SQLite WALs or open browser cookie stores. | **Explicit interpretation `A-01` / `D-14`.** Combine SOPS+age secret envelopes (Keychain-custodied private key) with encrypted SQLite candidate store and encrypted closed-browser profile snapshots (`C-09`). |

---

## 3. Full Vision vs. Gated Core Beta Scope

- **Full Vision (Preserved in Architecture, Schemas & Traceability):**
  All 54 requirements (`AA-INS-001`..`AA-UX-004`, `NFR-01`..`NFR-09`) and 34 founder brief items remain in the specification and repository contracts. No requested capability is deleted.
- **Releasable Core Beta (Pending Gate Clearances `G-01`–`G-09`):**
  - Native SwiftUI macOS shell + menu-bar app (`AutoApply.app`) with 13-step resumable onboarding (`O-01`–`O-13`).
  - Isolated private Python/Hermes runtime supervisor (`RuntimeSupervisor`), deterministic `PolicyBroker`, and Keychain-backed SOPS+age `CredentialBroker`.
  - Resume import (`PDF`/`DOCX`), immutable original retention, structured fact extraction/confirmation, optional voice/text interview, and scoped reusable question bank (`CandidateStore`).
  - `anthropic/claude-sonnet-5.5` writer route, claim verification, deterministic reference-matching `DOCX`/`PDF` renderer, visual/ATS layout QA, and outbound SHA-256 hash guard supporting both `frozen-original` and `tailored-approved` modes (`DocumentPipeline`).
  - Durable SQLite job ledger, 30-day configurable employer dedupe, single-owner leases, committed-value browser field verification, background/foreground/takeover handoff, and uncertain-submission reconciliation (`ApplicationEngine`) proven against local synthetic ATS fixtures and one explicitly authorized pilot ATS (`P21`).
  - Local deterministic Gmail thread/bounce reconciliation (`G-05` cloud-LLM gate default-deny until cleared), local Teal outbox with `sync_pending`/export until `G-07` clears, and draft/reminder/user-handoff LinkedIn networking while `G-08` remains closed (subject to founder approval of `D-01`–`D-07`).

---

## 4. Consolidated Owner Decision Set (`D-01`–`D-18`)

Every decision below includes the recommended default from `09-DECISIONS-AND-ASSUMPTIONS.md` and `14-REVIEW-CLARIFICATIONS.md`. Approving the recommended defaults allows Phase 0 spikes (`P01`–`P04`) and Phase 1–3 local vertical slices to proceed immediately without blocking on external vendor contracts.

### Part A — Blocking Commercial & Integration Scope Decisions (`D-01`–`D-07`)

| ID | Decision Topic | Recommended Default (Awaiting Founder Approval) | Impact / Gate |
| :--- | :--- | :--- | :--- |
| **D-01** | **CloakBrowser Rights & Local Dev Engine** | **Default:** Pursue written CloakBrowser OEM/distribution/control terms and verify latest free GitHub-tier rules (`G-01`). Do not bundle CloakBrowser in a commercial release until cleared. Authorize an isolated local Chromium/Playwright test fixture driver strictly for development/CI while `G-01` is pending (never marketed or shipped as a silent replacement). | `G-01`, `AA-AUTH-003`, `C-01` |
| **D-02** | **ChatGPT / Codex Commercial Integration** | **Default:** Apply for OpenAI commercial client registration (`G-02`). Keep the ChatGPT/Codex connector visibly gated in `O-04` until approved, and allow local/beta testing via the customer's OpenRouter key rather than reusing any personal/developer OAuth client identity. | `G-02`, `AA-AUTH-002`, `C-03` |
| **D-03** | **Dolphin 24B Fallback Orchestration** | **Default:** Preserve exact model ID `cognitivecomputations/dolphin-mistral-24b-venice-edition` (never append `:free`). Build and benchmark a strict schema-validated DOM text action-proposal adapter in `P02` (`G-03`). If Dolphin cannot pass deterministic action/safety tests or encounters vision-required steps, pause/block fallback orchestration and ask the founder before enabling any paid tool-capable alternative. | `G-03`, `AA-AUTH-001`, `C-03` |
| **D-04** | **Gmail Onboarding Mode & Data Boundary** | **Default:** Support **Production Google Desktop OAuth (PKCE)** as the recommended primary path **plus** an eligibility-checked, user-authenticated App-Password flow with trusted native secret capture (suppressing agent DOM/screenshots/extensions per `C-04`). Enforce default-deny on sending any Google-derived mail data to cloud LLMs until `G-05` verification clears (`C-05`). | `G-04`, `G-05`, `AA-MAIL-001`..`003` |
| **D-05** | **Teal Tracker Integration Path** | **Default:** Seek documented Teal partner/API or permitted integration approval (`G-07`). Ship the authoritative local SQLite ledger + durable `sync_pending` outbox + CSV/JSON export so no application is lost or blocked while `G-07` is pending. | `G-07`, `AA-TRACK-001`..`002`, `C-10` |
| **D-06** | **LinkedIn Networking Launch Scope** | **Default:** Keep full automated LinkedIn connections/messages/follow-ups in the codebase behind `G-08`, hard-blocked by `PolicyBroker` (including automated profile reads/status polling per `C-08`) until platform permission is obtained. For initial beta/launch, expose transparently labelled local draft generation, cadence reminders, and genuine user-operated handoff. | `G-08`, `AA-SOC-001`..`002`, `C-08` |
| **D-07** | **CapSolver Packaging & Runtime Key** | **Default:** Validate CapSolver redistribution rights and ephemeral runtime key injection (no plaintext key in `assets/config.js`) in `P04`/`P26` (`G-06`). Restrict CapSolver strictly to the isolated ATS browser profile (excluded from Google/Teal/LinkedIn/auth profiles per `C-07`) with explicit cost disclosure and mandatory human handoff on site restrictions. | `G-06`, `AA-AUTH-004`, `C-07` |

### Part B — Product, Technical & Commercial Policy Defaults (`D-08`–`D-18`)

| ID | Decision Topic | Recommended Default (Awaiting Founder Approval) | Impact / Requirement |
| :--- | :--- | :--- | :--- |
| **D-08** | **Target macOS & CPU Matrix** | **Default:** Native SwiftUI/AppKit shell targeting **Apple Silicon (`arm64`) on macOS 14 (Sonoma)+** for v1; Intel (`x86_64`) remains an explicit later option after dependency proof. | `AA-INS-001`, `G-09` |
| **D-09** | **Distribution Channel & Bundle ID** | **Default:** Direct Developer ID-signed, Hardened Runtime, notarized download (outside Mac App Store initially). Use placeholder `app.autoapply.desktop` (or founder-supplied reverse-DNS) until final brand/Apple Developer Team ID are provided. | `AA-INS-001`, `G-09` |
| **D-10** | **5-Day Free Trial Activation Rules** | **Default:** `O-02` reserves the trial path without starting the clock; `O-13` activates the server-issued **120-hour trial** only after essential readiness checks pass and the user explicitly confirms (`C-02`). No credit card required for trial; no auto-billing without separate checkout. Offline rollback cannot extend server expiry. | `AA-LIC-001`..`002`, `C-02` |
| **D-11** | **USD 20/Month Subscription & Seats** | **Default:** USD 20/month for AutoApply desktop access (external AI/CapSolver/Teal fees separate), **1 active Mac seat** per subscription (with self-serve device transfer/deactivation), **72-hour signed offline entitlement lease** for paid users, and cancellation effective at the end of the paid-through period via hosted checkout/portal. | `AA-LIC-001`..`004`, `C-02` |
| **D-12** | **Default Autonomy, Visibility & Dedupe** | **Default:** Initial mode is **Background visibility + Review-first autonomy**, 1 submission owner, and a **configurable 30-day rolling direct-employer dedupe window**. Bounded auto-submit mandates require separate explicit opt-in. | `AA-JOB-003`, `AA-JOB-005`, `AA-UX-001`..`002` |
| **D-13** | **Document Modes & Canonical Style** | **Default:** Support both `frozen-original` (byte-identical) and `tailored-approved` modes. Customer's uploaded reference resume defines the canonical style profile (never a generic single template or founder resume layout). | `AA-DOC-002`..`004`, `C-11` |
| **D-14** | **Secrets & Local Data Encryption** | **Default:** Confirm **"SOP Age Key" = SOPS + `age`** with a per-installation `age` private identity stored in macOS Keychain (ACL-bound to `CredentialBroker`), plus encrypted SQLite candidate database (including WAL/journals), encrypted artifact store, and encrypted closed-browser snapshots (`C-04`, `C-09`). | `NFR-02`, `C-04`, `C-09` |
| **D-15** | **Voice Interview & Transcription** | **Default:** Optional/skippable voice interview with full typed equivalent; prefer validated on-device transcription (cloud transcription requires separate consent/cost disclosure); delete raw audio automatically after the user saves the reviewed transcript/facts unless retention is toggled on. | `AA-KB-003`, `NFR-04` |
| **D-16** | **Jurisdictions & Languages** | **Default:** English v1, covering US-oriented application questions with explicit country-specific work authorization/sponsorship/residence separation (without assuming US citizenship/residence). Voluntary demographic disclosures default to "ask when encountered" and are never inferred. | `AA-KB-004`, `AA-JOB-002` |
| **D-17** | **Retention, Export & Post-Expiry Access** | **Default:** Redacted diagnostic logs retained 30 days; application evidence and documents retained until user deletion; full schema-validated export of facts, answers, jobs, and documents remains free and available even after trial/subscription expiry (excluding secrets unless an encrypted recovery archive is explicitly created). | `AA-LIC-003`, `NFR-08` |
| **D-18** | **Support, Operations & Payment Provider** | **Default:** Use Stripe (in test mode during development) for hosted checkout/portal/webhooks, Ed25519 server-signed entitlement leases, and previewable redacted support bundles. Final support SLA/email/merchant account to be supplied before Phase 5 launch. | `AA-LIC-004`, `C-12` |
