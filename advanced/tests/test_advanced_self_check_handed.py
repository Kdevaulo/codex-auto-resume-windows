"""v0.6.26 (review of the third round, V6): the watcher's judge sees this edition's own waiting records.

A queued prompt, a reset message, a chat message or a continuation of this edition waits in its own state and is handed
to core each tick. The self-check's recovery rules read only core's waiting records, so with nothing of core's waiting
and a prompt waiting notLoaded, Codex changed and no word came. Now core keeps each handed record's wait of the tick and
the judge reads it beside its own (the standard lane's tests/test_self_check_handed.py holds the seam with a stand-in).
The review's repro: prompt_queue on, T1 not loaded, a message added, ticks.

Nothing reaches the real machine: the Restart Manager is a stub, and the homes are scratch ones.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_advanced_prompt_queue as prompt_queue  # noqa: E402  (a module, so its cases are not bound here)
from codex_auto_resume import machine  # noqa: E402
from test_engine import T1  # noqa: E402
from test_self_check_handed import judged  # noqa: E402


class HandedPromptTests(prompt_queue.QueueCase):
    def test_a_prompt_waiting_for_a_conversation_not_open_feeds_the_judge(self):
        plug = self.on()
        self.h.backend.loaded_map[T1] = "notLoaded"
        self.assertTrue(self.add(plug)["done"])
        for _ in range(3):
            self.h.tick(advance=1)
        self.assertEqual(self.sends(), [])
        self.assertEqual(self.h.store.records_in(machine.WAITING, home_key=""), [], "no record of core's waits")
        self.assertEqual(judged(self), "recovery_blocked:locks_unread")
        self.assertEqual(getattr(self.h.engine, "handed_waits", None), {T1: "notLoaded"})

    def test_a_prompt_that_went_says_nothing(self):
        plug = self.on()
        self.assertTrue(self.add(plug)["done"])
        self.h.tick(advance=1)
        self.assertEqual(len(self.sends()), 1)
        self.assertIsNone(judged(self))


if __name__ == "__main__":
    unittest.main()
