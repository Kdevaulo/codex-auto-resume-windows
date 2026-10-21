"""The core audit's minor findings, each held where it was found (v0.6.20, plans/v0620-audit/core.md M1-M7).

M1 a watch with no default engine logs nothing every second; M2 `codex --version` output that is not UTF-8 is read,
not raised; M3 a queue delete that worked stays reported as worked when the helper is slow to go; M4 a clock set back
ends the usage and loaded caches; M5 a Codex home whose key changes with its folder's reach (a mapped network drive) is
never retired, nor its waiting records cancelled, on that alone; M6 every write that cancels a record gives it its
outcome time; M7 a resend's claim reads the conversation's day and spacing again, as a first claim does.

Its own module: the scenario modules are frozen (tests/neutral.py MODULES). Scratch folders, a scratch LOCALAPPDATA and
simulated Codex homes only; no process is started.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

from codexsim import BASE, CodexHome
from codex_auto_resume import homes as configured
from codex_auto_resume.codex import appserver, transport
from codex_auto_resume.engine.freshness import FreshnessMixin
from codex_auto_resume.runtime import homes as runtime_homes
from codex_auto_resume.runtime.loop import WatchLoop
from codex_auto_resume.store import Store

from test_homes import App as HomesApp, T1, TURN
import test_plug_points as plug_points  # its cases are not bound here, so they run in their own module alone

THREAD = "11111111-1111-7111-8111-111111111111"
QUEUED = "22222222-2222-7222-8222-222222222222"


def failure(turn=TURN, key="d" * 64, thread=T1):
    return {"thread_id": thread, "turn_id": turn, "completed_at": BASE, "started_at": BASE - 5, "ordinal": 1,
            "interruption_id": key, "reset_at": None, "limit_type": "x", "uncertain": False,
            "category": "server_5xx"}


class Scratch(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)


class WatchWithNoEngineTests(unittest.TestCase):
    def test_no_default_engine_is_no_failure_and_the_homes_are_still_watched(self):
        failures, watched, fired = [], [], iter([None, None, "stop"])
        homes = types.SimpleNamespace(watch_needed=lambda: True, watch=lambda: watched.append(1))
        loop = types.SimpleNamespace(_homes=homes, _wait_for=lambda stop, wake, seconds: next(fired),
                                     _record_failure=failures.append)
        self.assertEqual(WatchLoop._between_ticks(loop, None, None, None, 60, 0.0), "stop")
        self.assertEqual(failures, [], "nothing logged every second while the engine is rebuilt")
        self.assertEqual(len(watched), 2)


class VersionDecodeTests(Scratch):
    def test_a_version_that_is_not_utf8_is_read_not_raised(self):
        local = self.root / "local"
        exe = local / "OpenAI" / "Codex" / "bin" / "0abc" / "codex.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"MZ")

        def run(args, **options):
            output = b"codex-cli 0.163.0 \xff\n".decode(options["encoding"], options.get("errors", "strict"))
            return subprocess.CompletedProcess(args, 0, stdout=output)
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}), patch.object(transport.S, "run", run), \
                patch.object(transport.Backend, "_queue_interface_ok", return_value=True):
            backend = transport.Backend(self.root / "codex", exe)
            checks = backend.engine_checks()
        self.assertEqual(checks["version_runs"], transport.PASS)
        self.assertTrue(checks["version"].startswith("codex-cli 0.163.0"))


if __name__ == "__main__":
    unittest.main()
