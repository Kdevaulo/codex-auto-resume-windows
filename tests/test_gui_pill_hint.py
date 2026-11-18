r"""v0.6.24: on a special day the version's pill hints that it can be pressed (the owner, 2026-11-18, the Hint board's H2 and
H3): it nudges up about 3 px now and then - every 7 s, as the board's car-nudge - and its ring glows slowly in the day's
colour (Brand.DayRing, over 4 s, as car-ring); a hand cursor over it. Neither on an ordinary day, in High Contrast, with
motion reduced or Windows' animations off (the ring left out, not held still), in a picture or a probe without a probe date,
or off the screen. Under battery saver or a locked session (Motion.Ambient) it holds still, as the other motion that goes
by itself does.

PillHint on a control of a window shown far off the screen and never activated (as test_gui_v0623_motion's probes), and
the window compiled with a probe of its own, never shown (tests/dayeggprobe.py), for its wiring. GUI test module (it shows
a window off the screen): run on its own, through gui_lock.sh.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import dayeggprobe  # noqa: E402
import guiscan  # noqa: E402
from codex_auto_resume.brand import days as brand_days  # noqa: E402
from test_gui_v0611_access import compile_window, run_probe  # noqa: E402
from test_gui_v0623_motion import PROBE_HEAD, PROBE_HELPERS, PROBE_TAIL  # noqa: E402

PROBE = r"""
$pill = New-Object Windows.Forms.Panel
Place $pill 40 40 120 28
Pump 40
$hint = MakeWith 'PillHint' @($pill)
$out.nudges = @()
foreach ($ms in 0, 3000, 6020, 6160, 6300, 6440, 6580, 6685, 6790, 6895, 7000) { $out.nudges += [double](S 'PillHint' 'NudgeAt' @([double]$ms)) }
$out.rings = @()
foreach ($ms in 0, 1000, 2000, 3000, 4000) { $out.rings += [double](S 'PillHint' 'RingAt' @([double]$ms)) }

$null = Call $hint 'Follow' @([string]$null)
$out.ordinary = [bool](P $hint 'Moving')
$null = Call $hint 'Follow' @('new_year')
$out.special = [bool](P $hint 'Moving')
Pump 2100
$out.ring = [double](P $hint 'Ring')
$bitmap = New-Object Drawing.Bitmap 120, 28
$g = [Drawing.Graphics]::FromImage($bitmap)
$g.Clear((SProp 'Palette' 'Raised'))
$null = Call $hint 'PaintRing' @($g, (New-Object Drawing.Rectangle 0, 0, 120, 28), [single]14)
$g.Dispose()
$edge = $bitmap.GetPixel(60, 1)
$middle = $bitmap.GetPixel(60, 14)
$out.edge = @([int]$edge.R, [int]$edge.G, [int]$edge.B)
$out.middle = @([int]$middle.R, [int]$middle.G, [int]$middle.B)
$out.ground = Argb (SProp 'Palette' 'Raised')
$bitmap.Dispose()
$out.dayRing = Argb (S 'Brand' 'DayRing' @('new_year'))

# Battery saver: held - the pill at rest, the ring where it was, asked once a second.
SetSF 'TaskbarMark' 'BatterySaverOn' ([Said]::Answer($true))
$null = S 'Motion' 'AskAmbientAgain' @()
Pump 1200
$out.held = @([bool](P $hint 'Held'), [int](P $hint 'Nudge'))
SetSF 'TaskbarMark' 'BatterySaverOn' ([Said]::Answer($false))
$null = S 'Motion' 'AskAmbientAgain' @()
Pump 1200
$out.letGo = @([bool](P $hint 'Moving'), [bool](P $hint 'Held'))

Reduce $true
$null = Call $hint 'Follow' @('new_year')
$out.reduced = @([bool](P $hint 'Moving'), [int](P $hint 'Nudge'), [double](P $hint 'Ring'))
Reduce $false
SetSF 'Soft' 'WindowsAnimates' ([Said]::Answer($false))
$null = Call $hint 'Follow' @('new_year')
$out.animationsOff = [bool](P $hint 'Moving')
SetSF 'Soft' 'WindowsAnimates' ([Said]::Answer($true))
SetSF 'Palette' 'Contrast' $true
$null = Call $hint 'Follow' @('new_year')
$out.contrast = @([bool](P $hint 'Moving'), [double](P $hint 'Ring'))
SetSF 'Palette' 'Contrast' $false
$null = Call $hint 'Follow' @('new_year')
$out.again = [bool](P $hint 'Moving')
$pill.Visible = $false
$null = Call $hint 'Follow' @('new_year')
$out.hidden = [bool](P $hint 'Moving')
$null = Call $hint 'Dispose' @()
"""

# The window's wiring, never shown: the cursor, and no hint off the screen or in the layout audit.
BODY = r"""
                        form.FollowPillHint();
                        at["hand"] = form.versionPill.Cursor == Cursors.Hand && form.versionText.Cursor == Cursors.Hand;
                        at["moving"] = form.pillHint.Moving;
                        at["look"] = form.pillHint.Look ?? "";
                        form.auditing = true;
                        form.FollowPillHint();
                        at["audited"] = form.pillHint.Look ?? "";
                        form.auditing = false;
"""


@unittest.skipUnless(dayeggprobe.CSC.is_file(), "needs the in-box C# compiler")
class PillHintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = compile_window(work)
        cls.answer = run_probe(PROBE_HEAD + PROBE_HELPERS + PROBE + PROBE_TAIL, work, 200, CAR_EXE=str(exe))
        cls.wired = dayeggprobe.run(BODY)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_the_nudge_is_the_boards_three_pixels_every_seven_seconds(self):
        nudges = self.answer["nudges"]
        self.assertEqual(nudges[:3], [0.0, 0.0, 0.0], "at rest for most of the 7 s")
        self.assertGreater(nudges[3], 0.0)
        self.assertAlmostEqual(nudges[4], 3.0)
        self.assertAlmostEqual(nudges[6], 0.0)
        self.assertAlmostEqual(nudges[8], 1.0)
        self.assertAlmostEqual(nudges[10], 0.0)
        self.assertLessEqual(max(nudges), 3.0)

    def test_the_ring_glows_and_fades_over_four_seconds(self):
        rings = self.answer["rings"]
        self.assertAlmostEqual(rings[0], 0.0)
        self.assertAlmostEqual(rings[2], 1.0)
        self.assertAlmostEqual(rings[4], 0.0)

    def test_on_a_special_day_it_moves_and_on_an_ordinary_one_it_does_not(self):
        self.assertFalse(self.answer["ordinary"])
        self.assertTrue(self.answer["special"])
        self.assertGreater(self.answer["ring"], 0.9)

    def test_the_ring_is_the_days_colour_just_inside_the_edge(self):
        red, green, blue = (int(brand_days.DAY_RINGS["new_year"][i:i + 2], 16) for i in (1, 3, 5))
        edge, middle = self.answer["edge"], self.answer["middle"]
        ground = self.answer["ground"] & 0xFFFFFF
        self.assertEqual(middle, [ground >> 16, (ground >> 8) & 255, ground & 255], "the body untouched")
        self.assertNotEqual(edge, middle)
        # Toward the day's gold from the ground: red stays high, blue drops.
        self.assertLess(edge[2], middle[2])
        self.assertEqual(self.answer["dayRing"] & 0xFFFFFF, (red << 16) | (green << 8) | blue)

    def test_battery_saver_holds_it_and_letting_go_moves_it_again(self):
        held, nudge = self.answer["held"]
        self.assertTrue(held)
        self.assertEqual(nudge, 0, "the pill at rest while held")
        self.assertEqual(self.answer["letGo"], [True, False])

    def test_never_with_motion_reduced_animations_off_high_contrast_or_off_the_screen(self):
        self.assertEqual(self.answer["reduced"], [False, 0, 0.0], "motion reduced: no nudge and the ring left out")
        self.assertFalse(self.answer["animationsOff"])
        self.assertEqual(self.answer["contrast"], [False, 0.0])
        self.assertTrue(self.answer["again"])
        self.assertFalse(self.answer["hidden"])

    def test_the_window_shows_a_hand_on_a_special_day_and_never_moves_off_the_screen(self):
        for locale, days in self.wired.items():
            for day, at in days.items():
                with self.subTest(locale=locale, day=day):
                    special = day != "ordinary"
                    self.assertEqual(at["hand"], special)
                    self.assertEqual(at["look"], day if special else "")
                    self.assertFalse(at["moving"], "never shown: nothing moves")
                    self.assertEqual(at["audited"], "", "never in a picture or the layout audit")


class PillHintSourceTests(unittest.TestCase):
    def test_the_hint_follows_the_windows_clock_and_moves_the_pill_in_its_slot(self):
        follow = guiscan.member_body("SettingsForm", "FollowPillHint")
        self.assertIn("LightSweepsShown ? EggDay() : null", follow)
        self.assertIn("FollowPillHint();", guiscan.member_body("SettingsForm", "FollowDayScene"))
        self.assertIn("pillHint.Nudge", guiscan.member_body("SettingsForm", "BuildVersionPill"))
        self.assertIn("PaintRing", guiscan.type_body("VersionPill"))


if __name__ == "__main__":
    unittest.main()
