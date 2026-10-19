"""P16's QUEUE_FOR_OPEN (v0.6.15-beta): a conversation the app does not hold is sent the ordinary continuation, left in
Codex's queue for when it is opened - kept only while the plug says so, and seven days and an hour at most - and every
withdrawal core makes of a queued item still fires at once.

The plug is a test's own (test_plug_points.Asked) answering QUEUE_FOR_OPEN at P16; the engine runs against codexsim.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_engine import T1  # noqa: E402
from test_plug_points import Asked, Channel, PluggedCase  # noqa: E402
from sessionsim import holding_sessions  # noqa: E402
from codex_auto_resume import machine  # noqa: E402
from codex_auto_resume.domain import ids  # noqa: E402
from codex_auto_resume.domain.plug import DEFER, Alternative, BACKEND  # noqa: E402
from codex_auto_resume.engine.foropen import DEFERRED_LONGEST  # noqa: E402

DAY = 86400.0


class ForOpen(PluggedCase):
    def queued_for_open(self, h=None, **answers):
        """A usage-limited conversation the app does not hold, sent for when it is opened and left in Codex's queue."""
        h = h or self.h
        self.ready_after_reset(h, loaded=False)
        h.backend.loaded_map[T1] = "notLoaded"
        h.backend.after_accept = "queue"
        plug = Asked(unloaded=Alternative.QUEUE_FOR_OPEN, **answers)
        self.plugged(plug, h)
        h.tick()
        row = h.record()
        self.assertEqual(row["state"], "queued", row["last_error"])
        self.assertEqual(len(h.backend.send_calls), 1)
        return plug, row

    def state(self, h=None):
        row = (h or self.h).record()
        return row["state"], row["last_error"]


class QueueTests(ForOpen):
    def test_it_goes_the_ordinary_way_and_is_kept_three_days(self):
        plug, row = self.queued_for_open()
        self.assertIn(row["marker"], self.h.backend.send_calls[0][1])
        self.assertEqual(machine.decode_gates(row["gate_eval"])["thread_available"], (machine.PASS, machine.PLUGGED))
        for _ in range(3 * 24):
            self.h.tick(advance=3600)
        self.assertEqual(self.h.record()["state"], "queued")
        self.assertEqual(self.h.backend.deleted, [], "nothing taken back while the plug keeps it")

    def test_unknown_never_qualifies(self):
        self.ready_after_reset(loaded=False)
        self.h.backend.loaded_map[T1] = "unknown"
        self.plugged(Asked(unloaded=Alternative.QUEUE_FOR_OPEN))
        self.h.tick()
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(self.h.record()["last_error"], "loaded_state_unknown")

    def test_a_channel_with_the_marker_waits_as_a11_says(self):
        h = self.fresh()
        self.ready_after_reset(h, loaded=False)
        h.backend.loaded_map[T1] = "notLoaded"
        channel = Channel(h)
        self.plugged(Asked(unloaded=Alternative.QUEUE_FOR_OPEN, sender=lambda record, backend: channel), h)
        h.tick()
        self.assertEqual((h.backend.send_calls, channel.calls), ([], []))
        self.assertEqual(h.record()["last_error"], "notLoaded")

    def test_a_channel_under_a_client_id_the_plug_named_carries_it_with_no_marker(self):
        """v0.6.17 (issue #42): the door only a plug opens - its channel, under the client id core derives, proven by
        that id. Fails with the door reverted: it waited notLoaded and nothing was sent."""
        h = self.fresh()
        self.ready_after_reset(h, loaded=False)
        h.backend.loaded_map[T1] = "notLoaded"
        sent = []

        class ClientChannel:
            def send(self, thread_id, prompt, *, launch_guard=None, client_id=None):
                with launch_guard as permitted:
                    sent.append((thread_id, prompt, permitted, client_id))
                return {"outcome": "unknown"}
        self.plugged(Asked(unloaded=Alternative.QUEUE_FOR_OPEN, sender=lambda record, backend: ClientChannel(),
                           delivery=Alternative.CLIENT_ID), h)
        h.tick()
        self.assertEqual(h.backend.send_calls, [], "not core's backend")
        ((thread, prompt, permitted, client),) = sent
        row = h.record()
        self.assertEqual((thread, permitted, client), (T1, True, ids.continuation_client_id(row["interruption_id"])))
        self.assertNotIn(row["marker"], prompt)
        self.assertEqual(row["recovery_client_id"], client)

    def test_to_session_never_goes_through_the_door_even_with_a_channel_and_a_client_id(self):
        """v0.6.17: the door is QUEUE_FOR_OPEN's alone - no measurement proves a session takes an item by its client id.
        Fails with the door opened for TO_SESSION too: the plug's channel sent it under the client id."""
        h = self.fresh()
        holding_sessions(h.backend)
        self.ready_after_reset(h, loaded=False)
        h.backend.loaded_map[T1] = "elsewhere"
        sent = []

        class ClientChannel:
            def send(self, thread_id, prompt, *, launch_guard=None, client_id=None):
                with launch_guard as permitted:
                    sent.append((thread_id, permitted, client_id))
                return {"outcome": "unknown"}
        def held(record):
            return Alternative.TO_SESSION if record.get("holder") == "session" else DEFER
        self.plugged(Asked(unloaded=held, sender=lambda record, backend: ClientChannel(),
                           delivery=Alternative.CLIENT_ID), h)
        h.tick()
        self.assertEqual((h.backend.send_calls, sent), ([], []))
        self.assertEqual(h.record()["last_error"], "held_by_other_session")

    def test_the_plug_no_longer_keeping_it_takes_it_back_and_gives_it_back(self):
        plug, row = self.queued_for_open()
        plug.answers["unloaded"] = DEFER
        self.h.watch(advance=61)
        self.assertEqual(self.state(), ("withdrawn_unconfirmed", "window_ended"))
        self.assertEqual(self.h.home.queued(T1), [], "deleted at once")
        for _ in range(4):
            self.h.watch(advance=60)
        released = self.h.record()
        self.assertIn(released["state"], machine.WAITING)
        self.assertEqual(released["last_error"], "released_after_withdrawal")
        self.assertEqual(released["chain_continuations"], row["chain_continuations"] - 1, "its claim given back")

    def test_seven_days_and_an_hour_whatever_the_plug_says(self):
        """Fails with the cap reverted: the plug keeps answering QUEUE_FOR_OPEN."""
        plug, row = self.queued_for_open()
        self.h.tick(advance=DEFERRED_LONGEST - 120)
        self.assertEqual(self.h.record()["state"], "queued")
        self.h.tick(advance=240)
        self.assertEqual(self.state(), ("withdrawn_unconfirmed", "window_ended"))

    def test_opened_and_not_delivered_it_is_given_back_and_sent_the_ordinary_way(self):
        plug, row = self.queued_for_open()
        self.h.backend.loaded_map[T1] = "loaded"         # opened, and Codex does not run the queue head
        self.h.watch(advance=6)
        self.assertEqual(self.h.record()["state"], "queued")
        self.h.watch(advance=200)
        self.assertEqual(self.state(), ("withdrawn_unconfirmed", "not_delivered_on_open"))
        told = [args for hook, args in plug.asked if hook == "moved" and args[1] == "withdrawn_unconfirmed"]
        self.assertEqual(told[-1][0]["withdraw_reason"], "not_delivered_on_open", "P14 is told why")
        for _ in range(4):
            self.h.watch(advance=60)
        self.assertIn(self.h.record()["state"], machine.WAITING)

    def test_every_other_withdrawal_fires_at_once(self):
        cases = {
            "cancel": lambda h, row: h.store.cancel_interruption(row["interruption_id"], h.now, actor="gui"),
            "thread_disabled": lambda h, row: h.store.set_thread_enabled(T1, False, at=h.now),
            "paused": lambda h, row: h.store.set_enabled(False, h.now),
            "observe_only": lambda h, row: h.store.set_observe_only(True),
            "superseded_by_user": lambda h, row: h.home.add_turn(T1),
            "user_queued_input": lambda h, row: h.home.enqueue(T1, "something of my own"),
        }
        in_codex = {"superseded_by_user", "user_queued_input"}
        for reason, act in cases.items():
            with self.subTest(reason):
                h = self.fresh()
                plug, row = self.queued_for_open(h)
                h.tick(advance=1)                          # seen once: the one-second watch then rests
                act(h, row)
                if reason in in_codex:
                    h.tick(advance=60)                     # what Codex says, at the next poll's look
                else:
                    h.watch(advance=1)                     # what the store says, within a second
                found = h.record()
                self.assertEqual(found["withdraw_reason"], reason, found["state"])

    def test_the_one_second_watch_rests_but_sees_a_pause_within_a_second(self):
        plug, row = self.queued_for_open()
        self.h.tick(advance=1)
        calls = self.h.backend.identity_calls
        for _ in range(30):
            self.h.watch(advance=1)
        self.assertLessEqual(self.h.backend.identity_calls - calls, 1, "one look at Codex a poll, not one a second")
        self.h.store.set_enabled(False, self.h.now)
        self.h.watch(advance=1)
        self.assertEqual(self.state()[0], "withdrawn_unconfirmed")

    def test_an_edit_hands_it_over(self):
        plug, row = self.queued_for_open()
        self.h.home.edit_queued(self.h.home.queued(T1)[0], "my own words")
        self.h.watch(advance=1)
        self.assertEqual(self.state(), ("handed_over", "queued_item_edited"))

    def test_delivered_on_open_is_an_ordinary_recovery(self):
        plug, row = self.queued_for_open()
        self.h.backend.loaded_map[T1] = "loaded"
        self.h.home.dispatch(T1)
        self.follow()
        self.assertEqual(self.h.record()["state"], "recovered")


if __name__ == "__main__":
    unittest.main()
