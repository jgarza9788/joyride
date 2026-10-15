import importlib.machinery
import importlib.util
import os
import stat
import sys
import tempfile
import time
import unittest

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin")
sys.path.insert(0, BIN)
_loader = importlib.machinery.SourceFileLoader("joyride_input", os.path.join(BIN, "joyride-input"))
ji = importlib.util.module_from_spec(importlib.util.spec_from_loader("joyride_input", _loader))
_loader.exec_module(ji)


class TypeText(unittest.TestCase):
    def run_type(self, text):
        with tempfile.TemporaryDirectory() as d:
            stub = os.path.join(d, "wtype")
            with open(stub, "w") as f:
                f.write('#!/bin/sh\necho "$@" > "%s/args"\ncat > "%s/in"\n' % (d, d))
            os.chmod(stub, os.stat(stub).st_mode | stat.S_IXUSR)
            old = os.environ["PATH"]
            os.environ["PATH"] = d + os.pathsep + old
            try:
                dm = object.__new__(ji.Daemon)
                dm.typers = []
                dm.type_text(text)
                for p in dm.typers:
                    p.wait(timeout=5)
            finally:
                os.environ["PATH"] = old
            args = os.path.join(d, "args")
            if not os.path.exists(args):
                return None, None
            return open(args).read().strip(), open(os.path.join(d, "in"), encoding="utf-8").read()

    def test_text_goes_over_stdin_not_argv(self):
        argv, stdin = self.run_type("s3cret")
        self.assertEqual(argv, "-")
        self.assertEqual(stdin, "s3cret")

    def test_non_ascii(self):
        self.assertEqual(self.run_type("é")[1], "é")

    def test_empty_or_bad_input_spawns_nothing(self):
        self.assertEqual(self.run_type(""), (None, None))
        self.assertEqual(self.run_type(None), (None, None))


if __name__ == "__main__":
    unittest.main()
