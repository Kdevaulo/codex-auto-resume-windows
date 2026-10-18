"""The notification card in the README's motion picture (build/motion_card.py): the card's own paint, offscreen.

The settled card on the canvas must be the README card's own picture byte for byte (make_screenshots._SettledCard),
its entrance and exit the card's own motion (notice_card.entrance, leaving), its light the card's own breath and its
hover the card's own face. Drawn with Windows' GDI+, as the card always is; nothing is put on the screen.
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

import motion_card  # noqa: E402

# Room right of the work area and under it, so the floating shadow stays on the canvas.
CANVAS = (1200, 900)
WORK = (0, 0, 1100, 820)
BORN = 1000


def canvas_colour():
    from codex_auto_resume import brand
    return bytes(brand.rgb(brand.palette("light", brand.DEFAULT_DESIGN)["canvas"]))


@unittest.skipUnless(os.name == "nt", "the card is drawn with Windows' GDI+")
class CardFramesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = motion_card.CardFrames("en", scale=1.5, work=WORK, monitor=(0, 0) + CANVAS)

    @classmethod
    def tearDownClass(cls):
        cls.frames.close()

    def canvas_with(self, drawn) -> bytearray:
        width, height = CANVAS
        canvas = bytearray(canvas_colour() * (width * height))
        self.frames.lay_on(canvas, width, height, drawn)
        return canvas

    def test_the_settled_card_is_the_readme_card_byte_for_byte(self):
        import make_screenshots
        from codex_auto_resume import brand, notice_card
        settled = make_screenshots._SettledCard("en", "light", brand.DEFAULT_DESIGN, 1.5, None)
        try:
            want, width, height, pad = (make_screenshots.bgra_rgb(settled.at(0)), settled.width, settled.height,
                                        settled.pad)
        finally:
            settled.close()
        drawn = self.frames.drawn(BORN + notice_card.ENTRANCE_MS, BORN, light=BORN)
        self.assertEqual(drawn.alpha, 1.0)
        canvas = self.canvas_with(drawn)
        left, top = self.frames.place[0] - pad, self.frames.place[1] - pad
        got = b"".join(bytes(canvas[((top + y) * CANVAS[0] + left) * 3:((top + y) * CANVAS[0] + left + width) * 3])
                       for y in range(height))
        self.assertEqual(len(got), len(want))
        self.assertTrue(got == want, "the settled card differs from the README card's own picture")

    def test_the_entrance_is_the_card_s_own_motion(self):
        from codex_auto_resume import notice_card
        x, y = self.frames.place
        for elapsed in range(0, notice_card.ENTRANCE_MS + 1, 40):
            with self.subTest(elapsed=elapsed):
                drawn = self.frames.drawn(BORN + elapsed, BORN)
                want = notice_card.entrance(elapsed)
                self.assertEqual(drawn.frame, tuple(want))
                self.assertAlmostEqual(drawn.alpha, want.alpha)
                self.assertEqual((drawn.body.left, drawn.body.top), (x, y + int(round(want.offset * 1.5))),
                                 "it rises out of the taskbar's side")

    def test_it_leaves_as_the_card_leaves_and_is_then_gone(self):
        from codex_auto_resume import notice_card
        leave = BORN + 2000
        for elapsed in (0, 40, 120, 200):
            with self.subTest(elapsed=elapsed):
                drawn = self.frames.drawn(leave + elapsed, BORN, leave=leave)
                self.assertAlmostEqual(drawn.alpha, notice_card.leaving(elapsed))
        self.assertIsNone(self.frames.drawn(leave + notice_card.EXIT_MS, BORN, leave=leave))

    def test_a_fading_card_is_laid_at_its_alpha(self):
        drawn = self.frames.drawn(BORN + 2100, BORN, leave=BORN + 2000)
        faded, whole = self.canvas_with(drawn), self.canvas_with(drawn._replace(alpha=1.0))
        ground = canvas_colour()
        cx, cy = self.frames.place[0] + 30, self.frames.place[1] + 30
        at = (cy * CANVAS[0] + cx) * 3
        for channel in range(3):
            expected = (whole[at + channel] * round(drawn.alpha * 255) + ground[channel] * (255 - round(drawn.alpha * 255)))
            self.assertLessEqual(abs(faded[at + channel] - expected / 255.0), 1.0)

    def test_the_light_breathes_on_the_picture_s_clock_and_nothing_else_moves(self):
        from codex_auto_resume import notice_card
        settled = BORN + notice_card.ENTRANCE_MS
        one, other = self.frames.drawn(settled + 400, BORN), self.frames.drawn(settled + 1400, BORN)
        self.assertNotEqual(one.body.pixels, other.body.pixels, "the light did not move")
        top, bottom = self.frames.card.renderer.halo_rows
        row = one.body.width * 4
        self.assertEqual(one.body.pixels[:top * row], other.body.pixels[:top * row])
        self.assertEqual(one.body.pixels[bottom * row:], other.body.pixels[bottom * row:])
        self.assertEqual(self.frames.drawn(settled + 400, BORN).body.pixels, one.body.pixels,
                         "the same moment drew another light")

    def test_the_hover_and_the_press_are_the_card_s_own_faces_on_the_button(self):
        from codex_auto_resume import notice_card
        settled = BORN + notice_card.ENTRANCE_MS + 100
        rest = self.frames.drawn(settled, BORN)
        hovered = self.frames.drawn(settled, BORN, hover="open")
        pressed = self.frames.drawn(settled, BORN, hover="open", pressed="open")
        self.assertNotEqual(rest.body.pixels, hovered.body.pixels)
        self.assertNotEqual(hovered.body.pixels, pressed.body.pixels)
        left, top, right, bottom = self.frames.button("open")
        x, y = self.frames.place
        width = rest.body.width
        changed = [(index // 4 % width + x, index // 4 // width + y) for index in range(0, len(rest.body.pixels), 4)
                   if rest.body.pixels[index:index + 4] != hovered.body.pixels[index:index + 4]]
        self.assertTrue(all(left - 8 <= cx < right + 8 and top - 8 <= cy < bottom + 8 for cx, cy in changed),
                        "the hover changed the card away from its button")
        self.assertEqual(self.frames.drawn(settled, BORN).body.pixels, rest.body.pixels, "the face came back")

    def test_open_is_the_open_dashboard_button_inside_the_card(self):
        label = [action["label"] for action in self.frames.card.vm["actions"]
                 if action["target"] == self.frames.target("open")]
        self.assertEqual(label, ["Open Dashboard"])
        left, top, right, bottom = self.frames.button("open")
        x, y = self.frames.place
        width, height = self.frames.card.size
        self.assertTrue(x <= left < right <= x + width and y <= top < bottom <= y + height)
        with self.assertRaises(KeyError):
            self.frames.target("explode")

    def test_it_stands_where_the_stack_puts_the_newest_card(self):
        from codex_auto_resume import brand, notice_card
        gap = int(round(brand.SPACING["m"] * 1.5))
        want, _edge = notice_card.stack_positions([self.frames.card.size], WORK, (0, 0) + CANVAS, None,
                                                  gap=gap, spacing=gap)
        self.assertEqual(self.frames.place, want[0])
        self.assertEqual(self.frames.place[0] + self.frames.card.size[0], WORK[2] - gap)


@unittest.skipUnless(os.name == "nt", "the card is drawn with Windows' GDI+")
class CardPictureTests(unittest.TestCase):
    """make_motion draws a plan with no window - the card on its own - on the plain canvas."""

    def test_the_card_rises_rests_and_leaves_on_the_plain_canvas(self):
        import tempfile
        import make_motion
        import motion_plan
        from test_social_motion import composite, read_apng
        plan = {"format": motion_plan.FORMAT, "name": "card-test", "locale": "en",
                "canvas": {"size": [776, 540], "ground": "canvas", "theme": "light", "design": "soft"},
                "card": {"scale": 2.0, "locale": "en", "at": [52, 52]}, "pointer": {"rest": [820, 660]},
                "scenes": [{"id": "A", "steps": [{"card": "enter", "frames": 3, "step": 120}, {"hold": 200},
                                                 {"card": "leave", "frames": 2, "step": 120}, {"hold": 100}]}]}
        motion_plan.check(plan)
        with tempfile.TemporaryDirectory() as name:
            plan["output"] = str(Path(name) / "card.png")
            report = make_motion.make(plan, None, Path(name) / "work")
            shown = list(composite(read_apng(Path(plan["output"]).read_bytes())))
        ground = canvas_colour()
        self.assertEqual(shown[0], ground * (776 * 540), "frame 1 is the empty canvas the card rises onto")
        self.assertEqual(shown[-1], ground * (776 * 540), "it ends where it loops back to")
        middle = shown[len(shown) // 2]
        at = ((52 + 60) * 776 + 52 + 60) * 3
        self.assertNotEqual(middle[at:at + 3], ground, "the card stands at its place")
        self.assertEqual(report.ms, motion_plan.plan_end(plan))


@unittest.skipUnless(os.name == "nt", "the card is drawn with Windows' GDI+")
class CardMarginsTests(unittest.TestCase):
    def test_the_card_picture_has_the_same_margin_on_every_side_as_the_still_below_it(self):
        """The owner, 2026-10-19: much more background lay below the card than above it. The canvas is the card and
        its floating shadow's reach on all four sides - the size of the README's still card - and the card enters
        from the bottom edge."""
        import make_motion
        import make_screenshots
        import motion_plan
        for name, locale in (("card-en", "en"), ("card-ko", "ko")):
            with self.subTest(name):
                plan = motion_plan.load(make_motion.plan_path(name))
                still = make_screenshots._SettledCard(locale, "light", "soft", 2.0, None)
                try:
                    self.assertEqual(plan["canvas"]["size"], [still.width, still.height])
                    self.assertEqual(plan["card"]["at"], [still.pad, still.pad])
                finally:
                    still.close()
                self.assertNotIn("transparent", plan["canvas"], "the background stays as it is, not clear")


class LayTests(unittest.TestCase):
    def layer(self):
        pixels = bytearray()
        for index in range(12):
            alpha = (0, 64, 128, 255)[index % 4]
            pixels += bytes(((index * 7) * alpha // 255, (index * 13) * alpha // 255, (index * 19) * alpha // 255,
                             alpha))
        return motion_card.Layer(bytes(pixels), 4, 3, 1, 1)

    def test_at_full_alpha_it_is_the_generator_s_own_over(self):
        import make_screenshots
        layer = self.layer()
        rgb = bytearray(bytes((200, 150, 100)) * 36)
        motion_card.lay(rgb, 6, 6, layer, 1.0)
        bgra = bytearray(bytes((100, 150, 200, 255)) * 36)
        make_screenshots._over(bgra, 6, layer.pixels, 4, 3, 1, 1)
        self.assertEqual(bytes(rgb), make_screenshots.bgra_rgb(bytes(bgra)))

    def test_at_no_alpha_nothing_changes_and_off_the_canvas_is_cut(self):
        rgb = bytearray(bytes((1, 2, 3)) * 36)
        motion_card.lay(rgb, 6, 6, self.layer(), 0.0)
        self.assertEqual(rgb, bytearray(bytes((1, 2, 3)) * 36))
        motion_card.lay(rgb, 6, 6, self.layer()._replace(left=4, top=5), 1.0)
        self.assertEqual(len(rgb), 108)

    def test_half_alpha_halves_what_it_covers(self):
        layer = motion_card.Layer(bytes((0, 0, 200, 255)), 1, 1, 0, 0)
        rgb = bytearray(bytes((0, 0, 0)))
        motion_card.lay(rgb, 1, 1, layer, 0.5)
        self.assertEqual(rgb[0], (200 * 128 + 127) // 255)


if __name__ == "__main__":
    unittest.main()
