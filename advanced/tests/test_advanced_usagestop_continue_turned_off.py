"""review6 A2: Continue after the reset on at the stop and turned off before the reset - nothing goes, and the person is
asked to press Resume.

usage_pause's statement says that with Continue after the reset off "a notice asks you to press Resume in Codex". The stop
says it only where the choice is off at the stop; with the choice turned off afterwards nothing started at the reset and
nothing was said, so the queue the app paused stayed paused unsaid. Now the reset says it, once, and the stop is kept as
a hold with no words from then on (review6 A1's shape).

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_usagestop_continue_turned_off
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.vocabulary import Actor, OptionKey  # noqa: E402
from test_advanced_usagestop_carry import DAY  # noqa: E402
from test_advanced_usagestop_continue_off import ContinueOffCase  # noqa: E402


class TurnedOffAfterTheStop(ContinueOffCase):
    def test_the_reset_asks_for_resume_and_starts_nothing(self):
        """Fails with nothing said: no press_resume, no resume_unproven, the paused queue waiting unsaid."""
        plug, turn = self.running()
        self.h.tick(advance=61)
        self.h.tick(advance=61)
        self.assertEqual(self.kinds(plug), [], "the choice on at the stop: a continuation will come")
        assert plug.runtime.arming.set_option("usage_wrap_up", OptionKey.WRAP_AFTER_RESET, 2,
                                              generation=plug.runtime.state.meta()["generation"],
                                              actor=Actor.DASHBOARD)["done"]
        self.after_reset(plug, turn)
        self.h.tick(advance=60)
        self.assertEqual(self.kinds(plug), ["press_resume"])
        for _ in range(8):
            self.h.tick(advance=DAY / 4)
        self.assertEqual(self.starts, [])
        self.assertEqual(self.journal(plug).count("pause.resume_unproven"), 1, "said once")
        (row,) = plug.runtime.state.continuations(capability=self.cap, pending=None)
        self.assertIsNone(row["words"], "kept as a hold: no version starts it")


if __name__ == "__main__":
    unittest.main()
