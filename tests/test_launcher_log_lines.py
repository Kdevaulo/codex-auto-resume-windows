"""A supervised start writes "launcher started" once, and launcher.log reaches back further (v0.6.26, the third audit's
O5).

Every supervised start wrote "launcher started (pid N)" for the supervisor and again for its child, whose pid the line
before had just named ("watcher started as a supervised child (pid N)"); at five lines a start, the 50 the log kept
reached back two days. The child writes no such line now, and the log keeps 200 lines. Its own module (the supervisor's
fakes are test_launcher_supervisor's).

    PYTHONPATH="src;tests" python -m unittest test_launcher_log_lines
"""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT / "src"), str(ROOT / "tests")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from test_launcher_supervisor import SupervisorCase  # noqa: E402


class LauncherLogTests(SupervisorCase):
    def written(self, name):
        path = self.home / "logs" / name
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def test_a_supervised_start_says_launcher_started_once(self):
        plug = self.answering()
        self.launch([], plug, codes=[0])                                    # the supervisor
        self.launch(["run", self.launcher.CHILD_ARGUMENT], NULL_PLUG(), watcher_code=0)   # its child, run here
        text = self.written("launcher.log")
        self.assertEqual(text.count("launcher started"), 1, text)
        self.assertEqual(text.count("watcher started as a supervised child"), 1, text)

    def test_the_log_keeps_two_hundred_lines(self):
        self.assertGreaterEqual(self.launcher.LAUNCH_LOG_LINES, 200)
        for number in range(self.launcher.LAUNCH_LOG_LINES + 30):
            self.launcher._note(self.home, "line %d" % number)
        lines = self.written("launcher.log").splitlines()
        self.assertTrue(lines[-1].endswith("line %d" % (self.launcher.LAUNCH_LOG_LINES + 29)))
        self.assertGreaterEqual(len(lines), 200)
        self.assertLessEqual(len(lines), self.launcher.LAUNCH_LOG_LINES + 1)


def NULL_PLUG():
    from codex_auto_resume.domain.plug import NULL
    return NULL


if __name__ == "__main__":
    unittest.main()
