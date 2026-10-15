"""Codex's own files, read.

`source.py` was 728 lines. It is the same reader, composed here from two mixins, so every
`from .source import LocalSource` and every call reads exactly as it did:

    paths       where Codex keeps its files, and the columns each must have
    schema      finding a database, and refusing one whose schema has moved
    history     every statement this product sends to Codex - and nowhere else
    values      Codex's words and numbers, read one way
    labels      the name a person would recognise, cut to a length
    payload     one interruption, read out of what Codex recorded
    errors      the one refusal

Nothing here writes to Codex. Every connection is opened read-only.
"""
from __future__ import annotations

from .errors import SourceError  # noqa: F401
from .history import HistoryMixin
from .labels import MAX_LABEL_CHARS, _label  # noqa: F401
from .values import (KNOWN_STATUSES, MAX_ITEM_BYTES, MAX_META_BYTES,  # noqa: F401
                     MAX_SCAN_BYTES, PROGRESS_ITEM_TYPES, _json, _turn_status,
                     epoch, normalize)
from .paths import DB_KINDS, _safe_path  # noqa: F401
from .payload import _choose_reset, _content_has_marker, _queue_has_marker, admissible, detect  # noqa: F401
from .schema import SchemaMixin


class LocalSource(SchemaMixin, HistoryMixin):
    """Codex's own files, read read-only.
    """
    # P19 (v0.6.16-beta.3): which conversations besides a person's own `_eligibility` takes up (values.taken_thread_source)
    # - the engine sets it from its plug each tick; empty, the standard edition's always, it is A15 as ever.
    widened = frozenset()
    # P18 (v0.6.16-beta.4): the kinds of conversation besides the app's `_eligibility` takes up (codex/eligibility.py),
    # set by the engine from its plug each tick; empty, the standard edition's always.
    session_kinds = frozenset()

    def elsewhere(self, codex_home) -> "LocalSource":
        """A reader of another Codex home, made as this one is (v0.6.15-beta): for the labels of that home's records,
        where the control layer, which builds no reader of its own, is handed this one."""
        return type(self)(codex_home, chains=self.chains)
