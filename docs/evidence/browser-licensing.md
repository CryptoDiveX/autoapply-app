# P01 Evidence — CloakBrowser Licensing, Isolation, Concurrency & Extension Loading

- **Ticket:** `P01`
- **Date:** 2026-10-18
- **Related Gate:** `G-01` (`status: unapproved` — blocked pending written vendor OEM/distribution agreement)
- **Requirement IDs:** `AA-INS-002`, `AA-INS-004`, `AA-AUTH-003`, `AA-AUTH-004`, `NFR-01`, `C-01`, `C-07`
- **Acceptance Test IDs:** `T-INS-02`, `T-AUTH-04`, `T-SEC-03`, `T-REL-02`

---

## 1. Primary-Source Licensing Findings (`[12]`, `[13]`, `[14]`)

1. **Free Tier vs. Binary Redistribution (`BINARY-LICENSE.md` `[13]`, `README.md` `[14]`):**
   - CloakBrowser's open-source wrapper (`MIT`) is distinct from the proprietary browser binary (`BINARY-LICENSE.md`).
   - The free GitHub-authenticated licence key grants **1 concurrent session** for personal/individual developer use.
   - `BINARY-LICENSE.md` explicitly restricts:
     - Bundling, embedding, or redistributing the proprietary binary inside a commercial software product without a separate OEM/commercial agreement.
     - Exposing customer-facing browser control in a paid commercial product without OEM/SaaS authorization.
   - **Inconsistency noted (`F-02`):** Promotional text in `README.md` and version-specific clauses in `BINARY-LICENSE.md` differ regarding whether the latest binary build is permanently covered under the free tier.
2. **Commercial Gate Status (`G-01`):**
   - Because written vendor OEM/redistribution/customer-control permission has not been obtained, **`G-01` remains `unapproved` (blocked for commercial release)**.
   - Neither a customer's personal GitHub login nor the USD 20/month AutoApply subscription automatically grants OEM binary redistribution rights.
   - No alternative browser may silently replace CloakBrowser in customer-facing claims without explicit founder approval (`D-01`, `C-01`).

---

## 2. Technical Isolation & Coexistence Contract (`AA-INS-002`, `NFR-01`, `C-07`)

To guarantee zero interference with any existing CloakBrowser, Chromium, Chrome, or Playwright installation on the customer's Mac (`T-INS-02`):

1. **Dedicated App-Owned Root:**
   - Binary cache/install path: `~/Library/Application Support/AutoApply/browser/bin/`
   - Licence token path: `~/Library/Application Support/AutoApply/browser/licence/cloak_entitlement.json` (encrypted at rest via `CredentialBroker`)
   - Browser cache path: `~/Library/Caches/AutoApply/browser-cache/`
   - Never read or write `~/.cloakbrowser`, `~/.cache/cloakbrowser`, `~/.config/cloakbrowser`, `~/Library/Application Support/Google/Chrome`, or `~/Library/Application Support/Chromium`.
2. **Partitioned Profiles & 1-Session Time-Multiplexing (`C-07`):**
   - Four strictly isolated profile directories under `~/Library/Application Support/AutoApply/browser/profiles/`:
     - `auth_trusted`: Used exclusively for user-operated login/security steps (Google, ChatGPT, GitHub entitlement). **Zero third-party extensions loaded; agent DOM observation and screenshots suppressed.**
     - `ats_operator`: Used for job-board/ATS form inspection and submission. Only profile permitted to load the pinned, integrity-verified CapSolver extension (`AA-AUTH-004`, `G-06`).
     - `teal_tracker`: Isolated session for `https://app.tealhq.com/job-tracker` (`C-10`). No CapSolver extension.
     - `linkedin_session`: Isolated session for LinkedIn (`AA-AUTH-005`). No CapSolver extension; automated reads/polls/sends blocked unless `G-08` is approved (`C-08`).
   - **Single-Session Lease (`BrowserSessionLeaseManager`):** Enforces at most **1 active browser session** at any instant to respect the free tier's 1-session concurrency limit (`C-01`, `C-07`). Switching from `ats_operator` to `auth_trusted` or `teal_tracker` cleanly checkpoints and closes the active profile session before launching the next.
3. **Environment & Port Hygiene:**
   - Strip inherited `CHROME_DEVEL_SANDBOX`, `PLAYWRIGHT_BROWSERS_PATH`, `CLOAKBROWSER_*`, and fixed `CDP` debugging port variables from the parent environment.
   - Bind debugging/control over an ephemeral loopback pipe or socket owned by `RuntimeSupervisor`, never a fixed global port (e.g., `9222`).

---

## 3. Verification Artifact

- **Automated Test:** `tests/coexistence/test_browser_paths.py`
- **Classification:** Local contract & filesystem coexistence test (`mock/local`; does not claim `G-01` vendor legal clearance).
