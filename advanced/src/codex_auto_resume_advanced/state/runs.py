# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""What the edition keeps of a headless turn while it runs (stage 4's version, v0.6.16-beta.4).

    headless_runs  one row for each turn run here, keyed by the interruption it continues: which capability ran it,
                   in which conversation, when it began and by when its cap ends it, a person's Stop asked from the
                   Dashboard's bridge, and how it ended (RunEnd) - written only by the capability's P8 tick in the
                   watcher, from what the follower told it (codex/headless.py), and by a Stop; read by the Dashboard

It holds no word of a conversation, no model's name and no path.
"""
from __future__ import annotations

from ..vocabulary import RunEnd
from .schema import HEADLESS_CAPABILITIES
from .session import StateError, _key, _thread, _timestamp, _word


def _capability(value):
    if value not in HEADLESS_CAPABILITIES:
        raise StateError("invalid capability")
    return value


_RUN_COLUMNS = ("interruption_id", "capability", "thread_id", "started_at", "ends_by", "stop_requested_at",
                "ended_at", "end")


class RunsMixin:
    # ------------------------------------------------------------------ headless runs
    def run_started(self, key, capability, thread_id, *, started_at, ends_by) -> None:
        """A run the follower holds now: its row written, or written again."""
        _key(key, "run key")
        _capability(capability)
        _thread(thread_id)
        started, ends = _timestamp(started_at, "started_at"), _timestamp(ends_by, "ends_by")
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO headless_runs (interruption_id, capability, thread_id, started_at, ends_by) VALUES "
                "(?,?,?,?,?) ON CONFLICT(interruption_id) DO UPDATE SET capability=excluded.capability, "
                "thread_id=excluded.thread_id, started_at=excluded.started_at, ends_by=excluded.ends_by, "
                "ended_at=NULL, end=NULL", (key, capability, thread_id, started, ends))

    def run_ended(self, key, end, *, at=None) -> bool:
        """A run's end, as the follower told it; False where there was no such run."""
        _key(key, "run key")
        end = _word(end, RunEnd, "end")
        now = self._now(at)
        with self._transaction() as connection:
            return connection.execute("UPDATE headless_runs SET ended_at=?, end=? WHERE interruption_id=? AND "
                                      "end IS NULL", (now, end, key)).rowcount == 1

    def run_stop(self, key, *, at=None) -> bool:
        """A person's Stop of the run of `key`, asked from the Dashboard: False where none is running."""
        _key(key, "run key")
        now = self._now(at)
        with self._transaction() as connection:
            return connection.execute("UPDATE headless_runs SET stop_requested_at=? WHERE interruption_id=? AND "
                                      "end IS NULL", (now, key)).rowcount == 1

    def runs(self, *, live=True, limit=20) -> list:
        """The runs, the newest first: only those still going with `live`."""
        with self._read() as connection:
            if connection is None:
                return []
            rows = connection.execute(
                "SELECT %s FROM headless_runs %s ORDER BY started_at DESC LIMIT ?"
                % (", ".join(_RUN_COLUMNS), "WHERE end IS NULL" if live else ""), (int(limit),)).fetchall()
        return [dict(zip(_RUN_COLUMNS, row)) for row in rows]

    def prune_runs(self, before, *, capability=None) -> int:
        """Ended runs older than `before` - only `capability`'s, where given - gone."""
        _timestamp(before, "before")
        if capability is not None:
            _capability(capability)
        with self._transaction(create=False) as connection:
            if connection is None:
                return 0
            return connection.execute("DELETE FROM headless_runs WHERE end IS NOT NULL AND ended_at < ? AND "
                                      "(? IS NULL OR capability = ?)", (before, capability, capability)).rowcount


class RunsHandle:
    """What a headless capability's code is given of the state (state.Scoped's `runs`): its own runs - reads always,
    writes only while the runtime has it on, as the other handles."""
    __slots__ = ("capability", "_calls")

    def __init__(self, state, capability, on):
        self.capability = capability

        def is_on():
            return on is not None and on() is True

        self._calls = {
            "on": is_on,
            "live": lambda: [row for row in state.runs(live=True) if row["capability"] == capability],
            "started": lambda key, thread_id, *, started_at, ends_by: state.run_started(
                key, capability, thread_id, started_at=started_at, ends_by=ends_by),
            # An end is written whatever the capability stands at: the run happened.
            "ended": lambda key, end: state.run_ended(key, end),
            # Ended rows older than `before` gone, whatever the capability stands at (engine/headless.follow_up).
            "prune": lambda before: state.prune_runs(before, capability=capability),
        }

    def __getattr__(self, name):
        calls = object.__getattribute__(self, "_calls")
        if name in calls:
            return calls[name]
        raise AttributeError(name)
