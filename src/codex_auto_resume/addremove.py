"""The entry in Windows' list of installed programs ("Add or remove programs"), and nothing else.

Settings > Apps, `winget list`, `winget upgrade` and `winget uninstall` all find an installed program through one
key under the current user's Uninstall key. This writes that one key, per user, with the values Windows reads from
it: the name and version and publisher people see, where the program is, and the command that removes it - the
installer's own uninstall, kept as a copy in the installation (`uninstall\\install.ps1`, put there by the
installer), and the same command with -Silent for a caller that cannot answer or press a key.

One key per edition, by a fixed name (`CodexAutoResume`, and the advanced edition's with its word added), and only
one of them at a time: an edition change writes the new edition's and takes the other's away, a repair or an
update writes the same key again. Nothing is ever written to HKLM, and no other key is written.

What is removed is what can be proved ours, the rule the Run value follows (startup.belongs_to): a key is this
installation's only when its InstallLocation is this home and its uninstall command runs this home's kept
uninstaller. A key of that name that says anything else - another copy of this tool, something that happens to be
called the same - is left as it is.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import config, startup

UNINSTALL_ROOT = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
BASE_NAME = "CodexAutoResume"
PUBLISHER = "songyb111-gachon"
DEFAULT_DISPLAY_NAME = "Codex Auto Resume"
KEPT_FOLDER = "uninstall"
KEPT_SCRIPT = "install.ps1"
EDITIONS = ("standard", "advanced")


def key_name(edition: str) -> str:
    """The standard edition's key is `CodexAutoResume`; another edition adds its word, capitalised."""
    return BASE_NAME + ("" if edition == "standard" else edition.capitalize())


def key_path(edition: str) -> str:
    return UNINSTALL_ROOT + "\\" + key_name(edition)


def kept_script(home) -> Path:
    return Path(home) / KEPT_FOLDER / KEPT_SCRIPT


def powershell() -> Path:
    root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    return Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def uninstall_command(home, silent: bool = False) -> str:
    """The kept uninstaller, run by PowerShell by its full path as Install.cmd runs it. -Silent is the switch
    that asks nothing and waits for no key; the installer accepts it and the .cmd launchers act on it."""
    argv = [str(powershell()), "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(kept_script(home)), "-Uninstall"]
    if silent:
        argv.append("-Silent")
    return " ".join(startup.quote_argument(argument) for argument in argv)


def display_name() -> str:
    """The name the installed manifest gives this edition: the advanced edition's carries its word."""
    try:
        manifest = json.loads((config.PROJECT_ROOT / config.PLUGIN_MANIFEST).read_text(encoding="utf-8-sig"))
        text = str(manifest["interface"]["displayName"]).strip()
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_DISPLAY_NAME
    return text or DEFAULT_DISPLAY_NAME


def entry_values(home, name: str, version: str) -> dict:
    """The values of one key: name -> (value, REG_SZ or REG_DWORD, by Python type)."""
    return {
        "DisplayName": name,
        "DisplayVersion": version,
        "Publisher": PUBLISHER,
        "InstallLocation": str(Path(home)),
        "UninstallString": uninstall_command(home),
        "QuietUninstallString": uninstall_command(home, silent=True),
        "NoModify": 1,
        "NoRepair": 1,
    }


def read(edition: str) -> dict | None:
    """The values of the key of this edition's name, or None when there is none."""
    winreg = startup._winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path(edition), 0, winreg.KEY_READ) as key:
            found, index = {}, 0
            for name in ("DisplayName", "DisplayVersion", "Publisher", "InstallLocation", "UninstallString",
                         "QuietUninstallString", "NoModify", "NoRepair"):
                try:
                    found[name] = winreg.QueryValueEx(key, name)[0]
                except FileNotFoundError:
                    continue
            return found
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise startup.StartupError("Cannot read the current user's Uninstall key") from exc


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
    winreg = startup._winreg()
    done = []
    if edition not in EDITIONS or not kept_script(home).is_file() or not version or version == "unknown":
        return done
    existing = read(edition)
    if existing is not None and not owned(existing, home):
        return done
    values = entry_values(home, name or display_name(), version)
    if existing != values:
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path(edition), 0, winreg.KEY_SET_VALUE) as key:
                for value_name, value in values.items():
                    kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
                    winreg.SetValueEx(key, value_name, 0, kind, value)
        except OSError as exc:
            raise startup.StartupError("Cannot write the current user's Uninstall key") from exc
        done.append("wrote " + key_name(edition))
    for other in EDITIONS:
        if other != edition:
            done += ["removed " + key_name(other)] if remove_edition(other, home) else []
    return done


def remove_edition(edition: str, home) -> bool:
    """Delete this edition's key if it is this installation's. True when it was deleted."""
    winreg = startup._winreg()
    if not owned(read(edition), home):
        return False
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path(edition))
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise startup.StartupError("Cannot remove the current user's Uninstall key") from exc
    return True


def unregister(home) -> list[str]:
    """Delete whichever edition's key is this installation's. The names of the keys removed."""
    return [key_name(edition) for edition in EDITIONS if remove_edition(edition, home)]
