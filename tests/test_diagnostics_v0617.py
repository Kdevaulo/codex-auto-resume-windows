"""v0.6.17: what Diagnostics says of where the watcher and the Dashboard's bridge run.

* Inside another app: a process descended from an MSIX app - the Codex app, Claude desktop - writes HKCU and
  %APPDATA% into that app's private view, and may end when that app closes. The bridge asks win/kernel.py's walk
  (held guard by guard in tests/test_host_app.py PythonWalkTests) of the watcher's process, named by its heartbeat
  and held to the time it says it started, and of its own; `host-app` gives both back, a package family name at
  most. Here the control method and the bridge, with the walk stood in for: no live process is asked, so the answer
  is the same inside Claude on this laptop and inside nothing on CI.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codex_auto_resume import control, controlcli  # noqa: E402
from codex_auto_resume.win import kernel  # noqa: E402
from test_control import ControlTestCase  # noqa: E402

CODEX = "OpenAI.Codex_2p2nqsd0c76g0"
OUTSIDE = {"state": "outside", "family": None, "app": None}
INSIDE = {"state": "inside", "family": CODEX, "app": "OpenAI.Codex"}


class HostAppControlTests(ControlTestCase):
    """control.host_app: the watcher's part asked of the process its heartbeat names, only while it runs."""

    def asked(self, watcher, walk):
        calls = []

        def stand_in(pid=None, started_by=None):
            calls.append((pid, started_by))
            return dict(walk(pid))
        with patch.object(kernel, "host_app", side_effect=stand_in), \
                patch.object(control.Control, "_watcher", lambda self, store: watcher):
            return self.control.host_app(), calls

    def test_no_watcher_running_is_said_and_only_the_bridge_is_asked(self):
        answer, calls = self.asked({"running": False, "pid": 4242, "started_at": 1.0e9}, lambda pid: OUTSIDE)
        self.assertEqual(answer, {"watcher": {"state": "not_running", "family": None, "app": None}, "bridge": OUTSIDE})
        self.assertEqual(calls, [(None, None)], "a watcher that does not run is not looked for")

    def test_a_running_watcher_is_asked_by_its_heartbeats_id_and_start(self):
        answer, calls = self.asked({"running": True, "pid": 4242, "started_at": 1.0e9},
                                   lambda pid: INSIDE if pid == 4242 else OUTSIDE)
        self.assertEqual(answer, {"watcher": INSIDE, "bridge": OUTSIDE})
        self.assertIn((4242, 1.0e9), calls, "held to the time the watcher says it started")

    def test_a_running_watcher_without_an_id_or_a_start_is_unknown(self):
        for watcher in ({"running": True, "pid": None, "started_at": 1.0e9},
                        {"running": True, "pid": 4242, "started_at": None},
                        {"running": True, "pid": True, "started_at": 1.0e9},
                        {"running": None}):
            with self.subTest(watcher):
                answer, calls = self.asked(watcher, lambda pid: INSIDE)
                self.assertEqual(answer["watcher"]["state"], "unknown")
                self.assertEqual(calls, [(None, None)])

    def test_the_bridge_gives_both_parts(self):
        with patch.object(kernel, "host_app", side_effect=lambda pid=None, started_by=None: dict(OUTSIDE)):
            reply = controlcli.dispatch(self.control, "host-app", {})
        self.assertEqual(reply, {"ok": True, "result": {
            "watcher": {"state": "not_running", "family": None, "app": None}, "bridge": OUTSIDE}})


if __name__ == "__main__":
    unittest.main()
