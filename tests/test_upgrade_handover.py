"""An upgrade replaces the running watcher, and the launchers run only system binaries.

Both came out of the security review for v0.5.7.

Upgrading used to rename app\\ and runtime\\ under a live watcher - which Windows allows -
and leave the old process running the old code from the renamed copy, while setup saw
the watcher mutex held and started nothing. For an ordinary release that delays the new
version until the next sign-in. For a security fix it means the fix is installed and not
in effect, so "upgrade" would not have been the remedy the changelog says it is. The
installer now asks the watcher to stop through its own stop event and waits for it.

Measured on real Windows with the exact block from install.ps1 run against a staged
installation: a running watcher is handed over in under two seconds; a stand-in that
ignores the request is left running after sixty seconds, never killed, and the installer
says so instead of claiming the new version is running.

Install.cmd and Uninstall.cmd called `chcp` and `powershell.exe` by bare name, and
cmd.exe searches the current directory first. Extracted into a Downloads folder that
already held a planted chcp.bat, the verified installer ran the planted file before its
own script. Reproduced before the fix.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "build" / "install" / "install.ps1"
LAUNCHERS = [ROOT / "build" / "install" / "Install.cmd", ROOT / "build" / "install" / "Uninstall.cmd"]


class LauncherPathTests(unittest.TestCase):
    def test_system_binaries_are_called_by_absolute_path(self):
        for launcher in LAUNCHERS:
            text = launcher.read_text(encoding="utf-8")
            with self.subTest(launcher.name):
                self.assertIn(r'"%SystemRoot%\System32\chcp.com"', text)
                self.assertIn(r'"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"', text)

    def test_no_command_is_resolved_through_the_current_directory(self):
        """Every line that runs something names it by absolute path, or is a cmd builtin.

        `rem` and `goto` are internal to cmd.exe like the rest of the set: cmd acts on them
        itself and never looks for a file by that name, so a planted rem.bat or goto.bat in
        the current directory is never run - `rem` is even dropped by the parser before any
        command is looked up. A line starting with `:` is a label, which runs nothing. The
        edition-change question in Install.cmd needs all three.
        """
        builtins = {"@echo", "setlocal", "title", "set", "echo.", "echo", "if", "pause", "exit", "for",
                    "rem", "goto"}
        for launcher in LAUNCHERS:
            for number, line in enumerate(launcher.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if not stripped or stripped.startswith(":"):
                    continue
                first = stripped.split()[0].lower()
                with self.subTest("%s:%d" % (launcher.name, number)):
                    if first.startswith('"%systemroot%'):
                        continue
                    self.assertIn(first, builtins, "run by bare name: %r" % stripped)

    def test_no_stray_control_characters(self):
        """A mangled backslash once became a vertical tab inside one of these paths."""
        for launcher in LAUNCHERS:
            with self.subTest(launcher.name):
                self.assertFalse(re.search(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]", launcher.read_bytes()))


class UpgradeHandoverTests(unittest.TestCase):
    def setUp(self):
        self.source = INSTALL.read_text(encoding="utf-8")
        self.handover = self.source[self.source.index("$previousWatcherStillRunning = $false"):
                                    self.source.index("# Replace only the program directories.")]

    def test_the_watcher_is_handed_over_before_the_files_are_replaced(self):
        handover = self.source.index("$previousWatcherStillRunning = $false")
        swap = self.source.index("Move-Item -Path $pair.dst -Destination $aside")
        setup = self.source.index("$setupArgs = @('setup')")
        self.assertLess(handover, swap)
        self.assertLess(swap, setup)

    def test_it_asks_through_the_stop_event_and_never_kills(self):
        self.assertIn("Invoke-Setup @('stop')", self.handover)
        self.assertNotIn("Stop-Process", self.handover,
                         "a watcher killed mid-submission cannot prove what it sent")

    def test_the_wait_is_bounded(self):
        self.assertRegex(self.handover, r"AddSeconds\(\d+\)")
        self.assertIn("while ((Get-Date) -lt $deadline", self.handover)

    def test_only_this_installations_watcher_counts(self):
        start = self.source.index("function Get-OwnedWatcherProcess")
        body = self.source[start:self.source.index("function Invoke-Codex", start)]
        self.assertIn("Test-PathInside $exe $RunDir", body)
        self.assertIn("watcher-launcher", body)

    def test_the_count_is_not_wrapped_into_a_constant(self):
        """`@(f).Count` of a function returning `,$array` is always 1."""
        self.assertNotIn("@(Get-OwnedWatcherProcess)", self.source)

    def test_a_watcher_left_running_is_reported_not_hidden(self):
        tail = self.source[self.source.index("Step 'Checking the installation'"):]
        self.assertIn("$previousWatcherStillRunning", tail)
        branch = tail[tail.index("elseif ($previousWatcherStillRunning)"):]
        branch = branch[:branch.index("} else {")]
        self.assertNotIn("Installed and running", branch)
        # The settings window has a Start watcher button and no Stop watcher button, so
        # the message may only point at the one that exists.
        self.assertIn("Start watcher", branch)
        self.assertNotIn("Stop watcher", branch)


class RestartAfterUpdateTests(unittest.TestCase):
    """v0.6.16, the owner: after an update everything that ran before runs again, on the new version, by itself -
    and nothing the person had turned off. The handover above stops the old watcher; whether one ran is read before
    it does, and the setup that follows is told when none did (--watcher-was-stopped), so it starts the new one
    only where it runs at sign-in anyway (scripts/plugin_setup.py, tests/test_plugin.py holds that half). The
    notification-area icon is the watcher's own (STANDARDS F8), so it comes back with it."""

    def setUp(self):
        self.text = INSTALL.read_text(encoding="utf-8")

    def test_whether_a_watcher_ran_is_read_before_it_is_stopped(self):
        read = self.text.index("$watcherWasRunning = (Get-OwnedWatcherProcess).Count -gt 0")
        self.assertLess(read, self.text.index("Stopping the running watcher so the new version takes over"))
        self.assertLess(read, self.text.index("if ($watcherWasRunning) {"))

    def test_the_update_tells_setup_when_no_watcher_ran(self):
        told = self.text.index("if ($upgrade -and -not $watcherWasRunning) { $setupArgs += '--watcher-was-stopped' }")
        self.assertLess(self.text.index("$setupArgs = @('setup')"), told)
        self.assertIn("$code = Invoke-Setup $setupArgs", self.text[told:], "and setup runs with it after")

class DashboardAfterUpdateTests(unittest.TestCase):
    """v0.6.16: an update from a setup program or with -Silent, while this installation's Dashboard is open, asks it
    to close itself - its own close, through an event named after the installation, never anything ended from
    outside - waits a minute for it as the watcher is waited for, and opens it again on the new version where it
    was. A window with unsaved Settings changes keeps them and stays open, and the update goes on. The Dashboard
    that started the update itself is left alone: it opens the new version on its own."""

    def setUp(self):
        self.text = INSTALL.read_text(encoding="utf-8")
        self.window = (ROOT / "gui" / "WindowReopen.cs").read_text(encoding="utf-8")
        self.update = (ROOT / "gui" / "DashboardMaintenance.cs").read_text(encoding="utf-8")

    def block(self, start, end):
        return self.text[self.text.index(start):self.text.index(end, self.text.index(start))]

    def test_only_this_installations_dashboards_but_the_one_that_started_the_update(self):
        found = self.block("function Get-OwnedDashboardProcess {", "function Get-UpdateEventName {")
        self.assertIn("-Filter \"Name='CodexAutoResumeSettings.exe'\"", found)
        self.assertIn("if (Test-PathInside $exe $OwnedHome) { $found += $process }", found)
        self.assertIn("$process.ProcessId -eq $starter", found)
        self.assertIn('[void][int]::TryParse([string]$env:CODEX_AUTO_RESUME_UPDATING_DASHBOARD, [ref]$starter)', found)
        self.assertIn('info.EnvironmentVariables["CODEX_AUTO_RESUME_UPDATING_DASHBOARD"] =', self.update)

    def test_the_dashboard_is_asked_before_the_files_move_and_never_ended(self):
        asked = self.block("$dashboardsOpen = $upgrade -and (Get-OwnedDashboardProcess).Count -gt 0",
                           "$pairs = @(@{ src = 'app'")
        self.assertIn("[void]$closeEvent.Set()", asked)
        self.assertIn("$deadline = (Get-Date).AddSeconds(60)", asked)
        self.assertIn("[void]$closeEvent.Reset(); $closeEvent.Dispose()", asked)
        for kill in ("Stop-Process", "Kill(", "taskkill", "CloseMainWindow"):
            self.assertNotIn(kill, asked)

    def test_it_opens_again_after_setup_in_the_form_its_own_reopen_wrote(self):
        reopen = self.block("$reopenRequest = Join-Path (Join-Path $InstallHome 'config') 'reopen-after-update.txt'",
                            "Write-Host ''\nif ($script:Failed)")
        self.assertLess(self.text.index("$null = Invoke-Setup @('doctor')"), self.text.index(reopen))
        self.assertIn("if ($dashboardsOpen -and (Test-Path -LiteralPath $reopenRequest -PathType Leaf)) {", reopen)
        self.assertIn("$reopenLine -cmatch '^--[a-z]+(=[A-Za-z0-9,._-]+)?( --[a-z]+(=[A-Za-z0-9,._-]+)?)*$'", reopen)
        self.assertIn("-NoNewWindow", reopen)
        self.assertIn('internal const string UpdateReopenFile = "reopen-after-update.txt";', self.window)

    def test_the_window_closes_through_its_own_close_and_keeps_unsaved_changes(self):
        body = self.window[self.window.index("private void CloseForUpdate()"):]
        body = body[:body.index("\n        }\n")]
        self.assertIn("if (updatingHere || reopening || auditing || Dirty()) return;", body)
        self.assertLess(body.index("Dirty()"), body.index("File.WriteAllText("))
        self.assertTrue(body.rstrip().endswith("Close();"), "its own close, last")
        self.assertIn("updatingHere = true;", self.update)
        self.assertIn("WatchForUpdate();", (ROOT / "gui" / "SettingsApp.cs").read_text(encoding="utf-8"))

    def test_both_sides_name_the_event_alike(self):
        """The window's name (UpdateEventName) and the installer's (Get-UpdateEventName), against Python's."""
        import hashlib
        import os
        import subprocess
        source = self.block("function Get-UpdateEventName {", "function Get-OwnedWatcherProcess {")
        script = source + "\nforeach ($p in $args) { Get-UpdateEventName $p }\n"
        homes = [r"C:\Users\ExampleUser\.codex-auto-resume", "C:\\Users\\ExampleUser\\.Codex-Auto-Resume\\",
                 r"D:\x y\z"]
        expected = ["Local\\CodexAutoResume.CloseForUpdate." +
                    hashlib.sha256(home.rstrip("\\").lower().encode("utf-8")).hexdigest()[:16] for home in homes]
        powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        if not powershell.is_file():
            self.skipTest("Windows PowerShell")
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            probe = Path(folder) / "name.ps1"
            probe.write_text(script, encoding="utf-8-sig")
            done = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                   "-File", str(probe), *homes], capture_output=True, text=True, timeout=120,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(done.stdout.split(), expected, done.stderr)
        name = self.window[self.window.index("internal static string UpdateEventName(string root)"):]
        name = name[:name.index("\n        }\n")]
        for piece in ("Path.GetFullPath(root).TrimEnd('\\\\').ToLowerInvariant()", "new UTF8Encoding(false).GetBytes(full)",
                      'new StringBuilder("Local\\\\CodexAutoResume.CloseForUpdate.")', "for (int i = 0; i < 8; i++)",
                      'hash[i].ToString("x2", CultureInfo.InvariantCulture)'):
            self.assertIn(piece, name)

if __name__ == "__main__":
    unittest.main()
