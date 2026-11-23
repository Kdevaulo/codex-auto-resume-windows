# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""The forced stop near a usage limit (v0.6.16-beta.4, item (h) of the owner's additions to issue #29) - usage_pause.

At the stop percentage a person chose for a window (97 by default, each window its own, apart from the stop the
wrap-up's words ask for), the window is held until it resets, as the plain pause held it: core's records wait (HOLD)
and the edition's own continuations are not handed to core. And now each conversation switched on whose turn is
running is stopped - through the Codex app's own channel, the IPC pipe the app's Stop button uses (codex/ipc.py,
measurement MIPC): the stop the person would make, once for that window. It works only for a conversation the app has
open; where it cannot stop one - the app does not hold it, the app is not running, its build checks another version of
the request, it does not answer - it falls back to holding, and a notice says the turn could not be stopped.

A stopped conversation's queue is paused by the app, and the pause survives the app's restart. When the window resets, a conversation it stopped is continued once - Continue after the reset,
the wrap-up's choice, on by default - by a turn started through the same channel (ipc.start_turn), which goes past the
paused queue; only while that turn of the stop is still the conversation's latest, ended, with nothing after it (A17)
and the app holds the conversation (A11). It is kept in `continuations` (ContinuationKind.AFTER_RESET, its window's
length in minutes in `chain`), so a restart forgets nothing; where the app does not hold the conversation it waits, and
a notice says to open it in Codex. That turn is also what lets the queue go: once it completes, the app sends what was
queued and the pause is gone (measured 2026-10-16). Where Continue after the reset is off, nothing will, and a notice
asks the person to press Resume in Codex.

v0.6.26 (R2, review V1): where reset_message is on and the person's own message for that conversation falls due at that
very reset, that turn carries the message's words and its marker instead of the continuation's - the person's message
goes, once, and the turn lets the paused queue go; reset_message leaves such a message to it (resetmessage.carried_by_stop)
rather than queuing it into the paused queue, where it would sit for good. That turn carries it once every window the
stop holds has reset (review4 V1, the owner's answer of 2026-11-23), and the message never expires while it waits.

Every outcome is one closed word, journalled (registry codes); never a conversation's words.
"""
from __future__ import annotations

import contextlib

from codex_auto_resume import continuation, failures, settings
from codex_auto_resume.domain import ids
from codex_auto_resume.domain.plug import DEFER
from codex_auto_resume.domain.plughands import Widening

from .. import statement
from ..codex import inuse, ipc
from ..codex.turns import Turns, booted_of
from ..vocabulary import ContinuationKind, ContinuationReason, OptionKey, RecordState, RuleState
from .continued import answer_key, words_pass
from . import resetwatch
from .resetmessage import ResetMessage
from .usage import AFTER_RESET_KEY, EVERY_CONVERSATION, NOTICE_FOR, ON, WRAP_UP, UsagePause, _reset_since, windows
FINAL = frozenset({"completed", "failed", "interrupted"})
# How many notices the stop keeps for the icon to show (each once in a watcher's life, by its key).
NOTICES_KEPT = 16
# A start after the reset that failed is asked again after this long, doubled at each failure up to BACKOFF_MOST - never
# every tick, each of which may wait for the app's answers.
BACKOFF_SECONDS = 300
BACKOFF_MOST = 3600
# v0.6.26 (audit-advanced2 R2, the owner's answer of 2026-11-22, "the reset message only"): a person's reset message for a
# conversation this stopped, going at the very reset its continuation waits for, goes INSTEAD of that continuation - as
# reset_message's statement promises ("in place of a continuation waiting there for the same reset"). Its code is
# reset_message's (engine/resetmessage.py); MESSAGE_INSTEAD is this capability's journal word for a continuation it ended
# so.
RESET_MESSAGE = "reset_message"
MESSAGE_INSTEAD = "message_instead"
# v0.6.26 (review V1): the core of R2's fix. reset_message's message goes into Codex's queue, which the stop paused, and
# only the turn this capability starts after the reset lets that queue go (MIPC): ending the continuation for it left
# both waiting for good. So the stop's turn after the reset carries the message's words itself, once, in the
# continuation's place (`_carry`), and reset_message leaves such a message to it (resetmessage.carried_by_stop). What
# `_message_instead` finds of one: carried by that turn, gone instead, or sent into the paused queue.
CARRY, INSTEAD, QUEUED, CONTINUE = "carry", "instead", "queued", "continue"
# The app's own answers that the turn was not started: the message waits again with its words.
REFUSED_STARTS = frozenset({ipc.Stop.NO_CLIENT, ipc.Stop.VERSION_MISMATCH, ipc.Stop.REFUSED})


def _time(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _counts_here(rule, window, row, rows, now) -> bool:
    """Whether a counting message falls due at the very reset continuation `row` waits for - by reset_message's own
    guard (resetmessage.ResetMessage._same_reset, review V2): its occasion is the next reset of its window, and the
    window open now resets when that continuation's reset is, not yet HOLD_FOR past. That reset is read from the meter
    (`rows`) as `_reset_since` reads it: the reset it shows where its window was open at the stop, else the start of
    the window it shows, which began after the stop. Or its occasion counted already, by a reset counted since the
    stop - due, marked so at reset_message's next look (resetwatch.due). A rule for a later reset, or one whose
    occasion was counted before the stop, is not this one's."""
    if (window is not None and resetwatch.due(rule, window) and _time(window.get("last_closed_at"))
            and window["last_closed_at"] >= row["created_at"]):
        return True
    found = [meter for meter in windows(rows) if meter["minutes"] == row["chain"]]
    reset = found[0]["reset_at"] if found else None
    if not _time(reset):
        return False
    if reset - row["chain"] * 60 > row["created_at"]:
        reset -= row["chain"] * 60
    return ResetMessage._same_reset(rule, window, {"category": failures.USAGE_LIMIT, "reset_at": reset}, now)


class _StopErrand:
    """P8's errand, run by core last in the tick with its guards (domain/plughands.Errand): the stops due and the
    continuations after a reset, each request to the app written inside one of core's errand guards - so a Pause,
    Observe only, an administrator's DisableAutoResume and quiet hours hold both, as they hold every send."""
    __slots__ = ("code", "view", "targets", "window")

    def __init__(self, code, view, targets, window):
        self.code, self.view, self.targets, self.window = code, view, targets, window

    def run(self, guard):
        targets, window = self.targets, self.window
        # matrix5 M1: the meter's errand may have saved a new reading in this very tick, after P8's tick marked what
        # it read - a window newly over its stop percentage right after a reset. It is marked held here first, and its
        # running turns stopped, so no turn starts into it below (`after_reset` asks holding()).
        try:
            newly = self.code._once(self.code._mark())
        except Exception:
            newly = []
        if newly:
            try:
                targets = list(targets) + [found for found in self.code._running(self.view) if found not in targets]
            except Exception:
                pass
            window = window or newly[0]
        if targets:
            self.code.stop_all(targets, window, guard)
        try:
            self.code.after_reset(self.view, guard)
        except Exception:
            pass
        return None


class UsageStop(UsagePause):
    """usage_pause's code from v0.6.16-beta.4: the pause's holding, and the forced stop and its continuation after
    the reset. `stop`, `start` and `home` are seams a test fills (ipc.stop_turn, ipc.start_turn, the Codex home)."""
    __slots__ = ("_stop", "_start", "_home", "_notices", "_backoff", "_stopped", "_unsure")

    def __init__(self, paths, *, stop=None, start=None, home=None):
        super().__init__(paths)
        self._stop = stop
        self._start = start
        self._home = home
        self._notices = []
        self._backoff = {}                   # {continuation: (failures, when it is asked again)}, in this process
        self._stopped = []                   # the windows stopped, (bucket, minutes, reset_at): once each per reset
        self._unsure = {}                    # {continuation: said}, its carried start perhaps not received (B4)

    # ---------------------------------------------------------------- reading Codex
    def _codex_home(self):
        return self._home if self._home is not None else inuse.home(self.paths)

    def _source(self):
        """Core's reader, judging a conversation as core does - a person's own, or P19's widening while Recover every
        conversation is on - and never a kind Codex makes for itself (as the wrap-up judges one)."""
        from codex_auto_resume.codex import LocalSource
        source = LocalSource(self._codex_home())
        try:
            widened = self._scoped.armed(EVERY_CONVERSATION) is True
        except Exception:
            widened = False
        source.widened = frozenset({Widening.EVERY_DESKTOP}) if widened else frozenset()
        return source

    def _locale(self):
        try:
            return continuation.resolve_locale(settings.load(self.paths.settings_file))
        except Exception:
            return None

    # ---------------------------------------------------------------- P8
    def tick(self, view):
        scoped = self._scoped
        if scoped is None:
            return DEFER
        newly, targets = self._once(self._mark()), []
        if newly:
            try:
                targets = self._running(view)
            except Exception:
                targets = []
        if not targets and not self._waiting():
            return DEFER
        return _StopErrand(self, view, targets, newly[0] if newly else None)

    def _once(self, newly) -> list:
        """The windows newly held that were not stopped already for this reset: a window switched off and on again
        is held again, but a turn the person resumed in it is not stopped a second time."""
        fresh = []
        for row in newly:
            key = (row["bucket"], row["minutes"], row["reset_at"])
            if key not in self._stopped:
                self._stopped.append(key)
                fresh.append(row)
        del self._stopped[:-NOTICES_KEPT]
        return fresh

    def _running(self, view) -> list:
        """(thread, turn) of each conversation switched on, of the kind core recovers, whose latest turn runs."""
        turns, source, found = Turns(self._codex_home()), self._source(), []
        for thread in turns.running(booted=booted_of(self.paths)):
            try:
                if view.thread_enabled(thread) is not True or source.latest(thread) is None:
                    continue
                turn = turns.latest(thread)
            except Exception:
                continue
            if turn is not None and turn.status == "inProgress":
                found.append((thread, turn))
        return found

    def stop_all(self, targets, window, guard=None):
        """The errand: each running turn stopped through the app, inside one of core's guards (`guard`); what came of
        each journalled and, where it matters, said in a notice; each one stopped remembered for its continuation after
        the reset. One the guard refused is not asked, and nothing is said of it."""
        stop = self._stop or ipc.stop_turn
        for thread, turn in targets:
            try:
                word = stop(thread, turn.turn_id, gate=guard)
            except Exception:
                word = ipc.Stop.BROKEN
            if word == ipc.Stop.HELD:
                self._count("held")
                continue
            if word not in (ipc.Stop.STOPPED, ipc.Stop.UNCONFIRMED):
                self._count("not_stopped")
                self._notice("not_stopped", window)
                continue
            # A stop with no answer in time may have been made: kept as one, so the queue the app may have paused is
            # let go by the continuation after the reset, or the person asked to press Resume.
            self._count("stopped" if word == ipc.Stop.STOPPED else "stop_unconfirmed")
            if not self._remember(thread, turn, window):
                # No continuation after the reset will start a turn there, which is what lets the paused queue go.
                self._count("resume_unproven")
                self._notice("press_resume", window)
        return None

    def _continue_on(self) -> bool:
        """Whether Continue after the reset (the wrap-up's choice) is on; off where it cannot be read."""
        try:
            return self._scoped.options_of(WRAP_UP).get(OptionKey.WRAP_AFTER_RESET, ON) == ON
        except Exception:
            return False

    def _remember(self, thread, turn, window) -> bool:
        """A conversation it stopped, kept for one turn after its window resets: its continuation where Continue after
        the reset (the wrap-up's choice) is on. Kept with it off too (review4 V4, the owner's answer of 2026-11-23): a
        reset message of that conversation is then still carried by the stop's own turn, never queued into the paused
        queue, and without one nothing goes (`after_reset`). Whether a continuation will go."""
        scoped = self._scoped
        try:
            going = self._continue_on()
            key = answer_key(ContinuationKind.AFTER_RESET, thread, window["bucket"], window["minutes"],
                             window["reset_at"])
            if scoped.continuations.get(key) is not None:
                return going
            if not going:
                # review6 A1: kept with no words, so no version - this one, or an older one a person goes back to -
                # ever starts the product's continuation from it; the message's own words come from its rule.
                scoped.continuations.hold(key, ContinuationKind.AFTER_RESET, thread, ordinal=turn.ordinal,
                                          chain=window["minutes"])
                return False
            words = statement.CATALOGS.text(AFTER_RESET_KEY, self._locale())
            if not words_pass(words):
                return False
            scoped.continuations.add(key, ContinuationKind.AFTER_RESET, thread, words, ordinal=turn.ordinal,
                                     chain=window["minutes"])
            return True
        except Exception:
            return False

    def _waiting(self) -> list:
        """The continuations after a reset that wait - with words, or (review6 A1) held with none, for a message only."""
        try:
            return [row for row in self._scoped.continuations.mine() if row["record_state"] == RecordState.WAITING
                    and row["kind"] == ContinuationKind.AFTER_RESET]
        except Exception:
            return []

    def after_reset(self, view, guard=None) -> None:
        """Each conversation it stopped whose window has reset: continued once by a turn the app starts - its request
        written inside one of core's guards (`guard`), and waiting while that refuses - while the stopped turn is still
        its latest, ended, with nothing after it, and the app holds it; ended where newer work came; waiting, with a
        notice, where the app does not hold it."""
        scoped = self._scoped
        handle = scoped.continuations
        waiting = self._waiting()
        if not waiting:
            return
        try:
            # v0.6.18: while any window it holds has not reset - the weekly one still held when the five-hour one
            # resets - no continuation of its own starts either: the pause's own promise (holding()), which holds the
            # wrap-up's continuation after the reset the same way (`holds`).
            held = self.holding()
        except Exception:
            return
        now, rows = scoped.now(), scoped.meter.rows()
        turns, source, start = Turns(self._codex_home()), self._source(), self._start or ipc.start_turn
        going = self._continue_on()
        for row in waiting:
            thread = row["thread_id"]
            # review4 V3: a carried start in doubt is kept in the state (`doubt`), so a restart inside the backoff still
            # waits it out and asks for Resume, never taking it as sent.
            doubted = row.get("launching_at")
            unsure = row["record_id"] in self._unsure or _time(doubted)
            if not _reset_since(rows, row["chain"], row["created_at"], now) or (held and not unsure):
                # review4 V2: newer work before the reset - the person's Resume let the paused queue go - ends the
                # stop's hold now, not at the reset: a message it held then goes by reset_message's own route at its
                # own reset, its day counted from here (resetmessage._held_by_stop).
                self._newer_ends(row, view, source, turns)
                continue
            found = self._message_instead(row, rows, now)
            if found is None:
                continue                                                # not known now: nothing sent, asked next look
            if held and not unsure:
                # v0.6.26 (review4 V1, the owner's answer of 2026-11-23): no turn starts while any window the stop holds
                # has not reset - neither its continuation nor the person's message it carries. The message waits for
                # every held window, reset_message holding it meanwhile (resetmessage.carried_by_stop) and never letting
                # it expire for that wait (`_held_by_stop`, audit4 B1/B3); then this turn carries it, once, and nothing
                # follows it. (audit4 B1's first fix carried it at its own window's reset, into a weekly window over its
                # stop percentage.)
                continue
            if found[0] == INSTEAD and not unsure:
                handle.end(ContinuationReason.SUPERSEDED, thread_id=thread)          # the person's message went (R2)
                self._count(MESSAGE_INSTEAD)
                continue
            if found[0] == QUEUED:
                # Sent into the queue the stop paused (core queued it before this version carried such messages): only a
                # turn lets that queue go, and any turn started would carry words of its own beside it. Nothing more is
                # sent; the person is asked to press Resume in Codex, and this waits, so a chat message there is still
                # left with Codex (engine/chat.paused_by_stop). Their message running there ends it as newer work.
                if self._notice("press_resume", {"minutes": row["chain"], "reset_at": None, "bucket": "codex"}):
                    self._count("resume_unproven")
            try:
                if view.thread_enabled(thread) is not True:
                    continue
                if source.latest(thread) is None:
                    if found[0] == CARRY:
                        self._message_gone(row, found[1])
                    continue
                latest = turns.latest(thread)
            except Exception:
                continue
            if latest is None or latest.ordinal != row["ordinal"]:
                handle.end(ContinuationReason.SUPERSEDED, thread_id=thread)          # newer work came (A17)
                if unsure:
                    self._unsure.pop(row["record_id"], None)
                    self._count(MESSAGE_INSTEAD)                                     # the carried turn did start
                continue
            if unsure:
                # audit4 B4: the carried start was written with no answer, or the pipe failed under it, and after one
                # backoff no turn of it is there. Its words are gone - it may yet arrive, and is never sent twice - so the
                # person is asked to press Resume, as for a message in the paused queue, and this waits: a chat message
                # there is still left with Codex, and their Resume ends it as newer work.
                again = self._backoff.get(row["record_id"], (0, (doubted or now) + BACKOFF_SECONDS))[1]
                if not self._unsure.get(row["record_id"]) and now >= again:
                    self._unsure[row["record_id"]] = True                            # said once
                    if self._notice("press_resume", {"minutes": row["chain"], "reset_at": None, "bucket": "codex"}):
                        self._count("resume_unproven")
                continue
            if latest.status not in FINAL or found[0] == QUEUED:
                continue
            if found[0] == CONTINUE and not (going and row["words"]) and row["words"]:
                # review6 A2: Continue after the reset was on at the stop and is off now. Nothing will start here, and
                # the paused queue stays paused: the person is asked to press Resume, as the stop asks where the choice
                # was off from the start, and the row is kept as a hold with no words from here on.
                try:
                    handle.unword(row["answer_id"])
                except Exception:
                    pass
                if self._notice("press_resume", {"minutes": row["chain"], "reset_at": None, "bucket": "codex"}):
                    self._count("resume_unproven")
                continue
            if found[0] == CONTINUE and not (going and row["words"]):
                # review4 V4: Continue after the reset off - nothing of the product's own goes. This waits with the
                # paused queue, so a reset message of the conversation falling due later is still carried by this turn
                # at its due time, and lets that queue go; newer work (the person's Resume) ends it.
                continue
            failures, again = self._backoff.get(row["record_id"], (0, 0))
            if now < again:
                continue                                                # failed lately: asked again later
            if found[0] == CARRY:
                self._carry(row, found[1], start, guard, now, failures)
                continue
            word = start(thread, row["words"] + "\n\n" + ids.short_marker(row["record_id"]), gate=guard)
            if word == ipc.Stop.HELD:
                continue                                                # held by core: asked again when it lets go
            if word == ipc.Stop.UNCONFIRMED:
                # v0.6.18: written, no answer in time - it may have started. Nothing is said of a failure: the next look
                # after the backoff finds a newer turn (ended SUPERSEDED, nothing sent twice) or starts it again.
                self._backoff[row["record_id"]] = (failures + 1,
                                                   now + min(BACKOFF_SECONDS * 2 ** failures, BACKOFF_MOST))
                continue
            if word == ipc.Start.STARTED:
                self._backoff.pop(row["record_id"], None)
                handle.end(ContinuationReason.SENT, thread_id=thread)
                self._count("continued")
            else:
                self._backoff[row["record_id"]] = (failures + 1,
                                                   now + min(BACKOFF_SECONDS * 2 ** failures, BACKOFF_MOST))
                self._count("not_continued")
                self._notice("not_continued", {"minutes": row["chain"], "reset_at": None, "bucket": "codex"})

    def _newer_ends(self, row, view, source, turns) -> None:
        """review4 V2: the stop's continuation `row` ended superseded where its conversation has newer work than the
        turn it stopped - read as `after_reset` reads it, and nothing ended on what cannot be read."""
        thread = row["thread_id"]
        try:
            if view.thread_enabled(thread) is not True or source.latest(thread) is None:
                return
            latest = turns.latest(thread)
        except Exception:
            return
        if latest is not None and latest.ordinal != row["ordinal"]:
            self._scoped.continuations.end(ContinuationReason.SUPERSEDED, thread_id=thread)

    def _message_gone(self, row, rule) -> None:
        """review4 V2: a message the stop's turn would carry, in a conversation core's reader no longer finds - archived
        or gone - so no turn can start there. It is not kept waiting for ever: it ends as reset_message ends a message
        that was not started (resetmsg.not_started), its words gone, and the person is told that the stopped
        conversation could not be continued (`not_continued`)."""
        try:
            if self._scoped.resets.message_not_started(rule["rule_id"]) is not True:
                return
        except Exception:
            return
        self._count("not_continued")
        self._notice("not_continued", {"minutes": row["chain"], "reset_at": None, "bucket": "codex"})

    def _carry(self, row, rule, start, guard, now, failures) -> None:
        """v0.6.26 (review V1): the stop's turn after the reset, started as continuation `row`'s would be, carrying the
        person's reset message `rule` instead - its words, a blank line and its own marker, as core's one send carries
        them - so the message reaches Codex once and the turn lets the paused queue go (MIPC: start_turn is the measured
        route, and the only one). The message's launch is written inside core's guard just before the one request
        (state/resets.carry_message): a restart then finds it sent and never sends it again, and a Cancel is refused.
        Started: the message is sent, watched by core until its marker is in Codex's history, and the continuation ends
        superseded. Written with no answer in time, or the pipe failing under it (it may have started): the message is
        sent all the same - never twice - but the continuation waits one backoff for the turn to show, and where none does
        the person is asked to press Resume (audit4 B4). The app answering no: the message waits again with its words,
        and the start is asked again after the backoff."""
        handle, resets, thread = self._scoped.continuations, self._scoped.resets, row["thread_id"]
        launched = []

        @contextlib.contextmanager
        def launch():
            with (guard() if guard is not None else contextlib.nullcontext(True)) as permitted:
                if permitted is True:
                    try:
                        permitted = resets.carry_message(rule["rule_id"]) is True
                    except Exception:
                        permitted = False
                    if permitted:
                        launched.append(True)
                yield permitted
        try:
            word = start(thread, rule["words"] + "\n\n" + ids.short_marker(rule["record_id"]), gate=launch)
        except Exception:
            word = ipc.Stop.BROKEN
        if launched and word not in REFUSED_STARTS:
            try:
                resets.carried_message(rule["rule_id"], True)
            except Exception:
                pass                                       # launched: a restart takes it as sent (resetmessage.records)
            if word != ipc.Start.STARTED:
                # audit4 B4: written with no answer in time, or the pipe failed under the write - it may have started,
                # so its words go and it is never sent again, but nothing proves it went. The continuation waits one
                # backoff: a newer turn then ends it; none, and the person is asked to press Resume (`after_reset`).
                self._unsure[row["record_id"]] = False
                self._backoff[row["record_id"]] = (failures + 1,
                                                   now + min(BACKOFF_SECONDS * 2 ** failures, BACKOFF_MOST))
                try:
                    handle.doubt(row["answer_id"])
                except Exception:
                    pass
                return
            self._backoff.pop(row["record_id"], None)
            handle.end(ContinuationReason.SUPERSEDED, thread_id=thread)
            self._count(MESSAGE_INSTEAD)
            return
        if launched:
            try:
                resets.carried_message(rule["rule_id"], False)
            except Exception:
                pass
        if word == ipc.Stop.HELD and not launched:
            return                                         # held by core: asked again when it lets go
        self._backoff[row["record_id"]] = (failures + 1, now + min(BACKOFF_SECONDS * 2 ** failures, BACKOFF_MOST))
        self._count("not_continued")
        self._notice("not_continued", {"minutes": row["chain"], "reset_at": None, "bucket": "codex"})

    def _message_instead(self, row, rows, now):
        """What of the person's reset messages stands for continuation `row` at the reset it waits for (R2, the owner's
        answer of 2026-11-22, "the reset message only"; review V1-V3) - one of reset_message's rules for that
        conversation, of either window (audit4 B3), reset_message on:
        (CARRY, rule)   due since the stop, waiting with its words: the stop's turn carries it in the continuation's place
                        (`_carry`), for reset_message leaves it to that turn (resetmessage.carried_by_stop);
        (INSTEAD, rule) sent since the stop by that turn, or delivered: the continuation ends superseded;
        (QUEUED, rule)  sent since the stop into Codex's queue, which the stop paused: nothing more is sent (`after_reset`);
        None            not known now, or counting for this very reset still - its occasion the next reset of its
                        window, that window the one open at the stop (resetmessage's own `_same_reset`, at most HOLD_FOR
                        past that reset): asked next look, nothing sent on a guess that two may go;
        (CONTINUE, None) none of these: the continuation goes. A message held for a person (count_gap, window_gone, ask
                        first) may never go, and one counting for a later reset is not this one's: neither takes it."""
        scoped = self._scoped
        try:
            # audit4 B3 (the owner's answer of 2026-11-23, "carry it at the stop's own turn"): every window's rules of the
            # conversation - one written for the other window, due while the stop holds, is carried by this turn too.
            rules = [rule for rule in scoped.resets.reset_rules(capability=RESET_MESSAGE, pending=None)
                     if rule.get("thread_id") == row["thread_id"]]
            counted = scoped.resets.windows() if rules else {}
            on = scoped.armed(RESET_MESSAGE) is True if rules else False
        except Exception:
            return None
        since, waiting = row["created_at"], None
        for rule in rules:
            state, flying = rule.get("state"), rule.get("record_state") == RecordState.IN_FLIGHT
            sent = next((rule.get(name) for name in ("sent_at", "launching_at") if _time(rule.get(name))), None)
            if state == RuleState.DONE and _time(rule.get("sent_at")) and rule["sent_at"] >= since:
                return INSTEAD, rule
            if state != RuleState.READY:
                family = (rule.get("bucket"), rule.get("minutes"))
                if state == RuleState.COUNTING and on and _counts_here(rule, counted.get(family), row, rows, now):
                    waiting = True
                continue
            if flying:
                if sent is None:
                    waiting = True                                 # claimed, its launch not begun: asked next look
                elif sent >= since:
                    return (QUEUED if rule.get("queue_id") is not None else INSTEAD), rule
                continue
            if (on and rule.get("record_state") == RecordState.WAITING and rule.get("words")
                    and _time(rule.get("due_at")) and rule["due_at"] >= since):
                return CARRY, rule
        return None if waiting else (CONTINUE, None)

    # ---------------------------------------------------------------- the icon's notices
    def _notice(self, kind, window) -> bool:
        """A notice for the icon, once by its key: whether it is new."""
        now = self._scoped.now()
        key = "%s:%s:%s" % (kind, window.get("minutes"), window.get("reset_at") or int(now // NOTICE_FOR))
        if any(notice["key"] == key for notice in self._notices):
            return False
        self._notices.append({"key": key, "kind": kind, "window_minutes": window.get("minutes"), "at": now,
                              "reset_at": window.get("reset_at")})
        del self._notices[:-NOTICES_KEPT]
        return True

    def notices(self, now) -> list:
        """What the stop has to say to the icon now: the notices of the last NOTICE_FOR seconds - its key, kind
        (not_stopped, press_resume, not_continued), the window and its reset. Codes and numbers only."""
        return [{key: notice[key] for key in ("key", "kind", "window_minutes", "reset_at")}
                for notice in self._notices if 0 <= now - notice["at"] < NOTICE_FOR]
