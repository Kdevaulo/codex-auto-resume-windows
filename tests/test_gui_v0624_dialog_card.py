r"""v0.6.24-beta.2: a dialog is its title row and ONE card - content and buttons - and its owner is dimmed while it is open.

The owner's decisions of 2026-11-16 (the design canvas, row 13):

- layout A, "한 카드에 모두": under the title row (on the dialog's ground, unchanged) one card holds the dialog's content
  AND its buttons - the buttons inside the card at its foot, right-aligned (mirrored in right to left), with the gap the
  cards keep over their buttons (SoftDialog.ButtonsAbove); nothing below the card but its ground's padding. Done once for
  every dialog in SoftDialog.Gather, which moves the rows a dialog's code docks at its top and foot into its body's card;
- no bottom Close on a dialog with nothing to answer (the Timeline, the log, the detection check, the compatibility
  report): the title row's X closes it, and Esc still does (SoftDialog.ProcessDialogKey); a dialog with an answer keeps
  its buttons;
- the dialog keeps Windows' own opening motion, and while it is open its owner is dimmed: a veil of the shadow's ink at
  about 20 % over the owner's whole window in its shape, taking no input and never activated, faded in only where motion
  is allowed, none in High Contrast, none for a dialog laid out as a child (the audit, a still); a dialog opened from a
  dialog dims only its own owner (DialogVeil).

One probe compiled with the window: the Dashboard's real dialogs built as their audit builds them (never shown), a dialog
laid out with the Dashboard's own card and button row left to right and mirrored, and SoftDialogs shown 30000 px off the
desktop with SW_SHOWNOACTIVATE over an owner shown there too (never activated, never on the screen).

GUI test module (it shows windows, off the screen): run on its own, through gui_lock.sh.
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
using System.Drawing.Drawing2D;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class CardNative
    {
        [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr window, int command);
        [DllImport("user32.dll")] internal static extern bool IsWindow(IntPtr window);
        [DllImport("user32.dll")] internal static extern bool IsWindowVisible(IntPtr window);
        [DllImport("user32.dll")] internal static extern IntPtr GetWindow(IntPtr window, int command);
        [DllImport("user32.dll")] internal static extern int GetWindowLong(IntPtr window, int index);
        [DllImport("user32.dll")] internal static extern bool GetWindowRect(IntPtr window, out Chrome.RECT rect);
        [DllImport("user32.dll")] internal static extern int GetWindowRgn(IntPtr window, IntPtr region);
        [DllImport("user32.dll")] internal static extern IntPtr SendMessage(IntPtr window, int message, IntPtr w, IntPtr l);
        [DllImport("user32.dll")] internal static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] internal static extern bool GetLayeredWindowAttributes(IntPtr window, out int key, out byte alpha, out int flags);
        [DllImport("gdi32.dll")] internal static extern IntPtr CreateRectRgn(int l, int t, int r, int b);
        [DllImport("dwmapi.dll")] internal static extern int DwmGetWindowAttribute(IntPtr window, int attribute, out Chrome.RECT value, int size);
        [DllImport("dwmapi.dll", EntryPoint = "DwmGetWindowAttribute")] internal static extern int DwmCloaked(IntPtr window, int attribute, out int value, int size);

        // DWMWA_CLOAKED: nonzero while DWM holds the window off the screen.
        internal static bool Cloaked(IntPtr h)
        {
            int value;
            return DwmCloaked(h, 14, out value, 4) == 0 && value != 0;
        }
        [DllImport("gdi32.dll")] internal static extern bool DeleteObject(IntPtr o);
        internal const int Away = -30000, SW_SHOWNOACTIVATE = 4, GW_OWNER = 4, GW_HWNDNEXT = 2, GWL_EXSTYLE = -20;

        internal static void Pump(int times)
        {
            for (int i = 0; i < times; i++) { Application.DoEvents(); Thread.Sleep(10); }
        }

        internal static List<object> Box(Rectangle r)
        {
            return new List<object> { (double)r.X, (double)r.Y, (double)r.Width, (double)r.Height };
        }

        internal static Rectangle WindowRect(IntPtr h)
        {
            Chrome.RECT r;
            GetWindowRect(h, out r);
            return Rectangle.FromLTRB(r.Left, r.Top, r.Right, r.Bottom);
        }

        // What shows of a window: its own rectangle where it has a region, Windows' visible frame otherwise.
        internal static Rectangle Shown(IntPtr h)
        {
            if (HasRegion(h)) return WindowRect(h);
            Chrome.RECT r;
            if (DwmGetWindowAttribute(h, 9, out r, Marshal.SizeOf(typeof(Chrome.RECT))) == 0)
                return Rectangle.FromLTRB(r.Left, r.Top, r.Right, r.Bottom);
            return WindowRect(h);
        }

        internal static bool HasRegion(IntPtr h)
        {
            IntPtr region = CreateRectRgn(0, 0, 0, 0);
            int kind = GetWindowRgn(h, region);
            DeleteObject(region);
            return kind > 1;
        }

        // Whether `below` comes after `above` in the z-order before `stop` does.
        internal static bool Under(IntPtr above, IntPtr below, IntPtr stop)
        {
            for (IntPtr at = GetWindow(above, GW_HWNDNEXT); at != IntPtr.Zero; at = GetWindow(at, GW_HWNDNEXT))
            {
                if (at == below) return true;
                if (at == stop) return false;
            }
            return false;
        }
    }

    internal static class DialogCardProbe
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
                Palette.AdoptDesign("soft");
                Palette.Adopt("light");
                SettingsForm.DialogCardRun(argv[1], said);
                said["veil"] = Veils();
            }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }

        static SoftDialog Plain(string text)
        {
            var d = new SoftDialog();
            d.Text = text;
            d.BackColor = Palette.Canvas;
            Soft.DialogBar(d);
            d.StartPosition = FormStartPosition.Manual;
            d.Location = new Point(CardNative.Away, CardNative.Away);
            d.ShowInTaskbar = false;
            d.ClientSize = new Size(320, 160);
            return d;
        }

        static Form Owner(bool region)
        {
            var owner = new Form();
            owner.FormBorderStyle = FormBorderStyle.None;
            owner.ShowInTaskbar = false;
            owner.StartPosition = FormStartPosition.Manual;
            owner.Location = new Point(CardNative.Away, CardNative.Away);
            owner.Size = new Size(640, 480);
            if (region)
            {
                var path = new GraphicsPath();
                path.AddEllipse(0, 0, 640, 480);
                owner.Region = new Region(path);
            }
            IntPtr h = owner.Handle;
            CardNative.ShowWindow(h, CardNative.SW_SHOWNOACTIVATE);
            CardNative.Pump(3);
            return owner;
        }

        static Dictionary<string, object> Veiled(SoftDialog dialog, Form owner)
        {
            var said = new Dictionary<string, object>();
            DialogVeil veil = dialog.Veil;
            said["veiled"] = veil != null;
            if (veil == null) return said;
            IntPtr v = veil.Handle;
            said["visible"] = CardNative.IsWindowVisible(v);
            said["owner"] = CardNative.GetWindow(v, CardNative.GW_OWNER) == owner.Handle;
            said["over"] = CardNative.WindowRect(v) == CardNative.Shown(owner.Handle);
            said["veilRect"] = CardNative.Box(CardNative.WindowRect(v));
            said["ownerRect"] = CardNative.Box(CardNative.Shown(owner.Handle));
            int ex = CardNative.GetWindowLong(v, CardNative.GWL_EXSTYLE);
            said["layered"] = (ex & 0x00080000) != 0;
            said["through"] = (ex & 0x00000020) != 0;
            said["noActivate"] = (ex & 0x08000000) != 0;
            said["hit"] = (double)CardNative.SendMessage(v, 0x0084, IntPtr.Zero, IntPtr.Zero).ToInt64();
            said["mouseActivate"] = (double)CardNative.SendMessage(v, 0x0021, owner.Handle, IntPtr.Zero).ToInt64();
            said["underDialog"] = CardNative.Under(dialog.Handle, v, owner.Handle);
            said["overOwner"] = CardNative.Under(v, owner.Handle, IntPtr.Zero);
            said["region"] = CardNative.HasRegion(v);
            said["shaped"] = veil.Shaped;
            said["full"] = (double)veil.Full;
            said["colour"] = veil.Colour.ToArgb() == DialogVeil.Ink().ToArgb();
            int key, flags;
            byte alpha;
            CardNative.GetLayeredWindowAttributes(v, out key, out alpha, out flags);
            said["alpha"] = (double)alpha;
            said["foreground"] = CardNative.GetForegroundWindow() == v;
            return said;
        }

        static Dictionary<string, object> Scene(bool region, bool contrast, bool still)
        {
            var said = new Dictionary<string, object>();
            bool was = Palette.Contrast;
            Palette.Contrast = contrast;
            try
            {
                Form owner = Owner(region);
                said["ownerRegion"] = CardNative.HasRegion(owner.Handle);
                SoftDialog dialog = Plain("A dialog over its owner");
                dialog.Owner = owner;
                IntPtr h = dialog.Handle;
                CardNative.ShowWindow(h, CardNative.SW_SHOWNOACTIVATE);
                // As it is shown, before any message is handed out: the veil on and painted at its fullest, the dialog
                // still held off the screen until it has painted.
                said["first"] = (double)(dialog.Veil == null ? -1 : dialog.Veil.Alpha);
                said["veilOnFirst"] = dialog.Veil != null && CardNative.IsWindowVisible(dialog.Veil.Handle);
                CardNative.Pump(40);
                said["open"] = Veiled(dialog, owner);
                IntPtr veil = dialog.Veil == null ? IntPtr.Zero : dialog.Veil.Handle;
                if (still)
                {
                    // A dialog opened from this one dims this one, and this one's veil stays where it was.
                    SoftDialog inner = Plain("A dialog over a dialog");
                    inner.Owner = dialog;
                    IntPtr i = inner.Handle;
                    CardNative.ShowWindow(i, CardNative.SW_SHOWNOACTIVATE);
                    CardNative.Pump(20);
                    said["inner"] = Veiled(inner, dialog);
                    said["outerKept"] = CardNative.IsWindowVisible(veil);
                    IntPtr innerVeil = inner.Veil == null ? IntPtr.Zero : inner.Veil.Handle;
                    inner.Close();
                    CardNative.Pump(5);
                    said["innerGone"] = innerVeil != IntPtr.Zero && !CardNative.IsWindow(innerVeil);
                    inner.Dispose();
                }
                dialog.Close();
                CardNative.Pump(5);
                said["gone"] = veil == IntPtr.Zero || !CardNative.IsWindow(veil);
                said["cleared"] = dialog.Veil == null;
                dialog.Dispose();
                owner.Close();
                owner.Dispose();
            }
            finally { Palette.Contrast = was; }
            return said;
        }

        static Dictionary<string, object> Child()
        {
            // A dialog laid out as a child (the layout audit, a still): no veil.
            var said = new Dictionary<string, object>();
            Form owner = Owner(false);
            SoftDialog dialog = Plain("A dialog laid out, never shown");
            dialog.TopLevel = false;
            dialog.Visible = true;
            IntPtr h = dialog.Handle;
            CardNative.Pump(3);
            said["veiled"] = dialog.Veil != null;
            dialog.Dispose();
            owner.Close();
            owner.Dispose();
            return said;
        }

        static Dictionary<string, object> Veils()
        {
            var said = new Dictionary<string, object>();
            bool reduce = Soft.ReduceMotionSetting;
            Func<bool> animates = Soft.WindowsAnimates;
            try
            {
                // Motion allowed by the probe itself, through the switch the window reads (Soft.ReduceMotion: this
                // product's setting and Windows' animation effects): the CI's runners have Windows' animation off, and
                // the veil (rightly) came at its fullest at once there (dev CI 43945024319).
                Soft.ReduceMotionSetting = false;
                Soft.WindowsAnimates = delegate { return true; };
                said["moving"] = Scene(false, false, true);
                said["region"] = Scene(true, false, false);
                said["contrast"] = Scene(false, true, false);
                // Windows' animation effects off, as on a runner: no fade.
                Soft.WindowsAnimates = delegate { return false; };
                said["windowsStill"] = Scene(false, false, false);
                // This product's own setting to reduce motion: no fade.
                Soft.WindowsAnimates = delegate { return true; };
                Soft.ReduceMotionSetting = true;
                said["still"] = Scene(false, false, false);
                // The dark theme: a stronger veil (DialogVeil.DarkStrength), of the dark shadow's ink.
                Soft.ReduceMotionSetting = false;
                Palette.Adopt("dark");
                said["dark"] = Scene(false, false, false);
                said["darkInk"] = DialogVeil.Ink().ToArgb() == Tokens.ShadowDark.ToArgb();
                Palette.Adopt("light");
            }
            finally
            {
                Soft.ReduceMotionSetting = reduce;
                Soft.WindowsAnimates = animates;
            }
            said["child"] = Child();
            said["strength"] = DialogVeil.Strength;
            said["darkStrength"] = DialogVeil.DarkStrength;
            return said;
        }
    }

    internal sealed partial class SettingsForm
    {
        private static Rectangle CardInDialog(Control control, Form dialog)
        {
            int x = 0, y = 0;
            for (Control c = control; c != null && c != dialog; c = c.Parent) { x += c.Left; y += c.Top; }
            return new Rectangle(x, y, control.Width, control.Height);
        }

        private static List<object> CardList(IEnumerable<string> lines)
        {
            var list = new List<object>();
            foreach (string line in lines) list.Add(line);
            return list;
        }

        private Dictionary<string, object> CardOf(Form dialog)
        {
            var said = new Dictionary<string, object>();
            dialog.TopLevel = false;
            Materialise(dialog);
            dialog.PerformLayout();
            var soft = (SoftDialog)dialog;
            SoftCard card = soft.BodyCard;
            said["card"] = card != null;
            if (card == null) return said;
            Control ground = card.Parent;
            Rectangle face = CardInDialog(card, dialog);
            said["face"] = CardNative.Box(face);
            said["client"] = new List<object> { (double)dialog.ClientSize.Width, (double)dialog.ClientSize.Height };
            said["padding"] = new List<object> { (double)card.Padding.Left, (double)card.Padding.Top,
                                                 (double)card.Padding.Right, (double)card.Padding.Bottom };
            said["groundBelow"] = (double)ground.Padding.Bottom;
            var others = new List<object>();
            foreach (Control child in dialog.Controls)
                if (child != soft.TitleGround && child != ground && Soft.OwnVisible(child)) others.Add(child.GetType().Name);
            said["onGround"] = others;
            var buttons = new List<object>();
            foreach (Button button in DialogButtons(dialog))
            {
                if (!Soft.OwnVisible(button)) continue;
                var one = new Dictionary<string, object>();
                one["text"] = button.Text;
                one["box"] = CardNative.Box(CardInDialog(button, dialog));
                one["inCard"] = face.Contains(CardInDialog(button, dialog));
                buttons.Add(one);
            }
            said["buttons"] = buttons;
            said["accept"] = dialog.AcceptButton != null;
            said["cancel"] = dialog.CancelButton != null;
            var findings = new List<string>();
            AuditDialogCard("probe", dialog, findings);
            said["findings"] = CardList(findings);
            return said;
        }

        // A dialog laid out as the Dashboard's are - its body on DialogBodyCard, its buttons in ButtonRow docked at its foot
        // on the ground - left to right or mirrored.
        private Dictionary<string, object> Drawn(bool mirrored)
        {
            Mirror.Window = mirrored;
            try
            {
                var dialog = new SoftDialog();
                dialog.Text = "A dialog of the Dashboard's kind";
                dialog.Font = Font;
                dialog.BackColor = Canvas;
                Soft.DialogBar(dialog);
                dialog.ClientSize = new Size(Px(420), Px(160));
                var body = new SoftStack();
                body.ColumnCount = 1;
                body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f));
                body.Controls.Add(Value("Words in the body of the dialog."));
                dialog.Controls.Add(DialogBodyCard(body));
                dialog.ClientSize += DialogCardGrowth();
                int asked = dialog.ClientSize.Height;
                FlowLayoutPanel buttons = ButtonRow();
                buttons.FlowDirection = FlowDirection.RightToLeft;
                buttons.Padding = Pad(0, 0, 16, 16);
                Button go = MakeButton("Do it", true, null);
                Button stay = MakeButton(S("action.cancel", "Cancel"), false, null);
                buttons.Controls.Add(go);
                buttons.Controls.Add(stay);
                dialog.Controls.Add(buttons);
                int before = buttons.GetPreferredSize(new Size(dialog.ClientSize.Width, 0)).Height;
                var said = CardOf(dialog);
                said["mirrored"] = Mirror.Of(dialog.Controls[0]);
                said["asked"] = (double)asked;
                said["before"] = (double)before;
                said["title"] = (double)((SoftDialog)dialog).TitleReserve;
                said["row"] = CardNative.Box(CardInDialog(buttons, dialog));
                said["rowPadding"] = new List<object> { (double)buttons.Padding.Left, (double)buttons.Padding.Top,
                                                        (double)buttons.Padding.Right, (double)buttons.Padding.Bottom };
                said["rowColour"] = buttons.BackColor.ToArgb() == Palette.Card.ToArgb();
                said["above"] = (double)Px(SoftDialog.ButtonsAbove);
                said["go"] = CardNative.Box(CardInDialog(go, dialog));
                said["stay"] = CardNative.Box(CardInDialog(stay, dialog));
                dialog.Dispose();
                return said;
            }
            finally { Mirror.Window = false; }
        }

        internal static void DialogCardRun(string dir, Dictionary<string, object> said)
        {
            var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-en.json"), Encoding.UTF8)) as Dictionary<string, object>;
            var snapshot = Json.Parse(File.ReadAllText(Path.Combine(dir, "snapshot.json"), Encoding.UTF8)) as Dictionary<string, object>;
            string nowhere = Path.Combine(dir, "nowhere");
            using (var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, null))
            {
                form.auditing = true;
                form.TopLevel = false;
                said["closeWord"] = form.S("action.close", "Close");
                var row = ((List<object>)snapshot["pending"])[0] as Dictionary<string, object>;
                var dialogs = new Dictionary<string, object>();
                using (Form d = form.BuildConversationMessage(row, "Carry on, please.")) dialogs["conversation"] = form.CardOf(d);
                using (Form d = form.BuildOnceWords(row, "Then run the tests.")) dialogs["once"] = form.CardOf(d);
                var events = new List<object>();
                var entry = new Dictionary<string, object>();
                entry["at"] = 1.8e9;
                entry["code"] = "detected";
                entry["to_code"] = "waiting_reset";
                events.Add(entry);
                using (Form d = form.BuildTimeline(row, events, null)) dialogs["timeline"] = form.CardOf(d);
                using (Form d = form.BuildLogs()) dialogs["logs"] = form.CardOf(d);
                using (Form d = form.BuildDetectionCheck()) dialogs["check"] = form.CardOf(d);
                using (Form d = form.BuildOwnReport()) dialogs["report"] = form.CardOf(d);
                using (Form d = form.BuildVersions()) dialogs["versions"] = form.CardOf(d);
                said["dialogs"] = dialogs;
                said["ltr"] = form.Drawn(false);
                said["rtl"] = form.Drawn(true);
            }
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class DialogCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="car-dialog-card-")
        work = Path(cls.folder.name)
        reply = {"ok": True, "language": "en", "strings": l10n.catalog("en"), "endonyms": dict(l10n.ENDONYMS),
                 "preference": "en", "system_language": "en"}
        (work / "strings-en.json").write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        (work / "snapshot.json").write_text(json.dumps(fullest_snapshot(time.time()), ensure_ascii=False), encoding="utf-8")
        probe = work / "DialogCardProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "DialogCard.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.DialogCardProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
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
                cls.failure = "the probe failed (exit %d): %s" % (done.returncode, cls.answer.get("error"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    @staticmethod
    def inside(box, face):
        return (box[0] >= face[0] and box[1] >= face[1] and box[0] + box[2] <= face[0] + face[2]
                and box[1] + box[3] <= face[1] + face[3])

    def test_every_dashboard_dialog_is_one_card_with_its_buttons_inside(self):
        for name, said in self.answer["dialogs"].items():
            with self.subTest(dialog=name):
                self.assertTrue(said["card"], "its content is on a card of its own")
                self.assertEqual(said["onGround"], [], "nothing but the card's ground under the title row")
                for button in said["buttons"]:
                    self.assertTrue(button["inCard"], "%s at %s is inside the card at %s" % (button["text"], button["box"], said["face"]))
                self.assertEqual(said["findings"], [], "the card audit (WindowAudit.AuditDialogCard) finds nothing")
                face, client = said["face"], said["client"]
                self.assertEqual(client[1] - (face[1] + face[3]), said["groundBelow"], "nothing under the card but its ground's padding")

    def test_a_dialog_with_nothing_to_answer_has_no_close_of_its_own(self):
        close = self.answer["closeWord"]
        for name in ("timeline", "logs", "check", "report"):
            with self.subTest(dialog=name):
                said = self.answer["dialogs"][name]
                self.assertNotIn(close, [button["text"] for button in said["buttons"]])
                self.assertFalse(said["cancel"], "no Cancel button for Esc to press: SoftDialog closes it on Esc itself")
        for name in ("timeline", "logs"):
            with self.subTest(dialog=name):
                self.assertEqual([b for b in self.answer["dialogs"][name]["buttons"] if b["text"] == close], [])
        # A dialog with an answer keeps its buttons: Cancel and the action.
        texts = [button["text"] for button in self.answer["dialogs"]["conversation"]["buttons"]]
        self.assertGreaterEqual(len(texts), 3)
        self.assertTrue(self.answer["dialogs"]["conversation"]["cancel"])
        versions = [button["text"] for button in self.answer["dialogs"]["versions"]["buttons"]]
        self.assertIn(close, versions, "Install another version answers with Install, and Close is its Cancel")
        self.assertEqual(len(versions), 2)

    def test_esc_closes_a_dialog_with_no_cancel_button(self):
        body = guiscan.member_body("SoftDialog", "ProcessDialogKey")
        self.assertIn("Keys.Escape", body)
        self.assertIn("CancelButton == null", body)
        self.assertIn("Close()", body)

    def test_the_buttons_stand_at_the_card_s_foot_right_aligned_and_mirrored(self):
        for side in ("ltr", "rtl"):
            with self.subTest(side=side):
                said = self.answer[side]
                self.assertEqual(said["mirrored"], side == "rtl")
                self.assertEqual(said["findings"], [])
                face, pad = said["face"], said["padding"]
                row = said["row"]
                self.assertEqual(row[1] + row[3], face[1] + face[3] - pad[3], "the row ends at the card's foot, inside its padding")
                self.assertEqual(said["rowPadding"], [0, said["above"], 0, 0], "ButtonsAbove over the buttons, no inset at the sides")
                self.assertTrue(said["rowColour"], "the row is on the card's colour")
                go, stay = said["go"], said["stay"]
                inner_left, inner_right = face[0] + pad[0], face[0] + face[2] - pad[2]
                if side == "ltr":
                    self.assertEqual(go[0] + go[2], inner_right, "the action is the rightmost, at the card's inner edge")
                    self.assertLess(stay[0], go[0])
                else:
                    self.assertEqual(go[0], inner_left, "mirrored: the action is the leftmost, at the card's inner edge")
                    self.assertGreater(stay[0], go[0])
                self.assertEqual(go[1] + go[3], face[1] + face[3] - pad[3])

    def test_the_body_keeps_the_height_it_was_laid_out_at(self):
        said = self.answer["ltr"]
        # Asked: body card + its growth; then the row on the ground (before), now the row in the card (ButtonsAbove + button).
        button = said["go"][3]
        self.assertEqual(said["client"][1], said["title"] + said["asked"] - said["before"] + said["above"] + button)

    def test_the_owner_is_veiled_while_the_dialog_is_open_and_not_after(self):
        for scene in ("moving", "region", "windowsStill", "still", "dark"):
            with self.subTest(scene=scene):
                said = self.answer["veil"][scene]
                veil = said["open"]
                self.assertTrue(veil["veiled"])
                self.assertTrue(veil["visible"])
                self.assertTrue(veil["owner"], "owned by the dialog's owner")
                self.assertTrue(veil["over"], "over the owner's whole window")
                self.assertTrue(veil["layered"] and veil["through"] and veil["noActivate"], "takes no input, never activates")
                self.assertEqual(veil["hit"], -1, "HTTRANSPARENT")
                self.assertEqual(veil["mouseActivate"], 3, "MA_NOACTIVATE")
                self.assertFalse(veil["foreground"])
                self.assertTrue(veil["underDialog"], "just under the dialog")
                self.assertTrue(veil["overOwner"], "over its owner")
                self.assertTrue(veil["colour"], "the shadow's ink")
                key = "darkStrength" if scene == "dark" else "strength"
                self.assertEqual(veil["full"], round(255 * self.answer["veil"][key]))
                self.assertAlmostEqual(self.answer["veil"]["strength"], 0.20, delta=0.05)
                self.assertEqual(veil["alpha"], veil["full"], "at its fullest once open")
                self.assertTrue(said["gone"], "gone as the dialog closes")
                self.assertTrue(said["cleared"])

    def test_it_takes_the_owner_s_shape(self):
        said = self.answer["veil"]["region"]
        self.assertTrue(said["ownerRegion"])
        self.assertTrue(said["open"]["shaped"] and said["open"]["region"], "the owner's own region")

    def test_the_veil_is_on_at_its_fullest_before_the_dialog_is_seen(self):
        """Live re-check 7: a fade timed on the dialog's thread came on 130-283 ms after the dialog's first frame, in one
        step. The veil is on, painted, at its fullest as the dialog is shown - motion allowed or not, Windows' animation on
        (Soft.WindowsAnimates, as the probe sets it) or off - and the dialog is held off the screen until it has painted."""
        for scene in ("moving", "windowsStill", "still", "dark"):
            with self.subTest(scene=scene):
                said = self.answer["veil"][scene]
                self.assertEqual(said["first"], said["open"]["full"], "at its fullest at once")
                self.assertTrue(said["veilOnFirst"], "on the screen as the dialog is shown")

    def test_the_dark_veil_dims_the_dark_window_as_the_light_one_does_the_light(self):
        """Live re-check 7: in dark, 20 % took the Dashboard's mean grey only from 37.5 to 32; in light from 234 to 192, a
        luminance ratio of 1.56. DarkStrength gives the dark Dashboard (37.5 over the dark shadow's ink, about 10) that ratio."""
        def lum(grey):
            c = grey / 255.0
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        light = lum(234) / lum(192)
        strength = self.answer["veil"]["darkStrength"]
        dark = lum(37.5) / lum(37.5 * (1 - strength) + 10 * strength)
        self.assertAlmostEqual(dark, light, delta=0.05, msg="the dark ratio %.3f against the light %.3f" % (dark, light))
        said = self.answer["veil"]["dark"]["open"]
        self.assertEqual(said["full"], round(255 * strength))
        self.assertTrue(said["colour"] and self.answer["veil"]["darkInk"], "the dark shadow's ink")

    def test_none_in_high_contrast_nor_for_a_dialog_laid_out_as_a_child(self):
        self.assertFalse(self.answer["veil"]["contrast"]["open"]["veiled"])
        self.assertFalse(self.answer["veil"]["child"]["veiled"])

    def test_a_dialog_from_a_dialog_dims_only_its_own_owner(self):
        said = self.answer["veil"]["moving"]
        inner = said["inner"]
        self.assertTrue(inner["veiled"] and inner["owner"], "owned by the dialog it was opened from")
        self.assertEqual(inner["veilRect"], inner["ownerRect"], "over what shows of that dialog")
        self.assertTrue(said["outerKept"], "the first veil stays over the window")
        self.assertTrue(said["innerGone"])


if __name__ == "__main__":
    unittest.main()
