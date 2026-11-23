r"""Each page of the picker's list gets 60 seconds, and the run is bounded by its budget alone (the owner, 2026-11-23, F5).

Install another version... reads GitHub's list of releases page by page (Get-ReleasePages). Until now each page had 20 s,
so that twenty pages times a page's limit stayed inside $PickBudgetSeconds (400 s): 0.8 MB in 20 s asked a network for
about 40 KB/s, where only three pages are read today. The owner chose the audit's first option: a page's limit is 60 s,
and the budget alone bounds the run - each page is asked with the smaller of its 60 s and what is left of the budget, a
page's reading never runs past the budget, and a run with too little left is a throw (nothing listed, as any page that
cannot be read). The window waits longer than the budget (test_release_pages_many).

Lifted out of scripts/bootstrap.ps1 as tests/test_release_list_hostile_entries.py lifts it, with Invoke-WebRequest a
stand-in answering from files this test wrote and writing down the deadline each page was asked with: nothing here
reaches the network, the registry or an installation.
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

from test_release_list_hostile_entries import LIFT as HOSTILE_LIFT  # noqa: E402
from test_version_picker import BOOTSTRAP, GOOD_FINAL, PAGES, POWERSHELL, RELEASE, assets  # noqa: E402

SIZE = 30
LIFT = HOSTILE_LIFT.replace(
    "    $file = Join-Path $env:CAR_STUB_PAGES $page\n",
    "    $file = Join-Path $env:CAR_STUB_PAGES $page\n"
    "    Add-Content -LiteralPath $env:CAR_CALLS -Value ([string]$TimeoutSec) -Encoding ASCII\n").replace(
    "    if ($case.page_seconds) { $PickPageTimeoutMax = [int]$case.page_seconds }\n",
    "    if ($case.page_seconds) { $PickPageTimeoutMax = [int]$case.page_seconds }\n"
    "    $PickBudgetSeconds = $constants['PickBudgetSeconds']\n"
    "    if ($case.budget) { $PickBudgetSeconds = [int]$case.budget }\n"
    "    $env:CAR_CALLS = $case.calls\n").replace(
    "    $answer.seconds = $clock.Elapsed.TotalSeconds\n",
    "    $answer.seconds = $clock.Elapsed.TotalSeconds\n"
    "    $answer.asked = @(Get-Content -LiteralPath $case.calls -ErrorAction SilentlyContinue | ForEach-Object { [int]$_ })\n")
assert LIFT.count("CAR_CALLS") == 2 and "$case.budget" in LIFT and "$answer.asked" in LIFT, "the lift has moved"


def page(number):
    """Thirty published releases, all above the floor, none on another page."""
    versions = ["9.%d.%d" % (number, index) for index in range(SIZE, 0, -1)]
    return [{"tag_name": "v" + v, "prerelease": False, "draft": False, "body": "",
             "assets": [{"name": name, "size": 1} for name in assets(v)]} for v in versions]


@unittest.skipUnless(POWERSHELL.is_file(), "the bootstrap is PowerShell on Windows")
class BudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.folder = folder
        work = Path(folder.name)
        (work / "release.json").write_text(json.dumps(dict(RELEASE, release_pages=PAGES)), encoding="utf-8")
        # name -> (pages served, each page's parse in seconds, the budget or None for the bootstrap's own)
        cases = {"as_written": (1, 0, None), "budget_ends_it": (20, 2, 30)}
        written = []
        for name, (served, parse, budget) in cases.items():
            pages = work / "pages" / name
            pages.mkdir(parents=True)
            for number in range(1, served + 1):
                (pages / str(number)).write_text(json.dumps(page(number)), encoding="ascii")
            (pages / str(served + 1)).write_bytes(b"[]")
            written.append({"name": name, "reader": "pages", "folder": str(pages),
                            "final": GOOD_FINAL.replace("%d", "{0}"), "parse_seconds": parse, "page_seconds": None,
                            "timeout": 15, "budget": budget, "calls": str(work / (name + ".calls"))})
        (work / "cases.json").write_text(json.dumps(written), encoding="utf-8")
        done = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", LIFT],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                              env=dict(os.environ, CAR_BOOTSTRAP=str(BOOTSTRAP), CAR_CASES=str(work / "cases.json"),
                                       CAR_RELEASE=str(work / "release.json")),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        cls.done = done
        cls.answer = json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else None

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.answer is None:
            self.fail("the probe did not run: " + (self.done.stderr or self.done.stdout)[-3000:])

    def case(self, name):
        return self.answer["cases"][name]

    def test_each_page_is_given_sixty_seconds(self):
        c = self.answer["constants"]
        self.assertEqual(c["PickPageTimeoutMax"], 60)
        answer = self.case("as_written")
        self.assertIsInstance(answer["found"], list, answer)
        self.assertEqual(len(answer["found"]), SIZE)
        self.assertEqual(answer["asked"], [60, 60], "page 1 and the empty page 2, each with its 60 s")

    def test_a_pages_limit_is_never_more_than_the_budget(self):
        c = self.answer["constants"]
        self.assertLessEqual(c["PickPageTimeoutMax"], c["PickBudgetSeconds"])
        asked = self.case("budget_ends_it")["asked"]
        self.assertIn(asked[0], (29, 30), "the smaller of 60 s and a budget of 30 s (whole seconds, rounded down)")
        self.assertEqual(asked, sorted(asked, reverse=True), "each page is given what is left, never more")

    def test_the_run_ends_by_the_budget(self):
        answer = self.case("budget_ends_it")
        self.assertEqual(answer["found"], "THROWS", answer)
        self.assertIn("Too little time", answer["why"])
        self.assertLess(answer["seconds"], 30 + 5, "over within the budget, not twenty pages of 60 s")
        self.assertLess(len(answer["asked"]), 20, "the budget ended it before the twentieth page")


if __name__ == "__main__":
    unittest.main()
