"""v0.6.24: the window's render mode draws the status light's sweep, the line under the headline gliding in as it ends,
and the veil under a dialog (gui/WindowRender.cs RenderSweep, PaintVeil).

- A frame `sweep` ms into the sweep draws the light's own sweep at that moment (HaloDot.StillSweepMs, by its own
  DrawSweep) and the line under the headline as an Arrive(AsideAfterMs) leaves it then (AsideLabel.ArriveAt): held back,
  gliding in over OutMs, then simply there. Past the sweep's end the window is at rest, pixel for pixel.
- A frame with a dialog open lays the veil over the whole window under it: the shadow's ink at DialogVeil's alpha at its
  fullest - 51 in light, 82 in dark.

Small jobs of the real window, offscreen - nothing shown, nothing captured.
GUI test module (it compiles the window): run on its own, through gui_lock.sh.
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

import motion_plan  # noqa: E402
import motion_window  # noqa: E402

# The light's sweep (gui/Marks.cs HaloDot) and the line's arrival (SettingsForm.AsideAfterMs, AsideLabel.OutMs), in ms.
ARC_MS = 735
LINE_AFTER, LINE_GLIDE = 850, 400


def box(width, one, other):
    """(left, top, right, bottom) of the pixels two RGB pictures differ in, or None."""
    xs, ys = [], []
    for y in range(len(one) // (width * 3)):
        a, b = one[y * width * 3:(y + 1) * width * 3], other[y * width * 3:(y + 1) * width * 3]
        if a == b:
            continue
        ys.append(y)
        xs.extend(x for x in range(width) if a[x * 3:x * 3 + 3] != b[x * 3:x * 3 + 3])
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1) if xs else None


def render(theme: str, frames: list, work: Path, exe: Path):
    job = {"out": str(work / theme), "theme": theme, "design": "soft",
           "forms": {"en": {"answers": motion_window.answers("en")}},
           "targets": ["overview.toggle", "pending.timeline", "dialog.close", "dialog.window"],
           "chrome": motion_window.chrome({"window": {"still": "assets/screenshot-dashboard.png"}}),
           "frames": [dict(frame, index=index) for index, frame in enumerate(frames)]}
    result = motion_window.render(exe, job, work / ("job-" + theme))
    return result, list(motion_window.pictures(result, work / theme))


@unittest.skipUnless(os.name == "nt" and motion_window.CSC.is_file(), "the window is built with Windows' C# compiler")
class SweepAndVeilTests(unittest.TestCase):
    SWEEP = [
        {"locale": "en", "page": "overview", "light": 0},                     # 0 at rest
        {"locale": "en", "page": "overview", "light": 0, "sweep": 0},         # 1 the window opening
        {"locale": "en", "page": "overview", "light": 0, "sweep": 400},       # 2 the arc half way round
        {"locale": "en", "page": "overview", "light": 0, "sweep": LINE_AFTER - 15},              # 3 the line still held
        {"locale": "en", "page": "overview", "light": 0, "sweep": LINE_AFTER + LINE_GLIDE // 2},  # 4 gliding in
        {"locale": "en", "page": "overview", "light": 0, "sweep": LINE_AFTER + LINE_GLIDE + 15},  # 5 in; the rings
        {"locale": "en", "page": "overview", "light": 0, "sweep": motion_plan.SWEEP_MS},           # 6 over
        {"locale": "en", "page": "overview", "light": 0},                     # 7 at rest again
    ]
    VEIL = [
        {"locale": "en", "page": "pending", "light": 0},                                    # 0 at rest
        {"locale": "en", "page": "pending", "light": 0, "dialog": {"kind": "timeline"}},    # 1 the dialog open
        {"locale": "en", "page": "pending", "light": 0},                                    # 2 closed
    ]

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = motion_window.compile_window(work / "exe")
        cls.light, cls.lights = render("light", cls.SWEEP + cls.VEIL, work, exe)
        cls.dark, cls.darks = render("dark", cls.VEIL, work, exe)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def picture(self, index):
        return self.lights[index][1]

    def differ(self, one, other):
        return box(self.light["client"][0], self.picture(one), self.picture(other))

    def test_every_frame_was_drawn_and_every_read_answered(self):
        for result, drawn, frames in ((self.light, self.lights, self.SWEEP + self.VEIL), (self.dark, self.darks, self.VEIL)):
            self.assertEqual(result["notes"], [])
            self.assertEqual(result["misses"], [])
            self.assertEqual(len(drawn), len(frames))

    def test_mid_sweep_the_light_differs_from_rest_and_at_its_end_the_window_is_at_rest(self):
        self.assertIsNotNone(self.differ(0, 2), "the arc half way round")
        self.assertIsNotNone(self.differ(0, 5), "the rings after the line has come in")
        self.assertIsNotNone(self.differ(2, 5))
        self.assertEqual(self.picture(6), self.picture(0), "the sweep over: the window at rest")
        self.assertEqual(self.picture(7), self.picture(0))

    def test_once_the_line_is_in_only_the_light_differs_from_rest(self):
        width = self.light["client"][0]
        changed = self.differ(0, 5)
        toggle = self.lights[0][2]["overview.toggle"]
        self.assertLess(changed[2], width * 0.12, "the light, at the header's left: %r" % (changed,))
        self.assertLess(changed[3], toggle[1], "above the Right now card: %r" % (changed,))

    def test_the_line_under_the_headline_is_absent_before_its_glide_and_present_after(self):
        width = self.light["client"][0]
        held = self.differ(0, 3)
        self.assertIsNotNone(held)
        self.assertGreater(held[2] - held[0], width * 0.2, "a whole line of words is missing: %r" % (held,))
        line = box(width, self.picture(2), self.picture(3))
        self.assertTrue(line is None or line[2] < width * 0.12, "held back alike at 400 and 835 ms: only the light moves")
        gliding = self.differ(3, 4)
        self.assertIsNotNone(gliding, "coming in")
        self.assertGreater(gliding[2] - gliding[0], width * 0.2)
        self.assertIsNotNone(self.differ(0, 4), "not yet all there half way through its glide")
        # In: where the line is, the frame after its glide is the window at rest.
        top, bottom = held[1], held[3]
        rest, after = self.picture(0), self.picture(5)
        left = int(width * 0.12)
        for y in range(top, bottom):
            self.assertEqual(after[(y * width + left) * 3:(y + 1) * width * 3],
                             rest[(y * width + left) * 3:(y + 1) * width * 3], "row %d of the line" % y)

    def veil_fit(self, drawn, result):
        """[(alpha, ink, worst)] for each channel: the veil the frame with the dialog open lays over the frame at rest,
        outside the dialog and its shadow, as the straight line through every such pixel, out = ink a + under (1 - a);
        `worst` is the farthest a pixel is from it, in levels."""
        width, height = result["client"]
        rest, veiled = drawn[0][1], drawn[1][1]
        x, y, wide, tall = drawn[1][2]["dialog.window"]
        reach = 40
        channels = ([], [], [])
        for row in range(0, height, 3):
            for column in range(0, width, 3):
                if x - reach <= column < x + wide + reach and y - reach <= row < y + tall + reach:
                    continue
                at = (row * width + column) * 3
                for channel in range(3):
                    channels[channel].append((rest[at + channel], veiled[at + channel]))
        fits = []
        for pairs in channels:
            count = float(len(pairs))
            mean_u = sum(u for u, _o in pairs) / count
            mean_o = sum(o for _u, o in pairs) / count
            slope = (sum((u - mean_u) * (o - mean_o) for u, o in pairs) / sum((u - mean_u) ** 2 for u, _o in pairs))
            alpha = 1.0 - slope
            ink = (mean_o - slope * mean_u) / alpha
            fits.append((alpha * 255, ink, max(abs(o - (ink * alpha + u * slope)) for u, o in pairs)))
        return fits

    def test_the_veil_is_at_its_fullest_in_light_and_in_dark(self):
        for name, result, drawn, full in (("light", self.light, self.lights[len(self.SWEEP):], 51),
                                          ("dark", self.dark, self.darks, 82)):
            with self.subTest(name):
                for alpha, ink, worst in self.veil_fit(drawn, result):
                    self.assertAlmostEqual(alpha, full, delta=0.6)
                    self.assertLessEqual(worst, 1.5, "one veil over the whole window, of one ink")
                    self.assertLess(ink, 128, "the shadow's ink, never a light one")
                self.assertEqual(drawn[2][1], drawn[0][1], "gone with the dialog")


if __name__ == "__main__":
    unittest.main()
