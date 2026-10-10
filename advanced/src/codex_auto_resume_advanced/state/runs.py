# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""What the edition keeps of a headless turn while it runs, and of Codex's settings it changed (version 5,
v0.6.15-beta.3).

    headless_runs  one row for each turn run here, keyed by the interruption it continues: which capability ran it,
                   in which conversation, when it began and by when its cap ends it, a person's Stop asked from the
                   Dashboard's bridge, and how it ended (RunEnd) - written only by the capability's P8 tick in the
                   watcher, from what the follower told it (codex/headless.py), and by a Stop; read by the Dashboard
    codex_config   one row for each of Codex's own retry settings the edition wrote (codex_retry_settings): whether
                   it had a value before and which, the value written, and how it ended (ConfigOutcome) - so it is
                   put back as it was, and one the person changed since is left theirs

Neither holds a word of a conversation, a model's name or a path.
"""
from __future__ import annotations

from ..vocabulary import ConfigOutcome, RunEnd
from .schema import CONFIG_KEYS, HEADLESS_CAPABILITIES
from .session import StateError, _key, _thread, _timestamp, _word


def _capability(value):
    if value not in HEADLESS_CAPABILITIES:
        raise StateError("invalid capability")
    return value


def _value(value, name):
    if value is not None and (type(value) is not int or not 0 <= value <= 1000):
        raise StateError("invalid %s" % name)
    return value


_RUN_COLUMNS = ("interruption_id", "capability", "thread_id", "started_at", "ends_by", "stop_requested_at",
                "ended_at", "end")
_CONFIG_COLUMNS = ("key_path", "prior_present", "prior_value", "written_value", "written_at", "restored_at",
                   "outcome")


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

    def prune_runs(self, before) -> int:
        """Ended runs older than `before`, gone."""
        _timestamp(before, "before")
        with self._transaction(create=False) as connection:
            if connection is None:
                return 0
            return connection.execute("DELETE FROM headless_runs WHERE end IS NOT NULL AND ended_at < ?",
                                      (before,)).rowcount

    # ------------------------------------------------------------------ Codex's settings changed
    def config_rows(self) -> dict:
        """{key_path: row} for each of Codex's settings the edition wrote."""
        with self._read() as connection:
            rows = [] if connection is None else connection.execute(
                "SELECT %s FROM codex_config" % ", ".join(_CONFIG_COLUMNS)).fetchall()
        return {row[0]: dict(zip(_CONFIG_COLUMNS, row)) for row in rows}

    def config_written(self, key_path, *, prior_present, prior_value, written_value, at=None) -> None:
        """A setting written: what it was before (present, and its value) and what was written - kept until it is put
        back. A row already there keeps the prior it first saw: writing again never forgets what was the person's."""
        if key_path not in CONFIG_KEYS or type(prior_present) is not bool:
            raise StateError("invalid setting")
        _value(prior_value, "prior_value")
        _value(written_value, "written_value")
        now = self._now(at)
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO codex_config (key_path, prior_present, prior_value, written_value, written_at, outcome) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(key_path) DO UPDATE SET written_value=excluded.written_value, "
                "written_at=excluded.written_at, restored_at=NULL, outcome=excluded.outcome",
                (key_path, int(prior_present), prior_value, written_value, now, ConfigOutcome.APPLIED))

    def config_ended(self, key_path, outcome, *, at=None) -> None:
        """A setting put back (restored), left as the person set it (left_theirs) or refused by Codex (refused)."""
        if key_path not in CONFIG_KEYS:
            raise StateError("invalid setting")
        outcome = _word(outcome, ConfigOutcome, "outcome")
        now = self._now(at)
        with self._transaction() as connection:
            connection.execute("UPDATE codex_config SET restored_at=?, outcome=? WHERE key_path=?",
                               (now, outcome, key_path))


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
        }

    def __getattr__(self, name):
        calls = object.__getattribute__(self, "_calls")
        if name in calls:
            return calls[name]
        raise AttributeError(name)


class ConfigHandle:
    """Codex's own settings the edition wrote, as codex_retry_settings' code is given them (state.Scoped's `config`):
    read, a write recorded, an end recorded - whatever the capability stands at, since putting a value back is what
    turning it off asks for."""
    __slots__ = ("_calls",)

    def __init__(self, state):
        self._calls = {"config_rows": state.config_rows, "config_written": state.config_written,
                       "config_ended": state.config_ended}

    def __getattr__(self, name):
        calls = object.__getattribute__(self, "_calls")
        if name in calls:
            return calls[name]
        raise AttributeError(name)
