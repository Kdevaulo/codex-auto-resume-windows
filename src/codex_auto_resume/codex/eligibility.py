"""Which kinds of Codex conversation this product takes up: the checks of a `threads` row's source and its rollout's
first line, pure (v0.6.16-beta.4).

The Codex app's own conversations always (A15): source vscode, an originator of the app's (values.DESKTOP_ORIGINATORS),
its first line's source vscode. Beside them, only while the edition's plug names them (P18, domain/plughands
SessionKind), a terminal's Codex TUI - source cli, originator codex-tui - and the VS Code extension's - source vscode,
originator codex_vscode - as MO recorded them on codex-cli 0.162.0-alpha.17.2 (2026-10-16). A word not on these lists
takes nothing up, never another conversation; `codex exec` runs (codex_exec) and every kind Codex makes for itself
stay out - but for a fork a person made of one in the app (issue #66, "exec_forked"). Every statement sent to Codex stays in codex/history.py (tests/test_codex_schema.py); this only judges what
it read. The standard edition names no kind: the app's alone, as ever.

Pure: nothing here reads or writes.
"""
from __future__ import annotations

from ..domain import ids, skips
from .values import (ADOPTED_ORIGINATORS, DESKTOP_ORIGINATORS, EXEC_FORK_ORIGINATORS, NOT_DESKTOP_ORIGINATORS,
                     taken_thread_source)

ORIGINATORS_CLI = frozenset({"codex-tui"})
ORIGINATORS_IDE = frozenset({"codex_vscode"})
# (threads.source, the first line's source, its originators) for each kind: the app's, and the two a plug may name.
KINDS = {"desktop": ("vscode", "vscode", DESKTOP_ORIGINATORS), "cli": ("cli", "cli", ORIGINATORS_CLI),
         "ide": ("vscode", "vscode", ORIGINATORS_IDE),
         # issue #37: a CLI conversation the Desktop app took over - the app's own, always (values.ADOPTED_ORIGINATORS).
         "adopted": ("vscode", "cli", ADOPTED_ORIGINATORS),
         # and one the app forked from it ("continue in a new chat"): the fork's first line keeps the TUI's originator
         # but says source vscode (measured on app 26.1013 / codex-cli 0.163.0-alpha.10.2) - the app's own too.
         "forked": ("vscode", "vscode", ADOPTED_ORIGINATORS),
         # issue #66 (v0.6.24): a fork a person made in the app of a `codex exec` run - the app's row, a first line that
         # keeps codex_exec with source vscode and NAMES the run it was forked from (FORKS_ONLY). The narrowest shape
         # that is the person's own: nothing shows that every vscode row whose first line says codex_exec is one (the
         # history only ever kept codex exec out as a default), while a fork exists only because someone forked it in
         # the app. A standalone exec run has threads source exec, and the product's own (the advanced edition's
         # window anchor) is an ephemeral `codex exec` that leaves no conversation at all (MANCHOR).
         "exec_forked": ("vscode", "vscode", EXEC_FORK_ORIGINATORS)}
# The kinds whose first line must name the conversation it was forked from (`forked`).
FORKS_ONLY = frozenset({"exec_forked"})
# The kinds taken up whatever the plug names: the app's own, those it took over or forked from the CLI, and a person's
# fork of an exec run. Each still needs the app's row (row_problem: source vscode, a person's thread_source, not
# archived, paginated).
APPS = ("desktop", "adopted", "forked", "exec_forked")


def _shapes(kinds):
    return [(kind, KINDS[kind]) for kind in ("desktop", "adopted", "forked", "exec_forked", "cli", "ide")
            if kind in APPS or kind in kinds]


# The shape a conversation is taken up in while the plug widens to every desktop conversation (P19): the app's row, its
# first line's source the app's too, and any originator but values.NOT_DESKTOP_ORIGINATORS (`widened_originator`).
WIDENED = ("vscode", "vscode")


def widened_originator(originator, widened=frozenset()) -> bool:
    """Whether `originator` is taken up on the app's row because the plug widens to every desktop conversation (P19,
    EVERY_DESKTOP): a word (1 to 64 characters, as a widened label is) not on the closed deny-list. Never unwidened -
    the standard edition's `widened` is always empty - and never a first line with no originator at all."""
    return ("every_desktop" in widened and isinstance(originator, str) and 0 < len(originator) <= 64
            and originator not in NOT_DESKTOP_ORIGINATORS)


def forked(first) -> bool:
    """Whether a rollout's first line (its session_meta payload) names the conversation it was forked from."""
    return isinstance(first, dict) and ids.is_uuid(first.get("forked_from_id"))


def source_taken(source, kinds=frozenset()) -> bool:
    """Whether a `threads` row's source is one of a kind taken up: the app's, or one of `kinds`."""
    return any(source == shape[0] for _kind, shape in _shapes(kinds))


def row_problem(row, kinds=frozenset(), widened=frozenset(), composed=False):
    """Why a `threads` row (source, archived, thread_source, history_mode) is not one taken up, as the word
    domain/skips.py says it in - or None: a source of the app's or of `kinds`, not archived, a person's own (or, while
    the plug widens to them, P19, another label - or an agent-made conversation whose failed turn the person started from
    the input box, `composed`, issue #54 - values.taken_thread_source), paginated."""
    for wrong, word in ((not source_taken(row["source"], kinds), "source " + skips.kind(row["source"])),
                        (row["archived"] != 0, "archived"),
                        (not taken_thread_source(row["thread_source"], widened, composed),
                         "thread_source " + skips.kind(row["thread_source"])),
                        (row["history_mode"] != "paginated", "history_mode " + skips.kind(row["history_mode"]))):
        if wrong:
            return word
    return None


def originator_taken(source, first, kinds=frozenset(), widened=frozenset()) -> bool:
    """Whether a first line's (`first`, its session_meta payload) originator is one of a kind taken up whose rows have
    `source` - for a kind of FORKS_ONLY, only where the line names the conversation it was forked from - or, on the app's
    row while the plug widens to every desktop conversation, any originator but the deny-list's (`widened_originator`)."""
    if not isinstance(first, dict):
        return False
    originator = first.get("originator")
    return (any(source == shape[0] and originator in shape[2] and (kind not in FORKS_ONLY or forked(first))
                for kind, shape in _shapes(kinds))
            or (source == WIDENED[0] and widened_originator(originator, widened)))


def newer_than_engine(cli_version, engine_version) -> bool:
    """Whether the Codex a conversation's first line says wrote it (`cli_version`) is newer than the engine's own
    `codex --version`, both read as the compatibility data reads a version (compat/model.parse_version); False where
    either cannot be read - a guard that only ever holds back, never a refusal on a guess."""
    from ..compat.model import parse_version
    written = parse_version("codex-cli " + cli_version) if isinstance(cli_version, str) else None
    engine = parse_version(engine_version)
    return written is not None and engine is not None and written > engine


def kind_of(source, payload, kinds=frozenset(), widened=frozenset()):
    """The kind - "desktop", "cli" or "ide" - a conversation is, by its row's source and its first line's
    originator and source, of the app's and `kinds` - or "desktop" for the app's row and first line with any originator
    but the deny-list's while the plug widens to every desktop conversation (P19); None for anything else."""
    if not isinstance(payload, dict):
        return None
    found = next((kind for kind, shape in _shapes(kinds) if source == shape[0] and payload.get("source") == shape[1]
                  and payload.get("originator") in shape[2] and (kind not in FORKS_ONLY or forked(payload))), None)
    if found is None and (source, payload.get("source")) == WIDENED and widened_originator(payload.get("originator"),
                                                                                           widened):
        return "desktop"
    return "desktop" if found in ("adopted", "forked", "exec_forked") else found
