"""What the icon says: its tooltip, and how much of one Windows will take.

Pure - it asks Windows nothing. The countdown is `ui/words.py`'s, shared with the popup and
the notification card, so that "3m 20s" is spelled one way wherever this product writes it.
"""
from __future__ import annotations

from ..words import LOW_LEFT, countdown, left, share, window_name  # noqa: F401


TIP_CHARS = 128

# v0.6.14: the edition no surface names beside the version or the product (the owner, 2026-10-05: "no
# Standard label in the standard edition"). The status still carries its code; only the word is not shown.
UNNAMED_EDITION = "standard"


def tooltip_parts(snapshot: dict, strings: dict, now: float, edition: str | None = None) -> dict:
    """What hovering over the icon says, in its parts (v0.6.24): what the icon's drawn card shows (tipplan.py), and
    what `tooltip` joins into the one text Windows is given. The same facts, no new ones, and never cut short: only
    szTip has a length.

    `title` is the product's name; `edition` the catalog's word for an advanced edition that runs (edition.shown),
    None for the standard one or none (v0.6.14); `line` the state line as (text, is_countdown) pieces, the one piece
    that counts down to the next check marked; `meter` the advanced edition's usage windows (meter_rows), empty
    without them. An empty snapshot (before the first tick) has no line."""
    title = strings.get("tray.title", "Codex Auto Resume")
    named = strings.get("edition." + edition, edition) if edition and edition != UNNAMED_EDITION else None
    parts = {"title": title, "edition": named, "line": [], "meter": []}
    if not snapshot:
        return parts
    if snapshot.get("failed"):
        line = [(strings.get("tray.failed", "A recovery failed"), False)]
    elif snapshot.get("unconfirmed"):
        # v0.6.20: a sending nobody has confirmed - the amber light's own word.
        line = [(strings.get("activity.attention", "Needs your attention"), False)]
    elif not snapshot.get("enabled", True):
        line = [(strings.get("tray.paused", "Paused"), False)]
    else:
        waiting, running = snapshot.get("waiting", 0), snapshot.get("running", 0)
        line = []
        if snapshot.get("held"):
            # v0.6.20: and a record waiting for a person: the amber light's own word, before the counts.
            line.append((strings.get("activity.attention", "Needs your attention"), False))
        if running:
            line.append((strings.get("tray.running", "{n} running in Codex").replace("{n}", str(running)), False))
        if waiting:
            line.append((strings.get("tray.waiting", "{n} waiting").replace("{n}", str(waiting)), False))
            due = snapshot.get("next_at")
            if due:
                line.append((strings.get("tray.next", "next check in {time}")
                             .replace("{time}", countdown(due - now)), True))
        if not line:
            line = [(strings.get("tray.idle", "Nothing waiting"), False)]
    parts["line"] = line
    parts["meter"] = meter_rows(snapshot, strings)
    return parts


def tooltip(snapshot: dict, strings: dict, now: float, edition: str | None = None) -> str:
    """What hovering over the icon says. Built from the last tick; counted down locally.

    `edition` is the code of the edition that runs (edition.shown): the title names an advanced one, in the
    catalog's word, as every surface that shows the version does (v0.6.11). The standard edition, or none, and
    the title is the name alone (v0.6.14). Since v0.6.24 the join of `tooltip_parts`, word for word what it was."""
    parts = tooltip_parts(snapshot, strings, now, edition)
    text = tooltip_joined(parts)
    return text[:TIP_CHARS - 1] if parts["line"] else text


def tooltip_joined(parts) -> str:
    """The parts as one text, never cut short: the title (and the edition's word), the state line, the meter - each on a
    line of its own, the pieces of a line joined as the tooltip has always joined them. What the drawn card tells a
    screen reader (tipcard.py), and, cut to szTip's length, what Windows is given."""
    title = parts["title"] + (" · " + parts["edition"] if parts["edition"] else "")
    if not parts["line"]:
        return title
    meter = " · ".join(row["text"] for row in parts["meter"])
    return title + "\n" + " · ".join(text for text, _ in parts["line"]) + ("\n" + meter if meter else "")


# The key a surface puts an edition plug's fields under - domain/plug.EXTRA, which
# tests/test_usage_surfaces.py holds this to: the icon reads that one key and imports nothing of the plug's.
EXTRA = "advanced"
# The words a meter line is said in where the catalog has none (the catalog's own English).
_USAGE_WORDS = {"usage.window": "{window} {percent}% left", "usage.weekly": "weekly", "usage.days": "{n}-day",
                "usage.hours": "{n}-hour", "usage.minutes": "{n}-minute", "usage.limit": "limit"}


def meter_rows(snapshot, strings) -> list:
    """The advanced edition's usage meter, a row per window it last read (v0.6.24, from what was meter_line's): each
    {"label": its length (window_name), "percent": the share left in the catalog's own words, "fraction": how much is
    left, 0 to 1 - a full bar is plenty left, and it empties as the window is used (v0.6.24 final) - "low": whether as
    little is left as LOW_LEFT or less, the warning, and "text": the two as the catalog says them together - "5-hour 13%
    left"}. Only from what the edition's plug added under its one key; the standard edition adds nothing there, so it
    has none."""
    added = snapshot.get(EXTRA) if isinstance(snapshot, dict) else None
    meter = added.get("meter") if isinstance(added, dict) else None
    windows = meter.get("windows") if isinstance(meter, dict) else None
    if not isinstance(windows, list):
        return []

    def say(key, **fields):
        text = strings.get(key) or _USAGE_WORDS.get(key, key)
        for name, value in fields.items():
            text = text.replace("{%s}" % name, str(value))
        return text
    rows = []
    for window in windows:
        if not isinstance(window, dict) or type(window.get("used_percent")) not in (int, float):
            continue
        label, percent = window_name(window.get("window_minutes"), say), left(window)
        # The share left in the catalog's own words - "13% left", "13 % übrig", "%13 kaldı": its sentence with the name
        # taken out.
        alone = say("usage.window", window=_NAME_HELD, percent=percent).replace(_NAME_HELD, "").strip(_ROUND_THE_NAME)
        rows.append({"label": label, "percent": alone, "text": say("usage.window", window=label, percent=percent),
                     "fraction": max(0.0, min(1.0, 1.0 - float(window["used_percent"]) / 100.0)),
                     "low": percent <= LOW_LEFT})
    return rows


# What stands in for a window's name while its share is read out of its sentence, and what is left round the name.
_NAME_HELD, _ROUND_THE_NAME = "\x00", " :  "


def meter_line(snapshot, strings) -> str | None:
    """The advanced edition's usage meter as one line (v0.6.16-beta.3, issue #29): each window it last read, its
    length and its share - "5-hour 87% · weekly 40%", since v0.6.24 final the share left: "5-hour 13% left · weekly 60% left". Only from what the edition's plug added under its one key; the
    standard edition adds nothing there, so its tooltip is what it always was. None where there is nothing to say."""
    return " · ".join(row["text"] for row in meter_rows(snapshot, strings)) or None
