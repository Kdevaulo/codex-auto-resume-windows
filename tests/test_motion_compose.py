"""Laying one frame of the README's motion together (build/motion_compose.py): the window in the frame of its still,
its shadow, the taskbar strip and icon, and the pointer and its click drawn by us. Pure Python on tiny canvases."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import motion_compose as compose  # noqa: E402
import motion_plan  # noqa: E402

GROUND = (240, 242, 245)


def canvas(width, height, colour=GROUND):
    return bytearray(bytes(colour) * (width * height))


def pixel(picture, width, x, y):
    return tuple(picture[(y * width + x) * 3:(y * width + x) * 3 + 3])


class PointerTests(unittest.TestCase):
    def test_the_arrow_is_white_inside_a_dark_edge_and_clear_round_it(self):
        width, height, pixels = compose.arrow_sprite(1.5)
        tip = pixels[1 * width + 1]
        self.assertGreater(tip[3], 100, "the tip is drawn")
        self.assertLess(sum(tip[:3]), 3 * 128, "the tip is the edge's dark")
        inside = pixels[int(1 + 12 * 1.5) * width + int(1 + 3 * 1.5)]
        self.assertEqual(inside, (255, 255, 255, 255))
        self.assertEqual(pixels[1 * width + width - 1][3], 0)
        self.assertEqual(compose.arrow_sprite(1.5), (width, height, pixels), "the same arrow every time")
        pressed = compose.arrow_sprite(1.5, pressed=True)[2]
        self.assertEqual(pressed[int(1 + 12 * 1.5) * width + int(1 + 3 * 1.5)][:3], compose.ARROW_PRESSED)

    def test_the_pointer_stands_with_its_tip_where_it_is_told(self):
        picture = canvas(60, 60)
        compose.draw_pointer(picture, 60, 60, 20, 10)
        self.assertEqual(pixel(picture, 60, 20 + 4, 10 + 18), (255, 255, 255))
        self.assertEqual(pixel(picture, 60, 15, 5), GROUND, "nothing above and left of the tip")
        self.assertEqual(pixel(picture, 60, 50, 50), GROUND)

    def test_the_ripple_spreads_and_fades_on_the_brand_s_curve(self):
        frame = motion_plan.Frame(0, "A", (), (), ("at", "save"), ("save", 0))
        accent = (0, 0, 200)
        rings = {}
        for age in (0, 120, 239):
            spread_opacity = motion_plan.ripple_at(frame._replace(t=age))
            picture = canvas(80, 80)
            compose.draw_pointer(picture, 80, 80, 40, 40, ripple=spread_opacity, accent=accent)
            rings[age] = (spread_opacity, picture)
        self.assertEqual(rings[0][0], (0.0, 1.0))
        spread, opacity = rings[120][0]
        self.assertAlmostEqual(spread, motion_plan.ease(0.5))
        self.assertAlmostEqual(opacity, 1.0 - motion_plan.ease(0.5))
        radius = int(round(compose.RIPPLE_RADIUS * spread))
        left_of_tip = pixel(rings[120][1], 80, 40 - radius, 40)
        self.assertLess(left_of_tip[0], GROUND[0], "the ring is tinted with the accent where it has spread to")
        self.assertEqual(pixel(rings[120][1], 80, 40 - radius // 2 - 1, 40), GROUND, "it is a ring, not a disc")
        late = pixel(rings[239][1], 80, 40 - int(round(compose.RIPPLE_RADIUS * motion_plan.ease(239 / 240.0))), 40)
        self.assertGreater(late[0], left_of_tip[0], "it fades as it spreads")
        self.assertIsNone(motion_plan.ripple_at(frame._replace(t=240)))


class WindowTests(unittest.TestCase):
    def still(self):
        """A window picture 8 wide and 6 tall: 2 caption rows of (100, 0, 0) and its four corners clear."""
        width, height = 8, 6
        rgb = bytearray()
        for y in range(height):
            rgb += bytes((100, 0, 0) if y < 2 else (9, 9, 9)) * width
        alpha = bytearray(b"\xff" * (width * height))
        for x, y in ((0, 0), (7, 0), (0, 5), (7, 5)):
            alpha[y * width + x] = 0
        alpha[5 * width + 1] = 128
        return width, height, bytes(rgb), bytes(alpha)

    def test_the_client_area_is_laid_in_the_still_s_frame_and_corners(self):
        chrome = compose.WindowChrome(self.still(), (8, 4), size=(40, 30), at=(10, 5), ground=GROUND, scale=1.0)
        self.assertEqual(chrome.client_origin(), (10, 7))
        client = bytes((0, 200, 0)) * 32
        picture = chrome.frame(client)
        self.assertEqual(pixel(picture, 40, 11, 5), (100, 0, 0), "the caption is the still's")
        self.assertEqual(pixel(picture, 40, 12, 8), (0, 200, 0), "the client area is the frame's")
        self.assertEqual(pixel(picture, 40, 10, 10), pixel(chrome.base, 40, 10, 10), "a clear corner shows what is under it")
        half, under = pixel(picture, 40, 11, 10), pixel(chrome.base, 40, 11, 10)
        self.assertEqual(half[1], (200 * 128 + under[1] * 127 + 127) // 255,
                         "a corner pixel half covered is half the client's, over what is under it")

    def test_the_shadow_falls_under_the_window_and_fades_away_from_it(self):
        chrome = compose.WindowChrome(self.still(), (8, 4), size=(100, 100), at=(10, 5), ground=GROUND, scale=1.0)
        below = pixel(chrome.base, 100, 14, 12)
        further = pixel(chrome.base, 100, 14, 20)
        self.assertLess(below[0], GROUND[0])
        self.assertLessEqual(below[0], further[0])
        self.assertEqual(pixel(chrome.base, 100, 99, 99), GROUND, "it is gone well away from the window")

    def test_on_a_clear_canvas_only_the_window_and_its_shadow_are_not_transparent(self):
        chrome = compose.WindowChrome(self.still(), (8, 4), size=(100, 100), at=(40, 30), ground=None, scale=1.0)
        picture = chrome.frame(bytes((0, 200, 0)) * 32)
        self.assertEqual(len(picture), 100 * 100 * 4, "RGBA")

        def at(x, y):
            return tuple(picture[(y * 100 + x) * 4:(y * 100 + x) * 4 + 4])
        self.assertEqual(at(0, 0), (0, 0, 0, 0), "nothing painted outside the window: wholly transparent")
        self.assertEqual(at(99, 99), (0, 0, 0, 0))
        self.assertEqual(at(41, 30), (100, 0, 0, 255), "the caption, opaque")
        self.assertEqual(at(42, 33), (0, 200, 0, 255), "the client area, opaque")
        shadow = at(44, 40)
        self.assertEqual(shadow[:3], (0, 0, 0))
        self.assertTrue(0 < shadow[3] < 255, "the shadow is laid with its alpha")
        corner = at(41, 35)
        self.assertTrue(corner[3] < 255 and corner[1] > 0, "a corner Windows rounds is partly clear")
        outside = sum(1 for x in range(100) for y in range(100)
                      if at(x, y)[3] and not (10 <= x < 78 and 0 <= y < 76))
        self.assertEqual(outside, 0, "nothing beyond the shadow's reach")

    def test_the_pointer_on_a_clear_canvas_keeps_its_own_colour_and_coverage(self):
        picture = bytearray(60 * 60 * 4)
        compose.draw_pointer(picture, 60, 60, 20, 10)
        inside = picture[((10 + 18) * 60 + 24) * 4:((10 + 18) * 60 + 24) * 4 + 4]
        self.assertEqual(tuple(inside), (255, 255, 255, 255))
        self.assertEqual(tuple(picture[0:4]), (0, 0, 0, 0))

    def test_a_still_of_another_window_is_refused(self):
        with self.assertRaises(ValueError):
            compose.WindowChrome(self.still(), (9, 4), size=(40, 30), at=(0, 0), ground=GROUND)


class TaskbarTests(unittest.TestCase):
    def test_the_strip_is_one_colour_and_the_icon_lies_on_it_with_its_alpha(self):
        picture = canvas(10, 10)
        compose.draw_strip(picture, 10, 10, 6, 4, (238, 240, 243))
        self.assertEqual(pixel(picture, 10, 0, 6), (238, 240, 243))
        self.assertEqual(pixel(picture, 10, 0, 5), GROUND)
        icon = bytes((0, 0, 255, 255)) + bytes((0, 0, 255, 0)) + bytes((255, 0, 0, 128)) + bytes((0, 0, 0, 0))
        compose.draw_icon(picture, 10, 10, icon, 2, 3, 7)
        self.assertEqual(pixel(picture, 10, 3, 7), (255, 0, 0))
        self.assertEqual(pixel(picture, 10, 4, 7), (238, 240, 243))
        self.assertEqual(pixel(picture, 10, 3, 8), ((238 * 127 + 127) // 255, (240 * 127 + 127) // 255,
                                                    (255 * 128 + 243 * 127 + 127) // 255))


class LocateTests(unittest.TestCase):
    class Card:
        def button(self, verb):
            return {"open": (100, 200, 140, 220)}[verb]

    def test_a_target_is_the_centre_of_what_the_window_or_the_card_says(self):
        bounds = {"save": [10, 20, 30, 40]}
        self.assertEqual(compose.locate("save", bounds, (5, 7)), (5 + 25.0, 7 + 40.0))
        self.assertEqual(compose.locate("card.open", bounds, (5, 7), self.Card()), (120.0, 210.0))
        self.assertEqual(compose.locate({"at": [3, 4]}, bounds, (5, 7)), (3.0, 4.0))
        moved = motion_plan._frozen({"by": [-60, 2], "from": "save"})
        self.assertEqual(compose.locate(moved, bounds, (5, 7)), (5 + 25.0 - 60, 7 + 40.0 + 2))
        with self.assertRaises(KeyError):
            compose.locate("page.history", bounds, (0, 0))

    def test_a_moving_pointer_is_its_eased_fraction_of_the_way(self):
        frame = motion_plan.Frame(0, "A", (), (), ("move", (("at", (0, 0)),), "save", 0.25), ())
        self.assertEqual(compose.pointer_at(frame, {"save": [96, 46, 8, 8]}, (0, 0)), (25.0, 12.5))


if __name__ == "__main__":
    unittest.main()
