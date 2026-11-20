r"""v0.6.24 final: a text box's own right-click menu opens where it fits - above the pointer near the window's foot.

The final's live acceptance (J12): the Custom message box in Settings > Continuation message sits near the Dashboard's
bottom edge, and its menu (EditMenu, gui/SoftEdit.cs) opened below the pointer and ran past the window onto the desktop.
EditMenu.Place now opens it below the point where its card fits between the point and the bottom of the window's client
area, and above it where it does not (EditMenu.Upward); the card is kept inside the screen's working area as every soft
menu's is (SoftMenuLayer.Place, Within), and the layer puts the card's corner at the point the menu was opened at
(SoftMenuLayer.Anchor), the caret's as well as the pointer's.

A probe compiled with the window's sources makes a window, never shown, with a text box at its foot and one at its top, at
100, 150 and 200 %, builds the box's real menu (EditMenu.Build in a SoftMenu, the window's font) and asks EditMenu.Place
where it opens from a point inside each box. Nothing is ever on screen. GUI test module: run it through gui_lock.sh.
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
    internal sealed partial class SettingsForm
    {
        internal static double TextMenuSystemScale { get { return SystemScale; } }
    }

    internal static class TextMenuProbe
    {
        static List<object> Box(Rectangle r)
        {
            return new List<object> { (double)r.X, (double)r.Y, (double)r.Width, (double)r.Height };
        }

        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            var said = new Dictionary<string, object>();
            int code = 0;
            try
            {
                Palette.AdoptDesign(null);
                Palette.Adopt("light");
                foreach (double scale in new[] { 1.0, 1.5, 2.0 })
                {
                    SettingsForm.AdoptDisplayScale(scale);
                    SettingsForm.AdoptTextSize(1.0, 1.0);
                    float factor = (float)(scale / SettingsForm.TextMenuSystemScale);
                    Font box = SystemFonts.MessageBoxFont;
                    var font = new Font(box.FontFamily, box.SizeInPoints * factor, box.Style, GraphicsUnit.Point);
                    Soft.BaseFont = font;
                    Rectangle area = Screen.PrimaryScreen.WorkingArea;
                    var form = new Form();
                    form.Font = font;
                    form.StartPosition = FormStartPosition.Manual;
                    form.FormBorderStyle = FormBorderStyle.None;
                    form.ShowInTaskbar = false;
                    int width = Math.Min(Soft.Px(1000), area.Width - 100), height = Math.Min(Soft.Px(618), area.Height - 100);
                    form.Bounds = new Rectangle(area.X + 50, area.Y + 50, width, height);
                    var foot = new SoftTextArea();
                    foot.Bounds = new Rectangle(Soft.Px(20), height - Soft.Px(70), Soft.Px(400), Soft.Px(50));
                    var top = new SoftTextArea();
                    top.Bounds = new Rectangle(Soft.Px(20), Soft.Px(20), Soft.Px(400), Soft.Px(50));
                    form.Controls.Add(foot);
                    form.Controls.Add(top);
                    IntPtr made = form.Handle;
                    var answer = new Dictionary<string, object>();
                    Rectangle window = form.RectangleToScreen(form.ClientRectangle);
                    answer["window"] = Box(window);
                    answer["area"] = Box(area);
                    foreach (KeyValuePair<string, SoftTextArea> each in new[] {
                        new KeyValuePair<string, SoftTextArea>("foot", foot), new KeyValuePair<string, SoftTextArea>("top", top) })
                    {
                        TextBoxBase text = each.Value.Box;
                        // A point in the box near its bottom, on the screen (the form's client area there, as Place reads it).
                        Point at = new Point(window.X + each.Value.Left + Soft.Px(10), window.Y + each.Value.Bottom - Soft.Px(4));
                        using (var menu = new SoftMenu())
                        {
                            menu.Font = font;
                            menu.Items.AddRange(EditMenu.Build(text));
                            Rectangle card;
                            ToolStripDropDownDirection direction = EditMenu.Place(text, menu, at, out card);
                            answer[each.Key] = new Dictionary<string, object> {
                                { "direction", direction.ToString() }, { "card", Box(card) },
                                { "at", new List<object> { (double)at.X, (double)at.Y } } };
                        }
                    }
                    form.Dispose();
                    said[scale.ToString("0.00", CultureInfo.InvariantCulture)] = answer;
                }
                var pure = new List<object>();
                var room = new Rectangle(0, 0, 1000, 600);
                foreach (int[] c in new[] { new[] { 100, 200 }, new[] { 450, 200 }, new[] { 590, 200 }, new[] { 300, 400 }, new[] { 300, 280 } })
                    pure.Add(EditMenu.Upward(c[0], c[1], room));
                said["upward"] = pure;
            }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class TextMenuFitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="car-text-menu-")
        work = Path(cls.folder.name)
        probe = work / "TextMenuProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "TextMenu.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.TextMenuProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
            done = subprocess.run([str(exe), str(out)], capture_output=True, timeout=300, creationflags=NO_WINDOW,
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

    def scales(self):
        return [(scale, answer) for scale, answer in sorted(self.answer.items()) if scale != "upward"]

    def test_a_box_at_the_windows_foot_opens_its_menu_above_the_pointer_inside_the_window(self):
        """Fails with the menu always below the point: its card runs past the window's bottom edge."""
        for scale, answer in self.scales():
            x, y, w, h = answer["foot"]["card"]
            wx, wy, ww, wh = answer["window"]
            with self.subTest(scale=scale):
                self.assertEqual(answer["foot"]["direction"], "AboveRight")
                self.assertLessEqual(y + h, answer["foot"]["at"][1], "the card's bottom at or above the point")
                self.assertGreaterEqual(y, wy)
                self.assertLessEqual(y + h, wy + wh, "inside the window")

    def test_a_box_at_the_top_opens_below_as_ever(self):
        for scale, answer in self.scales():
            x, y, w, h = answer["top"]["card"]
            with self.subTest(scale=scale):
                self.assertEqual(answer["top"]["direction"], "BelowRight")
                self.assertEqual(y, answer["top"]["at"][1])

    def test_the_card_stays_inside_the_working_area(self):
        for scale, answer in self.scales():
            ax, ay, aw, ah = answer["area"]
            for where in ("foot", "top"):
                x, y, w, h = answer[where]["card"]
                with self.subTest(scale=scale, where=where):
                    self.assertTrue(ax <= x and x + w <= ax + aw and ay <= y and y + h <= ay + ah)

    def test_the_rule(self):
        # 200 high in a window 600 high: below from 100 (it fits); above from 450 and from 590 (it does not fit below, and
        # does above); 400 high from 300: it fits neither way and there is no more room above than below - below; 200 high
        # from 280: 320 below, it fits - below.
        self.assertEqual(self.answer["upward"], [False, True, True, False, False])


class TextMenuFitsSourceTests(unittest.TestCase):
    def test_the_menu_opens_the_way_place_says_at_the_point_it_was_opened_at(self):
        body = guiscan.member_body("EditMenu", "Open")
        self.assertIn("ToolStripDropDownDirection direction = Place(box, menu, screen, out card);", body)
        self.assertIn("menu.Layer.Anchor = screen;", body)
        self.assertIn("menu.Show(box, box.PointToClient(screen), direction);", body)
        self.assertIn("Point at = Anchor ?? Cursor.Position;", guiscan.read("gui/SoftMenu.cs"))


if __name__ == "__main__":
    unittest.main()
