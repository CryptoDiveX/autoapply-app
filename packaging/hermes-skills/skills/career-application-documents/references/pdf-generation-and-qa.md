# Programmatic PDF Generation and QA

Use this reference when a tailored resume and cover letter must be delivered as polished PDFs rather than editable source files.

## Recommended generation pattern

A deterministic PDF library is often the safest final path because it gives direct control over page size, margins, spacing, page breaks, and selectable text.

For ReportLab-style generation:

1. Use `SimpleDocTemplate` or `BaseDocTemplate` with an explicit page size and margins.
2. Define reusable paragraph styles for name, contact line, headline, summary, section heading, role, organization, dates, bullets, skills, and cover-letter body.
3. Use a restrained palette, for example dark navy for hierarchy, near-black for body text, a muted blue-gray for secondary text, and a pale blue-gray for portfolio cards.
4. Use `Table` only for controlled alignment such as role/date rows, two-column skills, or a small project portfolio.
5. Use `KeepTogether` for a role header plus its first bullets.
6. Use explicit `PageBreak` when the desired two-page narrative is known.
7. Add a small footer with candidate name, application label, and page count.
8. Set PDF metadata such as title, author, and subject.

## Page-balancing method

Do not accept the first PDF merely because its page count is correct.

1. Render every page at a readable scale.
2. Identify the lowest meaningful content block on each page.
3. Check whether the remaining whitespace looks intentional.
4. If page one is too dense and page two is sparse, redistribute sections rather than shrinking all text.
5. A concise selected-project portfolio can expose factual evidence and improve balance without adding unsupported claims.
6. Adjust section spacing, table padding, and leading in small increments.
7. Re-render after every material adjustment.

Avoid solving balance problems with filler text, decorative graphics, or inflated claims.

## Cover-letter layout

A reliable one-page structure is:

- Candidate name and contact header
- Date
- Hiring team and organization
- Exact role in a subject line
- Salutation
- Four or five short justified paragraphs
- Closing and candidate name

Justified text can create wide gaps on short lines. Inspect the rendered page, not only the source. If spacing becomes distracting, revise sentence length or use left alignment unless the user's brief requires justification.

## Text verification checklist

After generation, open each PDF with a PDF parser and verify:

- Expected page count
- Candidate name
- Employer name
- Exact role in the cover letter
- Required contact details
- No replacement glyphs such as `\uFFFD`
- No prohibited punctuation or characters
- Selectable extracted text of plausible length

When a character ban is strict, scan both the generation source and the text re-extracted from the final PDF. This catches characters introduced by copied source material or later edits.

## Visual verification checklist

Render all final pages and inspect:

- No clipping or overlap
- No orphaned section heading
- No heading stranded at the bottom of a page
- Dates aligned consistently
- Bullets wrapped cleanly
- Fonts large enough for normal reading
- Margins consistent across pages
- Second page contains a meaningful amount of content
- Footer does not collide with content
- Cover letter remains on one page
- Visual hierarchy matches the source resume's spirit and the user's brief

## Factual guardrail

If the posting asks for tools or methods absent from the source resume, do not insert them into the skills section or experience bullets. They may be mentioned in the cover letter as areas of interest, provided the wording does not imply prior delivery experience.

## Delivery check

Write the final PDFs directly to the user's requested destination and verify those exact paths. Temporary scripts and rendered QA images belong in a temporary working directory, not beside the final deliverables unless requested.
