"""The fifth check of v0.6.26 (the owner's request of 2026-11-23): every combination of the advanced forced stop
(usage_pause), the person's reset message (reset_message) and the stop's own continuation after the reset, written down
as cases and run.

Rounds three and four each found their worst advanced bug where these three meet (audit4 B1: the carried message expired
unsent while the other window held; B3: a message for the other window went into the paused queue and was sent days
later beside the continuation). Each was a combination no single test held. Here every case drives the real engine -
core's engine and store, the edition's runtime with usage_meter, usage_pause and reset_message on, a simulated Codex home
and app - with fakes only at the edges: the clock, the Codex app's stop and start (ipc seams), the app's queue (paused
by a stop, let go by the turn started after the reset, as MIPC measured) and the usage reads.

What each case must come to is worked out here from the sources alone, never from the code under test
(`Expectation`):
- the advanced statements (en) of usage_pause ("When the window resets, a conversation it stopped is continued once
  ... only if nothing newer happened there"; "Messages you queued yourself ... are not touched") and reset_message ("At
  that reset the watcher sends it once ... in place of a continuation waiting there for the same reset"; "In a
  conversation Stop near a limit has stopped, the stop's own turn after its reset carries the message instead: that
  turn does not go through those checks or count toward the twenty a day, and the message waits for that reset even
  when it was written for the other limit");
- the owner's decisions: 2026-11-22 "the reset message only" (never both), 2026-11-23 B3 (a stopped conversation's
  message of either window is held for the stop's own after-reset turn and carried by it) and B5 (that turn skips the
  usual checks and the day's count); and the owner's answers after this sweep's first run (2026-11-23): V1, the held
  message waits until EVERY window the stop holds has reset and is then carried by the stop's own turn, once - no turn
  while a held window holds, no separate continuation; V4, with Continue after the reset off a stopped conversation
  with a reset message still gets that one turn under V1, and without one nothing goes; a held message never expires
  while the stop holds it; and the coordinator's call from V1, Resume pressed before the reset ends the hold, the
  message then going by reset_message's usual route at its own reset;
- the fixed rules: only the watcher sends, the exact thread, nothing on the off chance, a person's words never deleted
  unsent without being told, nothing into the paused queue from core for a conversation the stop paused.
Where the sources disagree or say nothing, a case is marked `owner` and only the invariants every source agrees on are
held (the report, plans/v0626-audit4/matrix5.md, lists them as "needs the owner").

The invariants held in every case: (a) at most one start the app receives per conversation per reset; (b) a message's
words written at most once, never deleted unsent without the person being told, never expired while the stop holds them;
(c) no continuation beside a message; (d) nothing sent by core into the queue the stop paused; (e) no start while a
window the stop holds still holds; (f) the journal and the page say what happened; (g) a restart changes none of it.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -B -m unittest test_advanced_matrix_stop_reset
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import secrets
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume import settings  # noqa: E402
from codex_auto_resume.domain import ids  # noqa: E402
from codex_auto_resume_advanced import surfaces  # noqa: E402
from codex_auto_resume_advanced.codex import inuse, ipc  # noqa: E402
from codex_auto_resume_advanced.control import resets as resets_control  # noqa: E402
from codex_auto_resume_advanced.registry import RESET_MESSAGE, USAGE_METER, USAGE_WRAP_UP  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Actor, OptionKey  # noqa: E402
from test_advanced_usagestop import StopCase, _through  # noqa: E402
from test_engine import T1  # noqa: E402

FIVE, WEEK = 300, 10080
LENGTH = {FIVE: FIVE * 60, WEEK: WEEK * 60}
HOUR, DAY = 3600, 86400
STOP_AT, BELOW = 98, 50          # a window at its stop percentage (97 by default), and one well below it
CONTINUATION = "The usage limit has reset."      # the start of continue.after_reset (en)
PERSON = "the person's own queued words"
RESUMED = "the person's own turn after Resume"
REFUSED = (ipc.Stop.NO_CLIENT, ipc.Stop.VERSION_MISMATCH, ipc.Stop.REFUSED)
WORDS = {"A": "matrix message A, written by the person", "A2": "matrix message A, written again by the person",
         "B": "matrix message B, the second one"}

# ---------------------------------------------------------------------------------------------------- the dimensions
STOPS = ("none", "five", "weekly", "both")                   # 1. the stop
MESSAGES = ("none", "own", "other", "each", "five2")         # 2. own/other: the stop's window or the other one;
#                                                              each: one, then one for the other window once the first
#                                                              went; five2: "the 2nd 5-hour reset from now"
ORDERS = ("five_first", "weekly_first", "same", "sleep")     # 3. reset order
USAGES = ("available", "other_holds", "unknown", "fails")    # 7. usage read at the reset
AROUND = ("restart_before", "restart_mid", "not_received")   # 4. around the reset
TIMES = ("app_closed_two_days", "written_six_days_ago", "turned_off", "deleted", "replaced", "resume_before",
         "pause", "observe_only", "quiet_hours", "held_then_deleted", "continue_off")   # 5. time (+ the wrap-up's choice)
QUEUES = ("person", "core")                                  # 6. Codex's queue (empty is every other case)
HELD_CANCEL = HOUR + HOUR        # held_then_deleted: Cancel an hour after the 5-hour reset (t0 + 1 h), relative to t0


@dataclass(frozen=True)
class Case:
    stop: str
    messages: str
    order: str = "five_first"
    usage: str = "available"
    variant: str = "-"           # one of AROUND, TIMES or "queue_" + QUEUES, or "-"

    @property
    def name(self) -> str:
        return "stop=%s msg=%s order=%s usage=%s variant=%s" % (self.stop, self.messages, self.order, self.usage,
                                                               self.variant)


def pruned(case) -> str | None:
    """Why a combination cannot exist (or is the very same input as another), or None for one that is run."""
    if case.usage == "other_holds" and case.order in ("same", "sleep"):
        return "both windows reset before the first read after a reset: no window is left to hold (same input as available)"
    v = case.variant
    if v == "-":
        return None
    needs_stop = {"restart_mid", "not_received", "resume_before", "continue_off", "queue_person", "queue_core",
                  "app_closed_two_days", "held_then_deleted"}
    if case.stop == "none" and v in needs_stop:
        return "no stop: nothing is paused, started or held by it"
    needs_message = {"written_six_days_ago", "turned_off", "deleted", "replaced", "queue_core", "held_then_deleted"}
    if case.messages == "none" and v in needs_message:
        return "no message to act on"
    if v in ("queue_core", "held_then_deleted"):
        base = expect(replace(case, variant="-"), timeline(replace(case, variant="-"), 0))
        if v == "queue_core" and base.turn != "message:A":
            return ("the message falls due after the stop's turn: an older version queued it into a queue no longer "
                    "paused")
        if v == "held_then_deleted" and not (base.turn == "message:A" and base.at.get("A", 0) > HELD_CANCEL):
            return "the message is not held by the stop an hour after the 5-hour reset"
    return None


# ---------------------------------------------------------------------------------------------------- the timeline
@dataclass
class Timeline:
    t0: int
    resets: dict                                  # {minutes: the first reset}
    asleep: tuple | None = None                   # (from, to): no look between
    blocked: tuple | None = None                  # (from, to): Pause / Observe only / quiet hours / the app closed

    def reset_after(self, minutes, at) -> int:
        """The first reset of window `minutes` after time `at`."""
        reset = self.resets[minutes]
        while reset <= at:
            reset += LENGTH[minutes]
        return reset

    def nth_reset(self, minutes, n) -> int:
        return self.resets[minutes] + (n - 1) * LENGTH[minutes]

    def look(self, at) -> int:
        """The first look at or after `at`: on waking, where the PC slept through it."""
        if self.asleep and self.asleep[0] < at < self.asleep[1]:
            return self.asleep[1]
        return at


def timeline(case, t0) -> Timeline:
    if case.order == "five_first":
        made = Timeline(t0, {FIVE: t0 + HOUR, WEEK: t0 + 3 * DAY})
    elif case.order == "weekly_first":
        made = Timeline(t0, {FIVE: t0 + HOUR, WEEK: t0 + HOUR // 2})
    elif case.order == "same":
        made = Timeline(t0, {FIVE: t0 + HOUR, WEEK: t0 + HOUR})
    else:                                         # both reset while the PC sleeps; it wakes 4.5 hours on
        made = Timeline(t0, {FIVE: t0 + HOUR, WEEK: t0 + 2 * HOUR}, asleep=(t0 + 600, t0 + 4 * HOUR + HOUR // 2))
    first = min(made.resets.values())
    if case.variant in ("pause", "observe_only", "quiet_hours"):
        made.blocked = (first - 600, first + 2 * HOUR)
    return made


def stop_windows(case) -> tuple:
    return {"none": (), "five": (FIVE,), "weekly": (WEEK,), "both": (FIVE, WEEK)}[case.stop]


def message_windows(case) -> list:
    """[(label, minutes, ordinal)] of the first message, and of the second one ("each")."""
    own = WEEK if case.stop == "weekly" else FIVE
    other = FIVE if own == WEEK else WEEK
    return {"none": [], "own": [("A", own, 1)], "other": [("A", other, 1)], "each": [("A", own, 1), ("B", other, 1)],
            "five2": [("A", FIVE, 2)]}[case.messages]


# ---------------------------------------------------------------------------------------------------- the expectation
@dataclass
class Expectation:
    """What the sources say a case comes to: the one turn the stop starts and what it carries, what core sends, how each
    message ends, the notices that must be shown - or `owner` where no source says."""
    turn: str | None = None                         # "continuation", "message:A", or None
    core: list = field(default_factory=list)        # labels core sends, in order
    ends: dict = field(default_factory=dict)        # {label: delivered|expired|cancelled|unproven|unsent}
    at: dict = field(default_factory=dict)          # {label: when it went}
    notices: set = field(default_factory=set)
    owner: str | None = None                        # why this case needs the owner, or None
    person_runs: bool = False                       # the person's own queued item runs, once


def held_windows(case, tl) -> set:
    """The windows the stop holds: those over their stop percentage at the stop, and, where the read after the first
    reset says another is over, that one too."""
    held = set(stop_windows(case))
    first = min(tl.resets.values())
    if case.usage == "other_holds" and case.stop != "none":
        held |= {minutes for minutes in (FIVE, WEEK) if tl.resets[minutes] > first}
    return held


def release_of(case, tl):
    """When every window the stop holds has reset (V1), or None with no stop."""
    held = held_windows(case, tl)
    return max(tl.resets[minutes] for minutes in held) if held else None


def expect(case, tl) -> Expectation:
    """From the sources, never from the code:
    (1) No stop: a message goes through core at its reset, once usage is available and nothing stands in the way, or
        expires a day after it fell due (eight days after it was written).
    (2) V1 (the owner, 2026-11-23): a stopped conversation's reset message is held until EVERY window the stop holds has
        reset; then the stop's own turn carries it, once - no turn while a held window still holds, and no separate
        continuation. A held message never expires while the stop holds it.
    (3) No message held: the stop's continuation goes once, when every held window has reset (usage_pause).
    (4) V4: with Continue after the reset off, a stopped conversation with a held message still gets that one turn,
        under (2); without one nothing goes, and a notice asks for Resume. A message due after every held window has
        reset, the paused queue still holding because no turn went, is carried by the stop's own turn at its due time,
        once, letting that queue go - never queued by core (the coordinator's call from V4).
    (5) Resume pressed before the reset ends the hold (the coordinator's call from V1): no stop's turn, and the message
        goes by reset_message's usual route at its own reset, its day counted from the Resume.
    (6) A message due after the stop's continuation went goes through core at its own reset.
    Nothing goes on the off chance: a message that needs a window counted after the first reset waits (or expires)
    where no read succeeds after it."""
    found = Expectation()
    first = min(tl.resets.values())
    release = release_of(case, tl)
    blocked_until = tl.blocked[1] if tl.blocked else 0
    if case.variant == "app_closed_two_days":
        blocked_until = release + 2 * DAY
    usage_ok = case.usage in ("available", "other_holds")
    messages = message_windows(case)
    cancel_at = {"turned_off": tl.t0 + 1800, "deleted": tl.t0 + 1800,
                 "held_then_deleted": tl.t0 + HELD_CANCEL}.get(case.variant)
    if case.variant == "replaced":
        found.ends["A"] = "cancelled"
        messages = [("A2",) + tuple(messages[0][1:])] + messages[1:]
    stopped = case.stop != "none" and case.variant != "resume_before"
    continue_on = case.variant != "continue_off"
    if case.variant == "continue_off":
        found.notices.add("press_resume")
    go = tl.look(max(release, blocked_until)) if stopped else None        # the look the stop's turn goes at
    written = tl.t0 - 6 * DAY if case.variant == "written_six_days_ago" else tl.t0
    hold_open, finished_at = stopped, None
    for index, (label, minutes, ordinal) in enumerate(messages):
        if index == 0:
            due = tl.nth_reset(minutes, ordinal)
            if not usage_ok and ordinal > 1:
                found.ends[label] = "unsent"          # its window opens after the first reset: never counted
                break
        else:
            if finished_at is None:
                break                                 # the second one is written once the first has gone
            if not usage_ok and finished_at >= first:
                found.ends[label] = "unsent"          # no read succeeds after the reset: nothing on the off chance
                break
            due = tl.reset_after(minutes, finished_at)
        if hold_open and due <= go:
            # V1: held until every held window has reset, then carried by the stop's turn, once.
            if cancel_at is not None and cancel_at < go:
                found.ends[label] = "cancelled"
                break
            hold_open = False
            if case.variant == "queue_core":
                found.ends[label] = "delivered"           # in the paused queue already; it runs at the person's Resume
                found.notices.add("press_resume")
                break
            if case.variant == "not_received":
                found.ends[label] = "unproven"            # its words written once, never again; nothing shows it came
                found.notices.add("press_resume")
                break
            found.turn = "message:" + label
            found.ends[label] = "delivered"
            found.at[label] = finished_at = go
            continue
        if hold_open:
            hold_open = False
            if continue_on:
                found.turn = "continuation"
            else:
                # The coordinator's call from V4: no turn went, so the stop's paused queue still holds; the stop's own
                # turn carries the message at its due time, once, and lets that queue go - never core's queue.
                found.turn = "message:" + label
                found.ends[label] = "delivered"
                found.at[label] = finished_at = tl.look(max(due, blocked_until))
                continue
        # handed to core at its own reset: usage must be available, nothing standing in the way
        sends_at = tl.look(max(due, blocked_until))
        expires_at = min(due + DAY, written + 8 * DAY) if index == 0 else due + DAY
        if cancel_at is not None and cancel_at < min(sends_at, expires_at):
            found.ends[label] = "cancelled"
            break
        if usage_ok and sends_at < expires_at:
            found.core.append(label)
            found.ends[label] = "delivered"
            found.at[label] = finished_at = sends_at
        elif usage_ok:
            found.ends[label] = "expired"
        else:
            # Usage never readable after the reset: nothing goes on the off chance. Whether it waits or expires a day on
            # is in no statement; either is held by the invariants (the page and the journal say which).
            found.ends[label] = "unsent"
    if hold_open and continue_on:
        found.turn = "continuation"
    if case.variant == "app_closed_two_days":
        found.notices.add("not_continued")
    if case.variant == "queue_person":
        found.person_runs = True
    found.ends = {label: end for label, end in found.ends.items() if end != "owner"}
    return found


# ---------------------------------------------------------------------------------------------------- the world
class FakeSession:
    """One usage read, as the edition's session answers it: the world's usage at the world's time."""

    def __init__(self, world):
        self.world = world

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def call(self, method, params=None):
        return self.world.usage_reply()


class World:
    """One case, run: the harness, the plug, the seams, the clock moved from moment to moment, and what was seen."""

    def __init__(self, test, case):
        self.t, self.case = test, case
        test.BESIDE = (USAGE_METER, RESET_MESSAGE) + ((USAGE_WRAP_UP,) if case.variant == "continue_off" else ())
        self.h = test.h = test.fresh()
        self.tl = timeline(case, int(self.h.now))
        self.paused = set()
        self.starts, self.sends, self.ran, self.stops = [], [], [], []
        self.notices, self.rules, self.labels = set(), {}, {}
        self.expired_seen = []
        self.pending_turn = None
        self.not_received_once = case.variant == "not_received"
        self.problems = []
        h = self.h
        h.backend.after_accept = "queue"
        h.backend.loaded_map[T1] = "loaded"
        h.backend.on_send = self._core_sent
        self.app = dict(h.backend.app)
        self.plug = self.build(first=True)
        # A turn runs in T1 at the start. With no stop, it has ended before any reset: a turn still running when the read
        # after a reset shows a window over its stop percentage would be stopped then - a stop, not "none".
        self.turn = h.home.add_turn(T1, status="inProgress" if case.stop != "none" else "completed", progress=False)

    # ------------------------------------------------------------------ building
    def build(self, first=False):
        t = self.t
        if first:
            plug = t.armed(self.h)
            values = settings.defaults()
            values["continuation_language"] = "en"
            settings.save(plug.paths.settings_file, values)
            if self.case.variant == "continue_off":
                for key, value in ((OptionKey.WINDOW_FIVE_HOUR, 2), (OptionKey.WINDOW_WEEKLY, 2),
                                   (OptionKey.WRAP_AFTER_RESET, 2)):
                    assert plug.runtime.arming.set_option("usage_wrap_up", key, value,
                                                          generation=plug.runtime.state.meta()["generation"],
                                                          actor=Actor.DASHBOARD)["done"]
        else:
            plug = t.advanced(self.h)
            t.plugged(plug, self.h)
        runtime = plug.runtime
        code = runtime._code_of(runtime.registry.get("usage_pause"))
        code._home = self.h.home.root
        code._stop = self._stop
        code._start = self._start
        meter = runtime._code_of(runtime.registry.get("usage_meter"))
        meter._app_running = lambda: bool(self.h.backend.app)
        meter._session = lambda: FakeSession(self)
        message = runtime._code_of(runtime.registry.get("reset_message"))
        message._open = lambda: FakeSession(self)
        return plug

    def restart(self):
        self.plug = self.build()

    # ------------------------------------------------------------------ the edges
    def window_now(self, minutes, now):
        reset = self.tl.reset_after(minutes, now) if now >= self.tl.resets[minutes] else self.tl.resets[minutes]
        if now < self.tl.resets[minutes]:
            used = STOP_AT if minutes in stop_windows(self.case) else BELOW
            if self.case.usage == "other_holds" and now >= min(self.tl.resets.values()):
                used = STOP_AT
        else:
            used = 1
        return used, reset

    def usage_reply(self):
        now = self.h.now
        after = now >= min(self.tl.resets.values())
        if after and self.case.usage == "fails":
            raise OSError("the usage read failed")
        if after and self.case.usage == "unknown":
            return {"rateLimitsByLimitId": {"codex": {"primary": "unreadable"}}}
        slots = {}
        for slot, minutes in (("primary", FIVE), ("secondary", WEEK)):
            used, reset = self.window_now(minutes, now)
            slots[slot] = {"usedPercent": used, "windowDurationMins": minutes, "resetsAt": int(reset)}
        return {"rateLimitsByLimitId": {"codex": slots}, "rateLimitResetCredits": {"availableCount": 0, "credits": []}}

    def core_usage(self):
        now = self.h.now
        if now >= min(self.tl.resets.values()) and self.case.usage in ("unknown", "fails"):
            return {"available": None, "reset_at": None, "limit_type": "unknown", "reason": "usage_snapshot_unknown"}
        return {"available": True, "reset_at": None, "limit_type": "exposed_windows", "reason": "ok"}

    def app_closed(self) -> bool:
        if self.case.variant != "app_closed_two_days":
            return False
        reset = release_of(self.case, self.tl)
        return reset - 600 <= self.h.now < reset + 2 * DAY

    def _stop(self, thread, turn, gate=None):
        def made():
            self.stops.append((self.h.now, thread, turn))
            self.h.home.set_turn(thread, turn, status="interrupted", completed_at=int(self.h.now))
            self.paused.add(thread)
        return _through(gate, made, ipc.Stop.STOPPED)

    def _start(self, thread, text, gate=None):
        if self.app_closed():
            answer = ipc.Stop.NO_CLIENT
        elif self.not_received_once:
            answer = ipc.Stop.UNCONFIRMED
        else:
            answer = ipc.Start.STARTED

        def made():
            received = answer == ipc.Start.STARTED
            self.starts.append({"at": self.h.now, "text": text, "answer": answer, "received": received,
                                "written": answer not in REFUSED})
            if answer == ipc.Stop.UNCONFIRMED:
                self.not_received_once = False
            if received:
                if self.case.variant == "restart_mid":
                    self.pending_turn = (thread, text)
                else:
                    self.run_turn(thread, text)
        return _through(gate, made, answer)

    def run_turn(self, thread, text):
        """The app starts a turn with `text`, it ends, and the queue the stop paused goes (MIPC)."""
        self.h.home.add_turn(thread, status="completed", user_text=text)
        self.ran.append((self.h.now, text))
        self.paused.discard(thread)
        self.drain()

    def _core_sent(self, thread, prompt):
        self.sends.append({"at": self.h.now, "thread": thread, "text": prompt, "paused": thread in self.paused})

    def queued_texts(self, thread=T1):
        import json
        with self.h.home._db("queue_1.sqlite") as db:
            return [json.loads(row[0])["UserInput"]["content"][0]["text"] for row in db.execute(
                "SELECT payload_json FROM queued_items WHERE thread_id=? ORDER BY queue_order", (thread,))]

    def drain(self, thread=T1):
        """The app runs what is queued in a conversation whose queue is not paused."""
        while thread not in self.paused and self.h.backend.app:
            texts = self.queued_texts(thread)
            if not texts:
                return
            self.h.home.dispatch(thread)
            self.ran.append((self.h.now, texts[0]))

    # ------------------------------------------------------------------ the person
    def write(self, label, minutes, ordinal, at=None):
        runtime = self.plug.runtime
        argument = {"kind": "message", "bucket": "codex", "minutes": minutes, "ordinal": ordinal, "thread_id": T1,
                    "words": WORDS[label], "generation": runtime.state.meta()["generation"]}
        if at is not None:                         # a message written days ago: as the state writes one then
            rule = runtime.state.add_reset_rule("reset_message", "codex", minutes, ordinal, thread_id=T1,
                                                words=WORDS[label], record_id=secrets.token_hex(32), at=at)
            self.labels[label] = rule
            return {"done": True, "rule": rule}
        with patch.object(resets_control, "_wake", lambda runtime: None):
            made = resets_control.add(runtime, argument)
        if made.get("done"):
            self.labels[label] = made["rule"]
        return made

    def cancel(self, label):
        runtime = self.plug.runtime
        with patch.object(resets_control, "_wake", lambda runtime: None):
            return resets_control.cancel(runtime, self.labels[label], runtime.state.meta()["generation"])

    def resume(self):
        """The person presses Resume in Codex: the queue goes, and they go on in that conversation."""
        self.paused.discard(T1)
        self.drain()
        self.h.home.add_turn(T1, status="completed", user_text=RESUMED)
        self.ran.append((self.h.now, RESUMED))

    def queued_by_core_before(self, label):
        """An older version's state, read mid-update: the message sent by core into the queue the stop paused."""
        state = self.plug.runtime.state
        rule = self.labels[label]
        row = state.reset_rule(rule)
        if row is None or row["state"] not in ("counting", "ready"):
            return False
        text = WORDS[label] + "\n\n" + ids.short_marker(row["record_id"])
        queue_id = self.h.home.enqueue(T1, text)
        assert state.change_rule(rule, state="ready", due_at=int(self.h.now))
        assert state.carry_message(rule, at=self.h.now)
        assert state.carried_message(rule, True, at=self.h.now)
        assert state.record_moved(row["record_id"], "sent", at=self.h.now, queue_id=queue_id) is not None
        self.sends.append({"at": self.h.now, "thread": T1, "text": text, "paused": True, "older": True})
        return True

    # ------------------------------------------------------------------ the clock
    def moments(self) -> list:
        """The looks the watcher makes: a few after each reset that matters, at least one a day, none while asleep."""
        tl, case = self.tl, self.case
        events = {tl.resets[FIVE], tl.resets[WEEK]}
        if case.messages in ("each", "five2"):
            events |= {tl.resets[FIVE] + n * LENGTH[FIVE] for n in (1, 2)}
        if case.messages == "each":
            events.add(tl.resets[WEEK] + LENGTH[WEEK])
        horizon = max(events) + DAY + 2 * HOUR
        if case.variant in ("app_closed_two_days", "written_six_days_ago"):
            horizon = max(horizon, max(tl.resets.values()) + 3 * DAY + 2 * HOUR)
        slow = case.variant in ("not_received", "app_closed_two_days")
        points = {tl.t0 + 61, tl.t0 + 122, horizon}
        if case.variant != "-":
            points.add(tl.t0 + 1800)
        for event in events:
            points |= {event + 61, event + 122, event + 183}
            if slow:
                points |= {event + 600, event + 1260}
        if tl.blocked:
            points |= {tl.blocked[0], tl.blocked[1] + 1, tl.blocked[1] + 62, tl.blocked[1] + 123}
        if case.variant == "app_closed_two_days":
            end = release_of(case, tl) + 2 * DAY
            points |= {end + 1, end + 62, end + 123, end + 3700, end + 3761}
        if case.variant == "held_then_deleted":
            points.add(tl.t0 + HELD_CANCEL)
        filled = []
        for point in sorted(points):               # a look at least once a day, so a day's expiry is seen
            while filled and point - filled[-1] > DAY:
                filled.append(filled[-1] + DAY)
            filled.append(point)
        if tl.asleep:
            filled = [point for point in filled if not tl.asleep[0] < point < tl.asleep[1]]
            filled += [tl.asleep[1], tl.asleep[1] + 61, tl.asleep[1] + 122]
        return sorted(set(filled))

    def run(self):
        case, tl, h = self.case, self.tl, self.h
        messages = message_windows(case)
        if case.variant not in ("written_six_days_ago",):
            for label, minutes, ordinal in messages[:1]:
                made = self.write(label, minutes, ordinal)
                if not made.get("done"):
                    self.problems.append("the message was refused: %s" % made)
        else:
            label, minutes, ordinal = messages[0]
            self.write(label, minutes, ordinal, at=tl.t0 - 6 * DAY)
        if case.messages == "each":
            made = self.write("B", messages[1][1], messages[1][2])
            if made.get("done") or made.get("refusal") != "already_scheduled":
                self.problems.append("one message to a conversation: the second was not refused (%s)" % made)
            self.labels.pop("B", None)
        quiet = None
        if case.variant == "quiet_hours":
            blocked = tl.blocked
            quiet = patch.object(type(h.engine), "quiet_until",
                                 lambda engine, now: blocked[1] if blocked[0] <= now < blocked[1] else None)
            quiet.start()
        moments = self.moments()
        self._last = moments[-1]
        try:
            for moment in moments:
                h.now = moment
                self.before(moment)
                h.backend.usage_result = self.core_usage()
                h.backend.app = {} if self.app_closed() else dict(self.app)
                h.tick()
                self.after(moment)
        finally:
            if quiet is not None:
                quiet.stop()
        return self

    def before(self, moment):
        case, tl, h = self.case, self.tl, self.h
        if moment == tl.t0 + 1800:
            if case.variant == "restart_before":
                self.restart()
            elif case.variant == "turned_off":
                self.plug.runtime.arming.disarm("reset_message", actor=Actor.DASHBOARD)
            elif case.variant == "deleted":
                self.cancel("A")
            elif case.variant == "replaced":
                self.cancel("A")
                _label, minutes, ordinal = message_windows(case)[0]
                if not self.write("A2", minutes, ordinal).get("done"):
                    self.problems.append("the replacement was refused")
            elif case.variant == "resume_before":
                self.resume()
            elif case.variant == "queue_person":
                h.home.enqueue(T1, PERSON)
        if case.variant == "held_then_deleted" and moment == tl.t0 + HELD_CANCEL:
            self.cancel("A")
        if tl.blocked and case.variant in ("pause", "observe_only"):
            standing = tl.blocked[0] <= moment < tl.blocked[1]
            if standing != getattr(self, "_standing", False):
                self._standing = standing
                if case.variant == "pause":
                    h.store.set_enabled(not standing, moment)
                else:
                    h.store.set_observe_only(standing)
        if case.variant == "queue_core" and "A" in self.labels and not getattr(self, "_queued", False):
            label, minutes, ordinal = message_windows(case)[0]
            due = tl.nth_reset(minutes, ordinal)
            if moment >= due + 61:
                self._queued = self.queued_by_core_before("A") or True
        if case.variant == "queue_core" and moment == self._last:
            self.resume()                                   # the person presses Resume at last

    def after(self, moment):
        h = self.h
        if self.pending_turn is not None:                   # restart_mid: the watcher restarted before the turn showed
            thread, text = self.pending_turn
            self.pending_turn = None
            self.restart()
            self.run_turn(thread, text)
        self.drain()
        if self.case.messages == "each" and "B" not in self.labels and "A" in self.labels:
            row = self.plug.runtime.state.reset_rule(self.labels["A"])
            if row is not None and row["state"] == "done" and row["reason"] == "delivered":
                self.b_written_at = moment
                if not self.write("B", *message_windows(self.case)[1][1:]).get("done"):
                    self.problems.append("the second message was refused after the first went")
        try:
            view = surfaces.meter_view(self.plug.runtime)
            self.notices |= {notice["kind"] for notice in view.get("meter", {}).get("notices", [])}
        except Exception as error:                          # noqa: BLE001 - what the page cannot read is a finding
            self.problems.append("the page could not be read: %r" % error)

    # ------------------------------------------------------------------ what was seen
    def label_of(self, text):
        for label, words in WORDS.items():
            if text.startswith(words):
                return label
        if text.startswith(CONTINUATION):
            return "continuation"
        if text in (PERSON, RESUMED):
            return text
        return "?" + text[:30]

    def seen(self) -> dict:
        state = self.plug.runtime.state
        rules = {label: state.reset_rule(rule) for label, rule in self.labels.items()}
        ends = {}
        for label, row in rules.items():
            if row is None:
                ends[label] = "gone"
            elif row["state"] == "done":
                ends[label] = {"delivered": "delivered", "expired": "expired", "unknown": "unproven"}.get(
                    row["reason"], "done:" + str(row["reason"]))
            elif row["state"] == "cancelled":
                ends[label] = "cancelled"
            elif row["record_state"] == "in_flight":
                ends[label] = "in_flight"
            else:
                ends[label] = "waiting"
        received = [start for start in self.starts if start["received"]]
        return {"turn": None if not received else ("message:" + self.label_of(received[0]["text"])
                                                   if self.label_of(received[0]["text"]) in WORDS
                                                   else self.label_of(received[0]["text"])),
                "received": received, "written": [start for start in self.starts if start["written"]],
                "core": [self.label_of(send["text"]) for send in self.sends if not send.get("older")],
                "ends": ends, "rules": rules,
                "continuations": state.continuations(capability="usage_pause", pending=None),
                "journal": state.journal(limit=2000), "notices": set(self.notices),
                "page": resets_control.view(self.plug.runtime)}


# ---------------------------------------------------------------------------------------------------- the checks
COUNTED = {"run": 0, "pruned": 0}


def tearDownModule():
    sys.stderr.write("\nmatrix: %(run)d cases run, %(pruned)d pruned\n" % COUNTED)


class MatrixCase(StopCase):
    BESIDE = (USAGE_METER, RESET_MESSAGE)

    def setUp(self):
        super().setUp()
        patcher = patch.object(inuse, "backend", side_effect=OSError("no real Codex in a test"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def sweep(self, cases):
        for case in cases:
            why = pruned(case)
            if why is not None:
                COUNTED["pruned"] += 1
                continue
            COUNTED["run"] += 1
            with self.subTest(case.name):
                self.check(case)

    def check(self, case):
        world = World(self, case).run()
        seen = world.seen()
        tl = world.tl
        wanted = expect(case, tl)
        self.assertEqual(world.problems, [], case.name)
        self.invariants(case, world, seen, wanted)
        if wanted.owner is None:
            got = {"turn": seen["turn"], "core": seen["core"],
                   "ends": {label: ("unsent" if wanted.ends.get(label) == "unsent" and end in ("waiting", "expired")
                                    else end) for label, end in seen["ends"].items() if label in wanted.ends}}
            want = {"turn": wanted.turn, "core": wanted.core, "ends": wanted.ends}
            self.assertEqual(got, want, "%s: what was sent and how each message ended" % case.name)
            self.assertLessEqual(wanted.notices, seen["notices"], "%s: the notices shown" % case.name)
        if wanted.person_runs:
            runs = [at for at, text in world.ran if text == PERSON]
            self.assertEqual(len(runs), 1, "%s: the person's own queued item runs once, untouched" % case.name)
            self.assertEqual(self.h.backend.deleted, [], "%s: nothing of the person's taken back" % case.name)

    def invariants(self, case, world, seen, wanted):
        name, tl = case.name, world.tl
        # (a) at most one start the app receives in the conversation for this stop
        self.assertLessEqual(len(seen["received"]), 1, "%s (a): starts received %s" % (name, seen["received"]))
        # (b) each message's words written at most once, and run at most once
        for label in world.labels:
            written = [s for s in seen["written"] if world.label_of(s["text"]) == label]
            cored = [s for s in seen["core"] if s == label]
            self.assertLessEqual(len(written) + len(cored), 1, "%s (b): %s written %d times" %
                                 (name, label, len(written) + len(cored)))
            runs = [at for at, text in world.ran if world.label_of(text) == label]
            self.assertLessEqual(len(runs), 1, "%s (b): %s ran %d times" % (name, label, len(runs)))
        # (b) never expired while the stop holds it
        stops = seen["continuations"]
        for entry in seen["journal"]:
            if entry["code"] != "resetmsg.expired":
                continue
            for stop in stops:
                ended = stop["finished_at"]
                if stop["created_at"] <= entry["at"] and (ended is None or entry["at"] - ended < DAY):
                    self.fail("%s (b): a message expired at %+d s while the stop held it (continuation %s)" %
                              (name, entry["at"] - tl.t0, stop["reason"]))
        # (b, f) a message's words gone unsent only where the person is told: the page and the journal say why
        page = {item["rule_id"]: item for item in seen["page"].get("rules", [])}
        codes = [entry["code"] for entry in seen["journal"]]
        for label, row in seen["rules"].items():
            if row is None or row["words"] is not None or row["sent_at"] is not None:
                continue
            if row["state"] in ("done", "cancelled"):
                self.assertIn(row["rule_id"], page, "%s (f): %s ended unsent and the page does not show it" %
                              (name, label))
                if row["reason"] == "expired":
                    self.assertIn("resetmsg.expired", codes, "%s (f): expired with no journal line" % name)
        # (c) no continuation beside a message
        continued = [s for s in seen["received"] if world.label_of(s["text"]) == "continuation"]
        carried = [s for s in seen["written"] if world.label_of(s["text"]) in WORDS]
        self.assertFalse(continued and carried, "%s (c): a continuation and a carried message both started" % name)
        for start in continued:
            for send in world.sends:
                label = world.label_of(send["text"])
                rule = seen["rules"].get(label)
                if rule is None or rule["due_at"] is None:
                    continue
                stop_made = min((stop["created_at"] for stop in stops), default=None)
                if stop_made is not None and stop_made <= rule["due_at"] <= start["at"]:
                    self.fail("%s (c): %s, due at %+d s while the stop's continuation waited, went beside it" %
                              (name, label, rule["due_at"] - tl.t0))
        # (d) nothing sent by core into the queue the stop paused
        for send in world.sends:
            if send["paused"] and not send.get("older"):
                self.fail("%s (d): core sent %s into the paused queue at %+d s" %
                          (name, world.label_of(send["text"]), send["at"] - tl.t0))
        # (e) no start while a window the stop holds still holds (V1: for the carried message as for the continuation)
        held = held_windows(case, tl)
        for start in seen["written"]:
            late = [minutes for minutes in sorted(held) if start["at"] < tl.resets[minutes]]
            self.assertEqual(late, [], "%s (e): %s started at %+d s while %s held" %
                             (name, world.label_of(start["text"]), start["at"] - tl.t0, late))
        # (f) a stop's continuation still waiting at the end is explained by a notice
        for stop in stops:
            if stop["finished_at"] is None:
                self.assertTrue(seen["notices"] & {"press_resume", "not_continued"},
                                "%s (f): the stop's continuation still waits at the end and nothing says why" % name)


def base_cases(stop, order):
    return [Case(stop, messages, order, usage) for messages in MESSAGES for usage in USAGES]


class NoStop(MatrixCase):
    def test_five_first(self):
        self.sweep(base_cases("none", "five_first"))

    def test_weekly_first(self):
        self.sweep(base_cases("none", "weekly_first"))

    def test_same(self):
        self.sweep(base_cases("none", "same"))

    def test_sleep(self):
        self.sweep(base_cases("none", "sleep"))


class FiveHourStop(MatrixCase):
    def test_five_first(self):
        self.sweep(base_cases("five", "five_first"))

    def test_weekly_first(self):
        self.sweep(base_cases("five", "weekly_first"))

    def test_same(self):
        self.sweep(base_cases("five", "same"))

    def test_sleep(self):
        self.sweep(base_cases("five", "sleep"))


class WeeklyStop(MatrixCase):
    def test_five_first(self):
        self.sweep(base_cases("weekly", "five_first"))

    def test_weekly_first(self):
        self.sweep(base_cases("weekly", "weekly_first"))

    def test_same(self):
        self.sweep(base_cases("weekly", "same"))

    def test_sleep(self):
        self.sweep(base_cases("weekly", "sleep"))


class BothStop(MatrixCase):
    def test_five_first(self):
        self.sweep(base_cases("both", "five_first"))

    def test_weekly_first(self):
        self.sweep(base_cases("both", "weekly_first"))

    def test_same(self):
        self.sweep(base_cases("both", "same"))

    def test_sleep(self):
        self.sweep(base_cases("both", "sleep"))


def variant_cases(variants, orders=("five_first",)):
    return [Case(stop, messages, order, "available", variant) for variant in variants
            for stop in ("five", "weekly", "both") for messages in ("none", "own", "other") for order in orders]


class AroundTheReset(MatrixCase):
    def test_restarts_and_a_start_not_received(self):
        self.sweep(variant_cases(AROUND))


class TimeWhileHeld(MatrixCase):
    def test_the_app_closed_and_old_messages(self):
        self.sweep(variant_cases(("app_closed_two_days", "written_six_days_ago")))

    def test_the_person_changes_the_message(self):
        self.sweep(variant_cases(("turned_off", "deleted", "replaced", "held_then_deleted")))

    def test_resume_before_the_reset(self):
        self.sweep(variant_cases(("resume_before",)))

    def test_pause_observe_and_quiet_hours(self):
        self.sweep(variant_cases(("pause", "observe_only", "quiet_hours")))

    def test_continue_after_the_reset_off(self):
        self.sweep(variant_cases(("continue_off",)))


class CodexQueue(MatrixCase):
    def test_the_persons_item_and_an_older_versions_item(self):
        self.sweep(variant_cases(("queue_person", "queue_core")))


class Pruned(MatrixCase):
    """What cannot exist, held as the product refuses it (so a prune is never a guess): a message for every reset, a
    weekly message for a later reset, and two messages waiting in one conversation (asserted in every "each" case)."""

    def test_a_message_never_repeats_and_a_weekly_one_is_for_the_next_reset_only(self):
        world = World(self, Case("five", "none"))
        runtime = world.plug.runtime
        argument = {"kind": "message", "bucket": "codex", "minutes": FIVE, "ordinal": 1, "thread_id": T1,
                    "words": WORDS["A"], "generation": runtime.state.meta()["generation"]}
        with patch.object(resets_control, "_wake", lambda runtime: None):
            self.assertFalse(resets_control.add(runtime, dict(argument, repeat=True))["done"], "no message repeats")
            self.assertFalse(resets_control.add(runtime, dict(argument, minutes=WEEK, ordinal=2))["done"],
                             "a weekly window is offered for its next reset only")
            self.assertTrue(resets_control.add(runtime, dict(argument, ordinal=2))["done"])


if __name__ == "__main__":
    unittest.main()
