"""The pick follows its run to the end when its window is hidden (v0.6.18 live acceptance, B2, candidate 3).

Install another version... -> v0.6.17, twice: part-way through the install the setup window was gone, the Dashboard
minimized in the same quarter second, and a "still working" box came up. The bootstrap ran on for ten seconds more and
installed v0.6.17 well, but there was no finished page, no exit code and no "Installed v0.6.17", and the old Dashboard
stayed open. No close was asked. Minimizing the Dashboard hides the windows it owns (WM_SHOWWINDOW, SW_PARENTCLOSING),
and WinForms ends a modal window's loop once that window is hidden, with no close and no FormClosing. ShowDialog returned
with the run still going. A person's Show desktop does the same.

Now the setup window is not hidden that way while the run goes on. If its loop ends anyway, the pick brings the Dashboard
back and shows the window again until the installer has ended. What the run says while the window has no handle is kept
and told once it has one, so its end is never lost.

The window is compiled from the shipped sources and shown off screen over a stand-in owner, with a runner that takes a
few seconds. Nothing is installed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import guiscan  # noqa: E402

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PROBE = r"""
param([string]$How)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$asm = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$any = [Reflection.BindingFlags]'Static,Instance,NonPublic,Public'
Add-Type -ReferencedAssemblies System.Windows.Forms -TypeDefinition @'
using System; using System.Threading; using System.Runtime.InteropServices;
public static class CarPickHiddenRunner {
    public static int Ended = int.MinValue;
    public static int Run(object flow, Action<string> line, Action<double> unpacked) {
        line("  Installing"); Thread.Sleep(5000); line("  Checking the installation"); Ended = 0; return 0;
    }
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
}
'@
$flowType = $asm.GetType('CodexAutoResume.InstallerFlow', $true)
$windowType = $asm.GetType('CodexAutoResume.InstallerWindow', $true)
$flow = [Activator]::CreateInstance($flowType, $any, $null,
                                    [object[]]@('update', 'C:\Users\ExampleUser\.codex-auto-resume', 'standard', 'standard', '0.6.17'), $null)
$flowType.GetField('Another', $any).SetValue($flow, $true)
$words = [Activator]::CreateInstance($asm.GetType('CodexAutoResume.InstallerWords', $true), $any, $null, [object[]]@($null, 'en'), $null)
$runner = [Delegate]::CreateDelegate($windowType.GetNestedType('Runner', $any), [CarPickHiddenRunner].GetMethod('Run'))
$window = [Activator]::CreateInstance($windowType, $any, $null, [object[]]@($flow, $words, $null, $runner, $null, $null), $null)
$owner = New-Object System.Windows.Forms.Form
$owner.StartPosition = 'Manual'; $owner.Location = New-Object System.Drawing.Point(-4000, -4000)
$window.StartPosition = 'Manual'; $window.Location = New-Object System.Drawing.Point(-4000, -3000)
$script:r = @{ how = $How }
$owner.add_Shown({
    $t = New-Object System.Windows.Forms.Timer; $t.Interval = 1500
    $t.add_Tick({ $t.Stop()
        # The Dashboard minimized under the window; or the window hidden outright, which ends the loop whatever it does.
        if ($How -eq 'owner') { [void][CarPickHiddenRunner]::ShowWindow($owner.Handle, 6) } else { $window.Hide() }
    })
    $t.Start()
    $done = New-Object System.Windows.Forms.Timer; $done.Interval = 250
    $done.add_Tick({ if ([CarPickHiddenRunner]::Ended -eq 0 -and $windowType.GetProperty('Page', $any).GetValue($window) -eq 'finish') { $done.Stop(); $window.Close() } })
    $done.Start()
    $null = $window.ShowDialog($owner)
    $script:r.first_ended = [CarPickHiddenRunner]::Ended
    $script:r.owner_iconic = [CarPickHiddenRunner]::IsIconic($owner.Handle)
    if ($How -eq 'gap') {
        # The run ends while the window has no handle; then it is shown again, as SettingsForm.InstallPick does.
        while ([CarPickHiddenRunner]::Ended -ne 0) { Start-Sleep -Milliseconds 100 }
        Start-Sleep -Milliseconds 500
        $script:r.running_in_gap = [bool]$windowType.GetProperty('Running', $any).GetValue($window)
        $shows = 0
        while ($windowType.GetProperty('Running', $any).GetValue($window) -and -not $window.IsDisposed -and $shows -lt 3) {
            $shows++
            $null = $window.ShowDialog($owner)
        }
        $script:r.shows = $shows
    }
    $script:r.code = $windowType.GetProperty('Code', $any).GetValue($window)
    $script:r.page = $windowType.GetProperty('Page', $any).GetValue($window)
    $owner.BeginInvoke([Action]{ $owner.Close() }) | Out-Null
})
[System.Windows.Forms.Application]::Run($owner)
$script:r | ConvertTo-Json -Compress
"""


def body(member: str) -> str:
    return guiscan.member_body("SettingsForm", member)


class SourceTests(unittest.TestCase):
    def test_the_pick_follows_its_run_until_it_has_ended(self):
        pick = body("InstallPick")
        first = pick.index("window.ShowDialog(this);")
        loop = pick.index("while (window.Running && !window.IsDisposed)")
        self.assertLess(first, loop)
        again = pick[loop:pick.index("updatingHere = false;")]
        self.assertIn("if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;", again)
        self.assertIn("window.ShowDialog(this);", again)
        self.assertLess(pick.index("updatingHere = false;"), pick.index("ReportPick(outcome, reason, converted, detail, releases);"))

    def test_the_window_is_not_hidden_with_its_owner_while_it_runs(self):
        window = guiscan.type_body("InstallerWindow", "gui/InstallerWindow.cs")
        self.assertIn("if (m.Msg == WM_SHOWWINDOW && running && m.WParam == IntPtr.Zero && m.LParam.ToInt64() == SW_PARENTCLOSING)",
                      window)
        post = guiscan.member_body("InstallerWindow", "Post")
        self.assertIn("waiting.Add(action);", post)
        self.assertIn("foreach (MethodInvoker action in told) BeginInvoke(action);",
                      guiscan.member_body("InstallerWindow", "OnHandleCreated"))


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        exe = Path(cls.folder.name) / "CodexAutoResumeSettings.exe"
        subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                        "/reference:System.dll", "/reference:System.Drawing.dll",
                        "/reference:System.Windows.Forms.dll",
                        *[str(path) for path in guiscan.sources()]],
                       check=True, capture_output=True, timeout=300, creationflags=NO_WINDOW)
        probe = Path(cls.folder.name) / "probe.ps1"
        probe.write_text(PROBE, encoding="utf-8-sig")
        cls.answers, cls.failures = {}, {}
        for how in ("owner", "gap"):
            try:
                result = subprocess.run([str(POWERSHELL), "-STA", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                                         "Bypass", "-File", str(probe), "-How", how], capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=60,
                                        env=dict(os.environ, CAR_EXE=str(exe)), creationflags=NO_WINDOW)
            except subprocess.TimeoutExpired:
                cls.failures[how] = "the probe did not end within a minute"
                continue
            lines = result.stdout.strip().splitlines()
            if result.returncode == 0 and lines:
                cls.answers[how] = json.loads(lines[-1])
            else:
                cls.failures[how] = (result.stderr or result.stdout)[-3000:]

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def answer(self, how: str) -> dict:
        if how not in self.answers:
            self.fail("the probe did not run: " + self.failures.get(how, ""))
        return self.answers[how]

    def test_the_owner_minimized_neither_ends_the_window_nor_hides_the_run(self):
        seen = self.answer("owner")
        self.assertTrue(seen["owner_iconic"], "the stand-in Dashboard was minimized")
        self.assertEqual(seen["first_ended"], 0, "the window stayed until the run had ended")
        self.assertEqual((seen["code"], seen["page"]), (0, "finish"))

    def test_shown_again_after_its_loop_ended_it_still_hears_how_the_run_ended(self):
        seen = self.answer("gap")
        self.assertEqual(seen["first_ended"], -2147483648, "hidden, the loop ended before the run")
        self.assertTrue(seen["running_in_gap"], "the end the run told while the window had no handle was kept")
        self.assertEqual(seen["shows"], 1)
        self.assertEqual((seen["code"], seen["page"]), (0, "finish"), "told once it was shown again")


if __name__ == "__main__":
    unittest.main()
