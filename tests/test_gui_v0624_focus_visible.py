r"""v0.6.24: focus rings for the keyboard only - none after the mouse (the owner, 2026-11-16).

The owner's screenshot of the v0.6.24-beta Dashboard: a page tab clicked with the mouse kept its blue keyboard ring. Every
control draws its ring only as `Focused && ShowFocusCues`, which follows the window's UISF_HIDEFOCUS; Windows and WinForms
clear that on keyboard input (Tab, Alt, F10) and nothing set it again, so after any keyboard use a click left a ring.
FocusCues (gui/SoftChrome.cs), one message filter for every window with the chrome and every SoftDialog, now:

- sets UISF_HIDEFOCUS on the window again at a mouse press anywhere in it - a tab, a page, a popup it owns - before the
  press reaches the control, so the control it focuses has no ring and neither has any other;
- clears it at a key after which the focus stands on another control of the window: Tab as before, and the arrows along
  the page tabs, which moved the focus with no ring at all;
- leaves it alone at a key that moves no focus.

One probe compiled with the window: the real Dashboard (SettingsForm) and a SoftDialog, each shown 30000 px off the desktop
and never activated by the probe, driven by real messages posted to the controls and handed out by the thread's own
message loop (the mouse press and key reach the filter as Windows' input does). Nothing is captured; the ring is read
from the tab drawn into a bitmap.

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

PROBE = r"""
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class CueNative
    {
        [DllImport("user32.dll")] internal static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr w, IntPtr l);
        [DllImport("user32.dll")] internal static extern bool PostMessage(IntPtr h, int msg, IntPtr w, IntPtr l);
        [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr h, int command);
        [DllImport("user32.dll")] internal static extern IntPtr GetFocus();
        internal const int Away = -30000;
        internal const int WM_KEYDOWN = 0x0100, WM_KEYUP = 0x0101, WM_LBUTTONDOWN = 0x0201, WM_LBUTTONUP = 0x0202,
                           WM_RBUTTONDOWN = 0x0204, WM_RBUTTONUP = 0x0205;
        internal const int VK_TAB = 0x09, VK_SHIFT = 0x10, VK_RIGHT = 0x27;

        internal static void Pump()
        {
            for (int i = 0; i < 6; i++) { Application.DoEvents(); Thread.Sleep(5); }
        }

        // A press and its release in the middle of `c`, as the mouse's come: posted, handed out by the message loop.
        internal static void Press(Control c, bool right)
        {
            int at = ((c.Height / 2) << 16) | (c.Width / 2 & 0xFFFF);
            PostMessage(c.Handle, right ? WM_RBUTTONDOWN : WM_LBUTTONDOWN, new IntPtr(right ? 2 : 1), new IntPtr(at));
            PostMessage(c.Handle, right ? WM_RBUTTONUP : WM_LBUTTONUP, IntPtr.Zero, new IntPtr(at));
            Pump();
        }

        // A key down and up at the control with the focus, as the keyboard's come.
        internal static void Key(int key, int scan, bool extended)
        {
            IntPtr to = GetFocus();
            int down = 1 | (scan << 16) | (extended ? 1 << 24 : 0);
            PostMessage(to, WM_KEYDOWN, new IntPtr(key), new IntPtr(down));
            PostMessage(to, WM_KEYUP, new IntPtr(key), new IntPtr(unchecked((int)(down | 0xC0000000))));
            Pump();
        }

        internal static void Clear(Form form)
        {
            // As Windows sends it after keyboard input: WM_CHANGEUISTATE, UIS_CLEAR, UISF_HIDEFOCUS.
            SendMessage(form.Handle, 0x0127, new IntPtr(2 | (1 << 16)), IntPtr.Zero);
            Pump();
        }

        internal static bool Cues(Control c)
        {
            PropertyInfo cues = typeof(Control).GetProperty("ShowFocusCues", BindingFlags.Instance | BindingFlags.NonPublic);
            return (bool)cues.GetValue(c, null);
        }

        // UISF_HIDEFOCUS as Windows holds it for the window (WM_QUERYUISTATE).
        internal static bool Hidden(Form form)
        {
            return (SendMessage(form.Handle, 0x0129, IntPtr.Zero, IntPtr.Zero).ToInt64() & 1) != 0;
        }

        internal static Dictionary<string, object> State(Form form)
        {
            Control focused = Control.FromChildHandle(GetFocus());
            var said = new Dictionary<string, object> {
                { "hidden", Hidden(form) },
                { "focusedIn", focused != null && focused.FindForm() == form },
                { "focusedType", focused == null ? "" : focused.GetType().Name },
                { "focusedText", focused == null ? "" : focused.Text ?? "" },
                { "cues", focused != null && Cues(focused) } };
            var tab = focused as NavButton;
            if (tab != null) said["ring"] = (double)Ring(tab);
            return said;
        }

        // How many of the tab's pixels outside its body are the focus ring's colour: the ring is drawn there and nothing else.
        internal static int Ring(NavButton tab)
        {
            using (var bitmap = new Bitmap(tab.Width, tab.Height))
            {
                tab.DrawToBitmap(bitmap, new Rectangle(Point.Empty, tab.Size));
                Rectangle face = tab.Face;
                Color ring = Palette.Focus;
                int count = 0;
                for (int y = 0; y < bitmap.Height; y++)
                    for (int x = 0; x < bitmap.Width; x++)
                    {
                        if (face.Contains(x, y)) continue;
                        Color c = bitmap.GetPixel(x, y);
                        if (Math.Abs(c.R - ring.R) + Math.Abs(c.G - ring.G) + Math.Abs(c.B - ring.B) <= 24) count++;
                    }
                return count;
            }
        }
    }

    internal static class FocusVisibleProbe
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
                said["dashboard"] = SettingsForm.FocusVisibleDashboard(argv[1]);
                said["dialog"] = Dialog();
            }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }

        static Dictionary<string, object> Dialog()
        {
            var said = new Dictionary<string, object>();
            var dialog = new SoftDialog();
            dialog.Text = "A dialog";
            Soft.DialogBar(dialog);
            dialog.StartPosition = FormStartPosition.Manual;
            dialog.Location = new Point(CueNative.Away, CueNative.Away);
            dialog.ShowInTaskbar = false;
            dialog.ClientSize = new Size(360, 160);
            var first = new Button { Text = "First", Bounds = new Rectangle(16, 16, 120, 32) };
            var second = new Button { Text = "Second", Bounds = new Rectangle(160, 16, 120, 32) };
            dialog.Controls.Add(first);
            dialog.Controls.Add(second);
            IntPtr h = dialog.Handle;
            CueNative.ShowWindow(h, 4);   // SW_SHOWNOACTIVATE
            CueNative.Pump();
            said["titled"] = dialog.CaptionHost != null;
            first.Focus();
            CueNative.Clear(dialog);
            said["cleared"] = CueNative.State(dialog);
            CueNative.Press(second, false);
            said["clicked"] = CueNative.State(dialog);
            said["clickedSecond"] = second.Focused;
            said["firstAfterClick"] = CueNative.Cues(first);
            CueNative.Key(CueNative.VK_TAB, 0x0F, false);
            said["tabbed"] = CueNative.State(dialog);
            dialog.Close();
            dialog.Dispose();
            return said;
        }
    }

    internal sealed partial class SettingsForm
    {
        internal static Dictionary<string, object> FocusVisibleDashboard(string dir)
        {
            var said = new Dictionary<string, object>();
            var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-en.json"), Encoding.UTF8)) as Dictionary<string, object>;
            string nowhere = Path.Combine(dir, "nowhere");
            var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, null);
            form.auditing = true;
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(CueNative.Away, CueNative.Away);
            form.ShowInTaskbar = false;
            IntPtr h = form.Handle;
            CueNative.ShowWindow(h, 4);   // SW_SHOWNOACTIVATE: never made the foreground window
            CueNative.Pump();
            NavButton first = form.navButtons[PageOrder[0]], second = form.navButtons[PageOrder[1]];
            said["pages"] = new List<object> { PageOrder[0], PageOrder[1], PageOrder[2] };
            // Every page clicked below is made first, as the window makes them ready ahead: a control made and drawn for the
            // first time asks WinForms for its cues, which sets UISF_HIDEFOCUS on its window by itself (Control.ShowFocusCues)
            // - a page built by the click would hide the ring with or without FocusCues.
            for (int i = 2; i >= 0; i--)
            {
                form.ShowPage(PageOrder[i]);
                form.PerformLayout();
                CueNative.Pump();
            }

            // The owner's case: the keyboard was used once (Windows cleared the bit), then the mouse.
            first.Focus();
            CueNative.Clear(form);
            said["cleared"] = CueNative.State(form);
            CueNative.Press(second, false);
            said["clicked"] = CueNative.State(form);
            said["clickedPage"] = form.currentPage;
            said["clickedSecond"] = second.Focused;
            said["otherTabCues"] = CueNative.Cues(first);

            // A key that moves no focus leaves them hidden.
            CueNative.Key(CueNative.VK_SHIFT, 0x2A, false);
            said["shift"] = CueNative.State(form);

            // Tab shows them again.
            CueNative.Key(CueNative.VK_TAB, 0x0F, false);
            said["tabbed"] = CueNative.State(form);

            // A right press on the page hides them; the arrow along the tabs shows them again.
            CueNative.Press(form.pageHost, true);
            said["pagePress"] = CueNative.State(form);
            second.Focus();
            CueNative.Pump();
            said["refocused"] = CueNative.State(form);
            CueNative.Key(CueNative.VK_RIGHT, 0x4D, true);
            said["arrowed"] = CueNative.State(form);
            said["arrowedTo"] = form.navButtons[PageOrder[2]].Focused;

            // A press in a popup the window owns (a drop-down's list, a menu) is the mouse in the window too.
            var popup = new Form();
            popup.FormBorderStyle = FormBorderStyle.None;
            popup.ShowInTaskbar = false;
            popup.StartPosition = FormStartPosition.Manual;
            popup.Location = new Point(CueNative.Away, CueNative.Away);
            popup.Size = new Size(120, 80);
            popup.Owner = form;
            IntPtr p = popup.Handle;
            CueNative.ShowWindow(p, 4);
            CueNative.Pump();
            CueNative.Press(popup, false);
            said["popupPress"] = CueNative.Hidden(form);
            popup.Close();
            popup.Dispose();
            form.Close();
            form.Dispose();
            return said;
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class FocusVisibleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="car-focus-visible-")
        work = Path(cls.folder.name)
        reply = {"ok": True, "language": "en", "strings": l10n.catalog("en"), "endonyms": dict(l10n.ENDONYMS),
                 "preference": "en", "system_language": "en"}
        (work / "strings-en.json").write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        probe = work / "FocusVisibleProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "FocusVisible.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.FocusVisibleProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
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

    def keyboard(self, state, what):
        self.assertTrue(state["focusedIn"], what + ": the focus is in the window")
        self.assertFalse(state["hidden"], what + ": UISF_HIDEFOCUS clear")
        self.assertTrue(state["cues"], what + ": the focused control shows its ring")

    def mouse(self, state, what):
        self.assertTrue(state["focusedIn"], what + ": the focus is in the window")
        self.assertTrue(state["hidden"], what + ": UISF_HIDEFOCUS set again")
        self.assertFalse(state["cues"], what + ": the focused control shows no ring")

    def test_after_the_keyboard_the_focused_tab_has_its_ring(self):
        said = self.answer["dashboard"]
        self.keyboard(said["cleared"], "cleared")
        self.assertEqual(said["cleared"]["focusedType"], "NavButton")
        self.assertGreater(said["cleared"]["ring"], 20, "the ring is drawn round the tab")

    def test_a_click_on_a_tab_leaves_it_chosen_and_focused_with_no_ring(self):
        said = self.answer["dashboard"]
        self.mouse(said["clicked"], "clicked")
        self.assertEqual(said["clicked"]["focusedType"], "NavButton")
        self.assertTrue(said["clickedSecond"], "the tab clicked has the focus")
        self.assertEqual(said["clickedPage"], said["pages"][1], "and is the page shown")
        self.assertEqual(said["clicked"]["ring"], 0, "no ring drawn")
        self.assertFalse(said["otherTabCues"], "nor on any other control")

    def test_a_key_that_moves_no_focus_shows_no_ring(self):
        self.mouse(self.answer["dashboard"]["shift"], "shift")

    def test_tab_after_the_mouse_shows_the_ring_again(self):
        self.keyboard(self.answer["dashboard"]["tabbed"], "tabbed")

    def test_a_press_on_the_page_hides_it_and_an_arrow_along_the_tabs_shows_it(self):
        said = self.answer["dashboard"]
        self.assertTrue(said["pagePress"]["hidden"], "a right press on the page sets UISF_HIDEFOCUS")
        self.mouse(said["refocused"], "refocused")
        self.assertTrue(said["arrowedTo"], "the arrow moved the focus to the next tab")
        self.keyboard(said["arrowed"], "arrowed")
        self.assertGreater(said["arrowed"]["ring"], 20)

    def test_a_press_in_a_popup_the_window_owns_hides_it(self):
        self.assertTrue(self.answer["dashboard"]["popupPress"])

    def test_a_dialog_shows_its_ring_for_the_keyboard_only(self):
        said = self.answer["dialog"]
        self.assertTrue(said["titled"])
        self.keyboard(said["cleared"], "cleared")
        self.mouse(said["clicked"], "clicked")
        self.assertTrue(said["clickedSecond"], "the button pressed has the focus")
        self.assertFalse(said["firstAfterClick"])
        self.keyboard(said["tabbed"], "tabbed")


if __name__ == "__main__":
    unittest.main()
