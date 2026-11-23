"""v0.6.26 (review of the third round, K1): a Codex home that lost its thread-writer-locks folder is said, not waited on.

Update resilience #4 made `loaded()` answer "unknown" where the paired app's home keeps no lock folder, so such a record
waits `loaded_state_unknown`; rule (b) of the watcher's judge read only `notLoaded`, so it never held, and every record
waited "whether the conversation is open cannot be told yet" for ever with no word. #4's other half - the compatibility
report's lock_directory check - still said NOT_APPLICABLE for a home that has conversations and no lock folder.

The first test drives the real path: the real transport's loaded() over a scratch home, the engine's dispatch, the
watcher's gathering of the facts (runtime/loop.py) and the judge. No test asks this PC anything: the app's identity, the
engine's own check and the Restart Manager are stubs.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import compat, compatio  # noqa: E402
from codex_auto_resume.codex import LocalSource, transport  # noqa: E402
from codex_auto_resume.runtime import loop  # noqa: E402
from codexsim import APP, CodexHome  # noqa: E402
from test_engine import EngineCase, T1  # noqa: E402
from test_recovery_blocked import Watcher  # noqa: E402

SERVER = APP["server"]["pid"]


class LoadedPathTests(EngineCase):
    """Backend.loaded -> dispatch -> the watcher's facts -> the judge, over a home with no lock folder."""

    def setUp(self):
        super().setUp()
        real = transport.Backend(self.h.home.root, self.h.home.root / "codex.exe")
        for stub in (patch.object(real, "_compatible", return_value=None),
                     patch.object(real, "app_identity", side_effect=lambda: dict(APP))):
            stub.start()
            self.addCleanup(stub.stop)
        # The engine asks the real transport whether the conversation is open; everything else stays the stand-in's.
        self.h.backend.loaded = real.loaded
        self.h.backend.codex_home = self.h.home.root
        self.h.backend.app_look = "matched"
        self.watcher = Watcher(self.root / "product")
        # The app's paired server holds the newest databases; nobody holds a writer lock.
        held = patch.object(loop, "resource_users", side_effect=lambda *paths: (
            [{"pid": SERVER, "created": APP["server"]["created"]}]
            if any(Path(path).suffix == ".sqlite" for path in paths) else []))
        held.start()
        self.addCleanup(held.stop)
        self.now = 0.0
        clock = patch.object(loop.time, "time", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def word_after(self, minutes):
        for step in range(minutes + 1):
            self.now = 1000.0 + 60.0 * step
            self.watcher._self_check(self.h.store, self.h.engine, 500.0)
        self.assertEqual(self.watcher.failures, [])
        return json.loads(self.watcher.paths.self_check_file.read_text(encoding="utf-8"))["blocked"]

    def test_a_home_without_its_lock_folder_is_said_after_ten_minutes(self):
        self.assertFalse((self.h.home.root / "thread-writer-locks").exists())
        self.ready_after_reset(loaded=False)
        self.h.tick()
        self.assertEqual(self.h.record()["last_error"], "loaded_state_unknown")
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertIsNone(self.word_after(5))
        self.assertEqual(self.word_after(11), "recovery_blocked:locks_unread")

    def test_a_lock_folder_that_is_there_is_no_contradiction(self):
        (self.h.home.root / "thread-writer-locks").mkdir()
        with patch.object(transport, "resource_users", return_value=[]):
            self.ready_after_reset(loaded=False)
            self.h.tick()
        self.assertEqual(self.h.record()["last_error"], "notLoaded")
        self.assertIsNone(self.word_after(11))


class LockDirectoryCheckTests(unittest.TestCase):
    """#4's other half: the compatibility report's lock_directory check."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = CodexHome(Path(temp.name) / "codex-home")

    def check(self):
        return compatio.source_checks(LocalSource(self.home.root))["lock_directory"]

    def test_a_home_with_conversations_and_no_lock_folder_fails(self):
        self.home.add_thread(T1)
        self.assertEqual(self.check(), compat.FAIL)
        (self.home.root / "thread-writer-locks").mkdir()
        self.assertEqual(self.check(), compat.PASS)

    def test_a_home_that_never_opened_a_conversation_is_not_yet_applicable(self):
        self.assertEqual(self.check(), compat.NOT_APPLICABLE)


if __name__ == "__main__":
    unittest.main()
