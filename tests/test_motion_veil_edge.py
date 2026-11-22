"""The veil under a dialog in a motion picture is the product's veil (v0.6.26; guifix D9, D10): DialogVeil dims each of
the window's pixels at how much of it is the window's - its hairline as much as the rest, its anti-aliased edge at that
edge's coverage, over the window and what shows through it alike. The render mode cuts a frame's own edge before it
lays the veil (so the hairline is dimmed with the window), says which veil it laid (frames.json `veil`), and the
compositor lays each partly covered edge pixel as the screen composes it. One small job of the real window, offscreen,
never on the screen; nothing is captured, no committed picture is compared."""
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

import motion_compose  # noqa: E402
import motion_window  # noqa: E402

PENDING = {"locale": "en", "page": "pending", "light": 0, "selected": {"pending": 0}}


def light_veil() -> tuple:
    """The product's veil at its fullest in light (gui/SoftChrome.cs DialogVeil): 20 % of the theme's ink."""
    from codex_auto_resume import brand
    return int(round(255 * 0.20)), tuple(brand.rgb(brand.palette("light", "soft")["ink"]))


def veiled(under: int, ink: int, alpha: int) -> int:
    """gui/WindowRender.cs Veiled: one channel under the veil's ink at `alpha`."""
    return (ink * alpha + under * (255 - alpha) + 127) // 255


class CompositorTests(unittest.TestCase):
    """WindowChrome.frame lays a partly covered edge pixel of a veiled frame as the screen composes the window's edge
    under DialogVeil: the window's own colour at its coverage over what is under it, the veil's ink at its alpha times
    that coverage over both."""

    def chrome(self):
        # A window 3 by 2 with no caption: its top-left pixel half the window's, every other wholly; a clear canvas.
        rgb = bytes(3 * 2 * 3)
        alpha = bytes([128, 255, 255, 255, 255, 255])
        return motion_compose.WindowChrome((3, 2, rgb, alpha), (3, 2), size=(3, 2), at=(0, 0), ground=(200, 200, 200),
                                           shadow=False)

    def test_a_partly_covered_edge_pixel_is_dimmed_at_its_coverage_over_what_is_under_it(self):
        chrome = self.chrome()
        window, ink, alpha = (240, 230, 220), (30, 40, 50), 51
        client = bytes([channel for _ in range(6) for channel in (veiled(window[0], ink[0], alpha),
                                                                   veiled(window[1], ink[1], alpha),
                                                                   veiled(window[2], ink[2], alpha))])
        picture = chrome.frame(client, (alpha, ink))
        ground = 200
        for c in range(3):
            cover = 128 / 255.0
            edge = window[c] * cover + ground * (1 - cover)
            share = alpha * cover / 255.0
            wanted = ink[c] * share + edge * (1 - share)
            self.assertAlmostEqual(picture[c], wanted, delta=1.0, msg="channel %d" % c)
        # A pixel wholly the window's is the frame's own, veiled at the veil's full alpha.
        self.assertEqual(tuple(picture[3:6]), tuple(client[3:6]))

    def test_without_a_veil_the_edge_is_the_frame_s_own_at_its_coverage(self):
        chrome = self.chrome()
        client = bytes([240, 230, 220] * 6)
        picture = chrome.frame(client)
        self.assertAlmostEqual(picture[0], 240 * 128 / 255.0 + 200 * 127 / 255.0, delta=1.0)


@unittest.skipUnless(os.name == "nt" and motion_window.CSC.is_file(), "the window is built with Windows' C# compiler")
class RenderVeilTests(unittest.TestCase):
    FRAMES = [dict(PENDING), dict(PENDING, dialog={"kind": "timeline"}), dict(PENDING, dialog={"kind": "timeline",
                                                                                               "appear_ms": 60})]

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = motion_window.compile_window(work)
        import make_screenshots
        cls.edge = motion_window.frame_edge()
        job = {"out": str(work / "out"), "theme": "light", "design": "soft", "scale": make_screenshots.PINNED_SCALE,
               **cls.edge, "forms": {"en": {"answers": motion_window.answers("en")}},
               "targets": ["dialog.window"],
               "frames": [dict(frame, index=index) for index, frame in enumerate(cls.FRAMES)]}
        cls.result = motion_window.render(exe, job, work)
        cls.pictures = list(motion_window.pictures(cls.result, work / "out"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def pixel(self, index, x, y):
        width = self.result["client"][0]
        at = (y * width + x) * 3
        return tuple(self.pictures[index][1][at:at + 3])

    def test_each_frame_with_the_dialog_says_the_veil_it_laid(self):
        self.assertEqual(self.result["notes"], [])
        veils = motion_window.veils(self.result)
        self.assertNotIn(0, veils, "no dialog, no veil")
        alpha, ink = veils[1]
        self.assertEqual((alpha, ink), light_veil(), "at rest: DialogVeil.FullNow in light (20 %), the theme's ink")
        self.assertLess(veils[2][0], alpha, "part way in, part of it")
        self.assertEqual(veils[2][1], ink)

    def test_the_window_s_hairline_is_dimmed_with_the_rest_of_the_window(self):
        if not self.edge:
            self.skipTest("the window has Windows' corner: no hairline of its own in its frames")
        alpha, ink = light_veil()
        width, height = self.result["client"]
        # The middle of each edge - the top's and the left's outermost pixels are the hairline - and one pixel in.
        for x, y in ((width // 2, 0), (0, height // 2), (width // 2, 1), (width - 1, height // 2), (width // 2, height - 1)):
            with self.subTest(x=x, y=y):
                rest, under = self.pixel(0, x, y), self.pixel(1, x, y)
                self.assertEqual(under, tuple(veiled(rest[c], ink[c], alpha) for c in range(3)))

    def test_every_pixel_of_the_window_s_corner_is_veiled_alike_for_the_compositor(self):
        if not self.edge:
            self.skipTest("the window has Windows' corner, which the compositor cuts")
        alpha, ink = light_veil()
        width, height = self.result["client"]
        for y in range(0, 24):
            for x in range(0, 24):
                rest, under = self.pixel(0, x, y), self.pixel(1, x, y)
                if rest == (0, 0, 0):
                    continue                     # outside the corner: nothing of the window
                self.assertEqual(under, tuple(veiled(rest[c], ink[c], alpha) for c in range(3)), (x, y))
                back = motion_compose.unveiled(under, (alpha, ink))
                self.assertLessEqual(max(abs(a - b) for a, b in zip(back, rest)), 1, (x, y, back, rest))


if __name__ == "__main__":
    unittest.main()
