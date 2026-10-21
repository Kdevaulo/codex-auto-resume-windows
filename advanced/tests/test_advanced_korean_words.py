"""The advanced edition's Korean catalog calls the watcher what the product's catalog calls it (v0.6.18).

The owner's rule: the product's catalogs say 워처 for the watcher (src/codex_auto_resume/locales/ko.json), and the
advanced catalog is the product's too - a person reads its statements beside the window's words. The Korean documents
keep 감시기, and are not held here.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT / "advanced" / "src", ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from codex_auto_resume_advanced import statement  # noqa: E402

OTHER_WORDS = ("감시자", "감시기")


def catalog(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class WatcherWordTests(unittest.TestCase):
    def test_the_advanced_korean_catalog_says_워처_and_never_another_word(self):
        table = catalog(statement.DIRECTORY / "ko.json")
        for key, text in table.items():
            for word in OTHER_WORDS:
                with self.subTest(key=key, word=word):
                    self.assertNotIn(word, text)
        self.assertTrue(any("워처" in text for text in table.values()))

    def test_the_product_s_own_catalog_is_the_rule_it_follows(self):
        table = catalog(ROOT / "src" / "codex_auto_resume" / "locales" / "ko.json")
        self.assertTrue(any("워처" in text for text in table.values()))
        self.assertFalse(any(word in text for text in table.values() for word in OTHER_WORDS))


if __name__ == "__main__":
    unittest.main()
