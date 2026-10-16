"""A full context window's record, and the compaction turns after it (v0.6.16-beta.4).

The standard edition never retries a turn that failed on its model's context window (A14). The edition's plug may take
one up at P17 - Codex's contextWindowExceeded alone (failures.admits) - and then a compaction is what makes room: the
person's own /compact in the app, or one the plug's route runs. A compaction turn is Codex's own work, not the
person's, so for that record alone it supersedes nothing (A17 for every other record): a later turn whose items are a
contextCompaction and, beside it, only reasoning - its kinds, never its content (codex/history.turn_observation) -
leaves the failure the one to continue, and the continuation that follows it is the record's.
"""
from __future__ import annotations

# The kind of record a compaction turn supersedes nothing of: a full context window, taken up (P17).
COMPACTED = "terminal_invalid"


class CompactionMixin:
    def compacted_since(self, row, latest) -> bool:
        """Whether every turn after a full context window's failure is a compaction alone, the latest among them."""
        if row.get("category") != COMPACTED or (latest.get("ordinal") or 0) <= row["ordinal"]:
            return False
        try:
            turns = self.source.later_turns(row["thread_id"], row["ordinal"], self.proof(row))
        except Exception:
            return False
        return bool(turns) and all(turn["kind"] == "foreign" and self.compaction(row, turn) for turn in turns)

    def compaction(self, row, turn) -> bool:
        """Whether a later `turn` of a full context window's record is a compaction alone; a look that fails, no."""
        if row.get("category") != COMPACTED or turn.get("turn_id") is None:
            return False
        try:
            seen = self.source.turn_observation(row["thread_id"], turn["turn_id"], self.proof(row))
        except Exception:
            return False
        return seen.get("compaction_only") is True

    def foreign(self, row, turn) -> bool:
        """Whether a later `turn` is someone else's work over `row`: never a compaction alone of COMPACTED's (A17)."""
        return turn["kind"] == "foreign" and not self.compaction(row, turn)
