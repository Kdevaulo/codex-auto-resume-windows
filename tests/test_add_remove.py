"""-Silent, and the entry in Add or remove programs (winget's way in and out).

Two things the winget package needs, and one rule for each (docs/STANDARDS.md F2, F5, F12):

* `-Silent` makes Install.cmd and Uninstall.cmd ask nothing and wait for no key, with every exit code and every line
  they have without it; install.ps1 accepts it (it never asks anything itself); the setup program passes it on and,
  with it, does not wait for Enter when it stops (tests/test_setup.py holds that half).
* The installer keeps a copy of itself in the installation, and the engine's setup writes ONE key under the user's
  Uninstall key - by a fixed name per edition - that names it; the engine's uninstall removes the key, and the
  installer the copy, but only what it can prove is its own.

Nothing here touches the real registry, the real installation or a real Codex. The launchers run in a scratch folder
whose "System32" is a copy of the two programs they call, and whose install.ps1 is a stub; the registry is a fake
module in the place startup.py already has for it (`startup._winreg`); the installer's functions are lifted out of
install.ps1 and run against scratch folders, as tests/test_installer.py does.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from codex_auto_resume import addremove, config, startup  # noqa: E402
import test_installer as installer  # noqa: E402  (its helpers: block, run_probe, ps_literal, VOICE)

INSTALL_DIR = ROOT / "build" / "install"
PS1 = INSTALL_DIR / "install.ps1"
WINDOWS = os.name == "nt"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SYSTEM32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"

STUB_PS1 = ('Add-Content -LiteralPath $env:STUB_RECORD -Value ("ran: " + ($args -join " "))\r\n'
            "exit ([int]$env:STUB_EXIT)\r\n")


class Launcher:
    """A copy of Install.cmd or Uninstall.cmd in a folder of its own, with a stub install.ps1 beside it, and a
    "SystemRoot" of the test's own holding the two programs the launcher calls by that path (chcp and PowerShell)."""

    def __init__(self, case: unittest.TestCase, name: str):
        self.base = Path(tempfile.mkdtemp(prefix="launcher-"))
        case.addCleanup(shutil.rmtree, self.base, True)
        folder = self.base / "archive"
        (folder / "install").mkdir(parents=True)
        # The launcher names the two programs by %SystemRoot%; here that is the scratch root, set in the text
        # (a changed SystemRoot in the environment would break PowerShell itself).
        text = (INSTALL_DIR / name).read_bytes().decode("utf-8").replace("%SystemRoot%", str(self.base / "root"))
        (folder / name).write_bytes(text.encode("utf-8"))
        (folder / "install" / "install.ps1").write_bytes(STUB_PS1.encode("ascii"))
        shell = self.base / "root" / "System32" / "WindowsPowerShell" / "v1.0"
        shell.mkdir(parents=True)
        shutil.copyfile(SYSTEM32 / "chcp.com", self.base / "root" / "System32" / "chcp.com")
        shutil.copyfile(SYSTEM32 / "WindowsPowerShell" / "v1.0" / "powershell.exe", shell / "powershell.exe")
        self.script = folder / name
        self.record = self.base / "record.txt"

    def run(self, *arguments: str, code: int = 0):
        environment = dict(os.environ, STUB_RECORD=str(self.record), STUB_EXIT=str(code))
        done = subprocess.run([str(SYSTEM32 / "cmd.exe"), "/d", "/c", str(self.script), *arguments],
                              capture_output=True, stdin=subprocess.DEVNULL, env=environment, timeout=120,
                              creationflags=NO_WINDOW, cwd=str(self.base))
        return done.returncode, done.stdout.decode("mbcs", "replace"), self.runs()

    def runs(self) -> list:
        return self.record.read_text(encoding="ascii", errors="replace").splitlines() if self.record.is_file() else []


@unittest.skipUnless(WINDOWS and (SYSTEM32 / "WindowsPowerShell" / "v1.0" / "powershell.exe").is_file(),
                     "the launchers are Windows batch files")
class LauncherTests(unittest.TestCase):
    PAUSE = "Press any key"
    ASK = "Change the edition?"

    def test_install_cmd_without_the_switch_still_pauses_and_still_asks(self):
        code, out, runs = Launcher(self, "Install.cmd").run()
        self.assertEqual((code, runs), (0, ["ran: "]))
        self.assertIn(self.PAUSE, out)
        code, out, runs = Launcher(self, "Install.cmd").run(code=14)
        self.assertEqual(code, 14, "an answer of no leaves the exit code as it was")
        self.assertIn(self.ASK, out)
        self.assertIn("Nothing was changed.", out)
        self.assertIn(self.PAUSE, out)
        self.assertEqual(runs, ["ran: "], "no answer is no, and the installer is not run again")

    def test_install_cmd_with_the_switch_asks_nothing_and_waits_for_no_key(self):
        for exit_code in (0, 1, 14, 3):
            with self.subTest(exit_code):
                code, out, runs = Launcher(self, "Install.cmd").run("-Silent", code=exit_code)
                self.assertEqual(code, exit_code)
                self.assertEqual(runs, ["ran: -Silent"], "passed on to install.ps1, once")
                self.assertNotIn(self.PAUSE, out)
                self.assertNotIn(self.ASK, out)
                self.assertEqual("Installation did not finish" in out, exit_code != 0)

    def test_the_switch_is_found_among_other_switches_in_any_case(self):
        code, out, runs = Launcher(self, "Install.cmd").run("-SkipStartup", "-silent", code=0)
        self.assertEqual((code, runs), (0, ["ran: -SkipStartup -silent"]))
        self.assertNotIn(self.PAUSE, out)
        _, out, _ = Launcher(self, "Install.cmd").run("-SkipStartup")
        self.assertIn(self.PAUSE, out)

    def test_uninstall_cmd_pauses_unless_silent_and_ends_with_the_installers_code(self):
        code, out, runs = Launcher(self, "Uninstall.cmd").run("-Purge", code=1)
        self.assertEqual((code, runs), (1, ["ran: -Uninstall -Purge"]))
        self.assertIn(self.PAUSE, out)
        code, out, runs = Launcher(self, "Uninstall.cmd").run("-Silent", code=1)
        self.assertEqual((code, runs), (1, ["ran: -Uninstall -Silent"]))
        self.assertNotIn(self.PAUSE, out)

    def test_the_launchers_keep_their_line_endings_and_their_one_pause(self):
        for name in ("Install.cmd", "Uninstall.cmd"):
            data = (INSTALL_DIR / name).read_bytes()
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""), name)
            text = data.decode("utf-8")
            self.assertEqual(len(re.findall(r"(?m)^pause\s*$", text)), 0, "every pause waits for the switch")
            self.assertEqual(text.count("if not defined SILENT pause"), 1, name)


@unittest.skipUnless(WINDOWS and installer.POWERSHELL, "the installer is PowerShell on Windows")
class InstallerSwitchTests(unittest.TestCase):
    def test_install_ps1_accepts_the_switch(self):
        """In a home with nothing in it the uninstall branch stops where it should - with a parameter binding
        error instead, it would never reach that line."""
        with tempfile.TemporaryDirectory() as home:
            done = subprocess.run(
                [installer.POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(PS1), "-Uninstall", "-Silent"],
                capture_output=True, text=True, timeout=120, creationflags=NO_WINDOW,
                env=dict(os.environ, CODEX_AUTO_RESUME_PLUGIN_HOME=home))
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("No installed runtime found here", done.stdout)
        self.assertNotIn("parameter", (done.stdout + done.stderr).lower())

    def test_it_asks_nothing_itself(self):
        text = PS1.read_text(encoding="utf-8")
        for asking in ("Read-Host", "PromptForChoice", "ReadKey", "Console]::In", "Pause"):
            self.assertNotIn(asking, text)


KEPT = "function Install-KeptUninstaller"
JOURNAL_FUNCTION = "function Write-CopyJournal"


@unittest.skipUnless(WINDOWS and installer.POWERSHELL, "the installer is PowerShell on Windows")
class KeptUninstallerTests(unittest.TestCase):
    """The installer's own function, lifted out of install.ps1 and run against scratch folders."""

    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="kept-"))
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.home = self.temp / "home"
        self.home.mkdir()
        self.source = self.temp / "archive" / "install" / "install.ps1"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"# the installer\r\nexit 0\r\n")
        self.outside = self.temp / "outside"
        self.outside.mkdir()

    def keep(self, source=None, before: str = ""):
        text = PS1.read_text(encoding="utf-8")
        helpers = installer.block(text, "function Resolve-Canonical", "function Get-Edition")
        helpers += installer.block(text, "function Remove-OwnedItem", "function Invoke-Setup")
        helpers += installer.block(text, KEPT, JOURNAL_FUNCTION)
        script = ("$OwnedHome = %s\n%s\n$kept = Install-KeptUninstaller -Source %s\n'result: ' + $kept\n"
                  % (installer.ps_literal(self.home), before, installer.ps_literal(source or self.source)))
        return installer.run_probe(installer.VOICE + helpers, script)

    def kept(self) -> Path:
        return self.home / "uninstall" / "install.ps1"

    def test_the_installer_is_copied_whole_into_a_folder_of_the_installations_own(self):
        done = self.keep()
        self.assertIn("result: True", done.stdout, done.stdout + done.stderr)
        self.assertEqual(self.kept().read_bytes(), self.source.read_bytes())
        self.assertEqual(sorted(path.name for path in self.kept().parent.iterdir()), ["install.ps1"],
                         "no half-written copy is left beside it")

    def test_a_second_run_replaces_it_and_the_path_matches_the_one_the_engine_names(self):
        self.keep()
        self.source.write_bytes(b"# the next version\r\n")
        self.assertIn("result: True", self.keep().stdout)
        self.assertEqual(self.kept().read_bytes(), b"# the next version\r\n")
        self.assertEqual(self.kept(), addremove.kept_script(self.home))

    def test_the_kept_copy_itself_as_the_source_is_left_as_it_is(self):
        self.keep()
        done = self.keep(source=self.kept())
        self.assertIn("result: True", done.stdout, done.stdout + done.stderr)
        self.assertEqual(self.kept().read_bytes(), self.source.read_bytes())

    def test_a_junction_where_the_folder_should_be_is_not_followed(self):
        junction = self.home / "uninstall"
        made = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(self.outside)],
                              capture_output=True, creationflags=NO_WINDOW)
        if made.returncode != 0:
            self.skipTest("no junction could be made here")
        done = self.keep()
        self.assertIn("result: False", done.stdout, done.stdout + done.stderr)
        self.assertEqual(list(self.outside.iterdir()), [], "nothing was written where the junction points")

    def test_a_junction_to_another_place_inside_the_installation_is_not_followed_either(self):
        inside = self.home / "app"
        inside.mkdir()
        made = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(self.home / "uninstall"), str(inside)],
                              capture_output=True, creationflags=NO_WINDOW)
        if made.returncode != 0:
            self.skipTest("no junction could be made here")
        done = self.keep()
        self.assertIn("result: False", done.stdout, done.stdout + done.stderr)
        self.assertEqual(list(inside.iterdir()), [], "nothing was written through the junction")

    def test_a_file_where_the_folder_should_be_is_left_alone(self):
        (self.home / "uninstall").write_text("not a folder", encoding="utf-8")
        done = self.keep()
        self.assertIn("result: False", done.stdout, done.stdout + done.stderr)
        self.assertEqual((self.home / "uninstall").read_text(encoding="utf-8"), "not a folder")

    def test_a_home_that_cannot_be_written_into_says_so_and_keeps_going(self):
        self.source.unlink()
        done = self.keep()
        self.assertIn("result: False", done.stdout, done.stdout + done.stderr)
        self.assertIn("Could not keep an uninstaller", done.stdout)
        self.assertFalse(self.kept().exists())


@unittest.skipUnless(WINDOWS and installer.POWERSHELL, "the installer is PowerShell on Windows")
class InstallerFlowTests(unittest.TestCase):
    def setUp(self):
        self.text = PS1.read_text(encoding="utf-8")

    def test_it_is_kept_only_for_the_ordinary_home_and_before_the_engine_writes_the_entry(self):
        call = installer.block(self.text, "# The entry in Add or remove programs is written", "Step 'Setting up the watcher'")
        self.assertIn("IsNullOrWhiteSpace($env:CODEX_AUTO_RESUME_PLUGIN_HOME)", call)
        self.assertIn("Install-KeptUninstaller -Source $PSCommandPath", call)
        self.assertLess(self.text.index("Install-KeptUninstaller -Source"), self.text.rindex("$code = Invoke-Setup $setupArgs"))
        self.assertEqual(self.text.count("Install-KeptUninstaller -Source"), 1)

    def test_the_installer_writes_no_registry_key_itself(self):
        for forbidden in ("New-ItemProperty", "Set-ItemProperty", "reg add", "reg.exe", "HKCU:", "Registry]::"):
            self.assertNotIn(forbidden, self.text)

    def test_the_uninstall_removes_the_kept_folder_after_the_program_files_and_before_the_proof(self):
        branch = installer.block(self.text, "if ($Uninstall)", "# -------------------------------------------------------------------------- install")
        removal = branch.index("$null = Remove-OwnedItem $kept")
        self.assertGreater(removal, branch.index("Some program files are still in use"))
        self.assertLess(removal, branch.index("'.owned-by-codex-auto-resume'"))
        self.assertIn("-not $keptItem.LinkType", branch)

    def uninstall_tail(self, home: Path, kept: bool, link: Path | None = None):
        text = self.text
        source = installer.VOICE + installer.block(text, "function Quote-Argument", "function Invoke-Setup")
        source += "\nfunction Fail { param([string]$m) $script:Failed = $true; Write-Host $m }\n"
        script = ("$OwnedHome = %s\n$InstallHome = $OwnedHome\n$AppDir = Join-Path $OwnedHome app\n"
                  "$RunDir = Join-Path $OwnedHome runtime\n$PluginCacheRoot = Join-Path $OwnedHome cache\n"
                  "$PluginName = 'fixture-plugin'\n$MarketplaceName = 'fixture-market'\n$script:Failed = $false\n"
                  "$Purge = $false\n" % installer.ps_literal(home))
        script += ("function Get-CodexCli { return $null }\nfunction Get-OwnedMcpProcess { return ,@() }\n")
        branch = installer.block(text, "# ----------------------------------------------------------------------- uninstall",
                                 "# -------------------------------------------------------------------------- install")
        script += "if ($true) {\n" + branch[branch.index("    $codex = Get-CodexCli"):]
        return installer.run_probe(source, script)

    def installation(self, root: Path) -> Path:
        home = root / "home"
        (home / "app").mkdir(parents=True)
        (home / "runtime").mkdir()
        (home / "runtime" / "python.exe").write_text("fixture", encoding="utf-8")
        (home / ".owned-by-codex-auto-resume").write_text("fixture", encoding="utf-8")
        (home / "config").mkdir()
        (home / "config" / "settings.json").write_text("{}", encoding="utf-8")
        (home / "uninstall").mkdir()
        (home / "uninstall" / "install.ps1").write_text("# kept", encoding="utf-8")
        return home

    def test_uninstalling_takes_the_kept_copy_and_keeps_the_settings(self):
        with tempfile.TemporaryDirectory() as name:
            home = self.installation(Path(name))
            done = self.uninstall_tail(home, kept=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertFalse((home / "uninstall").exists(), "the kept uninstaller goes with the program")
            self.assertTrue((home / "config" / "settings.json").is_file())

    def test_a_junction_named_uninstall_is_not_followed_out_of_the_installation(self):
        with tempfile.TemporaryDirectory() as name:
            home = self.installation(Path(name))
            outside = Path(name) / "outside"
            outside.mkdir()
            (outside / "precious.txt").write_text("not ours", encoding="utf-8")
            shutil.rmtree(home / "uninstall")
            made = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(home / "uninstall"), str(outside)],
                                  capture_output=True, creationflags=NO_WINDOW)
            if made.returncode != 0:
                self.skipTest("no junction could be made here")
            done = self.uninstall_tail(home, kept=True)
            self.assertTrue((outside / "precious.txt").is_file(), done.stdout + done.stderr)


# ---------------------------------------------------------------------------------------------------- the key

class FakeWinreg:
    """The slice of winreg the entry uses, over a dict: key path -> {value name: (value, kind)}."""
    HKEY_CURRENT_USER = object()
    KEY_READ, KEY_SET_VALUE = 1, 2
    REG_SZ, REG_DWORD = 1, 4

    def __init__(self):
        self.keys: dict = {}
        self.writes = []

        class Key:
            def __init__(inner, path):
                inner.path = path

            def __enter__(inner):
                return inner

            def __exit__(inner, *exc):
                return False

        self.Key = Key

    def OpenKey(self, root, path, reserved, access):
        if path not in self.keys:
            raise FileNotFoundError(path)
        return self.Key(path)

    def CreateKeyEx(self, root, path, reserved, access):
        self.keys.setdefault(path, {})
        self.writes.append(path)
        return self.Key(path)

    def QueryValueEx(self, key, name):
        values = self.keys.get(key.path, {})
        if name not in values:
            raise FileNotFoundError(name)
        return values[name]

    def SetValueEx(self, key, name, reserved, kind, value):
        self.keys.setdefault(key.path, {})[name] = (value, kind)

    def DeleteKey(self, root, path):
        if path not in self.keys:
            raise FileNotFoundError(path)
        del self.keys[path]


class Entry(unittest.TestCase):
    """A scratch home with a kept uninstaller, and a fake registry in startup's place for it."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / ".codex-auto-resume"
        (self.home / "uninstall").mkdir(parents=True)
        (self.home / "uninstall" / "install.ps1").write_text("# kept", encoding="utf-8")
        self.registry = FakeWinreg()
        guard = patch.object(startup, "_winreg", return_value=self.registry)
        guard.start()
        self.addCleanup(guard.stop)

    def values(self, edition="standard"):
        return {name: value for name, (value, kind) in self.registry.keys[addremove.key_path(edition)].items()}


@unittest.skipUnless(WINDOWS, "the registry is Windows'")
class KeyTests(Entry):
    def test_one_key_with_the_values_windows_and_winget_read(self):
        done = addremove.register(self.home, "standard", "1.2.3", "Codex Auto Resume")
        self.assertEqual(done, ["wrote CodexAutoResume"])
        self.assertEqual(list(self.registry.keys),
                         [r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CodexAutoResume"])
        values = self.values()
        self.assertEqual({key: values[key] for key in ("DisplayName", "DisplayVersion", "Publisher")},
                         {"DisplayName": "Codex Auto Resume", "DisplayVersion": "1.2.3",
                          "Publisher": "songyb111-gachon"})
        self.assertEqual(values["InstallLocation"], str(self.home))
        self.assertEqual((values["NoModify"], values["NoRepair"]), (1, 1))
        kinds = {name: kind for name, (value, kind) in self.registry.keys[addremove.key_path("standard")].items()}
        self.assertEqual(kinds["NoModify"], FakeWinreg.REG_DWORD)
        self.assertEqual(kinds["UninstallString"], FakeWinreg.REG_SZ)
        self.assertEqual(sorted(values), sorted(["DisplayName", "DisplayVersion", "Publisher", "InstallLocation",
                                                 "UninstallString", "QuietUninstallString", "NoModify", "NoRepair"]))

    def test_the_commands_run_the_kept_installer_by_full_paths_and_the_quiet_one_adds_the_switch(self):
        addremove.register(self.home, "standard", "1.2.3", "Codex Auto Resume")
        values = self.values()
        loud, quiet = startup.parse_command(values["UninstallString"]), startup.parse_command(values["QuietUninstallString"])
        self.assertEqual(loud[0].lower(), str(addremove.powershell()).lower())
        self.assertEqual(loud[1:], ["-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                    str(self.home / "uninstall" / "install.ps1"), "-Uninstall"])
        self.assertEqual(quiet, loud + ["-Silent"])

    def test_a_home_with_spaces_is_one_argument(self):
        home = Path(self.temp.name) / "Example User" / ".codex-auto-resume"
        (home / "uninstall").mkdir(parents=True)
        (home / "uninstall" / "install.ps1").write_text("# kept", encoding="utf-8")
        addremove.register(home, "standard", "1.2.3", "Codex Auto Resume")
        argv = startup.parse_command(self.values()["QuietUninstallString"])
        self.assertIn(str(home / "uninstall" / "install.ps1"), argv)
        self.assertTrue(addremove.owned(self.registry.keys[addremove.key_path("standard")] and
                                        {k: v for k, (v, _) in self.registry.keys[addremove.key_path("standard")].items()},
                                        home))

    def test_the_other_editions_key_has_its_own_fixed_name(self):
        self.assertEqual((addremove.key_name("standard"), addremove.key_name("advanced")),
                         ("CodexAutoResume", "CodexAutoResumeAdvanced"))
        addremove.register(self.home, "advanced", "1.2.3", "Codex Auto Resume Advanced")
        self.assertEqual(list(self.registry.keys), [addremove.key_path("advanced")])
        self.assertEqual(self.values("advanced")["DisplayName"], "Codex Auto Resume Advanced")

    def test_an_update_rewrites_the_one_key_and_a_repeat_writes_nothing(self):
        addremove.register(self.home, "standard", "1.2.3", "Codex Auto Resume")
        writes = len(self.registry.writes)
        self.assertEqual(addremove.register(self.home, "standard", "1.2.3", "Codex Auto Resume"), [])
        self.assertEqual(len(self.registry.writes), writes, "the same entry is not written again")
        self.assertEqual(addremove.register(self.home, "standard", "1.2.4", "Codex Auto Resume"), ["wrote CodexAutoResume"])
        self.assertEqual(self.values()["DisplayVersion"], "1.2.4")
        self.assertEqual(len(self.registry.keys), 1)

    def test_an_edition_change_leaves_exactly_one_key(self):
        addremove.register(self.home, "standard", "1.2.3", "Codex Auto Resume")
        done = addremove.register(self.home, "advanced", "1.2.3", "Codex Auto Resume Advanced")
        self.assertEqual(done, ["wrote CodexAutoResumeAdvanced", "removed CodexAutoResume"])
        self.assertEqual(list(self.registry.keys), [addremove.key_path("advanced")])
        done = addremove.register(self.home, "standard", "1.2.3", "Codex Auto Resume")
        self.assertEqual(list(self.registry.keys), [addremove.key_path("standard")])
        self.assertEqual(done, ["wrote CodexAutoResume", "removed CodexAutoResumeAdvanced"])

    def test_nothing_is_written_without_a_kept_uninstaller_or_a_known_version(self):
        (self.home / "uninstall" / "install.ps1").unlink()
        self.assertEqual(addremove.register(self.home, "standard", "1.2.3", "x"), [])
        (self.home / "uninstall" / "install.ps1").write_text("# kept", encoding="utf-8")
        for version in ("", "unknown"):
            self.assertEqual(addremove.register(self.home, "standard", version, "x"), [])
        self.assertEqual(addremove.register(self.home, "sideways", "1.2.3", "x"), [])
        self.assertEqual(self.registry.keys, {})

    def test_the_display_name_is_the_installed_manifests_and_the_publisher_is_the_plugin_author(self):
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(addremove.display_name(ROOT / ".codex-plugin" / "plugin.json"), manifest["interface"]["displayName"])
        self.assertEqual(addremove.display_name(ROOT / "no-such-manifest.json"), "Codex Auto Resume")
        self.assertEqual(addremove.PUBLISHER, manifest["author"]["name"])


@unittest.skipUnless(WINDOWS, "the registry is Windows'")
class ProvenanceTests(Entry):
    """Only a key that can be proved this installation's is overwritten or deleted."""

    def foreign(self, **changes):
        addremove.register(self.home, "standard", "1.2.3", "Codex Auto Resume")
        key = self.registry.keys[addremove.key_path("standard")]
        for name, value in changes.items():
            key[name] = (value, FakeWinreg.REG_SZ)
        return dict(key)

    def test_unregister_removes_this_installations_key(self):
        addremove.register(self.home, "standard", "1.2.3", "Codex Auto Resume")
        self.assertEqual(addremove.unregister(self.home), ["CodexAutoResume"])
        self.assertEqual(self.registry.keys, {})
        self.assertEqual(addremove.unregister(self.home), [], "nothing to remove is not an error")

    def test_a_key_of_that_name_for_another_home_is_kept_and_not_overwritten(self):
        other = Path(self.temp.name) / "other-home"
        before = self.foreign(InstallLocation=str(other))
        self.assertEqual(addremove.unregister(self.home), [])
        self.assertEqual(addremove.register(self.home, "standard", "9.9.9", "x"), [])
        self.assertEqual(dict(self.registry.keys[addremove.key_path("standard")]), before)

    def test_a_key_whose_uninstall_command_is_not_this_homes_kept_installer_is_kept(self):
        before = self.foreign(UninstallString='"C:\\Other\\uninstall.exe" /S')
        self.assertEqual(addremove.unregister(self.home), [])
        self.assertEqual(dict(self.registry.keys[addremove.key_path("standard")]), before)

    def test_a_key_that_only_names_the_home_is_not_enough(self):
        before = self.foreign(UninstallString='"C:\\Other\\uninstall.exe" /S')
        self.assertFalse(addremove.owned({"InstallLocation": str(self.home), "UninstallString": "x"}, self.home))
        self.assertFalse(addremove.owned(None, self.home))
        self.assertFalse(addremove.owned({}, self.home))
        self.assertIsNotNone(before)

    def test_an_edition_change_does_not_take_a_foreign_key_of_the_other_name(self):
        other = Path(self.temp.name) / "other-home"
        self.registry.keys[addremove.key_path("standard")] = {
            "InstallLocation": (str(other), 1), "UninstallString": ("x", 1)}
        addremove.register(self.home, "advanced", "1.2.3", "Codex Auto Resume Advanced")
        self.assertIn(addremove.key_path("standard"), self.registry.keys)

    def test_no_other_key_is_ever_touched(self):
        unrelated = {r"Software\Microsoft\Windows\CurrentVersion\Uninstall\SomethingElse": {"DisplayName": ("x", 1)},
                     startup.RUN_KEY: {"CodexAutoResume": ("run", 1)}}
        self.registry.keys.update({key: dict(value) for key, value in unrelated.items()})
        addremove.register(self.home, "standard", "1.2.3", "Codex Auto Resume")
        addremove.register(self.home, "advanced", "1.2.3", "Codex Auto Resume Advanced")
        addremove.unregister(self.home)
        self.assertEqual(self.registry.keys, unrelated)
        self.assertEqual(set(self.registry.writes), {addremove.key_path("standard"), addremove.key_path("advanced")})


@unittest.skipUnless(WINDOWS, "the registry is Windows'")
class WiringTests(Entry):
    """The two commands that reach it: the plugin bridge's setup and the engine's uninstall."""

    def test_the_engines_uninstall_removes_the_entry_and_says_so(self):
        from codex_auto_resume import cli, shortcut
        addremove.register(self.home, "standard", "1.2.3", "Codex Auto Resume")
        out = io.StringIO()
        with patch.object(shortcut, "uninstall", return_value=False), patch.dict(
                os.environ, {"LOCALAPPDATA": str(Path(self.temp.name) / "none"),
                             "CODEX_HOME": str(Path(self.temp.name) / "codex"), config.ENV_HOME: str(self.home)}), \
                contextlib.redirect_stdout(out):
            code = cli.main(["--home", str(self.home), "uninstall", "--keep-state"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertNotIn(addremove.key_path("standard"), self.registry.keys)
        self.assertIn("entry in Add or remove programs", out.getvalue())

    def test_the_bridges_setup_registers_only_through_this_module(self):
        text = (ROOT / "scripts" / "plugin_setup.py").read_text(encoding="utf-8")
        self.assertIn("addremove.register(home, edition.name().value, config.version(),", text)
        self.assertIn("addremove.display_name(config.PROJECT_ROOT / config.PLUGIN_MANIFEST))", text)
        self.assertEqual(text.count("addremove."), 2)
        for forbidden in ("winreg", "CurrentVersion"):
            self.assertNotIn(forbidden, text)

    def test_the_bridges_setup_writes_the_entry_after_the_protocol_and_before_the_watcher_starts(self):
        text = (ROOT / "scripts" / "plugin_setup.py").read_text(encoding="utf-8")
        setup = text[text.index("def cmd_setup"):text.index("def cmd_enable")]
        self.assertLess(setup.index("startup.install_protocol"), setup.index("addremove.register"))
        self.assertLess(setup.index("addremove.register"), setup.index("started = start_watcher(home)"))

    def test_the_only_registry_code_added_lives_in_the_one_module(self):
        found = []
        for path in (ROOT / "src" / "codex_auto_resume").rglob("*.py"):
            if "CurrentVersion\\Uninstall" in path.read_text(encoding="utf-8", errors="replace"):
                found.append(path.name)
        self.assertEqual(found, ["addremove.py"])


if __name__ == "__main__":
    unittest.main()
