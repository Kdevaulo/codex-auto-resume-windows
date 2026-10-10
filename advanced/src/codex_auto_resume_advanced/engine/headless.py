# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""Headless run: a conversation nothing holds is run here while Codex is closed (v0.6.15-beta.3, P16 and P8).

The standard edition waits for the Codex app to hold a conversation before anything is sent there (A11), and only
through `codex queue` (A2). With this on, core asks P16 for a record of a default home's conversation where the app is
not running and nothing holds the conversation's writer lock (core's engine/delivery.py, `holder="none", app=False`),
and this answers a route (codex/headless.HeadlessRun): core decides the words, claims - this capability paying one unit
there - makes its pre-send look, and calls the route once inside its launch guard. The route runs one turn on our own
app server with the settings Codex saved for the conversation, declines every approval the turn asks, refuses a
conversation saved with full access or with another reviewer of approvals before anything starts, and lets go.

It answers nothing - DEFER, the standard edition's wait - unless the record was asked with no app and no holder, it is
not one this edition's compaction continues (a full context window: compact_continue's), and no run is live in this
watcher (one at a time, R3). The turn is capped at the person's Hours (1 to 6, 1 by default); a person's Stop on
Pending's row (advanced-headless-stop, the Dashboard's bridge alone - never MCP) interrupts it, and so does the Codex
app starting (Q3: at once, until a measurement shows what the app does then).

At P8 it does the bookkeeping the route's own thread may not: it writes the live run's row (state/runs.py) for the
Dashboard, reads a Stop asked from the bridge and hands it on, and journals how each run ended (its codes). Until M6B -
a headless turn on the thread's own saved settings - passes for the Codex in force, its statement carries the
UNMEASURED warning (arming.warnings_for).
"""
from __future__ import annotations

import time

from codex_auto_resume.domain import ids
from codex_auto_resume.domain.plug import DEFER

from ..codex import headless, inuse
from ..vocabulary import OptionKey, RunEnd

CAPABILITY = "headless_run"
# A full context window is compact_continue's to continue (engine/compact.py), never this one's.
TERMINAL_INVALID = "terminal_invalid"
HOURS = (1, 2, 3, 4, 5, 6)
DEFAULT_HOURS = 1
HOUR = 3600
# How long an ended run's row is kept for the Dashboard to show how it ended.
KEEP_ENDED = 86400


def unheld(record) -> bool:
    """Whether core asked P16 for `record` with the Codex app closed and nothing holding its conversation (core's
    engine/delivery.py) - never in the watch of a continuation queued for opening, which hands neither."""
    return isinstance(record, dict) and record.get("app") is False and record.get("holder") == "none"


def _app_running(paths):
    """A look at whether the Codex app has started, on one backend made once (core's pairing reads the processes)."""
    made = []

    def running() -> bool:
        if not made:
            made.append(inuse.backend(paths))
        return made[0].app_identity() is not None
    return running


class HeadlessRunCode:
    """The capability's code: its hooks at P16 and P8. `bind` gives it its view of the state (state.Scoped).

    Its seams are the tests': `session` opens the app-server sessions (None: live ones against the Codex the watcher
    drives, codex/headless.live_session); `follower` is the process's one (codex/headless.FOLLOWER); `app_running`
    the look at the Codex app (None: core's pairing, through codex/inuse.py)."""
    __slots__ = ("paths", "_scoped", "_open", "follower", "_app", "_routes", "clock")

    def __init__(self, paths, *, session=None, follower=None, app_running=None, clock=time.time):
        self.paths, self._scoped = paths, None
        self._open = session if session is not None else headless.live_session(paths)
        self.follower = follower or headless.FOLLOWER
        self._app = app_running if app_running is not None else _app_running(paths)
        self._routes = {}
        self.clock = clock

    def bind(self, scoped):
        self._scoped = scoped

    def _hours(self) -> int:
        try:
            hours = self._scoped.options().get(OptionKey.CEILING_HOURS, DEFAULT_HOURS)
        except Exception:
            hours = DEFAULT_HOURS
        return hours if hours in HOURS else DEFAULT_HOURS

    def unloaded(self, record):
        """P16: the route, for a record asked with no app and no holder, of a kind this runs, while no run is live."""
        key = record.get("interruption_id") if isinstance(record, dict) else None
        if (not unheld(record) or not ids.is_interruption_id(key) or self._scoped is None
                or record.get("category") == TERMINAL_INVALID or self.follower.live() is not None):
            return DEFER
        route = headless.HeadlessRun(CAPABILITY, key=key, session=self._open, follower=self.follower,
                                     seconds=self._hours() * HOUR, app_running=self._app)
        self._routes = {key: route}
        return route

    def tick(self, view):
        """P8: the live run's row written, a Stop from the bridge handed on, and how each run ended journalled -
        what the route's own thread may not do. Never an errand: nothing here asks Codex anything."""
        scoped = self._scoped
        if scoped is None:
            return DEFER
        runs = scoped.runs
        live = self.follower.live()
        try:
            if live is not None and live["capability"] == CAPABILITY:
                stored = {row["interruption_id"]: row for row in runs.live()}
                row = stored.get(live["key"])
                if row is None:
                    runs.started(live["key"], live["thread_id"], started_at=live["started_at"],
                                 ends_by=live["ends_by"])
                elif row.get("stop_requested_at") is not None:
                    self.follower.stop(live["key"], RunEnd.INTERRUPTED)
            for refused in [route for route in self._routes.values() if route.refused is not None]:
                scoped.count(str(refused.refused))
                refused.refused = None
            for ended in self.follower.drain(CAPABILITY):
                runs.ended(ended["key"], ended["end"])
                scoped.count(str(ended["end"]))
            for row in runs.live():
                if live is None or row["interruption_id"] != live["key"]:
                    runs.ended(row["interruption_id"], RunEnd.LOST)       # a run no thread follows any more
        except Exception:
            pass                                       # the next tick writes what this one could not
        return DEFER


def make(paths) -> HeadlessRunCode:
    """The capability's factory (registry.CapabilityDef.make): its code for one installation."""
    return HeadlessRunCode(paths)
