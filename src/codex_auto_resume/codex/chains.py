"""The ids a split conversation has had, remembered (v0.6.16-beta.3, issue #30).

Codex can split a conversation more than once (codex/rollout.py): A's turns go on under B, then under C. Which ids
came before the current one is read from the names of A's earlier files - but a file can leave the sessions folder
(archived, deleted), and an id the next listing no longer finds would drop out of A's chain: A's own old failure
would be the latest again although the person worked under B, and every later id's place would move (rollout.SPAN).
So the chain a conversation has had is remembered here, and only ever extended: an id never leaves it.

What is kept is ids only - per Codex home (homes.key, a digest of its path), each conversation's ids in order - in
a small JSON file of the product's own state folder (config/split-chains.json), written whole and atomically, by
the watcher alone (the Dashboard's bridge reads it). Bounded: the newest MAX_CONVERSATIONS conversations of each
home and MAX_IDS ids each. Without a file (a test, the command line) it is remembered for this process only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .. import homes
from ..domain import ids

FORMAT = 1
MAX_CONVERSATIONS = 2000
MAX_IDS = 64
MAX_BYTES = 4 * 1024 * 1024


class ChainMemory:
    """Each split conversation's ids, in order (its own first), as this product has seen them."""

    def __init__(self, path=None, *, writable=True):
        self.path = None if path is None else Path(path)
        self.writable = writable and self.path is not None
        self._homes, self._stamp = None, None

    def _changed(self) -> bool:
        """Whether a reader's file was written since it was read (the watcher writes; the bridge reads)."""
        try:
            stamp = self.path.stat().st_mtime_ns if self.path is not None else None
        except OSError:
            stamp = None
        if self.writable or stamp == self._stamp:
            return False
        self._stamp = stamp
        return True

    def _load(self) -> dict:
        if self._homes is None or self._changed():
            self._homes = {}
            try:
                if self.path is not None and self.path.is_file() and self.path.stat().st_size <= MAX_BYTES:
                    found = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(found, dict) and found.get("format") == FORMAT:
                        for home, held in (found.get("homes") or {}).items():
                            if isinstance(home, str) and isinstance(held, dict):
                                self._homes[home] = {
                                    owner: tuple(each for each in chain if ids.is_uuid(each))[:MAX_IDS]
                                    for owner, chain in held.items()
                                    if ids.is_uuid(owner) and isinstance(chain, list)}
            except (OSError, ValueError, RecursionError):
                self._homes = {}
        return self._homes

    def get(self, home, thread_id) -> tuple:
        """The ids after `thread_id`'s own that its turns have been recorded under, oldest first - () for none."""
        return self._load().get(homes.key(home), {}).get(thread_id, ())

    def extend(self, home, thread_id, chain) -> tuple:
        """`chain` (the ids after its own, oldest first) joined to what is remembered, which it only extends: what
        is remembered keeps its place, a new id goes after it. Returns the remembered chain, saved if it grew."""
        held = self.get(home, thread_id)
        grown = held + tuple(each for each in dict.fromkeys(chain) if each not in held and each != thread_id)
        if grown != held and len(grown) <= MAX_IDS:
            table = self._load().setdefault(homes.key(home), {})
            table.pop(thread_id, None)
            table[thread_id] = grown
            while len(table) > MAX_CONVERSATIONS:
                table.pop(next(iter(table)))
            self._save()
            return grown
        return held

    def _save(self):
        if not self.writable:
            return
        text = json.dumps({"format": FORMAT, "homes": {home: {owner: list(chain) for owner, chain in held.items()}
                                                         for home, held in self._homes.items()}}, allow_nan=False)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(self.path.name + ".tmp")
            temporary.write_text(text, encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            pass                                    # remembered for this process; written again on the next change


# One memory per file in a process, and one for a source given none.
_MEMORIES = {}


def memory(path=None, *, writable=True) -> ChainMemory:
    """The ChainMemory of `path` (the state folder's file), shared by every reader in this process - or the
    process's own where there is no file."""
    key = (None if path is None else str(Path(path)), writable)
    if key not in _MEMORIES:
        _MEMORIES[key] = ChainMemory(path, writable=writable)
    return _MEMORIES[key]
