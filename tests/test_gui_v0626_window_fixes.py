r"""The window's third-round fixes (v0.6.26, plans/v0626-audit: audit-gui-chrome.md, audit-design-motion.md).

G1. The wait cursor of a window that waits (ChromeHost, UseWaitCursor) was set for every WM_SETCURSOR before Windows saw
it: a press on a Dashboard a dialog or the setup window held (HTERROR) no longer brought that window forward or sounded,
and the resize edges showed the hourglass. Now Windows handles HTERROR first and the wait cursor comes after it, and over
a resize band Windows' size arrows stay.

G4. After a long action the hourglass stayed over a resting pointer until it moved: only the editor gave the pointer back
(GivePointerBack). Now every wait of the window ends so - SetBusy, the version listing's dialog and the editor - through
one call (ChromeHost.PointerBack).

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


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = compile_window(work)
        cls.answer = run_probe(PROBE, work, 300, CAR_EXE=str(exe))

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


if __name__ == "__main__":
    unittest.main()
