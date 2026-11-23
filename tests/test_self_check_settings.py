"""v0.6.26 (review of the third round, K5): a settings file that cannot be read is not "the Codex engine is missing".

While the settings file cannot be read the watcher builds no engine (App.engine raises Unreadable, v0.6.18), and the
self-check took every tick without an engine for engine_missing: after three ticks it said "The Codex engine could not
be found or checked", which names the wrong cause - the engine was never looked for. Now such a tick counts nothing
toward it; a tick with readable settings and no engine counts as before.

No test asks this PC anything: the process list is a stub, and the folders are scratch ones.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume.runtime import loop  # noqa: E402
from codex_auto_resume.runtime.app import App  # noqa: E402
from codex_auto_resume.settings import Unreadable  # noqa: E402
from test_recovery_blocked import Store, Watcher  # noqa: E402


class SettingsUnreadableTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.watcher = Watcher(Path(temp.name) / "product")
        stub = patch.object(loop, "app_running_now", return_value=True)
        stub.start()
        self.addCleanup(stub.stop)

    def blocked_after(self, ticks):
        for _ in range(ticks):
            self.watcher._self_check(Store([]), None, 500.0)
        self.assertEqual(self.watcher.failures, [])
        return json.loads(self.watcher.paths.self_check_file.read_text(encoding="utf-8"))["blocked"]

    def test_the_app_builds_no_engine_while_its_settings_cannot_be_read(self):
        # The state the self-check reads: App.engine refuses to build on settings it could not read.
        unread = types.SimpleNamespace(_settings_good=False, refresh_settings=lambda engine: False)
        with self.assertRaises(Unreadable):
            App.engine(unread, None)

    def test_unreadable_settings_never_say_the_engine_is_missing(self):
        self.watcher._settings_good = False
        self.assertIsNone(self.blocked_after(4))

    def test_readable_settings_and_no_engine_still_say_it(self):
        self.watcher._settings_good = True
        self.assertEqual(self.blocked_after(3), "detection_blocked:engine_missing")

    def test_settings_read_again_start_the_count_from_there(self):
        self.watcher._settings_good = False
        self.assertIsNone(self.blocked_after(2))
        self.watcher._settings_good = True
        self.assertIsNone(self.blocked_after(2))
        self.assertEqual(self.blocked_after(1), "detection_blocked:engine_missing")


if __name__ == "__main__":
    unittest.main()
