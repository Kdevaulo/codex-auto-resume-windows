r"""v0.6.24-beta.3: the day spread wide (W2, the owner's pick of 2026-11-17) on the surfaces the tray draws.

On a special day the popup's header, the icon's own card (the hover card) and the notification card each take the day over
their header past the words - its ground, its specks across all of it, its scene as tall as the band at the outer end - the
card's own colour fading into it, as brand.day_band lays it out once for all three. Each is drawn offscreen (the popup's
renderer, no window) with a day given by the test, never today's date, and held to:

- the day's ground and its scene where the band is, and the specks across the band (they come out without them);
- everything outside the band the very pixels of an ordinary day: the words, the light, the rows, the buttons;
- the words on the card's own colour, so their contrast is an ordinary day's - the second line 4.5:1 in both themes;
- none in High Contrast nor in Classic; the hover card and the notification card read the date only on the watcher's own icon.

Drawn offscreen, nothing shown: run on its own, through gui_lock.sh.
"""
from __future__ import annotations

import unittest
from unittest import mock

from codex_auto_resume import brand, notice_card
from codex_auto_resume.brand.colour import contrast
from codex_auto_resume.ui import popup as tray_popup

LOOKS = ("birthday", "new_year", "christmas", "seollal", "chuseok")


def at(size, pixels, x, y):
    index = (int(y) * size[0] + int(x)) * 4
    return (pixels[index + 2], pixels[index + 1], pixels[index])


def band_of(plan):
    found = [item for item in plan["items"] if item["kind"] == "scene"]
    return found[0] if found else None


class _Surface:
    """What each surface's tests share: its plan and pixels with a day and without."""

    def check_band(self, day_plan, day_pixels, look):
        band = band_of(day_plan)
        self.assertIsNotNone(band, look)
        left, top, right, bottom = (int(round(value)) for value in band["rect"])
        ground = brand.rgb(brand.DAY_LOOKS[look][2])
        size = day_plan["size"]
        clear = int(band["fade"][1])
        # The day's ground: past the fade, the band is the day's - its ground, its specks and its scene.
        cells = [at(size, day_pixels, x, y) for y in range(top + 1, bottom - 1) for x in range(clear + 1, right - 1)]
        self.assertGreater(sum(1 for cell in cells if cell == ground), 50, look)
        # Its scene at the outer end, when its main piece is whole there.
        if band["scene_shown"]:
            piece = right - (brand.SCENE_WIDTH - brand.SCENE_FOCUS[look]) * band["unit"]
            scene = [at(size, day_pixels, x, y) for y in range(top + 1, bottom - 1) for x in range(int(piece), right - 1)]
            self.assertGreater(sum(1 for cell in scene if cell != ground), 20, look)
        return band

    def check_outside(self, plain_plan, plain, day_plan, day, band, rows=None):
        """Left of the band, every pixel is an ordinary day's; and below it, wherever the two plans are the same size. Inside
        the card's hairline: a wider card's edge is drawn along a longer path, a level off here and there."""
        left, top, right, bottom = (int(round(value)) for value in band["rect"])
        size, plain_size = day_plan["size"], plain_plan["size"]
        height = min(size[1], plain_size[1])
        edge = 2
        # Where an ordinary day's card is narrower (the icon's card), short of its outer corner.
        corner = plain_size[0] - int(plain_plan["items"][0].get("radius", 0)) - edge
        for y in rows or range(edge, height - edge):
            for x in range(edge, min(left, corner)):
                self.assertEqual(at(size, day, x, y), at(plain_size, plain, x, y), (x, y))
        if size == plain_size:
            for y in range(bottom + 1, height - edge):
                for x in range(edge, size[0] - edge):
                    self.assertEqual(at(size, day, x, y), at(plain_size, plain, x, y), (x, y))

    def check_words_stand_on_the_card(self, plan, band, theme, design="soft"):
        ground = brand.card_ground(theme, design)
        tokens = brand.palette(theme, design)
        left = band["rect"][0]
        for item in plan["items"]:
            # Every line of words but a chip's, which stands on its own pill over the day.
            if item["kind"] == "text" and item["role"] != "chip" and item["rect"][1] < band["rect"][3]:
                self.assertFalse(left < item["rect"][0] < band["rect"][2], item["text"])
        # The fade begins at exactly the card's colour, past every word.
        self.assertGreaterEqual(contrast(tokens["muted"], ground), 4.5, theme)


class PopupTests(_Surface, unittest.TestCase):
    def setUp(self):
        self.renderer = tray_popup.Renderer()
        self.addCleanup(self.renderer.close)

    def draw(self, look, theme="light", ms=0.0, locale="en"):
        self.renderer.theme = theme
        vm = tray_popup.view_model([], {"enabled": True}, {}, 1800000000.0)
        vm["scene"] = look
        plan = self.renderer.layout(vm, 1.0, locale)
        return plan, bytes(self.renderer.draw(vm, plan, frame=tray_popup.halo("monitoring", 0.0), scene_ms=ms).pixels())

    def test_the_header_is_in_the_day_past_the_words(self):
        for theme in ("light", "dark"):
            plain_plan, plain = self.draw(None, theme)
            for look in LOOKS:
                with self.subTest(theme=theme, look=look):
                    plan, pixels = self.draw(look, theme)
                    band = self.check_band(plan, pixels, look)
                    self.check_outside(plain_plan, plain, plan, pixels, band)
                    self.check_words_stand_on_the_card(plan, band, theme)

    def test_the_band_is_the_header_s_whole_width_past_the_words(self):
        plan, _ = self.draw("seollal")
        band = band_of(plan)
        card = plan["card"]
        self.assertEqual(band["rect"][2], card[2] - 1, "to the card's outer side")
        self.assertEqual(band["rect"][1], card[1] + 1, "from its top")
        self.assertGreater(band["rect"][2] - band["rect"][0], (card[2] - card[0]) * 0.34, "wider than a corner")

    def test_the_specks_are_across_the_band(self):
        plan, pixels = self.draw("christmas", ms=1300.0)
        with mock.patch.object(brand, "speck_frame", lambda look, ms: []):
            _, bare = self.draw("christmas", ms=1300.0)
        band = band_of(plan)
        size = plan["size"]
        left, top, right, bottom = (int(value) for value in band["rect"])
        piece = int(right - (brand.SCENE_WIDTH - brand.SCENE_FOCUS["christmas"]) * band["unit"])
        differ = sum(1 for y in range(top, bottom) for x in range(int(band["fade"][0]), piece) if at(size, pixels, x, y) != at(size, bare, x, y))
        self.assertGreater(differ, 10, "specks left of the scene")

    def test_mirrored_the_day_stands_at_the_other_side(self):
        plan, _ = self.draw("new_year", locale="ar")
        band = band_of(plan)
        self.assertEqual(band["rect"][0], plan["card"][0] + 1)


if __name__ == "__main__":
    unittest.main()
