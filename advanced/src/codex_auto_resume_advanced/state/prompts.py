# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""A person's queued prompts (version 4, v0.6.14-beta.2): their own words for one conversation, to go after the turn
now running, at a time, or on a schedule - in order, each once.

    prompts   one row a prompt: its conversation, its words while one is still to go, when it goes (after_turn,
              at_time at `at`, recurring every day or week from `at`, at most 30 occurrences and never past
              `until`, 30 days from when it was written at most), whether it waits for the one before it to be
              delivered (`depends`), its place in its conversation's queue, where it stands, and the record of its
              current occurrence - a row of `records` (state/records.py) with an id of its own, which the one
              claim counts with core's rows (ledger.py)

The file refuses words on a prompt that is done or cancelled, a series past 30 occurrences or 30 days, and a
recurring prompt without its every; this module refuses the rest: twenty waiting in all, five to a conversation.
"""
from __future__ import annotations

from ..vocabulary import PromptEvery, PromptReason, PromptState, PromptTrigger, RecordState, Refusal
from .choices import Refused
from .schema import PROMPT_SPAN
from .session import StateError, _key, _thread, _timestamp, _word

# A prompt still to go: waiting for its time, due and being tried, or held for a person.
PENDING = (PromptState.WAITING, PromptState.READY, PromptState.HELD)
PROMPTS_LIMIT = 20
PER_CONVERSATION = 5
OCCURRENCES = range(1, 31)
# A prompt's words at most, as a reset message's: what core's one send carries less the marker.
WORDS_LIMIT = 8192
# What a prompt's row may be changed in by the engine (engine/promptqueue.py), and nothing else of it.
CHANGES = frozenset({"state", "reason", "record_id", "gate", "gate_reason", "due_at", "launching_at", "sent_at",
                     "finished_at", "sent_count"})


def _prompt(row) -> dict:
    found = dict(row)
    found["depends"] = bool(found["depends"])
    if "withdraw" in found:
        found["withdraw"] = bool(found["withdraw"])
    return found


class PromptsMixin:
    def add_prompt(self, thread_id, words, trigger, *, at=None, every=None, occurrences=1, until=None,
                   depends=False, now=None) -> int:
        """A person's prompt, waiting, last in its conversation's queue; its id. Refused (Refused) for words that
        are empty or too long (prompt_refused), a time or schedule that is not one on offer (occasion_invalid),
        twenty waiting in all or five in that conversation (queue_full), and a prompt that waits for the one
        before it where there is none (dependency_unknown)."""
        _thread(thread_id)
        current = self._now(now)
        if not isinstance(words, str) or not words.strip() or len(words) > WORDS_LIMIT:
            raise Refused(Refusal.PROMPT_REFUSED)
        try:
            trigger = _word(trigger, PromptTrigger, "trigger")
            every = None if every is None else _word(every, PromptEvery, "every")
        except StateError:
            raise Refused(Refusal.OCCASION_INVALID) from None
        if trigger == PromptTrigger.AFTER_TURN:
            shaped = at is None and every is None and occurrences == 1 and until is None
            due = current
        else:
            shaped = (at is not None and (every is not None) == (trigger == PromptTrigger.RECURRING)
                      and type(occurrences) is int and occurrences in OCCURRENCES
                      and (occurrences == 1 or trigger == PromptTrigger.RECURRING))
            due = at
        if trigger == PromptTrigger.RECURRING and until is None:
            until = current + PROMPT_SPAN
        try:
            due = _timestamp(due, "time")
            until = None if until is None else _timestamp(until, "until")
        except StateError:
            raise Refused(Refusal.OCCASION_INVALID) from None
        if (not shaped or (trigger != PromptTrigger.AFTER_TURN and due < current - 60)
                or (until is not None and not current < until <= current + PROMPT_SPAN)):
            raise Refused(Refusal.OCCASION_INVALID)
        with self._transaction() as connection:
            waiting = connection.execute("SELECT thread_id FROM prompts WHERE state IN (?,?,?)", PENDING).fetchall()
            if len(waiting) >= PROMPTS_LIMIT or sum(row[0] == thread_id for row in waiting) >= PER_CONVERSATION:
                raise Refused(Refusal.QUEUE_FULL)
            last = connection.execute("SELECT max(position) FROM prompts WHERE thread_id=?", (thread_id,)).fetchone()[0]
            if depends and last is None:
                raise Refused(Refusal.DEPENDENCY_UNKNOWN)
            cursor = connection.execute(
                "INSERT INTO prompts (thread_id, words, trigger, at, every, occurrences, sent_count, until, depends, "
                "position, state, created_at, due_at) VALUES (?,?,?,?,?,?,0,?,?,?,?,?,?)",
                (thread_id, words, trigger, None if trigger == PromptTrigger.AFTER_TURN else due, every, occurrences,
                 until, int(bool(depends)), 0 if last is None else last + 1, PromptState.WAITING, current, due))
            return cursor.lastrowid

    def prompts(self, *, thread_id=None, pending=True) -> list:
        """The prompts in queue order - by conversation, then place - each with its current occurrence's record
        state, queue item and whether a Cancel asked for it back: those still to go (`pending`), all (None), or
        the finished."""
        clauses, values = [], []
        if thread_id is not None:
            clauses.append("p.thread_id=?")
            values.append(_thread(thread_id))
        if pending is not None:
            clauses.append("p.state %s (?,?,?)" % ("IN" if pending else "NOT IN"))
            values.extend(PENDING)
        with self._read() as connection:
            if connection is None:
                return []
            rows = connection.execute(
                "SELECT p.*, c.state AS record_state, c.queue_id AS queue_id, c.withdraw AS withdraw FROM prompts p "
                "LEFT JOIN records c ON c.record_id = p.record_id%s ORDER BY p.thread_id, p.position"
                % (" WHERE " + " AND ".join(clauses) if clauses else ""), values).fetchall()
        return [_prompt(row) for row in rows]

    def prompt(self, prompt_id) -> dict | None:
        if type(prompt_id) is not int:
            raise StateError("invalid prompt id")
        with self._read() as connection:
            row = None if connection is None else connection.execute(
                "SELECT p.*, c.state AS record_state, c.queue_id AS queue_id, c.withdraw AS withdraw FROM prompts p "
                "LEFT JOIN records c ON c.record_id = p.record_id WHERE p.prompt_id=?", (prompt_id,)).fetchone()
        return None if row is None else _prompt(row)

    def change_prompt(self, prompt_id, **changes) -> None:
        """Some of a prompt's fields written (CHANGES), and nothing else of it - its words never."""
        if type(prompt_id) is not int or not changes or not set(changes) <= CHANGES:
            raise StateError("invalid prompt change")
        if "state" in changes:
            changes["state"] = _word(changes["state"], PromptState, "state")
        if changes.get("reason") is not None:
            changes["reason"] = _word(changes["reason"], PromptReason, "reason")
        if changes.get("record_id") is not None:
            _key(changes["record_id"], "record id")
        names = sorted(changes)
        # A prompt that ends lets its words go in the same statement: the file refuses them on a finished one.
        ending = ", words=NULL" if changes.get("state") in (PromptState.DONE, PromptState.CANCELLED) else ""
        with self._transaction(create=False) as connection:
            if connection is None:
                return
            connection.execute("UPDATE prompts SET %s%s WHERE prompt_id=?"
                               % (", ".join("%s=?" % name for name in names), ending),
                               tuple(changes[name] for name in names) + (prompt_id,))

    def cancel_prompt(self, prompt_id, at=None) -> str:
        """A person's Cancel of one prompt, its words gone - "cancelled"; or, for an occurrence Codex already holds
        in its queue, "withdrawing": core takes it back (the owner's answer of 2026-10-09), and the move it tells
        ends it. Refused (being_sent) while its occurrence is being sent, and for a prompt not still to go."""
        if type(prompt_id) is not int:
            raise StateError("invalid prompt id")
        now = self._now(at)
        with self._transaction(create=False) as connection:
            row = None if connection is None else connection.execute(
                "SELECT p.state, p.record_id, p.launching_at, p.sent_at, c.state AS record_state FROM prompts p "
                "LEFT JOIN records c ON c.record_id = p.record_id WHERE p.prompt_id=?", (prompt_id,)).fetchone()
            if row is None or row["state"] not in [str(state) for state in PENDING]:
                raise Refused(Refusal.INVALID_REQUEST)
            if row["record_state"] == RecordState.IN_FLIGHT and row["sent_at"] is not None:
                connection.execute("UPDATE records SET withdraw=1 WHERE record_id=? AND state=?",
                                   (row["record_id"], RecordState.IN_FLIGHT))
                return "withdrawing"
            if row["launching_at"] is not None or row["record_state"] == RecordState.IN_FLIGHT:
                raise Refused(Refusal.BEING_SENT)
            connection.execute("UPDATE prompts SET state=?, reason=?, words=NULL, finished_at=? WHERE prompt_id=?",
                               (PromptState.CANCELLED, PromptReason.BY_PERSON, now, prompt_id))
            if row["record_id"] is not None:
                connection.execute("UPDATE records SET state=?, finished_at=? WHERE record_id=? AND state=?",
                                   (RecordState.CANCELLED, now, row["record_id"], RecordState.WAITING))
            return "cancelled"

    def go_on_prompt(self, prompt_id) -> bool:
        """A person's Go on for a prompt held because the one before it did not arrive: it waits again. False if it
        is not held."""
        if type(prompt_id) is not int:
            raise StateError("invalid prompt id")
        with self._transaction(create=False) as connection:
            if connection is None:
                return False
            return connection.execute("UPDATE prompts SET state=?, reason=NULL WHERE prompt_id=? AND state=?",
                                      (PromptState.WAITING, prompt_id, PromptState.HELD)).rowcount == 1

    def end_prompts(self, reason, *, thread_id=None, at=None) -> int:
        """Every prompt still to go whose occurrence is not in flight - of `thread_id`, or all - ended with `reason`
        (turned off, the conversation switched off), its words gone. One in flight is left to core's watch,
        which settles it, and to the move that ends it. How many."""
        reason = _word(reason, PromptReason, "reason")
        now = self._now(at)
        clauses, values = ["p.state IN (?,?,?)", "(c.state IS NULL OR c.state=?)"], [*PENDING, RecordState.WAITING]
        if thread_id is not None:
            clauses.append("p.thread_id=?")
            values.append(_thread(thread_id))
        with self._transaction(create=False) as connection:
            if connection is None:
                return 0
            rows = connection.execute("SELECT p.prompt_id, p.record_id FROM prompts p LEFT JOIN records c ON "
                                      "c.record_id = p.record_id WHERE " + " AND ".join(clauses), values).fetchall()
            for prompt_id, record_id in rows:
                connection.execute("UPDATE prompts SET state=?, reason=?, words=NULL, finished_at=? WHERE "
                                   "prompt_id=?", (PromptState.CANCELLED, reason, now, prompt_id))
                if record_id is not None:
                    connection.execute("UPDATE records SET state=?, finished_at=? WHERE record_id=?",
                                       (RecordState.CANCELLED, now, record_id))
            return len(rows)


def prune(connection, now, max_age, limit) -> None:
    """Prompts finished `max_age` ago, then the oldest finished beyond `limit` - never one still to go."""
    finished = "state IN ('%s', '%s')" % (PromptState.DONE, PromptState.CANCELLED)
    connection.execute("DELETE FROM prompts WHERE %s AND coalesce(finished_at, created_at) < ?" % finished,
                       (now - max_age,))
    excess = connection.execute("SELECT count(*) FROM prompts").fetchone()[0] - limit
    if excess > 0:
        connection.execute("DELETE FROM prompts WHERE prompt_id IN (SELECT prompt_id FROM prompts WHERE %s "
                           "ORDER BY coalesce(finished_at, created_at) LIMIT ?)" % finished, (excess,))
