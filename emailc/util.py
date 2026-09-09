"""Small shared helpers: hashing, logging, TSV, maildir names."""

import hashlib
import os
import sys
import time

CHUNK = 65536
_seq = 0


def sha1_bytes(data):
    return hashlib.sha1(data).hexdigest()


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def lf_canonical(data):
    """Bytes with CRLF folded to LF. Comparing under this form makes a
    message on disk and the same message stored by an IMAP server
    compare equal, since servers may canonicalize line endings."""
    return data.replace(b"\r\n", b"\n")


def canonical_sha(data):
    return sha1_bytes(lf_canonical(data))


def is_carrier(name):
    """AppleDouble sidecar (._name) or other non-message file."""
    return name.startswith("._") or name == ".DS_Store"


def maildir_name(size):
    """Unique maildir filename: time.pid_seq,S=size."""
    global _seq
    _seq += 1
    return "%d.%d_%d,S=%d" % (int(time.time()), os.getpid(), _seq, size)


def ensure_maildir(path):
    for sub in ("cur", "new", "tmp"):
        os.makedirs(os.path.join(path, sub), exist_ok=True)


def write_maildir_message(md, data):
    """Atomically write one message into md/cur. Returns the path."""
    name = maildir_name(len(data))
    tmp = os.path.join(md, "tmp", name)
    dst = os.path.join(md, "cur", name)
    with open(tmp, "wb") as out:
        out.write(data)
    os.rename(tmp, dst)
    return dst


def log(fh, *fields):
    fh.write("\t".join(str(f) for f in fields) + "\n")
    fh.flush()


def stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S %Z")


def write_tsv(path, header, rows):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write("\t".join(header) + "\n")
        for row in rows:
            fh.write("\t".join(str(c) for c in row) + "\n")
    os.replace(tmp, path)


def read_tsv(path):
    with open(path) as fh:
        header = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            yield dict(zip(header, line.split("\t")))


def progress(msg):
    sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
    sys.stderr.flush()
