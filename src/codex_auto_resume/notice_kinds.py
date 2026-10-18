"""The kinds of notice a person can keep on screen until they click it (v0.6.16): one registry.

The owner, 2026-10-16: "알림을 클릭하기 전까지 화면에 떠있게 할 수 있게도 설정 가능하게" - and then, per kind: a usage
limit detected may stay while "resumed" goes away as it always did. So each kind here has an id, the notices it covers
(notifier's kinds), and its words in every catalog, and each is off by default: a notice goes away by itself after a
while, as before, unless its kind is in the setting FIELD. The setting holds the ids chosen and nothing else.

The standard edition's kinds are CORE, named by the catalog key their words are under. An edition registers its own
with `register` - the advanced edition as it makes the plug it hands core (edition.py loads it),
with its words in every language - so the standard build names none of them, and its notices are kept by the same
rule once they are registered. A registered kind's words are handed to the window with the settings' schema
(settings_schema), since the window's catalog is core's.

Pure but for the catalogs: no file, no clock, no Windows.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import threading

from . import l10n

# The setting: the ids of the kinds that stay until clicked (settings.FIELDS), none by default.
FIELD = "notices_stay"
# What an id is, and how many a stored value keeps - more than there are kinds, so an edition's are kept too.
ID = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
LIMIT = 64


@dataclass(frozen=True)
class Kind:
    """One kind: its id, the notifier kinds it covers, and its words - a catalog key of core's (`key`), or one text
    per language (`words`, an edition's)."""
    id: str
    notices: tuple
    key: str | None = None
    words: tuple = ()           # sorted (locale, text) pairs, every locale of l10n.LOCALES

    def label(self, locale) -> str:
        if self.key is not None:
            return l10n.text(self.key, locale)
        words = dict(self.words)
        return words.get(locale) or words[l10n.DEFAULT]


# The standard edition's kinds, in the order the window lists them. Their words are the catalogs' own: the
# notifications switch of the same event where there is one, else the notice's title, else (after a long sleep)
# words of their own.
CORE = (
    Kind("interruption", ("interruption",), "field.notify_interruption"),
    Kind("starting", ("starting",), "field.notify_starting"),
    Kind("resumed", ("resumed",), "msg.toast_resumed_title"),
    Kind("failed", ("failed", "unknown"), "msg.toast_failed_title"),
    Kind("stopped", ("stopped",), "field.notify_stopped"),
    Kind("cancelled", ("cancelled",), "msg.toast_cancelled_title"),
    Kind("needs_you", ("needs_you",), "field.notify_needs_you"),
    Kind("after_sleep", ("after_sleep",), "stay.after_sleep"),
    Kind("memory", ("memory_warning", "memory_stopped"), "msg.toast_memory_warning"),
    Kind("power", ("power_grace", "power_now", "power_failed", "power_not_met", "power_stopped"), "power.title"),
)

_lock = threading.Lock()
_registered = {}                # id -> Kind, an edition's, in the order registered


class KindError(ValueError):
    """A kind that cannot be registered: says which rule it broke."""


def register(kind_id, notices, words) -> Kind:
    """Register an edition's kind of notice: `kind_id` (lowercase letters, digits and _), the notifier kinds it covers,
    and `words`, its name in every language of l10n.LOCALES ({locale: text}). The one function an edition calls;
    registering the same id again replaces it. Raises KindError for anything else - a core id, a notice another
    kind covers, a language missing."""
    if not isinstance(kind_id, str) or not ID.match(kind_id):
        raise KindError("an id is lowercase letters, digits and _")
    notices = tuple(notices) if isinstance(notices, (list, tuple)) else ()
    if not notices or not all(isinstance(notice, str) and ID.match(notice) for notice in notices):
        raise KindError("a kind covers at least one notice")
    if not isinstance(words, dict) or set(words) != set(l10n.LOCALES) or not all(
            isinstance(text, str) and text.strip() and len(text) <= 200 for text in words.values()):
        raise KindError("a kind has its words in every language")
    with _lock:
        taken = {kind.id: kind for kind in CORE}
        taken.update((kind.id, kind) for kind in _registered.values() if kind.id != kind_id)
        if kind_id in taken:
            raise KindError("the id %s is taken" % kind_id)
        covered = {notice for kind in taken.values() for notice in kind.notices}
        if covered & set(notices):
            raise KindError("a notice is another kind's")
        made = Kind(kind_id, notices, words=tuple(sorted(words.items())))
        _registered[kind_id] = made
    return made


def kinds() -> tuple:
    """Every kind there is in this process: CORE, then an edition's, as registered."""
    with _lock:
        return CORE + tuple(_registered.values())


def ids() -> tuple:
    return tuple(kind.id for kind in kinds())


def kind_of(notice_kind):
    """The kind a notifier notice belongs to, or None (a demo card, or a notice no kind covers)."""
    for kind in kinds():
        if notice_kind in kind.notices:
            return kind
    return None


def chosen(values) -> frozenset:
    """The ids a settings mapping keeps on screen (FIELD), as stored; anything else is none."""
    stored = values.get(FIELD) if isinstance(values, dict) else None
    return frozenset(coerce(stored, []))


def stays(notice_kind, values) -> bool:
    """Whether a notice of this notifier kind stays on screen until clicked under these settings."""
    kind = kind_of(notice_kind)
    return kind is not None and kind.id in chosen(values)


def coerce(value, default):
    """The stored value: distinct ids, at most LIMIT, in the order given - an edition's ids included, so a choice made
    in the advanced edition outlives a switch to the standard one; anything else is `default`."""
    if not isinstance(value, list) or len(value) > LIMIT:
        return default
    kept = []
    for entry in value:
        if not isinstance(entry, str) or not ID.match(entry):
            return default
        if entry not in kept:
            kept.append(entry)
    return kept


def edition_labels(locale) -> dict:
    """An edition's kinds' words in `locale`, by id - what the window cannot find in core's catalog."""
    with _lock:
        return {kind.id: kind.label(locale) for kind in _registered.values()}
