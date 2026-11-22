"""Every English fallback the panel writes is the English catalog's sentence (v0.6.26, the third audit's R4).

`t('key', 'literal')` in panel.js is what the panel says where its catalog lacks the key, and says what en.json says.
Three had drifted: compat.checked said "Checked" (the catalog: "Evaluated", the word the window fixed in the second
round), help.continuation_language and preview.note dropped the catalog's second sentence.
test_l10n checks the panel's fallbacks only for the naming keys; this checks every `t()` call with a literal. Its own
module.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "codex_auto_resume" / "mcp" / "assets" / "panel.js"
ENGLISH = ROOT / "src" / "codex_auto_resume" / "locales" / "en.json"
LITERAL = r"'(?:[^'\\\r\n]|\\.)*'"
CALL = re.compile(r"\bt\(\s*('(?:[^'\\\r\n]|\\.)*')\s*,\s*((?:%s\s*\+?\s*)+)\)" % LITERAL)


class PanelFallbackTests(unittest.TestCase):
    def test_every_literal_fallback_is_the_english_catalogs_sentence(self):
        english = json.loads(ENGLISH.read_text(encoding="utf-8"))
        text = PANEL.read_text(encoding="utf-8")
        checked = 0
        for match in CALL.finditer(text):
            key = ast.literal_eval(match.group(1))
            said = "".join(ast.literal_eval(literal) for literal in re.findall(LITERAL, match.group(2)))
            if key not in english or not said:
                continue
            checked += 1
            with self.subTest(key=key):
                self.assertEqual(said, english[key])
        self.assertGreater(checked, 80, "the lookup found the panel's calls")


if __name__ == "__main__":
    unittest.main()
