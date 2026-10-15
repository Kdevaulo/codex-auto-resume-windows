# ADVANCED-EDITION-CODE: in the advanced edition's tree, never the standard one's.
"""v0.6.16-beta.3: a watched capability that needs rows to watch can be set up (the owner, 2026-10-11).

A message at a reset, a reset credit, Keep a conversation going and Queue messages for later each act only on what a
person set up for them - a rule, a conversation kept going, a queued message - and that could be done only while the
capability was on, so watching one had nothing to watch. Now: the bridge commands that add their rows take them while
the capability is watched as well; watched, its rows are evaluated and what it would have done is written to the watch
log, with when - never a send, never a credit spent or usage read for it; turning a watched one on keeps its rows, and
turning it off ends them as before. The standards still hold: watched means asked, journalled and never acting (K-rules).

Core's engine, store and simulated Codex (takingcase), the advanced plug with the shipped definitions.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from takingcase import TakingCase  # noqa: E402
from test_advanced_reset_message import RESET, MessageCase  # noqa: E402
from codex_auto_resume_advanced.engine.resetwatch import CLOSE_AFTER  # noqa: E402
from codex_auto_resume_advanced import surfaces, watchlog  # noqa: E402
from codex_auto_resume_advanced.registry import KEEP_GOING, LONG_RESET_MESSAGE, PROMPT_QUEUE, RESET_CREDIT, RESET_MESSAGE  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Actor, ArmingState, JournalCode, PromptState  # noqa: E402
from test_engine import T1  # noqa: E402

WORDS = "Watched-words-7f2a: carry on with the tests."


class WatchedCase(TakingCase):
    BESIDE = (LONG_RESET_MESSAGE,)

    def arm(self, plug, state="armed", capability=None, **changes):
        definition = plug.runtime.registry.get(capability or self.cap)
        changes.setdefault("warnings", [str(word) for word in plug.runtime.arming.warnings(definition)])
        return super().arm(plug, state=state, capability=capability, **changes)

    def watching(self):
        plug = self.armed(state=ArmingState.SHADOW)
        self.h.backend.loaded_map[T1] = "loaded"
        self.h.home.add_thread(T1)
        self.h.home.add_turn(T1, completed=int(self.h.now))
        return plug

    def bridge(self, plug, command, **argument):
        argument.setdefault("generation", plug.runtime.state.meta()["generation"])
        return surfaces.bridge(plug.runtime, command, argument)

    def watched_lines(self, plug):
        return [(line["point"], line["answer"]) for line in plug.runtime.state.journal(capability=self.cap)
                if line["code"] == JournalCode.WOULD_HAVE]

    def off(self):
        plug = self.advanced()
        self.plugged(plug)
        return plug


class QueueWatchedTests(WatchedCase):
    DEFINITION = PROMPT_QUEUE

    def add(self, plug, **argument):
        return self.bridge(plug, "advanced-prompt-add", thread_id=T1, words=WORDS, trigger="after_turn", **argument)

    def test_a_message_is_queued_while_watched_and_refused_while_off(self):
        self.assertEqual(self.add(self.off()).get("refusal"), "not_on")
        plug = self.watching()
        self.assertTrue(self.add(plug)["done"])
        self.assertEqual([row["words"] for row in plug.runtime.state.prompts(pending=None)], [WORDS])

    def test_watched_it_is_journalled_with_its_time_and_never_sent(self):
        plug = self.watching()
        self.add(plug)
        for _ in range(4):
            self.h.tick(advance=60)
        self.assertEqual(self.h.backend.send_calls, [], "never a send")
        self.assertIn(("records", "records"), self.watched_lines(plug))
        (row,) = plug.runtime.state.prompts(pending=None)
        self.assertEqual((row["state"], row["words"], row["record_id"]), (PromptState.WAITING, WORDS, None),
                         "nothing about the row moved")
        shown = watchlog.view(plug.runtime, self.cap)
        entry = next(entry for entry in shown["entries"] if entry["answer"] == "records")
        self.assertEqual(entry["count"], 1, "once for the one message")
        self.assertIsNotNone(entry["last"])

    def test_turned_on_it_keeps_the_rows_and_sends_once(self):
        plug = self.watching()
        self.add(plug)
        self.h.tick(advance=60)
        self.arm(plug, state=ArmingState.ARMED)
        self.h.tick(advance=60)
        self.assertEqual(len(self.h.backend.send_calls), 1)
        self.assertTrue(self.h.backend.send_calls[0][1].startswith(WORDS + "\n\n"))

    def test_turned_off_its_rows_end_as_before(self):
        plug = self.watching()
        self.add(plug)
        self.assertTrue(plug.runtime.arming.disarm(self.cap, actor=Actor.DASHBOARD)["done"])
        (row,) = plug.runtime.state.prompts(pending=None)
        self.assertNotIn(row["state"], (PromptState.WAITING, PromptState.READY))
        self.assertIsNone(row["words"])


class ResetMessageWatchedTests(WatchedCase):
    DEFINITION = RESET_MESSAGE

    def test_a_message_at_a_reset_is_added_while_watched_and_journalled_never_sent(self):
        add = dict(kind="message", bucket="codex", minutes=300, ordinal=1, thread_id=T1, words=WORDS)
        self.assertEqual(self.bridge(self.off(), "advanced-reset-add", **add).get("refusal"), "not_on")
        plug = self.watching()
        added = self.bridge(plug, "advanced-reset-add", **add)
        self.assertTrue(added["done"], added)
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertIn(("tick", "tick"), self.watched_lines(plug), "its look is journalled, never made")
        self.arm(plug, state=ArmingState.ARMED)
        self.assertIsNotNone(plug.runtime.state.reset_rule(added["rule"])["words"], "turned on, the rule is kept")


class ResetMessageDueWatchedTests(MessageCase):
    """A message at a reset adopted while on, then watched: when its reset comes by the stored windows it is journalled
    once as a message it would have sent - never sent, and no usage read for it."""

    def test_its_reset_comes_and_it_is_journalled_once_as_records(self):
        plug = self.armed()
        rule, _key = self.message(plug)
        self.h.tick()                                    # adopted while on, the windows stored
        self.arm(plug, state=ArmingState.SHADOW, warnings=list(plug.runtime.arming.warnings(self.DEFINITION)))
        reads = len(self.codex.calls)
        self.h.now = RESET + CLOSE_AFTER
        for _ in range(3):
            self.h.tick(advance=60)
        rows = [(line["point"], line["answer"]) for line in plug.runtime.state.journal(capability=self.cap)
                if line["code"] == JournalCode.WOULD_HAVE]
        self.assertEqual(rows.count(("records", "records")), 1, "once, as a message of yours it would have sent")
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(len(self.codex.calls), reads, "no usage read while watched")
        self.assertIsNotNone(self.found(plug, rule)["words"])


class CreditWatchedTests(WatchedCase):
    DEFINITION = RESET_CREDIT

    def test_a_credit_rule_is_added_while_watched_and_nothing_is_spent_or_read(self):
        add = dict(kind="credit", bucket="codex", minutes=300, ordinal=1)
        plug = self.watching()
        self.assertTrue(self.bridge(plug, "advanced-reset-add", **add)["done"])
        self.assertEqual(self.bridge(plug, "advanced-credit-now", bucket="codex", minutes=300).get("refusal"), "not_on",
                         "using a credit now is for one that is on alone")
        for _ in range(3):
            self.h.tick(advance=900)
        self.assertEqual(self.spends(plug), [])
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertIn(("tick", "tick"), self.watched_lines(plug))
        self.assertIsNone(plug.runtime.state.reading().get("credits"), "no credit count is kept")


class KeepGoingWatchedTests(WatchedCase):
    DEFINITION = KEEP_GOING

    def test_a_conversation_is_kept_going_while_watched_and_nothing_is_sent(self):
        self.assertEqual(self.bridge(self.off(), "advanced-keep-going-set", thread_id=T1, count=3).get("refusal"),
                         "not_on")
        plug = self.watching()
        picked = self.bridge(plug, "advanced-keep-going-set", thread_id=T1, count=3)
        self.assertTrue(picked["done"], picked)
        self.h.home.add_turn(T1, status="completed", progress=True, completed=int(self.h.now))
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertIn(("tick", "tick"), self.watched_lines(plug))
        self.arm(plug, state=ArmingState.ARMED)
        self.assertEqual(plug.runtime.state.keep_going(T1)["state"], "on", "turned on, the conversation is kept")

    def test_on_to_watched_keeps_the_conversation_and_watched_to_off_ends_it(self):
        plug = self.armed()
        self.h.backend.loaded_map[T1] = "loaded"
        self.h.home.add_thread(T1)
        self.assertTrue(self.bridge(plug, "advanced-keep-going-set", thread_id=T1, count=3)["done"])
        self.arm(plug, state=ArmingState.SHADOW)
        self.assertEqual(plug.runtime.state.keep_going(T1)["state"], "on", "watched, what the person picked stays")
        self.assertTrue(plug.runtime.arming.disarm(self.cap, actor=Actor.DASHBOARD)["done"])
        self.assertNotEqual(plug.runtime.state.keep_going(T1)["state"], "on", "turned off, it ends")


if __name__ == "__main__":
    unittest.main()
