r"""v0.6.24-beta.2: a question whose action deletes, cancels or cannot be undone starts the keyboard on its dismissal.

The live re-check 7 (2026-11-17, 150 %, GetGUIThreadInfo) found Clear history and Cancel all opening with the focus on the
action, so an Enter at once did it; the power action's question started on Cancel. The owner's decision: every question
whose action deletes, cancels or cannot be undone starts the keyboard on the dismissal - and Enter presses it - as the
power question does, each button keeping its look (the action's accent). They had started on the action since the
window's own message box (v0.6.6): v0.6.23 and v0.6.24-beta both set `ActiveControl = first`, the accent button.

One probe compiled with the window builds the Dashboard off the desktop and asks each such question through the code a
person's click runs - Clear history, Cancel all, Stop watcher, Restore defaults, a conversation's Cancel and Turn off -
with a timer that reads the open dialog (where the keyboard starts, what Enter presses, which button wears the accent)
and closes it with Escape, so nothing is ever sent. A question that takes nothing back (Turn automatic recovery back on)
still starts on its action.

GUI test module (it shows dialogs): run on its own, through gui_lock.sh.
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
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class QuestionStartProbe
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
                SettingsForm.QuestionStartRun(argv[1], said);
            }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        // The open question, read and closed with Escape by a timer while the asking code holds the thread in ShowDialog.
        private static Dictionary<string, object> QuestionSeen(SettingsForm form, Action ask)
        {
            Dictionary<string, object> seen = null;
            var timer = new Timer();
            timer.Interval = 150;
            timer.Tick += delegate
            {
                try
                {
                    foreach (Form open in Application.OpenForms)
                    {
                        var dialog = open as SoftDialog;
                        if (dialog == null || !dialog.Modal || !dialog.Visible) continue;
                        timer.Stop();
                        seen = new Dictionary<string, object>();
                        Control start = dialog.ActiveControl;
                        seen["start"] = start == null ? "" : start.Text;
                        seen["enter"] = dialog.AcceptButton == null ? "" : ((Control)dialog.AcceptButton).Text;
                        seen["escape"] = dialog.CancelButton == null ? "" : ((Control)dialog.CancelButton).Text;
                        var accent = new List<object>();
                        foreach (Button button in DialogButtons(dialog))
                        {
                            var soft = button as SoftButton;
                            if (soft != null && soft.Primary) accent.Add(button.Text);
                        }
                        seen["accent"] = accent;
                        dialog.Close();
                        return;
                    }
                }
                catch (Exception e) { seen = new Dictionary<string, object> { { "error", e.ToString() } }; timer.Stop(); }
            };
            timer.Start();
            ask();
            timer.Stop();
            timer.Dispose();
            return seen ?? new Dictionary<string, object> { { "error", "no question was seen" } };
        }

        internal static void QuestionStartRun(string dir, Dictionary<string, object> said)
        {
            var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-en.json"), Encoding.UTF8)) as Dictionary<string, object>;
            string nowhere = Path.Combine(dir, "nowhere");
            var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, null);
            form.auditing = true;
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(-30000, -30000);
            form.ShowInTaskbar = false;
            form.Show();
            Application.DoEvents();
            var row = new Dictionary<string, object>();
            row["interruption_id"] = "00000000-0000-4000-8000-0000000000aa";
            row["thread_id"] = "00000000-0000-4000-8000-0000000000bb";
            row["conversation"] = "example-project";
            said["clear"] = QuestionSeen(form, delegate { form.ClearHistory(); });
            form.ShowPage("pending");
            Application.DoEvents();
            form.pendingList.Items.Add("example-project");
            said["cancelAll"] = QuestionSeen(form, delegate { form.CancelAll(); });
            said["stopWatcher"] = QuestionSeen(form, delegate { form.StopWatcher(); });
            said["restore"] = QuestionSeen(form, delegate { form.RestoreDefaults(); });
            said["cancelOne"] = QuestionSeen(form, delegate {
                form.ConfirmCarefully(form.Named("confirm.cancel", "Stop recovering \"{name}\"? A continuation already running in Codex is not stopped.", row),
                                      form.S("action.cancel", "Cancel")); });
            said["benign"] = QuestionSeen(form, delegate {
                form.Confirm(form.S("confirm.resume", "Turn automatic recovery back on?"), form.S("action.resume", "Resume")); });
            said["sent"] = (double)form.busy;
            form.Close();
            form.Dispose();
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class QuestionStartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="car-question-start-")
        work = Path(cls.folder.name)
        cls.english = l10n.catalog("en")
        reply = {"ok": True, "language": "en", "strings": cls.english, "endonyms": dict(l10n.ENDONYMS),
                 "preference": "en", "system_language": "en"}
        (work / "strings-en.json").write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        probe = work / "QuestionStartProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "QuestionStart.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.QuestionStartProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
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
                cls.failure = "the probe failed (exit %d): %s %s" % (done.returncode, cls.answer.get("error"),
                                                               done.stderr.decode("mbcs", "replace")[-3000:])

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_a_question_that_takes_something_back_starts_on_its_dismissal(self):
        e = self.english
        cases = {"clear": (e["action.clear_history"], e["action.cancel"]),
                 "cancelAll": (e["action.cancel_all"], e["action.cancel"]),
                 "stopWatcher": (e["action.stop_watcher"], e["action.cancel"]),
                 "restore": (e["action.restore"], e["action.cancel"]),
                 # The conversation's own Cancel: its dismissal says Close, as Cancel beside Cancel names nothing.
                 "cancelOne": (e["action.cancel"], e["action.close"])}
        for name, (action, dismissal) in cases.items():
            with self.subTest(name):
                seen = self.answer[name]
                self.assertNotIn("error", seen)
                self.assertEqual(seen["start"], dismissal, "the keyboard starts on the dismissal")
                self.assertEqual(seen["enter"], dismissal, "Enter at once never does the action")
                self.assertEqual(seen["escape"], dismissal)
                self.assertEqual(seen["accent"], [action], "the action keeps its accent")

    def test_a_question_that_takes_nothing_back_still_starts_on_its_action(self):
        seen = self.answer["benign"]
        self.assertEqual(seen["start"], self.english["action.resume"])
        self.assertEqual(seen["enter"], self.english["action.resume"])

    def test_nothing_was_sent(self):
        self.assertEqual(self.answer["sent"], 0, "every question was answered by Escape")


if __name__ == "__main__":
    unittest.main()
