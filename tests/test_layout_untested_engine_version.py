"""v0.6.26 (fourth round, audit-core A4 / audit-limits J3): "a layout this version has not been tested on" reaches the
surfaces where the app's version cannot be read.

The layout's snapshot reads the app's version only where there is exactly one main, so on two mains or a helper alone
- the very shapes that are not tested - the watcher's `_layout_said` fell back to the engine's version as the layout
kept it: `codex --version`'s whole line, "codex-cli 0.171.0-alpha.13". The self-check's readers take a version of
letters, digits, dots and hyphens only, so they dropped it and Diagnostics, the status and the panel said nothing. Now
the engine's line stands in as its version word (domain/public.version_word).

Synthetic rows and a scratch folder only; the process list the self-check asks is a stub.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume.codex import layout  # noqa: E402
from codex_auto_resume.domain import public  # noqa: E402
from codex_auto_resume.domain.ids import CODEX_APP_FAMILY  # noqa: E402
from codex_auto_resume.runtime import loop  # noqa: E402
import test_pairing_roles as roles  # noqa: E402  (a module, so its cases are not bound here)
from test_recovery_blocked import Store, Watcher  # noqa: E402

TWO_MAINS = [roles.MAIN, roles.row(13, 1, roles.PACKAGE, 130, CODEX_APP_FAMILY), roles.row(20, 10, roles.ENGINE, 200)]
LINE = "codex-cli 0.171.0-alpha.13"
STARTED = 500.0


class UntestedVersionTests(roles.Case):
    def setUp(self):
        super().setUp()
        self.watcher = Watcher(self.home / "product")
        stub = patch.object(loop, "app_running_now", return_value=False)
        stub.start()
        self.addCleanup(stub.stop)

    def said(self, rows, engine_version):
        found = layout.snapshot(rows)
        layout.Watch(self.watcher.paths.codex_layout_file, "0.6.26").look(found, stamp=(1, 2),
                                                                           engine_version=engine_version)
        self.watcher._self_check(Store([]), None, STARTED)
        written = json.loads(self.watcher.paths.self_check_file.read_text(encoding="utf-8"))
        return found, public.self_check(written, STARTED)

    def test_two_mains_with_the_engines_line_reach_the_surfaces(self):
        """Fails with the fix reverted: the note held the whole line and the reader returned None."""
        found, check = self.said(TWO_MAINS, LINE)
        self.assertEqual((found["mains"], found["app_version"], found["shape"]), (2, None, None))
        self.assertIsNotNone(check)
        self.assertEqual(check["layout_untested"], "0.171.0-alpha.13")

    def test_the_apps_own_version_is_kept_as_it_was(self):
        rows = [roles.MAIN, roles.row(20, 99, roles.ENGINE, 200), roles.row(21, 99, roles.ENGINE, 210)]
        with patch.dict(layout.SHAPES, {}, clear=True):          # any shape untested, one main
            found, check = self.said(rows, LINE)
        self.assertEqual(found["app_version"], "26.1117.4957.0")
        self.assertEqual(check["layout_untested"], "26.1117.4957.0")

    def test_the_version_word(self):
        for text, word in ((LINE, "0.171.0-alpha.13"), ("0.170.0", "0.170.0"), ("26.1117.4957.0", "26.1117.4957.0"),
                           ("codex-cli", None), ("", None), (None, None), (17, None),
                           ("codex-cli " + "1" * 40, None), ("x 1.2.3 4.5", "1.2.3"), ("v1.2", "v1.2")):
            with self.subTest(text=text):
                self.assertEqual(public.version_word(text), word)


if __name__ == "__main__":
    unittest.main()
