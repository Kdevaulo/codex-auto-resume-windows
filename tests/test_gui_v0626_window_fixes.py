r"""The window's third-round fixes (v0.6.26, plans/v0626-audit: audit-gui-chrome.md, audit-design-motion.md).

G1. The wait cursor of a window that waits (ChromeHost, UseWaitCursor) was set for every WM_SETCURSOR before Windows saw
it: a press on a Dashboard a dialog or the setup window held (HTERROR) no longer brought that window forward or sounded,
and the resize edges showed the hourglass. Now Windows handles HTERROR first and the wait cursor comes after it, and over
a resize band Windows' size arrows stay.

G4. After a long action the hourglass stayed over a resting pointer until it moved: only the editor gave the pointer back
(GivePointerBack). Now every wait of the window ends so - SetBusy, the version listing's dialog and the editor - through
one call (ChromeHost.PointerBack).

G2 (the owner, 2026-11-22, "대화상자 유지"). The window minimised under one of its dialogs - Show desktop, or another
program - hid the dialog (WM_SHOWWINDOW, SW_PARENTCLOSING), and WinForms ended its modal loop with no close asked: the
dialog and what was typed in it were gone. Now a modal dialog stays, as the setup window does, and is there with what
was typed when the window comes back.

G3. A dialog's title read its first letter from a drawing as wide as the title row, pixel by pixel, on every size change
(11-43 ms each). Now it is read once per look and stops at the first ink: a dialog resized reads it no more, and the
inset is the one the whole reading gave, in every room tried, mirrored too. Its probe shows a stand-in owner and a dialog off the screen, minimises the owner
and brings it back.

The window is compiled from the shipped sources; its dialogs are made and asked, never shown. GUI test module: run on its
own, through gui_lock.sh.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import guiscan
from test_gui_v0611_access import CSC, POWERSHELL, compile_window, run_probe

PROBE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode('ThrowException')
[Windows.Forms.Application]::EnableVisualStyles()
[Windows.Forms.Application]::SetCompatibleTextRenderingDefault($false)
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class CarFixesUser {
    [DllImport("user32.dll", EntryPoint = "SendMessageW")] public static extern IntPtr Send(IntPtr h, int message, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern IntPtr GetCursor();
}
'@
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$static = [Reflection.BindingFlags]'Static,NonPublic,Public'
$instance = [Reflection.BindingFlags]'Instance,NonPublic,Public'
function T([string]$name) { return $assembly.GetType('CodexAutoResume.' + $name, $true) }
function Bare([object[]]$items) { $bare = New-Object 'object[]' $items.Length; for ($i = 0; $i -lt $items.Length; $i++) { $one = $items[$i]; if ($one -is [Management.Automation.PSObject]) { $one = $one.PSObject.BaseObject }; $bare[$i] = $one }; return ,$bare }
function S([string]$type, [string]$name, [object[]]$arguments) {
    $m = @((T $type).GetMethods($static) | Where-Object { $_.Name -eq $name -and $_.GetParameters().Count -eq $arguments.Count })[0]
    return $m.Invoke($null, (Bare $arguments))
}
function P($target, [string]$name) { return $target.GetType().GetProperty($name, $instance).GetValue($target, $null) }
$utf8 = New-Object Text.UTF8Encoding $false
$out = @{}
$null = S 'Palette' 'Adopt' @('light')
(T 'SettingsForm').GetField('dpiScale', $static).SetValue($null, [double]1.0)

function Dialog([string]$title, [string]$border) {
    $dialog = [Activator]::CreateInstance((T 'SoftDialog'), $true)
    $dialog.Text = $title
    $dialog.BackColor = (T 'Palette').GetField('Canvas', $static).GetValue($null)
    $null = S 'Soft' 'DialogBar' @($dialog)
    $dialog.FormBorderStyle = $border
    $dialog.MinimizeBox = $false
    $dialog.MaximizeBox = $false
    $dialog.ShowInTaskbar = $false
    $dialog.StartPosition = 'Manual'
    $dialog.Location = New-Object Drawing.Point -30000, -30000
    $dialog.ClientSize = New-Object Drawing.Size 600, 400
    return $dialog
}

# G1: the cursor the dialog sets, waiting, for the pointer over each part of it as Windows asks (WM_SETCURSOR, a move).
$cursors = @{}
foreach ($name in 'WaitCursor', 'Default', 'SizeNWSE', 'SizeWE', 'SizeNS', 'SizeNESW') {
    $cursors[[string][Windows.Forms.Cursors]::$name.Handle] = $name
}
$dialog = Dialog 'A dialog that waits' 'Sizable'
$null = $dialog.Handle
$dialog.UseWaitCursor = $true
$out.cursor = @{}
foreach ($hit in @(1, 2, 10, 12, 14, 17, -2)) {
    [Windows.Forms.Cursor]::Current = [Windows.Forms.Cursors]::IBeam
    $null = [CarFixesUser]::Send($dialog.Handle, 0x0020, $dialog.Handle, [IntPtr]((0x0200 -shl 16) -bor ($hit -band 0xFFFF)))
    $now = [string][CarFixesUser]::GetCursor()
    $out.cursor[[string]$hit] = $(if ($cursors.ContainsKey($now)) { $cursors[$now] } else { 'other' })
}
$dialog.Dispose()

# G3: the title's first letter read once, not on every size change; and what it reads is what the whole reading read.
$scans = (T 'SoftDialog').GetField('TitleScans', $static)
$dialog = Dialog 'Timeline' 'Sizable'
$null = $dialog.Handle
$dialog.PerformLayout()
$out.title_scans = -1
if ($scans) {
    $scans.SetValue($null, 0)
    foreach ($width in 700, 820, 1000, 1300, 1600, 2400, 650) {
        $dialog.ClientSize = New-Object Drawing.Size $width, 400
        $dialog.PerformLayout()
    }
    $out.title_scans = [int]$scans.GetValue($null)
}
$out.title_words = [int](P $dialog 'TitleWords').Width
$dialog.Dispose()
$inset = @((T 'SoftDialog').GetMethods($static) | Where-Object { $_.Name -eq 'TitleInkInset' -and $_.GetParameters().Count -eq 4 })[0]
$font = S 'Soft' 'RoleFont' @('heading')
$canvas = (T 'Palette').GetField('Canvas', $static).GetValue($null)
$ink = (T 'Palette').GetField('Ink', $static).GetValue($null)
$out.insets = @()
# The Persian Compatibility report, by its code points: the probe's file is read in the machine's code page.
$persian = -join [char[]]@(0x06AF, 0x0632, 0x0627, 0x0631, 0x0634, 0x20, 0x0633, 0x0627, 0x0632, 0x06AF, 0x0627, 0x0631, 0x06CC)
foreach ($text in 'Timeline', 'Install another version', $persian) {
    foreach ($mirrored in $false, $true) {
        foreach ($room in @(60, 20), @(600, 39), @(1300, 39), @(2400, 39)) {
            $flags = [Windows.Forms.TextFormatFlags]'SingleLine, VerticalCenter, NoPrefix, EndEllipsis'
            if ($mirrored) { $flags = $flags -bor [Windows.Forms.TextFormatFlags]'Right, RightToLeft' }
            $drawn = New-Object Drawing.Bitmap $room[0], $room[1], ([Drawing.Imaging.PixelFormat]::Format32bppArgb)
            $g = [Drawing.Graphics]::FromImage($drawn)
            $g.Clear($canvas)
            [Windows.Forms.TextRenderer]::DrawText($g, $text, $font, (New-Object Drawing.Rectangle 0, 0, $room[0], $room[1]), $ink, $canvas, $flags)
            $g.Dispose()
            $columns = S 'Chrome' 'InkColumns' @($drawn, $canvas, (New-Object Drawing.Rectangle 0, 0, $room[0], $room[1]))
            $columns = $columns.PSObject.BaseObject
            $drawn.Dispose()
            $whole = $(if ($columns.X -lt 0) { -1 } elseif ($mirrored) { $room[0] - 1 - $columns.Y } else { $columns.X })
            $now = [int]$inset.Invoke($null, (Bare @($text, $font, [bool]$mirrored, (New-Object Drawing.Size $room[0], $room[1]))))
            $out.insets += ,@($text, [bool]$mirrored, $room[0], $whole, $now)
        }
    }
}

# G4: a wait ended gives the cursor back at once; the pointer over none of ours (every window here is off the screen),
# the arrow.
$back = (T 'ChromeHost').GetMethod('PointerBack', $static)
$out.pointer_back = $null -ne $back
if ($back) {
    [Windows.Forms.Cursor]::Current = [Windows.Forms.Cursors]::WaitCursor
    $null = $back.Invoke($null, @())
    $now = [string][CarFixesUser]::GetCursor()
    $out.pointer_after = $(if ($cursors.ContainsKey($now)) { $cursors[$now] } else { 'other' })
}

[IO.File]::WriteAllText((Join-Path $env:CAR_WORK 'result.json'), ($out | ConvertTo-Json -Depth 6 -Compress), $utf8)
"""

KEPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
# A failing probe fails its test: never a dialog on the desktop waiting for someone (every handler exits with 3).
[System.Windows.Forms.Application]::SetUnhandledExceptionMode([System.Windows.Forms.UnhandledExceptionMode]::ThrowException)
function Stop-Probe([object]$Problem) { [Console]::Error.WriteLine('probe failed: ' + $Problem); [Environment]::Exit(3) }
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class CarKeptUser {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
'@
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$script:static = [Reflection.BindingFlags]'Static,NonPublic,Public'
function T([string]$name) { return $assembly.GetType('CodexAutoResume.' + $name, $true) }
$null = (T 'Palette').GetMethod('Adopt', $script:static, $null, [Type[]]@([string]), $null).Invoke($null, [object[]]@('light'))
(T 'SettingsForm').GetField('dpiScale', $script:static).SetValue($null, [double]1.0)
$script:owner = New-Object System.Windows.Forms.Form
$script:owner.StartPosition = 'Manual'; $script:owner.Location = New-Object System.Drawing.Point(-4000, -4000)
$script:owner.ShowInTaskbar = $false
$script:dialog = [Activator]::CreateInstance((T 'SoftDialog'), $true)
$script:dialog.Text = 'Message for this conversation'
$script:dialog.BackColor = (T 'Palette').GetField('Canvas', $script:static).GetValue($null)
$null = (T 'Soft').GetMethod('DialogBar', $script:static).Invoke($null, [object[]]@($script:dialog))
$script:dialog.FormBorderStyle = 'FixedDialog'; $script:dialog.MinimizeBox = $false; $script:dialog.MaximizeBox = $false
$script:dialog.ShowInTaskbar = $false
$script:dialog.StartPosition = 'Manual'; $script:dialog.Location = New-Object System.Drawing.Point(-4000, -3000)
$script:dialog.ClientSize = New-Object System.Drawing.Size 500, 200
$script:box = New-Object System.Windows.Forms.TextBox
$script:box.Dock = 'Top'
$script:dialog.Controls.Add($script:box)
$script:r = @{ closed_by_probe = $false }
$script:owner.add_Shown({
  try {
    $script:steps = New-Object System.Windows.Forms.Timer; $script:steps.Interval = 800
    $script:step = 0
    $script:steps.add_Tick({
      try {
        $script:step++
        if ($script:step -eq 1) {
            $script:box.Text = 'words typed before Show desktop'
            # The window minimised under its dialog, as Show desktop does.
            [void][CarKeptUser]::ShowWindow($script:owner.Handle, 6)
        } elseif ($script:step -eq 2) {
            $script:r.owner_iconic = [CarKeptUser]::IsIconic($script:owner.Handle)
            $script:r.dialog_visible = [CarKeptUser]::IsWindowVisible($script:dialog.Handle)
            [void][CarKeptUser]::ShowWindow($script:owner.Handle, 9)
        } else {
            $script:steps.Stop()
            $script:r.typed = $script:box.Text
            $script:r.closed_by_probe = $true
            $script:dialog.DialogResult = 'OK'
        }
      } catch { Stop-Probe $_ }
    })
    $script:steps.Start()
    $script:r.result = [string]$script:dialog.ShowDialog($script:owner)
    $script:steps.Stop()
    $script:r.steps = $script:step
    $script:owner.BeginInvoke([Action]{ $script:owner.Close() }) | Out-Null
  } catch { Stop-Probe $_ }
})
[System.Windows.Forms.Application]::Run($script:owner)
[IO.File]::WriteAllText((Join-Path $env:CAR_WORK 'result.json'), ($script:r | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding $false))
"""


class SourceTests(unittest.TestCase):
    def test_windows_sees_the_press_on_a_held_window_before_the_wait_cursor(self):
        wait = guiscan.member_body("ChromeHost", "WaitCursor")
        self.assertIn("if (hit == HTERROR) pass(ref m);", wait)
        self.assertLess(wait.index("if (hit == HTERROR) pass(ref m);"), wait.index("Cursor.Current = Cursors.WaitCursor;"))
        self.assertIn("return WaitCursor(ref m, pass);", guiscan.member_body("ChromeHost", "Intercept"))

    def test_every_wait_of_the_window_gives_the_pointer_back(self):
        busy = guiscan.member_body("SettingsForm", "SetBusy")
        self.assertIn("if (busy == 0) { if (UseWaitCursor) GivePointerBack(false); }", busy)
        give = guiscan.member_body("SettingsForm", "GivePointerBack")
        self.assertIn("if (!waited) ChromeHost.PointerBack();", give)
        rows = guiscan.member_body("SettingsForm", "ShowVersionRows")
        self.assertLess(rows.index("dialog.UseWaitCursor = false;"), rows.index("ChromeHost.PointerBack();"))
        editor = (guiscan.ROOT / "advanced" / "gui" / "AdvancedEditor.cs").read_text(encoding="utf-8")
        self.assertNotIn("void GivePointerBack(", editor, "one way to give the pointer back: the window's")
        self.assertIn("GivePointerBack(waited);", editor)

    def test_a_title_is_read_from_its_start_once_per_look(self):
        dialog = guiscan.type_body("SoftDialog")
        start = dialog.index("internal static int TitleInkInset(string text, Font font, bool mirrored, Size room)")
        inset = dialog[start:dialog.index("private static readonly Dictionary<string, int> titleInsets", start)]
        self.assertIn("if (titleInsets.TryGetValue(key, out found)) return found;", inset)
        self.assertIn("Chrome.FirstInkColumn(drawn, Palette.Canvas, mirrored)", inset)
        self.assertNotIn("Chrome.InkColumns(", inset)


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = compile_window(work)
        cls.answer = run_probe(PROBE, work, 300, CAR_EXE=str(exe))
        kept = work / "kept"
        kept.mkdir()
        cls.kept = run_probe(KEPT, kept, 120, CAR_EXE=str(exe))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_a_waiting_window_keeps_windows_size_arrows_and_waits_elsewhere(self):
        seen = self.answer["cursor"]
        self.assertEqual({hit: seen[hit] for hit in ("10", "12", "14", "17")},
                         {"10": "SizeWE", "12": "SizeNS", "14": "SizeNESW", "17": "SizeNWSE"})
        self.assertEqual({hit: seen[hit] for hit in ("1", "2", "-2")},
                         {"1": "WaitCursor", "2": "WaitCursor", "-2": "WaitCursor"})

    def test_a_wait_that_ended_gives_the_cursor_back_at_once(self):
        self.assertTrue(self.answer["pointer_back"], "ChromeHost.PointerBack")
        self.assertEqual(self.answer["pointer_after"], "Default")

    def test_a_dialog_stays_with_what_was_typed_when_its_window_is_minimised_under_it(self):
        seen = self.kept
        self.assertTrue(seen.get("owner_iconic"), "the stand-in window was minimised: %r" % seen)
        self.assertTrue(seen.get("dialog_visible"), "the dialog stayed on the screen: %r" % seen)
        self.assertTrue(seen["closed_by_probe"], "the dialog's loop ended only when the probe closed it: %r" % seen)
        self.assertEqual((seen["result"], seen["typed"]), ("OK", "words typed before Show desktop"))

    def test_a_dialog_resized_reads_its_title_no_more(self):
        self.assertGreater(self.answer["title_words"], 0)
        self.assertEqual(self.answer["title_scans"], 0, "SoftDialog.TitleScans after seven resizes")

    def test_the_title_inset_is_the_one_the_whole_reading_gave(self):
        for text, mirrored, width, whole, now in self.answer["insets"]:
            with self.subTest(text=text, mirrored=mirrored, room=width):
                if whole >= 0:
                    self.assertEqual(now, whole)


if __name__ == "__main__":
    unittest.main()
