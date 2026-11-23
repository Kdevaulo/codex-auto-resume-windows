"""The Codex app's process layout, counted by role, and the watcher's look when it changes (v0.6.26).

Update resilience #6 and #11 (the owner's approval of 2026-11-22). Every Codex update that left recovery waiting
silently moved the app's processes: 26.930 ran a second engine beside its server, an update rebuilt the engine into a
new bin folder, 26.1111 (#58) ran it from the app's package, 26.1117 (#67) under a helper. `snapshot` counts one look's
processes by role - mains, the package's helpers, engines under the main, under a helper or elsewhere, whether the
server was paired and held Codex's databases - and names the catalogued shape it is (`SHAPES`, the shapes
tests/test_codex_layouts.py holds the pairing to), or none. No path, no pid and no command line is kept: counts, the
app's package version (the digits Windows names its folder with) and fixed words.

`Watch` is the watcher's side: at the first look and whenever the engine's file or the app's package version changes it
says the layout in the log - and that it is one this version was not tested on, where so - and keeps it, with the last
look that paired, in config/codex-layout.json (`read`). That file outlives this product's own update: the first looks
after a new version of it pair nothing where the version before paired say so (`unpaired_after_update`) until one
pairs. It decides nothing: no send, no wait and no reason comes of it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time

from . import pairing

FORMAT = 1
# The process shapes this version is tested on (tests/test_codex_layouts.py), by (mains, engines under the main,
# engines under a helper): one child (26.915, 26.1007, 26.1111's package engine, an engine rebuilt into a new folder),
# two children (26.930: app-server and exec-server), the server under a helper (26.1117, beside the exec-server or not),
# the app open with no engine yet (starting, or its server restarting), and the app closed.
SHAPES = {(1, 1, 0): "single_child", (1, 2, 0): "two_children", (1, 0, 1): "helper_parented",
          (1, 1, 1): "helper_parented", (1, 0, 0): "starting", (0, 0, 0): "closed"}
# Review K8: "starting" is a tested layout only for a while. An app whose engine is no longer a codex.exe under it - one
# an update renamed, which the inventory does not list - looks "starting" for ever; past this many seconds of looks
# that all found it so, it is a layout this version has not been tested on.
STARTING_SECONDS = 600.0
_VERSION = re.compile(r"OpenAI\.Codex_([0-9][0-9.]{0,31})_", re.I)
_WORD = re.compile(r"[\x20-\x7e]{1,64}\Z")


def _engine(row) -> bool:
    return pairing.engine_row(row)


def snapshot(rows, codex_exe=None, seen=None) -> dict:
    """One look's processes counted by role, content-free. `seen` is what desktop_pair told its caller: a look that
    paired has `server_holds`. Never raises: rows that cannot be read count as nothing."""
    found = {"mains": 0, "helpers": 0, "renamed_main": False, "app_version": None, "engines_under_main": 0,
             "engines_under_helper": 0, "engines_elsewhere": 0, "engine_in_package": False,
             "paired": isinstance(seen, dict) and "server_holds" in seen,
             "server_holds": seen.get("server_holds") if isinstance(seen, dict) else None, "shape": None}
    try:
        rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        mains = pairing.app_mains(rows)
        found["mains"] = len(mains)
        main = mains[0] if len(mains) == 1 else None
        # Fourth round A1: a package program of a folder below `app` counts as a helper only under the main.
        found["helpers"] = sum(1 for row in rows if pairing.app_process(row) and not any(row is each for each in mains)
                               and (pairing._main_place(row["path"])
                                    or (main is not None and pairing.under_app(rows, row, main["pid"]))))
        if main is not None:
            found["renamed_main"] = not pairing._package_app(main["path"])
            version = _VERSION.search(main["path"])
            found["app_version"] = version.group(1).rstrip(".") if version else None
        for row in rows:
            if not _engine(row):
                continue
            if main is not None and row.get("parent") == main["pid"] and pairing.under_app(rows, row, main["pid"]):
                found["engines_under_main"] += 1
            elif main is not None and pairing.under_app(rows, row, main["pid"]):
                found["engines_under_helper"] += 1
            else:
                found["engines_elsewhere"] += 1
        found["engine_in_package"] = codex_exe is not None and pairing._package_file(str(codex_exe))
    except Exception:
        pass
    found["shape"] = SHAPES.get((min(found["mains"], 2), found["engines_under_main"], found["engines_under_helper"]))
    return found


def catalogued(found) -> bool:
    """Whether a snapshot is one of the shapes this version is tested on."""
    return isinstance(found, dict) and found.get("shape") in SHAPES.values()


def _word(value):
    return value if isinstance(value, str) and _WORD.match(value) else None


def read(path) -> dict | None:
    """What the watcher last kept of the layout (config/codex-layout.json), or None where there is none or it cannot be
    read: {"format", "code_version", "engine_version", "app_version", "layout", "catalogued", "last_good",
    "updated_from", "unpaired_after_update"} - `last_good` the last look that paired, with the version of this product,
    of the engine and of the app it was made on."""
    try:
        found = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return found if isinstance(found, dict) and found.get("format") == FORMAT else None


def _write(path, value) -> None:
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name("%s.%d.tmp" % (target.stem, os.getpid()))      # config.owned_state_files
        temporary.write_text(json.dumps(value, sort_keys=True, allow_nan=False), encoding="utf-8")
        os.replace(temporary, target)
    except (OSError, ValueError):
        pass                                        # said in the log; written again at the next change


class Watch:
    """The watcher's look at the layout: `look` at every tick with the backend's last snapshot; it writes and says
    something only when the engine's file, the app's package version, the pairing or the after-update fact changes."""

    def __init__(self, path, code_version, log=None, clock=None):
        self.path, self.code_version, self.log = path, _word(code_version), log or (lambda *_: None)
        self.clock = clock or time.monotonic
        self._starting_since = None         # the first of the looks running that found the app "starting"
        self._untested = None               # whether the last look was one of a layout not tested on
        self._found, self._found_at = None, None    # the last snapshot looked at, and when it was first
        before = read(path) or {}
        self._kept = before
        self._key = None
        previous = _word(before.get("code_version"))
        # The version this product was updated from, until a look pairs: kept in the file too, so a watcher started
        # again before then still knows it.
        self.updated_from = (previous if previous and previous != self.code_version
                             else _word(before.get("updated_from")))

    def look(self, found, *, stamp=None, engine_version=None) -> dict | None:
        """Take one look's snapshot; returns what is kept now, or None where there was nothing to look at."""
        if not isinstance(found, dict):
            return None
        app_open = found.get("mains", 0) > 0 or found.get("helpers", 0) > 0
        # Audit-reachability I1: the watcher looks at the backend's last snapshot every tick, and only a record the
        # engine checks makes a new one. A snapshot looked at again is no new look: it is judged as at its first look,
        # so one old "starting" look never runs out the K8 count.
        if found is not self._found:
            self._found, self._found_at = found, self.clock()
        at = self._found_at
        if found.get("shape") == "starting":
            if self._starting_since is None or at < self._starting_since:
                self._starting_since = at
        else:
            self._starting_since = None
        tested = catalogued(found) and not (self._starting_since is not None
                                            and at - self._starting_since >= STARTING_SECONDS)
        untested = app_open and not tested
        key = (stamp, found.get("app_version"))
        changed, said = key != self._key, self._untested
        self._untested = untested
        if changed:
            self._key = key
            self.log("Codex layout: %d main, %d helper, engines %d under the main, %d under a helper, %d elsewhere; "
                     "%s" % (found.get("mains", 0), found.get("helpers", 0), found.get("engines_under_main", 0),
                             found.get("engines_under_helper", 0), found.get("engines_elsewhere", 0),
                             "paired" if found.get("paired") else "not paired"))
        if untested and (changed or said is False):
            self.log("Codex %s runs in a layout this version has not been tested on"
                     % (found.get("app_version") or "(version unknown)"))
        kept = dict(self._kept)
        last_good = kept.get("last_good") if isinstance(kept.get("last_good"), dict) else None
        if found.get("paired"):
            self.updated_from = None
            last_good = {"code_version": self.code_version, "engine_version": _word(engine_version),
                         "app_version": found.get("app_version"),
                         "layout": {name: value for name, value in found.items() if name != "server_holds"}}
        unpaired = bool(self.updated_from and app_open and not found.get("paired") and last_good)
        if unpaired and not kept.get("unpaired_after_update"):
            self.log("the first looks since this product was updated from %s pair no Codex server, where that version "
                     "paired one" % self.updated_from)
        now = {"format": FORMAT, "code_version": self.code_version, "engine_version": _word(engine_version),
               "app_version": found.get("app_version"),
               "layout": {name: value for name, value in found.items() if name != "server_holds"},
               "catalogued": tested,
               "last_good": last_good, "updated_from": self.updated_from, "unpaired_after_update": unpaired}
        if now != self._kept:
            self._kept = now
            _write(self.path, now)
        return dict(now)
