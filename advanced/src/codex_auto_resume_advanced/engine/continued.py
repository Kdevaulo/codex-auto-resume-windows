# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""What the edition's own continuations share (v0.6.15-beta): the key one is kept under, and what core is handed of
one (P2's CONTINUATION).

An empty reply continued (engine/emptyreply.py), a subagent's stop told to its parent (engine/subagent.py) and a
conversation kept going (engine/keepgoing.py) each answer one turn, once: the key is a digest of what it answers,
which is also its record's id (state/continuations.py). Core sends one only while the turn it follows is still the
conversation's latest, and never to a conversation that is not a person's own (core's engine/plugrecords.py), in
the edition's catalog words, which nothing fills in (continuation.validate_continuation).
"""
from __future__ import annotations

import hashlib
import json

from codex_auto_resume import continuation
from codex_auto_resume.domain import ids

from ..vocabulary import RecordState


def answer_key(*parts) -> str:
    """The key a continuation is kept under: 64 hex digits of what it answers - its capability's word, the
    conversation, the turn and (for a subagent's stop) the child - so one turn is answered once."""
    return hashlib.sha256(json.dumps([str(part) for part in parts], separators=(",", ":")).encode("utf-8")).hexdigest()


def words_pass(words) -> bool:
    """Whether `words` are words core sends as a continuation (continuation.validate_continuation)."""
    try:
        continuation.validate_continuation(words)
    except Exception:
        return False
    return True


def handed(row) -> dict | None:
    """What core is handed of one continuation (P2: plughands.records_of): one waiting, with its words; one in flight,
    to be watched, with the queue item Codex took it as - or None for one not to hand."""
    key = row.get("record_id")
    if key is None or row.get("finished_at") is not None:
        return None
    own = {"record_id": key, "thread_id": row["thread_id"], "marker": ids.short_marker(key),
           "purpose": "continuation", "ordinal": row["ordinal"]}
    if row["record_state"] == RecordState.IN_FLIGHT:
        return dict(own, state="in_flight", words=None, sent_at=row.get("launching_at") or row.get("claimed_at"),
                    queue_id=row.get("queue_id"), withdraw=bool(row.get("withdraw")))
    if row["record_state"] == RecordState.WAITING and row.get("words"):
        return dict(own, state="waiting", words=row["words"], sent_at=None, queue_id=None, withdraw=False)
    return None
