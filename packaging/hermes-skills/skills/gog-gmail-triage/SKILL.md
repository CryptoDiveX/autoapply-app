---
name: gog-gmail-triage
description: Triage Gmail for urgent/time-sensitive items using the gog CLI, with a conservative noise-filtering workflow for cron-style monitoring.
version: 1.0.0
author: Hermes
license: MIT
metadata:
  hermes:
    tags: [Google, Gmail, Email, Triage, Monitoring, gog]
---

# gog Gmail triage

Use this skill when Gmail should be checked directly through the `gog` CLI instead of IMAP clients like Himalaya, especially for urgent-message monitoring jobs.

## Why this skill exists

In this environment, `gog` was available and authenticated for Gmail access. It worked better than IMAP-oriented flows for urgent triage because it could:

- search Gmail directly with Gmail query syntax
- return message-level JSON (`gmail messages search`)
- fetch metadata/snippets quickly (`gmail get --format=metadata`)
- generate direct Gmail web links (`gmail url`)

This is useful for cron jobs that should only notify on genuinely urgent items.

## Core workflow

### 1. Verify availability

```bash
gog --help
gog gmail --help
```

Use the account explicitly when needed. In Hermes profile sessions, retry with the real user home if profile-home credentials are missing:

```bash
gog -a user@example.com ...
HOME=~ gog -a alex.mercer@example.com -j --results-only gmail labels list
```

If `gog` reports missing OAuth client credentials under a path like `~/.hermes/profiles/main/home/...`, that may be a profile HOME issue rather than broken real-user auth; set `HOME=~` and retry before falling back.

### 2. Prefer message-level search, not thread-level search

For triage, use:

```bash
gog -a user@example.com -j --results-only gmail messages search --max 20 'QUERY'
```

Avoid relying only on:

```bash
gog gmail search ...
```

because that returns thread-level results and can hide which individual message is new or urgent.

### 3. Start broad, then narrow

Useful first-pass searches:

```bash
gog -a user@example.com -j --results-only gmail messages search --max 20 'newer_than:3d (label:inbox OR label:important)'

gog -a user@example.com -j --results-only gmail messages search --max 20 'newer_than:7d is:unread (label:inbox OR label:important)'
```

If the mailbox uses filters and urgent mail may skip Inbox, also search beyond Inbox with category exclusions:

```bash
gog -a user@example.com -j --results-only gmail messages search --max 30 'newer_than:7d -category:promotions -category:social ("action required" OR urgent OR deadline OR today OR tomorrow OR overdue OR invoice OR receipt OR payment OR failed OR declined OR locked OR verify OR verification OR security OR insurance)'
```

## Important experiential findings

### If Gmail API auth fails, fall back immediately to Himalaya
A live operational finding: when `gog` returns OAuth errors such as:

```text
invalid_grant
Token has been expired or revoked.
```

stop trying to force Gmail API access for that run and switch to `himalaya` immediately for mailbox cleanup. This is especially important for unattended cron jobs where re-auth is not possible.

Practical pattern:

1. try a lightweight Gmail API command first, for example:

```bash
gog -a user@example.com -j --results-only gmail labels list
```

2. if that fails with `invalid_grant` / revoked token errors, use Himalaya for the entire cleanup pass
3. keep the cleanup conservative because IMAP folder semantics may be less label-precise than the Gmail API

### `gmail batch modify` works well for conservative cleanup
For direct Gmail cleanup through `gog`, the most reliable operation was batch label modification on message IDs surfaced by search.

Useful pattern:

```bash
# Move older receipt-like mail out of Inbox into the Receipts label
gog -a user@example.com -y gmail batch modify MSG1 MSG2 MSG3 --add Receipts --remove INBOX

# Archive safe FYI/promotional mail by removing Inbox only
gog -a user@example.com -y gmail batch modify MSG4 MSG5 MSG6 --remove INBOX
```

Dry-run first when the rules are nuanced:

```bash
gog -a user@example.com -n -y gmail batch modify MSG1 MSG2 --add Receipts --remove INBOX
gog -a user@example.com -n -y gmail batch modify MSG3 MSG4 --remove INBOX
```

This is a strong replacement for IMAP-style move/archive flows when Gmail API access via `gog` is available.

### Label discovery is easy through `gmail labels list`
Before doing cleanup, list labels once so you can confirm the exact user label names (for example `Receipts`, `Action Required`, custom folders mirrored as labels):

```bash
gog -a user@example.com -j --results-only gmail labels list
```

This avoids guessing whether a destination label exists before using `--add Receipts` or checking protected labels.

### `gmail search -p` is a strong cleanup review surface
For cleanup jobs, the top-level thread/message listing command was fast and operator-friendly:

```bash
gog -a user@example.com gmail search 'in:inbox newer_than:3d' -p --max=30
```

In plain mode it returns a compact TSV-like table with:

- ID
- DATE
- FROM
- SUBJECT
- LABELS
- THREAD

That makes it easy to review candidate mail classes before changing labels. In practice, this was enough to identify safe cleanup targets such as older promo/FYI items and receipt-like messages, then feed the returned IDs directly into `gmail batch modify`.

Use JSON when you need scripting fields, but prefer `-p` for quick human review during mailbox cleanup.

### Important pitfall: `gmail search -p` can behave thread-like enough to mislead cleanup decisions
A useful live finding: even with a query like `in:inbox older_than:1d`, `gog gmail search -p` may still show rows that represent threads containing sent mail or mixed-label history, and the displayed row can look like a `SENT` item or otherwise not reflect the exact message-level label state you intend to clean up.

Practical implication:

- use `gmail search -p` for broad review only
- before modifying labels, confirm candidates with `gmail get --format=metadata` or use `gmail messages search` for message-precise enumeration
- avoid assuming every row from `gmail search -p` is a standalone Inbox message safe to batch-modify

Reliable pattern:

```bash
# broad review

gog -a user@example.com gmail search 'in:inbox older_than:1d' -p --max=30

# precise confirmation

gog -a user@example.com -j --results-only gmail get MESSAGE_ID --format=metadata --headers=From,To,Subject,Date
```

This matters most for conservative cleanup jobs where accidentally acting on a thread because one row looked archive-safe would be too aggressive.

### Verification after cleanup should use targeted re-search + metadata checks
After modifying labels, verify in two ways:

1. re-run a search for the same candidate class still in Inbox
2. inspect a small sample with `gmail get --format=metadata` and confirm `labelIds` no longer include `INBOX` (and include `Receipts` when applicable)

Example:

```bash
# candidate class should now be empty or much smaller
gog -a user@example.com -j --results-only gmail messages search --max 20 'in:inbox older_than:1d subject:receipt'

# spot-check one modified message
gog -a user@example.com -j --results-only gmail get MESSAGE_ID --format=metadata --headers=From,Subject,Date
```

### Preserve context-rich medical invoices even if they look receipt-like
A useful cleanup exception: if a medical invoice may need reimbursement follow-up, an Asana task, or attachment/reference handling, do **not** auto-move/archive it just because it matches `invoice` or `receipt`.

In practice, claim confirmations and generic payment receipts were often safe to move to `Receipts`, but a provider invoice still sitting in Inbox could be intentionally preserved so the user/task workflow keeps message context and links attached.

### Treat protected labels/surfaces as off-limits by default
For conservative cleanup automations, explicitly exclude or preserve these review surfaces unless the rule set says otherwise:

- `label:"Action Required"`
- `label:important -in:inbox`
- appointment / dental flows such as Jane / Healthy Smile / Dental Charo

These surfaces often contain intentionally staged mail, follow-up items, or review queues. Cleanup should target clearly safe noise classes outside them first.

### Receipt aging rule works cleanly with label modification
If receipts should remain visible for one day, use a date gate and move them to the existing receipts label instead of archiving directly:

```bash
gog -a user@example.com gmail search 'in:inbox older_than:1d (from:uber.com OR from:lyftmail.com OR subject:receipt OR from:invoice)' -p --max=50

gog -a user@example.com -y gmail batch modify MSG1 MSG2 MSG3 --add Receipts --remove INBOX
```

This preserves mailbox organization without losing the receipt history.

### Generic FYI/archive actions are safest as `--remove=INBOX`
When the goal is to archive a safe non-receipt FYI item, prefer removing only the Inbox label:

```bash
gog -a user@example.com -y gmail batch modify MSG1 MSG2 MSG3 --remove=INBOX
```

This keeps other Gmail labels intact and behaves like archive instead of delete or destructive move.

### `gmail messages search` is the best triage primitive
This gave the cleanest monitoring results because each row includes:

- `id`
- `threadId`
- `from`
- `subject`
- `date`
- `labels`

That makes it easy to shortlist candidates before reading them.

### `gmail get --format=metadata` is usually enough
To inspect a candidate without pulling the full raw body:

```bash
gog -a user@example.com -j --results-only gmail get MESSAGE_ID --format=metadata --headers=From,To,Subject,Date
```

The returned object also includes a `snippet`, which is often enough to determine urgency.

### `gmail get --format=full` can be misleading on multipart mail
A useful pitfall from real triage: for some multipart messages, especially HTML-heavy threads with inline assets or PDFs, this command may return a JSON list of attachment descriptors instead of a clean message object/body:

```bash
gog -a user@example.com -j --results-only gmail get MESSAGE_ID --format=full
```

So if metadata/snippet is not enough and you need the actual readable body, prefer a targeted message search with `--include-body` instead of relying on `get --format=full`:

```bash
gog -a user@example.com -j gmail messages search --max 1 --include-body 'subject:"Exact Subject" newer_than:1d'
```

This worked well for pulling the readable body text of recent Wealthsimple mortgage emails after `get --format=full` surfaced only inline attachment info.

### Attachment workflow for Gmail medical receipts
When a follow-up or receipt email includes a PDF and `gmail get --format=full` surfaces attachment descriptors, you can still complete a reimbursement/inspection workflow directly through `gog` without falling back to IMAP.

Reliable pattern:

1. inspect metadata first:

```bash
gog -a user@example.com -j --results-only gmail get MESSAGE_ID --format=metadata --headers=From,To,Subject,Date
```

2. fetch attachment descriptors (often via `--format=full` on these multipart receipt mails):

```bash
gog -a user@example.com -j --results-only gmail get MESSAGE_ID --format=full
```

3. download the specific attachment using the returned `attachmentId`:

```bash
gog -a user@example.com gmail attachment MESSAGE_ID ATTACHMENT_ID --out /tmp/receipts --name receipt.pdf
```

4. if text extractors like `pdftotext`/`pdfinfo` are missing on macOS, render a preview image and inspect it with vision:

```bash
qlmanage -t -s 1600 -o /tmp/receipt-preview /tmp/receipts/receipt.pdf
# then analyze /tmp/receipt-preview/receipt.pdf.png with vision
```

This worked well for a Forge Health physiotherapy receipt: the follow-up email body itself was not the important part, but the attached PDF carried the insurer-ready fields (provider, patient, practitioner license, invoice number, amount, paid status). It also allowed confirming that a clinic follow-up email was only a duplicate reference to an already-tracked receipt, not a new reimbursement item.

### `gmail url` can generate direct links from message IDs
After identifying urgent candidates, generate Gmail links for the report:

```bash
gog -a user@example.com -j --results-only gmail url MESSAGE_ID1 MESSAGE_ID2
```

This is good for final notifications because the user can jump directly into Gmail.

### Thread follow-up inspection: do not rely on `thread:<gmail_thread_id>`
A useful pitfall from live triage: the `threadId` returned by `gmail messages search` / `gmail get` is a Gmail API thread ID, not something you should assume works as a Gmail search operator value in later `gog gmail messages search` queries.

In practice, a query like:

```bash
gog -a user@example.com -j gmail messages search --max 5 --include-body 'thread:19dadd2052393f1e'
```

can return nothing even when the message metadata clearly shows that `threadId`.

Reliable fallback when you need to decide whether something is a **Follow-up** thread (user already replied, waiting on the other party):

1. inspect the inbound message metadata first:

```bash
gog -a user@example.com -j --results-only gmail get MESSAGE_ID --format=metadata --headers=From,To,Subject,Date
```

2. look for nearby sent mail and recent replies using exact/near-exact subject plus sender/recipient filters instead of `thread:<id>`
3. if needed, pull a recent body with `--include-body` using the subject/from constraints

Example pattern:

```bash
gog -a user@example.com -j gmail messages search --max 5 --include-body 'from:clinic@example.com subject:"Re: Rate Your Experience Today" newer_than:3d'
```

This worked to confirm that a clinic thread was genuinely a follow-up case because the mailbox contained a recent sent reply and the provider's response referenced it directly.

### Keyword searches produce many false positives
Terms like `security`, `action`, `invoice`, `today`, or `deadline` can surface noisy automated mail such as:

- Asana notifications/comments
- receipts
- promos
- routine reminders

So always shortlist with search, then inspect metadata/snippets before alerting.

### Check recipient when mailbox may contain forwarded/shared mail
Use metadata headers to confirm whether the message actually targets the monitored user:

```bash
gog -a user@example.com -j --results-only gmail get MESSAGE_ID --format=metadata --headers=From,To,Subject,Date
```

This helps avoid alerting on messages that were merely copied into the account or belong to another alias/person.

## Conservative urgent triage procedure

1. Search recent Inbox + Important mail.
2. Search a broader recent set with negative category filters for urgent/security/payment keywords.
3. Ignore obvious noise categories:
   - newsletters/promos
   - receipts unless action is needed
   - auto-generated task comments unless same-day action is clearly required
4. Read only shortlisted messages with `gmail get --format=metadata`.
5. Use `snippet` to determine whether the item is actually urgent.
6. Generate Gmail URLs for anything worth reporting.
7. If nothing is clearly urgent/new, return `[SILENT]` in cron-style jobs.

## Example urgent cases worth alerting

- verification link or code that expires soon and appears tied to intentional signup/login
- payment failure / declined charge / overdue invoice
- account locked or suspended
- human email requiring same-day action
- deadline today or tomorrow with explicit action needed

## Example non-urgent cases to suppress

- routine receipts
- generic FYI security notices with no action required
- newsletters/promotions
- automated work-comment traffic unless the content itself is urgent

## Cleanup exception: Google Cloud advisory/security notifications are not generic account-security FYI

A useful distinction from inbox-cleanup work: not every Google-branded security email should be treated as routine archive-safe noise.

If a message comes from Google Cloud / `advisory-notifications-noreply@google.com` and references a specific cloud resource, project, vulnerability, advisory, or "Notification Details" link in Google Cloud, preserve it for review instead of auto-archiving it under a generic Google security-FYI rule.

Example signals:

- subject like `New Advisory Notification`
- body text such as `You've received an important Google Cloud notification affecting your resource`
- vulnerability / CVE references
- links into `console.cloud.google.com/security/advisorynotifications/...`

These are operational/security notices about infrastructure, not routine account-login alerts, so they should be handled conservatively.

## Recommended command set

```bash
# Broad recent scan
gog -a user@example.com -j --results-only gmail messages search --max 20 'newer_than:3d (label:inbox OR label:important)'

# Unread scan
gog -a user@example.com -j --results-only gmail messages search --max 20 'newer_than:7d is:unread (label:inbox OR label:important)'

# Broader urgent-keyword scan outside pure Inbox
gog -a user@example.com -j --results-only gmail messages search --max 30 'newer_than:7d -category:promotions -category:social ("action required" OR urgent OR deadline OR today OR tomorrow OR overdue OR invoice OR receipt OR payment OR failed OR declined OR locked OR verify OR verification OR security OR insurance)'

# Inspect a candidate
gog -a user@example.com -j --results-only gmail get MESSAGE_ID --format=metadata --headers=From,To,Subject,Date

# Produce direct Gmail links
gog -a user@example.com -j --results-only gmail url MESSAGE_ID1 MESSAGE_ID2
```

## Pitfalls

- Thread-level `gmail search` may hide which exact message is relevant.
- Search keywords alone are noisy; always confirm with metadata/snippets.
- Important/Urgent labels are not enough by themselves; filtered mail may live outside Inbox.
- Some messages that look urgent are confirmations or receipts only; inspect before notifying.

## When to prefer Himalaya instead

Use Himalaya when the task is IMAP/SMTP mailbox management, composition, reply, moving messages, or when direct Gmail API access via `gog` is unavailable.
