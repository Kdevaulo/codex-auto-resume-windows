r"""v0.6.24-beta.2: a window starts with its focus rings hidden, however it was opened.

The live re-check 8 (2026-11-17) found a ring on the Dashboard's first page tab with no key pressed: on the first fresh
light open of a scratch Dashboard, and in the Hebrew window after it reopened itself on another monitor's scale
(--reopened=1). Windows gives a new window the keyboard cues of the input that came last on the desktop - a window started
from a script, or after keys typed elsewhere, starts with UISF_HIDEFOCUS clear - and FocusCues only set it again at a mouse
press. Now FocusCues hides the rings as a watched window's handle is made (again, when it is made anew) and as it is first
shown; the first key that moves the focus shows them, as before (tests/test_gui_v0624_focus_visible.py).

A probe compiled with the window builds the Dashboard 30000 px off the desktop; before it is shown its cues are cleared,
as Windows leaves them after keyboard input elsewhere; then it is shown with no key pressed, and its UISF_HIDEFOCUS read
(WM_QUERYUISTATE). Then its cues are cleared again and its window made anew (RecreateHandle, as a relayout to right to
left makes it) and read again. A SoftDialog made the same way is read too.

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
    internal static class StartCues
    {
        [DllImport("user32.dll", EntryPoint = "SendMessageW")]
        internal static extern IntPtr SendMessage(IntPtr window, int message, IntPtr w, IntPtr l);
        [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr window, int command);

        internal static void Pump()
        {
            for (int i = 0; i < 10; i++) { Application.DoEvents(); Thread.Sleep(10); }
        }

        // As Windows leaves a window after keyboard input: WM_CHANGEUISTATE, UIS_CLEAR, UISF_HIDEFOCUS.
        internal static void Clear(Form form)
        {
            SendMessage(form.Handle, 0x0127, new IntPtr(2 | (1 << 16)), IntPtr.Zero);
        }

        internal static bool Hidden(Form form)
        {
            return (SendMessage(form.Handle, 0x0129, IntPtr.Zero, IntPtr.Zero).ToInt64() & 1) != 0;
        }

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
                SettingsForm.StartCuesRun(argv[1], said);
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
            dialog.Location = new Point(-30000, -30000);
            dialog.ShowInTaskbar = false;
            dialog.ClientSize = new Size(360, 160);
            dialog.Controls.Add(new Button { Text = "First", Bounds = new Rectangle(16, 16, 120, 32) });
            IntPtr h = dialog.Handle;
            Pump();
            Clear(dialog);
            said["cleared"] = !Hidden(dialog);
            dialog.Show();
            Pump();
            said["shown"] = Hidden(dialog);
            dialog.Close();
            dialog.Dispose();
            return said;
        }
    }

    internal sealed partial class SettingsForm
    {
        internal static void StartCuesRun(string dir, Dictionary<string, object> said)
        {
            var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-en.json"), Encoding.UTF8)) as Dictionary<string, object>;
            string nowhere = Path.Combine(dir, "nowhere");
            var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, null);
            form.auditing = true;
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(-30000, -30000);
            form.ShowInTaskbar = false;
            IntPtr h = form.Handle;
            StartCues.Pump();
            said["made"] = StartCues.Hidden(form);
            // As if the last input on the desktop had been the keyboard.
            StartCues.Clear(form);
            said["cleared"] = !StartCues.Hidden(form);
            form.Show();
            StartCues.Pump();
            said["shown"] = StartCues.Hidden(form);
            // Its window made anew, cues cleared before.
            StartCues.Clear(form);
            MethodInfo recreate = typeof(Control).GetMethod("RecreateHandle", BindingFlags.Instance | BindingFlags.NonPublic);
            recreate.Invoke(form, null);
            StartCues.Pump();
            said["recreated"] = StartCues.Hidden(form);
            said["newWindow"] = form.Handle != h;
            form.Close();
            form.Dispose();
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class CuesAtStartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="car-cues-at-start-")
        work = Path(cls.folder.name)
        reply = {"ok": True, "language": "en", "strings": l10n.catalog("en"), "endonyms": dict(l10n.ENDONYMS),
                 "preference": "en", "system_language": "en"}
        (work / "strings-en.json").write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        probe = work / "StartCuesProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "StartCues.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.StartCues", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
            environment.pop("CODEX_AR_STILL_READY", None)
            done = subprocess.run([str(exe), str(out), str(work)], capture_output=True, timeout=300,
                                  creationflags=NO_WINDOW, env=environment)
            cls.answer = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
            if done.returncode != 0 or "error" in cls.answer or not cls.answer:
                cls.failure = "the probe failed (exit %d): %s %s" % (done.returncode, cls.answer.get("error"),
                                                                      done.stderr.decode("mbcs", "replace")[-2000:])

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_the_scene_is_keyboard_use_elsewhere(self):
        self.assertTrue(self.answer["cleared"], "the cues were cleared before it was shown, as after keys elsewhere")
        self.assertTrue(self.answer["dialog"]["cleared"])

    def test_a_fresh_window_is_shown_with_its_rings_hidden(self):
        self.assertTrue(self.answer["made"], "hidden as its window is made")
        self.assertTrue(self.answer["shown"], "and as it is shown, with no key pressed")

    def test_a_window_made_anew_starts_with_its_rings_hidden(self):
        self.assertTrue(self.answer["newWindow"])
        self.assertTrue(self.answer["recreated"])

    def test_a_dialog_is_shown_with_its_rings_hidden(self):
        self.assertTrue(self.answer["dialog"]["shown"])


if __name__ == "__main__":
    unittest.main()
