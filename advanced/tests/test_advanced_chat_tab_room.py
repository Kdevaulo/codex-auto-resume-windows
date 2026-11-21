r"""v0.6.24 final: the tab row keeps the Chat tab's room until the list says whether it shows, so nothing moves.

The final's live acceptance (J9): the advanced edition's tab row gained Chat about a second after opening, when the first
list arrived, and the row changed once. Whether Chat shows is the capability's standing state - advanced.sqlite and the
engine's compatibility, nothing the window can read for itself - so until the list is read the row keeps its room
(SettingsForm.TabsHeld, AdvancedChat.cs): the tabs are fitted, and the window held, as if it were there.

A probe compiled with both editions' window sources builds the window never shown (TopLevel = false, as the layout audits
do), the version's pill known from the start, the advanced words adopted, in English and Korean at 100, 150 and 200 % and at the largest text sizes: then
the list arrives with chat on - every tab that was there keeps its place and size, the pill too, and Chat stands right after
the last of them - or with chat off - the pill keeps its place, Chat stays hidden, and no tab is narrower or further left
than it was. GUI test module (it makes windows, never shown): run it on its own, through gui_lock.sh.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from advancedcase import ROOT  # noqa: E402
import guiscan  # noqa: E402
from codex_auto_resume import l10n  # noqa: E402
from pagecase import CSC, overlay_sources  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LOCALES = ("en", "ko", "de", "ru")
# The window at its opening width, and narrower - as a person may leave it - where the tabs fill the row.
WIDTHS = (0, 880)
# (display scale, text size): 100, 150 and 200 %, at text size 1 and at the largest a 3840 by 2160 screen allows,
# where the eight tabs need to be drawn closer than six.
CASES = ((1.0, 1.0), (1.5, 1.0), (2.0, 1.0), (1.0, 2.25), (1.5, 2.25), (2.0, 1.75))
WORDS = ROOT / "advanced" / "src" / "codex_auto_resume_advanced" / "locales"

PROBE = r"""
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class ChatRoomProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { SettingsForm.ChatRoomRun(argv[1], said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        private static List<object> ChatRoomBox(Control control, Control within)
        {
            var box = new Rectangle(Point.Empty, control.Size);
            for (Control c = control; c != null && c != within; c = c.Parent) box.Offset(c.Left, c.Top);
            return new List<object> { (double)box.X, (double)box.Y, (double)box.Width, (double)box.Height };
        }

        private Dictionary<string, object> ChatRoomRead()
        {
            Materialise(this);
            PerformLayout();
            var said = new Dictionary<string, object>();
            said["pill"] = ChatRoomBox(versionPill, this);
            said["fit"] = PillFit;
            var tabs = new Dictionary<string, object>();
            foreach (KeyValuePair<string, NavButton> tab in navButtons)
                if (tab.Value.Parent != null && Soft.OwnVisible(tab.Value)) tabs[tab.Key] = ChatRoomBox(tab.Value, this);
            said["tabs"] = tabs;
            said["client"] = new List<object> { (double)ClientSize.Width, (double)ClientSize.Height };
            return said;
        }

        internal static void ChatRoomRun(string dir, Dictionary<string, object> said)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(null);
            Palette.Adopt("light");
            var cases = Json.Parse(File.ReadAllText(Path.Combine(dir, "cases.json"), Encoding.UTF8)) as List<object>;
            System.Reflection.FieldInfo fallback = typeof(Control).GetField("defaultFont",
                System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
            Font defaultBefore = Control.DefaultFont;
            foreach (object item in cases)
            {
                var one = (Dictionary<string, object>)item;
                string locale = (string)one["locale"];
                double scale = (double)one["scale"], text = (double)one["text"];
                var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-" + locale + ".json"), Encoding.UTF8)) as Dictionary<string, object>;
                var words = (Dictionary<string, object>)strings["advanced_words"];
                var answer = new Dictionary<string, object>();
                int narrow = (int)(double)one["width"];
                foreach (string chat in new[] { "armed", "off" })
                {
                    AdoptDisplayScale(scale);
                    AdoptTextSize(text, text);
                    float factor = (float)(scale / SystemScale);
                    Font box = TextScale.Apply(SystemFonts.MessageBoxFont, 1.0, text);
                    var windowFont = new Font(box.FontFamily, box.SizeInPoints * factor, box.Style, GraphicsUnit.Point);
                    Font fallen = TextScale.Apply(defaultBefore, 1.0, text);
                    if (fallback != null)
                        fallback.SetValue(null, new Font(fallen.FontFamily, fallen.SizeInPoints * factor, fallen.Style, GraphicsUnit.Point));
                    Mirror.Window = Mirror.Language(locale);
                    string nowhere = Path.Combine(dir, "nowhere-" + locale);
                    using (var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, windowFont))
                    {
                        form.auditing = true;
                        form.TopLevel = false;
                        form.ClientSize = form.OpeningClient;
                        if (narrow > 0) form.ClientSize = new Size(form.Px(narrow), form.ClientSize.Height);
                        form.ShowPage("overview");
                        // The version as the window reads it from its own files before the first state (ShowLocalVersion).
                        form.ShowVersion(form.versionText, new Dictionary<string, object> { { "version", "0.6.24" }, { "edition", "advanced" } });
                        form.AdoptAdvancedWords(words);
                        var read = new Dictionary<string, object>();
                        read["before"] = form.ChatRoomRead();
                        var capability = new Dictionary<string, object> { { "id", "codex_chat" }, { "state", chat } };
                        form.advancedListing = new Dictionary<string, object> { { "capabilities", new List<object> { capability } } };
                        form.UpdateChatTab();
                        read["after"] = form.ChatRoomRead();
                        answer[chat] = read;
                    }
                }
                said[locale + " " + scale.ToString("0.00", CultureInfo.InvariantCulture) + " " +
                     text.ToString("0.00", CultureInfo.InvariantCulture) + " " + narrow.ToString(CultureInfo.InvariantCulture)] = answer;
            }
        }
    }
}
"""


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class ChatTabRoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        for locale in LOCALES:
            words = json.loads((WORDS / (locale + ".json")).read_text(encoding="utf-8"))
            reply = {"ok": True, "language": locale, "strings": l10n.catalog(locale), "endonyms": dict(l10n.ENDONYMS),
                     "preference": locale, "system_language": locale, "advanced_words": words}
            (work / ("strings-%s.json" % locale)).write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        cases = [{"locale": locale, "scale": scale, "text": text, "width": width}
                 for locale in LOCALES for scale, text in CASES for width in WIDTHS]
        (work / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
        probe = work / "ChatRoomProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "ChatRoom.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.ChatRoomProbe",
                                "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], *[str(path) for path in overlay_sources()],
                                str(probe)],
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

    def test_chat_on_comes_into_room_already_kept(self):
        """Fails without the held room: in English the eight tabs are drawn closer (or the window held wider) only once
        Chat shows, and every tab moves."""
        for where, answer in sorted(self.answer.items()):
            before, after = answer["armed"]["before"], answer["armed"]["after"]
            with self.subTest(where):
                self.assertNotIn("chat", before["tabs"])
                self.assertIn("chat", after["tabs"])
                self.assertEqual(after["client"], before["client"], "the window keeps its size")
                self.assertEqual(after["pill"], before["pill"], "the pill keeps its place")
                for name, box in before["tabs"].items():
                    self.assertEqual(after["tabs"][name], box, name + " keeps its place and size")

    def test_chat_off_moves_nothing_back_over_the_tabs(self):
        for where, answer in sorted(self.answer.items()):
            before, after = answer["off"]["before"], answer["off"]["after"]
            with self.subTest(where):
                self.assertNotIn("chat", after["tabs"])
                self.assertEqual(after["pill"], before["pill"])
                self.assertEqual(after["client"], before["client"])
                for name, box in before["tabs"].items():
                    self.assertGreaterEqual(after["tabs"][name][2], box[2], name + " is never narrower")


class ChatTabRoomSourceTests(unittest.TestCase):
    def test_the_row_and_the_window_count_the_held_tab(self):
        window = guiscan.read("gui/SettingsApp.cs")
        self.assertIn("TabsHeld(held);", window)
        page = (ROOT / "advanced" / "gui" / "AdvancedPage.cs").read_text(encoding="utf-8")
        self.assertIn("(!Soft.OwnVisible(tab) && !held.Contains(tab))", page)
        chat = (ROOT / "advanced" / "gui" / "AdvancedChat.cs").read_text(encoding="utf-8")
        self.assertIn("if (chatTab != null && !chatTabKnown && !Soft.OwnVisible(chatTab)) held.Add(chatTab);", chat)


if __name__ == "__main__":
    unittest.main()
