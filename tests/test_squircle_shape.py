"""v0.6.24: the corner is Figma's squircle at 60 %, as the owner approved it on the Squircle board.

brand/shape.py is the geometry the window, the popup and the notification card draw with. Held here: the board's own
path (its numbers are the fixture), the budget that backs the smoothing off on a short side, pills and rings that
stay circles, the designs that keep circular corners, and `inside` and `distance` against the outline itself.
"""
from __future__ import annotations

import math
import random
import unittest

from codex_auto_resume import brand
from codex_auto_resume.brand import scale, shape


# The Squircle board's path for a 16 px corner at 60 %:
#   M 94.4 0 c 8.96 0 13.44 0 16.86 1.74 a 16 16 0 0 1 6.99 6.99 ...
# on a box 120 px wide - the corner begins 25.6 px from its vertex.
BOARD = {"p": 25.6, "a": 8.96, "a+b": 13.44, "a+b+c": 16.86, "d": 1.74, "chord": 6.99}


def _polygon_inside(x, y, points) -> bool:
    inside = False
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def _to_segment(x, y, a, b) -> float:
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length))
    return math.hypot(x - ax - t * dx, y - ay - t * dy)


class BoardTests(unittest.TestCase):
    def test_the_token_is_sixty_percent_and_soft_draws_it(self):
        self.assertEqual(scale.CORNER_SMOOTHING, 0.6)
        self.assertEqual(shape.design_smoothing("soft"), scale.CORNER_SMOOTHING)
        self.assertEqual(shape.design_smoothing(), scale.CORNER_SMOOTHING, "Soft is the default design")

    def test_classic_and_plain_keep_circular_corners(self):
        self.assertEqual(shape.design_smoothing("classic"), 0.0)
        self.assertEqual(shape.design_smoothing("plain"), 0.0)
        self.assertEqual(set(shape.DESIGN_SMOOTHING), set(brand.DESIGNS), "every design says")

    def test_a_16_px_corner_is_the_boards_path(self):
        found = shape.corner(16, 0.6, 1000)
        got = {"p": found.p, "a": found.a, "a+b": found.a + found.b, "a+b+c": found.a + found.b + found.c,
               "d": found.d, "chord": found.chord}
        for name, want in BOARD.items():
            with self.subTest(name=name):
                self.assertAlmostEqual(got[name], want, delta=0.005)

    def test_the_outline_starts_where_the_board_does(self):
        segments = shape.outline((0, 0, 120, 80), 16, 0.6)
        top_right = segments[3:6]
        kind, p0, p1, p2, p3 = top_right[0]
        self.assertEqual(kind, "bezier")
        self.assertAlmostEqual(p0[0], 94.4, places=6)
        self.assertEqual(p0[1], 0.0)
        for got, want in ((p1[0] - p0[0], 8.96), (p2[0] - p0[0], 13.44), (p3[0] - p0[0], 16.86), (p3[1], 1.74)):
            self.assertAlmostEqual(got, want, delta=0.005)
        kind, centre, radius, start, sweep = top_right[1]
        self.assertEqual((kind, radius), ("arc", 16.0))
        self.assertEqual(centre, (104.0, 16.0), "the arc is the circle of radius 16 a circular corner would draw")
        end = (centre[0] + radius * math.cos(math.radians(start + sweep)),
               centre[1] + radius * math.sin(math.radians(start + sweep)))
        self.assertAlmostEqual(end[0] - p3[0], 6.99, delta=0.005)
        self.assertAlmostEqual(end[1] - p3[1], 6.99, delta=0.005)
        self.assertEqual(top_right[2][-1], (120.0, 25.6), "and it ends 25.6 px down the side")

    def test_the_outline_is_continuous_and_tangent_at_every_joint(self):
        points = shape.flatten(shape.outline((3, 5, 203, 95), 16, 0.6), 64)
        steps = [math.hypot(x1 - x0, y1 - y0) for (x0, y0), (x1, y1) in zip(points, points[1:])]
        self.assertLess(max(steps), 200.5, "nothing jumps but the straight sides")
        for segment in shape.outline((3, 5, 203, 95), 16, 0.6):
            if segment[0] == "bezier":
                p0, p1, p2, p3 = segment[1:]
                # zero curvature at the side: the first two controls lie on the side with the start
                self.assertTrue(p0[0] == p1[0] == p2[0] or p0[1] == p1[1] == p2[1] or
                                p1[0] == p2[0] == p3[0] or p1[1] == p2[1] == p3[1], segment)


class BudgetTests(unittest.TestCase):
    def test_a_short_side_backs_the_smoothing_off(self):
        # (side, radius) -> smoothing drawn: the owner's 34 px control at 11 and a 34 x 26 caption button at 7.
        for box, radius, smoothing, p in (((34, 34), 11, 17 / 11 - 1, 17.0), ((34, 26), 7, 0.6, 11.2)):
            with self.subTest(box=box, radius=radius):
                found = shape.corner(radius, 0.6, min(box) / 2.0)
                self.assertAlmostEqual(found.smoothing, smoothing, places=9)
                self.assertAlmostEqual(found.p, p, places=9)
                self.assertLessEqual(found.p, min(box) / 2.0)
        self.assertAlmostEqual(shape.corner(11, 0.6, 17).smoothing, 0.545, places=3)

    def test_the_radii_are_unchanged(self):
        self.assertEqual({role: brand.RADII[role] for role in ("card", "control", "small")},
                         {"card": 16, "control": 11, "small": 7})

    def test_a_pill_stays_a_pill(self):
        for height in (20, 22, 34):
            with self.subTest(height=height):
                found = shape.corner(height / 2.0, 0.6, height / 2.0)
                self.assertFalse(shape.smoothed(found))
                segments = shape.outline((0, 0, 140, height), height / 2.0, 0.6)
                self.assertEqual([segment[0] for segment in segments], ["arc"] * 4)
                self.assertEqual([segment[4] for segment in segments], [90.0] * 4)

    def test_a_ring_drawn_round_a_circle_stays_a_circle(self):
        # the popup's rings: stroke_round(circle box, radius = half) (renderer.py)
        segments = shape.outline((10, 10, 30, 30), 10, 0.6)
        self.assertEqual([segment[0] for segment in segments], ["arc"] * 4)

    def test_no_smoothing_is_the_circle_exactly(self):
        for segment, start in zip(shape.outline((0, 0, 100, 60), 16, 0.0), (180.0, 270.0, 0.0, 90.0)):
            self.assertEqual(segment[0], "arc")
            self.assertEqual((segment[2], segment[3], segment[4]), (16.0, start, 90.0))

    def test_a_box_under_a_pixel_is_its_rectangle(self):
        self.assertEqual(shape.outline((0, 0, 1, 1), 16, 0.6), [])

    def test_corners_not_named_are_their_vertex(self):
        segments = shape.outline((0, 0, 100, 60), 16, 0.6, corners=("top_right", "bottom_right"))
        self.assertEqual(segments[0], ("point", (0.0, 0.0)))
        self.assertEqual(segments[-1], ("point", (0.0, 60.0)))
        self.assertEqual([segment[0] for segment in segments[1:-1]], ["bezier", "arc", "bezier"] * 2)


class InsideTests(unittest.TestCase):
    CASES = ((0, 0, 120, 80, 16), (0, 0, 60, 34, 11), (2, 3, 300, 400, 48), (0, 0, 46, 40, 11))

    def test_inside_is_the_outline_drawn(self):
        rng = random.Random(624)
        for left, top, right, bottom, radius in self.CASES:
            points = shape.flatten(shape.outline((left, top, right, bottom), radius, 0.6), 48)
            p = shape.corner(radius, 0.6, min(right - left, bottom - top) / 2.0).p
            checked = 0
            for _ in range(1200):
                # in the corner boxes, where the two can differ
                x = left + rng.uniform(-1, p + 1)
                y = top + rng.uniform(-1, p + 1)
                if rng.random() < 0.5:
                    x = right - (x - left)
                if rng.random() < 0.5:
                    y = bottom - (y - top)
                near = min(_to_segment(x, y, a, b) for a, b in zip(points, points[1:] + points[:1]))
                if near < 0.01:
                    continue
                checked += 1
                with self.subTest(case=(left, top, right, bottom, radius), x=x, y=y):
                    self.assertEqual(shape.inside(x, y, (left, top, right, bottom), radius, 0.6),
                                     _polygon_inside(x, y, points))
            self.assertGreater(checked, 900)

    def test_a_point_inside_the_circles_corner_but_outside_the_squircles(self):
        box = (0, 0, 240, 160)                   # a card at 200 %
        self.assertTrue(shape.inside(28, 0.45, box, 32, 0.0), "the circle has nearly reached the side 28 px in")
        self.assertFalse(shape.inside(28, 0.45, box, 32, 0.6), "the squircle is still easing in")
        self.assertTrue(shape.inside(52, 0.05, box, 32, 0.6), "and past 51.2 px it is the side")

    def test_distance_is_the_circles_exactly_without_smoothing(self):
        for x, y in ((50, 30), (58, 38), (40, 39.5), (59.9, 0)):
            qx, qy = abs(x) - (60 - 16), abs(y) - (40 - 16)
            want = math.hypot(qx, qy) - 16 if qx > 0 and qy > 0 else max(qx, qy) - 16
            self.assertEqual(shape.distance(x, y, 60, 40, 16, 0.0), want)

    def test_distance_says_inside_and_how_far_near_the_outline(self):
        hw, hh, radius = 100.0, 70.0, 22.0
        box = (-hw, -hh, hw, hh)
        p = shape.corner(radius, 0.6, hh).p
        top_right = shape.outline(box, radius, 0.6)[3:6]
        points = [(hw - p - 10, -hh)] + shape.flatten(top_right, 96) + [(hw, -hh + p + 10)]
        worst = 0.0
        for i in range(0, 160, 2):
            for j in range(0, 160, 2):
                x, y = hw - 36 + i / 4.0 + 0.11, -(hh - 36 + j / 4.0 + 0.07)
                true = min(_to_segment(x, y, a, b) for a, b in zip(points, points[1:]))
                if true > 2.0:
                    continue
                inside = shape.inside(x, y, box, radius, 0.6)
                got = shape.distance(x, y, hw, hh, radius, 0.6)
                worst = max(worst, abs(got - (-true if inside else true)))
        self.assertLess(worst, 0.06, "within two pixels of the outline, where a pixel's coverage is decided")


if __name__ == "__main__":
    unittest.main()
