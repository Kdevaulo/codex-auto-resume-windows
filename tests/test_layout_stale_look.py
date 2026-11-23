"""v0.6.26 (fourth round, audit-reachability I1): one old "starting" look never becomes a layout not tested on.

Review K8 made "starting" a tested shape only for STARTING_SECONDS of looks that all found it so. But the watcher hands
the layout watch the backend's last snapshot at every tick (runtime/app.py `_layout_look`), and only a record the engine
checks makes a new one (codex/transport.py `app_identity`). So a record checked while the app was starting, then gone
without another look, left one snapshot that the watch's clock kept counting on: ten minutes later the watcher said
Codex runs in a layout this version has not been tested on, while the app had long run normally. Now a snapshot looked
at again is judged as at its first look.

Synthetic rows and a scratch folder only (test_pairing_roles' Case for the package folder).
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import config  # noqa: E402
from codex_auto_resume.codex import layout  # noqa: E402
from codex_auto_resume.runtime import app  # noqa: E402
import test_pairing_roles as roles  # noqa: E402  (a module, so its cases are not bound here)

STARTING = [roles.MAIN, roles.RENDERER]
MINUTE = 60.0


class StaleLookTests(roles.Case):
    def setUp(self):
        super().setUp()
        self.now, self.lines = 0.0, []
        clock = patch("time.monotonic", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.paths = config.Paths(self.home / "product")
        # What App._layout_look is given: the backend it drives, whose `layout` only app_identity sets.
        self.watcher = types.SimpleNamespace(paths=self.paths, _backend_stamp=(1, 2),
                                             logger=types.SimpleNamespace(info=self.say),
                                             _backend=types.SimpleNamespace(layout=layout.snapshot(STARTING),
                                                                            engine_version="0.170.0"))

    def say(self, text, *args):
        self.lines.append(text % args if args else text)

    def tick(self, at):
        self.now = at
        app.App._layout_look(self.watcher)
        return json.loads(self.paths.codex_layout_file.read_text(encoding="utf-8"))

    def untested(self):
        return [line for line in self.lines if "has not been tested on" in line]

    def test_one_starting_look_ticked_on_for_long_stays_tested(self):
        """Fails with the fix reverted: catalogued False after ten minutes of ticks, and the log said so."""
        self.assertEqual(self.watcher._backend.layout["shape"], "starting")
        for minute in range(13):
            kept = self.tick(minute * MINUTE)
        self.assertIs(kept["catalogued"], True)
        self.assertEqual(self.untested(), [])

    def test_new_looks_that_stay_starting_still_turn_after_ten_minutes(self):
        """Review K8 holds: each tick with a snapshot of its own counts."""
        for minute in range(11):
            self.watcher._backend.layout = layout.snapshot(STARTING)
            kept = self.tick(minute * MINUTE)
        self.assertIs(kept["catalogued"], False)
        self.assertEqual(len(self.untested()), 1)


if __name__ == "__main__":
    unittest.main()
