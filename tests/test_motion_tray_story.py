"""The tray popup's motion picture shows where to click (v0.6.24, the owner's option A of 2026-11-17).

Under the popup the right end of a taskbar is drawn - a plain strip, never a capture of Windows - with the product's tray
icon in its notification area, and the picture tells one story on one clock: the pointer comes to the icon, rests on it,
the icon's hover card appears as the product shows it, a press with a click ring of our own, the card goes and the popup
opens above the strip where the product places it, the switches are turned off and on as before, and the pointer clicks
elsewhere (which closes it) and leaves. The end is the start: no popup and no card.

What the product does, and where it is read (build/motion_popup.py and build/motion_tip.py have the whole of it):
- the hover card comes when the shell says the pointer rests on the icon (NIN_POPUPOPEN: Windows' hover time, 400 ms by
  default - a hold in the plan, since the product has no constant for it), fades in over brand's transition on brand's curve
  with no rise (ui/tray/tipcard.py _appear, _fade_step), and a click hides it at once as the popup comes (clicks.py _select);
- the popup fades in and rises SPACING xs into place over brand's transition (ui/popup/messages.py _start_opening), and is
  placed by ui/popup/placement.place: centred on the icon, SPACING m above the work area, inside it.

The plan's tests are pure; the drawn ones use Windows' GDI+ in memory (nothing is written, nothing is put on the screen). The
pictures themselves are the main session's.
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
import motion_compose  # noqa: E402
import motion_plan  # noqa: E402

NAMES = ("popup-en", "popup-ko")
HOVER_MS = 400            # Windows' default mouse-hover time: how long the pointer rests before the shell says so


def plan_of(name):
    return motion_plan.load(make_motion.plan_path(name))


def beats(frames):
    """The moments (ms) of the story's beats, read from the frames alone."""
    icon = [frame for frame in frames if frame.pointer == ("at", "tray.icon")]
    pressed = [frame for frame in frames if dict(frame.window).get("pressed") == "tray.icon"]
    tip = [frame for frame in frames if frame.tip]
    popup = [frame for frame in frames if frame.popup]
    return {"comes": next(f.t for f in frames if f.pointer[0] == "move" and f.pointer[2] == "tray.icon"),
            "rest": icon[0].t, "card": tip[0].t, "press": pressed[0].t, "release": pressed[-1].t,
            "popup": popup[0].t, "ask": next(f.t for f in popup if dict(f.popup)["busy"]),
            "close": next(f.t for f in frames if f.t > popup[0].t and not f.popup),
            "last_card": tip[-1].t}


class StoryTests(unittest.TestCase):
    def test_the_frame_list_has_the_five_beats_in_order_the_card_before_the_press(self):
        for name in NAMES:
            with self.subTest(name):
                frames = motion_plan.expand(plan_of(name))
                at = beats(frames)
                self.assertLess(at["comes"], at["rest"], "1. the pointer comes to the icon")
                self.assertLess(at["rest"], at["card"], "2. it rests on it, and then the hover card appears")
                self.assertLess(at["card"], at["press"], "the card is on screen before the press")
                self.assertLess(at["press"], at["release"], "3. a press, which lasts")
                self.assertLessEqual(at["release"], at["popup"], "4. the popup opens when the press is let go")
                self.assertLess(at["popup"], at["ask"], "5. then today's story: the switches")
                self.assertLess(at["ask"], at["close"])
                self.assertEqual(frames[-1].pointer, frames[0].pointer, "and the pointer leaves where it came from")
                self.assertTrue(any(frame.ripple and frame.ripple[0] == "tray.icon" for frame in frames),
                                "the press has our own click ring")

    def test_the_hover_card_is_on_screen_only_between_the_rest_and_the_press_and_never_with_the_popup(self):
        for name in NAMES:
            with self.subTest(name):
                frames = motion_plan.expand(plan_of(name))
                at = beats(frames)
                shown = [frame for frame in frames if frame.tip]
                self.assertTrue(shown)
                for frame in frames:
                    self.assertFalse(frame.tip and frame.popup, "the card is never with the popup (%d ms)" % frame.t)
                for frame in shown:
                    self.assertEqual(frame.pointer, ("at", "tray.icon"), "the pointer rests on the icon throughout")
                    self.assertGreaterEqual(frame.t, at["rest"] + HOVER_MS, "not before the shell's hover time")
                    self.assertLessEqual(frame.t, at["release"], "and not after the press is let go (%d ms)" % frame.t)
                self.assertEqual(at["card"], at["rest"] + HOVER_MS,
                                 "it comes after Windows' hover time on the icon, and not at once")
                self.assertTrue(any(frame.t >= at["press"] for frame in shown), "the press is made with the card on screen")
                after = [frame for frame in frames if frame.t > at["last_card"]]
                self.assertFalse(any(frame.tip for frame in after), "and once it is gone it does not come back")

    def test_the_card_fades_in_over_brands_transition_and_goes_at_once_where_the_popup_comes(self):
        from codex_auto_resume import brand
        from codex_auto_resume.ui.popup.motion import GLIDE_FRAME_MS
        for name in NAMES:
            with self.subTest(name):
                frames = motion_plan.expand(plan_of(name))
                at = beats(frames)
                born = dict([f for f in frames if f.tip][0].tip)["born"]
                self.assertEqual(born, at["card"])
                fade = [frame.t for frame in frames if frame.tip and frame.t < born + brand.MOTION["transition_ms"]]
                self.assertEqual(fade, [born + index * GLIDE_FRAME_MS for index in range(len(fade))],
                                 "a frame every 16 ms of the fade, the card's own frame timer")
                self.assertGreaterEqual(len(fade) * GLIDE_FRAME_MS, brand.MOTION["transition_ms"] - GLIDE_FRAME_MS)
                self.assertLessEqual(at["popup"] - at["last_card"], GLIDE_FRAME_MS, "the popup is the very next thing")
                for frame in frames:
                    if frame.tip:
                        self.assertEqual(dict(frame.tip)["until"], at["popup"], "each says when the click took it away")

    def test_the_popup_opens_with_the_products_fade_and_rise_in_frames_of_16_ms(self):
        from codex_auto_resume import brand
        from codex_auto_resume.ui.popup.motion import GLIDE_FRAME_MS
        for name in NAMES:
            with self.subTest(name):
                frames = motion_plan.expand(plan_of(name))
                opened = dict([f for f in frames if f.popup][0].popup)["opened"]
                opening = [frame.t for frame in frames if frame.popup and frame.t < opened + brand.MOTION["transition_ms"]]
                self.assertEqual(opening, [opened + index * GLIDE_FRAME_MS for index in range(len(opening))])
                self.assertGreaterEqual(len(opening), 9, "frames, not a jump")

    def test_the_first_and_last_frames_are_equal_so_it_loops_without_a_jump(self):
        for name in NAMES:
            with self.subTest(name):
                plan = plan_of(name)
                frames = motion_plan.expand(plan)
                first, last = frames[0], frames[-1]
                # A click's ring is remembered by the frames after it (its start), though it has faded after RIPPLE_MS:
                # what is drawn is `ripple_at`, which is nothing at both ends.
                self.assertEqual(first._replace(t=0, scene="", ripple=()), last._replace(t=0, scene="", ripple=()))
                for frame in (first, last):
                    self.assertEqual((frame.popup, frame.tip, frame.card), ((), (), ()), "no popup, no card")
                    self.assertIsNone(motion_plan.ripple_at(frame), "and no click ring")
                self.assertEqual(plan["length"], [13200, 13200], "three breaths: the light and the icon are where they began")
                self.assertEqual(motion_plan.plan_end(plan) % 4400, 0)

    def test_the_icon_s_breath_is_where_it_began_at_the_loop(self):
        from codex_auto_resume.ui import tray
        end = motion_plan.plan_end(plan_of("popup-en"))
        self.assertEqual(tray.icon_frame("watching", 0, 0), tray.icon_frame("watching", end, end),
                         "the end of the picture is the start of a sweep: the same level, the head at home")

    def test_the_pointer_comes_from_off_the_picture_and_leaves_by_clicking_on_the_strip(self):
        for name in NAMES:
            with self.subTest(name):
                plan = plan_of(name)
                strip = plan["taskbar"]
                frames = motion_plan.expand(plan)
                at = beats(frames)
                rest = plan["pointer"]["rest"]
                self.assertGreater(rest[0], plan["canvas"]["size"][0], "off the canvas, right of it")
                clicks = sorted({frame.ripple for frame in frames if frame.ripple}, key=lambda ripple: ripple[1])
                away = dict(clicks[-1][0])["at"]
                self.assertTrue(strip["top"] < away[1] < strip["top"] + strip["height"], "on the strip")
                icon_left = strip["edge"] - strip["icon"]["right"] - strip["icon"]["size"]
                self.assertLess(away[0], icon_left, "left of the icon: nothing of ours")
                self.assertGreater(clicks[-1][1], at["ask"], "after the story, and it is that click that closes the popup")
                shut = next(frame for frame in frames if frame.t > at["ask"] and not frame.popup)
                self.assertGreater(shut.t, clicks[-1][1], "the popup goes when it is clicked elsewhere (WM_ACTIVATE), at once")


class StepTests(unittest.TestCase):
    def plan(self, *steps):
        return {"format": "car-motion/1", "name": "t", "scenes": [{"id": "S", "steps": list(steps)}]}

    def test_the_hover_card_is_shown_once_and_never_with_the_popup(self):
        for steps in ([{"tip": "hide"}], [{"tip": "show"}, {"tip": "show"}], [{"popup": "open"}, {"tip": "show"}],
                      [{"tip": "maybe"}], [{"tip": "show", "popup": "open"}]):
            with self.subTest(steps), self.assertRaises(motion_plan.PlanError):
                motion_plan.check(self.plan(*steps, {"hold": 100}))

    def test_a_click_takes_the_card_away_at_once_as_the_popup_comes_and_each_frame_is_told_when(self):
        frames = motion_plan.expand(self.plan(
            {"tip": "show", "frames": 3, "step": 16, "hold": 100}, {"popup": "open", "frames": 2, "step": 16},
            {"hold": 50}))
        self.assertEqual([(frame.t, bool(frame.tip), bool(frame.popup)) for frame in frames],
                         [(0, True, False), (16, True, False), (32, True, False), (148, False, True),
                          (164, False, True), (180, False, True)])
        self.assertEqual({dict(frame.tip)["until"] for frame in frames if frame.tip}, {148})
        self.assertEqual(dict(frames[0].tip)["born"], 0)

    def test_a_hover_card_nothing_ever_takes_away_has_no_end(self):
        frames = motion_plan.expand(self.plan({"tip": "show", "hold": 100}, {"tip": "hide", "hold": 100}))
        self.assertEqual([dict(frame.tip) if frame.tip else None for frame in frames], [{"born": 0}, None])

    def test_a_step_with_frames_draws_each_and_waits_after_them_only_as_long_as_it_says(self):
        frames = motion_plan.expand(self.plan({"popup": "open", "frames": 4, "step": 16, "hold": 20}, {"hold": 10}))
        self.assertEqual([frame.t for frame in frames], [0, 16, 32, 48, 84])

    def test_the_icon_is_a_target_the_pointer_can_go_to_and_press(self):
        frames = motion_plan.expand(self.plan({"move": "tray.icon", "frames": 3, "step": 16},
                                              {"press": "tray.icon", "frames": 2, "step": 16}, {"hold": 20}))
        self.assertEqual(frames[0].pointer[1:3], ((("at", (0, 0)),), "tray.icon"))
        self.assertEqual([dict(frame.window).get("pressed") for frame in frames], [None, None, None, "tray.icon",
                                                                                   "tray.icon", None])


class ComposeTests(unittest.TestCase):
    def test_the_strip_on_a_clear_canvas_is_opaque_and_leaves_what_is_above_it_clear(self):
        picture = bytearray(8 * 6 * 4)
        motion_compose.draw_strip(picture, 8, 6, 4, 2, (238, 240, 243))
        self.assertEqual(tuple(picture[(4 * 8) * 4:(4 * 8) * 4 + 4]), (238, 240, 243, 255))
        self.assertEqual(tuple(picture[(5 * 8 + 7) * 4:(5 * 8 + 7) * 4 + 4]), (238, 240, 243, 255))
        self.assertEqual(set(picture[:(4 * 8) * 4]), {0})

    def test_a_layer_over_nothing_is_copied_and_at_an_alpha_it_is_as_clear_as_the_alpha_says(self):
        layer = bytes((10, 20, 30, 255, 10, 20, 30, 128, 0, 0, 0, 0, 90, 90, 90, 255))        # 2 x 2
        picture = bytearray(4 * 3 * 4)
        motion_compose.lay_rgba(picture, 4, 3, layer, 2, 1, 1)
        self.assertEqual(tuple(picture[(1 * 4 + 1) * 4:(1 * 4 + 1) * 4 + 8]), (10, 20, 30, 255, 10, 20, 30, 128))
        self.assertEqual(tuple(picture[(2 * 4 + 2) * 4:(2 * 4 + 2) * 4 + 4]), (90, 90, 90, 255))
        faded = bytearray(4 * 3 * 4)
        motion_compose.lay_rgba(faded, 4, 3, layer, 2, 1, 1, alpha=51)
        self.assertEqual(faded[(1 * 4 + 1) * 4 + 3], 51)
        self.assertEqual(faded[(1 * 4 + 2) * 4 + 3], (128 * 51 + 127) // 255)
        self.assertEqual(faded[(1 * 4 + 1) * 4:(1 * 4 + 1) * 4 + 3], bytes((10, 20, 30)), "its colour is its own")
        untouched = bytearray(4 * 3 * 4)
        motion_compose.lay_rgba(untouched, 4, 3, layer, 2, 1, 1, alpha=0)
        self.assertEqual(set(untouched), {0})

    def test_a_layer_over_the_strip_is_blended_where_it_covers_and_the_strip_stays_opaque(self):
        picture = bytearray(4 * 2 * 4)
        motion_compose.draw_strip(picture, 4, 2, 0, 2, (200, 200, 200))
        layer = bytes((0, 0, 0, 255, 0, 0, 0, 51, 0, 0, 0, 0, 0, 0, 0, 0))        # 4 x 1
        motion_compose.lay_rgba(picture, 4, 2, layer, 4, 0, 1)
        self.assertEqual(tuple(picture[(1 * 4) * 4:(1 * 4) * 4 + 4]), (0, 0, 0, 255), "opaque covers")
        self.assertEqual(tuple(picture[(1 * 4 + 1) * 4:(1 * 4 + 1) * 4 + 4]), (160, 160, 160, 255), "a fifth covers a fifth")
        self.assertEqual(tuple(picture[(1 * 4 + 2) * 4:(1 * 4 + 2) * 4 + 4]), (200, 200, 200, 255), "clear leaves it")

    def test_what_falls_outside_the_canvas_is_cut_off_and_nothing_is_written_past_it(self):
        layer = bytes((1, 2, 3, 255)) * 9
        picture = bytearray(3 * 3 * 4)
        motion_compose.lay_rgba(picture, 3, 3, layer, 3, 2, 2)
        self.assertEqual(tuple(picture[(2 * 3 + 2) * 4:(2 * 3 + 2) * 4 + 4]), (1, 2, 3, 255))
        self.assertEqual(sum(1 for value in picture[3::4] if value), 1)
        motion_compose.lay_rgba(picture, 3, 3, layer, 3, -2, -2)
        self.assertEqual(tuple(picture[0:4]), (1, 2, 3, 255))

    def test_the_icon_s_face_is_a_soft_rounded_square_that_stops_at_its_edge(self):
        picture = bytearray(bytes((238, 240, 243, 255)) * (20 * 20))
        motion_compose.draw_face(picture, 20, 20, 4, 4, 12, 12, 4.0, (0, 0, 0), 0.5)
        centre = tuple(picture[(10 * 20 + 10) * 4:(10 * 20 + 10) * 4 + 4])
        self.assertEqual(centre[3], 255)
        self.assertLess(centre[0], 238, "darker under the face")
        self.assertEqual(tuple(picture[(2 * 20 + 2) * 4:(2 * 20 + 2) * 4 + 4]), (238, 240, 243, 255), "and not outside it")
        corner = tuple(picture[(4 * 20 + 4) * 4:(4 * 20 + 4) * 4 + 3])
        self.assertGreater(corner[0], centre[0], "the corner is rounded off: less of it covers there")


@unittest.skipUnless(os.name == "nt", "the popup and the card are drawn with Windows' GDI+")
class DrawnTests(unittest.TestCase):
    """The plan drawn: the strip, the hover card and the popup, as make_motion.make lays them, in memory only."""

    @classmethod
    def setUpClass(cls):
        import motion_apng
        import motion_popup
        cls.plan = plan_of("popup-en")
        cls.width, cls.height = cls.plan["canvas"]["size"]
        cls.strip = cls.plan["taskbar"]
        end = motion_plan.plan_end(cls.plan)
        cls.frames, _delays, _end = make_motion.schedule(cls.plan, make_motion.icon_moments(cls.plan, end))
        at = beats(cls.frames)
        cls.at = at

        def near(t):
            return next(frame for frame in cls.frames if frame.t >= t)
        picks = {"start": near(0), "waiting": near(at["rest"] + 200), "fading": near(at["card"] + 80),
                 "card": near(at["card"] + 600), "press": near(at["press"] + 32), "opening": near(at["popup"] + 64),
                 "open": near(at["popup"] + 600), "closed": near(at["close"] + 200), "last": cls.frames[-1]}
        cls.picks = picks
        cls.pictures = {}

        def schedule(plan, also=()):
            chosen = list(picks.values())
            return chosen, [100] * len(chosen), 100 * len(chosen)

        def run(plan, draw, also=()):
            for key, frame in picks.items():
                cls.pictures[key] = draw(frame)
                yield 100, frame.scene, cls.pictures[key]

        def assemble(path, width, height, frames, target=None, cap=None, alpha=False):
            for _frame in frames:
                pass
            return types.SimpleNamespace(size=0, frames=len(picks), ms=0, scenes=[], over_target=False)

        with mock.patch.object(make_motion, "schedule", schedule), mock.patch.object(make_motion, "run", run), \
                mock.patch.object(motion_apng, "assemble", assemble), \
                mock.patch.object(motion_popup.PopupFrames, "is_the_still", return_value=True), \
                tempfile.TemporaryDirectory() as work:
            make_motion.make(cls.plan, None, Path(work))
        cls.popup = motion_popup.PopupFrames("en", scale=2.0)
        end = cls.strip["edge"]
        cls.work, cls.monitor = (0, 0, end, cls.strip["top"]), (0, 0, end, cls.height)
        size, size_icon = cls.strip["icon"]["size"], cls.strip["icon"]["right"]
        left = end - size_icon - size
        top = cls.strip["top"] + (cls.strip["height"] - size) // 2
        cls.anchor = (left, top, left + size, top + size)

    @classmethod
    def tearDownClass(cls):
        cls.popup.close()

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
                self.assertEqual(tuple(picture[at:at + 3]), colour, "and the strip's own colour, past the popup's shadow")

    def test_the_icon_is_drawn_on_the_strip_in_every_frame(self):
        left, top, right, bottom = self.anchor
        for key, picture in self.pictures.items():
            with self.subTest(key):
                differing = 0
                for y in range(top, bottom):
                    for x in range(left, right):
                        at = (y * self.width + x) * 4
                        differing += tuple(picture[at:at + 3]) != tuple(
                            picture[(self.strip["top"] + 2) * self.width * 4 + 2 * 4:][:3])
                self.assertGreater(differing, 50, "the product's own icon is on the strip")

    def test_the_hover_card_is_drawn_only_in_the_frames_between_the_rest_and_the_press(self):
        import motion_tip
        tip = motion_tip.TipFrames("en", scale=2.0, work=self.work, monitor=self.monitor, box=self.anchor)
        try:
            plan, _light, (x, y) = tip.reading(0)
        finally:
            tip.close()
        centre = (x + plan["size"][0] // 2, y + plan["size"][1] // 2)
        for key in ("start", "waiting", "closed", "last"):
            self.assertEqual(self.alpha(key, *centre), 0, "no card in %s" % key)
        self.assertEqual(self.alpha("card", *centre), 255, "the card is there, opaque, once it has faded in")
        self.assertEqual(self.alpha("press", *centre), 255, "and while it is pressed")
        self.assertTrue(0 < self.alpha("fading", *centre) < 255, "it is part way while it fades in")

    def test_the_hover_card_stands_beside_the_icon_on_the_taskbar_s_side_as_the_product_places_it(self):
        from codex_auto_resume.ui.tray.tipplan import TIP_GAP
        import motion_tip
        tip = motion_tip.TipFrames("en", scale=2.0, work=self.work, monitor=self.monitor, box=self.anchor)
        try:
            plan, _light, (x, y) = tip.reading(0)
        finally:
            tip.close()
        width, height = plan["size"]
        gap = TIP_GAP * 2
        self.assertEqual(y + height, self.strip["top"] - gap, "TIP_GAP above the taskbar")
        centre = (self.anchor[0] + self.anchor[2]) // 2
        self.assertEqual(x, min(centre - width // 2, self.strip["edge"] - gap - width),
                         "centred on the icon, inside the work area")
        self.assertEqual(x + width, self.strip["edge"] - gap, "the icon is at the end of the strip, so the work area decides")

    def test_the_popup_sits_above_the_strip_its_edge_aligned_as_the_product_places_it(self):
        from codex_auto_resume import brand
        gap = int(round(brand.SPACING["m"] * 2.0))
        origin = self.popup.origin(self.work, self.monitor, self.anchor)
        card = self.popup.view()[1]["card"]
        wide, tall = card[2] - card[0], card[3] - card[1]
        left, top = origin[0] + self.popup.pad, origin[1] + self.popup.pad       # the card's own corner on the canvas
        centre = (self.anchor[0] + self.anchor[2]) // 2
        self.assertEqual(top + tall, self.strip["top"] - gap, "SPACING m above the strip: the card's own edge")
        self.assertEqual(left, min(centre - wide // 2, self.strip["edge"] - gap - wide),
                         "centred on the icon, and held inside the work area by SPACING m")
        self.assertEqual(left + wide, self.strip["edge"] - gap, "so its right edge is that gap from the screen's")
        self.assertGreaterEqual(min(origin), 0, "nothing of the card's shadow is cut off")
        self.assertLessEqual(origin[0] + self.popup.size[0], self.width)
        self.assertLessEqual(origin[1] + self.popup.size[1], self.height)
        # And it is that card that is drawn there, opaque, with the gap clear of it but for its shadow.
        mid = left + wide // 2
        self.assertEqual(self.alpha("open", mid, top + tall - 1), 255)
        self.assertTrue(0 < self.alpha("open", mid, top + tall + 2) < 255, "its shadow, not the card")
        self.assertEqual(self.alpha("open", left + wide - 1, top + tall // 2), 255)

    def test_the_popup_is_drawn_only_between_the_click_and_the_click_elsewhere_and_fades_in_on_the_way(self):
        origin = self.popup.origin(self.work, self.monitor, self.anchor)
        card = self.popup.view()[1]["card"]
        centre = (origin[0] + self.popup.pad + (card[2] - card[0]) // 2, origin[1] + self.popup.pad + 40)
        for key in ("start", "waiting", "fading", "card", "press", "closed", "last"):
            self.assertEqual(self.alpha(key, *centre), 0, "no popup in %s" % key)
        self.assertEqual(self.alpha("open", *centre), 255)
        self.assertTrue(0 < self.alpha("opening", *centre) < 255, "part way while it opens")

    def test_the_first_and_the_last_picture_are_the_empty_strip_with_only_the_icon_moving(self):
        one, other = self.pictures["start"], self.pictures["last"]
        self.assertEqual(len(one), self.width * self.height * 4)
        left, top, right, bottom = self.anchor
        changed = [at // 4 for at in range(0, len(one), 4) if one[at:at + 4] != other[at:at + 4]]
        for position in changed:
            x, y = position % self.width, position // self.width
            self.assertTrue(left <= x < right and top <= y < bottom, "only the icon's own breath differs (%d, %d)" % (x, y))


if __name__ == "__main__":
    unittest.main()
