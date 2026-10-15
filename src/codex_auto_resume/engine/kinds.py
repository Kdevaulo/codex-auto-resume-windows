"""Which conversations besides the Codex app's the engine watches (P18, v0.6.16-beta.4).

The standard edition watches the app's own conversations alone (A15), and the NULL plug keeps it so. A plug may name
a terminal's Codex TUI and the VS Code extension too (domain/plughands.SessionKind): asked once a tick while not
paused (K5), and set on the engine's reader, so every eligibility check of this tick - detection, the latest turn a
record is checked against, a usage limit's reset time, a stalled turn - reads them (codex/eligibility.py). A kind that
leaves ends, cancelled, the waiting records of its conversations (session_kind_off): what the plug no longer watches is
never sent to, and what is in flight is followed to its end. The cancel is core's, final, as any cancel is.
"""
from __future__ import annotations

from ..machine import WAITING

# The reason a kind no longer watched cancels its waiting records with.
OFF = "session_kind_off"


class KindsMixin:
    def session_kinds(self):
        kinds = self.plug.sessions()
        before = self.__dict__.get("_session_kinds", frozenset())
        if kinds == before:
            return
        self.source.session_kinds = self._session_kinds = kinds
        gone, left = before - kinds, []
        for row in self._records(WAITING) if gone else ():
            try:
                if self.source.taken(row["thread_id"], before) and not self.source.taken(row["thread_id"], kinds):
                    left.append(row)
            except Exception:
                pass                    # one that cannot be read is left as it is: never cancelled on a guess
        for row in left:
            # One at a time, each told to the plug as it moves (none moved if it left waiting meanwhile).
            if self.store.cancel_waiting([row["interruption_id"]], self.clock(), OFF):
                self.moved(row, "cancelled")
                self.log(row["thread_id"], "cancelled", OFF)
