# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""Which subagents a conversation spawned, and how each one's latest turn ended, read-only (v0.6.14-beta.2) - never
what either says.

Codex keeps who spawned whom in `thread_spawn_edges` of the newest state_<N>.sqlite (parent, child, status - the
three columns required). A child's latest turn is read from the turn history as core reads a turn: its status, and
for a failed one its error classified by core's failures.classify (codex/values.normalize) and dropped to the
category word at once (B9's rule: the raw error never kept). Children are read only for a parent the subagent
recovery is asked about (engine/subagent.py). Nothing here is ever written, and nothing is ever sent to a child.
"""
from __future__ import annotations

import sqlite3
from typing import NamedTuple

from codex_auto_resume.codex.values import normalize
from codex_auto_resume.domain import ids

from .turns import TurnsUnavailable, connect

EDGE_COLUMNS = frozenset({"parent_thread_id", "child_thread_id", "status"})
CHILDREN = "SELECT child_thread_id FROM thread_spawn_edges WHERE parent_thread_id=? ORDER BY rowid LIMIT ?"
CHILD_TURN = ("SELECT thread_id, turn_id, status, error_json, started_at, completed_at, rollout_ordinal "
              "FROM thread_turns WHERE thread_id=? ORDER BY rollout_ordinal DESC LIMIT 1")
STATEMENTS = (CHILDREN, CHILD_TURN)
TURN_COLUMNS = frozenset({"thread_id", "turn_id", "status", "error_json", "started_at", "completed_at",
                          "rollout_ordinal"})
# How many children of one parent are read at most.
CHILDREN_LIMIT = 20


class Child(NamedTuple):
    thread_id: str
    turn_id: str | None         # its latest turn, or None where it has none
    status: str | None          # completed, failed, interrupted, inProgress - or None
    category: str | None        # a failed turn's category word (failures.CATEGORIES), never its error


class Lineage:
    """The spawn edges and the children's latest turns of the Codex home `home`."""

    def __init__(self, home):
        self.home = home

    def children(self, parent) -> list:
        """The subagents `parent` spawned, oldest first, at most CHILDREN_LIMIT, each with how its latest turn ended.
        TurnsUnavailable where either database cannot be read as this reads it."""
        if not ids.is_uuid(parent):
            raise TurnsUnavailable("not a conversation")
        connection = connect(self.home, "state", {"thread_spawn_edges": EDGE_COLUMNS})
        try:
            found = [row[0] for row in connection.execute(CHILDREN, (parent, CHILDREN_LIMIT)).fetchall()]
        except (sqlite3.Error, ValueError):
            raise TurnsUnavailable("the spawn edges cannot be read") from None
        finally:
            connection.close()
        found = [child for child in found if ids.is_uuid(child) and child != parent]
        if not found:
            return []
        connection = connect(self.home, "history", {"thread_turns": TURN_COLUMNS})
        children = []
        try:
            for child in found:
                row = connection.execute(CHILD_TURN, (child,)).fetchone()
                if row is None:
                    children.append(Child(child, None, None, None))
                    continue
                turn = normalize(dict(zip(("thread_id", "turn_id", "status", "error_json", "started_at",
                                           "completed_at", "rollout_ordinal"), row)))
                if turn is None:
                    children.append(Child(child, None, None, None))
                    continue
                children.append(Child(child, turn["turn_id"], turn["status"], turn["category"]))
        except (sqlite3.Error, ValueError):
            raise TurnsUnavailable("the turn history cannot be read") from None
        finally:
            connection.close()
        return children
