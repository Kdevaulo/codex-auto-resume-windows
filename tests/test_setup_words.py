"""What the setup's log says, in the order it says it (v0.6.17, the live acceptance's second round).

Three things the log said wrongly, each held here by a test that fails with its fix reverted:

* mid-log, setup printed "could not be confirmed" about a watcher the installer then looked at again, and its
  last word said the watcher runs - setup now says "not confirmed yet" where its caller will look again;
* a Repair's last word was "Updated." - it says it was repaired;
* the look's own line was in the PC's language inside a log that is otherwise English.

Nothing here reaches the real registry, the real install or a real watcher: setup runs against a scratch home with
the registry faked and the watcher start stubbed, and the installer's script is lifted by marker and run with its
setup stubbed (the way tests/test_upgrade_handover.py does it).
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from codex_auto_resume import l10n, shortcut, startup

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "build" / "install" / "install.ps1"
BOOTSTRAP = ROOT / "scripts" / "bootstrap.ps1"
CATALOGS = ROOT / "src" / "codex_auto_resume" / "locales"


def _plugin_setup():
    module = sys.modules.get("plugin_setup_under_test")
    if module is None:
        spec = importlib.util.spec_from_file_location("plugin_setup_under_test", ROOT / "scripts" / "plugin_setup.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class ScratchSetup(unittest.TestCase):
    """plugin_setup's `setup` against a scratch home: no real registry, no shortcut, no watcher."""

    def setUp(self):
        from test_cli import FakeWinreg
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "runtime"
        self.bridge = _plugin_setup()
        patches = [patch.object(l10n, "current", return_value="en"),
                   patch.object(startup, "_winreg", return_value=FakeWinreg())]
        for target, replacement in (("install", None), ("uninstall", False), ("current_value", None),
                                    ("register_aumid", True), ("unregister_aumid", False)):
            patches.append(patch.object(startup, target, return_value=replacement))
        for target, replacement in (("install", True), ("uninstall", False)):
            patches.append(patch.object(shortcut, target, return_value=replacement))
        for guard in patches:
            guard.start()
            self.addCleanup(guard.stop)
        self.addCleanup(self._close_log_handlers)
        for name in ("python.exe", "pythonw.exe"):
            path = self.home / "runtime" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"")
        package = self.home / "app" / "src" / "codex_auto_resume"
        package.mkdir(parents=True, exist_ok=True)
        (package / "cli.py").write_text("", encoding="utf-8")
        (self.home / "app" / "src" / "auto_resume.py").write_text("", encoding="utf-8")

    @staticmethod
    def _close_log_handlers():
        import logging
        logger = logging.getLogger("codex_auto_resume")
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)

    def setup(self, *flags, started="unconfirmed", seen=False):
        args = self.bridge.build_parser().parse_args(["setup", "--no-startup", *flags])
        output = io.StringIO()
        with patch.object(self.bridge, "runtime_home", return_value=self.home), \
             patch.object(self.bridge, "start_watcher", return_value=started), \
             patch.object(self.bridge, "watcher_seen", return_value=seen), \
             contextlib.redirect_stdout(output):
            code = self.bridge.cmd_setup(args)
        return code, output.getvalue()


class MidLogWordTests(ScratchSetup):
    """A watcher setup could not confirm is "not confirmed yet" where the installer looks again, a verdict where
    nothing does."""

    def test_the_installer_s_setup_says_not_confirmed_yet(self):
        code, text = self.setup("--will-look-again")
        self.assertEqual(code, self.bridge.EXIT_UNCONFIRMED, "the exit code is still the unconfirmed one")
        self.assertIn(l10n.message("setup_unconfirmed_yet"), text)
        self.assertNotIn(l10n.message("setup_unconfirmed"), text, "no final verdict where a later look follows")

    def test_a_setup_run_alone_keeps_the_final_word(self):
        code, text = self.setup()
        self.assertEqual(code, self.bridge.EXIT_UNCONFIRMED)
        self.assertIn(l10n.message("setup_unconfirmed"), text)
        self.assertNotIn(l10n.message("setup_unconfirmed_yet"), text)

    def test_a_confirmed_watcher_is_the_same_word_either_way(self):
        for flags in ((), ("--will-look-again",)):
            with self.subTest(flags=flags):
                code, text = self.setup(*flags, started="running")
                self.assertEqual(code, self.bridge.EXIT_OK)
                self.assertIn(l10n.message("setup_done"), text)
                self.assertNotIn(l10n.message("setup_unconfirmed"), text)
                self.assertNotIn(l10n.message("setup_unconfirmed_yet"), text)

    def test_a_watcher_left_stopped_is_still_said_to_be_left_stopped(self):
        code, text = self.setup("--keep-state", "--watcher-was-stopped", "--will-look-again")
        self.assertIn(l10n.message("setup_left_stopped"), text)
        self.assertNotIn(l10n.message("setup_unconfirmed_yet"), text)

    def test_the_two_words_say_different_things(self):
        yet, final = l10n.message("setup_unconfirmed_yet"), l10n.message("setup_unconfirmed")
        self.assertNotEqual(yet, final)
        self.assertIn("yet", yet)
        self.assertNotIn("could not be confirmed", yet, "no verdict in the word that is not one")

    def test_every_language_has_the_new_word_of_its_own(self):
        english = l10n.text("msg.setup_unconfirmed_yet", "en")
        for locale in l10n.LOCALES:
            if locale == "en":
                continue
            table = json.loads((CATALOGS / ("%s.json" % locale)).read_text(encoding="utf-8"))
            with self.subTest(locale):
                self.assertIn("msg.setup_unconfirmed_yet", table)
                self.assertNotEqual(table["msg.setup_unconfirmed_yet"], english)
                self.assertNotEqual(table["msg.setup_unconfirmed_yet"], table["msg.setup_unconfirmed"])

    def test_korean_calls_the_watcher_the_way_the_korean_documents_do(self):
        self.assertIn("감시기", l10n.text("msg.setup_unconfirmed_yet", "ko"))


class CallersLookAgainTests(unittest.TestCase):
    """Every script that says setup's last word looks again after it, and says so to setup."""

    def test_install_ps1_tells_setup_it_will_look_again_and_does(self):
        text = INSTALL.read_text(encoding="utf-8")
        flag = text.index("$setupArgs += '--will-look-again'")
        run = text.index("$code = Invoke-Setup $setupArgs", flag)        # setup runs after the flag is set
        self.assertIn("Invoke-Setup @('watcher-running'", text[run:], "and the look that follows is the reason for it")

    def test_the_bootstraps_check_over_tells_setup_it_will_look_again_and_does(self):
        text = BOOTSTRAP.read_text(encoding="utf-8")
        start = text.index("$arguments = @($setup, 'setup', '--keep-state')")
        branch = text[start:text.index("exit $code", start)]
        self.assertIn("$arguments += '--will-look-again'", branch)
        self.assertIn("'watcher-running'", branch)

    def test_the_plugin_s_own_setup_does_not(self):
        """Run from Codex (the skill) nothing looks again: nothing there says the flag."""
        for path in (ROOT / "skills" / "codex-auto-resume" / "SKILL.md", ROOT / "docs" / "PLUGIN.md"):
            if path.is_file():
                self.assertNotIn("--will-look-again", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
