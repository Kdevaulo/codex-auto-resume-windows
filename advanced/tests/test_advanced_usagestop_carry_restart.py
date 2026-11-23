"""review4 V3: audit4 B4's wait for an unconfirmed carried start survives a watcher restart.

B4 kept "this carried start may not have arrived" in the process's memory only. A watcher restarted inside the backoff
read the in-flight message as sent, ended the stop's continuation superseded and said nothing - B4's own bug again. Now
the doubt is kept in the state (the continuation's `launching_at`), so the restarted watcher waits the backoff out, asks
for Resume if no turn came, and never starts the message again.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_usagestop_carry_restart
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.codex import ipc  # noqa: E402
from codex_auto_resume_advanced.engine.usagestop import BACKOFF_SECONDS  # noqa: E402
import test_advanced_usagestop_carry_unconfirmed as unconfirmed  # noqa: E402  (a module: its cases not bound here)
from test_engine import T1  # noqa: E402


class RestartInsideTheBackoff(unconfirmed.UnconfirmedCarry):
    # UnconfirmedCarry's helpers; its own tests are not run twice here.
    test_an_unanswered_carry_with_no_turn_asks_for_resume_and_waits = None
    test_a_carry_the_pipe_failed_under_is_said_the_same_way = None
    test_an_unanswered_carry_whose_turn_shows_ends_quietly = None

    def test_a_restart_inside_the_backoff_still_asks_for_resume(self):
        """Fails with the doubt in memory alone: after the restart the continuation ends superseded, nothing said."""
        plug, _rule = self.carried_unsure(ipc.Stop.UNCONFIRMED)
        self.h.tick(advance=60)
        plug = self.restarted()
        for _ in range(4):
            self.h.tick(advance=BACKOFF_SECONDS / 2 + 1)
        self.waits(plug)
        self.assertEqual(self.kinds(plug), ["press_resume"])
        self.assertEqual(len(self.starts), 1, "never started again")
        self.assertEqual(self.h.backend.send_calls, [])
        self.h.home.add_turn(T1, status="completed", user_text="the person's own")     # they pressed Resume
        for _ in range(2):
            self.h.tick(advance=60)
        self.assertEqual(self.outcome(plug), "superseded")


if __name__ == "__main__":
    unittest.main()
