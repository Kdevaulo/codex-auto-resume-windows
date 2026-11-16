"""What an update moved aside and could not delete, swept when the watcher starts (v0.6.18) and from the Dashboard's
bridge (v0.6.24, controlcli.sweep_soon) - beside the package, not in runtime/, so the bridge loads no watcher with it.

An update moves `app`, `runtime` and the Dashboard's files aside as `<name>.old-<stamp>` before it copies the new
ones (build/install/install.ps1), and deletes them once the copy is in place - unless something still had them open:
a Dashboard window of the old version, a Codex-started MCP server on the old runtime. Those stayed in the home until
the next install, about 14 MB each. The watcher now sweeps them as it starts, once it holds its mutex.

It touches nothing:
* in a home that is not provably ours (Paths.owns_home, the installer's own gate for the same sweep);
* while an installation, repair or update runs, or whether one does cannot be told (its lock);
* while the installer's copy journal is there: an update cut off by a power cut leaves the only complete tree under
  an `.old-` name, and only that journal tells which - the next install reads it and puts the tree back;
* that is not a direct child named `<name>.old-<14 digits>`, or that is a link or junction.

What is in use is left for a later look. A folder is first renamed, which Windows refuses while a file in it is open -
but not while a program runs from it: an image Windows has loaded does not hold its folder's name (the v0.6.24 review,
with PING.EXE run from a runtime.old- folder). So a folder any running program's file lies in is left as it is, asked of
every process this account can look at (windows.running_images), and every folder is left where that list cannot be
made. One line in the log says what was swept and what was left, and only when there was something.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil

from . import config, windows

# install.ps1: `$pair.dst + '.old-' + $stamp`, the stamp Get-Date -Format 'yyyyMMddHHmmss'; and the name a folder is
# given here just before it is deleted, so one whose deletion stopped half way is swept the next time.
SET_ASIDE = re.compile(r"[^\\/]+\.old-\d{14}(\.sweep)?")
# install.ps1 $Journal.
JOURNAL = ".codex-auto-resume-install-journal.json"


def candidates(home: Path) -> list[Path]:
    """The set-aside copies directly under `home`, by name; links and junctions are never one."""
    try:
        entries = sorted(Path(home).iterdir())
    except OSError:
        return []
    return [entry for entry in entries if SET_ASIDE.fullmatch(entry.name) and not config.is_link(entry)]


def _holds_a_program(entry: Path, images) -> bool:
    """Whether a running program's file lies inside the folder `entry`, by full path, case-blind."""
    try:
        inside = os.path.normcase(str(Path(entry).resolve())).rstrip("\\/") + os.sep
    except OSError:
        return True
    return any(os.path.normcase(image).startswith(inside) for image in images)


def _images(running):
    try:
        return running()
    except Exception:                               # noqa: BLE001 - a list not made is no list
        return None


def sweep(paths, log=None, *, installing=None, running=None) -> tuple[int, int]:
    """Delete what an update set aside in `paths.home`, where nothing holds it. (swept, left in use)."""
    home = paths.home
    found = candidates(home)
    if not found:
        return 0, 0
    installing = windows.install_in_progress if installing is None else installing
    if (home / JOURNAL).exists() or installing() is not False or not paths.owns_home():
        return 0, 0
    running = windows.running_images if running is None else running
    images = None
    swept = left = 0
    for entry in found:
        if not paths.confined(entry) or config.is_link(entry):
            continue
        try:
            if entry.is_dir():
                if images is None:
                    images = _images(running)
                if images is None or _holds_a_program(entry, images):
                    left += 1                      # a program runs from it, or that cannot be told: a later look
                    continue
                target = entry if entry.name.endswith(".sweep") else entry.with_name(entry.name + ".sweep")
                if target != entry:
                    os.rename(entry, target)       # refused while anything in it is open
                shutil.rmtree(target)
            else:
                entry.unlink()                     # refused while the program runs
            swept += 1
        except OSError:
            left += 1
    if log is not None:
        log("set-aside copies an update left: %d removed, %d still in use", swept, left)
    return swept, left
