"""Restore defaults never deletes the copy it has just set aside, whatever the clock says (v0.6.26, review K4).

`set_aside` keeps the newest five set-aside settings files by the time in their names. Where five copies carry a later
time than the clock now says - a clock set back, a time sync after a clock that ran ahead - the copy just made was the
oldest by name and was deleted at once: the person's unreadable settings were gone, and the caller named a file that no
longer existed. Now the copy just made is always kept, with the four newest of the others. Its own module.

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

NOW = "20261122T170452Z"


def _name(stamp):
    return "settings.unreadable-%s.json" % stamp


class ClockBackTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.settings = self.root / "settings.json"

    def _set_aside(self):
        self.settings.write_text("{ not json", encoding="utf-8")
        with patch.object(policy.time, "strftime", return_value=NOW):
            return policy.set_aside(self.settings)

    def _copies(self):
        return sorted(path.name for path in self.root.glob(policy.SET_ASIDE_GLOB))

    def test_the_copy_just_made_stays_beside_five_stamped_later(self):
        later = ["20991231T00000%dZ" % second for second in range(5)]
        for stamp in later:
            (self.root / _name(stamp)).write_text("old", encoding="utf-8")
        made = self._set_aside()
        self.assertTrue(made.is_file(), "the person's settings were deleted the moment they were set aside")
        self.assertEqual(made.read_text(encoding="utf-8"), "{ not json")
        self.assertFalse(self.settings.exists())
        # Five in all: the new copy and the four newest of the others; the oldest of those goes.
        self.assertEqual(self._copies(), sorted([_name(NOW)] + [_name(stamp) for stamp in later[1:]]))

    def test_with_the_clock_right_the_newest_five_stay_as_before(self):
        older = ["2026110%dT010101Z" % day for day in range(1, 8)]
        for stamp in older:
            (self.root / _name(stamp)).write_text("old", encoding="utf-8")
        made = self._set_aside()
        self.assertEqual(self._copies(), sorted([made.name] + [_name(stamp) for stamp in older[-4:]]))


if __name__ == "__main__":
    unittest.main()
