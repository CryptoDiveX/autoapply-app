# Outreach follow-up workflow

For an incoming recruiter email with a personalized JobDiva/JobOpportunityForYou resume-response link, use [linked resume response verification](jobdiva-linked-resume-response.md).

Use this for user-authorized recruiter replies, openings inquiries, post-call follow-up, follow-up after a verified application, and explicitly authorized application withdrawal or candidate-data deletion requests. Keep outreach distinct from application success. Withdrawal correspondence is administrative, not recruiting outreach.

## Procedure

1. **Resolve the requested conversation or contact.** For cold outreach, prefer the job post, company careers/contact pages, public LinkedIn profiles, and exact published business addresses or numbers. For a user-authorized reply to an incoming recruiter, verify the observed sender or Reply-To against the actual thread and company identity and retain that message as provenance. Do not guess addresses, widen recipients or substitute a new company inbox for the requested thread.
2. **Keep recipient scope appropriate.** For a new contact-discovery pass, prioritize recruiter/talent, hiring manager, product leader, founder/operator, or role-adjacent team member. For an existing recruiter reply or post-call thank-you, use the known conversation instead of opening a parallel multi-person outreach campaign. Do not invent who attended a user-reported call.
3. **Write the message in the channel language.** Use Russian for Russian postings or Russian contacts unless English is clearly more appropriate. If a Russian-language message addresses a clearly Russian person, use a Cyrillic/Russian name form.
4. **Use the reply-oriented structure.** Greet, say Alex saw the role on the source, give one concise relevance reason, then end with a direct question asking who to discuss the role with. This sounds less generic than a simple `I applied` notice.
5. **Prefer a personalized LinkedIn note, with a verified quota fallback.** Check the exact person's canonical profile for an existing Pending/connected state before acting. When several visible Connect controls expose the same observed recipient-specific invite href, preserve all controls but deduplicate by that exact href and verified canonical profile before requiring a single destination. Recover only navigation/readback after a duplicate-control assertion; never repeat an existing send action to repair proof. Scope Connect to that person's accessible name or observed custom-invite href, then verify that the invitation dialog names the intended recipient. If the personalized-note allowance is exhausted, Vasya authorizes `Send without a note`. Reopen the canonical profile and require the recipient-specific Pending control before recording success; a dismissed invitation modal alone is not proof. Save the prepared note separately, but record the actually sent no-note request with empty `message_text`. Never duplicate a pending request or buy Premium.
6. **Check current professional contact sources before using another channel.** Inspect the person's own Contact info, current About/hiring posts and employer-controlled pages, then search the exact name with work-email/phone terms. If navigating an observed Contact info href redirects to the profile without opening its panel, click the live Contact info anchor and read the visible overlay. Save exact source URL and text for any email or number. Reject masked snippets, guessed email patterns, other people's numbers, former-employer addresses and private contact-broker data; none establishes a usable current professional contact. If no verified address/number is found, log that bounded result and send no email, SMS or WhatsApp. Review again after invitation acceptance rather than inventing details.
7. **Send or attempt through the safest available channel.** Email and LinkedIn are normal first choices. Use WhatsApp only when the number is publicly listed in a business context or explicitly authorized. For WhatsApp, prefer WhatsApp Web in the persistent VB Jobs Cloak profile for low-volume manual or semi-manual work. When WhatsApp Web is logged in but CDP automation times out, or when WhatsApp outreach needs repeatable sending, use the standalone CLI recipe below with persistent `LocalAuth`; Vasya has approved this path for VB Jobs outreach. Treat the CLI as an unofficial WhatsApp Web client, so log every attempt, respect public-contact limits, and stop if WhatsApp asks for re-authentication, account checks, or other human verification.
8. **Record every contact and attempt in the outreach database.** Retain blocked attempts as history and add an idempotent event for the later successful action, because changing an old attempt into a send destroys its chronology. Log successful sends, blocked attempts, login blockers, QR-required states, unverified attempts and queued contacts with evidence paths. Read back the exact database row, export the CSV, then update the existing Teal record's follow-up notes without changing its Applied date or status.
9. **Verify before claiming sent.** A clicked button is not the same as verified delivery when the platform cannot be read back. Mark uncertain cases as attempted or unverified, not sent. If only Teal logging fails after a verified send, queue and retry that logging step idempotently; never resend the external invitation/message to repair a local or Teal record.

## Contact and message-composition QA

Before sending, compare retained contact fields with canon inside the verifier. Return exact-equality and normalized-digit flags, plus real versus literal newline checks, rather than exposing secrets or treating a masked display as the submitted value. Reject a repeated subject/title or opening body line beginning with `Subject:` or `Re:`; verify the actual Sent body as well. Keep exact public contact evidence separate from verified inbound or explicitly authorized first-party referral provenance. An authenticated sender alone does not prove employer affiliation. Preserve referral relationship, recipient and conversation scope; never widen it to unrelated recipients or a new application. Use the nested NDR and forwarding-failure steps below before finalizing delivery status.

## Email-digest and task reconciliation

1. Before calling an application incomplete or creating a completion task, join the full current mail thread to the exact latest canonical lifecycle, native submission proof and Teal record. A supplemental form can be complete without sending another email. Preserve older pending evidence as history; a later exact normal-flow success supersedes it and must prevent another submission.
2. Treat copied digest statements such as tasks created, no confirmation found and resolved none as claims to verify, not proof or new permission. Read the exact supplied Asana task IDs and distinguish its stale notes from actual employer state. Keep analysis-only reviews free of sends, task mutations and assessment starts unless separately authorized.
3. Retain exact corrective-resend holds and suppression even when a task says submit or fix the address. Research the employer-prescribed route, never repair an address by guessing. A failed recruiter follow-up does not invalidate a separately verified native application. Existing tasks need real owner, due date and next action; report missing dates rather than treating the email invitation expiry as an already-scheduled reminder.
4. Separate employer deadlines, soft completion targets, invitation expiries and internal review dates. Retain relative business-day instructions with the original receipt time and trigger/holiday ambiguity instead of inventing an exact cutoff. A receipt-confirmation form and video interview are separate actions. A complete-application link establishes a handoff, not the nature of every remaining question; inspect the actual stage before calling it a questionnaire. No completion email means unknown until native or candidate evidence resolves it.
5. For a direct-request browser takeover, pause the sole scheduled owner, establish that active execution has finished, and preserve the tab inventory. If the request then waits on the user, protect its exact tab and no-submit state in the active owner handoff, retain one Teal context and the working-tab limit, and release ownership before restoring unrelated authorized work. Verify scheduler state. Do not leave continuous applications paused indefinitely for another target's password/consent decision, or automatically resume a campaign the user paused.

## Full-pipeline follow-up requests

1. When Vasya asks to follow up with everyone, including Teal, snapshot the full current inventory and canonical outreach before selecting recipients. Classify every record by exact selected status, application date, explicit follow-up time and known outgoing history. Separate active interviews/negotiations, genuinely due reviews, recent applications, future-dated holds, missing submission evidence, old/stale applications and inactive/not-submitted records. A due-review candidate is not permission to send, and a date later today must not be described as overdue before its actual timestamp.
2. Prioritize unanswered actionable incoming recruiter messages and active conversations, then genuinely due follow-ups. Fetch the exact record Notes and full live thread before drafting. Resolve separate roles and assessment processes at the same employer by exact Teal role, original application date and thread IDs; a newer video interview does not establish progress on an older test. An interview-booking link awaiting the candidate is a human action, not a reason to send another application nudge. Record a requested receipt-confirmation form separately without opening an assessment, accepting recording terms or claiming completion. An automated no-reply ATS receipt is not a human recruiter conversation, and an empty bounded mail search leaves older history unresolved rather than proving no contact. Do not claim booking, screening completion or an accepted legal agreement. Older applications require current context and a valid route, not a blanket message merely because their dates are old.
3. Serialize the finite pass through the existing sole application/browser owner. Save an explicit request file, full review queue and durable per-record decision/cursor. Update both the active brief and persisted owner prompt/notepad. If the owner is running, preserve it and call the new task queued until adoption is evidenced; never start a second authenticated follow-up worker or claim edits changed an in-flight context. Process bounded follow-up batches alongside continuing authorized applications without resetting the numeric target. Existing first-DM no-repeat rules remain.
4. Interpret historical outreach `sent_at` alongside its channel, status, actual message body and positive send proof. An unsuccessful Connect or message-box attempt can carry a populated timestamp; preserve it as an attempt, not a real outgoing message or a seven-day waiting-period anchor. Recover the actual conversation before choosing either a follow-up or a retry.
5. Record actual verified sends separately from holds, reviewed contacts, unresolved history and candidate actions. Recheck the last real outgoing message before each send, respect explicit due dates and avoid immediate repeat nudges. A broad finite follow-up request is not permission for an indefinite repeating-message schedule. Append the exact sent text and next owner/date to the exact Teal record while preserving its stage, source, role and application date. Report a metadata scan or queued pass honestly, never as messages already sent or every conversation already reviewed.

## Same-thread email and screening replies

1. **Read before drafting.** Find the exact subject or company, fetch `HOME=~ gog -a alex.mercer@example.com gmail thread get <thread-id> --json`, and inspect all current messages. Search across matching threads rather than stopping at an automated support acknowledgement, because ticket systems can separate the acknowledgement from the substantive reply or add a company prefix to its subject. When nested `--select` fields yield `{}`, fetch full JSON and filter it locally instead of concluding the thread is empty. Decode text/plain MIME parts when available; otherwise render the HTML as text. Recheck the latest message immediately before send because an assessment link or recruiter reply can arrive while copy is being prepared.
2. **Choose scope and length.** For an openings inquiry, explicitly distinguish a job at the recruitment company itself from its client opportunities. For an employer-provided HR referral that Vasya explicitly asks to action, apply the first-party provenance rule in SKILL.md: retain the exact referral message, match the company and support relationship, extract the referred person's name/address verbatim, and search Sent for an existing equivalent handoff before drafting. Address the referred HR person, briefly name the referrer and role, give one relevant fit reason and ask about the next step; target roughly 70-100 words excluding the signature rather than repeating the original application. Do not stop at acknowledging support or repeat broad contact hunting after the exact authorized recipient is resolved. For a post-call thank-you, use only the user's stated call facts and ask about the requested next step, not an assumed appointment. For screening, retain separate question identifiers in the internal draft and check all are answered, with short numbered sections in the email. Keep legal and monitoring information separate from questions so an ordinary reply does not accidentally accept those terms.
3. **Preserve provenance without regenerating needlessly.** Keep model requests, raw responses and parsed revisions immutable. Save each fresh mutable thread snapshot under a new revision instead of asserting that labels or history metadata are identical to an earlier read. Do not hard-code an expected thread message count as the definition of safety; compare exact relevant message IDs, recipients and any already-sent equivalent reply. For missing evidence, use a supported alternative story without inventing negative claims. Deterministic headings and numbering may assemble model-authored answers; record exact span sources and omissions.
4. **Send once using reply metadata.** Use the existing subject, exact intended recipient and an actual observed message from the original thread, normally its latest relevant incoming message:

   ```bash
   HOME=~ gog -a alex.mercer@example.com gmail send \
     --to <verified-recipient> \
     --subject '<existing reply subject>' \
     --reply-to-message-id <incoming-gmail-message-id> \
     --body-file <approved-body.txt> --json --no-input
   ```

   For an authorized handoff to a referred HR person, set `--to` to that exact referral address while anchoring `--reply-to-message-id` to the observed referring email. Preserve the latest relevant subject, including an employer-added prefix; do not use reply-all or carry customer-support CC/BCC recipients into the HR handoff unless requested. Verify the resulting thread ID instead of assuming that matching subjects or a changed recipient preserve threading.

   Add `--attach <exact-approved-resume>` only when requested and only after the immediate in-script approved-file guard. Never use a guessed RFC Message-ID where the command expects the Gmail message ID. Complete draft and recipient QA before recording a durable send intent. Protect the outbound step with an exclusive local lock, write that intent immediately before the guarded send, then save the provider result before any readback. If the result exists, resume verification and logging rather than rerunning the sender. If an intent exists without a provider result, inspect exact Sent recipient, subject, body and timing first, because a timeout can occur after provider acceptance; do not interpret a missing receipt as permission to send again.
5. **Verify exact state.** Fetch `gmail get <sent-message-id> --json` and the original thread. Require the intended From, To, subject, Sent label, original `threadId` and exact approved body after CRLF normalization. Verify the attachment is absent for a text-only reply or download and hash the actual attached approved PDF when present. A failed readback is not permission to resend: retry only the bounded read-only retrieval using the saved provider ID. Check matching bounces and retain their purpose separately from application success.
6. **Decode nested delivery-status content.** Gmail can represent `message/delivery-status` as a container with an empty body and a child `text/plain` part. Carry delivery-status ancestry through the MIME walk and decode every descendant body before comparing Final-Recipient, Action, Status and the original In-Reply-To. An empty parent body does not establish that no delivery status exists. Preserve the actual Sent and attachment proof, revoke application credit on a correlated failed inbox, and never resend to repair the parser.
6a. **Include Spam and Trash in delivery-failure discovery.** Prefix bounded Gmail NDR searches with `in:anywhere`, including employer-domain postmasters, because a genuine correlated rejection can be classified as Spam while the default search stays empty. Broaden a suspiciously empty one-day result to three days and correlate each recovered NDR by the original RFC Message-ID and decoded Final-Recipient. Treat an indexed message whose exact GET returns404 as unavailable current evidence, not as proof of delivery or permission to clear historical no-retry protection. Preserve the saved exact proof and never resend to repair retrieval. Normalize optional MIME header values with `header.get('value', '')` before building a header map so a missing optional value cannot interrupt failure reconciliation.

7. **Append, do not restage history.** Fetch the exact existing Teal record first, append readable exact sent text and next action, and read back the note, status relationship and original `applied_at`. Change only follow-up fields for ordinary outreach; neither a historical applied date nor an archived/incident stage should be silently replaced. Add an idempotent outreach event keyed to the actual sent message, then export the complete SQLite table and compare every CSV field with null normalized to an empty value.
8. **Set a bounded follow-up.** Record owner, due date and what is awaited, then create or reuse one matching reminder. For an assessment invitation, report the link and deadline without promising completion or starting screen sharing. Keep the reminder read-only unless a new send is explicitly authorized. Confirm saved reminder state before claiming it is scheduled, and keep runtime failure notices local.

## Accepted LinkedIn connections and recurring follow-up

1. **Require actual acceptance and original job relevance.** Join current first-degree profile or Connected on card evidence to the exact canonical profile URL in a recorded job-related invitation. When recent-card scrolling repeatedly exposes the same window, reconcile a bounded batch of unresolved tracked profiles rather than checking only the newest invitation each tick. Select source events with positive recipient-specific Pending or Sent/Withdraw proof, not a substring match on `sent`, because `not sent` and discovered-only records are not invitations. Filter this positive invitation set before taking a bounded slice; slicing the newest unfiltered rows first can select only discovered contacts and silently perform no acceptance checks. Require a saved live readback for each claimed checked profile and advance a persistent coverage cursor rather than repeatedly scanning only the latest contacts. Exclude globally messaged people and uncertain send intents before opening profiles. Save per-profile readbacks and a coverage cursor, retain incomplete requests as partial, and never message a newly accepted person without separate current-country and loaded-history checks. When a historical source contact label appends employer context to the person's name, preserve that composite label separately from the observed live display name. Require the exact canonical profile and live Pending or first-degree identity, rather than requiring the entire descriptive label to occur in the header. After a label-only monitor assertion fails, recover only monitor/log persistence under a new evidence revision; never repeat a profile invitation or message to repair the label. Sort connections Recently added and save extraction batches. Stop only after the observed dates cover the relevant tracked invitation period, or reconcile every unresolved tracked profile individually. Do not equate new connections, Pending invitations, contact research or unverified invite clicks with accepted job contacts. Unresolved job mapping means skip and log.
2. **Deduplicate people across roles and check live history.** Before a first post-acceptance message, inspect canonical outreach, per-profile tracking, all prior send intents/receipts and the actual recipient conversation. If a newly accepted contact already received a recent verified email for the same job, record the acceptance separately and hold the LinkedIn DM rather than creating an immediate cross-channel duplicate. Preserve the actual email receipt as the reason, keep monitor `sent_at` unchanged for a DM that was not sent, and keep `runs.sent_count` at zero for that observation. Search LinkedIn messages by the exact name and require loaded history rather than a blank loading panel. Existing real outgoing messages, visible invitation notes stored as conversation text, previous accepted-follow-up receipts or unresolved send attempts block another automatic message. A person accepting several weeks later does not erase an earlier message. Incoming replies do not authorize repeated nudges or automatic screening answers.
3. **Keep the initial message short and job-specific.** Under explicit user authorization, send at most one concise first follow-up per profile. Use scoped Sonnet5, immutable model revisions, canonical claims, exact role/company, thanks for connecting, one relevant fit reason and one simple question. Ask role-adjacent recruiters to route to the appropriate colleague rather than assuming they own hiring. Do not claim an application or CV was received without evidence. No attachments, em dashes, unsupported expertise, long pitch or automatic second message. Apply current employer-country and role-market exclusions to legacy contacts too; unresolved permitted operating identity remains blocked.
4. **Persist intent and verify a real outgoing event.** Save an exclusive per-profile intent immediately before the sole scoped Send click. Treat an empty contenteditable composer as blank only after trimming its text, because a genuine empty editor can contain a newline. After native insertion, wait in a bounded read-only loop for the exact scoped Send button to enable. Check readiness before creating the durable send intent, not just after a fixed one-second sleep, because LinkedIn can retain the exact draft while its Send button is briefly disabled. Persist the exclusive intent only after the recipient, draft and single enabled Send control are all verified, then immediately recheck those same facts before the sole click. If the correct text is already staged and no send intent exists, recover only readiness and the untouched send stage without retyping or rerunning earlier staging. Continue in the same recipient composer instead of Page.navigate on a staged unsent draft, which can hang its renderer. If a pre-send owned tab hangs, preserve evidence, close only that identified owned tab, verify its removal and reopen. Chrome /json/close returns plain text and closure can be asynchronous, so do not parse it as JSON or assume an immediate target-list read is final. Never recover an uncertain send by clicking Send again. Capture the created thread URL, exact body, sender and time, reload that thread and require the message to persist once.
5. **Maintain a person-keyed state ledger plus canonical records.** Track canonical profile URL, original invitation/job source, company, role, accepted evidence/date, previous-message decision, exact sent text, UTC action time, thread URL, evidence path, last check and status. Preserve LinkedIn displayed connection date separately if it differs from the real UTC clock. Add the exact outgoing body to canonical outreach, export and compare the complete CSV, and append readable notes to the existing exact Teal record without changing its Applied date/status. On a stale saved Teal ID404, fresh-search the exact company and role, preserve both old token and new observed record ID as provenance, and do not invent a replacement ID or create a duplicate record. Outreach earns no application credit. Set owner and review due date, not permission for another automatic message.
6. **Serialize recurring checks with the application owner.** For user-requested every12hour monitoring, prefer a lightweight no-agent scheduler that atomically queues/coalesces a request, with the existing sole background browser owner servicing it before a new application target. Persist the queue-consumer instruction in both owner job prompt and active brief. Never run a competing authenticated browser worker. Acknowledge only the matching request under a queue lock after verified results are saved; preserve incomplete requests for safe retry. User-paused application work must not be automatically resumed by the checker. Verify recurrence, unlimited repeat state, script path and consumer readback. Cron scripts must use a filename relative to the active profile scripts directory; the cron tool rejects absolute paths. Test request creation, pending-request deduplication, acknowledgment/new-request behavior and duplicate-send blocking. Keep routine output and runtime failures local.

## Canonical database

Before adapting a prior target logger, inspect `PRAGMA table_info(outreach_events)` and validate every prepared event key against that exact schema before any tracker mutation. Store an email address in the observed `contact_value` field and its mailto URI in `contact_url` when those are the actual columns; never assume `email` or `contact_title` exists because an older helper used it. Preserve titles in supported metadata. If insertion fails after verified sends or Teal updates, recover only the rolled-back local transaction, full CSV export and unfinished progress records, not the outbound or tracker stages.

- SQLite source of truth: `~/Hermes/job-applications/outreach-database/outreach.sqlite3`
- CSV export: `~/Hermes/job-applications/outreach-database/outreach_events.csv`
- Useful view: `v_recent_outreach`

Minimum `outreach_events` fields:

- `sent_at`
- `company`
- `role`
- `contact_name`
- `channel`
- `contact_value` or `contact_url`
- `source_url`
- `subject`
- `message_text`
- `status`
- `status_class`
- `source_file`

Recommended status classes:

- `sent_or_clicked`: provider send returned success or the platform send/invite button was clicked and readback supports it.
- `readback_positive`: later page readback shows pending/sent/invitation state.
- `blocked_or_opened_not_sent`: login, no send button, message box unavailable, or platform blocked sending.
- `attempted_unverified`: an action was attempted but no reliable platform readback is available.
- `error`: tool or provider error.

## Withdrawal and data-deletion requests

1. **Resolve scope and stop further recruiting actions for the target.** Match the company, role, original posting URL, ATS record and receipt. Preserve submission history. Use the sprint skill to pause or correct stale workers and queues when the user also changes eligibility rules. Do not infer that every employer on a regional job board belongs to that region.
2. **Find the actual withdrawal/privacy route.** Inspect the acknowledgement for an observed manage-application link or withdrawal control, then the employer's candidate-specific privacy notice. Prefer the published candidate privacy or HR contact over general customer support. Save the exact contact, source URL and relevant text. Do not reply to a no-reply ATS address, construct a guessed withdrawal URL or send the request to an unrelated affiliate. If extraction omits the contact section, retrieve the same official page's complete HTML and inspect that section before concluding no contact exists.
3. **Draft a short neutral request.** Use the normal scoped copywriting workflow. Identify the applicant, role and application date or link; state withdrawal effective immediately; withdraw consent to future talent-pool retention; request deletion of the CV, candidate profile, application materials and associated recruitment data, including ATS/processor copies where applicable. Ask for written confirmation and the scope and retention period of any legally required exception. Do not allege unlawful processing, cite an unverified law, repeat the user's frustration, explain excluded nationalities or attach more personal data.
4. **Check for an existing request before sending once.** Search Sent for the exact recipient and withdrawal subject, and inspect any saved send receipt. For Gmail, use the explicit account and a body file: `HOME=~ gog -a alex.mercer@example.com gmail send --to <verified-contact> --subject <subject> --body-file <request.txt> --json`. Omit attachments and tracking. Save the send response before attempting readback, so a readback failure cannot trigger another send.
5. **Verify the exact outgoing message.** Run `gog -a alex.mercer@example.com gmail get <provider-message-id> --json`. Require the Sent label, expected From and To, exact subject and body, and no unintended attachment. Normalize CRLF to LF only for equality comparison. Use Gmail internalDate for the request time. Check bounces separately; Sent is not proof of delivery, withdrawal processing or deletion.
6. **Reconcile independent state without erasing history.** Add an idempotent administrative event to the canonical outreach database, read back its exact body/status and refresh the complete CSV. Mark the campaign target `withdrawal_requested_do_not_count`; preserve the actual original submission date and evidence. Add an explicit `Count status: DO NOT COUNT` marker to the original submitted log section as well as the separate withdrawal entry, because section-based counters can otherwise keep counting the historical success. Rerun the canonical counter and verify the withdrawn heading is excluded without erasing its original proof. In Teal, update the exact record with readable withdrawal/deletion notes and an appropriate archived/withdrawn state when available. A tracker change is not employer-side proof. If tracker access is unavailable, save the exact record ID and pending repair, complete the available email/log/database work, and never resend the request to repair bookkeeping.
7. **Track three separate milestones.** Record `request_sent`, `withdrawal_confirmed` and `data_deletion_confirmed` independently. A reply confirming only withdrawal must not set deletion complete. Record any explicitly stated lawful retention exception without asserting that all data was erased. Schedule a confirmation check with a named owner and due date; the check should inspect matching replies and bounces, not automatically send another message unless authorized.
8. **Report the actual outcome concisely.** State the original submission channel first when asked, then the recipient and verified action, and finish with confirmation still pending when appropriate. Do not say the application was withdrawn or the data deleted solely because the request was sent.

## Templates

### Russian, named person

```text
Здравствуйте, Дарина!

Я увидел вакансию Project Manager в Росско на hh.ru. Роль показалась мне интересной, потому что она связана с продуктовой координацией, ИТ-процессами, B2B и запуском рабочих решений.

С кем я могу обсудить эту позицию в компании?

С уважением,
Алекс Мерсер
+1 555 234 5678
https://www.linkedin.com/in/alexander-mercer/
```

### Russian, company channel

```text
Здравствуйте!

Я увидел вакансию Project Manager в вашей компании на hh.ru. Роль показалась мне интересной, потому что она связана с продуктовой координацией, ИТ-процессами, B2B и запуском рабочих решений.

С кем я могу обсудить эту позицию в компании?

С уважением,
Алекс Мерсер
+1 555 234 5678
https://www.linkedin.com/in/alexander-mercer/
```

### Russian, LinkedIn connection note

```text
Здравствуйте, Дарина! Я увидел вакансию Project Manager в Росско на hh.ru. Роль показалась мне близкой по опыту в product management, ИТ-процессах и запуске рабочих решений. С кем я могу обсудить эту позицию?
```

### English, named person

```text
Hi Sarah,

I saw the Project Manager role at Rossko on hh.ru. The position stood out to me because it connects product coordination, IT processes, B2B workflows and launching practical solutions.

Who would be the best person to speak with about this role?

Best,
Alex Mercer
+1 555 234 5678
https://www.linkedin.com/in/alexander-mercer/
```

### English, LinkedIn connection note

```text
Hi Sarah, I saw the Project Manager role at Rossko on hh.ru. The position stood out because it connects product coordination, IT processes and practical launch execution. Who would be the best person to speak with about this role?
```

## WhatsApp CLI recipe

Use this when WhatsApp Web is visually available but CDP cannot reliably read or click the page, or when the outreach run needs repeatable WhatsApp sending.

1. Create or reuse `~/Hermes/job-applications/outreach-database/whatsapp-cli/`.
2. Install dependencies from `templates/whatsapp-cli-package.json` or copy that template to `package.json` and run:

```bash
npm install
```

3. Use `scripts/whatsapp_cli_send.js` as the sender script. Keep auth data under the run folder, not a system temp directory, so QR pairing survives later sends. Do not add a second Puppeteer `--user-data-dir` when using `whatsapp-web.js` `LocalAuth`; two profile directories can prevent the QR pairing from being stored where the client expects it.
4. First run may emit `qr_required` and write a QR PNG. Send that PNG to Vasya and wait for phone pairing. If the user says the QR was scanned but the result remains `qr_required` and the LocalAuth session folder is empty, stop the process, remove the duplicate user-data-dir or stale auth/profile state, restart once, and show the new QR. Do not keep reusing an expired QR.
5. Send with an explicit message file and result path:

```bash
node send.js \
  --phone 77753535353 \
  --message-file rossko-message.txt \
  --company Rossko \
  --role "Project Manager" \
  --source-url https://ns.rossko.ru/ \
  --out ~/Hermes/job-applications/outreach-database/whatsapp-cli/rossko-send-result.json
```

6. Count a WhatsApp CLI send when the result JSON says `status: "sent"` and the process exits successfully. `message_id` may be null even after `whatsapp-web.js` reports `SENT <phone>@c.us`; do not downgrade a successful send solely because the serialized message id is absent. If the result says `qr_required`, `timeout_waiting_for_qr_scan_or_ready`, `not_registered`, `send_error`, or any unverified status, log it as blocked or attempted, not sent.
7. Immediately import the result JSON into `outreach.sqlite3` and refresh `outreach_events.csv`. Use `channel = whatsapp_cli` for CLI sends.

## Query examples

```bash
sqlite3 ~/Hermes/job-applications/outreach-database/outreach.sqlite3 \
  "SELECT sent_at, company, contact_name, channel, COALESCE(contact_value, contact_url), status FROM v_recent_outreach LIMIT 30;"
```

```bash
sqlite3 ~/Hermes/job-applications/outreach-database/outreach.sqlite3 \
  "SELECT company, channel, status_class, COUNT(*) FROM outreach_events GROUP BY company, channel, status_class ORDER BY company;"
```
