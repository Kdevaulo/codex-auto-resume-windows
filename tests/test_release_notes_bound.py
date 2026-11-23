"""A release body over 100,000 characters is refused before anything is published (v0.6.26, audit4 F4).

The car-release checklist held release bodies under 100,000 characters by hand (`release_notes.py X.Y.Z | wc -c`); the
script wrote any length, and release.yml published whatever it wrote, so the first thing to stop a long body was GitHub's
own refusal at 125,000, at the publish step. build/release_notes.py now refuses a body over BODY_MAX and exits 1, and
the release workflow's notes step runs it, before the job that publishes. A changelog is written for each case in a
scratch folder; the repository's own is only read, to show every published entry is under the bound.
"""
from __future__ import annotations

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


def changelog(body_length: int) -> str:
    """A changelog whose entry for VERSION makes a release body of exactly `body_length` characters."""
    head = "# Changelog\n\n## v%s - test\n\n> **A test.** One sentence.\n\n" % VERSION
    tail = "\n\n## v9.9.8 - before\n\n> **Before.** One sentence.\n"
    entry = "> **A test.** One sentence.\n\n"
    fixed = len(release_notes.download_block(VERSION)) + 1 + len(entry)
    return head + "x" * (body_length - fixed) + tail


class BoundTests(unittest.TestCase):
    def test_the_bound_is_one_hundred_thousand(self):
        self.assertEqual(release_notes.BODY_MAX, 100000)

    def test_a_body_at_the_bound_is_written_and_one_over_is_refused(self):
        self.assertEqual(len(release_notes.notes(changelog(100000), VERSION)), 100000)
        with self.assertRaises(ValueError) as refused:
            release_notes.notes(changelog(100001), VERSION)
        self.assertIn("100001", str(refused.exception))

    def test_the_command_exits_1_and_writes_nothing_for_a_body_over_the_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            log, out = Path(folder, "CHANGELOG.md"), Path(folder, "release-notes.md")
            log.write_text(changelog(100001), encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "build" / "release_notes.py"), VERSION, "--changelog",
                                   str(log), "--output", str(out)], capture_output=True, text=True, encoding="utf-8",
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertEqual(done.returncode, 1, done.stderr)
            self.assertIn("over the 100000", done.stderr)
            self.assertFalse(out.exists(), "no notes file for the workflow to publish")
            log.write_text(changelog(100000), encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "build" / "release_notes.py"), VERSION, "--changelog",
                                   str(log), "--output", str(out)], capture_output=True, text=True, encoding="utf-8",
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_workflow_makes_the_notes_with_it_before_it_publishes(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        made = workflow.index('python build/release_notes.py "$env:VERSION" --output build/dist/release-notes.md')
        self.assertLess(made, workflow.index("gh release create"))

    def test_every_published_entry_is_under_the_bound(self):
        text = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
        for version in re.findall(r"(?m)^## v(\d+\.\d+\.\d+(?:-[\w.]+)?)\b", text):
            with self.subTest(version=version):
                release_notes.notes(text, version)


if __name__ == "__main__":
    unittest.main()
