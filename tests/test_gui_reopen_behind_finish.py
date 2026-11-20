"""v0.6.24 final: the Dashboard the setup opens again after a Repair or an update stands behind the Finish page.

The final's live acceptance (J10): after a Repair the setup opened the Dashboard again (install.ps1 Open-ClosedDashboard,
`<the window's own reopen> --after-update`) and it came up over the setup window's Finish page, hiding it whole - a person
might wait for a window they could not see. Such a start now opens without taking the activation (ShowWithoutActivation,
OpensBehind) and stands directly behind the window in front (HostApp.StandBehindFront), as its handle is made and once
more as it is shown. Every other start opens as it always did.

The source half reads gui/*.cs through guiscan. The built half compiles the real window and, with windows far off every
screen that are never activated, asks HostApp to stand a hidden window behind another, then shows it without activation
as the Form does: it stays behind, and the foreground stays where it was. Nothing is ever on screen; nothing of the real
installation is read.
"""
from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

import guiscan
from test_gui_v0611_access import CSC, POWERSHELL, compile_window, run_probe

PROBE = r"""
$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Windows.Forms
    [Windows.Forms.Application]::SetUnhandledExceptionMode([Windows.Forms.UnhandledExceptionMode]::ThrowException)
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Z {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window, int command);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr window, int command);
    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] public static extern IntPtr Style(IntPtr window, int index);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int cx, int cy, uint flags);
    public static bool Above(IntPtr upper, IntPtr lower) {
        for (IntPtr at = GetWindow(lower, 3); at != IntPtr.Zero; at = GetWindow(at, 3)) if (at == upper) return true;
        return false;
    }
    public static bool Next(IntPtr upper, IntPtr lower) { return GetWindow(upper, 2) == lower; }
}
'@
    $assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
    $flags = [Reflection.BindingFlags]'Static,NonPublic,Public'
    $host_ = $assembly.GetType('CodexAutoResume.HostApp', $true)
    $behind3 = $host_.GetMethod('StandBehind', $flags, $null, [Type[]]@([IntPtr], [IntPtr], [int]), $null)
    $behind2 = $host_.GetMethod('StandBehind', $flags, $null, [Type[]]@([IntPtr], [IntPtr]), $null)
    $form = $assembly.GetType('CodexAutoResume.SettingsForm', $true)
    $decide = $form.GetMethod('OpensBehindFor', $flags)
    $out = @{}
    $cases = @()
    foreach ($case in (ConvertFrom-Json $env:CAR_CASES)) {
        $argv = [string[]]@($case.argv | ForEach-Object { [string]$_ })
        $call = [object[]]::new(2); $call[0] = $argv; $call[1] = [bool]$case.capture
        $cases += [bool]$decide.Invoke($null, $call)
    }
    $out.cases = $cases
    function Off-Screen([bool]$show) {
        $made = New-Object Windows.Forms.Form
        $made.StartPosition = 'Manual'
        $made.ShowInTaskbar = $false
        $made.FormBorderStyle = 'None'
        $made.Bounds = New-Object Drawing.Rectangle -30000, -30000, 40, 40
        [void]$made.Handle
        if ($show) { [void][Z]::ShowWindow($made.Handle, 4) }     # SW_SHOWNOACTIVATE
        return $made
    }
    $front = [Z]::GetForegroundWindow()
    # The setup window, shown; the Dashboard made after it - a new window goes on top - and not yet shown.
    $setup = Off-Screen $true
    $dashboard = Off-Screen $false
    $out.stood = [bool]$behind3.Invoke($null, [object[]]@($dashboard.Handle, $setup.Handle, -1))
    # Shown as the Form shows a window that opens without activation (ShowWithoutActivation: SW_SHOWNOACTIVATE).
    [void][Z]::ShowWindow($dashboard.Handle, 4)
    $out.behind = [Z]::Above($setup.Handle, $dashboard.Handle)
    $out.right_behind = [Z]::Next($setup.Handle, $dashboard.Handle)
    $out.frontKept = ([Z]::GetForegroundWindow() -eq $front)
    # Never behind a window of its own process.
    $other = Off-Screen $true
    $out.own = [bool]$behind2.Invoke($null, [object[]]@($other.Handle, $setup.Handle))
    # Never behind a topmost window: it would be made topmost too.
    $top = Off-Screen $true
    [void][Z]::SetWindowPos($top.Handle, [IntPtr]::new(-1), 0, 0, 0, 0, 0x13)
    $out.topmost = [bool]$behind3.Invoke($null, [object[]]@($other.Handle, $top.Handle, -1))
    $out.topmostLeft = (([Z]::Style($other.Handle, -20).ToInt64() -band 0x8) -ne 0)
    # Never behind a hidden window, nor behind nothing.
    $hidden = Off-Screen $false
    $out.hidden = [bool]$behind3.Invoke($null, [object[]]@($other.Handle, $hidden.Handle, -1))
    $out.nothing = [bool]$behind3.Invoke($null, [object[]]@($other.Handle, [IntPtr]::Zero, -1))
    foreach ($made in @($setup, $dashboard, $other, $top, $hidden)) { $made.Dispose() }
    [IO.File]::WriteAllText((Join-Path $env:CAR_WORK 'result.json'), (ConvertTo-Json $out -Compress), (New-Object Text.UTF8Encoding $false))
    exit 0
} catch {
    [IO.File]::WriteAllText((Join-Path $env:CAR_WORK 'probe.failed'), $_.Exception.ToString())
    exit 3
}
"""

# (command line, a capture's?) -> opens behind the window in front
CASES = [
    (["--page=settings", "--section=continuation", "--bounds=10,20,1000,618", "--reopened=1", "--after-update"], False, True),
    (["--page=pending", "--reopened=1", "--after-update"], False, True),
    (["--page=pending", "--reopened=1", "--after-update"], True, False),
    (["--page=pending", "--reopened=1"], False, False),
    ([], False, False),
    (["--page=history"], False, False),
    (["--outside", "--page=pending"], False, False),
]


class SourceTests(unittest.TestCase):
    def test_a_window_the_setup_opened_again_shows_without_activation(self):
        """Fails with the old body, which activated it: the capture's event alone opened a window without it."""
        form = guiscan.type_body("SettingsForm", "gui/DashboardData.cs")
        start = form.index("protected override bool ShowWithoutActivation")
        body = form[start:form.index("}", form.index("get", start))]
        self.assertIn("Soft.StillReady != null || OpensBehind || base.ShowWithoutActivation", body)

    def test_main_decides_it_from_the_command_line_before_the_window_is_made(self):
        main = guiscan.member_body("Program", "Main")
        self.assertIn("SettingsForm.OpensBehind = SettingsForm.OpensBehindFor(argv, Soft.StillReady != null);", main)
        self.assertLess(main.index("SettingsForm.OpensBehind ="), main.index("new SettingsForm(persistent)"))

    def test_it_stands_behind_the_front_as_its_handle_is_made_and_as_it_is_shown(self):
        created = guiscan.member_body("SettingsForm", "OnHandleCreated")
        self.assertIn("if (OpensBehind) HostApp.StandBehindFront(Handle);", created)
        self.assertLess(created.index("base.OnHandleCreated(e);"), created.index("StandBehindFront"))
        shown = guiscan.member_body("SettingsForm", "OnShown")
        self.assertIn("if (OpensBehind) HostApp.StandBehindFront(Handle);", shown)
        self.assertLess(shown.index("StandBehindFront"), shown.index("base.OnShown(e);"))

    def test_the_order_changes_without_activating(self):
        host = guiscan.type_body("HostApp")
        start = host.index("internal static bool StandBehind(IntPtr window, IntPtr front, int own)")
        body = host[start:host.index("internal static bool StandBehindFront", start)]
        self.assertIn("SetWindowPos(window, front, 0, 0, 0, 0, SwpNoSize | SwpNoMove | SwpNoActivate)", body)
        self.assertNotIn("HwndTopMost", body)
        self.assertIn("GetForegroundWindow()", guiscan.member_body("HostApp", "StandBehindFront"))


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "the window is compiled with the in-box C# compiler")
class BuiltTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        work = Path(cls.folder.name).resolve()
        cases = json.dumps([{"argv": argv, "capture": capture} for argv, capture, _ in CASES])
        cls.answer = run_probe(PROBE, work, 300, CAR_EXE=str(compile_window(work)), CAR_CASES=cases)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_only_the_setups_reopen_opens_behind(self):
        self.assertEqual(self.answer["cases"], [expected for _, _, expected in CASES])

    def test_it_stays_right_behind_the_setup_window_once_shown_without_activation(self):
        """Fails with StandBehind a no-op: the Dashboard, made after the setup window, stays above it."""
        self.assertTrue(self.answer["stood"])
        self.assertTrue(self.answer["behind"])
        self.assertTrue(self.answer["right_behind"])
        self.assertTrue(self.answer["frontKept"], "the Finish page keeps the keyboard")

    def test_it_never_stands_behind_its_own_a_topmost_a_hidden_or_no_window(self):
        self.assertFalse(self.answer["own"])
        self.assertFalse(self.answer["topmost"])
        self.assertFalse(self.answer["topmostLeft"])
        self.assertFalse(self.answer["hidden"])
        self.assertFalse(self.answer["nothing"])


if __name__ == "__main__":
    unittest.main()
