"""The pick's setup window stays until the installer has ended (v0.6.18 live acceptance, B2).

Install another version... -> v0.6.17: the setup window showed the download, then closed part-way. There was no finished
page, no exit code and no "Installed v0.6.17", and an empty "did not finish" box came up although v0.6.17 installed well.
A raw WM_CLOSE that another program posts to the window - an older installer closing this installation's Dashboard
windows as a person closes them (install.ps1, Close-DashboardWindow) - reaches WinForms as TaskManagerClosing, and the
window refused only UserClosing. So the close went through, ShowDialog returned with the run still going, and the pick
read its first outcome, "failed", with nothing under it.

Now every close but Windows ending the session is refused while the run goes on, in the one way the window already had
(installer.progress.busy): a raw WM_CLOSE and the owner's own close alike. The run ends, the finished page shows its exit
code, and the pick reads what the bootstrap printed. Where Windows ends the session first the pick says the work may
still be going on (diag.update_running), and a failure is never shown with nothing under it.

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
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$asm = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$any = [Reflection.BindingFlags]'Static,Instance,NonPublic,Public'
Add-Type -ReferencedAssemblies System.Windows.Forms -TypeDefinition @'
using System; using System.Threading; using System.Runtime.InteropServices;
public static class CarPickCloseRunner {
    public static int Ended = int.MinValue;
    public static long EndedAt;
    public static int Run(object flow, Action<string> line, Action<double> unpacked) {
        line("  Installing"); Thread.Sleep(6000); line("  Checking the installation");
        EndedAt = DateTime.UtcNow.Ticks; Ended = 0; return 0;
    }
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, int m, IntPtr w, IntPtr l);
}
'@
$flowType = $asm.GetType('CodexAutoResume.InstallerFlow', $true)
$windowType = $asm.GetType('CodexAutoResume.InstallerWindow', $true)
$wordsType = $asm.GetType('CodexAutoResume.InstallerWords', $true)
$flow = [Activator]::CreateInstance($flowType, $any, $null,
                                    [object[]]@('update', 'C:\Users\ExampleUser\.codex-auto-resume', 'standard', 'standard', '0.6.17'), $null)
$flowType.GetField('Another', $any).SetValue($flow, $true)
$words = [Activator]::CreateInstance($wordsType, $any, $null, [object[]]@($null, 'en'), $null)
$runner = [Delegate]::CreateDelegate($windowType.GetNestedType('Runner', $any), [CarPickCloseRunner].GetMethod('Run'))
$window = [Activator]::CreateInstance($windowType, $any, $null, [object[]]@($flow, $words, $null, $runner, $null, $null), $null)
$owner = New-Object System.Windows.Forms.Form
$owner.Text = 'car-pick-close-owner'
$owner.StartPosition = 'Manual'; $owner.Location = New-Object System.Drawing.Point(-4000, -4000)
$window.StartPosition = 'Manual'; $window.Location = New-Object System.Drawing.Point(-4000, -3000)
$script:events = New-Object System.Collections.ArrayList
$script:result = @{}
$window.add_FormClosing({ param($s, $e) [void]$script:events.Add('window ' + [string]$e.CloseReason + ' ' + $e.Cancel) })
$owner.add_Shown({
    # A raw WM_CLOSE, as Process.CloseMainWindow and every other program sends it, then the owner's own close.
    $post = New-Object System.Windows.Forms.Timer
    $post.Interval = 1500
    $post.add_Tick({ $post.Stop(); [void][CarPickCloseRunner]::PostMessage($window.Handle, 0x10, [IntPtr]::Zero, [IntPtr]::Zero) })
    $post.Start()
    $shut = New-Object System.Windows.Forms.Timer
    $shut.Interval = 3000
    $shut.add_Tick({ $shut.Stop(); $script:result.busy = [bool]$windowType.GetField('closingAsked', $any).GetValue($window); $owner.Close() })
    $shut.Start()
    # Once the run has ended the window may close: the person's Finish.
    $done = New-Object System.Windows.Forms.Timer
    $done.Interval = 250
    $done.add_Tick({
        if ([CarPickCloseRunner]::Ended -eq 0 -and $windowType.GetProperty('Page', $any).GetValue($window) -eq 'finish') {
            $done.Stop(); $window.Close()
        }
    })
    $done.Start()
    $null = $window.ShowDialog($owner)
    $script:result.returned_at = [DateTime]::UtcNow.Ticks
    $script:result.ended_at = [CarPickCloseRunner]::EndedAt
    $script:result.ended = [CarPickCloseRunner]::Ended
    $script:result.code = $windowType.GetProperty('Code', $any).GetValue($window)
    $owner.BeginInvoke([Action]{ $owner.Close() }) | Out-Null
})
[System.Windows.Forms.Application]::Run($owner)
$script:result.events = @($script:events)
$script:result | ConvertTo-Json -Compress
"""


def body(member: str) -> str:
    return guiscan.member_body("SettingsForm", member)


class SourceTests(unittest.TestCase):
    def test_every_close_but_the_sessions_end_is_refused_while_it_runs(self):
        closing = guiscan.member_body("InstallerWindow", "OnFormClosing")
        self.assertIn("if (running && e.CloseReason != CloseReason.WindowsShutDown)", closing)
        self.assertNotIn("if (running && e.CloseReason == CloseReason.UserClosing)\n", closing,
                         "UserClosing alone let a raw WM_CLOSE (TaskManagerClosing) through")
        self.assertEqual(closing.count("closingAsked = true;"), 1, "one way to refuse: the busy note")

    def test_a_pick_whose_run_never_ended_in_the_window_is_not_a_failure(self):
        pick = body("InstallPick")
        shown = pick.index("window.ShowDialog(this);")
        running = pick.index('if (window.Code == int.MinValue) outcome = "running";')
        self.assertLess(shown, running)
        self.assertLess(running, pick.index("ReportPick(outcome, reason, converted, detail, releases);"))

    def test_a_failure_is_never_shown_with_nothing_under_it(self):
        pick = body("InstallPick")
        fallback = pick.index("if (string.IsNullOrEmpty(detail)) detail = Tail(window.Log);")
        self.assertLess(fallback, pick.index("ReportPick(outcome, reason, converted, detail, releases);"))
        self.assertIn("detail = new InstallerWords(strings, openedLanguage).Outcome(InstallerFlow.Update, window.Code);",
                      pick)


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
        result = subprocess.run([str(POWERSHELL), "-STA", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                 "-File", str(probe)], capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=120, env=dict(os.environ, CAR_EXE=str(exe)),
                                creationflags=NO_WINDOW)
        cls.result = result
        lines = result.stdout.strip().splitlines()
        cls.answer = json.loads(lines[-1]) if result.returncode == 0 and lines else {}

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if not self.answer:
            self.fail("the probe did not run: " + (self.result.stderr or self.result.stdout)[-3000:])

    def test_a_close_while_it_runs_neither_ends_the_window_nor_the_run(self):
        self.assertEqual(self.answer["ended"], 0, "the run ended")
        self.assertGreaterEqual(self.answer["returned_at"], self.answer["ended_at"],
                                "the window was still there when the run ended")
        self.assertEqual(self.answer["code"], 0, "the finished page has the run's exit code")

    def test_each_close_was_refused_the_one_way_and_the_finish_closes_it(self):
        # A refused close never reaches the FormClosing event (OnFormClosing returns before it): the one close the
        # event sees is the Finish, after the run. Before the fix the raw WM_CLOSE went through as TaskManagerClosing.
        self.assertEqual(self.answer["events"], ["window UserClosing False"])
        self.assertTrue(self.answer["busy"], "the raw WM_CLOSE was refused with the busy note")


if __name__ == "__main__":
    unittest.main()
