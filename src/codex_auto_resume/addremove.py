"""The entry in Windows' list of installed programs ("Add or remove programs"), and nothing else.

Settings > Apps, `winget list`, `winget upgrade` and `winget uninstall` all find an installed program through one
key under the current user's Uninstall key. This writes that one key, per user, with the values Windows reads from
it: the name and version and publisher people see, where the program is, and the command that removes it - the
installer's own uninstall, kept as a copy in the installation (`uninstall\\install.ps1`, put there by the
installer), and the same command with -Silent for a caller that cannot answer or press a key. Since v0.6.16 the
command a person runs from Settings > Apps shows it in the installer window: the installation's own Dashboard
program with `--uninstall` and that kept script (gui/SettingsRemove.cs), which runs the script's uninstall with
-Silent and shows how far it is; the quiet command still runs the script itself, with no window.

One key per edition, by a fixed name (`CodexAutoResume`, and the advanced edition's with its word added), and only
one of them at a time: an edition change writes the new edition's and takes the other's away, a repair or an
update writes the same key again. Nothing is ever written to HKLM, and no other key is written. This module
decides what the key says and whose it is; startup.py, the one module that touches the registry, reads, writes
and deletes it.

What is removed is what can be proved ours, the rule the Run value follows (startup.belongs_to): a key is this
installation's only when its InstallLocation is this home and its uninstall command runs this home's kept
uninstaller. A key of that name that says anything else - another copy of this tool, something that happens to be
called the same - is left as it is.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from . import startup

UNINSTALL_ROOT = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
BASE_NAME = "CodexAutoResume"
PUBLISHER = "songyb111-gachon"
DEFAULT_DISPLAY_NAME = "Codex Auto Resume"
# The first version that writes the entry and keeps the uninstaller. The bootstrap, the winget manifests and the tests
# hold their own copies of this number to it; a hand-over to an older version removes the entry first.
FIRST_VERSION = "0.6.16"
# Set by install.ps1 around the engine's uninstall step: the installer removes the entry itself once every removal
# has succeeded, so a failed uninstall stays listed and can be run again.
KEEP_ENTRY_ENV = "CODEX_AUTO_RESUME_KEEP_ENTRY"
KEPT_FOLDER = "uninstall"
KEPT_SCRIPT = "install.ps1"
# The installation's Dashboard program, which shows the uninstall in the installer window (gui/SettingsRemove.cs).
WINDOW = "CodexAutoResumeSettings.exe"
WINDOW_SWITCH = "--uninstall"
# The program's icon, which the installer puts beside the Dashboard program (build/make_release.py): the one Settings >
# Apps shows beside the entry (DisplayIcon). The Dashboard program carries the same icon, for a home without the file.
ICON = "codex-auto-resume.ico"
EDITIONS = ("standard", "advanced")
VALUE_NAMES = ("DisplayName", "DisplayVersion", "Publisher", "InstallLocation", "UninstallString",
               "QuietUninstallString", "NoModify", "NoRepair", "DisplayIcon")


def key_name(edition: str) -> str:
    """The standard edition's key is `CodexAutoResume`; another edition adds its word, capitalised."""
    return BASE_NAME + ("" if edition == "standard" else edition.capitalize())


def key_path(edition: str) -> str:
    return UNINSTALL_ROOT + "\\" + key_name(edition)


def kept_script(home) -> Path:
    return Path(home) / KEPT_FOLDER / KEPT_SCRIPT


def _plain(path, directory: bool) -> bool:
    """An ordinary folder or file: not a symbolic link, not a junction or any other reparse point, which is
    followed by is_file() and so by a command that runs what it points at."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        return False
    return stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)


def kept_uninstaller_present(home) -> bool:
    """The kept uninstaller is there, and so is the folder it is in, as plain files and not links (F4)."""
    return _plain(Path(home) / KEPT_FOLDER, True) and _plain(kept_script(home), False)


def remove_kept(home) -> bool:
    """Delete the kept uninstaller, and its folder once empty. Only plain ones; True when the script is gone."""
    if not kept_uninstaller_present(home):
        return False
    try:
        kept_script(home).unlink()
        (Path(home) / KEPT_FOLDER).rmdir()
    except OSError:
        pass
    return not kept_script(home).exists()


def powershell() -> Path:
    root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    return Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def uninstall_command(home, silent: bool = False) -> str:
    """The kept uninstaller. Quiet, it is run by PowerShell by its full path as Install.cmd runs it, with -Silent,
    the switch that asks nothing and waits for no key. Otherwise it is shown in the installer window, by the
    installation's own Dashboard program naming the same kept script - where that program is there, and by
    PowerShell as the quiet command runs it, without -Silent, where it is not."""
    window = Path(home) / WINDOW
    if not silent and window.is_file():
        return " ".join(startup.quote_argument(argument)
                        for argument in (str(window), WINDOW_SWITCH, str(kept_script(home))))
    argv = [str(powershell()), "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(kept_script(home)), "-Uninstall"]
    if silent:
        argv.append("-Silent")
    return " ".join(startup.quote_argument(argument) for argument in argv)


def display_name(manifest_path) -> str:
    """The name the installed manifest gives this edition: the advanced edition's carries its word."""
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
        text = str(manifest["interface"]["displayName"]).strip()
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_DISPLAY_NAME
    return text or DEFAULT_DISPLAY_NAME


def display_icon(home) -> str | None:
    """The installed program's icon, for Settings > Apps: the icon file the installer puts in the home, else the
    Dashboard program's own (its first icon, `,0`); None where neither is there. The entry had none, and Settings
    showed a blank square beside it (v0.6.16 acceptance)."""
    for name, suffix in ((ICON, ""), (WINDOW, ",0")):
        if _plain(Path(home) / name, False):
            return str(Path(home) / name) + suffix
    return None


def entry_values(home, name: str, version: str) -> dict:
    """The values of one key: name -> (value, REG_SZ or REG_DWORD, by Python type)."""
    values = {
        "DisplayName": name,
        "DisplayVersion": version,
        "Publisher": PUBLISHER,
        "InstallLocation": str(Path(home)),
        "UninstallString": uninstall_command(home),
        "QuietUninstallString": uninstall_command(home, silent=True),
        "NoModify": 1,
        "NoRepair": 1,
    }
    icon = display_icon(home)
    if icon:
        values["DisplayIcon"] = icon
    return values


def read(edition: str) -> dict | None:
    """The values of the key of this edition's name, or None when there is none."""
    return startup.read_key(key_path(edition), VALUE_NAMES)


def owned(values: dict | None, home) -> bool:
    """True when this key describes the installation rooted at `home`: it is installed there, and what it runs
    to uninstall is this home's kept uninstaller (not merely something in the same place)."""
    if not values:
        return False
    location, command = values.get("InstallLocation"), values.get("UninstallString")
    if not isinstance(location, str) or not isinstance(command, str) or not startup._same_path(location, home):
        return False
    try:
        argv = startup.parse_command(command)
    except startup.StartupError:
        return False
    return any(startup._same_path(argument, kept_script(home)) for argument in argv[1:])


def register(home, edition: str, version: str, name: str | None = None) -> list[str]:
    """Write this edition's key for the installation at `home`, and take the other edition's away when it is
    this installation's. Nothing is written unless the kept uninstaller is there for the key to name, and
    nothing is written over a key of that name that is not this installation's. Returns what was done."""
    done = []
    if edition not in EDITIONS or not kept_uninstaller_present(home) or not version or version == "unknown":
        return done
    existing = read(edition)
    if existing is not None and not owned(existing, home):
        return done
    values = entry_values(home, name or DEFAULT_DISPLAY_NAME, version)
    if existing != values:
        startup.write_key(key_path(edition), values)
        done.append("wrote " + key_name(edition))
    for other in EDITIONS:
        if other != edition:
            done += ["removed " + key_name(other)] if remove_edition(other, home) else []
    return done


def remove_edition(edition: str, home) -> bool:
    """Delete this edition's key if it is this installation's. True when it was deleted."""
    return owned(read(edition), home) and startup.delete_key(key_path(edition))


def unregister(home) -> list[str]:
    """Delete whichever edition's key is this installation's. The names of the keys removed."""
    return [key_name(edition) for edition in EDITIONS if remove_edition(edition, home)]
