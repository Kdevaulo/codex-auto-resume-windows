"""MQO (v0.6.17, issue #42): a continuation queued for opening with no marker, proven by its client id.

The probe calls exactly the methods it declared, stops before adding anything where the app holds the conversation,
adds one item with no marker under a client id of no one's, follows the queue while the person opens the
conversation, and looks for that client id in Codex's history the way core proves a marker-free continuation
delivered (measure._client_recorded: LocalSource.marker_rows, which engine/reconcile.py reads). It records booleans
and a bucket only, and its verdict stays blocked for the person who watched. Nothing here opens a real Codex.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advancedcase  # noqa: E402,F401  (puts src, advanced/src and tests on the path)
from codex_auto_resume_advanced import measure, measured  # noqa: E402
from codex_auto_resume_advanced.codex import protocol  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Measurement, Verdict  # noqa: E402
from test_advanced_measure_stage4 import THREAD, VERSIONS, Backend, FakeSession  # noqa: E402

MQO = Measurement.MQO
ITEM = {"id": "q", "clientUserMessageId": measure._SAMPLE_MQO_CLIENT_ID}


class MqoCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.dir, ignore_errors=True))
        for name, value in (("_MQO_OPEN_SECONDS", 0.05), ("_MQO_FIND_SECONDS", 0.05), ("_M2B_POLL_SECONDS", 0.01)):
            patcher = patch.object(measure, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.sessions, self.looked_for = [], []

    def run_one(self, *, held=(), lists=None, recorded=True):
        """MQO against a fake: the app holds `held`; each thread/queue/list answers the next of `lists` (the last
        again once they run out); the history has the client id or not (`recorded`)."""
        answers = list(lists if lists is not None else ([ITEM], []))

        def queue_list(_params):
            return {"data": answers.pop(0) if len(answers) > 1 else answers[0]}
        replies = {"thread/loaded/list": {"data": list(held)}, "thread/queue/add": {"queuedSubmissionId": "q"},
                   "thread/queue/list": queue_list}

        def factory(measurement):
            self.sessions.append(FakeSession(measurement, replies))
            return self.sessions[-1]

        def history(ctx, client_id):
            self.looked_for.append(client_id)
            return recorded
        with patch.object(measure, "_client_recorded", history):
            summary = measure.run(MQO, session_factory=factory, backend=Backend(), versions=VERSIONS, thread=THREAD,
                                  clock=lambda: 1_800_000_000.0, directory=self.dir)
        return summary, json.loads(Path(summary["recorded"]).read_text(encoding="utf-8"))

    def calls(self):
        return [(method, params) for session in self.sessions for method, params in session.calls]


class ShapeTests(MqoCase):
    def test_it_declares_its_three_methods_and_has_a_probe(self):
        self.assertEqual(protocol.MEASUREMENT_METHODS[MQO], ("thread/loaded/list", "thread/queue/add",
                                                             "thread/queue/list"))
        self.assertIs(measure.PROBES[MQO], measure._mqo)
        self.assertNotIn(MQO, measured.MEASURED, "unmeasured until the owner's run")

    def test_queued_then_taken_on_open_and_found_by_its_client_id_in_the_history(self):
        summary, record = self.run_one()
        self.assertEqual(record["verdict"], Verdict.BLOCKED, "the person who watched settles it")
        observed = record["observed"]
        self.assertEqual({key: observed[key] for key in ("held_before", "add_accepted", "queued_while_not_held",
                                                          "taken", "client_id_on_user_item")},
                         {"held_before": False, "add_accepted": True, "queued_while_not_held": True, "taken": True,
                          "client_id_on_user_item": True})
        self.assertEqual(self.looked_for[:1], [measure._SAMPLE_MQO_CLIENT_ID], "core's proof, by that client id")
        (add,) = [params for method, params in self.calls() if method == "thread/queue/add"]
        self.assertEqual(add["clientUserMessageId"], measure._SAMPLE_MQO_CLIENT_ID)
        self.assertNotIn("codex-auto-resume", json.dumps(add), "no marker")
        self.assertTrue({method for method, _params in self.calls()} <= set(protocol.MEASUREMENT_METHODS[MQO]))
        self.assertIn("open the throwaway conversation in the Desktop", record["note"])

    def test_a_conversation_the_app_holds_is_not_added_to(self):
        summary, record = self.run_one(held=(THREAD,))
        self.assertEqual(record["observed"]["held_before"], True)
        self.assertNotIn("thread/queue/add", [method for method, _params in self.calls()])

    def test_not_taken_in_time_and_the_history_is_not_read(self):
        summary, record = self.run_one(lists=([ITEM],), recorded=True)
        self.assertEqual((record["observed"]["taken"], record["observed"]["client_id_on_user_item"]), (False, False))
        self.assertEqual(self.looked_for, [])

    def test_the_record_is_content_free(self):
        summary, record = self.run_one()
        text = json.dumps(record)
        for secret in (THREAD, measure._SAMPLE_MQO_CLIENT_ID, measure._M2B_PROMPT):
            self.assertNotIn(secret, text)
        self.assertTrue(all(isinstance(value, (bool, int, str)) for value in record["observed"].values()))

    def test_the_client_id_look_is_cores_own_delivery_proof(self):
        """The look reads LocalSource.marker_rows with the client id - what core's reconcile follows a marker-free
        continuation by (engine/reconcile.py) - so a pass means marker-free can prove it."""
        found = []

        class Source:
            def __init__(self, home):
                pass

            def marker_rows(self, thread, token):
                found.append((thread, token))
                return [object()]
        ctx = measure.Context(MQO, backend=Backend(home=self.dir), thread=THREAD)
        with patch("codex_auto_resume.codex.LocalSource", Source):
            self.assertTrue(measure._client_recorded(ctx, measure._SAMPLE_MQO_CLIENT_ID))
        self.assertEqual(found, [(THREAD, measure._SAMPLE_MQO_CLIENT_ID)])
        reconcile = (Path(measure.__file__).resolve().parents[2].parent / "src" / "codex_auto_resume" / "engine"
                     / "reconcile.py").read_text(encoding="utf-8")
        self.assertIn("self.source.marker_rows(thread, marker)", reconcile)


if __name__ == "__main__":
    unittest.main()
