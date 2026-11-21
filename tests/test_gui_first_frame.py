r"""The Dashboard's first frame comes as soon as the window can paint it (v0.6.24 final).

The final's live re-check 3 (L3, 2026-11-21): the Start menu's shortcut showed the Dashboard's first frame 6.1-7.2 s after
the click, three times running. Measured on the same PC from a scratch installation of each edition, with the window's
own start marks (StartMarks, CODEX_AR_START_MARKS) and its real bridge, five runs each, the old and the new window turn
about:

- The first font any thread of the process makes builds GDI+'s collection of every font installed: 225-260 ms in a bare
  program, 230-525 ms inside the window's constructor, on the window's thread, before anything could be painted. Now a
  thread of its own makes it as Main starts (Program.WarmFonts); the constructor's font found it built - its share fell
  from a median 265-397 ms to 90-119 ms.
- Every method of the 1-1.4 MB window runs through the JIT on the window's thread the first time it is called (no ngen
  without an administrator). Now .NET's multicore JIT writes down what the start compiled in the installation's config\
  (Program.StartProfile) and compiles it ahead on the other cores the next time: building the window fell from a median
  268-289 ms to 134-146 ms, making its handles from 129-139 to 57-67 ms, the first page and the show from 352-481 to
  287-368 ms.
- The first frame, from the process's creation: standard median 1819 ms (1743-2518) before, 1174 ms (1056-1512) after;
  advanced 1437 ms (1227-2009) before, 911 ms (789-1456) after. (A start through explorer adds about 1 s before the
  process exists: measured 1.0 s from `explorer.exe` to a probe's process start.)
- A start whose words are not cached (StringsCache: the first after an update, or a key that never matches) waits for
  the interpreter before its first frame, up to StringsWaitMilliseconds: 0.4-0.9 s here on a compiled tree, 4.0-4.9 s
  on a tree no Python had compiled yet - a first frame at 7.7 s, the size of L3's. That wait is not changed here.

The probe: a process of a program compiled with the window, whose Main does what Program.Main does before the window is
made - the font thread, the hand-over's question, the app it runs inside, the start's profile in a scratch
installation's config\ - then the real Dashboard (standard edition), answered from the pictures' pinned answers, shown
30000 px off the desktop as an unowned tool window that is never activated. The window's own marks say when each step
was reached and when its first frame came on (no longer cloaked). GUI test module (it shows windows, off the screen): run
on its own, through gui_lock.sh.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
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

# The first frame of a start that has its profile, from the process's creation: the best of three, because the window's
# thread and the threads that work ahead of it share the cores with whatever else the machine runs, and on a loaded PC
# every start is slower - the new one most, which gains by the cores that are free. Measured on the owner's PC at 150 %,
# this probe (each run prints its marks), the machine quiet: with both changes 705-1024 ms, a start from its profile 705
# and 880; with neither 1409 and 1740. The real start from a scratch installation: 1056-1512 ms with both, a median of
# 1174 (standard), and 1743-2518, a median of 1819, with neither. 1300 ms holds the new start and fails the old one;
# with other test sets running both took 1.8-2.4 s - a failure here is believed only once it fails again on a quiet PC.
FIRST_FRAME_BUDGET_MS = 1300
# GitHub's runners: two cores, a slower disk, no profile from an earlier run of the same build - a budget that still
# catches the window waiting seconds for something before its first paint (the strings wait is 5 s).
CI_FIRST_FRAME_BUDGET_MS = 4000
# And against the start with neither change in the same sitting, the best of three of each: 705 against 1409, 757
# against 1395, 797 against 1093, 1011 against 1503 ms on this PC (0.50-0.73). A quiet PC brought the old start under the
# budget (974-1360 ms), never this close to the new one; with both changes taken back the two are one start, and the
# best of three of either is the other's within some 15 %. Not on CI's runners, whose two cores leave the threads
# working ahead little room.
FIRST_FRAME_SHARE_OF_OLD = 0.8
# The window's own wait for its first font once the font thread has made one (the constructor's "window made" to
# "font"): 64-80 ms in this probe and medians of 90-119 ms in the real start, against 228-236 ms in this probe and
# 230-525 ms in the real start on the window's thread alone. On a machine with fewer fonts both are smaller, and this
# still holds. The median of the four starts.
FONT_WAIT_BUDGET_MS = 150

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
    internal static class FirstFrameProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            // argv: warm|cold, the scratch installation, the answers, the result.
            bool warm = argv[0] == "warm";
            // As Program.Main: the font thread first of all (WarmFonts).
            if (warm) Program.WarmFonts();
            StartMarks.Mark("main");
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            try { return SettingsForm.FirstFrameRun(argv[1], argv[2], argv[3], warm); }
            catch (Exception e)
            {
                File.WriteAllText(argv[3], "{\"error\":" + Json.Write(e.ToString()) + "}");
                return 3;
            }
        }
    }

    internal sealed partial class SettingsForm
    {
        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] private static extern IntPtr FrameGetLong(IntPtr h, int index);
        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] private static extern IntPtr FrameSetLong(IntPtr h, int index, IntPtr value);
        [DllImport("user32.dll", EntryPoint = "ShowWindow")] private static extern bool FrameShowWindow(IntPtr h, int cmd);

        internal static int FirstFrameRun(string root, string answersPath, string outPath, bool warm)
        {
            // As Program.Main before the window is made: the hand-over asked (no window of this program is open), the app
            // this process runs inside, and from there on the start's profile (StartProfile).
            HandOverTo(Application.ExecutablePath, "");
            HostApp.Inside();
            if (warm) Program.StartProfile(root);
            StartMarks.Mark("opening");
            Theme.Opened = "light";
            Design.Opened = "soft";
            Palette.AdoptDesign("soft");
            Palette.Adopt(Theme.Current("light"));
            var job = Json.Parse(File.ReadAllText(answersPath, new UTF8Encoding(false))) as Dictionary<string, object>;
            renderAnswers = Items(job, "answers");
            PersistentBridge.Answers = delegate(string command, string argument)
            {
                Thread.Sleep(20);
                return RenderAnswer(command, argument);
            };
            DialogAnswers = delegate { return false; };
            string nowhere = Path.Combine(root, "nowhere");
            var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), RenderAnswer("strings", null), null);
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(-30000, -30000);
            form.placedBounds = Rectangle.Empty;
            IntPtr h = form.Handle;
            // No taskbar button and never activated.
            FrameSetLong(h, -20, (IntPtr)(FrameGetLong(h, -20).ToInt64() | 0x80 | 0x08000000));
            form.OnLoad(EventArgs.Empty);
            form.placedBounds = Rectangle.Empty;
            FrameShowWindow(h, 4);
            form.BeginInvoke(new MethodInvoker(delegate { form.placedBounds = Rectangle.Empty; form.OnShown(EventArgs.Empty); }));
            var context = new ApplicationContext();
            var end = new System.Windows.Forms.Timer();
            end.Interval = 50;
            var since = Stopwatch.StartNew();
            end.Tick += delegate
            {
                try
                {
                    if (!form.firstFrameMarked && since.ElapsedMilliseconds < 20000) return;
                    if (since.ElapsedMilliseconds < 1500) return;
                    end.Stop();
                    var said = new Dictionary<string, object>();
                    said["first_frame_marked"] = form.firstFrameMarked;
                    File.WriteAllText(outPath, Json.Write(said), new UTF8Encoding(false));
                    form.Close();
                    context.ExitThread();
                }
                catch (Exception e)
                {
                    File.WriteAllText(outPath, "{\"error\":" + Json.Write(e.ToString()) + "}");
                    context.ExitThread();
                }
            };
            end.Start();
            Application.Run(context);
            return 0;
        }
    }
}
"""


def marks(text: str) -> dict:
    """{step: ms since the process was created}, each step's first mark."""
    found = {}
    for line in text.splitlines():
        at, _, step = line.strip().partition(" ")
        if step:
            found.setdefault(step, float(at))
    return found


class SourceTests(unittest.TestCase):
    def test_the_font_thread_starts_before_anything_else(self):
        """Fails with WarmFonts' call taken out of Main, or put after the work it is to run beside."""
        main = guiscan.member_body("Program", "Main")
        start = main.index("WarmFonts();")
        for later in ("AppContext.SetSwitch(", "Application.EnableVisualStyles();", "SettingsForm.HandsOverOnStart(",
                      "HostApp.Inside()", "new Bridge(root)", "new SettingsForm("):
            with self.subTest(later):
                self.assertLess(start, main.index(later))
        warm = guiscan.member_body("Program", "WarmFonts")
        self.assertIn("SystemFonts.MessageBoxFont", warm)
        self.assertIn("warm.IsBackground = true;", warm)

    def test_the_profile_is_started_only_for_a_window_that_opens(self):
        """After the hand-over and the relaunch outside have both ended a start they take; never a capture's."""
        main = guiscan.member_body("Program", "Main")
        profile = main.index("if (Soft.StillReady == null) StartProfile(root);")
        self.assertLess(main.index("SettingsForm.HandOverTo("), profile)
        self.assertLess(main.index("HostApp.StuckInside = inside;"), profile)
        self.assertLess(profile, main.index("new Bridge(root)"))
        start = guiscan.member_body("Program", "StartProfile")
        self.assertIn('Path.Combine(root, "config")', start)
        self.assertIn("if (!Directory.Exists(folder)) return;", start)
        self.assertIn("System.Runtime.ProfileOptimization.SetProfileRoot(folder);", start)
        self.assertIn("System.Runtime.ProfileOptimization.StartProfile(StartProfileName);", start)

    def test_the_marks_cost_nothing_when_they_are_off(self):
        marks_type = guiscan.type_body("StartMarks")
        self.assertIn('Environment.GetEnvironmentVariable("CODEX_AR_START_MARKS")', marks_type)
        mark = guiscan.member_body("StartMarks", "Mark")
        self.assertRegex(mark, r"^[^{]*\{\s*if \(said == null\) return;", "the first thing a mark does")
        self.assertIn("if (StartMarks.On && !firstFrameMarked) MarkFirstFrame(m.Msg);", guiscan.member_body("SettingsForm", "WndProc"))


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class FirstFrameTests(unittest.TestCase):
    """Processes of the real window, off the screen: when its first frame came, and what it waited for before."""

    @classmethod
    def setUpClass(cls):
        import advanced_shots
        cls.folder = tempfile.TemporaryDirectory(prefix="car-first-frame-")
        work = Path(cls.folder.name)
        read, _envelope = advanced_shots.read_answers("standard", "base", "en")
        answers = work / "answers.json"
        answers.write_text(json.dumps(advanced_shots.form_answers(read), ensure_ascii=False), encoding="utf-8")
        probe = work / "FirstFrameProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "FirstFrame.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/optimize+", "/out:" + str(exe),
                                "/main:CodexAutoResume.FirstFrameProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.root = work / "install"
        (cls.root / "config").mkdir(parents=True)
        cls.profile = cls.root / "config" / "window-start.jit"
        cls.runs = {"warm": [], "cold": []}
        cls.profile_after_first = None
        if cls.failure is None:
            # The start with neither change three times, between the new start's four: the first of those writes the
            # profile down, the three after it start from it (a start with neither change writes none and reads none).
            for i, mode in enumerate(("cold", "warm", "cold", "warm", "cold", "warm", "warm")):
                out = work / ("out-%d.json" % i)
                marked = work / ("marks-%d.txt" % i)
                environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"),
                                   CODEX_AR_START_MARKS=str(marked))
                environment.pop("CODEX_AR_STILL_READY", None)
                done = subprocess.run([str(exe), mode, str(cls.root), str(answers), str(out)], capture_output=True,
                                      timeout=120, creationflags=NO_WINDOW, env=environment, cwd=str(work))
                said = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
                if done.returncode != 0 or "error" in said or not said.get("first_frame_marked") or not marked.is_file():
                    cls.failure = "the probe failed (exit %d): %s" % (done.returncode, json.dumps(said)[:2000])
                    break
                cls.runs[mode].append(marks(marked.read_text(encoding="utf-8")))
                if mode == "warm" and cls.profile_after_first is None:
                    cls.profile_after_first = cls.profile.is_file() and cls.profile.stat().st_size > 0
        for mode, runs in cls.runs.items():
            for run in runs:
                print(mode, {step: round(at) for step, at in run.items()}, file=sys.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_the_first_frame_comes_within_its_budget(self):
        """Fails with either change taken back: the window then took 1.4-1.8 s on this PC."""
        profiled = self.runs["warm"][1:]
        first = min(run["first frame"] for run in profiled)
        on_ci = bool(os.environ.get("GITHUB_ACTIONS"))
        budget = CI_FIRST_FRAME_BUDGET_MS if on_ci else FIRST_FRAME_BUDGET_MS
        self.assertLessEqual(first, budget, "the first frame %.0f ms after the process was created: %s"
                             % (first, [round(run["first frame"]) for run in profiled]))
        old = min(run["first frame"] for run in self.runs["cold"])
        if not on_ci:
            self.assertLessEqual(first, old * FIRST_FRAME_SHARE_OF_OLD,
                                 "the first frame %.0f ms, the start with neither change %.0f ms" % (first, old))
        for run in profiled:
            self.assertLess(run["main"], run["window made"])
            self.assertLess(run["built"], run["first frame"])

    def test_the_windows_first_font_waits_for_no_font_collection(self):
        """Fails with WarmFonts doing nothing: the collection is built on the window's thread, in its first font."""
        waits = [run["font"] - run["window made"] for run in self.runs["warm"]]
        wait = statistics.median(waits)
        self.assertLessEqual(wait, FONT_WAIT_BUDGET_MS, "the window's first font took %.0f ms: %s"
                             % (wait, [round(each) for each in waits]))

    def test_the_start_is_written_down_and_started_from(self):
        """Fails with StartProfile doing nothing: no profile in config\\ after the first start that opened."""
        self.assertTrue(self.profile_after_first, "no profile of the start in the installation's config\\")


if __name__ == "__main__":
    unittest.main()
