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
from codex_auto_resume_advanced import surfaces  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Actor  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
