"""Who holds a conversation "elsewhere", for tests of P16's TO_SESSION (v0.6.16-beta.4).

The real Backend.loaded keeps the pid and creation time of the one other Codex session holding a conversation it says
is "elsewhere" (`session_holder`, codex/transport.py), and the engine sends to that session only while the same one
still holds it (engine/tosession.py, engine/routes.py). codexsim's SimBackend is v0.6.10's file and must stay so
(test_released_calls), so it never sets one - and with none the engine waits (held_by_other_session), as every
released scenario expects. `holding_sessions` gives one SimBackend the real one's habit: `session_map` names each
conversation's holder ((pid, created), or None for one that cannot be read), one default session for the rest.
"""
from __future__ import annotations

DEFAULT_SESSION = (7, 70)


def holding_sessions(backend):
    """`backend` (a codexsim SimBackend), its `loaded` keeping `session_holder` as the real Backend's does."""
    if getattr(backend, "_holds_sessions", False):
        return backend
    plain = backend.loaded

    def loaded(thread_id, app_identity):
        backend.session_holder = None
        found = plain(thread_id, app_identity)
        if found == "elsewhere":
            backend.session_holder = getattr(backend, "session_map", {}).get(thread_id, DEFAULT_SESSION)
        return found
    backend.loaded, backend._holds_sessions, backend.session_holder = loaded, True, None
    return backend
