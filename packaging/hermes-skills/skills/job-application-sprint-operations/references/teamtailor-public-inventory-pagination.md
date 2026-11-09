# Teamtailor public inventory pagination

1. Follow each exact observed Show more href through public read-only GET and preserve the final redirect URL. A `/jobs/show_more?page=2` link can normally redirect to `/jobs?page=2`.
2. Preserve identifiers and query strings exactly. Later published Show more hrefs can contain both the previous page parameter and the next one. Do not normalize, reconstruct or guess the next link.
3. Deduplicate actual role URLs across every returned page. Compare their cardinality with the board's declared job total before claiming complete coverage. Preserve every page response and its observed next link.
4. Keep exact expired roles separate from current sibling openings and their location labels. A complete board lacking a matching title does not establish employer-wide closure. A Manila Fully Remote card does not establish Batumi engagement.
5. Remain public-only: no browser session, candidate routes, accounts, authentication or form actions are needed for this inventory procedure.
