# The walkthrough

Read this once from top to bottom before you run a single command.
Then come back and do it one stage at a time. Each stage ends with a
checkpoint. Do not move to the next stage until the checkpoint holds.

Budget: a few evenings for a few hundred thousand messages. The slow
parts are copying data off old drives and the server import. Everything
else is minutes.

## Before stage 1: decide three places

You need three directories, ideally on the same big disk or NAS:

- **archive**: where the original files will be gathered. After stage 2
  nothing here changes, ever. Treat it as read-only.
- **normalized**: Maildir conversions of everything in archive. This is
  a derivative. You can delete it and regenerate it.
- **work**: logs, resume state, the dedupe quarantine and reports.

Put these in `config.toml` (copy `config.example.toml`). Then:

```
python3 emailc.py check
```

It prints each path and whether it exists, and tries the server if one
is configured. The server can wait until stage 5.

Make a text file called `NOTES.md` in your work directory. Every
checkpoint below asks you to write a number in it. Date every entry.

## Stage 1: inventory

Find every email artifact on every old disk before touching anything.

```
python3 emailc.py inventory
```

`paths.sources` in the config lists the roots to scan. Mount old drives
read-only if you can. On a Mac, `diskutil mount readOnly <disk>`.

Output: `work/inventory.tsv` with one row per file (one row per
Maildir), and a summary by kind on the terminal.

What you will see:

- **emlx**: Apple Mail. Thousands of small files under `*.mbox/Messages/`.
- **mbox**: single files, often from Google Takeout or old Unix mail.
  Apple Mail's `Foo.mbox` is a directory, not an mbox. The inventory
  tells them apart.
- **maildir**: directories with `cur/`, `new/`, `tmp/`. Server backups.
- **pst / ost**: Outlook. One file can hold years of mail.
- **msg**: single Outlook messages. Only real OLE files are counted.
- **eml**: single RFC 822 messages.
- **other-mail**: Thunderbird indexes, Outlook for Mac `.olm` and the
  like. Listed so you know they exist. See docs/formats.md for what to
  do with each.

**Checkpoint 1.** In NOTES.md write the summary table. Write down the
sources you scanned and any that you could not mount. If a drive is
failing, image it first (`dd` or `ddrescue`) and scan the image.

## Stage 2: gather

Copy every inventoried source into `archive/`, organized by where it
came from. This is the one step this toolkit does not do for you,
because rsync does it better than any script.

Pick a layout that names the provenance, for example:

```
archive/
  applemail/2019-imac/         <- a whole ~/Library/Mail from one machine
  applemail/2024-laptop/
  maildir/2011-server/
  outlook/work.ost
  takeout/2026-01/             <- Google Takeout mbox files
  gmail/you@gmail.com/         <- written by `emailc gmail pull`
```

Copy with rsync, keeping times and never deleting:

```
rsync -a --info=progress2 "/Volumes/Old Drive/Users/me/Library/Mail/" archive/applemail/2019-imac/
```

Then prove the copy:

```
rsync -a --checksum --dry-run -i "/Volumes/Old Drive/Users/me/Library/Mail/" archive/applemail/2019-imac/ | head
```

An empty result means every file matched by checksum. Anything printed
is a file that differs. Investigate, do not shrug.

Two things you will meet on Mac-origin drives:

- `._name` files. These are AppleDouble sidecars carrying Finder
  metadata. They are not email. Every reader in this toolkit skips
  them. Copy them or not as you like.
- `.AppleDouble/` directories from old AFP shares. Same story.

**Checkpoint 2.** For each source, write the file count and byte total
of source and destination side by side. `find DIR -type f | wc -l` and
`du -sh DIR`. They must match.

Do not delete the sources yet. Not until stage 6 passes.

## Stage 3: normalize

Convert everything into Maildir. One command per source:

```
python3 emailc.py normalize emlx    archive/applemail/2019-imac   applemail/2019-imac
python3 emailc.py normalize emlx    archive/applemail/2024-laptop applemail/2024-laptop
python3 emailc.py normalize maildir archive/maildir/2011-server   maildir/2011-server
python3 emailc.py normalize mbox    archive/takeout/2026-01       takeout/2026-01
python3 emailc.py normalize maildir archive/gmail/you@gmail.com   gmail/you@gmail.com
```

The last argument is the path under `normalized/`. Keep the provenance
in the name. You will use these prefixes in the dedupe policy.

Outlook files need an external converter first, because pst/ost is a
binary database. Install `libpst` (`readpst`) and run:

```
mkdir -p work/pst-stage/work.ost
readpst -r -o work/pst-stage/work.ost archive/outlook/work.ost
python3 emailc.py normalize eml work/pst-stage/work.ost outlook/work.ost
```

`readpst -r` writes one file per message in a folder tree. Details and
the equivalent for `.msg` files are in docs/formats.md, including how
to run the converters in a throwaway Docker container when you do not
want to install them.

Every normalize run prints `DONE ok=N skip=M` and writes
`work/normalize.log`. Open the log and read every SKIP line. Typical
skips: zero-byte files, truncated emlx files from a crashed machine,
files that are not mail at all. Decide for each one whether you care.

Then count:

```
python3 emailc.py counts
```

and spot-check the emlx conversion on a random sample:

```
python3 emailc.py sample 500 archive/applemail
```

**Checkpoint 3.** Write in NOTES.md, per source: files in archive,
`ok` and `skip` from the log, messages in `work/counts.tsv`. For emlx
sources `ok` must equal the number of `.emlx` files minus skips. For
mbox sources compare against `grep -c '^From ' file.mbox`. The sample
check must report `failed=0`.

## Stage 4: dedupe

Your sources overlap. Two laptop backups a year apart hold mostly the
same mail. Find the duplicates now, on disk, before anything reaches a
server. Deduping on the server afterwards is possible,
and it is where most of the trouble comes from. Do it here.

```
python3 emailc.py dedupe plan
```

Two messages are duplicates when both their Message-ID and a hash of
their bytes match. Same Message-ID with different bytes is left alone
(drafts, resent mail, messages a client rewrote). Messages with no
Message-ID are matched on bytes only.

One copy per group is kept. Which one is set by `dedupe.prefer` in the
config: a list of normalized-tree prefixes, best first. Put your
newest and most complete source first.

The plan prints totals and ten sample groups. Look at the samples. The
KEEP line should be from the source you expect. If it is not, fix
`prefer` and plan again. Open `work/dupes.tsv` and skim it.

When you are satisfied:

```
python3 emailc.py dedupe apply
```

Losers are moved to `work/quarantine/` under their original relative
path. Nothing is deleted. Every move is logged with its hashes in
`work/dedupe.log`. If a file changed between plan and apply it is
skipped as MISMATCH and you plan again.

Run `python3 emailc.py counts` again.

**Checkpoint 4.** messages before, copies quarantined, messages after.
before minus quarantined must equal after. Write all three down.

## Stage 5: import

You need an IMAP server. docs/server.md covers choosing one and setting
it up. Short version: Dovecot or Stalwart on a machine you control,
reachable only on your LAN or through a tunnel, with a dedicated
archive account. Fill in `[server]` in the config and run
`python3 emailc.py check` until it says connected.

See the plan first:

```
python3 emailc.py import plan
```

One line per folder with its message count. Folders are named
`<prefix>/<path under normalized>`, so `Archive/applemail/2019-imac/INBOX.mbox`.

Try one small folder:

```
python3 emailc.py import run --only Archive/applemail/2019-imac/Sent.mbox --workers 1
```

Then open a mail client, connect to the archive account and look at
that folder. Dates right? Bodies readable? Attachments open? If yes:

```
python3 emailc.py import run --workers 4
```

This runs for hours on a large corpus. It is resumable: kill it, start
it again, it skips what is done. Progress is in `work/import.N.log`.
FAIL lines are messages the server rejected, usually because the file
is not a valid message (an image readpst exported as a "message", a
calendar item, a corrupt file). They are never retried on their own.
Collect them at the end and decide.

Two workers per CPU core on the server is plenty. More does not help
and can make the server drop connections.

**Checkpoint 5.** Sum of `sent=` across all `FOLDER-DONE` lines, sum
of `failed=`. sent plus failed must equal the stage 4 after count.

```
grep -h FOLDER-DONE work/import.*.log | awk -F'\t' '{split($3,a,"=");split($5,b,"=");s+=a[2];f+=b[2]} END{print "sent",s,"failed",f}'
```

## Stage 6: verify

Two checks. Counts and bytes.

```
python3 emailc.py reconcile
```

For every folder: expected (files in normalized) against live (IMAP
STATUS). OK, DELTA or MISSING. Every DELTA must be explained. The usual
explanations are the FAIL lines from stage 5, and a server that is still
building its index after a restart (wait ten minutes and run again).

```
python3 emailc.py verify 50
```

Picks 50 random messages from disk, finds each on the server by
Message-ID and compares a hash of the bytes. Every one should be `ok`.
`wrapped` must be zero. If it is not, read docs/lessons.md before doing
anything else.

**Checkpoint 6.** reconcile totals, verify result. When both are clean
the archive is done.

Only now may you consider retiring the source drives. Keep `archive/`
forever. Snapshot it. Back it up off site.

## After: Gmail, and keeping it going

Pull your Gmail into the same archive:

```
python3 emailc.py gmail pull
```

then normalize, dedupe and import it like any other source. Run the
pull again whenever you like; it fetches only new messages. Put it in
cron monthly. docs/gmail-imap.md explains app passwords, what All Mail
and labels are, and the alternatives (mbsync, Takeout).

## When something goes wrong

- Stop. Do not run the next stage.
- Read the log for the stage you are on. Every skip and failure has a
  path and a reason.
- Write in NOTES.md what you saw, with the date and time, before you
  change anything.
- docs/verification.md has the list of ways counts disagree and what
  each one means.
