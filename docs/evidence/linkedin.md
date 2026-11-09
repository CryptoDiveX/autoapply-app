# P03 Evidence — LinkedIn Networking Platform Gate & Manual-Assist Boundary

- **Ticket:** `P03`
- **Date:** 2026-10-18
- **Related Gate:** `G-08` (`status: unapproved`)
- **Requirement IDs:** `AA-AUTH-005`, `AA-SOC-001`, `AA-SOC-002`, `C-08`
- **Acceptance Test IDs:** `T-SOC-01`, `T-SOC-02`, `T-AUTH-03`, `T-AUTH-04`

---

## 1. Published Platform Policy (`[18]`, `F-08`, `C-08`)

- LinkedIn's official prohibited software policy (`https://linkedin.com/help/linkedin/answer/a1341387`) forbids bots, browser extensions, and automated tools that scrape profiles, poll connection/message states, send automated invitations, or send automated messages/follow-ups.
- Neither a valid customer login in the `linkedin_session` profile nor customer consent in AutoApply overrides this platform restriction (`AA-SOC-001`, `C-08`).

---

## 2. Hard-Blocked Operations While `G-08` Is Unapproved (`T-SOC-01`)

When `G-08` is `unapproved`, `FeatureGateEnforcer` deterministically denies **all** automated LinkedIn operations:
- `linkedin.read_profile` (automated contact/profile scraping)
- `linkedin.navigate_for_collection` (automated search/directory traversal)
- `linkedin.poll_connection_status` (automated acceptance polling)
- `linkedin.poll_message_replies` (automated inbox/reply scraping)
- `linkedin.send_connection_request` (automated invitation dispatch)
- `linkedin.send_message` (automated initial message dispatch)
- `linkedin.send_followup` (automated follow-up dispatch)

---

## 3. Compliant Manual-Assist Mode (Pending Founder Decision `D-06`)

- While `G-08` is closed, AutoApply supports:
  1. Storing user-supplied contact names/URLs/notes in the local `Contact` table.
  2. Generating tailored connection/message/follow-up drafts via `writer.primary` (`anthropic/claude-sonnet-5.5`) for human review.
  3. Scheduling local follow-up reminders and opening the user-operated session for manual copy/paste and human send confirmation.
- When `G-08` is approved in the future, automated execution still enforces the strict sequence in `C-08`:
  `exact_contact_selected → connection_request_approved → acceptance_verified → message_approved_and_sent → reply_or_opt_out_checked → single_bounded_followup`.
