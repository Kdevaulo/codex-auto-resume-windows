"""What opens and closes on its own timer is drawn at each step of its fade, and the window's answers are its own
(v0.6.26, audit-apng M3, M4, M5, M7).

- M3: the Timeline dialog fades in over brand's transition once painted (SoftDialog.OpenFade, FadeStep: 255 * Motion.Ease),
  its own corner's edge and shadow with it, and the veil under it with it (DialogVeil at its fullest times the dialog's
  alpha, gui-audit D9); it came whole in one frame.
- M4: the Pending row menu fades in and rises into place (SoftMenuLayer.Open, Tick), and on Escape its last picture fades
  out over brand's press time (SoftLayerFade); it came and went in one frame.
- M5: the Interface language drop-down opens as the button goes down (SoftCombo: WM_LBUTTONDOWN), looks open while its
  list is - its edge a step darker, its chevron turned (FaceWanted, chevron) - takes its hover face (faceHover), and its
  list's last picture fades out as a row is chosen (SoftDropList.FadeOut); the picture pressed it for 128 ms first, never
  turned the chevron, and closed the list in one frame.
- M7: Retry now's answer is taken as the window takes it - its own RetryNow, answered from the pinned installation's
  reply - so the note under the list says what the product says; the picture showed nothing.

The plan's tests are pure; the render mode's are read from its source (nothing is drawn here)."""
from __future__ import annotations

import inspect
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import guiscan  # noqa: E402
import make_motion  # noqa: E402
import motion_plan  # noqa: E402
from motion_plan import PlanError  # noqa: E402


def plan_of(*steps):
    plan = {"format": motion_plan.FORMAT, "name": "t", "locale": "en", "pointer": {"rest": [0, 0]},
            "scenes": [{"id": "A", "steps": list(steps)}]}
    motion_plan.check(plan)
    return plan


def state(frame) -> dict:
    return motion_plan.thawed(frame.window)


def readme(name="readme-en"):
    return motion_plan.load(make_motion.plan_path(name))


class FadeMomentTests(unittest.TestCase):
    def test_a_fade_steps_by_its_own_timer_for_brands_times(self):
        from codex_auto_resume import brand
        self.assertEqual((brand.MOTION["transition_ms"], brand.MOTION["press_ms"]), (160, 80))
        self.assertEqual(motion_plan.FADE_STEP, 15, "Motion.Interval")
        self.assertEqual(motion_plan.opening_moments(), list(range(0, 160, 15)))
        self.assertEqual(motion_plan.opening_length(), 165)
        self.assertEqual(motion_plan.closing_moments(), [0, 15, 30, 45, 60, 75])
        self.assertEqual(motion_plan.closing_length(), 90)


class MenuTests(unittest.TestCase):
    def test_the_row_menu_fades_in_then_out_with_its_item_still_lit(self):
        frames = motion_plan.expand(plan_of({"right": "task.0", "frames": 2, "step": 16, "hold": 100},
                                            {"hover": "menu.4", "frames": 1, "step": 40}, {"dismiss": "menu", "hold": 50}))
        menus = [(frame.t, state(frame).get("menu"), state(frame).get("hover")) for frame in frames]
        opening = [(t, menu) for t, menu, _hover in menus if menu and "appear_ms" in menu]
        self.assertEqual(opening, [(32 + offset, {"at": "task.0", "appear_ms": offset})
                                   for offset in motion_plan.opening_moments()])
        self.assertIn((197, {"at": "task.0"}, None), menus, "then at rest")
        closing = [(t, menu, hover) for t, menu, hover in menus if menu and "close_ms" in menu]
        self.assertEqual([t for t, _m, _h in closing], [337 + offset for offset in motion_plan.closing_moments()])
        self.assertTrue(all(hover == "menu.4" for _t, _m, hover in closing), "its last picture, the item in hand lit")
        self.assertEqual(menus[-1], (427, None, None), "gone, and the item with it")

    def test_the_readme_s_menu_scene_keeps_its_length(self):
        for name in ("readme-en", "readme-ko"):
            with self.subTest(name):
                steps = [step for scene in readme(name)["scenes"] if scene["id"] == "S1m" for step in scene["steps"]]
                self.assertIn({"right": "task.0", "frames": 8, "step": 16, "hold": 500 - motion_plan.opening_length()},
                              steps)
                self.assertIn({"dismiss": "menu", "hold": 700 - motion_plan.closing_length()}, steps)


class DropDownTests(unittest.TestCase):
    def test_the_list_opens_as_the_button_goes_down_and_fades_out_as_a_row_is_chosen(self):
        frames = motion_plan.expand(plan_of({"move": "setting.interface_language", "frames": 2, "step": 16},
                                            {"open": "setting.interface_language", "frames": 11, "step": 15, "hold": 100},
                                            {"rows": ["en", "ko"], "step": 50}, {"choose": "ko", "hold": 60}))
        first = next(frame for frame in frames if "droplist" in state(frame))
        self.assertEqual(first.ripple, ("setting.interface_language", first.t), "the press's ring with the list")
        self.assertEqual(state(first)["droplist"]["appear_ms"], 0)
        closing = [frame for frame in frames if "close_ms" in (state(frame).get("droplist") or {})]
        self.assertEqual([state(frame)["droplist"]["close_ms"] for frame in closing], motion_plan.closing_moments())
        for frame in closing:
            self.assertEqual(state(frame)["combo"], {"interface_language": "ko"}, "the value shown at once")
            self.assertEqual(frame.pointer, ("at", "row.ko"), "the pointer stays where it pressed")
        self.assertNotIn("droplist", state(frames[-1]))
        self.assertEqual(frames[-1].pointer, ("at", "row.ko"))

    def test_the_readme_opens_the_list_on_the_press_s_first_frame(self):
        for name in ("readme-en", "readme-ko"):
            with self.subTest(name):
                steps = [step for scene in readme(name)["scenes"] if scene["id"] == "S11" for step in scene["steps"]]
                self.assertNotIn("press", {key for step in steps for key in step})
                self.assertEqual(steps[-1], {"open": "setting.interface_language", "hold": 1100 + 8 * 16,
                                             "frames": 11, "step": 15})

    def test_the_render_gives_the_drop_down_its_open_look_and_its_hover(self):
        opened = guiscan.member_body("SettingsForm", "ComboLooksOpen")
        self.assertIn('GetField("drop", own)', opened)
        self.assertIn('GetField("chevron", own)', opened)
        self.assertIn("chevron.Jump(open ? 1.0 : 0.0)", opened)
        self.assertIn('RenderMs(listed, "close_ms") < 0', guiscan.member_body("SettingsForm", "RenderComboOpen"),
                      "a closing list leaves the drop-down closed, as CloseList does at once")
        # v0.6.26 (audit-apng M6): the render face's hover is the control's own change, found in RenderHover.
        self.assertIn('type.GetField("faceHover", RenderOwn)', guiscan.member_body("SettingsForm", "RenderHover"))
        self.assertIn("RenderComboOpen(Map(frame, \"droplist\"));", guiscan.member_body("SettingsForm", "RenderState"))
        self.assertIn("private SoftDropList drop;", guiscan.read("gui/SoftCombo.cs"))
        self.assertIn("private readonly Transition chevron;", guiscan.read("gui/SoftCombo.cs"))
        self.assertIn("private bool faceHover;", guiscan.read("gui/SoftCombo.cs"))


class RenderFadeTests(unittest.TestCase):
    def test_the_menu_and_the_list_fade_as_their_own_painters_fade(self):
        opening = guiscan.member_body("SettingsForm", "RenderOpening")
        self.assertIn("appear / Math.Max(1, Motion.Duration)", opening)
        self.assertIn("(int)Math.Round(255 * eased)", opening)
        self.assertIn("(int)Math.Round(Soft.Px(Brand.SpaceXs) * (1.0 - eased))", opening)
        closing = guiscan.member_body("SettingsForm", "RenderClosing")
        self.assertIn("ms / Math.Max(1, Motion.Press)", closing)
        self.assertIn("from * (1.0 - Motion.Ease(", closing)
        menu = guiscan.member_body("SettingsForm", "RenderMenu")
        self.assertIn('RenderMs(menu, "close_ms")', menu)
        self.assertIn('RenderOpening(RenderMs(menu, "appear_ms"), out alpha, out rise);', menu)
        self.assertIn("LayFaded(picture, renderMenuLast, renderMenuLastAt, RenderClosing(closing, renderMenuLastAlpha));", menu)
        listed = guiscan.member_body("SettingsForm", "RenderDropList")
        self.assertIn("LayFaded(picture, renderListLast, renderListLastAt, RenderClosing(closing, renderListLastAlpha));",
                      listed)
        for product, words in (("SoftMenuLayer", "alpha = t >= 1.0 ? 255 : (int)Math.Round(255 * eased);"),
                               ("SoftMenuLayer", "rise = t >= 1.0 ? 0 : (int)Math.Round(Soft.Px(Brand.SpaceXs) * (1.0 - eased));"),
                               ("SoftLayerFade", "Lay((int)Math.Round(from * (1.0 - Motion.Ease(t))));"),
                               ("SoftDropList", "alpha = (int)Math.Round(closingFrom * (1.0 - Motion.Ease(part)));")):
            self.assertIn(words, guiscan.type_body(product), "the product still fades as the picture does: %s" % product)

    def test_the_dialog_and_its_veil_fade_in_together(self):
        alpha = guiscan.member_body("SettingsForm", "RenderDialogAlpha")
        self.assertIn("appear / Math.Max(1, Motion.Duration)", alpha)
        self.assertIn("(int)Math.Round(255 * Motion.Ease(t))", alpha)
        self.assertIn("SetFade((int)Math.Round(255 * Motion.Ease(t)));", guiscan.type_body("SoftDialog"))
        dialog = guiscan.member_body("SettingsForm", "RenderDialog")
        self.assertIn('int fade = RenderDialogAlpha(RenderMs(dialog, "appear_ms"));', dialog)
        self.assertIn("PaintVeil(picture, (int)Math.Round(DialogVeil.FullNow * fade / 255.0));", dialog)
        self.assertIn("Blend(picture, under, fade);", dialog)

    def test_the_dialog_opens_with_a_step_of_its_own_and_closes_with_a_cut(self):
        frames = motion_plan.expand(plan_of({"set": {"page": "pending", "selected": {"pending": 0}}, "hold": 50},
                                            {"dialog": {"kind": "timeline"}, "hold": 100},
                                            {"set": {"dialog": None}, "hold": 50}))
        dialogs = [(frame.t, state(frame).get("dialog")) for frame in frames]
        self.assertEqual([t for t, dialog in dialogs if dialog and "appear_ms" in dialog],
                         [50 + offset for offset in motion_plan.opening_moments()])
        self.assertIn((215, {"kind": "timeline"}), dialogs)
        self.assertEqual(dialogs[-1], (315, None))
        for bad in ({"dialog": None}, {"dialog": {"kind": "settings"}}):
            with self.subTest(bad), self.assertRaises(PlanError):
                plan_of(dict(bad, hold=10))

    def test_the_readme_s_timeline_fades_in_and_keeps_its_length(self):
        steps = [step for scene in readme()["scenes"] if scene["id"] == "S2c" for step in scene["steps"]]
        self.assertIn({"dialog": {"kind": "timeline"}, "hold": 1600 - motion_plan.opening_length()}, steps)
        self.assertNotIn({"set": {"dialog": {"kind": "timeline"}}, "hold": 1600}, steps)


class AnsweredTests(unittest.TestCase):
    def test_retry_now_s_answer_comes_as_the_busy_look_ends_and_is_taken_once(self):
        for name in ("readme-en", "readme-ko"):
            with self.subTest(name):
                frames = motion_plan.expand(readme(name))
                answered = [frame for frame in frames if state(frame).get("answered") == "retry-now"]
                self.assertTrue(answered)
                first = answered[0]
                self.assertEqual(first.scene, "S2a")
                self.assertEqual(state(first)["page"], "pending")
                self.assertNotIn("busy", state(first), "the answer ends the call in flight")
                self.assertEqual(state(first)["selected"], {"pending": 0}, "on the row it was asked for")
                self.assertTrue(all(state(frame)["page"] == "pending" for frame in answered),
                                "another page leaves it behind")
        with self.assertRaises(PlanError):
            plan_of({"set": {"answered": "pause"}, "hold": 10})

    def test_the_render_takes_the_answer_through_the_window_s_own_retry_now(self):
        body = guiscan.member_body("SettingsForm", "RenderAnswered")
        self.assertIn('if (command != "retry-now")', body)
        self.assertIn("RetryNow();", body)
        self.assertIn('Ok(RenderAnswer("retry-now", IdArgument(row)))', body)
        self.assertIn('RenderAnswered(Str(frame, "answered"), writer);', guiscan.member_body("SettingsForm", "RenderState"))
        self.assertIn('pendingNoteText = check == "asked"', guiscan.member_body("SettingsForm", "RetryNow"))

    def test_the_pinned_installation_is_asked_retry_now_after_every_read(self):
        import motion_window
        source = inspect.getsource(motion_window.answers)
        self.assertIn('shots.ask(surface, "retry-now", argument)', source)
        self.assertLess(source.index('"preview"') if '"preview"' in source else source.index("preview_request"),
                        source.index('"retry-now", argument'), "asked last: every read before it is as it was")
        self.assertIn('if reply.get("ok"):', source, "a refusal is left out, never a failed picture")


if __name__ == "__main__":
    unittest.main()
