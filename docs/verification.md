# Counting and hashing

The whole method is: count at every boundary, and the counts must
chain. Files in source equals files in archive. Messages extracted
equals files minus skips. Messages after dedupe equals messages before
minus quarantined. Messages on the server equals messages after dedupe
minus rejects. Any break in the chain is a real problem or a real
explanation, and you find out which before going on.

## The numbers to keep

| Boundary | Left side | Right side |
| --- | --- | --- |
| gather | files and bytes in source (`find`, `du`) | same in archive |
| normalize | emlx files, mbox `From ` lines, maildir files | `ok` in normalize.log, `work/counts.tsv` |
| dedupe | messages before (`counts`) | quarantined + messages after |
| import | messages after dedupe | `sent` + `failed` in import logs |
| reconcile | `expected` (disk) | `live` (IMAP STATUS) |
| verify | sha1 of disk bytes, CRLF folded | sha1 of server bytes, CRLF folded |

Write each pair in NOTES.md with the date and time.

## When gather counts differ

- rsync excludes. Check for `--exclude` flags and `.rsync-filter` files.
- Symlinks. `find -type f` does not count them; rsync `-a` copies them
  as links. Count with `-type f -o -type l` on both sides.
- Unreadable directories on the source. `find DIR -type d ! -readable`.
  Fix permissions or `sudo`, then re-run rsync.
- Files changed during copy. Source was live. Stop the writer and
  re-run rsync with `--checksum`.

## When normalize counts differ

- SKIP lines. Every one has a reason. Truncated emlx, empty files,
  bad length prefix. Sum them; `ok + skip` must equal the input count.
- mbox `From ` lines inside bodies. `grep -c` over-counts; the
  converter's `ok` is the truth. Difference should be small and each
  extra message will be headerless (rejected later at import).
- Hidden `.AppleDouble/` directories on the source. The readers skip
  them; `find` counts them. Use `find ... -not -path '*/.AppleDouble/*'`.

## When dedupe counts differ

They cannot. `before - quarantined = after` is arithmetic on the same
tree. If it fails, something else wrote to the normalized tree between
the two counts. Find out what.

## When import counts differ

- FAIL lines. Sum them. They are messages the server refused:
  invalid RFC 822, too large, a bare attachment readpst produced.
  `sent + failed = after dedupe` must hold.
- FOLDER-FAIL lines. A whole folder could not be created or selected.
  Usually a name the server rejects (too long, a character it does not
  allow). Rename in the normalized tree and re-run.
- A worker died. The last log has no WORKER-DONE. Restart the same
  command; the state directory makes it resume.

## When reconcile shows DELTA

- live < expected by exactly the FAIL count for that folder: the
  rejects. Expected.
- live < expected, not matching FAIL: the state file claims messages
  were sent that are not there. Happens when the server accepted the
  APPEND and lost the message on a crash. Delete the folder's
  `work/state/<sha1>.done`, re-run import for that folder, reconcile
  again.
- live > expected: the folder was imported twice into different
  hierarchies, or the server is rebuilding its index and STATUS is
  reporting stale numbers. Wait ten minutes, run again. If it holds,
  the folder has duplicates on the server. This toolkit does not delete
  on the server. Delete the folder in a mail client and re-import it,
  after removing its state file.
- MISSING: the folder was never created. See FOLDER-FAIL.

## When verify shows NOTFOUND or MISMATCH

- NOTFOUND with a folder name the server rejects: the mapping from
  normalized path to folder name differs from what was imported (you
  changed `server.prefix`, or renamed folders on the server).
- NOTFOUND in an existing folder: the message is a FAIL from import,
  or the server altered the Message-ID header (some do, on messages
  with none or with a malformed one).
- MISMATCH: the bytes differ beyond line endings. Fetch the message
  from the server by hand and diff. Common causes: the server added a
  header, or the importer wrapped the message (`wrapped` > 0 in the
  verify output; docs/lessons.md).

## Sampling

Verify samples. Fifty random messages catch systematic errors (every
message wrapped, every date wrong). They do not catch a single lost
message. Reconcile catches that: counts are exhaustive. Use both.

## Hashes

sha1 of the bytes with CRLF folded to LF. sha1 is fine here; nobody
is attacking your archive, and it is fast. Fold line endings because
IMAP servers store CRLF and disk files may have LF. Nothing else is
folded: a server that rewrites headers fails verify, which is what you
want.
