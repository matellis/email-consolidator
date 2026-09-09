# Email formats you will meet

Every format below is either RFC 822 text with some wrapper, or a
binary container that a tool can unpack into RFC 822 text. The goal of
stage 3 is the same for all of them: one Maildir, one file per message,
bytes untouched.

## emlx (Apple Mail)

Where: `~/Library/Mail/V*/<account>/<Mailbox>.mbox/<uuid>/Data/.../Messages/NNN.emlx`
on newer macOS, `~/Library/Mail/Mailboxes/<Mailbox>.mbox/Messages/NNN.emlx`
on old ones. Also `NNN.partial.emlx` for messages whose attachments
were not downloaded.

Layout of one file:

```
1234\n                 <- decimal byte count of the message
<exactly 1234 bytes>   <- the RFC 822 message
<?xml ...plist...>     <- Apple metadata: flags, colour, date received
```

The toolkit reads line 1, takes exactly that many bytes, and discards
the plist. That is the whole conversion. The plist holds flags (read,
flagged, junk) and the received date. The importer marks everything read and
take the date from the `Date:` header. If you want the plist flags,
they are in the archive copy forever.

Gotchas:

- `.emlx` files from a machine that crashed can be truncated. The
  reader raises and the file is logged as SKIP. Check the count of
  skips against what you expect from that machine's history.
- Mailbox directories are named `Foo.mbox`. They are not mbox files.
- Apple's `Attachments/` directories beside `Messages/` hold detached
  attachments for `.partial.emlx`. They are not messages. Nothing in
  this toolkit reads them; the archive copy keeps them.

## mbox

One file, many messages, each preceded by a line beginning `From `
(with a space, no colon). Google Takeout, Thunderbird, Unix mail
spools, Eudora all produce a variant.

The reader splits on `From ` at line start and drops the separator
line. Message bodies that contain a line beginning `From ` are
supposed to have been escaped to `>From ` by the writer. Some writers
do not. If a count from `grep -c '^From '` looks too high relative to
what the client showed, that is why. The normalized messages are still
each a valid file; a wrongly split one just becomes two, and the
second has no headers and will be rejected at import. Rare.

Count: `grep -c '^From ' file.mbox`.

Google Takeout mbox files add `X-Gmail-Labels:` and `X-GM-THRID:`
headers. Keep them. They are your only record of labels for old mail.

## Maildir

A directory with `cur/`, `new/`, `tmp/`. One file per message. The
filename encodes uniqueness and, after the colon or comma, flags.
Subfolders vary by server:

- Courier and Dovecot "Maildir++": subfolders are dot-prefixed
  siblings, `.Sent`, `.Sent.2009`, inside the top maildir.
- Dovecot "fs" layout and most conversions: nested directories.

The toolkit walks both. Courier names are split on dots into a path.

Count: files in `cur/` plus `new/`, ignoring `._*`.

## pst and ost (Outlook)

A single binary database holding folders, messages, contacts,
calendar. `.pst` is a personal archive, `.ost` is the offline cache of
an Exchange or Microsoft 365 mailbox. Both are readable by `libpst`:

```
readpst -r -o OUTDIR file.pst
```

`-r` writes a directory per folder with one numbered file per message,
RFC 822 with attachments MIME-encoded. Then
`emailc normalize eml OUTDIR outlook/<name>`.

Install: `apt install pst-utils`, `brew install libpst`, or run it in a
container without installing anything:

```
docker run --rm -v /path/to/archive:/in:ro -v /path/to/stage:/out debian:bookworm-slim \
  sh -c 'apt-get update -qq && apt-get install -y -qq pst-utils >/dev/null && readpst -r -o /out /in/outlook/work.ost'
```

Gotchas:

- Calendar items, contacts and some embedded objects come out as
  files that are not mail. The IMAP server rejects them at import as
  `invalidEmail` or similar. Expect a FAIL count in the hundreds for a
  busy Exchange mailbox. They are still in the readpst output.
- Some images come out as bare files without headers. Same story.
- Very large ost files (tens of GB) take hours. Run on the NAS.
- A corrupt or password-protected pst: `readpst` says so. `pst2ldif`
  and Outlook itself are the only other readers. If you still have a
  Windows machine with Outlook, open the pst there and export to a
  new pst first; Outlook repairs on export.
- `readpst` may produce two roots for one file (`x.ost` and `x.ost1`)
  when the container has a second top-level store. Merge them by hand
  or normalize them under two names.

## msg (Outlook single message)

An OLE compound file (magic bytes `d0 cf 11 e0`). Convert with
`msgconvert` from the Perl `Email::Outlook::Message` package:

```
apt install libemail-outlook-message-perl
msgconvert file.msg      # writes file.eml beside it
```

Then `emailc normalize eml`. Text files that happen to end in `.msg`
(localization catalogs, game files) are not mail; the inventory checks
the magic and skips them.

## eml

One RFC 822 message per file. `emailc normalize eml` copies each into
a maildir. Also the output format of readpst and msgconvert.

## olm (Outlook for Mac)

A zip file with an XML message per file. Not supported by this
toolkit. Open it in Outlook for Mac and export, or unzip it and look:
the XML contains the raw message in some versions.

## Thunderbird

Profiles hold mbox files without an extension, next to `.msf` index
files. The mbox files are the mail; treat each as `mbox`. The `.msf`
files can be ignored.

## What "bytes untouched" means

Every reader hands the server exactly the bytes between the format's
delimiters. No line-ending changes, no header additions. Servers may
store with CRLF; the verify step compares with CRLF folded to LF for
that reason. If you ever want to prove a message on the server is the
same as one on disk, that is the comparison to use.
