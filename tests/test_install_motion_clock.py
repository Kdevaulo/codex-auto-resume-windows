"""The setup window's bar in the install motion glides on the picture's clock (v0.6.26, audit-apng M6): the frames tell
the shim (build/motion/InstallerRender.cs) their moment, the bar takes its own timer's steps up to it - part way between
two milestones a frame after the line that moved it, at the milestone well after - and when the run ends the bar fills
before the Finish page comes, as InstallerBar.Finish holds it back for up to FinishSeconds. Nothing is shown on the
screen and no picture is compared with a committed one: the shim says how far its bar is drawn (`bar.shown`) and which
page each frame shows."""
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
import motion_plan  # noqa: E402

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
# The bar's own numbers (gui/InstallerWindow.cs InstallerBar, gui/InstallerFlow.cs InstallerProgress).
GLIDE_INTERVAL = 16
FINISH_MS = 400


class JobTests(unittest.TestCase):
    def test_every_frame_of_the_job_tells_the_shim_its_moment(self):
        plan = motion.load("install-en")
        frames = motion_plan.expand(plan)[:3]
        states = motion.job(plan, frames, Path("frames"))["frames"]
        self.assertEqual([state["moment"] for state in states], [frame.t for frame in frames])


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "the setup window is built with Windows' C# compiler")
class BarClockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory(prefix="install-clock-test-")
        exe = motion.compile_shim(Path(cls.work.name) / "shim")
        plan = motion.load("install-en")
        events = len(plan["events"])
        frames = [{"page": "welcome", "moment": 0}, {"page": "options", "moment": 100},
                  {"page": "progress", "progress": 0, "moment": 200},
                  {"page": "progress", "progress": 20, "moment": 1000},       # 3 the lines that move the bar
                  {"page": "progress", "progress": 20, "moment": 1032},       # 4 two of its steps later
                  {"page": "progress", "progress": 20, "moment": 2000},       # 5 there
                  {"page": "progress", "progress": events, "moment": 3000},
                  {"page": "progress", "progress": events, "moment": 3600}]   # 7 at the last milestone
        # The run ends at 4000: a frame at each of the bar's steps for its FinishSeconds, then one well after.
        cls.end = len(frames)
        frames += [{"page": "finish", "progress": events, "moment": 4000 + step}
                   for step in range(0, FINISH_MS + GLIDE_INTERVAL, GLIDE_INTERVAL)]
        frames.append({"page": "finish", "progress": events, "moment": 5000})
        for index, frame in enumerate(frames):
            frame.update(index=index, light=0)
        data = motion.job(plan, [], Path(cls.work.name) / "clock" / "frames")
        data["frames"] = frames
        cls.frames = frames
        cls.result = motion.render(exe, data, Path(cls.work.name) / "clock")

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def shown(self, index):
        bar = self.result["frames"][index]["bounds"].get("bar.shown")
        return None if bar is None else bar[0]

    def test_it_ran_and_noted_nothing(self):
        self.assertEqual(self.result["notes"], [])
        self.assertEqual(len(self.result["frames"]), len(self.frames))

    def test_the_bar_glides_up_to_where_the_work_is(self):
        at_lines, part_way, there = self.shown(3), self.shown(4), self.shown(5)
        self.assertEqual(at_lines, self.shown(2), "at the lines' own moment it has not moved yet")
        self.assertLess(at_lines, part_way, "two steps later it is on its way")
        self.assertLess(part_way, there, "...and not yet there")

    def test_the_run_s_end_fills_the_bar_before_the_finish_page(self):
        pages = [entry.get("page") for entry in self.result["frames"][self.end:]]
        self.assertEqual(pages[0], "progress", "the run has ended; the bar fills on the Progress page")
        self.assertEqual(pages[-1], "finish")
        first = pages.index("finish")
        self.assertEqual(pages[first:], ["finish"] * (len(pages) - first), "and the Finish page stays")
        self.assertLessEqual(first, FINISH_MS // GLIDE_INTERVAL + 1, "within FinishSeconds of the run's end")
        filled = [self.shown(self.end + index) for index in range(first)]
        self.assertLess(filled[0], 1.0)
        self.assertEqual(filled, sorted(filled), "the bar only goes forward")
        self.assertGreater(filled[-1], filled[0], "it fills while the Finish page waits")


if __name__ == "__main__":
    unittest.main()
