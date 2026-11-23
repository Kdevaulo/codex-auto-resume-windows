"""review6 A4: an unconfirmed carried start, kept for a restart (review4 V3), is nothing an older version starts.

The doubt left the stop's continuation waiting WITH the catalog's words. v0.6.25 reads no doubt and starts any waiting
row with words, so going back inside the backoff sent the product's continuation as a second turn beside the person's
message. The doubt now takes the words away; v0.6.25 and v0.6.26-beta, read from their tags, start nothing from it, and
this version still waits the backoff out and asks for Resume.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_usagestop_doubt_legacy
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.codex import ipc  # noqa: E402
from codex_auto_resume_advanced.engine.usagestop import UsageStop  # noqa: E402
import test_advanced_usagestop_carry_unconfirmed as unconfirmed  # noqa: E402  (a module: its cases not bound here)
import test_advanced_usagestop_legacy_hold as hold  # noqa: E402  (a module: its cases not bound here)


class DoubtAfterADowngrade(unconfirmed.UnconfirmedCarry):
    test_an_unanswered_carry_with_no_turn_asks_for_resume_and_waits = None
    test_a_carry_the_pipe_failed_under_is_said_the_same_way = None
    test_an_unanswered_carry_whose_turn_shows_ends_quietly = None

    def test_the_doubted_row_has_no_words(self):
        plug, _rule = self.carried_unsure(ipc.Stop.UNCONFIRMED)
        (row,) = plug.runtime.state.continuations(capability=self.cap, pending=None)
        self.assertIsNotNone(row["launching_at"])
        self.assertIsNone(row["words"])

    def test_v0_6_25_starts_nothing_beside_the_message(self):
        """Fails with the words kept: v0.6.25 starts the product's continuation as a second turn."""
        hold._need_tags(self)
        plug, _rule = self.carried_unsure(ipc.Stop.UNCONFIRMED)
        self.start_answer = ipc.Start.STARTED
        old = hold.legacy("v0.6.25")
        methods = {name: value for name, value in vars(old.UsageStop).items()
                   if callable(value) and not name.startswith("__")}
        with patch.multiple(UsageStop, **methods):
            plug = self.restarted()
            for _ in range(4):
                self.h.tick(advance=151)
        self.assertEqual(len(self.starts), 1, "the person's message only")


if __name__ == "__main__":
    unittest.main()
