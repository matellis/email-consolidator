# Gmail over IMAP

Gmail is the one source that is alive. You are reading from it, and
you must never write to it while doing this.

## Turn it on

1. Gmail settings, "See all settings", "Forwarding and POP/IMAP",
   enable IMAP. (On newer accounts IMAP is always on and this section
   is gone.)
2. Google Account, Security, turn on 2-Step Verification if it is not.
3. Google Account, Security, "App passwords". Create one named
   "archive". Google shows a 16-character password once. Put it in a
   file:

```
mkdir -p ~/.secrets && umask 077
printf '%s' 'abcd efgh ijkl mnop' | tr -d ' ' > ~/.secrets/gmail-app.pw
```

   Point `gmail.password_file` at it. Delete the app password from
   Google when you are finished.

Google Workspace accounts may have app passwords disabled by an
administrator. Then you need OAuth2 (XOAUTH2), which needs a client
id and a token refresh flow. `mbsync` and `imapsync` both support it;
this toolkit's stdlib puller does not. Use one of them (below) and
normalize the result.

Server: `imap.gmail.com`, port 993, TLS. Login is the full address.

## How Gmail looks over IMAP

Gmail has no folders. It has one store of messages and labels on them.
IMAP sees each label as a folder, and a message with three labels
appears in three folders. Then there is `[Gmail]/All Mail`, which is
the store itself: every message, once (except Spam and Trash, which
are their own folders).

So: pull All Mail, and record the labels. That gives you everything,
once, with the information to rebuild the label view if you want it.

The folder name is localized. German accounts have
`[Gmail]/Alle Nachrichten`. The puller finds it by the `\All` flag in
LIST, not by name.

Gmail adds three IMAP attributes per message:

- `X-GM-MSGID`: 64-bit id, stable for the life of the message. The
  puller's resume key.
- `X-GM-THRID`: thread id.
- `X-GM-LABELS`: the labels, as a list. System labels look like
  `\Inbox`, `\Sent`, `\Important`, `\Starred`.

## Pull with this toolkit

```
python3 emailc.py gmail pull
```

Writes `archive/gmail/<user>/All Mail/` as a Maildir with the raw bytes
of each message, and `archive/gmail/<user>/labels.tsv` with
`gm_msgid`, labels and filename. `work/gmail-<user>.done` holds every
fetched id; a re-run fetches only new ones.

Options: `--since 01-Jan-2020` limits by internal date (IMAP date
format, day-Mon-year). `--limit 100` for a trial.

Expect a first pull of 100,000 messages to take several hours. Gmail
throttles bulk IMAP. The puller backs off on throttle responses and
reconnects on drops. Kill it and restart it whenever you like.

Then treat the result like any other source:

```
python3 emailc.py normalize maildir "archive/gmail/you@gmail.com/All Mail" gmail/you@gmail.com
```

## Keeping it in sync

Run the pull from cron. Monthly is enough for an archive:

```
0 3 1 * * cd /path/to/email-consolidator && python3 emailc.py gmail pull >> work/gmail-cron.log 2>&1
```

then normalize and import the new messages the same way. The importer
skips what it has already sent, so re-running `import run` over the
gmail folder is safe.

## Alternatives

**mbsync (isync)**: mature, fast, does two-way sync but can be pinned
to one-way. Stores into a Maildir. `examples/mbsyncrc` is a one-way
config for All Mail. Supports XOAUTH2 via a SASL plugin. Does not
record `X-GM-LABELS`.

**imapsync**: copies IMAP to IMAP directly, Gmail into your archive
server, no disk in between. Good for a continuous mirror. Skip the
normalize and dedupe stages for what it copies, but run reconcile
against its own report.

**Google Takeout**: one-time export as mbox, with `X-Gmail-Labels:`
headers on every message. The best baseline for a very large account
because it does not hit IMAP throttling. Request it, download, put the
mbox files under `archive/takeout/<date>/`, normalize as `mbox`. Then
use the puller with `--since` for everything after the export date.

## Never do this

- Do not select All Mail read-write. The puller selects read-only.
- Do not run any tool with "expunge", "delete" or "move" against Gmail
  during this project.
- Do not use your normal Google password anywhere. App password or
  OAuth only.
- Do not commit the password file. `.gitignore` here excludes `*.pw`.
