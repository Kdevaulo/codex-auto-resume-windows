"""The notification card's motion picture stands on the right end of a taskbar (v0.6.24, the owner's wish of 2026-11-19).

The same plain strip the tray popup's motion picture has (tests/test_motion_tray_story.py) is drawn under the card, with the
product's tray icon on it at its own frames of the moment: the card's status is waiting, so the icon is the waiting one
(ui.tray.ICON_FOR_LIGHT: watching), breathing on its own timer. The card stands where the product's stack puts it
(notice_card.stack_positions, which is popup.place: centred on the icon, SPACING m above the work area, inside it), and
rises into place as the product moves it (notice_card.entrance: RISE px below, fading in) - never out of the canvas's edge.
The pointer story is what it was: there is none. The picture is three breaths long, so the card's light and the icon
are where they began when it loops. Drawn with Windows' GDI+, in memory: nothing is written, nothing is put on the screen.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import make_motion  # noqa: E402
import motion_plan  # noqa: E402

NAMES = ("card-en", "card-ko")
SCALE = 2.0
PAD = 52                  # the card's float shadow's reach at 200 %, which the card's still keeps round the card


def plan_of(name):
    return motion_plan.load(make_motion.plan_path(name))


class PlanTests(unittest.TestCase):
    def test_the_strip_is_under_the_card_in_both_languages_with_the_icon_the_card_means(self):
        from codex_auto_resume import notice_card
        from codex_auto_resume.ui import tray
        import make_screenshots as shots
        light = notice_card.view(shots.card_notice("en"))["status"]
        for name in NAMES:
            with self.subTest(name):
                plan = plan_of(name)
                strip = plan["taskbar"]
                self.assertEqual(strip["icon"]["state"], tray.ICON_FOR_LIGHT[light],
                                 "the card means %s: the icon shows what the watcher shows then" % light)
                self.assertEqual((strip["height"], strip["icon"]["size"]), (96, 32), "Windows 11's taskbar at 200 %")
                self.assertNotIn("at", plan["card"], "the card stands where the product puts it, not where a plan says")
                self.assertIsNone(plan["pointer"], "the pointer story is what it was: none")
                self.assertTrue(make_motion.icon_moments(plan, motion_plan.plan_end(plan)),
                                "the strip's icon moves on its own timer")

    def test_the_canvas_is_the_old_picture_with_the_gap_and_the_strip_under_it(self):
        from codex_auto_resume import brand
        gap = int(round(brand.SPACING["m"] * SCALE))
        # The card's own height at 200 %. v0.6.26-beta.2 (audit4 F1): the English card is set in Segoe UI now, as an
        # English Windows sets it, not in this machine's Malgun Gothic Latin - 30 px shorter than the 436 it was.
        heights = {"card-en": 406, "card-ko": 420}
        for name in NAMES:
            with self.subTest(name):
                plan = plan_of(name)
                strip = plan["taskbar"]
                self.assertEqual(plan["canvas"]["size"], [776, strip["top"] + strip["height"]])
                self.assertEqual(strip["top"], PAD + heights[name] + gap, "the card, the gap the product keeps, the strip")
                self.assertEqual(strip["edge"], 776 - PAD + gap,
                                 "the card's right edge is that gap from the screen's: its shadow reaches past it")
                self.assertIs(plan["canvas"]["transparent"], True, "a clear ground above the strip")
                self.assertEqual(plan["budget"], {"cap": 4000000})

    def test_it_leaves_and_comes_again_and_ends_at_rest_where_it_began(self):
        from codex_auto_resume import notice_card
        for name in NAMES:
            with self.subTest(name):
                frames = motion_plan.expand(plan_of(name))
                first, last = frames[0], frames[-1]
                self.assertEqual(dict(first.card)["born"], -notice_card.ENTRANCE_MS, "frame 1: the card at rest")
                cards = [dict(frame.card) if frame.card else None for frame in frames]
                gone = cards.index(None)
                self.assertTrue(any(card and card["born"] > 0 for card in cards[gone:]), "and it comes again")
                born = dict(last.card)["born"]
                self.assertGreaterEqual(last.t - born, notice_card.ENTRANCE_MS, "at rest at the end")
                for card in (dict(first.card), dict(last.card)):
                    self.assertEqual((card["hover"], card["pressed"], card["leave"]), (None, None, None))
                self.assertEqual((first.window, first.pointer, first.popup, first.tip),
                                 (last.window, last.pointer, last.popup, last.tip))

    def test_the_loop_is_whole_breaths_for_the_card_s_light_and_the_icon(self):
        from codex_auto_resume import brand, notice_card
        from codex_auto_resume.ui import tray
        for name in NAMES:
            with self.subTest(name):
                plan = plan_of(name)
                end = motion_plan.plan_end(plan)
                self.assertEqual(plan["length"], [end, end])
                self.assertEqual(end % brand.GLOW["waiting_ms"], 0, "the icon's breath is where it began")
                self.assertEqual(tray.icon_frame("watching", 0, 0), tray.icon_frame("watching", end, end),
                                 "three breaths: the end is the start of a sweep, the head at home at the top level")
                frames = motion_plan.expand(plan)
                first, last = dict(frames[0].card), dict(frames[-1].card)
                self.assertEqual((end - last["born"]) % brand.GLOW["waiting_ms"],
                                 (0 - first["born"]) % brand.GLOW["waiting_ms"],
                                 "the card's light is counted from when it came: the same moment of its breath")
                leaves = [dict(frame.card)["leave"] for frame in frames if frame.card and dict(frame.card)["leave"]]
                self.assertEqual(leaves[0], notice_card.HOLD_MS, "it stands as long as the product holds a card")


@unittest.skipUnless(os.name == "nt", "the card is drawn with Windows' GDI+")
class DrawnTests(unittest.TestCase):
    """The plan drawn: the strip, the icon and the card, as make_motion.make lays them, in memory only."""

    @classmethod
    def setUpClass(cls):
        import motion_apng
        cls.plan = plan_of("card-en")
        cls.width, cls.height = cls.plan["canvas"]["size"]
        cls.strip = cls.plan["taskbar"]
        end = motion_plan.plan_end(cls.plan)
        cls.end = end
        frames, _delays, _end = make_motion.schedule(cls.plan, make_motion.icon_moments(cls.plan, end))
        cls.frames = frames

        def near(t):
            return next(frame for frame in frames if frame.t >= t)
        entering = [frame for frame in frames if frame.card and 0 <= frame.t - dict(frame.card)["born"] < 340
                    and dict(frame.card)["born"] > 0]
        cls.picks = {"start": frames[0], "rest": near(3000), "leaving": near(6100), "gone": near(7000),
                     "rising": entering[2], "risen": near(8460 + 340 + 100), "last": frames[-1],
                     "end": frames[-1]._replace(t=end)}
        cls.pictures = {}

        def schedule(plan, also=()):
            chosen = list(cls.picks.values())
            return chosen, [100] * len(chosen), 100 * len(chosen)

        def run(plan, draw, also=()):
            for key, frame in cls.picks.items():
                cls.pictures[key] = draw(frame)
                yield 100, frame.scene, cls.pictures[key]

        def assemble(path, width, height, frames, target=None, cap=None, alpha=False):
            for _frame in frames:
                pass
            return types.SimpleNamespace(size=0, frames=len(cls.picks), ms=0, scenes=[], over_target=False)

        with mock.patch.object(make_motion, "schedule", schedule), mock.patch.object(make_motion, "run", run), \
                mock.patch.object(motion_apng, "assemble", assemble), tempfile.TemporaryDirectory() as work:
            make_motion.make(cls.plan, None, Path(work))
        left = cls.strip["edge"] - cls.strip["icon"]["right"] - cls.strip["icon"]["size"]
        top = cls.strip["top"] + (cls.strip["height"] - cls.strip["icon"]["size"]) // 2
        cls.anchor = (left, top, left + cls.strip["icon"]["size"], top + cls.strip["icon"]["size"])

    def alpha(self, key, x, y):
        return self.pictures[key][(y * self.width + x) * 4 + 3]

    def test_the_taskbar_strip_is_drawn_in_every_frame_opaque_and_its_own_colour_under_everything(self):
        from codex_auto_resume import brand
        colour = tuple(brand.rgb(self.strip["colour"]))
        bottom = self.strip["top"] + self.strip["height"] - 1
        for key, picture in self.pictures.items():
            with self.subTest(key):
                rows = [picture[(y * self.width) * 4 + 3:((y + 1) * self.width) * 4:4]
                        for y in range(self.strip["top"], bottom + 1)]
                self.assertTrue(all(set(row) == {255} for row in rows), "every strip pixel is opaque")
                at = (bottom * self.width + 2) * 4
                self.assertEqual(tuple(picture[at:at + 3]), colour, "and the strip's own colour, past the card's shadow")

    def test_the_icon_is_drawn_on_the_strip_in_every_frame(self):
        left, top, right, bottom = self.anchor
        for key, picture in self.pictures.items():
            with self.subTest(key):
                base = (self.strip["top"] + 2) * self.width * 4 + 2 * 4
                differing = sum(1 for y in range(top, bottom) for x in range(left, right)
                                if tuple(picture[(y * self.width + x) * 4:(y * self.width + x) * 4 + 3])
                                != tuple(picture[base:base + 3]))
                self.assertGreater(differing, 50, "the product's own icon is on the strip")

    def test_the_card_sits_above_the_strip_where_the_product_places_it(self):
        from codex_auto_resume import brand, notice_card
        import motion_card
        gap = int(round(brand.SPACING["m"] * SCALE))
        work = (0, 0, self.strip["edge"], self.strip["top"])
        card = motion_card.CardFrames("en", scale=SCALE, work=work, monitor=(0, 0, self.strip["edge"], self.height),
                                      anchor=self.anchor)
        try:
            wide, tall = card.card.size
            left, top = card.place
        finally:
            card.close()
        centre = (self.anchor[0] + self.anchor[2]) // 2
        self.assertEqual(top + tall, self.strip["top"] - gap, "SPACING m above the strip")
        self.assertEqual(left, min(centre - wide // 2, self.strip["edge"] - gap - wide), "centred on the icon, held inside")
        self.assertEqual(left + wide, self.strip["edge"] - gap, "so its right edge is that gap from the screen's")
        mid = left + wide // 2
        self.assertEqual(self.alpha("rest", mid, top + tall - 1), 255, "the card is opaque, at rest, there")
        self.assertEqual(self.alpha("rest", left + wide - 1, top + tall // 2), 255)
        self.assertTrue(0 < self.alpha("rest", mid, top + tall + 2) < 255, "its shadow lies in the gap, not the card")
        self.assertEqual(self.alpha("rest", mid, 0), 0, "a clear ground above the card's shadow")
        self.assertEqual(self.alpha("gone", mid, top + tall // 2), 0, "no card while it is gone")
        self.assertEqual(self.alpha("risen", mid, top + 60), 255, "and it is there again once it has risen")

    def test_the_card_rises_from_above_the_strip_as_the_product_moves_it_and_never_from_the_canvas_edge(self):
        from codex_auto_resume import notice_card
        import motion_card
        frame = self.picks["rising"]
        born = dict(frame.card)["born"]
        want = notice_card.entrance(frame.t - born)
        self.assertGreater(want.offset, 0, "it is still rising")
        self.assertLessEqual(want.offset * SCALE, self.height - self.strip["top"],
                             "the dip it rises through is the product's RISE, in the gap and a little of the strip")
        left = self.strip["edge"] - 24 - 672
        # part way: the card is dimmer than at rest, and it is not on the canvas's bottom rows
        mid = left + 336
        rising = [self.alpha("rising", mid, y) for y in range(0, self.strip["top"])]
        self.assertTrue(any(0 < value < 255 for value in rising), "faded part way in")
        self.assertEqual(self.alpha("rising", mid, 5), 0, "the clear ground above is clear")

    def test_the_first_picture_and_the_picture_the_loop_comes_back_to_are_the_same(self):
        self.assertEqual(self.pictures["start"], self.pictures["end"],
                         "the card at rest on the strip, its light and the icon where they began")

    def test_the_last_frame_is_the_card_at_rest_and_the_icon_where_it_began_to_the_timer_s_step(self):
        left, top, right, bottom = self.anchor
        one, other = self.pictures["start"], self.pictures["last"]
        differing = [at // 4 for at in range(0, len(one), 4) if one[at:at + 4] != other[at:at + 4]]
        card_rows = range(0, self.strip["top"])
        for position in differing:
            x, y = position % self.width, position // self.width
            self.assertTrue((left <= x < right and top <= y < bottom) or y in card_rows,
                            "only the icon's breath and the card's light differ (%d, %d)" % (x, y))
        light = [position // self.width for position in differing if position // self.width < self.strip["top"]]
        self.assertLess(max(light, default=0) - min(light, default=0), 120, "the card's light band alone")


if __name__ == "__main__":
    unittest.main()
