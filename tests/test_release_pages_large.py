r"""The largest page of releases GitHub can send is read (the owner, 2026-11-23, v0.6.26).

"지금 앱이 릴리즈 페이지 용량이 커지면 못 읽는거 용량 한도 늘리자": the bootstraps up to v0.6.25 refuse a page of the
list of releases over $ReleasesMaxChars (2 MiB to v0.6.22, 8 MiB from v0.6.23), and a growing list or long release
notes could reach it - installed copies keep their own bound, which nothing can help. From v0.6.26 the bound is above
the THEORETICAL MAXIMUM of one page: thirty releases (the picker's page; the update check's is ten), each with

  - a body at GitHub's limit of 125,000 characters, every one a control character JSON can only write as six
    (\u0001) - its worst escaping; a character outside the BMP is two UTF-16 units raw, and GitHub sends non-ASCII raw,
  - a name of 1,024 such characters and a target_commitish of 255,
  - sixteen files, twice the eight a release of this product carries, each with a name and a label of 255 characters
    (the label worst-escaped too) and its uploader,
  - and every other field GitHub's list gives a release: its URLs, its author, its reactions.

That page is built here, and

  - it lists, through the picker's reader (Get-ReleasePages) and through Read-ReleasesPage, under Windows PowerShell
    5.1's ConvertFrom-Json, well within the page's own deadline ($PickPageTimeoutMax);
  - the bound is above it with a margin, and a page one character over the bound is refused before it is parsed -
    ConvertFrom-Json is never called for it;
  - a page of 8 MiB + 1 (what the bootstraps v0.6.23 to v0.6.25 refuse) lists now, through the picker's reader and
    the update check's (Get-PublishedPrereleases).

The functions are lifted out of scripts/bootstrap.ps1 as tests/test_version_picker.py lifts them, with
Invoke-WebRequest a stand-in that answers from files this test wrote: nothing here reaches the network, the registry
or an installation. Everything else the reader checks - published entries only, no redirect, the host and path, the
whole-call deadline, the page count - is held where it was (test_version_picker, test_release_pages_many,
test_prerelease_offer) and is unchanged.
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

MIB = 1024 * 1024
SIZE = 30
BODY_LIMIT = 125000            # GitHub: "body is too long (maximum is 125000 characters)"
NAME_LIMIT = 1024
REF_LIMIT = 255
FILES = 16                     # twice the eight files a release of this product carries
WORST = "\x01"                 # JSON writes it as \u0001: six characters for one
OWNER, REPO = RELEASE["owner"], RELEASE["repo"]
API = "https://api.github.com/repos/%s/%s" % (OWNER, REPO)


def user(login="a" * 39, number=2 ** 53):
    """An author or uploader as GitHub's list gives one, at the longest login GitHub allows (39)."""
    home = "https://api.github.com/users/" + login
    return {"login": login, "id": number, "node_id": "MDQ6VXNlcjE" + "A" * 40,
            "avatar_url": "https://avatars.githubusercontent.com/u/%d?v=4" % number, "gravatar_id": "",
            "url": home, "html_url": "https://github.com/" + login, "followers_url": home + "/followers",
            "following_url": home + "/following{/other_user}", "gists_url": home + "/gists{/gist_id}",
            "starred_url": home + "/starred{/owner}{/repo}", "subscriptions_url": home + "/subscriptions",
            "organizations_url": home + "/orgs", "repos_url": home + "/repos",
            "events_url": home + "/events{/privacy}", "received_events_url": home + "/received_events",
            "type": "User", "user_view_type": "public", "site_admin": False}


def asset(name, number):
    """One file of a release, every field GitHub's list gives it, its label worst-escaped."""
    return {"url": API + "/releases/assets/%d" % number, "id": number, "node_id": "RA_" + "k" * 40,
            "name": name, "label": WORST * REF_LIMIT, "uploader": user(), "content_type": "application/octet-stream",
            "state": "uploaded", "size": 2 ** 53, "digest": "sha256:" + "0" * 64, "download_count": 2 ** 53,
            "created_at": "2026-11-23T00:00:00Z", "updated_at": "2026-11-23T00:00:00Z",
            "browser_download_url": "https://github.com/%s/%s/releases/download/v9.9.9/%s" % (OWNER, REPO, name)}


def release(version, number):
    """One release at the largest GitHub can make it, of a version the picker counts."""
    tag = "v" + version
    names = assets(version)
    names += [(("x%d-" % index) + "a" * REF_LIMIT)[:REF_LIMIT] for index in range(FILES - len(names))]
    return {"url": API + "/releases/%d" % number, "assets_url": API + "/releases/%d/assets" % number,
            "upload_url": "https://uploads.github.com/repos/%s/%s/releases/%d/assets{?name,label}" % (OWNER, REPO,
                                                                                                     number),
            "html_url": "https://github.com/%s/%s/releases/tag/%s" % (OWNER, REPO, tag), "id": number,
            "author": user(), "node_id": "RE_" + "k" * 40, "tag_name": tag, "target_commitish": "b" * REF_LIMIT,
            "name": WORST * NAME_LIMIT, "draft": False, "immutable": False, "prerelease": "-" in version,
            "created_at": "2026-11-23T00:00:00Z", "updated_at": "2026-11-23T00:00:00Z",
            "published_at": "2026-11-23T00:00:00Z",
            "assets": [asset(name, number * 100 + index) for index, name in enumerate(names)],
            "tarball_url": API + "/tarball/" + tag, "zipball_url": API + "/zipball/" + tag,
            "body": WORST * BODY_LIMIT,
            "reactions": {"url": API + "/releases/%d/reactions" % number, "total_count": 2 ** 53,
                          "+1": 2 ** 53, "-1": 2 ** 53, "laugh": 2 ** 53, "hooray": 2 ** 53, "confused": 2 ** 53,
                          "heart": 2 ** 53, "rocket": 2 ** 53, "eyes": 2 ** 53},
            "mentions_count": 2 ** 53,
            "discussion_url": "https://github.com/%s/%s/discussions/%d" % (OWNER, REPO, number)}


VERSIONS = ["0.7.%d" % number for number in range(SIZE, 0, -1)]


def theoretical_page():
    """The largest page of thirty GitHub can send, as it sends it (JSON, ASCII, control characters escaped)."""
    return json.dumps([release(version, 900000 + index) for index, version in enumerate(VERSIONS)],
                      ensure_ascii=True, separators=(",", ":"))


def padded(length):
    """A page of thirty ordinary releases, exactly `length` characters long: the last one's body takes the rest."""
    entries = [{"tag_name": "v" + v, "prerelease": False, "draft": False, "body": "",
                "assets": [{"name": name, "size": 1} for name in assets(v)]} for v in VERSIONS]
    short = json.dumps(entries, ensure_ascii=True)
    entries[-1]["body"] = "a" * (length - len(short))
    page = json.dumps(entries, ensure_ascii=True)
    assert len(page) == length, (len(page), length)
    return page


LIFT = r"""
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:CAR_BOOTSTRAP, [ref]$null, [ref]$errors)
if ($errors -and $errors.Count) { throw 'bootstrap.ps1 does not parse' }
$wanted = @('Get-FinalUri', 'Assert-TrustedHost', 'Invoke-BoundedWebRequest', 'Get-VersionParts',
            'Compare-ProductVersion', 'Format-UnreadVersion', 'Get-PrereleaseVersion', 'Get-ChosenVersion',
            'Read-ReleasesPage', 'Get-ReleasePages', 'Get-PublishedPrereleases')
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
# The parser, counted: a page refused for its size never reaches it.
$script:parsed = 0
function ConvertFrom-Json {
    param([Parameter(ValueFromPipeline = $true)]$InputObject)
    $script:parsed += 1
    Microsoft.PowerShell.Utility\ConvertFrom-Json -InputObject $InputObject
}

foreach ($case in (Get-Content -LiteralPath $env:CAR_CASES -Raw -Encoding UTF8 | ConvertFrom-Json)) {
    $env:CAR_STUB_PAGES = $case.folder
    $env:CAR_STUB_FINAL = $case.final
    $script:parsed = 0
    $answer = [ordered]@{}
    $clock = [Diagnostics.Stopwatch]::StartNew()
    try {
        if ($case.reader -eq 'pages') {
            $answer.found = @(Get-ReleasePages -Release $Release | ForEach-Object { $_.Version })
        } elseif ($case.reader -eq 'prereleases') {
            $read = Get-PublishedPrereleases -Release $Release -TimeoutSec $ReleasesTimeoutMax
            $answer.found = @($read)
        } else {
            $read = Read-ReleasesPage -Release $Release -Uri ($case.final -f '1') -TimeoutSec $PickPageTimeoutMax
            $answer.found = @($read | ForEach-Object {
                [string]$_.tag_name + ' ' + [string]$_.body.Length + ' ' + [string]@($_.assets).Count })
        }
    } catch { $answer.found = 'THROWS'; $answer.why = $_.Exception.Message }
    $answer.seconds = $clock.Elapsed.TotalSeconds
    $answer.parsed = $script:parsed
    $out.cases[$case.name] = $answer
}
$out | ConvertTo-Json -Depth 6 -Compress
"""


@unittest.skipUnless(POWERSHELL.is_file(), "the bootstrap is PowerShell on Windows")
class LargePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.folder = folder
        work = Path(folder.name)
        (work / "release.json").write_text(json.dumps(dict(RELEASE, release_pages=PAGES)), encoding="utf-8")
        bound = cls.bound_in_script()
        cls.theoretical = theoretical_page()
        prereleases = [{"tag_name": "v0.7.%d-beta.%d" % (number, number + 1), "prerelease": True, "draft": False,
                        "body": ""} for number in range(10, 0, -1)]
        short = json.dumps(prereleases, ensure_ascii=True)
        prereleases[-1]["body"] = "a" * (8 * MIB + 1 - len(short))
        bodies = {"theoretical": cls.theoretical, "over_the_bound": padded(bound + 1), "at_the_bound": padded(bound),
                  "old_bound_plus_one": padded(8 * MIB + 1),
                  "old_bound_plus_one_update_check": json.dumps(prereleases, ensure_ascii=True)}
        assert len(bodies["old_bound_plus_one_update_check"]) == 8 * MIB + 1
        # name -> (which reader, the body of page 1); page 2, where one is read, is the empty last page.
        cases = [("theoretical_pages", "pages", "theoretical"), ("theoretical_page", "page", "theoretical"),
                 ("over_the_bound", "pages", "over_the_bound"), ("at_the_bound", "pages", "at_the_bound"),
                 ("old_bound_plus_one", "pages", "old_bound_plus_one"),
                 ("old_bound_plus_one_update_check", "prereleases", "old_bound_plus_one_update_check")]
        written = []
        for name, reader, body in cases:
            pages = work / "pages" / name
            pages.mkdir(parents=True)
            (pages / "1").write_bytes(bodies[body].encode("ascii"))
            (pages / "2").write_bytes(b"[]")
            final = (GOOD_FINAL.replace("%d", "{0}") if reader == "pages" or reader == "page"
                     else RELEASE["releases"])
            written.append({"name": name, "reader": reader, "folder": str(pages), "final": final})
        (work / "cases.json").write_text(json.dumps(written), encoding="utf-8")
        cls.lengths = {name: len(bodies[body]) for name, _, body in cases}
        done = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", LIFT],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                              env=dict(os.environ, CAR_BOOTSTRAP=str(BOOTSTRAP), CAR_CASES=str(work / "cases.json"),
                                       CAR_RELEASE=str(work / "release.json")))
        cls.done = done
        cls.answer = json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else None

    @classmethod
    def bound_in_script(cls):
        import re
        found = re.findall(r"(?m)^\$ReleasesMaxChars = (\d+)\s*$", BOOTSTRAP.read_text(encoding="utf-8"))
        assert len(found) == 1, found
        return int(found[0])

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.answer is None:
            self.fail("the probe did not run: " + (self.done.stderr or self.done.stdout)[-3000:])

    def case(self, name):
        return self.answer["cases"][name]

    def found(self, name):
        found = self.case(name)["found"]
        return [found] if isinstance(found, str) else list(found)

    def test_the_bound_is_above_the_theoretical_page_with_a_margin(self):
        bound = self.answer["constants"]["ReleasesMaxChars"]
        self.assertEqual(bound, self.bound_in_script())
        size = len(self.theoretical)
        self.assertGreater(size, 22 * 1000 * 1000, "the page is built at GitHub's limits")
        self.assertGreaterEqual(bound, size * 1.25, "a quarter at least above the largest page GitHub sends")
        self.assertEqual(bound, 32 * MIB)

    def test_the_theoretical_page_lists_through_the_picker(self):
        answer = self.case("theoretical_pages")
        self.assertEqual(self.found("theoretical_pages"), VERSIONS, answer.get("why"))
        self.assertEqual(answer["parsed"], 2, "page 1, then the empty page 2")

    def test_the_theoretical_page_is_read_whole_and_inside_the_page_deadline(self):
        answer = self.case("theoretical_page")
        self.assertEqual(self.found("theoretical_page"), ["v%s %d %d" % (v, BODY_LIMIT, FILES) for v in VERSIONS],
                         answer.get("why"))
        self.assertEqual(answer["parsed"], 1)
        self.assertLess(answer["seconds"], self.answer["constants"]["PickPageTimeoutMax"],
                        "the stand-in serves at once: what is left is the parse, on this machine")

    def test_one_character_over_the_bound_is_refused_before_it_is_parsed(self):
        answer = self.case("over_the_bound")
        self.assertEqual(self.lengths["over_the_bound"], self.answer["constants"]["ReleasesMaxChars"] + 1)
        self.assertEqual(answer["found"], "THROWS")
        self.assertIn("larger than this script reads", answer["why"])
        self.assertEqual(answer["parsed"], 0, "ConvertFrom-Json is never called for it")

    def test_a_page_at_the_bound_lists(self):
        self.assertEqual(self.lengths["at_the_bound"], self.answer["constants"]["ReleasesMaxChars"])
        self.assertEqual(self.found("at_the_bound"), VERSIONS, self.case("at_the_bound").get("why"))

    def test_a_page_the_v0623_to_v0625_bootstraps_refuse_lists_now(self):
        self.assertEqual(self.lengths["old_bound_plus_one"], 8 * MIB + 1)
        self.assertEqual(self.found("old_bound_plus_one"), VERSIONS, self.case("old_bound_plus_one").get("why"))
        self.assertEqual(self.lengths["old_bound_plus_one_update_check"], 8 * MIB + 1)
        self.assertEqual(self.found("old_bound_plus_one_update_check"),
                         ["0.7.%d-beta.%d" % (n, n + 1) for n in range(10, 0, -1)],
                         self.case("old_bound_plus_one_update_check").get("why"))


if __name__ == "__main__":
    unittest.main()
