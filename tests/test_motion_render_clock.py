"""The window's glides in a motion picture are drawn at each frame's moment (v0.6.26, audit-apng M6): the current tab, a
button's hover and the busy look glide from the frame their change came in, on the picture's clock, never the wall clock -
and a paused window opened again for the picture carries the call in flight, so the call's end glides there too. One
small job of the real window, offscreen, never on the screen; nothing is captured; the frames are compared with each
other. And every frame the generator writes tells the window its moment."""
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

import motion_plan  # noqa: E402
import motion_window  # noqa: E402

OVERVIEW = {"locale": "en", "page": "overview", "light": 0}
PENDING = {"locale": "en", "page": "pending", "light": 0, "selected": {"pending": 0}}


class FrameMomentTests(unittest.TestCase):
    def test_every_frame_tells_the_window_its_moment(self):
        frame = motion_plan.Frame(1234, "S1", (("page", "pending"),), (), ("at", "page.pending"), ())
        state = motion_window.frame_state(frame, 7, light_step=33)
        self.assertEqual(state["moment"], 1234)
        self.assertEqual(state["light"], 1221, "the light keeps its own timer's step")


@unittest.skipUnless(os.name == "nt" and motion_window.CSC.is_file(), "the window is built with Windows' C# compiler")
class RenderClockTests(unittest.TestCase):
    FRAMES = [
        dict(OVERVIEW, moment=0),                                                  # 0 at rest
        dict(PENDING, moment=1000),                                                # 1 the tab's change comes in
        dict(PENDING, moment=1080),                                                # 2 half way through its glide
        dict(PENDING, moment=1400),                                                # 3 arrived
        dict(PENDING, moment=2000, hover="pending.retry"),                         # 4 the pointer comes onto Retry now
        dict(PENDING, moment=2080, hover="pending.retry"),                         # 5 half way
        dict(PENDING, moment=2400, hover="pending.retry"),                         # 6 arrived
        dict(OVERVIEW, moment=3000),                                               # 7 the Overview at rest
        dict(OVERVIEW, moment=3500, busy=True),                                    # 8 Pause's call in flight comes in
        dict(OVERVIEW, moment=3580, busy=True),                                    # 9 half way to the busy look
        dict(OVERVIEW, moment=3900, busy=True),                                    # 10 arrived
        dict(OVERVIEW, moment=4500, variant="paused"),                             # 11 the call answered: paused
        dict(OVERVIEW, moment=4580, variant="paused"),                             # 12 half way back from the busy look
        dict(OVERVIEW, moment=4900, variant="paused"),                             # 13 arrived
    ]

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = motion_window.compile_window(work)
        job = {"out": str(work / "out"), "theme": "light", "design": "soft",
               "forms": {"en": {"answers": motion_window.answers("en")},
                         "en-paused": {"answers": motion_window.answers("en", paused=True)}},
               "targets": ["page.pending", "pending.retry", "overview.toggle"],
               "frames": [dict(frame, index=index) for index, frame in enumerate(cls.FRAMES)]}
        cls.result = motion_window.render(exe, job, work)
        cls.pictures = list(motion_window.pictures(cls.result, work / "out"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def level(self, index, box):
        """The mean of every channel of frame `index` over `box` (left, top, width, height)."""
        width = self.result["client"][0]
        picture = self.pictures[index][1]
        x, y, wide, tall = (int(value) for value in box)
        total = sum(sum(picture[(row * width + x) * 3:(row * width + x + wide) * 3]) for row in range(y, y + tall))
        return total / float(wide * tall * 3)

    def half_way(self, index, start, end, name):
        """Frame `index` over target `name` stands strictly between frames `start` and `end` there, on average: a glide
        part way, not a cut at either end."""
        box = self.pictures[end][2][name]
        part, low, high = self.level(index, box), self.level(start, box), self.level(end, box)
        self.assertGreater(abs(high - low), 1, "%s changes at all (%.2f to %.2f)" % (name, low, high))
        self.assertTrue(min(low, high) + 0.2 < part < max(low, high) - 0.2,
                        "%s half way: %.2f, between %.2f and %.2f" % (name, part, low, high))

    def test_every_frame_was_drawn_and_every_read_answered(self):
        self.assertEqual(self.result["notes"], [])
        self.assertEqual(self.result["misses"], [])
        self.assertEqual(len(self.pictures), len(self.FRAMES))

    def test_the_current_tab_glides(self):
        self.half_way(2, 1, 3, "page.pending")

    def test_a_hover_glides_from_the_frame_it_came_in(self):
        self.half_way(5, 4, 6, "pending.retry")
        self.assertEqual(self.pictures[4][1], self.pictures[3][1], "at its first moment it has not moved yet")

    def test_the_busy_look_glides(self):
        self.half_way(9, 8, 10, "overview.toggle")

    def test_a_paused_window_opened_again_glides_out_of_the_call_in_flight(self):
        self.half_way(12, 11, 13, "overview.toggle")


if __name__ == "__main__":
    unittest.main()
