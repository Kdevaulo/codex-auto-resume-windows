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
        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] internal static extern IntPtr GetWindowLongPtr(IntPtr h, int i);
        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] internal static extern IntPtr SetWindowLongPtr(IntPtr h, int i, IntPtr v);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] internal static extern int GetWindowText(IntPtr h, StringBuilder text, int most);
        internal const int Away = -30000, GWL_STYLE = -16, WS_MAXIMIZE = 0x01000000, WS_VISIBLE = 0x10000000;
        internal const uint SWP_NOZORDER = 0x0004, SWP_NOACTIVATE = 0x0010;

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

    // A window with the Dashboard's caption and corner whose procedure records what reaches Windows' own handling.
    internal sealed class FrameProbeForm : Form
    {
        internal ChromeHost Caption;
        internal readonly List<object> Reached = new List<object>();
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
            if (Recording && (msg == 0x85 || msg == 0x86 || msg == 0xAE || msg == 0xAF || msg == 0x0C || msg == 0x80))
            {
                long style = IsHandleCreated ? FrameNative.GetWindowLongPtr(Handle, FrameNative.GWL_STYLE).ToInt64() : 0;
                Reached.Add(new List<object> { (double)msg, (double)m.LParam.ToInt64(), (style & FrameNative.WS_VISIBLE) != 0 });
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
            return new List<object> { form.Reached, text.ToString(), FrameNative.IsWindowVisible(h),
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
                { "corner", form.CaptionHost.OuterCorner.ToString() } };
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
            form.Show();
            Application.DoEvents();
            said["shown"] = CornerFrameState(form);
            FrameNative.Maximised(h, true, FrameNative.Away + 10, 1400, 900);
            said["maximised"] = CornerFrameState(form);
            FrameNative.Maximised(h, false, FrameNative.Away + 20, 1100, 760);
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
        reply = {"ok": True, "language": "en", "strings": l10n.catalog("en"), "endonyms": dict(l10n.ENDONYMS),
                 "preference": "en", "system_language": "en"}
        (work / "strings-en.json").write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
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

if __name__ == "__main__":
    unittest.main()
