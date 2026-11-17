r"""v0.6.24-beta.2: a question's Korean words wrap only between words.

The live re-check 7 (2026-11-17, 150 %) found the questions breaking Korean inside a word: Clear history "있 / 는", Cancel
all "있 / 을", the power question "그다 / 음" and "멈춥 / 니다". The question's words were a plain Label, wrapped by Windows,
which breaks Hangul between any two syllables; everywhere else the window's words are a WrapLabel (Soft.Wrap), which
breaks Korean only at spaces. The message box (Dialog) now measures and draws its words as a WrapLabel too
(QuestionWords).

A probe compiled with the window builds the Dashboard in Korean, never shown, makes each question's words as the dialog
makes them, at the width the dialog gives them, and reads the lines they are drawn in (WrapLabel.Lines, what OnPaint
draws), at 100 % and 150 %: every line ends where the sentence has a space or a line break of its own.

GUI test module (it makes windows, never shown): run on its own, through gui_lock.sh.
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
KEYS = ("confirm.clear", "confirm.cancel_all", "confirm.cancel", "confirm.stop_watcher", "power.confirm")

PROBE = r"""
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class QuestionWordsProbe
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
                Application.SetCompatibleTextRenderingDefault(false);
                Palette.AdoptDesign(null);
                Palette.Adopt("light");
                SettingsForm.QuestionWordsRun(argv[1], said);
            }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        internal static void QuestionWordsRun(string dir, Dictionary<string, object> said)
        {
            var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-ko.json"), Encoding.UTF8)) as Dictionary<string, object>;
            var texts = Json.Parse(File.ReadAllText(Path.Combine(dir, "texts.json"), Encoding.UTF8)) as Dictionary<string, object>;
            Font message = SystemFonts.MessageBoxFont;
            foreach (double scale in new[] { 1.0, 1.5 })
            {
                AdoptDisplayScale(scale);
                float factor = (float)(scale / SystemScale);
                var font = new Font(message.FontFamily, message.SizeInPoints * factor, message.Style, GraphicsUnit.Point);
                string nowhere = Path.Combine(dir, "nowhere");
                var at = new Dictionary<string, object>();
                using (var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, font))
                {
                    form.auditing = true;
                    form.TopLevel = false;
                    foreach (var pair in texts)
                    {
                        // As Dialog lays them: measured at 420 logical px, the dialog at least 300 wide, the words as wide.
                        WrapLabel words = form.QuestionWords((string)pair.Value);
                        Size measured = words.GetPreferredSize(new Size(form.Px(420), 0));
                        int width = Math.Max(form.Px(300), measured.Width);
                        var one = new Dictionary<string, object>();
                        one["lines"] = words.Lines(width);
                        one["kind"] = words.GetType().Name;
                        at[pair.Key] = one;
                        words.Dispose();
                    }
                }
                said[scale.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture)] = at;
            }
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class QuestionWordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="car-question-words-")
        work = Path(cls.folder.name)
        korean = l10n.catalog("ko")
        reply = {"ok": True, "language": "ko", "strings": korean, "endonyms": dict(l10n.ENDONYMS),
                 "preference": "ko", "system_language": "ko"}
        (work / "strings-ko.json").write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        cls.texts = {key: korean[key].replace("{name}", "example-project") for key in KEYS if key in korean}
        (work / "texts.json").write_text(json.dumps(cls.texts, ensure_ascii=False), encoding="utf-8")
        probe = work / "QuestionWordsProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "QuestionWords.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.QuestionWordsProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
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

    def test_the_questions_are_korean(self):
        self.assertGreaterEqual(len(self.texts), 4)

    def test_a_korean_question_wraps_only_between_its_words(self):
        for scale in ("1.0", "1.5"):
            for key, text in self.texts.items():
                with self.subTest(scale=scale, key=key):
                    seen = self.answer[scale][key]
                    self.assertEqual(seen["kind"], "WrapLabel", "measured and drawn as the window's other words")
                    lines = seen["lines"].replace("\r\n", "\n").split("\n")
                    source = text.replace("\r\n", "\n")
                    at = 0
                    for line in lines[:-1]:
                        stripped = line.rstrip(" ")
                        found = source.find(stripped, at)
                        self.assertGreaterEqual(found, 0, "the line %r is the sentence's own" % line)
                        end = found + len(stripped)
                        self.assertLess(end, len(source))
                        self.assertIn(source[end], " \n", "%s: a line ends inside a word: %r | %r" % (key, line, source[end:end + 8]))
                        at = end
                    self.assertGreater(len(lines), 1, "long enough to wrap, so a break is asked of it")


if __name__ == "__main__":
    unittest.main()
