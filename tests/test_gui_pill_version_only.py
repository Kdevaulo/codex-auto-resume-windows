r"""v0.6.24: the version's pill shows the version alone and tells the advanced edition by its ink (the owner, 2026-11-18,
picked from real renders).

- The label's text is the version alone in both editions - never the edition's word, High Contrast too - and a screen
  reader is still told both ("v0.6.24 Advanced").
- The advanced edition's ink is its own named colour (brand.tokens.EDITION_INK: #3F68B0 light, #9AB8EE dark, Brand.EditionInk),
  the standard edition's the secondary ink; the pill's fill and edge are the standard ones in both (Palette.Raised, Line).
- The version is centred on the pill by its ink - digit tops to baseline - within half a device pixel, at 100, 150 and
  200 %: its line box centred left 9 px above the ink and 7 below at 150 %.

A probe compiled with the window builds it never shown (TopLevel = false, as LayoutAudit does). GUI test module: run on
its own, through gui_lock.sh.
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
from codex_auto_resume.brand import tokens  # noqa: E402

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

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
    internal static class VersionOnlyProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { SettingsForm.VersionOnlyRun(argv[1], said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        internal static void VersionOnlyRun(string dir, Dictionary<string, object> said)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(null);
            var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-en.json"), Encoding.UTF8)) as Dictionary<string, object>;
            System.Reflection.FieldInfo fallback = typeof(Control).GetField("defaultFont",
                System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
            Font defaultBefore = Control.DefaultFont;
            foreach (string theme in new[] { "light", "dark" })
                foreach (double scale in new[] { 1.0, 1.5, 2.0 })
                    foreach (string edition in new[] { "advanced", "standard" })
                    {
                        Palette.Adopt(theme);
                        AdoptDisplayScale(scale);
                        AdoptTextSize(1.0, 1.0);
                        float factor = (float)(scale / SystemScale);
                        Font box = SystemFonts.MessageBoxFont;
                        var windowFont = new Font(box.FontFamily, box.SizeInPoints * factor, box.Style, GraphicsUnit.Point);
                        if (fallback != null)
                            fallback.SetValue(null, new Font(defaultBefore.FontFamily, defaultBefore.SizeInPoints * factor, defaultBefore.Style, GraphicsUnit.Point));
                        Mirror.Window = false;
                        string nowhere = Path.Combine(dir, "nowhere");
                        var at = new Dictionary<string, object>();
                        using (var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, windowFont))
                        {
                            form.auditing = true;
                            form.TopLevel = false;
                            form.MinimumSize = Size.Empty;
                            form.ClientSize = form.OpeningClient;
                            form.ShowPage("overview");
                            form.ShowVersion(form.versionText, new Dictionary<string, object> { { "version", "0.6.24" }, { "edition", edition } });
                            Materialise(form);
                            form.PerformLayout();
                            VersionPill pill = form.versionPill;
                            at["fit"] = form.PillFit;
                            at["text"] = form.versionText.Text ?? "";
                            at["name"] = pill.AccessibleName ?? "";
                            at["edition"] = form.S("edition." + edition, edition);
                            at["ink"] = (double)(form.versionText.ForeColor.ToArgb() & 0xFFFFFF);
                            at["secondary"] = (double)(Palette.Secondary.ToArgb() & 0xFFFFFF);
                            at["back"] = (double)(pill.BackColor.ToArgb() & 0xFFFFFF);
                            at["raised"] = (double)(Palette.Raised.ToArgb() & 0xFFFFFF);
                            // The pill as it is drawn, read row by row across its words: where the ink is.
                            using (var picture = new Bitmap(pill.Width, pill.Height))
                            {
                                pill.DrawToBitmap(picture, new Rectangle(Point.Empty, pill.Size));
                                Rectangle words = pill.Label.Bounds;
                                int ground = Palette.Raised.ToArgb(), first = -1, last = -1;
                                for (int row = 2; row < pill.Height - 2; row++)
                                    for (int column = words.Left; column < words.Right; column++)
                                    {
                                        Color c = picture.GetPixel(column, row);
                                        if (Math.Abs(c.R - Palette.Raised.R) + Math.Abs(c.G - Palette.Raised.G) + Math.Abs(c.B - Palette.Raised.B) > 60)
                                        {
                                            if (first < 0) first = row;
                                            last = row;
                                            break;
                                        }
                                    }
                                at["inkRows"] = new List<object> { (double)first, (double)last };
                                at["height"] = (double)pill.Height;
                                // The edge: the pixel at the middle of its top, the standard hairline.
                                Color edge = picture.GetPixel(pill.Width / 2, 0);
                                at["edgeTop"] = (double)(edge.ToArgb() & 0xFFFFFF);
                            }
                        }
                        said[theme + " " + scale.ToString("0.0", CultureInfo.InvariantCulture) + " " + edition] = at;
                    }
            if (fallback != null) fallback.SetValue(null, defaultBefore);
        }
    }
}
"""


def colour(hex_colour):
    return int(hex_colour[1:], 16)


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class VersionOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        reply = {"ok": True, "language": "en", "strings": l10n.catalog("en"), "endonyms": dict(l10n.ENDONYMS),
                 "preference": "en", "system_language": "en"}
        (work / "strings-en.json").write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        probe = work / "VersionOnlyProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "VersionOnly.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.VersionOnlyProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
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

    def test_the_version_alone_and_the_edition_told_to_a_screen_reader(self):
        for where, at in self.answer.items():
            with self.subTest(where):
                self.assertEqual(at["fit"], "whole")
                self.assertEqual(at["text"], "v0.6.24", "the version alone, never the edition's word")
                if where.endswith("advanced"):
                    self.assertEqual(at["name"], "v0.6.24 " + at["edition"], "a screen reader is told both")
                else:
                    self.assertEqual(at["name"], "v0.6.24")

    def test_the_advanced_edition_is_told_by_its_ink_alone(self):
        for where, at in self.answer.items():
            theme = where.split()[0]
            with self.subTest(where):
                if where.endswith("advanced"):
                    self.assertEqual(at["ink"], colour(tokens.EDITION_INK[theme]))
                else:
                    self.assertEqual(at["ink"], at["secondary"], "the standard edition keeps the secondary ink")
                self.assertEqual(at["back"], at["raised"], "the standard fill")
        for theme in ("light", "dark"):
            for scale in ("1.0", "1.5", "2.0"):
                advanced, standard = self.answer["%s %s advanced" % (theme, scale)], self.answer["%s %s standard" % (theme, scale)]
                with self.subTest(theme=theme, scale=scale):
                    self.assertEqual(advanced["edgeTop"], standard["edgeTop"], "the standard edge")

    def test_the_version_is_centred_by_its_ink(self):
        for where, at in self.answer.items():
            first, last = at["inkRows"]
            with self.subTest(where):
                self.assertGreaterEqual(first, 0, "ink found")
                above, below = first, at["height"] - 1 - last
                self.assertLessEqual(abs(above - below), 1, "within half a device pixel: %s above, %s below" % (above, below))


class VersionOnlySourceTests(unittest.TestCase):
    def test_the_ink_is_a_named_theme_colour(self):
        self.assertEqual(tokens.EDITION_INK, {"light": "#3F68B0", "dark": "#9AB8EE"})
        ink = guiscan.member_body("SettingsForm", "VersionInk")
        self.assertIn("Tokens.Dark ? Brand.Dark.EditionInk() : Brand.EditionInk()", ink)
        self.assertIn("Palette.Contrast ? Secondary", ink)


if __name__ == "__main__":
    unittest.main()
