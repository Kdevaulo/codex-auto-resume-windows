"""audit4 B4: a carried start the app may not have received is not taken as sent and forgotten.

The stop's turn after the reset carries the person's reset message (usagestop._carry). Once launched, every answer but
the app's own "no" ended the continuation at once: a start written with no answer in time (UNCONFIRMED) or a pipe that
failed under the write (BROKEN) ended it superseded, the words gone, the paused queue left paused, nothing said - and a
chat message sent there afterwards was taken back as one the stop no longer held. Now the words still go (it may have
started: never sent twice), but the continuation waits one backoff: a newer turn then ends it; none, and the person is
asked to press Resume, as for a message in the paused queue, while it waits on.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_usagestop_carry_unconfirmed
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.codex import ipc  # noqa: E402
from codex_auto_resume_advanced.engine import chat as chat_engine  # noqa: E402
from codex_auto_resume_advanced.engine.usagestop import BACKOFF_SECONDS  # noqa: E402
from test_advanced_usagestop_carry import CarryCase  # noqa: E402
from test_engine import T1  # noqa: E402


class UnconfirmedCarry(CarryCase):
    def carried_unsure(self, answer):
        self.start_answer = answer
        plug, turn = self.stopped()
        self.after_reset(plug, turn)
        rule = self.rule(plug, state="ready", due_at=self.reset + 60)
        self.h.tick(advance=60)
        self.assertEqual(self.starts, self.carried(), "one start, the person's words")
        row = plug.runtime.state.reset_rule(rule)
        self.assertIsNone(row["words"], "its words gone: it may have started, and is never sent twice")
        return plug, rule

    def waits(self, plug):
        stops = plug.runtime.state.continuations(thread_id=T1, pending=None)
        self.assertEqual([stop["finished_at"] for stop in stops], [None], "the stop's continuation still waits")
        return stops

    def test_an_unanswered_carry_with_no_turn_asks_for_resume_and_waits(self):
        """Fails with the old end: superseded at once, nothing said, a chat sent there then taken back."""
        plug, _rule = self.carried_unsure(ipc.Stop.UNCONFIRMED)
        self.waits(plug)
        self.assertEqual(self.kinds(plug), [], "nothing said before the backoff")
        for _ in range(3):
            self.h.tick(advance=BACKOFF_SECONDS / 2 + 1)
        self.assertEqual(len(self.starts), 1, "never started again")
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(self.kinds(plug), ["press_resume"])
        self.assertIn("pause.resume_unproven", self.journal(plug))
        stops = self.waits(plug)
        self.assertTrue(chat_engine.paused_by_stop({"thread_id": T1, "sent_at": self.h.now}, stops),
                        "a chat sent now is left with Codex")
        self.h.home.add_turn(T1, status="completed", user_text="the person's own")   # they pressed Resume
        for _ in range(2):
            self.h.tick(advance=60)
        self.assertEqual(self.outcome(plug), "superseded")

    def test_a_carry_the_pipe_failed_under_is_said_the_same_way(self):
        plug, _rule = self.carried_unsure(ipc.Stop.BROKEN)
        self.waits(plug)
        for _ in range(3):
            self.h.tick(advance=BACKOFF_SECONDS / 2 + 1)
        self.assertEqual(self.kinds(plug), ["press_resume"])
        self.assertEqual(len(self.starts), 1)

    def test_an_unanswered_carry_whose_turn_shows_ends_quietly(self):
        """It did start, the answer lost: the turn shows, and the continuation ends superseded, nothing said."""
        plug, _rule = self.carried_unsure(ipc.Stop.UNCONFIRMED)
        self.h.home.add_turn(T1, status="completed", user_text=self.carried()[0][1])
        for _ in range(3):
            self.h.tick(advance=BACKOFF_SECONDS / 2 + 1)
        self.assertEqual(self.outcome(plug), "superseded")
        self.assertEqual(self.kinds(plug), [])
        self.assertEqual(len(self.starts), 1)
        self.assertIn("pause.message_instead", self.journal(plug))


if __name__ == "__main__":
    unittest.main()
