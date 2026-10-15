# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""Proactive usage, near a limit (v0.6.16-beta.3, issue #29): the usage meter, and the wrap-up and the pause that
need it.

The standard edition reads usage only when a recovery is due (C9), so near a limit it knows nothing until a turn
fails at it. Three capabilities, each off until a person turns it on:

* usage_meter (P8) - while the Codex app runs, reads usage on its own every POLL_MINUTES the person chose (5 to
  60, 15 by default), through one finite session of its own asking account/rateLimits/read alone, and keeps the
  windows as core keeps a reading (state/meter.py). The tooltip and the popup show it (surfaces.meter_view); and
  when the five-hour or the weekly window reaches the person's warning percentage (85 by default), a notice is shown
  once for that window - once for each reset, across restarts. It never satisfies core's usage gate: core reads its
  own live usage when a recovery is due, and nothing core decides reads this.
* usage_wrap_up (P8, P2), which requires the meter - at the person's wrap-up percentage of a window (90 by default),
  each conversation switched on whose latest turn is running is sent one message of the edition's own, once for
  that window: its words the person's choice of three (short, standard, detailed), a P2 WRAP_UP record core queues
  through `codex queue` as every continuation goes, so Codex delivers it when the running turn ends - and only while
  that turn is still the latest and still running (core's engine/plugrecords.py). The key is the conversation, the
  window and its reset (continued.answer_key), kept in `continuations`, so one window is answered once.
* usage_pause (P8, P3), which requires the meter - at the person's pause percentage of a window (95 by default), no
  further continuation from this product until that window resets: core's records wait at their gates (HOLD), and
  the edition's own continuations are not handed to core (`holds`, runtime.records). A person's own messages - a
  queued prompt, a message at a reset - and anything they type in Codex are not touched, nor is a wrap-up. The pause
  is marked on the window's row, so a restart keeps it, and it lets go when the window resets - its reset time
  passed, or a reading shows the window reset early and below the percentage.

The five-hour window is any bucket's 300-minute window, the weekly one any bucket's 10080-minute window; each stage
reads each window on its own percentage.
"""
from __future__ import annotations

from codex_auto_resume.domain.plug import DEFER, Alternative
from codex_auto_resume.domain.plughands import RECORDS_LIMIT, Widening

from codex_auto_resume import continuation, settings

from ..codex import credits, inuse
from ..codex.turns import Turns
from ..vocabulary import ContinuationKind, ContinuationReason, OptionKey, RecordState, WordingKey
from .continued import answer_key, handed
from .wrapwords import ON, SWITCH, DEFAULT_STYLE, STYLE_KEYS, STYLES, render  # noqa: F401 - the registry's, the tests'

METER, WRAP_UP, PAUSE = "usage_meter", "usage_wrap_up", "usage_pause"
# Recover every conversation (engine/everyconversation.py): while it is on, core takes up P19's widening, and so does
# the wrap-up - never more than core would recover.
EVERY_CONVERSATION = "every_conversation"
FIVE_HOUR, WEEKLY = 300, 10080
WINDOWS = (FIVE_HOUR, WEEKLY)
# The choices a person picks from: the meter's spacing in minutes, a percentage, the wrap-up's wording.
POLL_CHOICES = (5, 10, 15, 20, 30, 45, 60)
DEFAULT_POLL = 15
PERCENTS = (50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 96, 97, 98, 99)
DEFAULT_WARN, DEFAULT_WRAP, DEFAULT_PAUSE = 85, 90, 95
# v0.6.16-beta.4: the stop percentage the wrap-up's words ask Codex to stop at (wrapwords.py), each window its own.
DEFAULT_STOP_WORDS = 95
STOP_WORDS_OPTIONS = {FIVE_HOUR: OptionKey.STOP_WORDS_FIVE_HOUR, WEEKLY: OptionKey.STOP_WORDS_WEEKLY}
# (e): each window acted on or not - the meter's own choice, which the warning, the wrap-up and the stop each follow.
WINDOW_OPTIONS = {FIVE_HOUR: OptionKey.WINDOW_FIVE_HOUR, WEEKLY: OptionKey.WINDOW_WEEKLY}
# (b): the wrap-up's Custom text for each window (state `wordings`).
CUSTOM_WORDINGS = {FIVE_HOUR: WordingKey.WRAP_CUSTOM_FIVE_HOUR, WEEKLY: WordingKey.WRAP_CUSTOM_WEEKLY}
# Each capability's percentage option for each window.
STAGE_OPTIONS = {METER: {FIVE_HOUR: OptionKey.WARN_FIVE_HOUR, WEEKLY: OptionKey.WARN_WEEKLY},
                 WRAP_UP: {FIVE_HOUR: OptionKey.WRAP_FIVE_HOUR, WEEKLY: OptionKey.WRAP_WEEKLY},
                 PAUSE: {FIVE_HOUR: OptionKey.PAUSE_FIVE_HOUR, WEEKLY: OptionKey.PAUSE_WEEKLY}}
# A reading older than this is not acted on by the wrap-up: two of the longest spacings.
FRESH = 2 * 60 * max(POLL_CHOICES)
# A window is past its reset this long after the reset time (engine/resetwatch.CLOSE_AFTER).
CLOSE_AFTER = 60
# How long after a warning its notice is shown (the tray takes it from the next tick's surface).
NOTICE_FOR = 900
# The wrap-up looks at most once a minute.
LOOK_EVERY = 60


def percent(options, capability, minutes) -> int | None:
    """The percentage a capability's stage acts at for a window of `minutes`, from its options, or None."""
    key = STAGE_OPTIONS.get(capability, {}).get(minutes)
    value = options.get(key) if key is not None else None
    return value if type(value) is int else None


def reached(row, threshold, now) -> bool:
    """Whether a window's row is at or over `threshold` with its reset still ahead (and known)."""
    return (threshold is not None and row["used_percent"] >= threshold and type(row["reset_at"]) is int
            and now < row["reset_at"] + CLOSE_AFTER)


def windows(rows):
    """The rows of the five-hour and the weekly windows, any bucket's."""
    return [row for row in rows.values() if row["minutes"] in WINDOWS]


def acting(meter_options) -> frozenset:
    """The windows a person lets these capabilities act on (v0.6.16-beta.4, item (e)): each one switched on in the
    meter's choices - both by default. Both off, the meter still reads and shows usage, and nothing acts."""
    return frozenset(minutes for minutes, key in WINDOW_OPTIONS.items() if meter_options.get(key, ON) == ON)


def _acting(scoped) -> frozenset:
    """The windows acted on, as the meter's choices say; every window where they cannot be read."""
    try:
        return acting(scoped.options_of(METER))
    except Exception:
        return frozenset(WINDOWS)


class _Errand:
    __slots__ = ("code",)

    def __init__(self, code):
        self.code = code

    def run(self, guard):
        return self.code.look()


# ---------------------------------------------------------------------------- the meter
class UsageMeter:
    """usage_meter's code: its P8 errand. `session` and `app_running` are seams a test fills."""
    __slots__ = ("paths", "_scoped", "_session", "_app_running", "_looked")

    def __init__(self, paths, *, session=None, app_running=None):
        self.paths = paths
        self._scoped = None
        self._session = session
        self._app_running = app_running
        self._looked = None

    def bind(self, scoped):
        self._scoped = scoped

    def tick(self, view):
        scoped = self._scoped
        if scoped is None:
            return DEFER
        try:
            spacing = scoped.options().get(OptionKey.POLL_MINUTES, DEFAULT_POLL) * 60
            now = scoped.now()
            read = [row["read_at"] for row in scoped.meter.rows().values()]
        except Exception:
            return DEFER
        last = max([*read, self._looked or 0]) if (read or self._looked) else None
        if last is not None and 0 <= now - last < spacing:
            return DEFER
        return _Errand(self)

    def _running(self) -> bool:
        """Whether the Codex app runs now: the meter reads only then (core's pairing, through the backend)."""
        if self._app_running is not None:
            return self._app_running() is True
        try:
            return inuse.backend(self.paths).app_identity() is not None
        except Exception:
            return False

    def _read(self):
        """One usage read through a finite session of the meter's own: the windows core keeps, or None."""
        if self._session is not None:
            opened = self._session()
        else:
            from ..codex.protocol import Session
            opened = Session(inuse.backend(self.paths), capability=METER)
        with opened as session:
            return credits.parse(session.call(credits.READ, {}))["windows"]

    def look(self):
        scoped = self._scoped
        handle = scoped.meter
        if not handle.on():
            return None
        now = scoped.now()
        if not self._running():
            return None
        self._looked = now
        try:
            found = self._read()
        except Exception:
            found = None
        if found is None:
            self._count("unreadable")
            return None
        handle.save(found)
        self._count("read")
        options = scoped.options()
        on = acting(options)
        for row in windows(handle.rows()):
            if row["minutes"] not in on:
                continue                                   # (e) a window switched off: shown, never warned of
            if reached(row, percent(options, METER, row["minutes"]), now) and row["warned_reset_at"] != row["reset_at"]:
                if handle.mark(row["bucket"], row["minutes"], warned_reset_at=row["reset_at"]):
                    self._count("warned")
        return None

    def _count(self, code) -> None:
        try:
            self._scoped.count(code)
        except Exception:
            pass


# ---------------------------------------------------------------------------- the wrap-up
class UsageWrapUp:
    """usage_wrap_up's code: at P8 the conversations to ask, at P2 the messages waiting."""
    __slots__ = ("paths", "_scoped", "_home", "_looked", "_turn")

    def __init__(self, paths, *, home=None):
        self.paths = paths
        self._scoped = None
        self._home = home
        self._looked = None
        self._turn = 0

    def bind(self, scoped):
        self._scoped = scoped

    def _codex_home(self):
        return self._home if self._home is not None else inuse.home(self.paths)

    def _source(self):
        """Core's own reader of the Codex home, judging a conversation as core does (codex/history._eligibility): a
        person's own - or, while Recover every conversation is on, P19's widening - and never a kind Codex makes for
        itself (a subagent, a review, a memory pass, an agent-made conversation). Its `latest` is None for any other."""
        from codex_auto_resume.codex import LocalSource
        source = LocalSource(self._codex_home())
        try:
            widened = self._scoped.armed(EVERY_CONVERSATION) is True
        except Exception:
            widened = False
        source.widened = frozenset({Widening.EVERY_DESKTOP}) if widened else frozenset()
        return source

    def tick(self, view):
        scoped = self._scoped
        if scoped is None:
            return DEFER
        now = scoped.now()
        if self._looked is not None and 0 <= now - self._looked < LOOK_EVERY:
            return DEFER
        self._looked = now
        try:
            self._look(view, now)
        except Exception:
            pass
        return DEFER

    def _look(self, view, now) -> None:
        scoped = self._scoped
        handle = scoped.continuations
        if not handle.on():
            return
        options = scoped.options()
        on = _acting(scoped)
        due = [row for row in windows(scoped.meter.rows()) if row["minutes"] in on
               and now - row["read_at"] <= FRESH and reached(row, percent(options, WRAP_UP, row["minutes"]), now)]
        if not due:
            return
        # v0.6.16-beta.4: the words of each window due - with the numbers where that wording is chosen - in the
        # continuation language, made once a look (wrapwords.render).
        try:
            locale = continuation.resolve_locale(settings.load(self.paths.settings_file))
        except Exception:
            locale = None
        try:
            custom = scoped.wordings()
        except Exception:
            custom = {}
        worded = []
        for row in due:
            words = render(style=options.get(OptionKey.WRAP_STYLE, DEFAULT_STYLE), minutes=row["minutes"],
                           used=row["used_percent"], locale=locale,
                           stop_at=options.get(STOP_WORDS_OPTIONS[row["minutes"]], DEFAULT_STOP_WORDS),
                           reset_at=row["reset_at"], include_reset=options.get(OptionKey.WRAP_RESET_TIME, ON) == ON,
                           custom=custom.get(CUSTOM_WORDINGS.get(row["minutes"])))
            if words is not None:
                worded.append((row, words))
        if not worded:
            return
        turns = Turns(self._codex_home())
        source = self._source()
        for thread in turns.running():
            try:
                if view.thread_enabled(thread) is not True or source.latest(thread) is None:
                    continue                    # switched off, or not a conversation core would recover
                turn = turns.latest(thread)
            except Exception:
                continue
            if turn is None or turn.status != "inProgress":
                continue
            for row, words in worded:
                key = answer_key(WRAP_UP, thread, row["bucket"], row["minutes"], row["reset_at"])
                if handle.get(key) is None and handle.add(key, ContinuationKind.WRAP_UP, thread, words,
                                                          ordinal=turn.ordinal):
                    self._count("found")

    def records(self, view):
        """P2: every wrap-up waiting, with its words. One in flight is the runtime's to hand."""
        scoped = self._scoped
        if scoped is None:
            return DEFER
        try:
            rows = scoped.continuations.mine()
        except Exception:
            return DEFER
        waiting = [row for row in rows if row["record_state"] == RecordState.WAITING]
        if waiting:
            waiting = self._still_due(waiting)
        found = [record for record in (handed(row) for row in waiting) if record is not None]
        # Core tries RECORDS_LIMIT a tick: past it, those waiting are handed from a place that moves on each tick, so
        # none waits behind the others for good (as engine/resetmessage.py hands its messages).
        if len(found) > RECORDS_LIMIT:
            start = (self._turn * RECORDS_LIMIT) % len(found)
            found = found[start:] + found[:start]
            self._turn += 1
        return found or DEFER

    def _still_due(self, waiting) -> list:
        """The waiting ones whose conversation core would still recover and whose turn is still the latest and still
        running; every other one ends superseded here - core would keep it waiting for good (not a conversation it
        takes up) or drop it (its turn moved on), and either way it would take a place among core's few a tick.
        Where Codex's files cannot be read now, each is left as it is, for the next tick."""
        try:
            source = self._source()
        except Exception:
            return waiting
        kept, ended = [], set()
        for row in waiting:
            thread = row["thread_id"]
            try:
                latest = source.latest(thread)
            except Exception:
                kept.append(row)
                continue
            if (latest is not None and latest.get("ordinal") == row["ordinal"]
                    and latest.get("status") == "inProgress"):
                kept.append(row)
            elif thread not in ended:
                ended.add(thread)
                try:
                    self._scoped.continuations.end(ContinuationReason.SUPERSEDED, thread_id=thread)
                except Exception:
                    pass
        return [row for row in kept if row["thread_id"] not in ended]

    def _count(self, code) -> None:
        try:
            self._scoped.count(code)
        except Exception:
            pass


# ---------------------------------------------------------------------------- the pause
class UsagePause:
    """usage_pause's code: at P8 the windows it holds for marked and let go, at P3 HOLD while one holds, and
    `holds` for the edition's own continuations (runtime.records)."""
    __slots__ = ("paths", "_scoped")

    def __init__(self, paths):
        self.paths = paths
        self._scoped = None

    def bind(self, scoped):
        self._scoped = scoped

    def tick(self, view):
        scoped = self._scoped
        if scoped is None:
            return DEFER
        try:
            handle = scoped.meter
            if not handle.on():
                return DEFER
            now = scoped.now()
            options = scoped.options()
            on = _acting(scoped)
            for row in windows(handle.rows()):
                # (e) a window switched off is never held, and one held lets go when it is switched off.
                acted = row["minutes"] in on
                over = acted and reached(row, percent(options, PAUSE, row["minutes"]), now)
                held = row["paused_reset_at"]
                if over and held != row["reset_at"]:
                    if handle.mark(row["bucket"], row["minutes"], paused_reset_at=row["reset_at"]):
                        self._count("paused")
                elif held is not None and not over and (not acted or held != row["reset_at"]
                                                         or now >= held + CLOSE_AFTER):
                    if handle.mark(row["bucket"], row["minutes"], clear_pause=True):
                        self._count("resumed")
        except Exception:
            pass
        return DEFER

    def holding(self) -> bool:
        """Whether a window the pause marked has not reset yet - its reset time not yet passed."""
        scoped = self._scoped
        if scoped is None:
            return False
        now = scoped.now()
        return any(row["paused_reset_at"] is not None and now < row["paused_reset_at"] + CLOSE_AFTER
                   for row in windows(scoped.meter.rows()))

    def gate(self, name, record, facts):
        """P3: HOLD a record of core's while a window holds; nothing for anything else."""
        if not isinstance(record, dict) or "interruption_id" not in record:
            return DEFER
        try:
            return Alternative.HOLD if self.holding() else DEFER
        except Exception:
            return DEFER

    def holds(self, record) -> bool:
        """Whether a record of the edition's own is held back from core this tick: a continuation waiting -
        never a person's message, never a wrap-up, never one already in flight."""
        if not (isinstance(record, dict) and record.get("state") == "waiting"
                and record.get("purpose") == "continuation"):
            return False
        try:
            return self.holding()
        except Exception:
            return False

    def _count(self, code) -> None:
        try:
            self._scoped.count(code)
        except Exception:
            pass


def previews(state, now) -> dict:
    """What the wrap-up would send for each window now, exactly (v0.6.16-beta.4, item (a)): its wording, numbers,
    reset time and Custom words as they stand, in the continuation language - for the page to show under the choice.
    Of the meter's last reading of that window where there is one, else as if the window had just reached the wrap-up
    percentage, resetting a window's length from now. {minutes: words or None}."""
    try:
        options, custom = state.options(WRAP_UP), state.wordings(WRAP_UP)
        rows = {}
        for row in windows(state.meter()):
            rows.setdefault(row["minutes"], row)
    except Exception:
        return {}
    try:
        locale = continuation.resolve_locale(settings.load(state.paths.settings_file))
    except Exception:
        locale = None
    found = {}
    for minutes in WINDOWS:
        row = rows.get(minutes)
        live = row is not None and type(row["reset_at"]) is int and row["reset_at"] > now
        found[minutes] = render(
            style=options.get(OptionKey.WRAP_STYLE, DEFAULT_STYLE), minutes=minutes, locale=locale,
            used=row["used_percent"] if live else options.get(STAGE_OPTIONS[WRAP_UP][minutes], DEFAULT_WRAP),
            stop_at=options.get(STOP_WORDS_OPTIONS[minutes], DEFAULT_STOP_WORDS),
            reset_at=row["reset_at"] if live else int(now) + minutes * 60,
            include_reset=options.get(OptionKey.WRAP_RESET_TIME, ON) == ON, custom=custom.get(CUSTOM_WORDINGS[minutes]))
    return found


def make_meter(paths) -> UsageMeter:
    return UsageMeter(paths)


def make_wrap_up(paths) -> UsageWrapUp:
    return UsageWrapUp(paths)


def make_pause(paths) -> UsagePause:
    return UsagePause(paths)
