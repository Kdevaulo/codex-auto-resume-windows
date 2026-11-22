"""v0.6.26 (audit-advanced2 R2, the owner's answer of 2026-11-22, "the reset message only"): with usage_pause and
reset_message both on, a conversation the forced stop stopped gets the person's reset message at the reset INSTEAD of
usage_pause's own continuation - as reset_message's statement promises ("in place of a continuation waiting there for the
same reset").

The continuation after the reset is started over the app's channel, not through core's records, so reset_message's P3
gate never held it, and a message sent into the paused queue starts no turn, so `after_reset` never saw newer work: both
went. Now `after_reset` ends its continuation superseded (journal pause.message_instead) where a reset message of that
conversation and window is due or in flight, was sent since the stop, or counts for this very reset.

Core's engine and a simulated Codex home, as test_advanced_usagestop; the rule is written into the edition's state as
reset_message writes one.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_usagestop_reset_message
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.registry import RESET_MESSAGE, USAGE_METER  # noqa: E402
from test_advanced_usagestop import StopCase  # noqa: E402
from test_engine import T1  # noqa: E402

RECORD = "b" * 64


class MessageInstead(StopCase):
    # Both on, as a person has them: reset_message off would end its own pending rules at the next sweep.
    BESIDE = (USAGE_METER, RESET_MESSAGE)

    def stopped(self):
        """T1 stopped near the limit, its continuation after the reset waiting, and the window reset."""
        plug, turn = self.running()
        self.h.tick(advance=61)
        self.h.tick(advance=61)
        (row,) = plug.runtime.state.continuations(capability=self.cap, pending=None)
        self.assertEqual(row["kind"], "after_reset")
        return plug, turn

    def rule(self, plug, ordinal=1, **changes):
        state = plug.runtime.state
        rule_id = state.add_reset_rule("reset_message", "codex", 300, ordinal, thread_id=T1, words="my own words",
                                       record_id=RECORD, at=self.h.now)
        if changes:
            self.assertTrue(state.change_rule(rule_id, **changes))
        return rule_id

    def window(self, plug):
        """The window as reset_message's watch counts it: no reset counted yet, the open one resetting at self.reset."""
        plug.runtime.state.save_windows([{"bucket": "codex", "minutes": 300, "open_reset_at": self.reset,
                                          "open_full": False, "last_closed_at": None, "resets": 0, "hits": 0,
                                          "seen_at": self.h.now, "misses": 0}])

    def outcome(self, plug):
        (row,) = plug.runtime.state.continuations(capability=self.cap, pending=None)
        return row["reason"]

    def test_a_message_due_at_this_reset_goes_instead(self):
        """Fails with R2 open: the continuation is started as well, and Codex gets both."""
        plug, turn = self.stopped()
        self.after_reset(plug, turn)
        self.rule(plug, state="ready", due_at=self.reset + 60)
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(self.starts, [])
        self.assertEqual(self.outcome(plug), "superseded")
        self.assertIn("pause.message_instead", self.journal(plug))

    def test_a_message_sent_since_the_stop_goes_instead(self):
        plug, turn = self.stopped()
        self.after_reset(plug, turn)
        self.rule(plug, state="done", reason="delivered", due_at=self.reset + 60, sent_at=self.reset + 70)
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(self.starts, [])
        self.assertEqual(self.outcome(plug), "superseded")

    def test_a_message_counting_for_this_reset_goes_instead(self):
        """Its reset not counted yet when the stop's look comes: the message's occasion is still this reset. A guard in
        this harness (it passes with R2 open: the simulated home starts a turn for the message core sends, which the
        app's paused queue would not)."""
        plug, turn = self.stopped()
        self.rule(plug, base=0)
        self.window(plug)
        self.after_reset(plug, turn)
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(self.starts, [])

    def test_a_message_for_a_later_reset_leaves_the_continuation(self):
        """A guard: a message for the third reset from now takes nothing of this one (passes with R2 open)."""
        plug, turn = self.stopped()
        self.rule(plug, ordinal=3, base=0)
        self.window(plug)
        self.after_reset(plug, turn)
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(len(self.starts), 1)
        self.assertIn("pause.continued", self.journal(plug))

    def test_a_message_that_fell_due_before_the_stop_leaves_the_continuation(self):
        plug, turn = self.stopped()
        self.rule(plug, state="done", reason="delivered", due_at=int(self.h.now) - 3600, sent_at=int(self.h.now) - 3500)
        self.after_reset(plug, turn)
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(len(self.starts), 1)


if __name__ == "__main__":
    unittest.main()
