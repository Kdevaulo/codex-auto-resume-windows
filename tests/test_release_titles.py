"""Every release has a short title, and its notes open with one sentence on what it set out to do.

The owner asked (2026-11-17) that every release say what release it is, and what it focused on, at the top.
The changelog is the one place release notes are written, so both live there: the first paragraph of every
`## vX.Y.Z[-suffix] - headline` entry is

    > **Short title.** One sentence on what this release set out to do.

in `docs/CHANGELOG.md` and, in the same words in Korean, `docs/CHANGELOG.ko.md`. `build/release_notes.py
--title` reads it and prints the release's title - `vX.Y.Z[-suffix] - Short title` - and release.yml
publishes the release under that title instead of the bare version.

* EntryLineTests - every entry of both changelogs opens with the line, and the two files list the same versions.
* LimitTests - a title is 3-8 words (English) and at most 60 characters; the sentence is about one line.
* TitleCommandTests - `release_notes.py --title` prints the title for a version, fails loudly for an entry
  without the line, and the notes it prints for a version still open with that line.
* WorkflowTests - release.yml builds the title with `--title`, carries it in the build artifact and publishes
  under it.

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
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
EN = ROOT / "docs" / "CHANGELOG.md"
KO = ROOT / "docs" / "CHANGELOG.ko.md"

DASH = "—"
HEADING = re.compile(r"^## v(\S+) " + DASH + " ", re.MULTILINE)


def _load_notes():
    spec = importlib.util.spec_from_file_location("release_notes_titles", NOTES_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(NOTES_SCRIPT.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(NOTES_SCRIPT.parent))
    return module


notes = _load_notes()


def _entries(path: Path) -> dict[str, str]:
    """version -> the entry's first paragraph's first line (the line right under the heading)."""
    text = path.read_text(encoding="utf-8")
    found = {}
    marks = list(HEADING.finditer(text))
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        body = text[mark.end():end].split("\n", 1)[1] if "\n" in text[mark.end():end] else ""
        lines = [line for line in body.splitlines() if line.strip()]
        found[mark.group(1)] = lines[0] if lines else ""
    return found


def _changelogs():
    files = [EN]
    if languages.both_languages():
        files.append(KO)
    return files


def _parts(line: str):
    found = notes.LEAD.match(line)
    return (found.group(1), line[found.end() - 1:]) if found else (None, None)


class EntryLineTests(unittest.TestCase):
    def test_every_entry_opens_with_its_title_line(self):
        for path in _changelogs():
            entries = _entries(path)
            self.assertGreaterEqual(len(entries), 69, path.name)
            missing = [version for version, line in entries.items() if notes.LEAD.match(line) is None]
            self.assertEqual(missing, [], "%s: entries that do not open with '> **Title.** Sentence.'" % path.name)

    def test_the_line_is_the_first_paragraph_before_anything_else(self):
        # Under the heading, ahead of the compare link and the pre-release paragraph.
        text = EN.read_text(encoding="utf-8")
        for mark in HEADING.finditer(text):
            after = text[mark.end():].split("\n", 1)[1]
            self.assertTrue(after.startswith("\n> **"), mark.group(0))

    @unittest.skipUnless(languages.both_languages(), "the Korean changelog is on dev only")
    def test_english_and_korean_list_the_same_versions_in_the_same_order(self):
        english = [m.group(1) for m in HEADING.finditer(EN.read_text(encoding="utf-8"))]
        korean = [m.group(1) for m in HEADING.finditer(KO.read_text(encoding="utf-8"))]
        self.assertEqual(english, korean)
        self.assertEqual(len(set(english)), len(english))


class LimitTests(unittest.TestCase):
    def test_a_title_and_its_sentence_stay_short(self):
        for path in _changelogs():
            for version, line in _entries(path).items():
                title, sentence = _parts(line)
                self.assertIsNotNone(title, (path.name, version))
                self.assertLessEqual(len(title), 60, (path.name, version, title))
                self.assertFalse(title.endswith("."), (path.name, version, title))
                self.assertLessEqual(len(sentence.strip()), 220, (path.name, version, len(sentence)))
                self.assertGreater(len(sentence.strip()), 20, (path.name, version))
                self.assertTrue(sentence.strip().endswith("."),(path.name, version, sentence))

    @unittest.skipIf(languages.generated_ko_branch(), "docs/CHANGELOG.md is the Korean text on the ko branch")
    def test_an_english_title_is_three_to_eight_words(self):
        for version, line in _entries(EN).items():
            title, _ = _parts(line)
            self.assertIn(len(title.split()), range(3, 9), (version, title))
            self.assertTrue(title[0].isupper(), (version, title))

    def test_no_title_or_sentence_names_what_the_public_text_never_names(self):
        # Internal names and owner-only words stay out of public text (owner 2026-11-08, 2026-11-17).
        forbidden = re.compile(r"WindowCorner|\bDWM\b|\bseat\b|\bthe owner\b|easter|이스터", re.IGNORECASE)
        for path in _changelogs():
            for version, line in _entries(path).items():
                self.assertIsNone(forbidden.search(line), (path.name, version, line))


class TitleCommandTests(unittest.TestCase):
    SAMPLE = ("# Changelog\n\n"
              "## v9.9.9 " + DASH + " A long headline, with a list of things\n\n"
              "> **A made-up title.** This one sets out to prove the line is read.\n\n"
              "[The commits in this release](https://example.invalid)\n\nBody.\n\n"
              "## v9.9.9-beta " + DASH + " The beta\n\n"
              "> **The beta's title.** Its own sentence.\n\nBody.\n\n"
              "## v9.9.8 " + DASH + " No line here\n\n"
              "[The commits in this release](https://example.invalid)\n\nBody.\n")

    def _run(self, version, text):
        with tempfile.TemporaryDirectory() as scratch:
            changelog = Path(scratch) / "CHANGELOG.md"
            changelog.write_text(text, encoding="utf-8")
            return subprocess.run([sys.executable, str(NOTES_SCRIPT), version, "--title", "--changelog",
                                   str(changelog)], capture_output=True, text=True, encoding="utf-8")

    def test_the_title_is_the_version_and_the_short_title(self):
        done = self._run("9.9.9", self.SAMPLE)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "v9.9.9 " + DASH + " A made-up title")

    def test_a_pre_release_reads_its_own_entry_and_a_leading_v_is_accepted(self):
        done = self._run("v9.9.9-beta", self.SAMPLE)
        self.assertEqual(done.stdout.strip(), "v9.9.9-beta " + DASH + " The beta's title")

    def test_an_entry_without_the_line_fails_loudly(self):
        done = self._run("9.9.8", self.SAMPLE)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("does not open with its title line", done.stderr)
        self.assertEqual(done.stdout, "")

    def test_a_line_that_is_not_the_first_paragraph_is_not_found(self):
        late = self.SAMPLE.replace("[The commits in this release](https://example.invalid)\n\nBody.\n\n## v9.9.9-beta",
                                   "[The commits in this release](https://example.invalid)\n\n"
                                   "> **Too late.** After the link.\n\n## v9.9.9-beta").replace(
            "> **A made-up title.** This one sets out to prove the line is read.\n\n", "")
        done = self._run("9.9.9", late)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("does not open with its title line", done.stderr)

    def test_a_version_with_no_entry_fails(self):
        done = self._run("1.2.3", self.SAMPLE)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("has no section for v1.2.3", done.stderr)

    def test_the_output_option_writes_the_title_alone_with_a_line_feed(self):
        with tempfile.TemporaryDirectory() as scratch:
            changelog = Path(scratch) / "CHANGELOG.md"
            changelog.write_text(self.SAMPLE, encoding="utf-8")
            target = Path(scratch) / "release-title.txt"
            self.assertEqual(notes.main(["9.9.9", "--title", "--changelog", str(changelog),
                                         "--output", str(target)]), 0)
            self.assertEqual(target.read_bytes(), ("v9.9.9 " + DASH + " A made-up title\n").encode("utf-8"))

    def test_the_notes_open_with_the_line_after_the_download_block(self):
        body = notes.notes(self.SAMPLE, "9.9.9")
        rest = body.split("\n\n", 1)[1]
        self.assertTrue(rest.startswith("> **A made-up title.** This one sets out"), rest[:80])

    def test_the_real_notes_open_with_each_entrys_line_and_rebasing_keeps_it(self):
        text = EN.read_text(encoding="utf-8")
        for version in re.findall(r"^## v(\S+) ", text, re.MULTILINE)[:6]:
            line = _entries(EN)[version]
            self.assertIsNotNone(notes.LEAD.match(line), version)
            body = notes.notes(text, version)
            self.assertIn("\n\n" + line + "\n", body, version)
            self.assertEqual(notes.rebase(line), line, version)
            self.assertTrue(notes.section(text, version).startswith(line), version)

    @unittest.skipIf(languages.generated_ko_branch(), "docs/CHANGELOG.md is the Korean text on the ko branch")
    def test_the_published_titles_are_these(self):
        text = EN.read_text(encoding="utf-8")
        wanted = {
            "0.6.24-beta.2": "Dialogs as one card and a shorter Dashboard",
            "0.6.23": "Smaller downloads, smoother controls, more languages",
            "0.6.20": "A status light for every state",
            "0.1.0": "The first public release",
        }
        for version, title in wanted.items():
            self.assertEqual(notes.release_title(text, version), "v%s %s %s" % (version, DASH, title))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_the_build_reads_the_title_from_the_changelog_beside_the_notes(self):
        self.assertRegex(self.text, r'python build/release_notes\.py "\$env:VERSION" --title --output '
                                    r'build/dist/release-title\.txt')
        self.assertIn('--output build/dist/release-notes.md', self.text)

    def test_the_title_travels_in_the_build_artifact(self):
        upload = self.text.split("uses: actions/upload-artifact", 1)[1].split("if-no-files-found", 1)[0]
        self.assertIn("build/dist/release-title.txt", upload)

    def test_the_release_is_published_under_that_title(self):
        publish = self.text.split("name: Publish the GitHub release", 1)[1]
        self.assertIn('title="$(cat dist/release-title.txt)"', publish)
        self.assertIn('--title "$title"', publish)
        self.assertNotIn('--title "v$VERSION"', self.text)
        self.assertNotIn('--title "v$VERSION"', publish)

    def test_a_title_that_does_not_start_with_the_version_stops_the_publish(self):
        publish = self.text.split("name: Publish the GitHub release", 1)[1]
        self.assertIn('[[ "$title" == "v$VERSION "* ]]', publish)
        self.assertLess(publish.index('[[ "$title" == "v$VERSION "* ]]'), publish.index("gh release create"))


if __name__ == "__main__":
    unittest.main()
