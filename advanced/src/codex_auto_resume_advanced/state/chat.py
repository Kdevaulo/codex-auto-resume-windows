# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""What the edition keeps of the Dashboard's chat messages (version 5, v0.6.16-beta.4).

    chat_messages  one row for each message a person sent from the Dashboard's Chat page, with its record (a row of
                   `records`, counted in every claim as the edition's own): its words only while it waits to be handed
                   to core - gone the moment it is claimed to be sent, cancelled, or turned off (the owner's answer of
                   2026-10-11: chat keeps no content) - and when it was made, sent and finished, and why

Every write is one transaction across the message's row and its record's, as the prompt queue's are.
"""
from __future__ import annotations

from ..vocabulary import ChatReason, ChatState, RecordState
from .schema import CHAT_WORDS
from .session import StateError, _key, _thread, _word

CAPABILITY = "codex_chat"
_COLUMNS = ("message_id", "thread_id", "words", "state", "reason", "record_id", "created_at", "sent_at", "finished_at")
# How a record's move ends its message: the reason, and the record's state then.
_ENDS = {"delivered": (ChatReason.DELIVERED, RecordState.FINISHED),
         "unproven": (ChatReason.UNKNOWN, RecordState.FINISHED),
         "superseded": (ChatReason.DELIVERED, RecordState.FINISHED),
         "handed_over": (ChatReason.DELIVERED, RecordState.FINISHED),
         "withdrawn": (ChatReason.WITHDRAWN, RecordState.CANCELLED),
         "not_taken": (ChatReason.NOT_TAKEN, RecordState.CANCELLED)}


def _words(value):
    if not isinstance(value, str) or not 0 < len(value) <= CHAT_WORDS:
        raise StateError("invalid words")
    return value


class ChatMixin:
    def add_chat(self, thread_id, words, record_id, *, at=None) -> int:
        """A message waiting to be handed to core, its record waiting with it: its id."""
        _thread(thread_id)
        _words(words)
        _key(record_id, "record id")
        now = self._now(at)
        with self._transaction() as connection:
            if connection.execute("SELECT 1 FROM records WHERE record_id=?", (record_id,)).fetchone():
                raise StateError("record id taken")
            connection.execute("INSERT INTO records (record_id, capability, thread_id, state, created_at, claims) "
                               "VALUES (?,?,?,?,?,0)", (record_id, CAPABILITY, thread_id, RecordState.WAITING, now))
            cursor = connection.execute(
                "INSERT INTO chat_messages (thread_id, words, state, record_id, created_at) VALUES (?,?,?,?,?)",
                (thread_id, words, ChatState.WAITING, record_id, now))
            return cursor.lastrowid

    def chats(self, *, thread_id=None, pending=False, limit=50) -> list:
        """The messages, oldest first: of one conversation with `thread_id`, only waiting or in flight with
        `pending`."""
        clauses, values = [], []
        if thread_id is not None:
            _thread(thread_id)
            clauses.append("thread_id=?")
            values.append(thread_id)
        if pending:
            clauses.append("state IN ('%s', '%s')" % (ChatState.WAITING, ChatState.IN_FLIGHT))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._read() as connection:
            if connection is None:
                return []
            rows = connection.execute("SELECT %s FROM chat_messages%s ORDER BY message_id DESC LIMIT ?"
                                      % (", ".join(_COLUMNS), where), (*values, int(limit))).fetchall()
        return [dict(zip(_COLUMNS, row)) for row in reversed(rows)]

    def chat_by_record(self, record_id):
        _key(record_id, "record id")
        with self._read() as connection:
            row = None if connection is None else connection.execute(
                "SELECT %s FROM chat_messages WHERE record_id=?" % ", ".join(_COLUMNS), (record_id,)).fetchone()
        return dict(zip(_COLUMNS, row)) if row else None

    def chat_sent(self, record_id, *, at=None) -> bool:
        """Its send began: in flight, and its words gone (the owner's answer: nothing of it is kept once sent)."""
        _key(record_id, "record id")
        now = self._now(at)
        with self._transaction() as connection:
            moved = connection.execute(
                "UPDATE chat_messages SET state=?, words=NULL, sent_at=? WHERE record_id=? AND state=?",
                (ChatState.IN_FLIGHT, now, record_id, ChatState.WAITING)).rowcount == 1
            if moved:
                connection.execute("UPDATE records SET state=?, claimed_at=? WHERE record_id=?",
                                   (RecordState.IN_FLIGHT, now, record_id))
            return moved

    def chat_released(self, record_id) -> bool:
        """A claim given back before its send began: waiting again - its words are still there, never sent."""
        _key(record_id, "record id")
        with self._transaction() as connection:
            return connection.execute("UPDATE records SET state=? WHERE record_id=? AND state=? AND EXISTS "
                                      "(SELECT 1 FROM chat_messages WHERE record_id=? AND state=?)",
                                      (RecordState.WAITING, record_id, RecordState.IN_FLIGHT, record_id,
                                       ChatState.WAITING)).rowcount == 1

    def chat_ended(self, record_id, move, *, at=None) -> bool:
        """A sent message's end, as core's move says it (_ENDS): finished or cancelled, why, and its record with it."""
        _key(record_id, "record id")
        if move not in _ENDS:
            raise StateError("invalid move")
        reason, state = _ENDS[move]
        now = self._now(at)
        with self._transaction() as connection:
            ended = connection.execute(
                "UPDATE chat_messages SET state=?, reason=?, words=NULL, finished_at=? WHERE record_id=? AND state IN "
                "(?, ?)", (ChatState.DONE if state == RecordState.FINISHED else ChatState.CANCELLED, reason, now,
                           record_id, ChatState.WAITING, ChatState.IN_FLIGHT)).rowcount == 1
            if ended:
                connection.execute("UPDATE records SET state=?, finished_at=? WHERE record_id=?",
                                   (state, now, record_id))
            return ended

    def cancel_chat(self, reason, *, record_id=None, thread_id=None, at=None) -> int:
        """Waiting messages cancelled - one by its record, a conversation's, or every one - their words gone: a
        person's Cancel, chat turned off, a conversation switched off. One in flight is its watch's to end."""
        reason = _word(reason, ChatReason, "reason")
        clauses, values = ["state=?"], [ChatState.WAITING]
        if record_id is not None:
            clauses.append("record_id=?")
            values.append(_key(record_id, "record id"))
        if thread_id is not None:
            clauses.append("thread_id=?")
            values.append(_thread(thread_id))
        now = self._now(at)
        with self._transaction(create=False) as connection:
            if connection is None:
                return 0
            keys = [row[0] for row in connection.execute(
                "SELECT record_id FROM chat_messages WHERE " + " AND ".join(clauses), values).fetchall()]
            for key in keys:
                connection.execute("UPDATE chat_messages SET state=?, reason=?, words=NULL, finished_at=? WHERE "
                                   "record_id=?", (ChatState.CANCELLED, reason, now, key))
                connection.execute("UPDATE records SET state=?, finished_at=? WHERE record_id=?",
                                   (RecordState.CANCELLED, now, key))
            return len(keys)
