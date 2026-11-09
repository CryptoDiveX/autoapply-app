# Public source encoding

1. Retain original public HTTP response bytes before decoding. Honor an explicit HTML charset or verified UTF-8 rather than blindly accepting requests.text defaults, because a missing HTTP charset can produce Latin-1 mojibake in valid role and legal pages.
2. Preserve failed text derivatives and recover only offline decoding into distinct evidence files. When saved text is reversibly Latin-1 decoded UTF-8, document that transformation and retain the original derivative.
3. Verify exact employer names, role labels and quoted clauses after decoding. Never rewrite candidate prose, refetch an unchanged role, reupload or repeat an outbound action merely to repair source encoding.
