"""Which advanced surfaces say what is LEFT of a usage window, and which say what is USED (the owner, 2026-11-18).

The owner first asked for what is left everywhere ("다 바꾸자"), then drew the line: a place for an at-a-glance "may I
keep going?" says what is left; a place about pace, history, diagnosis or the limits a person sets says what is used.
Here, in every language the advanced catalogs carry:

- left: the saved accounts' meters' words, the analytics card's reading of a window and when none would be left;
- used: the limits a person sets (Warn at, Wrap up at, Pause at, Ask to stop at, "85%"), the statements that explain
  them (85%, 90% and 97% by default) and the analytics' change over the last hour.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;tests" python -m unittest discover -s advanced/tests -p test_advanced_usage_word_split.py
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

LOCALES = Path(__file__).resolve().parents[1] / "src" / "codex_auto_resume_advanced" / "locales"


def catalogs():
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted(LOCALES.glob("*.json"))}


class StatementTests(unittest.TestCase):
    def test_the_statements_say_the_limits_as_the_share_used(self):
        """The warning, the wrap-up and the stop at the share used they act at, 85, 90 and 97 by default - never the
        share left (15, 10, 3) that the at-a-glance surfaces say."""
        found = catalogs()
        self.assertEqual(len(found), 22)
        english = found["en"]
        self.assertIn("reaches the percentage you set for a warning (85% by default,", english["statement.usage_meter.does"])
        self.assertIn("reaches the wrap-up percentage you set (90% by default,", english["statement.usage_wrap_up.does"])
        self.assertIn("reaches the stop percentage you set (97% by default,", english["statement.usage_pause.does"])
        self.assertIn("reaches its stop percentage", english["page.pause_limits"])
        for locale, table in found.items():
            with self.subTest(locale=locale):
                self.assertIn("85", table["statement.usage_meter.does"])
                self.assertIn("90", table["statement.usage_wrap_up.does"])
                self.assertIn("97", table["statement.usage_pause.does"])
                for key in ("statement.usage_meter.does", "statement.usage_wrap_up.does", "statement.usage_pause.does"):
                    self.assertNotIn("left by default", table[key])


class ThresholdTests(unittest.TestCase):
    def test_the_limits_a_person_sets_are_said_as_the_share_used(self):
        """"Warn at (5-hour window)" with "85%": the share used each acts at, in the same number the engine keeps - no
        word for "left" in any language's labels, values or the wrap-up's preview headings."""
        found = catalogs()
        english = found["en"]
        self.assertEqual(english["page.option.percent"], "{n}%")
        self.assertEqual(english["page.option.warn_five_hour"], "Warn at (5-hour window)")
        self.assertEqual(english["page.preview.300"], "When the five-hour window reaches it:")
        left_words = {"en": "left", "ko": "남", "de": "übrig", "fr": "rest", "ja": "残り", "zh-CN": "剩余", "zh-TW": "剩餘",
                      "ru": "остал", "es": "qued", "tr": "kal"}
        keys = ["page.option.percent", "page.preview.300", "page.preview.10080"] + [
            "page.option.%s_%s" % (name, window) for name in ("warn", "wrap", "pause", "stop_words")
            for window in ("five_hour", "weekly")]
        for locale, table in found.items():
            for key in keys:
                with self.subTest(locale=locale, key=key):
                    if locale in left_words:
                        self.assertNotIn(left_words[locale], table[key].lower())
                    if key == "page.option.percent":
                        self.assertEqual(table[key].replace("{n}", "").replace(" ", "").replace(" ", ""), "%")


if __name__ == "__main__":
    unittest.main()
