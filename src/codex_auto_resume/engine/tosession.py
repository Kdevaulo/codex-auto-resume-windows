"""A continuation sent to a conversation another Codex session holds (v0.6.16-beta.4, P16's TO_SESSION).

The app's queue reaches a conversation the Codex app holds; a terminal's TUI and VS Code's server each take a `codex
queue` item for a conversation they hold too (M5). Where loaded() says "elsewhere" (codex/transport.py) and the plug
answers TO_SESSION at P16, core sends its own words with its marker through its own backend, under the one claim,
the thread_available gate passed with the word `session` - and only while the same session, by pid and creation
time, still holds it at the re-check under the dispatch lock.

The watch keeps it queued while that session holds the conversation. It is taken back when that session lets go of
it (session_ended), and when the session has not taken it within the delivery window (session_expired); each is
stored as a withdrawal reason v0.6.15-beta and beta.2 already know and release alike - window_ended and
not_delivered_on_open - so a picker downgrade meets no word it refuses (the review's blocker 2), and both are given
back to waiting once nothing ran. The standard edition's own expiry (`expired`) is untouched: it still settles
failed (the review's blocker 1). Where the app holds the conversation after all, the item is an ordinary queued one.
"""
from __future__ import annotations

from .. import machine
from ..domain.plug import Alternative

# What each of the two withdrawals is stored as (a word every schema-5 reader knows), and shown as (domain/public.py).
STORED = machine.SESSION_WITHDRAWALS


class ToSessionMixin:
    @staticmethod
    def to_session(row) -> bool:
        """Whether `row` was sent to a conversation another Codex session held (P16's TO_SESSION): its claim's gate
        vector - core's own validated column - passed thread_available with the word `session`."""
        return machine.decode_gates(row.get("gate_eval")).get("thread_available") == (machine.PASS, machine.SESSION)

    def _session(self, row, loaded, vector):
        """P16 for a conversation another Codex session holds: TO_SESSION, with the holder's identity kept for the
        re-check under the lock - or None, core's own wait (held_by_other_session)."""
        if loaded != "elsewhere" or vector["consent"][0] != machine.PASS:
            return None
        answer = self.plug.unloaded(dict(row, holder="session", app=True))
        if answer is not Alternative.TO_SESSION:
            return None
        vector["thread_available"] = machine.gate(machine.PASS, machine.SESSION)
        return Alternative.TO_SESSION

    def _session_reason(self, row, loaded, now):
        """Why a continuation sent to another session is taken back now, or None to keep it queued: that session let
        go of the conversation (notLoaded), or did not take it within the delivery window while holding it - or, held
        by the app now, the app did not (expired, as for any queued item)."""
        if loaded == "notLoaded":
            return "session_ended"
        if now - (row.get("submitted_at") or now) < self.options["delivery_timeout_seconds"]:
            return None
        return "expired" if loaded == "loaded" else "session_expired"
