"""A person's Go on gives a held queued message a day of its own from the press (v0.6.26, finding R1 of the third
audit). A Pause takes back a message Codex held and holds it for the person; one whose earlier message did not arrive is
held too. Pressed a day or more after it fell due, Go on used to make its occurrence at that old due time, so the first
tick that could not send it - the conversation not open in the app, usage unknown, quiet hours - expired it unsent and
deleted its words. Now it waits a day from the press like any occurrence, and a series keeps its slot.

Held against core's own engine, store and simulated Codex home (takingcase.py), as test_advanced_prompt_queue is.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_advanced_prompt_queue import SENTINEL, QueueCase  # noqa: E402
from codex_auto_resume_advanced import surfaces  # noqa: E402
from codex_auto_resume_advanced.vocabulary import PromptReason, PromptState  # noqa: E402
from test_engine import T1  # noqa: E402

DAY = 86400


class GoOnWindowTests(QueueCase):
    def go_on(self, plug, prompt):
        answer = surfaces.bridge(plug.runtime, "advanced-prompt-go-on",
                                 {"prompt": prompt, "generation": plug.runtime.state.meta()["generation"]})
        self.assertTrue(answer["done"])

    def held_at_a_pause(self, **argument):
        """A message Codex held, taken back by a Pause and held for the person: (plug, its prompt id)."""
        plug = self.on()
        self.h.backend.after_accept = "queue"
        self.add(plug, **argument)
        for _ in range(3):
            self.h.tick(advance=5)
        self.assertEqual(len(self.h.home.queued(T1)), 1)
        prompt = self.prompts(plug)[0]["prompt_id"]
        self.h.store.set_enabled(False, self.h.now)
        self.h.tick(advance=1)
        self.h.tick(advance=1)
        self.assertEqual(self.h.home.queued(T1), [], "taken back")
        self.assertEqual(plug.runtime.state.prompt(prompt)["state"], PromptState.HELD)
        self.h.store.set_enabled(True, self.h.now)
        self.h.backend.after_accept = "dispatch"
        return plug, prompt

    def not_open_then_open(self, ticks=3):
        """The first ticks after the press cannot send it - the app does not hold the conversation - then it can."""
        self.h.backend.loaded_map[T1] = "notLoaded"
        for _ in range(ticks):
            self.h.tick(advance=60)
        self.h.backend.loaded_map[T1] = "loaded"
        for _ in range(3):
            self.h.tick(advance=1000)

    def test_go_on_two_days_after_a_pause_is_sent_though_the_first_ticks_cannot_send_it(self):
        """Fails with Go on keeping the old due time: the second tick expires it unsent, its words deleted."""
        plug, prompt = self.held_at_a_pause()
        self.h.tick(advance=2 * DAY)
        self.go_on(plug, prompt)
        self.not_open_then_open()
        row = plug.runtime.state.prompt(prompt)
        self.assertNotEqual(row["reason"], PromptReason.EXPIRED)
        self.assertEqual(len(self.sends()), 2, "sent again on Go on, once")
        self.assertTrue(self.sends()[1].startswith(SENTINEL + "\n\n"))
        self.assertEqual((row["state"], row["reason"], row["words"]), (PromptState.DONE, PromptReason.DELIVERED, None))

    def test_its_day_counts_from_the_press_and_then_it_still_expires(self):
        plug, prompt = self.held_at_a_pause()
        self.h.tick(advance=2 * DAY)
        self.go_on(plug, prompt)
        self.h.backend.loaded_map[T1] = "notLoaded"
        self.h.tick(advance=60)
        self.h.tick(advance=DAY - 600)
        row = plug.runtime.state.prompt(prompt)
        self.assertEqual((row["state"], row["words"]), (PromptState.READY, SENTINEL), "still within its day")
        self.h.tick(advance=1200)
        row = plug.runtime.state.prompt(prompt)
        self.assertEqual((row["state"], row["reason"]), (PromptState.DONE, PromptReason.EXPIRED),
                         "a day from the press, never sent, it expires as every occurrence does")
        self.assertEqual(len(self.sends()), 1)

    def test_a_weekly_series_goes_on_and_keeps_its_slot(self):
        plug, prompt = self.held_at_a_pause(trigger="recurring", at=self.h.now + 5, every="week", occurrences=3)
        slot = plug.runtime.state.prompt(prompt)["due_at"]
        self.h.tick(advance=3 * DAY)
        self.go_on(plug, prompt)
        self.assertEqual(plug.runtime.state.prompt(prompt)["due_at"], slot, "its slot kept")
        self.not_open_then_open()
        row = plug.runtime.state.prompt(prompt)
        self.assertEqual(len(self.sends()), 2, "the held occurrence sent on Go on")
        self.assertEqual((row["state"], row["sent_count"], row["due_at"]), (PromptState.WAITING, 1, slot + 7 * DAY))

    def test_one_held_because_the_one_before_did_not_arrive_goes_on_days_later(self):
        plug = self.on()
        self.add(plug, words="first one of mine", trigger="at_time", at=self.h.now + 7200)
        second = self.add(plug, words="second one of mine", trigger="at_time", at=self.h.now + 3600,
                          depends=True)["prompt"]
        first = self.prompts(plug)[0]["prompt_id"]
        surfaces.bridge(plug.runtime, "advanced-prompt-cancel",
                        {"prompt": first, "generation": plug.runtime.state.meta()["generation"]})
        self.h.tick(advance=1)
        self.assertEqual(plug.runtime.state.prompt(second)["reason"], PromptReason.DEPENDENCY_FAILED)
        self.h.tick(advance=3 * DAY)
        self.go_on(plug, second)
        self.not_open_then_open()
        row = plug.runtime.state.prompt(second)
        self.assertEqual((row["state"], row["reason"]), (PromptState.DONE, PromptReason.DELIVERED))
        self.assertEqual(len(self.sends()), 1)

    def test_one_not_yet_due_waits_for_its_time_as_before(self):
        plug = self.on()
        self.add(plug, words="first one of mine", trigger="at_time", at=self.h.now + 7200)
        second = self.add(plug, words="second one of mine", trigger="at_time", at=self.h.now + 5 * DAY,
                          depends=True)["prompt"]
        first = self.prompts(plug)[0]["prompt_id"]
        surfaces.bridge(plug.runtime, "advanced-prompt-cancel",
                        {"prompt": first, "generation": plug.runtime.state.meta()["generation"]})
        self.h.tick(advance=1)
        self.go_on(plug, second)
        row = plug.runtime.state.prompt(second)
        self.assertEqual((row["state"], row["record_id"]), (PromptState.WAITING, None))
        self.h.tick(advance=DAY)
        self.assertEqual(self.sends(), [], "not before its time")


if __name__ == "__main__":
    unittest.main()
