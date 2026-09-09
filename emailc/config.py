"""Configuration: one TOML file, paths and server settings.

See config.example.toml for every key. The password is never in the
config; it lives in a separate file named by ``server.password_file``
with mode 0600.
"""

import os
import sys
import tomllib


DEFAULTS = {
    "paths": {
        "sources": [],
        "archive": "",
        "normalized": "",
        "work": "",
    },
    "server": {
        "host": "",
        "port": 993,
        "tls": True,
        "user": "",
        "password_file": "",
        "prefix": "Archive",
        "auth": "login",
    },
    "gmail": {
        "user": "",
        "password_file": "",
        "folder": "[Gmail]/All Mail",
    },
    "dedupe": {
        "prefer": [],
    },
}


class Config:
    def __init__(self, data, path):
        self.path = path
        self.data = data

    def __getitem__(self, section):
        merged = dict(DEFAULTS.get(section, {}))
        merged.update(self.data.get(section, {}))
        return merged

    @property
    def work(self):
        return self["paths"]["work"]

    @property
    def normalized(self):
        return self["paths"]["normalized"]

    @property
    def archive(self):
        return self["paths"]["archive"]

    def password(self, section="server"):
        pf = self[section]["password_file"]
        if not pf:
            raise SystemExit("no %s.password_file in %s" % (section, self.path))
        pf = os.path.expanduser(pf)
        mode = os.stat(pf).st_mode & 0o777
        if mode & 0o077:
            sys.stderr.write("WARNING: %s is readable by others (mode %o); "
                             "run chmod 600 on it\n" % (pf, mode))
        with open(pf) as fh:
            return fh.read().strip()


def load(path=None):
    path = path or os.environ.get("EMAILC_CONFIG", "config.toml")
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        raise SystemExit("config not found: %s (copy config.example.toml "
                         "to config.toml and edit it)" % path)
    cfg = Config(data, path)
    for key in ("archive", "normalized", "work"):
        if not cfg["paths"][key]:
            raise SystemExit("paths.%s is not set in %s" % (key, path))
    return cfg
