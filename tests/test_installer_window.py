"""The installer window (v0.6.16): a setup program's wizard, the Dashboard's update and the uninstall Add or remove
programs runs, in one window of the product's own design.

gui/InstallerFlow.cs decides what it asks and what each answer becomes, gui/InstallerWindow.cs shows it,
build/setup/SetupWindow.cs gives it what a setup program has, gui/SettingsRemove.cs what the entry in Add or remove
programs has, and gui/DashboardMaintenance.cs runs the Dashboard's update in it. What is held here:

* FlowTests - compiled into a setup program around a TEST archive (never the real installer) and called through
  reflection, with no window shown: the pages of each way it is shown; the switches each answer becomes, which are
  install.ps1's own (-SkipStartup on a first installation only, -AllowEditionChange only once asked, -Purge, and
  -Silent always); the bar's place and step from install.ps1's, the bootstrap's and the uninstall's own lines, never
  going back; the edition rule against install.ps1's; the language rules and endonyms against l10n's.
* ScriptTests - every line the bar reads is one the scripts print, so a reworded step fails here, not on a
  person's screen.
* LayoutAuditTests - InstallerAudit, the window measuring itself: every page of every way it is shown, in every
  language at every scaling and text size, cut off nowhere - and a canary, so a quiet report means something.
* CatalogTests and SourceTests - every word it says is in the catalogs; no console window in the window's mode
  (CREATE_NO_WINDOW on every console child); no elevation; nothing under HKLM.

Nothing here runs the real installer, touches a real home or the registry, or shows a window: the audit lays the
window out without showing it, as the settings window's audit does (tests/test_gui_layout.py).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
_BUILD = str(ROOT / "build")
if _BUILD not in sys.path:
    sys.path.insert(0, _BUILD)

import guiscan  # noqa: E402
import make_setup  # noqa: E402

from codex_auto_resume import l10n  # noqa: E402

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FLOW = (ROOT / "gui" / "InstallerFlow.cs").read_text(encoding="utf-8")
WINDOW = (ROOT / "gui" / "InstallerWindow.cs").read_text(encoding="utf-8")
SETUP_WINDOW = (ROOT / "build" / "setup" / "SetupWindow.cs").read_text(encoding="utf-8")
REMOVE = (ROOT / "gui" / "SettingsRemove.cs").read_text(encoding="utf-8")
INSTALL_PS1 = (ROOT / "build" / "install" / "install.ps1").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "scripts" / "bootstrap.ps1").read_text(encoding="utf-8")
SCALES = (1.0, 1.25, 1.5, 1.75, 2.0)
TEXT_SIZES = (1.0, 1.5, 2.25)
# Every scaling at Windows' usual text size, and every text size at 100%: the settings window's audit measures the
# scalings (tests/test_gui_layout.py), and a larger text size is the whole window that many times larger again
# (TextScale), so each is audited once rather than at every scaling - the audit builds every page of six ways the
# window is shown, five endings each, and all fifteen pairs took a quarter of an hour.
PAIRS = [(scale, 1.0) for scale in SCALES] + [(1.0, text) for text in TEXT_SIZES if text != 1.0]

TEST_ENTRIES = {"Install.cmd": b"@echo off\r\nexit /b 0\r\n",
                "install/install.ps1": b"# never run\r\n",
                "payload/app/src/codex_auto_resume/__init__.py": b"",
                "payload/app/.codex-plugin/plugin.json": b'{"name": "codex-auto-resume", "version": "9.9.9"}\n'}

# install.ps1's lines in the order a first installation prints them, the bootstrap's -Update before its own, and the
# uninstall's: what the bar is read from (FlowTests), each one checked against the scripts (ScriptTests).
INSTALLING = ["", "Codex Auto Resume", "edition: standard", "  [ok] Found Codex", "  Installing program files",
              "  [ok] Bundled Python 3.13 (no system Python needed)", "  Registering the Codex plugin",
              "  [ok] Codex plugin installed", "  Setting up the watcher", "    (the setup step's words, in any language)",
              "  Checking the installation", "Installed and running."]
UPDATING = ["Codex Auto Resume - setting up", "edition: standard",
            "  Asking github.com which release is newest. Nothing is uploaded, and no page is read.",
            "  Downloading v9.9.9 from github.com over HTTPS.", "  [ok] SHA-256 matches the digest pinned in this plugin",
            "  [ok] Archive contents verified as Codex Auto Resume v9.9.9", "  Installing", "edition: standard",
            "  [ok] Found Codex", "  Updating program files", "  Stopping the running watcher so the new version takes over",
            "  [ok] Bundled Python 3.13 (no system Python needed)", "  Registering the Codex plugin",
            "  Setting up the watcher", "  Checking the installation", "Updated. Your settings and pending recoveries were kept."]
REMOVING = ["Codex Auto Resume", "  Removing the watcher, autostart, notification identity and Start Menu entry",
            "  Removing the Codex plugin", "  Removing the marketplace this installation registered",
            "  Removing program files", "Removed. Settings and pending recoveries were kept."]

PROBE = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$any = [Reflection.BindingFlags]'Static,Instance,NonPublic,Public'
function T($name) { $assembly.GetType('CodexAutoResume.' + $name, $true) }
function Call($type, $name, $arguments) { (T $type).GetMethod($name, $any).Invoke($null, [object[]]$arguments) }
$FlowType = T 'InstallerFlow'
function NewFlow($mode, $edition, $installed) {
    $FlowType.GetConstructors($any)[0].Invoke([object[]]@([string]$mode, 'C:\Users\ExampleUser\.codex-auto-resume',
                                                      [string]$edition, $installed, '9.9.9'))
}
function SetField($flow, $field, $value) { $FlowType.GetField($field, $any).SetValue($flow, $value) }
# Internal members, which PowerShell's own dot does not reach.
function Of($object, $name) { $object.GetType().GetProperty($name, $any).GetValue($object, $null) }
function CallOn($object, $name, $arguments) { $object.GetType().GetMethod($name, $any).Invoke($object, [object[]]$arguments) }
# Lists go in as string arrays, which reflection takes for IEnumerable<string> and IList<string>: a list PowerShell
# made is handed over wrapped, and refused.
function Switches($flow, $given) {
    @($FlowType.GetMethod('Switches', $any).Invoke($flow, [object[]]@(,[string[]]@($given))))
}
$out = @{}
$input_ = ConvertFrom-Json ([IO.File]::ReadAllText($env:CAR_INPUT, [Text.Encoding]::UTF8))

# Pages, start and switches.
$first = NewFlow 'install' 'standard' $null
$upgrade = NewFlow 'install' 'standard' 'standard'
$change = NewFlow 'install' 'standard' 'advanced'
$update = NewFlow 'update' 'standard' 'standard'
$remove = NewFlow 'uninstall' 'standard' 'standard'
$out.pages = @{ install = @(CallOn $first 'Pages' @()); update = @(CallOn $update 'Pages' @()); uninstall = @(CallOn $remove 'Pages' @()) }
$out.switches = @{}
$out.switches.first = Switches $first @()
SetField $first 'StartAtSignIn' $false
$out.switches.first_no_startup = Switches $first @()
$out.switches.given = Switches $first @('-SkipStartup', '-AllowEditionChange', '-Silent', '-Other')
SetField $upgrade 'StartAtSignIn' $false
$out.switches.upgrade_no_startup = Switches $upgrade @()
$out.can_start = @{ unasked = (CallOn $change 'CanStart' @()); upgrade = (CallOn $upgrade 'CanStart' @()) }
$out.switches.change_unasked = Switches $change @()
SetField $change 'ChangeEdition' $true
$out.can_start.asked = (CallOn $change 'CanStart' @())
$out.switches.change_asked = Switches $change @()
$out.switches.remove = Switches $remove @()
SetField $remove 'Purge' $true
$out.switches.remove_purge = Switches $remove @()
$out.switches.update = Switches $update @()

# The bar, line by line.
$advance = (T 'InstallerProgress').GetMethod('Advance', $any)
$out.bar = @{}
foreach ($mode in @('install', 'update', 'uninstall')) {
    $at = [double]0; $step = 'starting'; $seen = @()
    foreach ($line in $input_.lines.$mode) {
        $arguments = [object[]]@($mode, [string]$line, $at, $step)
        $moved = $advance.Invoke($null, $arguments)
        $at = [double]$arguments[2]; $step = [string]$arguments[3]
        $seen += ,@($moved, $at, $step)
    }
    $out.bar[$mode] = $seen
}
$out.unpacked = @((Call 'InstallerProgress' 'Unpacked' @(0, 10)), (Call 'InstallerProgress' 'Unpacked' @(5, 10)),
                  (Call 'InstallerProgress' 'Unpacked' @(10, 10)), (Call 'InstallerProgress' 'Unpacked' @(3, 0)))

# Languages.
$out.normalized = @{}
foreach ($tag in $input_.tags) { $out.normalized[[string]$tag] = Call 'InstallerLanguages' 'Normalize' @([string]$tag) }
$list = [string[]]@('de-AT', 'ko-KR')
$none = [string[]]@()
$out.from_system = @((Call 'InstallerLanguages' 'FromSystem' @(,$list)), (Call 'InstallerLanguages' 'FromSystem' @(,$none)))
$out.resolved = @((Call 'InstallerLanguages' 'Resolve' @('ja', $list)), (Call 'InstallerLanguages' 'Resolve' @('system', $list)),
                  (Call 'InstallerLanguages' 'Resolve' @('ar', $list)), (Call 'InstallerLanguages' 'Resolve' @($null, $list)))
$Languages = T 'InstallerLanguages'
$out.all = @($Languages.GetField('All', $any).GetValue($null))
$out.held = @($Languages.GetField('Held', $any).GetValue($null))
$out.offered = @(Call 'InstallerLanguages' 'Offered' @())
$names = @{}
$endonyms = $Languages.GetField('Endonyms', $any).GetValue($null)
foreach ($key in $endonyms.Keys) { $names[$key] = $endonyms[$key] }
$out.endonyms = $names

# Editions, homes and versions.
$out.edition_of = @{}
foreach ($case in $input_.trees.PSObject.Properties) { $out.edition_of[$case.Name] = Call 'InstallerFlow' 'EditionOfSource' @([string]$case.Value) }
$out.installed_at = @{}
foreach ($case in $input_.homes.PSObject.Properties) { $out.installed_at[$case.Name] = Call 'InstallerFlow' 'InstalledAt' @([string]$case.Value) }
$entries = [string[]]@('payload/app/src/codex_auto_resume_advanced/__init__.py')
$plain = [string[]]@('payload/app/src/Codex_Auto_Resume_Advanced/__init__.py')
$out.entries = @((Call 'InstallerFlow' 'EditionOfEntries' @(,$entries)), (Call 'InstallerFlow' 'EditionOfEntries' @(,$plain)))
$out.home = @((Call 'InstallerFlow' 'HomeFrom' @('', 'C:\Users\ExampleUser')), (Call 'InstallerFlow' 'HomeFrom' @('D:\Elsewhere', 'C:\Users\ExampleUser')))
$out.version = @((Call 'InstallerFlow' 'VersionOf' @('{"version": "1.2.3"}')), (Call 'InstallerFlow' 'VersionOf' @('not json')))

# Words: the outcome of each code, and the steps' keys.
$WordsType = T 'InstallerWords'
$english = $WordsType.GetConstructors($any)[0].Invoke([object[]]@($null, 'en'))
$out.outcome = @{}
foreach ($code in @(0, 1, 14, 43, -2, -1)) {
    $out.outcome[[string]$code] = @($WordsType.GetMethod('Outcome', $any).Invoke($english, [object[]]@('install', [int]$code)),
                                    $WordsType.GetMethod('Explain', $any).Invoke($english, [object[]]@([int]$code)))
}
$out.removed = $WordsType.GetMethod('Outcome', $any).Invoke($english, [object[]]@('uninstall', [int]0))
$out.step_keys = @(Call 'InstallerWords' 'StepKeys' @())

# The window, built and never shown: its pages in order, and what a finished run leaves it saying.
$WindowType = T 'InstallerWindow'
$font = [System.Drawing.SystemFonts]::MessageBoxFont
$walk = NewFlow 'install' 'standard' 'advanced'
$built = $WindowType.GetConstructors($any)[0].Invoke([object[]]@($walk, $english, $null, $null, $null, $font))
$pages = @(Of $built 'Page')
$null = CallOn $built 'Go' @(1)
$pages += (Of $built 'Page')
$forward = $WindowType.GetField('forward', $any).GetValue($built)
$enabled = [System.Windows.Forms.Control].GetProperty('Enabled').GetValue($forward, $null)
$out.window = @{ pages = $pages; start_enabled_unasked = $enabled }
$null = CallOn $built 'Finished' @(14, "  [x]  This archive is the standard edition")
$out.window.after = @((Of $built 'Page'), (Of $built 'Code'), (Of $built 'OpenDashboard'), (Of $built 'Log').Contains('[x]'))
$done = $WindowType.GetConstructors($any)[0].Invoke([object[]]@((NewFlow 'install' 'standard' $null), $english, $null, $null, $null, $font))
$null = CallOn $done 'Finished' @(0, "The watcher could not be confirmed running, so nothing is being watched yet.")
$out.window.done = @((Of $done 'Page'), (Of $done 'Code'), (Of $done 'OpenDashboard'))

# An update (v0.6.16): its Notes page, the Dashboard it opens by itself, and Later, which closes with nothing installed.
$update = NewFlow 'update' 'standard' 'standard'
$FlowType.GetField('From', $any).SetValue($update, '9.9.8')
$updating = $WindowType.GetConstructors($any)[0].Invoke([object[]]@($update, $english, $null, $null, $null, $font))
$null = CallOn $updating 'Finished' @(0, "  Checking the installation")
$out.updated = @((Of $updating 'Page'), (Of $updating 'Code'), (Of $updating 'OpenDashboard'))
$reopened = $WindowType.GetConstructors($any)[0].Invoke([object[]]@((NewFlow 'install' 'standard' 'standard'), $english, $null, $null, $null, $font))
$null = CallOn $reopened 'Finished' @(0, "  [ok] The Dashboard was opened again on the new version")
$out.reopened = @((Of $reopened 'OpenDashboard'), @(@(CallOn $reopened 'ShownRows' @()) | Where-Object { $_.GetType().Name -eq 'SoftCheck' }).Count)
$out.updated_switches = @(@(CallOn $updating 'ShownRows' @()) | Where-Object { $_.GetType().Name -eq 'SoftCheck' }).Count
$later = $WindowType.GetConstructors($any)[0].Invoke([object[]]@((NewFlow 'update' 'standard' 'standard'), $english, $null, $null, $null, $font))
$null = CallOn $later 'Finished' @(-3, "update: later 9.9.8 9.9.9")
$out.later = @((Of $later 'Code'), (Of $later 'OpenDashboard'), $later.IsDisposed)

# What is new: a version's section of a changelog, its brief, and which file is read.
$notes = T 'InstallerNotes'
$changelog = [IO.File]::ReadAllText($env:CAR_CHANGELOG, [Text.Encoding]::UTF8)
$out.notes = @{}
foreach ($version in @('0.6.16-beta.3', '0.6.16-beta', '0.6.16', '9.9.9')) {
    $out.notes[$version] = $notes.GetMethod('Section', $any).Invoke($null, [object[]]@($changelog, $version))
}
$out.brief = $notes.GetMethod('Brief', $any).Invoke($null, [object[]]@([string]$out.notes['0.6.16-beta.3'], 3))
$docs = [string]$env:CAR_DOCS
$out.file = @(($notes.GetMethod('FileFor', $any).Invoke($null, [object[]]@($docs, 'ko'))),
              ($notes.GetMethod('FileFor', $any).Invoke($null, [object[]]@($docs, 'ja'))),
              ($notes.GetMethod('FileFor', $any).Invoke($null, [object[]]@($docs, 'en'))))

# An update's time limit, which the Notes page's wait does not count against.
$ClockType = T 'InstallerClock'
function NewClock($limit) { $ClockType.GetConstructors($any)[0].Invoke([object[]]@([long]$limit)) }
$clock = NewClock 1000
$out.clock = @((CallOn $clock 'Over' @([long]999)), (CallOn $clock 'Over' @([long]1000)))
$clock = NewClock 1000
$null = CallOn $clock 'Pause' @([long]100)
$out.clock += (CallOn $clock 'Over' @([long]1500000))
$null = CallOn $clock 'Resume' @([long]5000)
$out.clock += @((CallOn $clock 'Over' @([long]5500)), (CallOn $clock 'Over' @([long]5899)), (CallOn $clock 'Over' @([long]5900)))

# What a setup program's window shows for its command line.
$SetupType = $assembly.GetType('CodexAutoResumeSetup.SetupWindow', $true)
$out.setup = @{}
foreach ($case in @(@('plain'), @('uninstall', '-Uninstall'), @('purge', '-uninstall', '-Purge'), @('skip', '-SkipStartup'))) {
    $given = [string[]]@($case | Select-Object -Skip 1)
    $flow = $SetupType.GetMethod('FlowFor', $any).Invoke($null, [object[]]@($given, 'C:\Users\ExampleUser\.codex-auto-resume',
                                                                            'standard', 'standard', '9.9.9'))
    $out.setup[$case[0]] = @([string]$FlowType.GetField('Mode', $any).GetValue($flow), (CallOn $flow 'Pages' @())[0],
                             (Switches $flow $given) -join ' ')
}
$out | ConvertTo-Json -Depth 6 -Compress
"""

AUDIT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$audit = $assembly.GetType('CodexAutoResume.InstallerAudit', $true).GetMethod('LayoutAudit', [Reflection.BindingFlags]'Static,NonPublic')
$out = @{}
foreach ($case in (ConvertFrom-Json $env:CAR_CASES)) {
    $catalog = [IO.File]::ReadAllText([string]$case.catalog, [Text.Encoding]::UTF8)
    $key = [string]$case.name
    $out[$key] = @{}
    foreach ($pair in (ConvertFrom-Json $env:CAR_PAIRS)) {
        $scale = [double]$pair[0]; $text = [double]$pair[1]
        $out[$key][('{0:F2}/{1:F2}' -f $scale, $text)] = [string]$audit.Invoke($null, [object[]]@([string]$catalog, [string]$case.language, $scale, $text))
    }
}
[IO.File]::WriteAllText($env:CAR_RESULT, ($out | ConvertTo-Json -Depth 4 -Compress), (New-Object Text.UTF8Encoding $false))
"""


def _build(work: Path) -> Path:
    archive = work / "Test-v9.9.9-win-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, data in TEST_ENTRIES.items():
            bundle.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), data, compress_type=zipfile.ZIP_DEFLATED)
    return make_setup.build(archive, work / "out", "standard", "9.9.9")


def _powershell(script: str, work: Path, timeout: int, **environment) -> subprocess.CompletedProcess:
    probe = work / ("probe-%d.ps1" % len(list(work.glob("probe-*.ps1"))))
    probe.write_text(script, encoding="utf-8-sig")
    return subprocess.run([str(POWERSHELL), "-STA", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                           "-File", str(probe)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=NO_WINDOW, env=dict(os.environ, **environment))


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class FlowTests(unittest.TestCase):
    TAGS = ["ko", "ko-KR", "en-US", "zh", "zh-Hant-TW", "zh-HK", "zh-Hans", "pt-PT", "pt", "es-419", "in", "iw", "he",
            "ar-EG", "xx", "", "de_AT", "uk-UA", "nb-NO"]

    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="installer-flow-"))
        exe = _build(cls.work)
        trees = {}
        for name, package in (("advanced", "codex_auto_resume_advanced"), ("other_case", "Codex_Auto_Resume_Advanced"),
                              ("no_init", None), ("standard", None)):
            src = cls.work / "trees" / name / "src"
            src.mkdir(parents=True)
            if package:
                (src / package).mkdir()
                (src / package / "__init__.py").write_text("", encoding="utf-8")
            if name == "no_init":
                (src / "codex_auto_resume_advanced").mkdir()
            trees[name] = str(src)
        homes = {"none": str(cls.work / "homes" / "none"), "standard": str(cls.work / "trees" / "standard")}
        (cls.work / "homes" / "none").mkdir(parents=True)
        # An installation's app\src: the advanced tree, moved under an app folder.
        advanced_home = cls.work / "homes" / "advanced"
        shutil.copytree(cls.work / "trees" / "advanced", advanced_home / "app")
        homes["advanced"] = str(advanced_home)
        standard_home = cls.work / "homes" / "standard"
        shutil.copytree(cls.work / "trees" / "standard", standard_home / "app")
        homes["standard"] = str(standard_home)
        docs = cls.work / "docs"
        docs.mkdir()
        for name in ("CHANGELOG.md", "CHANGELOG.ko.md"):
            (docs / name).write_text("# Changelog\n", encoding="utf-8")
        source = cls.work / "input.json"
        source.write_text(json.dumps({"lines": {"install": INSTALLING, "update": UPDATING, "uninstall": REMOVING},
                                      "tags": cls.TAGS, "trees": trees, "homes": homes}), encoding="utf-8")
        cls.result = _powershell(PROBE, cls.work, 600, CAR_EXE=str(exe), CAR_INPUT=str(source),
                                 CAR_CHANGELOG=str(ROOT / "docs" / "CHANGELOG.md"), CAR_DOCS=str(docs))
        cls.docs = docs
        cls.answer = json.loads(cls.result.stdout) if cls.result.returncode == 0 and cls.result.stdout.strip() else {}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def setUp(self):
        if not self.answer:
            self.fail("the probe did not run: " + (self.result.stderr or self.result.stdout)[-3000:])

    def test_each_way_it_is_shown_has_its_pages(self):
        self.assertEqual(self.answer["pages"], {"install": ["welcome", "options", "progress", "finish"],
                                                "update": ["progress", "notes", "finish"],
                                                "uninstall": ["confirm", "progress", "finish"]})

    def test_each_answer_is_one_of_install_ps1s_own_switches_and_silent_is_always_passed(self):
        # ConvertTo-Json writes an array of one as its one value.
        switches = {name: value if isinstance(value, list) else [value] for name, value in self.answer["switches"].items()}
        self.assertEqual(switches["first"], ["-Silent"])
        self.assertEqual(switches["first_no_startup"], ["-SkipStartup", "-Silent"])
        self.assertEqual(switches["upgrade_no_startup"], ["-Silent"],
                         "an update keeps the sign-in choice (--keep-state): there is nothing to ask")
        self.assertEqual(switches["change_unasked"], ["-Silent"])
        self.assertEqual(switches["change_asked"], ["-AllowEditionChange", "-Silent"])
        self.assertEqual(switches["remove"], ["-Uninstall", "-Silent"])
        self.assertEqual(switches["remove_purge"], ["-Uninstall", "-Purge", "-Silent"])
        self.assertEqual(switches["update"], ["-Silent"])
        self.assertEqual(switches["given"], ["-SkipStartup", "-Other", "-Silent"],
                         "the window's answers stand for its own switches; any other word is passed on")
        for word in ("-SkipStartup", "-AllowEditionChange", "-Uninstall", "-Purge"):
            self.assertIn("[switch]$" + word[1:], INSTALL_PS1)

    def test_an_edition_change_starts_only_once_it_is_asked_for(self):
        self.assertEqual(self.answer["can_start"], {"unasked": False, "asked": True, "upgrade": True})
        window = self.answer["window"]
        self.assertEqual(window["pages"], ["welcome", "options"])
        self.assertFalse(window["start_enabled_unasked"], "Install is not pressed for an edition change nobody asked for")

    def test_a_finished_run_says_its_code_and_offers_the_dashboard_only_after_a_success(self):
        self.assertEqual(self.answer["window"]["after"], ["finish", 14, False, True])
        self.assertEqual(self.answer["window"]["done"], ["finish", 0, True])

    def test_the_bar_follows_the_scripts_lines_forward_only(self):
        for mode, lines in (("install", INSTALLING), ("update", UPDATING), ("uninstall", REMOVING)):
            with self.subTest(mode):
                seen = self.answer["bar"][mode]
                self.assertEqual(len(seen), len(lines))
                places = [place for _, place, _ in seen]
                self.assertEqual(places, sorted(places), "never back")
                self.assertGreater(places[-1], 0.9)
                self.assertLess(places[-1], 1.0, "only the exit code says it is done")
        install = {line.strip(): (moved, step) for line, (moved, _, step) in zip(INSTALLING, self.answer["bar"]["install"])}
        self.assertEqual(install["Registering the Codex plugin"], (True, "plugin"))
        self.assertEqual(install["Setting up the watcher"], (True, "setup"))
        self.assertFalse(install["(the setup step's words, in any language)"][0], "the localized lines move nothing")
        update = self.answer["bar"]["update"]
        self.assertFalse(update[1][0], "the bootstrap's own edition line, before it downloads, is no step")
        self.assertEqual(update[3][2], "download")
        self.assertEqual(self.answer["bar"]["uninstall"][-1][2], "finishing")
        self.assertEqual(self.answer["unpacked"], [0.0, 0.125, 0.25, 0.0])

    def test_the_languages_are_l10ns(self):
        self.assertEqual(self.answer["all"], list(l10n.LOCALES))
        self.assertEqual(sorted(self.answer["held"]), sorted(l10n.HELD))
        self.assertEqual(self.answer["offered"], list(l10n.OFFERED))
        self.assertEqual(self.answer["endonyms"], dict(l10n.ENDONYMS), "the picker names each language in itself")
        for tag in self.TAGS:
            with self.subTest(tag):
                self.assertEqual(self.answer["normalized"][tag], l10n.normalize(tag))
        self.assertEqual(self.answer["from_system"], ["de", "en"], "only the most preferred language counts")
        self.assertEqual(self.answer["resolved"], ["ja", "de", "en", "de"])

    def test_the_edition_is_install_ps1s_rule(self):
        self.assertEqual(self.answer["edition_of"], {"advanced": "advanced", "other_case": "standard",
                                                     "no_init": "standard", "standard": "standard"})
        self.assertEqual(self.answer["installed_at"], {"none": None, "advanced": "advanced", "standard": "standard"})
        self.assertEqual(self.answer["entries"], ["advanced", "standard"])
        self.assertIn("$_.Name -ceq 'codex_auto_resume_advanced'", INSTALL_PS1)
        self.assertIn("$upgrade = Test-Path $AppDir", INSTALL_PS1)

    def test_the_home_and_the_version_are_install_ps1s(self):
        self.assertEqual(self.answer["home"], [r"C:\Users\ExampleUser\.codex-auto-resume", r"D:\Elsewhere"])
        self.assertIn("$InstallHome = Join-Path $env:USERPROFILE '.codex-auto-resume'", INSTALL_PS1)
        self.assertEqual(self.answer["version"], ["1.2.3", ""])

    def test_an_update_shows_what_is_new_and_opens_the_dashboard_by_itself(self):
        """v0.6.16, the owner: an update shows itself - from what to what and what is new, before it installs, and
        "Updated to" after - and the Dashboard it was started from comes back on the new version by itself. Later
        closes the window with nothing installed and nothing opened."""
        self.assertEqual(self.answer["updated"], ["finish", 0, True])
        self.assertEqual(self.answer["updated_switches"], 0, "nothing to tick: the Dashboard comes back by itself")
        self.assertEqual(self.answer["reopened"], [False, 0],
                         "the installer opened again the Dashboard that was open: none is offered beside it")
        self.assertEqual(self.answer["later"], [-3, False, True])

    def test_what_is_new_is_the_versions_own_section_of_the_changelog(self):
        notes = self.answer["notes"]
        self.assertTrue(notes["0.6.16-beta.3"].startswith("v0.6.16-beta.3 \u2014 Words for this time"), notes["0.6.16-beta.3"][:80])
        self.assertNotIn("## v0.6.16-beta.2", notes["0.6.16-beta.3"], "it ends where the next version begins")
        self.assertTrue(notes["0.6.16-beta"].startswith("v0.6.16-beta \u2014 "), "not v0.6.16-beta.3's, whose name begins alike")
        self.assertIsNone(notes["9.9.9"])
        brief = self.answer["brief"].splitlines()
        self.assertEqual(len(brief), 3)
        self.assertFalse(any("](" in line or "**" in line for line in brief), brief)
        self.assertEqual(self.answer["file"], [str(self.docs / "CHANGELOG.ko.md"), str(self.docs / "CHANGELOG.md"),
                                               str(self.docs / "CHANGELOG.md")])

    def test_the_notes_pages_wait_is_not_the_installers_time(self):
        """Staying on the Notes page past the update's limit (20 minutes) reported "still running" with nothing
        installed, and left the bootstrap parked on its input until the window closed. The limit counts only the
        installer's time: none passes while the question is shown, and the wait is taken off once it is answered."""
        self.assertEqual(self.answer["clock"], [False, True, False, False, False, True])
        start = guiscan.member_body("SettingsForm", "StartBootstrap")
        self.assertNotIn("process.WaitForExit(milliseconds)", start)
        self.assertIn("var clock = new InstallerClock(milliseconds);", start)
        self.assertIn("if (clock.Over(time.ElapsedMilliseconds)) return \"running\";", start)
        asking = start[start.index("clock.Pause(time.ElapsedMilliseconds);"):]
        self.assertLess(asking.index("asked(notes)"), asking.index("clock.Resume(time.ElapsedMilliseconds);"),
                        "the clock waits as long as the question does")

    def test_a_setup_program_given_uninstall_shows_the_uninstall(self):
        """`Setup.exe -Uninstall` without -Silent dropped the switch (it is one the window answers) and showed the
        installation. It shows the uninstall, which passes -Uninstall on, with -Purge as its first answer."""
        self.assertEqual(self.answer["setup"], {"plain": ["install", "welcome", "-Silent"],
                                                "uninstall": ["uninstall", "confirm", "-Uninstall -Silent"],
                                                "purge": ["uninstall", "confirm", "-Uninstall -Purge -Silent"],
                                                "skip": ["install", "welcome", "-Silent"]})

    def test_each_code_says_what_it_means(self):
        outcome = self.answer["outcome"]
        self.assertEqual(outcome["0"], ["Codex Auto Resume is installed.", None])
        self.assertEqual(outcome["1"][0], "It did not finish (exit code 1).")
        self.assertIn("other edition", outcome["14"][1])
        self.assertIn("setup program stopped", outcome["43"][1])
        self.assertIn("still working", outcome["-2"][0])
        self.assertEqual(self.answer["removed"], "Codex Auto Resume is removed.")


class ScriptTests(unittest.TestCase):
    def milestones(self, table: str) -> list:
        body = FLOW[FLOW.index("Milestone[] %s =" % table):]
        body = body[:body.index("};")]
        return re.findall(r'new Milestone\("([^"]+)", ([0-9.]+), "([a-z_]+)"\)', body)

    def test_every_line_the_bar_reads_is_one_the_scripts_print(self):
        for table, scripts in (("Installing", (INSTALL_PS1,)), ("Updating", (BOOTSTRAP, INSTALL_PS1)),
                               ("Removing", (INSTALL_PS1,))):
            for starts, _, _ in self.milestones(table):
                with self.subTest(table=table, line=starts):
                    said = starts[len("[ok] "):] if starts.startswith("[ok] ") else starts
                    # PowerShell doubles an apostrophe inside a single-quoted string.
                    self.assertTrue(any(said.rstrip() in script.replace("''", "'") for script in scripts), said)

    def test_each_table_moves_forward(self):
        for table in ("Installing", "Updating", "Removing"):
            with self.subTest(table):
                places = [float(at) for _, at, _ in self.milestones(table)]
                self.assertEqual(places, sorted(places))
                self.assertLess(places[-1], 1.0)


class CatalogTests(unittest.TestCase):
    def said(self) -> dict:
        text = FLOW + WINDOW
        keys = dict(re.findall(r'Say\("([a-z_.]+)",\s*"((?:[^"\\]|\\.)*)"', text))
        # C#'s \uXXXX escapes, as the compiled words have them.
        keys = {key: re.sub(r"\\u([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), value) for key, value in keys.items()}
        steps = re.findall(r'"([^"]+)"', re.search(r"Steps =\s*\{(.*?)\};", FLOW, re.S).group(1))
        keys.update({"installer.step." + steps[i]: steps[i + 1] for i in range(0, len(steps), 2)})
        return keys

    def test_every_word_it_says_is_in_every_catalog_with_its_english_beside_it(self):
        english = l10n.catalog("en")
        said = self.said()
        self.assertGreater(len(said), 50)
        for key, fallback in said.items():
            with self.subTest(key):
                self.assertEqual(english.get(key), fallback.replace('\\"', '"'))
        for locale in l10n.LOCALES:
            # The file itself: l10n.catalog fills a missing key in with English.
            own = json.loads((l10n.DIRECTORY / ("%s.json" % locale)).read_text(encoding="utf-8"))
            with self.subTest(locale=locale):
                self.assertEqual(sorted(key for key in said if key not in own), [])


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class LayoutAuditTests(unittest.TestCase):
    """InstallerAudit: every page of every way the window is shown - a first installation, an update, an edition
    change each way, the Dashboard's update and the uninstall, and a finish for each kind of ending - in every
    language at five scalings and three text sizes, built and never shown."""

    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="installer-audit-"))
        exe = _build(cls.work)
        cases = [{"name": locale, "language": locale,
                  "catalog": str(l10n.DIRECTORY / ("%s.json" % locale))} for locale in l10n.LOCALES]
        # A word no switch's line can hold, and a button wider than the window. (A long word in a paragraph is
        # broken where the window's text is broken, and the window grows for it: that is not cut off.)
        canary = dict(l10n.catalog("en"), **{"field.startup": "S" * 300, "installer.next": "N" * 120})
        (cls.work / "canary.json").write_text(json.dumps(canary), encoding="utf-8")
        cases.append({"name": "canary", "language": "en", "catalog": str(cls.work / "canary.json")})
        result = cls.work / "result.json"
        cls.result = _powershell(AUDIT, cls.work, 300 * len(cases), CAR_EXE=str(exe), CAR_CASES=json.dumps(cases),
                                 CAR_PAIRS=json.dumps(PAIRS),
                                 CAR_RESULT=str(result))
        cls.answer = (json.loads(result.read_text(encoding="utf-8-sig"))
                      if cls.result.returncode == 0 and result.is_file() else {})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def setUp(self):
        if not self.answer:
            self.fail("the audit did not run: " + (self.result.stderr or self.result.stdout)[-3000:])

    def test_nothing_is_cut_off_in_any_language_at_any_scaling_or_text_size(self):
        for locale in l10n.LOCALES:
            for scale, text in PAIRS:
                report = self.answer[locale]["%.2f/%.2f" % (scale, text)]
                with self.subTest(locale=locale, scale=scale, text=text):
                    self.assertEqual(report, "", "\n" + "\n".join(report.splitlines()[:30]))

    def test_the_audit_finds_what_does_not_fit(self):
        report = self.answer["canary"]["1.00/1.00"]
        self.assertIn("SoftCheck'SSSS", report, "a 300-letter word went unreported, so a quiet report proves nothing")
        self.assertIn("button 'NNNN", report, "a button wider than the window went unreported")
        self.assertIn("/pages/options :: SoftCheck", report, "the options page was laid out and looked at")


class SourceTests(unittest.TestCase):
    def test_it_is_built_into_the_window_and_the_setup_programs_from_one_list(self):
        self.assertEqual(guiscan.group("installer"), ("gui/InstallerFlow.cs", "gui/InstallerWindow.cs"))
        self.assertEqual(make_setup.window_sources()[:2], ["gui/InstallerFlow.cs", "gui/InstallerWindow.cs"])
        self.assertEqual(make_setup.window_sources()[2:], list(guiscan.group("controls")) +
                         list(guiscan.group("generated")) + ["gui/WindowJson.cs"])
        self.assertIn("gui/SettingsRemove.cs", guiscan.group("settings"))

    def test_no_console_window_appears_in_the_windows_mode(self):
        """Every console program the window starts is started with no window: the setup program's cmd.exe
        (Setup.cs, Install), the uninstall's and the tidying PowerShell (SettingsRemove), and the Dashboard's
        bootstrap, as before. The one program it starts with a window is the Dashboard, which has no console."""
        setup = (ROOT / "build" / "setup" / "Setup.cs").read_text(encoding="utf-8")
        install = setup[setup.index("static int Install("):setup.index("static Thread Pass(")]
        self.assertIn("start.CreateNoWindow = true;", install)
        self.assertEqual(REMOVE.count("new ProcessStartInfo("), 3)
        self.assertEqual(REMOVE.count("start.CreateNoWindow = true;"), 2, "the uninstall and the tidying")
        self.assertEqual(REMOVE.count("UseShellExecute = false;"), 3)
        self.assertNotIn("UseShellExecute = true", SETUP_WINDOW + REMOVE)
        self.assertIn('"/target:winexe"', (ROOT / "build" / "make_setup.py").read_text(encoding="utf-8"))

    def test_the_window_is_never_closed_while_the_installer_runs(self):
        closing = WINDOW[WINDOW.index("protected override void OnFormClosing("):]
        closing = closing[:closing.index("\n        }\n")]
        self.assertIn("if (running && e.CloseReason == CloseReason.UserClosing)", closing)
        self.assertIn("e.Cancel = true;", closing)

    def test_it_asks_for_no_elevation_and_writes_nothing_under_hklm(self):
        manifest = (ROOT / "build" / "setup" / "setup.manifest").read_text(encoding="utf-8")
        self.assertIn('level="asInvoker"', manifest)
        for text in (FLOW, WINDOW, SETUP_WINDOW, REMOVE):
            self.assertNotIn("LocalMachine", text)
            self.assertNotIn("HKLM", text)
            self.assertNotIn("Registry.", text)

    def test_the_uninstall_runs_only_this_installations_kept_script_and_tidies_only_its_own_folder(self):
        self.assertIn('Path.Combine(Path.Combine(home, "uninstall"), "install.ps1")', REMOVE)
        self.assertIn("if (KeptScript(home, named) == null) return Refuse(named);", REMOVE)
        self.assertIn("'CodexAutoResume-Uninstall-*'", REMOVE)
        self.assertIn('internal const string FolderPrefix = "CodexAutoResume-Uninstall-";', REMOVE)
        tidy = REMOVE[REMOVE.index("internal const string TidyScript ="):REMOVE.index("private static void Tidy(")]
        self.assertNotIn("+ folder", tidy, "the folder is given in the environment, never in the script")
        main = guiscan.member_body("Program", "Main")
        self.assertLess(main.index("SettingsRemove.IsAsked(argv)"), main.index("new Bridge(root)"))

    def test_the_dashboards_update_asks_after_the_verified_download_and_before_the_install(self):
        """The bootstrap's -AskFirst stops between its checks of the download and the installer: the changelog's
        folder, the question, and only `install` on its input goes on (`update: later` and 16 otherwise). The
        Dashboard writes the person's answer there, and reads `later` as an update put off, not one that failed."""
        verified = BOOTSTRAP.index("Ok ('Archive contents verified as Codex Auto Resume v' + $target)")
        asked = BOOTSTRAP.index("Write-Host ('ask: install v' + $target)")
        self.assertLess(verified, asked)
        self.assertLess(asked, BOOTSTRAP.index("$installer = Join-Path $unpacked 'install\\install.ps1'"))
        self.assertIn("if ($answer -cne 'install') {", BOOTSTRAP)
        self.assertIn("$ExitLater = 16", BOOTSTRAP)
        update = guiscan.member_body("SettingsForm", "InstallUpdate")
        self.assertIn('flag + " -AskFirst"', update)
        self.assertIn("window.Ask(InstallerNotes.Section(", update)
        start = guiscan.member_body("SettingsForm", "StartBootstrap")
        self.assertIn('process.StandardInput.WriteLine(go ? "install" : "later");', start)
        self.assertIn("if (Asked != null) info.RedirectStandardInput = true;", start)
        self.assertIn('else if (code == UpdateLater && said == "later") answer = "later";',
                      guiscan.member_body("SettingsForm", "RunBootstrap"))

    def test_the_dashboards_update_runs_in_the_window_through_the_one_start_of_the_bootstrap(self):
        update = guiscan.member_body("SettingsForm", "InstallUpdate")
        self.assertIn("new InstallerWindow(flow,", update)
        self.assertIn('RunBootstrap(root, script, flag + " -AskFirst", UpdateMilliseconds,', update)
        self.assertIn("window.ShowDialog(this);", update)
        start = guiscan.member_body("SettingsForm", "StartBootstrap")
        self.assertIn("Action<string> heard = Heard;", start)


if __name__ == "__main__":
    unittest.main()
