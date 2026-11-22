r"""Install another version... lists every published release down to $PickFloor, hundreds of them (v0.6.26).

Until v0.6.26 the picker read at most five pages of thirty. Since v0.6.26 (tests/test_release_pages_floor.py) a full
page whose last release is older than the floor ends the list, but a NEW installation still said
`versions: unavailable` once 150 published releases at or above the floor existed: five full pages, the fifth still
above it, and no answer. About 54 such releases were out on 2026-11-23, at about 0.84 a day: mid-March 2027.

$PickMaxPages is twenty now, thirty to a page (the page STANDARDS.md C3 names): 600 published releases, so the
151st, the 300th and the 500th release above the floor - with the ten published below it - list in full, inside a
budget the window waits a little longer for. A list that still goes on past the twentieth page is no answer, a
page over $ReleasesMaxChars is refused before it is parsed, and a page that cannot be read lists nothing.

Get-ReleasePages is lifted out of scripts/bootstrap.ps1 and run with the network a stand-in, as
tests/test_version_picker.py does (its LIFT, with only pages to read), and -Versions runs as the whole script
under that module's PickerRun; nothing here reaches the network or the registry.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_version_picker import (BOOTSTRAP, GOOD_FINAL, INSTALLED, LIFT, PAGES, POWERSHELL,  # noqa: E402
                                 RELEASE, PickerRun, entry, kept, listed)

ROOT = Path(__file__).resolve().parents[1]
SIZE = 30
# Ten releases published below the floor, oldest last: they count on a page as any other.
BELOW = ["0.6.1", "0.6.0", "0.5.9", "0.5.8", "0.5.7", "0.5.6", "0.5.5", "0.5.4", "0.5.3", "0.5.2"]


def published(above):
    """The whole list, newest first: `above` releases above the floor, then the ten below it."""
    return ["0.7.%d" % number for number in range(above, 0, -1)] + BELOW


def paged(versions):
    """The list as GitHub pages it, thirty to a page; an empty page after a full last one."""
    pages = [[entry(v) for v in versions[start:start + SIZE]] for start in range(0, len(versions), SIZE)]
    return pages or [[]]


def pages_needed(versions):
    """How many pages are asked for: up to the first short one or the first full one ending below the floor."""
    for number, start in enumerate(range(0, len(versions), SIZE), start=1):
        page = versions[start:start + SIZE]
        if len(page) < SIZE or page[-1] in BELOW:
            return number
    return len(versions) // SIZE + 1


# name -> the pages served as (mode, body) by number from 1, what Get-ReleasePages gives back (THROWS or the kept
# entries), and how many pages it asked for.
CASES = {}
for _above in (151, 300, 500):
    _versions = published(_above)
    _asked = pages_needed(_versions)
    CASES["%d_above_the_floor" % _above] = ([("body", page) for page in paged(_versions)],
                                            [kept(v) for v in _versions[:_asked * SIZE]], _asked)
# 620 above the floor: the twentieth page is as full as the rest and still above it, so more may follow.
CASES["a_list_past_the_twentieth_page"] = ([("body", page) for page in paged(published(620))], "THROWS", 20)
# A page over the size bound, the twelfth of the 500, is refused, and nothing after it is asked for.
_large = [("body", page) for page in paged(published(500))]
_large[11] = ("large", None)
CASES["a_page_over_the_size_bound"] = (_large, "THROWS", 12)
# A page that cannot be read, the seventeenth, the last one the 500 need.
_failed = [("body", page) for page in paged(published(500))]
_failed[16] = ("throw", None)
CASES["the_last_page_cannot_be_read"] = (_failed, "THROWS", 17)


@unittest.skipUnless(POWERSHELL.is_file(), "the bootstrap is PowerShell on Windows")
class ManyReleasesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.folder = folder
        work = Path(folder.name)
        (work / "release.json").write_text(json.dumps(dict(RELEASE, release_pages=PAGES)), encoding="utf-8")
        pages = []
        for name, (served, _, _) in CASES.items():
            for number, (mode, body) in enumerate(served, start=1):
                page = work / "pages" / name / str(number)
                page.mkdir(parents=True)
                (page / "mode").write_text(mode, encoding="utf-8")
                (page / "final").write_text(GOOD_FINAL % number, encoding="utf-8")
                if mode == "body":
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

    def test_hundreds_of_releases_above_the_floor_list_in_full_and_no_more_is_ever_taken(self):
        for name, (_, expected, asked) in CASES.items():
            with self.subTest(name):
                answer = self.answer["pages"][name]
                found = answer["found"]
                self.assertEqual(found if found == "THROWS" else listed(found), expected)
                calls = [json.loads(call) for call in listed(answer["calls"])]
                self.assertEqual([call[1] for call in calls],
                                 [PAGES.replace("{page}", str(page)) for page in range(1, asked + 1)])
                c = self.answer["constants"]
                for method, _, redirects, seconds, to_file in calls:
                    self.assertEqual((method, redirects, to_file), ("Get", 0, False))
                    self.assertGreaterEqual(seconds, c["ReleasesTimeoutMin"])
                    self.assertLessEqual(seconds, c["PickPageTimeoutMax"])

    def test_the_500th_release_above_the_floor_ends_the_list_on_the_floor_not_on_a_short_page(self):
        """The 500 plus the ten below fill seventeen pages exactly: the last one ends it by reaching below the floor."""
        self.assertEqual(len(published(500)), 17 * SIZE)
        self.assertEqual(CASES["500_above_the_floor"][2], 17)

    def test_twenty_pages_inside_a_budget_the_window_waits_longer_for(self):
        c = self.answer["constants"]
        self.assertEqual((c["PickPageSize"], c["PickMaxPages"]), (SIZE, 20))
        self.assertGreaterEqual(c["PickPageSize"] * c["PickMaxPages"] - len(BELOW), 500,
                                "at least 500 releases above the floor list in full")
        self.assertLessEqual(c["PickMaxPages"] * c["PickPageTimeoutMax"], c["PickBudgetSeconds"])
        source = (ROOT / "gui" / "DashboardVersions.cs").read_text(encoding="utf-8")
        waits = re.findall(r"private const int ListMilliseconds = (\d+);", source)
        self.assertEqual(len(waits), 1)
        wait = int(waits[0]) / 1000
        self.assertGreater(wait, c["PickBudgetSeconds"], "the window waits longer than the listing's budget")
        self.assertLessEqual(wait, c["PickBudgetSeconds"] + 60, "and only a little longer")
        # -Pick reads the same pages before it installs, inside the window's wait for an install.
        maintenance = (ROOT / "gui" / "DashboardMaintenance.cs").read_text(encoding="utf-8")
        update = int(re.findall(r"private const int UpdateMilliseconds = (\d+);", maintenance)[0]) / 1000
        self.assertLessEqual(c["PickBudgetSeconds"] * 2, update)

    def test_a_page_of_thirty_is_far_inside_the_size_bound(self):
        """Thirty releases of today's notes (about 27 KB each) are about a tenth of $ReleasesMaxChars."""
        self.assertGreaterEqual(self.answer["constants"]["ReleasesMaxChars"], 8 * 1024 * 1024)


@unittest.skipUnless(POWERSHELL.is_file(), "the bootstrap is PowerShell on Windows")
class ManyReleasesRunTests(PickerRun):
    """-Versions, the whole script, on the day the 151st release above the floor is published."""

    def test_the_151st_release_above_the_floor_is_listed(self):
        self.installation(INSTALLED)
        versions = ["0.6.12-beta.%d" % number for number in range(151, 1, -1)] + [INSTALLED, "0.6.2"] + BELOW
        self.serve(*paged(versions))
        code, output, asked = self.run_it(Versions=True)
        self.assertEqual(code, 0, output[-2000:])
        self.assertEqual(len(self.answer_lines(output, "versions: listed ")), 1, output[-2000:])
        shown = {line.split()[1] for line in self.answer_lines(output, "version: ")}
        self.assertTrue({"0.6.12-beta.151", "0.6.12-beta.2", "0.6.2"} <= shown, sorted(shown)[:5])
        self.assertEqual([request[1] for request in asked if request[0] == "Get"],
                         [PAGES.replace("{page}", str(page)) for page in range(1, 7)])

    def test_a_list_past_the_twentieth_page_lists_nothing(self):
        self.installation(INSTALLED)
        self.serve(*paged(["0.6.12-beta.%d" % number for number in range(700, 1, -1)]))
        code, output, asked = self.run_it(Versions=True)
        self.assertEqual(code, 12, output[-2000:])
        self.assertEqual(self.answer_lines(output, "versions: "), ["versions: unavailable"])
        self.assertEqual(self.answer_lines(output, "version: "), [])
        self.assertEqual([request[1] for request in asked if request[0] == "Get"],
                         [PAGES.replace("{page}", str(page)) for page in range(1, 21)])


if __name__ == "__main__":
    unittest.main()
