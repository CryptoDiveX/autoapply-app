# Humi public careers inventory

1. Inspect the official employer page for the exact `div#HumiJobBoard`, `data-company` value and observed public embed script. A careers heading with no cards does not establish an empty inventory.
2. Read that script offline. When its `HumiJobBoard.ts` client explicitly builds `https://<slug>.applytojobs.ca/v1/embedded` with public `credentials:omit`, GET only that exact published read-only inventory. Preserve the official page, attributes, script construction, requested/final URLs, timestamp and complete response. Do not execute the script or call candidate endpoints.
3. Deduplicate repeated title and Learn More links by their exact actual role URL. Inspect every returned department, title and location before concluding there is no supported product, delivery or customer-workflow vacancy. Keep absence of a matching role separate from employer-wide closure.
4. Preserve labeled headquarters separately from role location. A valid employer-country source, a generic hiring invitation and unrelated active roles do not clear exact remote hiring geography, form, account, consent, challenge or file-delivery gates.
