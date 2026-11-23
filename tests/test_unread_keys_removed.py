"""Five core catalog keys nothing reads are in no catalog (v0.6.26, the third audit's R1).

action.refresh, panel.col_conversation, panel.col_state and timeline.empty were last read by v0.6.0 to v0.6.2;
custom.placeholder was never read by a release (only its neighbour custom.placeholders is). Each sat in all 22 catalogs
and 21 translation bases. Removed with the rule "delete only what can never be used": versions that old do not run
beside this one (an update closes the open Dashboard, and every version reads the catalogs it ships). Kept on purpose:
starter.setup, the source of .codex-plugin/plugin.json's defaultPrompt that test_diagnostics_tools pins; the advanced
edition's five page.queue.* / page.confirm.prompt words, which releases v0.6.16 to v0.6.20 read; and
msg.toast_button_open_codex (v0.6.18 to v0.6.20-beta). Its own module.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import srcscan  # noqa: E402
from codex_auto_resume import l10n  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GONE = ("action.refresh", "panel.col_conversation", "panel.col_state", "timeline.empty", "custom.placeholder")
KEPT = ("starter.setup", "msg.toast_button_open_codex")


class UnreadKeysTests(unittest.TestCase):
    def test_no_catalog_or_basis_holds_one(self):
        self.assertGreaterEqual(len(l10n.LOCALES), 22)
        for locale in l10n.LOCALES:
            table = l10n._read(locale)
            for key in GONE:
                with self.subTest(locale=locale, key=key):
                    self.assertNotIn(key, table)
        bases = sorted((ROOT / "build" / "l10n").glob("*.basis.json"))
        self.assertGreaterEqual(len(bases), 21)
        for path in bases:
            table = json.loads(path.read_text(encoding="utf-8"))
            for key in GONE:
                with self.subTest(file=path.name, key=key):
                    self.assertNotIn(key, table)

    def test_nothing_in_a_shipped_source_names_one(self):
        quoted = re.compile(r"""["'](?:%s)["']""" % "|".join(re.escape(key) for key in GONE))
        files = srcscan.text_files()
        for folder in ("gui", "scripts", "advanced/src", "advanced/gui"):
            files += [path for path in sorted((ROOT / folder).rglob("*"))
                      if path.suffix in (".py", ".cs", ".js", ".ps1") and "__pycache__" not in path.parts]
        for path in files:
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertIsNone(quoted.search(path.read_text(encoding="utf-8", errors="replace")))

    def test_the_kept_ones_are_still_in_the_english_catalog(self):
        english = l10n._read("en")
        for key in KEPT:
            self.assertIn(key, english)


if __name__ == "__main__":
    unittest.main()
