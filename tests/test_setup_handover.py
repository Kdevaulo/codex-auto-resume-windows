r"""The setup handover (v0.6.26): a verified archive that names its own setup program is installed by it.

From v0.6.27 the product is not Python, so its archive need not be the shape Test-Archive requires. The last Python
release's bootstrap learns one explicit way to install such a release: an archive that carries setup-handover.json at
its root (format codex-auto-resume/setup-handover/1, with the version, the edition and the setup program's path inside
the archive) is checked, unpacked, and handed to that program, started with install.ps1's own switches after
`-Handover <update|another|install> -Edition <edition>`, and waited for. The run says `update: handover <from> <version>
<code>` or `pick: handover <version> <edition> <code>` and exits 17: neither failed nor installed by the bootstrap.
Anything else is refused as before, and an archive without the marker is held to Test-Archive exactly as it always was.

The whole script runs as tests/test_edition_bootstrap.py runs it: a scratch plugin at 9.9.9, a scratch home and TEMP,
a stubbed network that serves only the archive and its checksum, and an installer stub that writes down how it was
bound. The setup program is a stand-in compiled here with the in-box C# compiler, of the Windows GUI subsystem, which
creates no window: it writes its arguments, the home it was given and whether the folder it came in is still there,
and ends with the code a case names. The Dashboard's readers of the two lines are compiled from gui/ and called
through reflection, as tests/test_gui_update.py and tests/test_gui_versions.py call theirs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import guiscan  # noqa: E402
from download_standin import BRIDGE  # noqa: E402
from test_edition_bootstrap import PACKAGE, required_entries, stub_installer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "scripts" / "bootstrap.ps1"
POWERSHELL = (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
              / "WindowsPowerShell" / "v1.0" / "powershell.exe")
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
RELEASE = json.loads((ROOT / "scripts" / "release.json").read_text(encoding="utf-8"))
TAG = "https://github.com/%s/%s/releases/tag/" % (RELEASE["owner"], RELEASE["repo"])
NOWHERE = "https://127.0.0.1:1/releases"
FORMAT = "codex-auto-resume/setup-handover/1"
SETUP = "payload/app/bin/setup.exe"

# The stand-in setup program. Every path through it ends with a code and nothing on the screen: no window is made, and
# an exception is caught rather than left to .NET, whose unhandled-exception box would open on the desktop.
STAND_IN = r"""
using System;
using System.IO;
using System.Text;
static class Program
{
    static int Main(string[] arguments)
    {
        try
        {
            string folder = Path.GetDirectoryName(typeof(Program).Assembly.Location);
            var text = new StringBuilder();
            text.Append("home=").Append(Environment.GetEnvironmentVariable("CODEX_AUTO_RESUME_PLUGIN_HOME")).Append('\n');
            text.Append("beside=").Append(File.Exists(Path.Combine(folder, "beside.txt"))).Append('\n');
            foreach (string argument in arguments) text.Append("arg=").Append(argument).Append('\n');
            File.WriteAllText(Environment.GetEnvironmentVariable("CAR_HANDED"), text.ToString());
            int code;
            return int.TryParse(Environment.GetEnvironmentVariable("CAR_SETUP_CODE"), out code) ? code : 0;
        }
        catch (Exception)
        {
            return 99;
        }
    }
}
"""

RUN = BRIDGE + r"""
function global:Invoke-WebRequest {
    param([string]$Uri, [string]$OutFile, [switch]$UseBasicParsing, [switch]$PassThru,
          [int]$MaximumRedirection, [int]$TimeoutSec, [string]$Method)
    Add-Content -LiteralPath $env:CAR_REQUESTS -Value (([string]$Method) + ' ' + $Uri) -Encoding UTF8
    $base = New-Object psobject
    if ($Method -eq 'Head' -and $env:CAR_LATEST) {
        $base | Add-Member -MemberType NoteProperty -Name ResponseUri -Value ([Uri]$env:CAR_LATEST)
    } elseif ($OutFile -and $env:CAR_ZIP -and $Uri.EndsWith('.zip')) {
        Copy-Item -LiteralPath $env:CAR_ZIP -Destination $OutFile
        $base | Add-Member -MemberType NoteProperty -Name ResponseUri -Value ([Uri]'https://release-assets.githubusercontent.com/a')
    } elseif ($OutFile -and $env:CAR_SUM -and $Uri.EndsWith('.zip.sha256')) {
        Copy-Item -LiteralPath $env:CAR_SUM -Destination $OutFile
        $base | Add-Member -MemberType NoteProperty -Name ResponseUri -Value ([Uri]'https://release-assets.githubusercontent.com/b')
    } else {
        throw 'there is no network here'
    }
    $response = New-Object psobject
    $response | Add-Member -MemberType NoteProperty -Name BaseResponse -Value $base
    return $response
}
$arguments = @{}
foreach ($pair in (ConvertFrom-Json $env:CAR_ARGUMENTS).PSObject.Properties) { $arguments[$pair.Name] = $pair.Value }
& $env:CAR_SCRIPT @arguments
exit $LASTEXITCODE
"""


def compiled(source: str, out: Path, target: str) -> Path:
    code = out.with_suffix(".cs")
    code.write_text(source, encoding="utf-8")
    subprocess.run([str(CSC), "/nologo", "/target:" + target, "/out:" + str(out), str(code)],
                   check=True, capture_output=True, timeout=300)
    return out


@unittest.skipUnless(POWERSHELL.is_file() and CSC.is_file(), "needs Windows PowerShell and the in-box C# compiler")
class HandoverRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.programs = tempfile.TemporaryDirectory()
        folder = Path(cls.programs.name)
        cls.gui = compiled(STAND_IN, folder / "gui.exe", "winexe").read_bytes()
        cls.console = compiled(STAND_IN, folder / "console.exe", "exe").read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.programs.cleanup()

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.plugin = self.root / "plugin"
        (self.plugin / "scripts").mkdir(parents=True)
        (self.plugin / ".codex-plugin").mkdir()
        shutil.copyfile(BOOTSTRAP, self.plugin / "scripts" / "bootstrap.ps1")
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        (self.plugin / ".codex-plugin" / "plugin.json").write_text(json.dumps(dict(manifest, version="9.9.9")),
                                                                    encoding="utf-8")
        release = dict(RELEASE, download=NOWHERE + "/download/v{version}/", latest=NOWHERE + "/latest")
        (self.plugin / "scripts" / "release.json").write_text(json.dumps(release), encoding="utf-8")
        self.home = self.root / "home"
        self.temp = self.root / "temp"
        self.temp.mkdir()
        self.requests = self.root / "requests.txt"
        self.installed = self.root / "installed.json"
        self.handed = self.root / "handed.txt"

    def installation(self, version, edition="standard"):
        (self.home / "runtime").mkdir(parents=True)
        (self.home / "runtime" / "python.exe").write_bytes(b"not a real interpreter")
        (self.home / "app" / ".codex-plugin").mkdir(parents=True)
        (self.home / "app" / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "codex-auto-resume", "version": version}), encoding="utf-8")
        (self.home / "app" / "scripts").mkdir()
        (self.home / "app" / "src" / "codex_auto_resume").mkdir(parents=True)
        if edition == "advanced":
            (self.home / "app" / "src" / PACKAGE).mkdir()
            (self.home / "app" / "src" / PACKAGE / "__init__.py").write_text("", encoding="utf-8")

    def archive(self, name="release.zip", python=False, edition="standard", marker="setup-handover.json",
                program=None, plugin_version="9.9.9", **said) -> Path:
        """A release archive: the stand-in at SETUP and a file beside it, the marker with `said` over a valid
        handover for 9.9.9 in `edition` (a value of None leaves the key out; marker=None leaves the file out), and
        with python=True every entry today's Test-Archive requires, its installer the recording stub."""
        manifest = {"format": FORMAT, "version": "9.9.9", "edition": edition, "setup": SETUP}
        manifest.update(said)
        manifest = {key: value for key, value in manifest.items() if value is not None}
        path = self.root / name
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr(SETUP, self.gui if program is None else program)
            bundle.writestr("payload/app/bin/beside.txt", "x")
            if marker:
                bundle.writestr(marker, json.dumps(manifest))
            if python:
                entries = required_entries()
                if edition == "advanced":
                    entries.append("payload/app/src/%s/__init__.py" % PACKAGE)
                for entry in entries:
                    if entry.endswith(".codex-plugin/plugin.json"):
                        bundle.writestr(entry, json.dumps({"name": "codex-auto-resume", "version": plugin_version}))
                    elif entry == "install/install.ps1":
                        bundle.writestr(entry, stub_installer())
                    else:
                        bundle.writestr(entry, "x")
        return path

    def run_it(self, latest=None, served=None, setup_code=None, given="", **arguments):
        environment = dict(os.environ, CODEX_AUTO_RESUME_PLUGIN_HOME=str(self.home), CODEX_AUTO_RESUME_OUTSIDE="1",
                           TEMP=str(self.temp), TMP=str(self.temp),
                           CAR_SCRIPT=str(self.plugin / "scripts" / "bootstrap.ps1"),
                           CAR_ARGUMENTS=json.dumps(arguments), CAR_REQUESTS=str(self.requests),
                           CAR_INSTALLED=str(self.installed), CAR_HANDED=str(self.handed),
                           CAR_LATEST=TAG + latest if latest else "", CAR_ZIP="", CAR_SUM="",
                           CAR_SETUP_CODE="" if setup_code is None else str(setup_code))
        if served:
            total = self.root / "served.sha256"
            total.write_text("%s  served.zip\n" % hashlib.sha256(served.read_bytes()).hexdigest(), encoding="utf-8")
            environment.update(CAR_ZIP=str(served), CAR_SUM=str(total))
        done = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                               "-Command", RUN], input=given, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", timeout=300, env=environment)
        return done.returncode, done.stdout

    def handed_over(self) -> dict:
        lines = self.handed.read_text(encoding="utf-8").splitlines()
        return {"home": lines[0][len("home="):], "beside": lines[1][len("beside="):],
                "arguments": [line[len("arg="):] for line in lines[2:]]}

    def assertLeftNothing(self):
        self.assertEqual(sorted(self.temp.glob("codex-auto-resume-*")), [], "the run's folder outlived it")

    def refused(self, path: Path, why: str, **arguments):
        code, output = self.run_it(ArchivePath=str(path), **arguments)
        self.assertEqual(code, 1, output[-2000:])
        self.assertIn(why, output)
        self.assertIn("Nothing was installed.", output)
        self.assertFalse(self.handed.exists(), "the setup program ran")
        self.assertFalse(self.installed.exists(), "the installer ran")
        self.assertLeftNothing()
        return output

    # ------------------------------------------------------------------------------------------- 1. handed over
    def test_the_setup_program_is_run_with_the_switches_and_the_run_says_it_handed_over(self):
        code, output = self.run_it(ArchivePath=str(self.archive()), NoStartup=True)
        self.assertEqual(code, 17, output[-2000:])
        self.assertIn("The archive asks to be installed by its own setup program, " + SETUP, output)
        self.assertIn("Handing over to the setup program of v9.9.9", output)
        self.assertIn("Handed over to the setup program of v9.9.9, which ended with code 0.", output)
        self.assertNotIn("Archive contents verified", output, "it is not the shape Test-Archive checks")
        for word in ("Installing", "Installation did not finish", "[!]"):
            self.assertNotIn(word, output)
        self.assertEqual(self.handed_over(), {"home": str(self.home), "beside": "True",
                                              "arguments": ["-Handover", "install", "-Edition", "standard",
                                                            "-SkipStartup"]})
        self.assertFalse(self.installed.exists())
        self.assertLeftNothing()

    def test_an_update_from_the_dashboard_says_handover_with_the_programs_code(self):
        self.installation("0.6.0")
        code, output = self.run_it(latest="v9.9.9", served=self.archive(), setup_code=3, given="install\n",
                                   Update=True, AskFirst=True)
        self.assertEqual(code, 17, output[-2000:])
        self.assertIn("SHA-256 matches the checksum published beside it", output)
        self.assertIn("ask: install v9.9.9", output)
        answers = [line for line in output.splitlines() if line.startswith("update: ")]
        self.assertEqual(answers, ["update: available 0.6.0 9.9.9", "update: handover 0.6.0 9.9.9 3"])
        self.assertEqual(self.handed_over()["arguments"], ["-Handover", "update", "-Edition", "standard"])
        self.assertLeftNothing()

    def test_an_asked_for_edition_change_is_passed_on_and_the_edition_is_named(self):
        self.installation("0.6.0", "standard")
        code, output = self.run_it(ArchivePath=str(self.archive(edition="advanced")), Edition="Advanced", Force=True)
        self.assertEqual(code, 17, output[-2000:])
        self.assertEqual(self.handed_over()["arguments"],
                         ["-Handover", "install", "-Edition", "advanced", "-AllowEditionChange"])

    def test_the_other_edition_is_still_refused_before_anything_is_fetched(self):
        self.installation("0.6.0", "standard")
        code, output = self.run_it(ArchivePath=str(self.archive(edition="advanced")), Edition="Advanced")
        self.assertEqual(code, 14, output[-2000:])
        self.assertFalse(self.handed.exists())

    # ----------------------------------------------------------------------------- 2. a path out of the folder
    def test_a_setup_path_that_could_leave_the_folder_is_refused(self):
        for setup in ("../setup.exe", "payload/../../setup.exe", "/setup.exe", "C:/setup.exe", "C:setup.exe",
                      "payload\\app\\bin\\setup.exe", "payload/./app/bin/setup.exe", "payload/app./bin/setup.exe",
                      "payload//app/bin/setup.exe", "payload/app/bin/setup.exe ", "payload/app/bin/setup.cmd",
                      "payload/app/bin/other.exe", "PAYLOAD/app/bin/setup.exe"):
            with self.subTest(setup):
                self.refused(self.archive(setup=setup), "names no program of its own")

    def test_an_entry_that_escapes_the_folder_is_refused(self):
        path = self.archive()
        with zipfile.ZipFile(path, "a") as bundle:
            info = zipfile.ZipInfo("placeholder")
            info.filename = "payload/../../outside.txt"
            bundle.writestr(info, "x")
        self.refused(path, "unsafe path")

    # ----------------------------------------------------------------------------- 3. version, edition, format
    def test_another_version_edition_or_format_is_refused(self):
        cases = ({"version": "9.9.8"}, {"edition": "advanced"}, {"edition": "Standard"},
                 {"format": "codex-auto-resume/setup-handover/2"}, {"format": None}, {"version": 9},
                 {"setup": None})
        for said in cases:
            with self.subTest(said):
                self.handed.unlink(missing_ok=True)
                self.refused(self.archive(**said), "setup handover")

    def test_a_marker_in_another_casing_or_not_json_is_refused(self):
        self.refused(self.archive(marker="Setup-Handover.json"), "unexpected casing")
        path = self.root / "garbled.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("setup-handover.json", "{not json")
            bundle.writestr(SETUP, self.gui)
        self.refused(path, "is not JSON")

    # ----------------------------------------------------------------------------------- 4. not a Windows program
    def test_a_program_that_is_not_a_windows_gui_image_is_refused(self):
        for name, program in (("text", b"not a program at all"), ("console", self.console),
                              ("short", b"MZ" + b"\0" * 10)):
            with self.subTest(name):
                self.refused(self.archive(program=program), "is not a Windows program")

    def test_a_link_on_the_way_to_the_program_is_refused(self):
        """Lifted out of the script: an unpacked folder whose way to the program goes through a junction."""
        unpacked = self.root / "unpacked"
        target = self.root / "elsewhere" / "bin"
        target.mkdir(parents=True)
        (target / "setup.exe").write_bytes(self.gui)
        (unpacked / "payload").mkdir(parents=True)
        made = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(unpacked / "payload" / "app"),
                               str(target.parent)], capture_output=True, text=True)
        if made.returncode != 0:
            self.skipTest("no junction could be made here: " + made.stdout + made.stderr)
        body = (r"try { Resolve-SetupProgram -Unpacked $env:CAR_UNPACKED -Setup 'payload/app/bin/setup.exe' } "
                r"catch { $_.Exception.Message }")
        said = lifted(["Resolve-SetupProgram"], body, CAR_UNPACKED=str(unpacked))
        self.assertIn("is a link", said)
        plain = self.root / "plain"
        (plain / "payload" / "app" / "bin").mkdir(parents=True)
        (plain / "payload" / "app" / "bin" / "setup.exe").write_bytes(self.gui)
        said = lifted(["Resolve-SetupProgram"], body, CAR_UNPACKED=str(plain))
        self.assertEqual(said, str(plain / "payload" / "app" / "bin" / "setup.exe"))

    # ------------------------------------------------------------------------- 5. and 6. no marker: as before
    def test_a_python_shaped_archive_without_the_marker_is_installed_as_before(self):
        code, output = self.run_it(ArchivePath=str(self.archive(python=True, marker=None)), NoStartup=True)
        self.assertEqual(code, 0, output[-2000:])
        self.assertIn("Archive contents verified as Codex Auto Resume v9.9.9", output)
        self.assertIn("  Installing", output)
        for word in ("setup program", "handover", "Handing over"):
            self.assertNotIn(word, output)
        self.assertEqual(json.loads(self.installed.read_text(encoding="utf-8-sig")),
                         {"PluginName": "codex-auto-resume", "SkipStartup": "True"})
        self.assertFalse(self.handed.exists())
        self.assertLeftNothing()

    def test_an_archive_of_another_shape_without_the_marker_is_refused_as_before(self):
        self.refused(self.archive(marker=None), "The archive is missing payload/runtime/python.exe.")

    # ------------------------------------------------------------------------------------------- 7. precedence
    def test_a_python_shaped_archive_with_the_marker_passes_test_archive_then_hands_over(self):
        code, output = self.run_it(ArchivePath=str(self.archive(python=True)))
        self.assertEqual(code, 17, output[-2000:])
        verified = output.index("Archive contents verified as Codex Auto Resume v9.9.9")
        self.assertLess(verified, output.index("Handing over to the setup program of v9.9.9"))
        self.assertFalse(self.installed.exists(), "the marker wins: install.ps1 is not run")
        self.assertEqual(self.handed_over()["arguments"], ["-Handover", "install", "-Edition", "standard"])

    def test_a_python_shaped_archive_with_the_marker_that_fails_test_archive_is_refused(self):
        self.refused(self.archive(python=True, plugin_version="9.9.8"), "The archive is version 9.9.8, not 9.9.9.")


LIFT = r"""
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:CAR_SCRIPT, [ref]$null, [ref]$errors)
if ($errors -and $errors.Count) { throw 'the script does not parse' }
foreach ($node in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    if (@($env:CAR_FUNCTIONS -split ',') -contains $node.Name) { Invoke-Expression $node.Extent.Text }
}
"""


def lifted(functions, body: str, **environment) -> str:
    done = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", LIFT + body],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
                          env=dict(os.environ, CAR_SCRIPT=str(BOOTSTRAP), CAR_FUNCTIONS=",".join(functions),
                                   **environment))
    if done.returncode != 0:
        raise AssertionError("the probe did not run: " + (done.stderr or done.stdout)[-2000:])
    return done.stdout.strip()


# ------------------------------------------------------------------------------------------- the Dashboard's side
# name -> (what the bootstrap printed, its exit code, RunBootstrap's answer)
UPDATES = {
    "handed_over": ("update: available 0.6.26 0.6.27\nupdate: handover 0.6.26 0.6.27 0", 17, "handover"),
    "not_finished": ("update: available 0.6.26 0.6.27\nupdate: handover 0.6.26 0.6.27 1602", 17, "handover-unfinished"),
    "line_without_its_code": ("update: handover 0.6.26 0.6.27", 17, "failed"),
    "code_without_its_line": ("update: available 0.6.26 0.6.27", 17, "failed"),
    "line_with_another_code": ("update: handover 0.6.26 0.6.27 0", 0, "failed"),
    "installed_as_before": ("update: available 0.6.26 0.6.27", 0, "installed"),
}
# name -> (what -Pick printed, its exit code, PickLine's outcome, the version and edition it read)
OFFERED = "pick: offered newer,release,kept,latest"
PICKS = {
    "handed_over": (OFFERED + "\npick: handover 0.6.27 standard 0", 17, "handover", "0.6.27 standard"),
    "not_finished": (OFFERED + "\npick: handover 0.6.27 advanced 5", 17, "handover-unfinished", "0.6.27 advanced"),
    "not_offered_first": ("pick: handover 0.6.27 standard 0", 17, "failed", None),
    "another_code": (OFFERED + "\npick: handover 0.6.27 standard 0", 0, "failed", None),
    "no_edition": (OFFERED + "\npick: handover 0.6.27 0", 17, "failed", None),
    "a_bad_version": (OFFERED + "\npick: handover 0.6.27;x standard 0", 17, "failed", None),
    "two_endings": (OFFERED + "\npick: handover 0.6.27 standard 0\npick: installed 0.6.27 standard", 17, "failed", None),
}

PROBE = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$form = $assembly.GetType('CodexAutoResume.SettingsForm', $true)
$flow = $assembly.GetType('CodexAutoResume.InstallerFlow', $true)
$flags = [Reflection.BindingFlags]'Static,NonPublic,Public'
$run = $form.GetMethod('RunBootstrap', $flags)
$pick = $form.GetMethod('PickLine', $flags)
$code = $form.GetMethod('PickCode', $flags)
$out = @{ updates = @{}; picks = @{}; codes = @{} }
$work = [string]$env:CAR_WORK
foreach ($case in (ConvertFrom-Json $env:CAR_UPDATES).PSObject.Properties) {
    $script = [string](Join-Path $work ($case.Name + '.ps1'))
    $body = @()
    foreach ($line in ($case.Value[0] -split "`n")) { $body += ("Write-Host " + ($line | ConvertTo-Json)) }
    $body += ('exit ' + $case.Value[1])
    [IO.File]::WriteAllText($script, ($body -join "`r`n"), (New-Object Text.UTF8Encoding $false))
    $arguments = [object[]]@($work, $script, '-Update', 60000, $null, $null, $null, $null, $null, $null, $null)
    $null = $run.Invoke($null, $arguments)
    $out.updates[$case.Name] = @($arguments[4], $arguments[5], $arguments[6])
}
foreach ($case in (ConvertFrom-Json $env:CAR_PICKS).PSObject.Properties) {
    $arguments = [object[]]@([string]$case.Value[0], [int]$case.Value[1], $null, $null, $null)
    $outcome = $pick.Invoke($null, $arguments)
    $out.picks[$case.Name] = @($outcome, $arguments[4])
}
foreach ($outcome in 'handover', 'handover-unfinished', 'installed', 'failed') {
    $out.codes[$outcome] = $code.Invoke($null, [object[]]@('done', $outcome, 17))
}
$out.handed_over = $flow.GetField('HandedOver', $flags).GetValue($null)
$out | ConvertTo-Json -Depth 5 -Compress
"""


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class DashboardReadsTheHandoverTests(unittest.TestCase):
    """The Dashboard takes a handover for neither a failure nor an install: its own installer window closes (the setup
    program's said how it went), and the Dashboard closes as after an update where that program ended with 0."""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = work / "CodexAutoResumeSettings.exe"
        subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                        "/reference:System.dll", "/reference:System.Drawing.dll",
                        "/reference:System.Windows.Forms.dll", *[str(path) for path in guiscan.sources()]],
                       check=True, capture_output=True, timeout=300)
        probe = work / "probe.ps1"
        probe.write_text(PROBE, encoding="utf-8")
        done = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                               "-File", str(probe)], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=600,
                              env=dict(os.environ, CAR_EXE=str(exe), CAR_WORK=str(work),
                                       CAR_UPDATES=json.dumps({k: list(v[:2]) for k, v in UPDATES.items()}),
                                       CAR_PICKS=json.dumps({k: list(v[:2]) for k, v in PICKS.items()})))
        cls.done = done
        cls.answer = json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else {}

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if not self.answer:
            self.fail("the probe did not run: " + (self.done.stderr or self.done.stdout)[-2000:])

    def test_the_update_line_is_read_with_the_code_it_came_with(self):
        for name, (_, _, expected) in UPDATES.items():
            with self.subTest(name):
                self.assertEqual(self.answer["updates"][name][0], expected)
        self.assertEqual(self.answer["updates"]["handed_over"][1:], ["0.6.26", "0.6.27"])

    def test_the_pick_line_is_read_in_its_closed_grammar(self):
        for name, (_, _, outcome, installed) in PICKS.items():
            with self.subTest(name):
                self.assertEqual(self.answer["picks"][name], [outcome, installed])

    def test_a_handover_is_the_windows_own_ending_never_an_exit_code(self):
        handed = self.answer["handed_over"]
        self.assertLess(handed, 0)
        self.assertEqual(self.answer["codes"], {"handover": handed, "handover-unfinished": handed, "installed": 0,
                                                "failed": 17})
        ended = guiscan.member_body("InstallerWindow", "Ended")
        self.assertIn("if (ended == InstallerFlow.Later || ended == InstallerFlow.HandedOver)", ended)
        update = guiscan.member_body("SettingsForm", "InstallUpdate")
        self.assertIn('if (answer == "handover") { Close(); return; }', update)
        pick = guiscan.member_body("SettingsForm", "InstallPick")
        self.assertIn('if (outcome == "handover") { Close(); return; }', pick)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.text = BOOTSTRAP.read_text(encoding="utf-8")

    def test_the_mode_and_switches_follow_the_run(self):
        self.assertIn("if ($Pick) { $mode = 'another' } elseif ($Update -or $Version) { $mode = 'update' }", self.text)
        self.assertIn("$handed = @('-Handover', $mode, '-Edition', $targetEdition)", self.text)
        self.assertIn("$ExitHandedOver = 17", self.text)

    def test_the_handover_comes_after_the_checks_and_before_the_installer(self):
        run = self.text[self.text.index("# " + "-" * 76 + " run"):]
        order = [run.index(marker) for marker in (
            "Get-Sha256 -Path $zip", "Read-SetupHandover -Zip $zip", "ExtractToDirectory", "ask: install v",
            "Resolve-SetupProgram -Unpacked $unpacked", "Start-Process -FilePath $setupProgram",
            "$pickLock.WaitOne(0)", "& $installer @arguments")]
        self.assertEqual(order, sorted(order))
        self.assertEqual(run.count("Start-Process"), 1)


if __name__ == "__main__":
    unittest.main()
