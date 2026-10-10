"""The prompt queue (v0.6.14-beta.2): a person's queued messages go after the current turn, at a time or on a schedule, in
order, each once, and their words go once each has ended; Cancel and Pause take back one Codex already holds.

Held against the shipped definition and statement and against core's own engine, store and simulated Codex home
(takingcase.py); the Dashboard's bridge adds them (surfaces.bridge), as the page does.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from takingcase import TakingCase  # noqa: E402
from codex_auto_resume import continuation  # noqa: E402
from codex_auto_resume_advanced import surfaces  # noqa: E402
from codex_auto_resume_advanced.registry import LONG_RESET_MESSAGE, PROMPT_QUEUE  # noqa: E402
from codex_auto_resume_advanced.vocabulary import PromptReason, PromptState, Refusal  # noqa: E402
from test_engine import T1  # noqa: E402

DAY = 86400
SENTINEL = "Sentinel-words-4c1e please look at the migration"


class QueueCase(TakingCase):
    DEFINITION = PROMPT_QUEUE
    BESIDE = (LONG_RESET_MESSAGE,)

    def arm(self, plug, state="armed", capability=None, **changes):
        definition = plug.runtime.registry.get(capability or self.cap)
        changes.setdefault("warnings", [str(word) for word in plug.runtime.arming.warnings(definition)])
        return super().arm(plug, state=state, capability=capability, **changes)

    def armed(self, h=None, state="armed", long=False):
        h = h or self.h
        plug = self.advanced(h)
        if long:
            self.arm(plug, capability=LONG_RESET_MESSAGE.id)
        self.arm(plug, state=state)
        self.plugged(plug, h)
        return plug

    def on(self, long=False):
        plug = self.armed(long=long)
        self.h.backend.loaded_map[T1] = "loaded"
        self.h.home.add_thread(T1)
        self.h.home.add_turn(T1, completed=int(self.h.now))
        return plug

    def add(self, plug, words=SENTINEL, trigger="after_turn", **argument):
        argument.update(thread_id=T1, words=words, trigger=trigger,
                        generation=plug.runtime.state.meta()["generation"])
        return surfaces.bridge(plug.runtime, "advanced-prompt-add", argument)

    def prompts(self, plug):
        return plug.runtime.state.prompts(pending=None)

    def sends(self):
        return [call[1] for call in self.h.backend.send_calls]


class TriggerTests(QueueCase):
    def test_after_this_turn_goes_at_once_exactly_as_written_and_its_words_go(self):
        plug = self.on()
        self.assertTrue(self.add(plug)["done"])
        self.h.tick(advance=1)
        self.assertEqual(len(self.sends()), 1)
        self.assertTrue(self.sends()[0].startswith(SENTINEL + "\n\n"), "as typed, the marker after a blank line")
        self.h.tick(advance=10)
        row = self.prompts(plug)[0]
        self.assertEqual((row["state"], row["reason"], row["words"]), (PromptState.DONE, PromptReason.DELIVERED, None))

    def test_at_a_time_it_waits_for_that_time(self):
        plug = self.on()
        self.add(plug, trigger="at_time", at=self.h.now + 3600)
        self.h.tick(advance=60)
        self.assertEqual(self.sends(), [])
        self.h.tick(advance=3600)
        self.assertEqual(len(self.sends()), 1)

    def test_a_daily_series_goes_each_day_and_ends_after_its_occurrences(self):
        """Fails with the recurrence reverted: a series would end after its first occurrence."""
        plug = self.on()
        self.add(plug, trigger="recurring", at=self.h.now + 60, every="day", occurrences=3)
        for _ in range(4):
            self.h.tick(advance=DAY)
            self.h.tick(advance=10)
        self.assertEqual(len(self.sends()), 3)
        row = self.prompts(plug)[0]
        self.assertEqual((row["state"], row["sent_count"], row["words"]), (PromptState.DONE, 3, None))

    def test_occurrences_missed_while_nothing_ran_are_caught_up_once(self):
        plug = self.on()
        self.add(plug, trigger="recurring", at=self.h.now + 60, every="day", occurrences=10)
        self.h.tick(advance=3 * DAY + 120)                 # three occurrences fell while nothing ran
        self.h.tick(advance=10)
        self.assertEqual(len(self.sends()), 1, "the latest alone")
        self.assertEqual(self.prompts(plug)[0]["sent_count"], 4, "the earlier three counted as used")


class OrderTests(QueueCase):
    def test_first_queued_first_sent_and_the_next_only_once_it_has_left_flight(self):
        plug = self.on()
        self.add(plug, words="first one of mine")
        self.add(plug, words="second one of mine")
        self.h.tick(advance=1)
        self.assertEqual([prompt.split("\n")[0] for prompt in self.sends()], ["first one of mine"])
        self.h.tick(advance=10)
        self.h.tick(advance=901)                          # fifteen minutes apart, as every recovery (A20 kept)
        self.assertEqual([prompt.split("\n")[0] for prompt in self.sends()], ["first one of mine",
                                                                               "second one of mine"])

    def test_one_that_depends_is_held_when_the_one_before_did_not_arrive(self):
        """Fails with `depends` reverted: the second would go though the first never did."""
        plug = self.on()
        self.add(plug, words="first one of mine", trigger="at_time", at=self.h.now + 7200)
        second = self.add(plug, words="second one of mine", depends=True)["prompt"]
        first = self.prompts(plug)[0]["prompt_id"]
        surfaces.bridge(plug.runtime, "advanced-prompt-cancel",
                        {"prompt": first, "generation": plug.runtime.state.meta()["generation"]})
        self.h.tick(advance=1)
        self.assertEqual(self.sends(), [])
        self.assertEqual((plug.runtime.state.prompt(second)["state"], plug.runtime.state.prompt(second)["reason"]),
                         (PromptState.HELD, PromptReason.DEPENDENCY_FAILED))
        self.assertTrue(surfaces.bridge(plug.runtime, "advanced-prompt-go-on",
                                        {"prompt": second, "generation": plug.runtime.state.meta()["generation"]})["done"])
        self.h.tick(advance=1)
        self.assertEqual(len(self.sends()), 1)


class WordsTests(QueueCase):
    def test_what_is_not_a_persons_own_message_is_refused(self):
        plug = self.on()
        template = continuation.build("usage_limit")
        for words in ("", "   ", template, "x [codex-auto-resume:0123456789abcdef]", "x" * 2001):
            with self.subTest(words=words[:20]):
                self.assertEqual(self.add(plug, words=words)["refusal"], Refusal.PROMPT_REFUSED)
        self.assertEqual(self.prompts(plug), [])

    def test_longer_messages_lets_it_be_longer(self):
        plug = self.on(long=True)
        self.assertTrue(self.add(plug, words="y" * 3000)["done"])

    def test_the_words_never_reach_the_journal_the_status_diagnostics_or_a_log(self):
        plug = self.on()
        self.add(plug)
        self.h.tick(advance=1)
        self.h.tick(advance=10)
        runtime = plug.runtime
        for where, what in (("journal", runtime.state.journal()), ("status", surfaces.status(runtime)),
                            ("diagnostics", surfaces.diagnostics(runtime)), ("core's log", self.h.logs),
                            ("core's events", self.h.store.events())):
            with self.subTest(where):
                self.assertNotIn("Sentinel-words-4c1e", json.dumps(what, default=str))

    def test_no_tool_of_a_model_reaches_it(self):
        self.assertFalse([tool["name"] for tool in surfaces.TOOLS if "prompt" in tool["name"]])


class TakeBackTests(QueueCase):
    def held_in_codex(self):
        plug = self.on()
        self.h.backend.after_accept = "queue"
        self.add(plug)
        self.h.tick(advance=1)
        self.assertEqual(len(self.h.home.queued(T1)), 1)
        return plug, self.prompts(plug)[0]["prompt_id"]

    def test_a_cancel_takes_one_codex_holds_back_out_of_its_queue(self):
        plug, prompt = self.held_in_codex()
        answer = surfaces.bridge(plug.runtime, "advanced-prompt-cancel",
                                 {"prompt": prompt, "generation": plug.runtime.state.meta()["generation"]})
        self.assertEqual(answer["cancelled"], "withdrawing")
        self.h.watch(advance=1)
        self.h.tick(advance=1)
        self.assertEqual(self.h.home.queued(T1), [], "taken back")
        row = plug.runtime.state.prompt(prompt)
        self.assertEqual((row["state"], row["reason"]), (PromptState.CANCELLED, PromptReason.WITHDRAWN))
        self.assertEqual(len(self.sends()), 1, "never sent twice")

    def test_a_pause_takes_it_back_and_holds_it_for_the_person(self):
        plug, prompt = self.held_in_codex()
        self.h.store.set_enabled(False, self.h.now)
        self.h.tick(advance=1)
        self.h.tick(advance=1)
        self.assertEqual(self.h.home.queued(T1), [])
        self.assertEqual(plug.runtime.state.prompt(prompt)["state"], PromptState.HELD)

    def test_go_on_after_a_pause_sends_the_persons_words_once_more(self):
        plug, prompt = self.held_in_codex()
        self.h.store.set_enabled(False, self.h.now)
        self.h.tick(advance=1)
        self.h.tick(advance=1)
        self.assertEqual(plug.runtime.state.prompt(prompt)["words"], SENTINEL, "kept while held for the person")
        self.h.store.set_enabled(True, self.h.now)
        self.h.backend.after_accept = "dispatch"
        answer = surfaces.bridge(plug.runtime, "advanced-prompt-go-on",
                                 {"prompt": prompt, "generation": plug.runtime.state.meta()["generation"]})
        self.assertTrue(answer["done"])
        for _ in range(3):
            self.h.tick(advance=1000)
        row = plug.runtime.state.prompt(prompt)
        self.assertNotEqual(row["reason"], PromptReason.TOO_LONG)
        self.assertEqual(len(self.sends()), 2, "sent again on Go on, once")
        self.assertTrue(self.sends()[1].startswith(SENTINEL + "\n\n"))
        self.assertEqual((row["state"], row["reason"], row["words"]), (PromptState.DONE, PromptReason.DELIVERED, None))


if __name__ == "__main__":
    unittest.main()
