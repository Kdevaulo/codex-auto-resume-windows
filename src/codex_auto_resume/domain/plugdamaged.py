"""The plug of an advanced installation whose package could not be loaded, and the one way core asks a plug.

Out of domain/plug.py, which is at its line budget, in v0.6.15-beta.3, and named through it still: `from
.plug import DamagedPlug, consult, fields` reads as it did. What is here is what domain/plug.py's docstring says of
them - DamagedPlug does everything NULL does and nothing else; `consult` asks a hook, puts NULL's answer in place of
one that raised and DEFER in place of a word its point does not take, and hands every hook copies; `fields` is what a
surface takes from one.

Pure, as the rest of domain/.
"""
from __future__ import annotations

import copy
import json

from .plug import ALTERNATIVES, DEFER, HOOKS, NULL, Alternative, Edition, Plug, PlugFailure, Point


class DamagedPlug(Plug):
    """An advanced installation whose package could not be loaded.

    It does everything NULL does and nothing else - a package half loaded is worse than one not
    loaded at all - and says so: its badge reads "Advanced - not loaded", and `reason` is why.
    """
    __slots__ = ("reason",)
    edition = Edition.ADVANCED
    badge = "Advanced - not loaded"

    def __init__(self, reason):
        self.reason = PlugFailure(reason)


def _handed(argument):
    """What a hook is given of `argument`: a copy of core's own records and facts, and anything
    else - a view, a connection, BACKEND - as it is, each being what its point hands over."""
    if isinstance(argument, (dict, list)):
        return copy.deepcopy(argument)
    return argument


def consult(plug, point, *arguments, failed=None):
    """Ask `plug` at `point`, the one way core asks.

    A hook that raises gets NULL's answer in its place, so a broken capability costs its own
    answer and nothing more; `failed`, if given, is told the point it happened at. At a decision
    point, an answer outside the point's closed set is DEFER: an unknown word, another point's
    word, or something that is not a word at all - and one whose hashing or comparison raises is
    a hook that failed, since that is the plug's own code running.

    Every record and every fact goes to the hook as a copy (`_handed`). The row whose thread and
    marker the send takes, the due list the tick goes on to try, the status a surface returns:
    a hook that rewrote any of them and answered DEFER would have relaxed what core does through
    a side effect, where DEFER says it changed nothing. NULL reads nothing, so it is given
    core's own and nothing is copied for the standard edition.
    """
    point = Point(point)
    hook = HOOKS[point]
    if plug is NULL:
        return getattr(NULL, hook)(*arguments)
    try:
        answer = getattr(plug, hook)(*(_handed(argument) for argument in arguments))
    except Exception:
        if failed is not None:
            failed(point)
        return getattr(NULL, hook)(*arguments)
    if point not in ALTERNATIVES or answer is DEFER:
        return answer
    try:
        accepted = answer in ALTERNATIVES[point]
    except TypeError:                                  # unhashable, so no word
        return DEFER
    except Exception:                                  # a __hash__ or __eq__ of the plug's raised
        if failed is not None:
            failed(point)
        return DEFER
    return Alternative(answer) if accepted else DEFER


def fields(answer):
    """What a surface takes from a plug: a JSON object, copied, or DEFER.

    Words for keys, and nothing JSON cannot write strictly - no NaN, no infinity, no object of
    some other kind - so what a plug adds reaches a front end through the same writer as every
    reply (controlcli.encode) and cannot break it. It is copied through that writer's own form,
    so nothing the plug keeps a reference to changes a reply after it was made.

    A dict with str keys exactly, not a subclass of either: a subclass brings its own iteration,
    items and hashing, which are the plug's code running here, outside `consult`. Anything at all
    that goes wrong while it is copied is DEFER - a surface is the status, get_status and the
    Dashboard, which a strange answer must never break."""
    try:
        if type(answer) is not dict or not all(type(key) is str for key in answer):
            return DEFER
        return json.loads(json.dumps(answer, allow_nan=False))
    except Exception:
        return DEFER
