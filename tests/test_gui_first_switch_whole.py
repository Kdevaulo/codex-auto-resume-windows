r"""The first switch to Diagnostics shows the page whole, never half of it over the page before (v0.6.24-beta.2).

M-CORNER re-check 8 (2026-11-17, odd item 1, recorded by desktop duplication at 150 %): a press on Diagnostics in a fresh
window changed nothing but the tab for about 1.5 s, then for 3 s or more showed the top of Diagnostics' status card over
the Overview, the Overview's Start watcher cut in half and grey bars.

The cause, measured on the real window off the screen (v0.6.23, v0.6.24-beta and beta.2 alike): a page pressed before
it is made ready is built and shown in the press, and asks to be painted - and a paint is the last thing a window's thread
takes, after every answer queued for it. The compatibility card's first answer then wrote the page on screen line by
line, each line laying the whole page out again: one message of 0.7-1.5 s (ShowCompatibility, SetLines, ShowParts), with
the page painted a control at a time on either side of it.

Now (gui/Dashboard.cs, gui/DashboardCompat.cs):
* the page a tab shows is painted whole, with its tab, before the press returns (ShowPage, PaintNow);
* the compatibility card written into Diagnostics on screen is written as ShowPage shows a page: its painting paused,
  everything in it that lays others out held, let go innermost first, the page laid out once and painted whole
  (ShowCompatibility, CompatPageOnScreen).

The live probe: the real window, standard edition, shown 30000 px off the desktop and never activated, answered from the
pictures' pinned scratch installation with 40 ms a read, its idle turns never raised - so no page is made ready ahead and
Diagnostics is built by the press, as in a fresh window. It counts the window's controls that still wait to be painted
when the press returns, and the layouts of the page and what still waits to be painted when the card's answer is written
into the page on screen. GUI test module (it shows a window, off the screen): run on its own, through gui_lock.sh.

v0.6.24-beta.3 (M-CORNER re-check 10, item 3): the page was whole 27-282 ms after the press, but 1-2 frames (15-85 ms) in
every fresh window showed Diagnostics' Status or Tools card over the Overview's cards: the press painted the page a
control at a time straight onto the window's surface, and the screen was composed between two of them. Now the page host
and everything in it is painted offscreen and put on the surface in one go (PaintAtOnce: WS_EX_COMPOSITED for that paint
alone). The probe reads the page host's area of the window's own surface after every paint and erase the press sends -
cloaked and moved onto a monitor for it, as a window off every monitor paints nothing onto its surface, then off again -
and no read may hold pixels of both pages: before, 76 of the press's 118 paints did in every run; now none.
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
    def test_the_page_shown_is_painted_before_the_press_returns(self):
        show = guiscan.member_body("SettingsForm", "ShowPage")
        self.assertLess(show.index("if (paused) Redraw(pageHost, true);"), show.index("if (paused) PaintAtOnce(pageHost);"))
        self.assertLess(show.index("if (paused) PaintAtOnce(pageHost);"), show.index('if (name == "diagnostics") LoadCompatibility();'))
        paint = guiscan.member_body("SettingsForm", "PaintNow")
        self.assertIn("RDW_UPDATENOW | RDW_ALLCHILDREN", paint)
        # v0.6.24-beta.3: the page host painted offscreen and put on the surface in one go, for that paint only.
        at_once = guiscan.member_body("SettingsForm", "PaintAtOnce")
        self.assertLess(at_once.index("style | WS_EX_COMPOSITED"), at_once.index("try { PaintNow(this); }"))
        self.assertLess(at_once.index("try { PaintNow(this); }"), at_once.index("new IntPtr(style)"))

    def test_the_card_on_screen_is_written_with_its_page_held(self):
        show = guiscan.member_body("SettingsForm", "ShowCompatibility")
        self.assertLess(show.index("Control page = CompatPageOnScreen();"), show.index("WriteCompatibility();"))
        self.assertLess(show.index("bool paused = page != null && Redraw(page, false);"), show.index("WriteCompatibility();"))
        self.assertLess(show.index("inner = HoldWithin(page);"), show.index("WriteCompatibility();"))
        self.assertLess(show.index("WriteCompatibility();"), show.index("if (written) LetGoWithin(inner);"))
        self.assertLess(show.index("if (written) LetGoWithin(inner);"), show.index("page.ResumeLayout(written);"))
        self.assertLess(show.index("if (paused) Redraw(page, true);"), show.index("if (paused) PaintNow(this);"))
        on_screen = guiscan.member_body("SettingsForm", "CompatPageOnScreen")
        self.assertIn('if (currentPage != "diagnostics"', on_screen)
        self.assertIn("Soft.OwnVisible(page)", on_screen)


PROBE = r"""
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class FirstSwitchProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            try { return SettingsForm.FirstSwitchRun(argv[0], argv[1]); }
            catch (Exception e) { File.WriteAllText(argv[1], "{\"error\":" + Json.Write(e.ToString()) + "}"); return 3; }
        }
    }

    internal sealed partial class SettingsForm
    {
        [DllImport("user32.dll", EntryPoint = "ShowWindow")] private static extern bool SwitchShowWindow(IntPtr h, int command);
        [DllImport("user32.dll", EntryPoint = "GetUpdateRect")] private static extern bool SwitchUpdateRect(IntPtr h, out SwitchRect rect, bool erase);
        [StructLayout(LayoutKind.Sequential)] private struct SwitchRect { public int Left, Top, Right, Bottom; }
        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] private static extern IntPtr SwitchGetLong(IntPtr h, int index);
        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] private static extern IntPtr SwitchSetLong(IntPtr h, int index, IntPtr value);


        // v0.6.24-beta.3: what the window's surface holds after each paint of the press, read from the window itself (its
        // device context, which reads the surface Windows composes the screen from, off the screen as on it).
        private delegate IntPtr SwitchHookProc(int code, IntPtr w, IntPtr l);
        [DllImport("user32.dll", EntryPoint = "SetWindowsHookExW")] private static extern IntPtr SwitchSetHook(int id, SwitchHookProc proc, IntPtr module, uint thread);
        [DllImport("user32.dll", EntryPoint = "UnhookWindowsHookEx")] private static extern bool SwitchUnhook(IntPtr hook);
        [DllImport("user32.dll", EntryPoint = "CallNextHookEx")] private static extern IntPtr SwitchNextHook(IntPtr hook, int code, IntPtr w, IntPtr l);
        [DllImport("kernel32.dll", EntryPoint = "GetCurrentThreadId")] private static extern uint SwitchThreadId();
        [DllImport("user32.dll", EntryPoint = "GetDCEx")] private static extern IntPtr SwitchGetDC(IntPtr h, IntPtr region, int flags);
        [DllImport("user32.dll", EntryPoint = "ReleaseDC")] private static extern int SwitchReleaseDC(IntPtr h, IntPtr dc);
        [DllImport("gdi32.dll", EntryPoint = "BitBlt")] private static extern bool SwitchBlt(IntPtr d, int x, int y, int w, int h, IntPtr s, int sx, int sy, int rop);
        [StructLayout(LayoutKind.Sequential)] private struct SwitchSent { public IntPtr Result, LParam, WParam; public uint Message; public IntPtr Window; }
        [DllImport("dwmapi.dll", EntryPoint = "DwmSetWindowAttribute")] private static extern int SwitchCloak(IntPtr h, int attribute, ref int value, int size);
        [DllImport("user32.dll", EntryPoint = "SetWindowPos")] private static extern bool SwitchPlace(IntPtr h, IntPtr after, int x, int y, int cx, int cy, int flags);

        // Off every monitor a window paints nothing onto its surface, so the press is read on one, cloaked all the while:
        // DWM shows none of it, and it is painted there as it would be on the screen.
        private static void SwitchMove(SettingsForm form, Point to)
        {
            SwitchPlace(form.Handle, IntPtr.Zero, to.X, to.Y, 0, 0, 0x0001 | 0x0004 | 0x0010);   // NOSIZE NOZORDER NOACTIVATE
            SwitchPump(5000, delegate
            {
                var waiting = new List<object>();
                SwitchWaiting(form, waiting);
                SwitchRect box;
                return waiting.Count == 0 && !SwitchUpdateRect(form.Handle, out box, false);
            });
        }

        private const int SwitchStride = 3;

        // The page host's area of the window's surface, every third pixel each way.
        private static int[] SwitchShot(Control form, Rectangle area)
        {
            using (var bitmap = new Bitmap(area.Width, area.Height, PixelFormat.Format32bppRgb))
            {
                using (Graphics graphics = Graphics.FromImage(bitmap))
                {
                    IntPtr into = graphics.GetHdc();
                    IntPtr from = SwitchGetDC(form.Handle, IntPtr.Zero, 0x2);          // DCX_CACHE: the children not clipped
                    SwitchBlt(into, 0, 0, area.Width, area.Height, from, area.X, area.Y, 0x00CC0020);
                    SwitchReleaseDC(form.Handle, from);
                    graphics.ReleaseHdc(into);
                }
                BitmapData data = bitmap.LockBits(new Rectangle(Point.Empty, bitmap.Size), ImageLockMode.ReadOnly, PixelFormat.Format32bppRgb);
                try
                {
                    int across = (area.Width + SwitchStride - 1) / SwitchStride, down = (area.Height + SwitchStride - 1) / SwitchStride;
                    var shot = new int[across * down];
                    for (int y = 0, i = 0; y < area.Height; y += SwitchStride)
                        for (int x = 0; x < area.Width; x += SwitchStride, i++)
                            shot[i] = Marshal.ReadInt32(data.Scan0, y * data.Stride + x * 4) & 0xFFFFFF;
                    return shot;
                }
                finally { bitmap.UnlockBits(data); }
            }
        }

        // Each paint's surface against the page before and the page whole: how many of the pixels the two differ in are
        // still the page before's, and how many already the page whole's.
        private static List<object> SwitchMixes(int[] before, int[] whole, List<int[]> shots, List<string> painted)
        {
            var mixes = new List<object>();
            int differ = 0;
            for (int i = 0; i < before.Length; i++) if (before[i] != whole[i]) differ++;
            for (int s = 0; s < shots.Count; s++)
            {
                int old = 0, fresh = 0;
                int[] shot = shots[s];
                for (int i = 0; i < before.Length; i++)
                {
                    if (before[i] == whole[i]) continue;
                    if (shot[i] == before[i]) old++;
                    else if (shot[i] == whole[i]) fresh++;
                }
                var mix = new Dictionary<string, object>();
                mix["painted"] = painted[s];
                mix["differ"] = (double)differ;
                mix["before"] = (double)old;
                mix["whole"] = (double)fresh;
                mixes.Add(mix);
            }
            return mixes;
        }

        // Messages handled, never an idle turn raised: nothing is made ready ahead.
        private static void SwitchPump(int ms, Func<bool> until)
        {
            var all = System.Diagnostics.Stopwatch.StartNew();
            while (all.ElapsedMilliseconds < ms)
            {
                Application.DoEvents();
                if (until != null && until()) return;
                Thread.Sleep(5);
            }
        }

        // The window's controls on screen that still wait to be painted, by type.
        private static void SwitchWaiting(Control parent, List<object> into)
        {
            foreach (Control child in parent.Controls)
            {
                if (!child.Visible || !child.IsHandleCreated) continue;
                SwitchRect box;
                if (SwitchUpdateRect(child.Handle, out box, false))
                    into.Add(child.GetType().Name + " " + child.Name + " in " + (child.Parent == null ? "-" : child.Parent.GetType().Name) +
                             " " + (box.Right - box.Left) + "x" + (box.Bottom - box.Top) + " of " + child.Width + "x" + child.Height);
                SwitchWaiting(child, into);
            }
        }

        internal static int FirstSwitchRun(string answersPath, string outPath)
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
            string nowhere = Path.Combine(Path.GetTempPath(), "car-first-switch-nowhere");
            var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), RenderAnswer("strings", null), null);
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(-30000, -30000);
            form.placedBounds = Rectangle.Empty;
            IntPtr h = form.Handle;
            // No taskbar button, never activated.
            SwitchSetLong(h, -20, (IntPtr)(SwitchGetLong(h, -20).ToInt64() | 0x80 | 0x08000000));
            form.OnLoad(EventArgs.Empty);
            SwitchShowWindow(h, 4);
            form.OnShown(EventArgs.Empty);
            form.placedBounds = Rectangle.Empty;
            SwitchPump(20000, delegate { return form.snapshot != null && form.settingsRead && form.bridge.InFlight == 0; });
            var said = new Dictionary<string, object>();
            said["prepared"] = new List<object>(form.preparedPages.ToArray());
            said["built_before"] = form.pages.ContainsKey("diagnostics");

            // The press, as a person's: built in it, and painted whole before it returns - the window's surface read after
            // every paint sent to it on the way.
            int cloak = 1;
            said["cloaked"] = SwitchCloak(h, 13, ref cloak, 4) == 0;                  // DWMWA_CLOAK
            if ((bool)said["cloaked"]) SwitchMove(form, Screen.PrimaryScreen.WorkingArea.Location);
            Rectangle area = new Rectangle(form.PointToClient(form.pageHost.PointToScreen(Point.Empty)), form.pageHost.Size);
            int[] before = SwitchShot(form, area);
            var shots = new List<int[]>();
            var painted = new List<string>();
            var reading = new System.Diagnostics.Stopwatch();
            SwitchHookProc hook = delegate(int code, IntPtr w, IntPtr l)
            {
                if (code >= 0)
                {
                    var sent = (SwitchSent)Marshal.PtrToStructure(l, typeof(SwitchSent));
                    if (sent.Message == 0x000F || sent.Message == 0x0014)          // WM_PAINT, WM_ERASEBKGND
                    {
                        Control control = Control.FromHandle(sent.Window);
                        if (control != null && (control == form || form.Contains(control)))
                        {
                            reading.Start();
                            shots.Add(SwitchShot(form, area));
                            reading.Stop();
                            painted.Add((sent.Message == 0x000F ? "paint " : "erase ") + control.GetType().Name + " " + control.Name);
                        }
                    }
                }
                return SwitchNextHook(IntPtr.Zero, code, w, l);
            };
            IntPtr hooked = SwitchSetHook(12, hook, IntPtr.Zero, SwitchThreadId());   // WH_CALLWNDPROCRET
            var clock = System.Diagnostics.Stopwatch.StartNew();
            try { form.navButtons["diagnostics"].PerformClick(); }
            finally { SwitchUnhook(hooked); }
            // The press itself, without the reads of its surface.
            said["press_ms"] = clock.Elapsed.TotalMilliseconds - reading.Elapsed.TotalMilliseconds;
            said["hooked"] = hooked != IntPtr.Zero;

            said["press_paints"] = SwitchMixes(before, SwitchShot(form, area), shots, painted);
            GC.KeepAlive(hook);
            SwitchMove(form, new Point(-30000, -30000));
            said["shown"] = form.currentPage;
            var waiting = new List<object>();
            SwitchWaiting(form, waiting);
            said["waiting_after_press"] = waiting;

            // Its reads answered: the compatibility card's answer is written into the page on screen.
            SwitchPump(20000, delegate { return !form.loadingCompat && form.bridge.InFlight == 0 && !form.refreshing; });
            SwitchPump(300, null);
            Control page = form.pages["diagnostics"];
            int layouts = 0;
            page.Layout += delegate { layouts++; };
            Dictionary<string, object> view = form.compatView;
            said["view"] = view != null;
            // The first answer after a failed read, as the first answer after a first switch: every line of the card changes.
            form.compatView = null;
            form.compatLive = null;
            form.compatUnreadable = true;
            form.ShowCompatibility();
            SwitchPump(200, null);
            layouts = 0;
            clock.Restart();
            if (view != null) form.ApplyCompatibility(view, false);
            said["card_ms"] = clock.Elapsed.TotalMilliseconds;
            said["card_layouts"] = (double)layouts;
            waiting = new List<object>();
            SwitchWaiting(form, waiting);
            said["waiting_after_card"] = waiting;
            said["card_text"] = form.compatOverall.Text;
            form.Close();
            form.Dispose();
            File.WriteAllText(outPath, Json.Write(said), new UTF8Encoding(false));
            return 0;
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class FirstSwitchTests(unittest.TestCase):
    """The real window, off the screen: Diagnostics pressed before it is made ready."""

    @classmethod
    def setUpClass(cls):
        import advanced_shots
        cls.folder = tempfile.TemporaryDirectory(prefix="car-first-switch-")
        work = Path(cls.folder.name)
        read, _envelope = advanced_shots.read_answers("standard", "base", "en")
        answers = work / "answers.json"
        answers.write_text(json.dumps(advanced_shots.form_answers(read), ensure_ascii=False), encoding="utf-8")
        probe = work / "FirstSwitchProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "FirstSwitch.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.FirstSwitchProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
            done = subprocess.run([str(exe), str(answers), str(out)], capture_output=True, timeout=300,
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

    def test_diagnostics_was_built_by_the_press(self):
        self.assertNotIn("diagnostics", self.answer["prepared"])
        self.assertFalse(self.answer["built_before"])
        self.assertEqual(self.answer["shown"], "diagnostics")

    def test_nothing_waits_to_be_painted_when_the_press_returns(self):
        self.assertEqual(self.answer["waiting_after_press"], [],
                         "the page shown and its tab painted whole in the press, before any answer queued meanwhile")

    def test_no_paint_of_the_press_shows_both_pages(self):
        # v0.6.24-beta.3 (M-CORNER re-check 10, item 3): the surface after each paint the press sent, in the page host's
        # area. A paint that leaves some of the Overview's pixels there and puts some of Diagnostics' beside them is a frame
        # a person can be shown mixing the two pages (1-2 frames, 15-85 ms, in every fresh window of the re-check).
        self.assertTrue(self.answer["hooked"])
        self.assertTrue(self.answer["cloaked"], "the press read on a monitor, cloaked")
        paints = self.answer["press_paints"]
        self.assertTrue(paints, "the press painted the page")
        differ = paints[0]["differ"]
        self.assertGreater(differ, 1000, "the two pages differ on the surface read")
        mixed = [paint for paint in paints
                 if paint["before"] >= differ * 0.02 and paint["whole"] >= differ * 0.02]
        self.assertEqual(mixed, [], "%d of the press's %d paints left both pages on the surface (of %d pixels that differ): %s"
                         % (len(mixed), len(paints), differ,
                            "; ".join("%s %d before %d whole" % (paint["painted"], paint["before"], paint["whole"])
                                      for paint in mixed[:8])))

    def test_the_card_written_on_screen_lays_its_page_out_once_and_is_painted(self):
        self.assertTrue(self.answer["view"], "the compatibility card had an answer to write")
        self.assertNotEqual(self.answer["card_text"], "unknown")
        # Once let go, and once more as the page settles its scrolling measure (SoftPage.Settle); written line by line, 8-30.
        self.assertLessEqual(self.answer["card_layouts"], 2, "the page laid out once, not once for each line written")
        self.assertEqual(self.answer["waiting_after_card"], [], "the page and the page host under it painted whole")


if __name__ == "__main__":
    unittest.main()
