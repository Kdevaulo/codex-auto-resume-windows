"""The icon's card's first row reads as one line, measured by its ink (v0.6.24 final).

The owner, 2026-11-18, of the hover card's header - the status light, "Codex Auto Resume" and the edition's pill
"고급판": "여기도 정렬이 안 맞아보여" (this does not look aligned either). The three were centred by their boxes: the light
on the row's box, the name and the pill's words each in a line box of their own font, so to the eye the light sat on the
line box's middle, below the letters' own middle, and the pill's words on a baseline of their own. And the light's box
left 2.5 px more between the light and the name than the name left before the pill.

Now (ui/tray/tipplan.py, the renderer's font metrics): the light is centred on the name's x-height middle; the pill's
words stand on the name's baseline and the pill is centred on that same middle; the name starts as far after the light's
own edge as the pill starts after the name. Each is read here off the card as drawn - its pixels, off-screen, by the
card's own renderer (tipcard.draw_offscreen: no window, nothing on the screen) - at 100, 150 and 200%:

- the light's ink centre is within 1 px of the x-height band's middle, the band read off the same card drawn with a name
  of x's alone (the layout places the row by the fonts' metrics, never by the name's letters, so both cards' rows are
  where they are);
- the pill's words end on the name's baseline: the lowest ink rows of the two are the same (neither "Codex Auto Resume"
  nor "Advanced" has a letter below the baseline);
- the gap from the light's ink to the name's ink and from the name's ink to the pill are within 1 px.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codex_auto_resume import brand, interface  # noqa: E402
from codex_auto_resume.ui.tray import words  # noqa: E402

NOW = 1_800_000_000.0
SNAPSHOT = {"enabled": True, "waiting": 1, "next_at": NOW + 200}
SCALES = (1.0, 1.5, 2.0)


def far(a, b):
    return sum(abs(x - y) for x, y in zip(a, b))


@unittest.skipUnless(os.name == "nt", "the card is drawn by GDI")
class HeaderInkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from codex_auto_resume.ui.tray import tipcard
        cls.cards = {}
        for scale in SCALES:
            parts = words.tooltip_parts(SNAPSHOT, interface.STRINGS["en"], NOW, "advanced")
            xs = dict(parts, title="x" * len(parts["title"]))
            cls.cards[scale] = (tipcard.draw_offscreen(parts, "monitoring", scale=scale, locale="en"),
                                tipcard.draw_offscreen(xs, "monitoring", scale=scale, locale="en"))

    @staticmethod
    def rgb(plan, pixels, x, y):
        index = (int(y) * plan["size"][0] + int(x)) * 4
        blue, green, red = pixels[index:index + 3]
        return red, green, blue

    def ink(self, plan, pixels, rect, colour=None):
        """The rows and columns of `rect` holding ink: a pixel at least half as far from the card's ground as the ink is
        (`colour`, or the ink colour farthest from the ground there)."""
        left, top, right, bottom = (int(value) for value in rect)
        ground = self.rgb(plan, pixels, plan["size"][0] - 3, plan["size"][1] // 2)
        cells = [(x, y, self.rgb(plan, pixels, x, y)) for y in range(top, bottom) for x in range(left, right)]
        target = colour or max((cell[2] for cell in cells), key=lambda value: far(value, ground))
        least = far(target, ground) / 2.0
        found = [(x, y) for x, y, value in cells if far(value, ground) >= least and far(value, target) < far(value, ground)]
        self.assertTrue(found, "no ink in %r" % (rect,))
        return min(y for _, y in found), max(y for _, y in found), min(x for x, _ in found), max(x for x, _ in found)

    def header(self, plan):
        halo = next(item for item in plan["items"] if item["kind"] == "halo")
        title = next(item for item in plan["items"] if item["kind"] == "text" and item["role"] == "name")
        chip = next(item for item in plan["items"] if item["kind"] == "chip")
        words_ = next(item for item in plan["items"] if item["kind"] == "text" and item["role"] == "chip")
        return halo, title, chip, words_

    def dot_ink(self, plan, pixels, halo, scale):
        reach = int(brand.STATUS_DOT["popup"] * scale) + 2
        rect = (halo["cx"] - reach, halo["cy"] - reach - 1, halo["cx"] + reach + 1, halo["cy"] + reach + 2)
        return self.ink(plan, pixels, rect)

    def test_the_light_is_centred_on_the_names_x_height_middle(self):
        for scale in SCALES:
            with self.subTest(scale=scale):
                _, (plan, pixels) = self.cards[scale]
                halo, title, _, _ = self.header(plan)
                top, bottom, _, _ = self.dot_ink(plan, pixels, halo, scale)
                x_top, x_bottom, _, _ = self.ink(plan, pixels, title["rect"])
                light, letters = (top + bottom + 1) / 2.0, (x_top + x_bottom + 1) / 2.0
                self.assertLessEqual(abs(light - letters), 1.0, "the light at %.1f, the x-height middle at %.1f"
                                     % (light, letters))

    def test_the_pills_words_stand_on_the_names_baseline(self):
        for scale in SCALES:
            with self.subTest(scale=scale):
                (plan, pixels), (xplan, xpixels) = self.cards[scale]
                _, title, chip, words_ = self.header(plan)
                name_bottom = self.ink(plan, pixels, title["rect"])[1]
                accent = brand.rgb(brand.palette("light", brand.DEFAULT_DESIGN)["accent"])
                pill_bottom = self.ink(plan, pixels, chip["rect"], accent)[1]
                self.assertEqual(pill_bottom, name_bottom, "the pill's words end at row %d, the name at %d"
                                 % (pill_bottom, name_bottom))
                self.assertEqual(self.ink(xplan, xpixels, self.header(xplan)[1]["rect"])[1], name_bottom,
                                 "the x's stand where the name stands")

    def test_the_pill_is_centred_on_the_same_middle(self):
        for scale in SCALES:
            with self.subTest(scale=scale):
                _, (plan, pixels) = self.cards[scale]
                _, title, chip, _ = self.header(plan)
                x_top, x_bottom, _, _ = self.ink(plan, pixels, title["rect"])
                pill = (chip["rect"][1] + chip["rect"][3]) / 2.0
                self.assertLessEqual(abs(pill - (x_top + x_bottom + 1) / 2.0), 1.0)

    def test_the_gaps_either_side_of_the_name_read_equal(self):
        for scale in SCALES:
            with self.subTest(scale=scale):
                (plan, pixels), _ = self.cards[scale]
                halo, title, chip, _ = self.header(plan)
                dot_right = self.dot_ink(plan, pixels, halo, scale)[3]
                _, _, name_left, name_right = self.ink(plan, pixels, title["rect"])
                before, after = name_left - dot_right - 1, chip["rect"][0] - name_right - 1
                self.assertLessEqual(abs(before - after), 1, "%d px after the light, %d px before the pill"
                                     % (before, after))


if __name__ == "__main__":
    unittest.main()
