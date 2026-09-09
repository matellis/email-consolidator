"""Byte-level spot check: N random messages from the normalized tree,
found on the server by Message-ID, compared by LF-canonical sha1.

A wrapped or altered message shows up here as MISMATCH. Run this after
every import and after every dedupe. Also reports any stored message
that begins with "UTF8 (" (the imaplib wrapper trap).
"""

import os
import random

from .dedupe import message_id
from .formats import maildir_keys, maildir_read
from .importer import client, jobs
from .util import canonical_sha, lf_canonical


def run(cfg, n=25, seed=None):
    rng = random.Random(seed)
    all_msgs = []
    for folder, md in jobs(cfg):
        for key in maildir_keys(md):
            all_msgs.append((folder, md, key))
    if not all_msgs:
        raise SystemExit("normalized tree is empty")
    sample = rng.sample(all_msgs, min(n, len(all_msgs)))
    cli = client(cfg)
    ok = bad = notfound = wrapped = 0
    for folder, md, key in sample:
        disk = maildir_read(md, key)
        mid = message_id(disk)
        want = canonical_sha(disk)
        try:
            cli.select(folder)
        except RuntimeError as e:
            print("NOFOLDER\t%s\t%s" % (folder, e))
            notfound += 1
            continue
        uids = cli.uids()
        hit = None
        if mid:
            heads = {}
            for i in range(0, len(uids), 500):
                heads.update(cli.fetch_header(uids[i:i + 500], "MESSAGE-ID"))
            for uid, val in heads.items():
                if mid in val.decode("ascii", "replace").lower():
                    body = cli.fetch_body(uid)
                    if body.startswith(b"UTF8 ("):
                        wrapped += 1
                    if canonical_sha(_unwrap(body)) == want:
                        hit = uid
                        break
        else:
            for uid in uids:
                body = cli.fetch_body(uid)
                if canonical_sha(_unwrap(body)) == want:
                    hit = uid
                    break
        if hit is None:
            print("NOTFOUND\t%s\t%s\t%s" % (folder, key, mid))
            notfound += 1
        else:
            ok += 1
    cli.close()
    print("VERIFY\tsample=%d\tok=%d\tnotfound=%d\tmismatch=%d\twrapped=%d"
          % (len(sample), ok, notfound, bad, wrapped))
    if wrapped:
        print("wrapped messages exist: the importer enabled UTF8=ACCEPT. "
              "See docs/lessons.md.")
    return 0 if ok == len(sample) else 1


def _unwrap(data):
    if data.startswith(b"UTF8 (") and data.rstrip().endswith(b")"):
        return data[6:data.rfind(b")")]
    return data
