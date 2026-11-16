"""v0.6.24: every mask follows the squircle - shadows, wells, the card's cut - in the window and in Python.

Until v0.6.24 nothing blurred a path: the window's Elevation covered each pixel by an analytic distance to a
circular-cornered box and blurred that, the popup's masks took an erfc of the same circular distance, and the
notification card cut its corners by a circle. So a squircle drawn by GDI+ would have stood on a circle's shadow.
Held here: each mask against the squircle itself (brute force, to the flattened outline), and a pixel inside the
circle's corner but outside the squircle's, which a circular mask gets wrong by far more than the tolerance.
"""
from __future__ import annotations

import math
import types
import unittest
from pathlib import Path

import squircleprobe
from codex_auto_resume import brand, notice_card
from codex_auto_resume.brand import shape
from codex_auto_resume.ui.popup import elevation

ROOT = Path(__file__).resolve().parent.parent


def _to_segment(x, y, a, b) -> float:
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length))
    return math.hypot(x - ax - t * dx, y - ay - t * dy)


class _TrueDistance:
    """Signed distance to the top-right corner of a box centred on the origin, by brute force: the corner's
    flattened outline with a length of each side beside it. Valid in that corner's quarter."""

    def __init__(self, half_w, half_h, radius, smoothing):
        box = (-half_w, -half_h, half_w, half_h)
        found = shape.corner(radius, smoothing, min(half_w, half_h))
        segments = shape.outline(box, radius, smoothing)
        corner = segments[3:6] if shape.smoothed(found) else segments[1:2]
        far = 2.0 * (half_w + half_h)
        self.points = [(half_w - found.p - far, -half_h)] + shape.flatten(corner, 48) + [(half_w, -half_h + found.p + far)]
        self.box, self.radius, self.smoothing = box, radius, smoothing

    def __call__(self, x, y) -> float:
        near = min(_to_segment(x, y, a, b) for a, b in zip(self.points, self.points[1:]))
        return -near if shape.inside(x, y, self.box, self.radius, self.smoothing) else near


def _stamped(case, smoothing) -> list:
    """One shadow as the window stamps it, worked out the long way: the body's sixteen-sample coverage, moved by the
    shadow's offset, blurred by the Gaussian integrated over each pixel, times the shadow's alpha."""
    theme, design, recipe, index, scale, margin, width, height, radius = case
    shadow = brand.SHADOWS[theme][recipe][index]
    sigma = shadow.blur * scale / 2.0
    across, down = width + 2 * margin, height + 2 * margin
    sx, sy = shadow.dx * scale, shadow.dy * scale
    box = (margin + sx, margin + sy, margin + sx + width, margin + sy + height)
    p = shape.corner(radius, smoothing, min(width, height) / 2.0).p
    grid = []
    for y in range(down):
        for x in range(across):
            cx, cy = x + 0.5, y + 0.5
            if cx < box[0] - 1 or cx > box[2] + 1 or cy < box[1] - 1 or cy > box[3] + 1:
                grid.append(0.0)
            elif (box[0] + 1 < cx < box[2] - 1 and box[1] + 1 < cy < box[3] - 1
                  and (box[0] + p + 1 < cx < box[2] - p - 1 or box[1] + p + 1 < cy < box[3] - p - 1)):
                grid.append(1.0)
            else:
                grid.append(sum(1 for a in range(4) for b in range(4)
                                if shape.inside(x + (a + 0.5) / 4, y + (b + 0.5) / 4, box, radius, smoothing)) / 16.0)
    spread = int(math.ceil(3 * sigma - 1e-9))
    phi = lambda value: 0.5 * math.erfc(-value / math.sqrt(2.0))
    kernel = [phi((k + 0.5) / sigma) - phi((k - 0.5) / sigma) for k in range(-spread, spread + 1)]
    rows = []
    for y in range(down):
        row = grid[y * across:(y + 1) * across]
        rows.append([sum(kernel[k + spread] * row[x - k] for k in range(-spread, spread + 1) if 0 <= x - k < across)
                     for x in range(across)])
    out = [0.0] * (across * down)
    for x in range(across):
        for y in range(down):
            value = sum(kernel[k + spread] * rows[y - k][x] for k in range(-spread, spread + 1) if 0 <= y - k < down)
            out[y * across + x] = round(255 * round(shadow.alpha, 4) * max(0.0, min(1.0, value)))
    return out


def _level(distance, sigma) -> float:
    return 127.5 * math.erfc(distance / (sigma * math.sqrt(2.0)))


def _old_lift(width, height, radius, blur) -> bytes:
    """v0.6.23's lift, as it was: the circular distance's erfc."""
    core = 2 * int(math.ceil(radius)) + 1
    box_w, box_h = min(width, core), min(height, core)
    radius = max(0.0, min(radius, box_w / 2.0, box_h / 2.0))
    sigma = blur / 2.0
    extent = int(math.ceil(3 * sigma)) + 1
    image_w, image_h = box_w + 2 * extent, box_h + 2 * extent
    data = bytearray(image_w * image_h)
    for j in range(image_h):
        for i in range(image_w):
            qx = abs(i + 0.5 - image_w / 2.0) - (box_w / 2.0 - radius)
            qy = abs(j + 0.5 - image_h / 2.0) - (box_h / 2.0 - radius)
            d = math.hypot(qx, qy) - radius if qx > 0 and qy > 0 else max(qx, qy) - radius
            data[j * image_w + i] = int(0.5 * math.erfc(d / (sigma * math.sqrt(2.0))) * 255 + 0.5)
    return bytes(data)


class LiftTests(unittest.TestCase):
    """The popup's and the card's outer shadows (ui/popup/elevation.lift_coverage)."""

    # light's card and tile lifts, and dark's control drop - the tightest blur there is (brand.SHADOWS)
    CASES = (("card", (336, 400), brand.RADII["card"], 14), ("control", (148, 44), brand.RADII["control"], 6),
             ("control dark", (90, 80), brand.RADII["control"], 2))

    def worst(self, mask, width, height, radius, blur, smoothing):
        """The mask's largest difference from the squircle blurred, in levels, over its top-right corner."""
        sigma, extent = blur / 2.0, mask["extent"]
        box_w, box_h = mask["width"] - 2 * extent, mask["height"] - 2 * extent
        truth = _TrueDistance(box_w / 2.0, box_h / 2.0, radius, smoothing)
        p = shape.corner(radius, smoothing, min(box_w, box_h) / 2.0).p
        worst = 0.0
        for j in range(0, mask["height"] // 2, 2):
            for i in range(mask["width"] // 2 + 1, mask["width"], 2):
                x, y = i + 0.5 - mask["width"] / 2.0, j + 0.5 - mask["height"] / 2.0
                if x < box_w / 2.0 - p - 1 or -y < box_h / 2.0 - p - 1:
                    continue
                want = _level(truth(x, y), sigma)
                worst = max(worst, abs(mask["coverage"][j * mask["width"] + i] - want))
        return worst

    def test_a_lift_is_the_squircle_blurred_within_two_and_a_half_levels(self):
        for recipe, body, radius, blur in self.CASES:
            for scale in (1.0, 1.5, 2.0):
                width, height = round(body[0] * scale), round(body[1] * scale)
                elevation._MASKS.clear()
                mask = elevation.lift_coverage(width, height, radius * scale, blur * scale)
                with self.subTest(recipe=recipe, scale=scale):
                    self.assertLessEqual(self.worst(mask, width, height, radius * scale, blur * scale, 0.6), 2.5)

    def test_a_circles_lift_is_not_the_squircles(self):
        """What the test above would see if the masks went back to the circle: at 60 % the squircle leaves the
        circle by under half a pixel at 200 %, which a wide blur hides, so dark's two-pixel drop shows it."""
        width, height, radius, blur = 180, 160, 22.0, 4.0          # dark's control drop at 200 %
        elevation._MASKS.clear()
        mask = elevation.lift_coverage(width, height, radius, blur)
        box_w, box_h = mask["width"] - 2 * mask["extent"], mask["height"] - 2 * mask["extent"]
        round_one = _TrueDistance(box_w / 2.0, box_h / 2.0, radius, 0.0)
        coverage = bytearray(mask["width"] * mask["height"])
        for j in range(mask["height"] // 2):
            for i in range(mask["width"] // 2, mask["width"]):
                x, y = i + 0.5 - mask["width"] / 2.0, j + 0.5 - mask["height"] / 2.0
                coverage[j * mask["width"] + i] = int(_level(round_one(x, y), blur / 2.0) + 0.5)
        circle = dict(mask, coverage=bytes(coverage))
        self.assertGreater(self.worst(circle, width, height, radius, blur, 0.6), 5.0)

    def test_without_smoothing_a_lift_is_v0623s_byte_for_byte(self):
        for args in ((336, 400, 16, 14), (148, 32, 11, 6), (40, 40, 20, 12)):
            elevation._MASKS.clear()
            with self.subTest(args=args):
                self.assertEqual(elevation.lift_coverage(*args, 0.0)["coverage"], _old_lift(*args))

    def test_a_mask_is_kept_by_its_box_and_its_smoothing(self):
        elevation._MASKS.clear()
        soft = elevation.lift_coverage(336, 400, 16, 14)
        self.assertIs(elevation.lift_coverage(336, 520, 16, 14), soft, "a taller card finds it")
        self.assertIsNot(elevation.lift_coverage(336, 400, 16, 14, 0.0), soft, "a circle's is its own")
        p = shape.corner(16, 0.6, 200).p
        self.assertEqual(soft["width"] - 2 * soft["extent"], 2 * int(math.ceil(p)) + 1,
                         "two corners as the squircle measures them, and one straight pixel")


class WellTests(unittest.TestCase):
    """A well (ui/popup/elevation.well_coverage): an inset shadow cut to the squircle."""

    WELLS = ((146, 48, 10, 6, 2, 2), (292, 96, 20, 12, 4, 4), (219, 72, 15, 9, -3, -3))

    @staticmethod
    def reference(box_w, box_h, radius, blur, dx, dy, smoothing) -> dict:
        """Each pixel of a box's top-right corner, as the cut to the outline and the moved outline blurred: by
        index into the mask, in levels."""
        sigma = blur / 2.0
        cut = _TrueDistance(box_w / 2.0, box_h / 2.0, radius, smoothing)
        p = shape.corner(radius, 0.6, min(box_w, box_h) / 2.0).p
        found = {}
        for j in range(0, box_h // 2):
            for i in range(box_w // 2 + 1, box_w):
                x, y = i + 0.5 - box_w / 2.0, j + 0.5 - box_h / 2.0
                if x < box_w / 2.0 - p - 1 or -y < box_h / 2.0 - p - 1:
                    continue
                inside = max(0.0, min(1.0, 0.5 - cut(x, y)))
                hole = _level(cut(x - dx, y - dy), sigma) if inside > 0 else 255.0
                found[j * box_w + i] = (255.0 - hole) * inside
        return found

    def test_the_cut_is_the_squircle_and_the_shadow_within_three_and_a_half_levels(self):
        # The cut is a pixel's 0.5 - d, as v0.6.5's was: a hundredth of a pixel of distance is two and a half levels
        # there, so a well is held a level looser than a lift.
        for width, height, radius, blur, dx, dy in self.WELLS:
            elevation._MASKS.clear()
            mask = elevation.well_coverage(width, height, radius, blur, dx, dy)
            want = self.reference(mask["width"], mask["height"], radius, blur, dx, dy, 0.6)
            worst = max(abs(mask["coverage"][index] - value) for index, value in want.items())
            with self.subTest(well=(width, height, radius, blur, dx, dy)):
                self.assertLessEqual(worst, 3.5)

    def test_a_circles_well_is_not_the_squircles(self):
        """What the test above would see if the well went back to the circle."""
        width, height, radius, blur, dx, dy = self.WELLS[1]           # a pressed button at 200 %
        mask = elevation.well_coverage(width, height, radius, blur, dx, dy)
        squircle = self.reference(mask["width"], mask["height"], radius, blur, dx, dy, 0.6)
        circle = self.reference(mask["width"], mask["height"], radius, blur, dx, dy, 0.0)
        self.assertGreater(max(abs(circle[index] - squircle[index]) for index in squircle), 10.0)

    def test_a_wells_light_is_its_shade_turned_round(self):
        elevation._MASKS.clear()
        light = elevation.well_coverage(146, 48, 10, 6, -2, -2)["coverage"]
        elevation._MASKS.clear()
        self.assertEqual(light, elevation.well_coverage(146, 48, 10, 6, 2, 2)["coverage"][::-1])


class CardCutTests(unittest.TestCase):
    """The notification card's own corner, a layered window's alpha (notice_card.corner_coverage)."""

    def test_each_pixel_is_its_sixteen_samples_of_the_squircle(self):
        for radius in (16, 24, 32):
            rows = notice_card.corner_coverage(radius)
            made = shape.profile(radius, 0.6, 1e9)
            self.assertEqual(len(rows), int(math.ceil(made.p)), "as long as the corner")
            for j, row in enumerate(rows):
                for i, value in enumerate(row):
                    count = sum(1 for sy in range(4) for sx in range(4)
                                if shape.inside_corner(made, i + (sx + 0.5) / 4.0, j + (sy + 0.5) / 4.0))
                    with self.subTest(radius=radius, i=i, j=j):
                        self.assertEqual(value, (count * 255 + 8) // 16)

    def test_inside_the_circle_but_outside_the_squircle_is_cut_away(self):
        rows = notice_card.corner_coverage(32)                       # a card at 200 %
        circle = notice_card.corner_coverage(32, 0.0)
        # at 60 % the squircle leaves the circle by under half a pixel here, so by a share of a pixel
        cut = [(i, j) for j in range(len(circle)) for i in range(len(circle[j])) if circle[j][i] - rows[j][i] >= 48]
        self.assertGreater(len(cut), 10, "the circle would have kept more of them")

    def test_without_smoothing_the_cut_is_the_circle_byte_for_byte(self):
        radius = 24
        size = int(math.ceil(radius))
        want = []
        for j in range(size):
            row = bytearray(size)
            for i in range(size):
                distance = math.hypot(radius - (i + 0.5), radius - (j + 0.5)) - radius
                if i + 0.5 >= radius or j + 0.5 >= radius:
                    distance = -1.0
                row[i] = int(round(min(1.0, max(0.0, 0.5 - distance)) * 255))
            want.append(bytes(row))
        self.assertEqual(notice_card.corner_coverage(radius, 0.0), tuple(want))

    def test_premultiply_cuts_the_squircle(self):
        width, height, radius = 120, 90, 32
        pixels = notice_card.premultiply(b"\xff" * (width * height * 4), width, height, radius)
        rows = notice_card.corner_coverage(radius)
        for j in range(len(rows)):
            for i in range(len(rows)):
                self.assertEqual(pixels[(j * width + (width - 1 - i)) * 4 + 3], rows[j][i])
        plain = notice_card.premultiply(b"\xff" * (width * height * 4), width, height, radius, smoothing=0.0)
        self.assertNotEqual(pixels, plain)

    def test_the_card_takes_its_designs_smoothing(self):
        from codex_auto_resume.ui.card import card
        smoothing = card.Card.smoothing.fget
        self.assertEqual(smoothing(types.SimpleNamespace(contrast=False, design="soft")), 0.6)
        self.assertEqual(smoothing(types.SimpleNamespace(contrast=False, design="classic")), 0.0)
        self.assertEqual(smoothing(types.SimpleNamespace(contrast=False, design="plain")), 0.0)
        self.assertEqual(smoothing(types.SimpleNamespace(contrast=True, design="plain")), 0.6, "Soft's in High Contrast")
        source = (ROOT / "src" / "codex_auto_resume" / "ui" / "card" / "card.py").read_text(encoding="utf-8")
        self.assertIn("self.renderer.canvas.smoothing = self.smoothing", source)
        self.assertIn("width, height, self.radius, smoothing=self.smoothing)", source)
        self.assertIn("width, height, self.radius, top, self.smoothing)", source)
        self.assertIn("popup.lift_coverage(width, height, radius, shadow.blur * self.scale, self.smoothing)", source)


@unittest.skipUnless(squircleprobe.available(), "needs the in-box C# compiler")
class WindowTests(unittest.TestCase):
    """The window's Elevation, through its own compiled code: its coverage and a stamped shadow."""

    @classmethod
    def setUpClass(cls):
        cls.covers = ((120, 90, 0.0, 0.0, 120.0, 90.0, 32.0, 0.6), (70, 56, 3.0, 4.0, 64.0, 48.0, 16.0, 0.6),
                      (120, 90, 0.0, 0.0, 120.0, 90.0, 32.0, 0.0))
        lines = ["cover %d %d %r %r %r %r %r %r" % case for case in cls.covers]
        # dark's control drop (0, 1, 2) at 200 % round a 90 x 80 body, and light's tile lift at 200 %
        cls.stamps = (("dark", "soft", "control", 0, 2.0, 20, 90, 80, 22.0), ("light", "soft", "control", 0, 2.0, 24, 96, 80, 22.0),
                      ("light", "classic", "control", 0, 2.0, 24, 96, 80, 14.0))
        lines += ["stamp %s %s %s %d %r %d %d %d %r" % case for case in cls.stamps]
        cls.answers = squircleprobe.ask(lines)

    def test_coverage_is_sixteen_samples_of_the_squircle(self):
        for case, grid in zip(self.covers, self.answers):
            across, down, left, top, width, height, radius, smoothing = case
            box = (left, top, left + width, top + height)
            worst, circle_worst = 0.0, 0.0
            for y in range(down):
                for x in range(across):
                    hits = sum(1 for sy in range(4) for sx in range(4)
                               if shape.inside(x + (sx + 0.5) / 4, y + (sy + 0.5) / 4, box, radius, smoothing))
                    rounds = sum(1 for sy in range(4) for sx in range(4)
                                 if shape.inside(x + (sx + 0.5) / 4, y + (sy + 0.5) / 4, box, radius, 0.0))
                    worst = max(worst, abs(grid[y * across + x] - hits / 16.0))
                    circle_worst = max(circle_worst, abs(grid[y * across + x] - rounds / 16.0))
            with self.subTest(case=case):
                self.assertLessEqual(worst, 1 / 16.0 + 1e-9, "a sample on the outline itself may fall either way")
                if radius >= 32 and smoothing:
                    self.assertGreaterEqual(circle_worst, 0.25, "and it is not the circle's")

    def test_a_stamped_shadow_is_the_squircle_blurred(self):
        for case, alpha in zip(self.stamps, self.answers[len(self.covers):]):
            theme, design, recipe, index, scale, margin, width, height, radius = case
            shadow = brand.SHADOWS[theme][recipe][index]
            smoothing = shape.design_smoothing(design)
            want = _stamped(case, smoothing)
            # Outside the body and in its corners: under the body's middle the window stamps nothing (StampOne).
            across, p = width + 2 * margin, shape.corner(radius, smoothing, min(width, height) / 2.0).p + 2
            seen = [k for k in range(len(alpha))
                    if not (margin <= k % across < margin + width and margin <= k // across < margin + height)
                    or (min(k % across - margin, margin + width - 1 - k % across) < p
                        and min(k // across - margin, margin + height - 1 - k // across) < p)]
            worst = max(abs(alpha[k] - want[k]) for k in seen)
            with self.subTest(case=case):
                self.assertLessEqual(worst, 1.5)
            if theme == "dark":
                circle = _stamped(case, 0.0)
                self.assertGreater(max(abs(a - b) for a, b in zip(circle, want)), 4.0,
                                   "the circle's would be told from it")


class GdiPlusTests(unittest.TestCase):
    """What the popup and its menus fill (ui/popup/gdiplus): GDI+'s own path, drawn offscreen."""

    def test_a_filled_body_is_the_squircle(self):
        import sys
        if sys.platform != "win32":
            self.skipTest("GDI+ is Windows'")
        from codex_auto_resume.ui import popup
        popup._declare()
        popup._gdiplus_acquire()
        try:
            canvas = popup._Canvas()
            self.assertIsNone(canvas.smoothing, "a canvas is Soft's until its owner says otherwise")
            try:
                canvas.ensure(240, 160)
                drawn = {}
                for smoothing in (0.6, 0.0):
                    canvas.smoothing = smoothing
                    with popup._Painter(canvas) as paint:
                        paint.fill_round((0, 0, 240, 160), 0, 0xFF000000)
                        paint.fill_round((0, 0, 240, 160), 32, 0xFFFFFFFF)
                    data = canvas.pixels()
                    drawn[smoothing] = [data[(j * 240 + i) * 4] for j in range(52) for i in range(52)]
            finally:
                canvas.close()
        finally:
            popup._gdiplus_release()
        squircle, circle = drawn[0.6], drawn[0.0]
        made = shape.profile(32, 0.6, 80)
        worst = 0
        for j in range(52):
            for i in range(52):
                count = sum(1 for sy in range(4) for sx in range(4)
                            if shape.inside_corner(made, i + (sx + 0.5) / 4.0, j + (sy + 0.5) / 4.0))
                worst = max(worst, abs(squircle[j * 52 + i] - count * 255 / 16.0))
        self.assertLess(worst, 112, "GDI+'s own antialiasing against sixteen samples")
        self.assertTrue(any(c - s >= 48 for c, s in zip(circle, squircle)), "and is not the circle")


if __name__ == "__main__":
    unittest.main()
