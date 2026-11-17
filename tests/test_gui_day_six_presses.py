r"""v0.6.24: six presses on the version's pill on a special day play that day's own egg in place of the three ordinary ones
(the owner, 2026-11-17/18, the Special board, as proposed): fireworks and stars on the new year, the swinging pouch and its
coins on seollal, the candle and confetti on the birthday, the rising full moon on chuseok, heavy snow and the tree's lights
at Christmas - each with its sentence. The one-at-a-time rules stay as they are (a6646ebbe): the first press of a run plays
the one-press egg, presses 2 to 5 nothing, the sixth clears it and plays the special one, presses during it are ignored. On
an ordinary day the three ordinary eggs, picked as before. Never shown, nothing may move here: the sentence alone, at once,
and no layer.

The day's egg itself (DayEgg) is drawn into pictures of its own: something at every moment until it ends, nothing after,
moving, inside the box the layer gives it round the pill (260 px either side, 130 above, the window's foot below) and on
the window's side of the pill (mirrored, the other). GUI test module (it makes windows, never shown): run on its own, through gui_lock.sh.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import dayeggprobe  # noqa: E402
import guiscan  # noqa: E402

BODY = r"""
                        var picks = new Queue<int>(new[] { 0, 0, 0 });
                        var asked = new List<object>();
                        form.SpecialEggs.Next = delegate(int kinds) { asked.Add((double)kinds); return picks.Count > 0 ? picks.Dequeue() : 0; };
                        form.detail.Text = "The line's own words";
                        var runs = new List<object>();
                        for (int round = 0; round < 3; round++)
                        {
                            Wait(2000);
                            var played = new List<object>();
                            for (int press = 0; press < 6; press++)
                            {
                                clock += 300;
                                form.EggsPlayed.Clear();
                                Press();
                                played.Add(string.Join(",", form.EggsPlayed.ToArray()));
                            }
                            var run = new Dictionary<string, object>();
                            run["played"] = played;
                            run["words"] = Words();
                            run["layer"] = form.confetti != null;
                            run["sweeping"] = form.stateDot.Sweeping;
                            // Pressing on while it plays: nothing.
                            int before = form.EggsPlayed.Count;
                            clock += 300;
                            Press();
                            run["during"] = form.EggsPlayed.Count == before && Words() == (string)run["words"];
                            runs.Add(run);
                        }
                        at["runs"] = runs;
                        at["asked"] = asked;
                        at["egg"] = S("status.aside_egg_" + pair.Key);
                        at["colours"] = S("status.aside_colours");
                        at["confetti"] = S("status.aside_confetti");
                        if (locale == "en" && pair.Key != "ordinary")
                        {
                            // The egg drawn on its own, as the layer draws it: the pill at (700, 300) in a 1000 by 800 layer.
                            var frames = new List<object>();
                            foreach (int inward in new[] { -1, 1 })
                            {
                                var egg = new DayEgg(pair.Key, new PointF(700, 300), 1f, inward);
                                foreach (double ms in new[] { 0.0, 300.0, 700.0, 1100.0, 1500.0, 1900.0, 2300.0, 2650.0, 2700.0, 3000.0 })
                                {
                                    using (var image = new Bitmap(1000, 800, PixelFormat.Format32bppPArgb))
                                    {
                                        using (Graphics g = Graphics.FromImage(image))
                                        {
                                            g.Clear(Color.Transparent);
                                            ((IEggPainting)egg).Paint(g, ms);
                                        }
                                        int count = 0, left = 1000, right = -1, top = 800, bottom = -1;
                                        long sum = 0;
                                        for (int y = 0; y < 800; y += 2)
                                            for (int x = 0; x < 1000; x += 2)
                                            {
                                                Color c = image.GetPixel(x, y);
                                                if (c.A == 0) continue;
                                                count++;
                                                sum += (x * 7 + y * 13) * (long)c.A + c.R;
                                                left = Math.Min(left, x); right = Math.Max(right, x);
                                                top = Math.Min(top, y); bottom = Math.Max(bottom, y);
                                            }
                                        var frame = new Dictionary<string, object>();
                                        frame["inward"] = (double)inward;
                                        frame["ms"] = ms;
                                        frame["count"] = (double)count;
                                        frame["sum"] = (double)sum;
                                        frame["box"] = new List<object> { (double)left, (double)right, (double)top, (double)bottom };
                                        frames.Add(frame);
                                    }
                                }
                            }
                            at["frames"] = frames;
                            at["length"] = (double)((IEggPainting)new DayEgg(pair.Key, PointF.Empty, 1f, -1)).Length;
                        }
"""

KOREAN = {"new_year": "올해 첫 대화도 제가 지켜볼게요.", "seollal": "세뱃돈 대신, 멈춘 대화를 이어 드릴게요.",
          "birthday": "생일 축하해 주셔서 고마워요! 촛불은 제가 끌게요.", "chuseok": "보름달처럼 꽉 찬 하루 보내세요.",
          "christmas": "메리 크리스마스! 오늘은 눈이 많이 와요."}
ORDINARY = ("colours", "count", "confetti")


@unittest.skipUnless(dayeggprobe.CSC.is_file(), "needs the in-box C# compiler")
class DaySixPressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.failure, cls.answer = None, {}
        try:
            cls.answer = dayeggprobe.run(BODY)
        except AssertionError as error:
            cls.failure = str(error)

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_a_special_days_sixth_press_plays_that_days_egg_and_never_an_ordinary_one(self):
        for locale, days in self.answer.items():
            for day, at in days.items():
                if day == "ordinary":
                    continue
                with self.subTest(locale=locale, day=day):
                    for run in at["runs"]:
                        self.assertEqual(run["played"], ["one", "", "", "", "", "day:" + day])
                        self.assertEqual(run["words"], at["egg"], "that day's sentence")
                        self.assertNotIn(run["words"], (at["colours"], at["confetti"]))
                    self.assertEqual(at["asked"], [], "no ordinary egg is picked on a special day")

    def test_on_an_ordinary_day_the_three_ordinary_eggs_as_before(self):
        for locale, days in self.answer.items():
            at = days["ordinary"]
            with self.subTest(locale=locale):
                self.assertEqual([run["played"] for run in at["runs"]],
                                 [["one", "", "", "", "", kind] for kind in ("colours", "count", "confetti")])
                self.assertEqual(at["asked"], [3, 2, 2])

    def test_one_at_a_time_and_where_nothing_may_move_the_sentence_alone(self):
        for locale, days in self.answer.items():
            for day, at in days.items():
                with self.subTest(locale=locale, day=day):
                    for run in at["runs"]:
                        self.assertTrue(run["during"], "a press while it plays changes nothing")
                        self.assertFalse(run["layer"], "never shown: no layer")
                        self.assertFalse(run["sweeping"])

    def test_the_owners_words(self):
        for day, words in KOREAN.items():
            self.assertEqual(self.answer["ko"][day]["egg"], words, day)

    def frames(self, day):
        return self.answer["en"][day]["frames"]

    def test_each_egg_draws_until_it_ends_and_nothing_after(self):
        for day in KOREAN:
            with self.subTest(day=day):
                length = self.answer["en"][day]["length"]
                self.assertGreaterEqual(length, 2000)
                self.assertLessEqual(length, 3000, "about 2-3 s")
                for frame in self.frames(day):
                    if frame["ms"] >= length:
                        self.assertEqual(frame["count"], 0, "gone at %s" % frame["ms"])
                    elif 300 <= frame["ms"] <= 2300:
                        self.assertGreater(frame["count"], 0, "something at %s" % frame["ms"])

    def test_each_egg_moves(self):
        for day in KOREAN:
            with self.subTest(day=day):
                sums = [frame["sum"] for frame in self.frames(day) if frame["inward"] == -1 and 300 <= frame["ms"] <= 2300]
                self.assertEqual(len(set(sums)), len(sums), "every moment a picture of its own")

    def test_each_egg_stays_in_its_box_beside_the_pill_and_mirrors(self):
        for day in KOREAN:
            for frame in self.frames(day):
                if frame["count"] == 0:
                    continue
                left, right, top, bottom = frame["box"]
                with self.subTest(day=day, ms=frame["ms"], inward=frame["inward"]):
                    self.assertGreaterEqual(top, 300 - 130)
                    self.assertGreaterEqual(left, 700 - 260)
                    self.assertLessEqual(right, 700 + 260)
                    middle = (left + right) / 2
                    if frame["inward"] < 0:
                        self.assertLess(middle, 700, "into the window, left of a pill at its right end")
                    else:
                        self.assertGreater(middle, 700, "mirrored: right of a pill at its left end")


class DaySixPressSourceTests(unittest.TestCase):
    def test_the_days_egg_moves_only_where_motion_may_and_never_in_high_contrast(self):
        egg = guiscan.member_body("SettingsForm", "DayEggPlay")
        self.assertIn("!Motion.Allowed(versionPill) || Palette.Contrast", egg)
        self.assertIn("client.Bottom", egg)
        self.assertIn("new ConfettiLayer(this, area, egg)", egg)

    def test_every_catalog_has_the_five_sentences(self):
        for path in sorted((ROOT / "src/codex_auto_resume/locales").glob("*.json")):
            catalog = json.loads(path.read_text(encoding="utf-8"))
            for day in KOREAN:
                with self.subTest(path.name, day=day):
                    self.assertTrue(catalog.get("status.aside_egg_" + day))


if __name__ == "__main__":
    unittest.main()
