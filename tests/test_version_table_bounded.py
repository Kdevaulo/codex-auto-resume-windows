r"""-Versions and -Pick never outlive the picker's budget, however long a hostile list (v0.6.26, review R1).

After Get-ReleasePages read the pages within $PickBudgetSeconds, Get-VersionTable sorted the list and judged every entry
twice with no clock, keeping rows with `$rows += ,$row`: five pages of 10,000 releases each kept -Versions running
945.8 s, past the window's 430 s wait. Now:
  - a page holding more releases than the $PickPageSize asked for is a throw (GitHub never sends more than per_page),
    so the table has at most $PickMaxPages pages of them to go through;
  - Get-VersionTable is held to the run's own stopwatch (-Clock, the one Get-ReleasePages read by) and throws once the
    budget has passed; -Versions and -Pick make both calls inside one try, so either throw is "unavailable";
  - its rows are kept in a list, so nineteen full pages are listed and judged well inside the budget.

Lifted out of scripts/bootstrap.ps1 as tests/test_version_picker.py lifts it, with Invoke-WebRequest a stand-in that
answers from files this test wrote: nothing here reaches the network, the registry or an installation.
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

from test_version_picker import BOOTSTRAP, GOOD_FINAL, PAGES, POWERSHELL, RELEASE, assets  # noqa: E402

LIFT = r"""
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:CAR_BOOTSTRAP, [ref]$null, [ref]$errors)
if ($errors -and $errors.Count) { throw 'bootstrap.ps1 does not parse' }
$wanted = @('Get-FinalUri', 'Assert-TrustedHost', 'Invoke-BoundedWebRequest', 'Get-VersionParts',
            'Compare-ProductVersion', 'Format-UnreadVersion', 'Get-PrereleaseVersion', 'Get-ChosenVersion',
            'Read-ReleasesPage', 'Get-ReleasePages', 'Get-SinceValue', 'Get-PinnedDigest',
            'Get-EditionRelease', 'Get-VersionVerdict', 'Get-VersionTable')
foreach ($node in $ast.FindAll({ param($n)
        $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    if ($wanted -contains $node.Name) { Invoke-Expression $node.Extent.Text }
}
foreach ($name in $wanted) {
    if (-not (Get-Command $name -CommandType Function -ErrorAction SilentlyContinue)) { throw ('bootstrap.ps1 has no ' + $name) }
}
foreach ($name in @('$ReleasesHosts', '$ReleasesMaxChars', '$ReleasesTimeoutMin', '$PickFloor', '$EditionsSince',
                    '$PolicySince', '$StateSchemaSince', '$StateReadableFrom', '$StateMarkSince',
                    '$AdvancedStateSince', '$AdvancedReadableFrom', '$AdvancedMarkSince', '$PickPageSize',
                    '$PickMaxPages', '$PickBudgetSeconds', '$PickPageTimeoutMax',
                    '$PickNewerPrereleases', '$PickOlderPrereleases')) {
    $found = $ast.FindAll({ param($n)
        $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -eq $name }, $true)
    if (-not $found) { throw ('bootstrap.ps1 has no ' + $name) }
    Invoke-Expression $found[0].Extent.Text
}
$Budget = $PickBudgetSeconds
$Release = Get-Content -LiteralPath $env:CAR_RELEASE -Raw -Encoding UTF8 | ConvertFrom-Json
function Invoke-WebRequest {
    param([string]$Uri, [switch]$UseBasicParsing, [string]$Method, [int]$MaximumRedirection,
          [int]$TimeoutSec, [string]$OutFile, [switch]$PassThru)
    $page = '1'
    if ($Uri -match '[?&]page=([0-9]+)\z') { $page = $Matches[1] }
    $file = Join-Path $env:CAR_STUB_PAGES $page
    if (-not (Test-Path -LiteralPath $file)) { throw 'the network is not there' }
    $base = New-Object psobject
    $base | Add-Member -MemberType NoteProperty -Name ResponseUri -Value ([Uri]($env:CAR_STUB_FINAL -f $page))
    $response = New-Object psobject
    $response | Add-Member -MemberType NoteProperty -Name BaseResponse -Value $base
    $response | Add-Member -MemberType NoteProperty -Name Content -Value ([IO.File]::ReadAllText($file))
    return $response
}
$env:CAR_STUB_FINAL = $env:CAR_FINAL
$out = [ordered]@{}
foreach ($case in (Get-Content -LiteralPath $env:CAR_CASES -Raw -Encoding UTF8 | ConvertFrom-Json)) {
    $env:CAR_STUB_PAGES = $case.folder
    $PickBudgetSeconds = $Budget
    $answer = [ordered]@{}
    $clock = [Diagnostics.Stopwatch]::StartNew()
    try {
        $listed = Get-ReleasePages -Release $Release
        $answer.listed = @($listed).Count
        if ($case.table) {
            if ($null -ne $case.budget) { $PickBudgetSeconds = [int]$case.budget }   # the table's budget alone
            $run = [Diagnostics.Stopwatch]::StartNew()
            if ($case.budget -eq 0) { Start-Sleep -Milliseconds 50 }
            $table = Get-VersionTable -Listed $listed -Installed '0.6.25' -InstalledEdition 'standard' -Release $Release `
                                      -Policy $false -Clock $run
            $answer.rows = @($table.Rows).Count
        }
        $answer.found = 'LISTED'
    } catch { $answer.found = 'THROWS'; $answer.why = $_.Exception.Message }
    $answer.seconds = $clock.Elapsed.TotalSeconds
    $out[$case.name] = $answer
}
$out | ConvertTo-Json -Depth 4 -Compress
"""


def entry(version):
    return {"tag_name": "v" + version, "prerelease": False, "draft": False, "body": "",
            "assets": [{"name": name, "size": 1} for name in assets(version)]}


def page(number, count=30):
    return [entry("9.%d.%d" % (number, index)) for index in range(count, 0, -1)]


@unittest.skipUnless(POWERSHELL.is_file(), "the bootstrap is PowerShell on Windows")
class BoundedTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.folder = folder
        work = Path(folder.name)
        (work / "release.json").write_text(json.dumps(dict(RELEASE, release_pages=PAGES)), encoding="utf-8")
        # name -> (pages, whether the table is made, the budget the table is held to or None)
        cases = {"thirty_one_on_a_page": ([page(1, 31)], False, None),
                 "past_the_budget": ([page(1)], True, 0),
                 "nineteen_full_pages": ([page(number) for number in range(1, 20)], True, None)}
        written = []
        for name, (pages, table, budget) in cases.items():
            where = work / "pages" / name
            where.mkdir(parents=True)
            for number, body in enumerate(pages, 1):
                (where / str(number)).write_text(json.dumps(body), encoding="ascii")
            if len(pages) < 20:
                (where / str(len(pages) + 1)).write_bytes(b"[]")
            written.append({"name": name, "folder": str(where), "table": table, "budget": budget})
        (work / "cases.json").write_text(json.dumps(written), encoding="utf-8")
        done = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", LIFT],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                              env=dict(os.environ, CAR_BOOTSTRAP=str(BOOTSTRAP), CAR_CASES=str(work / "cases.json"),
                                       CAR_RELEASE=str(work / "release.json"),
                                       CAR_FINAL=GOOD_FINAL.replace("%d", "{0}")),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        cls.done = done
        cls.answer = json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else None

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.answer is None:
            self.fail("the probe did not run: " + (self.done.stderr or self.done.stdout)[-3000:])

    def test_a_page_longer_than_asked_for_lists_nothing(self):
        answer = self.answer["thirty_one_on_a_page"]
        self.assertEqual(answer["found"], "THROWS", answer)
        self.assertIn("more releases than were asked for", answer["why"])

    def test_the_table_is_held_to_the_runs_budget(self):
        answer = self.answer["past_the_budget"]
        self.assertEqual(answer["found"], "THROWS", answer)
        self.assertIn("longer to go through than its budget", answer["why"])

    def test_nineteen_full_pages_are_judged_well_inside_the_budget(self):
        answer = self.answer["nineteen_full_pages"]
        self.assertEqual(answer["found"], "LISTED", answer)
        self.assertEqual(answer["listed"], 19 * 30)
        self.assertEqual(answer["rows"], 2 * 19 * 30, "each release in both editions")
        self.assertLess(answer["seconds"], 120, "the rows are kept without copying them at each one")

    def test_the_versions_and_pick_runs_make_the_table_inside_their_try_on_the_same_clock(self):
        text = BOOTSTRAP.read_text(encoding="utf-8")
        calls = re.findall(r"try \{\s*\$listed = Get-ReleasePages -Release \$release -Clock \$runClock\s*"
                           r"\$table = Get-VersionTable [^}]*-Clock \$runClock\s*\}", text)
        self.assertEqual(len(calls), 2, "-Versions and -Pick")


if __name__ == "__main__":
    unittest.main()
