"""Readers for the on-disk email formats.

Every reader yields raw message bytes and never modifies its input.

  emlx    Apple Mail. Line 1 is a decimal byte count N, then exactly N
          bytes of RFC 822 message, then an XML plist trailer.
  mbox    Messages separated by lines starting with "From ". The
          separator line is not part of the message.
  maildir cur/ and new/ hold one file per message.
  eml     One RFC 822 message per file (readpst -S and msgconvert
          output look like this).
  pst/ost/msg are binary Outlook containers. They are converted by
          external tools (readpst, msgconvert) into eml trees first.
          See docs/formats.md.
"""

import os
import re

from .util import CHUNK, is_carrier

HDR_START = re.compile(rb"^(From |[!-9;-~]+:)")


# ---------------------------------------------------------------- emlx

def emlx_extract(fh):
    """Return (message_bytes, declared_length). Raises ValueError on a
    malformed file. .partial.emlx files have the same layout."""
    line = fh.readline(64)
    if not line:
        raise ValueError("empty file")
    try:
        n = int(line.strip())
    except ValueError:
        raise ValueError("bad length prefix %r" % line[:20])
    if n <= 0:
        raise ValueError("zero/negative length %d" % n)
    parts = []
    got = 0
    while got < n:
        chunk = fh.read(min(CHUNK, n - got))
        if not chunk:
            raise ValueError("truncated: declared %d got %d" % (n, got))
        parts.append(chunk)
        got += len(chunk)
    return b"".join(parts), n


def emlx_read(path):
    with open(path, "rb") as fh:
        msg, _n = emlx_extract(fh)
    return msg


def plausible_message(data):
    """True when data starts like an RFC 822 message."""
    return bool(HDR_START.match(data))


# ---------------------------------------------------------------- mbox

def mbox_iter(path):
    """Yield (index, message_bytes) for every message in an mbox.
    Index starts at 1. The "From " separator line is dropped."""
    idx = 0
    buf = []
    with open(path, "rb") as fh:
        for line in fh:
            if line.startswith(b"From "):
                if buf:
                    yield idx, b"".join(buf)
                idx += 1
                buf = []
            elif idx > 0:
                buf.append(line)
    if buf:
        yield idx, b"".join(buf)


def mbox_count(path):
    n = 0
    with open(path, "rb") as fh:
        for line in fh:
            if line.startswith(b"From "):
                n += 1
    return n


def mbox_read(path, want):
    for idx, msg in mbox_iter(path):
        if idx == want:
            return msg
    raise KeyError("mbox %s has no message %d" % (path, want))


# ------------------------------------------------------------- maildir

def maildir_keys(md):
    """Yield relative keys (cur/name, new/name) for one maildir."""
    for sub in ("cur", "new"):
        d = os.path.join(md, sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not is_carrier(f):
                yield os.path.join(sub, f)


def maildir_count(md):
    return sum(1 for _ in maildir_keys(md))


def maildir_read(md, key):
    with open(os.path.join(md, key), "rb") as fh:
        return fh.read()


def is_maildir(path):
    return os.path.isdir(os.path.join(path, "cur"))


def walk_maildirs(root):
    """Yield every maildir under root, relative path first ("." for the
    root itself). Descends into nested maildirs, which Courier-style
    trees and readpst output both produce."""
    for dirpath, dirs, _files in os.walk(root):
        if "cur" in dirs:
            yield os.path.relpath(dirpath, root), dirpath
        dirs[:] = [d for d in dirs if d not in ("cur", "new", "tmp")
                   and d != ".AppleDouble"]


def courier_folder_parts(entry):
    """Courier maildir++ subfolder ".Sent.2009" -> ["Sent", "2009"]."""
    if entry.startswith("."):
        return [p for p in entry.lstrip(".").split(".") if p]
    return [entry]
