"""Rescan and reconcile (v0.6.16, issue #39): every waiting recovery looked at again, on a person's word.

A wait can outlive what it waits for. Codex can carry a conversation's work on in a file the watcher had not
followed yet (issue #30, which v0.6.16-beta.3 follows), or a person can work on in the conversation while a
recovery is held, postponed or paused - when the watcher does not look at it - and the wait stays on the Pending
page. This answers, for each waiting record, with the watcher's own rules and nothing copied from them:

* RETIRED, only on proof that a person's newer work came after its failure: its exact failed turn - that turn
  id, at the ordinal the record holds, across a split (codex/history.py `turn_observation`) - and after it a turn
  a person started, which no continuation or message of this product's started or joined (`persons`): the turns
  the engine itself calls foreign (engine/compaction.py, engine/plugrecords.py `persons_turns`), less any whose
  user messages carry a proof of any record this product holds of the conversation. What Codex's history already
  holds of that happened, so this is read whether or not the history has caught up. Where it has not, and the
  history proves nothing, the conversation's current file is read for the same proof (codex/rollout.py
  `superseded_in`): the failed turn's own end, then a person's message - never where a continuation of this
  product's was sent with no marker, which that file could not tell from a person's;
* RECHECKED, where the history is exactly current and the record is still its conversation's latest failure
  (engine/detect.py `valid_interruption`). Nothing about it changes: it waits as it did, and the watcher still
  checks it through every gate - reset grace, postponements, holds, consent, budgets - at its own time;
* UNRESOLVED, for everything else: a history behind with no proof, a file too large or unreadable, a home no
  longer in Settings, a latest turn that changed with no person's turn after it, or out of time. It stays as it
  is, and is said to be unresolved.

What is found is applied by the control layer (control/actions.py `rescan_pending`), which reads each record
again in the transaction that applies it and skips one that changed meanwhile. Read only here: nothing is sent,
nothing is written to Codex, no budget is touched - the engines this builds have no backend and no store.
"""
from __future__ import annotations

from pathlib import Path
import time

from . import config, homes as homes_module
from .codex import LocalSource, rollout
from .codex.chains import memory as chain_memory
from .domain import ids
from .engine import Engine
from .store.actions import RECHECKED, RETIRED, UNRESOLVED

# The longest the records are judged for, well under the Dashboard's wait for a bridge answer (gui/Dashboard.cs,
# 30 s): a record not reached by then is unresolved.
SECONDS = 20.0
# Why a record is unresolved, as the answer says it.
STALE, CHANGED_LATEST, UNREADABLE, TOO_LARGE, MARKER_FREE, HOME_UNKNOWN, OUT_OF_TIME, ROLLED_BACK = (
    "projection_stale", "latest_turn_changed", "unreadable", "too_large", "marker_free", "home_unknown",
    "out_of_time", "rolled_back")
# The reason a retired record is stopped with: the engine's own, for a later turn (engine/detect.py).
LATER_TURN = "later_turn_exists"


def proofs(kin) -> tuple:
    """(every proof a continuation of this product's may carry in the conversation, whether one went with no marker):
    each record's markers - its own and its key's long and short forms - and the client id a marker-free one was
    queued under (engine/delivery.py `proof`), for `kin`, every record this product holds of the conversation."""
    found, free = set(), False
    for row in kin:
        key = row["interruption_id"]
        found.update(ids.record_markers(key))
        if row.get("marker"):
            found.add(row["marker"])
        client = row.get("recovery_client_id")
        if client is not None and client == ids.continuation_client_id(key):
            found.add(client)
            free = True
    return tuple(sorted(proof for proof in found if ids.is_delivery_proof(proof))), free


def persons(engine, row, ours) -> list:
    """The turns after the record's exact failed turn that a person started: none unless that turn is found in the
    history at the ordinal the record holds (the anchor); then those the engine calls foreign and whose first user
    message is a person's (payload.later_turn's later_turn_exists), less any a proof in `ours` is in and any whose user
    messages carry a marker of this product's at all (ids.MARKER_PREFIX, as the file is read): a wrap-up's, say, whose
    record only the edition's plug holds."""
    source, thread = engine.source, row["thread_id"]
    proof = engine.proof(row)
    seen = source.turn_observation(thread, row["turn_id"], proof)
    if not seen.get("found") or seen.get("ordinal") != row["ordinal"]:
        return []
    found = []
    for turn in engine.persons_turns(thread, source.later_turns(thread, row["ordinal"], proof)):
        if turn["turn_id"] is None or turn.get("reason") != LATER_TURN or not engine.foreign(row, turn):
            continue
        if source.turn_markers(thread, turn["turn_id"], ours):
            continue                     # one of this product's continuations started it, or is in it
        if source.turn_observation(thread, turn["turn_id"], proof).get("branded_user_messages", 1):
            continue                     # a message of this product's is in it, whichever record it was
        found.append(turn)
    return found


def judge(engine, row, kin, deadline=None) -> tuple:
    """(outcome, reason) for one waiting record, by `engine` - the watcher's own rules, for the record's Codex home.
    RETIRED only on proof; RECHECKED only with Codex's history exactly current; UNRESOLVED otherwise."""
    if deadline is not None and time.monotonic() > deadline:
        return UNRESOLVED, OUT_OF_TIME
    thread = row["thread_id"]
    ours, free = proofs(kin)
    try:
        if persons(engine, row, ours):
            return RETIRED, LATER_TURN
    except Exception:
        return UNRESOLVED, UNREADABLE
    try:
        current = engine.fresh_throughout(thread, engine.clock())       # exactly current now, no grace
    except Exception:
        current = False
    if current:
        try:
            still = engine.valid_interruption(row)
        except Exception:
            return UNRESOLVED, UNREADABLE
        return (RECHECKED, None) if still else (UNRESOLVED, CHANGED_LATEST)
    if free:
        return UNRESOLVED, MARKER_FREE
    try:
        found = engine.source.rescan_evidence(thread, row["turn_id"])
    except Exception:
        found = rollout.UNREADABLE
    if found == rollout.LATER_MESSAGE:
        return RETIRED, LATER_TURN
    # A rollback after the failed turn's end - which Codex's history, not the file, says the outcome of - proves nothing.
    return UNRESOLVED, {rollout.TOO_LARGE: TOO_LARGE, rollout.UNREADABLE: UNREADABLE,
                        rollout.ROLLED_BACK: ROLLED_BACK}.get(found, STALE)


def sources_for(control) -> dict:
    """{home_key: reader} for each Codex home the watcher knows: the default ('') and each one Settings add, by the key
    its records carry (homes.key) - made as Diagnostics' check makes them (checkup.sources_for), the split ids
    remembered read only."""
    chains = chain_memory(control.paths.split_chains_file, writable=False)        # the watcher's, read only
    found = {"": LocalSource(config.codex_home(), chains=chains)}
    try:
        named = control.get_settings().get(homes_module.FIELD) or []
    except Exception:
        named = []
    for entry in named if isinstance(named, list) else []:
        try:
            found.setdefault(homes_module.key(entry["path"]), LocalSource(Path(entry["path"]), chains=chains))
        except Exception:
            continue
    return found


def judge_for(control, sources=None, *, now=None, seconds=SECONDS):
    """judge(row, kin) for control.rescan_pending: each record judged by an engine of its own Codex home's - one that
    has no backend and no store, so it can read and nothing else - within `seconds` from the first record."""
    sources = sources_for(control) if sources is None else sources
    now = time.time() if now is None else now
    engines, deadline = {}, time.monotonic() + seconds

    def judged(row, kin):
        key = row.get("home_key") or ""
        if key not in sources:
            return UNRESOLVED, HOME_UNKNOWN
        if key not in engines:
            engines[key] = Engine(None, sources[key], None, clock=lambda: now, home_key=key)
        return judge(engines[key], row, kin, deadline)
    return judged
