"""The engine's store as a plug is shown it: the reads, and none of the writes.

Moved out of engine/options.py in v0.6.16-beta.3, as it was, when that page passed its length.
"""
from __future__ import annotations


# What a plug is shown of the store, at P2 and P8: the reads the engine itself makes, and none
# of its writes. Not the journal, which no decision reads (tests/test_surface_properties.py): a
# plug learns what became of a record from the moves core tells it of as it writes them (P14,
# engine/announce.py), not from a history a pruned entry or a retention bound would change.
VIEW_READS = frozenset({"get", "records_in", "settings", "thread_enabled", "others_in_flight",
                        "recent_claims", "recent_claim_count", "claimed_on_thread",
                        # v0.6.14: the engine's own last usage reading - what core read, nothing new.
                        "last_usage"})


class StoreView:
    """The engine's store as a plug sees it, and the moment it was shown.

    The reads, and nothing that writes: a plug is told what core holds and decides nothing by
    changing it. Each read is the store's own, looked up when it is used, so a view costs
    nothing until a plug reads through it.

    The store is kept in a closure, not on an attribute, and a read is handed over as a function
    of its own rather than the store's bound method: `view._store`, or a read's `__self__`, would
    have been every write the store has.

    From v0.6.14 it shows the engine's own last usage reading too (`last_usage`, engine/freshness.py):
    (when, the windows), or None - what core already read for a recovery that was due, reused as it is,
    so a plug that counts usage windows asks Codex for nothing core has just been told.

    That keeps a plug from writing by accident, and it is all this can do. The plug is this
    product's own advanced package, running in core's process, and Python keeps nothing there
    from code that means to find it: a closure's cells, a frame's locals, the garbage collector
    and the store's file on disk all lead to the store. What is taken away is the plain way to
    a write a hook did not mean to make, not every way.
    """
    __slots__ = ("now", "_reads")

    def __init__(self, store, now, last_usage=None, home_key=None):
        self.now = now
        # v0.6.15-beta: the engine's own Codex home, so a plug is shown the records of that home alone - the
        # default home's, for the one engine a plug is given (runtime/homes.py) - however it asks.
        mine = (lambda rows: rows) if home_key is None else (
            lambda rows: [row for row in rows if row["home_key"] == home_key])
        # Written out one by one rather than looked up by name, so that each read names the
        # store call it makes and tests/test_ports.py sees every one of them: a call built at
        # run time is one no table can hold.
        reads = {
            "get": lambda *a, **k: store.get(*a, **k),
            "records_in": lambda *a, **k: store.records_in(*a, **dict(k, home_key=home_key)),
            "settings": lambda *a, **k: store.settings(*a, **k),
            "thread_enabled": lambda *a, **k: store.thread_enabled(*a, **k),
            "others_in_flight": lambda *a, **k: store.others_in_flight(*a, **k),
            "recent_claims": lambda *a, **k: store.recent_claims(*a, **k),
            "recent_claim_count": lambda *a, **k: store.recent_claim_count(*a, **k),
            "claimed_on_thread": lambda *a, **k: mine(store.claimed_on_thread(*a, **k)),
            "last_usage": lambda: last_usage() if last_usage is not None else None,
        }
        for name, call in reads.items():
            call.__name__ = call.__qualname__ = name
        self._reads = reads

    def __getattr__(self, name):
        if name in VIEW_READS and name in self._reads:
            return self._reads[name]
        raise AttributeError(name)
