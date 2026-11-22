"""Restore defaults keeps the newest five set-aside settings files and deletes the older (v0.6.26, the third audit's
N3, the owner's choice 2026-11-22).

Each Restore defaults over a settings file the product cannot read leaves `settings.unreadable-<UTC time>.json` beside
it (control/policy.py `set_aside`); until v0.6.26 nothing ever pruned them, each possibly over 4 MiB. Now a new copy
deletes the older ones but the newest five (itself included), touching only a plain file of exactly that name pattern
in that folder: a lookalike name, a folder, a link or another folder's copy stays. Its own module.

Scratch folders only.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume.control import policy  # noqa: E402

NOW = "20261122T120000Z"


def _name(stamp, number=0):
    return "settings.unreadable-%s%s.json" % (stamp, "-%d" % number if number else "")


class SetAsideKeepsFiveTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.settings = self.root / "settings.json"

    def _set_aside(self):
        self.settings.write_text("{ not json", encoding="utf-8")
        with patch.object(policy.time, "strftime", return_value=NOW):
            return policy.set_aside(self.settings)

    def _copies(self, folder=None):
        return sorted(path.name for path in (folder or self.root).glob(policy.SET_ASIDE_GLOB))

    def test_the_older_copies_go_and_the_newest_five_stay(self):
        stamps = ["2026110%dT010101Z" % day for day in range(1, 8)]
        for stamp in stamps:
            (self.root / _name(stamp)).write_text("old", encoding="utf-8")
        made = self._set_aside()
        self.assertEqual(made.name, _name(NOW))
        self.assertEqual(self._copies(), sorted([_name(stamp) for stamp in stamps[-4:]] + [_name(NOW)]))

    def test_fewer_than_six_are_all_kept(self):
        for day in range(1, 5):
            (self.root / _name("2026110%dT010101Z" % day)).write_text("old", encoding="utf-8")
        self._set_aside()
        self.assertEqual(len(self._copies()), 5)

    def test_in_one_second_the_numbered_copy_is_the_newer(self):
        for number in range(0, 4):
            (self.root / _name(NOW, number)).write_text("old", encoding="utf-8")
        (self.root / _name("20261121T000000Z")).write_text("older", encoding="utf-8")
        made = self._set_aside()
        self.assertEqual(made.name, _name(NOW, 4))
        self.assertEqual(self._copies(), sorted(_name(NOW, number) for number in range(0, 5)))

    def test_only_the_exact_name_in_that_folder_is_touched(self):
        keep = [self.root / "settings.unreadable-notes.json", self.root / (_name("20200101T000000Z") + ".bak"),
                self.root / "other.unreadable-20200101T000000Z.json", self.root / "settings.json.tmp"]
        for path in keep:
            path.write_text("mine", encoding="utf-8")
        (self.root / _name("20200102T000000Z")).mkdir()          # a folder of that name is not a copy
        elsewhere = self.root / "other"
        elsewhere.mkdir()
        for day in range(1, 8):
            (elsewhere / _name("2026110%dT010101Z" % day)).write_text("theirs", encoding="utf-8")
        for day in range(1, 8):
            (self.root / _name("2026110%dT010101Z" % day)).write_text("old", encoding="utf-8")
        self._set_aside()
        for path in keep:
            self.assertTrue(path.exists(), path.name)
        self.assertTrue((self.root / _name("20200102T000000Z")).is_dir())
        self.assertEqual(len(self._copies(elsewhere)), 7)
        self.assertEqual(len(list(self.root.glob("settings.unreadable-2026*.json"))), 5)

    def test_a_copy_that_cannot_be_deleted_does_not_stop_the_set_aside(self):
        for day in range(1, 8):
            (self.root / _name("2026110%dT010101Z" % day)).write_text("old", encoding="utf-8")
        with patch.object(Path, "unlink", side_effect=PermissionError("held")):
            made = self._set_aside()
        self.assertEqual(made.name, _name(NOW))
        self.assertFalse(self.settings.exists())


if __name__ == "__main__":
    unittest.main()
