"""v0.6.24: the window draws the same squircle the popup and the card draw.

gui/SoftShape.cs is brand/shape.py in C#. Held here, through the window's own compiled code (tests/squircleprobe.py,
which shows no window): one outline point for point, one profile, Soft.Rounded drawing the squircle at the design's
smoothing - Soft's, and Soft's in High Contrast as its radii are - and the circular corner, path for path as v0.6.23
drew it, in Classic, in Plain and wherever the budget leaves a corner round.
"""
from __future__ import annotations

import unittest

import guiscan
import squircleprobe
from codex_auto_resume.brand import shape

NAMES = (("top_left", 1), ("top_right", 2), ("bottom_right", 4), ("bottom_left", 8))

# (left, top, right, bottom, radius, smoothing, corners): a card, the board's box, a control, the owner's 34 px
# control and caption button, pills, a scale's fractions, the day scene's two outer corners, and the circle.
OUTLINES = ((0, 0, 120, 80, 16, 0.6, 15), (3, 5, 333, 405, 16, 0.6, 15), (0, 0, 90, 34, 11, 0.6, 15),
            (0, 0, 34, 34, 11, 0.6, 15), (10, 20, 44, 46, 7, 0.6, 15), (0, 0, 140, 22, 11, 0.6, 15),
            (0.5, 1.5, 300.25, 401.75, 24, 0.6, 15), (0, 0, 300, 90, 15, 0.6, 6), (0, 0, 300, 90, 15, 0.6, 9),
            (0, 0, 120, 80, 16, 0.0, 15), (0, 0, 46, 40, 11, 0.6, 15), (0, 0, 18, 18, 5, 0.6, 15))


def _flat(segment) -> list:
    kind = segment[0]
    if kind == "bezier":
        return [0.0] + [value for point in segment[1:] for value in point]
    if kind == "arc":
        (cx, cy), radius, start, sweep = segment[1:]
        return [1.0, cx, cy, radius, start % 360.0, sweep]
    return [2.0] + list(segment[1])


@unittest.skipUnless(squircleprobe.available(), "needs the in-box C# compiler")
class ParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lines = ["outline %r %r %r %r %r %r %d" % case for case in OUTLINES]
        lines += ["rounded light soft 0 0 120 80 16", "rounded dark soft 0 0 120 80 16",
                  "rounded light classic 0 0 120 80 16", "rounded dark plain 0 0 120 80 8",
                  "rounded contrast classic 0 0 120 80 16", "rounded contrast plain 0 0 120 80 16",
                  "rounded light soft 0 0 140 22 11", "rounded light soft 0 0 0.8 0.8 16"]
        cls.profiles = ((16, 0.6, 40), (11, 0.6, 17), (32, 0.6, 999), (7, 0.6, 13))
        lines += ["profile %r %r %r" % case for case in cls.profiles]
        cls.answers = squircleprobe.ask(lines)

    def test_every_outline_is_shapes_to_a_thousandth(self):
        for case, got in zip(OUTLINES, self.answers):
            left, top, right, bottom, radius, smoothing, mask = case
            named = tuple(name for name, bit in NAMES if mask & bit)
            want = [_flat(segment) for segment in shape.outline((left, top, right, bottom), radius, smoothing, named)]
            with self.subTest(case=case):
                self.assertEqual([segment[0] for segment in got], [segment[0] for segment in want])
                for mine, theirs in zip(got, want):
                    mine = list(mine)
                    if mine[0] == 1.0:
                        mine[4] %= 360.0
                    self.assertEqual(len(mine), len(theirs))
                    for a, b in zip(mine, theirs):
                        self.assertAlmostEqual(a, b, delta=1e-3)

    def test_soft_rounded_is_the_squircle_and_classic_and_plain_the_circle(self):
        soft, soft_dark, classic, plain, contrast_classic, contrast_plain, pill, dot = self.answers[len(OUTLINES):len(OUTLINES) + 8]
        for name, answer in (("soft", soft), ("soft dark", soft_dark), ("contrast over classic", contrast_classic),
                             ("contrast over plain", contrast_plain)):
            with self.subTest(design=name):
                self.assertEqual(answer["smoothing"], shape.design_smoothing("soft"))
                self.assertTrue(answer["squircle"], "Soft.Rounded is Shape.Squircle at Soft's smoothing")
                self.assertFalse(answer["arcs"])
        for name, answer in (("classic", classic), ("plain", plain)):
            with self.subTest(design=name):
                self.assertEqual(answer["smoothing"], 0)
                self.assertTrue(answer["arcs"], "the circular corner, path for path as v0.6.23 drew it")
        self.assertTrue(pill["arcs"] and pill["squircle"], "a pill is the same semicircles either way")
        self.assertEqual(dot["points"], 4, "a box under a pixel is its rectangle")

    def test_the_profiles_are_shapes(self):
        for case, got in zip(self.profiles, self.answers[len(OUTLINES) + 8:]):
            made = shape.profile(*case)
            with self.subTest(case=case):
                self.assertAlmostEqual(got["p"], made.p, places=9)
                self.assertEqual(len(got["rho"]), len(made.rho))
                self.assertLess(max(abs(a - b) for a, b in zip(got["rho"], made.rho)), 1e-6)
                self.assertLess(max(abs(a - b) for a, b in zip(got["lean"], made.lean)), 1e-6)


class SourceTests(unittest.TestCase):
    def test_soft_rounded_keeps_its_signature_and_draws_the_shape(self):
        body = guiscan.member_body("Soft", "Rounded")
        self.assertIn("internal static GraphicsPath Rounded(RectangleF bounds, float radius)", body)
        self.assertIn("return Shape.Squircle(bounds, radius, Shape.Smoothing);", body)
        self.assertNotIn("AddArc", body, "one geometry: Shape's")

    def test_the_day_scene_cuts_its_outer_corners_from_the_shape(self):
        body = guiscan.member_body("SoftDayScene", "Rounding")
        self.assertIn("Shape.Squircle(", body)
        self.assertIn("Shape.Corners.TopLeft | Shape.Corners.BottomLeft", body)
        self.assertIn("Shape.Corners.TopRight | Shape.Corners.BottomRight", body)
        self.assertIn("Region = new Region(", body)

    def test_the_shape_is_a_control_source_and_reads_the_generated_smoothing(self):
        self.assertIn("gui/SoftShape.cs", guiscan.group("controls"))
        source = guiscan.read("gui/SoftShape.cs")
        self.assertIn("Brand.DesignSmoothing(Design.Drawn(Palette.Theme, Palette.Design))", source)
        brand_cs = guiscan.read("gui/Brand.cs")
        self.assertIn("internal const double CornerSmoothing = 0.6;", brand_cs)
        self.assertIn("internal static double DesignSmoothing(string design)", brand_cs)


if __name__ == "__main__":
    unittest.main()
