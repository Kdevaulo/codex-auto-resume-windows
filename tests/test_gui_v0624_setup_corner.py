r"""v0.6.24-beta.2: the setup window has the Dashboard's own squircle corner (the owner, 2026-11-16: "설치앱은 스쿼글이 아닌가?").

gui/InstallerWindow.cs asks for it with the Dashboard's one call, ChromeHost.OwnCorner (gui/SoftChrome.cs), so the corner
is the shared one of gui/SoftWindowShape.cs - its region, its companion (the hairline, the edge and the shadow), DWM's
corner preference, nothing of Windows' classic frame painted - under the same switch and conditions (Brand.WindowSquircle,
WindowShape.Wanted: Windows 11, composition, not remote, not High Contrast). Every way the window is shown is that one
class: the setup program's first installation, update, repair and edition change (build/setup/SetupWindow.cs), the
Dashboard's update and Install another version (gui/DashboardMaintenance.cs, DashboardVersions.cs), the uninstall and its
refusal (gui/SettingsRemove.cs).

It is a fixed window (FormBorderStyle.FixedSingle, no maximise box): its own corner must never give it the resize band
the Dashboard's edges have (Chrome.Hit answers the side bands only for a sizable window, ChromeHost.InGrip likewise).

A probe compiled with the window's sources (gui/window.sources, which carry the [installer] group the setup programs are
built from) makes the real setup window of a first installation, shown 30000 px off the desktop and never activated,
nothing captured:

* the corner as the switch makes it, where WindowShape.Wanted holds: Squircle, a region cut (the cut corner outside it,
  the outermost pixel of each side inside), DWMWCP_DONOTROUND, no DWM frame, its companion made and shown, the window its
  own client area (600 x 600 at 100 % with no frame round it);
* what the pointer is over, asked as Windows asks it (the deepest child first): along every edge, 16 px deep, no resize
  code at all; HTCAPTION on the header card and the ground; the caption buttons the client's, minimise and close on,
  maximise off;
* minimised (as the minimise button or Win+D leaves it) Windows' corner, no region, the companion hidden; back
  (the taskbar), the same window rectangle to the pixel - with WinForms holding a bigger size to give back, too - its
  corner, region and companion again, twice over;
* another language picked on the window (Arabic, mirrored): the corner, region and companion are still there;
* with WindowShape.Wanted false (High Contrast): nothing made - no WindowCorner, no region, Windows' round corner, the
  window its client inside the frame Windows gives the style, as before.

And the setup window's offscreen drawing (build/motion/InstallerRender.cs, compiled with the setup program's sources by
build/make_install_motion.py) cuts its still and its frames with the same corner while the switch is on, word for word
as gui/WindowRender.cs does for the Dashboard.

GUI test module (it shows a window, off the screen): run on its own, through gui_lock.sh.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "tests"), str(ROOT / "build")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import guiscan  # noqa: E402

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HTCLIENT, HTCAPTION, HTLEFT, HTBOTTOMRIGHT = 1, 2, 10, 17
RESIZE = set(range(HTLEFT, HTBOTTOMRIGHT + 1))

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
    internal static class SetupNative
    {
        [DllImport("dwmapi.dll")] internal static extern int DwmGetWindowAttribute(IntPtr h, int attribute, out int value, int size);
        [DllImport("user32.dll")] internal static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr w, IntPtr l);
        [DllImport("user32.dll")] internal static extern bool IsWindowVisible(IntPtr h);
        [DllImport("user32.dll")] internal static extern bool IsWindow(IntPtr h);
        [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr h, int command);
        [DllImport("user32.dll")] internal static extern bool GetWindowRect(IntPtr h, out Chrome.RECT r);
        [DllImport("user32.dll")] internal static extern int GetWindowRgn(IntPtr h, IntPtr region);
        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] internal static extern IntPtr GetWindowLongPtr(IntPtr h, int i);
        [DllImport("gdi32.dll")] internal static extern IntPtr CreateRectRgn(int l, int t, int r, int b);
        [DllImport("gdi32.dll")] internal static extern bool PtInRegion(IntPtr region, int x, int y);
        [DllImport("gdi32.dll")] internal static extern bool DeleteObject(IntPtr o);

        [StructLayout(LayoutKind.Sequential)]
        internal struct WINDOWPLACEMENT { public int Length, Flags, ShowCmd; public Point Min, Max; public Chrome.RECT Normal; }
        [DllImport("user32.dll")] internal static extern bool GetWindowPlacement(IntPtr h, ref WINDOWPLACEMENT placement);
        [DllImport("user32.dll")] internal static extern bool SetWindowPlacement(IntPtr h, ref WINDOWPLACEMENT placement);

        internal const int Away = -30000;

        internal static Rectangle Rect(IntPtr h)
        {
            Chrome.RECT r;
            GetWindowRect(h, out r);
            return Rectangle.FromLTRB(r.Left, r.Top, r.Right, r.Bottom);
        }

        internal static List<object> Box(Rectangle r)
        {
            return new List<object> { (double)r.X, (double)r.Y, (double)r.Width, (double)r.Height };
        }

        internal static double Attribute(IntPtr h, int attribute)
        {
            int value;
            return DwmGetWindowAttribute(h, attribute, out value, 4) == 0 ? value : -1;
        }

        // The window's region: its kind (0 none, 1 empty, 2 simple, 3 complex) and whether it holds the pixel (x, y).
        internal static int RegionKind(IntPtr h)
        {
            IntPtr region = CreateRectRgn(0, 0, 0, 0);
            try { return GetWindowRgn(h, region); }
            finally { DeleteObject(region); }
        }

        internal static bool InRegion(IntPtr h, int x, int y)
        {
            IntPtr region = CreateRectRgn(0, 0, 0, 0);
            try { return GetWindowRgn(h, region) == 0 || PtInRegion(region, x, y); }
            finally { DeleteObject(region); }
        }

        // What Windows' question of what the pointer is over gets at `screen`: asked of the deepest child window there
        // first, and of what is under it while one answers HTTRANSPARENT, as Windows asks.
        internal static int Route(Control parent, Point screen)
        {
            for (int i = 0; i < parent.Controls.Count; i++)
            {
                Control c = parent.Controls[i];
                if (!Soft.OwnVisible(c) || !c.IsHandleCreated) continue;
                Chrome.RECT r;
                GetWindowRect(c.Handle, out r);
                if (screen.X < r.Left || screen.X >= r.Right || screen.Y < r.Top || screen.Y >= r.Bottom) continue;
                int code = Route(c, screen);
                if (code != Chrome.HTTRANSPARENT) return code;
            }
            IntPtr at = (IntPtr)(((screen.Y & 0xFFFF) << 16) | (screen.X & 0xFFFF));
            return SendMessage(parent.Handle, Chrome.WM_NCHITTEST, IntPtr.Zero, at).ToInt32();
        }
    }

    internal static class SetupCornerProbe
    {
        const BindingFlags Inside = BindingFlags.Instance | BindingFlags.NonPublic;

        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try
            {
                Application.EnableVisualStyles();
                Palette.AdoptDesign("soft");
                Palette.Adopt("light");
                said["wanted"] = WindowShape.Wanted();
                said["on"] = Window(true);
                Palette.Contrast = true;
                said["contrastWanted"] = WindowShape.Wanted();
                said["off"] = Window(true);
                Palette.Contrast = false;
            }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            Mirror.Window = false;
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }

        static InstallerWindow Make()
        {
            var flow = new InstallerFlow(InstallerFlow.Install, "C:\\Users\\ExampleUser\\.codex-auto-resume", "standard", null, "9.9.9");
            InstallerWindow.Speaker speaker = delegate(string other) { return new InstallerWords(null, other); };
            var window = new InstallerWindow(flow, speaker("en"), speaker, null, null, null);
            window.StartPosition = FormStartPosition.Manual;
            window.Location = new Point(SetupNative.Away, SetupNative.Away);
            window.ShowInTaskbar = false;
            IntPtr made = window.Handle;
            // Made off the desktop; from here on as the setup program has it (CenterScreen), so a new language (Fit) does
            // not centre it on the primary screen as a Manual window's is.
            window.StartPosition = FormStartPosition.CenterScreen;
            return window;
        }

        static Dictionary<string, object> State(InstallerWindow window)
        {
            IntPtr h = window.Handle;
            ChromeHost chrome = window.CaptionHost;
            Rectangle whole = SetupNative.Rect(h);
            IntPtr companion = chrome.Corner == null ? IntPtr.Zero : chrome.Corner.Companion;
            return new Dictionary<string, object> {
                { "state", window.WindowState.ToString() },
                { "corner", chrome.OuterCorner.ToString() },
                { "has", chrome.Corner != null },
                { "frameless", chrome.Frameless },
                { "preference", SetupNative.Attribute(h, Soft.CornerPreferenceAttribute) },
                { "dwmFrame", SetupNative.Attribute(h, 1) },
                { "region", (double)SetupNative.RegionKind(h) },
                { "window", SetupNative.Box(whole) },
                { "client", new List<object> { (double)window.ClientSize.Width, (double)window.ClientSize.Height } },
                { "companion", companion != IntPtr.Zero && SetupNative.IsWindow(companion) },
                { "companionShown", companion != IntPtr.Zero && SetupNative.IsWindowVisible(companion) },
                { "kept", typeof(Form).GetField("restoredWindowBoundsSpecified", Inside).GetValue(window).ToString() } };
        }

        // Every edge, every 5 px along it, 0 to 15 px in: the distinct answers, as Windows routes the question.
        static Dictionary<string, object> Edges(InstallerWindow window)
        {
            Rectangle w = SetupNative.Rect(window.Handle);
            var sides = new Dictionary<string, List<int>> { { "left", new List<int>() }, { "right", new List<int>() },
                                                            { "top", new List<int>() }, { "bottom", new List<int>() } };
            int deep = Soft.Px(16);
            for (int d = 0; d < deep; d++)
            {
                for (int y = w.Top; y < w.Bottom; y += 5)
                {
                    Note(sides["left"], SetupNative.Route(window, new Point(w.Left + d, y)));
                    Note(sides["right"], SetupNative.Route(window, new Point(w.Right - 1 - d, y)));
                }
                for (int x = w.Left; x < w.Right; x += 5)
                {
                    Note(sides["top"], SetupNative.Route(window, new Point(x, w.Top + d)));
                    Note(sides["bottom"], SetupNative.Route(window, new Point(x, w.Bottom - 1 - d)));
                }
            }
            var said = new Dictionary<string, object>();
            foreach (KeyValuePair<string, List<int>> side in sides)
            {
                var codes = new List<object>();
                foreach (int c in side.Value) codes.Add((double)c);
                said[side.Key] = codes;
            }
            bool grip = false;
            for (int y = w.Top + 1; y < w.Bottom - 1; y += 7)
                grip |= window.CaptionHost.InGrip(new Point(w.Left + 1, y)) || window.CaptionHost.InGrip(new Point(w.Right - 2, y));
            for (int x = w.Left + 1; x < w.Right - 1; x += 7)
                grip |= window.CaptionHost.InGrip(new Point(x, w.Top + 1)) || window.CaptionHost.InGrip(new Point(x, w.Bottom - 2));
            said["grip"] = grip;
            ChromeLayout layout = window.CaptionHost.Layout();
            said["sizable"] = layout.Sizable;
            said["band"] = (double)layout.Band;
            return said;
        }

        static void Note(List<int> codes, int code)
        {
            if (!codes.Contains(code)) codes.Add(code);
        }

        static Dictionary<string, object> Pointer(InstallerWindow window)
        {
            var header = (Control)typeof(InstallerWindow).GetField("header", Inside).GetValue(window);
            var body = (Control)typeof(InstallerWindow).GetField("body", Inside).GetValue(window);
            Rectangle card = header.RectangleToScreen(header.ClientRectangle);
            Rectangle content = body.RectangleToScreen(body.ClientRectangle);
            Rectangle w = SetupNative.Rect(window.Handle);
            ChromeHost chrome = window.CaptionHost;
            Func<Control, Point> middle = delegate(Control c)
            {
                Rectangle r = c.RectangleToScreen(c.ClientRectangle);
                return new Point(r.Left + r.Width / 2, r.Top + r.Height / 2);
            };
            return new Dictionary<string, object> {
                { "headerTop", (double)SetupNative.Route(window, new Point(card.Left + card.Width / 2, card.Top + 3)) },
                { "headerSide", (double)SetupNative.Route(window, new Point(card.Left + 4, card.Top + card.Height / 2)) },
                { "groundBetween", (double)SetupNative.Route(window, new Point(card.Left + card.Width / 2, (card.Bottom + content.Top) / 2)) },
                { "groundSide", (double)SetupNative.Route(window, new Point(w.Left + (content.Left - w.Left) / 2, content.Top + content.Height / 2)) },
                { "minimize", (double)SetupNative.Route(window, middle(chrome.MinimizeButton)) },
                { "close", (double)SetupNative.Route(window, middle(chrome.CloseButton)) },
                { "buttons", new List<object> { Soft.OwnVisible(chrome.MinimizeButton), chrome.MinimizeButton.Enabled,
                                                Soft.OwnVisible(chrome.MaximizeButton), chrome.MaximizeButton.Enabled,
                                                Soft.OwnVisible(chrome.CloseButton), chrome.CloseButton.Enabled } } };
        }

        // Minimised without being activated - as the minimise button or Win+D leaves it - and back as the taskbar brings
        // it, shown without being activated (ShowWindow: SetWindowPlacement would bring a window placed off every monitor
        // onto one). With `plant`, WinForms holds a size Windows' frame and caption bigger to give back (as it did on CI and
        // on the owner's monitors for the Dashboard).
        static List<object> Round(InstallerWindow window, bool plant)
        {
            IntPtr h = window.Handle;
            SetupNative.ShowWindow(h, 7);   // SW_SHOWMINNOACTIVE
            Application.DoEvents();
            var placement = new SetupNative.WINDOWPLACEMENT();
            placement.Length = Marshal.SizeOf(typeof(SetupNative.WINDOWPLACEMENT));
            SetupNative.GetWindowPlacement(h, ref placement);
            Dictionary<string, object> minimised = State(window);
            string planted = "";
            if (plant)
            {
                Rectangle normal = Rectangle.FromLTRB(placement.Normal.Left, placement.Normal.Top, placement.Normal.Right, placement.Normal.Bottom);
                typeof(Form).GetField("restoredWindowBounds", Inside).SetValue(window,
                    new Rectangle(normal.X, normal.Y, normal.Width + 22, normal.Height + 56));
                typeof(Form).GetField("restoredWindowBoundsSpecified", Inside).SetValue(window, BoundsSpecified.All);
                planted = typeof(Form).GetField("restoredWindowBoundsSpecified", Inside).GetValue(window).ToString();
            }
            SetupNative.ShowWindow(h, 4);   // SW_SHOWNOACTIVATE
            Application.DoEvents();
            return new List<object> { minimised, State(window), planted };
        }

        static Dictionary<string, object> Window(bool full)
        {
            var said = new Dictionary<string, object>();
            InstallerWindow window = Make();
            said["fixed"] = new List<object> { window.FormBorderStyle.ToString(), window.MaximizeBox, window.MinimizeBox };
            IntPtr h = window.Handle;
            said["made"] = State(window);
            SetupNative.ShowWindow(h, 4);   // SW_SHOWNOACTIVATE: never made the foreground window
            Application.DoEvents();
            said["shown"] = State(window);
            Padding frame = Chrome.Frame((int)SetupNative.GetWindowLongPtr(h, -16).ToInt64(), (int)SetupNative.GetWindowLongPtr(h, -20).ToInt64());
            said["styleFrame"] = new List<object> { (double)frame.Left, (double)frame.Top, (double)frame.Right, (double)frame.Bottom };
            said["dpi"] = (double)(int)Math.Round(96 * SettingsForm.DpiScale);
            Rectangle whole = SetupNative.Rect(h);
            said["outermost"] = new List<object> {
                SetupNative.InRegion(h, 0, whole.Height / 2), SetupNative.InRegion(h, whole.Width - 1, whole.Height / 2),
                SetupNative.InRegion(h, whole.Width / 2, 0), SetupNative.InRegion(h, whole.Width / 2, whole.Height - 1) };
            said["cutCorners"] = new List<object> {
                SetupNative.InRegion(h, 0, 0), SetupNative.InRegion(h, whole.Width - 1, 0),
                SetupNative.InRegion(h, 0, whole.Height - 1), SetupNative.InRegion(h, whole.Width - 1, whole.Height - 1) };
            said["edges"] = Edges(window);
            said["pointer"] = Pointer(window);
            if (full)
            {
                // Another language on the window, as its picker on the Welcome page gives it (Adopt): Arabic, mirrored,
                // and back to English.
                InstallerWindow.Speaker speaker = delegate(string other) { return new InstallerWords(null, other); };
                MethodInfo adopt = typeof(InstallerWindow).GetMethod("Adopt", Inside);
                adopt.Invoke(window, new object[] { speaker("ar") });
                Application.DoEvents();
                said["mirrored"] = State(window);
                said["mirroredHandle"] = window.Handle == h ? "same" : "made again";
                said["mirroredOn"] = Mirror.Of(window);
                said["edgesMirrored"] = Edges(window);
                said["pointerMirrored"] = Pointer(window);
                adopt.Invoke(window, new object[] { speaker("en") });
                Application.DoEvents();
                Mirror.Window = false;
                said["english"] = State(window);
                said["round1"] = Round(window, false);
                said["round2"] = Round(window, true);
                said["edgesAfter"] = Edges(window);
            }
            window.Close();
            window.Dispose();
            return said;
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class SetupCornerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="car-setup-corner-")
        work = Path(cls.folder.name)
        probe = work / "SetupCornerProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "SetupCorner.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.SetupCornerProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            # CODEX_AR_STILL_READY names an event nobody waits on: the window is made as a picture makes it, never
            # activated (ShowWithoutActivation, WS_EX_NOACTIVATE) - also as a new language makes its handle again.
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"),
                               CODEX_AR_STILL_READY="car-setup-corner-probe-" + str(os.getpid()))
            done = subprocess.run([str(exe), str(out)], capture_output=True, timeout=300, creationflags=NO_WINDOW,
                                  env=environment)
            cls.answer = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
            if done.returncode != 0 or "error" in cls.answer or not cls.answer:
                cls.failure = "the probe failed (exit %d): %s" % (done.returncode, cls.answer.get("error"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def on(self):
        if not self.answer["wanted"]:
            self.skipTest("this machine gives a window no corner of its own (WindowShape.Wanted)")
        return self.answer["on"]

    def test_it_is_a_fixed_window_with_no_maximise_box(self):
        self.assertEqual(self.answer["on"]["fixed"], ["FixedSingle", False, True])

    def test_where_it_is_wanted_the_setup_window_has_the_dashboard_s_corner(self):
        said = self.on()
        for step in ("made", "shown"):
            state = said[step]
            with self.subTest(step=step):
                self.assertTrue(state["has"], "ChromeHost.OwnCorner made the corner")
                self.assertEqual(state["corner"], "Squircle")
                self.assertTrue(state["frameless"])
                self.assertEqual(state["preference"], 1, "DWMWCP_DONOTROUND under the window's own corner")
                self.assertEqual(state["dwmFrame"], 0, "a window with a region has no frame from DWM")
                self.assertIn(state["region"], (2, 3), "the region is cut")
                self.assertTrue(state["companion"], "the companion is made")
                self.assertEqual(state["window"][2:], state["client"], "the window is its own client area")
        self.assertTrue(said["shown"]["companionShown"], "shown with the window")
        self.assertEqual(said["outermost"], [True, True, True, True], "the outermost pixel of each side is the window's")
        self.assertEqual(said["cutCorners"], [False, False, False, False], "the four corners are cut")

    def test_its_size_is_its_client_area_as_before(self):
        said = self.on()
        # 600 x 600 at text size 1 (test_gui_v0624_setup_600): with no frame round it, the window is exactly that.
        scale = said["dpi"] / 96.0
        self.assertEqual(said["shown"]["client"][0], round(600 * scale))
        self.assertEqual(said["shown"]["window"][2:], said["shown"]["client"])

    def test_no_edge_resizes_it_anywhere(self):
        for which in ("on", "off"):
            said = self.answer[which]
            for name in ("edges", "edgesAfter", "edgesMirrored"):
                if name not in said:
                    continue
                edges = said[name]
                with self.subTest(which=which, name=name):
                    self.assertFalse(edges["sizable"])
                    self.assertEqual(edges["band"], 0, "a fixed window has no resize band")
                    self.assertFalse(edges["grip"], "nothing gives a grip band to the window")
                    for side in ("left", "right", "top", "bottom"):
                        codes = set(int(code) for code in edges[side])
                        self.assertFalse(codes & RESIZE, "%s edge answers a resize code: %s" % (side, sorted(codes)))
                        self.assertTrue(codes, side)

    def test_it_drags_by_its_header_and_ground_and_its_buttons_are_its_own(self):
        for which in ("on", "off"):
            pointer = self.answer[which]["pointer"]
            with self.subTest(which=which):
                for place in ("headerTop", "headerSide", "groundBetween", "groundSide"):
                    self.assertEqual(pointer[place], HTCAPTION, place)
                self.assertEqual(pointer["minimize"], HTCLIENT)
                self.assertEqual(pointer["close"], HTCLIENT)
                # Minimise and close shown and on; maximise shown faint and off, as Windows draws a fixed window's pair.
                self.assertEqual(pointer["buttons"], [True, True, True, False, True, True])

    def test_minimised_it_has_windows_corner_and_back_it_is_exactly_as_it_was(self):
        said = self.on()
        shown = said["shown"]
        for name in ("round1", "round2"):
            minimised, back, planted = said[name]
            with self.subTest(name=name):
                self.assertEqual(minimised["state"], "Minimized")
                self.assertEqual(minimised["corner"], "Round", "Windows' corner while minimised: no region to come back with")
                self.assertEqual(minimised["region"], 0)
                self.assertFalse(minimised["companionShown"])
                if name == "round2":
                    self.assertEqual(planted, "All", "WinForms held a bigger size to give back")
                self.assertEqual(back["state"], "Normal")
                self.assertEqual(back["window"], shown["window"], "the same rectangle to the pixel: nothing grows")
                self.assertEqual(back["client"], shown["client"])
                self.assertEqual(back["corner"], "Squircle")
                self.assertIn(back["region"], (2, 3))
                self.assertEqual(back["preference"], 1)
                self.assertEqual(back["dwmFrame"], 0, "no classic frame: DWM's is off under the region")
                self.assertTrue(back["companionShown"], "the shadow is back with the window")
                self.assertEqual(back["kept"], "None", "nothing of WinForms' kept to give back later")

    def test_another_language_keeps_the_corner(self):
        said = self.on()
        self.assertTrue(said["mirroredOn"], "Arabic mirrors the window")
        # A new language makes the window's handle again (its RightToLeft): the corner follows the new one.
        self.assertIn(said["mirroredHandle"], ("same", "made again"))
        for step in ("mirrored", "english"):
            state = said[step]
            with self.subTest(step=step):
                self.assertEqual(state["state"], "Normal")
                self.assertEqual(state["corner"], "Squircle")
                self.assertIn(state["region"], (2, 3), "the region is cut on the window as it is now")
                self.assertTrue(state["companion"] and state["companionShown"], "its companion is there and shown")
                self.assertEqual(state["preference"], 1)
                self.assertEqual(state["dwmFrame"], 0)
                self.assertEqual(state["window"], said["shown"]["window"], "the same window, where it was")
                self.assertEqual(state["window"][2:], state["client"])

    def test_where_it_is_not_wanted_nothing_is_made_and_the_window_is_as_it_was(self):
        self.assertFalse(self.answer["contrastWanted"], "High Contrast: WindowShape.Wanted is false")
        said = self.answer["off"]
        frame = said["styleFrame"]
        self.assertEqual(frame[1], 0, "the caption is the window's own: no top frame")
        for step in ("made", "shown"):
            state = said[step]
            with self.subTest(step=step):
                self.assertFalse(state["has"], "no WindowCorner")
                self.assertFalse(state["frameless"])
                self.assertEqual(state["corner"], "Round")
                self.assertEqual(state["region"], 0, "no region")
                self.assertFalse(state["companion"])
                self.assertEqual(state["window"][2:], [state["client"][0] + frame[0] + frame[2],
                                                       state["client"][1] + frame[1] + frame[3]],
                                 "the client inside the frame Windows gives the style, as before")
        self.assertEqual(said["shown"]["preference"], 2, "DWMWCP_ROUND: Windows' round corner")
        for step in ("mirrored", "english"):
            with self.subTest(step=step):
                self.assertEqual(said[step]["window"], said["shown"]["window"])
                self.assertFalse(said[step]["has"])
        for name in ("round1", "round2"):
            _minimised, back, _planted = said[name]
            with self.subTest(name=name):
                self.assertEqual(back["window"], said["shown"]["window"], "back exactly as it was")
                self.assertEqual(back["region"], 0)
                self.assertFalse(back["companion"])


WINDOW = (ROOT / "gui" / "InstallerWindow.cs").read_text(encoding="utf-8")
SHIM = ROOT / "build" / "motion" / "InstallerRender.cs"


def member_in(text: str, member: str) -> str:
    """One method of a type's body `text`, found as guiscan.member_body finds one (the shim is not a window source)."""
    pattern = re.compile(r"(?m)^[ \t]*(?:(?:%s)[ \t]+)*[\w<>,\[\]\.\?]+[ \t]+%s[ \t]*\("
                         % ("|".join(guiscan.MODIFIERS), re.escape(member)))
    found = pattern.search(text)
    if found is None:
        raise AssertionError("no member named " + member)
    return guiscan._block(text, found.start())


class SourceTests(unittest.TestCase):
    def test_the_setup_window_asks_for_its_corner_with_the_dashboard_s_one_call(self):
        ctor = guiscan.member_body("InstallerWindow", "InstallerWindow")
        install = ctor.index("chrome = ChromeHost.Install(this, header, ground);")
        self.assertIn("chrome.OwnCorner();", ctor[install:install + 400])
        self.assertLess(ctor.index("chrome.OwnCorner();"), ctor.index("Adopt(words);"),
                        "asked before the window's size is set (Fit), so ClientSize means the window")
        own = guiscan.member_body("InstallerWindow", "OwnFrame")
        self.assertIn("if (chrome != null && chrome.Frameless) return Padding.Empty;", own)
        # No copy of the corner's code in the window: the shared mechanism alone.
        code = " ".join(line.split("//")[0] for line in WINDOW.splitlines())
        for name in ("SetWindowRgn", "WindowCorner", "DwmSetWindowAttribute", "WindowShape", "UpdateLayeredWindow"):
            self.assertNotIn(name, code, name)
        self.assertIn("Chrome.Uncaption(created, ClientSize, chrome != null && chrome.Frameless);", code,
                      "made at its ClientSize with no frame while its corner is its own")
        # Every message goes to the caption (and so to the corner) first.
        procedure = guiscan.member_body("InstallerWindow", "WndProc")
        statements = [line.strip() for line in procedure.splitlines()[1:]
                      if line.strip() and not line.strip().startswith(("//", "{", "}"))]
        self.assertEqual(statements[0], "if (chrome != null && chrome.Intercept(ref m, PassOn)) return;")

    def test_every_way_the_setup_window_is_shown_is_that_one_window(self):
        made = []
        for path in sorted((ROOT / "gui").glob("*.cs")) + sorted((ROOT / "build" / "setup").glob("*.cs")):
            text = path.read_text(encoding="utf-8")
            made += [path.name for _ in re.finditer(r"new InstallerWindow\(", text)]
        self.assertEqual(sorted(made), sorted(["DashboardMaintenance.cs", "DashboardVersions.cs", "SettingsRemove.cs",
                                               "SettingsRemove.cs", "SetupWindow.cs", "SetupWindow.cs"]))
        self.assertIn("internal sealed class InstallerWindow : Form", WINDOW)

    def test_the_resize_bands_are_a_sizable_window_s_alone(self):
        hit = guiscan.member_body("Chrome", "Hit")
        self.assertIn("if (l.Edges && l.Sizable && !l.Maximized)", hit)
        self.assertIn("if (l.Sizable && !l.Maximized && p.Y < l.Band)", hit)
        grip = guiscan.member_body("ChromeHost", "InGrip")
        self.assertIn("if (!l.Edges || !l.Sizable || l.Maximized) return false;", grip)
        layout = guiscan.member_body("ChromeHost", "Layout")
        self.assertIn("layout.Band = layout.Sizable ? TopBand() : 0;", layout)

    def test_the_setup_window_s_drawing_cuts_the_same_corner(self):
        shim = SHIM.read_text(encoding="utf-8")
        frame = guiscan.type_body("StillFrame", shim)
        # Word for word gui/WindowRender.cs's, as FramedStill and Rounded are (tests/test_pinned_stills.py).
        for member in ("SquircleStill", "CornerStill"):
            with self.subTest(member=member):
                self.assertEqual(member_in(frame, member).strip(),
                                 guiscan.member_body("SettingsForm", member).strip())
        main = member_in(guiscan.type_body("InstallerRender", shim), "Main")
        self.assertIn('StillFrame.Squircle(still) ? StillFrame.SquircleStill(picture, Int(still, "dpi"))', main)
        self.assertIn('Int(job, "edge_dpi")', main)
        self.assertIn("using (Bitmap edged = StillFrame.CornerStill(picture, edgeDpi))", main)
        squircle = member_in(frame, "Squircle")
        self.assertIn('still.TryGetValue("corner", out value) && value as string == "squircle"', squircle)

    def test_the_install_motion_asks_for_the_corner_while_the_switch_is_on(self):
        from unittest import mock
        from codex_auto_resume import brand
        import make_install_motion as motion
        import make_screenshots as shots
        plan = motion.load("install-en")
        job = motion.job(plan, [], Path("frames"))
        self.assertEqual(job.get("edge_dpi"), shots.PINNED_DPI if brand.WINDOW_SQUIRCLE else None)
        with mock.patch.object(brand, "WINDOW_SQUIRCLE", False):
            self.assertNotIn("edge_dpi", motion.job(plan, [], Path("frames")))
        source = (ROOT / "build" / "make_install_motion.py").read_text(encoding="utf-8")
        fidelity = source[source.index("def check_fidelity"):source.index("def draw_still")]
        self.assertIn("**motion_window.frame_edge()", fidelity, "the Welcome page held to the still is cut as the still is")
        still = source[source.index("def draw_still"):source.index("def render_input")]
        self.assertIn('"still": make_screenshots.still_job(make_screenshots.PINNED_DPI)', still,
                      "the still's job names the corner (make_screenshots.still_job)")


if __name__ == "__main__":
    unittest.main()
