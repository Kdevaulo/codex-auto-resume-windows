"""Why a failed turn was not taken up (v0.6.16-beta.3, asked for in issue #27).

Each reason is a code, decided where the watcher decides it - codex/history.py for what Codex recorded,
engine/detect.py for what Settings and the records say - and written to the log once per turn and reason
(logbook.skipped), never on every check. The Diagnostics check reads the same lines back. A code, a kind
word Codex itself uses (`kind`), an id: never a title, a message or a prompt.
"""
from __future__ import annotations

import re

BEFORE_WINDOW = "before_window"                 # A16: before arming, minus the look-back
NEWER_TURN = "newer_turn"                       # A17: a later turn came after it
OTHER_KIND = "other_kind"                       # A15: not a desktop conversation of a person's own
UNKNOWN_CONVERSATION = "unknown_conversation"   # no conversation Codex knows by its id
CONTINUED_ELSEWHERE = "continued_elsewhere"     # its conversation goes on under another id (issue #30)
NOT_RECOVERED = "not_recovered_kind"            # A13: not a kind it recovers
CATEGORY_OFF = "category_off"                   # that kind's recovery switched off in Settings
CONVERSATION_OFF = "conversation_off"           # recovery switched off for its conversation
RECOVERY_OFF = "recovery_off"                   # automatic recovery off

REASONS = (BEFORE_WINDOW, NEWER_TURN, OTHER_KIND, UNKNOWN_CONVERSATION, CONTINUED_ELSEWHERE, NOT_RECOVERED,
           CATEGORY_OFF, CONVERSATION_OFF, RECOVERY_OFF)

_KIND = re.compile(r"[A-Za-z0-9_.-]{1,32}\Z")


def kind(value) -> str:
    """A kind word as Codex writes one (a source, a thread_source, an originator, a category), safe to print:
    itself where it is a short plain word, `subagent` for any subagent's, `none` for none, else `other`."""
    if value is None:
        return "none"
    text = str(value)
    if "subagent" in text.lower():
        return "subagent"
    return text if _KIND.fullmatch(text) else "other"
