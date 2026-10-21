"""What every command has: the error it refuses with, the App it is given, the state it opens.

`PROG` is the name the parser prints and the name the shortcut runs, and is written here once.
"""
from __future__ import annotations

import os
import time

from .. import config
from ..app import App
from ..domain import ids
from ..openstate import open_state


PROG = "auto_resume"


class CliError(RuntimeError):
    pass


def canonical_thread_id(value: str) -> str:
    problem = ids.uuid_problem(value, as_text=True)
    if problem == ids.MALFORMED:
        raise CliError("thread id must be a canonical UUID (never --last or a name)")
    if problem is not None or str(value) != value:
        raise CliError("thread id must be lowercase canonical UUID text")
    return value


def _now() -> float:
    return time.time()


def _print(text: str = "") -> None:
    print(text)


# The setup window's request for progress lines (gui/InstallerFlow.cs, InstallerProgress.Variable), which install.ps1
# passes on to the setup step and the health check alone.
PROGRESS_LINES = "CODEX_AUTO_RESUME_PROGRESS_LINES"


def progress(step: str, done: int, total: int) -> None:
    """`progress: <step> <done>/<total>` - how much of an installer step is really done, for the setup window's bar,
    which reads the line and keeps it out of the log it shows. Only when the window asked for it: every other run
    prints exactly what it always did. Flushed, so the window has it while the step goes on, not when it ends."""
    if os.environ.get(PROGRESS_LINES) != "1" or total <= 0:
        return
    print("progress: %s %d/%d" % (step, max(0, min(done, total)), total), flush=True)


def _app(args) -> App:
    paths = config.Paths(args.home)
    return App(paths, codex_exe=args.codex_exe, codex_home=args.codex_home, console=not args.quiet)


def _open_state(app):
    """The state for a command that only switches things on or off, or cancels.

    While an older watcher still owns an unmigrated state, these keep working through
    the schema that watcher understands; nothing else does until it stops. So they do while an
    installation holds its lock: a notification's Cancel pressed during a pick, or the
    installer's own setup, works through that schema and upgrades nothing (openstate).
    """
    return open_state(app.paths.state_dir, legacy="always", hold_while_installing=True)
