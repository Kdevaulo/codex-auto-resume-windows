r"""v0.6.24 final: the setup window changes page in one frame, and keeps its size while it does.

Live re-check 3 (L1): after Repair was pressed, two DXGI frames still showed the first page with two grey boxes over it,
the next one the Progress page's head over the first page's remains, and only the fourth the Progress page whole - the old
page's controls were taken away and the new page's made, each painted on its own as the thread came to it. And at the
switch to Finish one poll read the window 906 x 940 for a moment where it is 900 x 900. Now every page change holds the
painting of the window's ground (WM_SETREDRAW) while the page is swapped and measured, then paints all of it offscreen and
puts it on the screen at once (WS_EX_COMPOSITED for that paint, RDW_UPDATENOW); and Fit sets the window's size only where
it changes.

A probe compiled with the window's sources makes the real setup window of a first installation, 30000 px off the desktop
and never activated, and goes through Welcome, Options, Progress (a stub run) and Finish, as a person's presses do. At paint
time it watches the window's ground and the page's sheet: every control a page change, or a change of the Progress page's
step list, adds comes while their painting is held, and the paint after every change is the one asked for at once,
composited offscreen - never a paint the thread comes to
later, a control at a time, which is a frame with neither page whole. Every move or size of the window is read back from
Windows. GUI test module (it shows a window, off the screen): run it on its own, through gui_lock.sh.
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

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PROBE = r"""
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class SwapProbe
    {
        [StructLayout(LayoutKind.Sequential)]
        internal struct RECT { public int Left, Top, Right, Bottom; }

        [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr window, out RECT rect);
        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] static extern IntPtr GetWindowLongPtr(IntPtr window, int index);

        const int WM_PAINT = 0x000F, WM_SETREDRAW = 0x000B, WM_WINDOWPOSCHANGED = 0x0047;

        // Which windows' coming WM_PAINT came through the thread's queue - painted as the thread came to it - rather than
        // sent by a paint asked for at once (RDW_UPDATENOW).
        static readonly HashSet<IntPtr> queued = new HashSet<IntPtr>();
        static bool shown;
        static Held ground, sheet;
        static string page = "";
        static int adds;
        // Every control a page change adds while the ground's painting is not held.
        static readonly List<object> alone = new List<object>();
        // After every time painting is let go, how the next paint of the ground came: "whole" (sent, composited) or not.
        static readonly List<object> after = new List<object>();
        static readonly List<object> sizes = new List<object>();

        sealed class Queue : IMessageFilter
        {
            public bool PreFilterMessage(ref Message m)
            {
                if (m.Msg == WM_PAINT) queued.Add(m.HWnd);
                return false;
            }
        }

        // The window's ground, or the page's sheet: whether its painting is held, and how it was painted after.
        sealed class Held : NativeWindow
        {
            internal bool On, waiting;

            protected override void WndProc(ref Message m)
            {
                if (m.Msg == WM_SETREDRAW)
                {
                    On = m.WParam == IntPtr.Zero;
                    if (!On) waiting = true;
                }
                if (m.Msg == WM_PAINT)
                {
                    bool came = queued.Remove(Handle);
                    if (waiting)
                    {
                        waiting = false;
                        bool composited = (GetWindowLongPtr(Handle, -20).ToInt64() & 0x02000000) != 0;
                        after.Add(!came && composited ? "whole" : came ? "queued" : "plain");
                    }
                }
                base.WndProc(ref m);
            }
        }

        sealed class Moves : NativeWindow
        {
            protected override void WndProc(ref Message m)
            {
                base.WndProc(ref m);
                if (m.Msg != WM_WINDOWPOSCHANGED) return;
                RECT r;
                if (GetWindowRect(Handle, out r))
                    sizes.Add(new List<object> { page, (double)(r.Right - r.Left), (double)(r.Bottom - r.Top) });
            }
        }

        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { Run(said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }

        static void Run(Dictionary<string, object> said)
        {
            var flow = new InstallerFlow(InstallerFlow.Install, "C:\\Users\\ExampleUser\\.codex-auto-resume", "standard", null, "9.9.9");
            flow.Unpacks = true;
            InstallerWindow.Speaker speaker = delegate(string other) { return new InstallerWords(null, other); };
            InstallerWindow.Runner runner = delegate(InstallerFlow answered, Action<string> line, Action<double> unpacked)
            {
                line("Codex Auto Resume setup: unpacking Test-v9.9.9-win-x64.zip into a folder");
                for (int i = 1; i <= 200; i++) unpacked(i / 200.0);
                foreach (string each in new[] { "  [ok] Found Codex", "  Installing program files",
                                                "  Copying the program files into place", "  Registering the Codex plugin",
                                                "  Setting up the watcher", "  Checking the installation" })
                {
                    line(each);
                    Thread.Sleep(120);
                }
                return 0;
            };
            var window = new InstallerWindow(flow, speaker("en"), speaker, runner, null, null);
            window.StartPosition = FormStartPosition.Manual;
            window.Location = new Point(-30000, -30000);
            window.ShowInTaskbar = false;
            IntPtr made = window.Handle;
            // Made off the desktop; from here on as the setup program has it (CenterScreen), so Fit at Finish does not
            // centre it on the primary screen as a Manual window's is.
            window.StartPosition = FormStartPosition.CenterScreen;
            Application.AddMessageFilter(new Queue());
            var moves = new Moves();
            ground = new Held();
            sheet = new Held();
            const BindingFlags inside = BindingFlags.NonPublic | BindingFlags.Instance;
            var groundControl = (Control)typeof(InstallerWindow).GetField("ground", inside).GetValue(window);
            var sheetControl = (Control)typeof(InstallerWindow).GetField("sheet", inside).GetValue(window);
            sheetControl.ControlAdded += delegate(object sender, ControlEventArgs e)
            {
                if (!shown) return;
                adds++;
                if (!ground.On && !sheet.On) alone.Add(window.Page + " " + e.Control.GetType().Name + " '" + (e.Control.Text ?? "") + "'");
            };
            MethodInfo forward = typeof(InstallerWindow).GetMethod("Forward", inside);
            var clock = Stopwatch.StartNew();
            var pages = new List<object>();
            int pressed = 0;
            var step = new System.Windows.Forms.Timer();
            step.Interval = 400;
            step.Tick += delegate
            {
                page = window.Page ?? "";
                if (pages.Count == 0 || (string)pages[pages.Count - 1] != page) pages.Add(page);
                if (page == InstallerFlow.Finish && !window.Running)
                {
                    step.Stop();
                    window.Close();
                    return;
                }
                if (clock.ElapsedMilliseconds > 60000) { step.Stop(); window.Close(); return; }
                // A person's press of the page's forward button: Welcome -> Options -> the run.
                if ((page == InstallerFlow.Welcome || page == InstallerFlow.Options) && pressed < 4)
                {
                    pressed++;
                    forward.Invoke(window, null);
                    page = window.Page ?? "";
                }
            };
            window.Shown += delegate
            {
                moves.AssignHandle(window.Handle);
                ground.AssignHandle(groundControl.Handle);
                sheet.AssignHandle(sheetControl.Handle);
                shown = true;
                sizes.Add(new List<object> { "shown", (double)window.Width, (double)window.Height });
                step.Start();
            };
            Application.Run(window);
            moves.ReleaseHandle();
            ground.ReleaseHandle();
            sheet.ReleaseHandle();
            said["pages"] = pages;
            said["alone"] = alone;
            said["after"] = after;
            said["adds"] = (double)adds;
            said["sizes"] = sizes;
            said["code"] = (double)window.Code;
            window.Dispose();
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class PageSwapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="car-page-swap-")
        work = Path(cls.folder.name)
        probe = work / "SwapProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "Swap.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.SwapProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            # CODEX_AR_STILL_READY names an event nobody waits on: the window is never activated (ShowWithoutActivation).
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"),
                               CODEX_AR_STILL_READY="car-page-swap-probe-" + str(os.getpid()))
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

    def test_it_went_through_every_page(self):
        self.assertEqual(self.answer["pages"][0], "welcome")
        for page in ("options", "progress", "finish"):
            self.assertIn(page, self.answer["pages"])
        self.assertEqual(self.answer["code"], 0)
        self.assertGreater(self.answer["adds"], 10, "the probe saw the pages' controls come")

    def test_no_control_of_a_new_page_comes_while_the_window_paints(self):
        """Fails with the swap painted as the thread comes to each control: frames with neither page whole."""
        self.assertEqual(self.answer["alone"], [])

    def test_each_page_change_is_painted_whole_at_once(self):
        """After every page change the next paint is the one asked for at once, composited offscreen."""
        self.assertGreaterEqual(len(self.answer["after"]), 3, "Options, Progress and Finish at least")
        self.assertEqual(set(self.answer["after"]), {"whole"}, self.answer["after"])

    def test_the_window_keeps_its_size_through_every_page_change(self):
        """Fails with Fit setting the window's size again at Finish: Windows had it 906 x 940 for a moment."""
        sizes = {(width, height) for _, width, height in self.answer["sizes"]}
        self.assertEqual(len(sizes), 1, self.answer["sizes"])


class PageSwapSourceTests(unittest.TestCase):
    def test_every_page_change_holds_the_painting_and_paints_once(self):
        for member in ("ShowPage", "Fit"):
            with self.subTest(member):
                body = guiscan.member_body("InstallerWindow", member)
                self.assertIn("bool held = HoldPainting();", body)
                self.assertIn("if (held) PaintWhole();", body)


if __name__ == "__main__":
    unittest.main()
