"""What stage 4's measurements changed in its routes (2026-10-16, codex-cli 0.162.0-alpha.17.2):

* M6B - a turn run here starts Codex's app server as the app starts its engine (windows.sandbox "mxc",
  features.prefer_mxc), so a command never waits on the sandbox's setup helper asking for elevation; the M6B probe
  starts its server the same way, and no other session does.
* MF - the conversation's own model is put back with thread/settings/update and read back on a plain resume; a
  model given at thread/resume is never the route (the thread keeps it).
* MC2 - the probe's watch reads every event the rollout gained since its last look, not only the newest.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase  # noqa: E402,F401
from codex_auto_resume_advanced.codex import headless, protocol  # noqa: E402
from codex_auto_resume_advanced.codex.sessions import Origins  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Measurement  # noqa: E402

THREAD = "0a1b2c3d-0001-7000-8000-000000000001"


class Started(Exception):
    pass


class Backend:
    codex_home = Path(".")

    def _compatible(self):
        pass

    def _argv(self):
        return ["codex.exe"]

    def _environment(self):
        return {}


def argv_of(session):
    seen = []

    def popen(argv, **keywords):
        seen.append(argv)
        raise Started()
    with patch.object(protocol.S, "Popen", popen):
        try:
            session.__enter__()
        except Started:
            pass
    return seen[0]


class HeadlessSettingsTests(unittest.TestCase):
    def test_a_turn_run_here_starts_its_server_as_the_app_starts_codex(self):
        """Fails with the settings reverted: the sandbox's setup helper would ask for elevation (M6B)."""
        argv = argv_of(protocol.Session(Backend(), capability="headless_run", config=headless.HEADLESS_CONFIG))
        self.assertEqual(argv, ["codex.exe", "-c", 'windows.sandbox="mxc"', "-c", "features.prefer_mxc=true",
                                "app-server", "--stdio"])
        made = []
        with patch.object(headless, "Session", lambda backend, **keywords: made.append(keywords)), \
                patch("codex_auto_resume_advanced.codex.inuse.backend", lambda paths: Backend()):
            headless.live_session(None)("headless_run")
        self.assertEqual(made, [{"capability": "headless_run", "config": headless.HEADLESS_CONFIG}])

    def test_every_other_session_starts_as_before(self):
        argv = argv_of(protocol.Session(Backend(), capability="marker_free_continuation"))
        self.assertEqual(argv, ["codex.exe", "app-server", "--stdio"])

    def test_the_m6b_probe_starts_its_server_as_the_route_does(self):
        from codex_auto_resume_advanced import measure
        made = []
        with patch.object(measure, "Session", lambda backend, measurement, **keywords: made.append(
                (measurement, keywords))):
            factory = measure.live_session_factory(None, backend=Backend())
            factory(Measurement.M6B)
            factory(Measurement.M6)
        self.assertEqual(made, [(Measurement.M6B, {"config": headless.HEADLESS_CONFIG}),
                                (Measurement.M6, {})])


class RestoreTests(unittest.TestCase):
    class Session:
        def __init__(self, model):
            self.model, self.calls = model, []

        def call(self, method, params):
            self.calls.append((method, params))
            return {"model": self.model} if method == "thread/resume" else {}

    def test_the_conversations_own_model_is_put_back_and_read_back(self):
        """Fails with the read back reverted: a model Codex did not take back would be said restored."""
        kept = self.Session("its-own-model")
        self.assertTrue(headless.Follower._restore(kept, THREAD, "its-own-model"))
        self.assertEqual([method for method, _ in kept.calls], ["thread/settings/update", "thread/resume"])
        self.assertNotIn("model", kept.calls[1][1], "a plain resume, never a model given at resume (MF)")
        still = self.Session("the-default-model")
        self.assertFalse(headless.Follower._restore(still, THREAD, "its-own-model"))


class EventsTests(unittest.TestCase):
    def test_every_event_since_the_last_look_is_read_in_order(self):
        """Fails with the newest event alone: a task that started and ended between two looks is missed."""
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            path = home / "sessions" / ("rollout-%s.jsonl" % THREAD)
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"type": "session_meta", "payload": {"type": "x"}}) + "\n", encoding="utf-8")
            origins = Origins(home)
            with patch.object(Origins, "_row", lambda self, thread: {"rollout_path": str(path)}):
                kinds, offset = origins.events_since(THREAD, None)
                self.assertEqual(kinds, [])
                with path.open("a", encoding="utf-8") as stream:
                    for kind in ("task_started", "agent_message", "task_complete"):
                        stream.write(json.dumps({"type": "event_msg", "payload": {"type": kind}}) + "\n")
                    stream.write('{"type": "event_msg", "payload"')            # a line still being written
                kinds, offset = origins.events_since(THREAD, offset)
                self.assertEqual(kinds, ["task_started", "agent_message", "task_complete"])
                self.assertEqual(origins.events_since(THREAD, offset)[0], [], "the half line is read once complete")


if __name__ == "__main__":
    unittest.main()
