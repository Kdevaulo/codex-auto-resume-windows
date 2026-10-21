r"""The update's archive download: streamed, counted, and checked at every hop.

scripts/bootstrap.ps1 fetches the archive and its checksum on System.Net.HttpWebRequest (Get-Remote without -Deadline,
Save-StreamedDownload) rather than Invoke-WebRequest -PassThru, which under Windows PowerShell 5.1 holds the whole body
and writes the file only at the end. What that gains, each proved here: the archive's real bytes on the setup window's
progress lines, only when the window asked and only where the response says its length; every redirect hop held to the
host rule before it is asked; the answer checked before a byte is written, the body streamed to a file of its own and
nothing left at the target after any failure; a body cut short named as such; a dropped connection resumed from where it
stopped, and only on a 206 that starts there. What it must not lose, proved too: Invoke-WebRequest's words for an HTTP
error, a rate limit (Get-RateLimitReset still finds the response), a refused connection and a timeout; its User-Agent and
headers; and the old path, used only where the new request cannot be made - never after a host refusal.

The real functions are lifted out of the shipped script by the PowerShell parser, as tests/test_update_check.py does.
The streamed download's one door to the network, Get-DownloadResponse, is replaced by a stand-in that answers from what
each case scripts, with .NET stand-ins for the response and its stream (a stream that drops the connection throws the
IOException a real one does); Invoke-WebRequest is a stand-in that writes down that it was asked and never reaches a
network. The comparisons with the real cmdlet ask a server this test runs on 127.0.0.1, and nothing else.
"""
from __future__ import annotations

import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "scripts" / "bootstrap.ps1"
POWERSHELL = (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
              / "WindowsPowerShell" / "v1.0" / "powershell.exe")

ARCHIVE = "https://github.com/example-owner/example-repo/releases/download/v1.2.3/CodexAutoResume-v1.2.3-win-x64.zip"
ASSETS = "https://release-assets.githubusercontent.com/github-production-release-asset/1/abc?sig=x"
OBJECTS = "https://objects.githubusercontent.com/github-production-release-asset-2e65be/1/abc"
REFUSED = "was redirected to a host this installer does not trust: "
TOO_MANY = "Too many automatic redirections were attempted."
SIZE = 300000


def pattern(size: int) -> bytes:
    """The body every case serves: StandInStream.Pattern's bytes."""
    return bytes((i * 31 + 7) % 251 for i in range(size))


BODY_SHA = hashlib.sha256(pattern(SIZE)).hexdigest()

LIFT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
Set-StrictMode -Version 2.0
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:CAR_BOOTSTRAP, [ref]$null, [ref]$errors)
if ($errors -and $errors.Count) { throw 'bootstrap.ps1 does not parse' }
$found = @()
foreach ($node in $ast.FindAll({ param($n)
        $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    if ($wanted -contains $node.Name) { $found += $node.Name; Invoke-Expression $node.Extent.Text }
}
foreach ($name in $wanted) { if ($found -notcontains $name) { throw ('bootstrap.ps1 has no ' + $name) } }
$allowedAst = $ast.FindAll({ param($n)
        $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $n.Left.Extent.Text -eq '$AllowedHosts' }, $true)
Invoke-Expression $allowedAst[0].Extent.Text
"""

STANDIN_TYPES = r"""
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Net;

public class StandInStream : Stream {
    private readonly byte[] data;
    private readonly int breakAfter;
    private int at;
    public StandInStream(byte[] data, int breakAfter) { this.data = data; this.breakAfter = breakAfter; }
    public static byte[] Pattern(int size) {
        byte[] bytes = new byte[size];
        for (int i = 0; i < size; i++) bytes[i] = (byte)((i * 31 + 7) % 251);
        return bytes;
    }
    public override int Read(byte[] buffer, int offset, int count) {
        if (breakAfter >= 0 && at >= breakAfter)
            throw new IOException("Unable to read data from the transport connection: the connection was closed.");
        int n = Math.Min(count, data.Length - at);
        if (breakAfter >= 0) n = Math.Min(n, breakAfter - at);
        Array.Copy(data, at, buffer, offset, n);
        at += n;
        return n;
    }
    public override bool CanRead { get { return true; } }
    public override bool CanSeek { get { return false; } }
    public override bool CanWrite { get { return false; } }
    public override long Length { get { throw new NotSupportedException(); } }
    public override long Position { get { return at; } set { throw new NotSupportedException(); } }
    public override void Flush() { }
    public override long Seek(long offset, SeekOrigin origin) { throw new NotSupportedException(); }
    public override void SetLength(long value) { throw new NotSupportedException(); }
    public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
}

public class StandInResponse : WebResponse {
    public int Code;
    public long Length;
    public Uri From;
    public Stream Body;
    public bool Closed;
    private readonly WebHeaderCollection headers = new WebHeaderCollection();
    public HttpStatusCode StatusCode { get { return (HttpStatusCode)Code; } }
    public override long ContentLength { get { return Length; } set { } }
    public override Uri ResponseUri { get { return From; } }
    public override WebHeaderCollection Headers { get { return headers; } }
    public override Stream GetResponseStream() { return Body; }
    public override void Close() { Closed = true; if (Body != null) Body.Dispose(); }
}
'@
"""

# Each case: the address asked, whether the window asked for progress lines, and the answers the network gives, one per
# request. An answer: a status, a Location, where it says it came from, the slice of the body it carries, the length it
# says (-1: none), after how many bytes the connection drops, a Content-Range - or a failure it throws.
STANDIN_PROBE = LIFT + STANDIN_TYPES + r"""
$cases = Get-Content -LiteralPath $env:CAR_CASES -Raw -Encoding UTF8 | ConvertFrom-Json
$global:Body = [StandInStream]::Pattern([int]$env:CAR_SIZE)

function Get-Field { param($Object, [string]$Name, $Default)
    if ($Object.PSObject.Properties.Match($Name).Count -and $null -ne $Object.$Name) { return $Object.$Name }
    return $Default
}

function New-StandIn { param($Answer, [switch]$Thrown)
    $from = [int](Get-Field $Answer 'from' 0)
    $to = [int](Get-Field $Answer 'to' $global:Body.Length)
    $slice = New-Object byte[] ($to - $from)
    [Array]::Copy($global:Body, $from, $slice, 0, $to - $from)
    $response = New-Object StandInResponse
    $response.Code = [int](Get-Field $Answer 'status' 200)
    $response.Length = [long](Get-Field $Answer 'length' ($to - $from))
    $response.From = [Uri](Get-Field $Answer 'final' $global:Asking)
    $response.Body = New-Object StandInStream($slice, [int](Get-Field $Answer 'drop' -1))
    $location = Get-Field $Answer 'location' $null
    if ($location) { $response.Headers['Location'] = $location }
    $range = Get-Field $Answer 'range' $null
    if ($range) { $response.Headers['Content-Range'] = $range }
    foreach ($pair in @((Get-Field $Answer 'headers' (New-Object psobject)).PSObject.Properties)) {
        $response.Headers[$pair.Name] = [string]$pair.Value
    }
    # One thrown with its failure is the failure's to carry (Get-RateLimitReset reads it), and stays open.
    if (-not $Thrown) { [void]$global:Made.Add($response) }
    return $response
}

# The streamed download's door: what it was asked, written down, and the case's next answer.
function global:Get-DownloadResponse { param($Request)
    $global:Asking = $Request.RequestUri.AbsoluteUri
    $global:Asked += ,@{ uri = $Request.RequestUri.AbsoluteUri; range = [string]$Request.Headers['Range']
                         redirects = $Request.AllowAutoRedirect; timeout = $Request.Timeout; agent = $Request.UserAgent }
    if ($global:Next -ge @($global:Case.answers).Count) { throw 'this case has no more answers' }
    $answer = @($global:Case.answers)[$global:Next]
    $global:Next++
    $failure = Get-Field $answer 'throw' $null
    if ($failure -eq 'io') { throw (New-Object IO.IOException 'The connection was closed before an answer came.') }
    if ($failure -eq 'web') {
        $response = New-StandIn $answer -Thrown
        throw (New-Object Net.WebException($answer.message, $null, [Net.WebExceptionStatus]::ProtocolError, $response))
    }
    return (New-StandIn $answer)
}

# The old path: written down, and never the network.
function global:Invoke-WebRequest {
    param([string]$Uri, [string]$OutFile, [switch]$UseBasicParsing, [switch]$PassThru,
          [int]$MaximumRedirection, [int]$TimeoutSec, [string]$Method)
    $global:OldPath++
    $old = Get-Field $global:Case 'old' $null
    if ($null -eq $old) { throw 'the old path was taken' }
    [IO.File]::WriteAllBytes($OutFile, $global:Body)
    $base = New-Object psobject
    $base | Add-Member -MemberType NoteProperty -Name ResponseUri -Value ([Uri]$old)
    $response = New-Object psobject
    $response | Add-Member -MemberType NoteProperty -Name BaseResponse -Value $base
    return $response
}

$realRequest = ${function:New-DownloadRequest}
$results = @()
$index = 0
foreach ($case in @($cases)) {
    $index++
    $global:Case = $case; $global:Next = 0; $global:Asked = @(); $global:OldPath = 0; $global:Threw = $null
    $global:Made = New-Object Collections.ArrayList
    if (Get-Field $case 'cannot' $false) { ${function:New-DownloadRequest} = { throw 'This PowerShell has no such type.' } }
    else { ${function:New-DownloadRequest} = $realRequest }
    $folder = Join-Path $env:CAR_ROOT ('case' + $index)
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
    $out = Join-Path $folder 'download.zip'
    $count = [bool](Get-Field $case 'count' $false)
    $printed = @(& { try { Get-Remote -Uri $case.uri -OutFile $out -What 'The archive' -Count:$count }
                     catch { $global:Threw = $_.Exception } } 6>&1 | ForEach-Object { [string]$_ })
    $file = $null
    if (Test-Path -LiteralPath $out) { $file = (Get-FileHash -LiteralPath $out -Algorithm SHA256).Hash.ToLowerInvariant() }
    # A response a failure carries (as .NET's own WebException carries it) is the failure's, and stays open.
    $carried = @()
    $inner = $null
    $link = $global:Threw
    while ($null -ne $link) {
        if ($link -is [Net.WebException] -and $null -ne $link.Response) { $carried += ,$link.Response }
        if ($link -ne $global:Threw -and $null -eq $inner) { $inner = $link.GetType().FullName }
        $link = $link.InnerException
    }
    $results += ,@{
        name = $case.name; printed = $printed; file = $file; asked = $global:Asked; old = $global:OldPath
        threw = $(if ($global:Threw) { $global:Threw.Message } else { $null })
        type = $(if ($global:Threw) { $global:Threw.GetType().FullName } else { $null })
        status = $(if ($global:Threw -is [Net.WebException]) { [string]$global:Threw.Status } else { $null })
        inner = $inner; carried = $carried.Count
        reset = $(if ($global:Threw) { Get-RateLimitReset $global:Threw } else { $null })
        leftovers = @(Get-ChildItem -LiteralPath $folder -Force | Where-Object { $_.Name -ne 'download.zip' } |
                      ForEach-Object { $_.Name })
        open = @($global:Made | Where-Object { -not $_.Closed -and $carried -notcontains $_ }).Count
    }
}
$words = @{}
foreach ($name in @('net_tooManyRedirections', 'net_resubmitprotofailed', 'net_servererror', 'net_httpstatuscode_NotModified')) {
    $words[$name] = Get-DownloadWords -Source 'net' -Name $name -Fallback 'none'
}
'@@RESULTS@@' + (ConvertTo-Json -InputObject @{ cases = $results; words = $words } -Depth 7 -Compress)
"""

WANTED_STANDIN = ("$wanted = @('Step', 'Get-FinalUri', 'Assert-TrustedHost', 'Get-RateLimitReset', 'Get-Remote', "
                  "'Get-ThrownException', 'Get-DownloadWords', 'New-DownloadRequest', 'Assert-TrustedHop', "
                  "'New-ServerError', 'Open-Download', 'Save-StreamedDownload')\n")


def redirect(location, status=302):
    return {"status": status, "location": location, "to": 0, "length": 0}


@unittest.skipUnless(POWERSHELL.is_file(), "the bootstrap is PowerShell on Windows")
class StreamedDownloadTests(unittest.TestCase):
    """Every case runs in one PowerShell, against the lifted functions and the stand-in door."""

    CASES = [
        # G1: the archive's real bytes, only when asked, only with a length.
        {"name": "lines", "uri": ARCHIVE, "count": True,
         "answers": [redirect(ASSETS), {"status": 200}]},
        {"name": "no_lines_unasked", "uri": ARCHIVE, "count": False,
         "answers": [redirect(ASSETS), {"status": 200}]},
        {"name": "no_lines_without_length", "uri": ARCHIVE, "count": True,
         "answers": [redirect(ASSETS), {"status": 200, "length": -1}]},
        # G2: every hop checked before it is asked.
        {"name": "hop_untrusted", "uri": ARCHIVE, "count": True,
         "answers": [redirect("https://downloads.example.com/archive.zip"), {"status": 200}]},
        {"name": "hop_http", "uri": ARCHIVE,
         "answers": [redirect("http://objects.githubusercontent.com/archive.zip", 301), {"status": 200}]},
        {"name": "hop_relative", "uri": ARCHIVE,
         "answers": [redirect("/example-owner/example-repo/releases/assets/1?x=1", 303),
                     redirect(OBJECTS, 307), redirect(ASSETS, 308), {"status": 200}]},
        {"name": "five_hops", "uri": ARCHIVE,
         "answers": [redirect("https://github.com/hop%d" % n) for n in range(1, 5)] + [redirect(ASSETS),
                                                                                         {"status": 200}]},
        {"name": "six_hops", "uri": ARCHIVE,
         "answers": [redirect("https://github.com/hop%d" % n) for n in range(1, 7)] + [{"status": 200}]},
        # What the cmdlet's request did with the rest of 3xx: followed a 300 with a Location, failed on any other
        # it did not follow, and on a Location that is no address.
        {"name": "multiple_choices", "uri": ARCHIVE,
         "answers": [redirect(ASSETS, 300), {"status": 200}]},
        {"name": "not_modified", "uri": ARCHIVE,
         "answers": [{"status": 304, "location": ASSETS, "to": 0, "length": 0}, {"status": 200}]},
        {"name": "redirect_nowhere", "uri": ARCHIVE,
         "answers": [{"status": 302, "to": 0, "length": 0}, {"status": 200}]},
        {"name": "answer_untrusted", "uri": ARCHIVE,
         "answers": [{"status": 200, "final": "https://downloads.example.com/archive.zip"}]},
        # G3 / G5: no partial file; a short body named.
        {"name": "drop_without_length", "uri": ARCHIVE,
         "answers": [redirect(ASSETS), {"status": 200, "length": -1, "drop": 100000}]},
        {"name": "short_body", "uri": ARCHIVE, "count": True,
         "answers": [redirect(ASSETS), {"status": 200, "to": 200000, "length": SIZE}]},
        {"name": "target_cannot_be_written", "uri": ARCHIVE, "readonly": True,
         "answers": [redirect(ASSETS), {"status": 200}]},
        # G6: a dropped connection resumed from where it stopped, through the same checks.
        {"name": "resumed", "uri": ARCHIVE, "count": True,
         "answers": [redirect(ASSETS), {"status": 200, "drop": 100000},
                     redirect(OBJECTS), {"status": 206, "from": 100000, "range": "bytes 100000-299999/300000"}]},
        {"name": "resumed_twice", "uri": ARCHIVE,
         "answers": [redirect(ASSETS), {"status": 200, "drop": 70000},
                     redirect(ASSETS), {"status": 206, "from": 70000, "drop": 50000,
                                        "range": "bytes 70000-299999/300000"},
                     redirect(ASSETS), {"status": 206, "from": 120000, "range": "bytes 120000-299999/*"}]},
        {"name": "dropped_three_times", "uri": ARCHIVE,
         "answers": [redirect(ASSETS), {"status": 200, "drop": 70000},
                     redirect(ASSETS), {"status": 206, "from": 70000, "drop": 50000,
                                        "range": "bytes 70000-299999/300000"},
                     redirect(ASSETS), {"status": 206, "from": 120000, "drop": 1000,
                                        "range": "bytes 120000-299999/300000"},
                     redirect(ASSETS), {"status": 206, "from": 121000, "range": "bytes 121000-299999/300000"}]},
        {"name": "resume_answered_200", "uri": ARCHIVE,
         "answers": [redirect(ASSETS), {"status": 200, "drop": 100000}, redirect(ASSETS), {"status": 200}]},
        {"name": "resume_wrong_start", "uri": ARCHIVE,
         "answers": [redirect(ASSETS), {"status": 200, "drop": 100000},
                     redirect(ASSETS), {"status": 206, "from": 90000, "range": "bytes 90000-299999/300000"}]},
        {"name": "resume_wrong_end", "uri": ARCHIVE,
         "answers": [redirect(ASSETS), {"status": 200, "drop": 100000},
                     redirect(ASSETS), {"status": 206, "from": 100000, "to": 200000,
                                        "range": "bytes 100000-199999/300000"}]},
        {"name": "resume_failed", "uri": ARCHIVE,
         "answers": [redirect(ASSETS), {"status": 200, "drop": 100000}, {"throw": "io"}]},
        {"name": "resume_redirected_away", "uri": ARCHIVE,
         "answers": [redirect(ASSETS), {"status": 200, "drop": 100000},
                     redirect("https://downloads.example.com/rest.zip"), {"status": 206}]},
        {"name": "drop_before_first_byte", "uri": ARCHIVE,
         "answers": [redirect(ASSETS), {"status": 200, "drop": 0}, {"status": 206}]},
        # L2: the failures' words and what they carry.
        {"name": "not_found", "uri": ARCHIVE,
         "answers": [{"throw": "web", "status": 404, "message": "The remote server returned an error: (404) Not Found."}]},
        {"name": "rate_limited", "uri": ARCHIVE,
         "answers": [{"throw": "web", "status": 403, "message": "The remote server returned an error: (403) Forbidden.",
                      "headers": {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1999999999"}}]},
        # L4: the old path only where the request cannot be made.
        {"name": "cannot_make_the_request", "uri": ARCHIVE, "cannot": True, "old": ASSETS, "answers": []},
    ]

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        root = Path(cls.folder.name)
        cases = root / "cases.json"
        cases.write_text(json.dumps(cls.CASES), encoding="utf-8")
        # A case whose folder cannot be written to: the file the download writes fails there, not the connection.
        environment = dict(os.environ, CAR_BOOTSTRAP=str(BOOTSTRAP), CAR_CASES=str(cases), CAR_ROOT=str(root),
                           CAR_SIZE=str(SIZE))
        probe = WANTED_STANDIN + STANDIN_PROBE.replace(
            "    $out = Join-Path $folder 'download.zip'\n",
            "    $out = Join-Path $folder 'download.zip'\n"
            "    if (Get-Field $case 'readonly' $false) { $out = Join-Path $folder 'no-such-folder\\download.zip' }\n")
        done = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", probe],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=600, env=environment)
        cls.stdout, cls.stderr, cls.code = done.stdout, done.stderr, done.returncode
        cls.results = {}
        marker = cls.stdout.rfind("@@RESULTS@@")
        if done.returncode == 0 and marker >= 0:
            answer = json.loads(cls.stdout[marker + len("@@RESULTS@@"):])
            cls.results = {row["name"]: row for row in answer["cases"]}
            cls.words = answer["words"]
            cls.too_many = cls.words["net_tooManyRedirections"]

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def case(self, name):
        self.assertEqual(self.code, 0, self.stderr[-3000:] + self.stdout[-3000:])
        self.assertIn(name, self.results, self.stdout[-3000:])
        row = self.results[name]
        for key in ("printed", "asked", "leftovers"):
            row[key] = [] if row[key] is None else (row[key] if isinstance(row[key], list) else [row[key]])
        # Whatever happened, every response asked for was closed and no partial file is left beside the target.
        self.assertEqual(row["open"], 0, row)
        self.assertEqual(row["leftovers"], [], row)
        return row

    def assertNothingWritten(self, row):
        self.assertIsNone(row["file"], row)
        self.assertEqual(row["leftovers"], [], row)

    # ------------------------------------------------------------------ G1
    def test_the_archive_bytes_are_counted_when_the_window_asked(self):
        row = self.case("lines")
        self.assertIsNone(row["threw"], row)
        self.assertEqual(row["file"], BODY_SHA)
        lines = [line.strip() for line in row["printed"]]
        self.assertTrue(lines, row)
        counts = []
        for line in lines:
            self.assertRegex(line, r"^progress: download [0-9]+/300000$")
            counts.append(int(line.split(" ")[2].split("/")[0]))
        # Real counts: what the 64 KB reads brought, rising, ending at the whole body.
        self.assertEqual(counts, sorted(set(counts)))
        self.assertEqual(counts[-1], SIZE)
        self.assertTrue(all(count % 65536 == 0 for count in counts[:-1]), counts)
        self.assertLessEqual(len(counts), 100)

    def test_no_line_when_the_window_did_not_ask(self):
        row = self.case("no_lines_unasked")
        self.assertIsNone(row["threw"], row)
        self.assertEqual(row["file"], BODY_SHA)
        self.assertEqual(row["printed"], [])

    def test_no_line_without_a_length(self):
        row = self.case("no_lines_without_length")
        self.assertIsNone(row["threw"], row)
        self.assertEqual(row["file"], BODY_SHA)
        self.assertEqual(row["printed"], [])

    def test_the_whole_run_prints_nothing_of_its_own(self):
        """Every case's output was its own (above); the PowerShell around them printed nothing else - no progress
        record reaches the output a caller reads."""
        self.assertEqual(self.code, 0, self.stderr[-3000:])
        self.assertEqual(self.stdout[:self.stdout.rfind("@@RESULTS@@")].strip(), "")

    # ------------------------------------------------------------------ G2
    def test_a_hop_to_an_untrusted_host_is_refused_before_it_is_asked(self):
        row = self.case("hop_untrusted")
        self.assertEqual(row["threw"], "The archive " + REFUSED + "downloads.example.com")
        self.assertEqual([ask["uri"] for ask in row["asked"]], [ARCHIVE])
        self.assertNothingWritten(row)
        self.assertEqual(row["printed"], [])
        self.assertEqual(row["old"], 0, "a host refusal is never tried another way")

    def test_a_hop_over_http_is_refused_before_it_is_asked(self):
        row = self.case("hop_http")
        self.assertEqual(row["threw"], "The archive " + REFUSED + "objects.githubusercontent.com")
        self.assertEqual(len(row["asked"]), 1)
        self.assertNothingWritten(row)
        self.assertEqual(row["old"], 0)

    def test_a_relative_location_is_followed_and_every_kind_of_redirect(self):
        row = self.case("hop_relative")
        self.assertIsNone(row["threw"], row)
        self.assertEqual(row["file"], BODY_SHA)
        self.assertEqual([ask["uri"] for ask in row["asked"]],
                         [ARCHIVE, "https://github.com/example-owner/example-repo/releases/assets/1?x=1",
                          OBJECTS, ASSETS])
        # Each request follows nothing by itself, asks from the start, and is the cmdlet's: its timeout, its agent.
        for ask in row["asked"]:
            self.assertIs(ask["redirects"], False)
            self.assertEqual(ask["range"], "")
            self.assertEqual(ask["timeout"], 300000)
            self.assertRegex(ask["agent"], r"^Mozilla/5\.0 \(Windows NT; Windows NT [0-9.]+; [A-Za-z-]*\) "
                                           r"WindowsPowerShell/5\.1\.")

    def test_five_redirects_are_followed_and_a_sixth_is_refused(self):
        row = self.case("five_hops")
        self.assertIsNone(row["threw"], row)
        self.assertEqual(row["file"], BODY_SHA)
        self.assertEqual(len(row["asked"]), 6)
        row = self.case("six_hops")
        # .NET's own words for it, in this Windows' language (RealRequestBesideTheCmdletTests: the cmdlet's).
        self.assertIn(self.too_many, (TOO_MANY, row["threw"]))
        self.assertNotEqual(self.too_many, "none")
        self.assertEqual(row["threw"], self.too_many)
        self.assertEqual(row["type"], "System.Net.WebException")
        self.assertEqual(len(row["asked"]), 6, "the sixth Location is never asked")
        self.assertNothingWritten(row)

    def test_an_answer_from_an_untrusted_host_writes_nothing(self):
        row = self.case("answer_untrusted")
        self.assertEqual(row["threw"], "The archive " + REFUSED + "downloads.example.com")
        self.assertNothingWritten(row)
        self.assertEqual(row["old"], 0)

    # ------------------------------------------------------------------ G3 / G5
    def test_a_connection_lost_without_a_length_leaves_no_partial_file(self):
        row = self.case("drop_without_length")
        self.assertEqual(row["type"], "System.IO.IOException")
        self.assertIn("transport connection", row["threw"])
        self.assertEqual(len(row["asked"]), 2, "nothing to resume against without a length")
        self.assertNothingWritten(row)

    def test_a_short_body_is_named_as_cut_short(self):
        row = self.case("short_body")
        self.assertEqual(row["threw"], "The archive was cut short: 200000 of 300000 bytes arrived.")
        self.assertNothingWritten(row)
        self.assertEqual(len(row["asked"]), 2, "a body that ended cleanly is not asked for again")

    def test_a_target_that_cannot_be_written_is_not_a_dropped_connection(self):
        row = self.case("target_cannot_be_written")
        self.assertIsNotNone(row["threw"], row)
        self.assertNotIn("cut short", row["threw"])
        self.assertEqual(len(row["asked"]), 2, "a failure of this machine's is not resumed")
        self.assertEqual(row["old"], 0)

    # ------------------------------------------------------------------ G6
    def test_a_dropped_connection_is_resumed_from_where_it_stopped(self):
        row = self.case("resumed")
        self.assertIsNone(row["threw"], row)
        self.assertEqual(row["file"], BODY_SHA, "byte for byte the whole body")
        self.assertEqual([(ask["uri"], ask["range"]) for ask in row["asked"]],
                         [(ARCHIVE, ""), (ASSETS, ""), (ARCHIVE, "bytes=100000-"), (OBJECTS, "bytes=100000-")])
        counts = [int(line.strip().split(" ")[2].split("/")[0]) for line in row["printed"]]
        self.assertEqual(counts, sorted(set(counts)))
        self.assertEqual(counts[-1], SIZE)

    def test_a_connection_dropped_twice_is_resumed_twice(self):
        row = self.case("resumed_twice")
        self.assertIsNone(row["threw"], row)
        self.assertEqual(row["file"], BODY_SHA)
        self.assertEqual([ask["range"] for ask in row["asked"]],
                         ["", "", "bytes=70000-", "bytes=70000-", "bytes=120000-", "bytes=120000-"])

    def test_a_third_drop_is_not_resumed(self):
        row = self.case("dropped_three_times")
        self.assertEqual(row["threw"], "The archive was cut short: 121000 of 300000 bytes arrived.")
        self.assertEqual(len(row["asked"]), 6)
        self.assertNothingWritten(row)

    def test_a_resume_answered_otherwise_is_cut_short_with_nothing_left(self):
        for name, received in (("resume_answered_200", 100000), ("resume_wrong_start", 100000),
                               ("resume_wrong_end", 100000), ("resume_failed", 100000)):
            with self.subTest(name):
                row = self.case(name)
                self.assertEqual(row["threw"], "The archive was cut short: %d of 300000 bytes arrived." % received)
                self.assertNothingWritten(row)
                self.assertEqual(row["old"], 0)

    def test_a_300_with_a_location_is_followed(self):
        row = self.case("multiple_choices")
        self.assertIsNone(row["threw"], row)
        self.assertEqual(row["file"], BODY_SHA)
        self.assertEqual([ask["uri"] for ask in row["asked"]], [ARCHIVE, ASSETS])

    def test_a_3xx_the_cmdlet_did_not_follow_fails_as_it_failed(self):
        for name in ("not_modified", "redirect_nowhere"):
            with self.subTest(name):
                row = self.case(name)
                self.assertEqual(row["type"], "System.Net.WebException")
                self.assertEqual(row["status"], "ProtocolError")
                self.assertEqual(row["carried"], 1, "the response on it, as .NET puts it there")
                self.assertEqual(len(row["asked"]), 1)
                self.assertNothingWritten(row)
        expected = self.words["net_servererror"].replace(
            "{0}", "(304) " + self.words["net_httpstatuscode_NotModified"])
        self.assertEqual(self.case("not_modified")["threw"], expected)
        self.assertTrue(self.case("redirect_nowhere")["threw"].startswith(
            self.words["net_servererror"].split("{0}")[0] + "(302)"))

    def test_a_resume_redirected_away_is_refused_in_the_hosts_words(self):
        row = self.case("resume_redirected_away")
        self.assertEqual(row["threw"], "The archive " + REFUSED + "downloads.example.com")
        self.assertEqual(len(row["asked"]), 3)
        self.assertNothingWritten(row)
        self.assertEqual(row["old"], 0)

    def test_a_failure_before_the_first_byte_is_not_resumed(self):
        row = self.case("drop_before_first_byte")
        self.assertEqual(row["type"], "System.IO.IOException")
        self.assertEqual(len(row["asked"]), 2)
        self.assertNothingWritten(row)

    # ------------------------------------------------------------------ L2 / L4
    def test_an_http_error_is_thrown_as_it_came(self):
        row = self.case("not_found")
        self.assertEqual(row["threw"], "The remote server returned an error: (404) Not Found.")
        self.assertEqual(row["type"], "System.Net.WebException")
        self.assertIsNone(row["reset"])
        self.assertNothingWritten(row)
        self.assertEqual(row["old"], 0, "an HTTP error is the answer; nothing else is tried")

    def test_a_rate_limit_is_still_found_on_what_was_thrown(self):
        row = self.case("rate_limited")
        self.assertEqual(row["threw"], "The remote server returned an error: (403) Forbidden.")
        self.assertEqual(row["reset"], "1999999999")
        self.assertEqual(row["old"], 0)

    def test_the_old_path_only_where_the_request_cannot_be_made(self):
        row = self.case("cannot_make_the_request")
        self.assertIsNone(row["threw"], row)
        self.assertEqual(row["old"], 1)
        self.assertEqual(row["asked"], [])
        self.assertEqual(row["file"], BODY_SHA)


# --------------------------------------------------------------------------- the real request beside the real cmdlet
class Recorder(http.server.BaseHTTPRequestHandler):
    """A server on 127.0.0.1 that answers what GitHub would, for one path each, and writes down what it was sent."""
    protocol_version = "HTTP/1.1"
    seen: list = []

    def log_message(self, *arguments):
        pass

    def do_GET(self):
        Recorder.seen.append((self.path, [(name, value) for name, value in self.headers.items()]))
        if self.path == "/missing":
            self.answer(404, b"Not Found")
        elif self.path == "/rate":
            self.answer(403, b"rate limit", {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1999999999"})
        elif self.path == "/notmodified":
            self.answer(304, b"", {"Location": "/ok"})
        elif self.path == "/nowhere":
            self.answer(302, b"")
        elif self.path.startswith("/loop"):
            self.answer(302, b"", {"Location": "/loop%d" % len(Recorder.seen)})
        elif self.path == "/slow":
            time.sleep(5)
            self.answer(200, b"late")
        else:
            self.answer(200, b"ok")

    def answer(self, status, body, headers=None):
        try:
            self.send_response(status)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass


class QuietServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass


REAL_PROBE = r"""
$wanted = @('Get-ThrownException', 'Get-DownloadWords', 'New-DownloadRequest', 'Get-DownloadResponse',
            'Get-RateLimitReset', 'New-ServerError')
""" + LIFT + r"""
$base = $env:CAR_SERVER
function Get-Outcome { param([scriptblock]$Ask)
    try { & $Ask; return @{ threw = $null } }
    catch {
        $e = $_.Exception
        $status = $null
        if ($e -is [Net.WebException]) { $status = [string]$e.Status }
        return @{ threw = $e.Message; type = $e.GetType().FullName; status = $status; reset = (Get-RateLimitReset $e) }
    }
}
$out = @{}
$scratch = Join-Path $env:CAR_ROOT 'cmdlet.bin'
foreach ($pair in @(@('/missing', 300), @('/rate', 300), @('/agent', 300), @('/slow', 2))) {
    $path = $pair[0]; $seconds = $pair[1]
    $new = Get-Outcome {
        $request = New-DownloadRequest -Uri ([Uri]($base + $path)) -Offset 0 -Cookies (New-Object Net.CookieContainer) `
                                       -TimeoutSec $seconds
        $response = Get-DownloadResponse -Request $request
        $response.Close()
    }
    $old = Get-Outcome {
        $null = Invoke-WebRequest -Uri ($base + $path) -OutFile $scratch -UseBasicParsing -PassThru -MaximumRedirection 5 `
                                  -TimeoutSec $seconds
    }
    $out[$path] = @{ new = $new; old = $old }
}
# Redirected for ever: the cmdlet's words when -MaximumRedirection 5 runs out, and the ones the streamed download says.
$old = Get-Outcome { $null = Invoke-WebRequest -Uri ($base + '/loop') -OutFile $scratch -UseBasicParsing -PassThru `
                                               -MaximumRedirection 5 -TimeoutSec 300 }
$out['loop'] = @{ old = $old; words = (Get-DownloadWords -Source 'net' -Name 'net_tooManyRedirections' -Fallback 'none') }
# A 3xx the cmdlet's request did not follow, asked by the streamed download's own request, which follows none.
foreach ($path in @('/notmodified', '/nowhere')) {
    $new = Get-Outcome {
        $request = New-DownloadRequest -Uri ([Uri]($base + $path)) -Offset 0 -Cookies (New-Object Net.CookieContainer) -TimeoutSec 300
        $response = Get-DownloadResponse -Request $request
        throw (New-ServerError -Response $response)
    }
    $old = Get-Outcome { $null = Invoke-WebRequest -Uri ($base + $path) -OutFile $scratch -UseBasicParsing -PassThru `
                                                   -MaximumRedirection 5 -TimeoutSec 300 }
    $out[$path] = @{ new = $new; old = $old }
}
# A request that fails as it is sent: one aborted before.
$request = New-DownloadRequest -Uri ([Uri]($base + '/agent2')) -Offset 0 -Cookies (New-Object Net.CookieContainer) -TimeoutSec 300
$request.Abort()
$out['aborted'] = Get-Outcome { $null = Get-DownloadResponse -Request $request }
# A port nothing listens on.
$new = Get-Outcome {
    $request = New-DownloadRequest -Uri ([Uri]$env:CAR_CLOSED) -Offset 0 -Cookies (New-Object Net.CookieContainer) -TimeoutSec 300
    $null = Get-DownloadResponse -Request $request
}
$old = Get-Outcome { $null = Invoke-WebRequest -Uri $env:CAR_CLOSED -OutFile $scratch -UseBasicParsing -PassThru -TimeoutSec 300 }
$out['closed'] = @{ new = $new; old = $old }
# The request as it is made: what the cmdlet leaves as .NET has it, and what it sets.
$request = New-DownloadRequest -Uri ([Uri]'https://github.com/x') -Offset 4096 -Cookies (New-Object Net.CookieContainer) -TimeoutSec 300
$out['request'] = @{
    proxy = [object]::ReferenceEquals($request.Proxy, [Net.WebRequest]::DefaultWebProxy)
    credentials = ($null -eq $request.Credentials); defaultCredentials = $request.UseDefaultCredentials
    readWrite = $request.ReadWriteTimeout; timeout = $request.Timeout; keepAlive = $request.KeepAlive
    redirects = $request.AllowAutoRedirect; range = [string]$request.Headers['Range']; method = $request.Method
    certificateCheck = ($null -eq $request.ServerCertificateValidationCallback)
    agent = $request.UserAgent; cmdletAgent = (New-Object Microsoft.PowerShell.Commands.WebRequestSession).UserAgent
    unlimited = (New-DownloadRequest -Uri ([Uri]'https://github.com/x') -Offset 0 -Cookies $null -TimeoutSec 0).Timeout
}
'@@RESULTS@@' + (ConvertTo-Json -InputObject $out -Depth 6 -Compress)
"""


@unittest.skipUnless(POWERSHELL.is_file(), "the bootstrap is PowerShell on Windows")
class RealRequestBesideTheCmdletTests(unittest.TestCase):
    """The streamed download's own request and door, unreplaced, beside Invoke-WebRequest on the same server."""

    @classmethod
    def setUpClass(cls):
        Recorder.seen = []
        cls.server = QuietServer(("127.0.0.1", 0), Recorder)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        closed = QuietServer(("127.0.0.1", 0), Recorder)
        closed_port = closed.server_address[1]
        closed.server_close()
        cls.folder = tempfile.TemporaryDirectory()
        environment = dict(os.environ, CAR_BOOTSTRAP=str(BOOTSTRAP), CAR_ROOT=cls.folder.name,
                           CAR_SERVER="http://127.0.0.1:%d" % cls.server.server_address[1],
                           CAR_CLOSED="http://127.0.0.1:%d/x" % closed_port)
        done = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", REAL_PROBE],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=300, env=environment)
        cls.done = done
        marker = done.stdout.rfind("@@RESULTS@@")
        cls.out = json.loads(done.stdout[marker + len("@@RESULTS@@"):]) if done.returncode == 0 and marker >= 0 else None

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.folder.cleanup()

    def outcome(self, key):
        self.assertIsNotNone(self.out, self.done.stderr[-3000:] + self.done.stdout[-3000:])
        return self.out[key]

    def test_an_http_error_reads_as_the_cmdlet_says_it(self):
        pair = self.outcome("/missing")
        self.assertIsNotNone(pair["new"]["threw"])
        self.assertEqual(pair["new"], pair["old"])

    def test_a_rate_limit_reads_as_the_cmdlet_says_it_and_its_reset_is_found(self):
        pair = self.outcome("/rate")
        self.assertEqual(pair["new"]["reset"], "1999999999")
        self.assertEqual(pair["new"], pair["old"])

    def test_a_timeout_reads_as_the_cmdlet_says_it(self):
        pair = self.outcome("/slow")
        self.assertEqual(pair["new"]["status"], "Timeout")
        self.assertEqual(pair["new"], pair["old"])

    def test_a_refused_connection_reads_as_the_cmdlet_says_it(self):
        pair = self.outcome("closed")
        self.assertIsNotNone(pair["new"]["threw"])
        self.assertEqual(pair["new"], pair["old"])

    def test_too_many_redirects_read_as_the_cmdlet_says_it(self):
        loop = self.outcome("loop")
        self.assertEqual(loop["old"]["status"], "ProtocolError")
        self.assertEqual(loop["old"]["type"], "System.Net.WebException")
        self.assertNotEqual(loop["words"], "none")
        # The cmdlet's .NET request says it on whichever thread finished the request, in that thread's language: on a
        # Windows installed in one language and shown in another, sometimes the installed one (and not always readable
        # through the console), sometimes the shown one - the one PowerShell's own thread, and the streamed download,
        # say it in. Where it came in the shown one, the words are the same.
        if loop["old"]["threw"].isascii():
            self.assertEqual(loop["words"], loop["old"]["threw"])

    def test_a_3xx_not_followed_reads_as_the_cmdlet_says_it(self):
        for path in ("/notmodified", "/nowhere"):
            with self.subTest(path):
                pair = self.outcome(path)
                self.assertEqual(pair["new"]["type"], pair["old"]["type"])
                self.assertEqual(pair["new"]["status"], pair["old"]["status"])
                # In the language shown, the same words (see the too-many-redirects test for why only there).
                if pair["old"]["threw"].isascii():
                    self.assertEqual(pair["new"], pair["old"])

    def test_a_request_failing_as_it_is_sent_fails_in_its_own_words(self):
        aborted = self.outcome("aborted")
        self.assertEqual(aborted["type"], "System.Net.WebException")
        self.assertEqual(aborted["status"], "RequestCanceled")
        self.assertFalse(aborted["threw"].startswith("Exception calling"), aborted)

    def test_the_request_is_sent_as_the_cmdlet_sends_its_own(self):
        pair = self.outcome("/agent")
        self.assertIsNone(pair["new"]["threw"])
        # Connection: Keep-Alive goes with the first request on a connection only, which says where .NET's pool
        # stood, not how the request was made.
        sent = [[(name, value) for name, value in headers if name.lower() != "connection"]
                for path, headers in Recorder.seen if path == "/agent"]
        self.assertEqual(len(sent), 2)
        self.assertIn("user-agent", [name.lower() for name, value in sent[0]])
        self.assertEqual(sent[0], sent[1], "the same headers, in the same order, with the same values")

    def test_the_request_is_made_as_the_cmdlet_makes_its_own(self):
        made = self.outcome("request")
        self.assertIs(made["proxy"], True, "the system proxy, as .NET has it")
        self.assertIs(made["credentials"], True)
        self.assertIs(made["defaultCredentials"], False)
        self.assertEqual(made["readWrite"], 300000, "the read timeout .NET leaves, as the cmdlet does")
        self.assertEqual(made["timeout"], 300000)
        self.assertEqual(made["unlimited"], -1, "-TimeoutSec 0 waits as long as it takes")
        self.assertIs(made["keepAlive"], True)
        self.assertIs(made["redirects"], False)
        self.assertEqual(made["range"], "bytes=4096-")
        self.assertEqual(made["method"], "GET")
        self.assertIs(made["certificateCheck"], True, "the certificate is checked as .NET checks it")
        self.assertEqual(made["agent"], made["cmdletAgent"])


if __name__ == "__main__":
    unittest.main()
