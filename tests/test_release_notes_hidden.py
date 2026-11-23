"""A release body that names a special day or a hidden press is refused before anything is published (v0.6.26, audit4 F4).

The special days and the hidden presses stay out of every document and every release note (the owner, 2026-11-16). The
only guard was tests/test_gui_v0623_days.py's five strings, in README, CHANGELOG and GUIDE. build/release_notes.py now
refuses a body naming any word it takes from the code - DAY_LOOKS's days and colours, the status.aside keys and their
sentences in every catalog, and what that test already guards - whole and in any case, exits 1 and writes no file, as it
does over BODY_MAX. Changelogs for the cases are written in a scratch folder; the repository's is only read.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "build") not in sys.path:
    sys.path.insert(0, str(ROOT / "build"))

import release_notes  # noqa: E402

VERSION = "9.9.9"


def changelog(sentence: str) -> str:
    return ("# Changelog\n\n## v%s - test\n\n> **A test.** One sentence.\n\n%s\n\n## v9.9.8 - before\n\n"
            "> **Before.** One sentence.\n" % (VERSION, sentence))


def guarded_by_the_days_test() -> list:
    """The words test_gui_v0623_days.test_no_document_names_it keeps out of the documents, read from its source."""
    tree = ast.parse((ROOT / "tests" / "test_gui_v0623_days.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "test_no_document_names_it":
            for inner in ast.walk(node):
                if isinstance(inner, ast.For) and isinstance(inner.iter, ast.Tuple):
                    return [ast.literal_eval(item) for item in inner.iter.elts]
    raise AssertionError("test_no_document_names_it has moved")


class HiddenWordTests(unittest.TestCase):
    def refused(self, sentence):
        try:
            release_notes.notes(changelog(sentence), VERSION)
        except ValueError as refusal:
            return str(refusal)
        return None

    def test_each_day_is_refused_in_any_case_and_spelling(self):
        for sentence, word in (("The icon dresses up for Christmas.", "christmas"), ("CHUSEOK looks", "chuseok"),
                               ("a Seollal scene", "seollal"), ("on New Year the icon", "new year"),
                               ("the new-year look", "new-year"), ("its birthday cake", "birthday")):
            with self.subTest(sentence=sentence):
                refusal = self.refused(sentence)
                self.assertIsNotNone(refusal)
                self.assertIn(repr(word).lower(), refusal.lower())

    def test_the_presses_sentences_keys_and_colours_are_refused(self):
        catalog = json.loads((ROOT / "src/codex_auto_resume/locales/en.json").read_text(encoding="utf-8"))
        korean = json.loads((ROOT / "src/codex_auto_resume/locales/ko.json").read_text(encoding="utf-8"))
        for sentence in ("`status.aside_egg_seollal` is new", catalog["status.aside_confetti"],
                         "She said: " + korean["status.aside_colours"], "the ground is #9e3a4b now"):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(self.refused(sentence))

    def test_everything_the_days_test_guards_is_refused(self):
        words = guarded_by_the_days_test()
        self.assertGreaterEqual(len(words), 5)
        for word in words:
            with self.subTest(word=word):
                self.assertIsNotNone(self.refused("before %s after" % word))

    def test_ordinary_words_are_not(self):
        for sentence in ("Every day the watcher checks; a press on Retry asks now.", "Monday to Friday, days, pressed",
                         "words with a day inside them: newyearly, christmastime, pressing", "a #EE84689 hash"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(self.refused(sentence))

    def test_the_command_exits_1_says_the_word_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            log, out = Path(folder, "CHANGELOG.md"), Path(folder, "release-notes.md")
            log.write_text(changelog("Snow on Christmas."), encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "build" / "release_notes.py"), VERSION, "--changelog",
                                   str(log), "--output", str(out)], capture_output=True, text=True, encoding="utf-8",
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertEqual(done.returncode, 1, done.stderr)
            self.assertIn("'christmas'", done.stderr.lower())
            self.assertFalse(out.exists())

    def test_every_published_entry_passes(self):
        text = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
        versions = re.findall(r"(?m)^## v(\d+\.\d+\.\d+(?:-[\w.]+)?)\b", text)
        self.assertGreater(len(versions), 50)
        for version in versions:
            with self.subTest(version=version):
                release_notes.notes(text, version)


if __name__ == "__main__":
    unittest.main()
