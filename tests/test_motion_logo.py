"""The README's logo, moving (build/motion_logo.py): the icon's own watching motion on the logo's own drawing.

Frame 1 must be the static logo exactly (what a viewer without APNG shows), every frame the logo but where the icon's
own head moves, the dark logo's rim kept, one whole cycle of the icon's own schedule, and the same bytes every time.
Pure Python: nothing is drawn by Windows.
"""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import make_motion  # noqa: E402
import motion_logo  # noqa: E402

SIZE = 48              # small, so the tests are quick; the plans draw 192


def plan(dark=False):
    return {"format": "car-motion/1", "kind": "logo", "name": "logo-test", "size": SIZE, "dark": dark,
            "state": "watching", "output": "unused.png"}


class LogoFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.light = list(motion_logo.frames(plan()))
        cls.dark = list(motion_logo.frames(plan(dark=True)))

    def test_frame_one_is_the_static_logo_exactly(self):
        from codex_auto_resume import brand
        self.assertEqual(self.light[0][2], brand.icon_render(SIZE), "a viewer without APNG sees the logo")
        self.assertEqual(self.dark[0][2], brand.icon_render(SIZE, motion_logo.logo_rim(True)),
                         "and the dark one with its rim")
        self.assertGreater(motion_logo.logo_rim(True), 0.0)
        self.assertEqual(motion_logo.logo_rim(False), 0.0)

    def test_it_is_one_cycle_of_the_icon_s_own_watching_schedule(self):
        import make_screenshots
        import make_social
        cycle = motion_logo.cycle("watching")
        self.assertEqual([delay for delay, _scene, _picture in self.light], [delay for delay, _p, _l in cycle])
        shown = make_screenshots.icon_timeline("watching", 0.0, make_social.watching_loop_ms())
        self.assertEqual(len(cycle), len(shown), "every frame the icon's timer shows, none merged or dropped")
        self.assertEqual(sum(delay for delay, _p, _l in cycle), make_social.watching_loop_ms())
        self.assertIn("sweep", {scene for _delay, scene, _picture in self.light})
        self.assertGreater(len({picture for _delay, _scene, picture in self.light}), 10, "the head moves")

    def test_only_the_icon_s_head_moves_and_the_rim_and_corners_stay(self):
        from codex_auto_resume import brand
        static = brand.icon_render(SIZE, motion_logo.logo_rim(True))
        changed = set()
        for _delay, _scene, picture in self.dark:
            for index in range(0, len(picture), 4):
                if picture[index:index + 4] != static[index:index + 4]:
                    changed.add((index // 4) % SIZE + (index // 4) // SIZE * 1j)
        self.assertTrue(changed, "nothing moved")
        edge = 3
        self.assertFalse([point for point in changed if not (edge <= point.real < SIZE - edge
                                                             and edge <= point.imag < SIZE - edge)],
                         "the motion reached the rim or the clear corners")
        self.assertTrue(all(picture[3] == static[3] == 0 for _d, _s, picture in self.dark), "the corner stays clear")

    def test_the_same_plan_makes_the_same_bytes_and_a_clear_cornered_rgba_apng(self):
        with tempfile.TemporaryDirectory() as name:
            outputs = []
            for run in (1, 2):
                given = dict(plan(), output=str(Path(name) / ("logo-%d.png" % run)))
                report = motion_logo.make(given)
                outputs.append(Path(given["output"]).read_bytes())
        self.assertEqual(outputs[0], outputs[1])
        raw = outputs[0]
        width, height, depth, colour = struct.unpack(">IIBB", raw[16:26])
        self.assertEqual((width, height, depth, colour), (SIZE, SIZE, 8, 6))
        self.assertGreater(report.frames, 10)
        self.assertEqual(report.ms, sum(delay for delay, _s, _p in self.light))

    def test_the_readme_logo_plans_are_drawn_at_192_within_their_budget(self):
        self.assertEqual(make_motion.LOGO_PLANS, ("logo-light", "logo-dark"))
        for name, dark in (("logo-light", False), ("logo-dark", True)):
            with self.subTest(name):
                given = make_motion.load(name)
                self.assertEqual((given["kind"], given["size"], given["dark"]), ("logo", 192, dark))
                self.assertEqual(given["budget"], {"cap": 2000000}, "quality first: a ceiling, no target")

    def test_what_the_logo_is_made_from_moves_with_the_icon_s_drawing_and_motion(self):
        import make_screenshots as shots
        given = make_motion.load("logo-light")
        before = make_motion.render_input(given)
        self.assertEqual(make_motion.render_input(dict(given)), before)
        with mock.patch.object(shots, "icon_drawing", return_value="moved"):
            self.assertNotEqual(make_motion.render_input(given), before)
        with mock.patch.object(shots, "window_digest", return_value="moved"):
            self.assertEqual(make_motion.render_input(given), before, "the window does not draw the logo")
        self.assertNotEqual(make_motion.render_input(make_motion.load("logo-dark")), before)


if __name__ == "__main__":
    unittest.main()
