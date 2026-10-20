"""The install motion's shim (build/motion/InstallerRender.cs), compiled with the setup program's own sources and run.

The shim is never shipped, so nothing else would notice when a change to the setup window breaks it: this compiles
it as build/make_install_motion.py does, and drives the window through a first installation in a few frames - each
page in turn, the run told some of install.ps1's lines, the Finish page - holding only what does not depend on this
machine's fonts: that it ran, which frames show the primary button, and that the window kept its width. No picture is
compared and none is written outside a temporary folder; nothing is shown on the screen.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import make_install_motion as motion  # noqa: E402

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "the setup window is built with Windows' C# compiler")
class ShimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory(prefix="install-motion-test-")
        cls.exe = motion.compile_shim(Path(cls.work.name) / "shim")

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def test_it_walks_a_first_installation_in_the_setup_window(self):
        plan = motion.load("install-en")
        events = len(plan["events"])
        frames = [{"page": "welcome", "progress": 0}, {"page": "welcome", "progress": 0, "hover": "button.forward"},
                  {"page": "options", "progress": 0}, {"page": "progress", "progress": 0},
                  {"page": "progress", "progress": 10}, {"page": "progress", "progress": events},
                  {"page": "finish", "progress": events}, {"page": "finish", "progress": events,
                                                           "pressed": "button.forward"}]
        for index, frame in enumerate(frames):
            frame.update(index=index, light=index * 100)
        data = motion.job(plan, [], Path(self.work.name) / "walk" / "frames")
        data["frames"] = frames
        result = motion.render(self.exe, data, Path(self.work.name) / "walk")
        drawn = list(motion.pictures(result, Path(self.work.name) / "walk" / "frames"))
        self.assertEqual([index for index, _size, _picture, _bounds in drawn], list(range(len(frames))))
        self.assertEqual(len({size[0] for _index, size, _picture, _bounds in drawn}), 1, "the window kept its width")
        self.assertAlmostEqual(drawn[0][1][0], round(600 * float(result["dpi_scale"])), delta=2)
        shows_button = ["button.forward" in bounds for _index, _size, _picture, bounds in drawn]
        # The primary button is Next, Install and Finish; while it installs the window has none.
        self.assertEqual(shows_button, [True, True, True, False, False, False, True, True])
        self.assertEqual(result["notes"], [])
        # The faces and the run change what is drawn: no two neighbouring frames of a new state are the same picture.
        pictures = [picture for _index, _size, picture, _bounds in drawn]
        for before, after, name in zip(pictures, pictures[1:], ("hover", "options", "progress", "unpacked", "lines",
                                                                "finish", "pressed")):
            with self.subTest(name):
                self.assertNotEqual(before, after)

    def test_a_text_area_shows_the_soft_bar_and_never_windows_own(self):
        """The log beside the bar is a SoftTextArea: its box is wider than its clip by Windows' own scroll bar, which the
        real window never shows - only the soft bar. DrawToBitmap printed that native bar anyway (the owner spotted it
        in the first pictures, 2026-10-20). Where the box keeps it, a frame holds none of its plain greys - its track and
        arrows are r = g = b, which no colour of the window's palette is - and the bar's place shows what the area
        itself draws there."""
        plan = motion.load("install-en")
        events = len(plan["events"])
        frames = [{"index": 0, "page": "welcome", "light": 0}, {"index": 1, "page": "options", "light": 40},
                  {"index": 2, "page": "progress", "progress": events, "light": 80}]
        data = motion.job(plan, [], Path(self.work.name) / "bar" / "frames")
        data["frames"] = frames
        result = motion.render(self.exe, data, Path(self.work.name) / "bar")
        index, (width, height), picture, bounds = list(motion.pictures(result, Path(self.work.name) / "bar" / "frames"))[-1]
        self.assertIn("area.0", bounds, "the Progress page shows its log")
        left, top, wide, tall = (int(value) for value in bounds["native.0"])
        greys = 0
        for y in range(max(0, top), min(height, top + tall)):
            for x in range(max(0, left), min(width, left + wide)):
                red, green, blue = picture[(y * width + x) * 3:(y * width + x) * 3 + 3]
                greys += red == green == blue and 40 <= red <= 250
        self.assertLess(greys, max(8, wide * tall // 200), "Windows' own scroll bar shows in the log (%d plain grey "
                                                            "pixels where the box keeps it)" % greys)

    def test_it_refuses_to_go_back_a_page(self):
        plan = motion.load("install-en")
        data = motion.job(plan, [], Path(self.work.name) / "back" / "frames")
        data["frames"] = [{"index": 0, "page": "options", "light": 0}, {"index": 1, "page": "welcome", "light": 40}]
        with self.assertRaises(RuntimeError) as caught:
            motion.render(self.exe, data, Path(self.work.name) / "back")
        self.assertIn("cannot go back", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
