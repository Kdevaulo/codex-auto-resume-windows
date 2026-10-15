"""Reading one interruption out of what Codex recorded.

`detect` turns a failed turn into the record the engine keeps, and the two checks after it answer
whether a message in Codex's history or queue is a continuation of ours: by its marker, or - for
one sent with none - by the client id it was queued under.
"""
from __future__ import annotations

import json
import math
import re

from .. import failures
from ..domain import ids
from .values import _json, _turn_status, epoch, error_shape, normalize


def detect(row) -> dict | None:
    """A failed turn this tool is willing to recover, or None.

    `unknown` and every terminal category stop here: they are never registered, so
    they can never be retried by a later change somewhere else in the pipeline.
    """
    normalized = normalize(row)
    if (normalized is None or normalized["status"] != "failed"
            or not failures.is_recoverable(normalized["category"] or "")
            or normalized["completed_at"] is None):
        return None
    normalized["interruption_id"] = ids.interruption_id(
        *(normalized[k] for k in ("thread_id", "turn_id", "completed_at", "ordinal")))
    return normalized


def _needing(row, kinds):
    """A failed turn whose category is one of `kinds`, normalized as `detect` normalizes one and with
    the id it would have - or None. Never passed to `detect`, and never registered."""
    normalized = normalize(row)
    if (normalized is None or normalized["status"] != "failed"
            or normalized["category"] not in kinds or normalized["completed_at"] is None):
        return None
    normalized["interruption_id"] = ids.interruption_id(
        *(normalized[k] for k in ("thread_id", "turn_id", "completed_at", "ordinal")))
    return normalized


def judge(row, needs_you=frozenset(), admissible=False, shapes=False) -> dict | None:
    """One failed latest turn as HistoryMixin.latest_failures brings it, or None: `detect`'s, else - from the
    same read - one of the `needs_you` kinds, else one the plug may take up (`admissible`), marked so; and with
    `shapes`, its error's shape (failures.shape), never a word of a message."""
    eligible = detect(dict(row))
    if eligible is None and needs_you:
        eligible = _needing(dict(row), needs_you)
    if eligible is None and admissible:
        eligible = _needing(dict(row), failures.ADMISSIBLE)
    if eligible is not None and admissible and eligible["category"] in failures.ADMISSIBLE:
        eligible["admissible"] = True
    if eligible is not None and shapes:
        eligible["shape"] = error_shape(dict(row))
    return eligible


def later_turn(row) -> dict:
    """One turn after the failed one, as HistoryMixin.later_turns classifies it: ours, someone else's, or not
    yet knowable - booleans and ids only."""
    status = _turn_status(row["status"])
    if row["first_is_ours"]:
        kind, reason = "ours", None
    elif not row["has_first"] and status == "inProgress":
        kind, reason = "undetermined", None
    elif not row["has_first"]:
        kind, reason = "foreign", "turn_without_user_item"
    else:
        kind, reason = "foreign", "later_turn_exists"
    return {"turn_id": row["turn_id"] if ids.is_uuid(row["turn_id"]) else None,
            "ordinal": row["rollout_ordinal"], "status": status, "kind": kind, "reason": reason}


def marker_row(row, marker) -> dict | None:
    """One history row holding our marker, as HistoryMixin.marker_rows gives it - None where its message
    is not ours after all."""
    payload = _json(row["item_json"])
    if not _item_is_ours(payload, marker):
        return None
    client = payload.get("clientId")
    ordinal = row["rollout_ordinal"]
    return {
        "turn_id": row["turn_id"] if ids.is_uuid(row["turn_id"]) else None,
        "ordinal": ordinal if type(ordinal) is int else None,
        "status": _turn_status(row["status"]),
        # A row whose turn is not projected yet cannot say who started it.
        "first_unset": bool(row["first_unset"]) or type(ordinal) is not int,
        "starts_turn": bool(row["starts_turn"]),
        "client_id": client if ids.is_client_id(client) else None,
    }


def admissible(row) -> dict | None:
    """A failed turn of a kind the standard edition never recovers alone and the edition's plug may
    take up (failures.ADMISSIBLE, domain/plug.py P17), as `detect` has a failure, or None. Registered
    only once the plug took it up, and checked again with this, never `detect`, before it is sent."""
    return _needing(row, failures.ADMISSIBLE)


def _content_has_marker(content, marker):
    return isinstance(content, list) and any(
        isinstance(item, dict) and item.get("type") == "text"
        and isinstance(item.get("text"), str) and marker in item["text"]
        for item in content)


def _queue_has_marker(payload, marker):
    if not isinstance(payload, dict):
        return False
    # TurnInput's serde shape is version-pinned; unknown shapes fail closed.
    # protocol/src/turn_input.rs derives serde without tag/rename attributes:
    # {"UserInput": {"content": [...], "client_id": ...}}.
    content = payload.get("UserInput")
    if not (set(payload) == {"UserInput"} and isinstance(content, dict)):
        return False
    if ids.is_marker(marker):
        return _content_has_marker(content.get("content"), marker)
    # A marker-free continuation (v0.6.11, domain/plug.py P15) is ours by the client id it was
    # queued under, and by nothing in its words.
    return content.get("client_id") == marker


def _item_is_ours(payload, proof):
    """Whether a history row's user message is our continuation: it carries our marker in its
    words, or - sent with none (P15) - Codex keeps our client id on it as `clientId`."""
    if not (isinstance(payload, dict) and payload.get("type") == "userMessage"):
        return False
    if ids.is_marker(proof):
        return _content_has_marker(payload.get("content"), proof)
    return payload.get("clientId") == proof


def _choose_reset(buckets, completed_at):
    blocked = []
    ambiguity = False
    for bucket, limits in buckets.items():
        has_window = False
        for name in ("primary", "secondary"):
            window = limits.get(name)
            if not isinstance(window, dict):
                continue
            used, reset = window.get("used_percent"), window.get("resets_at")
            if type(used) not in (int, float) or not math.isfinite(used) or used < 0:
                continue
            has_window = True
            if used >= 100:
                if epoch(reset) and reset >= completed_at:
                    blocked.append((reset, bucket + ":" + name))
                else:
                    ambiguity = True
        if not has_window:
            ambiguity = True
    if blocked:
        reset, limit = max(blocked)
        return {"reset_at": reset, "limit_type": limit, "uncertain": ambiguity or len(blocked) > 1}
    # Actual sample is codex primary=98%, immediately followed by premium=null.
    # Preserve its corroborating reset ONLY when its own usage is high enough to
    # plausibly be the block; a low-usage window's far-future reset must not delay
    # the first eligibility check. A fresh live availability check is still required.
    primary = buckets.get("codex", {}).get("primary")
    if isinstance(primary, dict):
        used = primary.get("used_percent")
        reset = primary.get("resets_at")
        if (type(used) in (int, float) and math.isfinite(used) and used >= 90
                and epoch(reset) and reset >= completed_at):
            return {"reset_at": reset, "limit_type": "codex:primary_hint", "uncertain": True}
    return {"reset_at": None, "limit_type": "unknown", "uncertain": True}
