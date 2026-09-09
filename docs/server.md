# The archive server

You need an IMAP server that will hold the archive and that you can
point any mail client at. The choice matters less than the rules
around it.

## Rules

- Private. It listens on your LAN or through a tunnel or VPN. No port
  forward on the router, no public listener, no exceptions. Mail
  servers on the open internet get attacked within minutes.
- Its own account. `archive@yourdomain` or similar. Not your live
  mailbox. The import writes hundreds of thousands of messages; keep
  that away from anything a phone syncs.
- Its data on a filesystem you snapshot. ZFS or btrfs snapshots before
  each import stage give you a way back.
- Not a relay. It does not need SMTP inbound. If the server includes
  SMTP, do not expose it.

## Choices

**Dovecot**: the standard. Fast, stable, Maildir or mdbox storage,
`doveadm` for counts and imports. Full-text search needs a plugin
(fts-flatcurve or Xapian). Runs anywhere, packaged everywhere. If you
run a NAS with Docker, a Dovecot container with a bind-mounted data
directory is an afternoon's work.

**Stalwart**: single binary, IMAP plus JMAP plus web admin plus
built-in full-text search. Newer, moving fast. Runs as a TrueNAS app.
Its IMAP is standard; the importer here uses nothing Stalwart-specific.

**Something you already run** (a hosted IMAP account, a Synology Mail
Server): fine if it is private and the quota fits. Check the message
count limits; some hosted plans cap folders at a few tens of
thousands of messages.

## Setting it up for the import

- Create the archive account. Make its password a long random string
  in a 0600 file, and point `server.password_file` at it.
- Decide the top folder. `Archive` is the default (`server.prefix`).
  Everything imports under it, so you can drop the whole tree and
  start over by deleting one folder.
- If the server offers a choice of storage, prefer a compressed
  multi-message store (Dovecot mdbox, Stalwart's default) over plain
  Maildir. Half a million messages as individual files is slow on
  most filesystems.
- Raise the maximum message size to at least 100 MB. Old mail has
  huge attachments, and the server rejecting a 60 MB message is a
  FAIL you then have to chase.
- Run `python3 emailc.py check`. It must say connected and show the
  hierarchy delimiter. `.` as a delimiter (some Dovecot configs) works;
  folder names are translated.

## How the import talks to it

Plain IMAP APPEND, one message at a time, with `\Seen` and an
INTERNALDATE from the message's `Date:` header. Two to four parallel
connections. No server-specific API. Resumable.

A JMAP importer for Stalwart, batching blob uploads and
`Email/import` calls, is faster, and it is where several of the
worst problems come from (see docs/lessons.md). Plain IMAP is slower
and loses nothing. This toolkit ships plain IMAP.

## Reaching it from outside

Your choice of VPN or tunnel. One working pattern: a Cloudflare tunnel
connector on the NAS, the private network route published in Zero
Trust, WARP client on every device. Mail clients then talk to the
server's LAN address as if at home. Tailscale or WireGuard do the same
job. The rule is the same in every case: the server itself has no
public address.

## Search

The reason for doing this at all. Test it early: import one folder,
open a client, search for a word you know is in one message. Dovecot
without an FTS plugin searches by reading every message and is unusable
at scale. Stalwart indexes on import.

## Backups of the server

The archive tree on disk is the record. The server is a view of it
that can be rebuilt by re-running stage 5. Snapshot the server data
anyway; a rebuild takes hours you would rather not spend.
