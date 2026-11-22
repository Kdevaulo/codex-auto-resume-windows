# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""Chat with a conversation from the Dashboard (v0.6.19, P2, P5 and P15; the owner's of 2026-10-02).

A person picks a conversation the Codex app has open on the Dashboard's Chat page, reads its last turns - their
messages and Codex's replies, read only while the page asks (codex/conversation.py) - and sends a message of up to
2,000 characters (control/chat.py). The message waits in the state (state/chat.py) until core takes it:

* P2 - each conversation's oldest waiting message is handed core as a person's MESSAGE record; core carries it out
  as it carries out every record of the edition's own - its gates (the app holds the conversation, nothing of core's
  in flight, consent, usage), the one claim, the last look, the one send - and follows it (engine/plugrecords.py).
* P5 and P15 - for that record this is the channel and the answer is CLIENT_ID: the words go into the conversation
  exactly as typed, with no marker, through `thread/queue/add` under the client id core derives from the record's id
  (MC1: it shows at once as the person's own message and runs), and core proves it by that id
  (engine/recordchannel.py).
* Its pace is its own (A20): one in flight in a conversation across both stores, thirty a conversation and sixty a
  day, never core's five a day or fifteen minutes (state/records.claim_record).
* Its words leave the disk the moment its send begins (state/chat.py); a message Codex did not take within three
  minutes is taken back and never sent again by itself - but none in a queue the forced stop paused, which Codex runs
  when it lets that queue go (v0.6.26); turned off, every message still waiting is cancelled. A Pause takes back none
  Codex holds (v0.6.23, `pause_keeps`): its statement's H4 and H6.

Approvals are still answered in Codex: what MC2 measured shows a turn in progress and finished, never a wait for one.
"""
from __future__ import annotations

from codex_auto_resume.domain import ids
from codex_auto_resume.domain.plug import DEFER, Alternative

from ..vocabulary import ChatState, ContinuationKind
from .markerfree import MarkerFreeContinuation
from .usage import PAUSE

CAPABILITY = "codex_chat"
WORDS = 2000


def handed(row) -> dict | None:
    """What core is handed of one message (P2: plughands.records_of), or None for one not to hand. Each is marked
    `pause_keeps` (v0.6.23): a Pause leaves one Codex holds in its queue, as the statement says (H4 departed)."""
    key = row.get("record_id")
    if not (isinstance(key, str) and len(key) == 64):
        return None
    own = {"record_id": key, "thread_id": row["thread_id"], "marker": ids.short_marker(key), "purpose": "message",
           "ordinal": None, "pause_keeps": True}
    if row["state"] == ChatState.IN_FLIGHT:
        return dict(own, state="in_flight", words=None, sent_at=row.get("sent_at"), queue_id=None, withdraw=False)
    if row["state"] == ChatState.WAITING and row.get("words"):
        return dict(own, state="waiting", words=row["words"], sent_at=None, queue_id=None, withdraw=False)
    return None


# How long Codex has to take a message it holds in its queue before it is taken back (A6: never sent again by itself).
TAKEN_WITHIN = 180


def watched(row, now, stops=()) -> dict | None:
    """A message in flight as core watches it: asked back out of Codex's queue once TAKEN_WITHIN has passed - but never
    one in a queue the forced stop paused (v0.6.26, M1: `paused_by_stop`), which Codex runs once it lets that queue go:
    taken back, its words would be gone, for the chat keeps none once it is sent."""
    record = handed(row)
    if (record is not None and record["sent_at"] is not None and now - record["sent_at"] >= TAKEN_WITHIN
            and not paused_by_stop(row, stops)):
        record["withdraw"] = True
    return record


def paused_by_stop(row, stops) -> bool:
    """Whether a message in flight went into, or sat in, the queue of a conversation usage_pause stopped (`stops`, the
    edition's continuations of its conversation): the stop's continuation after the reset there not yet started when it
    was sent (engine/usagestop.py). The app pauses that queue until the turn of that continuation ends, then sends it.
    The wrap-up's continuation after a reset is none of these: it stopped nothing."""
    return any(stop.get("capability") == PAUSE and stop.get("kind") == ContinuationKind.AFTER_RESET
               and stop.get("thread_id") == row["thread_id"]
               and (stop.get("finished_at") is None or stop["finished_at"] >= row["sent_at"]) for stop in stops)


def _ours(record) -> bool:
    """Whether `record` is a record of this edition's own (P2) - a record id and no interruption id - which is the only
    kind a chat message is; a recovery of core's never is."""
    return isinstance(record, dict) and "record_id" in record and "interruption_id" not in record


class Channel(MarkerFreeContinuation):
    """The one call a chat message goes by: thread/queue/add with its client id, over a session restricted to this
    capability's methods (codex/protocol.CAPABILITY_METHODS)."""
    __slots__ = ()

    def _session(self):
        if self._open is not None:
            return self._open()
        from ..codex import inuse
        from ..codex.protocol import Session
        return Session(inuse.backend(self.paths), capability=CAPABILITY)


class CodexChat:
    """The capability's code: its hooks at P2, P5 and P15. `bind` gives it its view of the state (state.Scoped)."""
    __slots__ = ("paths", "_scoped", "channel")

    def __init__(self, paths, *, session=None):
        self.paths, self._scoped = paths, None
        self.channel = Channel(paths, session=session)

    def bind(self, scoped):
        self._scoped = scoped

    def records(self, view):
        """P2: each conversation's oldest waiting message, and those in flight - for core to try or to watch."""
        scoped = self._scoped
        if scoped is None:
            return DEFER
        try:
            rows = scoped.chat.pending()
        except Exception:
            return DEFER
        found, seen = [], set()
        for row in rows:
            if row["state"] == ChatState.WAITING and view.thread_enabled(row["thread_id"]) is False:
                try:
                    scoped.chat.conversation_off(row["record_id"])
                except Exception:
                    pass
                continue
            if row["state"] == ChatState.WAITING and row["thread_id"] in seen:
                continue
            seen.add(row["thread_id"])
            record = handed(row)
            if record is not None:
                found.append(record)
        return found or DEFER

    def sender(self, record, backend):
        """P5: the channel, for a message of its own - and nothing for anything else: a recovery of core's, or any
        record of another capability's, goes as it would with chat off (the runtime asks this only for a chat
        message, runtime._own_record_answer; this holds it even where it is asked otherwise)."""
        return self.channel if _ours(record) else DEFER

    def delivery(self, record):
        """P15: no marker for a message of its own; core proves it by the client id it derives from the record's id."""
        return Alternative.CLIENT_ID if _ours(record) else DEFER


def make(paths) -> CodexChat:
    """The capability's factory (registry.CapabilityDef.make): its code for one installation."""
    return CodexChat(paths)
