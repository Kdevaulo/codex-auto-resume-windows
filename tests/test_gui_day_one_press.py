r"""v0.6.24: one press on the version's pill on a special day says that day's sentence (the owner, 2026-11-17/18, the Words
board, approved as proposed) - "새해에도 끊기면 제가 이어 둘게요. 올해도 잘 부탁해요." on the first of January, and so on for
seollal, the birthday, chuseok and Christmas - where every other day it says status.aside. In a picture or a probe without
a probe date (DayArt.On off) it is the ordinary sentence on any date.

The window compiled with a probe (tests/dayeggprobe.py), never shown, on the probe's own date (DayArt.Clock). GUI test
module (it makes windows, never shown): run on its own, through gui_lock.sh.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import dayeggprobe  # noqa: E402
import guiscan  # noqa: E402

BODY = r"""
                        Wait(2000);
                        form.detail.Text = "The line's own words";
                        Press();
                        at["one"] = Words();
                        at["sentence"] = S("status.aside_day_" + pair.Key);
                        at["ordinary"] = S("status.aside");
                        // A picture or a probe without a probe date: no day at all.
                        DayArt.On = false;
                        Wait(2000);
                        Press();
                        at["notOn"] = Words();
"""

# The owner's Korean, exactly.
KOREAN = {"new_year": "새해에도 끊기면 제가 이어 둘게요. 올해도 잘 부탁해요.",
          "seollal": "새해 복 많이 받으세요. 끊겨도 제가 이어 둘게요.",
          "birthday": "오늘은 제 생일이에요. 함께해 주셔서 고마워요.",
          "chuseok": "풍성한 한가위 보내세요. 쉬는 동안 끊겨도 제가 이어 둘게요.",
          "christmas": "메리 크리스마스! 끊겨도 제가 이어 둘게요."}
ENGLISH = {"new_year": "A new year, the same promise: if it stops, I'll pick it up.",
           "seollal": "Happy Lunar New Year. If it stops, I'll pick it up.",
           "birthday": "It's my birthday today. Thank you for keeping me around.",
           "chuseok": "Happy Chuseok. Rest well; if it stops, I'll pick it up.",
           "christmas": "Merry Christmas. If it stops, I'll pick it up."}


@unittest.skipUnless(dayeggprobe.CSC.is_file(), "needs the in-box C# compiler")
class DayOnePressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.failure, cls.answer = None, {}
        try:
            cls.answer = dayeggprobe.run(BODY)
        except AssertionError as error:
            cls.failure = str(error)

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_a_special_days_one_press_says_that_days_sentence(self):
        for locale, days in self.answer.items():
            for day, at in days.items():
                if day == "ordinary":
                    continue
                with self.subTest(locale=locale, day=day):
                    self.assertTrue(at["sentence"], "the sentence is in the catalog")
                    self.assertEqual(at["one"], at["sentence"])
                    self.assertNotEqual(at["one"], at["ordinary"])

    def test_an_ordinary_day_says_status_aside(self):
        for locale, days in self.answer.items():
            with self.subTest(locale=locale):
                self.assertEqual(days["ordinary"]["one"], days["ordinary"]["ordinary"])

    def test_without_a_probe_date_every_day_is_ordinary(self):
        for locale, days in self.answer.items():
            for day, at in days.items():
                with self.subTest(locale=locale, day=day):
                    self.assertEqual(at["notOn"], at["ordinary"])

    def test_the_owners_words(self):
        for day, words in KOREAN.items():
            self.assertEqual(self.answer["ko"][day]["one"], words, day)
            self.assertEqual(self.answer["en"][day]["one"], ENGLISH[day], day)


class DayOnePressCatalogTests(unittest.TestCase):
    def test_every_catalog_has_the_five_sentences(self):
        for path in sorted((ROOT / "src/codex_auto_resume/locales").glob("*.json")):
            catalog = json.loads(path.read_text(encoding="utf-8"))
            for day in KOREAN:
                with self.subTest(path.name, day=day):
                    self.assertTrue(catalog.get("status.aside_day_" + day), path.name)

    def test_the_press_asks_the_day_and_keeps_the_ordinary_sentence(self):
        body = guiscan.member_body("SettingsForm", "VersionPressed")
        self.assertIn('S("status.aside_day_" + day,', body)
        self.assertIn('detail.Aside(S("status.aside",', body)


if __name__ == "__main__":
    unittest.main()
