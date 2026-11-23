"""review4 V4 (= matrix5 M2), the owner's answer of 2026-11-23: with Continue after the reset off, a stopped conversation
that has a reset message still gets one turn after the reset - the stop's own, carrying the message - and core never
queues the message into the paused queue. Without a message nothing goes, as before.

The stop kept no continuation with Continue after the reset off, so reset_message had no stop's turn to leave the message
to, and core queued it into the queue the stop paused, where it sat until the person pressed Resume. Now the stop keeps
its turn either way; with the choice off the turn starts only to carry a message - one due at the reset, or (the
coordinator's call, after the owner's answer) one falling due later while the paused queue still holds because no turn
went - and the person's Resume ends it.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_usagestop_continue_off
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.registry import RESET_MESSAGE, USAGE_METER, USAGE_WRAP_UP  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Actor, OptionKey  # noqa: E402
from test_advanced_usagestop_carry import DAY, CarryCase  # noqa: E402
from test_engine import T1  # noqa: E402

HOUR = 3600


class ContinueOffCase(CarryCase):
    BESIDE = (USAGE_METER, RESET_MESSAGE, USAGE_WRAP_UP)

    def stopped_off(self):
        plug, turn = self.running()
        assert plug.runtime.arming.set_option("usage_wrap_up", OptionKey.WRAP_AFTER_RESET, 2,
                                              generation=plug.runtime.state.meta()["generation"],
                                              actor=Actor.DASHBOARD)["done"]
        self.h.tick(advance=61)
        self.h.tick(advance=61)
        self.assertEqual(len(self.stops), 1)
        self.assertEqual(self.kinds(plug), ["press_resume"], "nothing of the product's own will let the queue go")
        return plug, turn


class ContinueOffTests(ContinueOffCase):
    def test_a_message_due_at_the_reset_is_carried_by_the_stops_turn(self):
        """Fails with no turn kept: core queues the message into the paused queue (send_calls 1), nothing starts."""
        plug, turn = self.stopped_off()
        self.after_reset(plug, turn)
        rule = self.rule(plug, state="ready", due_at=self.reset + 60)
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertEqual(self.starts, self.carried(), "one start, the person's words and their message's marker")
        self.assertEqual(self.h.backend.send_calls, [], "nothing into the queue the stop paused")
        self.assertEqual(self.h.home.queued(T1), [])
        self.assertEqual(self.rule_row(plug, rule), ("done", "delivered"))
        self.assertNotIn("pause.continued", self.journal(plug))

    def test_a_message_due_after_the_reset_is_carried_at_its_due_time(self):
        """No turn went at the reset, so the paused queue still holds: a message falling due hours later is carried
        then by the stop's turn, never queued by core. Fails with no turn kept: core queues it."""
        plug, turn = self.stopped_off()
        self.after_reset(plug, turn)
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertEqual(self.starts, [], "no message yet: nothing goes")
        self.h.tick(advance=2 * HOUR)
        rule = self.rule(plug, state="ready", due_at=int(self.h.now))
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertEqual(self.starts, self.carried())
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(self.rule_row(plug, rule), ("done", "delivered"))

    def test_without_a_message_nothing_goes(self):
        plug, turn = self.stopped_off()
        self.after_reset(plug, turn)
        for _ in range(4):
            self.h.tick(advance=DAY / 4)
        self.assertEqual(self.starts, [])
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertNotIn("pause.continued", self.journal(plug))

    def test_the_persons_resume_ends_it(self):
        plug, turn = self.stopped_off()
        self.after_reset(plug, turn)
        self.h.tick(advance=60)
        self.h.home.add_turn(T1, status="completed", user_text="the person's own")     # they pressed Resume
        for _ in range(2):
            self.h.tick(advance=60)
        self.assertEqual(self.outcome(plug), "superseded")
        self.assertEqual(self.starts, [])


if __name__ == "__main__":
    unittest.main()
