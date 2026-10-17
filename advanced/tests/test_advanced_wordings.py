"""The wrap-up's Custom wording (v0.6.16-beta.4, item (b) of the owner's additions to issue #29): a person's own words
for each window, kept in the advanced state's `wordings`, checked as the custom continuation text is, never logged,
and sent with the numbers filled in.

    PYTHONPATH=src;advanced/src python -m unittest discover -s advanced/tests -p test_advanced_wordings.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase as ac  # noqa: E402
from codex_auto_resume_advanced import registry, surfaces  # noqa: E402
from codex_auto_resume_advanced.engine import wrapwords  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Actor, Refusal, WordingKey  # noqa: E402

FIVE, WEEKLY = WordingKey.WRAP_CUSTOM_FIVE_HOUR, WordingKey.WRAP_CUSTOM_WEEKLY


class CheckTests(unittest.TestCase):
    def test_the_custom_text_rules_and_the_four_placeholders(self):
        self.assertEqual(wrapwords.check_custom("Stop at {stop_at}% of {window}; {percent} used, resets {reset}."),
                         "Stop at {stop_at}% of {window}; {percent} used, resets {reset}.")
        for text, code in (("", "empty"), ("   ", "empty"), (None, "empty"), ("x" * 2001, "too_long"),
                           ("a\x00b", "control"), ("see [codex-auto-resume:00ff]", "marker"),
                           ("{prompt}", "placeholder"), ("a { b", "placeholder"), ("a } b", "placeholder")):
            with self.subTest(text=repr(text)[:20]):
                with self.assertRaises(wrapwords.WordingError) as raised:
                    wrapwords.check_custom(text)
                self.assertEqual(raised.exception.code, code)

    def test_custom_is_filled_in_and_a_window_without_words_gets_the_standard(self):
        filled = wrapwords.render(style=wrapwords.CUSTOM_STYLE, minutes=300, used=91.2, stop_at=95, locale="en",
                                  reset_at=None, custom="Used {percent}% of {window}, stop at {stop_at}%.{reset}")
        self.assertEqual(filled, "Used 91% of the five-hour limit, stop at 95%.")
        standard = wrapwords.render(style=wrapwords.CUSTOM_STYLE, minutes=300, used=91, stop_at=95, locale="en",
                                    custom=None)
        self.assertEqual(standard, wrapwords.render(style=2, minutes=300, used=91, stop_at=95, locale="en"))


class SettingTests(ac.AdvancedCase):
    def setUp(self):
        super().setUp()
        self.rt = self.runtime(*registry.REGISTRY)

    def set(self, key, words, **changes):
        request = dict(generation=self.rt.state.meta()["generation"], actor=Actor.DASHBOARD)
        request.update(changes)
        return self.rt.arming.set_wording("usage_wrap_up", key, words, **request)

    def test_set_read_and_taken_away_the_dashboards_alone(self):
        self.assertTrue(self.set(FIVE, "Wrap up at {percent}%.")["done"])
        self.assertEqual(self.rt.state.wordings("usage_wrap_up"), {FIVE: "Wrap up at {percent}%."})
        view = self.rt.arming.wordings_view("usage_wrap_up")
        self.assertEqual(view["wordings"], {str(FIVE): "Wrap up at {percent}%.", str(WEEKLY): None})
        self.assertEqual((view["limit"], view["placeholders"]), (2000, ["percent", "window", "stop_at", "reset"]))
        self.assertTrue(self.set(FIVE, None)["done"])
        self.assertEqual(self.rt.state.wordings("usage_wrap_up"), {})
        self.assertEqual(self.set(FIVE, "x", actor=Actor.MCP)["refusal"], Refusal.NOT_THE_DASHBOARD)
        self.assertEqual(self.set(FIVE, "x", generation=-1)["refusal"], Refusal.STALE_GENERATION)
        self.assertEqual(self.rt.arming.set_wording("usage_meter", FIVE, "x", generation=0,
                                                    actor=Actor.DASHBOARD)["refusal"], Refusal.WORDING_INVALID)
        self.assertEqual(self.rt.arming.wordings_view("usage_meter")["refusal"], Refusal.UNKNOWN_CAPABILITY)

    def test_a_refusal_names_the_check_and_writes_nothing(self):
        for words, problem in (("{x}", "placeholder"), ("y" * 2001, "too_long"), ("a\x01", "control")):
            with self.subTest(problem):
                found = self.set(WEEKLY, words)
                self.assertEqual((found["refusal"], found["problem"]), (Refusal.WORDING_INVALID, problem))
        self.assertEqual(self.rt.state.wordings("usage_wrap_up"), {})

    def test_the_words_are_never_logged(self):
        secret = "Only mine: wrap up gently {percent}"
        self.assertTrue(self.set(FIVE, secret)["done"])
        self.assertNotIn("gently", repr(self.rt.state.journal()))
        self.assertNotIn("gently", repr(surfaces.answer(self.rt, "diagnostics", {})))
        listing = surfaces.answer(self.rt, "mcp", {"request": "call", "tool": "list_advanced_capabilities",
                                                   "arguments": {}})
        self.assertNotIn("gently", repr(listing))

    def test_through_the_bridge(self):
        found = surfaces.answer(self.rt, "bridge", {"command": "advanced-wording", "argument": {
            "capability": "usage_wrap_up", "key": str(WEEKLY), "words": "Weekly {window}",
            "generation": self.rt.state.meta()["generation"]}})
        self.assertTrue(found["done"], found)
        read = surfaces.answer(self.rt, "bridge", {"command": "advanced-wordings",
                                                   "argument": {"capability": "usage_wrap_up"}})
        self.assertEqual(read["wordings"][str(WEEKLY)], "Weekly {window}")



if __name__ == "__main__":
    unittest.main()
