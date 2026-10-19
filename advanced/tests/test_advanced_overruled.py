"""One capability's answer overruled by another's (v0.6.17, issue #42): queue for opening kept on beside marker-free
continuation.

Core carries P16's QUEUE_FOR_OPEN only through its own backend, with its marker (core's engine/foropen.py). Marker-free
continuation answers P5 and P15 for every send, and taken there for a continuation queued for opening it left the
record waiting with notLoaded and nothing sent, while the journal said queue_for_open had acted. Now marker-free stands
aside for that send - core's backend sends it with its marker, into Codex's queue - and says so: an `overruled` journal
line that names the route it stood aside for, and the Dashboard's list carries which capability that was. A
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
from codex_auto_resume_advanced.codex import protocol  # noqa: E402
from codex_auto_resume_advanced.engine.markerfree import MarkerFreeContinuation  # noqa: E402
from codex_auto_resume_advanced.registry import MARKER_FREE  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Actor, JournalCode, Measurement, OverrideKind, Verdict  # noqa: E402
from test_advanced_marker_free import FakeAppServer, FakeBackend  # noqa: E402
from test_advanced_queue_for_open import ForOpenCase  # noqa: E402
from test_engine import T1  # noqa: E402

MARKER_FREE_ID = MARKER_FREE.id


class BothArmedCase(ForOpenCase):
    """Queue for opening and marker-free continuation both on, as a person turns them on, on a Codex both are measured
    and compatible on; marker-free's channel reaches a fake app server."""
    BESIDE = (MARKER_FREE,)

    def setUp(self):
        super().setUp()
        self.compat = {"status": "ok", "engine": {"found": True, "version": ac.ENGINE},
                       "capabilities": {name: {"state": "COMPATIBLE", "reason": "local_checks_passed"}
                                        for name in (MARKER_FREE.compat, self.DEFINITION.compat)}}
        self.measured = {Measurement.M7: (Verdict.PASS, ac.ENGINE), Measurement.M1: (Verdict.PASS, ac.ENGINE)}
        self.fake = FakeAppServer(self.h)
        h = self.h
        for target, name, value in (
                (protocol.S, "Popen", self.fake.popen),
                (MarkerFreeContinuation, "_session",
                 lambda _self: protocol.Session(FakeBackend(h.home.root), capability=MARKER_FREE_ID))):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def marker_free_journal(self, plug):
        return [(line["code"], line["point"], line["answer"])
                for line in plug.runtime.state.journal(capability=MARKER_FREE_ID)]

    def spent_by(self, plug):
        with contextlib.closing(sqlite3.connect(plug.runtime.state.path)) as connection:
            return [row[0] for row in connection.execute("SELECT capability FROM spend")]

    def listed(self, plug, capability):
        return next(item for item in plug.runtime.arming.listing()["capabilities"] if item["id"] == capability)


class ForOpenTests(BothArmedCase):
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

    def test_the_overrule_is_journalled_naming_both_and_the_dashboard_list_names_the_capability(self):
        """Fails with the fix reverted: marker-free was journalled as having acted, and the list said nothing."""
        plug = self.armed()
        self.assertIsNone(self.listed(plug, MARKER_FREE_ID)["overruled_by"])
        self.due()
        self.h.tick()
        lines = self.marker_free_journal(plug)
        self.assertIn((JournalCode.OVERRULED, Point.SENDER, Alternative.QUEUE_FOR_OPEN), lines)
        self.assertIn((JournalCode.OVERRULED, Point.DELIVERY, Alternative.QUEUE_FOR_OPEN), lines)
        self.assertNotIn(JournalCode.ACTED, [code for code, _point, _answer in lines], "not a silent 'acted'")
        self.assertIn((JournalCode.ACTED, Point.UNLOADED, Alternative.QUEUE_FOR_OPEN), self.journal(plug))
        self.assertEqual(self.listed(plug, MARKER_FREE_ID)["overruled_by"], self.cap)
        self.assertIsNone(self.listed(plug, self.cap)["overruled_by"])
        # Turned off it shows none; turned on again it is let go of - the word is about since it stood where it stands.
        self.h.now += 5
        self.assertTrue(plug.runtime.arming.disarm(MARKER_FREE_ID, actor=Actor.DASHBOARD)["done"])
        self.assertIsNone(self.listed(plug, MARKER_FREE_ID)["overruled_by"])
        self.h.now += 5
        self.arm(plug, capability=MARKER_FREE_ID)
        self.assertIsNone(self.listed(plug, MARKER_FREE_ID)["overruled_by"])


class LoadedTests(BothArmedCase):
    def test_a_conversation_the_app_holds_is_still_marker_frees_to_send(self):
        """Unchanged by the fix: no route at P16, so marker-free's channel sends it under the derived id."""
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
        self.assertIsNone(self.listed(plug, MARKER_FREE_ID)["overruled_by"])
        self.assertEqual(self.spent_by(plug), [MARKER_FREE_ID])


if __name__ == "__main__":
    unittest.main()
