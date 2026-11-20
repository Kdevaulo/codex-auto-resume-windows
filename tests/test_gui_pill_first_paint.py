r"""v0.6.24 final: the version's pill is in the window's first painted layout, not only after the first state.

The final's live acceptance (J9): while the Dashboard loaded, the tab row had no version pill; it came with the first state
from the bridge, and the row changed once after opening. The version is this installation's own, written in one place -
app\.codex-plugin\plugin.json (config.version reads it for the status) - and the edition is what its source tree is
(InstallerFlow.EditionOfSource). The window now reads both as it is built (ShowLocalVersion), before its first paint; the
status's read writes the same over it.

A probe compiled with the window builds it never shown (TopLevel = false, as LayoutAudit does) in a folder that holds an
installation's plugin.json, at 100, 150 and 200 %: before any state the pill is on the tabs' row with the version, and when
the first state arrives - naming the same version - neither the pill nor any tab moves. A folder with no plugin.json opens
as before, the pill waiting for the state. GUI test module (it makes windows, never shown): run it through gui_lock.sh.
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
SCALES = (1.0, 1.5, 2.0)

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
    internal static class PillFirstProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { SettingsForm.PillFirstRun(argv[1], said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        private static List<object> PillFirstBox(Control control, Control within)
        {
            var box = new Rectangle(Point.Empty, control.Size);
            for (Control c = control; c != null && c != within; c = c.Parent) box.Offset(c.Left, c.Top);
            return new List<object> { (double)box.X, (double)box.Y, (double)box.Width, (double)box.Height };
        }

        private Dictionary<string, object> PillFirstRead()
        {
            Materialise(this);
            PerformLayout();
            var said = new Dictionary<string, object>();
            said["text"] = versionText.Text ?? "";
            said["shown"] = versionPill != null && Soft.OwnVisible(versionPill) && versionPill.Parent != null && Soft.OwnVisible(versionPill.Parent);
            said["fit"] = PillFit;
            said["pill"] = PillFirstBox(versionPill, this);
            var tabs = new List<object>();
            foreach (Control tab in navButtons["overview"].Parent.Controls)
                if (Soft.OwnVisible(tab)) tabs.Add(PillFirstBox(tab, this));
            said["tabs"] = tabs;
            return said;
        }

        internal static void PillFirstRun(string dir, Dictionary<string, object> said)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(null);
            Palette.Adopt("light");
            var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings.json"), Encoding.UTF8)) as Dictionary<string, object>;
            var scales = Json.Parse(File.ReadAllText(Path.Combine(dir, "scales.json"), Encoding.UTF8)) as List<object>;
            foreach (object item in scales)
            {
                double scale = (double)item;
                AdoptDisplayScale(scale);
                AdoptTextSize(1.0, 1.0);
                float factor = (float)(scale / SystemScale);
                Font box = SystemFonts.MessageBoxFont;
                var windowFont = new Font(box.FontFamily, box.SizeInPoints * factor, box.Style, GraphicsUnit.Point);
                string nowhere = Path.Combine(dir, "nowhere");
                var answer = new Dictionary<string, object>();
                using (var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, windowFont))
                {
                    form.auditing = true;
                    form.TopLevel = false;
                    form.MinimumSize = Size.Empty;
                    form.ClientSize = form.OpeningClient;
                    form.ShowPage("overview");
                    answer["first"] = form.PillFirstRead();
                    // The first state: the status as the bridge answers it, naming the same version.
                    form.ShowVersion(form.versionText, new Dictionary<string, object> { { "version", "0.6.24" }, { "edition", "standard" } });
                    answer["state"] = form.PillFirstRead();
                }
                said[scale.ToString("0.00", CultureInfo.InvariantCulture)] = answer;
            }
        }
    }
}
"""


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class PillFirstPaintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        reply = {"ok": True, "language": "en", "strings": l10n.catalog("en"), "endonyms": dict(l10n.ENDONYMS),
                 "preference": "en", "system_language": "en"}
        (work / "strings.json").write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        (work / "scales.json").write_text(json.dumps(list(SCALES)), encoding="utf-8")
        probe = work / "PillFirstProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        cls.failure = None
        cls.answers = {}
        # Two installations: one whose plugin.json names the version (the window's own folder is its root), and one with
        # none - a copy of the window anywhere else.
        for name, manifest in (("installed", {"name": "codex-auto-resume", "version": "0.6.24"}), ("bare", None)):
            folder = work / name
            folder.mkdir()
            for copied in ("strings.json", "scales.json"):
                (folder / copied).write_bytes((work / copied).read_bytes())
            if manifest is not None:
                (folder / "app" / ".codex-plugin").mkdir(parents=True)
                (folder / "app" / ".codex-plugin" / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
                (folder / "app" / "src" / "codex_auto_resume").mkdir(parents=True)
            exe = folder / "PillFirst.exe"
            built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                    "/main:CodexAutoResume.PillFirstProbe",
                                    "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                    "/reference:System.dll", "/reference:System.Drawing.dll",
                                    "/reference:System.Windows.Forms.dll",
                                    *[str(path) for path in guiscan.sources()], str(probe)],
                                   capture_output=True, timeout=600, creationflags=NO_WINDOW)
            if built.returncode != 0:
                cls.failure = built.stdout.decode("mbcs", "replace")[-3000:]
                return
            out = folder / "out.json"
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
            done = subprocess.run([str(exe), str(out), str(folder)], capture_output=True, timeout=600,
                                  creationflags=NO_WINDOW, env=environment)
            answer = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
            if done.returncode != 0 or "error" in answer or not answer:
                cls.failure = "the probe failed (exit %d): %s" % (done.returncode, answer.get("error"))
                return
            cls.answers[name] = answer

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_the_pill_is_in_the_first_painted_layout(self):
        """Fails without ShowLocalVersion: before the first state the pill has no version and is not in the row."""
        for scale, answer in self.answers["installed"].items():
            with self.subTest(scale=scale):
                first = answer["first"]
                self.assertEqual(first["text"], "0.6.24")
                self.assertTrue(first["shown"])
                self.assertIn(first["fit"], ("whole", "version"))

    def test_the_first_state_moves_neither_the_pill_nor_a_tab(self):
        for scale, answer in self.answers["installed"].items():
            with self.subTest(scale=scale):
                self.assertEqual(answer["state"]["pill"], answer["first"]["pill"])
                self.assertEqual(answer["state"]["tabs"], answer["first"]["tabs"])
                self.assertEqual(answer["state"]["text"], "0.6.24")

    def test_a_window_with_no_plugin_json_waits_for_the_state_as_before(self):
        for scale, answer in self.answers["bare"].items():
            with self.subTest(scale=scale):
                self.assertEqual(answer["first"]["text"], "")
                self.assertEqual(answer["state"]["text"], "0.6.24")


class PillFirstSourceTests(unittest.TestCase):
    def test_the_window_reads_its_version_as_it_is_built(self):
        """Before the first paint: in the constructor, once the tabs and the pill are made, not on a bridge's answer."""
        built = guiscan.read("gui/SettingsApp.cs")
        start = built.index("BuildDashboard();")
        self.assertLess(start, built.index("ShowLocalVersion(installRoot);", start))
        body = guiscan.member_body("SettingsForm", "ShowLocalVersion")
        self.assertIn('"plugin.json"', body)
        self.assertIn("InstallerFlow.VersionOf(", body)
        self.assertIn("InstallerFlow.EditionOfSource(", body)
        self.assertIn("ShowVersion(versionText,", body)


if __name__ == "__main__":
    unittest.main()
