"""Pull a Gmail account into a local maildir over IMAP, one way.

Gmail specifics this handles:
  * "[Gmail]/All Mail" holds every message once. Labels are Gmail's
    folders; a message with three labels appears in three IMAP folders
    but is one message in All Mail. Pulling All Mail plus the X-GM-LABELS
    attribute gives everything once, with its labels.
  * X-GM-MSGID is a stable 64-bit id per message. It is the resume key,
    so a re-run only fetches what is new.
  * Gmail throttles bulk IMAP. Fetch in modest batches, sleep on
    throttle responses, and expect a first pull of a large mailbox to
    take hours. Restart freely; it resumes.
  * Auth: an App Password (2-Step Verification must be on) or OAuth2
    XOAUTH2. App Passwords are the simplest for a personal archive.
    See docs/gmail-imap.md.

Output:
  <archive>/gmail/<user>/All Mail/{cur,new,tmp}      raw RFC 822 bytes
  <archive>/gmail/<user>/labels.tsv                   gm_msgid, labels, file
  <work>/gmail-<user>.done                            gm_msgid per fetched
"""

import imaplib
import os
import re
import ssl
import time

from .util import ensure_maildir, log, progress, write_maildir_message

HOST = "imap.gmail.com"
PORT = 993
BATCH = 200
GM_RE = re.compile(rb"X-GM-MSGID (\d+)")
LABELS_RE = re.compile(rb"X-GM-LABELS \((.*?)\)(?= [A-Z]|\)$)", re.S)

imaplib._MAXLINE = 100_000_000


def connect(user, password):
    ctx = ssl.create_default_context()
    m = imaplib.IMAP4_SSL(HOST, PORT, ssl_context=ctx)
    m.login(user, password)
    return m


def gm_folder_name(m, want="[Gmail]/All Mail"):
    """The All Mail folder is localized. Find it by the \\All flag."""
    t, d = m.list()
    if t == "OK":
        for item in d:
            line = item if isinstance(item, bytes) else item[0]
            if b"\\All" in line.split(b")")[0]:
                name = line.rsplit(b" ", 1)[1].strip(b'"')
                return name.decode("utf-8", "replace")
    return want


def load_done(path):
    try:
        with open(path) as fh:
            return set(l.rstrip("\n") for l in fh)
    except OSError:
        return set()


def pull(cfg, since=None, limit=None):
    g = cfg["gmail"]
    user = g["user"]
    if not user:
        raise SystemExit("gmail.user is not set")
    password = cfg.password("gmail")
    root = os.path.join(cfg.archive, "gmail", user)
    md = os.path.join(root, "All Mail")
    ensure_maildir(md)
    os.makedirs(cfg.work, exist_ok=True)
    done_path = os.path.join(cfg.work, "gmail-%s.done" % user)
    done = load_done(done_path)
    labels_path = os.path.join(root, "labels.tsv")
    new_labels = not os.path.exists(labels_path)

    m = connect(user, password)
    folder = gm_folder_name(m, g["folder"])
    t, d = m.select('"%s"' % folder, readonly=True)
    if t != "OK":
        raise SystemExit("cannot select %s: %s" % (folder, d))
    progress("selected %s: %s messages on server" % (folder, d[0].decode()))
    crit = "ALL" if not since else "SINCE %s" % since
    t, d = m.uid("SEARCH", None, crit)
    uids = [int(x) for x in d[0].split()] if t == "OK" and d[0] else []
    progress("%d uids match %s" % (len(uids), crit))

    fetched = skipped = failed = 0
    with open(done_path, "a") as donefh, open(labels_path, "a") as labfh:
        if new_labels:
            labfh.write("gm_msgid\tlabels\tfile\n")
        for i in range(0, len(uids), BATCH):
            if limit is not None and fetched >= limit:
                break
            chunk = uids[i:i + BATCH]
            # 1) cheap pass: which of these are new?
            t, d = _retry(m, lambda: m.uid("FETCH",
                                           ",".join(map(str, chunk)),
                                           "(X-GM-MSGID)"))
            todo = []
            for item in d:
                if not item:
                    continue
                line = item if isinstance(item, bytes) else item[0]
                mm = GM_RE.search(line)
                if not mm:
                    continue
                gmid = mm.group(1).decode()
                uid = int(line.split()[2] if line.split()[1] == b"(UID" else
                          _uid_of(line))
                if gmid in done:
                    skipped += 1
                else:
                    todo.append((uid, gmid))
            # 2) fetch bodies for new ones, one at a time (bodies are big)
            for uid, gmid in todo:
                if limit is not None and fetched >= limit:
                    break
                try:
                    t, d = _retry(m, lambda: m.uid(
                        "FETCH", str(uid),
                        "(X-GM-MSGID X-GM-LABELS BODY.PEEK[])"))
                    body = None
                    meta = b""
                    for item in d:
                        if isinstance(item, tuple):
                            meta, body = item[0], item[1]
                    if body is None:
                        raise RuntimeError("no body")
                    lm = LABELS_RE.search(meta)
                    labels = lm.group(1).decode("utf-8", "replace") if lm else ""
                    path = write_maildir_message(md, body)
                    labfh.write("%s\t%s\t%s\n" % (
                        gmid, labels.replace("\t", " "),
                        os.path.relpath(path, root)))
                    donefh.write(gmid + "\n")
                    donefh.flush()
                    done.add(gmid)
                    fetched += 1
                except Exception as e:
                    log(open(os.path.join(cfg.work, "gmail.log"), "a"),
                        "FAIL", user, uid, gmid, e)
                    failed += 1
            progress("fetched=%d skipped=%d failed=%d (%d/%d uids)"
                     % (fetched, skipped, failed, min(i + BATCH, len(uids)),
                        len(uids)))
    try:
        m.logout()
    except Exception:
        pass
    print("DONE\tfetched=%d\tskipped=%d\tfailed=%d\tmaildir=%s"
          % (fetched, skipped, failed, md))


def _uid_of(line):
    i = line.find(b"UID ")
    return line[i + 4:].split()[0]


def _retry(m, fn, tries=6):
    for attempt in range(tries):
        try:
            t, d = fn()
            if t == "OK":
                return t, d
            msg = b" ".join(x for x in d if isinstance(x, bytes))
            if b"throttl" in msg.lower() or b"rate" in msg.lower():
                raise imaplib.IMAP4.abort(msg)
            return t, d
        except (imaplib.IMAP4.abort, OSError, ssl.SSLError) as e:
            if attempt == tries - 1:
                raise
            wait = min(30 * (2 ** attempt), 600)
            progress("gmail: %s; sleeping %ds" % (e, wait))
            time.sleep(wait)
            try:
                m.noop()
            except Exception:
                raise imaplib.IMAP4.abort("connection lost; restart the pull")
