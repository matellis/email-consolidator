import io
import os
import shutil
import tempfile
import unittest

from emailc import dedupe, formats, inventory, normalize, counts, imap_client
from emailc.config import Config

MSG_A = b"From: a@x\r\nMessage-ID: <One@x>\r\nSubject: a\r\n\r\nbody a\r\n"
MSG_B = b"From: b@x\r\nMessage-Id: <two@x>\r\nSubject: b\r\n\r\nbody b\r\n"
MSG_NOID = b"From: c@x\r\nSubject: c\r\n\r\nbody c\r\n"


def emlx_bytes(msg):
    return b"%d\n" % len(msg) + msg + b"<?xml plist trailer?>\n"


class Formats(unittest.TestCase):
    def test_emlx_extract(self):
        msg, n = formats.emlx_extract(io.BytesIO(emlx_bytes(MSG_A)))
        self.assertEqual(msg, MSG_A)
        self.assertEqual(n, len(MSG_A))

    def test_emlx_truncated(self):
        with self.assertRaises(ValueError):
            formats.emlx_extract(io.BytesIO(b"999\nshort"))

    def test_emlx_empty(self):
        with self.assertRaises(ValueError):
            formats.emlx_extract(io.BytesIO(b""))

    def test_mbox(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "m.mbox")
        with open(p, "wb") as fh:
            fh.write(b"From a@x Mon Jan  1 00:00:00 2001\n" + MSG_A +
                     b"From b@x Mon Jan  1 00:00:00 2001\n" + MSG_B)
        msgs = list(formats.mbox_iter(p))
        self.assertEqual([i for i, _ in msgs], [1, 2])
        self.assertEqual(msgs[0][1], MSG_A)
        self.assertEqual(msgs[1][1], MSG_B)
        self.assertEqual(formats.mbox_count(p), 2)
        self.assertEqual(formats.mbox_read(p, 2), MSG_B)
        shutil.rmtree(d)

    def test_plausible(self):
        self.assertTrue(formats.plausible_message(MSG_A))
        self.assertTrue(formats.plausible_message(b"From x\n"))
        self.assertFalse(formats.plausible_message(b"\x89PNG"))

    def test_courier_parts(self):
        self.assertEqual(formats.courier_folder_parts(".Sent.2009"),
                         ["Sent", "2009"])
        self.assertEqual(formats.courier_folder_parts("INBOX"), ["INBOX"])


class Dedupe(unittest.TestCase):
    def test_message_id(self):
        self.assertEqual(dedupe.message_id(MSG_A), "one@x")
        self.assertEqual(dedupe.message_id(MSG_B), "two@x")
        self.assertEqual(dedupe.message_id(MSG_NOID), "")
        # a Message-ID line in the body must not count
        body = b"Subject: s\r\n\r\nMessage-ID: <fake@x>\r\n"
        self.assertEqual(dedupe.message_id(body), "")

    def test_group_and_keeper(self):
        rows = [
            ("old/a", "one@x", "s1", 10),
            ("new/a", "one@x", "s1", 20),
            ("old/b", "two@x", "s2", 10),
            ("old/b2", "two@x", "s2-edited", 10),
            ("x/c", "", "s3", 5),
            ("y/c", "", "s3", 6),
        ]
        groups, multi = dedupe.group(rows)
        self.assertEqual(multi, {"two@x"})
        self.assertEqual(len(groups[("one@x", "s1")]), 2)
        self.assertEqual(dedupe.pick_keeper(groups[("one@x", "s1")], ["new"]),
                         "new/a")
        self.assertEqual(dedupe.pick_keeper(groups[("one@x", "s1")], []),
                         "new/a")   # newest mtime
        self.assertEqual(dedupe.pick_keeper(groups[("", "s3")], ["old"]),
                         "y/c")


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.src = os.path.join(self.d, "src")
        self.norm = os.path.join(self.d, "norm")
        self.work = os.path.join(self.d, "work")
        mb = os.path.join(self.src, "applemail", "laptop", "Inbox.mbox", "Messages")
        os.makedirs(mb)
        for i, m in enumerate((MSG_A, MSG_B, MSG_A)):
            with open(os.path.join(mb, "%d.emlx" % i), "wb") as fh:
                fh.write(emlx_bytes(m))
        with open(os.path.join(mb, "._0.emlx"), "wb") as fh:
            fh.write(b"\x00\x05\x16\x07 appledouble")
        with open(os.path.join(mb, "bad.emlx"), "wb") as fh:
            fh.write(b"garbage")
        os.makedirs(os.path.join(self.src, "mbox"))
        with open(os.path.join(self.src, "mbox", "list.mbox"), "wb") as fh:
            fh.write(b"From a\n" + MSG_A + b"From c\n" + MSG_NOID)
        os.makedirs(self.work)
        self.cfg = Config({"paths": {"sources": [self.src], "archive": self.src,
                                     "normalized": self.norm, "work": self.work},
                           "dedupe": {"prefer": ["applemail"]}}, "test")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_inventory(self):
        rows = inventory.scan([self.src])
        kinds = sorted(k for k, *_ in rows)
        self.assertEqual(kinds, ["emlx", "emlx", "emlx", "emlx", "mbox"])

    def test_normalize_dedupe(self):
        normalize.run(self.cfg, "emlx", os.path.join(self.src, "applemail"),
                      "applemail")
        normalize.run(self.cfg, "mbox", os.path.join(self.src, "mbox"), "mbox")
        rows = counts.collect(self.norm)
        self.assertEqual(sorted(rows), [("applemail/laptop/Inbox.mbox", 3),
                                        ("mbox/list.mbox", 2)])
        with open(os.path.join(self.work, "normalize.log")) as fh:
            log = fh.read()
        self.assertIn("SKIP", log)
        self.assertIn("bad.emlx", log)
        dedupe.plan(self.cfg, samples=1)
        dedupe.apply(self.cfg)
        rows = dict(counts.collect(self.norm))
        # MSG_A existed 3 times (2 emlx + 1 mbox): one kept, under applemail
        self.assertEqual(rows["applemail/laptop/Inbox.mbox"], 2)
        self.assertEqual(rows["mbox/list.mbox"], 1)
        q = os.path.join(self.work, "quarantine")
        moved = sum(len(f) for _, _, f in os.walk(q))
        self.assertEqual(moved, 2)


class Imap(unittest.TestCase):
    def test_utf7(self):
        self.assertEqual(imap_client.utf7_encode("Sent"), "Sent")
        self.assertEqual(imap_client.utf7_encode("A&B"), "A&-B")
        self.assertEqual(imap_client.utf7_encode("Entwürfe"), "Entw&APw-rfe")

    def test_join(self):
        self.assertEqual(imap_client.join_folder("Archive", ".hidden/a/b"),
                         "Archive/_hidden/a/b")
        self.assertEqual(imap_client.join_folder("Archive", "x", "..", "/"),
                         "Archive/x/_")


if __name__ == "__main__":
    unittest.main()
