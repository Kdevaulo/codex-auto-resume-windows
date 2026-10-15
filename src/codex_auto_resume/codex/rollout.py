"""A conversation's rollout file, read no further than this product needs (v0.6.16-beta.3).

Four readings, none of them a statement to a database - codex/history.py keeps every one:

    confined       which file a `threads` row's path names, if it is that conversation's in the sessions folder
    session_meta   the file's first line: who the conversation says it is
    continued_id   the id Codex records the conversation's turns under, where it split them
    reset_scan     the rate-limit snapshots just before a usage-limit failure, for the reset hint

The split is Codex's (openai/codex#43422, this project's issue #30): the `threads` row keeps the
conversation's id A, but its current file is named `..._A_B.jsonl` and its turns are projected under B,
which has no row of its own. Whether B is taken is history.py's (`_follow`), with every guard; this only
reads the name.
"""
from __future__ import annotations

from pathlib import Path
import re

from ..domain import ids
from .paths import _safe_path
from .payload import _choose_reset
from .values import MAX_ITEM_BYTES, MAX_META_BYTES, MAX_SCAN_BYTES, _json

UNKNOWN_RESET = {"reset_at": None, "limit_type": "unknown", "uncertain": True}


def confined(home, thread_id, raw):
    """`raw`, the rollout path Codex's `threads` row names, as a Path if it is this conversation's file in the
    Codex home `home`'s sessions folder: a .jsonl file whose name holds the id. None for anything else, which
    is then neither opened nor asked about."""
    if not ids.is_uuid(thread_id) or not isinstance(raw, str):
        return None
    path = _safe_path(Path(raw))
    if (not path.is_relative_to(_safe_path(Path(home) / "sessions"))
            or path.suffix != ".jsonl" or thread_id not in path.name):
        return None
    return path


def session_meta(path) -> dict | None:
    """The payload of the file's first line where it is a session_meta event, or None. An OSError is the
    caller's: a file that cannot be opened now is not a file that says nothing."""
    with path.open("rb") as stream:
        first = stream.readline(MAX_META_BYTES + 1)
    if len(first) > MAX_META_BYTES or not first.endswith(b"\n"):
        return None
    try:
        event = _json(first.decode("utf-8"))
    except UnicodeError:
        return None
    if not isinstance(event, dict) or event.get("type") != "session_meta":
        return None
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else None


def continued_id(thread_id, name) -> str | None:
    """B, where the file name `name` ends exactly in `<thread_id>_<B>.jsonl` and B is another id; else None."""
    if not ids.is_uuid(thread_id) or not isinstance(name, str):
        return None
    found = re.search(r"(?:^|[-_])%s_(%s)\.jsonl\Z" % (re.escape(thread_id), ids.uuid_pattern(any_case=True)), name)
    other = found.group(1) if found else None
    return other if other is not None and ids.is_uuid(other) and other != thread_id else None


def reset_scan(path, end, turn_id, completed_at) -> dict:
    """The reset hint of the usage-limit failure of `turn_id`, whose event ends at byte `end` of `path`: the
    rate-limit snapshots before it, chosen as payload._choose_reset chooses - or UNKNOWN_RESET."""
    if type(end) is not int or end <= 0:
        return dict(UNKNOWN_RESET)
    try:
        # The verified end offset is immediately after the failure event.
        # Never include a subsequent turn's unrelated rate-limit snapshot.
        with path.open("rb") as stream:
            start = max(0, end - MAX_SCAN_BYTES)
            stream.seek(start)
            if start:
                stream.readline(MAX_ITEM_BYTES + 1)
            remaining = end - stream.tell()
            if remaining <= 0:
                return dict(UNKNOWN_RESET)
            data = stream.read(min(MAX_SCAN_BYTES, remaining))
    except (OSError, ValueError):
        return dict(UNKNOWN_RESET)
    buckets = {}
    found = False
    for line in data.splitlines():
        if len(line) > MAX_ITEM_BYTES:
            continue
        try:
            event = _json(line.decode("utf-8"))
        except UnicodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "event_msg":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("type") == "task_complete" and payload.get("turn_id") == turn_id:
            error = payload.get("error")
            found = isinstance(error, dict) and error.get("codex_error_info") == "usage_limit_exceeded"
            break
        if payload.get("type") == "token_count":
            limits = payload.get("rate_limits")
            if isinstance(limits, dict):
                bucket = limits.get("limit_id")
                if isinstance(bucket, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", bucket):
                    buckets[bucket] = limits
    return _choose_reset(buckets, completed_at) if found else dict(UNKNOWN_RESET)
