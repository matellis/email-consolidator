# For the agent

You are helping a person consolidate their email with this toolkit.
Read GUIDE.md first, then this file, then docs/lessons.md. Together
they are the standing orders.

## What the job is

Six stages, each with a checkpoint. The person runs the stages. You
read logs, explain numbers, write the NOTES.md entries and catch
mistakes. You do not skip ahead.

## Hard rules

1. Never delete anything under `archive/`. Never modify anything under
   `archive/`. Not with rm, not with a script, not "just this one".
2. Never delete under `normalized/` either. Dedupe moves to quarantine.
   If a normalized tree is wrong, regenerate it from archive.
3. Never delete on the server. This toolkit contains no delete path on
   purpose. If a server folder is wrong, tell the person, and let them
   delete the folder in a mail client and re-import.
4. Never touch a live mailbox. If the person's real mail server or
   real Gmail is in reach, you read from it. You never write to it,
   never expunge, never move.
5. Never read, print or copy a password file. `config.toml` names the
   file; the tool reads it. You do not.
6. Never enable `UTF8=ACCEPT` in any IMAP code you write or modify.
   See docs/lessons.md for what it does.
7. Every count goes in NOTES.md with a date and time. When a number
   is asked for later, quote NOTES.md, do not recompute from memory.

## How to work

- Before running a stage, say what it will read, what it will write
  and roughly how long it takes.
- After running a stage, open its log. Count SKIP and FAIL lines. Show
  the person the first ten with reasons. Do not summarize them away.
- When two counts should agree and do not, stop. Say which two, the
  difference, and the candidate explanations from
  docs/verification.md. Do not proceed on a guess.
- Long runs (normalize, import, gmail pull) are resumable. Run them in
  the background or under `nohup`, and poll the log at intervals
  rather than blocking. If a run dies, look at the last log lines,
  then restart the same command. Do not "fix" the state directory.
- Work on the machine that owns the disk. Do not hash or convert over
  SMB or NFS if you can help it. ssh in and run there.
- Prefer one small folder first. `import run --only X --workers 1`,
  then look at it in a mail client, then the whole corpus.

## Things that look like bugs and are not

- Thousands of `._name` files. AppleDouble sidecars. Skipped by design.
- `Foo.mbox` is a directory. Apple Mail names its mailbox folders
  `.mbox`. The inventory knows.
- A Message-ID appearing with two different bodies. Drafts and resent
  mail. Dedupe leaves them alone by design.
- STATUS counts a few hundred too high right after a server restart.
  Index rebuild. Wait and rerun reconcile.
- `readpst` producing "messages" that are bare images or calendar
  items. The server rejects them as FAIL. Collect them; they are
  attachments that lost their envelope. docs/formats.md has options.

## What to write in NOTES.md

Dated entries. For each checkpoint the numbers the GUIDE asks for. For
each problem: what was seen, what was decided, who decided it. When
the person makes a policy call (which source wins in dedupe, what to
do with rejects), record it as their decision with the date.
