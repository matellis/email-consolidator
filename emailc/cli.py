"""emailc command line.

  emailc inventory                      scan paths.sources -> work/inventory.tsv
  emailc normalize KIND SRC DEST        convert one source into the normalized tree
  emailc sample N ROOT [ROOT...]        random re-extract check of emlx files
  emailc counts                         messages per mailbox -> work/counts.tsv
  emailc dedupe plan|apply              find and quarantine duplicates on disk
  emailc import plan|run [--workers N] [--only FOLDER] [--limit N]
  emailc reconcile                      expected vs live counts per folder
  emailc verify [N]                     byte-level spot check of N random messages
  emailc gmail pull [--since DD-Mon-YYYY] [--limit N]
  emailc check                          config and connection self-test

Config file: ./config.toml or $EMAILC_CONFIG.
"""

import sys

from . import config


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]

    if cmd == "sample":
        from . import sample
        return sample.run(int(rest[0]), rest[1:])

    cfg = config.load()

    if cmd == "inventory":
        from . import inventory
        return inventory.run(cfg)
    if cmd == "normalize":
        if len(rest) != 3:
            raise SystemExit("usage: emailc normalize KIND SRC DEST")
        from . import normalize
        return normalize.run(cfg, *rest)
    if cmd == "counts":
        from . import counts
        return counts.run(cfg)
    if cmd == "dedupe":
        from . import dedupe
        sub = rest[0] if rest else "plan"
        if sub == "plan":
            return dedupe.plan(cfg)
        if sub == "apply":
            return dedupe.apply(cfg)
        raise SystemExit("usage: emailc dedupe plan|apply")
    if cmd == "import":
        from . import importer
        sub = rest[0] if rest else "plan"
        if sub == "plan":
            return importer.plan(cfg)
        if sub == "run":
            opts = _opts(rest[1:], {"--workers": int, "--only": str,
                                    "--limit": int})
            return importer.run(cfg, workers=opts.get("--workers", 2),
                                only=opts.get("--only"),
                                limit=opts.get("--limit"))
        raise SystemExit("usage: emailc import plan|run")
    if cmd == "reconcile":
        from . import reconcile
        return reconcile.run(cfg)
    if cmd == "verify":
        from . import verify
        return verify.run(cfg, int(rest[0]) if rest else 25)
    if cmd == "gmail":
        from . import gmail
        if rest and rest[0] == "pull":
            opts = _opts(rest[1:], {"--since": str, "--limit": int})
            return gmail.pull(cfg, since=opts.get("--since"),
                              limit=opts.get("--limit"))
        raise SystemExit("usage: emailc gmail pull [--since DD-Mon-YYYY]")
    if cmd == "check":
        return check(cfg)
    raise SystemExit("unknown command %s\n%s" % (cmd, __doc__))


def _opts(args, spec):
    out = {}
    i = 0
    while i < len(args):
        if args[i] in spec:
            out[args[i]] = spec[args[i]](args[i + 1])
            i += 2
        else:
            raise SystemExit("bad argument %s" % args[i])
    return out


def check(cfg):
    import os
    print("config\t%s" % cfg.path)
    for key in ("archive", "normalized", "work"):
        p = cfg["paths"][key]
        print("paths.%s\t%s\t%s" % (key, p,
                                     "exists" if os.path.isdir(p) else "MISSING"))
    for src in cfg["paths"]["sources"]:
        print("source\t%s\t%s" % (src, "exists" if os.path.exists(
            os.path.expanduser(src)) else "MISSING"))
    s = cfg["server"]
    if s["host"]:
        from .importer import client
        try:
            cli = client(cfg)
            print("server\t%s:%s\tconnected as %s\tdelimiter=%r"
                  % (s["host"], s["port"], s["user"], cli.delim))
            cli.close()
        except Exception as e:
            print("server\t%s:%s\tFAILED\t%s" % (s["host"], s["port"], e))
    else:
        print("server\tnot configured (fine until stage 5)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
