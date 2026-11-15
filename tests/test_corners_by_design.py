"""v0.6.24: a corner follows its design - the popup's, its menus' and the tray card's (brand/shape.py `design_smoothing`).

W2 made every corner in Soft a squircle; Classic keeps v0.6.23's circular arcs, and so does Plain. The notification card
sets its canvas's smoothing itself (ui/card/card.py); the popup, its menus and the icon's card are drawn by the same
Renderer, which sets it when its design or its High Contrast is set - so that no surface can draw a design's corners with
another's. High Contrast draws Soft's look, corners included, as the notification card does.

Each test draws a surface offscreen, transparent round its card, and reads the card's top left corner back: the sum of
the corner's alpha, which is the area the card covers there, against the area the shape module gives for the arc and for
the squircle (sub-sampled four by four, as notice_card.corner_coverage does). A squircle eases into its sides from further away, so it covers less of the box than a circular
corner of the same radius, by several pixels' worth at the scale drawn here - far more than the antialiasing's own error.
Nothing is shown on a screen.
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

from codex_auto_resume import brand, interface  # noqa: E402
from codex_auto_resume.brand import shape  # noqa: E402

if os.name == "nt":
    from codex_auto_resume.ui import popup  # noqa: E402
    from codex_auto_resume.ui.popup import menuplan, menuwindow  # noqa: E402
    from codex_auto_resume.ui.tray import tipcard, words  # noqa: E402
    import test_tray_menu_drawn  # noqa: E402,F401  (its fixtures)
    import test_tray_popup  # noqa: E402,F401
    import test_tray_tipcard  # noqa: E402,F401

SCALE = 4.0           # large, so that the two corners differ by several pixels and not by one
SOFT, CIRCLE = shape.design_smoothing("soft"), shape.design_smoothing("classic")


def corner_alpha(pixels, width, left, top, reach):
    """The sum of the alpha in the box `reach` px square at the card's top left corner, in pixels' worth (alpha / 255)."""
    return sum(pixels[(y * width + x) * 4 + 3] for y in range(top, top + reach) for x in range(left, left + reach)) / 255.0


_AREAS = {}


def corner_area(radius, smoothing, reach):
    """The area of a `reach` px box at the corner of a big card that the shape covers, from sub-samples 4 by 4 in every
    pixel. A corner depends on its radius and smoothing alone, so one is worked out once."""
    key = (radius, smoothing, reach)
    if key not in _AREAS:
        card = (0, 0, 8 * reach, 8 * reach)
        _AREAS[key] = sum(sum(shape.inside(x + (i + 0.5) / 4.0, y + (j + 0.5) / 4.0, card, radius, smoothing)
                              for i in range(4) for j in range(4)) / 16.0
                          for y in range(reach) for x in range(reach))
    return _AREAS[key]


@unittest.skipUnless(os.name == "nt", "the popup is drawn by GDI+")
class CornersByDesignTests(unittest.TestCase):
    """Soft draws its squircle; Classic and Plain the arcs they always did; High Contrast Soft's, whichever design is chosen."""

    def pop(self, theme, design, contrast):
        renderer = popup.Renderer()
        self.addCleanup(renderer.close)
        renderer.theme, renderer.design, renderer.contrast, renderer.lone = theme, design, contrast, True
        vm = popup_view()
        plan = renderer.layout(vm, SCALE, "en")
        canvas = renderer.draw(vm, plan, frame=None)
        card = next(item for item in plan["items"] if item["kind"] == "card")
        return renderer, canvas.width, canvas.pixels(), tuple(plan["card"]), renderer._corner(card, SCALE)

    def menu(self, theme, design, contrast):
        renderer = menuwindow.MenuRenderer()
        self.addCleanup(renderer.close)
        renderer.theme, renderer.design, renderer.contrast = theme, design, contrast
        entries = test_tray_menu_drawn.entries()
        plan = renderer.menu_layout(entries, SCALE, "en")
        canvas = renderer.draw_menu(plan)
        radius = int(round(renderer._radii()["card"] * SCALE))
        return renderer, canvas.width, canvas.pixels(), tuple(plan["card"]), radius

    def tip(self, theme, design, contrast):
        renderer = tipcard.TipRenderer()
        self.addCleanup(renderer.close)
        renderer.theme, renderer.design, renderer.contrast = theme, design, contrast
        parts = words.tooltip_parts(test_tray_tipcard.FIXTURES["metered"], test_tray_tipcard.EN, test_tray_tipcard.NOW, "advanced")
        plan = renderer.tip_layout(parts, "monitoring", SCALE, "en")
        canvas = renderer.draw_tip(plan, None)
        return renderer, canvas.width, canvas.pixels(), tuple(plan["items"][0]["rect"]), renderer._corner(plan["items"][0], SCALE)

    def surfaces(self):
        return (("popup", self.pop), ("menu", self.menu), ("tray card", self.tip))

    def check(self, name, draw, theme, design, contrast, want):
        renderer, width, pixels, rect, radius = draw(theme, design, contrast)
        smoothing = want
        self.assertEqual(renderer.canvas.smoothing, smoothing, "%s: the canvas is not told its design's smoothing" % name)
        reach = int(shape.corner(radius, SOFT, min(rect[2] - rect[0], rect[3] - rect[1]) / 2.0).p) + 2
        drawn = corner_alpha(pixels, width, int(rect[0]), int(rect[1]), reach)
        as_squircle = corner_area(radius, SOFT, reach)
        as_arc = corner_area(radius, CIRCLE, reach)
        self.assertGreater(abs(as_squircle - as_arc), 5.0, "the two shapes must differ here for the test to tell them apart")
        wanted, other = (as_squircle, as_arc) if smoothing else (as_arc, as_squircle)
        self.assertLess(abs(drawn - wanted), abs(drawn - other),
                        "%s %s/%s: drawn %.1f, an arc %.1f, a squircle %.1f" % (name, theme, design, drawn, as_arc, as_squircle))
        self.assertLess(abs(drawn - wanted), 0.35 * abs(as_squircle - as_arc))

    def test_soft_draws_the_squircle_on_every_surface(self):
        for theme in brand.THEMES:
            for name, draw in self.surfaces():
                with self.subTest(surface=name, theme=theme):
                    self.check(name, draw, theme, "soft", False, SOFT)

    def test_classic_and_plain_draw_the_circular_arcs_on_every_surface(self):
        for design in ("classic", "plain"):
            for name, draw in self.surfaces():
                with self.subTest(surface=name, design=design):
                    self.check(name, draw, "light", design, False, CIRCLE)

    def test_high_contrast_draws_softs_corners_in_any_design(self):
        for design in brand.DESIGNS:
            for name, draw in self.surfaces():
                with self.subTest(surface=name, design=design):
                    self.check(name, draw, "light", design, True, SOFT)

    def test_a_renderer_follows_its_design_as_it_is_changed(self):
        """One renderer, its design and High Contrast set one after another, as the popup does when the look changes."""
        renderer = popup.Renderer()
        self.addCleanup(renderer.close)
        seen = []
        for design, contrast in (("classic", False), ("soft", False), ("plain", False), ("plain", True), ("classic", False)):
            renderer.design, renderer.contrast = design, contrast
            seen.append(renderer.canvas.smoothing)
        self.assertEqual(seen, [CIRCLE, SOFT, CIRCLE, SOFT, CIRCLE])


def popup_view():
    from test_tray_popup import EN, FakeControl, WindowsTests
    model = popup.PopupModel(EN)
    model.apply_outcome(("read",), popup.perform(("read",), FakeControl(WindowsTests.ROWS)), time.time())
    return model.view(time.time())


if __name__ == "__main__":
    unittest.main()
