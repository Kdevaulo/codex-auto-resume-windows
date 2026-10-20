"""A setup window that build/capture_window.ps1 starts can be photographed.

The capture reads the caption back and refuses a picture whose caption is active (five tries, then it fails). The
Dashboard never takes the foreground under a capture (SettingsForm.ShowWithoutActivation); the setup program's window
was brought forward as it opened (HostApp.BringToFront, so a window relaunched outside another app's view is in front),
and its still for the install motion could not be taken (2026-10-20). Read from the sources with tests/guiscan.py.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import guiscan  # noqa: E402


class CaptureTests(unittest.TestCase):
    def test_a_capture_is_never_brought_to_the_front(self):
        body = guiscan.member_body("HostApp", "BringToFront")
        guard = body.find('Environment.GetEnvironmentVariable("CODEX_AR_STILL_READY"))) return')
        self.assertGreater(guard, -1, "BringToFront brings a capture's window forward")
        self.assertLess(guard, body.find("Activate()"), "the guard comes after the window is activated")
        code = " ".join(line.split("//")[0] for line in body.splitlines())
        self.assertNotIn("Soft.", code, "HostApp.cs is compiled without the theme in the walk's test harness")

    def test_the_setup_window_opens_without_taking_the_foreground_under_a_capture(self):
        window = guiscan.type_body("InstallerWindow")
        self.assertIn("bool ShowWithoutActivation", window)
        self.assertIn("return Soft.StillReady != null || base.ShowWithoutActivation;", window)
        self.assertIn("if (Soft.StillReady != null) created.ExStyle |= 0x08000000;", window)


if __name__ == "__main__":
    unittest.main()
