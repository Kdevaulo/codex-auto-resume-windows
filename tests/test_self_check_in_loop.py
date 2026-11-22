"""v0.6.26 (review of the third round, K6): the watch loop runs its self-check at every tick, and a single tick does not.

The self-check's tests call WatchLoop._self_check directly, so with the loop's own call taken out they all still passed
and the watcher would never have said that recovery cannot work here. This module runs the real loop - test_watcher_
health's harness: a stand-in engine, a scratch home, no Windows but its own process's - and reads what it wrote beside
its heartbeat.
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import config, managed, settings  # noqa: E402
from codex_auto_resume.app import App  # noqa: E402
from codex_auto_resume.domain import public  # noqa: E402
from codex_auto_resume.windows import AdapterError  # noqa: E402
from test_cli import _reset_logging  # noqa: E402
import test_watcher_health as health  # noqa: E402  (a module, so its cases are not bound here)


class SelfCheckInLoopTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.addCleanup(_reset_logging)
        self.home = Path(folder.name)
        self.scratch = {"LOCALAPPDATA": str(self.home / "none"), "CODEX_HOME": str(self.home / "codex")}
        with patch.dict(os.environ, self.scratch), patch.object(App, "_read_managed", return_value=managed.NONE):
            self.app = App(config.Paths(self.home), console=False)
        self.checked = []

    def run_watcher(self, *, once, stops=(False, True)):
        settings.save(self.app.paths.settings_file, settings.defaults())
        self.app._stored = settings.load(self.app.paths.settings_file)
        self.app.settings = dict(self.app._stored)
        engines = []

        class Engine:
            def tick(self_inner):
                pass

        def made(store, **kwargs):
            engines.append(Engine())
            return engines[-1]

        real = App._self_check
        checked = self.checked

        def self_check(app, store, engine, started):
            checked.append(engine)
            return real(app, store, engine, started)

        pending = iter(stops)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, self.scratch))
            stack.enter_context(patch.object(App, "engine", side_effect=made))
            stack.enter_context(patch.object(App, "_self_check", self_check))
            stack.enter_context(patch.object(App, "wake_event", side_effect=AdapterError("unavailable")))
            stack.enter_context(patch.object(App, "_start_tray", return_value=None))
            stack.enter_context(patch.object(App, "_read_managed", return_value=managed.NONE))
            stack.enter_context(patch.object(App, "_watcher_notice", side_effect=health.Notices()))
            stack.enter_context(patch.object(App, "mutex"))
            stop_event = stack.enter_context(patch.object(App, "stop_event"))
            stop_event.return_value.__enter__.return_value.wait.side_effect = lambda seconds: next(pending)
            stack.enter_context(patch("codex_auto_resume.runtime.health.ownprocess", health.FakePort()))
            self.app.run(once=once, poll=5)
        return engines

    def test_every_tick_of_the_watch_runs_the_self_check_and_writes_it(self):
        engines = self.run_watcher(once=False)
        self.assertEqual(len(self.checked), 2, "one self-check a tick, two ticks")
        self.assertTrue(all(engine is engines[0] for engine in self.checked), "the tick's own engine")
        written = json.loads(self.app.paths.self_check_file.read_text(encoding="utf-8"))
        self.assertEqual(written["format"], public.SELF_CHECK_FORMAT)
        self.assertIsNone(written["blocked"])

    def test_a_single_tick_writes_none(self):
        self.run_watcher(once=True, stops=())
        self.assertEqual(self.checked, [])
        self.assertFalse(self.app.paths.self_check_file.exists())


if __name__ == "__main__":
    unittest.main()
