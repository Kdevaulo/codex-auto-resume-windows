"""Every release says what kind of release it is, in the line right under its title line.

The owner asked (2026-11-18) that every release say its nature - a bug fix, a feature change, a new feature, a
new design, a design change - and chose: the kind goes on a line right under the top aim line, every kind that
applies is listed, biggest first, and every published release carries it. So the second paragraph of every
`## vX.Y.Z[-suffix] - headline` entry is

    **Kind:** New features · Design changes · Bug fixes          (docs/CHANGELOG.md)
    **성격:** 기능 추가 · 디자인 수정 · 버그 수정                  (docs/CHANGELOG.ko.md, the twin words)

and the words come from one table, `build/release_notes.py` KINDS (English word -> Korean word).

* VocabularyTests - the table is the fixed list of nine, each word has one twin, and nothing else is a kind.
* EntryLineTests - every entry of both changelogs has the line, as its second paragraph, once.
* KindsTests - every entry's line reads (only words from the table, none twice), and the English and the Korean
  entry name the same kinds in the same order.
* KindsCommandTests - `release_notes.kinds` reads either language, gives English words back and refuses what is
  not in the table, a repeat, a missing line and a line that is not the second paragraph; the notes a release is
  published with carry the line, and `--title` is what it was.

On the generated ko branch docs/CHANGELOG.md is the Korean text; what is English there is not asked.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import languages

ROOT = Path(__file__).resolve().parent.parent
NOTES_SCRIPT = ROOT / "build" / "release_notes.py"
EN = ROOT / "docs" / "CHANGELOG.md"
KO = ROOT / "docs" / "CHANGELOG.ko.md"

DASH = "—"
HEADING = re.compile(r"^## v(\S+) " + DASH + " ", re.MULTILINE)
EXPECTED = {
    "New features": "기능 추가",
    "Feature changes": "기능 수정",
    "Bug fixes": "버그 수정",
    "New design": "디자인 추가",
    "Design changes": "디자인 수정",
    "Performance": "성능 개선",
    "Security": "보안 수정",
    "Languages": "언어·번역",
    "Under the hood": "내부 정리",
}


def _load_notes():
    spec = importlib.util.spec_from_file_location("release_notes_kinds", NOTES_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(NOTES_SCRIPT.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(NOTES_SCRIPT.parent))
    return module


notes = _load_notes()


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _versions(text: str) -> list:
    return [m.group(1) for m in HEADING.finditer(text)]


def _second_paragraph(text: str, version: str) -> str:
    paragraphs = re.split(r"\n\s*\n", notes.section(text, version))
    return paragraphs[1].strip() if len(paragraphs) > 1 else ""


def _english_changelog_is_english() -> bool:
    return not languages.generated_ko_branch()


class VocabularyTests(unittest.TestCase):
    def test_the_table_is_the_fixed_list_of_nine(self):
        self.assertEqual(notes.KINDS, EXPECTED)
        self.assertEqual(list(notes.KINDS), list(EXPECTED), "the order is the owner's list")

    def test_every_word_has_one_twin_and_no_word_is_both_languages(self):
        english, korean = list(notes.KINDS), list(notes.KINDS.values())
        self.assertEqual(len(set(english)), len(english))
        self.assertEqual(len(set(korean)), len(korean))
        self.assertEqual(set(english) & set(korean), set())
        for word in english + korean:
            self.assertEqual(word, word.strip())
            self.assertNotIn(notes.KIND_SEPARATOR, word)

    def test_the_separator_is_a_middle_dot_between_spaces(self):
        self.assertEqual(notes.KIND_SEPARATOR, " · ")


class EntryLineTests(unittest.TestCase):
    @unittest.skipUnless(_english_changelog_is_english(), "docs/CHANGELOG.md is the Korean text on the ko branch")
    def test_every_english_entry_has_its_kind_line_as_the_second_paragraph(self):
        text = _text(EN)
        versions = _versions(text)
        self.assertGreaterEqual(len(versions), 69)
        wrong = [v for v in versions if not _second_paragraph(text, v).startswith("**Kind:** ")]
        self.assertEqual(wrong, [], "entries whose second paragraph is not '**Kind:** A · B'")

    @unittest.skipUnless(languages.both_languages(), "the Korean changelog is on dev only")
    def test_every_korean_entry_has_its_kind_line_as_the_second_paragraph(self):
        text = _text(KO)
        versions = _versions(text)
        self.assertGreaterEqual(len(versions), 69)
        wrong = [v for v in versions if not _second_paragraph(text, v).startswith("**성격:** ")]
        self.assertEqual(wrong, [], "entries whose second paragraph is not '**성격:** 가 · 나'")

    def test_the_line_stands_under_the_title_line_and_is_one_line_alone_in_its_paragraph(self):
        for path in (EN, KO):
            if path is KO and not languages.both_languages():
                continue
            text = _text(path)
            for version in _versions(text):
                body = notes.section(text, version).split("\n\n")
                self.assertTrue(body[0].startswith("> **"), (path.name, version))
                self.assertNotIn("\n", body[1], (path.name, version))
                self.assertEqual(len(re.findall(r"^\*\*(?:Kind|성격):\*\*", notes.section(text, version),
                                                re.MULTILINE)), 1, (path.name, version))

    @unittest.skipUnless(languages.both_languages(), "the Korean changelog is on dev only")
    def test_both_changelogs_list_the_same_versions(self):
        self.assertEqual(_versions(_text(EN)), _versions(_text(KO)))


class KindsTests(unittest.TestCase):
    def test_every_entry_names_only_words_of_the_table_and_none_twice(self):
        for path in (EN, KO):
            if path is KO and not languages.both_languages():
                continue
            text = _text(path)
            for version in _versions(text):
                found = notes.kinds(text, version)
                self.assertGreaterEqual(len(found), 1, (path.name, version))
                self.assertEqual(len(set(found)), len(found), (path.name, version))
                for name in found:
                    self.assertIn(name, notes.KINDS, (path.name, version))

    @unittest.skipUnless(languages.both_languages(), "the Korean changelog is on dev only")
    def test_english_and_korean_name_the_same_kinds_in_the_same_order(self):
        english, korean = _text(EN), _text(KO)
        for version in _versions(english):
            self.assertEqual(notes.kinds(english, version), notes.kinds(korean, version), version)
            words_en = _second_paragraph(english, version).split(":** ", 1)[1].split(notes.KIND_SEPARATOR)
            words_ko = _second_paragraph(korean, version).split(":** ", 1)[1].split(notes.KIND_SEPARATOR)
            self.assertEqual([notes.KINDS[word] for word in words_en], words_ko, version)

    def test_a_release_of_only_fixes_says_so_and_a_final_covers_its_whole_line(self):
        # Spot checks the owner can read: v0.6.15 and v0.6.2 are fixes alone; v0.6.23's final lists what its
        # betas did, a language among them; v0.6.3 brought the neumorphic design.
        # docs/CHANGELOG.md on every branch: on ko it is the Korean text (no CHANGELOG.ko.md there), whose Korean kind
        # lines the reader gives back as the same English words.
        english = _text(EN)
        self.assertEqual(notes.kinds(english, "0.6.15"), ["Bug fixes"])
        self.assertEqual(notes.kinds(english, "0.6.2"), ["Bug fixes"])
        self.assertEqual(notes.kinds(english, "0.5.7"), ["Security"])
        self.assertEqual(notes.kinds(english, "0.6.12-alpha"), ["Under the hood"])
        self.assertIn("Languages", notes.kinds(english, "0.6.23"))
        self.assertIn("Performance", notes.kinds(english, "0.6.23"))
        self.assertEqual(notes.kinds(english, "0.6.3")[0], "New design")


class KindsCommandTests(unittest.TestCase):
    SAMPLE = ("# Changelog\n\n"
              "## v9.9.9 " + DASH + " A headline\n\n"
              "> **A made-up title.** This one sets out to prove the line is read.\n\n"
              "**Kind:** New features · Bug fixes\n\n"
              "[The commits in this release](https://example.invalid)\n\nBody.\n\n"
              "## v9.9.9-beta " + DASH + " The beta\n\n"
              "> **The beta's title.** Its own sentence.\n\n"
              "**Kind:** Under the hood\n\nBody.\n\n"
              "## v9.9.8 " + DASH + " Korean\n\n"
              "> **한 제목.** 한 문장입니다.\n\n"
              "**성격:** 디자인 추가 · 성능 개선\n\nBody.\n")

    def _with(self, old: str, new: str, version: str = "9.9.9") -> str:
        text = self.SAMPLE.replace(old, new)
        self.assertNotEqual(text, self.SAMPLE)
        return text

    def test_the_kinds_are_read_in_the_order_written(self):
        self.assertEqual(notes.kinds(self.SAMPLE, "9.9.9"), ["New features", "Bug fixes"])
        self.assertEqual(notes.kinds(self.SAMPLE, "v9.9.9"), ["New features", "Bug fixes"])

    def test_a_pre_release_reads_its_own_entry(self):
        self.assertEqual(notes.kinds(self.SAMPLE, "9.9.9-beta"), ["Under the hood"])

    def test_a_korean_line_is_given_back_as_english_words(self):
        self.assertEqual(notes.kinds(self.SAMPLE, "9.9.8"), ["New design", "Performance"])

    def test_a_word_that_is_not_in_the_table_is_refused(self):
        text = self._with("**Kind:** New features · Bug fixes", "**Kind:** New features · Cleanups")
        with self.assertRaises(SystemExit) as stopped:
            notes.kinds(text, "9.9.9")
        self.assertIn("Cleanups", str(stopped.exception))
        self.assertIn("not one of", str(stopped.exception))

    def test_the_other_languages_word_is_refused(self):
        text = self._with("**Kind:** New features · Bug fixes", "**Kind:** New features · 버그 수정")
        with self.assertRaises(SystemExit):
            notes.kinds(text, "9.9.9")
        korean = self._with("**성격:** 디자인 추가 · 성능 개선", "**성격:** 디자인 추가 · Performance")
        with self.assertRaises(SystemExit):
            notes.kinds(korean, "9.9.8")

    def test_a_kind_named_twice_is_refused(self):
        text = self._with("**Kind:** New features · Bug fixes", "**Kind:** Bug fixes · Bug fixes")
        with self.assertRaises(SystemExit) as stopped:
            notes.kinds(text, "9.9.9")
        self.assertIn("twice", str(stopped.exception))

    def test_an_entry_without_the_line_is_refused(self):
        text = self._with("**Kind:** New features · Bug fixes\n\n", "")
        with self.assertRaises(SystemExit) as stopped:
            notes.kinds(text, "9.9.9")
        self.assertIn("no kind line", str(stopped.exception))

    def test_a_line_that_is_not_the_second_paragraph_is_not_found(self):
        text = self._with("**Kind:** New features · Bug fixes\n\n[The commits in this release](https://example.invalid)",
                          "[The commits in this release](https://example.invalid)\n\n**Kind:** New features")
        with self.assertRaises(SystemExit):
            notes.kinds(text, "9.9.9")

    def test_an_empty_line_is_refused(self):
        text = self._with("**Kind:** New features · Bug fixes", "**Kind:** ")
        with self.assertRaises(SystemExit):
            notes.kinds(text, "9.9.9")

    def test_a_version_with_no_entry_fails(self):
        with self.assertRaises(SystemExit):
            notes.kinds(self.SAMPLE, "1.2.3")

    def test_a_windows_line_ending_is_read_too(self):
        self.assertEqual(notes.kinds(self.SAMPLE.replace("\n", "\r\n"), "9.9.9"), ["New features", "Bug fixes"])

    def test_the_notes_a_release_is_published_with_carry_the_line_after_the_title_line(self):
        body = notes.notes(self.SAMPLE, "9.9.9")
        self.assertIn("> **A made-up title.** This one sets out to prove the line is read.\n\n"
                      "**Kind:** New features · Bug fixes\n", body)

    def test_the_title_command_is_unchanged_by_the_line(self):
        with tempfile.TemporaryDirectory() as scratch:
            changelog = Path(scratch) / "CHANGELOG.md"
            changelog.write_text(self.SAMPLE, encoding="utf-8")
            done = subprocess.run([sys.executable, str(NOTES_SCRIPT), "9.9.9", "--title", "--changelog",
                                   str(changelog)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "v9.9.9 " + DASH + " A made-up title")

    def test_rebasing_the_notes_keeps_the_line(self):
        line = "**Kind:** New features · Bug fixes"
        self.assertEqual(notes.rebase(line), line)
        self.assertEqual(notes.rebase(_second_paragraph(self.SAMPLE, "9.9.9")), line)

    def test_the_real_notes_carry_each_entrys_line(self):
        text = _text(EN)
        for version in _versions(text)[:8]:
            line = _second_paragraph(text, version)
            self.assertIn("\n\n" + line + "\n", notes.notes(text, version), version)


if __name__ == "__main__":
    unittest.main()
