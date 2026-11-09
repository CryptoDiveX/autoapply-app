# Native Word export and emoji PDF parity

Use this when a resume or cover letter DOCX contains emoji, special color fonts, or other styling that does not survive LibreOffice headless export.

## What was learned

A DOCX generated with the Node `docx` package can contain real Apple Color Emoji runs. LibreOffice headless may still create a valid PDF with selectable text, but the emoji can be missing visually or inconsistently extracted. Microsoft Word on macOS exported the same DOCX to a PDF where the emojis were visible and extracted as real emoji text.

## Recommended workflow

1. Generate the DOCX normally.
2. If visual parity matters, open/export through Microsoft Word on macOS.
3. Verify with PDF metadata and text extraction:
   - expected page count
   - not encrypted
   - not scanned
   - expected candidate name and role text
   - no forbidden punctuation or placeholders
   - expected emoji characters, for example `💼` and `🎓`, if the task requires true emoji text
4. Render every PDF page to PNG and visually inspect section icons, margins, clipping, overlap, and page balance.
5. If Microsoft Word cannot be automated cleanly, use image icons only as a disclosed visual fallback. Image icons can preserve appearance but are not selectable emoji text.

## macOS Word file access

Microsoft Word may show `Grant File Access` when AppleScript exports files. Prefer scoped access over broad access:

- Select the project folder when the dialog allows it.
- Select the specific input or output file when the dialog requests an exact file.
- Do not recommend Full Disk Access when the user asked for folder-scoped access.

## Pitfall

When automating Word, verify the active document before export. A prior session saved the open resume under a cover-letter output name because Word's active document was not the intended cover letter. Always re-read the exported PDF text and confirm document-specific phrases, such as `Dear Hiring Team` for a cover letter.
