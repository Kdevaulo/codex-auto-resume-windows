r"""v0.6.24 (stage 1, surface E): the window's own outer corner on a live window, off every screen (gui/SoftWindowShape.cs).

A window of the window's own code - its caption (ChromeHost) installed as the Dashboard's is - shown 30000 px off the
desktop, never activated, nothing captured:

* the switch off, as it is in this commit: ChromeHost.OwnCorner makes nothing - no region, no companion, no window owned
  by it at all, Windows' round corner, its frame as W1 left it (ClientSize inside the left, right and bottom frames);
* the corner on (the same WindowCorner the switch would make, put on that caption by hand): after each of a sequence of
  moves and resizes, in the same message turn - nothing pumped between SetWindowPos and the reads - the companion's rect
  is the window's rect grown by the shadow's reach on every side, the window's region is the one WindowShape works out
  for its size (GetWindowRgn, GetRegionData), the window is its own client area, and the companion is shown;
* off while maximised (the window's WS_MAXIMIZE bit, so nothing is shown on a monitor) and in High Contrast: the region
  gone, the companion hidden, Windows' round corner - and on again after each; hidden with the window.

GUI test module (it shows a window, off the screen): run on its own, through gui_lock.sh.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import guiscan

ROOT = Path(__file__).resolve().parent.parent
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
NO_WINDOW = 0x08000000

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
    internal sealed class CornerProbeForm : Form
    {
        internal ChromeHost Caption;

        protected override bool ShowWithoutActivation { get { return true; } }

        protected override void WndProc(ref Message m)
        {
            if (Caption != null && Caption.Intercept(ref m, PassOn)) return;
            base.WndProc(ref m);
        }

        private void PassOn(ref Message m) { base.WndProc(ref m); }
    }

    internal static class CornerSyncProbe
    {
        [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }
        [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr window, out RECT rect);
        [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int w, int h, uint flags);
        [DllImport("user32.dll")] static extern int GetWindowRgn(IntPtr window, IntPtr region);
        [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr window);
        [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr window, uint command);
        [DllImport("user32.dll")] static extern bool EnumThreadWindows(int thread, EnumProc callback, IntPtr data);
        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] static extern IntPtr GetWindowLongPtr(IntPtr window, int index);
        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] static extern IntPtr SetWindowLongPtr(IntPtr window, int index, IntPtr value);
        [DllImport("user32.dll")] static extern int GetDpiForWindow(IntPtr window);
        [DllImport("kernel32.dll")] static extern int GetCurrentThreadId();
        [DllImport("gdi32.dll")] static extern IntPtr CreateRectRgn(int l, int t, int r, int b);
        [DllImport("gdi32.dll")] static extern int GetRegionData(IntPtr region, int size, byte[] data);
        [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr item);
        delegate bool EnumProc(IntPtr window, IntPtr data);

        const uint SWP_NOZORDER = 0x0004, SWP_NOACTIVATE = 0x0010;
        const int GWL_STYLE = -16, WS_MAXIMIZE = 0x01000000;
        const uint GW_OWNER = 4;
        const int Away = -30000;

        static string Q(string text) { return "\"" + text.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\""; }

        static Rectangle Rect(IntPtr window)
        {
            RECT r;
            GetWindowRect(window, out r);
            return Rectangle.FromLTRB(r.Left, r.Top, r.Right, r.Bottom);
        }

        // The window's region now, as rectangles; null when it has none.
        static List<Rectangle> Region(IntPtr window)
        {
            IntPtr into = CreateRectRgn(0, 0, 0, 0);
            try
            {
                if (GetWindowRgn(window, into) == 0) return null;
                int size = GetRegionData(into, 0, null);
                var data = new byte[size];
                GetRegionData(into, size, data);
                var rects = new List<Rectangle>();
                int count = BitConverter.ToInt32(data, 8);
                for (int i = 0; i < count; i++)
                {
                    int at = 32 + 16 * i;
                    rects.Add(Rectangle.FromLTRB(BitConverter.ToInt32(data, at), BitConverter.ToInt32(data, at + 4),
                                                 BitConverter.ToInt32(data, at + 8), BitConverter.ToInt32(data, at + 12)));
                }
                return rects;
            }
            finally { DeleteObject(into); }
        }

        static bool SameCover(List<Rectangle> one, List<Rectangle> two, Size size)
        {
            if (one == null || two == null) return false;
            var a = new byte[size.Width * size.Height];
            var b = new byte[size.Width * size.Height];
            foreach (Rectangle r in one) for (int y = Math.Max(0, r.Top); y < Math.Min(size.Height, r.Bottom); y++) for (int x = Math.Max(0, r.Left); x < Math.Min(size.Width, r.Right); x++) a[y * size.Width + x]++;
            foreach (Rectangle r in two) for (int y = Math.Max(0, r.Top); y < Math.Min(size.Height, r.Bottom); y++) for (int x = Math.Max(0, r.Left); x < Math.Min(size.Width, r.Right); x++) b[y * size.Width + x]++;
            for (int i = 0; i < a.Length; i++) if (a[i] != b[i]) return false;
            return true;
        }

        static int Owned(IntPtr owner)
        {
            int count = 0;
            EnumThreadWindows(GetCurrentThreadId(), delegate(IntPtr window, IntPtr data)
            {
                if (GetWindow(window, GW_OWNER) == owner) count++;
                return true;
            }, IntPtr.Zero);
            return count;
        }

        static CornerProbeForm Make(out ChromeHost caption)
        {
            var form = new CornerProbeForm();
            form.ShowInTaskbar = false;
            form.StartPosition = FormStartPosition.Manual;
            form.FormBorderStyle = FormBorderStyle.Sizable;
            form.Location = new Point(Away, Away);
            form.Size = new Size(640, 480);
            form.BackColor = Palette.Canvas;
            Soft.TitleBar(form);
            var card = new Panel();
            card.SetBounds(16, 16, 400, 80);
            form.Controls.Add(card);
            caption = ChromeHost.Install(form, card, form);
            form.Caption = caption;
            return form;
        }

        // One state of the window with its own corner: where everything is, read at once.
        static string State(CornerProbeForm form, WindowCorner corner, string step)
        {
            IntPtr handle = form.Handle, companion = corner.Companion;
            Rectangle window = Rect(handle);
            int margin = corner.Margin;
            Rectangle grown = Rectangle.Inflate(window, margin, margin);
            Rectangle layer = companion == IntPtr.Zero ? Rectangle.Empty : Rect(companion);
            List<Rectangle> region = Region(handle);
            double scale = GetDpiForWindow(handle) / 96.0;
            var edge = new WindowShape.Edge(window.Width, window.Height, Palette.RadiusCard, Shape.Smoothing, scale);
            bool expected = SameCover(region, WindowShape.RegionRects(edge), window.Size);
            return "{\"step\":" + Q(step) + ",\"corner\":" + Q(corner.Now.ToString()) +
                   ",\"window\":[" + window.X + "," + window.Y + "," + window.Width + "," + window.Height + "]" +
                   ",\"companion\":[" + layer.X + "," + layer.Y + "," + layer.Width + "," + layer.Height + "]" +
                   ",\"grown\":[" + grown.X + "," + grown.Y + "," + grown.Width + "," + grown.Height + "]" +
                   ",\"margin\":" + margin + ",\"dpi\":" + GetDpiForWindow(handle) +
                   ",\"shown\":" + (companion != IntPtr.Zero && IsWindowVisible(companion) ? "true" : "false") +
                   ",\"region\":" + (region == null ? "false" : "true") + ",\"expected\":" + (expected ? "true" : "false") +
                   ",\"client\":[" + form.ClientSize.Width + "," + form.ClientSize.Height + "]" +
                   ",\"frameless\":" + (form.Caption.Frameless ? "true" : "false") +
                   ",\"owned\":" + Owned(handle) + "}";
        }

        static void Move(IntPtr handle, int x, int y, int w, int h)
        {
            SetWindowPos(handle, IntPtr.Zero, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE);
        }

        [STAThread]
        static int Main(string[] args)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            string outPath = args[0];
            var parts = new List<string>();
            try
            {
                Application.EnableVisualStyles();
                Palette.AdoptDesign("soft");
                Palette.Adopt("light");

                // The switch as it is: OwnCorner makes nothing.
                ChromeHost plain;
                CornerProbeForm off = Make(out plain);
                plain.OwnCorner();
                off.Show();
                Move(off.Handle, Away, Away, 700, 500);
                Rectangle offRect = Rect(off.Handle);
                parts.Add("\"off\":{\"corner\":" + Q(plain.OuterCorner.ToString()) + ",\"has\":" + (plain.Corner != null ? "true" : "false") +
                          ",\"region\":" + (Region(off.Handle) == null ? "false" : "true") + ",\"owned\":" + Owned(off.Handle) +
                          ",\"frameless\":" + (plain.Frameless ? "true" : "false") +
                          ",\"window\":[" + offRect.Width + "," + offRect.Height + "],\"client\":[" + off.ClientSize.Width + "," + off.ClientSize.Height + "]}");
                off.Close();
                off.Dispose();

                // The corner on: the WindowCorner the switch would make, on the caption it would go on.
                ChromeHost caption;
                CornerProbeForm form = Make(out caption);
                WindowCorner corner = WindowCorner.Attach(form);
                typeof(ChromeHost).GetField("corner", BindingFlags.NonPublic | BindingFlags.Instance).SetValue(caption, corner);
                form.Show();
                IntPtr handle = form.Handle;
                var steps = new List<string>();
                steps.Add(State(form, corner, "shown"));
                int[][] moves = {
                    new[] { Away + 40, Away + 30, 640, 480 }, new[] { Away + 41, Away + 30, 640, 480 },
                    new[] { Away + 41, Away + 30, 900, 600 }, new[] { Away - 7, Away + 12, 901, 611 },
                    new[] { Away, Away, 500, 400 }, new[] { Away + 300, Away + 200, 1500, 1000 } };
                for (int i = 0; i < moves.Length; i++)
                {
                    Move(handle, moves[i][0], moves[i][1], moves[i][2], moves[i][3]);
                    steps.Add(State(form, corner, "move " + i));
                }
                Palette.Contrast = true;
                Move(handle, Away + 10, Away, 1500, 1000);
                steps.Add(State(form, corner, "high contrast"));
                Palette.Contrast = false;
                Move(handle, Away + 20, Away, 1500, 1000);
                steps.Add(State(form, corner, "contrast off"));
                IntPtr style = GetWindowLongPtr(handle, GWL_STYLE);
                SetWindowLongPtr(handle, GWL_STYLE, new IntPtr(style.ToInt64() | WS_MAXIMIZE));
                Move(handle, Away + 30, Away, 1500, 1000);
                steps.Add(State(form, corner, "maximised"));
                SetWindowLongPtr(handle, GWL_STYLE, new IntPtr(style.ToInt64() & ~(long)WS_MAXIMIZE));
                Move(handle, Away + 40, Away, 1500, 1000);
                steps.Add(State(form, corner, "restored"));
                form.Hide();
                steps.Add(State(form, corner, "hidden"));
                form.Show();
                steps.Add(State(form, corner, "shown again"));
                parts.Add("\"steps\":[" + string.Join(",", steps.ToArray()) + "]");
                form.Close();
                form.Dispose();
            }
            catch (Exception error)
            {
                parts.Add("\"error\":" + Q(error.ToString()));
            }
            File.WriteAllText(outPath, "{" + string.Join(",", parts.ToArray()) + "}", new UTF8Encoding(false));
            return 0;
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class CornerSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="car-corner-sync-")
        work = Path(cls.folder.name)
        probe = work / "CornerSyncProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "CornerSync.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.CornerSyncProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
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

    def steps(self):
        return {step["step"]: step for step in self.answer["steps"]}

    def test_with_the_switch_off_the_window_is_as_it_was(self):
        off = self.answer["off"]
        self.assertFalse(off["has"], "OwnCorner made a corner with the switch off")
        self.assertEqual(off["corner"], "Round")
        self.assertFalse(off["region"])
        self.assertEqual(off["owned"], 0, "a window owned by it: a companion")
        self.assertFalse(off["frameless"])
        # The frame W1 left: Windows' left, right and bottom frames round the client area, none at the top.
        self.assertLess(off["client"][0], off["window"][0])
        self.assertLess(off["client"][1], off["window"][1])

    def test_the_companion_follows_in_the_same_turn(self):
        moved = [step for step in self.answer["steps"] if step["step"] == "shown" or step["step"].startswith("move ")]
        self.assertEqual(len(moved), 7)
        for step in moved:
            with self.subTest(step=step["step"]):
                self.assertEqual(step["corner"], "Squircle")
                self.assertEqual(step["companion"], step["grown"], "the companion is not the window grown by the shadow")
                self.assertTrue(step["region"])
                self.assertTrue(step["expected"], "the region is not the one worked out for the window's size: %r" % step)
                self.assertTrue(step["shown"])
                self.assertTrue(step["frameless"])
                self.assertEqual(step["client"], step["window"][2:], "the window is not its own client area")
                self.assertEqual(step["owned"], 1)

    def test_off_while_maximised_and_in_high_contrast_and_on_again(self):
        steps = self.steps()
        for name in ("high contrast", "maximised"):
            with self.subTest(step=name):
                step = steps[name]
                self.assertEqual(step["corner"], "Round")
                self.assertFalse(step["region"])
                self.assertFalse(step["shown"])
                self.assertFalse(step["frameless"])
        for name in ("contrast off", "restored", "shown again"):
            with self.subTest(step=name):
                step = steps[name]
                self.assertEqual(step["corner"], "Squircle")
                self.assertTrue(step["region"])
                self.assertTrue(step["expected"], step)
                self.assertTrue(step["shown"], step)
                self.assertEqual(step["companion"], step["grown"], step)

    def test_hidden_with_the_window(self):
        self.assertFalse(self.steps()["hidden"]["shown"])


if __name__ == "__main__":
    unittest.main()
