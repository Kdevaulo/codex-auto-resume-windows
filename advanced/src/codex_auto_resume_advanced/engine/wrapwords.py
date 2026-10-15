# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""The wrap-up's words (v0.6.16-beta.4, the owner's additions to issue #29): what usage_wrap_up sends, exactly.

A person picks the wording (OptionKey.WRAP_STYLE): 1 short, 2 standard, 3 detailed - the edition's fixed words - 4
with the numbers: "You have used 90% of the five-hour limit. Get ready to stop safely, and stop when it reaches 95%." -
or 5 Custom: the person's own text for each window (state `wordings`, WordingKey), checked as the custom continuation
text is (check_custom) and never logged, which gets the numbers and the reset only where it writes {percent},
{window}, {stop_at} or {reset}; a window with no Custom text of its own is sent the standard wording.
The numbers are said of the window that triggered it - "the five-hour limit" or "this week's limit" - and every wording
is in the continuation language (core's continuation.resolve_locale), not the window's.

Include the reset time (OptionKey.WRAP_RESET_TIME, on by default) adds when the window that triggered it resets - "The
limit resets at 15:20." for the five-hour window, a date and a time for the weekly one - as core says a reset time.

The stop percentage the words name is the wrap-up's own (OptionKey.STOP_WORDS_*): a request to Codex, apart from the
forced stop's percentage (usage_pause), and written whether or not the forced stop is on.

`render` is the one place the words are made, so what the page shows under the choice is what is sent.
"""
from __future__ import annotations

import re
import time

from codex_auto_resume import continuation
from codex_auto_resume.domain import ids

from .. import statement

FIVE_HOUR, WEEKLY = 300, 10080
STYLE_KEYS = {1: "continue.wrap_up.short", 2: "continue.wrap_up.standard", 3: "continue.wrap_up.detailed",
              4: "continue.wrap_up.numbers"}
CUSTOM_STYLE = 5
STYLES = tuple(STYLE_KEYS) + (CUSTOM_STYLE,)
DEFAULT_STYLE = 2
# v0.6.16-beta.4 (b): the placeholders Custom text may write - and nothing else in braces.
PLACEHOLDERS = ("percent", "window", "stop_at", "reset")
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_CONTROLS = ("\t", "\n", "\r")
WINDOW_KEYS = {FIVE_HOUR: "continue.wrap_up.window.five_hour", WEEKLY: "continue.wrap_up.window.weekly"}
# v0.6.16-beta.4 (i): the sentence Include the reset time adds, and how a weekly reset's date is said.
RESET_KEYS = {FIVE_HOUR: "continue.wrap_up.resets_at", WEEKLY: "continue.wrap_up.resets_on"}
DATE_KEY = "continue.wrap_up.date"
# A switch's two values, as every on/off choice of these capabilities stores it.
ON, OFF = 1, 2
SWITCH = (ON, OFF)


class WordingError(ValueError):
    """Why a Custom wording is refused: one closed word - empty, too_long, control, marker or placeholder."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def check_custom(text) -> str:
    """A person's Custom wording, unchanged, or WordingError: the custom continuation text's rules - text of 1 to
    continuation.MAX_CUSTOM_LENGTH characters, not blank, no control character but a tab and the ends of a line, no
    marker of this product's - and braces only around the four placeholders."""
    if not isinstance(text, str) or not text.strip():
        raise WordingError("empty")
    if len(text) > continuation.MAX_CUSTOM_LENGTH:
        raise WordingError("too_long")
    if any(ord(character) < 32 and character not in _CONTROLS for character in text) or "\x7f" in text:
        raise WordingError("control")
    if ids.MARKER_PREFIX in text:
        raise WordingError("marker")
    rest = _PLACEHOLDER.sub(lambda found: "" if found.group(1) in PLACEHOLDERS else "{", text)
    if "{" in rest or "}" in rest:
        raise WordingError("placeholder")
    return text


def window_words(minutes, locale) -> str | None:
    """How the words name the window of `minutes`: "the five-hour limit", "this week's limit"."""
    key = WINDOW_KEYS.get(minutes)
    return None if key is None else statement.CATALOGS.text(key, locale)


def reset_words(reset_at, minutes, locale) -> str | None:
    """When a window resets, as the words say it: core's local hour and minute (continuation.format_reset_time) for the
    five-hour window, the date before it for the weekly one - or None where the reset is not known."""
    if type(reset_at) is not int:
        return None
    hour = continuation.format_reset_time(reset_at)
    if hour is None or minutes != WEEKLY:
        return hour
    moment = time.localtime(reset_at)
    return statement.CATALOGS.text(DATE_KEY, locale, time=hour, month=moment.tm_mon, day=moment.tm_mday)


def render(*, style, minutes, used, stop_at, locale, reset_at=None, include_reset=False, custom=None) -> str | None:
    """The words sent for a window of `minutes` at `used` percent, asking Codex to stop at `stop_at` percent - and,
    with `include_reset`, when that window resets at `reset_at` - or None where they cannot be made (a window this does
    not know, or words core would refuse as a continuation)."""
    window = window_words(minutes, locale)
    if window is None or type(stop_at) is not int:
        return None
    try:
        fields = {"percent": int(used), "window": window, "stop_at": stop_at}
    except (TypeError, ValueError):
        return None
    if style == CUSTOM_STYLE and isinstance(custom, str):
        try:
            check_custom(custom)
        except WordingError:
            return None
        filled = dict(fields, reset=reset_words(reset_at, minutes, locale) or "")
        words = _PLACEHOLDER.sub(lambda found: str(filled[found.group(1)]), custom)
    else:
        style = DEFAULT_STYLE if style == CUSTOM_STYLE else style
        words = statement.CATALOGS.text(STYLE_KEYS.get(style, STYLE_KEYS[DEFAULT_STYLE]), locale, **fields)
        reset = reset_words(reset_at, minutes, locale) if include_reset else None
        if words and reset:
            words = words + " " + statement.CATALOGS.text(RESET_KEYS[minutes], locale, reset=reset)
    try:
        return continuation.validate_continuation(words)
    except Exception:
        return None
