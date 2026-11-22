"""The tray motion does what the product does as a button goes down, and the popup's buttons answer the pointer
(v0.6.26, audit-apng M8).

- The icon's hover card goes on the icon's WM_LBUTTONDOWN (ui/tray/icon.py `_hide_tip`, before NIN_SELECT opens the
  popup): the picture drew it through the whole press.
- The popup goes as a press goes down anywhere but on itself (ui/popup/messages.py: WA_INACTIVE): the picture kept it
  for the press's 96 ms.
- A pointer over the popup's Pause or Open Dashboard gives that button its hover face, gliding there and back as the
  popup glides it (messages._face_glides); the picture's pointer crossed Open Dashboard with no face.

The plan's checks are pure; the popup's hit test and faces use its own layout and renderer in memory (GDI, nothing on
the screen, nothing written)."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import make_motion  # noqa: E402
import motion_compose  # noqa: E402
import motion_plan  # noqa: E402


def plan(*steps):
    return {"format": motion_plan.FORMAT, "name": "t", "pointer": {"rest": [0, 0]},
            "scenes": [{"id": "S", "steps": list(steps)}]}


class PressOrderTests(unittest.TestCase):
    def test_the_icon_s_button_going_down_takes_its_hover_card_away(self):
        frames = motion_plan.expand(plan({"tip": "show", "hold": 100}, {"press": "tray.icon", "frames": 3, "step": 16},
                                         {"popup": "open", "hold": 50}))
        self.assertEqual([(frame.t, bool(frame.tip), bool(frame.popup)) for frame in frames],
                         [(0, True, False), (100, False, False), (116, False, False), (132, False, False),
                          (148, False, True)])
        self.assertEqual(dict(frames[0].tip)["until"], 100, "told when the press took it away")

    def test_a_press_anywhere_but_on_the_popup_closes_it_as_it_goes_down(self):
        frames = motion_plan.expand(plan({"popup": "open", "hold": 100}, {"press": "popup.switch.1", "frames": 2, "step": 16},
                                         {"press": {"at": [5, 5]}, "frames": 2, "step": 16}, {"hold": 50}))
        self.assertEqual([(frame.t, bool(frame.popup)) for frame in frames],
                         [(0, True), (100, True), (116, True), (132, False), (148, False), (164, False)])

    def test_the_tray_plans_no_longer_close_the_popup_after_the_press(self):
        for name in ("popup-en", "popup-ko"):
            with self.subTest(name):
                loaded = motion_plan.load(make_motion.plan_path(name))
                steps = [step for scene in loaded["scenes"] for step in scene["steps"]]
                self.assertNotIn({"popup": "close", "hold": 400}, steps)
                frames = motion_plan.expand(loaded)
                last = max(f.ripple[1] for f in frames if f.ripple)
                self.assertFalse(next(f for f in frames if f.t == last).popup, "gone with the press's first frame")


class PopupHoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import motion_popup
        cls.popup = motion_popup.PopupFrames("en", scale=2.0)
        cls.buttons = {item["target"]: item["rect"] for item in cls.popup.view()[1]["items"] if item["kind"] == "button"}

    @classmethod
    def tearDownClass(cls):
        cls.popup.close()

    def centre(self, target):
        left, top, right, bottom = self.buttons[target]
        return ((left + right) / 2.0 + self.popup.shift[0], (top + bottom) / 2.0 + self.popup.shift[1])

    def test_the_pointer_over_a_button_is_its_hover_and_elsewhere_nothing_is(self):
        self.assertEqual(set(self.buttons), {("toggle",), ("dashboard",)})
        for target in self.buttons:
            self.assertEqual(self.popup.hovered(self.centre(target)), target)
        self.assertIsNone(self.popup.hovered((1, 1)))
        self.assertIsNone(self.popup.hovered(None))
        x, y = self.centre(("dashboard",))
        self.assertIsNone(self.popup.hovered((x, y), below=400), "the popup still rising: not under the pointer yet")

    def test_a_face_glides_there_and_back_in_brands_transition(self):
        from codex_auto_resume import brand
        plan_ = self.popup.view()[1]
        self.popup._face_states, self.popup._faces = None, {}
        self.assertEqual(self.popup.faces(plan_, None, 0), {}, "the first frame: nothing glides")
        going = self.popup.faces(plan_, ("dashboard",), 100)
        self.assertEqual(set(going), {("dashboard",)})
        self.assertEqual(going[("dashboard",)][1], 0.0, "from where it was")
        partway = self.popup.faces(plan_, ("dashboard",), 180)[("dashboard",)][1]
        self.assertTrue(0.0 < partway < 1.0)
        self.assertEqual(self.popup.faces(plan_, ("dashboard",), 100 + brand.MOTION["transition_ms"]), {}, "arrived")
        back = self.popup.faces(plan_, None, 400)
        self.assertEqual(set(back), {("dashboard",)}, "and back again when the pointer leaves")

    def test_the_tray_motion_s_pointer_crosses_a_button_and_so_gives_it_a_face(self):
        loaded = motion_plan.load(make_motion.plan_path("popup-en"))
        strip = loaded["taskbar"]
        end = motion_plan.plan_end(loaded)
        frames, _held, _end = make_motion.schedule(loaded, make_motion.icon_moments(loaded, end))
        edge = int(strip.get("edge"))
        icon = strip["icon"]
        left = edge - icon["right"] - icon["size"]
        top = strip["top"] + (strip["height"] - icon["size"]) // 2
        work, monitor = (0, 0, edge, strip["top"]), (0, 0, edge, loaded["canvas"]["size"][1])
        at = self.popup.origin(work, monitor, (left, top, left + icon["size"], top + icon["size"]))
        bounds = {name: (x + at[0], y + at[1], w, h) for name, (x, y, w, h) in self.popup.bounds().items()}
        bounds["tray.icon"] = (left, top, icon["size"], icon["size"])
        crossed = set()
        for frame in frames:
            if frame.popup and self.popup.opening(frame)[2]:
                x, y = motion_compose.pointer_at(frame, bounds, (0, 0))
                found = self.popup.hovered((x - at[0], y - at[1]))
                if found is not None:
                    crossed.add(found)
        self.assertIn(("dashboard",), crossed, "the way to the first switch passes over Open Dashboard")


if __name__ == "__main__":
    unittest.main()
