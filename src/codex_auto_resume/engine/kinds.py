"""Which conversations besides the Codex app's the engine watches (P18, v0.6.16-beta.4).

The standard edition watches the app's own conversations alone (A15), and the NULL plug keeps it so. A plug may name
a terminal's Codex TUI and the VS Code extension too (domain/plughands.SessionKind): asked once a tick while not
paused (K5), and set on the engine's reader, so every eligibility check of this tick - detection, the latest turn a
record is checked against, a usage limit's reset time, a stalled turn - reads them (codex/eligibility.py). A kind that
leaves ends, cancelled, the waiting records of its conversations (session_kind_off): what the plug no longer watches is
never sent to, and what is in flight is followed to its end. The cancel is core's, final, as any cancel is.

v0.6.16: a watcher that starts does not know what the one before it watched, so at its first ask every kind may
have been, and one its plug does not name then leaves as in a running watcher - after a restart with a capability
turned off, an entry into the advanced edition, a move to the standard edition. Left to the next check, which can no
longer read the conversation, such a record was retired as superseded, latest_turn_changed: untrue (live acceptance
item 8 e).
"""
from __future__ import annotations

from ..domain.plughands import SESSION_KINDS
from ..machine import WAITING

# The reason a kind no longer watched cancels its waiting records with.
OFF = "session_kind_off"


class KindsMixin:
    def newer_than_engine(self, row) -> bool:
        """Whether `row`'s conversation is of a kind the plug names - a terminal's, VS Code's - and its file's first
        line says a Codex newer than the engine's `codex --version` wrote it (the version skew guard): continued by an
        older engine, such a conversation may be read or written in a shape that engine does not know, so it waits,
        identity / version_newer_than_engine, until Codex is updated. False with no kind named - the standard
        edition's always, which reads nothing for it - and where either version cannot be read."""
        kinds = self.__dict__.get("_session_kinds", frozenset())
        if not kinds:
            return False
        try:
            return self.source.newer_than_engine(row["thread_id"], kinds, getattr(self.backend, "engine_version", None))
        except Exception:
            return False

    def session_kinds(self):
        kinds = self.plug.sessions()
        # The first ask of this watcher: what the one before it watched is unknown, so every kind may have been.
        before = self.__dict__.get("_session_kinds", frozenset(SESSION_KINDS))
        self.source.session_kinds = self._session_kinds = kinds
        if kinds == before:
            return
        gone, left = before - kinds, []
        for row in self._records(WAITING) if gone else ():
            try:
                # Taken now first: the app's own conversation, and every one still watched, costs one read.
                if not self.source.taken(row["thread_id"], kinds) and self.source.taken(row["thread_id"], before):
                    left.append(row)
            except Exception:
                pass                    # one that cannot be read is left as it is: never cancelled on a guess
        for row in left:
            # One at a time, each told to the plug as it moves (none moved if it left waiting meanwhile).
            if self.store.cancel_waiting([row["interruption_id"]], self.clock(), OFF):
                self.moved(row, "cancelled")
                self.log(row["thread_id"], "cancelled", OFF)
