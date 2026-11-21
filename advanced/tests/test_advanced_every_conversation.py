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
from test_adopted_cli import conversation as shaped  # noqa: E402
from codex_auto_resume.codex import eligibility  # noqa: E402
from codex_auto_resume import machine  # noqa: E402
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


class TurnedOffTests(TakingCase):
    """v0.6.20 (the pair audit; the owner's word of 2026-10-31): turned off, the waiting records of the conversations it
    widened to are cancelled - as turning other_sessions off cancels its own (core's engine/kinds.py, the same word,
    session_kind_off) - and a person's own conversation's record is untouched. Left to the next check, such a record
    could no longer be read and would be retired as superseded, which is untrue."""
    DEFINITION = EVERY_CONVERSATION

    def waiting(self, label):
        thread = codexsim.new_id()
        self.h.home.add_thread(thread, thread_source=label)
        self.h.backend.loaded_map[thread] = "loaded"
        self.h.now += 1
        self.h.home.fail_usage(thread)
        self.h.tick()
        (row,) = self.h.records(thread)
        self.assertIn(row["state"], machine.WAITING)
        return thread

    def test_turned_off_the_waiting_records_it_widened_to_are_cancelled(self):
        """Fails with the fix reverted: the widened record keeps waiting for a conversation core no longer takes up."""
        plug = self.armed()
        widened, own = self.waiting(NEW_LABEL), self.waiting("user")
        plug.runtime.arming.disarm(self.cap, actor=Actor.DASHBOARD)
        plug.runtime.states(fresh=True)
        self.h.tick(advance=1)
        row = self.h.record(widened)
        self.assertEqual((row["state"], row["last_error"]), ("cancelled", "session_kind_off"))
        self.assertNotEqual(self.h.record(own)["state"], "cancelled")

    def test_still_on_they_keep_waiting(self):
        self.armed()
        widened = self.waiting(NEW_LABEL)
        self.h.tick(advance=1)
        self.assertNotEqual(self.h.record(widened)["state"], "cancelled")


class AnyOriginatorTests(TakingCase):
    """v0.6.24 (the owner's word of 2026-11-19, "take up everything but what is confirmed"): on, a conversation on the app's
    row is taken up whatever its first line's originator, but the closed deny-list's (core's
    codex/values.NOT_DESKTOP_ORIGINATORS: codex_vscode, VS Code's own) - an originator Codex adds later, and issue #66's
    exec line with no fork, included. The row's source, the first line's source, the thread_source deny-list and every
    gate stand; off, it is the standard edition's allow-list, the #66 fork rule included."""
    DEFINITION = EVERY_CONVERSATION
    FUTURE = "codex_future"

    def failing(self, originator, row_source="vscode", meta_source="vscode", thread_source="user", **more):
        thread = codexsim.new_id()
        shaped(self.h.home, thread, row_source=row_source, meta_source=meta_source, originator=originator,
               thread_source=thread_source, **more)
        self.h.backend.loaded_map[thread] = "loaded"
        self.h.now += 1
        self.h.home.fail_usage(thread)
        self.h.tick()
        return self.h.records(thread)

    def test_on_an_unknown_originator_and_an_exec_line_with_no_fork_are_taken_up(self):
        """Fails with the widening reverted: "not taken up (other_kind: originator codex_future)"."""
        self.armed()
        self.assertEqual(len(self.failing(self.FUTURE)), 1)
        self.assertEqual(len(self.failing("codex_exec")), 1)
        wide = frozenset({Widening.EVERY_DESKTOP})
        self.assertEqual(eligibility.kind_of("vscode", {"source": "vscode", "originator": self.FUTURE}, widened=wide),
                         "desktop")
        self.assertTrue(eligibility.originator_taken("vscode", {"originator": self.FUTURE}, widened=wide))

    def test_on_vs_codes_own_exec_and_cli_rows_and_a_subagent_are_not(self):
        self.armed()
        for name, shape in (("VS Code's own", dict(originator="codex_vscode")),
                            ("a standalone exec run", dict(originator="codex_exec", row_source="exec", meta_source="exec")),
                            ("an exec row, unknown originator", dict(originator=self.FUTURE, row_source="exec",
                                                                     meta_source="exec")),
                            ("a terminal's", dict(originator="codex-tui", row_source="cli", meta_source="cli")),
                            ("a cli row, unknown originator", dict(originator=self.FUTURE, row_source="cli",
                                                                   meta_source="cli")),
                            ("a subagent", dict(originator=self.FUTURE, thread_source="subagent")),
                            ("a first line of another source", dict(originator=self.FUTURE, meta_source="exec")),
                            ("no originator", dict(originator=None))):
            with self.subTest(name):
                self.assertEqual(self.failing(**shape), [])
        wide = frozenset({Widening.EVERY_DESKTOP})
        self.assertIsNone(eligibility.kind_of("vscode", {"source": "vscode", "originator": "codex_vscode"}, widened=wide))
        self.assertFalse(eligibility.originator_taken("exec", {"originator": self.FUTURE}, widened=wide))

    def test_off_an_unknown_originator_is_refused_as_today(self):
        self.plugged(self.advanced())
        self.assertEqual(self.failing(self.FUTURE), [])
        self.assertEqual(self.failing("codex_exec"), [])
        self.assertIsNone(eligibility.kind_of("vscode", {"source": "vscode", "originator": self.FUTURE}))

    def test_turned_off_the_record_only_it_took_up_is_cancelled(self):
        plug = self.armed()
        (row,) = self.failing(self.FUTURE)
        self.assertIn(row["state"], machine.WAITING)
        plug.runtime.arming.disarm(self.cap, actor=Actor.DASHBOARD)
        plug.runtime.states(fresh=True)
        self.h.tick(advance=1)
        row = self.h.record(row["thread_id"])
        self.assertEqual((row["state"], row["last_error"]), ("cancelled", "session_kind_off"))


if __name__ == "__main__":
    unittest.main()
