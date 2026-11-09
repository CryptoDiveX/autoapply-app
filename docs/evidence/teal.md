# P03 Evidence — Teal Job Tracker Integration & Identity Verification

- **Ticket:** `P03`
- **Date:** 2026-10-18
- **Related Gate:** `G-07` (`status: unapproved`)
- **Requirement IDs:** `AA-AUTH-005`, `AA-TRACK-001`, `AA-TRACK-002`, `C-10`
- **Acceptance Test IDs:** `T-TRACK-01`, `T-TRACK-02`, `T-AUTH-03`, `T-AUTH-04`

---

## 1. Platform Permission vs. Session Login (`[16]`, `[17]`, `F-07`)

- Founder-specified onboarding destination (`C-10`): `https://app.tealhq.com/job-tracker` inside the isolated `teal_tracker` browser profile.
- A valid customer login session proves account identity for that customer's session, **not** commercial partner API permission or authorization to ship undocumented private endpoints observed in personal VB Jobs scripts.
- **`G-07` remains `unapproved`** until a documented vendor integration path or explicit partner approval is recorded.

---

## 2. Authoritative Local Ledger & Orthogonal Sync State (`AA-TRACK-001`..`002`, `C-10`)

1. **Authoritative Local SQLite Ledger:**
   - Every job and application is persisted locally first with its own submission state (`submitted_verified`, `submitted_unverified`, `uncertain`, etc.).
   - Teal synchronization state is tracked orthogonally (`not_connected | pending | syncing | verified | failed | conflict`).
   - A Teal outage or closed `G-07` gate leaves the record in `pending` (`sync_pending`) with full CSV/JSON export available; it **never** erases a local record or triggers a duplicate job application.
2. **Exact-Record Identity & Post-Write Readback (`T-TRACK-01`, `C-10`):**
   - Never overwrite a sibling role at the same company based on a loose company-name search.
   - Writes require matching `(account_id, remote_record_id, canonical_job_url, canonical_role_id)`, preserving existing user notes and sibling rows.
   - Missing projected fields in a read response are treated as `unprojected_field`, never as empty/null data justifying a destructive overwrite.
