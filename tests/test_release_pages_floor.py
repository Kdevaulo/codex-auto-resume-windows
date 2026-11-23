r"""Install another version... reads the list of releases only down to $PickFloor (v0.6.26).

Every bootstrap from v0.6.12 to v0.6.25 read at most $PickMaxPages pages of $PickPageSize and
ended only on a page with fewer: once the repository published its 150th release, page 5 came back
full and the picker said `versions: unavailable` on every installation, though nothing below
$PickFloor is ever offered. The list is newest first, so a full page whose last release that counts
is older than the floor ends it, the fifth too; a full fifth page that is still above the floor is
still no answer, and a release older than the floor named out of its place on a page ends nothing.

Get-ReleasePages is lifted out of scripts/bootstrap.ps1 and run with the network a stand-in, as
tests/test_version_picker.py does (its LIFT, with only pages to read); nothing here reaches the
network or the registry.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_version_picker import (BOOTSTRAP, GOOD_FINAL, INSTALLED, LIFT, LISTED, MAX_PAGES, PAGES,  # noqa: E402
                                 POWERSHELL, RELEASE, ROWS, PickerRun, entry, junk, kept, listed)


def full(*versions):
    """A full page: these releases, in this order, after entries the reader passes over."""
    return junk(30 - len(versions)) + [entry(version) for version in versions]


# name -> the pages served, from 1, what Get-ReleasePages gives back (THROWS or the kept entries),
# and how many pages it asked for.
CASES = {
    # The 150th release: five full pages, the fifth reaching below the floor. It is all of it.
    "a_full_fifth_page_past_the_floor": (
        [full("0.6.%d" % (20 - page)) for page in range(1, 5)] + [full("0.6.3", "0.6.1")],
        [kept("0.6.%d" % (20 - page)) for page in range(1, 5)] + [kept("0.6.3"), kept("0.6.1")], 5),
    # A full page past the floor ends the list: no second page is asked for (none is served).
    "a_full_first_page_past_the_floor": ([full("0.6.5", "0.6.2", "0.5.0")],
                                         [kept("0.6.5"), kept("0.6.2"), kept("0.5.0")], 1),
    # A pre-release of the floor is older than the floor.
    "the_floors_own_prerelease_is_past_it": ([full("0.6.2-beta")], [kept("0.6.2-beta")], 1),
    # The floor itself is offered, so the list goes on after it.
    "a_full_page_down_to_the_floor_goes_on": ([full("0.6.3", "0.6.2"), [entry("0.6.1")]],
                                              [kept("0.6.3"), kept("0.6.2"), kept("0.6.1")], 2),
    # What counts is the last release on the page, not one named out of its place.
    "an_old_release_out_of_its_place_ends_nothing": ([full("0.6.1", "0.6.9"), [entry("0.6.8")]],
                                                     [kept("0.6.1"), kept("0.6.9"), kept("0.6.8")], 2),
    # Entries the reader passes over after the last release do not hide that it is past the floor.
    "passed_over_entries_after_the_last_release": (
        [[entry("0.6.4"), entry("0.6.0")] + junk(28)], [kept("0.6.4"), kept("0.6.0")], 1),
    # A page with nothing that counts on it ends nothing either.
    "a_full_page_of_nothing_that_counts": ([junk(30), [entry("0.6.0")]], [kept("0.6.0")], 2),
    # $PickMaxPages full pages still above the floor may not be all of it: never one more, and a throw.
    "five_full_pages_above_the_floor": ([full("0.6.%d" % (MAX_PAGES + 10 - page)) for page in range(1, MAX_PAGES + 2)],
                                        "THROWS", MAX_PAGES),
}


@unittest.skipUnless(POWERSHELL.is_file(), "the bootstrap is PowerShell on Windows")
class FloorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.folder = folder
        work = Path(folder.name)
        (work / "release.json").write_text(json.dumps(dict(RELEASE, release_pages=PAGES)), encoding="utf-8")
        pages = []
        for name, (served, _, _) in CASES.items():
            for number, body in enumerate(served, start=1):
                page = work / "pages" / name / str(number)
                page.mkdir(parents=True)
                (page / "mode").write_text("body", encoding="utf-8")
                (page / "final").write_text(GOOD_FINAL % number, encoding="utf-8")
                (page / "body").write_text(json.dumps(body), encoding="utf-8")
            pages.append({"name": name, "folder": str(work / "pages" / name)})
        cases = {"chosen": [], "pages": pages, "policy": [], "verdicts": [], "tables": []}
        (work / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
        done = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", LIFT],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
                              env=dict(os.environ, CAR_BOOTSTRAP=str(BOOTSTRAP), CAR_CASES=str(work / "cases.json"),
                                       CAR_RELEASE=str(work / "release.json"), CAR_WORK=str(work)))
        cls.done = done
        cls.answer = json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else None

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.answer is None:
            self.fail("the probe did not run: " + (self.done.stderr or self.done.stdout)[-3000:])

    def test_the_pages_end_past_the_floor_and_a_full_one_above_it_is_no_answer(self):
        for name, (_, expected, asked) in CASES.items():
            with self.subTest(name):
                answer = self.answer["pages"][name]
                found = answer["found"]
                self.assertEqual(found if found == "THROWS" else listed(found), expected)
                calls = [json.loads(call) for call in listed(answer["calls"])]
                self.assertEqual([call[1] for call in calls],
                                 [PAGES.replace("{page}", str(page)) for page in range(1, asked + 1)])

    def test_the_floor_is_the_pickers_own(self):
        self.assertEqual(self.answer["constants"]["PickFloor"], "0.6.2")


@unittest.skipUnless(POWERSHELL.is_file(), "the bootstrap is PowerShell on Windows")
class FloorRunTests(PickerRun):
    """-Versions, the whole script, on the day the 150th release is published."""

    def test_five_full_pages_whose_last_reaches_below_the_floor_are_listed(self):
        self.installation(INSTALLED)
        self.serve(*([junk(30)] * 4 + [junk(30 - len(LISTED)) + LISTED]))
        code, output, asked = self.run_it(Versions=True)
        self.assertEqual(code, 0, output[-2000:])
        self.assertEqual(self.answer_lines(output, "version: "), ROWS)
        self.assertEqual([request[1] for request in asked if request[0] == "Get"],
                         [PAGES.replace("{page}", str(page)) for page in range(1, 6)])


if __name__ == "__main__":
    unittest.main()
