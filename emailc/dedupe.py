"""Stage 4: find and quarantine duplicate messages in the normalized
tree, BEFORE anything is imported to a server.

Key: normalized Message-ID + sha1 of LF-canonical bytes. Two files are
duplicates only when both match. A Message-ID that appears with more
than one distinct body (drafts, resent mail, edited copies) is left
alone entirely. Messages without a Message-ID are grouped by body hash
only.

One keeper per group, chosen by dedupe.prefer (a list of path prefixes
relative to the normalized tree, first match wins), then newest mtime,
then first path in sorted order.

`plan` writes work/dupes.tsv and prints a summary plus sample groups.
`apply` MOVES every loser into paths.work/quarantine/<same relative
path>. Nothing is deleted. Every move is logged with both hashes so it
can be reversed by hand.
"""

import os
import re
import shutil

from .formats import maildir_keys, walk_maildirs
from .util import canonical_sha, log, progress, read_tsv, write_tsv

MID_RE = re.compile(rb"^Message-ID:[ \t]*(.+?)[ \t]*$", re.I | re.M)
HDR_BYTES = 32768


def norm_mid(value):
    return value.strip().strip(b"<>").strip().lower().decode("ascii", "replace")


def message_id(data):
    head = data[:HDR_BYTES]
    body_start = head.find(b"\n\n")
    crlf = head.find(b"\r\n\r\n")
    if crlf != -1 and (body_start == -1 or crlf < body_start):
        body_start = crlf
    if body_start != -1:
        head = head[:body_start]
    m = MID_RE.search(head)
    return norm_mid(m.group(1)) if m else ""


def scan(normalized):
    """Yield (relpath, mid, sha, mtime) for every message."""
    for rel, md in walk_maildirs(normalized):
        for key in maildir_keys(md):
            p = os.path.join(md, key)
            with open(p, "rb") as fh:
                data = fh.read()
            relp = os.path.relpath(p, normalized)
            yield relp, message_id(data), canonical_sha(data), \
                int(os.stat(p).st_mtime)


def group(rows):
    """rows: iterable of (relpath, mid, sha, mtime).
    Returns (groups, multi_body_mids). groups: dict key -> list of
    (relpath, mtime), key = (mid, sha)."""
    by_mid = {}
    groups = {}
    for relp, mid, sha, mtime in rows:
        if mid:
            by_mid.setdefault(mid, set()).add(sha)
        groups.setdefault((mid, sha), []).append((relp, mtime))
    multi = {m for m, shas in by_mid.items() if len(shas) > 1}
    return groups, multi


def pick_keeper(paths, prefer):
    """paths: list of (relpath, mtime)."""
    for pref in prefer:
        pref = pref.strip("/") + "/"
        cands = sorted(p for p in paths if p[0].startswith(pref))
        if cands:
            return cands[0][0]
    newest = max(m for _p, m in paths)
    cands = sorted(p for p, m in paths if m == newest)
    return cands[0]


def plan(cfg, samples=10):
    prefer = cfg["dedupe"]["prefer"]
    progress("scanning %s" % cfg.normalized)
    rows = list(scan(cfg.normalized))
    groups, multi = group(rows)
    out_rows = []
    n_groups = n_losers = n_multi = 0
    for (mid, sha), paths in sorted(groups.items()):
        if len(paths) < 2:
            continue
        if mid in multi:
            n_multi += 1
            for p, _m in paths:
                out_rows.append((mid, sha, "multi-body", "keep", p))
            continue
        n_groups += 1
        keeper = pick_keeper(paths, prefer)
        for p, _m in sorted(paths):
            role = "keep" if p == keeper else "quarantine"
            if role == "quarantine":
                n_losers += 1
            out_rows.append((mid, sha, "dup", role, p))
    os.makedirs(cfg.work, exist_ok=True)
    out = os.path.join(cfg.work, "dupes.tsv")
    write_tsv(out, ("message_id", "sha1_canonical", "kind", "action", "path"),
              out_rows)
    print("messages scanned\t%d" % len(rows))
    print("duplicate groups\t%d" % n_groups)
    print("copies to quarantine\t%d" % n_losers)
    print("multi-body Message-IDs skipped\t%d" % n_multi)
    print("survivors after apply\t%d" % (len(rows) - n_losers))
    print("wrote %s" % out)
    shown = 0
    print("\nsample groups (keep first):")
    for (mid, sha), paths in groups.items():
        if len(paths) < 2 or mid in multi:
            continue
        keeper = pick_keeper(paths, prefer)
        print("  %s" % (mid or "<no message-id>"))
        print("    KEEP  %s" % keeper)
        for p, _m in sorted(paths):
            if p != keeper:
                print("    MOVE  %s" % p)
        shown += 1
        if shown >= samples:
            break


def apply(cfg):
    plan_path = os.path.join(cfg.work, "dupes.tsv")
    if not os.path.exists(plan_path):
        raise SystemExit("run `emailc dedupe plan` first")
    qroot = os.path.join(cfg.work, "quarantine")
    logpath = os.path.join(cfg.work, "dedupe.log")
    moved = missing = mismatch = 0
    with open(logpath, "a") as logfh:
        for row in read_tsv(plan_path):
            if row["action"] != "quarantine":
                continue
            src = os.path.join(cfg.normalized, row["path"])
            if not os.path.exists(src):
                log(logfh, "MISSING", row["path"])
                missing += 1
                continue
            with open(src, "rb") as fh:
                sha = canonical_sha(fh.read())
            if sha != row["sha1_canonical"]:
                # the file changed since the plan: never touch it
                log(logfh, "MISMATCH", row["path"], row["sha1_canonical"], sha)
                mismatch += 1
                continue
            dst = os.path.join(qroot, row["path"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            log(logfh, "MOVED", row["path"], row["message_id"], sha)
            moved += 1
    print("moved\t%d\nmissing\t%d\nmismatch\t%d\nquarantine\t%s\nlog\t%s"
          % (moved, missing, mismatch, qroot, logpath))
    if mismatch:
        print("MISMATCH rows were left in place. Re-run `dedupe plan`.")
