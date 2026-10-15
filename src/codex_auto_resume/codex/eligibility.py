"""Which kinds of Codex conversation this product takes up: the checks of a `threads` row's source and its rollout's
first line, pure (v0.6.16-beta.4).

The Codex app's own conversations always (A15): source vscode, an originator of the app's (values.DESKTOP_ORIGINATORS),
its first line's source vscode. Beside them, only while the edition's plug names them (P18, domain/plughands
SessionKind), a terminal's Codex TUI - source cli, originator codex-tui - and the VS Code extension's - source vscode,
originator codex_vscode - as MO recorded them on codex-cli 0.162.0-alpha.17.2 (2026-10-16). A word not on these lists
takes nothing up, never another conversation; `codex exec` runs (codex_exec) and every kind Codex makes for itself
stay out. Every statement sent to Codex stays in codex/history.py (tests/test_codex_schema.py); this only judges what
it read. The standard edition names no kind: the app's alone, as ever.

Pure: nothing here reads or writes.
"""
from __future__ import annotations

from ..domain import skips
from .values import DESKTOP_ORIGINATORS, taken_thread_source

ORIGINATORS_CLI = frozenset({"codex-tui"})
ORIGINATORS_IDE = frozenset({"codex_vscode"})
# (threads.source, the first line's source, its originators) for each kind: the app's, and the two a plug may name.
KINDS = {"desktop": ("vscode", "vscode", DESKTOP_ORIGINATORS), "cli": ("cli", "cli", ORIGINATORS_CLI),
         "ide": ("vscode", "vscode", ORIGINATORS_IDE)}


def _shapes(kinds):
    return [(kind, KINDS[kind]) for kind in ("desktop", "cli", "ide") if kind == "desktop" or kind in kinds]


def source_taken(source, kinds=frozenset()) -> bool:
    """Whether a `threads` row's source is one of a kind taken up: the app's, or one of `kinds`."""
    return any(source == shape[0] for _kind, shape in _shapes(kinds))


def row_problem(row, kinds=frozenset(), widened=frozenset()):
    """Why a `threads` row (source, archived, thread_source, history_mode) is not one taken up, as the word
    domain/skips.py says it in - or None: a source of the app's or of `kinds`, not archived, a person's own (or, while
    the plug widens to them, P19, another label - values.taken_thread_source), paginated."""
    for wrong, word in ((not source_taken(row["source"], kinds), "source " + skips.kind(row["source"])),
                        (row["archived"] != 0, "archived"),
                        (not taken_thread_source(row["thread_source"], widened),
                         "thread_source " + skips.kind(row["thread_source"])),
                        (row["history_mode"] != "paginated", "history_mode " + skips.kind(row["history_mode"]))):
        if wrong:
            return word
    return None


def originator_taken(source, originator, kinds=frozenset()) -> bool:
    """Whether a first line's originator is one of a kind taken up whose rows have `source`."""
    return any(source == shape[0] and originator in shape[2] for _kind, shape in _shapes(kinds))


def kind_of(source, payload, kinds=frozenset()):
    """The kind - "desktop", "cli" or "ide" - a conversation is, by its row's source and its first line's
    originator and source, of the app's and `kinds`; None for anything else."""
    if not isinstance(payload, dict):
        return None
    return next((kind for kind, shape in _shapes(kinds) if source == shape[0] and payload.get("source") == shape[1]
                 and payload.get("originator") in shape[2]), None)
