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
import unittest

ROOT = Path(__file__).resolve().parents[1]
GONE = ("action.refresh", "panel.col_conversation", "panel.col_state", "timeline.empty", "custom.placeholder")
KEPT = ("starter.setup", "msg.toast_button_open_codex")


class UnreadKeysTests(unittest.TestCase):
    def test_no_catalog_or_basis_holds_one(self):
        files = sorted((ROOT / "src" / "codex_auto_resume" / "locales").glob("*.json")) + sorted(
            (ROOT / "build" / "l10n").glob("*.basis.json"))
        self.assertGreaterEqual(len(files), 43)
        for path in files:
            table = json.loads(path.read_text(encoding="utf-8"))
            for key in GONE:
                with self.subTest(file=path.name, key=key):
                    self.assertNotIn(key, table)

    def test_nothing_in_a_shipped_source_names_one(self):
        quoted = re.compile(r"""["'](?:%s)["']""" % "|".join(re.escape(key) for key in GONE))
        for folder in ("src", "gui", "scripts", "advanced/src", "advanced/gui"):
            for path in sorted((ROOT / folder).rglob("*")):
                if path.suffix not in (".py", ".cs", ".js", ".ps1") or "__pycache__" in path.parts:
                    continue
                with self.subTest(path=str(path.relative_to(ROOT))):
                    self.assertIsNone(quoted.search(path.read_text(encoding="utf-8", errors="replace")))

    def test_the_kept_ones_are_still_in_the_english_catalog(self):
        english = json.loads((ROOT / "src" / "codex_auto_resume" / "locales" / "en.json").read_text(encoding="utf-8"))
        for key in KEPT:
            self.assertIn(key, english)


if __name__ == "__main__":
    unittest.main()
