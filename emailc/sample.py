"""Random-sample verification of emlx extraction.

Picks N random .emlx files, re-extracts them and checks:
  1. extracted byte count equals the length prefix
  2. the output starts like an RFC 822 message
Exit 0 only when every sampled file passes.
"""

import os
import random

from .formats import emlx_extract, plausible_message
from .util import is_carrier


def iter_emlx(roots):
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d != ".AppleDouble"]
            for f in files:
                if f.endswith(".emlx") and not is_carrier(f):
                    yield os.path.join(dirpath, f)


def run(n, roots, seed=1):
    files = list(iter_emlx(roots))
    random.seed(seed)
    sample = random.sample(files, min(n, len(files)))
    passed = failed = 0
    for path in sample:
        try:
            with open(path, "rb") as fh:
                msg, declared = emlx_extract(fh)
            if len(msg) != declared:
                raise ValueError("length mismatch %d != %d"
                                 % (len(msg), declared))
            if not plausible_message(msg):
                raise ValueError("implausible start: %r" % msg[:40])
            passed += 1
        except (OSError, ValueError) as e:
            print("FAIL\t%s\t%s" % (path, e))
            failed += 1
    print("SAMPLE\ttotal=%d\tpassed=%d\tfailed=%d"
          % (len(sample), passed, failed))
    return 0 if failed == 0 else 1
