r"""Issue #34: one-line text boxes cut their text off, and the Codex homes card joined empty parts and drew a grey band.

Every one-line box is a SoftTextArea: the GitHub login, the "send" word and the read-only lines of the compatibility
report's card, the rule editor's tag and the two status numbers on the Advanced features page, the Log's search, and
a Codex home's name. The well's padding is a message's - 12 px above and below - and in a box a field or a button high
that left less than a line. A one-line box (SoftTextArea.OneLine) keeps its size and place and centres its line, as a
button's text is; and the layout audit holds that every text box that shows, on every page and dialog of both
editions, shows at least one whole line (WindowAudit.AuditTextLine). The homes card joins only the parts of a row that
have text, stands its rows and buttons on the card's own ground, and gives an empty line no room.

Held through the compiled window (WindowTests) and its source (SourceTests).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import guiscan

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
POWERSHELL = (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
              / "WindowsPowerShell" / "v1.0" / "powershell.exe")

PROBE = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$F = $assembly.GetType('CodexAutoResume.SettingsForm', $true)
$A = $assembly.GetType('CodexAutoResume.SoftTextArea', $true)
$flags = [Reflection.BindingFlags]'Instance,Static,NonPublic,Public'
$out = @{}
$line = $F.GetMethod('HomeLine', $flags)
$out.joined = @(
  [string]$line.Invoke($null, [object[]]@(,[string[]]@('Default', '', 'Watched'))),
  [string]$line.Invoke($null, [object[]]@(,[string[]]@('Work', 'C:\Users\ExampleUser\.codex-work', 'Watched'))),
  [string]$line.Invoke($null, [object[]]@(,[string[]]@('Default', $null, ' ', 'Not looked at yet'))))
$font = New-Object Drawing.Font 'Segoe UI', 12
function Area($one, $height) {
  $area = $A.GetConstructor($flags, $null, [type[]]@(), $null).Invoke(@())
  $box = $A.GetField('Box', $flags).GetValue($area)
  $area.Font = $font; $box.Font = $font
  $area.Width = 280; $area.Height = $height
  if ($one) { $A.GetProperty('OneLine', $flags).SetValue($area, $true, $null) }
  $frame = New-Object Windows.Forms.Form
  $frame.ClientSize = New-Object Drawing.Size 400, 200
  $frame.Controls.Add($area)
  $frame.CreateControl(); $area.CreateControl(); $area.PerformLayout()
  $found = New-Object 'System.Collections.Generic.List[string]'
  $F.GetMethod('AuditTextLine', $flags).Invoke($null, [object[]]@('probe', $box.PSObject.BaseObject, $found.PSObject.BaseObject)) | Out-Null
  $result = @{ clip = [int]$box.Parent.Height; top = [int]$box.Parent.Top; line = [int]$font.Height; height = [int]$area.Height;
               findings = @($found) }
  $frame.Dispose()
  return $result
}
$out.one = Area $true 36
$out.well = Area $false 36
$out.message = Area $false 96
# The same cut-off box walked by the name check, with the line check on, and held off as it is for a dialog the
# screen has made smaller than its layout (AuditOwnValues): how many cut-offs each finds.
function Spoken($lines) {
  $area = $A.GetConstructor($flags, $null, [type[]]@(), $null).Invoke(@())
  $box = $A.GetField('Box', $flags).GetValue($area)
  $area.Font = $font; $box.Font = $font
  $area.Width = 280; $area.Height = 36
  $frame = New-Object Windows.Forms.Form
  $frame.ClientSize = New-Object Drawing.Size 400, 200
  $frame.Controls.Add($area)
  $frame.CreateControl(); $area.CreateControl(); $area.PerformLayout()
  $found = New-Object 'System.Collections.Generic.List[string]'
  $held = $F.GetField('AuditLines', $flags)
  $held.SetValue($null, $lines)
  try {
    $F.GetMethod('AuditSpoken', $flags).Invoke($null, [object[]]@('probe', $frame.PSObject.BaseObject, $found.PSObject.BaseObject)) | Out-Null
  } finally {
    $held.SetValue($null, $true)
  }
  $frame.Dispose()
  return @(@($found) | Where-Object { $_ -like '*its text is cut off*' }).Count
}
$out.spokenLines = Spoken $true
$out.spokenHeld = Spoken $false
$out | ConvertTo-Json -Depth 5 -Compress
"""


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = work / "CodexAutoResumeSettings.exe"
        subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                        "/reference:System.dll", "/reference:System.Drawing.dll",
                        "/reference:System.Windows.Forms.dll", *[str(path) for path in guiscan.sources()]],
                       check=True, capture_output=True, timeout=300,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        probe = work / "probe.ps1"
        probe.write_text(PROBE, encoding="utf-8")
        result = subprocess.run(
            [str(POWERSHELL), "-STA", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(probe)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), env=dict(os.environ, CAR_EXE=str(exe)))
        cls.result = result
        cls.answer = json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else {}

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if not self.answer:
            self.fail("the probe did not run: " + (self.result.stderr or self.result.stdout)[-2000:])

    def test_a_one_line_box_shows_its_whole_line_centred_in_the_same_size(self):
        one = self.answer["one"]
        self.assertEqual(one["height"], 36, "its size is kept")
        self.assertGreaterEqual(one["clip"], one["line"], "the whole line shows")
        self.assertLessEqual(abs(one["top"] * 2 + one["clip"] - one["height"]), 1, "centred, as a button's text is")
        self.assertEqual(one["findings"], [])

    def test_the_audit_finds_a_box_that_shows_less_than_a_line(self):
        """The well's message padding in a box a field high: the case of issue #34, which the audit now names."""
        well = self.answer["well"]
        self.assertLess(well["clip"], well["line"])
        self.assertEqual(len(well["findings"]), 1)
        self.assertIn("its text is cut off", well["findings"][0])
        self.assertEqual(self.answer["message"]["findings"], [], "a message's well is left as it is")

    def test_a_dialog_the_screen_made_smaller_is_asked_its_names_and_not_its_lines(self):
        """A custom value's dialog at 200% and the largest text size is wider than a 1024 x 768 screen lets a window be,
        so Windows makes it smaller than its layout and cuts its number box off (dev CI, 2026-10-15): the name check
        still walks it, the line check only where the dialog is whole - as its layout already was."""
        self.assertEqual(self.answer["spokenLines"], 1, "walked with the names, the cut-off box is found")
        self.assertEqual(self.answer["spokenHeld"], 0, "held off, it is not")

    def test_a_homes_row_joins_only_the_parts_that_have_text(self):
        self.assertEqual(self.answer["joined"], ["Default · Watched", "Work · C:\\Users\\ExampleUser\\.codex-work · Watched",
                                                 "Default · Not looked at yet"])


class SourceTests(unittest.TestCase):
    def test_every_one_line_box_is_one(self):
        """The four places a one-line box is made - two in the advanced edition's window, two in both editions' -
        each make it a one-line box."""
        root = Path(__file__).resolve().parents[1]
        for path, made in (("gui/DashboardTools.cs", "query.OneLine = true"), ("gui/SettingsHomes.cs", "area.OneLine = true"),
                           ("advanced/gui/AdvancedReport.cs", "box.OneLine = true"),
                           ("advanced/gui/AdvancedPage.cs", "box.OneLine = true")):
            with self.subTest(path):
                self.assertIn(made, (root / path).read_text(encoding="utf-8"))
        self.assertIn("query.OneLine = true", guiscan.member_body("SettingsForm", "BuildLogs"))
        self.assertIn("area.OneLine = true", guiscan.member_body("SettingsForm", "AskAlias"))

    def test_the_homes_card_stands_on_its_own_ground_with_no_empty_line_and_no_button_band(self):
        build = guiscan.member_body("SettingsForm", "BuildHomes")
        self.assertIn("homesRows.BackColor = Palette.Card", build)
        self.assertIn('ShowLine(homesRefusal, "")', build)
        self.assertNotIn("ButtonRow()", build)
        self.assertIn("HomeLine(", guiscan.member_body("SettingsForm", "ShowHomes"))

    def test_the_audit_checks_every_text_box_where_it_checks_every_name(self):
        self.assertIn("AuditTextLine(where, child, findings)", guiscan.member_body("SettingsForm", "AuditSpoken"))
        own = guiscan.member_body("SettingsForm", "AuditOwnValues")
        self.assertIn("AuditLines = whole;", own, "a custom value's dialog is held to whole lines where it is whole")
        self.assertIn("AuditLines = true;", own, "and the check is on again for everything walked after it")


if __name__ == "__main__":
    unittest.main()
