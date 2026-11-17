r"""v0.6.24-beta.2: a dialog's title is a row on the dialog's own ground, not a card (the owner's choice B, 2026-11-16).

In the beta every dialog of ours (SoftDialog) had its title words and caption buttons in a card of their own: 16 px of
ground above it and a card 46 px high, 62 logical px of the dialog's height, which made the dialogs 51 px taller than
with Windows' title bar and lowered the largest text size the window opens at (TextScale.Fitting). From the owner's
mockups he chose the title with no card: the words and the buttons straight on the dialog's ground, 8 px below its top,
one row as tall as a caption button (26), 8 px above its first card - 42 logical px in all - the words one type step under
a card's title (RoleFont "heading", where the card used "title") and 6 px in from the cards' outer edge, the buttons at
the row's end with the card's inset.

A probe compiled with the window builds a SoftDialog, never shown, as the chrome window test does - asked for 600 by 400,
a body docked to fill and a row docked at its foot - at 100 % and at 150 %, left to right and mirrored, and asks:

- the title takes 2 x 8 + 26 logical px (42 at 100 %, 63 at 150 %) where the card took 62, and the dialog is what it
  asked plus that;
- nothing in the title is a card: the row and its words are on the ground's own colour, and the caption buttons show
  the ground at rest - in High Contrast too, where a card's buttons show the person's Window colour;
- the row's words are the heading role, start 6 px in from the row (from its right, mirrored) and end before the
  buttons; the buttons stand centred in the row, and (the owner, 2026-11-16, canvas row 16) the Close cross's far end as
  far in from the dialog's end edge as the title's first letter is from its start edge, within a pixel, mirrored too;
- the row's ground, the strip above it and the words drag the dialog (HTCAPTION); its own body is the client's;
- the title audit (WindowAudit.AuditTitleRow) finds nothing in each.

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

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HTCLIENT, HTCAPTION = 1, 2
SCALES = (1.0, 1.5)

PROBE = r"""
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class TitleRowProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { SettingsForm.TitleRowRun(said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        private static List<object> RowBox(Rectangle r)
        {
            return new List<object> { (double)r.X, (double)r.Y, (double)r.Width, (double)r.Height };
        }

        private static Rectangle RowInDialog(Control control, Form dialog)
        {
            int x = 0, y = 0;
            for (Control c = control; c != null && c != dialog; c = c.Parent) { x += c.Left; y += c.Top; }
            return new Rectangle(x, y, control.Width, control.Height);
        }

        private static bool RowHasCard(Control control)
        {
            foreach (Control child in control.Controls)
                if (child is SoftCard || RowHasCard(child)) return true;
            return false;
        }

        private static Dictionary<string, object> TitleRowDialog(bool mirrored, bool contrast)
        {
            var said = new Dictionary<string, object>();
            Mirror.Window = mirrored;
            bool was = Palette.Contrast;
            Palette.Contrast = contrast;
            Palette.Adopt("light");
            try
            {
                using (var d = new SoftDialog())
                {
                    d.Text = "A dialog with a title of its own";
                    d.BackColor = Palette.Canvas;
                    Soft.DialogBar(d);
                    // v0.6.24-beta.2: it minimises, so its minimise shows; it cannot be resized, so no maximise for all
                    // MaximizeBox asks (the owner's rule: hide what cannot work).
                    d.FormBorderStyle = FormBorderStyle.FixedDialog;
                    d.MinimizeBox = true;
                    d.MaximizeBox = true;
                    d.ShowInTaskbar = false;
                    d.ClientSize = new Size(600, 400);
                    var body = new Panel();
                    body.Dock = DockStyle.Fill;
                    var foot = new Panel();
                    foot.Dock = DockStyle.Bottom;
                    foot.Height = 50;
                    d.Controls.Add(body);
                    d.Controls.Add(foot);
                    d.TopLevel = false;
                    d.CreateControl();
                    IntPtr h = d.Handle;
                    d.PerformLayout();
                    Application.DoEvents();
                    Panel row = d.TitleRow;
                    Label words = d.TitleWords;
                    ChromeHost caption = d.CaptionHost;
                    said["reserve"] = (double)d.TitleReserve;
                    said["client"] = new List<object> { (double)d.ClientSize.Width, (double)d.ClientSize.Height };
                    said["strip"] = RowBox(d.TitleGround.Bounds);
                    said["row"] = RowBox(row.Bounds);
                    said["words"] = RowBox(RowInDialog(words, d));
                    said["body"] = RowBox(body.Bounds);
                    said["card"] = RowHasCard(d.TitleGround) || row is SoftCard;
                    said["rowGround"] = row.BackColor.ToArgb() == d.BackColor.ToArgb();
                    said["wordsGround"] = words.BackColor.ToArgb() == d.BackColor.ToArgb();
                    said["face"] = caption.Face.ToArgb() == d.BackColor.ToArgb();
                    said["heading"] = words.Font.Equals(Soft.RoleFont("heading"));
                    // What Windows' text drawing keeps before the first letter: half of what its padding adds.
                    said["lead"] = (double)((TextRenderer.MeasureText("Ag", words.Font, new Size(int.MaxValue, 0), TextFormatFlags.SingleLine).Width -
                        TextRenderer.MeasureText("Ag", words.Font, new Size(int.MaxValue, 0), TextFormatFlags.SingleLine | TextFormatFlags.NoPadding).Width) / 2);
                    said["line"] = (double)Math.Max(words.Font.Height,
                        TextRenderer.MeasureText("Ag", words.Font, new Size(int.MaxValue, 0), TextFormatFlags.NoPrefix).Height);
                    said["mirrored"] = Mirror.Of(row);
                    var buttons = new Dictionary<string, object>();
                    buttons["close"] = RowBox(RowInDialog(caption.CloseButton, d));
                    buttons["maximize"] = RowBox(RowInDialog(caption.MaximizeButton, d));
                    buttons["minimize"] = RowBox(RowInDialog(caption.MinimizeButton, d));
                    said["minimizeShown"] = Soft.OwnVisible(caption.MinimizeButton);
                    said["maximizeShown"] = Soft.OwnVisible(caption.MaximizeButton);
                    said["buttons"] = buttons;
                    ChromeLayout layout = caption.Layout();
                    Rectangle r = row.Bounds, w = RowInDialog(words, d);
                    var hits = new Dictionary<string, object>();
                    hits["strip"] = (double)Chrome.Hit(new Point(300, Soft.Px(SoftDialog.TitleAbove) / 2), layout);
                    hits["rowStart"] = (double)Chrome.Hit(new Point(mirrored ? r.Right - 2 : r.Left + 2, r.Top + r.Height / 2), layout);
                    hits["words"] = (double)Chrome.Hit(new Point(w.Left + w.Width / 2, w.Top + w.Height / 2), layout);
                    hits["body"] = (double)Chrome.Hit(new Point(300, d.TitleReserve + 100), layout);
                    said["hits"] = hits;
                    var findings = new List<string>();
                    AuditTitleRow("probe", d, findings);
                    said["findings"] = HeldListRow(findings);
                }
            }
            finally
            {
                Palette.Contrast = was;
                Palette.Adopt("light");
                Mirror.Window = false;
            }
            return said;
        }

        private static List<object> HeldListRow(List<string> lines)
        {
            var list = new List<object>();
            foreach (string line in lines) list.Add(line);
            return list;
        }

        internal static void TitleRowRun(Dictionary<string, object> said)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(null);
            Palette.Adopt("light");
            Font message = SystemFonts.MessageBoxFont;
            foreach (double scale in new[] { 1.0, 1.5 })
            {
                AdoptDisplayScale(scale);
                float factor = (float)(scale / SystemScale);
                Soft.BaseFont = new Font(message.FontFamily, message.SizeInPoints * factor, message.Style, GraphicsUnit.Point);
                var at = new Dictionary<string, object>();
                at["ltr"] = TitleRowDialog(false, false);
                at["rtl"] = TitleRowDialog(true, false);
                at["contrast"] = TitleRowDialog(false, true);
                said[scale.ToString("0.00", System.Globalization.CultureInfo.InvariantCulture)] = at;
            }
        }
    }
}
"""


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class DialogTitleRowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        probe = work / "TitleRowProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "TitleRow.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.TitleRowProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
            done = subprocess.run([str(exe), str(out)], capture_output=True, timeout=600, creationflags=NO_WINDOW,
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

    def each(self):
        for scale in SCALES:
            for kind in ("ltr", "rtl", "contrast"):
                yield scale, kind, self.answer["%.2f" % scale][kind]

    def test_the_title_adds_42_logical_px_where_the_card_added_62(self):
        for scale, kind, said in self.each():
            with self.subTest(scale=scale, kind=kind):
                px = lambda n: int(round(n * scale))
                row = max(int(said["line"]), px(26))
                self.assertEqual(said["reserve"], 2 * px(8) + row)
                self.assertEqual(said["client"], [600, 400 + said["reserve"]])
                self.assertEqual(said["strip"], [0, 0, 600, said["reserve"]])
                self.assertEqual(said["row"], [px(16), px(8), 600 - 2 * px(16), row])
                self.assertEqual(said["body"][1], said["reserve"], "the dialog's own layout below it, as it was")
                if said["line"] <= px(26):
                    self.assertEqual(said["reserve"], {1.0: 42, 1.5: 63}[scale])

    def test_nothing_in_the_title_is_a_card_it_is_the_ground(self):
        for scale, kind, said in self.each():
            with self.subTest(scale=scale, kind=kind):
                self.assertFalse(said["card"], "no SoftCard in the title")
                self.assertTrue(said["rowGround"], "the row is the dialog's ground")
                self.assertTrue(said["wordsGround"], "its words are on the ground")
                self.assertTrue(said["face"], "the buttons show the ground at rest, in High Contrast too")

    def test_the_words_are_a_heading_6_px_in_and_the_buttons_centred_at_the_row_s_end(self):
        for scale, kind, said in self.each():
            with self.subTest(scale=scale, kind=kind):
                px = lambda n: int(round(n * scale))
                self.assertTrue(said["heading"], "one type step under a card's title")
                x, y, width, height = said["row"]
                buttons = said["buttons"]
                words = said["words"]
                self.assertTrue(said["minimizeShown"], "it minimises")
                self.assertFalse(said["maximizeShown"], "no maximise where it cannot be resized (v0.6.24-beta.2)")
                for name, box in buttons.items():
                    if name == "maximize":
                        continue
                    self.assertEqual(box[1], y + (height - box[3]) // 2, name + " centred in the row")
                    self.assertEqual(box[3], px(26))
                # The Close cross's ink across its button (CaptionButton.Glyph): strokes from 1 to 9 of a 10 px box centred
                # in it, with round caps half the 1.3 px stroke past their ends.
                close = buttons["close"]
                ox = round((close[2] - 10 * scale) / 2)
                cap = max(1.0, 1.3 * scale) / 2
                ink_left, ink_right = close[0] + ox + scale - cap, close[0] + ox + 9 * scale + cap
                if kind == "rtl":
                    self.assertTrue(said["mirrored"])
                    letter = 600 - (words[0] + words[2] - said["lead"])
                    self.assertLessEqual(abs(ink_left - letter), 1.5,
                                         "mirrored: the cross's left end as far from the left edge as the title from the right")
                    self.assertLess(buttons["close"][0], buttons["minimize"][0])
                    self.assertEqual(x + width - (words[0] + words[2]), px(6), "the words start 6 px in from the right")
                    self.assertGreaterEqual(words[0] - (buttons["minimize"][0] + buttons["minimize"][2]), px(8))
                else:
                    self.assertFalse(said["mirrored"])
                    letter = words[0] + said["lead"]
                    self.assertLessEqual(abs((600 - ink_right) - letter), 1.5,
                                         "the cross's right end as far from the right edge as the title's first letter from the left")
                    self.assertLess(buttons["minimize"][0], buttons["close"][0])
                    self.assertEqual(words[0] - x, px(6), "the words start 6 px in")
                    self.assertGreaterEqual(buttons["minimize"][0] - (words[0] + words[2]), px(8))

    def test_the_row_drags_the_dialog_and_its_body_is_the_client_s(self):
        for scale, kind, said in self.each():
            with self.subTest(scale=scale, kind=kind):
                hits = said["hits"]
                self.assertEqual(hits["strip"], HTCAPTION, "the ground above the row")
                self.assertEqual(hits["rowStart"], HTCAPTION, "the row's own ground")
                self.assertEqual(hits["words"], HTCAPTION, "the title's words")
                self.assertEqual(hits["body"], HTCLIENT)

    def test_the_title_audit_holds_the_row(self):
        for scale, kind, said in self.each():
            with self.subTest(scale=scale, kind=kind):
                self.assertEqual(said["findings"], [])


if __name__ == "__main__":
    unittest.main()
