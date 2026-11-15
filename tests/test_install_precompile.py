"""An update compiles the program it copies, once for each Python that will run it (v0.6.24, owner 2026-11-14).

The archive carries no compiled files (build/make_release.py), so the first process to import the program after an
update compiled every module it imported before it could answer. The v0.6.23 final's live acceptance saw the reopened
Dashboard on Loading... for 13.7 s after an update over a stopped watcher; on a scratch copy of the advanced edition the
Dashboard bridge's first answer took 9 to 10 s from a fresh tree and 2 to 3 s once its Python had compiled it. The
installer now compiles app\\src after the copy, for the bundled Python and the chosen one (advanced), counted in the
setup window's bar as the rest of the "files" step (install.ps1: Get-ChosenPython, Get-CompilePythons,
Invoke-Precompile).
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_installer_progress_lines import (INSTALL_PS1, POWERSHELL, PROGRESS, VARIABLE, _lift, _probe,  # noqa: E402
                                           _progress_lines)


def _function(name: str) -> str:
    return _lift("function %s {" % name, "\n}\n") + "\n}\n"


def _ps(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


@unittest.skipUnless(POWERSHELL.is_file(), "needs Windows PowerShell")
class PrecompileScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="install-precompile-"))
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.src = self.temp / "app" / "src"
        for relative in ("pkg/__init__.py", "pkg/a.py", "pkg/deep/b.py"):
            path = self.src / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("VALUE = %r\n" % relative, encoding="utf-8")
        (self.src / "pkg" / "notes.txt").write_text("not a module", encoding="utf-8")
        self.runtimes = self.temp / "runtimes"

    def run_script(self, body: str, python: str | None = None) -> subprocess.CompletedProcess:
        gate = _lift("$script:ProgressLines = $env:", "\n\n")
        head = ("$ErrorActionPreference = 'Stop'\nSet-StrictMode -Version 2.0\n"
                "$Python = %s\n$ChosenRuntimes = %s\n" % (_ps(Path(python or sys.executable)), _ps(self.runtimes)))
        script = (PROGRESS + gate + "\n" + head + _function("Get-ChosenPython") + _function("Get-CompilePythons")
                  + _function("Invoke-Precompile") + body)
        result = _probe(script, {VARIABLE: "1"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def compiled(self) -> list:
        tag = sys.implementation.cache_tag
        return sorted(path.relative_to(self.src).as_posix() for path in self.src.rglob("*.%s.pyc" % tag))

    def test_every_module_is_compiled_and_counted_after_what_was_copied(self):
        result = self.run_script("Invoke-Precompile -Pythons @($Python) -Source %s -Sources 3 -Before 2 -Total 5\n"
                                 % _ps(self.src))
        self.assertEqual(_progress_lines(result.stdout), ["progress: files 3/5", "progress: files 4/5",
                                                          "progress: files 5/5"])
        self.assertEqual(self.compiled(), ["pkg/__pycache__/__init__.%s.pyc" % sys.implementation.cache_tag,
                                           "pkg/__pycache__/a.%s.pyc" % sys.implementation.cache_tag,
                                           "pkg/deep/__pycache__/b.%s.pyc" % sys.implementation.cache_tag])
        self.assertIn("  Compiled the program for %s (" % Path(sys.executable).parent.name, result.stdout)
        self.assertNotIn(str(Path(sys.executable).parent), result.stdout, "the folder's name, never its path")

    def test_compiled_files_are_the_ones_python_takes(self):
        self.run_script("Invoke-Precompile -Pythons @($Python) -Source %s -Sources 3 -Before 0 -Total 3\n"
                        % _ps(self.src))
        spec = importlib.util.spec_from_file_location("a", self.src / "pkg" / "a.py")
        cached = Path(spec.cached)
        self.assertTrue(cached.is_file(), cached)
        # A cached file Python takes as current: compiling again finds nothing to do.
        import compileall
        before = cached.stat().st_mtime_ns
        self.assertTrue(compileall.compile_file(str(self.src / "pkg" / "a.py"), quiet=2))
        self.assertEqual(cached.stat().st_mtime_ns, before)

    def test_a_python_that_cannot_start_leaves_the_count_at_its_share(self):
        missing = self.temp / "gone" / "python.exe"
        result = self.run_script("Invoke-Precompile -Pythons @(%s, $Python) -Source %s -Sources 3 -Before 0 -Total 6\n"
                                 % (_ps(missing), _ps(self.src)))
        lines = _progress_lines(result.stdout)
        self.assertEqual(lines[0], "progress: files 3/6", "the missing one's share, at once")
        self.assertEqual(lines[-1], "progress: files 6/6")
        self.assertEqual(len(self.compiled()), 3)

    def test_a_module_that_does_not_compile_is_counted_and_the_rest_compiled(self):
        (self.src / "pkg" / "a.py").write_text("def broken(:\n", encoding="utf-8")
        result = self.run_script("Invoke-Precompile -Pythons @($Python) -Source %s -Sources 3 -Before 0 -Total 3\n"
                                 % _ps(self.src))
        self.assertEqual(_progress_lines(result.stdout)[-1], "progress: files 3/3")
        self.assertEqual(len(self.compiled()), 2)

    def chose(self, version: str, files=("python.exe",), record=None) -> Path:
        folder = self.runtimes / version
        folder.mkdir(parents=True, exist_ok=True)
        for name in files:
            (folder / name).write_bytes(b"MZ")
        (self.runtimes / "chosen.json").write_text(record if record is not None else json.dumps({"version": version}),
                                                   encoding="utf-8")
        return folder / "python.exe"

    def pythons(self, edition: str) -> list:
        result = self.run_script("$found = Get-CompilePythons -Edition '%s'\nWrite-Host ('count: ' + $found.Count)\n"
                                 "foreach ($p in $found) { Write-Host ('python: ' + $p) }\n" % edition)
        found = [line[len("python: "):] for line in result.stdout.splitlines() if line.startswith("python: ")]
        self.assertIn("count: %d" % len(found), result.stdout, "as the installer counts them: an array, as it is")
        return found

    def test_the_chosen_python_too_in_the_advanced_edition_alone(self):
        self.assertEqual(self.pythons("advanced"), [sys.executable], "nothing chosen")
        chosen = self.chose("3.15.2")
        self.assertEqual(self.pythons("advanced"), [sys.executable, str(chosen)])
        self.assertEqual(self.pythons("standard"), [sys.executable], "the standard edition has no chosen Python")

    def test_a_record_that_is_not_one_names_no_python(self):
        for record in ("{not json", json.dumps({"version": "3.15"}), json.dumps({"version": "4.0.0"}),
                       json.dumps({"other": "3.15.2"}), json.dumps(["3.15.2"]), " " * 5000):
            with self.subTest(record=record[:20]):
                self.chose("3.15.2", record=record)
                self.assertEqual(self.pythons("advanced"), [sys.executable])
        (self.runtimes / "3.15.2" / "python.exe").unlink()
        (self.runtimes / "chosen.json").write_text(json.dumps({"version": "3.15.2"}), encoding="utf-8")
        self.assertEqual(self.pythons("advanced"), [sys.executable], "no python.exe in its folder")

    def test_a_chosen_folder_that_is_a_junction_names_no_python(self):
        real = self.temp / "elsewhere"
        real.mkdir()
        (real / "python.exe").write_bytes(b"MZ")
        self.runtimes.mkdir()
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(self.runtimes / "3.15.2"), str(real)],
                              capture_output=True, creationflags=0x08000000)
        if made.returncode != 0:
            self.skipTest("no junction could be made here")
        (self.runtimes / "chosen.json").write_text(json.dumps({"version": "3.15.2"}), encoding="utf-8")
        self.assertEqual(self.pythons("advanced"), [sys.executable])


class PrecompilePlaceTests(unittest.TestCase):
    """Where the installer does it: after the copy, inside the copy's own step, with one total for the step."""

    def test_it_runs_after_both_trees_and_the_window_are_in_place_and_before_the_next_step(self):
        run = INSTALL_PS1.index("    Invoke-Precompile -Pythons $compilePythons -Source $compileSource -Sources")
        self.assertLess(INSTALL_PS1.index("-Entries $plan -Copied"), run)
        self.assertLess(INSTALL_PS1.index("foreach ($name in $rootFiles) {\n        $source"), run)
        self.assertLess(INSTALL_PS1.index("Fail 'The bundled Python runtime is missing from the payload.'"), run)
        self.assertLess(run, INSTALL_PS1.index("Ok ('Bundled Python '"), "before the window's next milestone")
        self.assertLess(run, INSTALL_PS1.index("Step 'Setting up the watcher'"), "before the watcher starts on it")

    def test_the_steps_one_total_counts_the_copy_and_the_compile(self):
        total = INSTALL_PS1.index("$copyFiles = @($copying | Where-Object { -not $_.Folder }).Count + "
                                  "$compileSources * $compilePythons.Count")
        self.assertLess(INSTALL_PS1.index("$compilePythons = Get-CompilePythons -Edition ([string](Get-Variable -Name edition"),
                        total)
        self.assertLess(total, INSTALL_PS1.index("Progress 'files' $copied $copyFiles"))
        self.assertIn("-Before $copied `\n                      -Total $copyFiles", INSTALL_PS1)


if __name__ == "__main__":
    unittest.main()
