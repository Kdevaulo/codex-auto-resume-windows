"""v0.6.24-beta.3 (W2): a frame of a special day's popup header costs what its scene alone cost before the day spread wide.

The day's specks are laid band after band from the card's outer side (brand.speck_elements), and a band is wider than
what the header shows of it: the popup filled every speck of every band each frame, most of them clipped away or fallen
out of sight, and made and deleted a brush for every piece. Measured offscreen at 100 % and 150 %, a frame took about a
third longer than the v0.6.24-beta.2 scene's. Now a band draws only the specks that can reach into what the header
shows (brand.speck_frame's `within`, from brand.speck_reach), none that has fallen past its foot, and the painter makes
each colour's brush once a frame (_Painter.keep_solids).

Offscreen drawing only (the popup's renderer, no window): it runs without a screen.
"""
from __future__ import annotations

import unittest
from unittest import mock

from codex_auto_resume import brand
from codex_auto_resume.ui import popup as tray_popup
from codex_auto_resume.ui.popup import gdiplus, renderer

LOOKS = tuple(brand.DAY_LOOKS)


class PopupFrameTests(unittest.TestCase):
    def setUp(self):
        self.renderer = tray_popup.Renderer()
        self.addCleanup(self.renderer.close)

    def plan(self, look, scale):
        vm = tray_popup.view_model([], {"enabled": True}, {}, 1800000000.0)
        vm["scene"] = look
        plan = self.renderer.layout(vm, scale, "en")
        self.renderer.draw(vm, plan, frame=tray_popup.halo("monitoring", 0.0), scene_ms=0.0)
        return plan

    def frame(self, plan, milliseconds):
        """The pieces a frame fills, and the brushes it makes."""
        pieces, brushes = [], []
        shape = renderer.Renderer._scene_shape
        made = gdiplus._Painter._brush

        def counted(paint, piece, at, scale):
            pieces.append(piece)
            return shape(paint, piece, at, scale)

        def making(painter, colour):
            brushes.append(colour)
            return made(painter, colour)

        with mock.patch.object(renderer.Renderer, "_scene_shape", staticmethod(counted)), \
                mock.patch.object(gdiplus._Painter, "_brush", making):
            self.renderer.draw_scene(plan, milliseconds)
        return pieces, brushes

    def test_a_frame_fills_no_speck_out_of_sight(self):
        for scale in (1.0, 1.5):
            for look in LOOKS:
                with self.subTest(look=look, scale=scale):
                    plan = self.plan(look, scale)
                    item = [entry for entry in plan["items"] if entry["kind"] == "scene"][0]
                    left, _, right, _ = item["rect"]
                    bands = 0
                    while bands * brand.SPECK_BAND * item["unit"] < right - left:
                        bands += 1
                    for milliseconds in (0.0, 1300.0, 4700.0):
                        pieces, _ = self.frame(plan, milliseconds)
                        specks = len(pieces) - len(brand.scene_elements(look))
                        self.assertGreaterEqual(specks, 0)
                        self.assertLess(specks, bands * len(brand.speck_elements(look)), "every speck of every band was filled")

    def test_the_specks_in_sight_are_all_drawn(self):
        """What is out of sight is left out, nothing else: the pixels are those of every speck drawn."""
        for look in LOOKS:
            with self.subTest(look=look):
                plan = self.plan(look, 1.5)
                culled = bytes(self.renderer.draw_scene(plan, 1300.0).pixels())
                every = brand.speck_frame
                with mock.patch.object(brand, "speck_frame", lambda one, milliseconds, within=None: every(one, milliseconds)):
                    whole = bytes(self.renderer.draw_scene(plan, 1300.0).pixels())
                self.assertEqual(culled, whole)

    def test_a_frame_makes_each_colour_s_brush_once(self):
        for look in LOOKS:
            with self.subTest(look=look):
                plan = self.plan(look, 1.5)
                pieces, brushes = self.frame(plan, 1300.0)
                # The ground, a round piece (seollal's stripes) and the card's colour past the words are filled as they
                # always were; every circle, ellipse and polygon in a colour already used takes its brush again.
                self.assertLess(len(brushes), len(pieces), "a brush for every piece")


if __name__ == "__main__":
    unittest.main()
