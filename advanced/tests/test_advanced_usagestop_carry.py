"""v0.6.26 (review V1-V3, V5 of the third round's fixes): with usage_pause and reset_message both on, the person's reset
message for a conversation the forced stop stopped goes once, at the reset, carried by the stop's own turn after the
reset - and that turn is what lets the queue the stop paused go.

R2's first fix ended the stop's continuation for the message and let core queue the message. But the app paused that
conversation's queue at the stop, and only the turn usage_pause starts after the reset (ipc.start_turn, MIPC measured
2026-10-16) lets that queue go: the message sat there for good, and nothing said so (V1). Now reset_message leaves such
a message to the stop (resetmessage.carried_by_stop), and the stop's turn after the reset carries the message's words
and its marker instead of the continuation's (usagestop._carry): one send, the person's words, nothing through core's
queue, the rule delivered, and nothing sent again after a restart. Here the simulated app keeps what is queued - as the
paused queue does - and starts a turn only for start_turn, sending what was queued once that turn ends.

V2: a message counting for a later reset - one of two counted, or "the next reset" made after this one was counted -
takes nothing of this reset. V3: a message held for a person (count_gap) may never go, and takes nothing either. V5: a
message already in that paused queue (sent there before this version) starts no turn beside it; the person is asked to
press Resume, and a chat message sent there meanwhile is still left with Codex.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_usagestop_carry
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume.domain import ids  # noqa: E402
from codex_auto_resume_advanced.codex import ipc  # noqa: E402
from codex_auto_resume_advanced.engine import chat as chat_engine  # noqa: E402
from test_advanced_usagestop import StopCase, _through  # noqa: E402
import test_advanced_usagestop_reset_message as instead  # noqa: E402
from test_engine import T1  # noqa: E402

WORDS = "my own words"
DAY = 86400


class CarryCase(StopCase):
    # MessageInstead's harness, not its tests: both on, the stop made, the rule written as reset_message writes one.
    BESIDE = instead.MessageInstead.BESIDE
    stopped, rule, window, outcome = (instead.MessageInstead.stopped, instead.MessageInstead.rule,
                                      instead.MessageInstead.window, instead.MessageInstead.outcome)

    def running(self, percent=98):
        plug, turn = super().running(percent)
        self.h.backend.after_accept = "queue"                      # the app keeps what is queued: the stop paused it
        self.seams(plug)
        return plug, turn

    def seams(self, plug):
        """The app's start: a turn with the words given, ended, and then what was queued sent - as MIPC measured."""
        code = self.code(plug)
        code._home = self.h.home.root
        code._stop = lambda thread, turn, gate=None: _through(gate, lambda: self.stops.append((thread, turn)),
                                                              self.stop_answer)

        def start(thread, text, gate=None):
            def made():
                self.starts.append((thread, text))
                if self.start_answer != ipc.Start.STARTED:
                    return                                          # the app answered no: nothing started
                self.h.home.add_turn(thread, status="completed", user_text=text)
                while self.h.home.dispatch(thread) is not None:
                    pass
            return _through(gate, made, self.start_answer)
        code._start = start

    def restarted(self):
        """A new watcher over the same state: a new plug, the engine rebuilt with it, the seams set again."""
        plug = self.advanced()
        self.plugged(plug)
        self.seams(plug)
        return plug

    def carried(self):
        return [(T1, WORDS + "\n\n" + ids.short_marker(instead.RECORD))]

    def rule_row(self, plug, rule_id):
        row = plug.runtime.state.reset_rule(rule_id)
        return row["state"], row["reason"]


class CarriedOnceTests(CarryCase):
    def test_the_message_goes_once_in_the_stops_turn_and_the_queue_is_let_go(self):
        """Fails with V1 open: no turn starts, the message sits in Codex's paused queue two days on, and nothing says
        so."""
        plug, turn = self.stopped()
        self.after_reset(plug, turn)
        rule = self.rule(plug, state="ready", due_at=self.reset + 60)
        for _ in range(5):
            self.h.tick(advance=60)
        self.assertEqual(self.starts, self.carried(), "one start, the person's words and their message's marker")
        self.assertEqual(self.h.backend.send_calls, [], "nothing into the queue the stop paused")
        self.assertEqual(self.h.home.queued(T1), [], "nothing left in Codex's queue")
        self.assertEqual(self.outcome(plug), "superseded")
        self.assertEqual(self.rule_row(plug, rule), ("done", "delivered"))
        for _ in range(4):
            self.h.tick(advance=DAY / 2)
        self.assertEqual(len(self.starts), 1)
        self.assertEqual(self.h.backend.send_calls, [])
        codes = self.journal(plug)
        self.assertIn("pause.message_instead", codes)
        self.assertIn("resetmsg.sent", codes)
        self.assertIn("resetmsg.delivered", codes)
        self.assertNotIn("pause.continued", codes)
        self.assertEqual(self.kinds(plug), [])

    def test_a_message_counting_for_this_reset_is_carried_once_its_window_closes(self):
        """The meter shows the new window before reset_message's count closes the old one: the stop waits that look -
        nothing on a guess - and carries the message when it falls due."""
        plug, turn = self.stopped()
        self.rule(plug, base=0, adopted_at=int(self.h.now) - 3600)
        self.window(plug)
        self.h.home.set_turn(T1, turn, status="interrupted", completed_at=int(self.h.now))
        self.h.now = self.reset + 20
        plug.runtime.state.save_meter([{"bucket": "codex", "window_minutes": 300, "used_percent": 1,
                                        "reset_at": self.reset + 5 * 3600}], at=self.h.now)
        self.h.tick(advance=1)
        self.assertEqual(self.starts, [], "its window not closed yet: the stop waits for it")
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(self.starts, self.carried())
        self.assertEqual(self.h.backend.send_calls, [])

    def test_a_restart_after_the_carry_sends_nothing_again(self):
        plug, turn = self.stopped()
        self.after_reset(plug, turn)
        rule = self.rule(plug, state="ready", due_at=self.reset + 60)
        self.h.tick(advance=60)
        self.assertEqual(self.starts, self.carried())
        plug = self.restarted()
        for _ in range(5):
            self.h.tick(advance=60)
        self.assertEqual(len(self.starts), 1)
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(self.rule_row(plug, rule), ("done", "delivered"))

    def test_a_watcher_that_stopped_inside_the_launch_never_sends_it_again(self):
        """Its launch written, the watcher gone before anything else: the next one takes it as sent - never a second
        start, never core's send - and ends the continuation."""
        plug, turn = self.stopped()
        self.after_reset(plug, turn)
        rule = self.rule(plug, state="ready", due_at=self.reset + 60)
        self.assertTrue(plug.runtime.state.carry_message(rule, at=self.h.now))
        plug = self.restarted()
        for _ in range(5):
            self.h.tick(advance=60)
        self.assertEqual(self.starts, [])
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(self.outcome(plug), "superseded")

    def test_where_the_app_refuses_the_start_the_message_waits_with_its_words(self):
        self.start_answer = ipc.Stop.REFUSED
        plug, turn = self.stopped()
        self.after_reset(plug, turn)
        rule = self.rule(plug, state="ready", due_at=self.reset + 60)
        self.h.tick(advance=60)
        row = plug.runtime.state.reset_rule(rule)
        self.assertEqual((row["state"], row["record_state"], row["words"], row["launching_at"]),
                         ("ready", "waiting", WORDS, None))
        self.assertEqual(self.h.backend.send_calls, [], "not handed to core while the stop waits to continue")
        self.assertIn("not_continued", self.kinds(plug))
        self.start_answer = ipc.Start.STARTED
        self.h.tick(advance=301)
        self.assertEqual(len(self.starts), 2, "asked again after the backoff, once started")
        self.assertEqual(self.starts[-1], self.carried()[0])
        self.assertEqual(self.outcome(plug), "superseded")


class NotThisResetTests(CarryCase):
    def counted(self, plug):
        """This reset counted already by reset_message's watch: no window open, one reset."""
        plug.runtime.state.save_windows([{"bucket": "codex", "minutes": 300, "open_reset_at": None, "open_full": False,
                                          "last_closed_at": self.reset, "resets": 1, "hits": 0, "seen_at": self.h.now,
                                          "misses": 0}])

    def continued(self, plug):
        self.assertEqual(len(self.starts), 1)
        self.assertFalse(self.starts[0][1].startswith(WORDS), "the stop's own continuation")
        self.assertIn("pause.continued", self.journal(plug))
        self.assertNotIn("pause.message_instead", self.journal(plug))

    def test_a_message_for_the_second_reset_with_one_counted_leaves_the_continuation(self):
        """V2: fails with the counting check that ignores which reset the window counted."""
        plug, turn = self.stopped()
        self.after_reset(plug, turn)
        self.rule(plug, ordinal=2, base=0, adopted_at=int(self.h.now) - 3600)
        self.counted(plug)
        for _ in range(3):
            self.h.tick(advance=61)
        self.continued(plug)

    def test_a_next_reset_message_made_after_this_reset_was_counted_leaves_the_continuation(self):
        plug, turn = self.stopped()
        self.after_reset(plug, turn)
        self.rule(plug, ordinal=1, base=1, adopted_at=int(self.h.now))
        self.counted(plug)
        for _ in range(3):
            self.h.tick(advance=61)
        self.continued(plug)

    def test_a_message_held_for_a_person_leaves_the_continuation(self):
        """V3: held for a gap longer than the window, it goes only on a person's Go on and may never go."""
        plug, turn = self.stopped()
        self.rule(plug, state="held", reason="count_gap")
        self.after_reset(plug, turn)
        for _ in range(3):
            self.h.tick(advance=61)
        self.continued(plug)


class AlreadyQueuedTests(CarryCase):
    def test_a_message_already_in_the_paused_queue_starts_nothing_beside_it_and_asks_for_resume(self):
        """V5: sent into the paused queue (as core did before this version), the message is there and only a turn lets
        it go: no continuation beside it, the person asked to press Resume - and the stop's continuation still waits,
        so a chat message sent there meanwhile is not taken back (engine/chat.paused_by_stop). Their Resume ends it."""
        plug, turn = self.stopped()
        self.after_reset(plug, turn)
        rule = self.rule(plug, state="ready", due_at=self.reset + 60)
        state = plug.runtime.state
        queue_id = self.h.home.enqueue(T1, WORDS + "\n\n" + ids.short_marker(instead.RECORD))
        self.assertTrue(state.carry_message(rule, at=self.reset + 70))
        self.assertTrue(state.carried_message(rule, True, at=self.reset + 70))
        self.assertIsNotNone(state.record_moved(instead.RECORD, "sent", at=self.reset + 70, queue_id=queue_id))
        for _ in range(5):
            self.h.tick(advance=60)
        self.assertEqual(self.starts, [])
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(self.kinds(plug), ["press_resume"])
        self.assertIn("pause.resume_unproven", self.journal(plug))
        stops = state.continuations(thread_id=T1, pending=None)
        self.assertEqual([stop["finished_at"] for stop in stops], [None], "the stop's continuation still waits")
        chat = {"thread_id": T1, "sent_at": self.h.now}
        self.assertTrue(chat_engine.paused_by_stop(chat, stops), "a chat sent now is left with Codex")
        self.h.home.dispatch(T1)                                      # the person pressed Resume: their message ran
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertEqual(self.starts, [])
        self.assertEqual(self.outcome(plug), "superseded")
        self.assertEqual(self.rule_row(plug, rule), ("done", "delivered"))


if __name__ == "__main__":
    unittest.main()
