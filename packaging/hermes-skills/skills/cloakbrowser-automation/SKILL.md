---
name: cloakbrowser-automation
description: Anti-detection CloakBrowser CDP & Browser-Use form automation skill (modeled on vb-jobs operations). Drives CloakBrowser on CDP port 19225 with human-paced typing, curved mouse trajectories, React-Select ArrowDown combobox selection, native PDF upload, and manual field override Knowledge Base learning.
version: 1.0.0
metadata:
  hermes:
    tags: [browser, cloakbrowser, cdp, job-applications, autofill, anti-detection]
---

# CloakBrowser Anti-Detection Job Form Automation (`vb-jobs` Standard)

## Overview
All job browsing, form prefilling, and application submission inside AutoApply run through the isolated **CloakBrowser** Chromium instance on CDP port `127.0.0.1:19225` (with companion bridge at `http://127.0.0.1:19299`).

## Non-Negotiable Execution Rules

1. **Human-Paced Typing (Never Instant Dump):**
   - Never dump full strings instantaneously into form fields in a way that triggers anti-bot heuristics on Greenhouse, Lever, Ashby, Workday, or LinkedIn.
   - Scroll each target control smoothly into the viewport before interacting.
   - Move the pointer along a multi-step human trajectory (`Input.dispatchMouseEvent` `mouseMoved` -> `mousePressed` -> `mouseReleased`) and focus the field.
   - Type character-by-character using hardware-trusted CDP key events (`Input.dispatchKeyEvent`) or human-paced input steps with randomized `32ms–68ms` inter-keystroke jitter and `180ms–320ms` inter-field pauses.

2. **LinkedIn Job Feeds (`/jobs/`, `/jobs/collections/`, `/jobs/search/`):**
   - On LinkedIn `/jobs/` home feeds where clicking a card does not open a split right-hand detail pane, navigate directly to the canonical `/jobs/view/<job_id>/` URL (`vb-job-application-operator` rule) while persisting the pending Prefill / Apply state so the form opens automatically upon page load.
   - Never report "Complete" or "Prefilled" if `0` fields were typed and `0` files were uploaded. Always open the Easy Apply modal or external ATS application form first.

3. **React-Select & Combobox Dropdowns:**
   - Focus the `.select__input` / `role="combobox"` element, dispatch `ArrowDown` (`keyCode: 40`) to open the menu, wait `150ms` for `.select__option` / `[role="option"]` nodes to mount, and click the matching option.

4. **Manual User Field Corrections -> Knowledge Base Update:**
   - Whenever the user manually edits or corrects any form field on a job application page, detect the modified `(question_label, final_value)` pair and surface a one-click **Update Knowledge Base** button in the extension.
   - Saving updates persists the answer to `screening_qa` / `qa_bank.md` and candidate memory so future applications automatically use the updated answer.
