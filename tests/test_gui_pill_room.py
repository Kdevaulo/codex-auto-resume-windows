r"""v0.6.24: the version's pill is never hidden (the owner, 2026-11-18, a screenshot of the English advanced edition with Chat
on: eight tabs - Overview, Pending, History, Statistics, Diagnostics, Settings, Advanced features, Chat - and no pill).

Where the tabs crowd, they are drawn closer first - the room at either side of every name alike, no closer than needed and
never closer than SettingsForm.TabPadXLeast - so the pill stays at the row's end; only where even the closest tabs leave it
no room does it stand in the header card, at the end of its second line under the caption buttons, Brand.PillInset from the
card's edge. An ordinary row keeps today's room (TabPadX). Mirrored for a language written right to left.

A probe compiled with the window builds it never shown (TopLevel = false, as LayoutAudit does) with the advanced edition's two
tabs added as AdvancedPage.cs and AdvancedChat.cs add them, in their own words, at 100, 150 and 200 % and at text sizes up to
the largest a 3840 by 2160 screen lets the window open at (TextScale.Fitting): the pill shown, in the row or the header;
no tab cut; the gaps between the tabs equal; the chosen tab's face clear of its neighbours. GUI test module (it makes
windows, never shown): run on its own, through gui_lock.sh.
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
LOCALES = ("en", "de", "ru", "ar")
ADVANCED = next(iter(sorted((ROOT / "advanced" / "src").glob("*/locales"))))
# (display scale, text size): 100, 150 and 200 %, each at text size 1 and at the largest a 3840 by 2160 screen allows.
CASES = ((1.0, 1.0), (1.5, 1.0), (2.0, 1.0), (1.0, 2.25), (1.5, 2.25), (2.0, 1.75))

PROBE = r"""
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class PillRoomProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { SettingsForm.PillRoomRun(argv[1], said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        private NavButton PillRoomTab(string words)
        {
            NavButton settings = navButtons["settings"];
            var tab = new NavButton();
            tab.Font = Soft.RoleFont("nav");
            tab.AutoSize = true;
            tab.AutoSizeMode = AutoSizeMode.GrowAndShrink;
            tab.FlatStyle = FlatStyle.Flat;
            tab.FlatAppearance.BorderSize = 0;
            tab.Padding = settings.Padding;
            tab.Margin = settings.Margin;
            tab.Text = words;
            tab.Visible = false;
            settings.Parent.Controls.Add(tab);
            return tab;
        }

        private static Rectangle PillRoomIn(Control control, Control within)
        {
            var box = new Rectangle(Point.Empty, control.Size);
            for (Control c = control; c != null && c != within; c = c.Parent) box.Offset(c.Left, c.Top);
            return box;
        }

        private Dictionary<string, object> PillRoomRead(int width)
        {
            if (width > 0) ClientSize = new Size(width, ClientSize.Height);
            Materialise(this);
            PerformLayout();
            var said = new Dictionary<string, object>();
            said["fit"] = PillFit;
            var findings = new List<string>();
            AuditPill(findings);
            said["findings"] = string.Join(" | ", findings.ToArray());
            var tabs = new List<NavButton>();
            Control strip = navButtons["overview"].Parent;
            foreach (Control control in strip.Controls)
                if (control is NavButton && Soft.OwnVisible(control)) tabs.Add((NavButton)control);
            var pads = new List<object>();
            var gaps = new List<object>();
            var cut = new List<string>();
            int faceGap = int.MaxValue;
            tabs.Sort(delegate(NavButton a, NavButton b) { return a.Left.CompareTo(b.Left); });
            for (int i = 0; i < tabs.Count; i++)
            {
                NavButton tab = tabs[i];
                pads.Add(new List<object> { (double)tab.Padding.Left, (double)tab.Padding.Right });
                if (tab.Left < 0 || tab.Right > strip.ClientSize.Width || tab.Width < tab.GetPreferredSize(Size.Empty).Width) cut.Add(tab.Text);
                if (i > 0)
                {
                    gaps.Add((double)(tab.Left - tabs[i - 1].Right));
                    Rectangle face = tab.Face, before = tabs[i - 1].Face;
                    face.Offset(tab.Location);
                    before.Offset(tabs[i - 1].Location);
                    faceGap = Math.Min(faceGap, face.Left - before.Right);
                }
            }
            said["pads"] = pads;
            said["gaps"] = gaps;
            said["cut"] = string.Join(", ", cut.ToArray());
            said["faceGap"] = (double)faceGap;
            said["count"] = (double)tabs.Count;
            said["full"] = (double)Px(TabPadX);
            said["least"] = (double)Px(TabPadXLeast);
            said["text"] = versionText.Text ?? "";
            if (PillFit == "header")
            {
                Rectangle pill = PillRoomIn(versionPill, this), card = PillRoomIn(hero, this), line = PillRoomIn(detail, this);
                said["pill"] = new List<object> { (double)pill.X, (double)pill.Y, (double)pill.Width, (double)pill.Height };
                said["card"] = new List<object> { (double)card.X, (double)card.Y, (double)card.Width, (double)card.Height };
                said["line"] = new List<object> { (double)line.X, (double)line.Y, (double)line.Width, (double)line.Height };
                said["captionBottom"] = (double)(card.Y + Px(Brand.CaptionInsetTop + Brand.CaptionButtonH));
            }
            int outer, start;
            PillInsets(out outer, out start);
            said["outer"] = (double)outer;
            said["inset"] = (double)Px(Brand.PillInset);
            return said;
        }

        internal static void PillRoomRun(string dir, Dictionary<string, object> said)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(null);
            Palette.Adopt("light");
            var cases = Json.Parse(File.ReadAllText(Path.Combine(dir, "cases.json"), Encoding.UTF8)) as List<object>;
            System.Reflection.FieldInfo fallback = typeof(Control).GetField("defaultFont",
                System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
            Font defaultBefore = Control.DefaultFont;
            foreach (string locale in new[] { "en", "de", "ru", "ar" })
            {
                var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-" + locale + ".json"), Encoding.UTF8)) as Dictionary<string, object>;
                var advanced = (Dictionary<string, object>)strings["advanced"];
                foreach (object item in cases)
                {
                    var pair = (List<object>)item;
                    double scale = (double)pair[0], text = (double)pair[1];
                    AdoptDisplayScale(scale);
                    AdoptTextSize(text, text);
                    float factor = (float)(scale / SystemScale);
                    Font box = TextScale.Apply(SystemFonts.MessageBoxFont, 1.0, text);
                    var windowFont = new Font(box.FontFamily, box.SizeInPoints * factor, box.Style, GraphicsUnit.Point);
                    Font fallen = TextScale.Apply(defaultBefore, 1.0, text);
                    if (fallback != null)
                        fallback.SetValue(null, new Font(fallen.FontFamily, fallen.SizeInPoints * factor, fallen.Style, GraphicsUnit.Point));
                    Mirror.Window = Mirror.Language(locale);
                    string nowhere = Path.Combine(dir, "nowhere-" + locale);
                    var answer = new Dictionary<string, object>();
                    using (var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, windowFont))
                    {
                        form.auditing = true;
                        form.TopLevel = false;
                        form.MinimumSize = Size.Empty;
                        form.ClientSize = form.OpeningClient;
                        form.ShowPage("overview");
                        form.ShowVersion(form.versionText, new Dictionary<string, object> { { "version", "0.6.24" }, { "edition", "advanced" } });
                        answer["six"] = form.PillRoomRead(0);
                        NavButton features = form.PillRoomTab((string)advanced["page.nav"]);
                        NavButton chat = form.PillRoomTab((string)advanced["page.chat.nav"]);
                        features.Visible = true;
                        answer["seven"] = form.PillRoomRead(0);
                        chat.Visible = true;
                        answer["eight"] = form.PillRoomRead(0);
                        // The chosen tab the last, whose heavier words are the widest it gets.
                        form.navButtons["chat"] = chat;
                        chat.Current = true;
                        chat.Font = Soft.RoleFont("nav_current");
                        answer["eightChosen"] = form.PillRoomRead(0);
                        // The window at its narrowest (MinimumSize, 800 wide), where the closest tabs leave the pill no room.
                        answer["narrowest"] = form.PillRoomRead(form.Px(800));
                        // And wide again: back in the row.
                        answer["again"] = form.PillRoomRead(form.OpeningClient.Width);
                    }
                    said[locale + " " + scale.ToString("0.00", CultureInfo.InvariantCulture) + " " + text.ToString("0.00", CultureInfo.InvariantCulture)] = answer;
                }
            }
        }
    }
}
"""


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class PillRoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        for locale in LOCALES:
            words = json.loads((ADVANCED / (locale + ".json")).read_text(encoding="utf-8"))
            reply = {"ok": True, "language": locale, "strings": l10n.catalog(locale), "endonyms": dict(l10n.ENDONYMS),
                     "preference": locale, "system_language": locale,
                     "advanced": {key: words[key] for key in ("page.nav", "page.chat.nav")}}
            (work / ("strings-%s.json" % locale)).write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        (work / "cases.json").write_text(json.dumps([list(case) for case in CASES]), encoding="utf-8")
        probe = work / "PillRoomProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "PillRoom.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.PillRoomProbe",
                                "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
            done = subprocess.run([str(exe), str(out), str(work)], capture_output=True, timeout=600,
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

    def each(self):
        for where, answer in sorted(self.answer.items()):
            for name in ("six", "seven", "eight", "eightChosen", "narrowest", "again"):
                yield where + " " + name, answer[name]

    def test_the_pill_is_always_shown_in_the_row_or_the_header(self):
        for where, row in self.each():
            with self.subTest(where):
                self.assertIn(row["fit"], ("whole", "version", "header"), "never hidden: " + where)
                self.assertEqual(row["findings"], "", "the layout audit's AuditPill")
                self.assertIn("0.6.24", row["text"])

    def test_the_owners_window_keeps_the_pill_in_the_row(self):
        """The window of the owner's screenshot: English, advanced, Chat on, at its opening size - the pill stays in the row,
        the tabs drawn closer, at every scale and text size."""
        for where, answer in self.answer.items():
            if where.startswith("en "):
                for name in ("eight", "eightChosen"):
                    with self.subTest(where=where, row=name):
                        self.assertIn(answer[name]["fit"], ("whole", "version"))

    def test_no_tab_is_cut(self):
        for where, row in self.each():
            with self.subTest(where):
                self.assertEqual(row["cut"], "")

    def test_the_gaps_are_equal_and_never_closer_than_the_least(self):
        for where, row in self.each():
            with self.subTest(where):
                sides = {side for pad in row["pads"] for side in pad}
                self.assertEqual(len(sides), 1, "every tab the same room at either side of its name: %s" % row["pads"])
                self.assertGreaterEqual(min(sides), row["least"])
                self.assertLessEqual(max(sides), row["full"])
                self.assertEqual(len(set(row["gaps"])), 1, "the tabs equally far apart: %s" % row["gaps"])

    def test_the_chosen_tabs_face_never_touches_a_neighbour(self):
        for where, row in self.each():
            with self.subTest(where):
                self.assertGreater(row["faceGap"], 0)

    def test_an_ordinary_row_is_as_it_was(self):
        """Six tabs - the standard edition's - at the window's opening size: today's room, the pill whole in the row."""
        for where, answer in self.answer.items():
            with self.subTest(where):
                six = answer["six"]
                self.assertEqual(six["fit"], "whole")
                self.assertEqual({side for pad in six["pads"] for side in pad}, {six["full"]})

    def test_closer_only_as_much_as_needed(self):
        """Where the pill fits whole with the tabs a pixel further apart, they are not drawn closer: the room at the sides is
        the most that leaves the pill whole - or the least, for the version alone or the header."""
        for where, row in self.each():
            side = row["pads"][0][0]
            with self.subTest(where):
                if row["fit"] == "whole" and side < row["full"]:
                    self.assertGreaterEqual(side, row["least"])
                if row["fit"] == "header":
                    self.assertEqual(side, row["least"], "the closest tabs left no room")

    def test_in_the_header_at_the_end_of_the_second_line_under_the_caption_buttons(self):
        seen = 0
        for where, row in self.each():
            if row["fit"] != "header":
                continue
            seen += 1
            x, y, w, h = row["pill"]
            cx, cy, cw, ch = row["card"]
            lx, ly, lw, lh = row["line"]
            with self.subTest(where):
                self.assertLessEqual(abs(row["outer"] - row["inset"]), 1, "Brand.PillInset from the card's edge")
                self.assertGreaterEqual(y, row["captionBottom"] - 1, "under the caption buttons")
                self.assertLessEqual(abs((y + h / 2) - (ly + lh / 2)), 2, "on the second line")
                if where.startswith("ar "):
                    self.assertLess(x + w, lx, "mirrored: at the card's left end, before the line")
                    self.assertLessEqual(abs(x - cx - row["inset"]), 1)
                else:
                    self.assertGreater(x, lx + lw, "after the line")
                    self.assertLessEqual(abs(cx + cw - (x + w) - row["inset"]), 1)
        self.assertGreater(seen, 0, "some window put the pill in the header (the narrowest, in a long language)")

    def test_back_in_the_row_when_there_is_room_again(self):
        for where, answer in self.answer.items():
            with self.subTest(where):
                self.assertEqual(answer["again"]["fit"], answer["eightChosen"]["fit"])


class PillRoomSourceTests(unittest.TestCase):
    def test_the_least_is_a_named_constant_about_half_of_today(self):
        window = guiscan.read("gui/SettingsApp.cs")
        self.assertIn("internal const int TabPadX = 18, TabPadXLeast = 9, TabPadY = 8;", window)
        self.assertIn("button.Padding = Pad(TabPadX, TabPadY, TabPadX, TabPadY);", guiscan.read("gui/Dashboard.cs"))


if __name__ == "__main__":
    unittest.main()
