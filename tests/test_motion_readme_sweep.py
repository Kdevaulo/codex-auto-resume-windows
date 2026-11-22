"""v0.6.24: the README's motion shows the status light's sweep and the veil under a dialog, as the window now does them.

- The sweep (gui/Marks.cs HaloDot.Sweep) and the line under the headline gliding in as it ends (AsideLabel.Arrive,
  AsideAfterMs after the sweep begins) play once as the window opens and once as the light turns on (SettingsForm.LightRead,
  SweepLight): from off - idle or paused - to watching, so Resume recovery sweeps too (LightTurnsOn("paused", ...)). The
  motion opens with the window opening (S0: the sweep, then the rest it held before) and sweeps again as Resume recovery
  is answered (S15b: the sweep's whole length, taken from the rest S16 held, so the picture is as long as before); the
  picture still ends at rest.
- The veil (DialogVeil) is laid by the render mode under every frame the Timeline dialog is open (S2c), at its fullest from
  the dialog's first frame and gone with it, as DialogVeil comes on before the dialog is seen and goes as it closes.

The plan half (this module, pure Python: nothing is drawn). The render half is tests/test_motion_window_sweep.py.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import guiscan  # noqa: E402
import make_motion  # noqa: E402
import motion_plan  # noqa: E402
import motion_window  # noqa: E402

PLANS = ("readme-en", "readme-ko")


def plan_of(name):
    return motion_plan.load(make_motion.plan_path(name))


def state(frame) -> dict:
    return motion_plan.thawed(frame.window)


def job_frames(plan):
    frames, _delays, _end = make_motion.schedule(plan)
    job = motion_window.job(plan, frames, Path("out"), forms={"en": {"answers": []}, "ko": {"answers": []}})
    return frames, job["frames"]


def constant(body: str, name: str) -> int:
    found = re.search(r"\b%s = (\d+)" % name, body)
    if not found:
        raise AssertionError("no constant %s" % name)
    return int(found.group(1))


class TheProductsNumbers(unittest.TestCase):
    def test_the_sweep_lasts_what_the_light_s_own_sweep_lasts(self):
        dot = guiscan.type_body("HaloDot")
        self.assertIn("internal const int SweepMs = SecondRingAt + RingMs;", dot)
        self.assertIn("sweep.To(1.0, true, SweepMs);", guiscan.member_body("HaloDot", "Sweep"))
        self.assertEqual(motion_plan.SWEEP_MS, constant(dot, "SecondRingAt") + constant(dot, "RingMs"))

    def test_the_line_has_come_in_before_the_sweep_is_over(self):
        app = guiscan.read("gui/SettingsApp.cs")
        after = int(re.search(r"AsideAfterMs = (\d+)", app).group(1))
        glide = int(re.search(r"InMs = \d+, OutMs = (\d+)", guiscan.type_body("AsideLabel")).group(1))
        self.assertLess(after + glide, motion_plan.SWEEP_MS)

    def test_the_sweep_s_frames_are_at_its_own_timer_s_step(self):
        """A Transition repaints on its own timer, Motion.Interval: the sweep and the line's glide move at that step."""
        interval = int(re.search(r"internal const int Interval = (\d+);", guiscan.read("gui/SoftTheme.cs")).group(1))
        for name in PLANS:
            with self.subTest(name):
                self.assertEqual(plan_of(name)["sweep_step_ms"], interval)

    def test_resume_recovery_turns_the_light_on_and_so_sweeps_it(self):
        """The light the read gives goes from paused to a watching one on Resume: LightTurnsOn says that sweeps."""
        turns = guiscan.member_body("SettingsForm", "LightTurnsOn")
        self.assertIn("LightOff(before) && LightWatching(after)", turns)
        self.assertIn('light == "paused"', guiscan.member_body("SettingsForm", "LightOff"))


class TheOpeningSweep(unittest.TestCase):
    def test_the_motion_opens_with_the_window_opening_and_its_light_sweeping(self):
        for name in PLANS:
            with self.subTest(name):
                plan = plan_of(name)
                frames, told = job_frames(plan)
                self.assertEqual(frames[0].t, 0)
                self.assertEqual(state(frames[0])["sweep"], {"why": "open", "from": 0})
                self.assertEqual(told[0]["sweep"], 0, "frame 1 is the sweep's first moment")
                opening = [(frame.t, item["sweep"]) for frame, item in zip(frames, told)
                           if "sweep" in item and frame.t < motion_plan.SWEEP_MS]
                # Every step of it, but one closer than a browser shows apart to the frame the next step begins with
                # (the rest that follows, at SWEEP_MS), as a ripple's frames are kept (motion_plan.fill).
                steps = [at for at in range(0, motion_plan.SWEEP_MS, plan["sweep_step_ms"])
                         if motion_plan.SWEEP_MS - at >= motion_plan.SHORTEST]
                self.assertEqual(opening, [(at, at) for at in steps],
                                 "a frame at every step of the sweep, each told how far into it it is")

    def test_then_the_rest_it_held_before_and_the_first_scene_s_length(self):
        for name in PLANS:
            with self.subTest(name):
                plan = plan_of(name)
                steps = plan["scenes"][0]["steps"]
                self.assertEqual(steps, [{"set": {"sweep": "open"}, "hold": motion_plan.SWEEP_MS}, {"hold": 2500}])
                frames, told = job_frames(plan)
                rest = [item for frame, item in zip(frames, told)
                        if motion_plan.SWEEP_MS <= frame.t < motion_plan.SWEEP_MS + 2500]
                self.assertTrue(rest)
                self.assertFalse([item for item in rest if "sweep" in item], "at rest once the sweep is over")
                self.assertEqual({item["page"] for item in rest}, {"overview"})


class TheResumeSweep(unittest.TestCase):
    def test_the_light_sweeps_as_resume_recovery_is_answered(self):
        for name in PLANS:
            with self.subTest(name):
                plan = plan_of(name)
                frames, told = job_frames(plan)
                resumed = next(index for index in range(1, len(frames))
                               if state(frames[index - 1]).get("variant") == "paused"
                               and "variant" not in state(frames[index]))
                self.assertEqual(frames[resumed].scene, "S15b")
                self.assertEqual(state(frames[resumed])["sweep"], {"why": "on", "from": frames[resumed].t})
                self.assertNotIn("busy", state(frames[resumed]), "as the call is answered, not while it is in flight")
                self.assertEqual(told[resumed]["sweep"], 0)
                sweeping = [(frame.t - frames[resumed].t, item["sweep"]) for frame, item in zip(frames, told)
                            if frame.t >= frames[resumed].t and "sweep" in item]
                self.assertEqual([at for at, _ms in sweeping], [ms for _at, ms in sweeping])
                self.assertEqual(sweeping[0][0], 0)
                self.assertGreaterEqual(sweeping[-1][0], motion_plan.SWEEP_MS - 2 * plan["sweep_step_ms"],
                                        "to its last step a browser shows apart from the rest that follows")
                self.assertLess(sweeping[-1][0], motion_plan.SWEEP_MS)
                self.assertEqual({frame.scene for frame in frames if "sweep" in state(frame)
                                  and frame.t >= frames[resumed].t}, {"S15b"}, "all of it before the last scene")
                last = [frame for frame in frames if frame.scene == "S16"]
                self.assertEqual(last[0].t, frames[resumed].t + motion_plan.SWEEP_MS)
                self.assertNotIn("sweep", state(last[0]), "which holds the window at rest")

    def test_only_two_sweeps_and_none_on_pause_or_on_the_language_s_reopen(self):
        for name in PLANS:
            with self.subTest(name):
                frames = motion_plan.expand(plan_of(name))
                starts = sorted({(state(frame)["sweep"]["from"], state(frame)["sweep"]["why"])
                                 for frame in frames if "sweep" in state(frame)})
                self.assertEqual([why for _at, why in starts], ["open", "on"])

    def test_the_loop_ends_at_rest(self):
        for name in PLANS:
            with self.subTest(name):
                frames, told = job_frames(plan_of(name))
                self.assertNotIn("sweep", told[-1])
                self.assertNotIn("sweep", state(frames[-1]))


class TheVeil(unittest.TestCase):
    def test_every_frame_of_the_dialog_is_drawn_veiled_and_none_other(self):
        render = guiscan.member_body("SettingsForm", "RenderDialog")
        # v0.6.26 (audit-apng M3): the veil fades in with the dialog (gui-audit D9): its fullest times the dialog's alpha.
        self.assertLess(render.index("PaintVeil(picture, (int)Math.Round(DialogVeil.FullNow * fade / 255.0));"),
                        render.index("PaintDialog(picture"), "the veil under the dialog, over the window")
        # Both of its overloads (v0.6.26: the veil at an alpha of its own while the dialog fades in).
        source = guiscan.read("gui/WindowRender.cs")
        veil = source[source.index("internal static void PaintVeil(Bitmap picture)"):source.index("internal static int Veiled(")]
        self.assertIn("DialogVeil.FullNow", veil, "at its fullest at once, as DialogVeil comes on")
        self.assertIn("DialogVeil.Ink()", veil)
        self.assertIn("Palette.Contrast", veil, "none in High Contrast, as DialogVeil.Over makes none")
        self.assertIn("full = FullNow;", guiscan.type_body("DialogVeil"))
        for name in PLANS:
            with self.subTest(name):
                frames, told = job_frames(plan_of(name))
                veiled = [index for index, item in enumerate(told) if "dialog" in item]
                self.assertTrue(veiled)
                self.assertEqual(veiled, list(range(veiled[0], veiled[-1] + 1)), "one stretch: the veil with the dialog")
                self.assertEqual({frames[index].scene for index in veiled}, {"S2c"})
                self.assertNotIn("dialog", told[veiled[-1] + 1], "and gone with it")


class ThePlanSays(unittest.TestCase):
    BASE = {"format": motion_plan.FORMAT, "name": "t", "locale": "en", "canvas": {"theme": "light"}}

    def test_a_sweep_is_as_the_window_opens_or_as_the_light_turns_on(self):
        for why in ("start", True, "off"):
            with self.subTest(why), self.assertRaises(motion_plan.PlanError):
                motion_plan.check(dict(self.BASE, scenes=[{"id": "A", "steps": [{"set": {"sweep": why}, "hold": 100}]}]))

    def test_the_frames_a_sweep_adds_and_its_end(self):
        plan = dict(self.BASE, scenes=[{"id": "A", "steps": [{"hold": 100}, {"set": {"sweep": "on"}, "hold": 2500}]}])
        motion_plan.check(plan)
        frames = motion_plan.fill(motion_plan.expand(plan), 2600, 100, sweep_step=15)
        swept = [frame.t for frame in frames if motion_plan.sweep_ms(frame) is not None]
        self.assertEqual(swept, list(range(100, 100 + motion_plan.SWEEP_MS, 15)))
        late = [frame for frame in frames if frame.t >= 100 + motion_plan.SWEEP_MS]
        self.assertTrue(late, "the lights' own frames go on after it")
        self.assertFalse([frame for frame in late if "sweep" in state(frame)], "gone from the state once over")
        self.assertEqual(motion_plan.fill(motion_plan.expand(plan), 2600, 0), motion_plan.expand(plan),
                         "without a step, nothing is added")


if __name__ == "__main__":
    unittest.main()
