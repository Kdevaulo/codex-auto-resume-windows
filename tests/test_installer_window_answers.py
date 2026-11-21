r"""v0.6.24 final: the setup window paints and answers all the way through a run.

Re-check 2 on the owner's install: after Repair the setup's first page hung half painted - two grey boxes, no Cancel,
presses not taken - for 2 to more than 15 s, and the Progress page showed with 7 of its 9 steps already ticked; once a Show
log press was not taken during the copy. The run was on a worker, but every line it printed and every entry it unpacked
(thousands, with the bundled Python) was a BeginInvoke of its own, and each unpacked entry laid the page out again: the
window's thread ran them back to back, and Windows hands a thread its posted messages before any input and before
WM_PAINT. Now the worker only writes into a list (Tell, TellUnpacked, TellEnded) that a timer of the window's takes in, in
order, no longer than HearBudget a turn (gui/InstallerWindow.cs).

A probe compiled with the window's sources makes the real setup window of a first installation, 30000 px off the desktop
and never activated, and presses Install (Forward) with a stub run that unpacks 20000 entries as fast as it can, prints
2000 progress lines, and says the installer's own lines a step at a time, each step slowed. From another thread it asks
the window WM_NULL through SendMessageTimeout every 20 ms from the press until the run returns: the window answers each
within 100 ms. The Progress page is the window's page the moment the press returns, and the run ends on Finish with every
line in the log, in order. GUI test module (it shows a window, off the screen): run it on its own, through gui_lock.sh.
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
    internal static class AnswersProbe
    {
        [DllImport("user32.dll", EntryPoint = "SendMessageTimeoutW")]
        private static extern IntPtr SendMessageTimeout(IntPtr window, int message, IntPtr wParam, IntPtr lParam, int flags,
                                                        int milliseconds, out IntPtr answer);

        private static readonly string[] Lines = {
            "Codex Auto Resume", "edition: standard", "  [ok] Found Codex", "  Installing program files",
            "  Copying the program files into place", "  [ok] Bundled Python 3.13 (no system Python needed)",
            "  Registering the Codex plugin", "  Setting up the watcher", "  Checking the installation" };

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
            var returned = new ManualResetEvent(false);
            InstallerWindow.Runner runner = delegate(InstallerFlow answered, Action<string> line, Action<double> unpacked)
            {
                line("Codex Auto Resume setup: unpacking Test-v9.9.9-win-x64.zip into a folder");
                for (int i = 1; i <= 20000; i++) unpacked(i / 20000.0);
                for (int i = 0; i < Lines.Length; i++)
                {
                    line(Lines[i]);
                    if (i == 4) for (int f = 1; f <= 2000; f++) line("progress: files " + f + "/2000");
                    Thread.Sleep(150);
                }
                returned.Set();
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
            var answers = new List<object>();
            int late = 0;
            long longest = 0;
            string pageAfterPress = null;
            bool done = false;
            var clock = Stopwatch.StartNew();
            var press = new System.Windows.Forms.Timer();
            press.Interval = 300;
            press.Tick += delegate
            {
                press.Stop();
                window.ShowPage(InstallerFlow.Options);
                IntPtr handle = window.Handle;
                var asking = new Thread(delegate()
                {
                    while (!returned.WaitOne(0))
                    {
                        var one = Stopwatch.StartNew();
                        IntPtr answer;
                        IntPtr ok = SendMessageTimeout(handle, 0 /* WM_NULL */, IntPtr.Zero, IntPtr.Zero, 0, 100, out answer);
                        long took = one.ElapsedMilliseconds;
                        lock (answers)
                        {
                            answers.Add((double)took);
                            if (ok == IntPtr.Zero) late++;
                            longest = Math.Max(longest, took);
                        }
                        Thread.Sleep(20);
                    }
                });
                asking.IsBackground = true;
                typeof(InstallerWindow).GetMethod("Forward", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(window, null);
                pageAfterPress = window.Page;
                asking.Start();
            };
            var watch = new System.Windows.Forms.Timer();
            watch.Interval = 50;
            watch.Tick += delegate
            {
                if (window.Page == InstallerFlow.Finish && !window.Running)
                {
                    done = true;
                    watch.Stop();
                    FieldInfo area = typeof(InstallerWindow).GetField("logArea", BindingFlags.NonPublic | BindingFlags.Instance);
                    said["logBox"] = ((SoftTextArea)area.GetValue(window)).Box.Text;
                    window.Close();
                }
                else if (clock.ElapsedMilliseconds > 90000) { watch.Stop(); window.Close(); }
            };
            window.Shown += delegate { press.Start(); watch.Start(); };
            Application.Run(window);
            said["pageAfterPress"] = pageAfterPress;
            said["done"] = done;
            said["code"] = (double)window.Code;
            lock (answers)
            {
                said["asked"] = (double)answers.Count;
                said["late"] = (double)late;
                said["longest"] = (double)longest;
            }
            FieldInfo log = typeof(InstallerWindow).GetField("log", BindingFlags.NonPublic | BindingFlags.Instance);
            said["log"] = log.GetValue(window).ToString();
            window.Dispose();
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class SetupWindowAnswersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="car-setup-answers-")
        work = Path(cls.folder.name)
        probe = work / "AnswersProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "Answers.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.AnswersProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            # CODEX_AR_STILL_READY names an event nobody waits on: the window is never activated (ShowWithoutActivation).
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"),
                               CODEX_AR_STILL_READY="car-setup-answers-probe-" + str(os.getpid()))
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

    def test_the_progress_page_is_up_the_moment_the_press_returns(self):
        self.assertEqual(self.answer["pageAfterPress"], "progress")

    def test_the_window_answers_within_100_ms_all_through_the_run(self):
        """Fails with every line and share a BeginInvoke of its own: the window answered nothing for seconds."""
        self.assertGreater(self.answer["asked"], 20, "asked all through a run of more than a second")
        self.assertEqual(self.answer["late"], 0, "longest wait %d ms" % self.answer["longest"])
        self.assertLess(self.answer["longest"], 100)

    def test_the_run_ends_on_finish_with_every_line_in_the_log_in_order(self):
        self.assertTrue(self.answer["done"])
        self.assertEqual(self.answer["code"], 0)
        box = self.answer["logBox"]
        last = -1
        for line in ("unpacking Test-v9.9.9", "Found Codex", "Copying the program files", "Registering the Codex plugin",
                     "Checking the installation"):
            at = box.find(line)
            self.assertGreater(at, last, line)
            last = at
        self.assertNotIn("progress: files", box, "the window's own progress lines stay out of the log")


class SetupWindowAnswersSourceTests(unittest.TestCase):
    def test_the_worker_posts_nothing_per_line(self):
        start = guiscan.member_body("InstallerWindow", "Start")
        self.assertIn("runner(flow, Tell, TellUnpacked)", start)
        self.assertNotIn("BeginInvoke", start)
        self.assertNotIn("Post(", start)
        self.assertLess(start.index("ShowPage(InstallerFlow.Progress);"), start.index("PaintNow();"))
        self.assertLess(start.index("PaintNow();"), start.index("QueueUserWorkItem"))

    def test_a_timer_takes_it_in_a_bounded_turn_at_a_time(self):
        hear = guiscan.member_body("InstallerWindow", "Hear")
        self.assertIn("spent.ElapsedMilliseconds < HearBudget", hear)
        self.assertIn("internal const int HearInterval = 30, HearBudget = 20;", guiscan.read("gui/InstallerWindow.cs"))


if __name__ == "__main__":
    unittest.main()
