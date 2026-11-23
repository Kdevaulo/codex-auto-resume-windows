"""A health check's lines in the watcher's log say whose they are (v0.6.26, the third audit's O4).

`doctor` and `status` build the engine as the watcher does, and what that logs ("engine ... is verified", "the ChatGPT
app was asked ...") went into auto-resume.log unmarked, so a reader took it for the watcher finding its engine again
(three groups with no watcher start were acceptance runs; after 12 of 21 setup restarts the log held two "engine ...
verified" lines in one second). Now each begins "(doctor, pid N) "; the watcher's own lines, and any other command's,
are as they were. Its own module.

Scratch home and Codex home only; nothing starts.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
import unittest

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import logbook  # noqa: E402
from codex_auto_resume.commands import base  # noqa: E402


class LogMarkTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.addCleanup(self._close)
        self.home = Path(self.folder.name) / "home"
        self.codex = Path(self.folder.name) / "codex"
        self.codex.mkdir()

    @staticmethod
    def _close():
        import logging
        logger = logging.getLogger(logbook.LOGGER_NAME)
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)

    def written_by(self, command):
        args = argparse.Namespace(command=command, home=str(self.home), codex_exe=None, codex_home=str(self.codex),
                                  quiet=True)
        app = base._app(args)
        app.logger.info("engine 1.2.3 is verified. Delivery is still proven")
        for handler in app.logger.handlers:
            handler.flush()
        return (self.home / "logs" / "auto-resume.log").read_text(encoding="utf-8").splitlines()[-1]

    def test_the_health_checks_mark_their_lines_with_their_name_and_pid(self):
        for command in ("doctor", "status"):
            with self.subTest(command):
                line = self.written_by(command)
                self.assertIn("] (%s, pid %d) engine 1.2.3 is verified" % (command, os.getpid()), line)

    def test_the_watcher_and_every_other_command_write_as_they_did(self):
        for command in ("run", "pending", "activate", None):
            with self.subTest(command):
                line = self.written_by(command)
                self.assertRegex(line, r"^\[[0-9: -]+\] engine 1\.2\.3 is verified")

    def test_a_percent_sign_in_a_mark_is_not_a_format_field(self):
        from codex_auto_resume import logbook as book
        log = Path(self.folder.name) / "x.log"
        logger = book.setup_logging(log, mark="(100% sure) ")
        logger.info("hello")
        for handler in logger.handlers:
            handler.flush()
        self.assertTrue(log.read_text(encoding="utf-8").rstrip().endswith("(100% sure) hello"))


if __name__ == "__main__":
    unittest.main()
