r"""A window that reopens itself stays until the new one is on the screen (v0.6.24-beta.2).

M-CORNER re-check 8 (2026-11-17, item 5c): every reopen for a language or a theme left no Dashboard on the screen for
0.6-1.0 s, between the old window going and the new one appearing in its place.

The old window closed as soon as Process.MainWindowHandle found the new one - a window shown, which is not a window
painted. v0.6.23 and v0.6.24-beta showed it unpainted (re-check 5: an empty outline with the desktop through it); since
c199bf14c it is cloaked until its first paint (WindowCorner.Cloak, Painted), so nothing was there. Measured off the screen
with both processes (40 ms a read, three runs each): the old window went 9-73 ms after the new one was shown, and the new
one first painted (v0.6.23, v0.6.24-beta: its first idle turn) or came on (beta.2: uncloaked) 96-206 ms after that - on
a real screen, with the real bridge and a whole window painted at 150 %, the 0.6-1.0 s seen.

Now the old window waits for the new one to be on the screen: shown and no longer held off by its own cloak
(SettingsForm.OnScreen, WindowCorner.HeldOff - DWMWA_CLOAKED's DWM_CLOAKED_APP; the shell's cloak, another virtual
desktop, is not waited for), then closes - 22-62 ms after the new one came on. It takes no input from the moment it
reopens (EnableWindow), so a person can never click two Dashboards; the new one opens at the old one's place and size as
before, and the ten seconds AwaitWindow allows still end the wait for a window that never comes on.

The live probe: two processes of a probe compiled with the window, each the real Dashboard (standard edition) shown 30000
px off the desktop as an unowned tool window that is never activated, answered from the pictures' pinned scratch
installation. The first reopens itself (Reopen), which starts the probe again as the new window; each says when, on the
machine's one clock (Stopwatch), its window was shown, came on (DWMWA_CLOAKED read every millisecond on a thread of its
own) and went. The new window's thread is kept busy for 400 ms before its first paint, as a real one is with its first
answers and a whole window to paint: the old one, closed once the new one was shown, went that long before it came on. GUI test module (it shows windows, off the screen): run on its own, through gui_lock.sh.
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
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import guiscan  # noqa: E402

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class SourceTests(unittest.TestCase):
    def test_the_old_window_waits_for_the_new_one_on_the_screen(self):
        reopen = guiscan.member_body("SettingsForm", "Reopen")
        self.assertIn("shown = AwaitWindow(delegate { started.Refresh(); return OnScreen(started.MainWindowHandle); },", reopen)
        self.assertLess(reopen.index("EnableWindow(Handle, false);"), reopen.index("AwaitWindow("),
                        "no input to the old window while both are there")
        on_screen = guiscan.member_body("SettingsForm", "OnScreen")
        self.assertIn("return window != IntPtr.Zero && !WindowCorner.HeldOff(window);", on_screen)

    def test_only_its_own_cloak_is_waited_for(self):
        held = guiscan.member_body("WindowCorner", "HeldOff")
        self.assertIn("DwmGetWindowAttribute(window, CloakedNow, out value, 4) == 0 && (value & CloakedByApp) != 0", held)
        self.assertIn("catch (Exception) { return false; }", held)
        source = guiscan.read("gui/SoftWindowShape.cs")
        self.assertIn("private const int CloakedNow = 14, CloakedByApp = 1;", source)


PROBE = r"""
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class HandOverProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            bool reopened = false;
            foreach (string a in argv) if (a.StartsWith("--reopened=")) reopened = true;
            string outPath = reopened ? Environment.GetEnvironmentVariable("HANDOVER_NEW_OUT") : argv[1];
            try { return reopened ? SettingsForm.HandOverNew() : SettingsForm.HandOverOld(argv[0], argv[1]); }
            catch (Exception e) { File.WriteAllText(outPath, "{\"error\":" + Json.Write(e.ToString()) + "}"); return 3; }
        }
    }

    internal sealed partial class SettingsForm
    {
        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] private static extern IntPtr HandGetLong(IntPtr h, int index);
        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] private static extern IntPtr HandSetLong(IntPtr h, int index, IntPtr value);
        [DllImport("user32.dll", EntryPoint = "ShowWindow")] private static extern bool HandShowWindow(IntPtr h, int cmd);
        [DllImport("user32.dll", EntryPoint = "IsWindowEnabled")] private static extern bool HandEnabled(IntPtr h);
        [DllImport("dwmapi.dll", EntryPoint = "DwmGetWindowAttribute")] private static extern int HandDwmGet(IntPtr h, int attribute, out int value, int size);

        private static double HandNow() { return Stopwatch.GetTimestamp() * 1000.0 / Stopwatch.Frequency; }

        private static SettingsForm HandForm(string answersPath)
        {
            Theme.Opened = "light";
            Design.Opened = "soft";
            Palette.AdoptDesign("soft");
            Palette.Adopt(Theme.Current("light"));
            var job = Json.Parse(File.ReadAllText(answersPath, new UTF8Encoding(false))) as Dictionary<string, object>;
            renderAnswers = Items(job, "answers");
            object gate = new object();
            PersistentBridge.Answers = delegate(string command, string argument)
            {
                lock (gate) Thread.Sleep(40);
                return RenderAnswer(command, argument);
            };
            DialogAnswers = delegate { return false; };
            string nowhere = Path.Combine(Path.GetTempPath(), "car-hand-over-nowhere-" + Process.GetCurrentProcess().Id);
            var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), RenderAnswer("strings", null), null);
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(-30000, -30000);
            form.placedBounds = Rectangle.Empty;
            return form;
        }

        private static void HandShow(SettingsForm form, int busyMs)
        {
            IntPtr h = form.Handle;
            // No taskbar button and never activated, yet a window of its own (unowned), as Process.MainWindowHandle finds.
            HandSetLong(h, -20, (IntPtr)(HandGetLong(h, -20).ToInt64() | 0x80 | 0x08000000));
            form.OnLoad(EventArgs.Empty);
            form.placedBounds = Rectangle.Empty;
            // The new window's thread busy before its first paint, as the real one is with its first answers and a whole
            // window to paint at 150 %: what it does in that time is taken before the show's own messages.
            if (busyMs > 0) form.BeginInvoke(new MethodInvoker(delegate { Thread.Sleep(busyMs); }));
            HandShowWindow(h, 4);
            form.BeginInvoke(new MethodInvoker(delegate { form.placedBounds = Rectangle.Empty; form.OnShown(EventArgs.Empty); }));
        }

        /// The window a reopen started: when it was shown, and when it came on the screen (no longer cloaked).
        internal static int HandOverNew()
        {
            string outPath = Environment.GetEnvironmentVariable("HANDOVER_NEW_OUT");
            var form = HandForm(Environment.GetEnvironmentVariable("HANDOVER_ANSWERS"));
            var said = new Dictionary<string, object>();
            IntPtr h = form.Handle;
            Func<bool> cloaked = delegate
            {
                int value;
                return HandDwmGet(h, 14, out value, 4) == 0 && value != 0;
            };
            said["cloaked_as_made"] = cloaked();
            double[] at = { -1, -1 };
            var spy = new Thread(delegate()
            {
                var until = Stopwatch.StartNew();
                while (until.ElapsedMilliseconds < 8000)
                {
                    if (at[0] >= 0 && !cloaked()) { at[1] = HandNow(); return; }
                    Thread.Sleep(1);
                }
            });
            spy.IsBackground = true;
            spy.Start();
            HandShow(form, 400);
            at[0] = HandNow();
            var context = new ApplicationContext();
            var end = new System.Windows.Forms.Timer();
            end.Interval = 4000;
            end.Tick += delegate
            {
                end.Stop();
                said["shown"] = at[0];
                said["on_screen"] = at[1];
                File.WriteAllText(outPath, Json.Write(said), new UTF8Encoding(false));
                form.Close();
                context.ExitThread();
            };
            end.Start();
            Application.Run(context);
            return 0;
        }

        /// The window that reopens: shown, then Reopen; when it stopped taking input and when its window went.
        internal static int HandOverOld(string answersPath, string outPath)
        {
            Environment.SetEnvironmentVariable("HANDOVER_ANSWERS", answersPath);
            string newOut = outPath + ".new.json";
            if (File.Exists(newOut)) File.Delete(newOut);
            Environment.SetEnvironmentVariable("HANDOVER_NEW_OUT", newOut);
            var form = HandForm(answersPath);
            var said = new Dictionary<string, object>();
            double reopenAt = -1, goneAt = -1;
            form.HandleDestroyed += delegate { if (goneAt < 0) goneAt = HandNow(); };
            HandShow(form, 0);
            var context = new ApplicationContext();
            var timer = new System.Windows.Forms.Timer();
            timer.Interval = 20;
            var since = Stopwatch.StartNew();
            timer.Tick += delegate
            {
                try
                {
                    if (reopenAt < 0)
                    {
                        if (since.ElapsedMilliseconds < 1500) return;
                        reopenAt = HandNow();
                        form.Reopen(false);
                        said["reopening"] = form.reopening;
                        said["enabled_while_reopening"] = HandEnabled(form.Handle);
                        if (!form.reopening) goneAt = 0;
                    }
                    else if ((goneAt >= 0 && File.Exists(newOut)) || since.ElapsedMilliseconds > 30000)
                    {
                        timer.Stop();
                        Thread.Sleep(200);
                        said["reopen"] = reopenAt;
                        said["gone"] = goneAt;
                        said["new"] = File.Exists(newOut) ? Json.Parse(File.ReadAllText(newOut, new UTF8Encoding(false))) : null;
                        File.WriteAllText(outPath, Json.Write(said), new UTF8Encoding(false));
                        context.ExitThread();
                    }
                }
                catch (Exception e)
                {
                    File.WriteAllText(outPath, "{\"error\":" + Json.Write(e.ToString()) + "}");
                    context.ExitThread();
                }
            };
            timer.Start();
            Application.Run(context);
            if (!form.IsDisposed) form.Dispose();
            return 0;
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class HandOverTests(unittest.TestCase):
    """Two processes of the real window, off the screen: the old one reopens itself as the new one."""

    RUNS = 2

    @classmethod
    def setUpClass(cls):
        import advanced_shots
        cls.folder = tempfile.TemporaryDirectory(prefix="car-hand-over-")
        work = Path(cls.folder.name)
        read, _envelope = advanced_shots.read_answers("standard", "base", "en")
        answers = work / "answers.json"
        answers.write_text(json.dumps(advanced_shots.form_answers(read), ensure_ascii=False), encoding="utf-8")
        probe = work / "HandOverProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "HandOver.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.HandOverProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.runs = []
        if cls.failure is None:
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
            for i in range(cls.RUNS):
                out = work / ("out-%d.json" % i)
                done = subprocess.run([str(exe), str(answers), str(out)], capture_output=True, timeout=120,
                                      creationflags=NO_WINDOW, env=environment, cwd=str(work))
                said = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
                if done.returncode != 0 or "error" in said or not said.get("new") or "error" in said["new"]:
                    cls.failure = "the probe failed (exit %d): %s" % (done.returncode, json.dumps(said)[:2000])
                    break
                cls.runs.append(said)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_the_old_window_reopened_and_took_no_input_meanwhile(self):
        for i, said in enumerate(self.runs):
            with self.subTest(run=i):
                self.assertTrue(said["reopening"])
                self.assertFalse(said["enabled_while_reopening"], "never two Dashboards a person can click")
                self.assertGreater(said["gone"], said["reopen"], "the old window closed once the new one came")

    def test_the_old_window_goes_only_once_the_new_one_is_on_the_screen(self):
        for i, said in enumerate(self.runs):
            new = said["new"]
            with self.subTest(run=i, cloaked=new["cloaked_as_made"]):
                came = new["on_screen"] if new["cloaked_as_made"] else new["shown"]
                self.assertGreater(came, 0, "the new window came on the screen")
                self.assertGreaterEqual(said["gone"], came,
                                        "the old window went %.0f ms before the new one came on" % (came - said["gone"]))


if __name__ == "__main__":
    unittest.main()
