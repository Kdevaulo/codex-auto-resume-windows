"""v0.6.24: nothing of the notification card's shadow lies under its body.

The card's shadow and body are two layers shown at one alpha. A shadow that reaches under the body shows through it while
the card fades, as a dark frame inside the card's edge. So the shadow layer is clear wherever the body covers wholly - in
the corner the body is drawn with (Soft the squircle, Classic and Plain the arc, High Contrast Soft's, and no shadow at
all) - and is what it was everywhere else. Drawn offscreen with Windows' GDI+, as the card always is; nothing is shown.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# (design, High Contrast): the four looks the card is drawn in.
LOOKS = (("soft", False), ("classic", False), ("plain", False), ("plain", True))


def _card(design, contrast, theme):
    import make_screenshots
    from codex_auto_resume import notice_window
    where = {"dpi": 144, "work": (0, 0, 0, 0), "monitor": (0, 0, 0, 0), "anchor": None}
    drawn = {"theme": theme, "design": design, "contrast": contrast, "reduced": False}
    return notice_window.Card(make_screenshots._NoStack(), make_screenshots.card_notice("en"), now_ms=0, where=where,
                              drawn=drawn, windows=False)


@unittest.skipUnless(os.name == "nt", "the card is drawn with Windows' GDI+")
class ShadowUnderBodyTests(unittest.TestCase):
    def settled(self, card, cut=True):
        """The card's body and shadow layers settled (full size, full depth), the shadow with or without its cut."""
        from codex_auto_resume import notice_card
        card._drawn_scale = card._drawn_level = None
        if not cut:
            card._cut_under_body = lambda layer: None
        try:
            card._paint_body(1.0)
            card._paint_shadow(notice_card.DEPTH_LEVELS - 1)
        finally:
            card.__dict__.pop("_cut_under_body", None)
        return card.body.pixels(), card.shadow.pixels()

    def each_look(self, check):
        """`check(card)` for the card in each look and theme, one sub-test apiece."""
        for design, contrast in LOOKS:
            for theme in ("light", "dark"):
                with self.subTest(design=design, contrast=contrast, theme=theme):
                    card = _card(design, contrast, theme)
                    try:
                        check(card)
                    finally:
                        card.close()

    def test_the_shadow_is_clear_wherever_the_body_is_opaque(self):
        self.each_look(self.clear_under_the_body)

    def clear_under_the_body(self, card):
        body, shadow = self.settled(card)
        width, height = card.size
        wide, margin = width + 2 * card.margin, card.margin
        if not card.shadows:                       # High Contrast: no shadow at all
            self.assertEqual(set(shadow), {0})
            return
        opaque = [(x, y) for y in range(height) for x in range(width) if body[(y * width + x) * 4 + 3] == 255]
        self.assertGreater(len(opaque), width * height * 0.9)
        under = max(shadow[((y + margin) * wide + x + margin) * 4 + 3] for x, y in opaque)
        self.assertEqual(under, 0, "the shadow reaches %d (alpha) under the opaque body" % under)

    def test_the_shadow_outside_the_body_is_what_it_was(self):
        self.each_look(self.kept_outside_the_body)

    def kept_outside_the_body(self, card):
        if not card.shadows:
            return
        body, cut = self.settled(card)
        _, whole = self.settled(card, cut=False)
        width, height = card.size
        wide, margin = width + 2 * card.margin, card.margin
        self.assertGreater(max(whole[3::4]), 0, "no shadow was drawn")
        held = bytearray(whole)
        for y in range(height):
            for x in range(width):
                if body[(y * width + x) * 4 + 3] == 255:
                    at = ((y + margin) * wide + x + margin) * 4
                    held[at:at + 4] = bytes(4)
        self.assertEqual(bytes(held), cut, "the cut changed the shadow where the body is not opaque")
        self.assertGreater(max(whole[((y + margin) * wide + x + margin) * 4 + 3]
                               for y in range(height) for x in range(width)
                               if body[(y * width + x) * 4 + 3] == 255), 0,
                           "the shadow never lay under the body: nothing was cut")

    def test_a_fading_card_shows_no_shadow_through_its_body(self):
        self.each_look(self.fades_clean)

    def fades_clean(self, card):
        import motion_card
        body, shadow = self.settled(card)
        width, height = card.size
        margin = card.margin
        cw, ch = width + 2 * margin + 40, height + 2 * margin + 40
        ground = bytes((200, 210, 220))
        for alpha in (0.25, 0.5):
            faded, whole = bytearray(ground * (cw * ch)), bytearray(ground * (cw * ch))
            for canvas, level in ((faded, alpha), (whole, 1.0)):
                if card.shadows:
                    motion_card.lay(canvas, cw, ch, motion_card.Layer(shadow, width + 2 * margin,
                                                                    height + 2 * margin, 20, 20), level)
                motion_card.lay(canvas, cw, ch, motion_card.Layer(body, width, height, 20 + margin, 20 + margin),
                                level)
            at = ((20 + margin + 30) * cw + 20 + margin + 30) * 3
            shown = round(alpha * 255)
            for channel in range(3):
                want = (whole[at + channel] * shown + ground[channel] * (255 - shown)) / 255.0
                self.assertLessEqual(abs(faded[at + channel] - want), 1.0)


if __name__ == "__main__":
    unittest.main()

