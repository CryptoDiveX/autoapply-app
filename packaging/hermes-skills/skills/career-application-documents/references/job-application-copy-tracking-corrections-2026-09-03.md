# Job Application Copywriting And Tracking Corrections, 2026-09-03

Session-specific lessons from a VB Jobs overnight application run. Use this as a reference for application-document workflows when a user cares about submitted-package review and tracker readability.

## Copywriting quality

- The user rejected generic cover-letter openings and weak copy.
- Prefer a specific, concrete first sentence tied to the product, customer workflow, or human service moment.
- Lead with what the candidate has done. Do not volunteer gaps, missing experience, or negative comparisons in candidate-facing copy unless a direct legal, eligibility, or form question explicitly requires it.
- Remove self-sabotaging phrases before submission, including `I do not have direct experience`, `I have not shipped`, `I want to be upfront`, `where my experience does not reach`, and `I do not carry a dedicated...`.
- If the user specifies a model or writing provider for application copy, treat it as a workflow requirement for resumes, cover letters, and screening answers.

## Screening and form-answer quality

- Build an intended answer map before submit: question text, intended answer, requested unit, and field type.
- Validate live form values after filling and before clicking submit. Read back actual input and textarea values from the page, not just the script's intended payload.
- For React-style ATS forms such as Workable, do not rely on direct DOM value assignment alone. Use trusted field `fill` or typing, blur the field, wait briefly, then compare actual values against the intended answers.
- Numeric answers must match the question's unit. Notice period in days should be an integer such as `14`. Years of experience should be a normal year count. CTC or salary fields must match the requested currency and period or use concise `N/A` language when the requested compensation structure does not apply.
- If a submitted Workable application has bad answers and the user authorizes repair, withdraw via the visible candidate-page link, reapply in a clean browser context, verify the corrected confirmation email, and check the conflict page if Workable reports multiple applications.

## Tracker notes must be readable

When logging application details in a tracker such as Teal:

- Use section headers on their own lines.
- Put a blank line between sections.
- Put every bullet on its own real newline.
- Record every form and questionnaire question plus the exact answer verbatim.
- Verify by reading the saved tracker record back, not by trusting the write call.

Good note shape:

```text
SUBMISSION

• Status: Applied
• Date applied: 2026-09-03
• Source URL: https://example.com/job

FORM ANSWERS

• Question: Are you authorized to work in this location?
• Answer: [exact submitted answer]

ACCOUNT

• Account created: Yes, standard credentials set used
```

## Browser mode must match the user's current situation

- Active computer use: avoid focus stealing and visible browser hijacking. Use background CDP or background computer-use delivery where possible.
- User away overnight: if explicitly authorized, full visible browser automation is allowed for the run only.
- Put the selected browser mode directly in the cron or subagent prompt so workers do not mix policies.

## Cron prompt size

- Long preloaded skill stacks plus continuity can blow up cron context.
- Keep overnight prompts compact.
- Avoid injecting long prior outputs. Save state in local files and read only the target-specific files needed for the current application.
