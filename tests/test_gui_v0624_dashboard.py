r"""v0.6.24-beta.2: the Dashboard's new proportions (the owner's decision of 2026-11-16, from mockups).

- The window opens 1000 by 618 at text size 1 (SettingsForm.OpeningHeight; the owner's decision of 2026-11-18, from real
  renders, the Overview's cards not growing; 588 in beta.2, 664 and 681 with the caption room before).
- The header card stays two lines and is 76 px tall at 100 % (HeroHeight: HeroPadY above and below the two lines).
- No footer card under any page but Settings: the save bar is Settings' alone, inside the height every page has, with the
  reopen note, Restore defaults and Save; the Close button is gone (the header's X closes the window).
- The version - and an advanced edition's word beside it, as the window says it everywhere else (VersionLabel; the
  standard edition is named nowhere, the owner's rule of 2026-10-05) - is a small raised pill at the outer end of the page
  tabs (VersionPill): centred on them, never over a tab, never reached by the Tab key, pressed as the version was
  (VersionPressed), named for a screen reader whole; where the tabs need the width it shows the version alone, then none;
  mirrored to the left end for a language written right to left.

A probe compiled with the window builds it never shown (TopLevel = false, as LayoutAudit does) at 100 %, in English and
Arabic. GUI test module (it makes windows, never shown): run on its own, through gui_lock.sh.
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
LOCALES = ("en", "ar")

PROBE = r"""
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class DashboardProportionsProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { SettingsForm.ProportionsRun(argv[1], said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        private static List<object> ProportionsBox(Rectangle r)
        {
            return new List<object> { (double)r.X, (double)r.Y, (double)r.Width, (double)r.Height };
        }

        private static Rectangle ProportionsIn(Control control, Control within)
        {
            var box = new Rectangle(Point.Empty, control.Size);
            for (Control c = control; c != null && c != within; c = c.Parent) box.Offset(c.Left, c.Top);
            return box;
        }

        private Dictionary<string, object> ProportionsPage(string page)
        {
            ShowPage(page);
            Materialise(this);
            PerformLayout();
            var said = new Dictionary<string, object>();
            said["footer"] = Soft.OwnVisible(footer);
            said["pageBottom"] = (double)pageHost.Bottom;
            said["footerTop"] = (double)footer.Top;
            said["footerBottom"] = (double)footer.Bottom;
            said["save"] = Soft.OwnVisible(saveButton) && saveButton.Parent != null && saveButton.Parent.Parent == savebar;
            said["restore"] = Soft.OwnVisible(restoreButton) && restoreButton.Parent != null && restoreButton.Parent.Parent == savebar;
            said["note"] = reopenNote.Parent == savebar;
            int above, below;
            said["tabRow"] = TabRowRoom(page, out above, out below) ? new List<object> { (double)above, (double)below } : null;
            return said;
        }

        private Dictionary<string, object> ProportionsPill(int width)
        {
            ClientSize = new Size(Px(width), ClientSize.Height);
            ShowPage("overview");
            Materialise(this);
            PerformLayout();
            var said = new Dictionary<string, object>();
            said["fit"] = PillFit;
            said["text"] = versionText.Text;
            said["name"] = versionPill.AccessibleName ?? "";
            if (PillFit == "none") return said;
            Rectangle pill = ProportionsIn(versionPill, nav);
            said["pill"] = ProportionsBox(pill);
            Rectangle tabs = Rectangle.Empty;
            foreach (NavButton tab in navButtons.Values)
            {
                Rectangle face = ProportionsIn(tab, nav);
                tabs = tabs.IsEmpty ? face : Rectangle.Union(tabs, face);
            }
            said["tabs"] = ProportionsBox(tabs);
            said["room"] = ProportionsBox(nav.DisplayRectangle);
            int outer, start;
            PillInsets(out outer, out start);
            said["insets"] = new List<object> { (double)outer, (double)start };
            said["pillInset"] = (double)Px(Brand.PillInset);
            var findings = new List<string>();
            AuditPill(findings);
            said["findings"] = string.Join("\n", findings.ToArray());
            return said;
        }

        /// Where the line under the headline is with the egg's sentence: what it will say, whether that is on its way or said,
        /// the words it shows now and its own words behind the sentence.
        private Dictionary<string, object> ProportionsAside()
        {
            var said = new Dictionary<string, object>();
            BindingFlags hidden = BindingFlags.Instance | BindingFlags.NonPublic;
            said["words"] = (string)typeof(AsideLabel).GetField("words", hidden).GetValue(detail) ?? "";
            said["waiting"] = (bool)typeof(AsideLabel).GetField("waiting", hidden).GetValue(detail);
            said["saying"] = detail.Saying;
            said["shows"] = detail.Text ?? "";
            said["behind"] = (string)typeof(AsideLabel).GetField("behind", hidden).GetValue(detail) ?? "";
            return said;
        }

        /// The special eggs' parts on their own (v0.6.24-beta.2): the colour run's steps and colours, the confetti's pieces, and
        /// the pick from a seeded random source.
        internal static Dictionary<string, object> ProportionsEggParts()
        {
            var said = new Dictionary<string, object>();
            var states = new List<object>();
            foreach (double ms in new[] { -1.0, 0.0, 419.0, 420.0, 840.0, 1260.0, 1679.0, 1680.0, 2099.0, 2100.0 })
                states.Add(HaloDot.ColourRunStateAt(ms) ?? "");
            said["states"] = states;
            said["runMs"] = (double)HaloDot.ColourRunMs;
            Color own = Color.FromArgb(1, 2, 3);
            Func<string, Color> fill = delegate(string state) { return HaloDot.DotColour(state, false); };
            var colours = new List<object>();
            foreach (double ms in new[] { 0.0, 210.0, 630.0, 1050.0, 1470.0, 1785.0, 2100.0 })
                colours.Add(HaloDot.ColourRunAt(ms, own, fill).ToArgb() == own.ToArgb() ? "own" :
                            Array.Find(HaloDot.ColourRunStates, delegate(string state) { return fill(state).ToArgb() == HaloDot.ColourRunAt(ms, own, fill).ToArgb(); }) ?? "between");
            said["colours"] = colours;
            var distinct = new List<int>();
            foreach (string state in HaloDot.ColourRunStates) if (!distinct.Contains(fill(state).ToArgb())) distinct.Add(fill(state).ToArgb());
            said["distinctColours"] = (double)distinct.Count;
            var burst = new ConfettiBurst(new Random(7), new PointF(300, 140), 1f, ConfettiBurst.Colours());
            var brand = new List<int>();
            foreach (Color colour in ConfettiBurst.Colours()) brand.Add(colour.ToArgb());
            double minX = double.MaxValue, maxX = double.MinValue, minY = double.MaxValue, maxY = double.MinValue;
            bool startsTogether = true, moved = false, opaqueEarly = true, goneAtEnd = true, inBrand = true;
            for (int i = 0; i < ConfettiBurst.Pieces; i++)
            {
                double opacity;
                PointF at = burst.At(i, 0, out opacity);
                if (at.X != 300 || at.Y != 140) startsTogether = false;
                if (!brand.Contains(burst.ColourOf(i).ToArgb())) inBrand = false;
                for (double ms = 0; ms <= ConfettiBurst.LengthMs; ms += 25)
                {
                    at = burst.At(i, ms, out opacity);
                    if (opacity > 0)
                    {
                        minX = Math.Min(minX, at.X); maxX = Math.Max(maxX, at.X);
                        minY = Math.Min(minY, at.Y); maxY = Math.Max(maxY, at.Y);
                    }
                    if (ms == 600 && (at.X != 300 || at.Y != 140)) moved = true;
                    if (ms <= 800 && opacity < 1.0) opaqueEarly = false;
                    if (ms >= ConfettiBurst.LengthMs && opacity > 0.0) goneAtEnd = false;
                }
            }
            said["confetti"] = new Dictionary<string, object> {
                { "startsTogether", startsTogether }, { "moved", moved }, { "opaqueEarly", opaqueEarly }, { "goneAtEnd", goneAtEnd },
                { "inBrand", inBrand }, { "box", new List<object> { minX - 300, maxX - 300, minY - 140, maxY - 140 } } };
            var pick = new EggPick();
            pick.Next = new Random(11).Next;
            var picked = new List<object>();
            for (int i = 0; i < 300; i++) picked.Add((double)pick.Pick());
            said["picked"] = picked;
            return said;
        }

        /// v0.6.24-beta.2 (the live re-check 8): a scrolling page with a card under the tab row's gap, its background drawn as
        /// the window draws it (Ground.Paint), in light and dark, at 100, 150 and 200 %, at rest and scrolled - with the top
        /// band's fade and without it. Per case: how far the page's top row is from its ground at most, across the card's top
        /// and its left lift; and how much steeper than the lift's own any column's steepest step is, in colour levels.
        /// The tabs' own row as FitVersionPill reckons it: each shown tab as wide as it asks, with its margins.
        private static int ProportionsTabsWidth(Control strip)
        {
            int width = strip.Padding.Horizontal;
            foreach (Control tab in strip.Controls)
                if (Soft.OwnVisible(tab)) width += tab.GetPreferredSize(Size.Empty).Width + tab.Margin.Horizontal;
            return width;
        }

        internal static Dictionary<string, object> ProportionsFade()
        {
            var said = new Dictionary<string, object>();
            foreach (string theme in new[] { "light", "dark" })
                foreach (double scale in new[] { 1.0, 1.5, 2.0 })
                    foreach (int scrolled in new[] { 0, 30 })
                    {
                        Palette.Adopt(theme);
                        AdoptDisplayScale(scale);
                        bool overflowing;
                        Rectangle card;
                        Color ground;
                        int band;
                        using (Bitmap faded = FadeRender(true, scrolled, out overflowing, out card, out ground, out band))
                        using (Bitmap cut = FadeRender(false, scrolled, out overflowing, out card, out ground, out band))
                        {
                            int top = 0, cutTop = 0, excess = int.MinValue;
                            int rows = Math.Min(faded.Height, band + Soft.Px(4));
                            for (int x = Math.Max(0, card.Left - Soft.Px(14)); x < Math.Min(faded.Width, card.Left + Soft.Px(60)); x++)
                            {
                                top = Math.Max(top, Levels(faded.GetPixel(x, 0), ground));
                                cutTop = Math.Max(cutTop, Levels(cut.GetPixel(x, 0), ground));
                                int steepest = 0, own = 0;
                                for (int y = 1; y < rows; y++)
                                {
                                    if (card.Contains(x, y) || card.Contains(x, y - 1)) continue;
                                    steepest = Math.Max(steepest, Levels(faded.GetPixel(x, y), faded.GetPixel(x, y - 1)));
                                    own = Math.Max(own, Levels(cut.GetPixel(x, y), cut.GetPixel(x, y - 1)));
                                }
                                excess = Math.Max(excess, steepest - own);
                            }
                            var at = new Dictionary<string, object>();
                            at["overflowing"] = overflowing;
                            at["top"] = (double)top;
                            at["cutTop"] = (double)cutTop;
                            at["excess"] = (double)excess;
                            said[theme + " " + scale.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture) + " " + scrolled] = at;
                        }
                    }
            return said;
        }

        private static int Levels(Color one, Color other)
        {
            return Math.Max(Math.Abs(one.R - other.R), Math.Max(Math.Abs(one.G - other.G), Math.Abs(one.B - other.B)));
        }

        private static Bitmap FadeRender(bool fade, int scrolled, out bool overflowing, out Rectangle card, out Color ground, out int band)
        {
            var page = new SoftPage();
            page.Size = new Size(Soft.Px(500), Soft.Px(300));
            page.Padding = new Padding(Soft.Px(16), Soft.Px(TabRowGap) - Soft.Px(TabRing), Soft.Px(17), Soft.Px(17));
            var spacer = new Panel();
            spacer.Dock = DockStyle.Top;
            spacer.Height = Soft.Px(2000);
            var body = new SoftCard();
            body.Dock = DockStyle.Top;
            body.Height = Soft.Px(120);
            page.Controls.Add(spacer);
            page.Controls.Add(body);
            page.Scrolls = true;
            if (fade) page.FadeTop = page.Padding.Top;
            page.PerformLayout();
            if (scrolled > 0) page.ScrollTo(Soft.Px(scrolled), false);
            overflowing = page.Overflowing;
            card = body.Bounds;
            ground = Ground.Colour(page);
            band = page.Padding.Top;
            var image = new Bitmap(page.Width, page.Height);
            using (Graphics g = Graphics.FromImage(image))
            using (var e = new PaintEventArgs(g, new Rectangle(Point.Empty, page.Size)))
                Ground.Paint(page, e);
            page.Dispose();
            return image;
        }

        internal static void ProportionsRun(string dir, Dictionary<string, object> said)
        {
            said["eggParts"] = ProportionsEggParts();
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(null);
            said["fade"] = ProportionsFade();
            Palette.Adopt("light");
            AdoptDisplayScale(1.0);
            foreach (string locale in new[] { "en", "ar" })
            {
                var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-" + locale + ".json"), Encoding.UTF8)) as Dictionary<string, object>;
                // At 100 % on any machine: the window's font at the scale of this machine's sign-in, as LayoutAudit makes it.
                dpiScale = 1.0;
                float factor = (float)(1.0 / SystemScale);
                Font box = SystemFonts.MessageBoxFont;
                var windowFont = new Font(box.FontFamily, box.SizeInPoints * factor, box.Style, GraphicsUnit.Point);
                Mirror.Window = Mirror.Language(locale);
                string nowhere = Path.Combine(dir, "nowhere-" + locale);
                var answer = new Dictionary<string, object>();
                using (var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, windowFont))
                {
                    form.auditing = true;
                    form.TopLevel = false;
                    form.MinimumSize = Size.Empty;
                    Size opening = form.OpeningClient;
                    form.ClientSize = opening;
                    answer["opening"] = new List<object> { (double)opening.Width, (double)opening.Height };
                    answer["heroRoom"] = (double)form.heroRoom;
                    form.ShowPage("overview");
                    Materialise(form);
                    form.PerformLayout();
                    answer["hero"] = (double)form.hero.Height;
                    answer["heroPadding"] = new List<object> { (double)form.hero.Padding.Top, (double)form.hero.Padding.Bottom };
                    answer["headerBottom"] = (double)form.header.Bottom;
                    answer["navBottom"] = (double)form.nav.Bottom;
                    answer["client"] = new List<object> { (double)form.ClientSize.Width, (double)form.ClientSize.Height };
                    var pages = new Dictionary<string, object>();
                    foreach (string page in PageOrder) pages[page] = form.ProportionsPage(page);
                    answer["pages"] = pages;
                    // v0.6.24-beta.2 (the owner, 2026-11-17, row 17, option C): with the watcher off, Start watcher in the Right
                    // now card in Pause's place and nothing in the header; once it runs, Pause and no Start watcher.
                    form.ShowPage("overview");
                    var actions = new Dictionary<string, object>();
                    foreach (bool off in new[] { true, false })
                    {
                        form.watcherOff = off;
                        form.ShowWatcherAction();
                        Materialise(form);
                        form.PerformLayout();
                        var at = new Dictionary<string, object>();
                        at["start"] = Soft.OwnVisible(form.startButton);
                        at["pause"] = Soft.OwnVisible(form.toggleButton);
                        at["sameCard"] = form.startButton.Parent != null && form.startButton.Parent == form.toggleButton.Parent;
                        bool inHeader = false;
                        for (Control c = form.startButton.Parent; c != null; c = c.Parent) if (c == form.header) inHeader = true;
                        at["inHeader"] = inHeader;
                        at["warning"] = form.nowWatcher.ForeColor.ToArgb() == Palette.Warning.ToArgb();
                        if (off) at["startBox"] = ProportionsBox(ProportionsIn(form.startButton, form));
                        else at["pauseBox"] = ProportionsBox(ProportionsIn(form.toggleButton, form));
                        actions[off ? "off" : "on"] = at;
                    }
                    answer["watcherActions"] = actions;
                    answer["closeField"] = typeof(SettingsForm).GetField("closeButton", BindingFlags.Instance | BindingFlags.NonPublic) != null;
                    // The pill, with an advanced edition's word and with the standard edition's none.
                    form.ShowVersion(form.versionText, new Dictionary<string, object> { { "version", "0.6.24-beta.2" }, { "edition", "advanced" } });
                    answer["advancedWord"] = form.S("edition.advanced", "Advanced");
                    answer["pillTabStop"] = form.versionPill.TabStop || form.versionText.TabStop;
                    answer["pillParent"] = form.versionText.Parent == form.versionPill && form.versionPill.Parent == form.pillSlot &&
                                           form.pillSlot.Parent == form.nav;
                    answer["opening1000"] = form.ProportionsPill(OpeningWidth);
                    answer["narrowest800"] = form.ProportionsPill(800);
                    answer["tooNarrow"] = form.ProportionsPill(480);
                    form.ShowVersion(form.versionText, new Dictionary<string, object> { { "version", "0.6.24-beta.2" }, { "edition", "standard" } });
                    answer["standard"] = form.ProportionsPill(OpeningWidth);
                    // A tab shown later, as the advanced edition shows Advanced features and Chat once their words come:
                    // the pill gives way to it, with nothing else laid out again (dev CI 43859506322, the Chat tab cut off).
                    NavButton settings = form.navButtons["settings"];
                    var later = new NavButton();
                    later.Font = settings.Font;
                    later.AutoSize = true;
                    later.AutoSizeMode = AutoSizeMode.GrowAndShrink;
                    later.Padding = settings.Padding;
                    later.Margin = settings.Margin;
                    later.Text = "Advanced features";
                    later.Visible = false;
                    settings.Parent.Controls.Add(later);
                    form.navButtons["later"] = later;
                    var other = new NavButton();
                    other.Font = settings.Font;
                    other.AutoSize = true;
                    other.AutoSizeMode = AutoSizeMode.GrowAndShrink;
                    other.Padding = settings.Padding;
                    other.Margin = settings.Margin;
                    other.Text = "Chat";
                    other.Visible = false;
                    settings.Parent.Controls.Add(other);
                    form.navButtons["other"] = other;
                    var before = form.ProportionsPill(OpeningWidth);
                    later.Visible = true;
                    other.Visible = true;
                    var grown = new Dictionary<string, object>();
                    grown["before"] = before["fit"];
                    grown["shown"] = form.PillFit;
                    // On any screen and in any font the tabs come to need the pill's room: the Chat tab's words grow, which
                    // lays out the strip alone, until the tabs, the gap and the whole pill no longer fit in the row (GitHub's
                    // runners' fonts are narrower than this PC's, and the two tabs alone left the pill whole there).
                    Control row = settings.Parent;
                    for (int grow = 0; grow < 60 && ProportionsTabsWidth(row) + form.Px(12) + form.versionPill.WholeWidth <= form.nav.DisplayRectangle.Width; grow++)
                        other.Text += " Chat";
                    grown["grew"] = ProportionsTabsWidth(row) + form.Px(12) + form.versionPill.WholeWidth > form.nav.DisplayRectangle.Width;
                    grown["fit"] = form.PillFit;
                    var cut = new List<string>();
                    foreach (NavButton tab in form.navButtons.Values)
                        if (Soft.OwnVisible(tab) && (tab.Left < 0 || tab.Right > tab.Parent.ClientSize.Width)) cut.Add(tab.Text);
                    var findings = new List<string>();
                    form.AuditPill(findings);
                    grown["cut"] = string.Join(", ", cut.ToArray());
                    grown["findings"] = string.Join(" | ", findings.ToArray());
                    answer["grown"] = grown;
                    form.ClientSize = opening;
                    // A press on the pill is a press on the version (VersionPressed), and one press is the egg (the owner,
                    // 2026-11-16): the sentence on its way or said. Then, as if the sweep had ended, the sentence said, and a
                    // press on the version's words 2 s later - a new run - starts it again from its start, nothing stacked on the
                    // line's own words. The presses' clock is the probe's.
                    double clock = 0.0;
                    form.PressNow = delegate { return clock; };
                    MethodInfo down = typeof(Control).GetMethod("OnMouseDown", BindingFlags.Instance | BindingFlags.NonPublic);
                    form.detail.Text = "The line's own words";
                    form.EggsPlayed.Clear();
                    down.Invoke(form.versionPill, new object[] { new MouseEventArgs(MouseButtons.Left, 1, 4, 4, 0) });
                    var first = form.ProportionsAside();
                    answer["pillPress"] = first;
                    if ((bool)first["waiting"])
                        typeof(AsideLabel).GetMethod("Speak", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(form.detail, null);
                    answer["said"] = form.ProportionsAside();
                    clock = Math.Max(clock, form.SpecialUntil) + 2000;
                    down.Invoke(form.versionText, new object[] { new MouseEventArgs(MouseButtons.Left, 1, 4, 4, 0) });
                    answer["labelPress"] = form.ProportionsAside();
                    answer["twoRuns"] = string.Join(",", form.EggsPlayed.ToArray());
                    answer["sentence"] = form.S("status.aside", "It's okay if it stops. I'll pick it up.");
                    // The sixth press in a row plays a special egg instead (the owner, 2026-11-16, "6번", "3개 중 하나가 랜덤으로
                    // 뜨게 하자"): four runs of six presses, the picks given (0, then 0, 0 and 1 of the two left), the count
                    // read standing in (3, then 0). Never shown, nothing here may move: each is its sentence alone, at once.
                    form.auditing = false;
                    FieldInfo run = typeof(PressRun).GetField("count", BindingFlags.Instance | BindingFlags.NonPublic);
                    var picks = new Queue<int>(new[] { 0, 0, 0, 1 });
                    var asked = new List<object>();
                    form.SpecialEggs.Next = delegate(int kinds) { asked.Add((double)kinds); return picks.Count > 0 ? picks.Dequeue() : 0; };
                    int counted = 3;
                    form.ReadRecoveredAllTime = delegate(Action<int> then) { then(counted); };
                    var runs = new List<object>();
                    for (int round = 0; round < 4; round++)
                    {
                        if (round == 3) counted = 0;
                        clock = Math.Max(clock, form.SpecialUntil) + 2000;
                        var played = new List<object>();
                        for (int press = 0; press < 6; press++)
                        {
                            clock += 100;
                            form.EggsPlayed.Clear();
                            down.Invoke(form.versionPill, new object[] { new MouseEventArgs(MouseButtons.Left, 1, 4, 4, 0) });
                            played.Add(string.Join(",", form.EggsPlayed.ToArray()));
                        }
                        var round_ = new Dictionary<string, object>();
                        round_["played"] = played;
                        round_["aside"] = form.ProportionsAside();
                        round_["colours"] = form.stateDot.ColoursRunning;
                        round_["confetti"] = form.confetti != null;
                        runs.Add(round_);
                    }
                    answer["runs"] = runs;
                    answer["asked"] = new List<object>(asked);   // the four rounds' picks, before the runs below
                    // The owner, 2026-11-17: one run of six, 0.3 s apart, plays the one-press egg once and the special one
                    // alone - what the run played, in order, and the line as the special egg starts on it.
                    clock = Math.Max(clock, form.SpecialUntil) + 2000;
                    form.EggsPlayed.Clear();
                    for (int press = 0; press < 6; press++)
                    {
                        clock += 300;
                        down.Invoke(form.versionPill, new object[] { new MouseEventArgs(MouseButtons.Left, 1, 4, 4, 0) });
                    }
                    answer["oneRun"] = string.Join(",", form.EggsPlayed.ToArray());
                    answer["oneRunAside"] = form.ProportionsAside();
                    answer["oneRunSweeping"] = form.stateDot.Sweeping;
                    // The owner, 2026-11-17, pressing on past six: thirty presses 0.3 s apart. A special egg ignores every press
                    // while it plays (its sentence's whole time, SpecialUntil); the next press after it begins a new run.
                    clock = form.SpecialUntil + 2000;
                    form.EggsPlayed.Clear();
                    var during = new List<object>();
                    for (int press = 0; press < 30; press++)
                    {
                        clock += 300;
                        bool playing = clock < form.SpecialUntil;
                        int countBefore = form.EggsPlayed.Count;
                        string saidBefore = (string)form.ProportionsAside()["words"];
                        down.Invoke(form.versionPill, new object[] { new MouseEventArgs(MouseButtons.Left, 1, 4, 4, 0) });
                        if (playing)
                            during.Add(form.EggsPlayed.Count == countBefore && (string)form.ProportionsAside()["words"] == saidBefore &&
                                       (int)run.GetValue(form.versionPresses) == 0);
                    }
                    answer["pressingOn"] = string.Join(",", form.EggsPlayed.ToArray());
                    answer["pressesDuring"] = during;
                    // Unsay on its own: an aside on its way gone at once, its own words back with no fade.
                    form.detail.Aside("Something to say", 500, 1000);
                    form.detail.Unsay();
                    answer["unsaid"] = form.ProportionsAside();
                    answer["unsaidFading"] = form.detail.Fading;
                    // In a picture or the layout audit the sixth press is no special egg.
                    form.auditing = true;
                    clock = Math.Max(clock, form.SpecialUntil) + 2000;
                    var audited = new List<object>();
                    for (int press = 0; press < 6; press++)
                    {
                        clock += 100;
                        form.EggsPlayed.Clear();
                        down.Invoke(form.versionPill, new object[] { new MouseEventArgs(MouseButtons.Left, 1, 4, 4, 0) });
                        audited.Add(string.Join(",", form.EggsPlayed.ToArray()));
                    }
                    answer["audited"] = audited;
                    var words = new Dictionary<string, object>();
                    foreach (string key in new[] { "status.aside_colours", "status.aside_confetti", "status.aside_count_many",
                                                   "status.aside_count_none", "status.aside_count_one" })
                        words[key] = form.S(key, "");
                    answer["eggWords"] = words;
                    answer["countOne"] = form.CountAside(1);
                    answer["countUnread"] = form.CountAside(-1);
                }
                said[locale] = answer;
            }
        }
    }
}
"""


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class DashboardProportionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        for locale in LOCALES:
            reply = {"ok": True, "language": locale, "strings": l10n.catalog(locale), "endonyms": dict(l10n.ENDONYMS),
                     "preference": locale, "system_language": locale}
            (work / ("strings-%s.json" % locale)).write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        probe = work / "DashboardProportionsProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "DashboardProportions.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.DashboardProportionsProbe",
                                "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
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

    def test_the_window_opens_1000_by_618_at_text_size_1(self):
        said = self.answer["en"]
        self.assertEqual(said["heroRoom"], 0, "English's two lines fit the 76 px card")
        self.assertEqual(said["opening"], [1000, 618])
        self.assertEqual(said["client"], [1000, 618])

    def test_the_header_card_is_two_lines_in_76_px(self):
        for locale in LOCALES:
            said = self.answer[locale]
            with self.subTest(locale=locale):
                self.assertEqual(said["heroPadding"], [15, 15])
                # A language whose two lines are taller makes a taller card, and the window opens taller by as much.
                self.assertEqual(said["hero"], 76 + said["heroRoom"])
                self.assertEqual(said["opening"][1], 618 + said["heroRoom"])

    def test_no_footer_outside_settings_and_the_save_bar_on_settings(self):
        for locale in LOCALES:
            said = self.answer[locale]
            height = said["client"][1]
            for page, at in said["pages"].items():
                with self.subTest(locale=locale, page=page):
                    if page == "settings":
                        self.assertTrue(at["footer"], "Settings keeps its save bar")
                        self.assertEqual(at["footerBottom"], height, "at the window's foot")
                        self.assertEqual(at["pageBottom"], at["footerTop"], "inside the height the pages have")
                        self.assertTrue(at["save"] and at["restore"], "Restore defaults and Save on the save bar")
                    else:
                        self.assertFalse(at["footer"], "a footer under " + page)
                        self.assertEqual(at["pageBottom"], height, "the page reaches the window's foot")
                    self.assertTrue(at["note"], "the reopen note is the save bar's")
            with self.subTest(locale=locale, what="Close"):
                self.assertFalse(said["closeField"], "the save bar's Close is gone: the header's X closes the window")

    def test_the_version_is_a_pill_at_the_end_of_the_tabs(self):
        for locale in LOCALES:
            said = self.answer[locale]
            pill = said["opening1000"]
            with self.subTest(locale=locale):
                self.assertTrue(said["pillParent"], "the version's label in the pill, in its slot in the tab strip's row")
                self.assertFalse(said["pillTabStop"], "not a tab: never reached by the Tab key")
                self.assertEqual(pill["fit"], "whole")
                self.assertEqual(pill["findings"], "", "the layout audit's AuditPill")
                self.assertIn("0.6.24-beta.2", pill["text"])
                # v0.6.24 (the owner, 2026-11-18): the version alone, the edition told by its ink and to a screen reader.
                self.assertEqual(pill["text"], "0.6.24-beta.2", "the number alone (2026-11-19), never the edition's word")
                self.assertEqual(pill["name"], pill["text"] + " " + said["advancedWord"], "a screen reader is told both")
                x, y, w, h = pill["pill"]
                tx, ty, tw, th = pill["tabs"]
                rx, ry, rw, rh = pill["room"]
                self.assertLessEqual(abs((y + h / 2) - (ty + th / 2)), 1, "centred on the tabs")
                self.assertLess(h, th, "smaller than a tab")
                if locale == "ar":
                    self.assertEqual(x, rx, "mirrored: at the strip's left end")
                    self.assertLess(x + w, tx, "and before the first tab")
                else:
                    self.assertEqual(x + w, rx + rw, "at the strip's right end")
                    self.assertGreater(x, tx + tw, "and after the last tab")
                standard = said["standard"]
                self.assertEqual(standard["fit"], "whole")
                self.assertEqual(standard["text"], "0.6.24-beta.2", "the standard edition is named nowhere (2026-10-05)")

    def test_the_tab_row_s_ends_stand_inside_the_header_card_s_edges(self):
        """The owner, 2026-11-17 (the design canvas's row 18): a round end lined up on a straight edge looks as if it sticks
        out, so the version's pill at the tab row's end and the first tab at its start stand Brand.PillInset inside the
        header card's edges - mirrored, the other way round. The value is the constant's, not a number written here."""
        for locale in LOCALES:
            pill = self.answer[locale]["opening1000"]
            outer, start = pill["insets"]
            with self.subTest(locale=locale):
                self.assertGreater(pill["pillInset"], 0)
                self.assertLessEqual(abs(outer - pill["pillInset"]), 1, "the pill: %s" % outer)
                self.assertLessEqual(abs(start - pill["pillInset"]), 1, "the first tab: %s" % start)

    def test_where_the_tabs_need_the_width_the_pill_shortens_then_goes(self):
        for locale in LOCALES:
            said = self.answer[locale]
            with self.subTest(locale=locale):
                narrow = said["narrowest800"]
                self.assertIn(narrow["fit"], ("whole", "version"))
                self.assertEqual(narrow["findings"], "")
                if narrow["fit"] == "version":
                    self.assertEqual(narrow["text"], "0.6.24-beta.2")
                    self.assertIn(said["advancedWord"], narrow["name"], "the edition is still said to a screen reader")
                # v0.6.24 (the owner, 2026-11-18): never hidden - where even the closest tabs leave no room, in the header
                # card (test_gui_pill_room).
                self.assertEqual(said["tooNarrow"]["fit"], "header", "where even the version does not fit, in the header")
                self.assertEqual(said["tooNarrow"]["findings"], "")

    def test_a_tab_shown_later_takes_the_pill_s_room(self):
        """dev CI 43859506322: the advanced edition shows its Advanced features and Chat tabs once their words come, which
        lays out the tab strip alone - the pill kept the room it had and the Chat tab was cut off in every language."""
        for locale in LOCALES:
            grown = self.answer[locale]["grown"]
            with self.subTest(locale=locale):
                self.assertEqual(grown["before"], "whole")
                # The tabs grown until the whole pill no longer fits beside them, on any screen and in any font (dev CI
                # 44034443580: the runners' narrower fonts left room for it): the tabs drawn closer, then the pill shortened
                # or in the header card (v0.6.24, the owner, 2026-11-18: never hidden), never over a tab.
                self.assertTrue(grown["grew"], "the tabs came to need the pill's room")
                self.assertIn(grown["fit"], ("whole", "version", "header"), "the pill gives way to the tabs, and stays")
                self.assertEqual(grown["cut"], "", "no tab cut off at the strip's end")
                self.assertEqual(grown["findings"], "")

    def test_one_press_on_the_pill_is_the_easter_egg(self):
        """The owner, 2026-11-16: "이스터에그 버전 알약 한번만 눌러도 뜨게 하자" - let one press on the version pill show the
        easter egg (seven presses, each within 1.8 s, were asked before). Every press shows it; a press while it shows starts
        it again from its start, and nothing stacks: the line's own words stay behind the sentence."""
        for locale in LOCALES:
            said = self.answer[locale]
            sentence = said["sentence"]
            with self.subTest(locale=locale):
                first = said["pillPress"]
                self.assertEqual(first["words"], sentence, "one press on the pill shows the egg's sentence")
                self.assertTrue(first["waiting"] or first["saying"])
                self.assertEqual(first["behind"], "The line's own words")
                self.assertTrue(said["said"]["saying"])
                self.assertEqual(said["said"]["shows"], sentence)
                again = said["labelPress"]
                self.assertEqual(again["words"], sentence, "a press on the version's words is a press on the version")
                self.assertTrue(again["waiting"] or again["saying"])
                self.assertEqual(again["behind"], "The line's own words", "the sentence is never taken for the line's own words")
                if again["waiting"]:
                    self.assertEqual(again["shows"], "The line's own words",
                                     "from its start: the line's own words while the sweep plays again, never the sentence held")

    def test_as_much_room_above_the_tab_row_as_below_it(self):
        """The owner, 2026-11-17 (the design canvas's row 15, option C, "촘촘하게"): 10 px from the header card's foot to the
        tabs' faces and 10 px from them to the top of the page's cards, on every page - it was 6 above and 20 below."""
        for locale in LOCALES:
            for page, at in self.answer[locale]["pages"].items():
                with self.subTest(locale=locale, page=page):
                    self.assertIsNotNone(at["tabRow"], "something under the tab row")
                    above, below = at["tabRow"]
                    self.assertLessEqual(abs(above - 10), 1, "above: %s" % above)
                    self.assertLessEqual(abs(below - 10), 1, "below: %s" % below)
                    self.assertLessEqual(abs(above - below), 1)

    def test_with_the_watcher_off_start_watcher_stands_in_pause_s_place(self):
        """The owner, 2026-11-17 (the design canvas's row 17, option C): with the watcher off the header shows the state
        only, and the Right now card's button is Start watcher in place of Pause recovery - the two never stand together."""
        for locale in LOCALES:
            actions = self.answer[locale]["watcherActions"]
            off, on = actions["off"], actions["on"]
            with self.subTest(locale=locale):
                self.assertTrue(off["start"])
                self.assertFalse(off["pause"], "no Pause while the watcher is off")
                self.assertTrue(off["sameCard"])
                self.assertFalse(off["inHeader"])
                self.assertTrue(off["warning"], "the watcher row in the warning colour")
                self.assertFalse(on["start"])
                self.assertTrue(on["pause"])
                self.assertFalse(on["warning"])
                sx, sy, sw, sh = off["startBox"]
                px, py, pw, ph = on["pauseBox"]
                self.assertEqual(sy + sh, py + ph, "in Pause's corner: the same foot")
                if locale == "ar":
                    self.assertEqual(sx + sw, px + pw, "mirrored: the same right edge")
                else:
                    self.assertEqual(sx, px, "the same left edge")

    def test_a_run_plays_the_one_press_egg_once_and_the_special_one_alone(self):
        """The owner, 2026-11-17: "6번 눌러야 뜨는 이스터에그를 보기 위해 여러번 클릭할 때, 1번 누르면 뜨는 이스터에그 시작이
        계속 반복해 / 둘이 중첩되어있네" - pressing towards the sixth restarted the one-press egg at every press, and the two
        overlapped. Within a run only its first press plays the one-press egg; the sixth clears it, nothing of it left, and
        plays the special egg alone; a press after 1.8 s of quiet is a new run."""
        for locale in LOCALES:
            said = self.answer[locale]
            with self.subTest(locale=locale):
                self.assertEqual(said["oneRun"], "one,confetti", "one one-press egg, then the special one (the pick after count)")
                self.assertEqual(said["twoRuns"], "one,one", "two presses 2 s apart: two runs, two one-press eggs")
                aside = said["oneRunAside"]
                self.assertNotEqual(aside["words"], said["sentence"], "the one-press sentence gone")
                self.assertEqual(aside["behind"], "The line's own words")
                self.assertFalse(said["oneRunSweeping"])
                unsaid = said["unsaid"]
                self.assertFalse(unsaid["waiting"] or unsaid["saying"])
                self.assertEqual(unsaid["shows"], "The line's own words")
                self.assertFalse(said["unsaidFading"], "no fade")

    def test_a_scrolling_page_fades_its_first_card_s_lift_instead_of_cutting_it(self):
        """The live re-check 8 (2026-11-17): on Settings and Diagnostics, which scroll, a straight line at the page's top cut
        the first card's lift - 237 above, 242 below, in one step - since the tab row's gap left too little room over the
        card. The page's top band now fades what is stamped there into its ground (SoftPage.FadeTop): its top row is the
        ground, and no column steps more than the lift's own gradient does - light and dark, at 100, 150 and 200 %, at rest
        and scrolled."""
        fade = self.answer["fade"]
        self.assertEqual(len(fade), 12)
        for key, at in sorted(fade.items()):
            with self.subTest(case=key):
                self.assertTrue(at["overflowing"], "the page scrolls")
                self.assertLessEqual(at["top"], 2, "the page's top row is its ground")
                self.assertLessEqual(at["excess"], 2, "a step steeper than the lift's own")
        self.assertGreater(max(at["cutTop"] for at in fade.values()), 2,
                           "without the band the line is there: the case reproduces the re-check's")

    def test_pressing_on_past_six_shows_one_egg_at_a_time(self):
        """The owner, 2026-11-17: "여섯번보다 더 계속 누를 경우는? 정확히 6번만 누르진 않을거잖아". Thirty presses 0.3 s apart:
        the one-press egg, a special one, the one-press egg again, another special one - never the same twice - each alone;
        a press while a special egg plays neither counts nor starts anything."""
        for locale in LOCALES:
            said = self.answer[locale]
            with self.subTest(locale=locale):
                played = said["pressingOn"].split(",")
                self.assertEqual(played[0::2], ["one"] * (len(played) // 2), played)
                self.assertGreaterEqual(len(played), 4, played)
                specials = played[1::2]
                self.assertNotIn("one", specials)
                self.assertFalse([i for i in range(1, len(specials)) if specials[i] == specials[i - 1]], specials)
                self.assertTrue(said["pressesDuring"], "some presses fell while a special egg played")
                self.assertTrue(all(said["pressesDuring"]), "a press during a special egg changed something")

    def test_the_sixth_press_in_a_row_plays_a_special_egg(self):
        """The owner, 2026-11-16: "여러번 누를때의 이스터에그도 별도로 만들자" - a separate egg for many presses - "3개 중
        하나가 랜덤으로 뜨게 하자" - one of three at random - and "6번": five presses are the one-press egg each, the sixth (each
        within 1.8 s of the last) one of the three special ones instead, and the run starts again."""
        for locale in LOCALES:
            said = self.answer[locale]
            with self.subTest(locale=locale):
                played = [run["played"] for run in said["runs"]]
                for run in played:
                    self.assertEqual(run[:5], ["one", "", "", "", ""],
                                     "five presses never play a special egg, and only the first plays the one-press egg")
                self.assertEqual([run[5] for run in played], ["colours", "count", "confetti", "count"])
                self.assertEqual(said["asked"], [3, 2, 2, 2], "the first of three, then one of the two not played last")
                self.assertEqual(said["audited"], ["one", "", "", "", "", ""], "never in a picture or the layout audit")

    def test_each_special_egg_says_its_sentence_and_nothing_moves_where_nothing_may(self):
        for locale in LOCALES:
            said = self.answer[locale]
            words = said["eggWords"]
            colours, count, confetti, none = said["runs"]
            with self.subTest(locale=locale):
                self.assertEqual(colours["aside"]["words"], words["status.aside_colours"])
                self.assertEqual(confetti["aside"]["words"], words["status.aside_confetti"])
                self.assertEqual(none["aside"]["words"], words["status.aside_count_none"], "none picked up yet at 0")
                before, after = words["status.aside_count_many"].split("{n}")
                self.assertTrue(count["aside"]["words"].startswith(before.rstrip()) and "3" in count["aside"]["words"],
                                "the real figure: " + count["aside"]["words"])
                self.assertTrue(count["aside"]["words"].endswith(after.lstrip()))
                self.assertEqual(said["countOne"], words["status.aside_count_one"])
                self.assertEqual(said["countUnread"], said["sentence"], "a count that cannot be read: the one-press sentence")
                # Never shown, motion is not allowed here: no colours run, no confetti - the sentence alone, at once.
                for run in said["runs"]:
                    self.assertFalse(run["colours"])
                    self.assertFalse(run["confetti"])
                    self.assertTrue(run["aside"]["saying"])
                    self.assertEqual(run["aside"]["behind"], "The line's own words")
        if "en" in LOCALES:
            self.assertEqual(self.answer["en"]["runs"][1]["aside"]["words"], "So far I have picked up 3 conversations for you.")

    @property
    def parts(self):
        return self.answer["eggParts"]

    def test_the_light_runs_through_its_four_colours_and_back(self):
        parts = self.parts
        self.assertEqual(parts["states"], ["", "monitoring", "monitoring", "attention", "paused", "failed", "failed", "", "", ""])
        self.assertEqual(parts["runMs"], 2100)
        self.assertEqual(parts["colours"], ["own", "monitoring", "attention", "paused", "failed", "between", "own"])
        self.assertEqual(parts["distinctColours"], 4)

    def test_the_confetti_bursts_from_the_pill_and_falls_within_its_box(self):
        confetti = self.parts["confetti"]
        for key in ("startsTogether", "moved", "opaqueEarly", "goneAtEnd", "inBrand"):
            self.assertTrue(confetti[key], key)
        left, right, top, bottom = confetti["box"]
        # SettingsForm.Confetti's box at 100 %: 260 px either side of the pill, 130 above it, the window's foot below.
        self.assertGreaterEqual(left, -260)
        self.assertLessEqual(right, 260)
        self.assertGreaterEqual(top, -130)
        self.assertGreater(bottom, 0, "it falls")

    def test_the_pick_is_one_of_three_never_the_same_twice_in_a_row(self):
        picked = self.parts["picked"]
        self.assertEqual(set(picked), {0, 1, 2})
        self.assertFalse([i for i in range(1, len(picked)) if picked[i] == picked[i - 1]])
        for kind in (0, 1, 2):
            self.assertGreater(picked.count(kind), 60, "each about a third")

    def test_the_confetti_takes_no_input_and_stays_with_its_window(self):
        layer = guiscan.type_body("ConfettiLayer")
        self.assertIn("internal const int ExStyle = 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000;", layer)
        self.assertNotIn("TOPMOST", layer)
        self.assertIn("cp.Parent = owner.Handle;", layer)
        egg = guiscan.member_body("SettingsForm", "Confetti")
        self.assertIn("!Motion.Allowed(versionPill) || Palette.Contrast", egg)
        self.assertIn("client.Bottom", egg)


class DashboardProportionsSourceTests(unittest.TestCase):
    def test_the_numbers(self):
        window = guiscan.read("gui/SettingsApp.cs")
        self.assertIn("internal const int OpeningHeight = 618;", window)
        self.assertIn("internal const int HeroHeight = 76;", window)
        self.assertNotIn("closeButton", guiscan.window())
        self.assertNotIn('S("action.close", "Close")', guiscan.member_body("SettingsForm", "BuildFooter"))
        self.assertIn("if (Soft.OwnVisible(footer) != settings) footer.Visible = settings;", guiscan.member_body("SettingsForm", "ShowPage"))


if __name__ == "__main__":
    unittest.main()
