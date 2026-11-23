"""A queued message Codex holds in its queue for days (v0.6.26, finding B1 of the third audit): a queue Codex paused -
usage_pause stopped the turn on the weekly window, or the person pressed Stop and has not resumed - keeps it there.
Its fate is known, so it is never told unproven: prompt_queue stays on, every other message the person queued keeps
its words, its row says it is queued in Codex, it is never sent a second time, and it is delivered once Codex lets the
queue go.

Held against core's own engine, store and simulated Codex home (takingcase.py), as test_advanced_prompt_queue is.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_advanced_prompt_queue import QueueCase  # noqa: E402
from codex_auto_resume_advanced import surfaces  # noqa: E402
from codex_auto_resume_advanced.registry import PROMPT_QUEUE  # noqa: E402
from codex_auto_resume_advanced.vocabulary import ArmingState, PromptReason, PromptState  # noqa: E402
from test_engine import T1  # noqa: E402

HOUR = 3600
FIRST, SECOND = "first one of mine, held", "second one of mine, later"


class HeldForDaysTests(QueueCase):
    def test_one_codex_holds_for_days_keeps_prompt_queue_on_and_every_other_message(self):
        """Fails with the unproven clock running while Codex holds it: a day on prompt_queue trips off, the second
        message is cancelled and its words deleted, and the first is done as unknown though it is still queued."""
        plug = self.on()
        self.h.backend.after_accept = "queue"                 # Codex keeps it: its queue is paused
        self.add(plug, words=FIRST)
        self.h.tick(advance=1)
        queued = self.h.home.queued(T1)
        self.assertEqual(len(queued), 1)
        first = self.prompts(plug)[0]["prompt_id"]
        second = self.add(plug, words=SECOND, trigger="at_time", at=self.h.now + 60 * HOUR)["prompt"]
        for _ in range(50):
            self.h.tick(advance=HOUR)
        self.assertEqual(plug.runtime.states(fresh=True).get(PROMPT_QUEUE.id), ArmingState.ARMED, "still on")
        row = plug.runtime.state.prompt(second)
        self.assertEqual((row["state"], row["words"]), (PromptState.WAITING, SECOND), "the other message is kept")
        row = plug.runtime.state.prompt(first)
        self.assertEqual(row["state"], PromptState.READY, "not done as unknown")
        self.assertEqual(self.h.home.queued(T1), queued, "still in Codex's queue, never deleted")
        listed = surfaces.bridge(plug.runtime, "advanced-prompts", {})
        shown = next(item for item in listed["prompts"] if item["prompt_id"] == first)
        self.assertTrue(shown["in_codex"], "its row says it is queued in Codex")
        self.assertEqual(len(self.sends()), 1, "never sent twice")
        self.h.home.dispatch(T1)                              # the queue goes on: Codex runs it
        self.h.tick(advance=5)
        row = plug.runtime.state.prompt(first)
        self.assertEqual((row["state"], row["reason"]), (PromptState.DONE, PromptReason.DELIVERED))
        self.assertEqual(len(self.sends()), 1)


if __name__ == "__main__":
    unittest.main()
