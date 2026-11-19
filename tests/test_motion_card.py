"""The notification card in the README's motion picture (build/motion_card.py): the card's own paint, offscreen.

The settled card on the canvas must be the README card's own picture byte for byte (make_screenshots._SettledCard),
on a clear ground - RGBA, the card opaque, its float shadow with its own alpha, everything else alpha 0 (the owner,
2026-11-16: on a desktop it floats with only its own shadow) - its entrance and exit the card's own motion (notice_card.entrance, leaving), its light the card's own breath and its
hover the card's own face. Drawn with Windows' GDI+, as the card always is; nothing is put on the screen.
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import motion_card  # noqa: E402

# Room right of the work area and under it, so the floating shadow stays on the canvas.
CANVAS = (1200, 900)
WORK = (0, 0, 1100, 820)
BORN = 1000


def read_rgba_apng(raw: bytes) -> list:
    """Each frame of an 8-bit RGBA APNG as the picture a viewer shows (every rectangle replaces what is under it)."""
    from test_social_motion import chunks, unfilter
    parts = chunks(raw)
    width, height, depth, colour = struct.unpack(">IIBB", dict(parts)[b"IHDR"][:10])
    assert (depth, colour) == (8, 6), "8-bit RGBA"
    frames, current = [], None
    for kind, data in parts:
        if kind == b"fcTL":
            current = {"control": struct.unpack(">IIIIIHHBB", data), "data": bytearray()}
            frames.append(current)
        elif kind == b"IDAT":
            current["data"] += data
        elif kind == b"fdAT":
            current["data"] += data[4:]
    canvas, shown = bytearray(width * height * 4), []
    for frame in frames:
        _n, w, h, x, y, _num, _den, dispose, blend = frame["control"]
        assert (dispose, blend) == (0, 0), "kept, and laid as the source, never over"
        pixels = unfilter(zlib.decompress(bytes(frame["data"])), w, h, 4)
        for row in range(h):
            at = ((y + row) * width + x) * 4
            canvas[at:at + w * 4] = pixels[row * w * 4:(row + 1) * w * 4]
        shown.append(bytes(canvas))
    return shown


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
        canvas = bytearray(width * height * 4)                  # a clear canvas
        self.frames.lay_on(canvas, width, height, drawn)
        return canvas

    def test_the_settled_card_is_the_readme_card_byte_for_byte(self):
        import make_screenshots
        from codex_auto_resume import brand, notice_card
        settled = make_screenshots._SettledCard("en", "light", brand.DEFAULT_DESIGN, 1.5, None)
        try:
            want, width, height, pad = (make_screenshots.clear_rgba(settled.at(0)), settled.width, settled.height,
                                        settled.pad)
        finally:
            settled.close()
        drawn = self.frames.drawn(BORN + notice_card.ENTRANCE_MS, BORN, light=BORN)
        self.assertEqual(drawn.alpha, 1.0)
        canvas = self.canvas_with(drawn)
        left, top = self.frames.place[0] - pad, self.frames.place[1] - pad
        got = b"".join(bytes(canvas[((top + y) * CANVAS[0] + left) * 4:((top + y) * CANVAS[0] + left + width) * 4])
                       for y in range(height))
        self.assertEqual(len(got), len(want))
        self.assertTrue(got == want, "the settled card differs from the README card's own picture")
        # ... which is the card opaque on a clear ground, its shadow between, and nothing elsewhere.
        alpha = got[3::4]
        self.assertEqual((alpha[0], alpha[width - 1], alpha[-1], alpha[-width]), (0, 0, 0, 0), "the corners are clear")
        self.assertEqual(alpha[(height // 2) * width + width // 2], 255, "the card is opaque")
        self.assertTrue(any(0 < value < 255 for value in alpha), "the shadow keeps its own alpha")
        outside = [(x, y) for y in range(CANVAS[1]) for x in (0, CANVAS[0] - 1)] + [
            (x, y) for y in (0, CANVAS[1] - 1) for x in range(CANVAS[0])]
        self.assertTrue(all(canvas[(y * CANVAS[0] + x) * 4 + 3] == 0 for x, y in outside),
                        "everything away from the card is wholly transparent")

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
        cx, cy = self.frames.place[0] + 30, self.frames.place[1] + 30
        at = (cy * CANVAS[0] + cx) * 4
        self.assertEqual(whole[at + 3], 255)
        self.assertLessEqual(abs(faded[at + 3] - round(drawn.alpha * 255)), 1, "its coverage is scaled by the alpha")
        for channel in range(3):
            self.assertLessEqual(abs(faded[at + channel] - whole[at + channel]), 2, "the colour is the card's own")

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
    """make_motion draws a plan with no window - the card on its own - on a clear canvas."""

    def test_the_card_rises_rests_and_leaves_on_a_clear_canvas(self):
        import tempfile
        import make_motion
        import motion_plan
        plan = {"format": motion_plan.FORMAT, "name": "card-test", "locale": "en",
                "canvas": {"size": [776, 540], "transparent": True, "theme": "light", "design": "soft"},
                "card": {"scale": 2.0, "locale": "en", "at": [52, 52]}, "pointer": {"rest": [820, 660]},
                "scenes": [{"id": "A", "steps": [{"card": "enter", "frames": 3, "step": 120}, {"hold": 200},
                                                 {"card": "leave", "frames": 2, "step": 120}, {"hold": 100}]}]}
        motion_plan.check(plan)
        with tempfile.TemporaryDirectory() as name:
            plan["output"] = str(Path(name) / "card.png")
            report = make_motion.make(plan, None, Path(name) / "work")
            shown = read_rgba_apng(Path(plan["output"]).read_bytes())
        clear = bytes(776 * 540 * 4)
        self.assertEqual(shown[0], clear, "frame 1 is the empty canvas the card rises onto: wholly transparent")
        self.assertEqual(shown[-1], clear, "it ends where it loops back to")
        middle = shown[len(shown) // 2]
        at = ((52 + 60) * 776 + 52 + 60) * 4
        self.assertEqual(middle[at + 3], 255, "the card stands at its place, opaque")
        self.assertEqual(middle[3], 0, "and its corner of the picture is clear")
        self.assertEqual(report.ms, motion_plan.plan_end(plan))


@unittest.skipUnless(os.name == "nt", "the card is drawn with Windows' GDI+")
class CardMarginsTests(unittest.TestCase):
    def test_the_card_picture_has_the_same_margin_on_every_side_as_the_still_above_the_strip(self):
        """The owner, 2026-10-19: much more background lay below the card than above it. The card and its floating
        shadow's reach on all four sides are the size of the README's still card; since 2026-11-19 the right end of a
        taskbar lies under that (tests/test_motion_card_strip.py): the gap the product keeps from the taskbar, then the
        strip, and the screen's edge the gap from the card's right edge - the shadow reaching past it, on the canvas."""
        import make_motion
        import make_screenshots
        import motion_plan
        from codex_auto_resume import brand
        gap = int(round(brand.SPACING["m"] * 2.0))
        for name, locale in (("card-en", "en"), ("card-ko", "ko")):
            with self.subTest(name):
                plan = motion_plan.load(make_motion.plan_path(name))
                # The committed still, not one drawn here: a card drawn on another machine takes that machine's
                # fonts, and the CI runner drew the English card 30 px shorter than the picture beside it.
                asset, _copy = make_screenshots.card_paths(locale)["light"]
                width, height = (int(part) for part in make_screenshots.dimensions(asset).split("x"))
                still = make_screenshots._SettledCard(locale, "light", "soft", 2.0, None)
                try:
                    pad = still.pad
                finally:
                    still.close()
                strip = plan["taskbar"]
                self.assertEqual(plan["canvas"]["size"], [width, strip["top"] + strip["height"]])
                self.assertEqual(strip["top"], height - pad + gap, "the still's own rows, then the gap, then the strip")
                self.assertEqual(strip["edge"], width - pad + gap)
                self.assertNotIn("at", plan["card"], "the product's placement puts it at the still's own margin")
                self.assertIs(plan["canvas"].get("transparent"), True, "the background is clear (2026-11-16)")
                self.assertNotIn("ground", plan["canvas"], "no canvas colour is laid under the card")


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
