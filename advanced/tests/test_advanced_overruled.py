"""One capability's answer overruled by another's (v0.6.17, issue #42): queue for opening kept on beside marker-free
continuation.

Core carries P16's QUEUE_FOR_OPEN only through its own backend, with its marker (core's engine/foropen.py). Marker-free
continuation answers P5 and P15 for every send, and taken there for a continuation queued for opening it left the
record waiting with notLoaded and nothing sent, while the journal said queue_for_open had acted. Now marker-free stands
aside for that send - core's backend sends it with its marker, into Codex's queue - and says so: an `overruled` journal
line that names the capability it stood aside for. That is a split - each goes on serving its own cases - so the
Dashboard shows nothing for it; the word there is for a capability whose answer another one voided (VoidTests). A
conversation the app holds it still serves through its own channel.

Held against the shipped definitions and statements and against core's own engine, store and simulated Codex home
(takingcase.py); marker-free's channel speaks to the fake app server of test_advanced_marker_free.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

import contextlib
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase as ac  # noqa: E402
from codex_auto_resume.domain import ids  # noqa: E402
from codex_auto_resume.domain.plug import Alternative, Point  # noqa: E402
from codex_auto_resume_advanced import runtime  # noqa: E402
from codex_auto_resume_advanced.codex import protocol  # noqa: E402
from codex_auto_resume_advanced.engine.markerfree import MarkerFreeContinuation  # noqa: E402
from codex_auto_resume_advanced.registry import MARKER_FREE  # noqa: E402
from codex_auto_resume_advanced.vocabulary import (Actor, ArmingWarning, JournalCode, Measurement,  # noqa: E402
                                                   OverrideKind, Verdict)
from test_advanced_marker_free import FakeAppServer, FakeBackend  # noqa: E402
from test_advanced_other_sessions import SessionsCase  # noqa: E402
from test_advanced_queue_for_open import ForOpenCase  # noqa: E402
from test_engine import T1  # noqa: E402

MARKER_FREE_ID = MARKER_FREE.id


class BothArmedCase(ForOpenCase):
    """Queue for opening and marker-free continuation both on, as a person turns them on, on a Codex both are measured
    and compatible on; marker-free's channel reaches a fake app server."""
    BESIDE = (MARKER_FREE,)
    # Whether the Desktop starts an item the moment it is added: it holds the conversation. Not for one it does not.
    DISPATCH = False

    def setUp(self):
        super().setUp()
        self.compat = {"status": "ok", "engine": {"found": True, "version": ac.ENGINE},
                       "capabilities": {name: {"state": "COMPATIBLE", "reason": "local_checks_passed"}
                                        for name in (MARKER_FREE.compat, self.DEFINITION.compat)}}
        self.measured = {Measurement.M7: (Verdict.PASS, ac.ENGINE), Measurement.M1: (Verdict.PASS, ac.ENGINE)}
        self.fake = FakeAppServer(self.h, dispatch=self.DISPATCH)
        h = self.h
        for target, name, value in (
                (protocol.S, "Popen", self.fake.popen),
                (MarkerFreeContinuation, "_session",
                 lambda _self: protocol.Session(FakeBackend(h.home.root), capability=MARKER_FREE_ID))):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def marker_free_journal(self, plug, reasons=False):
        return [(line["code"], line["point"], line["answer"]) + ((line["reason"],) if reasons else ())
                for line in plug.runtime.state.journal(capability=MARKER_FREE_ID)]

    def spent_by(self, plug):
        with contextlib.closing(sqlite3.connect(plug.runtime.state.path)) as connection:
            return [row[0] for row in connection.execute("SELECT capability FROM spend")]

    def listed(self, plug, capability):
        return next(item for item in plug.runtime.arming.listing()["capabilities"] if item["id"] == capability)


class ForOpenTests(BothArmedCase):
    """MQO unmeasured on this Codex (the fallback): core's backend carries a continuation queued for opening."""

    def test_a_continuation_for_opening_goes_through_cores_backend_with_its_marker_and_marker_free_sends_nothing(self):
        """Fails with the fix reverted: marker-free's channel was taken, and core waited notLoaded, nothing queued."""
        plug = self.armed()
        self.due()
        self.h.tick()
        row = self.h.record()
        self.assertEqual(row["state"], "queued", row["last_error"])
        self.assertEqual(len(self.h.backend.send_calls), 1, "core's backend sent it")
        self.assertTrue(self.prompt().endswith(row["marker"]), "with core's marker")
        self.assertEqual(self.h.home.queued(T1), [row["queue_id"]], "into Codex's queue")
        self.assertEqual((self.fake.started, self.fake.adds()), ([], []), "marker-free opened and sent nothing")
        self.assertIsNone(row.get("recovery_client_id"), "proven by the marker, not a client id")
        self.assertEqual(self.override(plug, row)["kind"], OverrideKind.QUEUE_FOR_OPEN)
        self.assertEqual(self.spent_by(plug), [self.cap], "queue for opening paid for it, marker-free nothing")
        self.h.tick(advance=60)
        self.assertEqual(len(self.h.backend.send_calls), 1, "never sent twice")
        self.assertEqual(self.fake.adds(), [], "never a marker-free copy of the same continuation")

    def test_the_overrule_is_journalled_naming_both_and_the_dashboard_shows_nothing_for_a_split(self):
        """Fails with the fix reverted: marker-free was journalled as having acted, and nothing named the other."""
        plug = self.armed()
        self.due()
        self.h.tick()
        lines = self.marker_free_journal(plug)
        self.assertIn((JournalCode.OVERRULED, Point.SENDER, self.cap), lines, "names queue_for_open")
        self.assertIn((JournalCode.OVERRULED, Point.DELIVERY, self.cap), lines)
        self.assertIn((JournalCode.OVERRULED, Point.SENDER, self.cap, ArmingWarning.UNMEASURED),
                      self.marker_free_journal(plug, reasons=True), "and why: MQO not measured on this Codex")
        self.assertNotIn(JournalCode.ACTED, [code for code, _point, _answer in lines], "not a silent 'acted'")
        self.assertIn((JournalCode.ACTED, Point.UNLOADED, Alternative.QUEUE_FOR_OPEN), self.journal(plug))
        # A split: each serves its own cases, so neither shows a word on the Dashboard.
        self.assertIsNone(self.listed(plug, MARKER_FREE_ID)["voided_by"])
        self.assertIsNone(self.listed(plug, self.cap)["voided_by"])


class MeasuredTests(BothArmedCase):
    """Route b (v0.6.17): with MQO passed for the Codex in force, both apply to the same record - queued for opening,
    with no marker, under its client id, and proven by it when the person opens the conversation."""

    def test_passed_it_is_queued_for_opening_with_no_marker_and_proven_by_its_client_id_on_open(self):
        """Fails with route b reverted: marker-free stood aside, and core's backend sent it with the marker."""
        self.measured[Measurement.MQO] = (Verdict.PASS, ac.ENGINE)
        plug = self.armed()
        self.due()
        key = self.h.record()["interruption_id"]
        self.h.tick()
        row = self.h.record()
        self.assertEqual(row["state"], "queued", row["last_error"])
        self.assert_no_send()
        (add,) = self.fake.adds()
        client = ids.continuation_client_id(key)
        self.assertEqual((add["threadId"], add["clientUserMessageId"]), (T1, client))
        self.assertNotIn(ids.MARKER_PREFIX, add["input"][0]["text"], "no marker")
        self.assertEqual(row["recovery_client_id"], client)
        self.assertEqual(self.h.home.queued(T1), [row["queue_id"]], "left in Codex's queue for the person to open")
        self.assertEqual(self.override(plug, row)["kind"], OverrideKind.QUEUE_FOR_OPEN)
        self.assertEqual(sorted(self.spent_by(plug)), sorted([self.cap, MARKER_FREE_ID]), "both paid for it")
        self.assertNotIn(JournalCode.OVERRULED, [line[0] for line in self.marker_free_journal(plug)])
        self.h.tick(advance=60)
        self.assertEqual((len(self.fake.adds()), self.h.backend.send_calls), (1, []), "never sent twice")
        # The person opens it: the Desktop runs the item, and the turn is found by its client id.
        self.h.backend.loaded_map[T1] = "loaded"
        self.h.home.dispatch(T1)
        ours = self.h.turn_ids()[-1]
        for _ in range(3):                  # the watch of an item queued for opening looks once a poll
            self.h.tick(advance=30)
        row = self.h.record()
        self.assertEqual((row["state"], row["recovery_turn_id"]), ("recovered", ours))
        self.assertEqual((len(self.fake.adds()), self.h.backend.send_calls), (1, []))

    def test_failed_it_falls_back_to_cores_marker_and_the_journal_says_the_measurement_failed(self):
        """Fails with the reason reverted: the journal did not say why marker-free stood aside."""
        self.measured[Measurement.MQO] = (Verdict.FAIL, ac.ENGINE)
        plug = self.armed()
        self.due()
        self.h.tick()
        row = self.h.record()
        self.assertEqual(row["state"], "queued", row["last_error"])
        self.assertTrue(self.prompt().endswith(row["marker"]), "core's backend, with its marker")
        self.assertEqual(self.fake.adds(), [])
        self.assertIn((JournalCode.OVERRULED, Point.SENDER, self.cap, ArmingWarning.MEASUREMENT_FAILED),
                      self.marker_free_journal(plug, reasons=True))

    def test_passed_on_another_codex_is_not_a_pass_here(self):
        self.measured[Measurement.MQO] = (Verdict.PASS, "codex-cli 0.0.1")
        plug = self.armed()
        self.due()
        self.h.tick()
        self.assertTrue(self.prompt().endswith(self.h.record()["marker"]))
        self.assertIn((JournalCode.OVERRULED, Point.SENDER, self.cap, ArmingWarning.UNMEASURED),
                      self.marker_free_journal(plug, reasons=True))


class ToSessionTests(SessionsCase):
    """P-2, #42's bug for the other route: other_sessions and marker-free continuation both on, and a conversation
    another Codex session - a terminal's, VS Code's - holds. MQO does not cover a session taking an item, so marker-free
    stands aside whatever MQO says, and core's backend sends it with its marker for that session to take."""
    BESIDE = (MARKER_FREE,)

    def setUp(self):
        super().setUp()
        self.compat = {"status": "ok", "engine": {"found": True, "version": ac.ENGINE},
                       "capabilities": {name: {"state": "COMPATIBLE", "reason": "local_checks_passed"}
                                        for name in (MARKER_FREE.compat, self.DEFINITION.compat)}}
        self.measured = {Measurement.M7: (Verdict.PASS, ac.ENGINE), Measurement.MQO: (Verdict.PASS, ac.ENGINE)}
        self.fake = FakeAppServer(self.h, dispatch=False)
        h = self.h
        for target, name, value in (
                (protocol.S, "Popen", self.fake.popen),
                (MarkerFreeContinuation, "_session",
                 lambda _self: protocol.Session(FakeBackend(h.home.root), capability=MARKER_FREE_ID))):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_continuation_for_another_session_goes_with_cores_marker_and_marker_free_stands_aside(self):
        """Fails with the fix reverted: marker-free's channel was taken, and core waited held_by_other_session."""
        plug, row = self.queued()
        self.assertEqual(len(self.h.backend.send_calls), 1, "core's backend sent it")
        self.assertTrue(self.prompt().endswith(row["marker"]), "with core's marker")
        self.assertEqual(self.fake.adds(), [], "marker-free sent nothing")
        lines = [(line["code"], line["point"], line["answer"], line["reason"])
                 for line in plug.runtime.state.journal(capability=MARKER_FREE_ID)]
        self.assertIn((JournalCode.OVERRULED, Point.SENDER, self.cap, ArmingWarning.UNMEASURED), lines,
                      "names other_sessions, and why: no measurement covers it")
        self.assertNotIn(JournalCode.ACTED, [line[0] for line in lines])


class VoidTests(BothArmedCase):
    """The general mechanism's other settlement (runtime.CONFLICTS' VOID), held on the same pair configured so: the
    later answer is taken, the earlier one is not paid for, and its capability - which could not act at all on a
    record it took up - is journalled as voided by the other and shown so on the Dashboard."""

    def setUp(self):
        super().setUp()
        voiding = tuple(line[:4] + (runtime.VOID,) for line in runtime.CONFLICTS)
        patcher = patch.object(runtime, "CONFLICTS", voiding)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_voided_answer_is_journalled_naming_the_other_and_the_dashboard_says_which(self):
        """Fails with the mechanism reverted: nothing journals queue_for_open's answer as voided, nor lists it."""
        plug = self.armed()
        self.due()
        self.h.tick()
        journal = self.journal(plug)
        self.assertIn((JournalCode.VOIDED, Point.UNLOADED, MARKER_FREE_ID), journal)
        self.assertIn((JournalCode.ACTED, Point.SENDER, Point.SENDER), self.marker_free_journal(plug))
        self.assertEqual(self.listed(plug, self.cap)["voided_by"], MARKER_FREE_ID)
        self.assertIsNone(self.listed(plug, MARKER_FREE_ID)["voided_by"])
        self.assertNotIn(self.cap, self.spent_by(plug), "a voided answer is not paid for")
        # Turned off it shows none; turned on again it is let go of - the word is about since it stood where it stands.
        self.h.now += 5
        self.assertTrue(plug.runtime.arming.disarm(self.cap, actor=Actor.DASHBOARD)["done"])
        self.assertIsNone(self.listed(plug, self.cap)["voided_by"])
        self.h.now += 5
        self.arm(plug)
        self.assertIsNone(self.listed(plug, self.cap)["voided_by"])


class LoadedTests(BothArmedCase):
    DISPATCH = True

    def test_a_conversation_the_app_holds_is_still_marker_frees_to_send(self):
        """Unchanged by the fix: no route at P16, so marker-free's channel sends it under the derived id - MQO
        measured or not."""
        plug = self.armed()
        self.ready_after_reset(loaded=True)
        key = self.h.record()["interruption_id"]
        self.h.tick()
        self.assert_no_send()
        (add,) = self.fake.adds()
        self.assertEqual(add["clientUserMessageId"], ids.continuation_client_id(key))
        self.assertNotIn(ids.MARKER_PREFIX, add["input"][0]["text"])
        lines = self.marker_free_journal(plug)
        self.assertIn((JournalCode.ACTED, Point.SENDER, Point.SENDER), lines)
        self.assertNotIn(JournalCode.OVERRULED, [code for code, _point, _answer in lines])
        self.assertIsNone(self.listed(plug, MARKER_FREE_ID)["voided_by"])
        self.assertEqual(self.spent_by(plug), [MARKER_FREE_ID])


if __name__ == "__main__":
    unittest.main()
