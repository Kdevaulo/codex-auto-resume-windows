"""The nine measurements stage 4 rests on (v0.6.16-beta.4): each probe calls exactly the methods it declared, records
only booleans, counts, buckets and closed words, and MB opens only a scratch Codex home of its own.

Every session is a fake that refuses a method its measurement did not declare, as the real one does; the files MO,
MXA and MC2 read are a temporary Codex home's. Nothing here opens a real Codex.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advancedcase  # noqa: E402,F401  (puts src, advanced/src and tests on the path)
from codex_auto_resume_advanced import evidence, measure  # noqa: E402
from codex_auto_resume_advanced.codex import protocol, sessions  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Measurement, ObservedWord, Verdict  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import live_evidence  # noqa: E402

THREAD = "0a1b2c3d-0001-7000-8000-0000000000aa"
TURN = "deadbeef-0000-7000-8000-00000000beef"
STAGE4 = (Measurement.M6B, Measurement.MO, Measurement.MX, Measurement.MXA, Measurement.MF, Measurement.M3B,
          Measurement.MB, Measurement.MC1, Measurement.MC2)
VERSIONS = {"product_version": "0.6.15-beta.3", "codex_version": "0.162.0-alpha.17.2", "windows_build": "10.0.26200"}
COMPLETED = {"method": "turn/completed", "params": {"threadId": THREAD, "turn": {"id": TURN, "status": "completed"}}}


class FakeSession:
    """A session answering `replies` by method (a callable is given the params), refusing any method its measurement
    did not declare exactly as the real one does, and handing `events` once."""

    def __init__(self, measurement, replies, events=(), home=None):
        self.allowed = protocol.methods_for(measurement)
        self.replies, self.events, self.home = replies, list(events), home
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def call(self, method, params=None):
        if method not in self.allowed:
            raise protocol.SessionRefused("not permitted for this measurement")
        self.calls.append((method, params))
        reply = self.replies.get(method, {})
        reply = reply(params) if callable(reply) else reply
        if isinstance(reply, Exception):
            raise reply
        return reply

    def drain_events(self):
        events, self.events = self.events, []
        return events

    def declined_count(self):
        return 2


class Backend:
    def __init__(self, home=None):
        self.codex_home, self.engine_version, self.codex_exe = home, VERSIONS["codex_version"], "codex.exe"

    def app_identity(self):
        return None


def refused(method, code=-32600):
    return protocol._refused_by_codex(method, code)


# What each probe is driven with to go its whole way.
REPLIES = {
    Measurement.M6B: {"thread/resume": {"sandbox": {"type": "workspaceWrite", "writableRoots": ["C:/work"]},
                                        "approvalPolicy": "on-request", "approvalsReviewer": "user",
                                        "activePermissionProfile": None, "model": "secret-model", "cwd": "C:/work"},
                      "turn/start": {"turn": {"id": TURN}}},
    Measurement.MX: {"thread/compact/start": {}},
    Measurement.MF: {"thread/resume": {"model": "the-threads-model"},
                     "model/list": {"data": [{"model": "codex-default", "isDefault": True},
                                             {"model": "the-threads-model", "isDefault": False}]},
                     "turn/start": {"turn": {"id": TURN}}},
    Measurement.M3B: {"turn/start": {"turn": {"id": TURN}}},
    Measurement.MB: {},
    Measurement.MC1: {"thread/queue/add": {"queuedSubmissionId": "q"}, "thread/queue/list": {"data": []}},
}


class ProbeCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.dir, ignore_errors=True))
        for name, value in (("_M6_TURN_SECONDS", 0.05), ("_M6_INTERRUPT_SECONDS", 0.05), ("_M6_POLL_SECONDS", 0.01),
                            ("_MC1_QUEUE_SECONDS", 0.05), ("_MC1_START_SECONDS", 0.05), ("_M2B_POLL_SECONDS", 0.01),
                            ("_MC2_SECONDS", 0.2), ("_MC2_POLL_SECONDS", 0.01)):
            patcher = patch.object(measure, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.sessions = []

    def factory(self, measurement, *, events=(COMPLETED,), with_home=False):
        replies = REPLIES.get(measurement, {})

        def plain(measured):
            self.sessions.append(FakeSession(measured, replies, events))
            return self.sessions[-1]

        def scratch(measured, home=None):
            self.sessions.append(FakeSession(measured, replies, events, home=home))
            return self.sessions[-1]
        return scratch if with_home else plain

    def run_one(self, measurement, factory=None, *, backend=None, thread=THREAD):
        summary = measure.run(measurement, session_factory=factory or self.factory(measurement),
                              backend=backend or Backend(), versions=VERSIONS, thread=thread,
                              clock=lambda: 1_800_000_000.0, directory=self.dir)
        record = json.loads(Path(summary["recorded"]).read_text(encoding="utf-8"))
        return summary, record

    def called(self):
        return [method for session in self.sessions for method, _params in session.calls]


class AllowListTests(ProbeCase):
    def test_every_new_measurement_has_its_methods_and_a_probe(self):
        for measurement in STAGE4:
            with self.subTest(measurement):
                self.assertIn(measurement, protocol.MEASUREMENT_METHODS)
                self.assertIn(measurement, measure.PROBES)

    def test_each_probe_calls_only_what_it_declared_and_reaches_its_end(self):
        for measurement in (Measurement.M6B, Measurement.MX, Measurement.MF, Measurement.M3B, Measurement.MC1):
            with self.subTest(measurement):
                self.sessions = []
                summary, record = self.run_one(measurement)
                self.assertNotIn("not reached", record.get("note") or "")
                self.assertTrue(set(self.called()) <= set(protocol.MEASUREMENT_METHODS[measurement]))
                self.assertTrue(self.called())

    def test_one_method_undeclared_and_the_probe_does_not_reach_codex(self):
        """Fails with an undeclared method allowed: the probe would call it."""
        for measurement in (Measurement.M6B, Measurement.MX, Measurement.MF, Measurement.M3B, Measurement.MC1):
            declared = protocol.MEASUREMENT_METHODS[measurement]
            dropped = next(method for method in declared if method != "thread/unsubscribe")
            with self.subTest(measurement), patch.dict(protocol.MEASUREMENT_METHODS,
                                                       {measurement: tuple(m for m in declared if m != dropped)}):
                self.sessions = []
                summary, record = self.run_one(measurement)
                self.assertTrue((record.get("note") or "").startswith("not reached"), record)

    def test_the_file_readers_open_no_session(self):
        for measurement in (Measurement.MO, Measurement.MXA, Measurement.MC2):
            with self.subTest(measurement):
                self.assertEqual(protocol.MEASUREMENT_METHODS[measurement], ())
                self.sessions = []
                self.run_one(measurement, thread=None)
                self.assertEqual(self.sessions, [])

    def test_no_new_method_is_forbidden_or_one_of_cores_three(self):
        from codex_auto_resume.codex.appserver import PROTOCOL_METHODS
        for measurement in STAGE4:
            methods = set(protocol.MEASUREMENT_METHODS[measurement])
            self.assertTrue(methods.isdisjoint(protocol.FORBIDDEN_METHODS), measurement)
            self.assertTrue(methods.isdisjoint(PROTOCOL_METHODS), measurement)


class ContentTests(ProbeCase):
    def test_every_record_is_content_free(self):
        for measurement in STAGE4:
            with self.subTest(measurement):
                self.sessions = []
                factory = self.factory(measurement, with_home=measurement == Measurement.MB)
                _summary, record = self.run_one(measurement, factory)
                self.assertEqual(live_evidence.content_refusals(record), [])
                text = json.dumps(record)
                for secret in (THREAD, "secret-model", "the-threads-model", "codex-default", "C:/work"):
                    self.assertNotIn(secret, text)

    def test_a_free_word_is_refused_and_every_observed_word_is_closed(self):
        with self.assertRaises(evidence.EvidenceError):
            evidence.build(Measurement.MO, Verdict.BLOCKED, {"originator": "codex-tui"}, product_version="0.6.15",
                           codex_version="0.162.0", windows_build="10.0.26200", recorded_at="2026-10-11T00:00Z",
                           note="x")
        for word in ObservedWord:
            self.assertTrue(evidence._content_free(str(word)), word)


class M6BTests(ProbeCase):
    def test_no_override_reaches_codex_and_the_saved_settings_are_words(self):
        _summary, record = self.run_one(Measurement.M6B)
        (session,) = self.sessions
        params = dict(session.calls)
        self.assertEqual(params["thread/resume"], {"threadId": THREAD, "excludeTurns": True})
        self.assertEqual(set(params["turn/start"]), {"threadId", "input"}, "the thread's own settings apply")
        observed = record["observed"]
        self.assertEqual((observed["sandbox"], observed["approval_policy"], observed["reviewer"]),
                         ("workspaceWrite", "on-request", "user"))
        self.assertIs(observed["permission_profile_set"], False)
        self.assertEqual(observed["approvals_declined"], 2)
        self.assertEqual(observed["turn_status"], "completed")
        self.assertEqual(record["verdict"], "blocked", "the person confirms")

    def test_a_word_codex_does_not_name_is_other(self):
        self.assertEqual(measure._settings({"sandbox": {"type": "somethingNew"}, "approvalPolicy": {"granular": {}},
                                            "approvalsReviewer": "auto"}),
                         {"sandbox": "other", "approval_policy": "granular", "reviewer": "other",
                          "permission_profile_set": False})


class MFTests(ProbeCase):
    def test_both_routes_are_tried_and_only_booleans_are_kept(self):
        _summary, record = self.run_one(Measurement.MF)
        self.assertEqual(record["verdict"], "pass")
        observed = record["observed"]
        self.assertIs(observed["resume_override_session_only"], True)
        self.assertIs(observed["restore_read_back"], True)
        calls = self.called()
        self.assertIn("thread/settings/update", calls)
        overrides = [params for session in self.sessions for method, params in session.calls
                     if method in ("thread/resume", "turn/start") and "model" in params]
        self.assertEqual(len(overrides), 2, "once at resume, once on a turn")

    def test_a_thread_on_the_default_model_is_left_to_the_person(self):
        with patch.dict(REPLIES, {Measurement.MF: dict(REPLIES[Measurement.MF],
                                                       **{"thread/resume": {"model": "codex-default"}})}):
            _summary, record = self.run_one(Measurement.MF)
        self.assertEqual(record["verdict"], "blocked")
        self.assertNotIn("turn/start", self.called())


class M3BTests(ProbeCase):
    def test_a_turn_with_no_input_under_a_client_id(self):
        self.run_one(Measurement.M3B)
        start = dict(self.sessions[0].calls)["turn/start"]
        self.assertEqual(start["input"], [])
        self.assertEqual(start["clientUserMessageId"], measure._SAMPLE_M3B_CLIENT_ID)

    def test_judged_by_the_turn_id_it_was_started_under_never_a_client_id(self):
        """v0.6.16-beta.4: a turn with no words keeps no client id (2026-10-16); the turn id turn/start returned, found
        in Codex's history, is the proof. Fails with the client-id rule back."""
        with patch.object(measure, "_turn_in_history", lambda ctx, turn: turn == TURN),                 patch.object(measure, "_client_recorded", lambda ctx, client: False):
            _summary, record = self.run_one(Measurement.M3B)
        self.assertEqual(record["verdict"], "pass", record)
        with patch.object(measure, "_turn_in_history", lambda ctx, turn: False):
            _summary, record = self.run_one(Measurement.M3B)
        self.assertEqual(record["verdict"], "fail")

    def test_codex_refusing_empty_input_is_a_fail_with_its_code(self):
        with patch.dict(REPLIES, {Measurement.M3B: {"turn/start": refused("turn/start")}}):
            _summary, record = self.run_one(Measurement.M3B)
        self.assertEqual(record["verdict"], "fail")
        self.assertEqual(record["observed"]["refusal_code"], -32600)


class MBTests(ProbeCase):
    def test_it_opens_only_a_scratch_home_and_removes_it(self):
        """Fails with the scratch home reverted: a session on the person's own Codex home."""
        _summary, record = self.run_one(Measurement.MB, self.factory(Measurement.MB, with_home=True),
                                        backend=Backend(self.dir / "the-persons-home"))
        (session,) = self.sessions
        self.assertIsNotNone(session.home)
        self.assertNotEqual(Path(session.home), self.dir / "the-persons-home")
        self.assertTrue(Path(session.home).name.startswith("car-mb-"))
        self.assertFalse(Path(session.home).exists(), "removed after")
        self.assertEqual({method for method, _p in session.calls}, {"config/read", "config/value/write"})
        self.assertIs(record["observed"]["scratch_home"], True)

    def test_a_factory_with_no_scratch_home_is_never_used(self):
        _summary, record = self.run_one(Measurement.MB, self.factory(Measurement.MB))
        self.assertEqual(self.sessions, [])
        self.assertEqual(record["verdict"], "blocked")

    def test_writes_read_back_removed_and_a_stale_version_refused_is_a_pass(self):
        config = {"config": {}, "version": 1}

        def read(_params):
            return json.loads(json.dumps(config))

        def write(params):
            if params["expectedVersion"] != config["version"]:
                return refused("config/value/write", -32010)
            node = config["config"]
            *parents, last = params["keyPath"].split(".")
            for part in parents:
                node = node.setdefault(part, {})
            if params["value"] is None:
                node.pop(last, None)
            else:
                node[last] = params["value"]
            config["version"] += 1
            return {"status": "ok"}
        with patch.dict(REPLIES, {Measurement.MB: {"config/read": read, "config/value/write": write}}):
            _summary, record = self.run_one(Measurement.MB, self.factory(Measurement.MB, with_home=True))
        self.assertEqual(record["verdict"], "pass", record)


class FileReaderTests(ProbeCase):
    def home(self, *, source="cli", originator="codex-tui", rollout_tail=()):
        home = (self.dir / "codex").resolve()
        (home / "sessions").mkdir(parents=True)
        rollout = home / "sessions" / ("rollout-%s.jsonl" % THREAD)
        lines = [{"type": "session_meta", "payload": {"id": THREAD, "originator": originator, "source": source,
                                                      "cli_version": "0.162.0"}}, *rollout_tail]
        rollout.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
        with sqlite3.connect(home / "state_5.sqlite") as db:
            db.execute("CREATE TABLE threads (id TEXT, rollout_path TEXT, source TEXT, thread_source TEXT, "
                       "history_mode TEXT, title TEXT)")
            db.execute("INSERT INTO threads VALUES (?, ?, ?, 'user', 'paginated', 'a title of the person')",
                       (THREAD, str(rollout), source))
        return home

    def test_mo_records_the_words_and_who_holds_it(self):
        home = self.home()
        with patch.object(measure, "_holder", return_value="session"):
            _summary, record = self.run_one(Measurement.MO, backend=Backend(home))
        observed = record["observed"]
        self.assertEqual((observed["source"], observed["originator"], observed["meta_source"], observed["holder"]),
                         ("cli", "cli_originator", "cli", "session"))
        self.assertIs(observed["cli_version_present"], True)
        self.assertNotIn("a title of the person", json.dumps(record))

    def test_an_originator_no_candidate_is_other(self):
        home = self.home(source="vscode", originator="Some Other Editor")
        with patch.object(measure, "_holder", return_value="unknown"):
            _summary, record = self.run_one(Measurement.MO, backend=Backend(home))
        self.assertEqual(record["observed"]["originator"], "other")

    def test_the_rollout_gives_only_its_newest_events_kind(self):
        home = self.home(rollout_tail=[{"type": "event_msg", "payload": {"type": "task_complete", "last": "words"}}])
        self.assertEqual(sessions.Origins(home).newest_event(THREAD), ("event_msg", "task_complete"))

    def test_the_origin_statement_selects_no_content(self):
        selected = sessions.ORIGIN.split(" FROM ")[0]
        for name in ("title", "preview", "first_user_message", "name", "cwd"):
            self.assertNotIn(name, selected.replace("rollout_path", ""))
        self.assertEqual(sessions.STATEMENTS, (sessions.ORIGIN,))

    def test_mc2_tells_which_said_first(self):
        watch = measure._Watch.__new__(measure._Watch)
        watch.first_turn, watch.first_event, watch._looked = TURN, None, True
        watch.db_start = watch.db_end = watch.rollout_start = watch.rollout_end = None
        watch.reply_ready = watch.waited_db = watch.waited_rollout = False
        later = "deadbeef-0000-7000-8000-00000000cafe"
        class Turn:
            def __init__(self, status):
                self.turn_id, self.status, self.kinds = later, status, {"agentMessage": 1}
        statuses = iter([None, Turn("inProgress"), Turn("completed"), Turn("completed")])
        # v0.6.16-beta.4: what the rollout gained since each look (sessions.Origins.events_since).
        events = iter([["task_started"], ["task_started"], [], ["task_complete"]])
        watch.turns = type("T", (), {"latest": lambda self, thread: next(statuses)})()
        watch.origins = type("O", (), {"events_since": lambda self, thread, offset: (next(events), 0)})()
        watch.thread, watch._offset = THREAD, None
        for now in (1.0, 2.0, 3.0, 9.0):
            watch.look(now)
        self.assertTrue(watch.settled())
        self.assertEqual(watch.observed(), {"started_first": "rollout", "finished_first": "db",
                                            "reply_item_ready_at_final": True, "approval_wait_seen_db": False,
                                            "approval_wait_seen_rollout": False, "finished_lag": "over_5s"})

    def test_mc2_reads_a_task_that_started_and_ended_between_two_looks(self):
        """Fails with the newest event alone (2026-10-16): the start would be missed and the run never settle."""
        watch = measure._Watch.__new__(measure._Watch)
        watch.first_turn, watch.first_event, watch._looked = TURN, None, True
        watch.db_start = watch.db_end = watch.rollout_start = watch.rollout_end = None
        watch.reply_ready = watch.waited_db = watch.waited_rollout = False
        watch.turns = type("T", (), {"latest": lambda self, thread: None})()
        watch.origins = type("O", (), {"events_since": lambda self, thread, offset: (
            ["task_started", "agent_message", "task_complete"], 0)})()
        watch.thread, watch._offset = THREAD, None
        watch.look(2.0)
        self.assertEqual((watch.rollout_start, watch.rollout_end), (2.0, 2.0))


if __name__ == "__main__":
    unittest.main()
