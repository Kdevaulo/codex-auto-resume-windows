"""What Pending and History say beside a row the advanced edition had a hand in (v0.6.16-beta.4, design-4 G4).

The status's P10 part carries it, keyed by interruption id (surfaces.rows): the kind of a terminal's or VS Code's
conversation (other_sessions). The window joins each word to a cell's own line (CellsWritten, advanced/gui/
AdvancedRuns.cs, at the standard window's point in Cells) - no cell, column or element of its own, as a second Codex
home's alias joins the label line. Held against core's own engine, store and simulated Codex home, and against the
window's sources as text (the window itself is driven by the GUI set).

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from advancedcase import ROOT  # noqa: E402
from test_advanced_other_sessions import SessionsCase  # noqa: E402
from test_advanced_compact_continue import CONTEXT_FULL, CompactCase  # noqa: E402
from codex_auto_resume import l10n  # noqa: E402
from codex_auto_resume.domain import ids  # noqa: E402
from codex_auto_resume_advanced import statement, surfaces  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Actor, RunEnd  # noqa: E402
from test_engine import T1, T2  # noqa: E402
from test_session_kinds import CLI, IDE  # noqa: E402

import guiscan  # noqa: E402

T3 = "0a1b2c3d-0001-7000-8000-000000000003"
RUNS = ROOT / "advanced" / "gui" / "AdvancedRuns.cs"


def written(source: Path) -> str:
    """CellsWritten's body in `source`, by its braces."""
    text = source.read_text(encoding="utf-8")
    found = re.search(r"(?m)^[ \t]*partial void CellsWritten\(", text)
    if found is None:
        raise AssertionError("no CellsWritten in %s" % source.name)
    return guiscan._block(text, found.start())


class RowsCase(SessionsCase):
    def rows(self, plug):
        return surfaces.rows(plug.runtime, store=self.h.store, source=self.h.source)

    def keys(self):
        return {row["thread_id"]: row["interruption_id"] for row in self.h.store.history(limit=200)}


class KindTests(RowsCase):
    def recovered(self):
        """Waiting recoveries in a terminal's, a VS Code and an app's conversation, with other_sessions on."""
        plug = self.armed()
        self.other(T1, CLI)
        self.other(T2, IDE)
        self.ready_after_reset(self.h, thread_id=T3)
        self.h.tick()
        keys = self.keys()
        self.assertEqual(set(keys), {T1, T2, T3})
        return plug, keys

    def test_a_terminals_and_a_vs_code_conversation_are_named_by_kind_and_the_apps_by_none(self):
        """Fails with surfaces.rows' kinds reverted: Pending and History would name no kind."""
        plug, keys = self.recovered()
        self.assertEqual(self.rows(plug), {"kinds": {keys[T1]: "cli", keys[T2]: "ide"}})

    def test_the_status_carries_them_under_the_editions_key(self):
        plug, keys = self.recovered()
        listed = surfaces._listed
        with patch.object(surfaces, "_listed", lambda runtime, store: listed(runtime, self.h.store)), \
                patch.object(surfaces, "_source", lambda runtime: self.h.source):
            shown = surfaces.status(plug.runtime)
        self.assertEqual(shown["kinds"], {keys[T1]: "cli", keys[T2]: "ide"})

    def test_turned_off_nothing_is_read(self):
        plug, keys = self.recovered()
        self.assertTrue(plug.runtime.arming.disarm(self.cap, actor=Actor.DASHBOARD)["done"])
        plug.runtime.states(fresh=True)
        with patch.object(surfaces, "_listed", side_effect=AssertionError("read while off")):
            self.assertEqual(surfaces.rows(plug.runtime), {})

    def test_a_reader_that_fails_says_nothing(self):
        plug, _ = self.recovered()

        class Broken:
            home = "broken"

            def taken(self, thread_id, kinds):
                raise OSError("locked")
        self.assertEqual(surfaces.rows(plug.runtime, store=self.h.store, source=Broken()), {})


class ModelTests(RowsCase):
    """A turn model_fallback ran on Codex's default model whose conversation's own model Codex would not put back
    (design-4 6, the review's finding 22): its id in "model_not_restored" while the model is owed - whatever the
    capability stands at now - so Pending and History say "This conversation now uses another model; switch it back
    in Codex", with no model's name."""
    KEY, OTHER, LIVE = "%064x" % 11, "%064x" % 12, "%064x" % 13

    def owed(self):
        plug = self.armed()
        state, now = plug.runtime.state, self.h.now
        for key in (self.KEY, self.OTHER, self.LIVE):
            state.run_owed(key, "model_fallback", T1, "gpt-own-model", started_at=now - 600, ends_by=now + 3000)
        state.run_ended(self.KEY, RunEnd.COMPLETED)
        state.run_ended(self.OTHER, RunEnd.INTERRUPTED)
        self.assertTrue(state.run_restored(self.OTHER), "put back and read back")
        return plug

    def test_a_model_codex_would_not_put_back_is_said_until_it_is(self):
        """Fails with surfaces.rows' model_not_restored reverted: the statement's promise would go unkept."""
        plug = self.owed()
        self.assertEqual(self.rows(plug)["model_not_restored"], [self.KEY])
        plug.runtime.state.run_restored(self.KEY)
        self.assertNotIn("model_not_restored", self.rows(plug))

    def test_it_is_said_with_every_capability_off_and_names_no_model(self):
        plug = self.owed()
        self.assertTrue(plug.runtime.arming.disarm(self.cap, actor=Actor.DASHBOARD)["done"])
        plug.runtime.states(fresh=True)
        shown = surfaces.rows(plug.runtime)
        self.assertEqual(shown, {"model_not_restored": [self.KEY]})
        self.assertNotIn("gpt-own-model", repr(shown))
        for locale in l10n.LOCALES:
            self.assertNotIn("{", statement.CATALOGS.catalog(locale)["page.row.model_not_restored"], locale)


class SilentTests(RowsCase):
    """A continuation a turn run here started with no words, proven by its id (silent_continuation, design-4 7): its
    id in "silent", so History says "continued with no words, proven by its id"."""

    def ran(self):
        """Three recoveries, each continued by a turn run here or not: with no words (the derived client id, as core's
        routes._silent writes it), with words and the marker, and by the derived id with no run here (a marker-free
        send through a channel)."""
        plug = self.armed()
        for thread in (T1, T2, T3):
            self.ready_after_reset(self.h, thread_id=thread)
        keys = self.keys()
        state, now = plug.runtime.state, self.h.now
        for thread in (T1, T2):
            state.run_started(keys[thread], "headless_run", thread, started_at=now - 60, ends_by=now + 3540)
            state.run_ended(keys[thread], RunEnd.COMPLETED)
        for thread in (T1, T3):
            self.h.store.update(keys[thread], at=now, recovery_client_id=ids.continuation_client_id(keys[thread]))
        return plug, keys

    def test_one_a_turn_run_here_started_with_no_words_is_said(self):
        """Fails with surfaces.rows' silent reverted: History would not say how it was continued."""
        plug, keys = self.ran()
        self.assertEqual(self.rows(plug)["silent"], [keys[T1]])

    def test_it_is_said_with_every_capability_off(self):
        plug, keys = self.ran()
        self.assertTrue(plug.runtime.arming.disarm(self.cap, actor=Actor.DASHBOARD)["done"])
        plug.runtime.states(fresh=True)
        listed = surfaces._listed
        with patch.object(surfaces, "_listed", lambda runtime, store: listed(runtime, self.h.store)):
            self.assertEqual(surfaces.rows(plug.runtime, store=self.h.store), {"silent": [keys[T1]]})


class CompactingTests(CompactCase):
    """A full conversation held for the person's /compact (compact_continue, design-4 5.2): its id in "compacting",
    so Pending's status says "Run /compact in Codex; it continues after"."""

    def rows(self, plug):
        return surfaces.rows(plug.runtime, store=self.h.store, source=self.h.source)

    def held(self):
        plug = self.armed()
        self.failing(CONTEXT_FULL)
        for _ in range(15):
            self.h.tick(advance=60)
        (row,) = self.h.records()
        self.assertEqual(self.h.backend.send_calls, [])
        return plug, row

    def test_held_for_the_persons_compact_it_is_named(self):
        """Fails with surfaces.rows' compacting reverted: Pending would not ask for /compact."""
        plug, row = self.held()
        self.assertEqual(self.rows(plug), {"compacting": [row["interruption_id"]]})

    def test_once_compacted_and_continued_it_is_not(self):
        plug, row = self.held()
        self.compaction()
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertEqual(len(self.h.backend.send_calls), 1)
        self.assertEqual(self.rows(plug), {})

    def test_watched_it_holds_nothing_and_nothing_is_said(self):
        plug = self.armed(state="shadow")
        self.failing(CONTEXT_FULL)
        self.h.tick()
        self.assertEqual(self.rows(plug), {})

    def test_the_statement_says_what_the_row_says_in_every_language(self):
        for locale in l10n.LOCALES:
            with self.subTest(locale):
                words = statement.CATALOGS.catalog(locale)
                self.assertIn(words["page.row.compact"], words["statement.compact_continue.does"])


class OneStopTests(unittest.TestCase):
    """A turn run here is stopped in one place: Stop... on the Advanced features page's runs card (AdvancedRuns.cs),
    never a second button on Pending (no two ways to one result; DECISIONS 2026-10-17, I1.m) - and the statement
    says where it is, in every language."""

    def test_the_statement_points_to_the_card_in_every_language(self):
        """Fails with the statement pointing at a Stop on Pending's row again."""
        for locale in l10n.LOCALES:
            with self.subTest(locale):
                words = statement.CATALOGS.catalog(locale)
                said = words["statement.headless_run.stop"]
                self.assertIn(words["page.runs.title"], said)
                self.assertIn(words["page.runs.stop"], said)
                self.assertNotIn("Pending", statement.CATALOGS.catalog("en")["statement.headless_run.stop"])

    def test_only_the_runs_card_sends_a_stop(self):
        sending = sorted(path.name for path in (ROOT / "advanced" / "gui").glob("*.cs")
                         if '"advanced-headless-stop"' in path.read_text(encoding="utf-8"))
        self.assertEqual(sending, [RUNS.name])


class WindowTests(unittest.TestCase):
    """The window's half, read as text: the standard window's point, and the overlay's body of it."""

    def test_the_standard_window_hands_every_row_to_the_point_before_it_is_shown(self):
        cells = guiscan.member_body("SettingsForm", "Cells")
        self.assertRegex(cells, r"CellsWritten\(row, pending, cells\);\s*return cells;")

    def test_the_kind_joins_the_label_line_and_nothing_else(self):
        """Fails with the kind's words taken out of CellsWritten."""
        body = written(RUNS)
        self.assertIn('Map(said, "kinds")', body)
        self.assertIn('cells[0] += " · " + Word("page.row.kind.cli", "CLI")', body)
        self.assertIn('cells[0] += " · " + Word("page.row.kind.ide", "VS Code")', body)
        self.assertNotRegex(body, r"\bnew\s+(Label|Panel|ColumnHeader|ListViewItem)\b", "no element of its own")

    def test_a_model_not_put_back_joins_the_status_line_of_pending_and_history(self):
        """Fails with the words taken out of CellsWritten."""
        body = written(RUNS)
        self.assertIn('if (Listed(said, "model_not_restored", key))', body)
        self.assertIn('cells[1] += " · " + Word("page.row.model_not_restored", "This conversation now uses another '
                      'model; switch it back in Codex")', body)

    def test_a_continuation_with_no_words_joins_historys_outcome_line_only(self):
        """Fails with the words taken out of CellsWritten."""
        body = written(RUNS)
        self.assertIn('if (!pending && Listed(said, "silent", key))', body)
        self.assertIn('cells[1] += " · " + Word("page.row.silent", "continued with no words, proven by its id")', body)

    def test_the_compact_hint_joins_pendings_status_line_only(self):
        """Fails with the hint taken out of CellsWritten."""
        body = written(RUNS)
        self.assertIn('if (pending && Listed(said, "compacting", key))', body)
        self.assertIn('cells[1] += " · " + Word("page.row.compact", "Run /compact in Codex; it continues after")', body)


if __name__ == "__main__":
    unittest.main()
