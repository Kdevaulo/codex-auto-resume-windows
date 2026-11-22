"""The setup window's log is English throughout, setup's summary block too (v0.6.26, the third audit's U1).

`plugin_setup setup` printed its summary (the ready title, the defaults, the four check lines, the verdict and the
autostart line) in the stored or Windows language, between English lines, in the log the installer relays into the
setup window. The installer now sets CODEX_AUTO_RESUME_SETUP_ENGLISH around every setup call it relays (Invoke-Setup),
and setup says its sentences in English then; run by Codex itself, with no such variable, it stays in the person's
language. Its own module.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codex_auto_resume import l10n  # noqa: E402
from test_setup_words import INSTALL, ScratchSetup  # noqa: E402

KEYS = ("ready_title", "ready_defaults", "ready_b1", "ready_b2", "ready_b3", "ready_b4", "setup_done")


class KoreanPcSetupTests(ScratchSetup):
    PIN_ENGLISH = False

    def setUp(self):
        super().setUp()
        guard = patch.object(l10n, "current", return_value="ko")
        guard.start()
        self.addCleanup(guard.stop)

    def test_the_installer_s_setup_is_english_whatever_the_language(self):
        with patch.dict(os.environ, {self.bridge.ENV_ENGLISH: "1"}):
            code, text = self.setup(started="running")
        self.assertEqual(code, self.bridge.EXIT_OK)
        for key in KEYS:
            with self.subTest(key):
                self.assertIn(l10n.text("msg." + key, "en"), text)
                self.assertNotIn(l10n.text("msg." + key, "ko"), text)

    def test_setup_run_by_codex_keeps_the_person_s_language(self):
        os.environ.pop(self.bridge.ENV_ENGLISH, None)
        code, text = self.setup(started="running")
        for key in KEYS:
            with self.subTest(key):
                self.assertIn(l10n.text("msg." + key, "ko"), text)


class InstallerAsksForEnglishTests(unittest.TestCase):
    def test_every_setup_call_the_installer_relays_is_asked_for_english(self):
        text = INSTALL.read_text(encoding="utf-8")
        start = text.index("function Invoke-Setup")
        body = text[start:text.index("\nfunction ", start + 10)]
        relay = body.index("$setup @Arguments | ForEach-Object {")   # the one call whose lines are relayed (and kept)
        self.assertLess(body.index("$env:CODEX_AUTO_RESUME_SETUP_ENGLISH = '1'"), relay)
        self.assertIn("$env:CODEX_AUTO_RESUME_SETUP_ENGLISH = $null", body[relay:], "and for no other call")


if __name__ == "__main__":
    unittest.main()
