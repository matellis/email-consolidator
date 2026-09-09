"""Stage 5: import the normalized tree into the IMAP server.

Every maildir under paths.normalized becomes the folder
  <server.prefix>/<relative path with "/" separators>
Every message is APPENDed with \\Seen and an INTERNALDATE from its Date:
header (file mtime when unparseable).

Resumable: work/state/<sha1 of folder>.done holds one line per message
key already appended. Restarting skips them. FAIL lines in
work/import.log name every message the server rejected; those are
never retried automatically and never abort the run.

Workers: N forked processes, each with its own connection, folders
balanced by message count.
"""

import email.utils
import hashlib
import os
import re
import sys
import time

from .formats import maildir_count, maildir_keys, maildir_read, walk_maildirs
from .imap_client import Client, join_folder
from .util import log, progress

DATE_RE = re.compile(rb"^Date:[ \t]*(.+?)[ \t]*$", re.I | re.M)
HDR_BYTES = 16384


def client(cfg):
    s = cfg["server"]
    return Client(s["host"], s["port"], s["user"], cfg.password(),
                  tls=s["tls"], auth=s["auth"]).connect()


def jobs(cfg):
    """Yield (folder, maildir_path) for the whole normalized tree."""
    prefix = cfg["server"]["prefix"]
    for rel, md in walk_maildirs(cfg.normalized):
        parts = [] if rel == "." else rel.split(os.sep)
        yield join_folder(prefix, *parts), md


def internal_date(msg, path):
    m = DATE_RE.search(msg[:HDR_BYTES])
    if m:
        try:
            dt = email.utils.parsedate_to_datetime(
                m.group(1).decode("ascii", "replace"))
            if dt is not None:
                return dt.timestamp()
        except (ValueError, TypeError, OverflowError):
            pass
    try:
        return os.path.getmtime(path)
    except OSError:
        return time.time()


def state_dir(cfg):
    d = os.path.join(cfg.work, "state")
    os.makedirs(d, exist_ok=True)
    return d


def state_path(cfg, folder):
    return os.path.join(state_dir(cfg),
                        hashlib.sha1(folder.encode("utf-8")).hexdigest()
                        + ".done")


def load_done(cfg, folder):
    try:
        with open(state_path(cfg, folder)) as fh:
            return set(l.rstrip("\n") for l in fh)
    except OSError:
        return set()


def run_folder(cfg, cli, folder, md, logfh, limit=None):
    done = load_done(cfg, folder)
    cli.ensure(folder)
    sent = skipped = failed = 0
    with open(state_path(cfg, folder), "a") as out:
        for key in maildir_keys(md):
            if limit is not None and sent >= limit:
                break
            if key in done:
                skipped += 1
                continue
            path = os.path.join(md, key)
            try:
                msg = maildir_read(md, key)
                if not msg:
                    raise RuntimeError("empty message")
                cli.append(folder, msg, internal_date(msg, path))
                out.write(key + "\n")
                out.flush()
                sent += 1
            except Exception as e:
                log(logfh, "FAIL", folder, key, e)
                failed += 1
    log(logfh, "FOLDER-DONE", folder, "sent=%d" % sent,
        "skipped=%d" % skipped, "failed=%d" % failed)
    return sent, failed


def plan(cfg):
    total = 0
    for folder, md in jobs(cfg):
        n = maildir_count(md)
        total += n
        print("%d\t%s" % (n, folder))
    print("TOTAL\t%d" % total, file=sys.stderr)


def run(cfg, workers=2, only=None, limit=None):
    all_jobs = []
    for folder, md in jobs(cfg):
        if only and folder != only and not folder.startswith(only + "/"):
            continue
        all_jobs.append((maildir_count(md), folder, md))
    all_jobs.sort(reverse=True)
    if not all_jobs:
        raise SystemExit("nothing to import (is paths.normalized right?)")
    if workers <= 1 or len(all_jobs) == 1:
        buckets = [all_jobs]
    else:
        buckets = [[] for _ in range(workers)]
        loads = [0] * workers
        for job in all_jobs:
            k = loads.index(min(loads))
            buckets[k].append(job)
            loads[k] += job[0]
    kids = []
    for wid, bucket in enumerate(buckets):
        if not bucket:
            continue
        pid = os.fork()
        if pid == 0:
            logpath = os.path.join(cfg.work, "import.%d.log" % wid)
            with open(logpath, "a") as logfh:
                cli = client(cfg)
                tsent = tfail = 0
                for _n, folder, md in bucket:
                    try:
                        s, f = run_folder(cfg, cli, folder, md, logfh, limit)
                    except Exception as e:
                        log(logfh, "FOLDER-FAIL", folder, e)
                        continue
                    tsent += s
                    tfail += f
                    progress("w%d %s sent=%d failed=%d" % (wid, folder, s, f))
                log(logfh, "WORKER-DONE", "sent=%d" % tsent,
                    "failed=%d" % tfail)
                cli.close()
            os._exit(0)
        kids.append(pid)
    for pid in kids:
        os.waitpid(pid, 0)
    print("RUN-COMPLETE. Now run: emailc reconcile")
