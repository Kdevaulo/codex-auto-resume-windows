"""The window's glides in a motion picture are drawn at each frame's moment (v0.6.26, audit-apng M6): the current tab, a
button's hover and the busy look glide from the frame their change came in, on the picture's clock, never the wall clock -
and a paused window opened again for the picture carries the call in flight, so the call's end glides there too. One
small job of the real window, offscreen, never on the screen; nothing is captured; the frames are compared with each
other. And every frame the generator writes tells the window its moment."""
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

import motion_plan  # noqa: E402
import motion_window  # noqa: E402

OVERVIEW = {"locale": "en", "page": "overview", "light": 0}
PENDING = {"locale": "en", "page": "pending", "light": 0, "selected": {"pending": 0}}
TIMELINE = {"kind": "timeline"}
SETTINGS = {"locale": "en", "page": "settings", "section": "general", "light": 0}
LIST = {"field": "interface_language", "hover": None}


class SwitchTests(unittest.TestCase):
    def test_a_clocked_render_answers_windows_animation_switch_itself(self):
        """A motion's glides are drawn whatever this machine's animation switch says (GitHub's runner has it off): the
        Dashboard's render and the setup window's shim each stand Windows' animations on, for a clocked job only."""
        import guiscan
        pinned = 'if (Clocked(Items(job, "frames"))) Soft.WindowsAnimates = delegate { return true; };'
        self.assertIn(pinned, guiscan.member_body("SettingsForm", "RenderFrames"))
        self.assertIn('frame.ContainsKey("moment")', guiscan.member_body("SettingsForm", "Clocked"))
        shim = (ROOT / "build" / "motion" / "InstallerRender.cs").read_text(encoding="utf-8")
        self.assertEqual(shim.count(pinned), 1)


class FrameMomentTests(unittest.TestCase):
    def test_every_frame_tells_the_window_its_moment(self):
        frame = motion_plan.Frame(1234, "S1", (("page", "pending"),), (), ("at", "page.pending"), ())
        state = motion_window.frame_state(frame, 7, light_step=33)
        self.assertEqual(state["moment"], 1234)
        self.assertEqual(state["light"], 1221, "the light keeps its own timer's step")


@unittest.skipUnless(os.name == "nt" and motion_window.CSC.is_file(), "the window is built with Windows' C# compiler")
class RenderClockTests(unittest.TestCase):
    FRAMES = [
        dict(OVERVIEW, moment=0),                                                  # 0 at rest
        dict(PENDING, moment=1000),                                                # 1 the tab's change comes in
        dict(PENDING, moment=1080),                                                # 2 half way through its glide
        dict(PENDING, moment=1400),                                                # 3 arrived
        dict(PENDING, moment=2000, hover="pending.retry"),                         # 4 the pointer comes onto Retry now
        dict(PENDING, moment=2080, hover="pending.retry"),                         # 5 half way
        dict(PENDING, moment=2400, hover="pending.retry"),                         # 6 arrived
        dict(OVERVIEW, moment=3000),                                               # 7 the Overview at rest
        dict(OVERVIEW, moment=3500, busy=True),                                    # 8 Pause's call in flight comes in
        dict(OVERVIEW, moment=3580, busy=True),                                    # 9 its first moments held (BusyHold)
        dict(OVERVIEW, moment=3640, busy=True),                                    # 10 still held, at 140 ms
        dict(OVERVIEW, moment=3730, busy=True),                                    # 11 half way, 80 ms past the hold
        dict(OVERVIEW, moment=4000, busy=True),                                    # 12 arrived
        dict(OVERVIEW, moment=4500, variant="paused"),                             # 13 the call answered: paused
        dict(OVERVIEW, moment=4580, variant="paused"),                             # 14 half way back from the busy look
        dict(OVERVIEW, moment=4900, variant="paused"),                             # 15 arrived
        dict(PENDING, moment=6000),                                                # 16 Pending again
        dict(PENDING, moment=6500),                                                # 17 at rest
        dict(PENDING, moment=7000, dialog=TIMELINE),                               # 18 the Timeline at rest
        dict(PENDING, dialog=TIMELINE),                                            # 19 the same on the wall clock
        dict(PENDING, moment=7500, dialog=TIMELINE, hover="dialog.close"),         # 20 onto its Close
        dict(PENDING, moment=7580, dialog=TIMELINE, hover="dialog.close"),         # 21 half way
        dict(PENDING, moment=7900, dialog=TIMELINE, hover="dialog.close"),         # 22 arrived
        dict(PENDING, moment=8500),                                                # 23 at rest
        dict(PENDING, moment=9000, busy=True),                                     # 24 a call that comes in...
        dict(PENDING, moment=9100, busy=True),                                     # 25 ...held...
        dict(PENDING, moment=9120),                                                # 26 ...and ends inside the hold
        dict(PENDING, moment=9500),                                                # 27 nothing shown
        dict(SETTINGS, moment=10000),                                              # 28 Settings
        dict(SETTINGS, moment=10500),                                              # 29 at rest
        dict(SETTINGS, moment=11000, droplist=dict(LIST, appear_ms=0)),            # 30 the list opens
        dict(SETTINGS, moment=11080, droplist=dict(LIST, appear_ms=80)),           # 31 half way
        dict(SETTINGS, moment=11400, droplist=dict(LIST)),                         # 32 open
        dict(SETTINGS, moment=12000, droplist=dict(LIST, close_ms=0)),             # 33 the list closes
        dict(SETTINGS, moment=12080, droplist=dict(LIST, close_ms=80)),            # 34 half way back
        dict(SETTINGS, moment=12400),                                              # 35 closed
    ]

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = motion_window.compile_window(work)
        job = {"out": str(work / "out"), "theme": "light", "design": "soft",
               "forms": {"en": {"answers": motion_window.answers("en")},
                         "en-paused": {"answers": motion_window.answers("en", paused=True)}},
               "targets": ["page.pending", "pending.retry", "overview.toggle", "dialog.close", "setting.interface_language"],
               "frames": [dict(frame, index=index) for index, frame in enumerate(cls.FRAMES)]}
        cls.result = motion_window.render(exe, job, work)
        cls.pictures = list(motion_window.pictures(cls.result, work / "out"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def level(self, index, box):
        """The mean of every channel of frame `index` over `box` (left, top, width, height)."""
        width = self.result["client"][0]
        picture = self.pictures[index][1]
        x, y, wide, tall = (int(value) for value in box)
        total = sum(sum(picture[(row * width + x) * 3:(row * width + x + wide) * 3]) for row in range(y, y + tall))
        return total / float(wide * tall * 3)

    def half_way(self, index, start, end, name, box=None):
        """Frame `index` over target `name` (or `box`) stands strictly between frames `start` and `end` there, on average:
        a glide part way, not a cut at either end."""
        box = box or self.pictures[end][2][name]
        part, low, high = self.level(index, box), self.level(start, box), self.level(end, box)
        self.assertGreater(abs(high - low), 1, "%s changes at all (%.2f to %.2f)" % (name, low, high))
        self.assertTrue(min(low, high) + 0.2 < part < max(low, high) - 0.2,
                        "%s half way: %.2f, between %.2f and %.2f" % (name, part, low, high))

    def test_every_frame_was_drawn_and_every_read_answered(self):
        self.assertEqual(self.result["notes"], [])
        self.assertEqual(self.result["misses"], [])
        self.assertEqual(len(self.pictures), len(self.FRAMES))

    def test_the_current_tab_glides(self):
        self.half_way(2, 1, 3, "page.pending")

    def test_a_hover_glides_from_the_frame_it_came_in(self):
        self.half_way(5, 4, 6, "pending.retry")
        self.assertEqual(self.pictures[4][1], self.pictures[3][1], "at its first moment it has not moved yet")

    def test_the_busy_look_holds_for_busy_hold_then_glides(self):
        """v0.6.26 (review P2): as the product, the buttons keep their look for BusyHold's 150 ms after the click
        (SetBusy, BusyHold.Begin, LooksEnabled), then glide to the busy look from that moment."""
        box = self.pictures[12][2]["overview.toggle"]
        self.assertEqual(self.level(9, box), self.level(8, box), "80 ms in: held")
        self.assertEqual(self.level(10, box), self.level(8, box), "140 ms in: still held")
        self.half_way(11, 8, 12, "overview.toggle")

    def test_a_call_that_ends_inside_the_hold_shows_nothing(self):
        box = self.pictures[23][2]["pending.retry"]
        for index in (24, 25, 26, 27):
            self.assertEqual(self.level(index, box), self.level(23, box), "frame %d" % index)

    def test_a_paused_window_opened_again_glides_out_of_the_call_in_flight(self):
        self.half_way(14, 13, 15, "overview.toggle")

    def test_a_dialog_built_for_each_frame_is_drawn_at_rest(self):
        self.assertEqual(self.pictures[18][1], self.pictures[19][1], "the Timeline at its frame's moment is the one at rest")

    def test_the_dialog_s_close_glides_from_the_frame_the_pointer_came_onto_it(self):
        self.half_way(21, 20, 22, "dialog.close")

    def test_the_drop_down_s_open_look_glides_in_and_out(self):
        """v0.6.26 (review P1): its edge and its chevron glide over brand's transition from the frame its list opens and
        from the frame it closes (OpenList, CloseList), read over the field's upper half, which the list never covers."""
        x, y, wide, tall = self.pictures[29][2]["setting.interface_language"]
        upper = (x, y, wide, max(1, int(tall) // 2))
        self.assertEqual(self.level(30, upper), self.level(29, upper), "at its first moment: as it was")
        self.half_way(31, 30, 32, None, upper)
        self.assertEqual(self.level(33, upper), self.level(32, upper), "closing, at its first moment: still open")
        self.half_way(34, 33, 35, None, upper)


if __name__ == "__main__":
    unittest.main()
