"""A lone surrogate in a settings string is refused as a SettingsError and never poisons a save (v0.6.26, the third
core audit's C2).

Since v0.6.23 the settings are written as UTF-8 with the characters themselves; a string holding half of a surrogate
pair (a `\\ud83d` JSON escape, through the control CLI or in a file an earlier version wrote) made `json.dumps(...)
.encode("utf-8")` raise UnicodeEncodeError, which no caller catches as a SettingsError, so every later save failed until
the one value was found. Its own module: the scenario modules are frozen (tests/neutral.py MODULES).

Scratch settings files only.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import settings  # noqa: E402

HALF = "go on \ud83d please"
THREAD = "019a0000-0000-7000-8000-000000000001"


class LoneSurrogateTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "settings.json"

    def test_a_write_holding_one_is_a_settings_error_naming_the_field(self):
        for changes in ({"custom_message": HALF}, {"codex_exe": "C:\\x\ud83d.exe"}):
            with self.assertRaises(settings.SettingsError) as caught:
                settings.update(self.path, changes)
            self.assertIn(next(iter(changes)), str(caught.exception))
        self.assertFalse(self.path.exists())

    def test_one_in_a_nested_value_is_refused_too(self):
        with self.assertRaises(settings.SettingsError):
            settings.validate_update({settings.homes.FIELD: ["C:\\codex\ud83d"]})

    def test_a_file_holding_one_reads_it_as_the_default_and_later_saves_work(self):
        self.path.write_text(json.dumps({"config_version": settings.CONFIG_VERSION, "custom_message": HALF,
                                         "theme": "light"}), encoding="utf-8")
        self.assertIn("\\ud83d", self.path.read_text(encoding="utf-8"))
        loaded = settings.load(self.path)
        self.assertEqual(loaded["custom_message"], settings.DEFAULTS["custom_message"])
        self.assertEqual(loaded["theme"], "light")
        settings.update(self.path, {"theme": "dark"})
        kept = settings.load(self.path)
        self.assertEqual(kept["theme"], "dark")
        self.assertEqual(kept["custom_message"], settings.DEFAULTS["custom_message"])

    def test_an_entry_holding_one_is_dropped_and_the_whole_ones_stay(self):
        by_thread = {THREAD: "keep going", "019a0000-0000-7000-8000-000000000002": HALF}
        self.path.write_text(json.dumps({"config_version": settings.CONFIG_VERSION,
                                         "custom_message_by_thread": by_thread}), encoding="utf-8")
        field = settings.continuation.BY_THREAD_FIELD
        self.assertEqual(settings.load(self.path)[field], {THREAD: "keep going"})
        settings.update(self.path, {"observe_only": True})

    def test_save_never_raises_an_encode_error(self):
        written = settings.save(self.path, dict(settings.defaults(), custom_message=HALF))
        self.assertEqual(written["custom_message"], settings.DEFAULTS["custom_message"])


if __name__ == "__main__":
    unittest.main()
