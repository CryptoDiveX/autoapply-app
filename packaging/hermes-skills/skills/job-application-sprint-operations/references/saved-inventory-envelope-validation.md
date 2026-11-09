# Saved inventory envelope validation

1. Normalize the actual response envelope before filtering an already-saved inventory. A full readback can store the JSON under `body`, with records under `body.data`, rather than expose top-level `data`. Decode a string body as JSON only when that is its observed type.
2. Assert the expected successful response, actual record container, plausible row count and `attributes.company_name` schema before accepting a negative employer result. Never convert an absent guessed key into an empty inventory through a default empty list.
3. Preserve a failed projection and recover only the local read-only verifier before dependent source fetches. Reuse the same saved inventory. Do not fetch authenticated systems from a public-only scout, replay candidate actions or erase earlier evidence to repair the schema error.
4. Treat filename-search results as discovery candidates. Resolve each returned path and confirm that its basename actually matches the requested pattern. Unrelated broken dependency symlinks do not establish target history or a completed exact-artifact check.
