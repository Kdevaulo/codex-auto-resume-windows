"""The Dashboard's render mode (gui/WindowRender.cs) and its driver (build/motion_window.py).

The window draws the README's motion picture itself, offscreen: built as the layout audit builds it, a child of
Windows' parking window that is never on the screen, answered from canned replies, put in each frame's state and
drawn into a bitmap. These hold the mode to never being a person's window (it takes a job only beside a capture's
event), to never asking anything of an installation or starting anything (its bridge answers from the job and refuses
the rest; it never reopens itself), and - in one small render of the real window - to drawing what each state asks:
a hover only on the control hovered, a drop list where the drop-down opens, a scroll the wheel's own distance.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import guiscan  # noqa: E402
import motion_plan  # noqa: E402
import motion_window  # noqa: E402


class SourceTests(unittest.TestCase):
    def test_the_render_mode_is_compiled_with_the_window(self):
        self.assertIn("gui/WindowRender.cs", guiscan.group("settings"))

    def test_a_job_is_taken_only_beside_a_capture_s_event(self):
        render = guiscan.read("gui/WindowRender.cs")
        job = render[render.index("internal static string RenderJob"):render.index("// The replies the window")]
        self.assertLess(job.index("if (Soft.StillReady == null) return null;"), job.index("CODEX_AR_RENDER_PLAN"))
        main = guiscan.member_body("Program", "Main")
        self.assertIn("if (renderJob != null) return SettingsForm.RenderFrames(renderJob);", main)
        self.assertLess(main.index("SettingsForm.RenderJob"), main.index("bridge.Available"),
                        "the render mode runs before anything looks for an installation")

    def test_the_bridge_answers_from_the_job_and_starts_no_process(self):
        bridge = guiscan.type_body("PersistentBridge")
        self.assertIn("internal static Func<string, string, Dictionary<string, object>> Answers;", bridge)
        for name in ("CallCounted", "CallOnce"):
            body = bridge[bridge.index(" " + name + "(string command"):]
            body = body[:body.index("\n        }\n")]
            with self.subTest(name):
                self.assertIn("if (Answers != null) return Answers(command, argument);", body)
                self.assertLess(body.index("Answers != null"), body.index("once.Call(") if "once.Call(" in body
                                else body.index("Ask("))
        render = guiscan.read("gui/WindowRender.cs")
        self.assertNotIn("Process.Start", render)
        self.assertNotIn("ProcessStartInfo", render)
        answer = render[render.index("RenderAnswer(string command"):render.index("private static string Compact")]
        self.assertIn('refused["ok"] = false;', answer)

    def test_the_drop_list_is_drawn_fading_in_and_rising_as_show_animates_it(self):
        """The open list fades in and rises into place over the transition (SoftDropList.Show, Tick): a frame
        `appear_ms` into it is drawn at the list's own alpha and rise, by the list's own arithmetic."""
        combo = guiscan.read("gui/SoftCombo.cs")
        paint = combo[combo.index("internal Bitmap PaintAt(int hovered, Rectangle area, double appearing)"):]
        paint = paint[:paint.index("Render();")]
        tick = combo[combo.index("private void Tick()"):]
        tick = tick[:tick.index("Push();")]
        for line in ("alpha = t >= 1.0 ? 255 : (int)Math.Round(255 * eased);",
                     "rise = t >= 1.0 ? 0 : (int)Math.Round(Soft.Px(Brand.SpaceXs) * (1.0 - eased));"):
            self.assertIn(line, tick, "Tick's own arithmetic moved")
            self.assertIn(line, paint, "the render draws the list another way than Tick moves it")
        render = guiscan.read("gui/WindowRender.cs")
        self.assertIn('listed.TryGetValue("appear_ms", out appearing)', render)
        self.assertIn("list.PaintAt(hovered, area, appear)", render)
        self.assertIn("matrix.Matrix33 = list.Alpha / 255f;", render)
        self.assertIn("int rise = list.CardOnScreen.Y - card.Y;", render)

    def test_a_rendered_window_never_reopens_itself(self):
        self.assertIn("rendering", guiscan.member_body("SettingsForm", "Reopen").split("\n", 3)[2])

    def test_the_light_s_moment_can_be_set_per_frame(self):
        self.assertRegex(guiscan.read("gui/SoftTheme.cs"), r"internal static double StillLightMs = ReadStillLight\(\);")


class JobTests(unittest.TestCase):
    def plan(self):
        plan = {"format": motion_plan.FORMAT, "name": "t", "locale": "en", "canvas": {"theme": "light"},
                "scenes": [{"id": "A", "steps": [{"move": "page.history", "frames": 2}, {"hover": "page.history"},
                                                 {"set": {"page": "settings", "section": "general"}},
                                                 {"open": "setting.interface_language"}, {"rows": ["en"]}]}]}
        motion_plan.check(plan)
        return plan

    def test_each_frame_is_its_state_and_the_moment_of_its_lights(self):
        plan = self.plan()
        frames = motion_plan.expand(plan)
        job = motion_window.job(plan, frames, Path("out"), forms={"en": {"answers": []}})
        self.assertEqual([frame["index"] for frame in job["frames"]], list(range(len(frames))))
        self.assertEqual([frame["light"] for frame in job["frames"]], [frame.t for frame in frames])
        self.assertEqual(job["frames"][2]["hover"], "page.history")
        self.assertEqual(job["frames"][-1]["droplist"], {"field": "interface_language", "hover": "en"})
        self.assertEqual(job["targets"], ["page.history", "row.en"])
        self.assertEqual((job["theme"], job["design"]), ("light", "soft"))

    def test_replies_keep_the_usage_reading_the_captured_pictures_show(self):
        """The captures write the envelope's heartbeat (test_still_usage), so the motion keeps its usage reading
        as the pinned installation gives it: nothing is taken out of a reply."""
        replies = {item["command"]: item["reply"] for item in motion_window.answers("en")}
        self.assertIsNotNone(replies["status"]["status"]["watcher"].get("usage"))
        self.assertIsNotNone(replies["dashboard"]["status"]["watcher"].get("usage"))

    def test_the_pictures_are_rebuilt_whole_from_each_frame_s_rectangle(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            (folder / "00000.rgb").write_bytes(bytes(range(12)))
            (folder / "00001.rgb").write_bytes(b"\xff\xfe\xfd")
            result = {"client": [2, 2], "frames": [
                {"index": 0, "box": [0, 0, 2, 2], "file": "00000.rgb", "bounds": {"save": [0, 0, 1, 1]}},
                {"index": 1, "box": [1, 1, 1, 1], "file": "00001.rgb"},
                {"index": 2, "box": [0, 0, 0, 0], "file": ""}]}
            drawn = list(motion_window.pictures(result, folder))
        self.assertEqual([index for index, _picture, _bounds in drawn], [0, 1, 2])
        self.assertEqual(drawn[0][1], bytes(range(12)))
        self.assertEqual(drawn[1][1], bytes(range(9)) + b"\xff\xfe\xfd")
        self.assertEqual(drawn[2][1], drawn[1][1])
        self.assertEqual(drawn[0][2], {"save": [0, 0, 1, 1]})


@unittest.skipUnless(os.name == "nt" and motion_window.CSC.is_file(), "the window is built with Windows' C# compiler")
class RenderTests(unittest.TestCase):
    """One small job of the real window, offscreen: three frames of English and nothing shown on the screen."""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = motion_window.compile_window(work)
        frames = [{"index": 0, "locale": "en", "page": "overview", "light": 0},
                  {"index": 1, "locale": "en", "page": "overview", "hover": "page.history", "light": 0},
                  {"index": 2, "locale": "en", "page": "settings", "section": "general", "light": 0,
                   "droplist": {"field": "interface_language", "hover": "en"}},
                  {"index": 3, "locale": "en", "page": "settings", "section": "general", "light": 0,
                   "scroll": {"notches": 1}}]
        job = {"out": str(work / "out"), "theme": "light", "design": "soft",
               "forms": {"en": {"answers": motion_window.answers("en")}},
               "targets": ["page.history", "setting.interface_language", "row.en", "save"], "frames": frames}
        cls.result = motion_window.render(exe, job, work)
        cls.pictures = list(motion_window.pictures(cls.result, work / "out"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def changed(self, one, other) -> tuple:
        width, height = self.result["client"]
        xs, ys = [], []
        for y in range(height):
            a, b = one[y * width * 3:(y + 1) * width * 3], other[y * width * 3:(y + 1) * width * 3]
            if a == b:
                continue
            ys.append(y)
            xs.extend(x for x in range(width) if a[x * 3:x * 3 + 3] != b[x * 3:x * 3 + 3])
        return (min(xs), min(ys), max(xs), max(ys)) if xs else None

    def test_every_frame_was_drawn_still_and_every_read_answered(self):
        self.assertEqual(self.result["notes"], [])
        self.assertEqual(self.result["misses"], [])
        self.assertEqual(len(self.pictures), 4)
        width, height = self.result["client"]
        self.assertEqual((width, height), (round(1000 * self.result["dpi_scale"]), round(664 * self.result["dpi_scale"])))

    def test_a_hover_changes_only_the_control_hovered(self):
        box = self.changed(self.pictures[0][1], self.pictures[1][1])
        self.assertIsNotNone(box, "the hover drew nothing")
        x, y, wide, tall = self.pictures[1][2]["page.history"]
        self.assertTrue(x <= box[0] and y <= box[1] and box[2] < x + wide and box[3] < y + tall,
                        "%r is outside the History tab %r" % (box, (x, y, wide, tall)))

    def test_the_drop_list_opens_under_its_field_with_its_rows_named(self):
        bounds = self.pictures[2][2]
        field, row = bounds["setting.interface_language"], bounds["row.en"]
        self.assertGreater(row[1], field[1] + field[3], "the list opens under the drop-down")
        self.assertNotIn("row.en", self.pictures[3][2], "a closed list has no rows")

    def test_a_turn_of_the_wheel_scrolls_as_far_as_softpage_scrolls(self):
        before = self.pictures[2][2]["setting.interface_language"][1]
        after = self.pictures[3][2]["setting.interface_language"][1]
        step = motion_window.WHEEL_LINES * round(33 * self.result["dpi_scale"])   # SoftBar.Line, as Soft.Px rounds
        self.assertEqual(before - after, step)


if __name__ == "__main__":
    unittest.main()
