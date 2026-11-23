"""After a click the pointer still rests on what it pressed, so the motions keep its hover there, as the product does
(v0.6.26, review P3): no MouseLeave comes while nothing moves under the pointer (SoftButton.Hover, NavButton). The hover
goes when the pointer moves on, when the page changes under a control of that page, or when the window is opened again;
a tab, a Settings section and the setup window's one primary button stay where they are across a page change. The
plans are expanded here (motion_plan.expand); the setup shim is asked once that a hover left on the Progress page, which
has no primary button, is nothing to note."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import make_install_motion  # noqa: E402
import motion_plan  # noqa: E402

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"


def faces(frames, scene):
    return [(frame.t, dict(frame.window).get("hover"), dict(frame.window).get("pressed"), dict(frame.window).get("page"),
             frame.pointer[0]) for frame in frames if frame.scene == scene]


class PlanTests(unittest.TestCase):
    def test_the_setup_window_s_forward_keeps_its_hover_on_the_next_page(self):
        for name in make_install_motion.PLAN_NAMES:
            with self.subTest(name):
                frames = motion_plan.expand(make_install_motion.load(name))
                options = [face for face in faces(frames, "S2") if face[3] == "options"]
                self.assertTrue(options)
                self.assertTrue(all(face[1] == "button.forward" and face[2] is None for face in options), options)
                moving = [face for face in faces(frames, "S3") if face[4] == "move"]
                self.assertTrue(moving and all(face[1] is None for face in moving[:25]), "the pointer moves on: gone")

    def test_the_readme_keeps_a_pressed_button_s_hover_until_the_pointer_moves(self):
        for name in ("readme-en", "readme-ko"):
            with self.subTest(name):
                frames = motion_plan.expand(motion_plan.load(motion_plan.PLANS / (name + ".json")))
                retry = faces(frames, "S2a")
                after = [face for face in retry if face[2] is None and face[0] > min(f[0] for f in retry if f[2])]
                self.assertTrue(after and all(face[1] == "pending.retry" for face in after), after)
                self.assertTrue(all(face[1] is None for face in faces(frames, "S2b")), "moved on to Why it is waiting")
                tab = [face for face in faces(frames, "S1") if face[3] == "pending"]
                self.assertTrue(tab and all(face[1] == "page.pending" for face in tab), "a tab stays where it is")
                self.assertTrue(all(face[1] is None for face in faces(frames, "S13")), "the window opened again")
                closed = [face for face in faces(frames, "S2c") if face[2] is None and face[0] > max(
                    f[0] for f in faces(frames, "S2c") if f[2] == "dialog.close")]
                self.assertTrue(closed and all(face[1] is None for face in closed), "the dialog it closed is gone")

    def test_a_page_change_takes_a_page_s_button_s_hover_with_it(self):
        plan = {"scenes": [{"id": "A", "steps": [
            {"set": {"page": "pending"}, "hold": 100}, {"hover": "pending.retry", "frames": 2, "step": 16},
            {"press": "pending.retry", "frames": 2, "step": 16}, {"hold": 100},
            {"set": {"page": "history"}, "hold": 100}]}]}
        states = [dict(frame.window) for frame in motion_plan.expand(plan)]
        self.assertEqual(states[-2].get("hover"), "pending.retry", "still on it while its page shows")
        self.assertIsNone(states[-1].get("hover"), "its page gone, its hover with it")


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "the setup window is built with Windows' C# compiler")
class ShimTests(unittest.TestCase):
    def test_a_hover_left_on_the_progress_page_is_nothing_to_note(self):
        with tempfile.TemporaryDirectory(prefix="install-keep-test-") as name:
            work = Path(name)
            exe = make_install_motion.compile_shim(work / "shim")
            plan = make_install_motion.load("install-en")
            data = make_install_motion.job(plan, [], work / "keep" / "frames")
            data["frames"] = [{"index": 0, "page": "welcome", "light": 0, "moment": 0},
                              {"index": 1, "page": "options", "light": 0, "moment": 100, "hover": "button.forward"},
                              {"index": 2, "page": "progress", "progress": 0, "light": 0, "moment": 200,
                               "hover": "button.forward"}]
            result = make_install_motion.render(exe, data, work / "keep")
            self.assertEqual(result["notes"], [])


if __name__ == "__main__":
    unittest.main()
