r"""v0.6.24-beta.3: the Dashboard's header shows its day's scene on a special day, and no slice of it where it has no room.

Found 2026-11-17 in renders of the window on each special day: the header card showed no scene, only slices of it behind
the three caption buttons. The scene (SoftDayScene) is the header's child above the card (the hero), and on the screen it
stands over the card: it is higher in the header's z-order and every child window clips its siblings. A picture of the
window is DrawToBitmap, which prints a window's children from the top of the z-order down, each over the one before - the
card was printed over the scene. Only the caption buttons, painted again over the picture (PaintCaptionOver), drew the
scene under them. The picture now lays the scene down over it as the screen stacks it (PaintSceneOver), then the buttons.

A probe compiled with the window builds the Dashboard as a render builds it (OpenForRender: a child of Windows' parking
window, never on the screen) at the pictures' pinned 150 %, with the probe's own date (DayArt.On, DayArt.Clock) - a special
day and an ordinary one - and compares the two pictures (RenderPicture) inside the header card, left of the caption buttons
and behind them. With words that leave no room, the scene is not shown and the two pictures are the same: no slice.

GUI test module (it compiles the window and builds windows that are never shown): run on its own, through gui_lock.sh.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import guiscan  # noqa: E402
from codex_auto_resume import l10n  # noqa: E402

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PROBE = r"""
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class DayHeaderProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { SettingsForm.DayHeaderRun(argv[1], said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")]
        private static extern IntPtr DayHeaderStyle(IntPtr h, int index);

        private static List<object> DayHeaderBox(Rectangle r)
        {
            return new List<object> { (double)r.Left, (double)r.Top, (double)r.Width, (double)r.Height };
        }

        private static Rectangle DayHeaderIn(Control c, Control root)
        {
            Point at = Point.Empty;
            for (Control each = c; each != null && each != root; each = each.Parent) at.Offset(each.Left, each.Top);
            return new Rectangle(at, c.Size);
        }

        // How many pixels of `area` differ between the two pictures by more than a rounding's worth in any channel.
        private static int DayHeaderDiffer(Bitmap one, Bitmap other, Rectangle area)
        {
            area.Intersect(new Rectangle(Point.Empty, one.Size));
            if (area.Width <= 0 || area.Height <= 0) return 0;
            int count = 0;
            for (int y = area.Top; y < area.Bottom; y++)
                for (int x = area.Left; x < area.Right; x++)
                {
                    Color a = one.GetPixel(x, y), b = other.GetPixel(x, y);
                    if (Math.Abs(a.R - b.R) > 8 || Math.Abs(a.G - b.G) > 8 || Math.Abs(a.B - b.B) > 8) count++;
                }
            return count;
        }

        private static Bitmap DayHeaderPicture(DateTime day, string headlineText, Dictionary<string, object> said, string work)
        {
            DayArt.On = true;
            DayArt.Clock = delegate { return day; };
            var writer = new RenderWriter(Path.Combine(work, "frames-" + day.ToString("yyyyMMdd") + (headlineText == null ? "" : "-long")));
            SettingsForm form = OpenForRender(writer);
            try
            {
                if (headlineText != null)
                {
                    form.headline.Text = headlineText;
                    form.detail.Text = headlineText;
                    Application.DoEvents();
                    form.PlaceDayScene();
                }
                said["look"] = form.dayLook;
                said["headline"] = form.headline.Text;
                said["sceneShown"] = Soft.OwnVisible(form.dayScene) && form.dayScene.Look != null;
                Rectangle hero = DayHeaderIn(form.hero, form);
                said["hero"] = DayHeaderBox(hero);
                said["scene"] = DayHeaderBox(DayHeaderIn(form.dayScene, form));
                Rectangle buttons = Rectangle.Empty;
                foreach (CaptionButton b in new[] { form.chrome.MinimizeButton, form.chrome.MaximizeButton, form.chrome.CloseButton })
                    if (Soft.OwnVisible(b))
                    {
                        Rectangle r = DayHeaderIn(b, form);
                        buttons = buttons.IsEmpty ? r : Rectangle.Union(buttons, r);
                    }
                said["buttons"] = DayHeaderBox(buttons);
                // On the screen: the scene above the card in the header's z-order, both clipping their siblings.
                if (form.dayScene.Parent == form.header)
                {
                    said["sceneAboveCard"] = form.header.Controls.GetChildIndex(form.dayScene) < form.header.Controls.GetChildIndex(form.hero);
                    const long clip = 0x04000000;   // WS_CLIPSIBLINGS
                    said["clipsSiblings"] = (DayHeaderStyle(form.dayScene.Handle, -16).ToInt64() & clip) != 0 &&
                                            (DayHeaderStyle(form.hero.Handle, -16).ToInt64() & clip) != 0;
                }
                // W2: where the band of the day begins, the ground the window's ground was given, a page card to hold unchanged.
                said["band"] = DayHeaderBox(DayHeaderIn(form.dayScene, form));
                said["canvas"] = (double)Palette.Canvas.ToArgb();
                string dayGround, dayTop, dayBottom;
                Brand.DayGround(form.dayLook ?? "seollal", out dayGround, out dayTop, out dayBottom);
                said["dayGround"] = (double)ColorTranslator.FromHtml(dayGround).ToArgb();
                SoftCard page = null;
                var walk = new Stack<Control>();
                walk.Push(form.pageHost);
                while (walk.Count > 0 && page == null)
                {
                    Control c = walk.Pop();
                    if (c is SoftCard && c != form.hero && Soft.OwnVisible(c) && c.Width > 200 && c.Height > 80) page = (SoftCard)c;
                    foreach (Control child in c.Controls) walk.Push(child);
                }
                if (page != null) said["pageCard"] = DayHeaderBox(Rectangle.Inflate(DayHeaderIn(page, form), -Soft.Px(20), -Soft.Px(20)));
                // A frame of the day: what the header's band costs to draw, as its timer draws it thirty times a second.
                if (Soft.OwnVisible(form.dayScene) && form.dayScene.Width > 0)
                    using (var frame = new Bitmap(form.dayScene.Width, form.dayScene.Height))
                    {
                        form.dayScene.DrawToBitmap(frame, new Rectangle(Point.Empty, frame.Size));
                        var clock = System.Diagnostics.Stopwatch.StartNew();
                        for (int i = 0; i < 30; i++) form.dayScene.DrawToBitmap(frame, new Rectangle(Point.Empty, frame.Size));
                        said["frameMs"] = clock.Elapsed.TotalMilliseconds / 30.0;
                    }
                return form.RenderPicture(new Dictionary<string, object>(), writer);
            }
            finally
            {
                form.Dispose();
                DayArt.On = false;
            }
        }

        private static Dictionary<string, object> DayHeaderCompare(DateTime special, DateTime plain, string headlineText, string work)
        {
            var said = new Dictionary<string, object>();
            var one = new Dictionary<string, object>();
            var other = new Dictionary<string, object>();
            using (Bitmap a = DayHeaderPicture(special, headlineText, one, work))
            using (Bitmap b = DayHeaderPicture(plain, headlineText, other, work))
            {
                said["special"] = one;
                said["plain"] = other;
                var hero = (List<object>)one["hero"];
                var box = (List<object>)one["buttons"];
                var card = new Rectangle((int)(double)hero[0], (int)(double)hero[1], (int)(double)hero[2], (int)(double)hero[3]);
                var buttons = new Rectangle((int)(double)box[0], (int)(double)box[1], (int)(double)box[2], (int)(double)box[3]);
                // The card left of the buttons, top to bottom, and the buttons themselves.
                var left = new Rectangle(card.Left, card.Top, Math.Max(0, buttons.Left - card.Left), card.Height);
                said["leftOfButtons"] = (double)DayHeaderDiffer(a, b, left);
                said["behindButtons"] = (double)DayHeaderDiffer(a, b, buttons);
                // The card's inside, its round corners left out: they show the window's ground, which a day tints.
                said["card"] = (double)DayHeaderDiffer(a, b, Rectangle.Inflate(card, -Soft.Px(24), 0));
                // The band: how much of it between the fade and the scene is the day's ground (the rest its specks).
                var band = (List<object>)one["band"];
                var inside = new Rectangle((int)(double)band[0], card.Top + Soft.Px(2), (int)(double)band[2], card.Height - Soft.Px(4));
                said["bandBox"] = DayHeaderBox(inside);
                said["leftOfBand"] = (double)DayHeaderDiffer(a, b, new Rectangle(card.Left + Soft.Px(24), card.Top + Soft.Px(2),
                                                                                    Math.Max(0, inside.Left - card.Left - Soft.Px(24)), card.Height - Soft.Px(4)));
                int dayGround = (int)(double)one["dayGround"], grounds = 0, all = 0;
                for (int y = inside.Top; y < inside.Bottom; y++)
                    for (int x = inside.Left + Soft.Px(100); x < inside.Left + inside.Width / 2; x++)
                    {
                        all++;
                        if (a.GetPixel(x, y).ToArgb() == dayGround) grounds++;
                    }
                said["dayGroundShare"] = all == 0 ? 0.0 : grounds / (double)all;
                // The window's ground: every pixel of an ordinary day's ground, on the day the tint - or near it, where a card's
                // lit edge, which an ordinary day's ground hides, lies on it - or one of the day's specks.
                int canvas = (int)(double)other["canvas"], ground = 0, tint = 0, specks = 0;
                Color tinted = Color.FromArgb((int)(double)one["canvas"]);
                for (int y = 0; y < a.Height; y += 2)
                    for (int x = 0; x < a.Width; x += 2)
                    {
                        if (b.GetPixel(x, y).ToArgb() != canvas) continue;
                        ground++;
                        Color day = a.GetPixel(x, y);
                        int far = Math.Max(Math.Abs(day.R - tinted.R), Math.Max(Math.Abs(day.G - tinted.G), Math.Abs(day.B - tinted.B)));
                        if (far <= 24) tint++;
                        else specks++;
                    }
                said["ground"] = new List<object> { (double)ground, (double)tint, (double)specks };
                if (one.ContainsKey("pageCard"))
                {
                    var box2 = (List<object>)one["pageCard"];
                    said["pageCard"] = (double)DayHeaderDiffer(a, b, new Rectangle((int)(double)box2[0], (int)(double)box2[1], (int)(double)box2[2], (int)(double)box2[3]));
                }
            }
            return said;
        }

        internal static void DayHeaderRun(string work, Dictionary<string, object> said)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Theme.Opened = "light";
            Palette.AdoptDesign(null);
            Palette.Adopt("light");
            // As a render job pinned at the pictures' 150 % (AdoptRenderScale).
            RenderPinned = true;
            AdoptDisplayScale(1.5);
            ScaleDefaultFont();
            AdoptTextSize(1.0, 1.0);
            Soft.StillLightMs = 0;
            var strings = Json.Parse(File.ReadAllText(Path.Combine(work, "strings-en.json"), new UTF8Encoding(false)));
            renderAnswers = new List<object> { new Dictionary<string, object> { { "command", "strings" }, { "reply", strings } } };
            PersistentBridge.Answers = RenderAnswer;
            DateTime special = DateTime.MinValue, plain = DateTime.MinValue;
            string look, top, bottom;
            for (DateTime day = new DateTime(2027, 1, 1); day.Year == 2027; day = day.AddDays(1))
            {
                if (Brand.DayLook(day.Year, day.Month, day.Day, out look, out top, out bottom))
                { if (special == DateTime.MinValue) special = day.AddHours(12); }
                else if (plain == DateTime.MinValue) plain = day.AddHours(12);
            }
            said["room"] = DayHeaderCompare(special, plain, null, work);
            // Words as long as the card holds, the headline and its second line: they reach the caption buttons and, below
            // them, the card's edge, and leave the scene no room (a long language at a large text size).
            string words = "Watching for interruptions in every conversation of every project on this computer, day and night";
            said["noRoom"] = DayHeaderCompare(special, plain, words + " " + words, work);
            PersistentBridge.Answers = null;
        }
    }
}
"""


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class DayHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        work = Path(cls.folder.name)
        reply = {"ok": True, "language": "en", "strings": l10n.catalog("en"), "endonyms": dict(l10n.ENDONYMS),
                 "preference": "en", "system_language": "en"}
        (work / "strings-en.json").write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        probe = work / "DayHeaderProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "DayHeader.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.DayHeaderProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"),
                               TEMP=str(work), TMP=str(work))
            done = subprocess.run([str(exe), str(out), str(work)], capture_output=True, timeout=300,
                                  creationflags=NO_WINDOW, env=environment)
            cls.answer = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
            if done.returncode != 0 or "error" in cls.answer or not cls.answer:
                cls.failure = "the probe failed (exit %d): %s" % (done.returncode, cls.answer.get("error"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_the_probe_s_date_gives_the_window_a_look_and_an_ordinary_day_none(self):
        room = self.answer["room"]
        self.assertTrue(room["special"]["look"], "the special day has its look")
        self.assertIsNone(room["plain"]["look"])

    def test_on_the_screen_the_scene_stands_over_the_card(self):
        special = self.answer["room"]["special"]
        self.assertTrue(special["sceneShown"])
        self.assertTrue(special["sceneAboveCard"], "higher in the header's z-order than the card")
        self.assertTrue(special["clipsSiblings"])

    def test_the_scene_shows_in_the_card_left_of_the_caption_buttons(self):
        """Fails without PaintSceneOver: the card was printed over the scene and only the buttons drew it."""
        room = self.answer["room"]
        hero, buttons = room["special"]["hero"], room["special"]["buttons"]
        self.assertGreater(buttons[2], 0, "the caption buttons are shown")
        # A good part of the card's height, over a run of columns wider than the buttons: the scene, not a fringe.
        self.assertGreater(room["leftOfButtons"], hero[3] * buttons[2] // 2, room)

    def test_and_behind_the_caption_buttons_as_well(self):
        self.assertGreater(self.answer["room"]["behindButtons"], 0)

    def test_w2_the_card_is_in_the_day_past_the_words(self):
        room = self.answer["room"]
        band, hero, buttons = room["special"]["band"], room["special"]["hero"], room["special"]["buttons"]
        self.assertLess(band[0], hero[0] + hero[2] * 0.5, "the day begins past the words, not in a corner")
        self.assertEqual(band[0] + band[2], hero[0] + hero[2] - 1, "and reaches the card's outer side, under the buttons")
        self.assertGreater(room["dayGroundShare"], 0.3, "the day's own ground")
        self.assertEqual(room["leftOfBand"], 0, "the words and the light stand as on any other day")

    def test_w2_the_window_s_ground_takes_the_day_faintly_with_its_specks_and_the_cards_stay(self):
        room = self.answer["room"]
        ground, tint, specks = room["ground"]
        self.assertGreater(ground, 1000)
        self.assertGreater(tint / ground, 0.9, "the tint")
        self.assertGreater(specks, 0, "and the day's specks on it")
        canvas, tinted, day = room["plain"]["canvas"], room["special"]["canvas"], room["special"]["dayGround"]
        mix = [round(((int(canvas) >> shift) & 255) * 0.9 + ((int(day) >> shift) & 255) * 0.1) for shift in (16, 8, 0)]
        got = [(int(tinted) >> shift) & 255 for shift in (16, 8, 0)]
        for one, other in zip(mix, got):
            self.assertLessEqual(abs(one - other), 1)
        self.assertEqual(room.get("pageCard"), 0, "a page's card is as on any other day")

    def test_w2_a_frame_of_the_band_costs_little(self):
        self.assertLess(self.answer["room"]["special"]["frameMs"], 12.0)

    def test_with_no_room_there_is_no_scene_and_no_slice_of_it(self):
        no_room = self.answer["noRoom"]
        self.assertTrue(no_room["special"]["look"], "a special day")
        self.assertGreater(len(no_room["special"]["headline"]), 100, "the long headline was still in place when drawn")
        self.assertFalse(no_room["special"]["sceneShown"])
        self.assertEqual(no_room["behindButtons"], 0, "no slice behind the caption buttons")
        self.assertEqual(no_room["card"], 0, "the card is as on an ordinary day")


class DayHeaderWiringTests(unittest.TestCase):
    def test_a_picture_lays_the_scene_down_before_the_caption_buttons(self):
        body = guiscan.member_body("SettingsForm", "RenderPicture")
        self.assertIn("PaintSceneOver(picture, this);", body)
        self.assertLess(body.index("PaintSceneOver(picture, this);"), body.index("PaintCaptionOver(picture, this);"))


if __name__ == "__main__":
    unittest.main()
