# VB Jobs Application Template Staging

Reusable staging folder for VB Jobs applications.

Files:
1. `headshot.png`, extracted from a verified prior photo resume DOCX.
2. `build_resume.js`, house resume DOCX builder copied from Claude handover.
3. `build_letter.js`, house cover letter DOCX builder copied from Claude handover.
4. `manifest.json`, source and checksum details.

Use:
1. Copy this whole folder to a company work directory.
2. Edit only the content blocks and filenames in the JS builders.
3. Run `npm install` if `node_modules` is missing.
4. Run `node build_resume.js` and `node build_letter.js`.
5. Render outputs and visually verify before upload.

Rules:
1. No fabricated claims.
2. No em dashes.
3. Cover letter is always included.
4. Use the photo on both documents.
