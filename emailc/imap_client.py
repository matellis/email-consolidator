"""A small IMAP client wrapper with the traps removed.

Rules baked in:
  * UTF8=ACCEPT is never enabled. With it, Python's imaplib wraps every
    APPEND as "UTF8 (...)" and some servers store that wrapper as the
    message. Folder names are sent as IMAP modified-UTF-7 instead.
  * Every APPEND is followed by nothing clever. Verification is a
    separate read-back step (verify.py).
  * Reconnect with backoff on connection loss; server NO/BAD answers
    are permanent and raised immediately.
"""

import imaplib
import ssl
import time

imaplib._MAXLINE = 100_000_000   # large FETCH responses


def utf7_encode(name):
    """RFC 3501 modified UTF-7 mailbox name."""
    out = []
    buf = []

    def flush():
        if buf:
            b = "".join(buf).encode("utf-16-be")
            import base64
            enc = base64.b64encode(b).decode("ascii").rstrip("=")
            out.append("&" + enc.replace("/", ",") + "-")
            buf.clear()

    for ch in name:
        o = ord(ch)
        if 0x20 <= o <= 0x7e:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            buf.append(ch)
    flush()
    return "".join(out)


def quote(name):
    return '"' + utf7_encode(name).replace("\\", "\\\\").replace('"', '\\"') + '"'


def sanitize(part):
    part = part.strip().strip("/").replace("/", "_")
    if part in ("", ".", ".."):
        part = "_"
    if part.startswith("."):
        part = "_" + part.lstrip(".")
    return part


def join_folder(*parts):
    comps = []
    for p in parts:
        comps.extend(sanitize(c) for c in p.split("/") if c != "")
    return "/".join(comps)


class Client:
    RETRIES = 5

    def __init__(self, host, port, user, password, tls=True, auth="login"):
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.tls, self.auth = tls, auth
        self.conn = None
        self.delim = "/"
        self.selected = None

    # ------------------------------------------------------ connection
    def connect(self):
        self.close()
        if self.tls:
            ctx = ssl.create_default_context()
            m = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ctx)
        else:
            m = imaplib.IMAP4(self.host, self.port)
        if self.auth == "plain":
            m.authenticate("PLAIN", lambda _x: b"\x00%s\x00%s" % (
                self.user.encode(), self.password.encode()))
        else:
            m.login(self.user, self.password)
        self.conn = m
        self.selected = None
        self._learn_delimiter()
        return self

    def _learn_delimiter(self):
        t, d = self.conn.list('""', '""')
        if t == "OK" and d and d[0]:
            line = d[0] if isinstance(d[0], bytes) else d[0][0]
            parts = line.split(b")", 1)
            if len(parts) == 2:
                rest = parts[1].strip().split(b" ", 1)[0]
                delim = rest.strip(b'"').decode("ascii", "replace")
                if delim and delim != "NIL":
                    self.delim = delim

    def close(self):
        if self.conn is not None:
            try:
                self.conn.logout()
            except Exception:
                pass
        self.conn = None
        self.selected = None

    def server_name(self, folder):
        """Our canonical "/"-joined folder -> server hierarchy."""
        return folder.replace("/", self.delim)

    def _retry(self, fn, *args):
        for attempt in range(1, self.RETRIES + 1):
            try:
                return fn(*args)
            except (imaplib.IMAP4.abort, BrokenPipeError,
                    ConnectionResetError, OSError, ssl.SSLError):
                if attempt == self.RETRIES:
                    raise
                time.sleep(5 * attempt)
                self.connect()
            except imaplib.IMAP4.error as e:
                s = str(e)
                if "illegal in state" in s or "Connection" in s:
                    if attempt == self.RETRIES:
                        raise
                    time.sleep(5 * attempt)
                    self.connect()
                else:
                    raise

    # --------------------------------------------------------- folders
    def ensure(self, folder):
        name = self.server_name(folder)
        t, _ = self.conn.select(quote(name), readonly=True)
        self.selected = None
        if t == "OK":
            return
        parts = folder.split("/")
        for i in range(1, len(parts) + 1):
            sub = self.server_name("/".join(parts[:i]))
            t, _ = self.conn.create(quote(sub))
            if t != "OK":
                t2, _ = self.conn.select(quote(sub), readonly=True)
                if t2 != "OK":
                    raise RuntimeError("cannot create %s" % sub)
        self.selected = None

    def status_messages(self, folder):
        name = self.server_name(folder)
        t, d = self.conn.status(quote(name), "(MESSAGES)")
        if t != "OK":
            return None
        line = d[0] if isinstance(d[0], bytes) else d[0][0]
        i = line.rfind(b"MESSAGES")
        return int(line[i:].split()[1].rstrip(b")"))

    def list_folders(self, prefix=""):
        pat = quote(self.server_name(prefix) + self.delim + "*") if prefix \
            else '"*"'
        t, d = self.conn.list('""', pat)
        names = []
        if t != "OK":
            return names
        for item in d:
            if not item:
                continue
            line = item if isinstance(item, bytes) else item[0]
            # (flags) "delim" name
            i = line.find(b")")
            rest = line[i + 1:].strip()
            _delim, name = rest.split(b" ", 1)
            name = name.strip().strip(b'"').decode("utf-8", "replace")
            names.append(name.replace(self.delim, "/"))
        if prefix and prefix not in names:
            names.insert(0, prefix)
        return names

    # -------------------------------------------------------- messages
    def append(self, folder, data, when):
        def do():
            t, d = self.conn.append(quote(self.server_name(folder)),
                                    "(\\Seen)", when, data)
            if t != "OK":
                raise imaplib.IMAP4.error(
                    d[0].decode("utf-8", "replace") if d else "APPEND failed")
        return self._retry(do)

    def select(self, folder, readonly=True):
        name = self.server_name(folder)
        t, d = self.conn.select(quote(name), readonly=readonly)
        if t != "OK":
            raise RuntimeError("cannot select %s: %s" % (folder, d))
        self.selected = folder
        return int(d[0])

    def uids(self):
        t, d = self.conn.uid("SEARCH", None, "ALL")
        if t != "OK" or not d or not d[0]:
            return []
        return [int(x) for x in d[0].split()]

    def fetch_body(self, uid):
        t, d = self.conn.uid("FETCH", str(uid), "(BODY.PEEK[])")
        if t != "OK":
            raise RuntimeError("FETCH %s failed" % uid)
        for item in d:
            if isinstance(item, tuple) and len(item) == 2:
                return item[1]
        raise RuntimeError("FETCH %s returned no body" % uid)

    def fetch_header(self, uids, header):
        """Return {uid: header_value_bytes} for a batch of uids."""
        if not uids:
            return {}
        seq = ",".join(str(u) for u in uids)
        t, d = self.conn.uid("FETCH", seq,
                             "(BODY.PEEK[HEADER.FIELDS (%s)])" % header)
        out = {}
        if t != "OK":
            return out
        for item in d:
            if isinstance(item, tuple) and len(item) == 2:
                meta, val = item
                i = meta.find(b"UID ")
                uid = int(meta[i + 4:].split()[0])
                out[uid] = val
        return out
