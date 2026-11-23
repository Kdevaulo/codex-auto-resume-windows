r"""A list of releases that is hostile cannot hold the bootstrap past its deadlines (v0.6.26, audit4 D2).

Read-ReleasesPage's deadline covered the request alone. The entries were gone through afterwards with no clock, and every
asset name was kept with `$names += ,$name`, which copies the array at each name: one published entry with 40,000 assets
`{"name":"a"}` - a page of half a MiB, far under the 32 MiB bound - took 237 s on this machine, more than half the
picker's 400 s, and the window leaves a bootstrap it stopped waiting for running. Now, in both readers of the list (the
picker's Get-ReleasePages and the update check's Get-PublishedPrereleases):

  - an entry naming more than the 1,000 files GitHub lets a release carry is a throw: nothing is listed;
  - the entries are gone through within the page's own deadline (from before its request, never past the whole call's
    $PickBudgetSeconds) or, for the update check, the call's $TimeoutSec - a parse that outlasts it is a throw;
  - a page of thirty releases of 1,000 files each still lists, well inside one page's deadline, with every name kept.

The functions are lifted out of scripts/bootstrap.ps1 as tests/test_release_pages_large.py lifts them, with
Invoke-WebRequest a stand-in that answers from files this test wrote: nothing here reaches the network, the registry or
an installation.
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

from test_version_picker import BOOTSTRAP, GOOD_FINAL, PAGES, POWERSHELL, RELEASE, assets  # noqa: E402

GITHUB_MOST = 1000             # files GitHub lets one release carry


def entry(version, names):
    return {"tag_name": "v" + version, "prerelease": "-" in version, "draft": False, "body": "",
            "assets": [{"name": name, "size": 1} for name in names]}


def filled(version, count):
    """The release's own files, then filler names, `count` in all."""
    names = assets(version)
    return names + ["f%d" % index for index in range(count - len(names))]


LIFT = r"""
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:CAR_BOOTSTRAP, [ref]$null, [ref]$errors)
if ($errors -and $errors.Count) { throw 'bootstrap.ps1 does not parse' }
$wanted = @('Get-FinalUri', 'Assert-TrustedHost', 'Invoke-BoundedWebRequest', 'Get-VersionParts',
            'Compare-ProductVersion', 'Format-UnreadVersion', 'Get-PrereleaseVersion', 'Get-ChosenVersion',
            'Read-ReleasesPage', 'Get-ReleasePages', 'Get-PublishedPrereleases', 'Get-PinnedDigest', 'Get-EditionRelease')
foreach ($node in $ast.FindAll({ param($n)
        $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    if ($wanted -contains $node.Name) { Invoke-Expression $node.Extent.Text }
}
foreach ($name in $wanted) {
    if (-not (Get-Command $name -CommandType Function -ErrorAction SilentlyContinue)) { throw ('bootstrap.ps1 has no ' + $name) }
}
$constants = @{}
foreach ($name in @('$ReleasesHosts', '$ReleasesMaxChars', '$ReleasesTimeoutMin', '$ReleasesTimeoutMax', '$PickFloor',
                    '$PickPageSize', '$PickMaxPages', '$PickBudgetSeconds', '$PickPageTimeoutMax')) {
    $found = $ast.FindAll({ param($n)
        $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -eq $name }, $true)
    if (-not $found) { throw ('bootstrap.ps1 has no ' + $name) }
    Invoke-Expression $found[0].Extent.Text
    $constants[$name.Substring(1)] = (Get-Variable -Name $name.Substring(1)).Value
}
$PageTimeoutAsWritten = $PickPageTimeoutMax
$Release = Get-Content -LiteralPath $env:CAR_RELEASE -Raw -Encoding UTF8 | ConvertFrom-Json
$out = [ordered]@{ constants = $constants; cases = [ordered]@{} }

# The network: page N of the case's folder, its body read as it is; no page there, no network.
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
# The parser, made as slow as the case says: what comes after the request, which its deadline does not cover.
$script:parseSeconds = 0
function ConvertFrom-Json {
    param([Parameter(ValueFromPipeline = $true)]$InputObject)
    if ($script:parseSeconds) { Start-Sleep -Milliseconds ([int](1000 * $script:parseSeconds)) }
    Microsoft.PowerShell.Utility\ConvertFrom-Json -InputObject $InputObject
}

foreach ($case in (Get-Content -LiteralPath $env:CAR_CASES -Raw -Encoding UTF8 | ConvertFrom-Json)) {
    $env:CAR_STUB_PAGES = $case.folder
    $env:CAR_STUB_FINAL = $case.final
    $PickPageTimeoutMax = $PageTimeoutAsWritten
    if ($case.page_seconds) { $PickPageTimeoutMax = [int]$case.page_seconds }
    $answer = [ordered]@{}
    $script:parseSeconds = [double]$case.parse_seconds
    $clock = [Diagnostics.Stopwatch]::StartNew()
    try {
        if ($case.reader -eq 'pages') {
            $pages = Get-ReleasePages -Release $Release
            $answer.found = @(foreach ($one in $pages) {
                $one.Version + ' ' + [string]@($one.Assets).Count + ' ' + [string](@($one.Assets) -join '|').Length })
        } else {
            $read = Get-PublishedPrereleases -Release $Release -TimeoutSec ([int]$case.timeout) -Edition 'standard'
            $answer.found = @($read)
        }
    } catch { $answer.found = 'THROWS'; $answer.why = $_.Exception.Message }
    $script:parseSeconds = 0
    $answer.seconds = $clock.Elapsed.TotalSeconds
    $out.cases[$case.name] = $answer
}
$out | ConvertTo-Json -Depth 6 -Compress
"""


@unittest.skipUnless(POWERSHELL.is_file(), "the bootstrap is PowerShell on Windows")
class HostileEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.folder = folder
        work = Path(folder.name)
        (work / "release.json").write_text(json.dumps(dict(RELEASE, release_pages=PAGES)), encoding="utf-8")
        thirty = ["0.7.%d" % number for number in range(30, 0, -1)]
        cls.thirty = thirty
        beta = "0.7.1-beta.2"
        # name -> (reader, page 1, how long its parse takes, the page's deadline or the call's)
        cases = {
            "too_many_files_pick": ("pages", [entry("0.7.1", filled("0.7.1", GITHUB_MOST + 1))], 0, None),
            "too_many_files_check": ("check", [entry(beta, filled(beta, GITHUB_MOST + 1))], 0, 15),
            "slow_after_the_request_pick": ("pages", [entry("0.7.1", assets("0.7.1"))], 6, 5),
            "slow_after_the_request_check": ("check", [entry(beta, assets(beta))], 6, 5),
            "github_most_pick": ("pages", [entry(v, filled(v, GITHUB_MOST)) for v in thirty], 0, None),
            "github_most_check": ("check", [entry(beta, filled(beta, GITHUB_MOST))], 0, 15),
        }
        written = []
        for name, (reader, page, parse, seconds) in cases.items():
            pages = work / "pages" / name
            pages.mkdir(parents=True)
            (pages / "1").write_text(json.dumps(page), encoding="ascii")
            (pages / "2").write_bytes(b"[]")
            written.append({"name": name, "reader": reader, "folder": str(pages),
                            "final": GOOD_FINAL.replace("%d", "{0}") if reader == "pages" else RELEASE["releases"],
                            "parse_seconds": parse, "page_seconds": seconds if reader == "pages" else None,
                            "timeout": seconds or 15})
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

    def test_an_entry_with_more_files_than_github_allows_lists_nothing_in_the_picker(self):
        answer = self.case("too_many_files_pick")
        self.assertEqual(answer["found"], "THROWS", answer)
        self.assertIn("more files on a release than GitHub allows", answer["why"])

    def test_an_entry_with_more_files_than_github_allows_offers_nothing_in_the_check(self):
        answer = self.case("too_many_files_check")
        self.assertEqual(answer["found"], "THROWS", answer)
        self.assertIn("more files on a release than GitHub allows", answer["why"])

    def test_the_pickers_page_deadline_covers_what_comes_after_its_request(self):
        answer = self.case("slow_after_the_request_pick")
        self.assertEqual(answer["found"], "THROWS", answer)
        self.assertIn("longer to read than its deadline", answer["why"])
        self.assertLess(answer["seconds"], 6 + 5, "thrown at the first entry past the deadline")

    def test_the_checks_deadline_covers_what_comes_after_its_request(self):
        answer = self.case("slow_after_the_request_check")
        self.assertEqual(answer["found"], "THROWS", answer)
        self.assertIn("longer to read than its deadline", answer["why"])

    def test_thirty_releases_of_githubs_most_files_list_whole_inside_one_pages_deadline(self):
        answer = self.case("github_most_pick")
        self.assertIsInstance(answer["found"], list, answer)
        names = filled(self.thirty[0], GITHUB_MOST)
        self.assertEqual([line.split(" ")[0] for line in answer["found"]], self.thirty)
        self.assertEqual(answer["found"][0], "%s %d %d" % (self.thirty[0], GITHUB_MOST, len("|".join(names))))
        self.assertLess(answer["seconds"], self.answer["constants"]["PickPageTimeoutMax"],
                        "the names are kept without copying the list at each one")

    def test_a_pre_release_of_githubs_most_files_is_still_offered(self):
        answer = self.case("github_most_check")
        self.assertEqual(answer["found"], ["0.7.1-beta.2"], answer)


if __name__ == "__main__":
    unittest.main()
