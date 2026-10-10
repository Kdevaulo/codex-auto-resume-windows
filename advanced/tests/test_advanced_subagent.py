"""Subagent recovery through the parent (v0.6.14-beta.2): a parent hears, in fixed words, which of its subagents stopped
and why - added to the continuation core sends it (5a), or, once MS passed, in one of its own after the parent finished
normally (5b) - and nothing is ever sent to a subagent.

Held against the shipped definition and statement and against core's own engine, store and simulated Codex home
(takingcase.py), whose state database is given the spawn edges Codex keeps.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

import contextlib
from pathlib import Path
import re
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from takingcase import TakingCase  # noqa: E402
from advancedcase import ENGINE  # noqa: E402
from codex_auto_resume import continuation, l10n  # noqa: E402
from codex_auto_resume_advanced import statement  # noqa: E402
from codex_auto_resume_advanced.engine import subagent  # noqa: E402
from codex_auto_resume_advanced.registry import SUBAGENT_PARENT  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Measurement, Verdict  # noqa: E402
from test_engine import T1  # noqa: E402

CHILDREN = ["0a1b2c3d-00c%d-7000-8000-0000000000c%d" % (n, n) for n in range(7)]


class SubagentCase(TakingCase):
    DEFINITION = SUBAGENT_PARENT

    def arm(self, plug, state="armed", capability=None, **changes):
        definition = plug.runtime.registry.get(capability or self.cap)
        changes.setdefault("warnings", [str(word) for word in plug.runtime.arming.warnings(definition)])
        return super().arm(plug, state=state, capability=capability, **changes)

    def on(self, h=None):
        h = h or self.h
        plug = self.armed(h)
        plug.runtime._code_of(plug.runtime.registry.get(self.cap))._home = h.home.root
        h.backend.loaded_map[T1] = "loaded"
        return plug

    def spawned(self, children, h=None, status="failed"):
        """`children` spawned by T1, each a subagent conversation whose latest turn ended `status`."""
        h = h or self.h
        h.home.add_thread(T1)
        with contextlib.closing(sqlite3.connect(h.home.root / "state_5.sqlite")) as db:
            db.execute("CREATE TABLE IF NOT EXISTS thread_spawn_edges (parent_thread_id TEXT, child_thread_id TEXT, "
                       "status TEXT)")
            for child in children:
                db.execute("INSERT INTO thread_spawn_edges VALUES (?,?,'closed')", (T1, child))
            db.commit()
        for child in children:
            h.home.add_thread(child, thread_source="subagent")
            if status == "failed":
                h.home.fail_usage(child)
            else:
                h.home.add_turn(child, status=status, completed=int(h.now))

    @staticmethod
    def lines(prompt):
        """The subagents' lines of a prompt, in the language the process speaks."""
        start = statement.CATALOGS.text(subagent.LINE_KEY, child="@CHILD@", kind="@KIND@").split("@CHILD@")[0]
        return [line for line in prompt.splitlines() if line.startswith(start)]


class ParentFailedTests(SubagentCase):
    def test_the_parent_s_continuation_says_which_subagent_stopped_and_why(self):
        self.on()
        self.spawned(CHILDREN[:2])
        self.due()
        self.h.tick()
        self.assertEqual([call[0] for call in self.h.backend.send_calls], [T1], "the parent alone is sent to")
        lines = self.lines(self.h.backend.send_calls[0][1])
        kind = statement.CATALOGS.text(subagent.KIND_PREFIX + "usage_limit")
        self.assertEqual(lines, [statement.CATALOGS.text(subagent.LINE_KEY, child=child, kind=kind)
                                 for child in CHILDREN[:2]])

    def test_a_line_carries_the_subagent_s_id_and_a_closed_word_and_nothing_else(self):
        self.on()
        self.spawned(CHILDREN[:1])
        self.due()
        self.h.tick()
        line = self.lines(self.h.backend.send_calls[0][1])[0]
        template = re.escape(statement.CATALOGS.text(subagent.LINE_KEY, child="CHILD", kind="KIND"))
        words = "|".join(re.escape(statement.CATALOGS.text(subagent.KIND_PREFIX + kind)) for kind in subagent.KINDS)
        self.assertRegex(line, "^" + template.replace("CHILD", "[0-9a-f-]{36}").replace("KIND", "(%s)" % words) + "$")

    def test_five_lines_at_most_and_each_stop_told_once(self):
        plug = self.on()
        self.spawned(CHILDREN)
        self.due()
        self.h.tick()
        self.assertEqual(len(self.lines(self.h.backend.send_calls[0][1])), subagent.MAX_LINES)
        told = [row for row in plug.runtime.state.continuations(pending=None) if row["reason"] == "mentioned"]
        self.assertEqual(len(told), subagent.MAX_LINES, "one mention a stop, kept")

    def test_no_subagent_stopped_leaves_core_s_words(self):
        self.on()
        self.spawned(CHILDREN[:2], status="completed")
        self.due()
        self.h.tick()
        self.assertEqual(self.lines(self.h.backend.send_calls[0][1]), [])

    def test_off_core_s_words_alone(self):
        self.plugged(self.advanced())
        self.spawned(CHILDREN[:2])
        self.due()
        self.h.tick()
        self.assertEqual(self.lines(self.h.backend.send_calls[0][1]), [])


class ParentFinishedTests(SubagentCase):
    def finished_parent(self):
        self.spawned(CHILDREN[:1])
        self.h.home.add_turn(T1, completed=int(self.h.now))
        for _ in range(3):
            self.h.tick(advance=61)

    def test_until_ms_passes_nothing_is_sent(self):
        self.on()
        self.finished_parent()
        self.assertEqual(self.h.backend.send_calls, [])

    def test_once_ms_passed_the_parent_is_sent_one_continuation_with_the_lines(self):
        """Fails if a child were handed: every send is the parent's."""
        self.measured = {Measurement.MS: (Verdict.PASS, ENGINE)}
        self.on()
        self.finished_parent()
        self.assertEqual([call[0] for call in self.h.backend.send_calls], [T1])
        self.assertEqual(len(self.lines(self.h.backend.send_calls[0][1])), 1)
        for _ in range(5):
            self.h.tick(advance=61)
        self.assertEqual(len(self.h.backend.send_calls), 1, "told once")


class WordsTests(unittest.TestCase):
    def test_the_words_pass_as_a_continuation_in_every_language(self):
        for locale in l10n.LOCALES:
            for kind in subagent.KINDS:
                with self.subTest(locale, kind=kind):
                    word = statement.CATALOGS.text(subagent.KIND_PREFIX + kind, locale)
                    line = statement.CATALOGS.text(subagent.LINE_KEY, locale, child=CHILDREN[0], kind=word)
                    continuation.validate_continuation("\n".join([line] * subagent.MAX_LINES))


if __name__ == "__main__":
    unittest.main()
