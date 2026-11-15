r"""v0.6.24 (stage 1, surface A): the window's own caption on top-level windows, made and never shown (gui/SoftChrome.cs).

The layout audit and test_gui_chrome_window build their windows TopLevel = false: what only a top-level window meets was
never asked there. A probe compiled with the window makes the Dashboard and the dialogs as real top-level windows that are
never shown (no WS_VISIBLE, nothing on the screen), and asks:

- the opening size of a top-level dialog: what it asked plus its title's strip, not one Windows caption taller. Form fills
  the window's size in at CreateWindowEx from its client size with Windows' caption counted
  (Form.FillInCreateParamsStartPosition); SoftDialog's CreateParams answers it without (Chrome.Uncaptioned);
- maximise, then restore: the window back at the size it had, not one caption taller. WinForms turns the client size it
  remembered as the window left its normal state into a window size with its own non-virtual SizeFromClientSize, which
  counts WS_CAPTION (Form.RestoreWindowBoundsIfNecessary); ChromeHost.Restoring answers it without. Maximised by its
  style and SetWindowPos, as Windows' own maximise leaves it, so nothing is shown;
- what the pointer is over on the Dashboard: the tab strip's ground and the save bar's ground drag the window as the hero
  does (HTCAPTION, design 3.4, O7); a tab, the save bar's card with its buttons and the version, and the page are the
  client's (the save bar is never dragged: test_gui_chrome_sources);
- maximised over a monitor with an auto-hide taskbar (the answer of SHAppBarMessage stubbed: Chrome.AppBarEdges), the client
  leaves Chrome.AutoHideRoom px at that edge, so the taskbar can still be brought out by the pointer; with none, the whole;
- in High Contrast, a caption button the window does not offer is drawn in the system's GrayText.

GUI test module (it makes windows, never shown): run on its own, through gui_lock.sh.
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
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class ChromeTopLevelProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { SettingsForm.TopLevelRun(argv[1], said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        private static class TopLevelNative
        {
            [DllImport("user32.dll")] internal static extern bool GetWindowRect(IntPtr h, out Chrome.RECT r);
            [DllImport("user32.dll")] internal static extern bool GetClientRect(IntPtr h, out Chrome.RECT r);
            [DllImport("user32.dll")] internal static extern bool ClientToScreen(IntPtr h, ref Point p);
            [DllImport("user32.dll")] internal static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr w, IntPtr l);
            [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] internal static extern IntPtr GetWindowLongPtr(IntPtr h, int i);
            [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] internal static extern IntPtr SetWindowLongPtr(IntPtr h, int i, IntPtr v);
            [DllImport("user32.dll")] internal static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
            [DllImport("user32.dll")] internal static extern bool IsWindowVisible(IntPtr h);
        }

        private const int TopLevelStyle = -16, TopLevelExStyle = -20, TopLevelMaximize = 0x01000000;
        private const uint TopLevelFlags = 0x0004 | 0x0010 | 0x0020;   // SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED

        private static List<object> Numbers(params int[] values)
        {
            var list = new List<object>();
            foreach (int value in values) list.Add((double)value);
            return list;
        }

        // The window's rectangle on the screen and its client rectangle there, each left, top, width, height.
        private static Dictionary<string, object> TopLevelBox(Form form)
        {
            Chrome.RECT window, client;
            TopLevelNative.GetWindowRect(form.Handle, out window);
            TopLevelNative.GetClientRect(form.Handle, out client);
            var origin = new Point(0, 0);
            TopLevelNative.ClientToScreen(form.Handle, ref origin);
            return new Dictionary<string, object> {
                { "window", Numbers(window.Left, window.Top, window.Right - window.Left, window.Bottom - window.Top) },
                { "client", Numbers(origin.X, origin.Y, client.Right, client.Bottom) },
                { "clientSize", Numbers(form.ClientSize.Width, form.ClientSize.Height) },
                { "state", form.WindowState.ToString() },
                { "visible", TopLevelNative.IsWindowVisible(form.Handle) } };
        }

        private static void TopLevelChildren(Control control)
        {
            MethodInfo create = typeof(Control).GetMethod("CreateControl", BindingFlags.Instance | BindingFlags.NonPublic, null,
                                                          new[] { typeof(bool) }, null);
            create.Invoke(control, new object[] { true });
        }

        // Maximised as Windows leaves a maximised window - its style, and its frame hung past the edges of `area` - without
        // showing it; then back at the rectangle it had.
        private static Dictionary<string, object> TopLevelMaximise(Form form, Rectangle area)
        {
            IntPtr h = form.Handle;
            long style = TopLevelNative.GetWindowLongPtr(h, TopLevelStyle).ToInt64();
            int ex = (int)TopLevelNative.GetWindowLongPtr(h, TopLevelExStyle).ToInt64();
            int frame = Chrome.Frame((int)style, ex).Left;
            TopLevelNative.SetWindowLongPtr(h, TopLevelStyle, (IntPtr)(style | TopLevelMaximize));
            TopLevelNative.SetWindowPos(h, IntPtr.Zero, area.Left - frame, area.Top - frame, area.Width + 2 * frame,
                                        area.Height + 2 * frame, TopLevelFlags);
            Application.DoEvents();
            return TopLevelBox(form);
        }

        private static Dictionary<string, object> TopLevelRestore(Form form, Chrome.RECT was)
        {
            IntPtr h = form.Handle;
            long style = TopLevelNative.GetWindowLongPtr(h, TopLevelStyle).ToInt64();
            TopLevelNative.SetWindowLongPtr(h, TopLevelStyle, (IntPtr)(style & ~(long)TopLevelMaximize));
            TopLevelNative.SetWindowPos(h, IntPtr.Zero, was.Left, was.Top, was.Right - was.Left, was.Bottom - was.Top, TopLevelFlags);
            Application.DoEvents();
            return TopLevelBox(form);
        }

        private static Dictionary<string, object> TopLevelMaxRestore(Form form)
        {
            var said = new Dictionary<string, object>();
            Chrome.RECT was;
            TopLevelNative.GetWindowRect(form.Handle, out was);
            said["made"] = TopLevelBox(form);
            for (int round = 1; round <= 2; round++)
            {
                said["maximised" + round] = TopLevelMaximise(form, Screen.FromHandle(form.Handle).WorkingArea);
                said["restored" + round] = TopLevelRestore(form, was);
            }
            return said;
        }

        // What Windows' question of what the pointer is over gets at `screen`: asked of the deepest child window there first,
        // and of what is under it while one answers HTTRANSPARENT (a control the window may be dragged by), as Windows asks.
        private static int TopLevelRoute(Control parent, Point screen)
        {
            foreach (Control c in parent.Controls)
            {
                if (!Soft.OwnVisible(c) || !c.IsHandleCreated) continue;
                Chrome.RECT r;
                TopLevelNative.GetWindowRect(c.Handle, out r);
                if (screen.X < r.Left || screen.X >= r.Right || screen.Y < r.Top || screen.Y >= r.Bottom) continue;
                int code = TopLevelRoute(c, screen);
                if (code != Chrome.HTTRANSPARENT) return code;
            }
            IntPtr at = (IntPtr)(((screen.Y & 0xFFFF) << 16) | (screen.X & 0xFFFF));
            return TopLevelNative.SendMessage(parent.Handle, Chrome.WM_NCHITTEST, IntPtr.Zero, at).ToInt32();
        }

        private static int TopLevelHit(Form form, Control over, int dx, int dy)
        {
            Rectangle face = over.RectangleToScreen(over.ClientRectangle);
            return TopLevelRoute(form, new Point(face.Left + dx, face.Top + dy));
        }

        private static SettingsForm TopLevelDashboard(string dir, string locale)
        {
            var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-" + locale + ".json"), Encoding.UTF8)) as Dictionary<string, object>;
            string nowhere = Path.Combine(dir, "nowhere-" + locale);
            var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, null);
            form.auditing = true;
            form.ClientSize = form.OpeningClient;
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(60, 40);
            IntPtr h = form.Handle;
            TopLevelChildren(form);
            form.PerformLayout();
            Application.DoEvents();
            return form;
        }

        private static Dictionary<string, object> TopLevelGrounds(SettingsForm form)
        {
            var said = new Dictionary<string, object>();
            bool mirrored = Mirror.Of(form);
            // The tab strip: its own ground at its far edge, the strip's ground past the last tab, and a tab.
            Rectangle tabs = Rectangle.Empty;
            Control strip = null;
            foreach (NavButton tab in form.navButtons.Values)
            {
                Rectangle face = tab.RectangleToScreen(tab.ClientRectangle);
                tabs = tabs.IsEmpty ? face : Rectangle.Union(tabs, face);
                strip = tab.Parent;
            }
            Rectangle navFace = form.nav.RectangleToScreen(form.nav.ClientRectangle);
            Rectangle stripFace = strip.RectangleToScreen(strip.ClientRectangle);
            int middle = tabs.Top + tabs.Height / 2;
            said["navEdge"] = (double)TopLevelRoute(form, new Point(mirrored ? navFace.Left + 3 : navFace.Right - 3, middle));
            int past = mirrored ? tabs.Left - 20 : tabs.Right + 20;
            said["navPastTabs"] = (double)TopLevelRoute(form, new Point(past, middle));
            said["navPastTabsInStrip"] = stripFace.Contains(past, middle);
            said["tab"] = (double)TopLevelHit(form, form.navButtons["overview"], 12, 12);
            // The save bar: the footer's ground round its card, the card's own face between the version and the buttons, a
            // button, and the version.
            said["footerGround"] = (double)TopLevelHit(form, form.footer, 3, 3);
            Rectangle version = form.versionText.RectangleToScreen(form.versionText.ClientRectangle);
            Rectangle close = form.closeButton.RectangleToScreen(form.closeButton.ClientRectangle);
            Rectangle bar = form.savebar.RectangleToScreen(form.savebar.ClientRectangle);
            int between = mirrored ? (close.Right + version.Left) / 2 : (version.Right + close.Left) / 2;
            said["savebarFace"] = (double)TopLevelRoute(form, new Point(between, bar.Top + bar.Height / 2));
            said["saveButton"] = (double)TopLevelHit(form, form.closeButton, form.closeButton.Width / 2, form.closeButton.Height / 2);
            said["version"] = (double)TopLevelHit(form, form.versionText, form.versionText.Width / 2, form.versionText.Height / 2);
            said["page"] = (double)TopLevelHit(form, form.pageHost, form.pageHost.Width / 2, form.pageHost.Height / 2);
            said["hero"] = (double)TopLevelHit(form, form.hero, form.hero.Width / 2, 6);
            return said;
        }

        // Maximised over the whole monitor, as with an auto-hide taskbar, with Windows' answer of which edges have one
        // stubbed (Chrome.AppBarEdges): bottom, then none.
        private static Dictionary<string, object> TopLevelAutoHide(SettingsForm form)
        {
            var said = new Dictionary<string, object>();
            FieldInfo stub = typeof(Chrome).GetField("AppBarEdges", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);
            if (stub == null)
            {
                said["stub"] = "missing";
                return said;
            }
            object real = stub.GetValue(null);
            Chrome.RECT was;
            TopLevelNative.GetWindowRect(form.Handle, out was);
            Rectangle monitor = Screen.FromHandle(form.Handle).Bounds;
            said["monitor"] = Numbers(monitor.Left, monitor.Top, monitor.Width, monitor.Height);
            var asked = new List<object>();
            try
            {
                foreach (int edges in new[] { 8, 2, 0 })
                {
                    int answer = edges;
                    stub.SetValue(null, (Func<Rectangle, int>)delegate(Rectangle on) { asked.Add(Numbers(on.Left, on.Top, on.Width, on.Height)); return answer; });
                    said["edges" + edges] = TopLevelMaximise(form, monitor);
                }
                said["restored"] = TopLevelRestore(form, was);
            }
            finally { stub.SetValue(null, real); }
            said["asked"] = asked;
            return said;
        }

        // Chrome.LeaveForAppBars, a table: the client of a maximised window, the monitor and the edges with an auto-hide bar.
        private static Dictionary<string, object> TopLevelLeave()
        {
            var said = new Dictionary<string, object>();
            MethodInfo leave = typeof(Chrome).GetMethod("LeaveForAppBars", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);
            if (leave == null)
            {
                said["missing"] = true;
                return said;
            }
            var monitor = new Rectangle(0, 0, 1920, 1080);
            var cases = new Dictionary<string, object[]> {
                { "none", new object[] { new Rectangle(0, 0, 1920, 1080), monitor, 0 } },
                { "bottom", new object[] { new Rectangle(0, 0, 1920, 1080), monitor, 8 } },
                { "top", new object[] { new Rectangle(0, 0, 1920, 1080), monitor, 2 } },
                { "left", new object[] { new Rectangle(0, 0, 1920, 1080), monitor, 1 } },
                { "right", new object[] { new Rectangle(0, 0, 1920, 1080), monitor, 4 } },
                { "all", new object[] { new Rectangle(0, 0, 1920, 1080), monitor, 15 } },
                { "workArea", new object[] { new Rectangle(0, 0, 1920, 1032), monitor, 8 } },
                { "second", new object[] { new Rectangle(1920, 0, 2560, 1440), new Rectangle(1920, 0, 2560, 1440), 8 } } };
            foreach (KeyValuePair<string, object[]> one in cases)
            {
                var r = (Rectangle)leave.Invoke(null, one.Value);
                said[one.Key] = Numbers(r.Left, r.Top, r.Right, r.Bottom);
            }
            return said;
        }

        private static SoftDialog TopLevelDialog(FormBorderStyle border)
        {
            var d = new SoftDialog();
            d.Text = "A dialog with a title of its own";
            d.BackColor = Palette.Canvas;
            Soft.DialogBar(d);
            d.FormBorderStyle = border;
            d.MinimizeBox = false;
            d.MaximizeBox = true;
            d.ShowInTaskbar = false;
            d.StartPosition = FormStartPosition.Manual;
            d.Location = new Point(120, 90);
            d.ClientSize = new Size(600, 400);
            var body = new Panel();
            body.Dock = DockStyle.Fill;
            var row = new Panel();
            row.Dock = DockStyle.Bottom;
            row.Height = 50;
            d.Controls.Add(body);
            d.Controls.Add(row);
            IntPtr h = d.Handle;
            TopLevelChildren(d);
            Application.DoEvents();
            return d;
        }

        private static Dictionary<string, object> TopLevelOpened(SoftDialog d)
        {
            var said = TopLevelBox(d);
            int style = (int)TopLevelNative.GetWindowLongPtr(d.Handle, TopLevelStyle).ToInt64();
            int ex = (int)TopLevelNative.GetWindowLongPtr(d.Handle, TopLevelExStyle).ToInt64();
            Size outer = Chrome.WindowSize(new Size(600, 400 + d.TitleReserve), Chrome.Frame(style, ex));
            said["reserve"] = (double)d.TitleReserve;
            said["expectedWindow"] = Numbers(outer.Width, outer.Height);
            return said;
        }

        // A caption button the window does not offer, in High Contrast and out of it: the ink its look asks for.
        private static Dictionary<string, object> TopLevelGreyed()
        {
            var said = new Dictionary<string, object>();
            SoftDialog d = TopLevelDialog(FormBorderStyle.FixedDialog);
            CaptionButton minimize = d.CaptionHost.MinimizeButton, close = d.CaptionHost.CloseButton;
            MethodInfo wanted = typeof(CaptionButton).GetMethod("Wanted", BindingFlags.Instance | BindingFlags.NonPublic);
            bool was = Palette.Contrast;
            try
            {
                foreach (bool contrast in new[] { true, false })
                {
                    Palette.Contrast = contrast;
                    var off = (SurfaceLook)wanted.Invoke(minimize, null);
                    var on = (SurfaceLook)wanted.Invoke(close, null);
                    string key = contrast ? "contrast" : "plain";
                    said[key + "Off"] = (double)off.Ink.ToArgb();
                    said[key + "On"] = (double)on.Ink.ToArgb();
                    said[key + "OffEnabled"] = minimize.Enabled;
                }
            }
            finally { Palette.Contrast = was; }
            said["grayText"] = (double)SystemColors.GrayText.ToArgb();
            said["windowText"] = (double)SystemColors.WindowText.ToArgb();
            said["muted"] = (double)Palette.Muted.ToArgb();
            d.Dispose();
            return said;
        }

        internal static void TopLevelRun(string dir, Dictionary<string, object> said)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(null);
            Palette.Adopt("light");
            AdoptDisplayScale(1.0);
            foreach (string locale in new[] { "en", "ar" })
            {
                SettingsForm form = TopLevelDashboard(dir, locale);
                said["grounds-" + locale] = TopLevelGrounds(form);
                said["restore-" + locale] = TopLevelMaxRestore(form);
                if (locale == "en") said["autohide"] = TopLevelAutoHide(form);
                form.Dispose();
            }
            Mirror.Window = false;
            foreach (FormBorderStyle border in new[] { FormBorderStyle.FixedDialog, FormBorderStyle.Sizable })
            {
                SoftDialog d = TopLevelDialog(border);
                said["opened-" + border] = TopLevelOpened(d);
                said["restore-" + border] = TopLevelMaxRestore(d);
                d.Dispose();
            }
            said["leave"] = TopLevelLeave();
            said["greyed"] = TopLevelGreyed();
        }
    }
}
"""

HTCLIENT, HTCAPTION = 1, 2


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class TopLevelChromeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        for locale in LOCALES:
            reply = {"ok": True, "language": locale, "strings": l10n.catalog(locale), "endonyms": dict(l10n.ENDONYMS),
                     "preference": locale, "system_language": locale}
            (work / ("strings-%s.json" % locale)).write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        probe = work / "ChromeTopLevelProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "ChromeTopLevel.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.ChromeTopLevelProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
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

    def test_nothing_was_shown(self):
        for key, said in self.answer.items():
            for step, box in (said.items() if isinstance(said, dict) else ()):
                if isinstance(box, dict) and "visible" in box:
                    with self.subTest(key=key, step=step):
                        self.assertFalse(box["visible"])

    def test_a_top_level_dialog_opens_at_what_it_asked_plus_its_title(self):
        for border in ("FixedDialog", "Sizable"):
            said = self.answer["opened-" + border]
            with self.subTest(border=border):
                self.assertGreater(said["reserve"], 26 + 20)
                self.assertEqual(said["clientSize"], [600, 400 + said["reserve"]])
                self.assertEqual(said["client"][2:], [600, 400 + said["reserve"]], "Windows' client rectangle")
                self.assertEqual(said["window"][2:], said["expectedWindow"], "no Windows caption in the window's height")

    def test_maximise_then_restore_comes_back_at_the_size_it_had(self):
        for key in ("restore-en", "restore-ar", "restore-Sizable", "restore-FixedDialog"):
            said = self.answer[key]
            for round in (1, 2):
                with self.subTest(key=key, round=round):
                    self.assertEqual(said["maximised%d" % round]["state"], "Maximized")
                    self.assertEqual(said["restored%d" % round]["state"], "Normal")
                    self.assertEqual(said["restored%d" % round]["window"], said["made"]["window"])
                    self.assertEqual(said["restored%d" % round]["client"], said["made"]["client"])
                    self.assertEqual(said["restored%d" % round]["clientSize"], said["made"]["clientSize"])

    def test_the_tab_strip_and_the_save_bar_s_ground_drag_the_window_and_nothing_on_them_does(self):
        for locale in LOCALES:
            said = self.answer["grounds-" + locale]
            with self.subTest(locale=locale):
                self.assertTrue(said["navPastTabsInStrip"], "the point past the last tab is on the strip")
                for ground in ("navEdge", "navPastTabs", "footerGround", "hero"):
                    self.assertEqual(said[ground], HTCAPTION, ground)
                for control in ("tab", "savebarFace", "saveButton", "version", "page"):
                    self.assertEqual(said[control], HTCLIENT, control)

    def test_maximised_over_an_auto_hide_taskbar_the_window_leaves_its_edge(self):
        said = self.answer["autohide"]
        self.assertNotEqual(said.get("stub"), "missing", "Chrome.AppBarEdges is what a test stubs")
        left, top, width, height = said["monitor"]
        whole = [left, top, width, height]
        self.assertEqual(said["edges0"]["client"], whole, "no auto-hide bar: the whole monitor")
        self.assertEqual(said["edges8"]["client"], [left, top, width, height - 2], "bottom: 2 px left at the foot")
        self.assertEqual(said["edges2"]["client"], [left, top + 2, width, height - 2], "top: 2 px left at the top")
        self.assertTrue(said["asked"], "asked of the monitor the window is maximised on")
        for asked in said["asked"]:
            self.assertEqual(asked, whole)
        self.assertEqual(said["restored"]["state"], "Normal")

    def test_the_room_left_for_an_auto_hide_bar_is_at_its_edge_alone(self):
        said = self.answer["leave"]
        self.assertNotIn("missing", said, "Chrome.LeaveForAppBars")
        self.assertEqual(said["none"], [0, 0, 1920, 1080])
        self.assertEqual(said["bottom"], [0, 0, 1920, 1078])
        self.assertEqual(said["top"], [0, 2, 1920, 1080])
        self.assertEqual(said["left"], [2, 0, 1920, 1080])
        self.assertEqual(said["right"], [0, 0, 1918, 1080])
        self.assertEqual(said["all"], [2, 2, 1918, 1078])
        self.assertEqual(said["workArea"], [0, 0, 1920, 1032], "a client short of the monitor's edge already leaves it")
        self.assertEqual(said["second"], [1920, 0, 4480, 1438], "on a second monitor, at its own edge")

    def test_in_high_contrast_a_button_not_offered_is_in_gray_text(self):
        said = self.answer["greyed"]
        self.assertFalse(said["contrastOffEnabled"])
        self.assertEqual(said["contrastOff"], said["grayText"], "the system's GrayText")
        self.assertEqual(said["contrastOn"], said["windowText"])
        self.assertNotEqual(said["plainOff"], said["grayText"], "outside High Contrast: Muted, faint")


if __name__ == "__main__":
    unittest.main()
