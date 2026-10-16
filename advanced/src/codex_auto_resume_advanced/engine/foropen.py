# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""Queue for opening: a conversation the Codex app does not hold is sent core's ordinary continuation, left in Codex's
queue for when the person opens it, for the days they chose (v0.6.15-beta, P16's QUEUE_FOR_OPEN).

The standard edition waits for the app to hold a conversation before it sends anything there (A11: nothing is queued
on the off chance). With this on, P16 answers QUEUE_FOR_OPEN for a usage-limited conversation the app does not hold
(core asks only where it reads notLoaded, never unknown, after consent): core sends its own words, with its marker,
through its own backend, under the one claim - which writes this capability's QUEUE_FOR_OPEN override, one per
interruption (ledger.py) - and Codex delivers it when the conversation is opened (M1). In the watch core asks again
whether to keep it there: yes while the override is within the person's Days (3 to 7, 3 by default), no after - and
core takes it back at seven days and an hour whatever is answered (core's engine/foropen.py). An interruption once
queued for opening is never queued for opening again: given back to waiting, it waits for the app as A11 says.

Opened and not delivered within core's 180 seconds, core takes it back (not_delivered_on_open), gives it back to
waiting and sends it the ordinary way to the now loaded conversation - and this capability turns off: the tripwire
NOT_DELIVERED_ON_OPEN (runtime.moved). Where the goal continuation's route applies it answers first, before this in
the registry, and its route is carried out.

It holds no memory of its own: what it reads is the state's, through its view (state.Scoped).
"""
from __future__ import annotations

from codex_auto_resume.domain.plug import DEFER, Alternative

from ..vocabulary import OptionKey, OverrideKind

CAPABILITY = "queue_for_open"
DAYS = (3, 4, 5, 6, 7)
DEFAULT_DAYS = 3
DAY = 86400
# Where core asks P16 for a conversation the running app does not hold (core's engine/delivery.APP_FREE).
APP_FREE = "app_free"


def watching(record) -> bool:
    """Whether core asks about a continuation already queued for opening (its watch hands `queued_since`), rather
    than whether to queue one."""
    return isinstance(record, dict) and "queued_since" in record


class QueueForOpen:
    """The capability's code: its hook at P16. `bind` gives it its view of the state (state.Scoped)."""
    __slots__ = ("paths", "_scoped")

    def __init__(self, paths):
        self.paths = paths
        self._scoped = None

    def bind(self, scoped):
        self._scoped = scoped

    def unloaded(self, record):
        """P16: QUEUE_FOR_OPEN to queue a record not queued for opening before, or - in the watch - to keep one
        queued while its override is within the Days chosen; DEFER otherwise, and where the state cannot be read."""
        scoped = self._scoped
        key = record.get("interruption_id") if isinstance(record, dict) else None
        if scoped is None or not isinstance(key, str):
            return DEFER
        # v0.6.16-beta.4: queued only for a conversation the running app does not hold - never one asked with the
        # app closed or held by another session; the watch, which hands neither, asks only whether to keep it.
        if not watching(record) and record.get("holder") != APP_FREE:
            return DEFER
        try:
            override = scoped.request(key)
            if not watching(record):
                return DEFER if override is not None else Alternative.QUEUE_FOR_OPEN
            days = scoped.options().get(OptionKey.DAYS, DEFAULT_DAYS)
            now = scoped.now()
        except Exception:
            return DEFER
        if override is None or override.get("kind") != OverrideKind.QUEUE_FOR_OPEN:
            return DEFER
        days = days if days in DAYS else DEFAULT_DAYS
        return Alternative.QUEUE_FOR_OPEN if now - override["created_at"] < days * DAY else DEFER


def make(paths) -> QueueForOpen:
    """The capability's factory (registry.CapabilityDef.make): its code for one installation."""
    return QueueForOpen(paths)
