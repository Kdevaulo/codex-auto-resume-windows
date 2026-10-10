"""One turn of a conversation nothing holds, run here, every approval declined, always let go (v0.6.15-beta.3,
codex/headless.py).

Every session is a fake app server of the test's own; nothing here opens a real Codex. The follower runs on its
own thread, as in the watcher, and each test waits for it to end.
"""
from __future__ import annotations

from pathlib import Path
import sys
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advancedcase  # noqa: E402,F401
from codex_auto_resume_advanced.codex import headless, protocol  # noqa: E402
from codex_auto_resume_advanced.vocabulary import RunEnd  # noqa: E402

THREAD = "0a1b2c3d-0001-7000-8000-000000000001"
TURN = "deadbeef-0000-7000-8000-00000000beef"
KEY = "%064x" % 9
CLIENT = "0a1b2c3d-0001-7000-8000-0000000000c1"
SAVED = {"sandbox": {"type": "workspaceWrite"}, "approvalPolicy": "on-request", "approvalsReviewer": "user",
         "activePermissionProfile": None, "model": "the-threads-model"}


class Server:
    """A session as the route meets it: answers by method (an exception is raised), completes the turn after
    `completes_after` seconds (None: only when interrupted), and keeps every call in order."""

    def __init__(self, capability, *, replies=None, completes_after=0.05, status="completed"):
        self.allowed = protocol.methods_for_capability(capability)
        self.replies = dict({"thread/resume": SAVED, "turn/start": {"turn": {"id": TURN}},
                             "thread/compact/start": {}}, **(replies or {}))
        self.completes_after, self.status = completes_after, status
        self.calls, self.events, self.closed, self.lock = [], [], False, threading.Lock()
        self.started_at = None

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.closed = True
        return False

    def call(self, method, params=None):
        if method not in self.allowed:
            raise protocol.SessionRefused("method not permitted for this session")
        with self.lock:
            self.calls.append((method, params))
        reply = self.replies.get(method, {})
        if isinstance(reply, Exception):
            raise reply
        if method in ("turn/start", "thread/compact/start"):
            self.started_at = time.monotonic()
        if method == "turn/interrupt":
            self._complete("interrupted")
        return reply

    def _complete(self, status):
        with self.lock:
            self.events.append({"method": "turn/completed",
                                "params": {"threadId": THREAD, "turn": {"id": TURN, "status": status}}})

    def drain_events(self):
        if (self.started_at is not None and self.completes_after is not None
                and time.monotonic() - self.started_at >= self.completes_after):
            self.started_at = None
            self._complete(self.status)
        with self.lock:
            found, self.events = self.events, []
        return found

    def methods(self):
        return [method for method, _params in self.calls]


class RouteCase(unittest.TestCase):
    def setUp(self):
        self.follower = headless.Follower(poll=0.01)
        self.servers = []
        for name, value in (("INTERRUPT_SECONDS", 0.5), ("APP_LOOK_SECONDS", 0.0)):
            original = getattr(headless, name)
            setattr(headless, name, value)
            self.addCleanup(setattr, headless, name, original)

    def route(self, capability="headless_run", *, seconds=5, mode=headless.TURN, model=None, app_running=None,
              **server):
        def opening(asked):
            self.servers.append(Server(asked, **server))
            return self.servers[-1]
        return headless.HeadlessRun(capability, key=KEY, session=opening, follower=self.follower, seconds=seconds,
                                    mode=mode, model=model, app_running=app_running)

    def ended(self, seconds=5.0):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            found = self.follower.drain("headless_run") + self.follower.drain("model_fallback") \
                + self.follower.drain("compact_continue")
            if found:
                return found[0]
            time.sleep(0.01)
        self.fail("the run never ended")

    def resume(self, route, unheld=True, words="Continue.\n\n[codex-auto-resume:0123456789abcdef]"):
        return route.resume(THREAD, still_unloaded=lambda: unheld, words=words, client_id=CLIENT)


class StepTests(RouteCase):
    def test_a_turn_runs_on_the_saved_settings_with_cores_words_and_is_let_go(self):
        answered = self.resume(self.route())
        self.assertEqual(answered, {"outcome": "ran", "turn_id": TURN})
        ended = self.ended()
        self.assertEqual(ended["end"], RunEnd.COMPLETED)
        (server,) = self.servers
        params = dict(server.calls)
        self.assertEqual(params["thread/resume"], {"threadId": THREAD, "excludeTurns": True}, "no override at all")
        self.assertEqual(params["turn/start"]["input"][0]["text"].split("\n")[0], "Continue.")
        self.assertEqual(params["turn/start"]["clientUserMessageId"], CLIENT)
        self.assertEqual(set(params["turn/start"]), {"threadId", "input", "clientUserMessageId"})
        self.assertEqual(server.methods()[-1], "thread/unsubscribe")
        self.assertTrue(server.closed)

    def test_settings_off_the_allow_list_are_refused_before_anything_starts(self):
        """Fails with the allow-list reverted: a full-access conversation would be run here."""
        cases = {"full access": {"sandbox": {"type": "dangerFullAccess"}},
                 "outside sandbox": {"sandbox": {"type": "externalSandbox"}},
                 "another reviewer": {"approvalsReviewer": "auto"},
                 "a permission profile": {"activePermissionProfile": {"kind": "full"}},
                 "a granular policy": {"approvalPolicy": {"granular": {}}},
                 "nothing said": {"sandbox": None}}
        for name, change in cases.items():
            with self.subTest(name):
                self.servers = []
                route = self.route(replies={"thread/resume": dict(SAVED, **change)})
                answered = self.resume(route)
                self.assertEqual(answered["outcome"], "not_started")
                self.assertEqual(route.refused, RunEnd.REFUSED_SETTINGS)
                self.assertNotIn("turn/start", self.servers[0].methods())
                self.assertTrue(self.servers[0].closed)
                self.assertIsNone(self.follower.live())

    def test_a_session_that_does_not_open_or_a_resume_refused_starts_nothing(self):
        def failing(asked):
            raise OSError("no app server")
        route = headless.HeadlessRun("headless_run", key=KEY, session=failing, follower=self.follower)
        self.assertEqual(self.resume(route)["outcome"], "not_started")
        refused = self.route(replies={"thread/resume": protocol._refused_by_codex("thread/resume", -32600)})
        self.assertEqual(self.resume(refused)["outcome"], "not_started")

    def test_the_app_or_a_holder_appearing_at_the_last_look_starts_nothing(self):
        route = self.route()
        self.assertEqual(self.resume(route, unheld=False)["outcome"], "not_started")
        self.assertNotIn("turn/start", self.servers[0].methods())

    def test_codex_refusing_the_turn_is_not_started_and_no_answer_is_unknown(self):
        refused = self.route(replies={"turn/start": protocol._refused_by_codex("turn/start", -32600)})
        answered = self.resume(refused)
        self.assertEqual(answered["outcome"], "not_started")
        self.assertTrue(answered.get("refused_by_codex"))
        from codex_auto_resume.codex.errors import AdapterError
        silent = self.route(replies={"turn/start": AdapterError("protocol_timeout")})
        self.assertEqual(self.resume(silent)["outcome"], "unknown")

    def test_only_one_run_at_a_time(self):
        first = self.route(completes_after=None)
        self.assertEqual(self.resume(first)["outcome"], "ran")
        second = self.route()
        self.assertEqual(self.resume(second)["outcome"], "not_started")
        self.follower.stop()
        self.ended()

    def test_a_route_of_headless_run_cannot_compact_or_change_a_model(self):
        allowed = protocol.methods_for_capability("headless_run")
        for method in ("thread/compact/start", "thread/settings/update", "model/list", "thread/queue/add"):
            self.assertNotIn(method, allowed)


class FollowerTests(RouteCase):
    def test_the_cap_interrupts_the_turn_and_it_is_let_go(self):
        self.resume(self.route(seconds=0.1, completes_after=None))
        self.assertEqual(self.ended()["end"], RunEnd.CAPPED)
        methods = self.servers[0].methods()
        self.assertLess(methods.index("turn/interrupt"), methods.index("thread/unsubscribe"))

    def test_a_stop_interrupts_it(self):
        self.resume(self.route(completes_after=None))
        self.assertIsNotNone(self.follower.live())
        self.assertTrue(self.follower.stop(KEY))
        self.assertEqual(self.ended()["end"], RunEnd.INTERRUPTED)
        self.assertIsNone(self.follower.live())

    def test_the_codex_app_starting_interrupts_it_at_once(self):
        """Q3: until a measurement says what the app does with a conversation our server holds."""
        self.resume(self.route(completes_after=None, app_running=lambda: True))
        self.assertEqual(self.ended()["end"], RunEnd.YIELDED)
        self.assertIn("turn/interrupt", self.servers[0].methods())

    def test_a_failed_turn_is_said_so(self):
        self.resume(self.route(status="failed"))
        self.assertEqual(self.ended()["end"], RunEnd.FAILED)

    def test_the_watcher_leaving_interrupts_first(self):
        self.resume(self.route(completes_after=None))
        headless.stop_all(self.follower, seconds=3)
        self.assertIsNone(self.follower.live())
        self.assertIn("turn/interrupt", self.servers[0].methods())
        self.assertEqual(self.ended()["end"], RunEnd.INTERRUPTED)

    def test_each_capability_drains_its_own_ends(self):
        self.resume(self.route())
        deadline = time.monotonic() + 5
        while self.follower.live() is not None and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.follower.drain("model_fallback"), [])
        self.assertEqual(len(self.follower.drain("headless_run")), 1)


if __name__ == "__main__":
    unittest.main()
