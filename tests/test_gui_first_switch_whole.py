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
        self.assertLess(show.index("if (paused) Redraw(pageHost, true);"), show.index("if (paused) PaintNow(this);"))
        self.assertLess(show.index("if (paused) PaintNow(this);"), show.index('if (name == "diagnostics") LoadCompatibility();'))
        paint = guiscan.member_body("SettingsForm", "PaintNow")
        self.assertIn("RDW_UPDATENOW | RDW_ALLCHILDREN", paint)

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

            // The press, as a person's: built in it, and painted whole before it returns.
            var clock = System.Diagnostics.Stopwatch.StartNew();
            form.navButtons["diagnostics"].PerformClick();
            said["press_ms"] = clock.Elapsed.TotalMilliseconds;
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

    def test_the_card_written_on_screen_lays_its_page_out_once_and_is_painted(self):
        self.assertTrue(self.answer["view"], "the compatibility card had an answer to write")
        self.assertNotEqual(self.answer["card_text"], "unknown")
        # Once let go, and once more as the page settles its scrolling measure (SoftPage.Settle); written line by line, 8-30.
        self.assertLessEqual(self.answer["card_layouts"], 2, "the page laid out once, not once for each line written")
        self.assertEqual(self.answer["waiting_after_card"], [], "the page and the page host under it painted whole")


if __name__ == "__main__":
    unittest.main()
