"""v0.6.26 final: setup's log says the watcher runs on the chosen Python, beside the bundled one.

The 2026-11-24 acceptance read "[ok] Bundled Python 3.14 (no system Python needed)" in an update's log while the watcher
ran on the python.org 3.15.2 the person had chosen in the advanced edition (runtimes\\3.15.2). The bundled line stays as
it was - it still runs setup and the launcher, and the setup window's step reads its start (gui/InstallerFlow.cs) - and
a line after it names the chosen Python where one runs the watcher, by the rule the compile uses (Get-CompilePythons).
The standard edition, and an advanced one with nothing chosen, log exactly what they logged.

The installer's own functions and lines are run, cut from build/install/install.ps1, against a scratch folder: no
real installation, no real runtimes folder.

    PYTHONPATH=src;tests python -m unittest test_installer_chosen_python_line
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL_PS1 = (ROOT / "build" / "install" / "install.ps1").read_text(encoding="utf-8")
SYSTEM = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
POWERSHELL = SYSTEM / "WindowsPowerShell" / "v1.0" / "powershell.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
BUNDLED_LINE = "    Ok ('Bundled Python ' + $runtimeVersion + ' (no system Python needed)')"


def cut(start, end):
    first = INSTALL_PS1.index(start)
    return INSTALL_PS1[first:INSTALL_PS1.index(end, first)]


@unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "the installer is PowerShell on Windows")
class ChosenPythonLineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtimes = self.root / "runtimes"
        self.bundled = self.root / "runtime" / "python.exe"
        self.bundled.parent.mkdir(parents=True)
        self.bundled.write_bytes(b"")

    def choose(self, version):
        folder = self.runtimes / version
        folder.mkdir(parents=True)
        (folder / "python.exe").write_bytes(b"")
        (self.runtimes / "chosen.json").write_text('{"version": "%s"}' % version, encoding="utf-8")

    def log(self, edition):
        functions = cut("function Get-ChosenPython {", "function Invoke-Precompile {")
        start = INSTALL_PS1.index(BUNDLED_LINE)
        lines = INSTALL_PS1[start:INSTALL_PS1.index("\n    }", start) + len("\n    }")]

        def quoted(value):
            return "'" + str(value).replace("'", "''") + "'"
        script = ("Set-StrictMode -Version 2.0\n$ErrorActionPreference = 'Stop'\n"
                  "function Ok { param([string]$m) Write-Host ('  [ok] ' + $m) }\n" + functions +
                  "\n$ChosenRuntimes = %s\n$Python = %s\n$edition = %s\n$runtimeVersion = '3.14'\n"
                  % (quoted(self.runtimes), quoted(self.bundled), quoted(edition)) + lines + "\nWrite-Host 'went on'\n")
        path = self.root / "probe.ps1"
        path.write_text(script, encoding="utf-8-sig")
        done = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                               str(path)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              encoding="utf-8", errors="replace", timeout=120, creationflags=NO_WINDOW)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("went on", done.stdout)
        return [line.strip() for line in done.stdout.splitlines() if line.strip().startswith("[ok]")]

    def test_a_chosen_python_that_runs_the_watcher_is_named_beside_the_bundled_one(self):
        self.choose("3.15.2")
        self.assertEqual(self.log("advanced"), ["[ok] Bundled Python 3.14 (no system Python needed)",
                                                "[ok] The watcher runs on the chosen Python 3.15.2"])

    def test_nothing_chosen_logs_what_it_logged(self):
        self.assertEqual(self.log("advanced"), ["[ok] Bundled Python 3.14 (no system Python needed)"])

    def test_the_standard_edition_logs_what_it_logged_whatever_a_record_says(self):
        self.choose("3.15.2")
        self.assertEqual(self.log("standard"), ["[ok] Bundled Python 3.14 (no system Python needed)"])

    def test_the_setup_windows_step_still_reads_the_bundled_line_first(self):
        flow = (ROOT / "gui" / "InstallerFlow.cs").read_text(encoding="utf-8")
        self.assertEqual(flow.count('new Milestone("[ok] Bundled Python"'), 2)
        self.assertNotIn("The watcher runs on", flow)


if __name__ == "__main__":
    unittest.main()
