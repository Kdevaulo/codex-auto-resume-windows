"""The Dashboard's bridge sweeps what an update set aside and could not delete (v0.6.24, the owner 2026-11-15).

An in-app update renames the running CodexAutoResumeSettings.exe - the window that runs the update - to
`.old-<stamp>`. The watcher's sweep (runtime/setaside.py) runs as the watcher starts, while that window is still open,
so the v0.6.23 final's live acceptance found the previous exe in the installation after the in-app update, until the
next install; an update over a stopped watcher starts no watcher at all. The long-lived bridge of the Dashboard that
opens after it (controlcli serve) now runs the same sweep, with every gate it has, soon after it starts and again
while anything is still in use (controlcli.sweep_soon, SWEEP_AFTER).

Scratch homes only; the installer's lock is answered here, never asked of this PC.
"""
from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_auto_resume import config, controlcli, windows
from codex_auto_resume.control import Control
from codex_auto_resume import setaside

STAMP = "20261115022653"


class SweepSoonTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.paths = config.Paths(str(Path(folder.name) / "home"))
        self.assertTrue(self.paths.claim_home())
        self.home = self.paths.home
        self.control = Control(self.paths)
        self.waited = []
        guard = patch.object(windows, "install_in_progress", return_value=False)
        guard.start()
        self.addCleanup(guard.stop)

    def run_soon(self, wait=None):
        worker = controlcli.sweep_soon(self.control, wait=wait or self.waited.append)
        worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertTrue(worker.daemon, "never keeps the bridge alive")

    def test_an_old_window_still_open_is_left_and_taken_once_it_has_gone(self):
        old = self.home / ("CodexAutoResumeSettings.exe.old-" + STAMP)
        old.write_bytes(b"MZ" * 1000)
        handle = open(old, "rb")             # as a running program holds its file: no delete while open
        self.addCleanup(lambda: handle.closed or handle.close())

        def wait(seconds):
            self.waited.append(seconds)
            if len(self.waited) == 3:
                handle.close()               # the old window closed between two looks

        self.run_soon(wait)
        self.assertFalse(old.exists())
        self.assertEqual(self.waited, list(controlcli.SWEEP_AFTER[:3]), "looked again while it was in use, then stopped")

    def test_it_stops_after_a_look_that_leaves_nothing(self):
        old = self.home / ("CodexAutoResumeSettings.exe.old-" + STAMP)
        old.write_bytes(b"MZ")
        keep = self.home / "CodexAutoResumeSettings.exe"
        keep.write_bytes(b"MZ")
        self.run_soon()
        self.assertFalse(old.exists())
        self.assertTrue(keep.exists(), "the program itself is never one")
        self.assertEqual(self.waited, [controlcli.SWEEP_AFTER[0]], "the first look waits for the window's reads")
        self.assertGreater(controlcli.SWEEP_AFTER[0], 0)

    def test_a_copy_in_use_to_the_end_is_left_for_the_next_start(self):
        old = self.home / ("CodexAutoResumeSettings.exe.old-" + STAMP)
        old.write_bytes(b"MZ")
        with open(old, "rb"):
            self.run_soon()
            self.assertTrue(old.exists())
        self.assertEqual(self.waited, list(controlcli.SWEEP_AFTER))

    def test_the_watchers_gates_hold(self):
        """It is the watcher's own sweep: nothing while an install runs, or its copy journal is there."""
        old = self.home / ("CodexAutoResumeSettings.exe.old-" + STAMP)
        old.write_bytes(b"MZ")
        with patch.object(windows, "install_in_progress", return_value=True):
            self.run_soon()
        self.assertTrue(old.exists())
        (self.home / setaside.JOURNAL).write_text("{}", encoding="utf-8")
        self.run_soon()
        self.assertTrue(old.exists())

    def test_a_failure_ends_the_sweep_and_nothing_else(self):
        with patch.object(setaside, "sweep", side_effect=OSError("no")) as sweep:
            self.run_soon()
        self.assertEqual(sweep.call_count, 1)


class ServeTests(unittest.TestCase):
    def test_the_long_lived_bridge_starts_it_and_the_one_shot_form_does_not(self):
        with tempfile.TemporaryDirectory() as folder:
            home = str(Path(folder) / "home")
            with patch.object(controlcli, "sweep_soon") as soon, \
                    patch.object(controlcli, "serve", return_value=0) as served, \
                    patch.object(controlcli.sys, "stdin", io.StringIO("")):
                self.assertEqual(controlcli.main(["--home", home, "serve"]), 0)
            soon.assert_called_once()
            served.assert_called_once()
            self.assertEqual(soon.call_args.args[0].paths.home, served.call_args.args[0].paths.home)
            with patch.object(controlcli, "sweep_soon") as soon, \
                    patch.object(controlcli, "_emit", return_value=0), \
                    patch.object(controlcli, "dispatch", return_value={"ok": True}):
                controlcli.main(["--home", home, "status"])
            soon.assert_not_called()

    def test_the_window_starts_its_bridge_through_main_with_serve(self):
        source = (Path(__file__).resolve().parents[1] / "gui" / "Dashboard.cs").read_text(encoding="utf-8")
        self.assertIn('"from codex_auto_resume.controlcli import main;"', source)
        self.assertIn('Bridge.Quote(appSrc) + " serve"', source)


if __name__ == "__main__":
    unittest.main()
