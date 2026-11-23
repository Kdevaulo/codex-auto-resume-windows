"""A release body that describes a hidden press, or names a special day inflected or spelled apart, is refused too
(v0.6.26, review R2).

ceb426f47 refused the code's own words - DAY_LOOKS' names and colours, the status.aside keys and sentences - but let
"Press the version text six times", "a hidden easter egg", "Confetti falls", "Christmases" and "Seol-lal" through.
build/release_notes.py now also refuses the press described (PRESS_PATTERNS, from gui/SoftEggs.cs), each day's name with
its letters spelled apart, plural or possessive, and the Korean day names with their particles. Every entry of both
changelogs still passes, and the ordinary words real entries use ("six hours", "the sixth page", "hidden", "pressed",
"여섯 번 열 때", "발생일") are not refused.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "build") not in sys.path:
    sys.path.insert(0, str(ROOT / "build"))

import release_notes  # noqa: E402

VERSION = "9.9.9"


def refused(sentence):
    text = ("# Changelog\n\n## v%s - test\n\n> **A test.** One sentence.\n\n%s\n\n## v9.9.8 - before\n\n"
            "> **Before.** One sentence.\n" % (VERSION, sentence))
    try:
        release_notes.notes(text, VERSION)
    except ValueError as refusal:
        return str(refusal)
    return None


class FormTests(unittest.TestCase):
    def test_the_reviews_inputs_are_refused(self):
        for sentence in ("Press the version text six times for a surprise.",
                         "A hidden easter egg: the status light sweeps through four colours.",
                         "Confetti falls when you find it.", "Christmases", "Seol-lal"):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(refused(sentence))

    def test_close_forms_of_the_days_and_the_press_are_refused(self):
        for sentence in ("two Birthdays", "happy new years", "NewYear look", "chu-seok", "Easter-Eggs", "an egg",
                         "the sixth press plays one", "pressing the version label six", "presses on the version",
                         "six clicks", "추석에 쉬어요", "설날의 장면", "버전을 여섯 번 누르면", "이스터에그를 찾았다",
                         "콘페티가 내려요"):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(refused(sentence))

    def test_the_words_real_entries_need_are_not(self):
        for sentence in ("six hours, the sixth page and six of seven openings", "a hidden row, a surprise, pressed Retry",
                         "Every day, Monday to Friday", "여섯 번 열 때", "한도는 네 번에서 여섯 번이었습니다",
                         "오류 발생일", "숨겨진 창", "eggshell christmastime newyearly"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(refused(sentence))

    def test_every_entry_of_both_changelogs_passes(self):
        for name in ("docs/CHANGELOG.md", "docs/CHANGELOG.ko.md"):
            path = ROOT / name
            if not path.is_file():
                continue                                   # main and the ko branch carry one of them
            text = path.read_text(encoding="utf-8")
            versions = re.findall(r"(?m)^## v(\d+\.\d+\.\d+(?:-[\w.]+)?)\b", text)
            self.assertGreater(len(versions), 50, name)
            for version in versions:
                with self.subTest(name=name, version=version):
                    release_notes.notes(text, version)


if __name__ == "__main__":
    unittest.main()
