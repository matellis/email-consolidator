# email-consolidator

Stdlib Python only. No pip installs. Python 3.11 or newer.

## Who this is for

You have email scattered across old machines and backup drives. You
want it all in one place, searchable from any mail client, deduplicated,
and you want to be sure you did not lose anything. You are comfortable
in a terminal. You may be working with an AI coding agent; there is a
file for it too ([AGENTS.md](AGENTS.md)).

## The shape of the job

```
 sources ──▶ archive ──▶ normalized ──▶ dedupe ──▶ IMAP server
 (read-only) (originals,  (maildir,      (quarantine, (Archive/...)
              gathered)   regenerable)   never delete)
      │            │             │              │            │
      └── inventory┴── counts ───┴── counts ────┴── reconcile + verify
```

Six stages. Each one ends with a count you write down. The counts must
agree with each other at every step. That chain of counts is the proof.

| Stage | Command | Output |
| --- | --- | --- |
| 1 Inventory | `emailc inventory` | `work/inventory.tsv` |
| 2 Gather | `rsync` (you), see GUIDE | `archive/` |
| 3 Normalize | `emailc normalize ...` | `normalized/`, `work/counts.tsv` |
| 4 Dedupe | `emailc dedupe plan` then `apply` | `work/dupes.tsv`, `work/quarantine/` |
| 5 Import | `emailc import run` | messages on the server |
| 6 Verify | `emailc reconcile`, `emailc verify` | `work/reconcile.tsv` |

Gmail is pulled with `emailc gmail pull` and then treated as one more
source. See [docs/gmail-imap.md](docs/gmail-imap.md).

## Start here

1. Read [GUIDE.md](GUIDE.md) top to bottom once before running anything.
2. Copy `config.example.toml` to `config.toml` and fill in your paths.
3. `python3 emailc.py check`
4. Follow the GUIDE one stage at a time.

## Rules

- Originals are never modified and never deleted by this tool.
- Duplicates are moved to a quarantine folder, never deleted.
- Every stage logs what it skipped. Read the skips.
- Nothing is imported before the normalized tree is counted and deduped.
- Every server import is followed by a count reconciliation and a
  byte-level sample check.

## Documents

- [GUIDE.md](GUIDE.md): the walkthrough, one stage at a time.
- [AGENTS.md](AGENTS.md): rules for an AI agent helping you run this.
- [docs/formats.md](docs/formats.md): emlx, mbox, Maildir, pst/ost,
  msg, eml. What they are and how to read each one.
- [docs/gmail-imap.md](docs/gmail-imap.md): talking to Gmail over IMAP,
  app passwords, All Mail and labels, Takeout, keeping it in sync.
- [docs/server.md](docs/server.md): choosing and setting up the IMAP
  server that holds the archive, and how to reach it safely.
- [docs/verification.md](docs/verification.md): the counting and
  hashing discipline, and what to do when numbers disagree.
- [docs/lessons.md](docs/lessons.md): failure modes seen in this kind of job and why.

## Status

Built from scripts that ran a real consolidation end to end. The
stdlib IMAP client in this repo was checked against a
live Stalwart server for connection, folder listing, STATUS and body
fetch. Unit tests cover the format readers, dedupe grouping and the
normalize pipeline: `python3 -m unittest discover -s tests`.

MIT licensed.
