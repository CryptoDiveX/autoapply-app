---
name: career-application-documents
description: "Use when tailoring resumes and cover letters to job posts."
version: 1.0.0
metadata:
  hermes:
    tags: [resume, cover-letter, career, pdf, ats, documents]
    related_skills: [pdf, docx]
---

# Career Application Documents

## When to use

Use this skill when a user provides a resume and a job posting and wants a tailored resume, cover letter, application package, or polished PDF deliverables. It applies to technical, executive, regulated, public-sector, and other high-stakes applications.

## Core standard

Optimize fit without weakening credibility. Every claim must be traceable to the source resume or other candidate-provided material. Reframe and prioritize facts, but never invent experience, metrics, titles, dates, tools, eligibility, or language proficiency.

## Workflow

For session-specific lessons on application-copy quality, tracker-note readability, browser run modes, and compact overnight cron prompts, see `references/job-application-copy-tracking-corrections-2026-09-03.md`.

### 1. Lock the operational requirements

1. Confirm that both the source resume and full job posting are available.
2. Extract the exact company name and exact role title from the posting.
3. Use a date tool for any requested current date. Do not infer it from conversation metadata.
4. Honor the requested destination directory before generation. If the user asks for Downloads, write the final files there rather than leaving them in a workspace or temporary directory.
5. Record hard formatting constraints such as page limits, filename patterns, punctuation bans, font expectations, and whether the chat or session must be renamed.
6. If session renaming is required in Hermes, list sessions, identify the current session by recency and workspace, rename that verified ID, then list again to confirm. Never guess a session ID.

### 2. Extract both content and visual evidence

1. Extract selectable text from each input PDF. Prefer a PDF text extractor or PyMuPDF when programmatic extraction is needed.
2. Render the source resume pages to images and inspect them. Text extraction alone does not reveal typography, spacing, density, page-break quality, hierarchy, or visual rhythm.
3. Capture the source resume's page size, margins, type scale, header treatment, date alignment, bullet style, section flow, and density.
4. Treat visual instructions in the user's brief as requirements, not suggestions.

### 3. Build a job requirement map

Organize the posting into:

- Mandatory education, experience, eligibility, and language requirements
- Preferred or asset qualifications
- Technical methods, tools, platforms, and domain knowledge
- Delivery expectations such as CI/CD, monitoring, quality, experimentation, or ownership
- Communication, collaboration, judgment, and personal attributes
- Location, time-zone, relocation, travel, or regulatory constraints
- Organizational tone and values

Rank the requirements by importance and repetition.

### 4. Diagnose candidate fit before writing

Create three internal groups:

1. **Direct matches:** explicitly supported by the source material.
2. **Transferable matches:** supported experience that can be honestly reframed toward the role.
3. **Gaps:** requirements not supported by the source.

Do not convert interest in a target technology into claimed experience. For example, a cover letter may express interest in RAG, OCR, evaluation, or fine-tuning, but the resume must not claim hands-on delivery unless the source supports it.

### 5. Tailor the resume

1. Write a role-specific headline and summary using only supported facts.
2. Elevate the most relevant work into a dedicated section when that improves the narrative.
3. Reorder sections for relevance while preserving each role's real title, organization, and dates.
4. Write substantive bullets that connect actions, systems, ownership, and outcomes.
5. Mirror important posting language only where the candidate's evidence supports it.
6. Compress less relevant work without erasing chronology.
7. Use a selected project or technology portfolio when it helps expose relevant evidence and balance a two-page layout.
8. Keep skills accurate, normalized, correctly spelled, and easy for ATS parsing.

### 6. Write the cover letter

1. Keep it to one page unless the user requests otherwise.
2. Open with a specific, natural sentence that ties the role to the employer's product, customer workflow, or human service moment. Avoid banal first sentences unless a form field forces very short plain text.
3. Lead with what the candidate has done: proven wins, customer impact, product judgment, and the human experience around the work.
4. Use two or three strong examples from the tailored resume.
5. Show why the examples transfer to the employer's challenges.
6. Address eligibility or language only when supported.
7. Mention unsupported target areas as motivation or interest, never as completed experience. Do not volunteer gaps, missing experience, or self-sabotaging negative comparisons in candidate-facing copy unless a direct legal, eligibility, or form question explicitly requires it.
8. If the user specifies a dedicated copywriting model, provider, or style authority for application documents, use it for cover letters, resume wording, and screening answers.
9. Close with a concise request to discuss fit.

### 7. Design for ATS and human review

- Use selectable text and a simple reading order.
- Prefer Letter or the source document's page size unless the user specifies another standard.
- Use clear hierarchy, restrained color, consistent typography, and right-aligned dates.
- Dark navy section headings and subtle rules are a reliable professional pattern when consistent with the brief.
- Use tables only for simple alignment or visual cards. Avoid complex multi-column structures that scramble extraction order.
- Keep headings with their following content.
- Avoid a page break immediately after a heading.
- Avoid a nearly empty second page. Rebalance content, adjust spacing, or add a concise factual project portfolio rather than inserting filler.
- Match the source resume's formatting spirit, not necessarily every pixel.

### 8. Generate the final files

Use deterministic filenames derived from the candidate name and role or organization. Create the final PDFs directly in the requested destination. Temporary HTML, images, or scripts may remain in a temporary directory, but the deliverables must not.

For a proven programmatic PDF workflow and QA checklist, read `references/pdf-generation-and-qa.md`. For DOCX-to-PDF cases where emoji or special fonts must match the DOCX visually, read `references/native-word-export-emoji-pdf.md`.

### 9. Verify before delivery

When a source DOCX uses emojis or special color fonts, do not assume every PDF renderer preserves them. LibreOffice headless may render a valid PDF while dropping Apple Color Emoji. If exact visual parity is required, use the platform's native renderer, such as Microsoft Word on macOS, or replace decorative emoji with image icons and disclose the tradeoff.

Verification is mandatory:

1. Open each PDF programmatically and verify the expected page count.
2. Re-extract text and confirm the candidate name, organization, and exact role where appropriate.
3. Scan extracted text and generation sources for forbidden punctuation, forbidden characters, and self-sabotaging gap language such as `I do not have direct experience`, `I have not shipped`, `I want to be upfront`, or `where my experience does not reach`.
4. Check for replacement glyphs, missing text, clipping, and suspiciously small files.
5. Render every final page to an image.
6. Visually inspect clipping, overlap, margins, date alignment, font size, hierarchy, blank regions, orphaned headings, and page-break quality.
7. Regenerate after any material visual defect, then repeat the checks.
8. Report only verified page counts and file paths.

## Hard-constraint handling

A user's punctuation or style ban applies to all requested documents and any accompanying delivery text when the brief says so. Do not merely avoid typing the character during drafting. Scan the source used for generation and the extracted text from the final PDFs.

## Common pitfalls

- Treating a submitted application as complete before tracker entry is verified. If the workflow includes Teal or another tracker, read the saved record back and confirm status, applied date, URL, files, exact submitted answers, salary answer where known, and readable notes.
- Submitting form answers without validating the requested unit and live field value. Days should be normal integer days, years should be normal year counts, and salary or CTC fields should match the requested currency and period. Values like negative decimals or thousands-formatted experience years are a hard stop.
- Using direct DOM assignment as the only fill method on React application forms. Prefer trusted field `fill` or typing, blur the field, then read actual input and textarea values back from the live page before submit.
- Saving tracker notes as a wall of text. Use section headers, blank lines, and one bullet per real newline. Record form questions and answers verbatim.
- Mixing browser-use modes across a batch run. If the user is actively using the computer, avoid focus stealing; if the user explicitly authorizes full overnight browser use, state that run-mode override in the worker prompt.
- Letting long cron prompts and continuity summaries consume context. For overnight application runs, keep prompts compact and store state in local files.
- Tailoring by keyword stuffing rather than evidence
- Claiming a target framework, model-evaluation method, or language level that appears only in the posting
- Producing a polished-looking PDF without checking whether its text is selectable
- Verifying only page count and skipping visual inspection
- Leaving the final artifact in a temporary directory after the user named a destination
- Treating large blank regions as harmless when the brief explicitly asks for a balanced page
- Using a dense one-page layout when two balanced pages would be more legible
- Creating a second page with only a heading and a few lines
