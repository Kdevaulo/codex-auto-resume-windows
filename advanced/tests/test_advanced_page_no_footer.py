# ADVANCED-EDITION-CODE: in the advanced edition's tree, never the standard one's.
"""v0.6.24: the Settings save bar never stands on Advanced features or Chat (the owner, 2026-11-18, a screenshot of the
installed v0.6.24-beta.2 advanced edition: an empty card at the window's foot under the page's buttons).

Since v0.6.24-beta.2 the save bar (the window's `footer`) is Settings' alone: ShowPage shows it there and hides it on
every other page. This edition's two pages are shown by their own switches (ShowAdvanced, ShowChat), which hid Save and
Restore defaults but left the bar - so after Settings it stood empty on both. They hide it the same way, before the page
is laid out, and the page reaches as far down as the Overview does.

The window compiled with this edition's sources and a probe of its own, built as AdvancedLayoutAudit builds it (never
shown), switched: a fresh open to Advanced features and to Chat; Settings, Advanced features, Chat; and Settings, Chat,
Advanced features. GUI test module: run on its own (gui_lock.sh), in the advanced lane.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;tests" python -m unittest discover -s advanced/tests -p test_advanced_page_no_footer.py
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

import guiscan  # noqa: E402
from advancedcase import ROOT  # noqa: E402
from pagecase import CSC, overlay_sources, strings  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
WORDS = next(iter(sorted((ROOT / "advanced" / "src").glob("*/locales")))) / "en.json"

PROBE = r"""
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class NoFooterProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { SettingsForm.NoFooterRun(argv[1], said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        private Dictionary<string, object> NoFooterRead(string page)
        {
            if (page == AdvancedPageName) ShowAdvanced();
            else if (page == ChatPageName) ShowChat();
            else ShowPage(page);
            Materialise(this);
            PerformLayout();
            var said = new Dictionary<string, object>();
            said["page"] = currentPage ?? "";
            said["footer"] = Soft.OwnVisible(footer);
            said["hostBottom"] = (double)pageHost.Bottom;
            said["client"] = (double)ClientSize.Height;
            return said;
        }

        internal static void NoFooterRun(string dir, Dictionary<string, object> said)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(null);
            Palette.Adopt("light");
            string stringsJson = File.ReadAllText(Path.Combine(dir, "strings.json"), Encoding.UTF8);
            var words = Json.Parse(File.ReadAllText(Path.Combine(dir, "words.json"), Encoding.UTF8)) as Dictionary<string, object>;
            var orders = Json.Parse(File.ReadAllText(Path.Combine(dir, "orders.json"), Encoding.UTF8)) as Dictionary<string, object>;
            foreach (KeyValuePair<string, object> order in orders)
            {
                var seen = new List<object>();
                WithAdvancedWindow(stringsJson, 1.0, delegate(SettingsForm form)
                {
                    form.AdoptAdvancedWords(words);
                    foreach (object page in (List<object>)order.Value) seen.Add(form.NoFooterRead((string)page));
                });
                said[order.Key] = seen;
            }
        }
    }
}
"""

ORDERS = {"fresh advanced": ["advanced"], "fresh chat": ["chat"],
          "settings, advanced, chat": ["overview", "settings", "advanced", "chat"],
          "settings, chat, advanced": ["overview", "settings", "chat", "advanced"]}


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class NoFooterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        (work / "strings.json").write_text(json.dumps(strings("en"), ensure_ascii=False), encoding="utf-8")
        (work / "words.json").write_text(WORDS.read_text(encoding="utf-8"), encoding="utf-8")
        (work / "orders.json").write_text(json.dumps(ORDERS), encoding="utf-8")
        probe = work / "NoFooterProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "NoFooter.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.NoFooterProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], *[str(path) for path in overlay_sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
            done = subprocess.run([str(exe), str(out), str(work)], capture_output=True, timeout=600, creationflags=NO_WINDOW,
                                  env=environment)
            cls.answer = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
            if done.returncode != 0 or "error" in cls.answer or not cls.answer:
                cls.failure = "the probe failed (exit %d): %s" % (done.returncode, cls.answer.get("error"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_neither_page_shows_the_save_bar_in_any_order(self):
        for order, seen in self.answer.items():
            for at in seen:
                with self.subTest(order=order, page=at["page"]):
                    self.assertEqual(at["footer"], at["page"] == "settings", "the save bar on Settings alone")

    def test_each_page_reaches_as_far_down_as_the_overview(self):
        for order in ("settings, advanced, chat", "settings, chat, advanced"):
            seen = self.answer[order]
            overview = seen[0]
            self.assertEqual(overview["page"], "overview")
            for at in seen[2:]:
                with self.subTest(order=order, page=at["page"]):
                    self.assertEqual(at["hostBottom"], overview["hostBottom"], "the page has the room the bar took")
        for order in ("fresh advanced", "fresh chat"):
            at = self.answer[order][0]
            with self.subTest(order=order):
                self.assertFalse(at["footer"])
                self.assertEqual(at["hostBottom"], self.answer["settings, advanced, chat"][0]["hostBottom"])


class NoFooterSourceTests(unittest.TestCase):
    def test_every_page_switch_sets_the_save_bar(self):
        for name, method in (("AdvancedPage.cs", "private void ShowAdvanced()"), ("AdvancedChat.cs", "private void ShowChat()")):
            source = (ROOT / "advanced" / "gui" / name).read_text(encoding="utf-8")
            body = guiscan._block(source, source.index(method))
            with self.subTest(name):
                self.assertIn("if (Soft.OwnVisible(footer)) footer.Visible = false;", body)
                self.assertLess(body.index("footer.Visible = false"), body.index("pageHost.SuspendLayout()"),
                                "before the page is laid out")


if __name__ == "__main__":
    unittest.main()
