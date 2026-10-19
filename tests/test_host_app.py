"""v0.6.17: the Dashboard, the setup programs and install.ps1 inside another app's private view of Windows.

A process descended from an MSIX app - the Codex app, Claude desktop - writes HKCU and %APPDATA% into that app's
private view, which Windows never reads. The one signal that held is a live ancestor with package identity
(gui/HostApp.cs, and install.ps1's Find-PackagedAncestor); the way out is the desktop shell or WMI, with a mark that
stops a second relaunch. Here:

* the decision, over process tables of the tests' own - the C# one compiled with a small harness, the PowerShell
  one lifted out of install.ps1 - including how far a walk goes before it stops;
* install.ps1's gate with its process table and its launcher stubbed: it relaunches inside, carries on outside, the
  mark stops a second relaunch, and a relaunch that fails is said once;
* the wiring, by guiscan's blocks: the Dashboard's Main and the setup programs' Started ask before the bridge and the
  window and pass the mark on; Repair, an update's install and Install another version refuse while stuck inside;
* item 3a: the Dashboard started after Finish goes through the routine that brings it to the front.

Nothing here relaunches anything or asks the live process tree a question whose answer depends on where the test
runs: on this laptop the tests run inside Claude, on CI inside nothing.
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

ROOT = Path(__file__).resolve().parents[1]
_BUILD = str(ROOT / "build")
if _BUILD not in sys.path:
    sys.path.insert(0, _BUILD)

import guiscan  # noqa: E402
import make_setup  # noqa: E402
from test_installer import VOICE, block, run_probe  # noqa: E402

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HOST = ROOT / "gui" / "HostApp.cs"
INSTALL = (ROOT / "build" / "install" / "install.ps1").read_text(encoding="utf-8")
SETUP = (ROOT / make_setup.SOURCE).read_text(encoding="utf-8")
SETUP_WINDOW = (ROOT / make_setup.WINDOW).read_text(encoding="utf-8")
LOCALES = ROOT / "src" / "codex_auto_resume" / "locales"
CODEX = "OpenAI.Codex_2p2nqsd0c76g0"

# The harness: HostApp.Decide over each table, and how many times it looked a process up there. Compiled with
# gui/HostApp.cs alone, into an executable of the test's own; nothing in the shipped programs is a test's.
HARNESS = r"""
using System;
using System.Collections;
using System.Collections.Generic;
using CodexAutoResume;

namespace HostAppProbe
{
    // A table that counts its lookups, so a walk that went on past where it should have stopped is seen.
    sealed class Counting : IDictionary<int, HostApp.Row>
    {
        readonly Dictionary<int, HostApp.Row> rows = new Dictionary<int, HostApp.Row>();
        internal int Lookups;
        public bool TryGetValue(int key, out HostApp.Row value) { Lookups++; return rows.TryGetValue(key, out value); }
        public HostApp.Row this[int key] { get { Lookups++; return rows[key]; } set { rows[key] = value; } }
        public void Add(int key, HostApp.Row value) { rows.Add(key, value); }
        public bool ContainsKey(int key) { Lookups++; return rows.ContainsKey(key); }
        public bool Remove(int key) { return rows.Remove(key); }
        public ICollection<int> Keys { get { return rows.Keys; } }
        public ICollection<HostApp.Row> Values { get { return rows.Values; } }
        public void Add(KeyValuePair<int, HostApp.Row> item) { rows.Add(item.Key, item.Value); }
        public void Clear() { rows.Clear(); }
        public bool Contains(KeyValuePair<int, HostApp.Row> item) { return rows.ContainsKey(item.Key); }
        public void CopyTo(KeyValuePair<int, HostApp.Row>[] array, int index) { ((ICollection<KeyValuePair<int, HostApp.Row>>)rows).CopyTo(array, index); }
        public bool Remove(KeyValuePair<int, HostApp.Row> item) { return rows.Remove(item.Key); }
        public int Count { get { return rows.Count; } }
        public bool IsReadOnly { get { return false; } }
        public IEnumerator<KeyValuePair<int, HostApp.Row>> GetEnumerator() { return rows.GetEnumerator(); }
        IEnumerator IEnumerable.GetEnumerator() { return rows.GetEnumerator(); }
    }

    static class Program
    {
        static string Quote(string text) { return text == null ? "null" : "\"" + text.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\""; }

        static void Case(string name, int self, params object[] rows)
        {
            var table = new Counting();
            for (int i = 0; i < rows.Length; i += 4)
                table.Add((int)rows[i], new HostApp.Row((int)rows[i + 1], (long)rows[i + 2], (string)rows[i + 3]));
            string found = HostApp.Decide(self, table);
            Console.WriteLine("{\"case\": " + Quote(name) + ", \"found\": " + Quote(found) + ", \"lookups\": " + table.Lookups + "}");
        }

        static int Main()
        {
            // pid, parent, created, package
            Case("packaged ancestor", 100, 100, 90, 50L, null, 90, 80, 40L, null, 80, 4, 30L, "OpenAI.Codex_2p2nqsd0c76g0");
            Case("own package", 100, 100, 90, 50L, "Claude_pzs8sxrjxfjjc", 90, 4, 40L, null);
            Case("no package", 100, 100, 90, 50L, null, 90, 80, 40L, null, 80, 4, 30L, null);
            Case("parent created after its child", 100, 100, 90, 50L, null, 90, 80, 60L, "OpenAI.Codex_2p2nqsd0c76g0");
            Case("parent cannot be opened", 100, 100, 90, 50L, null, 90, 80, 0L, null, 80, 4, 0L, "OpenAI.Codex_2p2nqsd0c76g0");
            Case("cycle", 100, 100, 90, 10L, null, 90, 80, 10L, null, 80, 90, 10L, null);
            Case("self as its own parent", 100, 100, 100, 10L, null);
            var deep = new List<object>();
            for (int pid = 1000; pid > 1000 - HostApp.MaxSteps - 5; pid--) { deep.Add(pid); deep.Add(pid - 1); deep.Add((long)pid); deep.Add(null); }
            deep.Add(1000 - HostApp.MaxSteps - 5); deep.Add(0); deep.Add(1L); deep.Add("Far_away");
            Case("further than the walk goes", 1000, deep.ToArray());
            Console.WriteLine("{\"case\": \"name\", \"found\": " + Quote(HostApp.Name("OpenAI.Codex_2p2nqsd0c76g0") + "|" + HostApp.Name("NoHash")) + ", \"lookups\": 0}");
            Console.WriteLine("{\"case\": \"arguments\", \"found\": " + Quote(HostApp.Arguments(new[] { "--page=settings", "a b", "--outside" })) + ", \"lookups\": 0}");
            Console.WriteLine("{\"case\": \"relaunched\", \"found\": " + Quote(HostApp.Relaunched(new[] { "x", "--outside" }) + "|" + HostApp.Relaunched(new[] { "x" }) + "|" + string.Join(",", HostApp.Without(new[] { "--outside", "-Silent" }))) + ", \"lookups\": 0}");
            return 0;
        }
    }
}
"""


@unittest.skipUnless(CSC.is_file(), "the in-box C# compiler is not available")
class DecisionTests(unittest.TestCase):
    """HostApp.Decide over tables of the test's own."""

    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="host-app-"))
        harness = cls.work / "probe.cs"
        harness.write_text(HARNESS, encoding="utf-8")
        exe = cls.work / "probe.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:exe", "/platform:x64", "/out:" + str(exe),
                                "/reference:System.dll", "/reference:System.Windows.Forms.dll", str(HOST), str(harness)],
                               capture_output=True, text=True, encoding="mbcs", errors="replace", timeout=300,
                               creationflags=NO_WINDOW)
        cls.built = built.returncode == 0 and exe.is_file()
        cls.build_output = built.stdout + built.stderr
        cls.answers = {}
        if cls.built:
            ran = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120, creationflags=NO_WINDOW)
            for line in ran.stdout.splitlines():
                answer = json.loads(line)
                cls.answers[answer["case"]] = answer

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def answer(self, case):
        if not self.built:
            self.fail("the harness did not build: " + self.build_output[-3000:])
        return self.answers[case]

    def test_a_packaged_ancestor_is_inside_and_its_family_is_kept(self):
        self.assertEqual(self.answer("packaged ancestor")["found"], CODEX)
        self.assertEqual(self.answer("own package")["found"], "Claude_pzs8sxrjxfjjc")

    def test_no_package_anywhere_is_outside(self):
        self.assertIsNone(self.answer("no package")["found"])

    def test_a_parent_created_after_its_child_ends_the_walk_outside(self):
        """Its id was reused: the packaged process that has it now is no ancestor of this one."""
        self.assertIsNone(self.answer("parent created after its child")["found"])

    def test_a_parent_that_cannot_be_opened_ends_the_walk_outside(self):
        """Whatever lies beyond it: past one that could not be opened, nothing is known to be an ancestor."""
        self.assertIsNone(self.answer("parent cannot be opened")["found"])

    def test_a_cycle_stops_at_once(self):
        for case in ("cycle", "self as its own parent"):
            with self.subTest(case):
                answer = self.answer(case)
                self.assertIsNone(answer["found"])
                self.assertLessEqual(answer["lookups"], 4, "the walk went round the cycle")

    def test_the_walk_goes_no_further_than_its_steps(self):
        answer = self.answer("further than the walk goes")
        self.assertIsNone(answer["found"])
        self.assertLessEqual(answer["lookups"], 34)

    def test_the_relaunch_passes_the_arguments_on_once_and_marks_them(self):
        self.assertEqual(self.answer("name")["found"], "OpenAI.Codex|NoHash")
        self.assertEqual(self.answer("arguments")["found"], '"--page=settings" "a b" --outside')
        self.assertEqual(self.answer("relaunched")["found"], "True|False|-Silent")


# ----------------------------------------------------------------------- install.ps1
GATE = block(INSTALL, "$script:HostAppSource = @'", "$outsideSwitches = @(")

# A table builder and a launcher of the test's own, defined after the script's so they are the ones called.
STUBS = r"""
$script:launched = 0
function Get-ProcessTable {
    param([int]$Self)
    $table = @{}
    $table[$Self] = @{ Parent = 41; Created = 50; Package = $null }
    $table[41] = @{ Parent = 40; Created = 40; Package = $null }
    $table[40] = @{ Parent = 4; Created = 30; Package = $env:CAR_PACKAGE }
    return $table
}
function Invoke-Outside {
    param([string]$Source, [string]$Log, [string]$CodeFile)
    $script:launched++
    Write-Host ('SOURCE ' + ($Source -replace "`r`n", ' | '))
    if ($env:CAR_LAUNCH -eq 'fail') { return $null }
    return 7
}
"""

DECIDE = r"""
Add-Type -TypeDefinition @'
public class CountingTable : System.Collections.Hashtable
{
    public int Lookups;
    public override object this[object key] { get { Lookups++; return base[key]; } set { base[key] = value; } }
}
'@
function Table($rows) {
    $table = New-Object CountingTable
    foreach ($row in $rows) { $table[[int]$row[0]] = @{ Parent = [int]$row[1]; Created = [long]$row[2]; Package = $row[3] } }
    return ,$table
}
$cases = [ordered]@{
    'packaged ancestor' = @(@(100, 90, 50, $null), @(90, 80, 40, $null), @(80, 4, 30, 'OpenAI.Codex_2p2nqsd0c76g0'))
    'own package' = @(@(100, 90, 50, 'Claude_pzs8sxrjxfjjc'), @(90, 4, 40, $null))
    'no package' = @(@(100, 90, 50, $null), @(90, 80, 40, $null), @(80, 4, 30, $null))
    'parent created after its child' = @(@(100, 90, 50, $null), @(90, 80, 60, 'OpenAI.Codex_2p2nqsd0c76g0'))
    'parent cannot be opened' = @(@(100, 90, 50, $null), @(90, 80, 0, $null), @(80, 4, 0, 'OpenAI.Codex_2p2nqsd0c76g0'))
    'cycle' = @(@(100, 90, 10, $null), @(90, 80, 10, $null), @(80, 90, 10, $null))
}
$answers = [ordered]@{}
foreach ($name in $cases.Keys) {
    $table = Table $cases[$name]
    $found = Find-PackagedAncestor -Table $table -Self 100
    $answers[$name] = @{ found = $found; lookups = $table.Lookups }
}
'JSON ' + ($answers | ConvertTo-Json -Compress)
"""


@unittest.skipUnless(POWERSHELL.is_file(), "the installer is PowerShell on Windows")
class InstallerGateTests(unittest.TestCase):
    """install.ps1's own functions, lifted out of it, with its process table and its launcher stubbed."""

    def run_gate(self, script: str, **environment) -> subprocess.CompletedProcess:
        saved = {name: os.environ.get(name) for name in ("CAR_PACKAGE", "CAR_LAUNCH", "CODEX_AUTO_RESUME_OUTSIDE")}
        try:
            for name in saved:
                os.environ.pop(name, None)
            os.environ.update(environment)
            done = run_probe(VOICE + GATE + STUBS, script)
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done

    RESOLVE = ("$code = Resolve-OutsideRun -Script 'C:\\x\\install.ps1' -Switches @('Silent', 'SkipStartup') "
               "-Values @{ PluginName = 'codex-auto-resume'; MarketplaceName = 'it''s' }\n"
               "'CODE ' + $(if ($null -eq $code) { 'none' } else { $code })\n"
               "'LAUNCHED ' + $script:launched\n"
               "'MARK ' + [string]$env:CODEX_AUTO_RESUME_OUTSIDE + '.'\n")

    def lines(self, done, prefix):
        return [line[len(prefix):] for line in done.stdout.splitlines() if line.startswith(prefix)]

    def test_the_decision_over_tables_of_its_own(self):
        done = self.run_gate(DECIDE)
        answers = json.loads(self.lines(done, "JSON ")[0])
        self.assertEqual(answers["packaged ancestor"]["found"], CODEX)
        self.assertEqual(answers["own package"]["found"], "Claude_pzs8sxrjxfjjc")
        for case in ("no package", "parent created after its child", "parent cannot be opened", "cycle"):
            with self.subTest(case):
                self.assertIsNone(answers[case]["found"])
        self.assertLessEqual(answers["cycle"]["lookups"], 4, "the walk went round the cycle")

    def test_inside_it_runs_again_outside_with_its_parameters_and_ends_with_that_code(self):
        done = self.run_gate(self.RESOLVE, CAR_PACKAGE=CODEX)
        self.assertEqual(self.lines(done, "CODE "), ["7"])
        self.assertEqual(self.lines(done, "LAUNCHED "), ["1"])
        source = self.lines(done, "SOURCE ")[0]
        self.assertIn("& 'C:\\x\\install.ps1' -Silent -SkipStartup -MarketplaceName 'it''s' -PluginName 'codex-auto-resume'",
                      source)
        self.assertIn("*>&1", source)
        self.assertIn("exit $code", source)
        self.assertNotIn("[!]", done.stdout, "a relaunch that worked says nothing of its own")

    def test_outside_it_carries_on_and_starts_nothing(self):
        done = self.run_gate(self.RESOLVE)
        self.assertEqual(self.lines(done, "CODE "), ["none"])
        self.assertEqual(self.lines(done, "LAUNCHED "), ["0"])

    def test_the_mark_stops_a_second_relaunch_and_goes_no_further(self):
        done = self.run_gate(self.RESOLVE, CAR_PACKAGE=CODEX, CODEX_AUTO_RESUME_OUTSIDE="1")
        self.assertEqual(self.lines(done, "CODE "), ["none"])
        self.assertEqual(self.lines(done, "LAUNCHED "), ["0"], "a run outside never relaunches")
        self.assertEqual(self.lines(done, "MARK "), ["."], "its children ask for themselves")

    def test_a_relaunch_that_fails_carries_on_and_says_once_what_stays_inside(self):
        done = self.run_gate(self.RESOLVE, CAR_PACKAGE=CODEX, CAR_LAUNCH="fail")
        self.assertEqual(self.lines(done, "CODE "), ["none"])
        warnings = [line for line in done.stdout.splitlines() if line.startswith("  [!]")]
        self.assertEqual(len(warnings), 1, done.stdout)
        self.assertIn("inside OpenAI.Codex,", warnings[0])
        for named in ("Settings > Apps", "sign-in", "Start menu", "Repair installation"):
            self.assertIn(named, warnings[0])

    def test_the_gate_runs_before_anything_else_the_script_does(self):
        gate = INSTALL.index("$outsideCode = Resolve-OutsideRun -Script $PSCommandPath")
        self.assertLess(gate, INSTALL.index("New-Object System.Threading.Mutex($false, 'Local\\CodexAutoResume.Install')"))
        self.assertLess(gate, INSTALL.index("Write-Host 'Codex Auto Resume'"))
        self.assertIn("if ($null -ne $outsideCode) { exit $outsideCode }", INSTALL)
        for switch in ("SkipStartup", "Uninstall", "Purge", "AllowEditionChange", "Silent"):
            self.assertRegex(INSTALL, r"param\(\s[\s\S]*\[switch\]\$%s\b" % switch)
            self.assertIn("'%s'" % switch, INSTALL[INSTALL.index("$outsideSwitches = @("):gate])
        launch = guiscan._block(INSTALL, INSTALL.index("function Invoke-Outside"))
        self.assertIn("ShowWindow = [uint16]0", launch, "no console window shows")
        self.assertIn("'CODEX_AUTO_RESUME_OUTSIDE=1'", launch)
        self.assertIn("[Environment]::GetEnvironmentVariables()", launch, "the run outside gets this run's environment")


# ----------------------------------------------------------------------- the wiring
def setup_method(name: str) -> str:
    found = re.search(r"\n[ \t]+(?:internal |private |public )?static \w+ %s\(" % re.escape(name), SETUP)
    return guiscan._block(SETUP, found.start())


def setup_window_method(name: str) -> str:
    found = re.search(r"\n[ \t]+(?:internal |private |public )?static \w+ %s\(" % re.escape(name), SETUP_WINDOW)
    return guiscan._block(SETUP_WINDOW, found.start())


class WiringTests(unittest.TestCase):
    def test_host_app_is_built_into_the_dashboard_and_the_setup_programs(self):
        self.assertIn("gui/HostApp.cs", guiscan.group("installer"))
        self.assertIn("gui/HostApp.cs", make_setup.window_sources())

    def test_the_dashboard_asks_before_the_bridge_and_relaunches_itself_marked(self):
        main = guiscan.member_body("Program", "Main")
        asked = main.index("HostApp.Inside()")
        self.assertLess(main.index("SettingsRemove.IsAsked(argv)"), asked)
        self.assertLess(main.index("SettingsForm.RenderJob"), asked)
        self.assertLess(asked, main.index("new Bridge(root)"))
        relaunch = main[asked:main.index("new Bridge(root)")]
        self.assertIn("!HostApp.Relaunched(argv)", relaunch)
        self.assertIn("HostApp.Relaunch(Application.ExecutablePath, HostApp.Arguments(argv), root))", relaunch)
        self.assertIn("return 0;", relaunch)
        self.assertIn("HostApp.StuckInside = inside;", relaunch)
        self.assertIn("Soft.StillReady == null ? HostApp.Inside() : null", main, "a capture's window stays")
        arguments = guiscan.member_body("HostApp", "Arguments")
        self.assertIn(".Append(Outside)", arguments)

    def test_the_setup_window_asks_before_it_opens_and_relaunches_itself_marked(self):
        started = setup_method("Started")
        self.assertLess(started.index("HostApp.Without(arguments)"), started.index("Passed.Acceptable(arguments)"))
        asked = started.index("HostApp.Inside()")
        self.assertLess(asked, started.index("return Windowed(arguments);"))
        self.assertIn("HostApp.Arguments(arguments)", started[asked:])
        self.assertIn("!relaunched", started[asked:started.index("return Windowed(arguments);")])
        self.assertIn("HostApp.StuckInside = inside;", started)
        self.assertIn("arguments[0] != CodexAutoResume.HostApp.Outside", setup_method("Hook"),
                      "the mark is no test's hook")

    def test_a_window_that_stayed_inside_passes_the_mark_to_its_reopening(self):
        """The window's own parser ignores what it does not know, and the setup program's, which refuses it, has it
        taken off first (Started, above). A reopen passes it on only for a window that stayed inside, which does
        not try again in the middle of a reopen."""
        self.assertIn("if (HostApp.StuckInside != null) arguments.Add(HostApp.Outside);",
                      guiscan.member_body("SettingsForm", "ReopenArguments"))

    def test_the_three_maintenance_actions_refuse_while_stuck_inside(self):
        refused = guiscan.member_body("SettingsForm", "RefusedInside")
        self.assertIn("if (HostApp.StuckInside == null) return false;", refused)
        self.assertIn('S("diag.inside_app"', refused)
        self.assertIn('"app", HostApp.Name(HostApp.StuckInside)', refused)
        for member, before in (("Repair", "Confirm("), ("InstallUpdate", "SetBusy(true)"),
                               ("OpenVersions", "BuildVersions()")):
            with self.subTest(member):
                body = guiscan.member_body("SettingsForm", member)
                self.assertIn("if (RefusedInside()) return;", body)
                self.assertLess(body.index("RefusedInside()"), body.index(before))

    def test_the_setup_window_says_so_before_it_installs_or_removes(self):
        note = guiscan.member_body("InstallerWindow", "InsideNote")
        self.assertIn("if (HostApp.StuckInside == null) return;", note)
        self.assertIn('words.Say("installer.inside_app"', note)
        for page in ("BuildOptions", "BuildMaintain", "BuildConfirm"):
            with self.subTest(page):
                self.assertIn("InsideNote(", guiscan.member_body("InstallerWindow", page))

    def test_every_language_says_both_with_the_app_named(self):
        for catalog in sorted(LOCALES.glob("*.json")):
            words = json.loads(catalog.read_text(encoding="utf-8"))
            for key in ("diag.inside_app", "installer.inside_app"):
                with self.subTest(catalog=catalog.name, key=key):
                    self.assertIn("{app}", words.get(key, ""))


class FrontTests(unittest.TestCase):
    """v0.6.17 item 3a: after Finish, the Dashboard opened behind the windows already there."""

    def test_the_dashboard_after_finish_is_started_in_front(self):
        opened = setup_window_method("OpenDashboard")
        self.assertIn("HostApp.StartInFront(exe, null, home);", opened)
        self.assertNotIn("Process.Start(", opened)
        reopened = guiscan.member_body("SettingsForm", "OpenNewDashboard")
        self.assertIn("HostApp.StartInFront(exe, null, root)", reopened)
        self.assertNotIn("Process.Start(", reopened)
        started = guiscan.member_body("HostApp", "StartInFront")
        self.assertIn("AllowSetForegroundWindow(started.Id);", started)

    def test_a_window_a_person_opened_brings_itself_forward(self):
        main = guiscan.member_body("Program", "Main")
        self.assertIn("if (request.Generation == 0 && Soft.StillReady == null) HostApp.BringToFront(window);", main)
        self.assertLess(main.index("HostApp.BringToFront(window);"), main.index("Application.Run(window);"))
        run = setup_window_method("Run")
        self.assertLess(run.index("HostApp.BringToFront(window);"), run.index("Application.Run(window);"))
        front = guiscan.member_body("HostApp", "BringToFront")
        self.assertIn("SetForegroundWindow(window.Handle);", front)
        self.assertIn("ShowWindow(window.Handle, SwRestore);", front)
        self.assertIn("HostApp.Present(window);", guiscan.member_body("SettingsRemove", "Present"))

    def test_the_relaunch_lets_the_new_window_take_the_foreground(self):
        relaunch = guiscan.member_body("HostApp", "Relaunch")
        self.assertLess(relaunch.index("AllowSetForegroundWindow(AsfwAny);"), relaunch.index("ShellRun("))


if __name__ == "__main__":
    unittest.main()
