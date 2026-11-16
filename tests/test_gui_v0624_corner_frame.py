r"""v0.6.24 W5: with its own corner the Dashboard has nothing of Windows' frame - no round corner of DWM's, no classic frame.

The live M-CORNER check on three monitors (2026-11-16, plans/v0624-corner-live/result.md) found, with the corner on:

- A: beyond the squircle, a ghost of Windows' own small round corner. DWM was asked for its round corner last:
  Soft.TitleBar asks for it as every window is made, and on the Dashboard that came after the corner had asked for none
  (DWMWA_WINDOW_CORNER_PREFERENCE read 2, DWMWCP_ROUND, on the Dashboard with its region cut). A window with a corner of
  its own now has Soft.TitleBar ask the corner (WindowCorner.Of, Prefer), as it is made and again whenever it changes;
- C: while the owner resized it, Windows' classic frame - a light-blue caption with the title, icon and buttons, a thick
  grey frame - painted over the window. A window with a region gets no frame from DWM (DWMWA_NCRENDERING_ENABLED reads
  0), so Windows' own handling of WM_NCPAINT, WM_NCACTIVATE, the theme's caption and frame messages, WM_SETTEXT and
  WM_SETICON paints the classic one straight onto it. While the corner is its own, none of them paints:
  WindowCorner.Intercept and ChromeHost.Unframed.

Two probes compiled with the window, each shown 30000 px off the desktop and never activated, nothing captured:

- the real Dashboard (SettingsForm): DWM's corner preference, read back, as it is made, shown, maximised (its
  WS_MAXIMIZE bit, so nothing comes on a monitor) and restored - DWMWCP_DONOTROUND (1) while its corner is its own and
  DWMWCP_ROUND (2) while Windows' is - and DWM's frame off while the region is cut;
- a window with the Dashboard's caption and corner, whose own window procedure records what reaches Windows' handling:
  while its corner is its own, no WM_NCPAINT and none of the theme's caption and frame messages, WM_NCACTIVATE with -1,
  a new title and icon taken while it is marked hidden and shown again after (the title taken); while Windows' corner is
  back (maximised), every one of them as before.

What a screen shows - the cut corner clear of any ghost, no classic frame while it is resized - is the measurement
session's to look at again (M-CORNER items 1 and 3).

GUI test module (it shows windows, off the screen): run on its own, through gui_lock.sh.
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
WM_NCPAINT, WM_NCACTIVATE, WM_NCUAHDRAWCAPTION, WM_NCUAHDRAWFRAME, WM_SETTEXT, WM_SETICON = 0x85, 0x86, 0xAE, 0xAF, 0x0C, 0x80

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
    internal static class FrameNative
    {
        [DllImport("dwmapi.dll")] internal static extern int DwmGetWindowAttribute(IntPtr h, int attribute, out int value, int size);
        [DllImport("user32.dll")] internal static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int cy, uint flags);
        [DllImport("user32.dll")] internal static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr w, IntPtr l);
        [DllImport("user32.dll")] internal static extern bool IsWindowVisible(IntPtr h);
        [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr h, int command);
        [DllImport("user32.dll")] internal static extern bool IsZoomed(IntPtr h);
        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] internal static extern IntPtr GetWindowLongPtr(IntPtr h, int i);
        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] internal static extern IntPtr SetWindowLongPtr(IntPtr h, int i, IntPtr v);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] internal static extern int GetWindowText(IntPtr h, StringBuilder text, int most);
        internal const int Away = -30000, GWL_STYLE = -16, WS_MAXIMIZE = 0x01000000, WS_VISIBLE = 0x10000000;
        internal const uint SWP_NOZORDER = 0x0004, SWP_NOACTIVATE = 0x0010;

        [DllImport("user32.dll")] internal static extern bool GetWindowRect(IntPtr h, out Chrome.RECT r);

        internal static List<object> Box(IntPtr h)
        {
            Chrome.RECT r;
            GetWindowRect(h, out r);
            return new List<object> { (double)r.Left, (double)r.Top, (double)(r.Right - r.Left), (double)(r.Bottom - r.Top) };
        }

        [DllImport("user32.dll")] internal static extern int GetWindowRgn(IntPtr h, IntPtr region);
        [DllImport("gdi32.dll")] internal static extern IntPtr CreateRectRgn(int l, int t, int r, int b);
        [DllImport("gdi32.dll")] internal static extern bool PtInRegion(IntPtr region, int x, int y);
        [DllImport("gdi32.dll")] internal static extern bool DeleteObject(IntPtr o);

        // Whether the window's region holds the window's pixel (x, y); true where it has no region.
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

        [StructLayout(LayoutKind.Sequential)]
        internal struct WINDOWPLACEMENT { public int Length, Flags, ShowCmd; public Point Min, Max; public Chrome.RECT Normal; }
        [DllImport("user32.dll")] internal static extern bool GetWindowPlacement(IntPtr h, ref WINDOWPLACEMENT placement);
        [DllImport("user32.dll")] internal static extern bool SetWindowPlacement(IntPtr h, ref WINDOWPLACEMENT placement);

        internal static double Attribute(IntPtr h, int attribute)
        {
            int value;
            return DwmGetWindowAttribute(h, attribute, out value, 4) == 0 ? value : -1;
        }

        internal static void Maximised(IntPtr h, bool on, int x, int w, int cy)
        {
            long style = GetWindowLongPtr(h, GWL_STYLE).ToInt64();
            SetWindowLongPtr(h, GWL_STYLE, new IntPtr(on ? style | WS_MAXIMIZE : style & ~(long)WS_MAXIMIZE));
            SetWindowPos(h, IntPtr.Zero, x, Away, w, cy, SWP_NOZORDER | SWP_NOACTIVATE);
            Application.DoEvents();
        }
    }

    // Where a maximised window goes: 30000 px off the desktop, at a size of its own (WM_GETMINMAXINFO), so a window
    // maximised for real - its placement, not only its style - never comes on a monitor.
    internal sealed class OffScreenMaximise : NativeWindow
    {
        [StructLayout(LayoutKind.Sequential)] struct POINT { public int X, Y; }
        [StructLayout(LayoutKind.Sequential)] struct MINMAXINFO { public POINT Reserved, MaxSize, MaxPosition, MinTrack, MaxTrack; }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == 0x0024)
            {
                base.WndProc(ref m);
                var info = (MINMAXINFO)Marshal.PtrToStructure(m.LParam, typeof(MINMAXINFO));
                Rectangle monitor = Screen.FromHandle(Handle).Bounds;
                info.MaxPosition.X = FrameNative.Away - monitor.Left;
                info.MaxPosition.Y = FrameNative.Away - monitor.Top;
                info.MaxSize.X = 1400;
                info.MaxSize.Y = 900;
                Marshal.StructureToPtr(info, m.LParam, false);
                return;
            }
            base.WndProc(ref m);
        }
    }

    // A window with the Dashboard's caption and corner whose procedure records what reaches Windows' own handling.
    internal sealed class FrameProbeForm : Form
    {
        internal ChromeHost Caption;
        internal readonly List<object> Reached = new List<object>();
        internal readonly List<object> Commands = new List<object>();
        internal bool Recording;

        protected override bool ShowWithoutActivation { get { return true; } }

        protected override void WndProc(ref Message m)
        {
            if (Caption != null && Caption.Intercept(ref m, PassOn)) return;
            PassOn(ref m);
        }

        private void PassOn(ref Message m)
        {
            int msg = m.Msg;
            if (msg == 0x0112)
            {
                // Recorded and not carried out: a restore would make the window the foreground one.
                Commands.Add((double)(m.WParam.ToInt64() & 0xFFF0));
                return;
            }
            if (Recording && (msg == 0x85 || msg == 0x86 || msg == 0xAE || msg == 0xAF || msg == 0x0C || msg == 0x80))
            {
                long style = IsHandleCreated ? FrameNative.GetWindowLongPtr(Handle, FrameNative.GWL_STYLE).ToInt64() : 0;
                Reached.Add(new List<object> { (double)msg, (double)m.LParam.ToInt64(), (style & FrameNative.WS_VISIBLE) != 0,
                                                Caption.Corner.Now.ToString(), FrameNative.IsZoomed(Handle) });
            }
            base.WndProc(ref m);
        }
    }

    internal static class CornerFrameProbe
    {
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
                said["dashboard"] = SettingsForm.CornerFrameDashboard(argv[1]);
                said["messages"] = Messages();
                said["minimisedToMaximised"] = SettingsForm.CornerFrameMinimisedToMaximised(argv[1]);
                said["edges-en"] = SettingsForm.CornerFrameEdges(argv[1], "en");
                said["edges-ar"] = SettingsForm.CornerFrameEdges(argv[1], "ar");
                Mirror.Window = false;
            }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }

        static List<object> Round(FrameProbeForm form, string step)
        {
            IntPtr h = form.Handle;
            form.Reached.Clear();
            form.Recording = true;
            FrameNative.SendMessage(h, 0x85, new IntPtr(1), IntPtr.Zero);
            FrameNative.SendMessage(h, 0x86, IntPtr.Zero, IntPtr.Zero);
            FrameNative.SendMessage(h, 0xAE, IntPtr.Zero, IntPtr.Zero);
            FrameNative.SendMessage(h, 0xAF, IntPtr.Zero, IntPtr.Zero);
            form.Text = "A title " + step;
            FrameNative.SendMessage(h, 0x80, IntPtr.Zero, SystemIcons.Application.Handle);
            form.Recording = false;
            var text = new StringBuilder(64);
            FrameNative.GetWindowText(h, text, text.Capacity);
            return new List<object> { new List<object>(form.Reached), text.ToString(), FrameNative.IsWindowVisible(h),
                                      form.Caption.Corner.Now.ToString() };
        }

        static Dictionary<string, object> Messages()
        {
            var said = new Dictionary<string, object>();
            var form = new FrameProbeForm();
            form.ShowInTaskbar = false;
            form.StartPosition = FormStartPosition.Manual;
            form.FormBorderStyle = FormBorderStyle.Sizable;
            form.Location = new Point(FrameNative.Away, FrameNative.Away);
            form.Size = new Size(640, 480);
            form.BackColor = Palette.Canvas;
            Soft.TitleBar(form);
            var card = new Panel();
            card.SetBounds(16, 16, 400, 80);
            form.Controls.Add(card);
            ChromeHost caption = ChromeHost.Install(form, card, form);
            form.Caption = caption;
            WindowCorner corner = WindowCorner.Attach(form);
            typeof(ChromeHost).GetField("corner", BindingFlags.NonPublic | BindingFlags.Instance).SetValue(caption, corner);
            form.Show();
            Application.DoEvents();
            IntPtr h = form.Handle;
            said["own"] = Round(form, "own");
            FrameNative.Maximised(h, true, FrameNative.Away + 10, 900, 700);
            said["maximised"] = Round(form, "maximised");
            // The restore button pressed and let go over it, as a person's click comes (HTMAXBUTTON, WM_NCLBUTTONDOWN/UP).
            Rectangle button = caption.MaximizeButton.RectangleToScreen(caption.MaximizeButton.ClientRectangle);
            int mid = ((button.Top + button.Height / 2) << 16) | ((button.Left + button.Width / 2) & 0xFFFF);
            said["maximisedHit"] = (double)FrameNative.SendMessage(h, 0x84, IntPtr.Zero, new IntPtr(mid)).ToInt64();
            form.Commands.Clear();
            FrameNative.SendMessage(h, 0xA1, new IntPtr(9), new IntPtr(mid));
            FrameNative.SendMessage(h, 0xA2, new IntPtr(9), new IntPtr(mid));
            Application.DoEvents();
            said["restoreClick"] = new List<object>(form.Commands);
            FrameNative.Maximised(h, false, FrameNative.Away + 20, 640, 480);
            said["restored"] = Round(form, "restored");
            form.Close();
            form.Dispose();
            return said;
        }
    }

    internal sealed partial class SettingsForm
    {
        static Dictionary<string, object> CornerFrameState(SettingsForm form)
        {
            IntPtr h = form.Handle;
            return new Dictionary<string, object> {
                { "preference", FrameNative.Attribute(h, Soft.CornerPreferenceAttribute) },
                { "dwmFrame", FrameNative.Attribute(h, 1) },
                { "corner", form.CaptionHost.OuterCorner.ToString() },
                { "kept", typeof(Form).GetField("restoredWindowBoundsSpecified",
                      BindingFlags.Instance | BindingFlags.NonPublic).GetValue(form).ToString() },
                { "window", FrameNative.Box(h) } };
        }

        // Along the page under the tabs, on every page: the window's outermost pixel, the band's innermost, and one pixel
        // further in, at each side; and whether the outermost pixel is the window's (its region) or the cut corner's.
        internal static Dictionary<string, object> CornerFrameEdges(string dir, string locale)
        {
            var said = new Dictionary<string, object>();
            var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-" + locale + ".json"), Encoding.UTF8)) as Dictionary<string, object>;
            string nowhere = Path.Combine(dir, "nowhere-" + locale);
            var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, null);
            form.auditing = true;
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(FrameNative.Away, FrameNative.Away);
            form.ShowInTaskbar = false;
            IntPtr h = form.Handle;
            FrameNative.ShowWindow(h, 4);   // SW_SHOWNOACTIVATE: never made the foreground window
            Application.DoEvents();
            Chrome.RECT whole;
            FrameNative.GetWindowRect(h, out whole);
            int width = whole.Right - whole.Left, height = whole.Bottom - whole.Top;
            int band = form.CaptionHost.Layout().Band;
            said["band"] = (double)band;
            said["corner"] = form.CaptionHost.OuterCorner.ToString();
            said["mirrored"] = Mirror.Of(form);
            var pages = new Dictionary<string, object>();
            foreach (string page in new List<string>(form.navButtons.Keys))
            {
                form.ShowPage(page);
                form.PerformLayout();
                Application.DoEvents();
                Rectangle host = form.pageHost.RectangleToScreen(form.pageHost.ClientRectangle);
                int y = host.Top + host.Height / 2;
                pages[page] = new List<object> {
                    (double)FrameNative.Route(form, new Point(whole.Left, y)),
                    (double)FrameNative.Route(form, new Point(whole.Left + band - 1, y)),
                    (double)FrameNative.Route(form, new Point(whole.Left + band, y)),
                    (double)FrameNative.Route(form, new Point(whole.Right - 1, y)),
                    (double)FrameNative.Route(form, new Point(whole.Right - band, y)),
                    (double)FrameNative.Route(form, new Point(whole.Right - band - 1, y)) };
            }
            said["pages"] = pages;
            said["outermost"] = new List<object> { FrameNative.InRegion(h, 0, height / 2), FrameNative.InRegion(h, width - 1, height / 2),
                                                   FrameNative.InRegion(h, width / 2, 0), FrameNative.InRegion(h, width / 2, height - 1) };
            said["cutCorner"] = FrameNative.InRegion(h, 0, 0);
            form.Close();
            form.Dispose();
            return said;
        }

        // Minimised with its corner cut, then back maximised - as the minimise button or Win+D and the taskbar bring it:
        // minimised without being activated, to come back maximised (WPF_RESTORETOMAXIMIZED), and shown again.
        internal static Dictionary<string, object> CornerFrameMinimisedToMaximised(string dir)
        {
            var said = new Dictionary<string, object>();
            var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-en.json"), Encoding.UTF8)) as Dictionary<string, object>;
            string nowhere = Path.Combine(dir, "nowhere-min");
            var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, null);
            form.auditing = true;
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(FrameNative.Away, FrameNative.Away);
            form.ShowInTaskbar = false;
            IntPtr h = form.Handle;
            var away = new OffScreenMaximise();
            away.AssignHandle(h);
            FrameNative.ShowWindow(h, 4);   // SW_SHOWNOACTIVATE
            Application.DoEvents();
            said["normal"] = form.CaptionHost.OuterCorner.ToString();
            var placement = new FrameNative.WINDOWPLACEMENT();
            placement.Length = Marshal.SizeOf(typeof(FrameNative.WINDOWPLACEMENT));
            FrameNative.GetWindowPlacement(h, ref placement);
            placement.Flags = 2;      // WPF_RESTORETOMAXIMIZED
            placement.ShowCmd = 7;    // SW_SHOWMINNOACTIVE
            FrameNative.SetWindowPlacement(h, ref placement);
            Application.DoEvents();
            said["minimised"] = new List<object> { form.WindowState.ToString(), form.CaptionHost.OuterCorner.ToString(),
                                                   (double)FrameNative.GetWindowRgn(h, IntPtr.Zero) };
            FrameNative.ShowWindow(h, 4);   // back, as it was to come back: maximised
            Application.DoEvents();
            IntPtr region = FrameNative.CreateRectRgn(0, 0, 0, 0);
            int kind = FrameNative.GetWindowRgn(h, region);
            FrameNative.DeleteObject(region);
            said["back"] = new List<object> { form.WindowState.ToString(), form.CaptionHost.OuterCorner.ToString(), (double)kind,
                                              FrameNative.Attribute(h, 1) };
            away.ReleaseHandle();
            form.Close();
            form.Dispose();
            return said;
        }

        internal static Dictionary<string, object> CornerFrameDashboard(string dir)
        {
            var said = new Dictionary<string, object>();
            var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-en.json"), Encoding.UTF8)) as Dictionary<string, object>;
            string nowhere = Path.Combine(dir, "nowhere");
            var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, null);
            form.auditing = true;
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(FrameNative.Away, FrameNative.Away);
            form.ShowInTaskbar = false;
            IntPtr h = form.Handle;
            said["made"] = CornerFrameState(form);
            FrameNative.ShowWindow(h, 4);   // SW_SHOWNOACTIVATE: never made the foreground window
            Application.DoEvents();
            said["shown"] = CornerFrameState(form);
            List<object> made = FrameNative.Box(h);
            FrameNative.Maximised(h, true, FrameNative.Away + 10, 1400, 900);
            said["maximised"] = CornerFrameState(form);
            // What WinForms keeps to give back, as it keeps it while the window is maximised on a 1024 by 768 screen (dev CI
            // read All there) and on the owner's monitors: a size Windows' frame and caption bigger than the window's.
            BindingFlags inside = BindingFlags.Instance | BindingFlags.NonPublic;
            typeof(Form).GetField("restoredWindowBounds", inside).SetValue(form, new Rectangle(
                (int)(double)made[0], (int)(double)made[1], (int)(double)made[2] + 22, (int)(double)made[3] + 56));
            typeof(Form).GetField("restoredWindowBoundsSpecified", inside).SetValue(form, BoundsSpecified.All);
            said["planted"] = typeof(Form).GetField("restoredWindowBoundsSpecified", inside).GetValue(form).ToString();
            FrameNative.Maximised(h, false, (int)(double)made[0], (int)(double)made[2], (int)(double)made[3]);
            said["restored"] = CornerFrameState(form);
            form.Close();
            form.Dispose();
            return said;
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class CornerFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="car-corner-frame-")
        work = Path(cls.folder.name)
        for locale in ("en", "ar"):
            reply = {"ok": True, "language": locale, "strings": l10n.catalog(locale), "endonyms": dict(l10n.ENDONYMS),
                     "preference": locale, "system_language": locale}
            (work / ("strings-%s.json" % locale)).write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        probe = work / "CornerFrameProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "CornerFrame.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.CornerFrameProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
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

    def test_dwm_rounds_the_dashboard_only_while_windows_corner_is_back(self):
        said = self.answer["dashboard"]
        own = "Squircle" if self.answer["wanted"] else "Round"
        for step, corner, preference in (("made", own, 1), ("shown", own, 1), ("maximised", "Round", 2),
                                         ("restored", own, 1)):
            with self.subTest(step=step):
                self.assertEqual(said[step]["corner"], corner)
                if corner == "Squircle":
                    self.assertEqual(said[step]["preference"], preference, "DWMWCP_DONOTROUND under the window's own corner")
                    self.assertEqual(said[step]["dwmFrame"], 0, "a window with a region has no frame from DWM")
                else:
                    self.assertEqual(said[step]["preference"], 2, "DWMWCP_ROUND: Windows' round corner")

    def test_whatever_winforms_kept_while_maximised_the_window_comes_back_exactly(self):
        said = self.answer["dashboard"]
        self.assertEqual(said["planted"], "All", "WinForms holds a size to give back, as it did on CI and live")
        self.assertEqual(said["restored"]["window"], said["shown"]["window"],
                         "Windows' normal position, not the size WinForms kept: nothing grows")
        self.assertEqual(said["restored"]["kept"], "None")

    def test_back_maximised_from_minimised_it_has_dwm_s_frame_and_no_region(self):
        said = self.answer["minimisedToMaximised"]
        if said["normal"] != "Squircle":
            self.skipTest("this machine gives the window no corner of its own (WindowShape.Wanted)")
        state, corner, region, dwm_frame = said["back"]
        self.assertEqual((state, corner), ("Maximized", "Round"))
        self.assertEqual([region, dwm_frame], [0, 1], "no region and DWM's frame: Windows clips a classic window it maximises "
                         "with a region of its own and paints its basic caption across the top")
        self.assertEqual(said["minimised"][:2], ["Minimized", "Round"], "Windows' corner while minimised: no region cut")

    def test_while_maximised_a_click_on_the_restore_button_restores(self):
        said = self.answer["messages"]
        self.assertEqual(said["maximisedHit"], 9, "HTMAXBUTTON")
        self.assertEqual(said["restoreClick"], [0xF120], "SC_RESTORE, once")

    def test_every_page_gives_its_sides_grip_band_to_the_window_mirrored_too(self):
        HTLEFT, HTRIGHT, HTCLIENT, HTCAPTION = 10, 11, 1, 2
        for locale in ("en", "ar"):
            said = self.answer["edges-" + locale]
            if said["corner"] != "Squircle":
                self.skipTest("this machine gives the window no corner of its own (WindowShape.Wanted)")
            self.assertEqual(said["mirrored"], locale == "ar")
            self.assertGreater(said["band"], 0)
            self.assertGreaterEqual(len(said["pages"]), 6)
            for page, hits in said["pages"].items():
                with self.subTest(locale=locale, page=page):
                    self.assertEqual(hits[:2], [HTLEFT, HTLEFT], "the left side's outermost and innermost band pixels")
                    self.assertIn(hits[2], (HTCLIENT, HTCAPTION), "one pixel further in is the page's")
                    self.assertEqual(hits[3:5], [HTRIGHT, HTRIGHT], "the right side's")
                    self.assertIn(hits[5], (HTCLIENT, HTCAPTION))

    def test_the_window_s_outermost_pixel_is_its_own_and_the_cut_corner_is_not(self):
        for locale in ("en", "ar"):
            said = self.answer["edges-" + locale]
            if said["corner"] != "Squircle":
                self.skipTest("this machine gives the window no corner of its own (WindowShape.Wanted)")
            with self.subTest(locale=locale):
                self.assertEqual(said["outermost"], [True, True, True, True], "left, right, top, bottom, mid-side")
                self.assertFalse(said["cutCorner"])

    def test_with_its_own_corner_nothing_of_windows_frame_is_painted(self):
        reached, title, visible, corner = self.answer["messages"]["own"]
        self.assertEqual(corner, "Squircle" if self.answer["wanted"] else "Round")
        if corner != "Squircle":
            self.skipTest("this machine gives the window no corner of its own (WindowShape.Wanted)")
        codes = [int(message[0]) for message in reached]
        for code in (WM_NCPAINT, WM_NCUAHDRAWCAPTION, WM_NCUAHDRAWFRAME):
            self.assertNotIn(code, codes, "answered with nothing: %#x" % code)
        activate = [message for message in reached if message[0] == WM_NCACTIVATE]
        self.assertTrue(activate, "WM_NCACTIVATE still reaches Windows' handling, for its activation")
        self.assertTrue(all(message[1] == -1 for message in activate), "with -1: no frame repainted for it")
        for code in (WM_SETTEXT, WM_SETICON):
            taken = [message for message in reached if message[0] == code]
            with self.subTest(code=code):
                self.assertTrue(taken)
                self.assertTrue(all(message[2] is False for message in taken), "taken while marked hidden")
        self.assertEqual(title, "A title own")
        self.assertTrue(visible, "shown again after")

    def test_with_windows_corner_back_every_message_reaches_windows_as_before(self):
        for step in ("maximised",):
            reached, title, visible, corner = self.answer["messages"][step]
            with self.subTest(step=step):
                self.assertEqual(corner, "Round")
                codes = [int(message[0]) for message in reached]
                for code in (WM_NCPAINT, WM_NCACTIVATE, WM_NCUAHDRAWCAPTION, WM_NCUAHDRAWFRAME, WM_SETTEXT, WM_SETICON):
                    self.assertIn(code, codes)
                for message in reached:
                    if message[0] == WM_NCACTIVATE:
                        self.assertEqual(message[1], 0)
                    if message[0] in (WM_SETTEXT, WM_SETICON):
                        self.assertIs(message[2], True)
                self.assertEqual(title, "A title " + step)
                self.assertTrue(visible)

    def test_restored_its_own_corner_again_paints_nothing_of_windows_frame(self):
        reached, title, visible, corner = self.answer["messages"]["restored"]
        if not self.answer["wanted"]:
            self.skipTest("this machine gives the window no corner of its own (WindowShape.Wanted)")
        self.assertEqual(corner, "Squircle")
        codes = [int(message[0]) for message in reached]
        self.assertNotIn(WM_NCPAINT, codes)
        self.assertEqual(title, "A title restored")
        self.assertTrue(visible)


if __name__ == "__main__":
    unittest.main()
