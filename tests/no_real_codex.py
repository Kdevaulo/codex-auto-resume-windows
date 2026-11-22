"""No test sees this PC's Codex processes: the guard every test run loads (v0.6.24 final).

Until v0.6.24 the process inventory (codex/pairing.py) was a PowerShell CIM query started through subprocess.run,
so every test that stands in for subprocess.run - the compatibility fixture (tests/test_compat_characterization.py
Fixture) and every test built on it - had no process list at all, as CI's runner has no Codex app. The inventory now
reads one Toolhelp snapshot and starts no process, so on a PC where the Codex app runs those tests saw its real
ChatGPT.exe and its OpenAI-signed codex.exe, and took that engine for their own: red here, green on CI.

**The seam.** win/kernel.processes_named is the one real read under the inventory. Once that module has run, the
guard puts itself in front of it: every ChatGPT.exe and codex.exe is left out of what it lists, so each test sees
the machine as CI's runner is - no Codex app, no engine - unless the test asks for this PC's own (`real()`). A test
that stands in for pairing.inventory or for processes_named puts its own stand-in in front of the guard, as it always
did, and nothing changes for it.

**Loaded by every run**, as tests/no_real_toast.py is: tests/sitecustomize.py installs it in any interpreter that has
tests/ on its path, and scripts/test_parts.py in the process that runs a suite. It imports nothing until the module it
guards is imported, and never raises out of install().

Not a test module (no `test_` prefix), so discovery does not collect it.
"""
from __future__ import annotations

import contextlib
import functools
import sys

GUARDED_MODULE = "codex_auto_resume.win.kernel"
# The program files of the Codex app and of every Codex engine, compared without case as Windows compares names.
HIDDEN = frozenset({"chatgpt.exe", "codex.exe"})
MARK = "_no_real_codex"

_state = {"installed": False, "real": 0}


def active() -> bool:
    """Whether the guard is installed in this interpreter."""
    return _state["installed"]


@contextlib.contextmanager
def real():
    """This PC's own Codex processes are listed while it lasts: for a test that compares the read with Windows' own."""
    _state["real"] += 1
    try:
        yield
    finally:
        _state["real"] -= 1


def _guard_kernel(module) -> None:
    listed = getattr(module, "processes_named", None)
    if listed is None or getattr(listed, MARK, False):
        return

    @functools.wraps(listed)
    def guarded(names, families=()):
        names, families = tuple(names), tuple(families)
        if _state["real"] <= 0:
            # v0.6.26: and no process of the Codex app's package found by its family, whatever it is called.
            names, families = tuple(name for name in names if str(name).casefold() not in HIDDEN), ()
        return listed(names, families)

    setattr(guarded, MARK, True)
    module.processes_named = guarded


class _Loader:
    def __init__(self, loader):
        self._loader = loader

    def create_module(self, spec):
        return self._loader.create_module(spec)

    def exec_module(self, module):
        self._loader.exec_module(module)
        try:
            _guard_kernel(module)
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._loader, name)


class _Finder:
    """Finds nothing itself: for the guarded module only, the spec the other finders find, with a loader that guards
    the module after it runs - before any module that imports processes_named by name can take it."""

    def find_spec(self, name, path=None, target=None):
        if name != GUARDED_MODULE:
            return None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(name, path, target)
            if spec is not None:
                if spec.loader is not None and hasattr(spec.loader, "exec_module"):
                    spec.loader = _Loader(spec.loader)
                return spec
        return None


def install() -> bool:
    """Install the guard in this interpreter (again is nothing). True when it is installed."""
    if _state["installed"]:
        return True
    try:
        if GUARDED_MODULE in sys.modules:
            kernel = sys.modules[GUARDED_MODULE]
            original = getattr(kernel, "processes_named", None)
            _guard_kernel(kernel)
            # A module that took the read by name before the guard came takes the guarded one now.
            pairing = sys.modules.get("codex_auto_resume.codex.pairing")
            if pairing is not None and original is not None and getattr(pairing, "processes_named", None) is original:
                pairing.processes_named = kernel.processes_named
        if not any(isinstance(finder, _Finder) for finder in sys.meta_path):
            sys.meta_path.insert(0, _Finder())
        _state["installed"] = True
    except Exception:
        return False
    return True
