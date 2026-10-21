# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""A weekly update check while idle (v0.6.18): the Dashboard's Check for updates, run by the watcher once a week.

The standard edition asks GitHub whether a newer release exists only when a person presses Check for updates (C4, C5),
and refreshes the Codex compatibility data only on request, never from the watcher (C7) - the check refreshes it as it
goes. With this capability on, the watcher runs that very check on its own, at most once in WEEK, and only while no
recovery is waiting, being sent or being watched (core's records, domain/states.py) - at P8, as an errand, which starts
it and returns: the check itself runs on a thread of its own, so a slow network never holds a tick.

The check is the Dashboard's, switch for switch (gui/DashboardMaintenance.cs, CheckForUpdates and StartBootstrap): this
installation's own scripts/bootstrap.ps1, run by Windows PowerShell from System32 by full path, `-NoProfile
-NonInteractive -ExecutionPolicy Bypass -File <script> -CheckOnly`, with CODEX_AUTO_RESUME_PLUGIN_HOME naming this
installation and no console (CREATE_NO_WINDOW), waited for at most CHECK_SECONDS - the window's CheckMilliseconds -
and never killed: one that has not finished by then is left to finish on its own, and says nothing. Its answer is read
as the window reads it (`offer`): the `update:` line and the exit code must agree, and a newer release is offered
where it says `available`; where it says `current` or `newer-local`, a pre-release on a `prerelease:` line is offered
- exactly what a pressed check would offer, nothing else. An administrator's DisableUpdateCheck, which greys the
window's button, means no check here either.

What it offers it shows once, as a notice of its own kind (`update_offered`, registered with core in plug.py), whose
one button opens the Dashboard's Diagnostics page, where an update is installed (surfaces.update_view, core's
runtime/app.py). It never downloads or installs anything. The time of the last check is kept in this edition's own
state (state/choices.py, `stamp`, under OptionKey.LAST_CHECK), written before the check starts, so a check that fails,
is refused by GitHub or never finishes waits for the next week like one that answered.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import threading

from codex_auto_resume.domain.plug import DEFER

from ..vocabulary import OptionKey

CAPABILITY = "idle_update_check"
WEEK = 7 * 86400
# The Dashboard's CheckMilliseconds (gui/DashboardMaintenance.cs), in seconds.
CHECK_SECONDS = 120
# How often the errand looks whether a check is due, in seconds.
LOOK_EVERY = 60
# The answers of scripts/bootstrap.ps1's -CheckOnly: the `update:` line's first word, with the exit code it comes with.
ANSWERS = {"current": 0, "available": 10, "newer-local": 11, "unavailable": 12}
# A release's version, as the bootstrap rebuilds it from three integers; and a pre-release's, as the window holds the
# `prerelease:` line to before it offers it (DashboardMaintenance.PrereleaseRule).
RELEASE = re.compile(r"(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\Z")
PRERELEASE = re.compile(r"(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})-(alpha|beta)"
                        r"(\.([2-9]|[1-9][0-9]{1,2}))?\Z")
# The variables the window sets, or takes away, for the check: this installation, and nothing of an install.
HOME_VARIABLE = "CODEX_AUTO_RESUME_PLUGIN_HOME"
INSTALL_VARIABLES = ("CODEX_AUTO_RESUME_UPDATING_DASHBOARD", "CODEX_AUTO_RESUME_PROGRESS_LINES")
# Core's states of a recovery that is waiting, being sent or being watched: none may be, for a check to start.
BUSY = ("WAITING", "CLAIMED", "IN_FLIGHT", "OBSERVING")


def _last(printed, name):
    """The rest of the last line of `printed` that starts with `name`, or None."""
    found = None
    for line in str(printed or "").replace("\r", "").split("\n"):
        line = line.strip()
        if line.startswith(name):
            found = line[len(name):]
    return found


def offer(code, printed):
    """What a check that exited with `code` and printed `printed` offers, as the Dashboard reads it: (version, False)
    for a newer release, (version, True) for a newer pre-release, or None for nothing - up to date, ahead, GitHub not
    asked, or an answer the code and the line do not agree on. Pure."""
    line = _last(printed, "update: ")
    words = line.split(" ") if line is not None else []
    said = words[0] if words else ""
    if said not in ANSWERS or ANSWERS[said] != code:
        return None
    if said == "available":
        latest = words[2] if len(words) > 2 else ""
        return (latest, False) if RELEASE.match(latest) else None
    if said in ("current", "newer-local"):
        pre = _last(printed, "prerelease: ")
        if pre is not None and pre.startswith("v") and PRERELEASE.match(pre[1:]):
            return pre[1:], True
    return None


def script_of(paths) -> Path:
    """This installation's bootstrap, as the window finds it beside itself: <home>\\app\\scripts\\bootstrap.ps1."""
    return Path(paths.home) / "app" / "scripts" / "bootstrap.ps1"


def run_check(script, home, seconds=CHECK_SECONDS):
    """Run `script` -CheckOnly as the Dashboard does and wait for it at most `seconds`: (exit code, what it printed), or
    None where Windows PowerShell or the script is not there, it could not be started, or it has not finished - then it
    is left to finish on its own, never killed."""
    from codex_auto_resume import pwsh
    powershell = pwsh.executable()
    if powershell is None or not Path(script).is_file():
        return None
    environment = dict(os.environ)
    environment[HOME_VARIABLE] = str(home)
    for name in INSTALL_VARIABLES:
        environment.pop(name, None)
    try:
        process = subprocess.Popen(
            [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script),
             "-CheckOnly"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        return None
    try:
        printed, _errors = process.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        # Left to finish, as the window leaves a check it calls "running": what it prints is read and dropped.
        threading.Thread(target=process.communicate, daemon=True).start()
        return None
    return process.returncode, printed.decode("utf-8", "replace")


def _update_check_managed() -> bool:
    """Whether an administrator's DisableUpdateCheck is set (core's managed.py), asked afresh."""
    from codex_auto_resume.control.policy import managed_policy
    return managed_policy().disable_update_check is True


class _Errand:
    __slots__ = ("code", "now")

    def __init__(self, code, now):
        self.code, self.now = code, now

    def run(self, guard):
        return self.code.start(self.now)


class IdleUpdateCheck:
    """idle_update_check's code: its P8 errand, and what it offers for the icon's surface. `run`, `managed` and `start`
    are seams a test fills: the check (run_check's shape), the administrator's switch, and how the check's thread is
    started (`start(target)`)."""
    __slots__ = ("paths", "_scoped", "_run", "_managed", "_start", "_lock", "_offered", "_said", "_running",
                 "_looked")

    def __init__(self, paths, *, run=None, managed=None, start=None):
        self.paths = paths
        self._scoped = None
        self._run = run or run_check
        self._managed = managed or _update_check_managed
        self._start = start or (lambda target: threading.Thread(target=target, daemon=True).start())
        self._lock = threading.Lock()
        self._offered = None                   # (version, prerelease) the last check offered, for this process
        self._said = None                      # the journal word of a check that ended, not yet counted
        self._running = False
        self._looked = None

    def bind(self, scoped):
        self._scoped = scoped

    def tick(self, view):
        scoped = self._scoped
        if scoped is None:
            return DEFER
        self._count_said()
        try:
            now = scoped.now()
            if self._looked is not None and 0 <= now - self._looked < LOOK_EVERY:
                return DEFER
            self._looked = now
            return _Errand(self, now) if self._due(view, now) else DEFER
        except Exception:
            return DEFER

    def _due(self, view, now) -> bool:
        """Whether a check may start now: none running, none in the last WEEK, nothing waiting, being sent or watched,
        not turned off by an administrator, and this installation's bootstrap there to run."""
        with self._lock:
            if self._running:
                return False
        last = self._scoped.stamped(OptionKey.LAST_CHECK)
        if type(last) is int and 0 <= now - last < WEEK:
            return False
        if self._busy(view):
            return False
        if self._managed() is not False:
            return False
        return script_of(self.paths).is_file()

    @staticmethod
    def _busy(view) -> bool:
        """Whether core holds a recovery that is waiting, being sent or watched - or its records cannot be read."""
        from codex_auto_resume.domain import states
        wanted = frozenset().union(*(getattr(states, name) for name in BUSY))
        try:
            return bool(view.records_in(wanted))
        except Exception:
            return True

    def start(self, now):
        """The errand: the time of this check kept first, then the check started on a thread of its own. Nothing starts
        where the time cannot be kept - a check that could not be counted would run again at the next look."""
        if self._scoped.stamp(OptionKey.LAST_CHECK, int(now)) is not True:
            return None
        with self._lock:
            if self._running:
                return None
            self._running = True
        try:
            self._start(self._check)
        except Exception:
            with self._lock:
                self._running = False
        return None

    def _check(self):
        """The check, on its own thread: what it offers kept for the surface, and its word for the next tick to count."""
        try:
            answered = self._run(script_of(self.paths), self.paths.home)
            found = offer(*answered) if answered is not None else None
            said = "unanswered" if answered is None else "offered" if found is not None else "checked"
        except Exception:
            found, said = None, "unanswered"
        with self._lock:
            if found is not None:
                self._offered = found
            self._said = said
            self._running = False

    def _count_said(self) -> None:
        with self._lock:
            said, self._said = self._said, None
        if said is not None:
            try:
                self._scoped.count(said)
            except Exception:
                pass

    def offered(self):
        """(version, prerelease) the last check of this process offered, or None."""
        with self._lock:
            return self._offered


def make(paths) -> IdleUpdateCheck:
    return IdleUpdateCheck(paths)
