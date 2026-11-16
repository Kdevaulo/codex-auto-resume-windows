r"""v0.6.24-beta.2: the Dashboard's new proportions (the owner's decision of 2026-11-16, from mockups).

- The window opens 1000 by 588 at text size 1 (SettingsForm.OpeningHeight; 664 and 681 with the caption room before).
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
            var findings = new List<string>();
            AuditPill(findings);
            said["findings"] = string.Join("\n", findings.ToArray());
            return said;
        }

        internal static void ProportionsRun(string dir, Dictionary<string, object> said)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(null);
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
                    form.ClientSize = opening;
                    // A press on the pill is a press on the version (VersionPressed): one press of the run it counts.
                    FieldInfo count = typeof(PressRun).GetField("count", BindingFlags.Instance | BindingFlags.NonPublic);
                    MethodInfo down = typeof(Control).GetMethod("OnMouseDown", BindingFlags.Instance | BindingFlags.NonPublic);
                    down.Invoke(form.versionPill, new object[] { new MouseEventArgs(MouseButtons.Left, 1, 4, 4, 0) });
                    answer["pillPress"] = (double)(int)count.GetValue(form.versionPresses);
                    down.Invoke(form.versionText, new object[] { new MouseEventArgs(MouseButtons.Left, 1, 4, 4, 0) });
                    answer["labelPress"] = (double)(int)count.GetValue(form.versionPresses);
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

    def test_the_window_opens_1000_by_588_at_text_size_1(self):
        said = self.answer["en"]
        self.assertEqual(said["heroRoom"], 0, "English's two lines fit the 76 px card")
        self.assertEqual(said["opening"], [1000, 588])
        self.assertEqual(said["client"], [1000, 588])

    def test_the_header_card_is_two_lines_in_76_px(self):
        for locale in LOCALES:
            said = self.answer[locale]
            with self.subTest(locale=locale):
                self.assertEqual(said["heroPadding"], [15, 15])
                # A language whose two lines are taller makes a taller card, and the window opens taller by as much.
                self.assertEqual(said["hero"], 76 + said["heroRoom"])
                self.assertEqual(said["opening"][1], 588 + said["heroRoom"])

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
                self.assertIn(said["advancedWord"], pill["text"], "an advanced edition's word beside the version")
                self.assertEqual(pill["name"], pill["text"], "a screen reader is told the version and the edition")
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
                self.assertEqual(standard["text"], "v0.6.24-beta.2", "the standard edition is named nowhere (2026-10-05)")

    def test_where_the_tabs_need_the_width_the_pill_shortens_then_goes(self):
        for locale in LOCALES:
            said = self.answer[locale]
            with self.subTest(locale=locale):
                narrow = said["narrowest800"]
                self.assertIn(narrow["fit"], ("whole", "version"))
                self.assertEqual(narrow["findings"], "")
                if narrow["fit"] == "version":
                    self.assertEqual(narrow["text"], "v0.6.24-beta.2")
                    self.assertIn(said["advancedWord"], narrow["name"], "the edition is still said to a screen reader")
                self.assertEqual(said["tooNarrow"]["fit"], "none", "where even the version does not fit, no pill")

    def test_a_press_on_the_pill_is_a_press_on_the_version(self):
        for locale in LOCALES:
            said = self.answer[locale]
            with self.subTest(locale=locale):
                self.assertEqual(said["pillPress"], 1)
                self.assertEqual(said["labelPress"], 2)


class DashboardProportionsSourceTests(unittest.TestCase):
    def test_the_numbers(self):
        window = guiscan.read("gui/SettingsApp.cs")
        self.assertIn("internal const int OpeningHeight = 588;", window)
        self.assertIn("internal const int HeroHeight = 76;", window)
        self.assertNotIn("closeButton", guiscan.window())
        self.assertNotIn('S("action.close", "Close")', guiscan.member_body("SettingsForm", "BuildFooter"))
        self.assertIn("if (Soft.OwnVisible(footer) != settings) footer.Visible = settings;", guiscan.member_body("SettingsForm", "ShowPage"))


if __name__ == "__main__":
    unittest.main()
