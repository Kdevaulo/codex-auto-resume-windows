"""v0.6.24 (O14 amended by the owner, 2026-11-15): the popup is its card - drawn alone, and its still.

The owner looked at the tray popup - a grey window holding one big card - and said the grey part outside the card should
go. The popup's window is now the card itself (ui/popup/layers.py), so its renderer draws the card ALONE (`Renderer.lone`):
transparent round it, premultiplied, no lift of its own - the card's shadow lies on the desktop in a window of its own,
from the notification card's rule (`float_shadows`). `card_still` is the same two pictures over nothing, offscreen, for
the pictures and the tests. Nothing here opens a window: the renderer draws into memory, and its pixels are read back.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import time
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codex_auto_resume import brand, notice_card  # noqa: E402

if os.name == "nt":
    from codex_auto_resume.ui import popup as tray_popup  # noqa: E402
    import test_tray_popup  # noqa: E402,F401  (its fixtures)

SCALES = (1.0, 1.5, 2.0)


def view():
    from test_tray_popup import EN, FakeControl, WindowsTests
    model = tray_popup.PopupModel(EN)
    model.apply_outcome(("read",), tray_popup.perform(("read",), FakeControl(WindowsTests.ROWS)), time.time())
    return model.view(time.time())


class _Drawn(unittest.TestCase):
    def setUp(self):
        self.renderer = tray_popup.Renderer()
        self.addCleanup(self.renderer.close)
        self.vm = view()

    def draw(self, scale=1.5, theme="light", design="soft", contrast=False, lone=True):
        renderer = self.renderer
        renderer.theme, renderer.design, renderer.contrast, renderer.lone = theme, design, contrast, lone
        plan = renderer.layout(self.vm, scale, "en")
        canvas = renderer.draw(self.vm, plan, frame=tray_popup.halo(self.vm["light"], 0, 0, design=design))
        return plan, canvas.width, canvas.pixels()

    @staticmethod
    def alpha(pixels, width, x, y):
        return pixels[(y * width + x) * 4 + 3]


@unittest.skipUnless(os.name == "nt", "the popup is drawn by GDI+")
class AloneTests(_Drawn):

    def test_round_the_card_there_is_nothing_no_grey_ground_and_no_lift(self):
        for scale in SCALES:
            for theme in brand.THEMES:
                for design in brand.DESIGNS:
                    with self.subTest(scale=scale, theme=theme, design=design):
                        plan, width, pixels = self.draw(scale, theme, design)
                        left, top, right, bottom = plan["card"]
                        height = len(pixels) // (4 * width)
                        outside = [self.alpha(pixels, width, x, y) for y in range(height) for x in range(width)
                                   if not (left <= x < right and top <= y < bottom)]
                        self.assertEqual(max(outside), 0, "something drawn round the card")

    def test_inside_the_card_every_pixel_is_whole_the_words_too(self):
        """GDI's text clears the alpha of what it draws; the card alone has it put back (Renderer._seal)."""
        for scale in SCALES:
            with self.subTest(scale=scale):
                plan, width, pixels = self.draw(scale)
                left, top, right, bottom = plan["card"]
                inset = int(round(brand.RADII["card"] * 2 * scale))
                for y in range(top + inset, bottom - inset):
                    row = pixels[(y * width + left + 1) * 4 + 3:(y * width + right - 1) * 4:4]
                    self.assertEqual(min(row), 255, "row %d has a pixel that is not opaque" % y)

    def test_its_corners_are_cut_by_the_shared_path_and_antialiased(self):
        plan, width, pixels = self.draw(1.5)
        left, top, right, bottom = plan["card"]
        self.assertEqual(self.alpha(pixels, width, left, top), 0, "the corner itself lies outside the card")
        self.assertEqual(self.alpha(pixels, width, right - 1, bottom - 1), 0)
        edge = {self.alpha(pixels, width, x, top + 1) for x in range(left, left + int(brand.RADII["card"] * 1.5))}
        self.assertTrue(any(0 < value < 255 for value in edge), "an antialiased edge, not a stair")

    def test_premultiplied_no_channel_above_its_alpha(self):
        plan, width, pixels = self.draw(1.5, theme="dark")
        self.assertTrue(all(pixels[index + channel] <= pixels[index + 3]
                            for index in range(0, len(pixels), 4) for channel in range(3)))

    def test_a_frame_of_the_light_keeps_the_card_whole(self):
        plan, width, _ = self.draw(1.5)
        for moment in (300.0, 1100.0, 2200.0):
            canvas = self.renderer.draw_halo(plan, tray_popup.halo(self.vm["light"], moment, moment))
            top, bottom = self.renderer.halo_rows
            pixels, (left, _, right, _) = canvas.pixels(), plan["card"]
            for y in range(top, bottom):
                row = pixels[(y * width + left + 30) * 4 + 3:(y * width + right - 30) * 4:4]
                self.assertEqual(min(row), 255, "a breath left row %d see-through" % y)

    def test_not_alone_it_is_drawn_as_before_with_its_ground(self):
        """The notification card draws with the same renderer and cuts its own corners: it is never alone."""
        self.assertFalse(self.renderer.lone, "alone only when asked")
        plan, width, pixels = self.draw(1.5, lone=False)
        self.assertEqual(self.alpha(pixels, width, 1, 1), 255)
        canvas = brand.rgb(brand.LIGHT["canvas"])
        self.assertLessEqual(max(abs(a - b) for a, b in zip(pixels[6:3:-1], canvas)), 1, "the grey ground")


@unittest.skipUnless(os.name == "nt", "the popup is drawn by GDI+")
class StillTests(_Drawn):
    def still(self, scale=1.5, theme="light", design="soft", contrast=False):
        plan, _, _ = self.draw(scale, theme, design, contrast)
        width, height, pixels = tray_popup.card_still(self.renderer, plan)
        return plan, width, height, pixels

    def test_the_still_is_the_card_and_its_shadow_on_nothing(self):
        for scale in SCALES:
            for theme in brand.THEMES:
                with self.subTest(scale=scale, theme=theme):
                    plan, width, height, pixels = self.still(scale, theme)
                    pad = tray_popup.layers.still_pad(scale)
                    card = plan["card"]
                    self.assertEqual((width, height), (card[2] - card[0] + 2 * pad, card[3] - card[1] + 2 * pad))
                    self.assertEqual(self.alpha(pixels, width, 0, 0), 0, "nothing at its edge")
                    below = self.alpha(pixels, width, width // 2, pad + card[3] - card[1] + int(4 * scale))
                    self.assertGreater(below, 0, "the card's shadow lies under it")
                    self.assertEqual(self.alpha(pixels, width, width // 2, height // 2), 255)

    def test_the_still_s_card_is_the_drawn_card_pixel_for_pixel(self):
        plan, width, pixels = self.draw(1.5)
        still_width, _, still = tray_popup.card_still(self.renderer, plan)
        pad = tray_popup.layers.still_pad(1.5)
        left, top, right, _ = plan["card"]
        for y in (top + 40, top + 120, top + 200):
            drawn = pixels[(y * width + left) * 4:(y * width + right) * 4]
            laid = still[((y - top + pad) * still_width + pad) * 4:((y - top + pad) * still_width + pad + right - left) * 4]
            self.assertEqual(drawn[40:-40], laid[40:-40])

    def test_no_shadow_floats_in_high_contrast_or_a_design_without_depth(self):
        for design, contrast in (("classic", False), ("plain", False), ("soft", True)):
            with self.subTest(design=design, contrast=contrast):
                plan, width, height, pixels = self.still(1.5, "dark", design, contrast)
                pad = tray_popup.layers.still_pad(1.5)
                self.assertEqual(self.alpha(pixels, width, width // 2, height - pad + int(4 * 1.5)), 0)
                self.assertEqual(tray_popup.layers.card_shadows("dark", design, contrast),
                                 () if contrast else notice_card.float_shadows("dark", design))

    def test_its_shadow_only_ever_darkens_a_dark_taskbar_as_a_light_desktop(self):
        """No pale halo (the owner, 2026-11-01/02, test_tray_menu_no_glow: light's pale blue-grey shadow shone round the
        icon's menu on a dark taskbar). The popup floats just above the taskbar, so every pixel of its shadow, laid over
        Windows 11's dark taskbar, a light desktop and white, leaves each channel no lighter than it was - and even over
        black, no lighter than the near-black ink every float shadow is drawn in (light's included)."""
        grounds = ((0x20, 0x20, 0x20), (0, 0, 0), (0xFF, 0xFF, 0xFF), (0xF3, 0xF3, 0xF3))
        for theme in brand.THEMES:
            with self.subTest(theme=theme):
                for shadow in tray_popup.float_shadows(theme):
                    self.assertLessEqual(brand.luminance(shadow.colour), tray_popup.layers.DARK_ENOUGH, shadow)
                ink = brand.rgb(brand.palette(tray_popup.layers.FLOAT_SHADOW_THEME)[tray_popup.layers.FLOAT_SHADOW_INK])
                plan, width, height, pixels = self.still(1.5, theme)
                pad, card = tray_popup.layers.still_pad(1.5), plan["card"]
                inside = (pad, pad, pad + card[2] - card[0], pad + card[3] - card[1])
                shaded = 0
                for y in range(0, height, 2):                    # every other pixel each way: the shadow is smooth
                    for x in range(0, width, 2):
                        if inside[0] <= x < inside[2] and inside[1] <= y < inside[3]:
                            continue
                        at = (y * width + x) * 4
                        alpha = pixels[at + 3]
                        if not alpha:
                            continue
                        shaded += 1
                        for ground in grounds:
                            for channel in range(3):
                                over = pixels[at + channel] + ground[2 - channel] * (255 - alpha) / 255.0
                                self.assertLessEqual(over, max(ground[2 - channel], ink[2 - channel]) + 0.5,
                                                     (x, y, ground))
                self.assertGreater(shaded, 0)

    def test_light_and_dark_stills_are_the_same_size(self):
        sizes = {self.still(1.5, theme, design)[1:3] for theme in brand.THEMES for design in brand.DESIGNS}
        self.assertEqual(len(sizes), 1)


@unittest.skipUnless(os.name == "nt", "the popup is drawn by GDI+")
class ShadowLayerTests(_Drawn):
    """The shadow window's own picture (layers.CardLayers), drawn without a window (its hwnd is never used here)."""

    def layer(self):
        layer = tray_popup.CardLayers(0)

        def close():
            layer._drop_images()
            layer.picture.close()
        self.addCleanup(close)
        return layer

    def test_nothing_of_the_shadow_lies_under_the_card(self):
        """The opening fades the card and its shadow together: a shadow under the card's body would show through the
        half-clear card as a dark frame inside its edge (review, 2026-11-15: alpha 139-205 up to 24 px in, in dark)."""
        for scale in SCALES:
            for theme in brand.THEMES:
                with self.subTest(scale=scale, theme=theme):
                    plan, width, pixels = self.draw(scale, theme)
                    layer = self.layer()
                    layer.shade(self.renderer, plan)
                    picture, margin = layer.picture.pixels(), layer.margin
                    left, top, right, bottom = plan["card"]
                    under = [picture[((y - top + margin) * layer.picture.width + x - left + margin) * 4 + 3]
                             for y in range(top, bottom) for x in range(left, right)
                             if pixels[(y * width + x) * 4 + 3] == 255]
                    self.assertEqual(max(under), 0, "shadow under the card's body")
                    below = picture[((bottom - top + margin + int(3 * scale)) * layer.picture.width
                                     + margin + (right - left) // 2) * 4 + 3]
                    self.assertGreater(below, 0, "and still all round it")

    def test_one_image_a_shadow_whatever_sizes_the_card_has_had(self):
        from codex_auto_resume.ui.popup import gdiplus
        from test_tray_popup import EN, FakeControl, WindowsTests
        self.renderer.theme, self.renderer.lone = "dark", True
        layer, counts = self.layer(), []
        for repeat in range(2):
            for count in range(len(WindowsTests.ROWS) + 1):
                model = tray_popup.PopupModel(EN)
                model.apply_outcome(("read",), tray_popup.perform(("read",), FakeControl(WindowsTests.ROWS[:count])),
                                    time.time())
                vm = model.view(time.time())
                plan = self.renderer.layout(vm, 1.5, "en")
                self.renderer.draw(vm, plan, frame=tray_popup.halo(vm["light"], 0, 0))
                layer.shade(self.renderer, plan)
                counts.append(len(layer.images))
        self.assertEqual(set(counts), {len(tray_popup.float_shadows("dark"))})
        before = gdiplus.gdiplus_objects()
        layer._drop_images()
        self.assertEqual(before - gdiplus.gdiplus_objects(), len(tray_popup.float_shadows("dark")))


class RecipeTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "the popup's package is Windows'")
    def test_the_popup_floats_the_notification_card_s_shadows(self):
        """One product, one rule: the popup cannot call notice_card (which imports it), so it holds the same rule, and
        this holds the two equal for every theme, design and scale."""
        for theme in brand.THEMES:
            for design in brand.DESIGNS:
                shadows = tray_popup.float_shadows(theme, design)
                with self.subTest(theme=theme, design=design):
                    self.assertEqual(shadows, notice_card.float_shadows(theme, design))
                    for scale in (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0):
                        self.assertEqual(tray_popup.float_reach(shadows, scale),
                                         notice_card.shadow_margin(shadows, scale) if shadows else 0)


if __name__ == "__main__":
    unittest.main()
