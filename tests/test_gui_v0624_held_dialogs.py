r"""v0.6.24: a text-entry dialog the screen holds smaller than it was laid out for is not held to a whole line in its box.

No form is larger than the largest window the screen allows (SystemInformation.MaxWindowTrackSize): on a screen too
small for a dialog, Windows makes it smaller than its layout asked for. The window opens only at a text size whose
dialogs its screen holds (TextScale.Fitting), so no person meets such a dialog, and every dialog audit leaves its layout
alone (WindowAudit.HeldByScreen) - the Settings page's own-value dialogs since v0.6.16, the title cards since v0.6.24.
The conversation's message and the words for this time still asked a whole line of their text box there: from v0.6.24
their title card's strip is inside the dialog and as large as the text, where Windows' caption was outside it, so at
200% and the largest text size on the CI's 1024 by 768 screen the box was left 22 px of a 72 px line, in all 22 languages
(dev CI 43797690688, test_gui_v0611_access).

A probe compiled with the window builds the Dashboard, never shown, at a scale this machine's own screen holds those two
dialogs at under a quarter of their height - as that screen held them - and asks:

- that the scene is the one the CI met: each dialog held, and its text box really left less than a line (AuditTextLine
  asked directly finds it), so the audit's quiet answer is not a scene that never happened;
- the two dialog audits: no line cut off in a held dialog, every name still asked, and the line check on again after;
- at 100%, where the screen holds them whole, both audits as before: nothing found, every name asked, and the line
  check in force (the box shows its whole line).

GUI test module (it makes windows, never shown): run on its own, through gui_lock.sh.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import guiscan  # noqa: E402
from codex_auto_resume import l10n  # noqa: E402
from test_gui_layout import fullest_snapshot  # noqa: E402

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
    internal static class HeldDialogsProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { SettingsForm.HeldRun(argv[1], said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        private static List<object> HeldList(List<string> lines)
        {
            var list = new List<object>();
            foreach (string line in lines) list.Add(line);
            return list;
        }

        // One dialog built as its audit builds it, and its text box asked for a whole line directly.
        private static Dictionary<string, object> HeldScene(Form dialog, SoftTextArea area)
        {
            var said = new Dictionary<string, object>();
            dialog.TopLevel = false;
            Materialise(dialog);
            dialog.PerformLayout();
            Size most = SystemInformation.MaxWindowTrackSize;
            said["held"] = dialog.Width >= most.Width || dialog.Height >= most.Height;
            said["height"] = (double)dialog.Height;
            var lines = new List<string>();
            AuditTextLine("scene", area.Box, lines);
            said["line"] = HeldList(lines);
            return said;
        }

        private static Dictionary<string, object> HeldAt(string dir, double scale, Dictionary<string, object> snapshot)
        {
            var said = new Dictionary<string, object>();
            AdoptDisplayScale(scale);
            float factor = (float)(scale / SystemScale);
            Font message = SystemFonts.MessageBoxFont;
            var font = new Font(message.FontFamily, message.SizeInPoints * factor, message.Style, GraphicsUnit.Point);
            var catalog = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-en.json"), Encoding.UTF8)) as Dictionary<string, object>;
            string nowhere = Path.Combine(dir, "nowhere");
            using (var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), catalog, font))
            {
                form.auditing = true;
                form.TopLevel = false;
                var row = ((List<object>)snapshot["pending"])[0] as Dictionary<string, object>;
                using (Form dialog = form.BuildConversationMessage(row, "Carry on with the plan, please. {reason}"))
                    said["conversationScene"] = HeldScene(dialog, form.conversationArea);
                using (Form dialog = form.BuildOnceWords(row, "Then run the tests, please. {reason}"))
                    said["onceScene"] = HeldScene(dialog, form.onceWordsArea);
                var findings = new List<string>();
                AuditedSpoken = 0;
                form.AuditConversationMessage(snapshot, findings);
                said["conversationSpoken"] = (double)AuditedSpoken;
                said["conversationLinesAfter"] = AuditLines;
                AuditedSpoken = 0;
                form.AuditOnceWords(snapshot, findings);
                said["onceSpoken"] = (double)AuditedSpoken;
                said["onceLinesAfter"] = AuditLines;
                said["findings"] = HeldList(findings);
            }
            return said;
        }

        internal static void HeldRun(string dir, Dictionary<string, object> said)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(null);
            Palette.Adopt("light");
            var snapshot = Json.Parse(File.ReadAllText(Path.Combine(dir, "snapshot.json"), Encoding.UTF8)) as Dictionary<string, object>;
            // The conversation's dialog is 591 logical px tall with its body card and title row (611 with the beta's title
            // card); at 200% and the largest text size (4.5) the CI's screen held the beta's to 780 of its 2750. Here: six times
            // what this screen holds. v0.6.24-beta.2: its buttons are in its card (SoftDialog.Gather, the owner's layout A),
            // where they keep 12 px over themselves in place of the 16 they kept under themselves on the ground - 4 logical
            // px more for the body, which at four and a half times this screen left the box a whole line here.
            Size most = SystemInformation.MaxWindowTrackSize;
            double held = Math.Max(2.0, 6.0 * most.Height / 587.0);
            said["most"] = new List<object> { (double)most.Width, (double)most.Height };
            said["heldScale"] = held;
            said["held"] = HeldAt(dir, held, snapshot);
            said["whole"] = HeldAt(dir, 1.0, snapshot);
        }
    }
}
"""


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class HeldDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        reply = {"ok": True, "language": "en", "strings": l10n.catalog("en"), "endonyms": dict(l10n.ENDONYMS),
                 "preference": "en", "system_language": "en"}
        (work / "strings-en.json").write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        (work / "snapshot.json").write_text(json.dumps(fullest_snapshot(time.time()), ensure_ascii=False), encoding="utf-8")
        probe = work / "HeldDialogsProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "HeldDialogs.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.HeldDialogsProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
            done = subprocess.run([str(exe), str(out), str(work)], capture_output=True, timeout=600,
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

    def test_the_scene_is_the_ci_s_a_held_dialog_whose_box_is_left_less_than_a_line(self):
        said = self.answer["held"]
        for scene in ("conversationScene", "onceScene"):
            with self.subTest(scene=scene):
                self.assertTrue(said[scene]["held"], "the screen holds the dialog smaller than it was laid out for")
                self.assertEqual(len(said[scene]["line"]), 1, "its text box is left less than a line")
                self.assertIn("its text is cut off", said[scene]["line"][0])

    def test_a_held_dialog_is_not_held_to_a_whole_line_and_is_still_asked_every_name(self):
        said = self.answer["held"]
        self.assertEqual([line for line in said["findings"] if "its text is cut off" in line], [])
        self.assertEqual(said["findings"], [], "and nothing else found")
        for dialog in ("conversation", "once"):
            with self.subTest(dialog=dialog):
                self.assertGreaterEqual(said[dialog + "Spoken"], 3, "its box and its buttons asked their names")
                self.assertTrue(said[dialog + "LinesAfter"], "the line check is on again for what follows")

    def test_a_dialog_the_screen_holds_whole_is_audited_as_before(self):
        said = self.answer["whole"]
        for scene in ("conversationScene", "onceScene"):
            with self.subTest(scene=scene):
                self.assertFalse(said[scene]["held"])
                self.assertEqual(said[scene]["line"], [], "its box shows a whole line")
        self.assertEqual(said["findings"], [])
        for dialog in ("conversation", "once"):
            with self.subTest(dialog=dialog):
                self.assertEqual(said[dialog + "Spoken"], self.answer["held"][dialog + "Spoken"], "the same names asked")
                self.assertTrue(said[dialog + "LinesAfter"])


if __name__ == "__main__":
    unittest.main()
