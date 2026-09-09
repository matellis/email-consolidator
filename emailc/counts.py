"""Count messages per mailbox in the normalized tree, write
work/counts.tsv (folder, messages). This is the expected side of every
later reconciliation."""

import os

from .formats import maildir_count, walk_maildirs
from .util import write_tsv


def collect(normalized):
    rows = []
    for rel, md in walk_maildirs(normalized):
        rows.append((rel, maildir_count(md)))
    return rows


def run(cfg):
    rows = collect(cfg.normalized)
    os.makedirs(cfg.work, exist_ok=True)
    out = os.path.join(cfg.work, "counts.tsv")
    write_tsv(out, ("folder", "messages"), rows)
    total = sum(n for _f, n in rows)
    print("mailboxes\t%d" % len(rows))
    print("messages\t%d" % total)
    print("wrote %s" % out)
