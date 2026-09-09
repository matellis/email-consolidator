# Lessons

Failure modes seen in real consolidations of this kind, and what this
toolkit does about each one. Read this before stage 5.

## 1. Deduping on the server instead of on disk

A common first design: import everything, then run a dedupe that
fetches every message from the server, hashes it, and deletes losers
with `UID STORE \Deleted` plus `UID EXPUNGE`. It can work. It also
takes days on a large corpus, any interruption leaves the server in a
half-deduped state, and every later repair has to reason about what
was already removed.

Deduping the normalized tree on disk first is a short job with a plain
file walk. It produces a TSV you can read before acting, and it moves
files rather than deleting them. Stage 4 does that. There is no
server-side delete in this toolkit.

## 2. UTF8=ACCEPT wraps every appended message

Python's `imaplib`, after `enable("UTF8=ACCEPT")`, sends an APPEND as
`UTF8 (` + message + `)`. That is correct per RFC 6855. Some servers
store the wrapper as part of the message. Every message imported that
way then begins with the bytes `UTF8 (` and ends with `)`. Mail clients
show them fine, because they parse leniently. Hash verification does
not, and a dedupe then has to learn to unwrap before comparing.

The usual reason for enabling it is non-ASCII folder names. The right
answer is modified UTF-7 folder names, which every server accepts. The
client here does that and never enables UTF8=ACCEPT. `emailc verify`
reports a `wrapped` count so the problem shows on the first sample.

## 3. A repair that runs again is a repair that duplicates

A repair that fetches every message in a mailbox in one pass will hit
a server timeout on the largest mailboxes. If the resume marker is
written only after a later verify step, each aborted run has already
re-imported clean copies and none of them are recorded. Each restart
imports them all again. A mailbox can grow by an order of magnitude
in a few restarts.

Rules that follow, all built into the importer here:

- Write the resume marker immediately after each successful append,
  never after a later step.
- Fetch in small chunks (50 UIDs) and reconnect on error.
- Any repair must be idempotent by construction: running it twice must
  do nothing the second time, and that must be true even if the first
  run died halfway.

## 4. Listing APIs that truncate

A JMAP `Mailbox/get` without ids may silently truncate at a few
hundred mailboxes. A mailbox path computed from the truncated list can
collide with a different mailbox, and an import then routes messages
into the wrong folder. Paginate every listing. Verify a folder's
identity by name and parent, not by position in a list. The IMAP
client here creates folders step by step and selects each one to
confirm it exists.

## 5. The fast importer is the fragile one

JMAP blob upload plus batched `Email/import` is several times faster
than IMAP APPEND. It also needs a fallback to IMAP for messages over
the upload limit, a second fallback for messages JMAP rejects but IMAP
accepts (readpst calendar items), a 429 backoff, a 400 backoff for
config reloads, and per-message isolation when a batch fails. The
plain IMAP path needs none of that. Speed is not the constraint;
correctness is. This toolkit ships the slow path.

## 6. Counts taken at the wrong moment

A STATUS sweep right after a server restart can overstate, because the
server is still catching up its index. A baseline taken then makes a
later reconciliation look wrong. Take counts when the server is idle,
and take them twice.

## 7. Two roots for one Outlook file

`readpst` can write `x.ost/` and `x.ost1/` for one `.ost` file. If the
import mapping merges them into one folder tree and the audit script
does not know that, the audit counts those folders twice. Any mapping
applied at import must be the same mapping used by every audit. Here
that is one function, `importer.jobs`, used by import, reconcile and
verify.

## 8. Rejects are real content

A small fraction of readpst output is not messages: calendar entries,
contact cards, images that had been attachments. The server rejects
them. One option is to wrap each in a minimal RFC 822 envelope
(`Subject: Recovered artifact: <name>`, body verbatim) and import them
under a separate folder so the search index still finds them. Whether
you want that is your call. The FAIL lines list them.

## 9. A count that does not name its path

A count file that says N messages live under a directory, when the
directory does not exist, costs hours of forensic work before it turns
out the counting script counted the originals in place for sources
imported without normalization. Nothing was lost; the count did not say
what it counted. Every count must name exactly the path it counted.
`work/counts.tsv` here is produced by one walk of one tree.

## 10. Things that work

- Extracting emlx by reading the length prefix. Sample checks of
  hundreds of files come back with zero mismatches.
- `readpst -r` on multi-gigabyte ost files. Slow, complete.
- Keeping originals untouched in a separate tree. Every repair above
  is possible only because the truth is still on disk.
- Writing every count into a dated notes file. Every time a number is
  questioned, the answer is in the notes.
