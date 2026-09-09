"""Stage 3: convert every source into maildir under paths.normalized.

Originals are never modified. The normalized tree is a derivative and
can be regenerated at any time.

Layout of the normalized tree mirrors the archive tree:
  normalized/<provenance>/<mailbox path>/{cur,new,tmp}

  emlx trees:  Foo.mbox/Messages/123.emlx -> Foo.mbox/cur/<name>
  mbox files:  foo.mbox -> foo.mbox/cur/<name> (one file per message)
  eml trees:   dir/x.eml -> dir/cur/<name>
  maildir:     copied as-is (cur+new -> cur)

Every conversion logs SKIP lines for unreadable input and a DONE line
with counts. The counts are the first verification gate.
"""

import os
import sys

from .formats import (emlx_extract, mbox_iter, maildir_keys, maildir_read,
                      walk_maildirs)
from .util import (CHUNK, ensure_maildir, is_carrier, log, progress,
                   write_maildir_message)


def _rel_target(srcroot, dstroot, path, strip_messages=True):
    rel = os.path.relpath(path, srcroot)
    d = os.path.dirname(rel)
    if strip_messages:
        if d == "Messages":
            d = ""
        elif d.endswith("/Messages"):
            d = d[: -len("/Messages")]
    return os.path.join(dstroot, d) if d else dstroot


def convert_emlx_tree(srcroot, dstroot, logfh):
    ok = skip = 0
    made = set()
    for dirpath, dirs, files in os.walk(srcroot):
        dirs[:] = [d for d in dirs if d != ".AppleDouble"]
        for f in sorted(files):
            if is_carrier(f) or not f.endswith(".emlx"):
                continue
            path = os.path.join(dirpath, f)
            try:
                with open(path, "rb") as fh:
                    msg, _n = emlx_extract(fh)
            except (OSError, ValueError) as e:
                log(logfh, "SKIP", path, e)
                skip += 1
                continue
            md = _rel_target(srcroot, dstroot, path)
            if md not in made:
                ensure_maildir(md)
                made.add(md)
            write_maildir_message(md, msg)
            ok += 1
    log(logfh, "DONE", "emlx", srcroot, "ok=%d" % ok, "skip=%d" % skip)
    return ok, skip


def convert_mbox_file(path, dstdir, logfh):
    """One mbox file -> one maildir at dstdir."""
    ensure_maildir(dstdir)
    ok = skip = 0
    for idx, msg in mbox_iter(path):
        if not msg.strip():
            log(logfh, "SKIP", "%s#%d" % (path, idx), "empty message")
            skip += 1
            continue
        write_maildir_message(dstdir, msg)
        ok += 1
    log(logfh, "DONE", "mbox", path, "ok=%d" % ok, "skip=%d" % skip)
    return ok, skip


def convert_eml_tree(srcroot, dstroot, logfh):
    """A tree of one-message-per-file .eml (readpst -S, msgconvert)."""
    ok = skip = 0
    made = set()
    for dirpath, dirs, files in os.walk(srcroot):
        dirs[:] = [d for d in dirs if d != ".AppleDouble"]
        for f in sorted(files):
            if is_carrier(f):
                continue
            path = os.path.join(dirpath, f)
            try:
                size = os.path.getsize(path)
                if size == 0:
                    raise ValueError("empty file")
                with open(path, "rb") as fh:
                    msg = fh.read()
            except (OSError, ValueError) as e:
                log(logfh, "SKIP", path, e)
                skip += 1
                continue
            rel = os.path.relpath(dirpath, srcroot)
            md = dstroot if rel == "." else os.path.join(dstroot, rel)
            if md not in made:
                ensure_maildir(md)
                made.add(md)
            write_maildir_message(md, msg)
            ok += 1
    log(logfh, "DONE", "eml", srcroot, "ok=%d" % ok, "skip=%d" % skip)
    return ok, skip


def copy_maildir_tree(srcroot, dstroot, logfh):
    ok = skip = 0
    for rel, md in walk_maildirs(srcroot):
        dst = dstroot if rel == "." else os.path.join(dstroot, rel)
        ensure_maildir(dst)
        for key in maildir_keys(md):
            try:
                msg = maildir_read(md, key)
                if not msg:
                    raise ValueError("empty file")
            except (OSError, ValueError) as e:
                log(logfh, "SKIP", os.path.join(md, key), e)
                skip += 1
                continue
            write_maildir_message(dst, msg)
            ok += 1
    log(logfh, "DONE", "maildir", srcroot, "ok=%d" % ok, "skip=%d" % skip)
    return ok, skip


KINDS = {
    "emlx": convert_emlx_tree,
    "eml": convert_eml_tree,
    "maildir": copy_maildir_tree,
}


def run(cfg, kind, src, dest):
    """emailc normalize KIND SRC DEST
    KIND: emlx | mbox | eml | maildir
    SRC: a directory (or a file for mbox) inside the archive
    DEST: provenance path relative to paths.normalized"""
    dstroot = os.path.join(cfg.normalized, dest)
    os.makedirs(cfg.work, exist_ok=True)
    logpath = os.path.join(cfg.work, "normalize.log")
    with open(logpath, "a") as logfh:
        progress("normalize %s %s -> %s" % (kind, src, dstroot))
        if kind == "mbox":
            if os.path.isdir(src):
                tot_ok = tot_skip = 0
                for dirpath, dirs, files in os.walk(src):
                    dirs[:] = [d for d in dirs if d != ".AppleDouble"]
                    for f in sorted(files):
                        if is_carrier(f) or not f.lower().endswith(".mbox"):
                            continue
                        p = os.path.join(dirpath, f)
                        rel = os.path.relpath(p, src)
                        o, s = convert_mbox_file(p, os.path.join(dstroot, rel),
                                                 logfh)
                        tot_ok += o
                        tot_skip += s
                ok, skip = tot_ok, tot_skip
            else:
                ok, skip = convert_mbox_file(src, dstroot, logfh)
        elif kind in KINDS:
            ok, skip = KINDS[kind](src, dstroot, logfh)
        else:
            raise SystemExit("unknown kind %s (emlx|mbox|eml|maildir)" % kind)
    print("DONE\tok=%d\tskip=%d\tlog=%s" % (ok, skip, logpath))
    if skip:
        print("skipped files are listed in the log. Read every one.")
