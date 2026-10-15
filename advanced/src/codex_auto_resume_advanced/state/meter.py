# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""The usage meter's last reading (version 5, v0.6.16-beta.3, issue #29).

    meter   one row for each usage window the meter last read - a bucket and a length in minutes - with how
            full it was, when it resets (Codex's whole seconds, or none), when it was read, and the reset each
            stage last acted for: the warning shown (warned_reset_at, warned_at) and the pause held
            (paused_reset_at). So each stage acts once for a window, across restarts.

Numbers only, as core keeps a usage reading (B10): never an account, a plan or a credit. The rows are the meter's
alone to write, while it is on; turning it off - by any move off, or every advanced feature off - deletes them
with it (state/arming.py), so what is held near a limit never outlives the meter.
"""
from __future__ import annotations

import math

from .schema import BUCKETS
from .session import StateError

# The meter's capability, whose move off deletes the rows.
METER = "usage_meter"
# The longest window a row may name, in minutes (the schema's CHECK): a week and ten times over.
MAX_MINUTES = 100800
_COLUMNS = ("bucket", "minutes", "used_percent", "reset_at", "read_at", "warned_reset_at", "warned_at",
            "paused_reset_at")


def _family(bucket, minutes):
    if bucket not in BUCKETS or type(minutes) is not int or not 1 <= minutes <= MAX_MINUTES:
        raise StateError("invalid window")
    return bucket, minutes


def _reset(value):
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise StateError("invalid reset time")
    return value


class MeterMixin:
    def meter(self) -> dict:
        """{(bucket, minutes): row} of the meter's last reading; empty with no file or no reading."""
        with self._read() as connection:
            if connection is None:
                return {}
            rows = connection.execute("SELECT %s FROM meter" % ", ".join(_COLUMNS)).fetchall()
        return {(row["bucket"], row["minutes"]): dict(row) for row in rows}

    def save_meter(self, windows, *, at=None) -> int:
        """One successful reading written: each window of `windows` (core's kept form - bucket, window_minutes,
        used_percent, reset_at) upserted, the stages' marks kept; a window the reading no longer shows is
        deleted. How many rows it holds after."""
        now = self._now(at)
        kept = {}
        for window in windows or ():
            if not isinstance(window, dict):
                continue
            used = window.get("used_percent")
            if type(used) not in (int, float) or not math.isfinite(used) or used < 0:
                continue
            try:
                family = _family(window.get("bucket"), window.get("window_minutes"))
                reset_at = _reset(window.get("reset_at"))
            except StateError:
                continue
            if family not in kept or used > kept[family][0]:
                kept[family] = (float(used), reset_at)
        with self._transaction() as connection:
            for (bucket, minutes), (used, reset_at) in kept.items():
                connection.execute(
                    "INSERT INTO meter (bucket, minutes, used_percent, reset_at, read_at) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(bucket, minutes) DO UPDATE SET used_percent=excluded.used_percent, "
                    "reset_at=excluded.reset_at, read_at=excluded.read_at", (bucket, minutes, used, reset_at, now))
            for bucket, minutes in [tuple(row) for row in connection.execute("SELECT bucket, minutes FROM meter")]:
                if (bucket, minutes) not in kept:
                    connection.execute("DELETE FROM meter WHERE bucket=? AND minutes=?", (bucket, minutes))
            return connection.execute("SELECT count(*) FROM meter").fetchone()[0]

    def mark_meter(self, bucket, minutes, *, warned_reset_at=None, paused_reset_at=None, clear_pause=False,
                   at=None) -> bool:
        """A stage's mark on one window's row: the reset a warning was shown for (and when), the reset a pause
        holds for, or the pause let go (`clear_pause`). Whether a row was there to mark."""
        bucket, minutes = _family(bucket, minutes)
        now = self._now(at)
        sets, values = [], []
        if warned_reset_at is not None:
            sets += ["warned_reset_at=?", "warned_at=?"]
            values += [_reset(warned_reset_at), now]
        if paused_reset_at is not None:
            sets.append("paused_reset_at=?")
            values.append(_reset(paused_reset_at))
        elif clear_pause:
            sets.append("paused_reset_at=NULL")
        if not sets:
            raise StateError("nothing to mark")
        with self._transaction(create=False) as connection:
            if connection is None:
                return False
            return connection.execute("UPDATE meter SET %s WHERE bucket=? AND minutes=?" % ", ".join(sets),
                                      (*values, bucket, minutes)).rowcount == 1


def _not_the_meter(*_arguments, **_keywords):
    raise StateError("only the meter writes a reading")


def end_meter(connection) -> None:
    """Every row of the meter deleted, in the caller's transaction: the meter turned off (state/arming.py)."""
    connection.execute("DELETE FROM meter")


class MeterHandle:
    """What a capability's code is given of the meter (state.Scoped's `meter`): the reading, for any capability -
    the wrap-up and the pause read it - and writes only for the meter and the pause, and only while the runtime has
    that capability on. Held in a closure, as the Scoped view is."""
    __slots__ = ("capability", "_calls")
    WRITERS = frozenset({METER, "usage_pause"})

    def __init__(self, state, capability, on):
        self.capability = capability

        def writing(call):
            def written(*arguments, **keywords):
                if capability not in MeterHandle.WRITERS or on is None or on() is not True:
                    raise StateError("the capability may not write the meter now")
                return call(*arguments, **keywords)
            return written
        self._calls = {
            "on": lambda: on is not None and on() is True,
            "now": lambda: state.clock(),
            "rows": state.meter,
            # Only the meter writes a reading; the pause only marks the window it holds for.
            "save": writing(state.save_meter if capability == METER else _not_the_meter),
            "mark": writing(state.mark_meter),
        }

    def __getattr__(self, name):
        calls = object.__getattribute__(self, "_calls")
        if name in calls:
            return calls[name]
        raise AttributeError(name)
