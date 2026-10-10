# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""What the edition keeps of its own continuations and of the conversations a person asked to keep going
(version 4, v0.6.14-beta.2).

    continuations  one row for each turn the edition answered or chose not to - a turn that ended with no reply
                   (empty_response), a subagent's stop (subagent_parent), a conversation kept going
                   (keep_going) - kept under what it answers (answer_id), so one turn is answered once. A row with a record is a
                   continuation core sends (P2's CONTINUATION, its record a row of `records`); one without is a
                   decision only (a goal left alone, a chain spent, a stop told in the parent's own words). Its
                   words, the catalog's, are kept only until it is sent
    keep_going     the conversations a person picked, each with how many continuations it may have and how many it
                   had, on until a stop says why

Every write is one transaction across a continuation's row and its record's, as the reset actions' are.
"""
from __future__ import annotations

from ..vocabulary import (ContinuationKind, ContinuationReason, KeepReason, KeepState, RecordState, Refusal)
from .choices import Refused
from .schema import CONTINUATION_CAPABILITIES
from .session import StateError, _key, _thread, _word

# A continuation's words at most: P2's CONTINUATION (core's continuation.CONTINUATION_LIMIT).
CONTINUATION_WORDS = 2000
# How many continuations a person may let one conversation have (keep_going's count).
KEEP_COUNTS = range(1, 11)
# How a record's move ends its continuation: the reason, and the record's state then.
_ENDS = {"delivered": (ContinuationReason.DELIVERED, RecordState.FINISHED),
         "unproven": (ContinuationReason.UNKNOWN, RecordState.FINISHED),
         "superseded": (ContinuationReason.SUPERSEDED, RecordState.FINISHED),
         "handed_over": (ContinuationReason.HANDED_OVER, RecordState.FINISHED),
         "withdrawn": (ContinuationReason.WITHDRAWN, RecordState.CANCELLED)}


def _capability(value):
    if value not in CONTINUATION_CAPABILITIES:
        raise StateError("invalid capability")
    return value


def _words(value):
    if not isinstance(value, str) or not 0 < len(value) <= CONTINUATION_WORDS:
        raise StateError("invalid words")
    return value


class ContinuationsMixin:
    # ------------------------------------------------------------------ continuations
    def add_continuation(self, key, capability, kind, thread_id, words, *, ordinal, chain=1, at=None) -> bool:
        """A continuation the edition will send for `key` - its record waiting, in the same transaction - or False
        where that turn was answered already (the key, which is also its record's id, is taken)."""
        _key(key, "continuation key")
        _capability(capability)
        kind = _word(kind, ContinuationKind, "kind")
        _thread(thread_id)
        _words(words)
        if type(ordinal) is not int or ordinal < 0 or type(chain) is not int or chain < 1:
            raise StateError("invalid continuation")
        now = self._now(at)
        with self._transaction() as connection:
            if connection.execute("SELECT 1 FROM continuations WHERE answer_id=? UNION SELECT 1 FROM records "
                                  "WHERE record_id=?", (key, key)).fetchone():
                return False
            connection.execute("INSERT INTO records (record_id, capability, thread_id, state, created_at, claims) "
                               "VALUES (?,?,?,?,?,0)", (key, capability, thread_id, RecordState.WAITING, now))
            connection.execute("INSERT INTO continuations (answer_id, capability, kind, thread_id, record_id, ordinal, "
                               "words, chain, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                               (key, capability, kind, thread_id, key, ordinal, words, chain, now))
            return True

    def note_continuation(self, key, capability, kind, thread_id, reason, *, ordinal=None, chain=0, at=None) -> bool:
        """A turn the edition decided not to answer, kept so it is decided once: no record, no words, finished with
        `reason` (a goal left alone, a chain spent, a stop told in the parent's own continuation). False if
        the key is taken."""
        _key(key, "continuation key")
        _capability(capability)
        kind = _word(kind, ContinuationKind, "kind")
        _thread(thread_id)
        reason = _word(reason, ContinuationReason, "reason")
        now = self._now(at)
        with self._transaction() as connection:
            if connection.execute("SELECT 1 FROM continuations WHERE answer_id=?", (key,)).fetchone():
                return False
            connection.execute("INSERT INTO continuations (answer_id, capability, kind, thread_id, ordinal, chain, "
                               "created_at, finished_at, reason) VALUES (?,?,?,?,?,?,?,?,?)",
                               (key, capability, kind, thread_id, ordinal, chain, now, now, reason))
            return True

    def continuation(self, key) -> dict | None:
        """One continuation's row, with its record's state (`record_state`, None for a decision only)."""
        _key(key, "continuation key")
        with self._read() as connection:
            row = None if connection is None else connection.execute(
                "SELECT n.*, c.state AS record_state, c.claimed_at AS claimed_at, c.queue_id AS queue_id, "
                "c.withdraw AS withdraw FROM continuations n LEFT JOIN records c ON c.record_id = n.record_id "
                "WHERE n.answer_id=?", (key,)).fetchone()
        return None if row is None else dict(row)

    def continuations(self, *, capability=None, thread_id=None, pending=True) -> list:
        """Continuations oldest first, each with its record's state and queue item: those whose record is still
        waiting or in flight (`pending`), every one (None), or the finished."""
        clauses, values = [], []
        if capability is not None:
            clauses.append("n.capability=?")
            values.append(_capability(capability))
        if thread_id is not None:
            clauses.append("n.thread_id=?")
            values.append(_thread(thread_id))
        if pending is True:
            clauses.append("n.finished_at IS NULL")
        elif pending is False:
            clauses.append("n.finished_at IS NOT NULL")
        with self._read() as connection:
            if connection is None:
                return []
            rows = connection.execute(
                "SELECT n.*, c.state AS record_state, c.claimed_at AS claimed_at, c.queue_id AS queue_id, "
                "c.withdraw AS withdraw FROM continuations n LEFT JOIN records c ON c.record_id = n.record_id%s "
                "ORDER BY n.created_at, n.answer_id" % (" WHERE " + " AND ".join(clauses) if clauses else ""),
                values).fetchall()
        return [dict(row) for row in rows]

    def last_continuation(self, thread_id, capability) -> dict | None:
        """The newest continuation of `capability` in `thread_id`, finished or not - what a chain counts on."""
        found = self.continuations(capability=capability, thread_id=thread_id, pending=None)
        return found[-1] if found else None

    def continuation_moved(self, record_id, move, *, at=None, queue_id=None) -> dict | None:
        """What core told of a continuation's record (P14), in one transaction across both rows: sent, its words go
        (and the queue item Codex took it as is kept); handed back or never started, it waits again with them;
        delivered, unproven, superseded, handed over or withdrawn, it ends with that reason. The capability and
        whether it turns it off (UNPROVEN), or None where it is no continuation of this file's."""
        _key(record_id, "record id")
        now = self._now(at)
        with self._transaction(create=False) as connection:
            if connection is None:
                return None
            row = connection.execute("SELECT n.capability, n.finished_at, c.state AS record_state FROM continuations n "
                                     "JOIN records c ON c.record_id = n.record_id WHERE n.record_id=?",
                                     (record_id,)).fetchone()
            if row is None or row["finished_at"] is not None:
                return None
            move = str(move)
            if move == "sent":
                connection.execute("UPDATE continuations SET words=NULL WHERE record_id=?", (record_id,))
                if isinstance(queue_id, str) and len(queue_id) == 36:
                    connection.execute("UPDATE records SET queue_id=? WHERE record_id=?", (queue_id, record_id))
            elif move in ("released", "not_started"):
                connection.execute("UPDATE records SET state=?, finished_at=NULL WHERE record_id=? AND state=?",
                                   (RecordState.WAITING, record_id, RecordState.IN_FLIGHT))
            elif move in _ENDS:
                reason, record_state = _ENDS[move]
                connection.execute("UPDATE continuations SET words=NULL, finished_at=?, reason=? WHERE record_id=?",
                                   (now, reason, record_id))
                connection.execute("UPDATE records SET state=?, finished_at=?, withdraw=0 WHERE record_id=?",
                                   (record_state, now, record_id))
            elif move == "withdraw_refused":
                connection.execute("UPDATE records SET withdraw=0 WHERE record_id=?", (record_id,))
            elif move != "waiting":
                return None
            return {"capability": row["capability"], "trip": move == "unproven"}

    def end_continuations(self, reason, *, capability=None, thread_id=None, at=None) -> int:
        """Every continuation still waiting to be sent - of `capability`, of `thread_id`, or all - ended with
        `reason` (turned off, the conversation switched off), its words gone and its record cancelled. One in
        flight is left to core's watch, which settles it. How many."""
        reason = _word(reason, ContinuationReason, "reason")
        clauses, values = ["n.finished_at IS NULL", "c.state=?"], [RecordState.WAITING]
        if capability is not None:
            clauses.append("n.capability=?")
            values.append(_capability(capability))
        if thread_id is not None:
            clauses.append("n.thread_id=?")
            values.append(_thread(thread_id))
        now = self._now(at)
        with self._transaction(create=False) as connection:
            if connection is None:
                return 0
            keys = [row[0] for row in connection.execute(
                "SELECT n.record_id FROM continuations n JOIN records c ON c.record_id = n.record_id WHERE "
                + " AND ".join(clauses), values).fetchall()]
            for key in keys:
                connection.execute("UPDATE continuations SET words=NULL, finished_at=?, reason=? WHERE record_id=?",
                                   (now, reason, key))
                connection.execute("UPDATE records SET state=?, finished_at=? WHERE record_id=?",
                                   (RecordState.CANCELLED, now, key))
            return len(keys)

    # ------------------------------------------------------------------ keep going
    def keep_going(self, thread_id=None):
        """One conversation's row (or None), or with no `thread_id` every row, the newest armed first."""
        with self._read() as connection:
            if connection is None:
                return None if thread_id is not None else []
            if thread_id is not None:
                row = connection.execute("SELECT * FROM keep_going WHERE thread_id=?", (_thread(thread_id),)).fetchone()
                return None if row is None else dict(row)
            return [dict(row) for row in connection.execute("SELECT * FROM keep_going ORDER BY armed_at DESC, "
                                                            "thread_id").fetchall()]

    def set_keep_going(self, thread_id, count, at=None) -> None:
        """A person's word that `thread_id` keeps going for `count` continuations (1 to 10): a row on, none used -
        made again where one was there. Refused (keep_count_invalid) for a count not on offer."""
        _thread(thread_id)
        if type(count) is not int or count not in KEEP_COUNTS:
            raise Refused(Refusal.KEEP_COUNT_INVALID)
        now = self._now(at)
        with self._transaction() as connection:
            connection.execute("INSERT OR REPLACE INTO keep_going (thread_id, count, used, armed_at, state) "
                               "VALUES (?,?,0,?,?)", (thread_id, count, now, KeepState.ON))

    def keep_going_used(self, thread_id, at=None) -> bool:
        """One more continuation counted (at SENT); the row is done (count_spent) once all are used. False if
        it is not on, or has none left."""
        _thread(thread_id)
        now = self._now(at)
        with self._transaction(create=False) as connection:
            if connection is None:
                return False
            row = connection.execute("SELECT count, used FROM keep_going WHERE thread_id=? AND state=?",
                                     (thread_id, KeepState.ON)).fetchone()
            if row is None or row["used"] >= row["count"]:
                return False
            used = row["used"] + 1
            spent = used >= row["count"]
            connection.execute("UPDATE keep_going SET used=?, state=?, reason=?, finished_at=? WHERE thread_id=?",
                               (used, KeepState.DONE if spent else KeepState.ON,
                                KeepReason.COUNT_SPENT if spent else None, now if spent else None, thread_id))
            return True

    def stop_keep_going(self, reason, *, thread_id=None, at=None) -> int:
        """Every conversation kept going - or `thread_id` alone - stopped with `reason`. How many."""
        reason = _word(reason, KeepReason, "reason")
        now = self._now(at)
        with self._transaction(create=False) as connection:
            if connection is None:
                return 0
            if thread_id is None:
                cursor = connection.execute("UPDATE keep_going SET state=?, reason=?, finished_at=? WHERE state=?",
                                            (KeepState.DONE, reason, now, KeepState.ON))
            else:
                cursor = connection.execute("UPDATE keep_going SET state=?, reason=?, finished_at=? WHERE state=? "
                                            "AND thread_id=?", (KeepState.DONE, reason, now, KeepState.ON,
                                                                _thread(thread_id)))
            return cursor.rowcount


def prune(connection, now, max_age, limit) -> None:
    """Continuations finished `max_age` ago and conversations kept going that stopped then, then the oldest
    finished beyond `limit` - never one still to be sent or in flight, which the claim counts, nor a row on."""
    old = now - max_age
    connection.execute("DELETE FROM continuations WHERE finished_at IS NOT NULL AND finished_at < ?", (old,))
    excess = connection.execute("SELECT count(*) FROM continuations").fetchone()[0] - limit
    if excess > 0:
        connection.execute("DELETE FROM continuations WHERE answer_id IN (SELECT answer_id FROM continuations WHERE finished_at "
                           "IS NOT NULL ORDER BY finished_at LIMIT ?)", (excess,))
    connection.execute("DELETE FROM keep_going WHERE state=? AND finished_at < ?", (KeepState.DONE, old))
