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
        [DllImport("user32.dll", EntryPoint = "IsWindowVisible")] private static extern bool FrameVisible(IntPtr h);
        [StructLayout(LayoutKind.Sequential)] private struct RECT { public int Left, Top, Right, Bottom; }
        [DllImport("user32.dll", EntryPoint = "GetWindowRect")] private static extern bool FrameRect(IntPtr h, out RECT box);
        [DllImport("dwmapi.dll", EntryPoint = "DwmGetWindowAttribute")] private static extern int FrameDwmGet(IntPtr h, int attribute, out int value, int size);
        [DllImport("winmm.dll", EntryPoint = "timeBeginPeriod")] private static extern int FrameFineSleep(int ms);

        private static double FrameNow() { return Stopwatch.GetTimestamp() * 1000.0 / Stopwatch.Frequency; }

        /// A control's window, and when it last handled WM_PAINT.
        private sealed class FramePaints : NativeWindow
        {
            internal readonly Control Control;
            internal double FirstPaint = -1;
            internal readonly List<double> Paints = new List<double>();
            internal readonly List<double> Moves = new List<double>();
            internal readonly List<double> Made = new List<double>();
            internal double ShownAt = -1;
            internal volatile bool OnAtUncloak;
            internal FramePaints(Control control)
            {
                Control = control;
                AssignHandle(control.Handle);
                control.SizeChanged += delegate { Moves.Add(FrameNow()); };
                control.HandleCreated += delegate { Made.Add(FrameNow()); };
                // A window that comes on after the uncloak is no part of the first frame.
                control.VisibleChanged += delegate { if (Soft.OwnVisible(control)) ShownAt = FrameNow(); };
                control.LocationChanged += delegate { Moves.Add(FrameNow()); };
            }
            protected override void WndProc(ref Message m)
            {
                if (m.Msg == 0x000F) { if (FirstPaint < 0) FirstPaint = FrameNow(); if (Paints.Count < 50) Paints.Add(FrameNow()); }
                base.WndProc(ref m);
            }
        }

        private static void FrameSpy(Control control, List<FramePaints> spies)
        {
            if (control.IsHandleCreated) spies.Add(new FramePaints(control));
            foreach (Control child in control.Controls) FrameSpy(child, spies);
        }

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
            // The bridge's first answer no sooner than FRAME_BRIDGE_READY_MS after the probe started, as a real one's
            // interpreter takes its time to start.
            int ready = 0;
            int.TryParse(Environment.GetEnvironmentVariable("FRAME_BRIDGE_READY_MS") ?? "0", out ready);
            var started = Stopwatch.StartNew();
            PersistentBridge.Answers = delegate(string command, string argument)
            {
                int left = ready - (int)started.ElapsedMilliseconds;
                if (left > 0) Thread.Sleep(left);
                Thread.Sleep(20);
                return RenderAnswer(command, argument);
            };
            DialogAnswers = delegate { return false; };
            string nowhere = Path.Combine(root, "nowhere");
            var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), RenderAnswer("strings", null), null);
            // A key for the words, as a person's window has one (StringsCache.Key): the advanced edition keeps its page's
            // words under it (AdvancedWordsCache).
            form.openedKey = "first-frame-probe";
            form.StartPosition = FormStartPosition.Manual;
            // On the screen, where its paints come as a person's window's do (a window off every monitor is given none
            // until something asks), or 30000 px off it.
            bool onScreen = Environment.GetEnvironmentVariable("FRAME_ON_SCREEN") == "1";
            Rectangle area = Screen.PrimaryScreen.WorkingArea;
            form.Location = onScreen ? new Point(area.X + Math.Max(0, (area.Width - form.Width) / 2), area.Y + Math.Max(0, (area.Height - form.Height) / 2))
                                     : new Point(-30000, -30000);
            form.placedBounds = Rectangle.Empty;
            IntPtr h = form.Handle;
            // No taskbar button and never activated: shown as the setup's reopen shows it, behind the window in front
            // (OpensBehind, ShowWithoutActivation), through the form's own Show - its controls' windows made as a
            // person's start makes them.
            FrameSetLong(h, -20, (IntPtr)(FrameGetLong(h, -20).ToInt64() | 0x80 | 0x08000000));
            OpensBehind = true;
            // When the edition's own tab came on (the advanced edition's), on the window's clock.
            double tabOn = -1;
            NavButton editionTab = null;
            form.Load += delegate
            {
                NavButton found;
                if (form.navButtons.TryGetValue("advanced", out found))
                {
                    editionTab = found;
                    if (Soft.OwnVisible(editionTab)) tabOn = 0;
                    editionTab.VisibleChanged += delegate { if (tabOn < 0 && Soft.OwnVisible(editionTab)) tabOn = FrameNow(); };
                }
            };
            // The form's own window watched from before its show; every other window of the first frame from its show on,
            // each one's first WM_PAINT (FramePaints).
            var spies = new List<FramePaints>();
            var own = new FramePaints(form);
            spies.Add(own);
            double showingAt = FrameNow();
            form.Show();
            form.placedBounds = Rectangle.Empty;
            double shownAt = FrameNow();
            foreach (Control child in form.Controls) FrameSpy(child, spies);
            // When DWM let go of the window's cloak: read every millisecond on a thread of its own.
            double[] uncloakedAt = { -1 };
            FrameFineSleep(1);
            var spy = new Thread(delegate()
            {
                var until = Stopwatch.StartNew();
                while (until.ElapsedMilliseconds < 20000)
                {
                    int value;
                    if (FrameDwmGet(h, 14, out value, 4) == 0 && value == 0)
                    {
                        uncloakedAt[0] = FrameNow();
                        // Which windows were on the screen at that moment, asked of Windows from this thread.
                        foreach (FramePaints each in spies)
                        {
                            RECT box;
                            each.OnAtUncloak = FrameVisible(each.Handle) && FrameRect(each.Handle, out box) &&
                                               box.Right > box.Left && box.Bottom > box.Top;
                        }
                        return;
                    }
                    Thread.Sleep(1);
                }
            });
            spy.IsBackground = true;
            spy.Start();
            var context = new ApplicationContext();
            var end = new System.Windows.Forms.Timer();
            end.Interval = 50;
            var since = Stopwatch.StartNew();
            end.Tick += delegate
            {
                try
                {
                    if (!form.firstFrameMarked && since.ElapsedMilliseconds < 20000) return;
                    if (since.ElapsedMilliseconds < 2500) return;
                    end.Stop();
                    var said = new Dictionary<string, object>();
                    said["first_frame_marked"] = form.firstFrameMarked;
                    said["uncloaked"] = uncloakedAt[0] - shownAt;
                    said["form_first_paint"] = own.FirstPaint < 0 ? -1.0 : own.FirstPaint - shownAt;
                    // Each window on the screen at the end that had no WM_PAINT between its show and the uncloak.
                    var unpainted = new List<object>();
                    int counted = 0;
                    foreach (FramePaints each in spies)
                    {
                        Control c = each.Control;
                        // The windows of the first frame: on the screen at the uncloak, with room. The form's own
                        // window is not among them: its pages cover the whole of it (docked), so it has nothing to paint.
                        if (c == form || !each.OnAtUncloak) continue;
                        counted++;
                        if (!(each.FirstPaint > showingAt && each.FirstPaint <= uncloakedAt[0]))
                            unpainted.Add(c.GetType().Name + " '" + (c.Text ?? "") + "' " + c.Bounds + " in " + (c.Parent == null ? "-" : c.Parent.GetType().Name) +
                                          (each.FirstPaint < 0 ? " never" : " first at " + (each.FirstPaint - shownAt).ToString("0")));
                    }
                    said["windows"] = (double)counted;
                    // Every window repainted in the first 120 ms after the uncloak, or moved/resized around it: what the first
                    // frame may have shown before it was right.
                    var after = new List<object>();
                    foreach (FramePaints each in spies)
                    {
                        Control c = each.Control;
                        if (c.IsDisposed) continue;
                        string who = c.GetType().Name + " '" + c.Text + "' " + c.Bounds + " in " + (c.Parent == null ? "-" : c.Parent.GetType().Name + " " + c.Parent.Bounds);
                        foreach (double at in each.Paints)
                            if (at > uncloakedAt[0] && at < uncloakedAt[0] + 120) { after.Add("paint " + who + " +" + (at - uncloakedAt[0]).ToString("0")); break; }
                        foreach (double at in each.Made)
                            if (at > showingAt) { after.Add("handle made again " + who + " " + (at - uncloakedAt[0]).ToString("+0;-0")); break; }
                        foreach (double at in each.Moves)
                            if (at > uncloakedAt[0] - 300 && at < uncloakedAt[0] + 120) { after.Add("move " + c.GetType().Name + " '" + c.Text + "' " + (at - uncloakedAt[0]).ToString("+0;-0")); break; }
                    }
                    said["around_uncloak"] = after;
                    // The windows painted last before the uncloak, latest first.
                    var order = new List<FramePaints>(spies);
                    order.RemoveAll(each => each.FirstPaint < 0 || each.FirstPaint > uncloakedAt[0]);
                    order.Sort((x, y) => y.FirstPaint.CompareTo(x.FirstPaint));
                    var last = new List<object>();
                    for (int i = 0; i < Math.Min(6, order.Count); i++)
                        last.Add(order[i].Control.GetType().Name + " '" + order[i].Control.Text + "' " + (order[i].FirstPaint - uncloakedAt[0]).ToString("0.0"));
                    said["painted_last"] = last;
                    said["unpainted"] = unpainted;
                    said["edition_tab"] = editionTab == null ? "none" : tabOn >= 0 && tabOn <= uncloakedAt[0] ? "in the first frame" : "after the first frame";
                    said["edition_tab_late"] = tabOn < 0 ? -1.0 : tabOn - uncloakedAt[0];
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


def advanced_sources() -> list:
    """The advanced edition's own window sources, compiled after the standard ones (advanced/gui/window.sources)."""
    found = []
    for line in (ROOT / "advanced" / "gui" / "window.sources").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("["):
            found.append(ROOT / line)
    return found


class Sitting:
    """A probe of one edition built in a folder of its own, and the starts of one sitting: each start's marks and what
    the probe saw of its first frame, by mode ("warm": both changes; "cold": neither)."""

    def __init__(self, edition: str, sequence: tuple, bridge_ready_ms: int = 0, on_screen: bool = False):
        import advanced_shots
        self.folder = tempfile.TemporaryDirectory(prefix="car-first-frame-")
        work = Path(self.folder.name)
        read, _envelope = advanced_shots.read_answers(edition, "base", "en")
        answers = work / "answers.json"
        answers.write_text(json.dumps(advanced_shots.form_answers(read), ensure_ascii=False), encoding="utf-8")
        probe = work / "FirstFrameProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "FirstFrame.exe"
        sources = [*guiscan.sources(), *(advanced_sources() if edition == "advanced" else [])]
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/optimize+", "/out:" + str(exe),
                                "/main:CodexAutoResume.FirstFrameProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in sources], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        self.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        self.root = work / "install"
        (self.root / "config").mkdir(parents=True)
        # The window's own installation is the probe's folder (AppDomain's base): its config\ holds what it keeps.
        (work / "config").mkdir()
        self.kept = work / "config" / "advanced-words-cache.json"
        self.profile = self.root / "config" / "window-start.jit"
        self.runs = {"warm": [], "cold": []}
        self.frames = {"warm": [], "cold": []}
        self.profile_after_first = None
        if self.failure is not None:
            return
        for i, mode in enumerate(sequence):
            out = work / ("out-%d.json" % i)
            marked = work / ("marks-%d.txt" % i)
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"),
                               CODEX_AR_START_MARKS=str(marked), FRAME_BRIDGE_READY_MS=str(bridge_ready_ms),
                               FRAME_ON_SCREEN="1" if on_screen else "0")
            environment.pop("CODEX_AR_STILL_READY", None)
            environment.pop("CODEX_AR_EDITION", None)
            done = subprocess.run([str(exe), mode, str(self.root), str(answers), str(out)], capture_output=True,
                                  timeout=120, creationflags=NO_WINDOW, env=environment, cwd=str(work))
            said = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
            if done.returncode != 0 or "error" in said or not said.get("first_frame_marked") or not marked.is_file():
                self.failure = "the probe failed (exit %d): %s" % (done.returncode, json.dumps(said)[:2000])
                return
            self.runs[mode].append(marks(marked.read_text(encoding="utf-8")))
            self.frames[mode].append(said)
            if mode == "warm" and self.profile_after_first is None:
                self.profile_after_first = self.profile.is_file() and self.profile.stat().st_size > 0
        for mode in ("warm", "cold"):
            for run, said in zip(self.runs[mode], self.frames[mode]):
                print(edition, mode, {step: round(at) for step, at in run.items()},
                      {key: said.get(key) for key in ("uncloaked", "form_first_paint", "around_uncloak", "painted_last", "windows", "unpainted", "edition_tab", "edition_tab_late")},
                      file=sys.stderr)


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class FirstFrameTests(unittest.TestCase):
    """Processes of the real window, off the screen: when its first frame came, and what it waited for before."""

    @classmethod
    def setUpClass(cls):
        # The start with neither change three times, between the new start's four: the first of those writes the
        # profile down, the three after it start from it (a start with neither change writes none and reads none).
        cls.sitting = Sitting("standard", ("cold", "warm", "cold", "warm", "cold", "warm", "warm"))
        cls.failure, cls.runs, cls.frames = cls.sitting.failure, cls.sitting.runs, cls.sitting.frames
        cls.profile_after_first = cls.sitting.profile_after_first

    @classmethod
    def tearDownClass(cls):
        cls.sitting.folder.cleanup()

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


def advanced_lane() -> bool:
    """Whether the advanced edition's package is on the path: its pinned answers are read from it."""
    try:
        import codex_auto_resume_advanced  # noqa: F401
    except ImportError:
        return False
    return True


# The bridge's first answer in the probes below: 2000 ms after the start, as the live re-check 4 (M2) saw a real start's
# - its first frame 1.47-1.50 s after the process was created, the Advanced features tab 0.24-0.55 s after that, and the
# state at 3.9 s. A bridge that answered at once would hide what comes before its first answer.
BRIDGE_READY_MS = 2000


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class WholeFirstFrameTests(unittest.TestCase):
    """The real window shown on the screen (never activated, under the GUI lock): what had painted when it was uncovered.

    The live re-check 4 (M2): in 3 starts of 5 the first frame on the screen had the header card's light, headline and line
    as a black strip, whole 37-64 ms later. Measured with this probe, every window of the first frame had had its WM_PAINT
    before the uncloak, and those three were the last painted, 1.7-5 ms before it: their drawing was still in GDI's batch
    when the cloak was let go. A screen cannot be photographed here (no capture), so the probe holds what can be seen from
    the window's side - every window painted before it is uncovered - and the source holds the flush between the two."""

    @classmethod
    def setUpClass(cls):
        cls.sitting = Sitting("standard", ("warm", "warm", "warm"), bridge_ready_ms=BRIDGE_READY_MS, on_screen=True)
        cls.failure, cls.frames = cls.sitting.failure, cls.sitting.frames

    @classmethod
    def tearDownClass(cls):
        cls.sitting.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_every_window_of_the_first_frame_has_painted_when_it_is_uncovered(self):
        for i, said in enumerate(self.frames["warm"]):
            with self.subTest(run=i):
                self.assertGreater(said["windows"], 20, "the probe found the first frame's windows")
                self.assertEqual(said["unpainted"], [], "uncovered before these had painted")

    def test_the_header_card_is_among_the_windows_painted_before_it_is_uncovered(self):
        """What the live re-check saw unpainted: the light, the headline and the line - painted, and then handed on."""
        for i, said in enumerate(self.frames["warm"]):
            with self.subTest(run=i):
                last = " ".join(said["painted_last"])
                for header in ("HaloDot", "Label ", "AsideLabel"):
                    self.assertIn(header, last)

    def test_what_was_painted_reaches_the_screen_before_the_cloak_is_let_go(self):
        """Fails with the flush taken back: GdiFlush, then DwmFlush, between the paint and the uncloak."""
        painted = guiscan.member_body("WindowCorner", "Painted")
        redraw = painted.index("RedrawWindow(handle, IntPtr.Zero, IntPtr.Zero, PaintAllNow);")
        gdi = painted.index("GdiFlush();")
        dwm = painted.index("DwmFlush();")
        uncloak = painted.index("DwmSetWindowAttribute(handle, Cloaking, ref off, 4);")
        self.assertLess(redraw, gdi)
        self.assertLess(gdi, dwm)
        self.assertLess(dwm, uncloak)


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
@unittest.skipUnless(advanced_lane(), "the advanced lane: its window's answers are read from its package")
class AdvancedFirstFrameTests(unittest.TestCase):
    """The advanced edition's window, off the screen, with a bridge that answers as a real one does: its tab row.

    The live re-check 4 (M2): in 4 starts of 5 the first frame's tab row ended at Settings, and Advanced features joined it
    0.24-0.55 s later - the tab waited for advanced-words, which comes with the bridge's first answers, and the first frame
    now comes before those. The first start here keeps the words it is answered (AdvancedWordsCache); the starts after it
    show the tab in their first frame."""

    @classmethod
    def setUpClass(cls):
        cls.sitting = Sitting("advanced", ("warm", "warm", "warm"), bridge_ready_ms=BRIDGE_READY_MS)
        cls.failure, cls.frames = cls.sitting.failure, cls.sitting.frames
        cls.kept = cls.sitting.kept.is_file()

    @classmethod
    def tearDownClass(cls):
        cls.sitting.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_the_first_start_comes_before_the_words_and_keeps_them(self):
        first = self.frames["warm"][0]
        self.assertEqual(first["edition_tab"], "after the first frame", "a start with nothing kept waits for the answer")
        self.assertTrue(self.kept, "the words answered were kept in config\\")

    def test_the_advanced_features_tab_is_in_the_first_frame(self):
        """Fails with the kept words taken back: the tab then joined the row 0.7-1.3 s after the first frame here."""
        for i, said in enumerate(self.frames["warm"][1:]):
            with self.subTest(run=i + 1):
                self.assertEqual(said["edition_tab"], "in the first frame",
                                 "%.0f ms after the first frame" % said["edition_tab_late"])


if __name__ == "__main__":
    unittest.main()
