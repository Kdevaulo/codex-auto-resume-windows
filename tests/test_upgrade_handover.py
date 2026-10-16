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

import os
from pathlib import Path
import re
import shutil
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "build" / "install" / "install.ps1"
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
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
        reopen = self.block("function Open-ClosedDashboard {", "# From here on, the Dashboard windows")
        self.assertLess(self.text.index("$null = Invoke-Setup @('doctor')"), self.text.index("Open-ClosedDashboard -Updated"))
        self.assertIn("if ($null -eq $script:DashboardsAskedAt -or $script:DashboardsReopened) { return }", reopen)
        self.assertIn("if ($line -cnotmatch $rule) { continue }", reopen)

    def test_a_record_opens_only_with_the_words_the_windows_own_parse_takes(self):
        """The record's rule took any --word=value of letters, digits and a few marks, so it let through words
        ParseArguments does not take - the window's own --uninstall among them. It now takes exactly the words
        ParseArguments does, read here from the window's own lists so the two cannot part."""
        def names(source, field):
            text = (ROOT / "gui" / source).read_text(encoding="utf-8")
            found = re.search(r"%s = \{([^}]*)\}" % field, text)
            return re.findall(r'"([a-z]+)"', found.group(1))
        pages, sections = names("Dashboard.cs", "PageOrder"), names("SettingsApp.cs", "SectionOrder")
        self.assertIn("history", pages)
        self.assertIn("appearance", sections)
        brand = (ROOT / "gui" / "Brand.cs").read_text(encoding="utf-8")
        designs = re.findall(r'text == "([a-z]+)"', brand[brand.index("internal static string DesignOf("):][:400])
        self.assertEqual(sorted(designs), ["classic", "plain", "soft"])
        accepted = (["--page=" + page for page in pages] + ["--section=" + section for section in sections] +
                    ["--theme=" + theme for theme in ("system", "light", "dark")] +
                    ["--design=" + design for design in designs] +
                    ["--focus=page." + page for page in pages] + ["--focus=section." + section for section in sections] +
                    ["--settings", "--maximized", "--reopened=1", "--reopened=9", "--bounds=-120,0,1024,768",
                     "--bounds=100,-32768,800,600", "--frame=7,0,7,7", "--focus=save", "--focus=start",
                     "--focus=setting.notify_on_failure",
                     "--page=history --section=general --bounds=10,20,800,600 --maximized --frame=8,0,8,8 "
                     "--theme=dark --design=classic --reopened=2 --focus=page.history"])
        refused = ["--uninstall", "--uninstall C:\\Users\\ExampleUser", "--page=nowhere", "--page=History", "--settings=1",
                   "--theme=blue", "--design=Soft", "--reopened=0", "--reopened=10", "--bounds=1,2,3",
                   "--bounds=1,2,-3,4", "--frame=100,0,0,0", "--focus=setting.Name", "--focus=nowhere",
                   "--reopened=\u0661", "--page=history  --maximized", "--page=history --hook",
                   "--page=history\n--uninstall", "-page=history", "--page=history;calc"]
        for words, opened in ((accepted, len(accepted)), (refused, 0)):
            records = [("reopen-after-update-%d.txt" % (100 + number), line, None) for number, line in enumerate(words)]
            said, _, left = self.run_reopen(records)
            with self.subTest(opened=opened):
                self.assertEqual(said.count("[ok] The Dashboard was opened again"), opened, said)
                self.assertEqual(left, [])

    def test_each_window_writes_a_record_of_its_own_and_its_own_pick_never_closes_it(self):
        """Two windows wrote the one reopen-after-update.txt, so only the last opened again; and InstallPick never set
        updatingHere, so with a second window open the window picking a version closed mid-pick and never said how it
        went. Each window now writes reopen-after-update-<its process id>.txt, and the installer opens each record
        named so - two windows open again as two - and only those."""
        import guiscan
        name = guiscan.member_body("SettingsForm", "UpdateReopenFile")
        self.assertIn('"reopen-after-update-" + process.ToString(CultureInfo.InvariantCulture) + ".txt"', name)
        close = guiscan.member_body("SettingsForm", "CloseForUpdate")
        self.assertIn("UpdateReopenFile(Process.GetCurrentProcess().Id)", close)
        self.assertIn("if (updatingHere ||", close)
        for member in ("InstallUpdate", "InstallPick"):
            body = guiscan.member_body("SettingsForm", member)
            with self.subTest(member):
                on = body.index("updatingHere = true;")
                self.assertLess(on, body.index("StartBootstrap(" if member == "InstallPick" else "RunBootstrap("),
                                "set before the bootstrap starts")
                self.assertGreater(body.index("updatingHere = false;"), on, "and cleared once it has ended")
        pick = guiscan.member_body("SettingsForm", "InstallPick")
        finish = pick[pick.index("MethodInvoker finish = delegate"):]
        self.assertIn("updatingHere = false;", finish, "cleared on the window's thread, once the pick has ended")
        said, started, left = self.run_reopen([("reopen-after-update-101.txt", "--page=history --reopened=1", None),
                                               ("reopen-after-update-202.txt", "--page=settings --reopened=1", None),
                                               ("reopen-after-update.txt", "--page=pending --reopened=1", None),
                                               ("reopen-after-update-x.txt", "--page=pending --reopened=1", None)])
        self.assertEqual(sorted(started), sorted(["--page=history", "--page=settings", "--reopened=1", "--reopened=1"]),
                         "each window's own record, and nothing else")
        self.assertEqual(said.count("[ok] The Dashboard was opened again on the new version"), 2)
        self.assertEqual(left, [], "every record is removed, opened or not")

    # ------------------------------------------------------------------ every way out (v0.6.16 review)
    def run_reopen(self, records, asked=True, calls=("-Updated",), dashboard=None):
        """Open-ClosedDashboard, lifted from install.ps1 with the helpers it calls, in a scratch home whose config
        folder holds `records` - (name, line, seconds the record was written before the request, or None for
        after it). Start-Process is a stub that writes down what it was asked to start - unless `dashboard` is a
        program to stand in for the Dashboard, which the real Start-Process starts, and which is ended here once
        it has written its process id. Returns (what it printed, what it started, the records left)."""
        import subprocess
        import tempfile
        from test_installer import VOICE, block, ps_literal
        if not POWERSHELL.is_file():
            self.skipTest("Windows PowerShell")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            home = Path(folder) / "home"
            (home / "config").mkdir(parents=True)
            if dashboard:
                shutil.copyfile(dashboard, home / "CodexAutoResumeSettings.exe")
            else:
                (home / "CodexAutoResumeSettings.exe").write_bytes(b"")
            started = Path(folder) / "started.txt"
            source = VOICE
            source += block(self.text, "function Resolve-Canonical {", "function Get-Edition {")
            source += block(self.text, "function Remove-OwnedItem {", "function Invoke-Setup {")
            source += block(self.text, "function Open-ClosedDashboard {", "# From here on, the Dashboard windows")
            if not dashboard:
                source += ("function Start-Process { param($FilePath, $ArgumentList, $WorkingDirectory, "
                           "[switch]$NoNewWindow) Add-Content -LiteralPath %s -Value ([string]$ArgumentList) }\n"
                           % ps_literal(started))
            script = ["$ErrorActionPreference = 'Stop'",
                      "$OwnedHome = %s" % ps_literal(home), "$InstallHome = $OwnedHome",
                      "$script:DashboardsReopened = $false",
                      "$now = [DateTime]::UtcNow",
                      "$script:DashboardsAskedAt = %s" % ("$now" if asked else "$null")]
            for name, line, before in records:
                path = ps_literal(home / "config" / name)
                script.append("[IO.File]::WriteAllText(%s, %s)" % (path, ps_literal(line)))
                when = "$now.AddSeconds(%d)" % (-before if before is not None else 1)
                script.append("(Get-Item -LiteralPath %s).LastWriteTimeUtc = %s" % (path, when))
            script += ["Open-ClosedDashboard %s" % call for call in calls]
            probe = Path(folder) / "probe.ps1"
            probe.write_text(source + "\n" + "\n".join(script) + "\n", encoding="utf-8-sig")
            done = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                   "-File", str(probe)], capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if dashboard:
                lines = [str(self.end_stand_in(home / "stand-in.pid"))]
            else:
                lines = started.read_text(encoding="utf-8").split() if started.exists() else []
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            return done.stdout, lines, sorted(os.listdir(home / "config"))

    @staticmethod
    def end_stand_in(pid_file):
        """Ends the stand-in Dashboard this test started, by the process id it wrote; its id, or None if it never
        wrote one."""
        import signal
        import time
        deadline = time.monotonic() + 15
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        try:
            pid = int(pid_file.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        return pid

    def test_a_record_is_opened_once_and_removed_and_a_stale_one_is_only_removed(self):
        """A record an earlier update left behind - written before this run asked - is never opened, and none is
        left for a later update to open."""
        said, started, left = self.run_reopen([("reopen-after-update-4242.txt", "--page=history --reopened=1", None)],
                                              calls=("-Updated", "", "-Updated"))
        self.assertEqual(started, ["--page=history", "--reopened=1"], "opened once, however often it is called")
        self.assertIn("[ok] The Dashboard was opened again on the new version", said)
        self.assertEqual(left, [])
        said, started, left = self.run_reopen([("reopen-after-update-4242.txt", "--page=history --reopened=1", 3600)])
        self.assertEqual(started, [], "a stale record was opened")
        self.assertEqual(left, [], "a stale record was left for a later update")
        said, started, left = self.run_reopen([("reopen-after-update-4242.txt", "--page=history", None)], asked=False)
        self.assertEqual(started, [], "nothing was asked to close, so nothing opens")

    def test_an_update_that_stops_opens_the_dashboard_again_as_it_was(self):
        said, started, _ = self.run_reopen([("reopen-after-update-4242.txt", "--page=settings --reopened=2", None)],
                                           calls=("",))
        self.assertEqual(started, ["--page=settings", "--reopened=2"])
        self.assertIn("[ok] The Dashboard was opened again", said)
        self.assertNotIn("on the new version", said)

    def test_the_dashboard_opened_again_holds_none_of_the_installers_handles(self):
        """Started with -NoNewWindow, the Dashboard opened again inherited install.ps1's output pipe: a parent that
        reads it to the end - the Dashboard that started an update (StartBootstrap gave up after 5 s and reported a
        failure), `$o = & Setup.exe -Silent` - waited for that Dashboard to close. Here a stand-in Dashboard, a
        Windows program that stays a minute, is opened by the real Start-Process under a parent reading the
        output to its end, as those do: the end comes when the installer's part does, not when the stand-in goes."""
        import subprocess
        import tempfile
        import time
        csc = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
        if not csc.is_file():
            self.skipTest("the in-box C# compiler")
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "StandIn.cs"
            source.write_text('class P { static void Main() { System.IO.File.WriteAllText("stand-in.pid", '
                              'System.Diagnostics.Process.GetCurrentProcess().Id.ToString()); '
                              'System.Threading.Thread.Sleep(60000); } }', encoding="utf-8")
            exe = Path(folder) / "StandIn.exe"
            subprocess.run([str(csc), "/nologo", "/target:winexe", "/out:" + str(exe), str(source)], check=True,
                           capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            begun = time.monotonic()
            said, started, _ = self.run_reopen([("reopen-after-update-4242.txt", "--page=overview --reopened=1", None)],
                                               dashboard=exe)
            took = time.monotonic() - begun
        self.assertIn("[ok] The Dashboard was opened again on the new version", said)
        self.assertNotEqual(started, ["None"], "the stand-in Dashboard never started")
        self.assertLess(took, 30, "the output's end waited for the Dashboard opened again to close")

    def test_every_way_out_once_the_dashboard_was_asked_opens_it_again(self):
        """install.ps1 closed the Dashboard, then could stop with 1 (put back, setup failed) before the reopen,
        which left the person's Dashboard closed. Every `exit` after the close step is inside the `try` whose
        `finally` opens it again, that `try` is the script's last statement, and a stale record is removed before
        the windows are asked."""
        import subprocess
        import tempfile
        if not POWERSHELL.is_file():
            self.skipTest("Windows PowerShell")
        probe_text = (
            "$ast = [System.Management.Automation.Language.Parser]::ParseFile($args[0], [ref]$null, [ref]$null)\n"
            "$tries = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.TryStatementAst] -and "
            "$n.Finally -and $n.Finally.Extent.Text -match 'Open-ClosedDashboard' }, $true))\n"
            "'tries ' + $tries.Count\n"
            "$try = $tries[0]\n"
            "'body ' + $try.Body.Extent.StartLineNumber + ' ' + $try.Body.Extent.EndLineNumber\n"
            "'last ' + [object]::ReferenceEquals($ast.EndBlock.Statements[$ast.EndBlock.Statements.Count - 1], $try)\n"
            "foreach ($e in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.ExitStatementAst] }, $true)) {\n"
            "    'exit ' + $e.Extent.StartLineNumber }\n")
        with tempfile.TemporaryDirectory() as folder:
            probe = Path(folder) / "ast.ps1"
            probe.write_text(probe_text, encoding="utf-8-sig")
            done = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                   "-File", str(probe), str(INSTALL)], capture_output=True, text=True, timeout=120,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        found = {}
        for line in done.stdout.splitlines():
            key, _, value = line.partition(" ")
            found.setdefault(key, []).append(value)
        self.assertEqual(found.get("tries"), ["1"], done.stdout + done.stderr)
        self.assertEqual(found.get("last"), ["True"], "nothing after the try may end the script")
        start, end = (int(n) for n in found["body"][0].split())
        lines = self.text.splitlines()

        def line_of(piece):
            return next(number for number, line in enumerate(lines, 1) if piece in line)

        asked = line_of("$dashboardsOpen = $upgrade -and (Get-OwnedDashboardProcess).Count -gt 0")
        self.assertLess(start, asked, "the try begins before the Dashboard is asked to close")
        late = [int(number) for number in found.get("exit", []) if int(number) > start]
        self.assertGreaterEqual(len(late), 4, "the exits after the close step were found")
        for number in late:
            self.assertLess(number, end, "an exit after the close step lies outside the try: " + lines[number - 1])
        stale = next(number for number, line in enumerate(lines, 1)
                     if number > start and "-Filter 'reopen-after-update*.txt'" in line)
        self.assertLess(stale, asked, "a record an earlier update left is removed before the windows are asked")

    def test_the_window_closes_through_its_own_close_and_keeps_unsaved_changes(self):
        import guiscan
        body = guiscan.member_body("SettingsForm", "CloseForUpdate")
        self.assertIn("if (updatingHere || reopening || auditing || Dirty())", body)
        self.assertLess(body.index("Dirty()"), body.index("File.WriteAllText("))
        self.assertTrue(body.rstrip().rstrip("}").rstrip().endswith("Close();"), "its own close, last")
        self.assertIn("updatingHere = true;", self.update)
        self.assertIn("WatchForUpdate();", (ROOT / "gui" / "SettingsApp.cs").read_text(encoding="utf-8"))

    def test_a_request_the_window_does_not_answer_leaves_it_listening_for_the_next(self):
        """The wait is registered to run once (executeOnlyOnce), so a CloseForUpdate that returned early - unsaved
        Settings changes, or the window's own update - stopped listening for good: a later setup program waited a
        minute and said unsaved changes kept the window open that were long gone. An early return marks the window
        to listen again, and the clock registers the wait again once the installer has reset the event - never while
        it is still set, which would hear the same request again at once."""
        import guiscan
        close = guiscan.member_body("SettingsForm", "CloseForUpdate")
        early = close[close.index("if (updatingHere || reopening || auditing || Dirty())"):close.index("bool normal")]
        self.assertIn("updateRearm = true;", early)
        self.assertLess(early.index("updateRearm = true;"), early.index("return;"))
        self.assertIn("if (updateRearm) ListenForUpdateAgain();", guiscan.member_body("SettingsForm", "TickReopen"))
        again = guiscan.member_body("SettingsForm", "ListenForUpdateAgain")
        self.assertIn("updateClose.WaitOne(0)) return;", again, "not while the request is still set")
        self.assertLess(again.index("updateClose.WaitOne(0)) return;"), again.index("updateRearm = false;"))
        self.assertIn("updateWait.Unregister(null);", again)
        self.assertIn("RegisterWaitForSingleObject(updateClose, UpdateHeard, null, -1, true)", again)
        watch = guiscan.member_body("SettingsForm", "WatchForUpdate")
        self.assertIn("RegisterWaitForSingleObject(updateClose, UpdateHeard, null, -1, true)", watch,
                      "the first wait and the ones after it hear alike")
        self.assertIn("BeginInvoke(new MethodInvoker(CloseForUpdate))", guiscan.member_body("SettingsForm", "UpdateHeard"))

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
