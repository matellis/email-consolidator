"""Stage 1: find every email artifact under the source roots.

Writes work/inventory.tsv with one row per file:
  kind  path  size  mtime
Kinds: emlx, mbox, maildir (one row per maildir, size is message
count), pst, ost, msg, eml, other-mail (Outlook .olm, Thunderbird
.msf indexes and the like, listed so nothing is silently ignored).

Nothing is read beyond a 4-byte magic check for .msg files.
"""

import os

from .formats import is_maildir
from .util import is_carrier, progress, write_tsv

EXT = {
    ".emlx": "emlx",
    ".mbox": "mbox",
    ".pst": "pst",
    ".ost": "ost",
    ".msg": "msg",
    ".eml": "eml",
    ".olm": "other-mail",
    ".msf": "other-mail",
    ".sbd": "other-mail",
}

OLE_MAGIC = b"\xd0\xcf\x11\xe0"


def classify(path, name):
    base, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext == ".mbox":
        # Apple Mail uses Foo.mbox as a DIRECTORY holding Messages/*.emlx;
        # real mbox is a file.
        return "mbox" if os.path.isfile(path) else None
    kind = EXT.get(ext)
    if kind == "msg":
        try:
            with open(path, "rb") as fh:
                if fh.read(4) != OLE_MAGIC:
                    return None   # a text ".msg" (locale catalog etc.)
        except OSError:
            return None
    return kind


def scan(roots):
    rows = []
    for root in roots:
        root = os.path.expanduser(root)
        progress("scanning %s" % root)
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d != ".AppleDouble"]
            if is_maildir(dirpath):
                n = 0
                for sub in ("cur", "new"):
                    try:
                        n += sum(1 for f in os.listdir(os.path.join(dirpath, sub))
                                 if not is_carrier(f))
                    except OSError:
                        pass
                rows.append(("maildir", dirpath, n,
                             int(os.stat(dirpath).st_mtime)))
                # a maildir's cur/new/tmp hold messages, not more sources
                dirs[:] = [d for d in dirs if d not in ("cur", "new", "tmp")]
            for f in files:
                if is_carrier(f):
                    continue
                p = os.path.join(dirpath, f)
                kind = classify(p, f)
                if kind is None:
                    continue
                try:
                    st = os.stat(p)
                except OSError:
                    rows.append(("error", p, 0, 0))
                    continue
                rows.append((kind, p, st.st_size, int(st.st_mtime)))
    return rows


def summarize(rows):
    by = {}
    for kind, _p, size, _m in rows:
        c, b = by.get(kind, (0, 0))
        by[kind] = (c + 1, b + (size if kind != "maildir" else 0))
    return by


def run(cfg):
    roots = cfg["paths"]["sources"]
    if not roots:
        raise SystemExit("paths.sources is empty")
    rows = scan(roots)
    os.makedirs(cfg.work, exist_ok=True)
    out = os.path.join(cfg.work, "inventory.tsv")
    write_tsv(out, ("kind", "path", "size", "mtime"), rows)
    print("kind\tcount\tbytes")
    for kind, (c, b) in sorted(summarize(rows).items()):
        print("%s\t%d\t%d" % (kind, c, b))
    print("wrote %s (%d rows)" % (out, len(rows)))
