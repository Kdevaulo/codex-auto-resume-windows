"""Recover every conversation but Codex's own (v0.6.16-beta.3): through core's own engine and simulated Codex home,
a failed turn in a conversation with a label the standard edition does not know is taken up while the capability is
on - and only then - and Codex's own kinds never are.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from takingcase import TakingCase  # noqa: E402
import codexsim  # noqa: E402
from codex_auto_resume.domain.plug import Point  # noqa: E402
from codex_auto_resume.domain.plughands import Widening  # noqa: E402
from codex_auto_resume_advanced import registry  # noqa: E402
from codex_auto_resume_advanced.registry import EVERY_CONVERSATION  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Actor  # noqa: E402

NEW_LABEL = "a_label_from_tomorrow"


class EveryConversationTests(TakingCase):
    DEFINITION = EVERY_CONVERSATION

    def conversation(self, h, label):
        thread = codexsim.new_id()
        h.home.add_thread(thread, thread_source=label)
        h.backend.loaded_map[thread] = "loaded"
        return thread

    def fail(self, h, thread):
        h.now += 1
        h.home.fail_usage(thread)
        h.tick()
        return h.records(thread)

    def test_the_definition_departs_from_a15_alone_at_p19(self):
        self.assertEqual((EVERY_CONVERSATION.departs_from, EVERY_CONVERSATION.points, EVERY_CONVERSATION.compat),
                         (("A15",), frozenset({Point.ELIGIBILITY}), "thread_eligibility"))
        self.assertIn("every_conversation", registry.REGISTRY.ids)

    def test_off_a_new_label_is_left_alone_as_the_standard_edition_leaves_it(self):
        self.plugged(self.advanced())
        thread = self.conversation(self.h, NEW_LABEL)
        self.assertEqual(self.fail(self.h, thread), [])

    def test_on_a_new_label_is_taken_up_and_codexs_own_kinds_never_are(self):
        self.armed()
        thread = self.conversation(self.h, NEW_LABEL)
        self.assertEqual(len(self.fail(self.h, thread)), 1)
        for label in ("subagent", "guardian_review", "memory_consolidation", "agent_created_thread"):
            with self.subTest(label):
                self.assertEqual(self.fail(self.h, self.conversation(self.h, label)), [])

    def test_watched_it_widens_nothing_and_notes_what_it_would_have_done(self):
        plug = self.armed(state="shadow")
        thread = self.conversation(self.h, NEW_LABEL)
        self.assertEqual(self.fail(self.h, thread), [])
        self.assertIn(("would_have", "eligibility", "eligibility"), self.journal(plug))

    def test_turned_off_the_widening_is_gone_at_the_next_tick(self):
        plug = self.armed()
        plug.runtime.arming.disarm(self.cap, actor=Actor.DASHBOARD)
        plug.runtime.states(fresh=True)
        self.h.tick()
        self.assertEqual(self.h.source.widened, frozenset())
        self.assertEqual(self.fail(self.h, self.conversation(self.h, NEW_LABEL)), [])

    def test_its_answer_is_the_one_closed_word(self):
        plug = self.armed()
        self.assertEqual(plug.runtime.eligibility(), frozenset({Widening.EVERY_DESKTOP}))


if __name__ == "__main__":
    unittest.main()
