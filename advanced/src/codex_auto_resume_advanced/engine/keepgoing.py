# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""Keep going (v0.6.14-beta.2, the plan's item 6): a conversation a person picked keeps going after a turn that ended
well, up to the count they chose, and stops on no progress, a finished plan or an active goal - at P8 and P2.

The standard edition recovers failures alone: a turn Codex completed well is never continued (A13). With this on, a
person picks conversations in the Dashboard (control/keepgoing.py, the bridge alone - never MCP) with a count of 1 to
10, and at P8, at most once a minute, each one's latest turn is looked at: completed with no error, the conversation
idle at least IDLE_FOR since, and not continued already - then one continuation of the edition's own words, "Carry on
with the next step of the plan." (A26), a P2 CONTINUATION core sends only while that turn is the latest. Counted at
SENT (runtime.py).

It stops, said why (state/continuations.py keep_going): no_progress - the turn left no kind of item that counts as
progress (core's codex/values.PROGRESS_ITEM_TYPES, Codex's own loop guard does the same); plan_done - every step of
the newest plan is completed, read as statuses alone (codex/turns.plan_statuses, B9 departed); plan_unreadable - a
plan item there whose steps cannot be read (fail closed); count_spent; goal_active - a goal Codex keeps going itself;
failed - a failed turn is core's ordinary recovery; by_person - an interrupted turn, or the Dashboard's Stop; turned
off, every row; a conversation switched off, its row. Until MK passes on the Codex in force, no more than
UNMEASURED_COUNT are sent (the narrowed route). The ledger's fifteen minutes and five a day still pace it.
"""
from __future__ import annotations

from codex_auto_resume.codex.values import PROGRESS_ITEM_TYPES
from codex_auto_resume.domain.plug import DEFER

from .. import statement
from ..codex import inuse
from ..codex.goals import Goals
from ..codex.turns import Turns, TurnsUnavailable
from ..vocabulary import ContinuationKind, GoalStatus, KeepReason, KeepState, Measurement, RecordState
from .continued import answer_key, handed, words_pass

CAPABILITY = "keep_going"
WORDS_KEY = "continue.keep_going"
IDLE_FOR = 60
LOOK_EVERY = 60
# Until MK - a throwaway conversation with a plan, its steps' statuses read - passes for the Codex in force.
UNMEASURED_COUNT = 3


def allowed(count, measured) -> int:
    """How many continuations a conversation armed with `count` may have now: its count, or no more than
    UNMEASURED_COUNT until MK passed."""
    return count if measured else min(count, UNMEASURED_COUNT)


class _Errand:
    __slots__ = ("code", "view")

    def __init__(self, code, view):
        self.code, self.view = code, view

    def run(self, guard):
        return self.code.look(self.view)


class KeepGoing:
    """The capability's code: its hooks at P8 and P2. `bind` gives it its view of the state (state.Scoped)."""
    __slots__ = ("paths", "_scoped", "_home", "_looked")

    def __init__(self, paths, *, home=None):
        self.paths = paths
        self._scoped = None
        self._home = home
        self._looked = None

    def bind(self, scoped):
        self._scoped = scoped

    def _codex_home(self):
        return self._home if self._home is not None else inuse.home(self.paths)

    # ------------------------------------------------------------------ P8
    def tick(self, view):
        scoped = self._scoped
        if scoped is None:
            return DEFER
        try:
            rows = [row for row in scoped.continuations.kept() if row["state"] == KeepState.ON]
        except Exception:
            return DEFER
        now = scoped.now()
        if not rows or (self._looked is not None and 0 <= now - self._looked < LOOK_EVERY):
            return DEFER
        return _Errand(self, view)

    def look(self, view):
        scoped = self._scoped
        handle = scoped.continuations
        if not handle.on():
            return None
        now = scoped.now()
        self._looked = now
        home = self._codex_home()
        turns = Turns(home)
        measured = scoped.passed(Measurement.MK)
        for row in handle.kept():
            if row["state"] != KeepState.ON:
                continue
            try:
                self._one(handle, view, home, turns, row, now, measured)
            except Exception:
                continue                                 # looked at again in a minute
        return None

    def _one(self, handle, view, home, turns, row, now, measured) -> None:
        thread = row["thread_id"]
        if view.thread_enabled(thread) is False:
            return self._stop(handle, thread, KeepReason.CONVERSATION_OFF)
        try:
            turn = turns.latest(thread)
        except TurnsUnavailable:
            return None
        if turn is None or turn.status in ("inProgress", "other"):
            return None
        if turn.status == "interrupted":
            return self._stop(handle, thread, KeepReason.BY_PERSON)
        if turn.status == "failed" or turn.errored:
            return self._stop(handle, thread, KeepReason.FAILED)
        if turn.completed_at is None or now - turn.completed_at < IDLE_FOR:
            return None
        key = answer_key(CAPABILITY, thread, turn.turn_id)
        if handle.get(key) is not None:
            return None                                  # this turn is continued already
        if not any(turn.kinds.get(kind, 0) for kind in PROGRESS_ITEM_TYPES):
            return self._stop(handle, thread, KeepReason.NO_PROGRESS)
        goal = Goals(home).read(thread)                  # unreadable raises: nothing this look
        if goal is not None and goal.status == GoalStatus.ACTIVE:
            return self._stop(handle, thread, KeepReason.GOAL_ACTIVE)
        try:
            statuses = turns.plan_statuses(thread)
        except TurnsUnavailable:
            return self._stop(handle, thread, KeepReason.PLAN_UNREADABLE)
        if statuses is not None and all(status == "completed" for status in statuses):
            return self._stop(handle, thread, KeepReason.PLAN_DONE)
        if row["used"] >= allowed(row["count"], measured):
            return self._stop(handle, thread, KeepReason.COUNT_SPENT)
        words = statement.CATALOGS.text(WORDS_KEY)
        if words_pass(words) and handle.add(key, ContinuationKind.KEEP_GOING, thread, words, ordinal=turn.ordinal):
            self._count("found")
        return None

    def _stop(self, handle, thread, reason) -> None:
        if handle.stop_kept(reason, thread_id=thread):
            self._count("stopped")

    # ------------------------------------------------------------------ P2
    def records(self, view):
        scoped = self._scoped
        if scoped is None:
            return DEFER
        try:
            rows = scoped.continuations.mine()
        except Exception:
            return DEFER
        found = [handed(row) for row in rows if row["record_state"] == RecordState.WAITING]
        return [record for record in found if record is not None] or DEFER

    def _count(self, code) -> None:
        try:
            self._scoped.count(code)
        except Exception:
            pass


def make(paths) -> KeepGoing:
    """The capability's factory (registry.CapabilityDef.make): its code for one installation."""
    return KeepGoing(paths)
