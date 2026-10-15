"""The edition's turn reader on a conversation Codex split (v0.6.16-beta.3, issue #30): read as core reads it.

Keep going and the empty-response recovery read a conversation's latest turn through codex/turns.py. Before this,
on a conversation whose turns Codex records under another id (B), it read A's own old turn: keep going went on
after the person had stopped the turn under B. Now it follows core's own `turn_chain`, and a later id's turn comes
after every earlier id's whatever Codex numbered it - also where B's ordinals start again (`Restarted`).

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_advanced_keep_going import KeepCase  # noqa: E402
from test_continuation_split import Restarted, SplitHome  # noqa: E402
from test_engine import T1, Harness  # noqa: E402
from codex_auto_resume.codex.rollout import SPAN  # noqa: E402
from codex_auto_resume_advanced.codex.turns import Turns  # noqa: E402


class SplitKeepCase(KeepCase):
    HOME = SplitHome

    def fresh(self, *, enable=True, **kwargs):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        kwargs.setdefault("home", self.HOME(Path(temp.name) / "codex-home"))
        h = Harness(Path(temp.name) / "state", options=kwargs.pop("options", self.options), **kwargs)
        self.addCleanup(h.close)
        if enable:
            h.enable()
        return h

    def test_keep_going_stops_when_the_person_stops_the_turn_under_b(self):
        plug = self.on()
        self.h.home.add_turn(T1, status="completed", completed=int(self.h.now) - 400)   # A's own, before the split
        self.h.home.rotate(T1)
        stopped = self.h.home.add_turn(T1, status="interrupted", progress=False, completed=int(self.h.now))
        latest = Turns(self.h.home.root).latest(T1)
        self.assertEqual((latest.turn_id, latest.status), (stopped, "interrupted"))
        self.assertGreater(latest.ordinal, SPAN)
        self.look(times=4)
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertNotEqual(self.row(plug)["used"], 1)

    def test_a_turn_under_b_names_its_conversation_and_counts_across_the_split(self):
        self.h.home.add_thread(T1)
        self.h.home.add_turn(T1, status="completed", completed=int(self.h.now) - 300)      # A's own, at ordinal 5
        self.h.home.rotate(T1)
        self.h.home.add_turn(T1, status="completed", completed=int(self.h.now) - 200)
        last = self.h.home.add_turn(T1, status="completed", completed=int(self.h.now) - 100)
        turns = Turns(self.h.home.root)
        self.assertEqual(turns.recent(int(self.h.now) - 1000), [T1])
        self.assertEqual(turns.between(T1, 5, turns.latest(T1).ordinal), 1, "B's first turn lies between")
        self.assertEqual(turns.latest(T1).turn_id, last)


class RestartedKeepCase(SplitKeepCase):
    HOME = Restarted


del KeepCase

if __name__ == "__main__":
    unittest.main()
