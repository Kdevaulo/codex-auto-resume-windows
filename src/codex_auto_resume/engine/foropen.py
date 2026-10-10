"""A continuation queued for when its conversation is opened (v0.6.15-beta, P16's QUEUE_FOR_OPEN).

A conversation the Codex app does not hold may be sent the ordinary continuation - core's backend, its marker, its
claim - and left in Codex's queue for when a person opens it, where the plug answers QUEUE_FOR_OPEN at P16
(domain/plug.py). Core keeps it there only while the plug still says so, and seven days and an hour at most
(DEFERRED_LONGEST); opened, it has the delivery window like any queued item, and then is taken back as not
delivered on open. Each of these withdrawals is given back to waiting once nothing ran (domain/public.py
RELEASABLE_WITHDRAWALS), and every other withdrawal core makes of a queued item fires as it always does.
"""
from __future__ import annotations

from .. import machine
from ..domain.plug import Alternative

# The longest a continuation is kept in Codex's queue for when its conversation is opened, whatever the plug says:
# seven days and an hour from when it was queued.
DEFERRED_LONGEST = 7 * 86400 + 3600


class ForOpenMixin:
    def _not_for_open(self, current, route, sender, client, vector) -> bool:
        """P16's QUEUE_FOR_OPEN (v0.6.15-beta) goes the ordinary way - core's backend, its marker - or not at all: a
        channel or a client id the plug named waits for the conversation to be opened, as A11 says. True if it waits."""
        if route is not Alternative.QUEUE_FOR_OPEN or (sender is self.backend and client is None):
            return False
        vector["thread_available"] = machine.gate(machine.WAIT, "notLoaded")
        self._wait(current, "waiting_for_loaded_thread", "notLoaded", self.options["state_poll_seconds"], vector)
        return True

    @staticmethod
    def for_open(row) -> bool:
        """Whether `row` was sent for its conversation to be opened (P16's QUEUE_FOR_OPEN, v0.6.15-beta): its claim's
        gate vector - core's own validated column - passed thread_available as the plug's doing, and only that answer
        leaves a queue item with that word (a route queues nothing)."""
        return ((machine.may_be_queued(row["state"], row.get("queue_id")) or row["state"] == "submitting")
                and machine.decode_gates(row.get("gate_eval")).get("thread_available") == (machine.PASS, machine.PLUGGED))

    def _open_reason(self, row, loaded, now):
        """Why a continuation queued for its conversation to be opened is taken back now, or None to keep it queued.
        Not held: kept while the plug still answers QUEUE_FOR_OPEN, asked again with when it was queued, and seven
        days and an hour at most (DEFERRED_LONGEST) - anything else is window_ended. Held: kept for the delivery
        window after core first saw it held (in memory; after a restart, from the first look then) - then Codex did
        not deliver it on open, not_delivered_on_open. Both are given back to waiting once nothing ran."""
        key = row["interruption_id"]
        opened = self.__dict__.setdefault("_loaded_since", {})
        if loaded == "loaded":
            first = opened.setdefault(key, now)
            return ("not_delivered_on_open" if now - first >= self.options["delivery_timeout_seconds"] else None)
        opened.pop(key, None)
        since = row.get("first_queued_at") or row.get("submitted_at") or now
        if now - since >= DEFERRED_LONGEST:
            return "window_ended"
        answer = self.plug.unloaded(dict(row, loaded=loaded, queued_since=since))
        if answer is not Alternative.QUEUE_FOR_OPEN:
            return "window_ended"
        # Kept: the one-second watch looks again only once a poll has passed on the engine's clock - the tick's own
        # watch, a poll on, always does - or at once if consent changed (watch).
        self.__dict__.setdefault("_for_open_seen", {})[key] = now
        return None

    def _for_open_rests(self, row) -> bool:
        """Whether the one-second watch leaves a continuation queued for opening alone this pass (v0.6.15-beta): its
        last look read it not held less than a poll ago, and nothing a person did since - a Pause, Observe only, a
        cancel, its conversation off - asks for it back, which the store alone says. Days of waiting cost one look at
        Codex a minute, not one a second, and a Pause is still taken back within a second."""
        seen = self.__dict__.get("_for_open_seen", {}).get(row["interruption_id"])
        if seen is None or not 0 <= self.clock() - seen < self.options["state_poll_seconds"] or not self.for_open(row):
            return False
        settings = self.store.settings()
        return bool(settings["enabled"] and not self.observing(settings) and not row.get("cancel_requested")
                    and self.store.thread_enabled(row["thread_id"]))
