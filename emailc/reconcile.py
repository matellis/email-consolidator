"""Stage 6: expected (normalized tree) vs live (IMAP STATUS) per folder.

Writes work/reconcile.tsv: folder, expected, live, status
(OK | MISSING | DELTA). Nothing is waved through: every DELTA row must
be explained before the archive is called done.

Caveat learned the hard way: STATUS counts taken while a server is
rebuilding its index after a restart can overstate. If numbers look
too high, wait and run again.
"""

import os

from .formats import maildir_count
from .importer import client, jobs
from .util import write_tsv


def run(cfg):
    cli = client(cfg)
    rows = []
    ok = missing = delta = 0
    for folder, md in jobs(cfg):
        expected = maildir_count(md)
        live = cli.status_messages(folder)
        if live is None:
            status = "MISSING"
            missing += 1
            live = 0
        elif live == expected:
            status = "OK"
            ok += 1
        else:
            status = "DELTA"
            delta += 1
        rows.append((folder, expected, live, status))
    cli.close()
    out = os.path.join(cfg.work, "reconcile.tsv")
    write_tsv(out, ("folder", "expected", "live", "status"), rows)
    print("OK\t%d\nMISSING\t%d\nDELTA\t%d" % (ok, missing, delta))
    print("expected total\t%d" % sum(r[1] for r in rows))
    print("live total\t%d" % sum(r[2] for r in rows))
    print("wrote %s" % out)
    if missing or delta:
        print("\nfolders needing attention:")
        for f, e, l, s in rows:
            if s != "OK":
                print("  %s\t%s\texpected=%d\tlive=%d" % (s, f, e, l))
    return 0 if not (missing or delta) else 1
